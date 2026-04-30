from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from paperlite.config import ENDPOINTS_ENV_VAR as ENDPOINTS_ENV_VAR, SOURCES_ENV_VAR as SOURCES_ENV_VAR, runtime_config
from paperlite.connectors.base import EndpointConfig, SourceConfig, SourceRecord
from paperlite.identity import normalize_source

FEED_SOURCE_TYPES = {"journal", "preprint", "news", "publisher", "working_papers"}
FEED_ENDPOINT_MODES = {"rss", "atom", "feed"}
IMPLEMENTED_ENDPOINT_MODES = FEED_ENDPOINT_MODES | {"api"}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _as_int(value: Any, default: int = 100) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _request_profile(value: Any) -> str | None:
    profile = str(value or "").strip()
    if not profile:
        return None
    if profile not in {"paperlite", "browser_compat"}:
        raise ValueError(f"unknown request_profile: {value}")
    return profile


def normalize_endpoint_mode(mode: str | None) -> str | None:
    if mode is None:
        return None
    value = str(mode).strip().lower().replace("-", "_")
    return value or None


def _source_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return runtime_config().sources_path


def _endpoint_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return runtime_config().endpoints_path


def clear_catalog_cache() -> None:
    load_source_records.cache_clear()
    load_endpoint_configs.cache_clear()


def endpoint_skip_reason(endpoint: EndpointConfig) -> str | None:
    mode = normalize_endpoint_mode(endpoint.mode) or ""
    status = str(endpoint.status or "active").strip().lower()
    if not endpoint.enabled:
        return "disabled"
    if status != "active":
        return f"status:{status}"
    if mode not in IMPLEMENTED_ENDPOINT_MODES:
        return f"unsupported_mode:{mode or 'missing'}"
    if mode in FEED_ENDPOINT_MODES and not str(endpoint.url or "").strip():
        return "missing_feed_url"
    return None


def is_runnable_endpoint(endpoint: EndpointConfig) -> bool:
    return endpoint_skip_reason(endpoint) is None


def source_record_from_dict(item: dict[str, Any]) -> SourceRecord:
    key = normalize_source(str(item.get("key", "")))
    source_kind = str(item.get("source_kind") or item.get("type") or "").strip().lower()
    if not key:
        raise ValueError("source config is missing key")
    if not source_kind:
        raise ValueError(f"source config {key} is missing type")

    name = str(item.get("name") or item.get("journal") or key).strip()
    raw = dict(item)
    return SourceRecord(
        key=key,
        name=name,
        source_kind=source_kind,
        publisher=item.get("publisher"),
        homepage=item.get("homepage"),
        issn=_as_list(item.get("issn")),
        tier=item.get("tier"),
        topics=_as_list(item.get("topics")),
        disciplines=_as_list(item.get("disciplines")),
        status=str(item.get("status") or "active"),
        origin=item.get("origin"),
        raw=raw,
    )


def endpoint_config_from_dict(item: dict[str, Any]) -> EndpointConfig:
    key = normalize_source(str(item.get("key", "")))
    source_key = normalize_source(str(item.get("source_key") or item.get("source") or ""))
    mode = str(item.get("mode") or item.get("access_mode") or item.get("method") or "").strip().lower()
    if not key:
        raise ValueError("endpoint config is missing key")
    if not source_key:
        raise ValueError(f"endpoint config {key} is missing source_key")
    if not mode:
        raise ValueError(f"endpoint config {key} is missing mode")

    return EndpointConfig(
        key=key,
        source_key=source_key,
        mode=mode,
        url=item.get("url"),
        provider=item.get("provider"),
        query=_as_dict(item.get("query")),
        format=item.get("format"),
        enabled=_as_bool(item.get("enabled"), default=True),
        priority=_as_int(item.get("priority"), default=100),
        status=str(item.get("status") or "active"),
        rate_limit_seconds=_as_float(item.get("rate_limit_seconds")),
        timeout_seconds=_as_float(item.get("timeout_seconds")),
        request_profile=_request_profile(item.get("request_profile")),
        raw=dict(item),
    )


def _flat_endpoint_from_source(item: dict[str, Any]) -> EndpointConfig | None:
    url = str(item.get("url") or "").strip()
    if not url:
        return None
    key = normalize_source(str(item.get("key", "")))
    if not key:
        return None
    method = str(item.get("method") or item.get("format") or "rss").strip().lower()
    mode = "atom" if method.startswith("atom") else "rss"
    return EndpointConfig(
        key=key,
        source_key=key,
        mode=mode,
        url=url,
        provider=item.get("publisher") or item.get("provider"),
        format=method or None,
        enabled=_as_bool(item.get("enabled"), default=True),
        priority=_as_int(item.get("priority"), default=100),
        status=str(item.get("status") or "active"),
        request_profile=_request_profile(item.get("request_profile")),
        raw=dict(item),
    )


def source_config_from_dict(item: dict[str, Any]) -> SourceConfig:
    source = source_record_from_dict(item)
    endpoint = _flat_endpoint_from_source(item)
    return source_config_from_records(source, endpoint)


