from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable

from paperlite.config import DEFAULT_RUNTIME_DIR
from paperlite.connectors.base import SourceRecord
from paperlite.connectors.journals import JournalFeedConnector
from paperlite.models import Paper
from paperlite.runner import EndpointTask, FetchResult, endpoint_request_profile, split_keys
from paperlite.sources import (
    FEED_ENDPOINT_MODES,
    IMPLEMENTED_ENDPOINT_MODES,
    endpoint_skip_reason,
    is_runnable_endpoint,
    load_endpoint_configs,
    load_source_records,
    normalize_endpoint_mode,
    source_config_from_records,
)
from paperlite.taxonomy import canonical_disciplines, canonicalize_discipline

DEFAULT_SOURCE_AUDIT_SNAPSHOT_PATH = DEFAULT_RUNTIME_DIR / "source_audit_snapshot.json"
DEFAULT_AUDIT_SAMPLE_SIZE = 3
DEFAULT_AUDIT_BATCH_LIMIT = 100
MAX_AUDIT_BATCH_LIMIT = 200
MAX_AUDIT_SAMPLE_SIZE = 20

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"

ISSUE_FETCH_FAILED = "fetch_failed"
ISSUE_ZERO_ITEMS = "zero_items"
ISSUE_MISSING_DOI = "missing_doi"
ISSUE_MISSING_ABSTRACT = "missing_abstract"
ISSUE_MISSING_DATE = "missing_date"
ISSUE_MISSING_URL = "missing_url"
ISSUE_MISSING_TITLE = "missing_title"
ISSUE_DUPLICATE_ITEMS = "duplicate_items"

DOI_EXPECTED_SOURCE_KINDS = {"journal", "preprint"}


@dataclass(frozen=True)
class SourceAuditResult:
    endpoint_key: str
    source_key: str
    source_name: str
    source_kind: str
    endpoint_mode: str
    status: str
    issue_tags: list[str]
    message: str
    checked_at: str
    elapsed_ms: int
    requested_sample_size: int
    item_count: int
    doi_missing_count: int = 0
    abstract_missing_count: int = 0
    date_missing_count: int = 0
    url_missing_count: int = 0
    title_missing_count: int = 0
    duplicate_count: int = 0
    warnings: list[str] | None = None
    sample_items: list[dict[str, object]] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "endpoint_key": self.endpoint_key,
            "source_key": self.source_key,
            "source_name": self.source_name,
            "source_kind": self.source_kind,
            "endpoint_mode": self.endpoint_mode,
            "status": self.status,
            "issue_tags": list(self.issue_tags),
            "message": self.message,
            "checked_at": self.checked_at,
            "elapsed_ms": self.elapsed_ms,
            "requested_sample_size": self.requested_sample_size,
            "item_count": self.item_count,
            "doi_missing_count": self.doi_missing_count,
            "abstract_missing_count": self.abstract_missing_count,
            "date_missing_count": self.date_missing_count,
            "url_missing_count": self.url_missing_count,
            "title_missing_count": self.title_missing_count,
            "duplicate_count": self.duplicate_count,
            "warnings": list(self.warnings or []),
            "sample_items": list(self.sample_items or []),
        }


AuditFetcher = Callable[[EndpointTask, int, float, str], FetchResult]


def checked_at_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clamp_int(value: int | str | None, default: int, *, minimum: int, maximum: int) -> int:
    try:
        selected = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        selected = int(default)
    return max(minimum, min(maximum, selected))


def _allowed_modes(mode: str | None) -> set[str]:
    selected = normalize_endpoint_mode(mode)
    if selected in {None, "", "feed"}:
        return set(FEED_ENDPOINT_MODES)
    if selected in {"all", "*"}:
        return set(IMPLEMENTED_ENDPOINT_MODES)
    if selected not in IMPLEMENTED_ENDPOINT_MODES:
        raise ValueError(f"unknown endpoint mode: {mode}")
    return {selected}


