from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from paperlite.config import runtime_config
from paperlite.connectors.base import EndpointConfig, SourceRecord
from paperlite.profiles import load_profiles
from paperlite.sources import is_runnable_endpoint, load_endpoint_configs, load_source_records
from paperlite.taxonomy import (
    area_label,
    canonical_disciplines,
    discipline_record,
    source_kind_record,
    taxonomy_areas,
    taxonomy_disciplines,
    taxonomy_source_kinds,
)

CORE_TIERS = {"T0", "flagship", "top-journal"}
TEMPORARILY_UNAVAILABLE_HEALTH_STATUSES = {
    "blocked_403",
    "dead_404",
    "failed",
    "html_not_feed",
    "redirect_error",
    "temporarily_unavailable",
    "timeout",
    "tls_error",
}


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _discipline_records_for_source(canonical: list[str]) -> list[dict[str, str]]:
    records = [discipline_record(value) for value in canonical]
    if not records:
        records = [discipline_record("Unclassified")]
    by_key: dict[str, dict[str, str]] = {}
    for record in records:
        by_key.setdefault(record["key"], record)
    return list(by_key.values())


def primary_discipline_record(canonical: list[str]) -> dict[str, str]:
    records = _discipline_records_for_source(canonical)
    for record in records:
        if record["key"] != "unclassified":
            return record
    return records[0]


def _sources_url(**params: object) -> str:
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    return "/sources" if not clean else f"/sources?{urlencode(clean)}"


def health_snapshot_path(path: str | Path | None = None) -> Path | None:
    if path:
        return Path(path)
    return runtime_config().health_snapshot_path


def load_health_snapshot(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    selected = health_snapshot_path(path)
    if selected is None or not selected.exists():
        return {}
    data = json.loads(selected.read_text(encoding="utf-8"))
    rows = data.get("health") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return {}
    snapshot: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if key:
            snapshot[key] = dict(row)
    return snapshot


def endpoint_health_status(endpoint: EndpointConfig, snapshot: dict[str, dict[str, Any]] | None = None) -> str:
    row = (snapshot or {}).get(endpoint.key)
    if row:
        if row.get("ok") is True:
            return "ok"
        classification = str(row.get("classification") or "").strip()
        return classification or "failed"
    if not endpoint.enabled:
        return endpoint.status or "disabled"
    return endpoint.status or "active"


def duplicate_endpoint_sources(endpoints: tuple[EndpointConfig, ...] | list[EndpointConfig]) -> dict[str, str]:
    by_url: dict[str, list[EndpointConfig]] = defaultdict(list)
    for endpoint in endpoints:
        if endpoint.url:
            by_url[str(endpoint.url).strip().lower()].append(endpoint)

    duplicate_of: dict[str, str] = {}
    for group in by_url.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: (item.source_key, item.key))
        canonical_source = ordered[0].source_key
        for endpoint in ordered[1:]:
            duplicate_of.setdefault(endpoint.source_key, canonical_source)
    return duplicate_of


def duplicate_url_summary(endpoints: tuple[EndpointConfig, ...] | list[EndpointConfig]) -> dict[str, int]:
    by_url: dict[str, list[str]] = defaultdict(list)
    for endpoint in endpoints:
        if endpoint.url:
            by_url[str(endpoint.url).strip().lower()].append(endpoint.key)
    duplicate_groups = [keys for keys in by_url.values() if len(keys) > 1]
    return {
        "duplicate_url_groups": len(duplicate_groups),
        "duplicate_endpoint_count": sum(len(keys) for keys in duplicate_groups),
    }


def profile_core_source_keys() -> set[str]:
    try:
        return {source for profile in load_profiles() for source in profile.sources}
    except Exception:
        return set()


def _source_health_status(
    endpoints: list[EndpointConfig],
    snapshot: dict[str, dict[str, Any]],
) -> str:
    if not endpoints:
        return "missing_endpoint"
    statuses = [endpoint_health_status(endpoint, snapshot) for endpoint in endpoints]
    if any(status == "ok" for status in statuses):
        return "ok"
    for status in sorted(TEMPORARILY_UNAVAILABLE_HEALTH_STATUSES):
        if status in statuses:
            return status
    if any(status == "active" for status in statuses):
        return "active"
    if any(status == "candidate" for status in statuses):
        return "candidate"
    if any(status == "disabled" for status in statuses):
        return "disabled"
    return statuses[0]


