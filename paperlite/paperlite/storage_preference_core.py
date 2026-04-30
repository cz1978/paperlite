from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import timedelta
from typing import Any

from paperlite.metadata_cleaning import sanitize_paper, sanitize_paper_payload
from paperlite.models import Paper
from paperlite.storage_schema import _json_dumps, _json_loads, _now, _now_dt

LIBRARY_ACTIONS = {
    "read",
    "unread",
    "favorite",
    "unfavorite",
    "hide",
    "unhide",
    "zotero",
    "export",
    "enrich",
    "translate",
    "detail",
    "ai_recommend",
    "ai_reject",
}
LIBRARY_ITEM_FILTERS = {"all", "favorite", "read", "hidden", "recent"}
PREFERENCE_PROFILE_ID = "default"
PREFERENCE_EVENT_LIMIT = 500
PREFERENCE_TERM_LIMIT = 16
MODEL_ASSISTED_ACTIONS = {"ai_recommend", "ai_reject"}
EXPLICIT_PREFERENCE_ACTIONS = {"favorite", "hide", "zotero", "export"}
UNDO_PREFERENCE_ACTIONS = {"unread": "read", "unfavorite": "favorite", "unhide": "hide"}
DEFAULT_PREFERENCE_SETTINGS = {
    "learning_enabled": True,
    "query_history_enabled": True,
    "model_signal_learning_enabled": True,
    "auto_purify_enabled": True,
    "query_max_age_days": 60,
    "model_signal_max_age_days": 21,
}
PREFERENCE_ACTION_WEIGHTS = {
    "favorite": 5,
    "zotero": 5,
    "export": 4,
    "detail": 3,
    "enrich": 3,
    "translate": 3,
    "read": 1,
    "ai_recommend": 1,
    "ai_reject": -1,
    "hide": -5,
}
RESEARCH_NOISE_TAGS = {
    "irrelevant",
    "weak_metadata",
    "announcement",
    "marketing",
    "duplicate",
    "too_old",
    "opinion_only",
    "low_method_detail",
    "non_research",
    "source_low_signal",
    "other",
}
PREFERENCE_STOPWORDS = {
    "about",
    "abstract",
    "after",
    "also",
    "an",
    "and",
    "announce",
    "announcement",
    "are",
    "arxiv",
    "as",
    "at",
    "based",
    "be",
    "been",
    "before",
    "between",
    "biorxiv",
    "by",
    "can",
    "cdots",
    "co",
    "data",
    "doi",
    "elsevier",
    "et",
    "fig",
    "figure",
    "for",
    "from",
    "geq",
    "has",
    "have",
    "how",
    "https",
    "in",
    "introduction",
    "is",
    "journal",
    "latex",
    "leq",
    "ldots",
    "log",
    "math",
    "mathbb",
    "mathrm",
    "into",
    "method",
    "model",
    "nbsp",
    "new",
    "no",
    "not",
    "novel",
    "of",
    "on",
    "or",
    "our",
    "paper",
    "preprint",
    "prefer",
    "publication",
    "research",
    "result",
    "results",
    "rss",
    "section",
    "show",
    "study",
    "that",
    "the",
    "these",
    "then",
    "this",
    "through",
    "to",
    "type",
    "using",
    "via",
    "we",
    "were",
    "where",
    "which",
    "with",
    "www",
}
TRAINING_PAPER_FIELDS = (
    "id",
    "source",
    "source_type",
    "title",
    "abstract",
    "authors",
    "url",
    "doi",
    "published_at",
    "categories",
    "concepts",
    "venue",
    "journal",
    "publisher",
)


def _redact_secretish_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", text)
    text = re.sub(r"(?i)\bbearer\s+[a-z0-9._-]{8,}", "Bearer [redacted]", text)
    text = re.sub(r"\bsk-[a-zA-Z0-9_-]{8,}", "sk-[redacted]", text)
    return text


def _clean_preference_text(value: str) -> str:
    return " ".join(_redact_secretish_text(value).strip().split())[:1000]


