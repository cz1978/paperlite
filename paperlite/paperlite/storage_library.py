from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

from paperlite.dedupe import dedupe_key
from paperlite.metadata_cleaning import sanitize_paper
from paperlite.models import Paper
from paperlite.storage_preference_core import (
    LIBRARY_ACTIONS,
    LIBRARY_ITEM_FILTERS,
    MODEL_ASSISTED_ACTIONS,
    UNDO_PREFERENCE_ACTIONS,
    _preference_settings_connection,
    _rebuild_preference_profile_connection,
)
from paperlite.storage_schema import _json_dumps, _json_loads, _now, connect

def library_key_for_paper(paper: Paper) -> str:
    return dedupe_key(sanitize_paper(paper))


def _paper_payload_key(paper: Paper) -> tuple[Paper, dict[str, Any], str]:
    cleaned = sanitize_paper(paper)
    return cleaned, cleaned.to_dict(), dedupe_key(cleaned)


def _library_state_from_row(
    row: sqlite3.Row | None,
    *,
    library_key: str,
    paper_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if row is None:
        return {
            "library_key": library_key,
            "paper_id": paper_id,
            "paper": payload or {},
            "read": False,
            "favorite": False,
            "hidden": False,
            "read_at": None,
            "favorite_at": None,
            "hidden_at": None,
            "first_action_at": None,
            "last_action_at": None,
        }
    stored_payload = _json_loads(row["payload_json"], {})
    return {
        "library_key": row["library_key"],
        "paper_id": row["paper_id"],
        "paper": stored_payload if isinstance(stored_payload, dict) else {},
        "read": bool(row["read_at"]),
        "favorite": bool(row["favorite_at"]),
        "hidden": bool(row["hidden_at"]),
        "read_at": row["read_at"],
        "favorite_at": row["favorite_at"],
        "hidden_at": row["hidden_at"],
        "first_action_at": row["first_action_at"],
        "last_action_at": row["last_action_at"],
    }


def get_library_state(papers: Iterable[Paper], *, path: str | Path | None = None) -> dict[str, Any]:
    keyed: list[tuple[str, Paper, dict[str, Any]]] = []
    for paper in papers:
        cleaned, payload, key = _paper_payload_key(paper)
        keyed.append((key, cleaned, payload))
    if not keyed:
        return {"items": [], "by_key": {}}

    keys = sorted({key for key, _paper, _payload in keyed})
    placeholders = ",".join("?" for _ in keys)
    with connect(path) as connection:
        rows = connection.execute(
            f"SELECT * FROM library_items WHERE library_key IN ({placeholders})",
            keys,
        ).fetchall()
    rows_by_key = {row["library_key"]: row for row in rows}
    items = [
        _library_state_from_row(
            rows_by_key.get(key),
            library_key=key,
            paper_id=paper.id,
            payload=payload,
        )
        for key, paper, payload in keyed
    ]
    return {"items": items, "by_key": {item["library_key"]: item for item in items}}


def apply_library_action(
    *,
    action: str,
    papers: Iterable[Paper],
    event_payload: dict[str, Any] | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    selected = str(action or "").strip().lower()
    if selected not in LIBRARY_ACTIONS:
        raise ValueError(f"library action must be one of {', '.join(sorted(LIBRARY_ACTIONS))}")
    prepared = [_paper_payload_key(paper) for paper in papers]
    if not prepared:
        raise ValueError("items must contain at least one paper")

    updated: list[dict[str, Any]] = []
    now = _now()
    with connect(path) as connection:
        settings = _preference_settings_connection(connection)
        learning_enabled = bool(settings.get("learning_enabled", True))
        model_signal_enabled = bool(settings.get("model_signal_learning_enabled", True))
        if selected in MODEL_ASSISTED_ACTIONS and (not learning_enabled or not model_signal_enabled):
            return {"action": selected, "updated": [], "by_key": {}, "skipped": True, "skip_reason": "preference_learning_disabled"}
        for paper, payload, key in prepared:
            row = connection.execute("SELECT * FROM library_items WHERE library_key = ?", (key,)).fetchone()
            read_at = row["read_at"] if row else None
            favorite_at = row["favorite_at"] if row else None
            hidden_at = row["hidden_at"] if row else None
            first_action_at = row["first_action_at"] if row else now

            if selected == "read":
                read_at = now
            elif selected == "unread":
                read_at = None
            elif selected == "favorite":
                favorite_at = now
            elif selected == "unfavorite":
                favorite_at = None
            elif selected == "hide":
                hidden_at = now
            elif selected == "unhide":
                hidden_at = None

            connection.execute(
                """
                INSERT INTO library_items (
                  library_key, paper_id, payload_json, read_at, favorite_at, hidden_at,
                  first_action_at, last_action_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_key) DO UPDATE SET
                  paper_id = excluded.paper_id,
                  payload_json = excluded.payload_json,
                  read_at = excluded.read_at,
                  favorite_at = excluded.favorite_at,
                  hidden_at = excluded.hidden_at,
                  first_action_at = library_items.first_action_at,
                  last_action_at = excluded.last_action_at,
                  updated_at = excluded.updated_at
                """,
                (
                    key,
                    paper.id,
                    _json_dumps(payload),
                    read_at,
                    favorite_at,
                    hidden_at,
                    first_action_at,
                    now,
                    now,
                ),
            )
            if learning_enabled:
                undo_target = UNDO_PREFERENCE_ACTIONS.get(selected)
                if undo_target:
                    connection.execute(
                        """
                        DELETE FROM library_events
                        WHERE library_key = ? AND action = ?
                        """,
                        (key, undo_target),
                    )
                else:
                    event = {"paper_id": paper.id, **(event_payload or {})}
                    connection.execute(
                        """
                        INSERT INTO library_events (event_id, library_key, action, payload_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex, key, selected, _json_dumps(event), now),
                    )
            updated_row = connection.execute("SELECT * FROM library_items WHERE library_key = ?", (key,)).fetchone()
            updated.append(_library_state_from_row(updated_row, library_key=key, paper_id=paper.id, payload=payload))
        if learning_enabled:
            _rebuild_preference_profile_connection(connection)
    return {"action": selected, "updated": updated, "by_key": {item["library_key"]: item for item in updated}}


def list_library_items(
    *,
    state: str = "all",
    limit: int = 100,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    selected = str(state or "all").strip().lower()
    if selected not in LIBRARY_ITEM_FILTERS:
        raise ValueError(f"library state must be one of {', '.join(sorted(LIBRARY_ITEM_FILTERS))}")
    where = ""
    if selected == "favorite":
        where = "WHERE favorite_at IS NOT NULL"
    elif selected == "read":
        where = "WHERE read_at IS NOT NULL"
    elif selected == "hidden":
        where = "WHERE hidden_at IS NOT NULL"
    max_rows = max(1, min(int(limit), 500))
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM library_items
            {where}
            ORDER BY last_action_at DESC, paper_id ASC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
    return [
        _library_state_from_row(row, library_key=row["library_key"], paper_id=row["paper_id"])
        for row in rows
    ]


def list_library_events(
    *,
    library_key: str | None = None,
    limit: int = 100,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if library_key:
        clauses.append("library_key = ?")
        params.append(library_key)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    max_rows = max(1, min(int(limit), 500))
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM library_events
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*params, max_rows),
        ).fetchall()
    return [
        {
            "event_id": row["event_id"],
            "library_key": row["library_key"],
            "action": row["action"],
            "payload": _json_loads(row["payload_json"], {}),
            "created_at": row["created_at"],
        }
        for row in rows
    ]

__all__ = [name for name in globals() if not name.startswith("__")]
