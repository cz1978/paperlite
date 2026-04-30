from __future__ import annotations

import json
from typing import Any

from paperlite.agent import paper_prompt, parse_paper
from paperlite.llm import complete_chat
from paperlite.models import Paper

NOISE_TAGS = {
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
QUALITY_BLOCKING_NOISE_TAGS = NOISE_TAGS - {"other"}


DEFAULT_AI_FILTER_QUERY = (
    "默认学术价值筛选：优先推荐适合今天优先阅读的论文。"
    "重点看研究问题是否清晰、方法或数据是否具体、摘要信息是否充分、"
    "是否有潜在影响或可复现/可跟进价值。"
    "信息不足但可能相关放入待定；明显像目录、公告、噪声、摘要缺失且价值弱，或与学术研究关联弱的条目放入不建议。"
)

AI_FILTER_PROMPT = """你是学术论文筛选助手。只基于用户给出的筛选要求和论文元数据判断推荐分组。
不要使用外部知识，不要编造论文没有提供的信息。

输出严格单个 JSON 对象：
{
  "group": "recommend",
  "importance": 80,
  "quality_score": 85,
  "preference_score": 70,
  "noise_tags": [],
  "matched_preferences": ["RAG", "benchmark"],
  "quality_reasons": ["研究问题清晰", "方法/数据具体"],
  "reason": "中文原因，60字以内",
  "confidence": 0.0
}

规则：
- group 只能是 recommend、maybe、reject。
- recommend 表示明显符合筛选要求，值得优先阅读。
- maybe 表示信息不足、只部分相关，或需要人工再看。
- reject 表示明显不符合筛选要求。
- importance 是 0 到 100 的整数，表示相对重要度/优先级。
- quality_score 是 0 到 100 的整数，只评价论文元数据展示出的研究质量和信息充分度。
- preference_score 是 0 到 100 的整数，只评价与用户个人偏好/本次筛选要求的匹配度。
- noise_tags 只能从 irrelevant、weak_metadata、announcement、marketing、duplicate、too_old、opinion_only、low_method_detail、non_research、source_low_signal、other 中选择。
- matched_preferences 最多 5 条，只列命中的偏好/筛选词/来源。
- quality_reasons 最多 5 条，只列公共质量依据。
- 如果 quality_score < 50，或存在明显噪音标签，即使 preference_score 很高也不要给 recommend。
- confidence 是 0 到 1 的数字，表示判断把握。"""


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _coerce_include(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "y", "1", "include", "keep", "保留", "相关", "符合"}:
        return True
    if text in {"false", "no", "n", "0", "exclude", "drop", "排除", "不相关", "不符合"}:
        return False
    return default


def _coerce_confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _coerce_importance(value: Any) -> int:
    return _coerce_score(value, default=50)


def _coerce_score(value: Any, *, default: int = 50) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return int(default)
    return int(max(0, min(100, round(number))))


def _normalize_group(value: Any, *, include: bool | None = None, importance: int = 50) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "recommend": "recommend",
        "recommended": "recommend",
        "推荐": "recommend",
        "推荐组": "recommend",
        "maybe": "maybe",
        "uncertain": "maybe",
        "borderline": "maybe",
        "待定": "maybe",
        "待定组": "maybe",
        "reject": "reject",
        "not_recommended": "reject",
        "not recommended": "reject",
        "exclude": "reject",
        "不建议": "reject",
        "不建议组": "reject",
        "排除": "reject",
    }
    if text in aliases:
        return aliases[text]
    if include is False:
        return "reject"
    if importance >= 70:
        return "recommend"
    if importance <= 35:
        return "reject"
    return "maybe"


def _clean_reason(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text[:80]


def _clean_string_list(value: Any, *, limit: int = 5, item_limit: int = 80) -> list[str]:
    if isinstance(value, str):
        candidates = [item.strip() for item in value.replace("；", ";").replace("，", ",").split(",")]
    elif isinstance(value, list):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if not item:
            continue
        short = item[:item_limit]
        key = short.lower()
        if key in seen:
            continue
        cleaned.append(short)
        seen.add(key)
        if len(cleaned) >= limit:
            break
    return cleaned


def _coerce_noise_tags(value: Any) -> list[str]:
    candidates = _clean_string_list(value, limit=6, item_limit=40)
    tags: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        tag = item.strip().lower().replace(" ", "_").replace("-", "_")
        if tag not in NOISE_TAGS or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)
    if not tags and candidates:
        return ["other"]
    return tags


def _quality_guard_group(group: str, *, quality_score: int, noise_tags: list[str]) -> str:
    if group != "recommend":
        return group
    if quality_score >= 50 and not (set(noise_tags) & QUALITY_BLOCKING_NOISE_TAGS):
        return group
    if quality_score < 35 or "non_research" in noise_tags or "irrelevant" in noise_tags:
        return "reject"
    return "maybe"


