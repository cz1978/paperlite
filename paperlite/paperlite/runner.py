from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from paperlite.connectors.base import EndpointConfig, SourceRecord
from paperlite.connectors.journals import JournalFeedConnector
from paperlite.dedupe import dedupe_papers
from paperlite.identity import normalize_source
from paperlite.models import Paper
from paperlite.profiles import SourceProfile, get_profile
from paperlite.sources import (
    FEED_ENDPOINT_MODES,
    endpoint_skip_reason,
    is_runnable_endpoint,
    load_endpoint_configs,
    load_source_records,
    source_config_from_records,
)

RUNNER_TIMEOUT_SECONDS = 18


@dataclass(frozen=True)
class EndpointTask:
    source: SourceRecord
    endpoint: EndpointConfig

    @property
    def source_key(self) -> str:
        return self.source.key

    @property
    def endpoint_key(self) -> str:
        return self.endpoint.key


@dataclass(frozen=True)
class FetchResult:
    source_key: str
    source_name: str
    endpoint_key: str
    endpoint_mode: str
    papers: list[Paper]
    warnings: list[str]
    error: str | None = None

    def endpoint_summary(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint_key,
            "mode": self.endpoint_mode,
            "count": len(self.papers),
            "warnings": list(self.warnings),
            "error": self.error,
        }


@dataclass(frozen=True)
class ResolvedSelection:
    tasks: list[EndpointTask]
    sources: list[str]
    endpoints: list[str]
    profile: SourceProfile | None
    selection_mode: str