def source_quality_fields(
    source: SourceRecord,
    endpoints: list[EndpointConfig],
    *,
    duplicate_of: str | None = None,
    profile_core_sources: set[str] | None = None,
    health_snapshot: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    canonical = canonical_disciplines(source.disciplines) or canonical_disciplines(source.topics)
    discipline_records = _discipline_records_for_source(canonical)
    discipline_keys = [record["key"] for record in discipline_records]
    area_keys = _dedupe_ordered([record["area_key"] for record in discipline_records])
    primary_discipline = primary_discipline_record(canonical)
    kind = source_kind_record(source.source_kind)
    category_keys = [f"{record['key']}.{kind['key']}" for record in discipline_records]
    category_labels = [f"{record['label']} · {kind['label']}" for record in discipline_records]
    snapshot = health_snapshot or {}
    health_status = _source_health_status(endpoints, snapshot)
    has_active_endpoint = any(endpoint.enabled and endpoint.status == "active" for endpoint in endpoints)
    core_sources = profile_core_sources if profile_core_sources is not None else profile_core_source_keys()
    core = bool(has_active_endpoint and (source.key in core_sources or str(source.tier or "") in CORE_TIERS))
    needs_review = bool(
        not canonical
        or "unclassified" in discipline_keys
        or not source.tier
        or duplicate_of
        or health_status in {"candidate", "missing_endpoint"}
    )
    if duplicate_of:
        quality_status = "duplicate"
    elif health_status in TEMPORARILY_UNAVAILABLE_HEALTH_STATUSES:
        quality_status = "temporarily_unavailable"
    elif health_status == "candidate":
        quality_status = "candidate"
    elif needs_review:
        quality_status = "needs_review"
    elif core:
        quality_status = "core"
    else:
        quality_status = "cataloged"
    return {
        "canonical_disciplines": canonical,
        "catalog_kind": source.source_kind,
        "quality_status": quality_status,
        "core": core,
        "duplicate_of": duplicate_of,
        "needs_review": needs_review,
        "health_status": health_status,
        "discipline_keys": discipline_keys,
        "primary_discipline": primary_discipline["name"],
        "primary_discipline_key": primary_discipline["key"],
        "primary_discipline_label": primary_discipline["label"],
        "area_keys": area_keys,
        "primary_area_key": primary_discipline["area_key"],
        "primary_area_label": primary_discipline["area_label"],
        "source_kind_key": kind["key"],
        "source_kind_label": kind["label"],
        "category_keys": category_keys,
        "category_labels": category_labels,
        "category_key": f"{primary_discipline['key']}.{kind['key']}",
        "category_label": f"{primary_discipline['label']} · {kind['label']}",
    }


def build_catalog_summary(health_snapshot_path_value: str | Path | None = None) -> dict[str, Any]:
    sources = load_source_records()
    endpoints = load_endpoint_configs()
    snapshot = load_health_snapshot(health_snapshot_path_value)
    endpoints_by_source: dict[str, list[EndpointConfig]] = defaultdict(list)
    for endpoint in endpoints:
        endpoints_by_source[endpoint.source_key].append(endpoint)

    duplicate_of = duplicate_endpoint_sources(endpoints)
    profile_sources = profile_core_source_keys()
    source_fields = [
        source_quality_fields(
            source,
            endpoints_by_source.get(source.key, []),
            duplicate_of=duplicate_of.get(source.key),
            profile_core_sources=profile_sources,
            health_snapshot=snapshot,
        )
        for source in sources
    ]
    health_counts = Counter(
        endpoint_health_status(endpoint, snapshot)
        for endpoint in endpoints
    )
    discipline_counts = Counter(
        discipline
        for fields in source_fields
        for discipline in fields["canonical_disciplines"]
    )
    duplicate_counts = duplicate_url_summary(endpoints)
    checked_values = sorted(
        str(row.get("checked_at"))
        for row in snapshot.values()
        if row.get("checked_at")
    )
    return {
        "source_count": len(sources),
        "endpoint_count": len(endpoints),
        "enabled_endpoint_count": sum(1 for endpoint in endpoints if endpoint.enabled),
        "temporarily_unavailable_endpoint_count": sum(1 for endpoint in endpoints if endpoint.status == "temporarily_unavailable"),
        "candidate_endpoint_count": sum(1 for endpoint in endpoints if endpoint.status == "candidate"),
        "source_kind_counts": dict(sorted(Counter(source.source_kind for source in sources).items())),
        "endpoint_mode_counts": dict(sorted(Counter(endpoint.mode for endpoint in endpoints).items())),
        "endpoint_status_counts": dict(sorted(Counter(endpoint.status for endpoint in endpoints).items())),
        "health_status_counts": dict(sorted(health_counts.items())),
        "discipline_counts": dict(sorted(discipline_counts.items())),
        "missing_discipline_count": sum(1 for fields in source_fields if not fields["canonical_disciplines"]),
        "missing_tier_count": sum(1 for source in sources if not source.tier),
        "core_source_count": sum(1 for fields in source_fields if fields["core"]),
        "needs_review_source_count": sum(1 for fields in source_fields if fields["needs_review"]),
        "duplicate_source_count": len(duplicate_of),
        "duplicate_url_groups": duplicate_counts["duplicate_url_groups"],
        "duplicate_endpoint_count": duplicate_counts["duplicate_endpoint_count"],
        "health_snapshot_loaded": bool(snapshot),
        "health_snapshot_path": str(health_snapshot_path(health_snapshot_path_value) or ""),
        "health_checked_at_min": checked_values[0] if checked_values else None,
        "health_checked_at_max": checked_values[-1] if checked_values else None,
    }


def format_catalog_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"- sources: {summary.get('source_count', 0)}",
        f"- endpoints: {summary.get('endpoint_count', 0)}",
        f"- enabled endpoints: {summary.get('enabled_endpoint_count', 0)}",
        f"- temporarily unavailable endpoints: {summary.get('temporarily_unavailable_endpoint_count', 0)}",
        f"- candidate endpoints: {summary.get('candidate_endpoint_count', 0)}",
        f"- core sources: {summary.get('core_source_count', 0)}",
        f"- needs review sources: {summary.get('needs_review_source_count', 0)}",
        f"- missing discipline sources: {summary.get('missing_discipline_count', 0)}",
        f"- duplicate URL groups: {summary.get('duplicate_url_groups', 0)}",
    ]
    checked = summary.get("health_checked_at_max")
    lines.append(f"- health snapshot: {checked or 'not loaded'}")
    return "\n".join(lines)


