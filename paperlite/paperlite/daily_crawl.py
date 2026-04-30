from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from paperlite.config import runtime_config
from paperlite.daily_dates import daily_window, today_local
from paperlite.profiles import multidisciplinary_supplement_source_keys
from paperlite.registry import list_sources
from paperlite.runner import resolve_selection, run_tasks, split_keys
from paperlite.storage import (
    create_or_update_crawl_schedule,
    create_crawl_run,
    delete_crawl_schedule,
    due_crawl_schedules,
    finish_crawl_run,
    get_crawl_run,
    list_crawl_schedules,
    mark_crawl_schedule_finished,
    mark_crawl_schedule_started,
    mark_crawl_running,
    record_source_result,
    store_daily_papers,
    update_crawl_schedule_status,
)

MAX_CRAWL_DAYS = 31
DEFAULT_CRAWL_LIMIT_PER_SOURCE = 100
MAX_SCHEDULE_LOOKBACK_DAYS = 30
MULTIDISCIPLINARY_DISCIPLINE_KEY = "multidisciplinary"

_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_STARTED = False
_SCHEDULER_STATUS_LOCK = threading.Lock()
_SCHEDULER_STATUS: dict[str, object | None] = {
    "last_poll_started_at": None,
    "last_success_at": None,
    "last_error_at": None,
    "last_error": None,
    "last_exception_type": None,
}


@dataclass(frozen=True)
class CrawlRequest:
    date_from: str
    date_to: str
    discipline_key: str
    source_keys: list[str]
    limit_per_source: int


def crawl_cooldown_seconds() -> int:
    return runtime_config().crawl_cooldown_seconds


def crawl_source_delay_seconds() -> float:
    return runtime_config().crawl_source_delay_seconds


def schedule_min_interval_minutes() -> int:
    return runtime_config().schedule_min_interval_minutes


def scheduler_poll_seconds() -> int:
    return runtime_config().scheduler_poll_seconds


def _parse_day(value: str | None, field: str) -> date:
    if not value:
        raise ValueError(f"{field} is required")
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def iter_days(date_from: str, date_to: str) -> list[str]:
    start = _parse_day(date_from, "date_from")
    end = _parse_day(date_to, "date_to")
    if start > end:
        raise ValueError("date_from must be before or equal to date_to")
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    if len(days) > MAX_CRAWL_DAYS:
        raise ValueError(f"date range must be {MAX_CRAWL_DAYS} days or fewer")
    return days


def _source_matches_discipline(
    source: dict,
    discipline_key: str,
    *,
    supplement_source_keys: set[str] | None = None,
) -> bool:
    direct_match = (
        source.get("primary_discipline_key") == discipline_key
        or discipline_key in (source.get("discipline_keys") or [])
    )
    if direct_match:
        return True
    if discipline_key == MULTIDISCIPLINARY_DISCIPLINE_KEY:
        return False
    return bool(
        str(source.get("name") or "") in (supplement_source_keys or set())
        and MULTIDISCIPLINARY_DISCIPLINE_KEY in (source.get("discipline_keys") or [])
    )


def resolve_crawl_source_keys(
    *,
    discipline_key: str,
    source: str | Iterable[str] | None = None,
) -> list[str]:
    discipline = str(discipline_key or "").strip()
    if not discipline:
        raise ValueError("discipline is required")
    requested = set(split_keys(source))
    supplement_source_keys = multidisciplinary_supplement_source_keys()
    resolved = []
    for item in list_sources():
        key = str(item.get("name") or "")
        if requested and key not in requested:
            continue
        if not item.get("supports_latest"):
            continue
        if not _source_matches_discipline(
            item,
            discipline,
            supplement_source_keys=supplement_source_keys,
        ):
            continue
        resolved.append(key)
    if requested and not resolved:
        raise ValueError("selected sources do not match the selected discipline or cannot fetch latest")
    if not requested and not resolved:
        raise ValueError("no latest-capable sources found for this discipline")
    return sorted(dict.fromkeys(resolved))


def build_crawl_request(
    *,
    date_from: str,
    date_to: str,
    discipline: str,
    source: str | Iterable[str] | None = None,
    limit_per_source: int = DEFAULT_CRAWL_LIMIT_PER_SOURCE,
) -> CrawlRequest:
    days = iter_days(date_from, date_to)
    discipline_key = str(discipline or "").strip()
    if not discipline_key:
        raise ValueError("discipline is required")
    limit = max(1, min(int(limit_per_source), 500))
    return CrawlRequest(
        date_from=days[0],
        date_to=days[-1],
        discipline_key=discipline_key,
        source_keys=resolve_crawl_source_keys(discipline_key=discipline_key, source=source),
        limit_per_source=limit,
    )