def _source_matches_discipline(source: SourceRecord, discipline: str | None) -> bool:
    if not discipline:
        return True
    selected = canonicalize_discipline(discipline)
    if not selected:
        return True
    canonical = canonical_disciplines(tuple(source.disciplines or source.topics))
    return selected in canonical


def select_audit_tasks(
    *,
    discipline: str | None = None,
    source: str | Iterable[str] | None = None,
    mode: str | None = None,
    limit: int = DEFAULT_AUDIT_BATCH_LIMIT,
    offset: int = 0,
) -> tuple[list[EndpointTask], dict[str, object]]:
    sources = {item.key: item for item in load_source_records()}
    endpoints = list(load_endpoint_configs())
    requested_sources = set(split_keys(source))
    missing_sources = sorted(requested_sources - set(sources))
    if missing_sources:
        raise ValueError(f"unknown source: {', '.join(missing_sources)}")

    allowed_modes = _allowed_modes(mode)
    filtered: list[EndpointTask] = []
    for endpoint in sorted(endpoints, key=lambda item: (item.source_key, item.priority, item.key)):
        if endpoint.mode not in allowed_modes:
            continue
        if not is_runnable_endpoint(endpoint):
            continue
        source_record = sources.get(endpoint.source_key)
        if source_record is None:
            continue
        if requested_sources and endpoint.source_key not in requested_sources:
            continue
        if not _source_matches_discipline(source_record, discipline):
            continue
        filtered.append(EndpointTask(source=source_record, endpoint=endpoint))

    start = max(0, int(offset or 0))
    batch_limit = max(1, int(limit or DEFAULT_AUDIT_BATCH_LIMIT))
    tasks = filtered[start : start + batch_limit]
    next_offset = start + batch_limit if start + batch_limit < len(filtered) else None
    return tasks, {
        "total_selected": len(filtered),
        "offset": start,
        "limit": batch_limit,
        "next_offset": next_offset,
        "mode": sorted(allowed_modes),
    }


def fetch_audit_endpoint(
    task: EndpointTask,
    sample_size: int,
    timeout_seconds: float,
    request_profile: str = "paperlite",
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
            [f"{endpoint.key}: endpoint is not runnable ({skip_reason})"],
        )
    try:
        if endpoint.mode in FEED_ENDPOINT_MODES:
            config = source_config_from_records(task.source, endpoint)
            papers = JournalFeedConnector(config=config).fetch_latest(
                limit=sample_size,
                timeout_seconds=timeout_seconds,
                request_profile=endpoint_request_profile(endpoint, request_profile),
            )
        else:
            from paperlite.registry import get_connector

            papers = get_connector(task.source_key).fetch_latest(limit=sample_size, timeout_seconds=timeout_seconds)
        return FetchResult(task.source_key, task.source.name, task.endpoint_key, endpoint.mode, papers[:sample_size], [])
    except Exception as exc:
        return FetchResult(task.source_key, task.source.name, task.endpoint_key, endpoint.mode, [], [f"{endpoint.key}: {exc}"])


def _norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _paper_duplicate_key(paper: Paper) -> str:
    for value in (paper.doi, paper.url, paper.id, paper.title):
        text = _norm_text(value).lower()
        if text:
            return text
    return ""


def _sample_items(papers: list[Paper], limit: int) -> list[dict[str, object]]:
    items = []
    for paper in papers[:limit]:
        items.append(
            {
                "id": paper.id,
                "title": paper.title,
                "doi": paper.doi,
                "url": paper.url,
                "published_at": paper.published_at.isoformat() if paper.published_at else None,
            }
        )
    return items


