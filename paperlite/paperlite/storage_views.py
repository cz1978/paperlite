from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from paperlite.storage_schema import _json_dumps, _json_loads, _now, connect

def _saved_view_from_row(row: sqlite3.Row) -> dict[str, Any]:
    filters = _json_loads(row["filters_json"], {})
    return {
        "view_id": row["view_id"],
        "name": row["name"],
        "filters": filters if isinstance(filters, dict) else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_saved_views(*, path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM saved_views
            ORDER BY updated_at DESC, name ASC
            """
        ).fetchall()
    return [_saved_view_from_row(row) for row in rows]


def save_view(
    *,
    name: str,
    filters: dict[str, Any],
    path: str | Path | None = None,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("view name is required")
    if not isinstance(filters, dict):
        raise ValueError("filters must be an object")
    now = _now()
    with connect(path) as connection:
        row = connection.execute("SELECT view_id, created_at FROM saved_views WHERE name = ?", (clean_name,)).fetchone()
        view_id = row["view_id"] if row else uuid.uuid4().hex
        created_at = row["created_at"] if row else now
        connection.execute(
            """
            INSERT INTO saved_views (view_id, name, filters_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              filters_json = excluded.filters_json,
              updated_at = excluded.updated_at
            """,
            (view_id, clean_name, _json_dumps(filters), created_at, now),
        )
        saved = connection.execute("SELECT * FROM saved_views WHERE name = ?", (clean_name,)).fetchone()
    return _saved_view_from_row(saved)


def delete_saved_view(
    *,
    view_id: str | None = None,
    name: str | None = None,
    path: str | Path | None = None,
) -> bool:
    selected_id = str(view_id or "").strip()
    selected_name = str(name or "").strip()
    if not selected_id and not selected_name:
        raise ValueError("view_id or name is required")
    with connect(path) as connection:
        before = connection.total_changes
        if selected_id:
            connection.execute("DELETE FROM saved_views WHERE view_id = ?", (selected_id,))
        else:
            connection.execute("DELETE FROM saved_views WHERE name = ?", (selected_name,))
        return connection.total_changes > before
