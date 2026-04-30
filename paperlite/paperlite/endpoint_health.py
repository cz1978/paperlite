from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

import httpx

from paperlite.catalog_quality import load_health_snapshot, health_snapshot_path
from paperlite.config import DEFAULT_HEALTH_SNAPSHOT_PATH
from paperlite.http_client import get_feed_url
from paperlite.registry import list_sources
from paperlite.sources import FEED_ENDPOINT_MODES, list_endpoints

CLASSIFICATION_OK = "ok"
CLASSIFICATION_DEAD_404 = "dead_404"
CLASSIFICATION_HTML_NOT_FEED = "html_not_feed"
CLASSIFICATION_BLOCKED_403 = "blocked_403"
CLASSIFICATION_TIMEOUT = "timeout"
CLASSIFICATION_TLS_ERROR = "tls_error"
CLASSIFICATION_REDIRECT_ERROR = "redirect_error"
CLASSIFICATION_HTTP_ERROR = "http_error"
CLASSIFICATION_REQUEST_ERROR = "request_error"


@dataclass(frozen=True)
class EndpointHealthResult:
    key: str
    source_key: str
    mode: str
    url: str | None
    ok: bool
    checked_at: str
    status_code: int | None = None
    content_type: str | None = None
    elapsed_ms: int | None = None
    classification: str = CLASSIFICATION_OK
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "source_key": self.source_key,
            "mode": self.mode,
            "url": self.url,
            "ok": self.ok,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "elapsed_ms": self.elapsed_ms,
            "classification": self.classification,
            "checked_at": self.checked_at,
            "error": self.error,
        }


HealthChecker = Callable[[dict[str, object], float, str], EndpointHealthResult]


def checked_at_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _looks_like_feed(body: str) -> bool:
    sample = body[:4096].lstrip().lower()
    return sample.startswith(("<?xml", "<rss", "<feed", "<rdf:rdf")) and any(
        marker in sample for marker in ("<rss", "<feed", "<rdf:rdf")
    )


def _classification_for_status(status_code: int) -> str:
    if status_code == 403:
        return CLASSIFICATION_BLOCKED_403
    if status_code == 404:
        return CLASSIFICATION_DEAD_404
    return CLASSIFICATION_HTTP_ERROR


def _classification_for_exception(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, httpx.TimeoutException) or "timed out" in text or "timeout" in text:
        return CLASSIFICATION_TIMEOUT
    if isinstance(exc, httpx.TooManyRedirects) or "redirect" in text:
        return CLASSIFICATION_REDIRECT_ERROR
    if "ssl" in text or "tls" in text or "certificate" in text:
        return CLASSIFICATION_TLS_ERROR
    return CLASSIFICATION_REQUEST_ERROR


def probe_endpoint(
    endpoint: dict[str, object],
    timeout_seconds: float,
    request_profile: str = "paperlite",
) -> EndpointHealthResult:
    key = str(endpoint.get("key") or "")
    source_key = str(endpoint.get("source_key") or "")
    mode = str(endpoint.get("mode") or "")
    url = endpoint.get("url")
    url_text = str(url).strip() if url else None
    checked_at = checked_at_now()
    if not url_text:
        return EndpointHealthResult(
            key,
            source_key,
            mode,
            None,
            False,
            checked_at,
            classification=CLASSIFICATION_REQUEST_ERROR,
            error="missing url",
        )

    started = perf_counter()
    try:
        profile = str(endpoint.get("request_profile") or request_profile or "paperlite").strip()
        response = get_feed_url(
            url_text,
            timeout_seconds=timeout_seconds,
            request_profile=profile,
        )
        elapsed_ms = int((perf_counter() - started) * 1000)
        content_type = response.headers.get("content-type")
        ok = 200 <= response.status_code < 400
        classification = CLASSIFICATION_OK
        error = None
        if not ok:
            classification = _classification_for_status(response.status_code)
            error = f"http {response.status_code}"
        elif mode in FEED_ENDPOINT_MODES and not _looks_like_feed(response.text):
            ok = False
            classification = CLASSIFICATION_HTML_NOT_FEED
            error = "response does not look like RSS/Atom"
        return EndpointHealthResult(
            key,
            source_key,
            mode,
            url_text,
            ok,
            checked_at,
            status_code=response.status_code,
            content_type=content_type,
            elapsed_ms=elapsed_ms,
            classification=classification,
            error=error,
        )
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        classification = _classification_for_exception(exc)
        return EndpointHealthResult(
            key,
            source_key,
            mode,
            url_text,
            False,
            checked_at,
            elapsed_ms=elapsed_ms,
            classification=classification,
            error=str(exc),
        )