def create_daily_crawl(
    *,
    date_from: str,
    date_to: str,
    discipline: str,
    source: str | Iterable[str] | None = None,
    limit_per_source: int = DEFAULT_CRAWL_LIMIT_PER_SOURCE,
    reuse_within_seconds: int | None = None,
    db_path: str | Path | None = None,
) -> dict:
    request = build_crawl_request(
        date_from=date_from,
        date_to=date_to,
        discipline=discipline,
        source=source,
        limit_per_source=limit_per_source,
    )
    return create_crawl_run(
        date_from=request.date_from,
        date_to=request.date_to,
        discipline_key=request.discipline_key,
        source_keys=request.source_keys,
        limit_per_source=request.limit_per_source,
        reuse_within_seconds=crawl_cooldown_seconds() if reuse_within_seconds is None else reuse_within_seconds,
        path=db_path,
    )


def _tasks_grouped_by_source(tasks):
    grouped = []
    index = {}
    for task in tasks:
        if task.source_key not in index:
            index[task.source_key] = len(grouped)
            grouped.append([])
        grouped[index[task.source_key]].append(task)
    return grouped


def run_daily_crawl(run_id: str, *, db_path: str | Path | None = None) -> None:
    run = get_crawl_run(run_id, path=db_path)
    if run is None:
        return
    if run["status"] == "completed":
        return
    total_items = 0
    warnings: list[str] = []
    attempted_endpoints = 0
    successful_endpoints = 0
    endpoint_errors: list[str] = []
    try:
        mark_crawl_running(run_id, path=db_path)
        selection = resolve_selection(source=run["source_keys"])
        task_groups = _tasks_grouped_by_source(selection.tasks)
        source_delay = crawl_source_delay_seconds()
        first_batch = True
        for day in iter_days(run["date_from"], run["date_to"]):
            _, since, until = daily_window(day)
            for tasks in task_groups:
                if not first_batch and source_delay > 0:
                    time.sleep(source_delay)
                first_batch = False
                results = run_tasks(tasks, since=since, until=until, limit=run["limit_per_source"])
                for result in results:
                    attempted_endpoints += 1
                    if result.error:
                        endpoint_errors.append(str(result.error))
                    else:
                        successful_endpoints += 1
                    stored = store_daily_papers(
                        run_id=run_id,
                        entry_date=day,
                        discipline_key=run["discipline_key"],
                        source_key=result.source_key,
                        papers=result.papers,
                        path=db_path,
                    )
                    total_items += stored
                    result_warnings = list(result.warnings)
                    warnings.extend(result_warnings)
                    record_source_result(
                        run_id=run_id,
                        source_key=result.source_key,
                        endpoint_key=result.endpoint_key,
                        endpoint_mode=result.endpoint_mode,
                        count=len(result.papers),
                        warnings=result_warnings,
                        error=result.error,
                        path=db_path,
                    )
        failed_all_attempted = (
            total_items == 0
            and attempted_endpoints > 0
            and endpoint_errors
            and successful_endpoints == 0
        )
        status = "failed" if failed_all_attempted else "completed"
        error = None
        if failed_all_attempted:
            first_error = endpoint_errors[0]
            error = first_error if len(endpoint_errors) == 1 else f"{len(endpoint_errors)} endpoints failed; first: {first_error}"
        if status == "completed" and total_items == 0 and "no_items_matched_date_range" not in warnings:
            warnings.append("no_items_matched_date_range")
        finish_crawl_run(
            run_id,
            status=status,
            total_items=total_items,
            warnings=warnings,
            error=error,
            path=db_path,
        )
    except Exception as exc:
        finish_crawl_run(
            run_id,
            status="failed",
            total_items=total_items,
            warnings=warnings,
            error=str(exc),
            path=db_path,
        )


def create_daily_schedule(
    *,
    discipline: str,
    source: str | Iterable[str] | None = None,
    interval_minutes: int,
    lookback_days: int = 0,
    limit_per_source: int = DEFAULT_CRAWL_LIMIT_PER_SOURCE,
    run_now: bool = False,
    db_path: str | Path | None = None,
) -> dict:
    discipline_key = str(discipline or "").strip()
    if not discipline_key:
        raise ValueError("discipline is required")
    interval = max(schedule_min_interval_minutes(), int(interval_minutes))
    lookback = max(0, min(int(lookback_days), MAX_SCHEDULE_LOOKBACK_DAYS))
    limit = max(1, min(int(limit_per_source), 500))
    source_keys = resolve_crawl_source_keys(discipline_key=discipline_key, source=source)
    return create_or_update_crawl_schedule(
        discipline_key=discipline_key,
        source_keys=source_keys,
        limit_per_source=limit,
        interval_minutes=interval,
        lookback_days=lookback,
        run_now=run_now,
        path=db_path,
    )


