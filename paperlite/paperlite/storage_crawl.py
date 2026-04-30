from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from paperlite.metadata_cleaning import sanitize_paper
from paperlite.models import Paper
from paperlite.storage_schema import (
    _crawl_request_key,
    _crawl_request_key_for_sources,
    _json_dumps,
    _json_loads,
    _normalized_source_list,
    _now,
    _now_dt,
    _parse_dt,
    _source_keys_json,
    _table_count,
    connect,
    default_db_path,
)

def find_reusable_crawl_run(
    *,
    date_from: str,
    date_to: str,
    discipline_key: str,
    source_keys: Iterable[str],
    limit_per_source: int,
    cooldown_seconds: int,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    request_key = _crawl_request_key_for_sources(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline_key,
        source_keys=source_keys,
        limit_per_source=limit_per_source,
    )
    now = _now_dt()
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, status, started_at FROM crawl_runs
            WHERE request_key = ?
            ORDER BY started_at DESC, rowid DESC
            LIMIT 20
            """,
            (request_key,),
        ).fetchall()
    if not rows:
        return None
    row = rows[0]
    if row["status"] in {"queued", "running"}:
        run = get_crawl_run(row["run_id"], path=path)
        if run:
            run["reused"] = True
            run["reuse_reason"] = "active"
            run["cooldown_seconds_remaining"] = None
            return run
    if row["status"] != "completed":
        return None
    started = _parse_dt(row["started_at"])
    if cooldown_seconds > 0 and started is not None:
        remaining = int(cooldown_seconds - (now - started).total_seconds())
        if remaining > 0:
            run = get_crawl_run(row["run_id"], path=path)
            if run:
                run["reused"] = True
                run["reuse_reason"] = "cooldown"
                run["cooldown_seconds_remaining"] = remaining
                return run
    return None


def create_crawl_run(
    *,
    date_from: str,
    date_to: str,
    discipline_key: str,
    source_keys: Iterable[str],
    limit_per_source: int,
    reuse_within_seconds: int = 0,
    path: str | Path | None = None,
) -> dict[str, Any]:
    source_list = _normalized_source_list(source_keys)
    source_json = _source_keys_json(source_list)
    request_key = _crawl_request_key(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline_key,
        source_keys_json=source_json,
        limit_per_source=limit_per_source,
    )
    if reuse_within_seconds > 0:
        reusable = find_reusable_crawl_run(
            date_from=date_from,
            date_to=date_to,
            discipline_key=discipline_key,
            source_keys=source_list,
            limit_per_source=limit_per_source,
            cooldown_seconds=reuse_within_seconds,
            path=path,
        )
        if reusable:
            return reusable
    run_id = uuid.uuid4().hex
    now = _now()
    reused_active_run_id: str | None = None
    with connect(path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO crawl_runs (
                  run_id, status, date_from, date_to, discipline_key,
                  source_keys_json, limit_per_source, started_at, warnings_json, request_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "queued",
                    date_from,
                    date_to,
                    discipline_key,
                    source_json,
                    int(limit_per_source),
                    now,
                    "[]",
                    request_key,
                ),
            )
        except sqlite3.IntegrityError:
            row = connection.execute(
                """
                SELECT run_id FROM crawl_runs
                WHERE request_key = ? AND status IN ('queued', 'running')
                ORDER BY started_at DESC, rowid DESC
                LIMIT 1
                """,
                (request_key,),
            ).fetchone()
            if row is None:
                raise
            reused_active_run_id = row["run_id"]
    if reused_active_run_id:
        run = get_crawl_run(reused_active_run_id, path=path) or {}
        run["reused"] = True
        run["reuse_reason"] = "active"
        run["cooldown_seconds_remaining"] = None
        return run
    run = get_crawl_run(run_id, path=path) or {}
    run["reused"] = False
    run["reuse_reason"] = None
    run["cooldown_seconds_remaining"] = 0
    return run


def mark_crawl_running(run_id: str, *, path: str | Path | None = None) -> None:
    with connect(path) as connection:
        connection.execute(
            "UPDATE crawl_runs SET status = ?, error = NULL WHERE run_id = ?",
            ("running", run_id),
        )


def finish_crawl_run(
    run_id: str,
    *,
    status: str,
    total_items: int,
    warnings: list[str] | None = None,
    error: str | None = None,
    path: str | Path | None = None,
) -> None:
    with connect(path) as connection:
        connection.execute(
            """
            UPDATE crawl_runs
            SET status = ?, finished_at = ?, total_items = ?, warnings_json = ?, error = ?
            WHERE run_id = ?
            """,
            (
                status,
                _now(),
                int(total_items),
                _json_dumps(warnings or []),
                error,
                run_id,
            ),
        )


def mark_interrupted_crawl_runs_failed(
    *,
    reason: str = "interrupted by server restart",
    path: str | Path | None = None,
) -> int:
    now = _now()
    with connect(path) as connection:
        before = connection.total_changes
        connection.execute(
            """
            UPDATE crawl_runs
            SET status = ?, finished_at = COALESCE(finished_at, ?), error = COALESCE(error, ?)
            WHERE status IN (?, ?)
            """,
            ("failed", now, reason, "queued", "running"),
        )
        return connection.total_changes - before


def upsert_paper(connection: sqlite3.Connection, paper: Paper) -> None:
    cleaned_paper = sanitize_paper(paper)
    payload = cleaned_paper.to_dict()
    connection.execute(
        """
        INSERT INTO paper_items (paper_id, source, title, published_at, payload_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(paper_id) DO UPDATE SET
          source = excluded.source,
          title = excluded.title,
          published_at = excluded.published_at,
          payload_json = excluded.payload_json,
          updated_at = excluded.updated_at
        """,
        (
            cleaned_paper.id,
            cleaned_paper.source,
            cleaned_paper.title,
            cleaned_paper.published_at.isoformat() if cleaned_paper.published_at else None,
            _json_dumps(payload),
            _now(),
        ),
    )


def store_daily_papers(
    *,
    run_id: str,
    entry_date: str,
    discipline_key: str,
    source_key: str,
    papers: Iterable[Paper],
    path: str | Path | None = None,
) -> int:
    created_at = _now()
    stored = 0
    with connect(path) as connection:
        for paper in papers:
            upsert_paper(connection, paper)
            before = connection.total_changes
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_entries (
                  entry_date, discipline_key, source_key, paper_id, run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entry_date, discipline_key, source_key, paper.id, run_id, created_at),
            )
            if connection.total_changes > before:
                stored += 1
    return stored


def record_source_result(
    *,
    run_id: str,
    source_key: str,
    endpoint_key: str,
    endpoint_mode: str,
    count: int,
    warnings: list[str] | None = None,
    error: str | None = None,
    path: str | Path | None = None,
) -> None:
    warnings = warnings or []
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT count, warnings_json, error FROM crawl_source_results
            WHERE run_id = ? AND source_key = ? AND endpoint_key = ?
            """,
            (run_id, source_key, endpoint_key),
        ).fetchone()
        if row:
            merged_warnings = [*_json_loads(row["warnings_json"], []), *warnings]
            merged_error = error or row["error"]
            connection.execute(
                """
                UPDATE crawl_source_results
                SET count = ?, warnings_json = ?, error = ?
                WHERE run_id = ? AND source_key = ? AND endpoint_key = ?
                """,
                (
                    int(row["count"]) + int(count),
                    _json_dumps(merged_warnings),
                    merged_error,
                    run_id,
                    source_key,
                    endpoint_key,
                ),
            )
            return
        connection.execute(
            """
            INSERT INTO crawl_source_results (
              run_id, source_key, endpoint_key, endpoint_mode, count, warnings_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_key,
                endpoint_key,
                endpoint_mode,
                int(count),
                _json_dumps(warnings),
                error,
            ),
        )


def get_crawl_run(run_id: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(path) as connection:
        row = connection.execute("SELECT * FROM crawl_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        source_results = [
            {
                "source": item["source_key"],
                "endpoint": item["endpoint_key"],
                "mode": item["endpoint_mode"],
                "count": item["count"],
                "warnings": _json_loads(item["warnings_json"], []),
                "error": item["error"],
            }
            for item in connection.execute(
                """
                SELECT * FROM crawl_source_results
                WHERE run_id = ?
                ORDER BY source_key, endpoint_key
                """,
                (run_id,),
            )
        ]
    started = _parse_dt(row["started_at"])
    finished = _parse_dt(row["finished_at"])
    duration_seconds = int((finished - started).total_seconds()) if started and finished else None
    return {
        "run_id": row["run_id"],
        "status": row["status"],
        "date_from": row["date_from"],
        "date_to": row["date_to"],
        "discipline_key": row["discipline_key"],
        "source_keys": _json_loads(row["source_keys_json"], []),
        "limit_per_source": row["limit_per_source"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "duration_seconds": duration_seconds,
        "total_items": row["total_items"],
        "warnings": _json_loads(row["warnings_json"], []),
        "error": row["error"],
        "source_results": source_results,
    }


def list_crawl_runs(
    *,
    limit: int = 20,
    status: str | None = None,
    discipline_key: str | None = None,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    selected_status = str(status or "").strip()
    selected_discipline = str(discipline_key or "").strip()
    clauses = []
    params: list[Any] = []
    if selected_status:
        clauses.append("status = ?")
        params.append(selected_status)
    if selected_discipline:
        clauses.append("discipline_key = ?")
        params.append(selected_discipline)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    max_rows = max(1, min(int(limit), 200))
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT run_id FROM crawl_runs
            {where}
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (*params, max_rows),
        ).fetchall()
    return [run for row in rows if (run := get_crawl_run(row["run_id"], path=path))]


RUNTIME_SUMMARY_TABLES = (
    "crawl_runs",
    "paper_items",
    "daily_entries",
    "crawl_source_results",
    "crawl_schedules",
    "translation_cache",
    "library_items",
    "library_events",
    "saved_views",
    "preference_prompts",
    "preference_query_history",
    "preference_settings",
    "preference_profile",
)


def runtime_storage_summary(*, path: str | Path | None = None) -> dict[str, Any]:
    db_path = Path(path) if path else default_db_path()
    with connect(path) as connection:
        table_counts = {table: _table_count(connection, table) or 0 for table in RUNTIME_SUMMARY_TABLES}
        latest_cache_row = connection.execute("SELECT MAX(entry_date) FROM daily_entries").fetchone()
        latest_paper_row = connection.execute("SELECT MAX(updated_at) FROM paper_items").fetchone()
    return {
        "db_path": str(db_path),
        "table_counts": table_counts,
        "cache_item_count": table_counts.get("paper_items", 0),
        "daily_entry_count": table_counts.get("daily_entries", 0),
        "latest_cache_date": latest_cache_row[0] if latest_cache_row else None,
        "latest_paper_updated_at": latest_paper_row[0] if latest_paper_row else None,
    }


def _schedule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schedule_id": row["schedule_id"],
        "status": row["status"],
        "discipline_key": row["discipline_key"],
        "source_keys": _json_loads(row["source_keys_json"], []),
        "limit_per_source": row["limit_per_source"],
        "interval_minutes": row["interval_minutes"],
        "lookback_days": row["lookback_days"],
        "next_run_at": row["next_run_at"],
        "last_run_id": row["last_run_id"],
        "last_started_at": row["last_started_at"],
        "last_finished_at": row["last_finished_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "warnings": _json_loads(row["warnings_json"], []),
        "error": row["error"],
    }


def get_crawl_schedule(schedule_id: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM crawl_schedules WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
    return _schedule_from_row(row) if row else None


def list_crawl_schedules(*, path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM crawl_schedules
            ORDER BY status ASC, next_run_at ASC, created_at ASC
            """
        ).fetchall()
    return [_schedule_from_row(row) for row in rows]


def update_crawl_schedule_status(
    schedule_id: str,
    *,
    status: str,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    selected = str(status or "").strip().lower()
    if selected not in {"active", "paused"}:
        raise ValueError("schedule status must be active or paused")
    with connect(path) as connection:
        before = connection.total_changes
        connection.execute(
            """
            UPDATE crawl_schedules
            SET status = ?, updated_at = ?
            WHERE schedule_id = ?
            """,
            (selected, _now(), schedule_id),
        )
        if connection.total_changes == before:
            return None
    return get_crawl_schedule(schedule_id, path=path)


def delete_crawl_schedule(schedule_id: str, *, path: str | Path | None = None) -> bool:
    with connect(path) as connection:
        before = connection.total_changes
        connection.execute("DELETE FROM crawl_schedules WHERE schedule_id = ?", (schedule_id,))
        return connection.total_changes > before


def create_or_update_crawl_schedule(
    *,
    discipline_key: str,
    source_keys: Iterable[str],
    limit_per_source: int,
    interval_minutes: int,
    lookback_days: int,
    run_now: bool = False,
    path: str | Path | None = None,
) -> dict[str, Any]:
    source_json = _source_keys_json(source_keys)
    now_dt = _now_dt()
    next_run_at = now_dt if run_now else now_dt + timedelta(minutes=int(interval_minutes))
    now = now_dt.isoformat()
    with connect(path) as connection:
        existing = connection.execute(
            """
            SELECT schedule_id FROM crawl_schedules
            WHERE discipline_key = ?
              AND source_keys_json = ?
              AND limit_per_source = ?
              AND lookback_days = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (discipline_key, source_json, int(limit_per_source), int(lookback_days)),
        ).fetchone()
        if existing:
            schedule_id = existing["schedule_id"]
            connection.execute(
                """
                UPDATE crawl_schedules
                SET status = 'active',
                    interval_minutes = ?,
                    next_run_at = ?,
                    updated_at = ?,
                    error = NULL
                WHERE schedule_id = ?
                """,
                (int(interval_minutes), next_run_at.isoformat(), now, schedule_id),
            )
        else:
            schedule_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO crawl_schedules (
                  schedule_id, status, discipline_key, source_keys_json, limit_per_source,
                  interval_minutes, lookback_days, next_run_at, created_at, updated_at,
                  warnings_json
                ) VALUES (?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, '[]')
                """,
                (
                    schedule_id,
                    discipline_key,
                    source_json,
                    int(limit_per_source),
                    int(interval_minutes),
                    int(lookback_days),
                    next_run_at.isoformat(),
                    now,
                    now,
                ),
            )
    return get_crawl_schedule(schedule_id, path=path) or {}


def due_crawl_schedules(
    *,
    now: datetime | None = None,
    limit: int = 10,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    due_at = (now or _now_dt()).astimezone(timezone.utc).isoformat()
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM crawl_schedules
            WHERE status = 'active' AND next_run_at <= ?
            ORDER BY next_run_at ASC
            LIMIT ?
            """,
            (due_at, int(limit)),
        ).fetchall()
    return [_schedule_from_row(row) for row in rows]


def mark_crawl_schedule_started(
    schedule_id: str,
    *,
    run_id: str,
    next_run_at: datetime,
    path: str | Path | None = None,
) -> None:
    now = _now()
    with connect(path) as connection:
        connection.execute(
            """
            UPDATE crawl_schedules
            SET last_run_id = ?,
                last_started_at = ?,
                next_run_at = ?,
                updated_at = ?,
                error = NULL
            WHERE schedule_id = ?
            """,
            (run_id, now, next_run_at.astimezone(timezone.utc).replace(microsecond=0).isoformat(), now, schedule_id),
        )


def mark_crawl_schedule_finished(
    schedule_id: str,
    *,
    warnings: list[str] | None = None,
    error: str | None = None,
    path: str | Path | None = None,
) -> None:
    now = _now()
    with connect(path) as connection:
        connection.execute(
            """
            UPDATE crawl_schedules
            SET last_finished_at = ?,
                updated_at = ?,
                warnings_json = ?,
                error = ?
            WHERE schedule_id = ?
            """,
            (now, now, _json_dumps(warnings or []), error, schedule_id),
        )
