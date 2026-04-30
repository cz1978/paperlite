from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from paperlite.config import runtime_config

SCHEMA_VERSION = 9
_CONNECT_INIT_LOCK = threading.Lock()

EXPECTED_SCHEMA_COLUMNS: dict[str, tuple[str, ...]] = {
    "schema_meta": (
        "key TEXT",
        "value TEXT NOT NULL DEFAULT ''",
    ),
    "crawl_runs": (
        "run_id TEXT",
        "status TEXT NOT NULL DEFAULT 'queued'",
        "date_from TEXT NOT NULL DEFAULT ''",
        "date_to TEXT NOT NULL DEFAULT ''",
        "discipline_key TEXT NOT NULL DEFAULT ''",
        "source_keys_json TEXT NOT NULL DEFAULT '[]'",
        "limit_per_source INTEGER NOT NULL DEFAULT 0",
        "started_at TEXT NOT NULL DEFAULT ''",
        "finished_at TEXT",
        "total_items INTEGER NOT NULL DEFAULT 0",
        "warnings_json TEXT NOT NULL DEFAULT '[]'",
        "error TEXT",
        "request_key TEXT NOT NULL DEFAULT ''",
    ),
    "paper_items": (
        "paper_id TEXT",
        "source TEXT NOT NULL DEFAULT ''",
        "title TEXT NOT NULL DEFAULT ''",
        "published_at TEXT",
        "payload_json TEXT NOT NULL DEFAULT '{}'",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "daily_entries": (
        "entry_date TEXT NOT NULL DEFAULT ''",
        "discipline_key TEXT NOT NULL DEFAULT ''",
        "source_key TEXT NOT NULL DEFAULT ''",
        "paper_id TEXT NOT NULL DEFAULT ''",
        "run_id TEXT",
        "created_at TEXT NOT NULL DEFAULT ''",
    ),
    "crawl_source_results": (
        "run_id TEXT NOT NULL DEFAULT ''",
        "source_key TEXT NOT NULL DEFAULT ''",
        "endpoint_key TEXT NOT NULL DEFAULT ''",
        "endpoint_mode TEXT NOT NULL DEFAULT ''",
        "count INTEGER NOT NULL DEFAULT 0",
        "warnings_json TEXT NOT NULL DEFAULT '[]'",
        "error TEXT",
    ),
    "crawl_schedules": (
        "schedule_id TEXT",
        "status TEXT NOT NULL DEFAULT 'active'",
        "discipline_key TEXT NOT NULL DEFAULT ''",
        "source_keys_json TEXT NOT NULL DEFAULT '[]'",
        "limit_per_source INTEGER NOT NULL DEFAULT 0",
        "interval_minutes INTEGER NOT NULL DEFAULT 0",
        "lookback_days INTEGER NOT NULL DEFAULT 0",
        "next_run_at TEXT NOT NULL DEFAULT ''",
        "last_run_id TEXT",
        "last_started_at TEXT",
        "last_finished_at TEXT",
        "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
        "warnings_json TEXT NOT NULL DEFAULT '[]'",
        "error TEXT",
    ),
    "translation_cache": (
        "cache_key TEXT",
        "paper_id TEXT NOT NULL DEFAULT ''",
        "content_hash TEXT NOT NULL DEFAULT ''",
        "target_language TEXT NOT NULL DEFAULT ''",
        "style TEXT NOT NULL DEFAULT ''",
        "title_zh TEXT NOT NULL DEFAULT ''",
        "brief_json TEXT NOT NULL DEFAULT '{}'",
        "translation TEXT NOT NULL DEFAULT ''",
        "model TEXT",
        "payload_json TEXT NOT NULL DEFAULT '{}'",
        "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "paper_embeddings": (
        "paper_id TEXT",
        "content_hash TEXT NOT NULL DEFAULT ''",
        "embedding_model TEXT NOT NULL DEFAULT ''",
        "dimensions INTEGER NOT NULL DEFAULT 0",
        "embedding_json TEXT NOT NULL DEFAULT '[]'",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "library_items": (
        "library_key TEXT",
        "paper_id TEXT NOT NULL DEFAULT ''",
        "payload_json TEXT NOT NULL DEFAULT '{}'",
        "read_at TEXT",
        "favorite_at TEXT",
        "hidden_at TEXT",
        "first_action_at TEXT NOT NULL DEFAULT ''",
        "last_action_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "library_events": (
        "event_id TEXT",
        "library_key TEXT NOT NULL DEFAULT ''",
        "action TEXT NOT NULL DEFAULT ''",
        "payload_json TEXT NOT NULL DEFAULT '{}'",
        "created_at TEXT NOT NULL DEFAULT ''",
    ),
    "saved_views": (
        "view_id TEXT",
        "name TEXT NOT NULL DEFAULT ''",
        "filters_json TEXT NOT NULL DEFAULT '{}'",
        "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "preference_prompts": (
        "prompt_id TEXT",
        "text TEXT NOT NULL DEFAULT ''",
        "enabled INTEGER NOT NULL DEFAULT 1",
        "weight INTEGER NOT NULL DEFAULT 1",
        "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "preference_query_history": (
        "query_id TEXT",
        "text TEXT NOT NULL DEFAULT ''",
        "source TEXT NOT NULL DEFAULT ''",
        "use_count INTEGER NOT NULL DEFAULT 1",
        "created_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "preference_settings": (
        "key TEXT",
        "value_json TEXT NOT NULL DEFAULT '{}'",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
    "preference_profile": (
        "profile_id TEXT",
        "profile_json TEXT NOT NULL DEFAULT '{}'",
        "signal_counts_json TEXT NOT NULL DEFAULT '{}'",
        "generated_at TEXT NOT NULL DEFAULT ''",
        "updated_at TEXT NOT NULL DEFAULT ''",
    ),
}


def default_db_path() -> Path:
    return runtime_config().db_path


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _table_count(connection: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return None


def _column_name(definition: str) -> str:
    return definition.split(maxsplit=1)[0].strip('"')


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}


def _apply_schema_migrations(connection: sqlite3.Connection) -> None:
    for table, definitions in EXPECTED_SCHEMA_COLUMNS.items():
        existing = _table_columns(connection, table)
        for definition in definitions:
            name = _column_name(definition)
            if name not in existing:
                connection.execute(f'ALTER TABLE "{table}" ADD COLUMN {definition}')
                existing.add(name)


@contextmanager
def connect(path: str | Path | None = None):
    db_path = Path(path) if path else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        with _CONNECT_INIT_LOCK:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA journal_mode = WAL")
            init_db(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crawl_runs (
          run_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          date_from TEXT NOT NULL,
          date_to TEXT NOT NULL,
          discipline_key TEXT NOT NULL,
          source_keys_json TEXT NOT NULL,
          limit_per_source INTEGER NOT NULL,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          total_items INTEGER NOT NULL DEFAULT 0,
          warnings_json TEXT NOT NULL DEFAULT '[]',
          error TEXT,
          request_key TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS paper_items (
          paper_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          title TEXT NOT NULL,
          published_at TEXT,
          payload_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_entries (
          entry_date TEXT NOT NULL,
          discipline_key TEXT NOT NULL,
          source_key TEXT NOT NULL,
          paper_id TEXT NOT NULL,
          run_id TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY (entry_date, discipline_key, source_key, paper_id),
          FOREIGN KEY (paper_id) REFERENCES paper_items(paper_id)
        );

        CREATE TABLE IF NOT EXISTS crawl_source_results (
          run_id TEXT NOT NULL,
          source_key TEXT NOT NULL,
          endpoint_key TEXT NOT NULL,
          endpoint_mode TEXT NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          warnings_json TEXT NOT NULL DEFAULT '[]',
          error TEXT,
          PRIMARY KEY (run_id, source_key, endpoint_key)
        );

        CREATE TABLE IF NOT EXISTS crawl_schedules (
          schedule_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          discipline_key TEXT NOT NULL,
          source_keys_json TEXT NOT NULL,
          limit_per_source INTEGER NOT NULL,
          interval_minutes INTEGER NOT NULL,
          lookback_days INTEGER NOT NULL DEFAULT 0,
          next_run_at TEXT NOT NULL,
          last_run_id TEXT,
          last_started_at TEXT,
          last_finished_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          warnings_json TEXT NOT NULL DEFAULT '[]',
          error TEXT
        );

        CREATE TABLE IF NOT EXISTS translation_cache (
          cache_key TEXT PRIMARY KEY,
          paper_id TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          target_language TEXT NOT NULL,
          style TEXT NOT NULL,
          title_zh TEXT NOT NULL DEFAULT '',
          brief_json TEXT NOT NULL DEFAULT '{}',
          translation TEXT NOT NULL DEFAULT '',
          model TEXT,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS paper_embeddings (
          paper_id TEXT PRIMARY KEY,
          content_hash TEXT NOT NULL,
          embedding_model TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          embedding_json TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (paper_id) REFERENCES paper_items(paper_id)
        );

        CREATE TABLE IF NOT EXISTS library_items (
          library_key TEXT PRIMARY KEY,
          paper_id TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          read_at TEXT,
          favorite_at TEXT,
          hidden_at TEXT,
          first_action_at TEXT NOT NULL,
          last_action_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS library_events (
          event_id TEXT PRIMARY KEY,
          library_key TEXT NOT NULL,
          action TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          FOREIGN KEY (library_key) REFERENCES library_items(library_key) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS saved_views (
          view_id TEXT PRIMARY KEY,
          name TEXT NOT NULL UNIQUE,
          filters_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preference_prompts (
          prompt_id TEXT PRIMARY KEY,
          text TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          weight INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preference_query_history (
          query_id TEXT PRIMARY KEY,
          text TEXT NOT NULL,
          source TEXT NOT NULL,
          use_count INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(text, source)
        );

        CREATE TABLE IF NOT EXISTS preference_settings (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preference_profile (
          profile_id TEXT PRIMARY KEY,
          profile_json TEXT NOT NULL,
          signal_counts_json TEXT NOT NULL,
          generated_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    _apply_schema_migrations(connection)
    _migrate_crawl_run_request_keys(connection)
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_entries_lookup
          ON daily_entries (entry_date, discipline_key, source_key);
        CREATE INDEX IF NOT EXISTS idx_paper_items_published
          ON paper_items (published_at);
        CREATE INDEX IF NOT EXISTS idx_crawl_runs_lookup
          ON crawl_runs (date_from, date_to, discipline_key, limit_per_source, started_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_crawl_runs_active_request_key
          ON crawl_runs (request_key)
          WHERE status IN ('queued', 'running');
        CREATE INDEX IF NOT EXISTS idx_crawl_schedules_due
          ON crawl_schedules (status, next_run_at);
        CREATE INDEX IF NOT EXISTS idx_translation_cache_paper
          ON translation_cache (paper_id, target_language, style);
        CREATE INDEX IF NOT EXISTS idx_paper_embeddings_model
          ON paper_embeddings (embedding_model, updated_at);
        CREATE INDEX IF NOT EXISTS idx_library_items_last_action
          ON library_items (last_action_at);
        CREATE INDEX IF NOT EXISTS idx_library_items_read
          ON library_items (read_at);
        CREATE INDEX IF NOT EXISTS idx_library_items_favorite
          ON library_items (favorite_at);
        CREATE INDEX IF NOT EXISTS idx_library_items_hidden
          ON library_items (hidden_at);
        CREATE INDEX IF NOT EXISTS idx_library_events_lookup
          ON library_events (library_key, created_at);
        CREATE INDEX IF NOT EXISTS idx_saved_views_updated
          ON saved_views (updated_at);
        CREATE INDEX IF NOT EXISTS idx_preference_prompts_enabled
          ON preference_prompts (enabled, updated_at);
        CREATE INDEX IF NOT EXISTS idx_preference_query_history_updated
          ON preference_query_history (updated_at);
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )

def split_source_keys(source_keys: str | Iterable[str] | None) -> list[str]:
    if source_keys is None:
        return []
    raw = source_keys.split(",") if isinstance(source_keys, str) else list(source_keys)
    return [str(item).strip() for item in raw if str(item).strip()]


def _normalized_source_list(source_keys: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(str(item).strip() for item in source_keys if str(item).strip()))


def _source_keys_json(source_keys: Iterable[str]) -> str:
    return _json_dumps(_normalized_source_list(source_keys))


def _crawl_request_key(
    *,
    date_from: str,
    date_to: str,
    discipline_key: str,
    source_keys_json: str,
    limit_per_source: int,
) -> str:
    return _json_dumps(
        {
            "date_from": str(date_from or ""),
            "date_to": str(date_to or ""),
            "discipline_key": str(discipline_key or ""),
            "source_keys": _json_loads(source_keys_json, []),
            "limit_per_source": int(limit_per_source),
        }
    )


def _crawl_request_key_for_sources(
    *,
    date_from: str,
    date_to: str,
    discipline_key: str,
    source_keys: Iterable[str],
    limit_per_source: int,
) -> str:
    return _crawl_request_key(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline_key,
        source_keys_json=_source_keys_json(source_keys),
        limit_per_source=limit_per_source,
    )


def _migrate_crawl_run_request_keys(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "crawl_runs")
    if "request_key" not in columns:
        return
    rows = connection.execute(
        """
        SELECT rowid, date_from, date_to, discipline_key, source_keys_json, limit_per_source
        FROM crawl_runs
        WHERE request_key IS NULL OR request_key = ''
        """
    ).fetchall()
    for row in rows:
        connection.execute(
            "UPDATE crawl_runs SET request_key = ? WHERE rowid = ?",
            (
                _crawl_request_key(
                    date_from=row["date_from"],
                    date_to=row["date_to"],
                    discipline_key=row["discipline_key"],
                    source_keys_json=row["source_keys_json"],
                    limit_per_source=row["limit_per_source"],
                ),
                row["rowid"],
            ),
        )
    duplicates = connection.execute(
        """
        SELECT rowid
        FROM (
          SELECT rowid,
                 ROW_NUMBER() OVER (
                   PARTITION BY request_key
                   ORDER BY started_at DESC, rowid DESC
                 ) AS rank
          FROM crawl_runs
          WHERE status IN ('queued', 'running')
        )
        WHERE rank > 1
        """
    ).fetchall()
    if duplicates:
        now = _now()
        connection.executemany(
            """
            UPDATE crawl_runs
            SET status = 'failed',
                finished_at = COALESCE(finished_at, ?),
                error = COALESCE(error, 'superseded duplicate active crawl run')
            WHERE rowid = ?
            """,
            [(now, row["rowid"]) for row in duplicates],
        )

__all__ = [name for name in globals() if not name.startswith("__")]
