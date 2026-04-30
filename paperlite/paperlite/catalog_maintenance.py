from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from paperlite.config import runtime_config
from paperlite.identity import normalize_source
from paperlite.sources import (
    FEED_ENDPOINT_MODES,
    IMPLEMENTED_ENDPOINT_MODES,
    clear_catalog_cache,
    endpoint_config_from_dict,
    is_runnable_endpoint,
    normalize_endpoint_mode,
)
from paperlite.taxonomy import Taxonomy, load_taxonomy

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ALLOWED_STATUSES = {"active", "candidate", "temporarily_unavailable"}
ALLOWED_ENDPOINT_MODES = IMPLEMENTED_ENDPOINT_MODES | {"manual"}


@dataclass(frozen=True)
class CatalogIssue:
    severity: str
    code: str
    message: str
    item: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.item:
            payload["item"] = self.item
        return payload


@dataclass(frozen=True)
class CatalogValidationResult:
    counts: dict[str, int | str]
    errors: tuple[CatalogIssue, ...]
    warnings: tuple[CatalogIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "counts": dict(self.counts),
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }

    def to_markdown(self) -> str:
        lines = [
            "# PaperLite Catalog Validation",
            "",
            f"Status: {'OK' if self.ok else 'FAILED'}",
            f"- sources: {self.counts.get('source_count', 0)}",
            f"- endpoints: {self.counts.get('endpoint_count', 0)}",
            f"- runnable endpoints: {self.counts.get('runnable_endpoint_count', 0)}",
            f"- errors: {len(self.errors)}",
            f"- warnings: {len(self.warnings)}",
        ]
        if self.errors:
            lines.extend(["", "## Errors"])
            lines.extend(_issue_markdown(issue) for issue in self.errors)
        if self.warnings:
            lines.extend(["", "## Warnings"])
            lines.extend(_issue_markdown(issue) for issue in self.warnings)
        return "\n".join(lines)


@dataclass(frozen=True)
class AddSourceResult:
    source_entry: dict[str, Any]
    endpoint_entry: dict[str, Any]
    source_yaml: str
    endpoint_yaml: str
    validation: CatalogValidationResult
    wrote: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "wrote": self.wrote,
            "source_entry": dict(self.source_entry),
            "endpoint_entry": dict(self.endpoint_entry),
            "source_yaml": self.source_yaml,
            "endpoint_yaml": self.endpoint_yaml,
            "validation": self.validation.to_dict(),
        }

    def to_markdown(self) -> str:
        action = "wrote to catalog" if self.wrote else "dry-run only; use --write to apply"
        return "\n".join(
            [
                "# PaperLite Add Source",
                "",
                f"Status: {action}",
                "",
                "## sources.yaml",
                "```yaml",
                self.source_yaml.rstrip(),
                "```",
                "",
                "## endpoints.yaml",
                "```yaml",
                self.endpoint_yaml.rstrip(),
                "```",
                "",
                self.validation.to_markdown(),
            ]
        )


def _issue_markdown(issue: CatalogIssue) -> str:
    target = f" `{issue.item}`" if issue.item else ""
    return f"- `{issue.code}`{target}: {issue.message}"


def _catalog_paths(
    sources_path: str | Path | None = None,
    endpoints_path: str | Path | None = None,
    taxonomy_path: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    config = runtime_config()
    return (
        Path(sources_path) if sources_path else config.sources_path,
        Path(endpoints_path) if endpoints_path else config.endpoints_path,
        Path(taxonomy_path) if taxonomy_path else config.taxonomy_path,
    )


def _load_yaml_items(path: Path, section: str) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    items = data.get(section) or []
    if not isinstance(items, list):
        raise ValueError(f"{path.name} must contain a list under '{section}'")
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path.name} {section}[{index}] must be a mapping")
        out.append(dict(item))
    return out


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _stable_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _alias_key(value: str) -> str:
    return " ".join(str(value).replace("_", " ").replace("-", " ").strip().lower().split())


def _canonical_discipline(value: str, taxonomy: Taxonomy) -> str | None:
    key = _alias_key(value)
    if key in taxonomy.ignored_discipline_terms:
        return None
    compact_key = key.replace(" ", "")
    canonical = taxonomy.discipline_aliases.get(key) or taxonomy.discipline_aliases.get(compact_key)
    if canonical and canonical in taxonomy.discipline_by_name:
        return canonical
    raw_key = _stable_key(value)
    record = taxonomy.discipline_by_key.get(raw_key)
    return str(record["name"]) if record else None