def list_daily_schedules(*, db_path: str | Path | None = None) -> list[dict]:
    return list_crawl_schedules(path=db_path)


def update_daily_schedule_status(
    schedule_id: str,
    *,
    status: str,
    db_path: str | Path | None = None,
) -> dict | None:
    return update_crawl_schedule_status(schedule_id, status=status, path=db_path)


def delete_daily_schedule(schedule_id: str, *, db_path: str | Path | None = None) -> bool:
    return delete_crawl_schedule(schedule_id, path=db_path)


def _scheduled_date_range(lookback_days: int) -> tuple[str, str]:
    end = today_local()
    start = end - timedelta(days=max(0, min(int(lookback_days), MAX_SCHEDULE_LOOKBACK_DAYS)))
    return start.isoformat(), end.isoformat()


def run_due_schedules_once(*, db_path: str | Path | None = None) -> list[dict]:
    ran = []
    for schedule in due_crawl_schedules(path=db_path):
        next_run_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=schedule["interval_minutes"])
        try:
            date_from, date_to = _scheduled_date_range(schedule["lookback_days"])
            run = create_daily_crawl(
                date_from=date_from,
                date_to=date_to,
                discipline=schedule["discipline_key"],
                source=schedule["source_keys"],
                limit_per_source=schedule["limit_per_source"],
                db_path=db_path,
            )
            mark_crawl_schedule_started(
                schedule["schedule_id"],
                run_id=run["run_id"],
                next_run_at=next_run_at,
                path=db_path,
            )
            if not run.get("reused") and run.get("status") == "queued":
                run_daily_crawl(run["run_id"], db_path=db_path)
            finished = get_crawl_run(run["run_id"], path=db_path) or run
            mark_crawl_schedule_finished(
                schedule["schedule_id"],
                warnings=finished.get("warnings") or [],
                error=finished.get("error"),
                path=db_path,
            )
            ran.append({"schedule": schedule["schedule_id"], "run": finished})
        except Exception as exc:
            mark_crawl_schedule_finished(
                schedule["schedule_id"],
                error=str(exc),
                path=db_path,
            )
            ran.append({"schedule": schedule["schedule_id"], "error": str(exc)})
    return ran


def _record_scheduler_poll_start() -> None:
    with _SCHEDULER_STATUS_LOCK:
        _SCHEDULER_STATUS["last_poll_started_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _record_scheduler_poll_success() -> None:
    with _SCHEDULER_STATUS_LOCK:
        _SCHEDULER_STATUS["last_success_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _SCHEDULER_STATUS["last_error"] = None
        _SCHEDULER_STATUS["last_error_at"] = None
        _SCHEDULER_STATUS["last_exception_type"] = None


def _record_scheduler_poll_error(exc: Exception) -> None:
    with _SCHEDULER_STATUS_LOCK:
        _SCHEDULER_STATUS["last_error_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _SCHEDULER_STATUS["last_error"] = str(exc)
        _SCHEDULER_STATUS["last_exception_type"] = type(exc).__name__


def scheduler_loop_status() -> dict[str, object | None]:
    with _SCHEDULER_STATUS_LOCK:
        return dict(_SCHEDULER_STATUS)


def reset_scheduler_loop_status() -> None:
    with _SCHEDULER_STATUS_LOCK:
        for key in _SCHEDULER_STATUS:
            _SCHEDULER_STATUS[key] = None


def run_scheduler_poll_once(*, db_path: str | Path | None = None) -> list[dict]:
    _record_scheduler_poll_start()
    try:
        ran = run_due_schedules_once(db_path=db_path)
    except Exception as exc:
        _record_scheduler_poll_error(exc)
        return [{"scheduler_error": str(exc), "exception_type": type(exc).__name__}]
    _record_scheduler_poll_success()
    return ran


def start_schedule_loop(*, db_path: str | Path | None = None) -> None:
    if not runtime_config().scheduler_enabled:
        return
    global _SCHEDULER_STARTED
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        _SCHEDULER_STARTED = True

    def worker() -> None:
        while True:
            run_scheduler_poll_once(db_path=db_path)
            time.sleep(scheduler_poll_seconds())

    thread = threading.Thread(target=worker, name="paperlite-crawl-scheduler", daemon=True)
    thread.start()
