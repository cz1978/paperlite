from __future__ import annotations

import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from paperlite.models import Paper
from paperlite.storage_preference_core import (
    MODEL_ASSISTED_ACTIONS,
    PREFERENCE_ACTION_WEIGHTS,
    PREFERENCE_EVENT_LIMIT,
    PREFERENCE_PROFILE_ID,
    _bounded_prompt_weight,
    _clean_preference_text,
    _event_noise_tags,
    _event_number,
    _preference_prompt_from_row,
    _preference_profile_from_row,
    _preference_query_from_row,
    _preference_settings_connection,
    _preference_signal_actions,
    _profile_payload_tokens,
    _profile_summary,
    _profile_tokens,
    _rebuild_preference_profile_connection,
    _relevance_tokens,
    _save_preference_settings_connection,
    _purify_preference_signals_connection,
    _token_overlap_score,
    _topic_payload_tokens,
    _training_correction_context,
    _training_label,
    _training_paper_payload,
    _training_signal_quality,
    _weighted_terms,
)
from paperlite.storage_schema import _json_loads, _now, connect

def list_preference_prompts(
    *,
    enabled: bool | None = None,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if enabled is not None:
        clauses.append("enabled = ?")
        params.append(1 if enabled else 0)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM preference_prompts
            {where}
            ORDER BY updated_at DESC, created_at DESC
            """,
            params,
        ).fetchall()
    return [_preference_prompt_from_row(row) for row in rows]


def list_preference_queries(
    *,
    limit: int = 50,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    max_rows = max(1, min(int(limit), 200))
    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM preference_query_history
            ORDER BY updated_at DESC, use_count DESC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
    return [_preference_query_from_row(row) for row in rows]


def get_preference_settings(*, path: str | Path | None = None) -> dict[str, Any]:
    with connect(path) as connection:
        settings = _preference_settings_connection(connection)
    return {"settings": settings}


def update_preference_settings(
    *,
    updates: dict[str, Any],
    path: str | Path | None = None,
) -> dict[str, Any]:
    if not isinstance(updates, dict):
        raise ValueError("settings updates must be an object")
    with connect(path) as connection:
        settings = _save_preference_settings_connection(connection, updates)
        _rebuild_preference_profile_connection(connection)
    return {"settings": settings}


def purify_preference_signals(*, path: str | Path | None = None) -> dict[str, Any]:
    with connect(path) as connection:
        settings = _preference_settings_connection(connection)
        result = _purify_preference_signals_connection(connection, settings)
        profile = _rebuild_preference_profile_connection(connection)
    return {"purify": result, "profile": profile}


def clear_preference_learning_data(*, path: str | Path | None = None) -> dict[str, Any]:
    with connect(path) as connection:
        before = connection.total_changes
        connection.execute("DELETE FROM preference_query_history")
        removed_queries = connection.total_changes - before

        before = connection.total_changes
        connection.execute("DELETE FROM library_events")
        removed_events = connection.total_changes - before

        before = connection.total_changes
        connection.execute("DELETE FROM preference_profile")
        removed_profiles = connection.total_changes - before

        profile = _rebuild_preference_profile_connection(connection)
    return {
        "cleared": True,
        "removed_queries": removed_queries,
        "removed_events": removed_events,
        "removed_profiles": removed_profiles,
        "profile": profile,
    }


def record_preference_query(
    *,
    text: str,
    source: str = "agent_filter",
    path: str | Path | None = None,
) -> dict[str, Any]:
    clean_text = _clean_preference_text(text)
    if not clean_text:
        raise ValueError("preference query text is required")
    clean_source = str(source or "agent_filter").strip()[:80] or "agent_filter"
    now = _now()
    with connect(path) as connection:
        settings = _preference_settings_connection(connection)
        if not settings.get("learning_enabled", True) or not settings.get("query_history_enabled", True):
            return {
                "recorded": False,
                "text": clean_text,
                "source": clean_source,
                "use_count": 0,
                "skip_reason": "preference_learning_disabled",
            }
        connection.execute(
            """
            INSERT INTO preference_query_history (query_id, text, source, use_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(text, source) DO UPDATE SET
              use_count = preference_query_history.use_count + 1,
              updated_at = excluded.updated_at
            """,
            (uuid.uuid4().hex, clean_text, clean_source, 1, now, now),
        )
        _rebuild_preference_profile_connection(connection)
        row = connection.execute(
            "SELECT * FROM preference_query_history WHERE text = ? AND source = ?",
            (clean_text, clean_source),
        ).fetchone()
    return _preference_query_from_row(row)


def save_preference_prompt(
    *,
    text: str,
    enabled: bool = True,
    weight: int = 1,
    prompt_id: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    clean_text = _clean_preference_text(text)
    if not clean_text:
        raise ValueError("preference prompt text is required")
    selected_id = str(prompt_id or uuid.uuid4().hex).strip()
    if not selected_id:
        raise ValueError("preference prompt id is required")
    now = _now()
    with connect(path) as connection:
        row = connection.execute(
            "SELECT created_at FROM preference_prompts WHERE prompt_id = ?",
            (selected_id,),
        ).fetchone()
        created_at = row["created_at"] if row else now
        connection.execute(
            """
            INSERT INTO preference_prompts (prompt_id, text, enabled, weight, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(prompt_id) DO UPDATE SET
              text = excluded.text,
              enabled = excluded.enabled,
              weight = excluded.weight,
              updated_at = excluded.updated_at
            """,
            (selected_id, clean_text, 1 if enabled else 0, _bounded_prompt_weight(weight), created_at, now),
        )
        _rebuild_preference_profile_connection(connection)
        saved = connection.execute("SELECT * FROM preference_prompts WHERE prompt_id = ?", (selected_id,)).fetchone()
    return _preference_prompt_from_row(saved)


def update_preference_prompt(
    *,
    prompt_id: str,
    text: str | None = None,
    enabled: bool | None = None,
    weight: int | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    selected_id = str(prompt_id or "").strip()
    if not selected_id:
        raise ValueError("preference prompt id is required")
    with connect(path) as connection:
        row = connection.execute("SELECT * FROM preference_prompts WHERE prompt_id = ?", (selected_id,)).fetchone()
        if row is None:
            raise ValueError("preference prompt not found")
        next_text = row["text"] if text is None else _clean_preference_text(text)
        if not next_text:
            raise ValueError("preference prompt text is required")
        next_enabled = bool(row["enabled"]) if enabled is None else bool(enabled)
        next_weight = int(row["weight"]) if weight is None else _bounded_prompt_weight(weight)
        connection.execute(
            """
            UPDATE preference_prompts
            SET text = ?, enabled = ?, weight = ?, updated_at = ?
            WHERE prompt_id = ?
            """,
            (next_text, 1 if next_enabled else 0, next_weight, _now(), selected_id),
        )
        _rebuild_preference_profile_connection(connection)
        updated = connection.execute("SELECT * FROM preference_prompts WHERE prompt_id = ?", (selected_id,)).fetchone()
    return _preference_prompt_from_row(updated)


def delete_preference_prompt(
    *,
    prompt_id: str,
    path: str | Path | None = None,
) -> bool:
    selected_id = str(prompt_id or "").strip()
    if not selected_id:
        raise ValueError("preference prompt id is required")
    with connect(path) as connection:
        before = connection.total_changes
        connection.execute("DELETE FROM preference_prompts WHERE prompt_id = ?", (selected_id,))
        deleted = connection.total_changes > before
        if deleted:
            _rebuild_preference_profile_connection(connection)
        return deleted


def rebuild_preference_profile(*, path: str | Path | None = None) -> dict[str, Any]:
    with connect(path) as connection:
        return _rebuild_preference_profile_connection(connection)


def get_preference_profile(*, path: str | Path | None = None) -> dict[str, Any]:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM preference_profile WHERE profile_id = ?",
            (PREFERENCE_PROFILE_ID,),
        ).fetchone()
        if row is None:
            return _rebuild_preference_profile_connection(connection)
        return _preference_profile_from_row(row)


def get_relevant_preference_profile(
    *,
    query: str = "",
    paper: Paper | dict[str, Any] | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    tokens = _relevance_tokens(query, paper)
    now = _now()
    with connect(path) as connection:
        settings = _preference_settings_connection(connection)
        prompt_rows = connection.execute(
            """
            SELECT * FROM preference_prompts
            WHERE enabled = 1
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        query_rows = []
        if settings.get("learning_enabled", True) and settings.get("query_history_enabled", True):
            query_rows = connection.execute(
                """
                SELECT * FROM preference_query_history
                ORDER BY updated_at DESC, use_count DESC
                LIMIT 50
                """
            ).fetchall()
        event_rows = []
        if settings.get("learning_enabled", True):
            event_rows = connection.execute(
                """
                SELECT library_events.action, library_items.payload_json
                FROM library_events
                LEFT JOIN library_items ON library_items.library_key = library_events.library_key
                ORDER BY library_events.created_at DESC
                LIMIT ?
                """,
                (PREFERENCE_EVENT_LIMIT,),
            ).fetchall()

    matched_prompts = []
    for row in prompt_rows:
        prompt = _preference_prompt_from_row(row)
        score = _token_overlap_score(tokens, prompt["text"])
        if score > 0:
            matched_prompts.append((score, prompt))
    matched_prompts.sort(key=lambda item: (-item[0], item[1]["updated_at"]))

    matched_queries = []
    for row in query_rows:
        query_item = _preference_query_from_row(row)
        score = _token_overlap_score(tokens, query_item["text"])
        if score > 0:
            matched_queries.append((score + int(query_item["use_count"]), query_item))
    matched_queries.sort(key=lambda item: (-item[0], item[1]["updated_at"]))

    positive_terms: Counter[str] = Counter()
    negative_terms: Counter[str] = Counter()
    positive_sources: Counter[str] = Counter()
    negative_sources: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    relevant_events = 0

    for _score, prompt in matched_prompts:
        for token in _profile_tokens(prompt["text"]):
            positive_terms[token] += 4 * _bounded_prompt_weight(prompt.get("weight"))

    for _score, query_item in matched_queries:
        query_weight = min(5, max(1, int(query_item.get("use_count") or 1))) * 2
        for token in _profile_tokens(query_item["text"]):
            positive_terms[token] += query_weight

    for row in event_rows:
        action = str(row["action"] or "").strip().lower()
        if action in MODEL_ASSISTED_ACTIONS and not settings.get("model_signal_learning_enabled", True):
            continue
        weight = int(PREFERENCE_ACTION_WEIGHTS.get(action, 0))
        payload = _json_loads(row["payload_json"], {})
        if weight == 0 or not isinstance(payload, dict):
            continue
        if not (tokens & set(_topic_payload_tokens(payload))):
            continue
        relevant_events += 1
        action_counts[action] += 1
        target_terms = positive_terms if weight > 0 else negative_terms
        for token in _profile_payload_tokens(payload):
            target_terms[token] += abs(weight)
        source = str(payload.get("source") or "").strip().lower()
        if source:
            if weight > 0:
                positive_sources[source] += abs(weight)
            else:
                negative_sources[source] += abs(weight)

    manual_prompts = [prompt for _score, prompt in matched_prompts[:5]]
    recent_queries = [query_item for _score, query_item in matched_queries[:5]]
    positive = _weighted_terms(positive_terms)
    negative = _weighted_terms(negative_terms)
    signal_counts = {
        "matched_prompt_count": len(manual_prompts),
        "matched_query_count": len(recent_queries),
        "matched_event_count": relevant_events,
        "actions": dict(sorted(action_counts.items())),
        "learning_enabled": bool(settings.get("learning_enabled", True)),
        "query_history_enabled": bool(settings.get("query_history_enabled", True)),
        "model_signal_learning_enabled": bool(settings.get("model_signal_learning_enabled", True)),
    }
    profile = {
        "version": 1,
        "summary": _profile_summary(
            manual_prompts=[prompt["text"] for prompt in manual_prompts],
            recent_queries=[query_item["text"] for query_item in recent_queries],
            positive_terms=positive,
            negative_terms=negative,
        ),
        "manual_prompts": [prompt["text"] for prompt in manual_prompts],
        "recent_queries": recent_queries,
        "positive_terms": positive,
        "negative_terms": negative,
        "positive_sources": _weighted_terms(positive_sources, limit=8),
        "negative_sources": _weighted_terms(negative_sources, limit=8),
        "settings": settings,
        "relevance": {
            "token_count": len(tokens),
            "matched_prompt_count": len(manual_prompts),
            "matched_query_count": len(recent_queries),
            "matched_event_count": relevant_events,
        },
    }
    profile["signal_counts"] = signal_counts
    return {
        "profile_id": PREFERENCE_PROFILE_ID,
        "profile": profile,
        "signal_counts": signal_counts,
        "generated_at": now,
        "updated_at": now,
    }


def evaluate_preference_learning(
    *,
    limit: int = 1000,
    k: int = 10,
    path: str | Path | None = None,
) -> dict[str, Any]:
    max_rows = max(1, min(int(limit), 5000))
    top_k = max(1, min(int(k), 100))
    with connect(path) as connection:
        item_rows = connection.execute(
            """
            SELECT library_key, paper_id, payload_json, last_action_at
            FROM library_items
            ORDER BY last_action_at DESC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
        event_rows = connection.execute(
            """
            SELECT library_key, action, payload_json, created_at
            FROM library_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max_rows * 5,),
        ).fetchall()

    event_groups: dict[str, list[dict[str, Any]]] = {}
    for row in event_rows:
        payload = _json_loads(row["payload_json"], {})
        event_groups.setdefault(row["library_key"], []).append(
            {
                "action": row["action"],
                "payload": payload if isinstance(payload, dict) else {},
                "created_at": row["created_at"],
            }
        )

    examples: list[dict[str, Any]] = []
    positive_terms: Counter[str] = Counter()
    negative_terms: Counter[str] = Counter()
    noise_tags: Counter[str] = Counter()
    for row in item_rows:
        events = event_groups.get(row["library_key"], [])
        if not events:
            continue
        actions = _preference_signal_actions(Counter(str(event["action"]) for event in events))
        if not actions:
            continue
        score = sum(int(PREFERENCE_ACTION_WEIGHTS.get(action, 0)) * count for action, count in actions.items())
        label = _training_label(score)
        payload = _json_loads(row["payload_json"], {})
        clean_payload = payload if isinstance(payload, dict) else {}
        for tag in _event_noise_tags(events):
            noise_tags[tag] += 1
        target_terms = positive_terms if score > 0 else negative_terms if score < 0 else None
        if target_terms is not None:
            for token in _profile_payload_tokens(clean_payload):
                target_terms[token] += abs(score)
        examples.append(
            {
                "paper_id": row["paper_id"],
                "label": label,
                "weight": int(score),
                "signals": dict(sorted(actions.items())),
                "last_action_at": row["last_action_at"],
            }
        )

    positive_count = sum(1 for item in examples if item["label"] in {"positive", "weak_positive"})
    negative_count = sum(1 for item in examples if item["label"] in {"negative", "weak_negative"})
    ranked = [item for item in examples[:top_k] if item["label"] != "neutral"]
    precision_at_k = None
    if ranked:
        precision_at_k = round(sum(1 for item in ranked if item["weight"] > 0) / len(ranked), 4)
    return {
        "version": 1,
        "example_count": len(examples),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "precision_at_k": precision_at_k,
        "k": top_k,
        "evaluated_count": len(ranked),
        "noise_tag_distribution": dict(sorted(noise_tags.items())),
        "top_positive_terms": _weighted_terms(positive_terms, limit=12),
        "top_negative_terms": _weighted_terms(negative_terms, limit=12),
    }


def export_preference_training_data(
    *,
    limit: int = 1000,
    include_weak: bool = True,
    include_model_assisted: bool = True,
    path: str | Path | None = None,
) -> dict[str, Any]:
    max_rows = max(1, min(int(limit), 5000))
    with connect(path) as connection:
        item_rows = connection.execute(
            """
            SELECT library_key, paper_id, payload_json, read_at, favorite_at, hidden_at,
                   first_action_at, last_action_at
            FROM library_items
            ORDER BY last_action_at DESC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
        event_rows = connection.execute(
            """
            SELECT library_key, action, payload_json, created_at
            FROM library_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max_rows * 5,),
        ).fetchall()
        prompt_rows = connection.execute(
            """
            SELECT * FROM preference_prompts
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
        query_rows = connection.execute(
            """
            SELECT * FROM preference_query_history
            ORDER BY updated_at DESC, use_count DESC
            LIMIT 200
            """
        ).fetchall()

    event_groups: dict[str, list[dict[str, Any]]] = {}
    for row in event_rows:
        payload = _json_loads(row["payload_json"], {})
        event_groups.setdefault(row["library_key"], []).append(
            {
                "action": row["action"],
                "payload": payload if isinstance(payload, dict) else {},
                "created_at": row["created_at"],
            }
        )

    examples: list[dict[str, Any]] = []
    for row in item_rows:
        events = event_groups.get(row["library_key"], [])
        if not events:
            continue
        actions = _preference_signal_actions(Counter(str(event["action"]) for event in events))
        if not actions:
            continue
        score = sum(int(PREFERENCE_ACTION_WEIGHTS.get(action, 0)) * count for action, count in actions.items())
        if not include_model_assisted and set(actions).issubset({"ai_recommend", "ai_reject"}):
            continue
        label = _training_label(score)
        if not include_weak and label.startswith("weak"):
            continue
        payload = _json_loads(row["payload_json"], {})
        example = {
            "kind": "paper_preference",
            "library_key": row["library_key"],
            "paper_id": row["paper_id"],
            "label": label,
            "weight": int(score),
            "signal_quality": _training_signal_quality(dict(actions)),
            "signals": dict(sorted(actions.items())),
            "noise_tags": _event_noise_tags(events),
            "quality_score": _event_number(events, "quality_score"),
            "preference_score": _event_number(events, "preference_score"),
            "correction_context": _training_correction_context(dict(actions), events),
            "paper": _training_paper_payload(payload if isinstance(payload, dict) else {}),
            "first_action_at": row["first_action_at"],
            "last_action_at": row["last_action_at"],
        }
        examples.append(example)

    return {
        "version": 1,
        "authorized": True,
        "settings": get_preference_settings(path=path)["settings"],
        "example_count": len(examples),
        "examples": examples,
        "manual_prompts": [_preference_prompt_from_row(row) for row in prompt_rows],
        "query_history": [_preference_query_from_row(row) for row in query_rows],
        "noise_policy": {
            "metadata_only": True,
            "secret_redaction": True,
            "weak_labels": include_weak,
            "model_assisted_signals": include_model_assisted,
            "strong_positive_actions": ["favorite", "zotero", "export"],
            "strong_negative_actions": ["hide"],
            "weak_model_actions": ["ai_recommend", "ai_reject"],
        },
    }
