from __future__ import annotations

from pathlib import Path
from typing import Any

from paperlite.storage_schema import _json_dumps, _json_loads, _now, connect

def get_translation_cache(cache_key: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM translation_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    payload = _json_loads(row["payload_json"], None)
    if not isinstance(payload, dict):
        return None
    payload["cached"] = True
    return payload


def upsert_translation_cache(
    *,
    cache_key: str,
    paper_id: str,
    content_hash: str,
    target_language: str,
    style: str,
    payload: dict[str, Any],
    path: str | Path | None = None,
) -> None:
    now = _now()
    brief = payload.get("brief") if isinstance(payload.get("brief"), dict) else {}
    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO translation_cache (
              cache_key, paper_id, content_hash, target_language, style,
              title_zh, brief_json, translation, model, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
              paper_id = excluded.paper_id,
              content_hash = excluded.content_hash,
              target_language = excluded.target_language,
              style = excluded.style,
              title_zh = excluded.title_zh,
              brief_json = excluded.brief_json,
              translation = excluded.translation,
              model = excluded.model,
              payload_json = excluded.payload_json,
              updated_at = excluded.updated_at
            """,
            (
                cache_key,
                paper_id,
                content_hash,
                target_language,
                style,
                str(payload.get("title_zh") or ""),
                _json_dumps(brief),
                str(payload.get("translation") or ""),
                payload.get("model"),
                _json_dumps({**payload, "cached": False}),
                now,
                now,
            ),
        )