def _bounded_prompt_weight(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 1
    return max(1, min(number, 5))


def _preference_prompt_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "prompt_id": row["prompt_id"],
        "text": row["text"],
        "enabled": bool(row["enabled"]),
        "weight": int(row["weight"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _preference_query_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "query_id": row["query_id"],
        "text": row["text"],
        "source": row["source"],
        "use_count": int(row["use_count"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _preference_profile_from_row(row: sqlite3.Row) -> dict[str, Any]:
    profile = _json_loads(row["profile_json"], {})
    signal_counts = _json_loads(row["signal_counts_json"], {})
    return {
        "profile_id": row["profile_id"],
        "profile": profile if isinstance(profile, dict) else {},
        "signal_counts": signal_counts if isinstance(signal_counts, dict) else {},
        "generated_at": row["generated_at"],
        "updated_at": row["updated_at"],
    }


def _coerce_setting_value(key: str, value: Any) -> Any:
    default = DEFAULT_PREFERENCE_SETTINGS[key]
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "on", "启用", "开启"}:
            return True
        if text in {"false", "0", "no", "n", "off", "禁用", "关闭"}:
            return False
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if key == "query_max_age_days":
        return max(1, min(number, 365))
    if key == "model_signal_max_age_days":
        return max(1, min(number, 365))
    return number


def _preference_settings_connection(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute("SELECT key, value_json FROM preference_settings").fetchall()
    settings = dict(DEFAULT_PREFERENCE_SETTINGS)
    for row in rows:
        key = str(row["key"] or "")
        if key not in DEFAULT_PREFERENCE_SETTINGS:
            continue
        settings[key] = _coerce_setting_value(key, _json_loads(row["value_json"], DEFAULT_PREFERENCE_SETTINGS[key]))
    return settings


def _save_preference_settings_connection(connection: sqlite3.Connection, updates: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    current = _preference_settings_connection(connection)
    for key, value in updates.items():
        if key not in DEFAULT_PREFERENCE_SETTINGS:
            continue
        current[key] = _coerce_setting_value(key, value)
        connection.execute(
            """
            INSERT INTO preference_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value_json = excluded.value_json,
              updated_at = excluded.updated_at
            """,
            (key, _json_dumps(current[key]), now),
        )
    return current


def _profile_text_parts(payload: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in ("title", "abstract", "venue", "journal", "publisher"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    for key in ("categories", "concepts", "authors"):
        value = payload.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item)
        elif value:
            parts.append(str(value))
    return parts


def _profile_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9_+-]{1,}|[\u4e00-\u9fff]{2,}", str(text or "").lower())
    return [token for token in tokens if token not in PREFERENCE_STOPWORDS and not re.fullmatch(r"v\d+", token)]


def _profile_payload_tokens(payload: dict[str, Any]) -> list[str]:
    return _profile_tokens(" ".join(_profile_text_parts(payload)))


def _topic_payload_tokens(payload: dict[str, Any]) -> list[str]:
    parts = [str(payload.get(key) or "") for key in ("title", "abstract", "source")]
    return _profile_tokens(" ".join(parts))


def _training_paper_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clean = sanitize_paper_payload(payload if isinstance(payload, dict) else {})
    return {key: clean.get(key) for key in TRAINING_PAPER_FIELDS if clean.get(key) not in (None, "", [])}


def _training_label(score: int) -> str:
    if score >= 3:
        return "positive"
    if score > 0:
        return "weak_positive"
    if score <= -3:
        return "negative"
    if score < 0:
        return "weak_negative"
    return "neutral"


def _training_signal_quality(actions: dict[str, int]) -> str:
    action_set = set(actions)
    if action_set & EXPLICIT_PREFERENCE_ACTIONS:
        return "explicit"
    if action_set & {"detail", "enrich", "translate", "read"}:
        return "implicit"
    if action_set & MODEL_ASSISTED_ACTIONS:
        return "model_assisted"
    return "unknown"


def _preference_signal_actions(actions: dict[str, int] | Counter[str]) -> Counter[str]:
    return Counter(
        {
            str(action): int(count)
            for action, count in actions.items()
            if int(count) > 0 and str(action) in PREFERENCE_ACTION_WEIGHTS
        }
    )


def _weighted_terms(counter: Counter[str], *, limit: int = PREFERENCE_TERM_LIMIT) -> list[dict[str, Any]]:
    return [
        {"term": term, "weight": int(weight)}
        for term, weight in counter.most_common(limit)
        if str(term).strip() and int(weight) > 0
    ]

def _profile_summary(
    *,
    manual_prompts: list[str],
    recent_queries: list[str],
    positive_terms: list[dict[str, Any]],
    negative_terms: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if manual_prompts:
        parts.append("长期提示词：" + "；".join(manual_prompts[:3]))
    if recent_queries:
        parts.append("常用筛选词：" + "；".join(recent_queries[:3]))
    if positive_terms:
        parts.append("偏好关键词：" + ", ".join(item["term"] for item in positive_terms[:8] if item.get("term")))
    if negative_terms:
        parts.append("弱化/避开：" + ", ".join(item["term"] for item in negative_terms[:8]))
    return " | ".join(parts) if parts else "暂无足够偏好信号"


def _coerce_paper_payload(value: Paper | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, Paper):
        return sanitize_paper(value).to_dict()
    if isinstance(value, dict):
        return sanitize_paper_payload(value)
    return {}


def _relevance_tokens(query: str, paper: Paper | dict[str, Any] | None) -> set[str]:
    payload = _coerce_paper_payload(paper)
    return set(_profile_tokens(query)) | set(_topic_payload_tokens(payload))


def _token_overlap_score(tokens: set[str], text: str) -> int:
    if not tokens:
        return 0
    return len(tokens & set(_profile_tokens(text)))


def _event_noise_tags(events: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        values = payload.get("noise_tags")
        if values is None and isinstance(payload.get("ai_decision"), dict):
            values = payload["ai_decision"].get("noise_tags")
        if isinstance(values, str):
            candidates = [values]
        elif isinstance(values, list):
            candidates = values
        else:
            candidates = []
        for value in candidates:
            tag = str(value or "").strip().lower()
            if tag not in RESEARCH_NOISE_TAGS or tag in seen:
                continue
            tags.append(tag)
            seen.add(tag)
    return tags


def _event_number(events: list[dict[str, Any]], key: str) -> int | None:
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        value = payload.get(key)
        if value is None and isinstance(payload.get("ai_decision"), dict):
            value = payload["ai_decision"].get(key)
        if value is None:
            continue
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            continue
        return max(0, min(100, number))
    return None


def _event_ai_groups(events: list[dict[str, Any]]) -> set[str]:
    groups: set[str] = set()
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        group = payload.get("display_group") or payload.get("group")
        if group is None and isinstance(payload.get("ai_decision"), dict):
            group = payload["ai_decision"].get("display_group") or payload["ai_decision"].get("group")
        clean = str(group or "").strip().lower()
        if clean in {"recommend", "maybe", "reject"}:
            groups.add(clean)
    return groups


def _training_correction_context(actions: dict[str, int], events: list[dict[str, Any]]) -> dict[str, Any]:
    action_set = set(actions)
    ai_groups = _event_ai_groups(events)
    explicit_positive = bool(action_set & {"favorite", "zotero", "export"})
    explicit_negative = bool(action_set & {"hide"})
    model_recommended = "ai_recommend" in action_set or "recommend" in ai_groups
    model_rejected = "ai_reject" in action_set or "reject" in ai_groups
    return {
        "explicit_positive": explicit_positive,
        "explicit_negative": explicit_negative,
        "model_recommended": model_recommended,
        "model_rejected": model_rejected,
        "overridden_model_signal": bool((model_recommended and explicit_negative) or (model_rejected and explicit_positive)),
    }


def _current_library_counts(connection: sqlite3.Connection) -> dict[str, int]:
    row = connection.execute(
        """
        SELECT
          SUM(CASE WHEN read_at IS NOT NULL THEN 1 ELSE 0 END) AS read_count,
          SUM(CASE WHEN favorite_at IS NOT NULL THEN 1 ELSE 0 END) AS favorite_count,
          SUM(CASE WHEN hidden_at IS NOT NULL THEN 1 ELSE 0 END) AS hidden_count,
          COUNT(*) AS item_count
        FROM library_items
        """
    ).fetchone()
    if row is None:
        return {"item_count": 0, "read_count": 0, "favorite_count": 0, "hidden_count": 0}
    return {
        "item_count": int(row["item_count"] or 0),
        "read_count": int(row["read_count"] or 0),
        "favorite_count": int(row["favorite_count"] or 0),
        "hidden_count": int(row["hidden_count"] or 0),
    }


def _purify_preference_signals_connection(
    connection: sqlite3.Connection,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = settings or _preference_settings_connection(connection)
    if not current.get("auto_purify_enabled", True):
        return {"enabled": False, "removed_queries": 0, "removed_model_events": 0, "removed_overridden_model_events": 0}
    now = _now_dt()
    query_cutoff = (now - timedelta(days=int(current.get("query_max_age_days") or 60))).isoformat()
    model_cutoff = (now - timedelta(days=int(current.get("model_signal_max_age_days") or 21))).isoformat()
    before = connection.total_changes
    connection.execute(
        """
        DELETE FROM preference_query_history
        WHERE use_count <= 1 AND updated_at < ?
        """,
        (query_cutoff,),
    )
    removed_queries = connection.total_changes - before

    model_actions = tuple(sorted(MODEL_ASSISTED_ACTIONS))
    placeholders = ",".join("?" for _ in model_actions)
    before = connection.total_changes
    connection.execute(
        f"""
        DELETE FROM library_events
        WHERE action IN ({placeholders}) AND created_at < ?
        """,
        (*model_actions, model_cutoff),
    )
    removed_model_events = connection.total_changes - before

    explicit_actions = tuple(sorted(EXPLICIT_PREFERENCE_ACTIONS))
    model_placeholders = ",".join("?" for _ in model_actions)
    explicit_placeholders = ",".join("?" for _ in explicit_actions)
    before = connection.total_changes
    connection.execute(
        f"""
        DELETE FROM library_events
        WHERE action IN ({model_placeholders})
          AND library_key IN (
            SELECT library_key FROM library_events
            WHERE action IN ({explicit_placeholders})
          )
        """,
        (*model_actions, *explicit_actions),
    )
    removed_overridden = connection.total_changes - before
    return {
        "enabled": True,
        "removed_queries": removed_queries,
        "removed_model_events": removed_model_events,
        "removed_overridden_model_events": removed_overridden,
    }


def _build_preference_profile(connection: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = _preference_settings_connection(connection)
    prompt_rows = connection.execute(
        """
        SELECT * FROM preference_prompts
        ORDER BY updated_at DESC, created_at DESC
        """
    ).fetchall()
    enabled_prompts = [_preference_prompt_from_row(row) for row in prompt_rows if bool(row["enabled"])]
    query_rows = []
    if settings.get("learning_enabled", True) and settings.get("query_history_enabled", True):
        query_rows = connection.execute(
            """
            SELECT * FROM preference_query_history
            ORDER BY updated_at DESC, use_count DESC
            LIMIT 50
            """
        ).fetchall()
    recent_queries = [_preference_query_from_row(row) for row in query_rows]
    event_rows = []
    if settings.get("learning_enabled", True):
        event_rows = connection.execute(
            """
            SELECT library_events.action, library_events.created_at, library_items.payload_json
            FROM library_events
            LEFT JOIN library_items ON library_items.library_key = library_events.library_key
            ORDER BY library_events.created_at DESC
            LIMIT ?
            """,
            (PREFERENCE_EVENT_LIMIT,),
        ).fetchall()

    positive_terms: Counter[str] = Counter()
    negative_terms: Counter[str] = Counter()
    positive_sources: Counter[str] = Counter()
    negative_sources: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()

    for prompt in enabled_prompts:
        prompt_weight = _bounded_prompt_weight(prompt.get("weight"))
        for token in _profile_tokens(str(prompt.get("text") or "")):
            positive_terms[token] += 4 * prompt_weight

    for query in recent_queries:
        query_weight = min(5, max(1, int(query.get("use_count") or 1))) * 2
        for token in _profile_tokens(str(query.get("text") or "")):
            positive_terms[token] += query_weight

    for row in event_rows:
        action = str(row["action"] or "").strip().lower()
        if action in MODEL_ASSISTED_ACTIONS and not settings.get("model_signal_learning_enabled", True):
            continue
        weight = int(PREFERENCE_ACTION_WEIGHTS.get(action, 0))
        if weight == 0:
            continue
        action_counts[action] += 1
        payload = _json_loads(row["payload_json"], {})
        if not isinstance(payload, dict):
            continue
        target_terms = positive_terms if weight > 0 else negative_terms
        for token in _profile_payload_tokens(payload):
            target_terms[token] += abs(weight)
        source = str(payload.get("source") or "").strip().lower()
        if source:
            if weight > 0:
                positive_sources[source] += abs(weight)
            else:
                negative_sources[source] += abs(weight)

    positive = _weighted_terms(positive_terms)
    negative = _weighted_terms(negative_terms)
    profile = {
        "version": 1,
        "summary": _profile_summary(
            manual_prompts=[prompt["text"] for prompt in enabled_prompts],
            recent_queries=[query["text"] for query in recent_queries],
            positive_terms=positive,
            negative_terms=negative,
        ),
        "manual_prompts": [prompt["text"] for prompt in enabled_prompts[:10]],
        "recent_queries": recent_queries[:10],
        "positive_terms": positive,
        "negative_terms": negative,
        "positive_sources": _weighted_terms(positive_sources, limit=8),
        "negative_sources": _weighted_terms(negative_sources, limit=8),
        "settings": settings,
    }
    signal_counts = {
        **_current_library_counts(connection),
        "prompt_count": len(prompt_rows),
        "enabled_prompt_count": len(enabled_prompts),
        "query_count": len(query_rows),
        "query_use_count": sum(int(query["use_count"]) for query in recent_queries),
        "events_considered": len(event_rows),
        "actions": dict(sorted(action_counts.items())),
        "learning_enabled": bool(settings.get("learning_enabled", True)),
        "model_signal_learning_enabled": bool(settings.get("model_signal_learning_enabled", True)),
        "query_history_enabled": bool(settings.get("query_history_enabled", True)),
    }
    profile["signal_counts"] = signal_counts
    return profile, signal_counts


def _rebuild_preference_profile_connection(connection: sqlite3.Connection) -> dict[str, Any]:
    now = _now()
    settings = _preference_settings_connection(connection)
    purify_result = _purify_preference_signals_connection(connection, settings)
    profile, signal_counts = _build_preference_profile(connection)
    profile["purify"] = purify_result
    connection.execute(
        """
        INSERT INTO preference_profile (
          profile_id, profile_json, signal_counts_json, generated_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(profile_id) DO UPDATE SET
          profile_json = excluded.profile_json,
          signal_counts_json = excluded.signal_counts_json,
          generated_at = excluded.generated_at,
          updated_at = excluded.updated_at
        """,
        (PREFERENCE_PROFILE_ID, _json_dumps(profile), _json_dumps(signal_counts), now, now),
    )
    row = connection.execute(
        "SELECT * FROM preference_profile WHERE profile_id = ?",
        (PREFERENCE_PROFILE_ID,),
    ).fetchone()
    return _preference_profile_from_row(row)

__all__ = [name for name in globals() if not name.startswith("__")]