CATALOG_COVERAGE_GENERAL_POLICY = (
    "multidisciplinary/unclassified are reported as their own general disciplines; "
    "they are not auto-expanded into every discipline."
)


def _coverage_counter_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "area_label": area_label(str(record.get("area_key") or "")),
        "source_count": 0,
        "runnable_source_count": 0,
        "healthy_source_count": 0,
        "unavailable_source_count": 0,
        "needs_review_source_count": 0,
        "core_source_count": 0,
        "source_kind_counts": {},
        "runnable_kind_counts": {},
        "endpoint_mode_counts": {},
        "health_status_counts": {},
        "sources_url": _sources_url(discipline=record.get("name")),
    }


def _bump_counter(record: dict[str, Any], field: str, key: str) -> None:
    counts = Counter(record.get(field) or {})
    counts[key] += 1
    record[field] = dict(sorted(counts.items()))


def build_catalog_coverage(health_snapshot_path_value: str | Path | None = None) -> dict[str, Any]:
    sources = load_source_records()
    endpoints = load_endpoint_configs()
    snapshot = load_health_snapshot(health_snapshot_path_value)
    endpoints_by_source: dict[str, list[EndpointConfig]] = defaultdict(list)
    for endpoint in endpoints:
        endpoints_by_source[endpoint.source_key].append(endpoint)

    duplicate_of = duplicate_endpoint_sources(endpoints)
    profile_sources = profile_core_source_keys()
    checked_values = sorted(
        str(row.get("checked_at"))
        for row in snapshot.values()
        if row.get("checked_at")
    )
    disciplines = {
        item["key"]: _coverage_counter_record(item)
        for item in taxonomy_disciplines()
    }
    totals = {
        "source_count": len(sources),
        "endpoint_count": len(endpoints),
        "discipline_count": len(disciplines),
        "runnable_source_count": 0,
        "healthy_source_count": 0,
        "unavailable_source_count": 0,
        "needs_review_source_count": 0,
        "core_source_count": 0,
        "source_kind_counts": {},
        "runnable_kind_counts": {},
        "endpoint_mode_counts": {},
        "health_status_counts": {},
        "health_snapshot_loaded": bool(snapshot),
        "health_snapshot_path": str(health_snapshot_path(health_snapshot_path_value) or ""),
        "health_checked_at_min": checked_values[0] if checked_values else None,
        "health_checked_at_max": checked_values[-1] if checked_values else None,
    }

    for source in sources:
        source_endpoints = endpoints_by_source.get(source.key, [])
        fields = source_quality_fields(
            source,
            source_endpoints,
            duplicate_of=duplicate_of.get(source.key),
            profile_core_sources=profile_sources,
            health_snapshot=snapshot,
        )
        kind_key = str(fields.get("source_kind_key") or source.source_kind or "unknown")
        runnable = any(is_runnable_endpoint(endpoint) for endpoint in source_endpoints)
        health_status = str(fields.get("health_status") or "unknown")
        healthy = runnable and health_status in {"ok", "active"}
        unavailable = (
            not runnable
            or fields.get("quality_status") == "temporarily_unavailable"
            or health_status in TEMPORARILY_UNAVAILABLE_HEALTH_STATUSES
        )

        totals["runnable_source_count"] += 1 if runnable else 0
        totals["healthy_source_count"] += 1 if healthy else 0
        totals["unavailable_source_count"] += 1 if unavailable else 0
        totals["needs_review_source_count"] += 1 if fields.get("needs_review") else 0
        totals["core_source_count"] += 1 if fields.get("core") else 0
        _bump_counter(totals, "source_kind_counts", kind_key)
        if runnable:
            _bump_counter(totals, "runnable_kind_counts", kind_key)
        _bump_counter(totals, "health_status_counts", health_status)
        for endpoint in source_endpoints:
            _bump_counter(totals, "endpoint_mode_counts", str(endpoint.mode or "unknown"))

        for discipline_key in fields.get("discipline_keys") or ["unclassified"]:
            record = disciplines.setdefault(
                discipline_key,
                _coverage_counter_record(discipline_record(discipline_key)),
            )
            record["source_count"] += 1
            record["runnable_source_count"] += 1 if runnable else 0
            record["healthy_source_count"] += 1 if healthy else 0
            record["unavailable_source_count"] += 1 if unavailable else 0
            record["needs_review_source_count"] += 1 if fields.get("needs_review") else 0
            record["core_source_count"] += 1 if fields.get("core") else 0
            _bump_counter(record, "source_kind_counts", kind_key)
            if runnable:
                _bump_counter(record, "runnable_kind_counts", kind_key)
            _bump_counter(record, "health_status_counts", health_status)
            for endpoint in source_endpoints:
                _bump_counter(record, "endpoint_mode_counts", str(endpoint.mode or "unknown"))

    return {
        "generated_from": "yaml_catalog",
        "general_policy": CATALOG_COVERAGE_GENERAL_POLICY,
        "totals": totals,
        "disciplines": sorted(disciplines.values(), key=lambda item: (item["area_key"], item["key"])),
    }