def audit_fetch_result(
    task: EndpointTask,
    result: FetchResult,
    *,
    sample_size: int,
    elapsed_ms: int = 0,
    checked_at: str | None = None,
) -> SourceAuditResult:
    papers = list(result.papers or [])
    issue_tags: list[str] = []
    warnings = list(result.warnings or [])
    if warnings and not papers:
        issue_tags.append(ISSUE_FETCH_FAILED)

    item_count = len(papers)
    doi_expected = task.source.source_kind in DOI_EXPECTED_SOURCE_KINDS
    doi_missing = sum(1 for paper in papers if not _norm_text(paper.doi))
    abstract_missing = sum(1 for paper in papers if not _norm_text(paper.abstract))
    date_missing = sum(1 for paper in papers if paper.published_at is None)
    url_missing = sum(1 for paper in papers if not _norm_text(paper.url))
    title_missing = sum(1 for paper in papers if not _norm_text(paper.title))
    keys = [_paper_duplicate_key(paper) for paper in papers]
    duplicate_count = len(keys) - len({key for key in keys if key})

    if not papers and not warnings:
        issue_tags.append(ISSUE_ZERO_ITEMS)
    if papers and doi_expected and doi_missing / item_count >= 0.5:
        issue_tags.append(ISSUE_MISSING_DOI)
    if papers and abstract_missing / item_count >= 0.5:
        issue_tags.append(ISSUE_MISSING_ABSTRACT)
    if papers and date_missing / item_count >= 0.5:
        issue_tags.append(ISSUE_MISSING_DATE)
    if papers and url_missing:
        issue_tags.append(ISSUE_MISSING_URL)
    if papers and title_missing:
        issue_tags.append(ISSUE_MISSING_TITLE)
    if papers and duplicate_count >= max(1, item_count // 3):
        issue_tags.append(ISSUE_DUPLICATE_ITEMS)

    issue_tags = list(dict.fromkeys(issue_tags))
    status = STATUS_OK
    if ISSUE_FETCH_FAILED in issue_tags:
        status = STATUS_FAIL
    elif issue_tags or warnings:
        status = STATUS_WARN

    if status == STATUS_OK:
        message = f"OK: sampled {item_count} items."
    elif status == STATUS_FAIL:
        message = warnings[0] if warnings else "Fetch failed."
    else:
        message = ", ".join(issue_tags or warnings[:2])

    return SourceAuditResult(
        endpoint_key=task.endpoint_key,
        source_key=task.source_key,
        source_name=task.source.name,
        source_kind=task.source.source_kind,
        endpoint_mode=task.endpoint.mode,
        status=status,
        issue_tags=issue_tags,
        message=message,
        checked_at=checked_at or checked_at_now(),
        elapsed_ms=elapsed_ms,
        requested_sample_size=sample_size,
        item_count=item_count,
        doi_missing_count=doi_missing,
        abstract_missing_count=abstract_missing,
        date_missing_count=date_missing,
        url_missing_count=url_missing,
        title_missing_count=title_missing,
        duplicate_count=duplicate_count,
        warnings=warnings,
        sample_items=_sample_items(papers, sample_size),
    )


def _severity_rank(status: str) -> int:
    return {STATUS_FAIL: 2, STATUS_WARN: 1, STATUS_OK: 0}.get(status, 0)


def summarize_audit_results(results: list[dict[str, object] | SourceAuditResult]) -> dict[str, object]:
    rows = [result.to_dict() if isinstance(result, SourceAuditResult) else dict(result) for result in results]
    status_counts = Counter(str(row.get("status") or STATUS_WARN) for row in rows)
    issue_counts: Counter[str] = Counter()
    for row in rows:
        for tag in row.get("issue_tags") or []:
            issue_counts[str(tag)] += 1
    top_problem_sources = sorted(
        [row for row in rows if row.get("status") != STATUS_OK],
        key=lambda row: (
            -_severity_rank(str(row.get("status") or "")),
            -len(row.get("issue_tags") or []),
            str(row.get("source_key") or ""),
            str(row.get("endpoint_key") or ""),
        ),
    )[:20]
    return {
        "checked_count": len(rows),
        "ok": status_counts.get(STATUS_OK, 0),
        "warn": status_counts.get(STATUS_WARN, 0),
        "fail": status_counts.get(STATUS_FAIL, 0),
        "status_counts": dict(sorted(status_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "problem_count": sum(1 for row in rows if row.get("status") != STATUS_OK),
        "top_problem_sources": [
            {
                "endpoint_key": row.get("endpoint_key"),
                "source_key": row.get("source_key"),
                "source_name": row.get("source_name"),
                "status": row.get("status"),
                "issue_tags": row.get("issue_tags") or [],
                "message": row.get("message"),
                "item_count": row.get("item_count"),
            }
            for row in top_problem_sources
        ],
    }


def source_audit_snapshot_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else DEFAULT_SOURCE_AUDIT_SNAPSHOT_PATH


def read_source_audit_snapshot(path: str | Path | None = None) -> dict[str, object]:
    selected = source_audit_snapshot_path(path)
    if not selected.exists():
        summary = summarize_audit_results([])
        return {"loaded": False, "path": str(selected), "updated_at": None, "audit": [], "summary": summary}
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except Exception:
        summary = summarize_audit_results([])
        return {"loaded": False, "path": str(selected), "updated_at": None, "audit": [], "summary": summary, "error": "snapshot_parse_failed"}
    rows = payload.get("audit") if isinstance(payload, dict) else []
    rows = rows if isinstance(rows, list) else []
    summary = summarize_audit_results([row for row in rows if isinstance(row, dict)])
    return {
        "loaded": True,
        "path": str(selected),
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "params": payload.get("params") if isinstance(payload, dict) else {},
        "audit": rows,
        "summary": summary,
    }


def merge_source_audit_snapshot(
    results: list[SourceAuditResult],
    *,
    path: str | Path | None = None,
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    selected = source_audit_snapshot_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    existing = read_source_audit_snapshot(selected)
    by_key: dict[str, dict[str, object]] = {}
    for row in existing.get("audit") or []:
        if isinstance(row, dict) and row.get("endpoint_key"):
            by_key[str(row["endpoint_key"])] = dict(row)
    for result in results:
        by_key[result.endpoint_key] = result.to_dict()
    rows = sorted(by_key.values(), key=lambda row: (str(row.get("source_key") or ""), str(row.get("endpoint_key") or "")))
    updated_at = checked_at_now()
    payload = {
        "updated_at": updated_at,
        "params": dict(params or {}),
        "summary": summarize_audit_results(rows),
        "audit": rows,
    }
    selected.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "path": str(selected),
        "count": len(rows),
        "updated": len(results),
        "updated_at": updated_at,
        "summary": payload["summary"],
    }


def replace_source_audit_snapshot(
    rows: list[dict[str, object]] | list[SourceAuditResult],
    *,
    path: str | Path | None = None,
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    selected = source_audit_snapshot_path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = [
        row.to_dict() if isinstance(row, SourceAuditResult) else dict(row)
        for row in rows
    ]
    normalized_rows.sort(key=lambda row: (str(row.get("source_key") or ""), str(row.get("endpoint_key") or "")))
    updated_at = checked_at_now()
    payload = {
        "updated_at": updated_at,
        "params": dict(params or {}),
        "summary": summarize_audit_results(normalized_rows),
        "audit": normalized_rows,
    }
    selected.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "path": str(selected),
        "count": len(normalized_rows),
        "updated": len(normalized_rows),
        "updated_at": updated_at,
        "summary": payload["summary"],
    }


def run_source_audit(
    *,
    discipline: str | None = None,
    source: str | Iterable[str] | None = None,
    mode: str | None = None,
    limit: int = DEFAULT_AUDIT_BATCH_LIMIT,
    offset: int = 0,
    sample_size: int = DEFAULT_AUDIT_SAMPLE_SIZE,
    timeout_seconds: float = 5.0,
    request_profile: str = "paperlite",
    write_snapshot: bool = False,
    snapshot_path: str | Path | None = None,
    fetcher: AuditFetcher = fetch_audit_endpoint,
) -> dict[str, object]:
    batch_limit = _clamp_int(limit, DEFAULT_AUDIT_BATCH_LIMIT, minimum=1, maximum=MAX_AUDIT_BATCH_LIMIT)
    selected_sample_size = _clamp_int(sample_size, DEFAULT_AUDIT_SAMPLE_SIZE, minimum=1, maximum=MAX_AUDIT_SAMPLE_SIZE)
    selected_timeout = max(1.0, min(float(timeout_seconds or 5.0), 30.0))
    profile = str(request_profile or "paperlite").strip()
    if profile not in {"paperlite", "browser_compat"}:
        raise ValueError("request_profile must be paperlite or browser_compat")

    tasks, selection = select_audit_tasks(
        discipline=discipline,
        source=source,
        mode=mode,
        limit=batch_limit,
        offset=max(0, int(offset or 0)),
    )
    checked_at = checked_at_now()
    results_by_index: dict[int, SourceAuditResult] = {}

    def audit_one(index: int, task: EndpointTask) -> tuple[int, SourceAuditResult]:
        started = perf_counter()
        fetch_result = fetcher(task, selected_sample_size, selected_timeout, profile)
        elapsed_ms = int((perf_counter() - started) * 1000)
        return index, (
            audit_fetch_result(
                task,
                fetch_result,
                sample_size=selected_sample_size,
                elapsed_ms=elapsed_ms,
                checked_at=checked_at,
            )
        )

    if tasks:
        with ThreadPoolExecutor(max_workers=max(1, min(len(tasks), 8))) as executor:
            futures = {executor.submit(audit_one, index, task): index for index, task in enumerate(tasks)}
            for future in as_completed(futures):
                index, result = future.result()
                results_by_index[index] = result
    results = [results_by_index[index] for index in range(len(tasks)) if index in results_by_index]
    params = {
        "discipline": discipline,
        "source": ",".join(split_keys(source)),
        "mode": mode,
        "limit": batch_limit,
        "offset": selection["offset"],
        "sample_size": selected_sample_size,
        "timeout_seconds": selected_timeout,
        "request_profile": profile,
    }
    payload: dict[str, object] = {
        "checked": len(results),
        "total_selected": selection["total_selected"],
        "offset": selection["offset"],
        "limit": batch_limit,
        "next_offset": selection["next_offset"],
        "sample_size": selected_sample_size,
        "results": [result.to_dict() for result in results],
        "summary": summarize_audit_results(results),
        "params": params,
    }
    if write_snapshot:
        payload["snapshot"] = merge_source_audit_snapshot(results, path=snapshot_path, params=params)
    return payload


def format_source_audit_markdown(payload: dict[str, object]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# PaperLite Source Content Audit",
        "",
        f"- checked: {summary.get('checked_count', payload.get('checked', 0))}",
        f"- ok/warn/fail: {summary.get('ok', 0)}/{summary.get('warn', 0)}/{summary.get('fail', 0)}",
        f"- problems: {summary.get('problem_count', 0)}",
        f"- next_offset: {payload.get('next_offset') if payload.get('next_offset') is not None else '-'}",
        "",
    ]
    issue_counts = summary.get("issue_counts") or {}
    if issue_counts:
        lines.append("## Issues")
        for key, value in sorted(issue_counts.items()):
            lines.append(f"- {key}: {value}")
        lines.append("")
    rows = payload.get("results") or payload.get("audit") or []
    if rows:
        lines.append("## Results")
        for row in rows:
            tags = ", ".join(row.get("issue_tags") or []) if isinstance(row, dict) else ""
            lines.append(
                f"- {row.get('status')} {row.get('endpoint_key')} -> {row.get('source_key')}: "
                f"{row.get('item_count')} items"
                + (f" [{tags}]" if tags else "")
            )
    return "\n".join(lines)