def source_config_from_records(
    source: SourceRecord,
    endpoint: EndpointConfig | None = None,
) -> SourceConfig:
    return SourceConfig(
        key=source.key,
        type=source.source_kind,
        journal=source.name,
        publisher=source.publisher,
        url=endpoint.url if endpoint else None,
        endpoint_key=endpoint.key if endpoint else None,
        mode=endpoint.mode if endpoint else None,
        issn=list(source.issn),
        tier=source.tier,
        topics=list(source.topics),
        disciplines=list(source.disciplines),
        timeout_seconds=endpoint.timeout_seconds if endpoint else None,
        raw={
            "origin": source.origin,
            "method": endpoint.format if endpoint else None,
            "source": source.to_dict(),
            "endpoint": endpoint.to_dict() if endpoint else None,
        },
    )


def _dedupe_by_key(configs: list[Any]) -> tuple[Any, ...]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for config in configs:
        if config.key in seen:
            continue
        seen.add(config.key)
        deduped.append(config)
    return tuple(deduped)


@lru_cache(maxsize=8)
def load_source_records(
    path: str | Path | None = None,
) -> tuple[SourceRecord, ...]:
    source_path = _source_path(path)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    items = data.get("sources") or []
    if not isinstance(items, list):
        raise ValueError("sources.yaml must contain a list under 'sources'")
    return _dedupe_by_key([source_record_from_dict(item) for item in items])


def _load_flat_source_items(path: str | Path | None = None) -> list[dict[str, Any]]:
    source_path = _source_path(path)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    items = data.get("sources") or []
    if not isinstance(items, list):
        raise ValueError("sources.yaml must contain a list under 'sources'")
    return [dict(item) for item in items]


@lru_cache(maxsize=8)
def load_endpoint_configs(
    sources_path: str | Path | None = None,
    endpoints_path: str | Path | None = None,
) -> tuple[EndpointConfig, ...]:
    source_keys = {source.key for source in load_source_records(sources_path)}
    endpoint_path = _endpoint_path(endpoints_path)

    configs: list[EndpointConfig] = []
    if endpoint_path.exists():
        data = yaml.safe_load(endpoint_path.read_text(encoding="utf-8")) or {}
        items = data.get("endpoints") or []
        if not isinstance(items, list):
            raise ValueError("endpoints.yaml must contain a list under 'endpoints'")
        configs.extend(endpoint_config_from_dict(item) for item in items)
    else:
        configs.extend(
            endpoint
            for item in _load_flat_source_items(sources_path)
            if (endpoint := _flat_endpoint_from_source(item))
        )

    missing = sorted({endpoint.source_key for endpoint in configs if endpoint.source_key not in source_keys})
    if missing:
        raise ValueError(f"endpoint source_key is unknown: {', '.join(missing[:10])}")
    return _dedupe_by_key(configs)


def load_source_configs(
    path: str | Path | None = None,
) -> tuple[SourceConfig, ...]:
    endpoints_by_source = {endpoint.source_key: endpoint for endpoint in load_endpoint_configs(path)}
    return tuple(
        source_config_from_records(source, endpoints_by_source.get(source.key))
        for source in load_source_records(path)
    )


def load_feed_source_configs(
    path: str | Path | None = None,
) -> tuple[SourceConfig, ...]:
    sources = {source.key: source for source in load_source_records(path)}
    return tuple(
        source_config_from_records(sources[endpoint.source_key], endpoint)
        for endpoint in load_endpoint_configs(path)
        if is_runnable_endpoint(endpoint)
        and endpoint.mode in FEED_ENDPOINT_MODES
        and endpoint.url
        and sources[endpoint.source_key].source_kind in FEED_SOURCE_TYPES
    )


def endpoint_mode_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for endpoint in load_endpoint_configs():
        counts[endpoint.mode] = counts.get(endpoint.mode, 0) + 1
    return dict(sorted(counts.items()))


def _validate_endpoint_filter(value: str | None, available: list[str], label: str) -> str | None:
    if value is None:
        return None
    selected = str(value).strip()
    if not selected:
        return None
    if selected not in available:
        raise ValueError(f"unknown endpoint {label}: {value}. Available {label}s: {', '.join(available)}")
    return selected


def list_endpoints(mode: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    selected_mode = normalize_endpoint_mode(mode)
    endpoint_configs = load_endpoint_configs()
    available_modes = sorted({endpoint.mode for endpoint in endpoint_configs})
    if selected_mode and selected_mode not in available_modes:
        raise ValueError(f"unknown endpoint mode: {mode}. Available modes: {', '.join(available_modes)}")
    selected_status = _validate_endpoint_filter(
        status,
        sorted({endpoint.status for endpoint in endpoint_configs}),
        "status",
    )

    sources = {source.key: source for source in load_source_records()}
    items = []
    for endpoint in sorted(endpoint_configs, key=lambda item: (item.source_key, item.priority, item.key)):
        if selected_mode and endpoint.mode != selected_mode:
            continue
        if selected_status and endpoint.status != selected_status:
            continue
        source = sources[endpoint.source_key]
        payload = endpoint.to_dict()
        payload.update(
            {
                "source_name": source.name,
                "source_kind": source.source_kind,
                "publisher": source.publisher,
                "topics": list(source.topics),
                "disciplines": list(source.disciplines),
            }
        )
        items.append(payload)
    return items