def _compact_counts(counts: dict[str, int] | None, *, limit: int = 4) -> str:
    if not counts:
        return "-"
    parts = [f"{key}:{value}" for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]
    return ", ".join(parts)


def format_catalog_coverage_markdown(coverage: dict[str, Any]) -> str:
    totals = coverage.get("totals") or {}
    lines = [
        "# PaperLite 来源覆盖",
        "",
        f"- sources: {totals.get('source_count', 0)}",
        f"- runnable sources: {totals.get('runnable_source_count', 0)}",
        f"- healthy sources: {totals.get('healthy_source_count', 0)}",
        f"- unavailable sources: {totals.get('unavailable_source_count', 0)}",
        f"- policy: {coverage.get('general_policy') or CATALOG_COVERAGE_GENERAL_POLICY}",
        "",
        "| discipline | sources | runnable | healthy | unavailable | kinds | health |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in coverage.get("disciplines", []):
        if int(item.get("source_count") or 0) <= 0:
            continue
        lines.append(
            "| "
            f"{item.get('key')} / {item.get('label')} | "
            f"{item.get('source_count', 0)} | "
            f"{item.get('runnable_source_count', 0)} | "
            f"{item.get('healthy_source_count', 0)} | "
            f"{item.get('unavailable_source_count', 0)} | "
            f"{_compact_counts(item.get('source_kind_counts'))} | "
            f"{_compact_counts(item.get('health_status_counts'))} |"
        )
    return "\n".join(lines)


def _empty_counter_record(record: dict[str, str]) -> dict[str, Any]:
    return {
        **record,
        "source_count": 0,
        "core_source_count": 0,
        "active_source_count": 0,
        "temporarily_unavailable_source_count": 0,
        "needs_review_source_count": 0,
        "source_kind_counts": {},
    }


def build_taxonomy_summary(health_snapshot_path_value: str | Path | None = None) -> dict[str, Any]:
    sources = load_source_records()
    endpoints = load_endpoint_configs()
    snapshot = load_health_snapshot(health_snapshot_path_value)
    endpoints_by_source: dict[str, list[EndpointConfig]] = defaultdict(list)
    for endpoint in endpoints:
        endpoints_by_source[endpoint.source_key].append(endpoint)

    duplicate_of = duplicate_endpoint_sources(endpoints)
    profile_sources = profile_core_source_keys()
    source_rows: list[dict[str, Any]] = []
    for source in sources:
        fields = source_quality_fields(
            source,
            endpoints_by_source.get(source.key, []),
            duplicate_of=duplicate_of.get(source.key),
            profile_core_sources=profile_sources,
            health_snapshot=snapshot,
        )
        source_rows.append({"source": source, "fields": fields})

    areas = {
        item["key"]: {
            **item,
            "source_count": 0,
            "core_source_count": 0,
            "needs_review_source_count": 0,
        }
        for item in taxonomy_areas()
    }
    disciplines = {
        item["key"]: _empty_counter_record(
            {
                **item,
                "area_label": area_label(str(item["area_key"])),
                "sources_url": _sources_url(discipline=item["name"]),
            }
        )
        for item in taxonomy_disciplines()
    }
    source_kinds = {
        item["key"]: {
            **item,
            "source_count": 0,
            "core_source_count": 0,
            "needs_review_source_count": 0,
            "sources_url": _sources_url(kind=item["key"]),
        }
        for item in taxonomy_source_kinds()
    }
    categories: dict[str, dict[str, Any]] = {}

    for row in source_rows:
        fields = row["fields"]
        kind_key = str(fields["source_kind_key"])
        if kind_key not in source_kinds:
            source_kinds[kind_key] = {
                **source_kind_record(kind_key),
                "source_count": 0,
                "core_source_count": 0,
                "needs_review_source_count": 0,
                "sources_url": _sources_url(kind=kind_key),
            }
        source_kinds[kind_key]["source_count"] += 1
        if fields["core"]:
            source_kinds[kind_key]["core_source_count"] += 1
        if fields["needs_review"]:
            source_kinds[kind_key]["needs_review_source_count"] += 1

        for area_key in fields.get("area_keys") or [fields["primary_area_key"]]:
            if area_key not in areas:
                areas[area_key] = {
                    "key": area_key,
                    "label": area_key,
                    "source_count": 0,
                    "core_source_count": 0,
                    "needs_review_source_count": 0,
                }
            areas[area_key]["source_count"] += 1
            if fields["core"]:
                areas[area_key]["core_source_count"] += 1
            if fields["needs_review"]:
                areas[area_key]["needs_review_source_count"] += 1

        for discipline_key in fields.get("discipline_keys") or ["unclassified"]:
            record = disciplines.setdefault(
                discipline_key,
                _empty_counter_record(
                    {
                        **discipline_record(discipline_key),
                        "sources_url": _sources_url(discipline=discipline_record(discipline_key)["name"]),
                    }
                ),
            )
            record["source_count"] += 1
            if fields["core"]:
                record["core_source_count"] += 1
            if fields["health_status"] in {"ok", "active"}:
                record["active_source_count"] += 1
            if fields["quality_status"] == "temporarily_unavailable":
                record["temporarily_unavailable_source_count"] += 1
            if fields["needs_review"]:
                record["needs_review_source_count"] += 1
            kind_counts = Counter(record["source_kind_counts"])
            kind_counts[kind_key] += 1
            record["source_kind_counts"] = dict(sorted(kind_counts.items()))

            category_key = f"{discipline_key}.{kind_key}"
            if category_key not in categories:
                discipline = disciplines[discipline_key]
                kind = source_kinds[kind_key]
                categories[category_key] = {
                    "key": category_key,
                    "label": f"{discipline['label']} · {kind['label']}",
                    "discipline_key": discipline_key,
                    "discipline": discipline["name"],
                    "discipline_label": discipline["label"],
                    "area_key": discipline["area_key"],
                    "area_label": discipline["area_label"],
                    "source_kind": kind_key,
                    "source_kind_label": kind["label"],
                    "source_count": 0,
                    "core_source_count": 0,
                    "temporarily_unavailable_source_count": 0,
                    "needs_review_source_count": 0,
                    "sources_url": _sources_url(discipline=discipline["name"], kind=kind_key),
                }
            categories[category_key]["source_count"] += 1
            if fields["core"]:
                categories[category_key]["core_source_count"] += 1
            if fields["quality_status"] == "temporarily_unavailable":
                categories[category_key]["temporarily_unavailable_source_count"] += 1
            if fields["needs_review"]:
                categories[category_key]["needs_review_source_count"] += 1

    return {
        "areas": sorted(areas.values(), key=lambda item: item["key"]),
        "disciplines": sorted(disciplines.values(), key=lambda item: (item["area_key"], item["key"])),
        "source_kinds": sorted(source_kinds.values(), key=lambda item: item["key"]),
        "categories": sorted(
            [item for item in categories.values() if item["source_count"] > 0],
            key=lambda item: (item["area_key"], item["discipline_key"], item["source_kind"]),
        ),
        "maintenance_fields": [
            "primary_discipline_key",
            "discipline_keys",
            "area_keys",
            "source_kind_key",
            "category_keys",
            "category_key",
            "health_status",
            "quality_status",
            "core",
            "needs_review",
            "duplicate_of",
        ],
    }


def format_taxonomy_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# PaperLite 分类映射",
        "",
        "维护字段: " + ", ".join(str(value) for value in summary.get("maintenance_fields", [])),
        "",
        "## 学科",
    ]
    for item in summary.get("disciplines", []):
        if int(item.get("source_count") or 0) <= 0:
            continue
        lines.append(
            f"- {item['key']} / {item['name']} / {item['label']}: "
            f"{item['source_count']} sources, core {item['core_source_count']}, review {item['needs_review_source_count']}"
        )
    lines.extend(["", "## 来源类型"])
    for item in summary.get("source_kinds", []):
        if int(item.get("source_count") or 0) <= 0:
            continue
        lines.append(
            f"- {item['key']} / {item['label']}: "
            f"{item['source_count']} sources, core {item['core_source_count']}, review {item['needs_review_source_count']}"
        )
    lines.extend(["", "## 组合类目"])
    for item in summary.get("categories", [])[:80]:
        lines.append(
            f"- {item['key']} / {item['label']}: {item['source_count']} sources -> {item['sources_url']}"
        )
    return "\n".join(lines)