def _run_health_checks(
    endpoints: list[dict[str, object]],
    *,
    timeout_seconds: float,
    checker: HealthChecker,
    max_workers: int,
    request_profile: str,
) -> list[EndpointHealthResult]:
    workers = max(1, min(max_workers, len(endpoints) or 1))
    results: list[EndpointHealthResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(checker, endpoint, timeout_seconds, request_profile): index
            for index, endpoint in enumerate(endpoints)
        }
        ordered: dict[int, EndpointHealthResult] = {}
        for future in as_completed(futures):
            ordered[futures[future]] = future.result()
    for index in range(len(endpoints)):
        results.append(ordered[index])
    return results


def check_endpoint_health(
    *,
    mode: str | None = "rss",
    limit: int = 50,
    timeout_seconds: float = 5.0,
    checker: HealthChecker = probe_endpoint,
    max_workers: int = 8,
    request_profile: str = "paperlite",
) -> list[EndpointHealthResult]:
    endpoints = [endpoint for endpoint in list_endpoints(mode=mode) if endpoint.get("url")]
    selected = endpoints[:max(0, limit)]
    return _run_health_checks(
        selected,
        timeout_seconds=timeout_seconds,
        checker=checker,
        max_workers=max_workers,
        request_profile=request_profile,
    )


def _split_keys(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    raw = value.split(",") if isinstance(value, str) else list(value)
    return [str(item).strip() for item in raw if str(item).strip()]


def select_health_endpoints(
    *,
    discipline: str | None = None,
    source: str | list[str] | tuple[str, ...] | None = None,
    mode: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    selected_mode = str(mode or "").strip().lower()
    if selected_mode in {"all", "*"}:
        selected_mode = ""
    allowed_modes = {selected_mode} if selected_mode else set(FEED_ENDPOINT_MODES)
    requested_sources = set(_split_keys(source))
    discipline_sources = (
        {str(item.get("name") or "") for item in list_sources(discipline=discipline)}
        if discipline
        else set()
    )
    source_filter = requested_sources
    if discipline_sources:
        source_filter = source_filter & discipline_sources if source_filter else discipline_sources
    endpoints = []
    for endpoint in list_endpoints():
        if endpoint.get("mode") not in allowed_modes:
            continue
        if not endpoint.get("url"):
            continue
        if source_filter and endpoint.get("source_key") not in source_filter:
            continue
        endpoints.append(endpoint)
    return endpoints[: max(0, int(limit))]


def check_selected_endpoint_health(
    *,
    discipline: str | None = None,
    source: str | list[str] | tuple[str, ...] | None = None,
    mode: str | None = None,
    limit: int = 50,
    timeout_seconds: float = 5.0,
    checker: HealthChecker = probe_endpoint,
    max_workers: int = 8,
    request_profile: str = "paperlite",
) -> list[EndpointHealthResult]:
    endpoints = select_health_endpoints(
        discipline=discipline,
        source=source,
        mode=mode,
        limit=limit,
    )
    return _run_health_checks(
        endpoints,
        timeout_seconds=timeout_seconds,
        checker=checker,
        max_workers=max_workers,
        request_profile=request_profile,
    )


def health_snapshot_write_path(path: str | Path | None = None) -> Path:
    return health_snapshot_path(path) or DEFAULT_HEALTH_SNAPSHOT_PATH


def merge_health_snapshot(
    results: list[EndpointHealthResult],
    *,
    path: str | Path | None = None,
) -> dict[str, object]:
    selected = health_snapshot_write_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    merged = load_health_snapshot(selected)
    for result in results:
        merged[result.key] = result.to_dict()
    rows = [merged[key] for key in sorted(merged)]
    payload = {
        "updated_at": checked_at_now(),
        "health": rows,
    }
    selected.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "path": str(selected),
        "count": len(rows),
        "updated": len(results),
        "updated_at": payload["updated_at"],
    }


def format_health_markdown(results: list[EndpointHealthResult]) -> str:
    lines = []
    for result in results:
        status = "OK" if result.ok else "FAIL"
        pieces = [
            f"- {status} {result.key} -> {result.source_key} ({result.mode})",
            f"status={result.status_code}" if result.status_code is not None else None,
            f"class={result.classification}",
            f"elapsed={result.elapsed_ms}ms" if result.elapsed_ms is not None else None,
            f"error={result.error}" if result.error else None,
            result.url,
        ]
        lines.append(" ".join(str(piece) for piece in pieces if piece))
    return "\n".join(lines)