def _normalized_url(value: Any) -> str:
    return str(value or "").strip()


def _key_issue(section: str, key: str, index: int) -> CatalogIssue | None:
    if not key:
        return CatalogIssue("error", "missing_key", f"{section}[{index}] is missing key", f"{section}[{index}]")
    if not KEY_RE.fullmatch(key):
        return CatalogIssue("error", "invalid_key", "key must match [a-z0-9][a-z0-9_-]*", key)
    return None


def validate_catalog(
    *,
    sources_path: str | Path | None = None,
    endpoints_path: str | Path | None = None,
    taxonomy_path: str | Path | None = None,
) -> CatalogValidationResult:
    source_path, endpoint_path, taxonomy_file = _catalog_paths(sources_path, endpoints_path, taxonomy_path)
    errors: list[CatalogIssue] = []
    warnings: list[CatalogIssue] = []

    try:
        taxonomy = load_taxonomy(taxonomy_file)
    except Exception as exc:
        return CatalogValidationResult(
            counts={"source_count": 0, "endpoint_count": 0, "runnable_endpoint_count": 0},
            errors=(CatalogIssue("error", "taxonomy_invalid", str(exc), str(taxonomy_file)),),
            warnings=(),
        )

    try:
        source_items = _load_yaml_items(source_path, "sources")
    except Exception as exc:
        return CatalogValidationResult(
            counts={"source_count": 0, "endpoint_count": 0, "runnable_endpoint_count": 0},
            errors=(CatalogIssue("error", "sources_invalid", str(exc), str(source_path)),),
            warnings=(),
        )
    try:
        endpoint_items = _load_yaml_items(endpoint_path, "endpoints")
    except Exception as exc:
        return CatalogValidationResult(
            counts={"source_count": len(source_items), "endpoint_count": 0, "runnable_endpoint_count": 0},
            errors=(CatalogIssue("error", "endpoints_invalid", str(exc), str(endpoint_path)),),
            warnings=(),
        )

    source_keys: set[str] = set()
    endpoint_keys: set[str] = set()
    urls_by_value: dict[str, list[str]] = {}
    runnable_endpoint_count = 0

    for index, item in enumerate(source_items, start=1):
        key = normalize_source(str(item.get("key") or "").strip())
        if issue := _key_issue("sources", key, index):
            errors.append(issue)
            continue
        if key in source_keys:
            errors.append(CatalogIssue("error", "duplicate_source_key", "source key is duplicated", key))
        source_keys.add(key)

        if not str(item.get("name") or "").strip():
            errors.append(CatalogIssue("error", "missing_source_name", "source is missing name", key))

        source_kind = _stable_key(item.get("source_kind") or item.get("type"))
        if not source_kind:
            errors.append(CatalogIssue("error", "missing_source_kind", "source is missing source_kind", key))
        elif source_kind not in taxonomy.source_kind_by_key:
            errors.append(CatalogIssue("error", "invalid_source_kind", f"unknown source_kind: {source_kind}", key))

        status = str(item.get("status") or "active").strip()
        if status not in ALLOWED_STATUSES:
            errors.append(CatalogIssue("error", "invalid_source_status", f"unknown source status: {status}", key))

        disciplines = _as_list(item.get("disciplines"))
        topics = _as_list(item.get("topics"))
        canonical_count = 0
        for discipline in disciplines:
            if _canonical_discipline(discipline, taxonomy) is None:
                errors.append(CatalogIssue("error", "invalid_discipline", f"unknown discipline: {discipline}", key))
            else:
                canonical_count += 1
        if status == "active" and not disciplines:
            for topic in topics:
                if _canonical_discipline(topic, taxonomy) is not None:
                    canonical_count += 1
            if not canonical_count:
                warnings.append(
                    CatalogIssue("warning", "missing_disciplines", "source has no canonical disciplines in disciplines or topics", key)
                )

    for index, item in enumerate(endpoint_items, start=1):
        key = normalize_source(str(item.get("key") or "").strip())
        if issue := _key_issue("endpoints", key, index):
            errors.append(issue)
            continue
        if key in endpoint_keys:
            errors.append(CatalogIssue("error", "duplicate_endpoint_key", "endpoint key is duplicated", key))
        endpoint_keys.add(key)

        source_key = normalize_source(str(item.get("source_key") or item.get("source") or "").strip())
        if not source_key:
            errors.append(CatalogIssue("error", "missing_endpoint_source_key", "endpoint is missing source_key", key))
        elif source_key not in source_keys:
            errors.append(CatalogIssue("error", "unknown_endpoint_source", f"endpoint source_key does not exist: {source_key}", key))

        mode = normalize_endpoint_mode(str(item.get("mode") or item.get("access_mode") or item.get("method") or ""))
        if not mode:
            errors.append(CatalogIssue("error", "missing_endpoint_mode", "endpoint is missing mode", key))
        elif mode not in ALLOWED_ENDPOINT_MODES:
            errors.append(CatalogIssue("error", "invalid_endpoint_mode", f"unsupported endpoint mode: {mode}", key))

        enabled = _as_bool(item.get("enabled"), default=True)
        status = str(item.get("status") or "active").strip()
        if status not in ALLOWED_STATUSES:
            errors.append(CatalogIssue("error", "invalid_endpoint_status", f"unknown endpoint status: {status}", key))
        if not enabled and status == "active":
            errors.append(CatalogIssue("error", "disabled_active_endpoint", "disabled endpoint must use candidate or temporarily_unavailable status", key))
        if enabled and status != "active":
            errors.append(CatalogIssue("error", "enabled_unavailable_endpoint", "non-active endpoint must set enabled: false", key))

        url = _normalized_url(item.get("url"))
        if mode in FEED_ENDPOINT_MODES and enabled and status == "active" and not url:
            errors.append(CatalogIssue("error", "missing_endpoint_url", "active feed endpoint is missing url", key))
        if url and mode in FEED_ENDPOINT_MODES and enabled and status == "active":
            urls_by_value.setdefault(url, []).append(key)

        try:
            endpoint = endpoint_config_from_dict(item)
            if is_runnable_endpoint(endpoint):
                runnable_endpoint_count += 1
        except Exception:
            pass

    for url, keys in sorted(urls_by_value.items()):
        if len(keys) > 1:
            warnings.append(CatalogIssue("warning", "duplicate_endpoint_url", f"URL is reused by {', '.join(keys)}", url))

    counts: dict[str, int | str] = {
        "source_count": len(source_items),
        "endpoint_count": len(endpoint_items),
        "runnable_endpoint_count": runnable_endpoint_count,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return CatalogValidationResult(counts=counts, errors=tuple(errors), warnings=tuple(warnings))


def _dump_yaml_item(item: dict[str, Any]) -> str:
    return yaml.safe_dump([item], allow_unicode=True, sort_keys=False)


def _append_yaml_item(path: Path, section: str, item_yaml: str) -> None:
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            text = f"{section}:\n"
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text + item_yaml, encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{section}:\n{item_yaml}", encoding="utf-8")


def _raise_if_issues(issues: list[CatalogIssue]) -> None:
    if issues:
        details = "; ".join(f"{issue.code}: {issue.message}{f' ({issue.item})' if issue.item else ''}" for issue in issues)
        raise ValueError(details)


def add_feed_source(
    *,
    key: str,
    name: str,
    kind: str,
    discipline: str,
    url: str,
    publisher: str | None = None,
    homepage: str | None = None,
    status: str = "active",
    origin: str | None = "manual",
    mode: str = "rss",
    write: bool = False,
    sources_path: str | Path | None = None,
    endpoints_path: str | Path | None = None,
    taxonomy_path: str | Path | None = None,
) -> AddSourceResult:
    source_path, endpoint_path, taxonomy_file = _catalog_paths(sources_path, endpoints_path, taxonomy_path)
    taxonomy = load_taxonomy(taxonomy_file)
    source_items = _load_yaml_items(source_path, "sources")
    endpoint_items = _load_yaml_items(endpoint_path, "endpoints")

    source_key = normalize_source(str(key or "").strip())
    endpoint_key = source_key
    endpoint_mode = normalize_endpoint_mode(mode) or ""
    source_kind = _stable_key(kind)
    endpoint_status = str(status or "active").strip()
    feed_url = _normalized_url(url)
    disciplines = _as_list(discipline)

    issues: list[CatalogIssue] = []
    if issue := _key_issue("sources", source_key, 1):
        issues.append(issue)
    if not str(name or "").strip():
        issues.append(CatalogIssue("error", "missing_source_name", "source name is required", source_key or None))
    if source_kind not in taxonomy.source_kind_by_key:
        issues.append(CatalogIssue("error", "invalid_source_kind", f"unknown source_kind: {source_kind}", source_key or None))
    if endpoint_mode not in FEED_ENDPOINT_MODES:
        issues.append(CatalogIssue("error", "invalid_endpoint_mode", "add-source only supports rss, atom, or feed", source_key or None))
    if endpoint_status not in ALLOWED_STATUSES:
        issues.append(CatalogIssue("error", "invalid_endpoint_status", f"unknown endpoint status: {endpoint_status}", source_key or None))
    if not feed_url:
        issues.append(CatalogIssue("error", "missing_endpoint_url", "url is required", source_key or None))
    if not disciplines:
        issues.append(CatalogIssue("error", "missing_disciplines", "at least one discipline is required", source_key or None))
    canonical_disciplines = []
    for value in disciplines:
        canonical = _canonical_discipline(value, taxonomy)
        if canonical is None:
            issues.append(CatalogIssue("error", "invalid_discipline", f"unknown discipline: {value}", source_key or None))
        else:
            canonical_disciplines.append(canonical)

    existing_source_keys = {normalize_source(str(item.get("key") or "")) for item in source_items}
    existing_endpoint_keys = {normalize_source(str(item.get("key") or "")) for item in endpoint_items}
    existing_urls = {_normalized_url(item.get("url")) for item in endpoint_items if _normalized_url(item.get("url"))}
    if source_key in existing_source_keys:
        issues.append(CatalogIssue("error", "duplicate_source_key", "source key already exists", source_key))
    if endpoint_key in existing_endpoint_keys:
        issues.append(CatalogIssue("error", "duplicate_endpoint_key", "endpoint key already exists", endpoint_key))
    if feed_url and feed_url in existing_urls:
        issues.append(CatalogIssue("error", "duplicate_endpoint_url", "url already exists in endpoints.yaml", feed_url))

    _raise_if_issues(issues)

    source_entry: dict[str, Any] = {
        "key": source_key,
        "name": str(name).strip(),
        "source_kind": source_kind,
    }
    if publisher:
        source_entry["publisher"] = str(publisher).strip()
    if homepage:
        source_entry["homepage"] = str(homepage).strip()
    source_entry["disciplines"] = canonical_disciplines
    source_entry["status"] = "active"
    if origin:
        source_entry["origin"] = str(origin).strip()

    endpoint_entry: dict[str, Any] = {
        "key": endpoint_key,
        "source_key": source_key,
        "mode": endpoint_mode,
    }
    if publisher:
        endpoint_entry["provider"] = str(publisher).strip()
    endpoint_entry["url"] = feed_url
    endpoint_entry["status"] = endpoint_status
    if endpoint_status != "active":
        endpoint_entry["enabled"] = False
    endpoint_entry["priority"] = 100

    source_yaml = _dump_yaml_item(source_entry)
    endpoint_yaml = _dump_yaml_item(endpoint_entry)
    validation = validate_catalog(sources_path=source_path, endpoints_path=endpoint_path, taxonomy_path=taxonomy_file)

    if write:
        _append_yaml_item(source_path, "sources", source_yaml)
        _append_yaml_item(endpoint_path, "endpoints", endpoint_yaml)
        clear_catalog_cache()
        try:
            from paperlite.registry import clear_registry_cache

            clear_registry_cache()
        except Exception:
            pass
        validation = validate_catalog(sources_path=source_path, endpoints_path=endpoint_path, taxonomy_path=taxonomy_file)

    return AddSourceResult(
        source_entry=source_entry,
        endpoint_entry=endpoint_entry,
        source_yaml=source_yaml,
        endpoint_yaml=endpoint_yaml,
        validation=validation,
        wrote=write,
    )