def split_keys(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = [str(item) for item in value]
    return [normalize_source(part) for part in raw if str(part).strip()]


def _catalog() -> tuple[dict[str, SourceRecord], dict[str, EndpointConfig]]:
    sources = {source.key: source for source in load_source_records()}
    endpoints = {endpoint.key: endpoint for endpoint in load_endpoint_configs()}
    return sources, endpoints


def _ordered_source_endpoints(source_keys: list[str], endpoints: dict[str, EndpointConfig]) -> list[EndpointConfig]:
    source_set = set(source_keys)
    selected = [
        endpoint for endpoint in endpoints.values()
        if endpoint.source_key in source_set and is_runnable_endpoint(endpoint)
    ]
    selected.sort(key=lambda item: (source_keys.index(item.source_key), item.priority, item.key))
    return selected


def _ordered_named_endpoints(
    endpoint_keys: list[str],
    endpoints: dict[str, EndpointConfig],
    *,
    include_non_runnable: bool = False,
) -> list[EndpointConfig]:
    selected = []
    for key in endpoint_keys:
        try:
            endpoint = endpoints[key]
        except KeyError as exc:
            raise ValueError(f"unknown endpoint: {key}") from exc
        if include_non_runnable or is_runnable_endpoint(endpoint):
            selected.append(endpoint)
    return selected


def resolve_selection(
    *,
    endpoint: str | Iterable[str] | None = None,
    source: str | Iterable[str] | None = None,
    profile: str | None = None,
) -> ResolvedSelection:
    sources, endpoints = _catalog()
    endpoint_keys = split_keys(endpoint)
    source_keys = split_keys(source)
    resolved_profile: SourceProfile | None = None

    if endpoint_keys:
        selected_endpoints = _ordered_named_endpoints(endpoint_keys, endpoints, include_non_runnable=True)
        selection_mode = "endpoint"
    elif source_keys:
        selected_endpoints = _ordered_source_endpoints(source_keys, endpoints)
        selection_mode = "source"
    else:
        resolved_profile = get_profile(profile)
        if resolved_profile.endpoints:
            selected_endpoints = _ordered_named_endpoints(list(resolved_profile.endpoints), endpoints)
            selection_mode = "profile_endpoint"
        else:
            source_keys = list(resolved_profile.sources)
            selected_endpoints = _ordered_source_endpoints(source_keys, endpoints)
            selection_mode = "profile"

    missing_sources = sorted({endpoint.source_key for endpoint in selected_endpoints if endpoint.source_key not in sources})
    if missing_sources:
        raise ValueError(f"endpoint source_key is unknown: {', '.join(missing_sources)}")

    tasks = [EndpointTask(source=sources[endpoint.source_key], endpoint=endpoint) for endpoint in selected_endpoints]
    source_order: list[str] = []
    for task in tasks:
        if task.source_key not in source_order:
            source_order.append(task.source_key)
    return ResolvedSelection(
        tasks=tasks,
        sources=source_order,
        endpoints=[task.endpoint_key for task in tasks],
        profile=resolved_profile,
        selection_mode=selection_mode,
    )


def _skip_warning(endpoint: EndpointConfig, reason: str) -> str:
    if endpoint.mode == "manual":
        return f"{endpoint.key}: manual endpoint; open the source URL directly"
    if endpoint.mode == "toc_watch":
        return f"{endpoint.key}: toc_watch is declared but not implemented"
    if reason.startswith("status:"):
        return f"{endpoint.key}: endpoint status is {reason.split(':', 1)[1]}; not fetched"
    if reason == "disabled":
        return f"{endpoint.key}: endpoint is disabled; not fetched"
    if reason == "missing_feed_url":
        return f"{endpoint.key}: feed endpoint is missing url; not fetched"
    if reason.startswith("unsupported_mode:"):
        return f"{endpoint.key}: endpoint mode {endpoint.mode} is not implemented; not fetched"
    return f"{endpoint.key}: endpoint is not runnable ({reason}); not fetched"


def _endpoint_timeout(endpoint: EndpointConfig, fallback_seconds: float) -> float:
    configured = endpoint.timeout_seconds
    if configured is None or configured <= 0:
        return fallback_seconds
    return min(float(configured), float(fallback_seconds))


def endpoint_request_profile(endpoint: EndpointConfig, fallback_profile: str = "paperlite") -> str:
    configured = str(endpoint.request_profile or "").strip()
    return configured or fallback_profile


def fetch_endpoint(
    task: EndpointTask,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    timeout_seconds: float = RUNNER_TIMEOUT_SECONDS,
) -> FetchResult:
    endpoint = task.endpoint
    skip_reason = endpoint_skip_reason(endpoint)
    if skip_reason:
        return FetchResult(
            task.source_key,
            task.source.name,
            task.endpoint_key,
            endpoint.mode,
            [],
            [_skip_warning(endpoint, skip_reason)],
        )

    try:
        if endpoint.mode in FEED_ENDPOINT_MODES:
            config = source_config_from_records(task.source, endpoint)
            papers = JournalFeedConnector(config=config).fetch_latest(
                since=since,
                until=until,
                limit=limit,
                timeout_seconds=_endpoint_timeout(endpoint, timeout_seconds),
                request_profile=endpoint_request_profile(endpoint),
            )
        else:
            from paperlite.registry import get_connector

            papers = get_connector(task.source_key).fetch_latest(
                since=since,
                until=until,
                limit=limit,
                timeout_seconds=_endpoint_timeout(endpoint, timeout_seconds),
            )
        papers = sorted(dedupe_papers(papers), key=lambda paper: paper.published_at or datetime.min, reverse=True)
        return FetchResult(task.source_key, task.source.name, task.endpoint_key, endpoint.mode, papers[:limit], [])
    except Exception as exc:
        error = f"{task.endpoint_key}: {exc}"
        return FetchResult(task.source_key, task.source.name, task.endpoint_key, endpoint.mode, [], [error], error)


def run_tasks(
    tasks: list[EndpointTask],
    *,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    timeout_seconds: int = RUNNER_TIMEOUT_SECONDS,
) -> list[FetchResult]:
    if not tasks:
        return []
    results: dict[str, FetchResult] = {}
    executor = ThreadPoolExecutor(max_workers=max(1, min(len(tasks), 6)))
    timed_out = False
    try:
        futures = {
            executor.submit(fetch_endpoint, task, since, until, limit, timeout_seconds): task
            for task in tasks
        }
        try:
            for future in as_completed(futures, timeout=timeout_seconds):
                task = futures[future]
                results[task.endpoint_key] = future.result()
        except TimeoutError:
            timed_out = True
        for future, task in futures.items():
            if task.endpoint_key in results:
                continue
            if future.done():
                results[task.endpoint_key] = future.result()
                continue
            if not future.done():
                future.cancel()
                results[task.endpoint_key] = FetchResult(
                    task.source_key,
                    task.source.name,
                    task.endpoint_key,
                    task.endpoint.mode,
                    [],
                    [f"{task.endpoint_key}: timed out after {timeout_seconds}s"],
                    f"{task.endpoint_key}: timed out after {timeout_seconds}s",
                )
    finally:
        executor.shutdown(wait=not timed_out, cancel_futures=True)
    return [results[task.endpoint_key] for task in tasks if task.endpoint_key in results]


def run_latest(
    *,
    endpoint: str | Iterable[str] | None = None,
    source: str | Iterable[str] | None = None,
    profile: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
) -> tuple[ResolvedSelection, list[FetchResult]]:
    selection = resolve_selection(endpoint=endpoint, source=source, profile=profile)
    results = run_tasks(selection.tasks, since=since, until=until, limit=limit)
    return selection, results


def flatten_results(results: list[FetchResult], limit: int) -> list[Paper]:
    papers = [paper for result in results for paper in result.papers]
    papers = sorted(dedupe_papers(papers), key=lambda paper: paper.published_at or datetime.min, reverse=True)
    return papers[:limit]