def _preference_profile_context(preference_profile: dict[str, Any] | None, *, use_profile: bool) -> tuple[str, str | None]:
    if not use_profile or not isinstance(preference_profile, dict):
        return "", None
    profile = preference_profile.get("profile") if isinstance(preference_profile.get("profile"), dict) else preference_profile
    if not isinstance(profile, dict):
        return "", None
    manual_prompts = [str(item).strip() for item in profile.get("manual_prompts") or [] if str(item).strip()]
    recent_queries = [
        str(item.get("text") or "").strip()
        for item in profile.get("recent_queries") or []
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    positive_terms = [
        str(item.get("term") or "").strip()
        for item in profile.get("positive_terms") or []
        if isinstance(item, dict) and str(item.get("term") or "").strip()
    ]
    negative_terms = [
        str(item.get("term") or "").strip()
        for item in profile.get("negative_terms") or []
        if isinstance(item, dict) and str(item.get("term") or "").strip()
    ]
    summary = str(profile.get("summary") or "").strip()
    if not manual_prompts and not recent_queries and not positive_terms and not negative_terms:
        return "", None
    lines = ["个人偏好画像（来自本地收藏、已读、隐藏和长期提示词）："]
    if summary and summary != "暂无足够偏好信号":
        lines.append(f"- 摘要：{summary}")
    if manual_prompts:
        lines.append("- 长期提示词：" + "；".join(manual_prompts[:5]))
    if recent_queries:
        lines.append("- 最近/常用手动筛选词：" + "；".join(recent_queries[:5]))
    if positive_terms:
        lines.append("- 正向偏好关键词：" + ", ".join(positive_terms[:12]))
    if negative_terms:
        lines.append("- 弱化/避开关键词：" + ", ".join(negative_terms[:12]))
    return "\n".join(lines), summary or None


def _effective_filter_query(
    clean_query: str,
    *,
    preference_profile: dict[str, Any] | None = None,
    use_profile: bool = True,
) -> tuple[str, bool, str | None]:
    profile_context, profile_summary = _preference_profile_context(preference_profile, use_profile=use_profile)
    lines = [
        f"公用默认标准：{DEFAULT_AI_FILTER_QUERY}",
        f"筛选要求：{clean_query}",
    ]
    if profile_context:
        lines.append(profile_context)
    return "\n\n".join(lines), bool(profile_context), profile_summary


def _safe_result(
    paper: Paper,
    query: str,
    effective_query: str,
    llm_result: dict[str, Any],
    *,
    reason: str,
    profile_used: bool = False,
    profile_summary: str | None = None,
) -> dict[str, Any]:
    return {
        "paper": paper.to_dict(),
        "query": query,
        "effective_query": effective_query,
        "profile_used": profile_used,
        "profile_summary": profile_summary,
        "group": "maybe",
        "importance": 50,
        "quality_score": 50,
        "preference_score": 50,
        "noise_tags": [],
        "matched_preferences": [],
        "quality_reasons": [],
        "include": True,
        "reason": reason,
        "confidence": None,
        "configured": bool(llm_result.get("configured")),
        "model": llm_result.get("model"),
        "warnings": list(llm_result.get("warnings") or []),
    }


def filter_paper(
    paper: dict[str, Any] | Paper,
    query: str | None = None,
    *,
    preference_profile: dict[str, Any] | None = None,
    use_profile: bool = True,
) -> dict[str, Any]:
    parsed = parse_paper(paper)
    raw_query = str(query or "").strip()
    clean_query = raw_query or DEFAULT_AI_FILTER_QUERY
    effective_query, profile_used, profile_summary = _effective_filter_query(
        clean_query,
        preference_profile=preference_profile,
        use_profile=use_profile,
    )

    llm_result = complete_chat(
        [
            {
                "role": "system",
                "content": AI_FILTER_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"{effective_query}\n\n"
                    "论文元数据：\n"
                    f"{paper_prompt(parsed)}"
                ),
            },
        ],
        temperature=0.1,
        max_tokens=260,
    )
    if not llm_result.get("configured"):
        return _safe_result(
            parsed,
            clean_query,
            effective_query,
            llm_result,
            reason="LLM 未配置，未执行 AI 筛选",
            profile_used=profile_used,
            profile_summary=profile_summary,
        )

    data = _extract_json_object(str(llm_result.get("answer") or ""))
    if data is None:
        return _safe_result(
            parsed,
            clean_query,
            effective_query,
            llm_result,
            reason="AI 未返回可解析判断，暂保留",
            profile_used=profile_used,
            profile_summary=profile_summary,
        )

    importance = _coerce_importance(data.get("importance"))
    quality_score = _coerce_score(data.get("quality_score"), default=importance)
    preference_score = _coerce_score(data.get("preference_score"), default=50)
    noise_tags = _coerce_noise_tags(data.get("noise_tags"))
    matched_preferences = _clean_string_list(data.get("matched_preferences"), limit=5)
    quality_reasons = _clean_string_list(data.get("quality_reasons"), limit=5)
    include = _coerce_include(data.get("include"), default=True)
    group = _normalize_group(data.get("group"), include=include, importance=importance)
    group = _quality_guard_group(group, quality_score=quality_score, noise_tags=noise_tags)
    return {
        "paper": parsed.to_dict(),
        "query": clean_query,
        "effective_query": effective_query,
        "profile_used": profile_used,
        "profile_summary": profile_summary,
        "group": group,
        "importance": importance,
        "quality_score": quality_score,
        "preference_score": preference_score,
        "noise_tags": noise_tags,
        "matched_preferences": matched_preferences,
        "quality_reasons": quality_reasons,
        "include": group != "reject",
        "reason": _clean_reason(data.get("reason"), "AI 未给出原因"),
        "confidence": _coerce_confidence(data.get("confidence")),
        "configured": True,
        "model": llm_result.get("model"),
        "warnings": list(llm_result.get("warnings") or []),
    }
