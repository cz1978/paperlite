from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from paperlite.storage_schema import _json_dumps, _json_loads, _now, connect, split_source_keys

MISSION_STATUSES = {"active", "paused"}


def _clean_text(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _clean_terms(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    raw = value.split(",") if isinstance(value, str) else list(value)
    return list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))


def _bounded_limit(value: int | str | None, *, default: int = 15) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(500, parsed))


def _mission_from_row(row: sqlite3.Row) -> dict[str, Any]:
    sources = split_source_keys(_json_loads(row["source_keys_json"], []))
    return {
        "mission_id": row["mission_id"],
        "name": row["name"],
        "topic": row["topic"],
        "discipline": row["discipline_key"] or None,
        "discipline_key": row["discipline_key"] or None,
        "source": sources,
        "source_keys": sources,
        "q": row["q"] or None,
        "include_terms": _clean_terms(_json_loads(row["include_terms_json"], [])),
        "exclude_terms": _clean_terms(_json_loads(row["exclude_terms_json"], [])),
        "prefer_terms": _clean_terms(_json_loads(row["prefer_terms_json"], [])),
        "instructions": row["instructions"] or "",
        "crawl_if_missing": bool(row["crawl_if_missing"]),
        "limit_per_source": int(row["limit_per_source"] or 15),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _mission_run_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "mission_id": row["mission_id"],
        "status": row["status"],
        "date_from": row["date_from"],
        "date_to": row["date_to"],
        "scope": _json_loads(row["scope_json"], {}),
        "crawl_run_id": row["crawl_run_id"],
        "counts": _json_loads(row["counts_json"], {}),
        "radar": _json_loads(row["radar_json"], {}),
        "warnings": _json_loads(row["warnings_json"], []),
        "error": row["error"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def get_research_mission(identifier: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    selected = _clean_text(identifier, limit=200)
    if not selected:
        return None
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT * FROM research_missions
            WHERE mission_id = ? OR name = ?
            """,
            (selected, selected),
        ).fetchone()
    return _mission_from_row(row) if row else None


def list_research_missions(
    *,
    status: str | None = "active",
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clean_status = _clean_text(status, limit=40) if status is not None else None
    conditions: list[str] = []
    params: list[Any] = []
    if clean_status:
        conditions.append("status = ?")
        params.append(clean_status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM research_missions
            {where}
            ORDER BY updated_at DESC, name ASC
            """,
            params,
        ).fetchall()
    return [_mission_from_row(row) for row in rows]


def save_research_mission(
    *,
    mission_id: str | None = None,
    name: str | None = None,
    topic: str | None = None,
    discipline: str | None = None,
    source_keys: str | Iterable[str] | None = None,
    q: str | None = None,
    include_terms: str | Iterable[str] | None = None,
    exclude_terms: str | Iterable[str] | None = None,
    prefer_terms: str | Iterable[str] | None = None,
    instructions: str | None = None,
    crawl_if_missing: bool | None = None,
    limit_per_source: int | str | None = None,
    status: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    clean_id = _clean_text(mission_id, limit=80)
    clean_name = _clean_text(name, limit=160)
    now = _now()
    with connect(path) as connection:
        existing = None
        if clean_id:
            existing = connection.execute("SELECT * FROM research_missions WHERE mission_id = ?", (clean_id,)).fetchone()
        if existing is None and clean_name:
            existing = connection.execute("SELECT * FROM research_missions WHERE name = ?", (clean_name,)).fetchone()

        previous = _mission_from_row(existing) if existing else {}
        selected_id = clean_id or str(previous.get("mission_id") or uuid.uuid4().hex)
        selected_name = clean_name or str(previous.get("name") or "").strip()
        if not selected_name:
            raise ValueError("research mission name is required")
        selected_topic = _clean_text(topic if topic is not None else previous.get("topic") or selected_name, limit=500)
        if not selected_topic:
            raise ValueError("research mission topic is required")
        selected_status = _clean_text(status if status is not None else previous.get("status") or "active", limit=40)
        if selected_status not in MISSION_STATUSES:
            raise ValueError("research mission status must be active or paused")
        created_at = str(previous.get("created_at") or now)

        sources = split_source_keys(source_keys) if source_keys is not None else list(previous.get("source_keys") or [])
        selected_crawl = bool(crawl_if_missing) if crawl_if_missing is not None else bool(previous.get("crawl_if_missing", True))
        selected_limit = _bounded_limit(
            limit_per_source,
            default=int(previous.get("limit_per_source") or 15),
        )

        try:
            connection.execute(
                """
                INSERT INTO research_missions (
                  mission_id, name, topic, discipline_key, source_keys_json, q,
                  include_terms_json, exclude_terms_json, prefer_terms_json, instructions,
                  crawl_if_missing, limit_per_source, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                  name = excluded.name,
                  topic = excluded.topic,
                  discipline_key = excluded.discipline_key,
                  source_keys_json = excluded.source_keys_json,
                  q = excluded.q,
                  include_terms_json = excluded.include_terms_json,
                  exclude_terms_json = excluded.exclude_terms_json,
                  prefer_terms_json = excluded.prefer_terms_json,
                  instructions = excluded.instructions,
                  crawl_if_missing = excluded.crawl_if_missing,
                  limit_per_source = excluded.limit_per_source,
                  status = excluded.status,
                  updated_at = excluded.updated_at
                """,
                (
                    selected_id,
                    selected_name,
                    selected_topic,
                    _clean_text(discipline if discipline is not None else previous.get("discipline_key"), limit=120),
                    _json_dumps(sources),
                    _clean_text(q if q is not None else previous.get("q"), limit=500),
                    _json_dumps(_clean_terms(include_terms if include_terms is not None else previous.get("include_terms"))),
                    _json_dumps(_clean_terms(exclude_terms if exclude_terms is not None else previous.get("exclude_terms"))),
                    _json_dumps(_clean_terms(prefer_terms if prefer_terms is not None else previous.get("prefer_terms"))),
                    _clean_text(instructions if instructions is not None else previous.get("instructions")),
                    1 if selected_crawl else 0,
                    selected_limit,
                    selected_status,
                    created_at,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("research mission name already exists") from exc
        row = connection.execute("SELECT * FROM research_missions WHERE mission_id = ?", (selected_id,)).fetchone()
    return _mission_from_row(row)


def delete_research_mission(identifier: str, *, path: str | Path | None = None) -> bool:
    mission = get_research_mission(identifier, path=path)
    if not mission:
        return False
    with connect(path) as connection:
        cursor = connection.execute("DELETE FROM research_missions WHERE mission_id = ?", (mission["mission_id"],))
    return cursor.rowcount > 0


def list_research_mission_runs(
    mission_id: str,
    *,
    limit: int = 20,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    selected_id = _clean_text(mission_id, limit=80)
    if not selected_id:
        return []
    selected_limit = _bounded_limit(limit, default=20)
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM research_mission_runs
            WHERE mission_id = ?
            ORDER BY started_at DESC, run_id DESC
            LIMIT ?
            """,
            (selected_id, selected_limit),
        ).fetchall()
    return [_mission_run_from_row(row) for row in rows]


def record_research_mission_run(
    *,
    mission_id: str,
    status: str,
    date_from: str,
    date_to: str,
    scope: dict[str, Any],
    crawl_run_id: str | None = None,
    counts: dict[str, Any] | None = None,
    radar: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    selected_id = _clean_text(mission_id, limit=80)
    if not selected_id:
        raise ValueError("research mission id is required")
    run_id = uuid.uuid4().hex
    started = started_at or _now()
    finished = finished_at or _now()
    with connect(path) as connection:
        if connection.execute("SELECT 1 FROM research_missions WHERE mission_id = ?", (selected_id,)).fetchone() is None:
            raise ValueError("research mission not found")
        connection.execute(
            """
            INSERT INTO research_mission_runs (
              run_id, mission_id, status, date_from, date_to, scope_json, crawl_run_id,
              counts_json, radar_json, warnings_json, error, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                selected_id,
                _clean_text(status, limit=40) or "ok",
                _clean_text(date_from, limit=40),
                _clean_text(date_to, limit=40),
                _json_dumps(scope or {}),
                _clean_text(crawl_run_id, limit=80) or None,
                _json_dumps(counts or {}),
                _json_dumps(radar or {}),
                _json_dumps(warnings or []),
                _clean_text(error) or None,
                started,
                finished,
            ),
        )
        row = connection.execute("SELECT * FROM research_mission_runs WHERE run_id = ?", (run_id,)).fetchone()
    return _mission_run_from_row(row)


def research_mission_seen_paper_ids(
    mission_id: str,
    paper_ids: Iterable[str],
    *,
    path: str | Path | None = None,
) -> set[str]:
    selected_id = _clean_text(mission_id, limit=80)
    selected_papers = [_clean_text(paper_id, limit=500) for paper_id in paper_ids]
    selected_papers = [paper_id for paper_id in selected_papers if paper_id]
    if not selected_id or not selected_papers:
        return set()
    placeholders = ",".join("?" for _ in selected_papers)
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT paper_id FROM research_mission_seen
            WHERE mission_id = ? AND paper_id IN ({placeholders})
            """,
            [selected_id, *selected_papers],
        ).fetchall()
    return {str(row["paper_id"]) for row in rows}


def mark_research_mission_seen(
    *,
    mission_id: str,
    run_id: str,
    paper_ids: Iterable[str],
    path: str | Path | None = None,
) -> int:
    selected_id = _clean_text(mission_id, limit=80)
    selected_run = _clean_text(run_id, limit=80)
    selected_papers = list(dict.fromkeys(_clean_text(paper_id, limit=500) for paper_id in paper_ids))
    selected_papers = [paper_id for paper_id in selected_papers if paper_id]
    if not selected_id or not selected_run or not selected_papers:
        return 0
    now = _now()
    with connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO research_mission_seen (
              mission_id, paper_id, first_seen_run_id, first_seen_at,
              last_seen_run_id, last_seen_at, seen_count
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(mission_id, paper_id) DO UPDATE SET
              last_seen_run_id = excluded.last_seen_run_id,
              last_seen_at = excluded.last_seen_at,
              seen_count = research_mission_seen.seen_count + 1
            """,
            [(selected_id, paper_id, selected_run, now, selected_run, now) for paper_id in selected_papers],
        )
    return len(selected_papers)


__all__ = [name for name in globals() if not name.startswith("__")]
