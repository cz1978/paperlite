from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperlite.agent import paper_prompt, parse_paper
from paperlite.llm import complete_chat
from paperlite.metadata_cleaning import clean_abstract_text, has_usable_abstract
from paperlite.models import Paper
from paperlite.translation_profiles import (
    DETAIL_TRANSLATION_STYLES,
    TranslationProfile,
    resolve_translation_profile,
)
import paperlite.storage as storage

_ALLOWED_BULLET_LABELS = {"结论", "方法", "数据", "背景", "机制", "对比", "风险", "应用"}
_NO_ABSTRACT_POLICY = "no_abstract_title_only_v4"
_DETAIL_TRANSLATION_POLICY = "detail_readable_v2"


def _authors_text(paper: Paper) -> str:
    if not paper.authors:
        return ""
    if len(paper.authors) == 1:
        return paper.authors[0]
    return f"{paper.authors[0]} et al."


def _brief_input(paper: Paper) -> dict[str, Any]:
    return {
        "title": paper.title,
        "abstract": _clean_paper_abstract(paper),
        "source_type": paper.source_type or paper.source or paper.publisher or "",
        "categories": list(paper.categories or paper.concepts or []),
        "authors": _authors_text(paper),
        "id": paper.doi or paper.id,
    }


def _translation_cache_key(
    paper: Paper,
    target: str,
    style: str,
    profile: TranslationProfile | None = None,
) -> tuple[str, str]:
    material = {
        "paper_id": paper.id,
        "title": paper.title,
        "abstract": _clean_paper_abstract(paper),
        "source_type": paper.source_type,
        "source": paper.source,
        "doi": paper.doi,
        "categories": list(paper.categories or paper.concepts or []),
        "target_language": target,
        "style": style,
        "translation_profile": profile.key if profile else "",
        "translation_profile_version": profile.version if profile else "",
        "translation_profile_hash": profile.prompt_hash if profile else "",
    }
    if style.lower() == "brief" and not _has_abstract(paper):
        material["brief_policy"] = _NO_ABSTRACT_POLICY
    if style.lower() in {"detail", "detail_literal", "literal_detail"}:
        material["detail_policy"] = _DETAIL_TRANSLATION_POLICY
    content = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content_hash, content_hash


def _profile_result_fields(profile: TranslationProfile | None) -> dict[str, Any]:
    if profile is None:
        return {
            "translation_profile": "",
            "translation_profile_version": "",
            "translation_profile_hash": "",
        }
    return {
        "translation_profile": profile.key,
        "translation_profile_version": profile.version,
        "translation_profile_hash": profile.prompt_hash,
    }


def _empty_brief() -> dict[str, Any]:
    return {
        "cn_flash_180": "",
        "card_headline": "",
        "card_bullets": [],
        "card_tags": [],
    }


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clean_paper_abstract(paper: Paper) -> str:
    return clean_abstract_text(
        paper.abstract,
        title=paper.title,
        doi=paper.doi,
        journal=paper.journal,
        venue=paper.venue,
    )


def _has_abstract(paper: Paper) -> bool:
    return has_usable_abstract(
        paper.abstract,
        title=paper.title,
        doi=paper.doi,
        journal=paper.journal,
        venue=paper.venue,
    )


def _normalize_brief(value: dict[str, Any] | None) -> dict[str, Any]:
    data = value or {}
    bullets = []
    for item in data.get("card_bullets") or []:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label"))
        text = _text(item.get("text"))
        if label not in _ALLOWED_BULLET_LABELS or not text:
            continue
        bullets.append({"label": label, "text": text})
        if len(bullets) == 4:
            break

    tags = []
    for item in data.get("card_tags") or []:
        tag = _text(item)
        if not tag:
            continue
        if not tag.startswith("#"):
            tag = f"#{tag.lstrip('#')}"
        tags.append(tag)
        if len(tags) == 5:
            break

    return {
        "cn_flash_180": _text(data.get("cn_flash_180")),
        "card_headline": _text(data.get("card_headline")),
        "card_bullets": bullets,
        "card_tags": tags,
    }


def _fallback_brief(paper: Paper, title_zh: str = "") -> dict[str, Any]:
    headline = title_zh or paper.title
    return {
        "cn_flash_180": title_zh or paper.title,
        "card_headline": headline[:30],
        "card_bullets": [{"label": "结论", "text": title_zh or paper.title[:50]}],
        "card_tags": [],
    }


def _format_brief_translation(title_zh: str, brief: dict[str, Any]) -> str:
    title = title_zh or brief.get("card_headline") or ""
    flash = brief.get("cn_flash_180") or ""
    parts = []
    if title:
        parts.append(f"标题：{title}")
    if flash:
        parts.append(f"摘要：{flash}")
    return "\n".join(parts)


def _title_only_result(
    paper: Paper,
    *,
    target: str,
    translation_style: str,
    profile: TranslationProfile | None,
    title_zh: str,
    title_result: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    brief = {
        "cn_flash_180": "",
        "card_headline": title_zh,
        "card_bullets": [],
        "card_tags": [],
    }
    return {
        "paper": paper.to_dict(),
        "target_language": target,
        "style": translation_style,
        "title_zh": title_zh,
        "brief": brief,
        "cn_flash_180": "",
        "card_headline": title_zh,
        "card_bullets": [],
        "card_tags": [],
        "translation": _format_brief_translation(title_zh, brief),
        **_profile_result_fields(profile),
        "model": title_result.get("model"),
        "configured": bool(title_result.get("configured")),
        "warnings": [*warnings, "abstract_missing_brief_skipped"],
        "cached": False,
        "abstract_missing": True,
        "brief_skipped": True,
        "skip_reason": "abstract_missing",
    }


def _translate_plain(
    paper: Paper,
    target: str,
    translation_style: str,
    profile: TranslationProfile | None,
) -> dict[str, Any]:
    system_prompt = profile.body_prompt if profile is not None else (
        "You translate research paper metadata using only the supplied fields. "
        "Preserve author names, DOI, URLs, formulas, model names, and technical terms when appropriate. "
        "Do not add facts or recommendations. Keep the display compact."
    )
    llm_result = complete_chat(
        [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": (
                    f"Translate this paper metadata into {target}. "
                    f"Style: {translation_style}. Use the existing title and abstract as the only source material.\n\n"
                    f"{paper_prompt(paper)}"
                ),
            },
        ],
        temperature=0.1,
        max_tokens=profile.max_tokens if profile is not None else 900,
    )
    return {
        "paper": paper.to_dict(),
        "target_language": target,
        "style": translation_style,
        "translation": llm_result.get("answer", ""),
        **_profile_result_fields(profile),
        "model": llm_result.get("model"),
        "configured": bool(llm_result.get("configured")),
        "warnings": list(llm_result.get("warnings") or []),
        "cached": False,
    }


def _detail_missing_result(
    paper: Paper,
    target: str,
    translation_style: str,
    profile: TranslationProfile | None,
) -> dict[str, Any]:
    return {
        "paper": paper.to_dict(),
        "target_language": target,
        "style": translation_style,
        "title_zh": "",
        "brief": {},
        "cn_flash_180": "",
        "card_headline": "",
        "card_bullets": [],
        "card_tags": [],
        "translation": "",
        "detail_translation": "",
        **_profile_result_fields(profile),
        "model": None,
        "configured": True,
        "warnings": ["abstract_missing_detail_skipped"],
        "cached": False,
        "abstract_missing": True,
        "detail_skipped": True,
        "skip_reason": "abstract_missing",
    }


def _translate_detail(
    paper: Paper,
    target: str,
    translation_style: str,
    profile: TranslationProfile | None,
) -> dict[str, Any]:
    if not _has_abstract(paper):
        return _detail_missing_result(paper, target, translation_style, profile)
    detail_text = _clean_paper_abstract(paper)
    llm_result = complete_chat(
        [
            {
                "role": "system",
                "content": profile.body_prompt if profile is not None else (
                    "You are an academic translation assistant. Translate the supplied paper abstract "
                    "faithfully into readable Chinese. Do not summarize, rewrite, or add facts."
                ),
            },
            {
                "role": "user",
                "content": detail_text,
            },
        ],
        temperature=0.1,
        max_tokens=profile.max_tokens if profile is not None else 1600,
    )
    translated = _text(llm_result.get("answer"))
    return {
        "paper": paper.to_dict(),
        "target_language": target,
        "style": translation_style,
        "title_zh": "",
        "brief": {},
        "cn_flash_180": "",
        "card_headline": "",
        "card_bullets": [],
        "card_tags": [],
        "translation": translated,
        "detail_translation": translated,
        **_profile_result_fields(profile),
        "model": llm_result.get("model"),
        "configured": bool(llm_result.get("configured")),
        "warnings": list(llm_result.get("warnings") or []),
        "cached": False,
        "abstract_missing": False,
        "detail_skipped": False,
    }


def _cacheable(result: dict[str, Any]) -> bool:
    warnings = [str(item) for item in result.get("warnings") or []]
    if not result.get("configured"):
        return False
    if any(item.startswith("llm_error:") for item in warnings):
        return False
    if "brief_json_parse_failed" in warnings or "brief_json_empty" in warnings:
        return False
    return bool(result.get("translation") or result.get("cn_flash_180") or result.get("title_zh"))


def translate_paper(
    paper: dict[str, Any] | Paper,
    target_language: str = "zh-CN",
    style: str | None = None,
    translation_profile: str | None = None,
    cache_path: str | Path | None = None,
) -> dict[str, Any]:
    parsed = parse_paper(paper)
    target = (target_language or "zh-CN").strip() or "zh-CN"
    requested_style = (style or "").strip()
    profile = resolve_translation_profile(translation_profile=translation_profile, style=requested_style or None)
    translation_style = requested_style or (profile.style if profile is not None else "brief")
    if profile is not None and target != profile.target_language:
        raise ValueError(
            f"translation_profile {profile.key} targets {profile.target_language}; requested target_language {target}"
        )
    cache_key, content_hash = _translation_cache_key(parsed, target, translation_style, profile)
    cached = storage.get_translation_cache(cache_key, path=cache_path)
    if cached is not None:
        return cached

    if translation_style.lower() in DETAIL_TRANSLATION_STYLES:
        result = _translate_detail(parsed, target, translation_style, profile)
        if _cacheable(result):
            storage.upsert_translation_cache(
                cache_key=cache_key,
                paper_id=parsed.id,
                content_hash=content_hash,
                target_language=target,
                style=translation_style,
                payload=result,
                path=cache_path,
            )
        return result

    if translation_style.lower() != "brief":
        result = _translate_plain(parsed, target, translation_style, profile)
        if _cacheable(result):
            storage.upsert_translation_cache(
                cache_key=cache_key,
                paper_id=parsed.id,
                content_hash=content_hash,
                target_language=target,
                style=translation_style,
                payload=result,
                path=cache_path,
            )
        return result

    title_result = complete_chat(
        [
            {
                "role": "system",
                "content": profile.title_prompt if profile is not None else (
                    "你是学术翻译助手。请将英文标题翻译为简洁的中文（保持学术性，≪100字符）。"
                    "请直接输出中文标题，不要添加任何解释或前缀。"
                ),
            },
            {
                "role": "user",
                "content": parsed.title,
            },
        ],
        temperature=0.1,
        max_tokens=120,
    )
    title_zh = _text(title_result.get("answer"))
    warnings = list(title_result.get("warnings") or [])
    if not title_result.get("configured"):
        brief = _empty_brief()
        return {
            "paper": parsed.to_dict(),
            "target_language": target,
            "style": translation_style,
            "title_zh": title_zh,
            "brief": brief,
            "cn_flash_180": brief["cn_flash_180"],
            "card_headline": brief["card_headline"],
            "card_bullets": brief["card_bullets"],
            "card_tags": brief["card_tags"],
            "translation": "",
            **_profile_result_fields(profile),
            "model": title_result.get("model"),
            "configured": False,
            "warnings": warnings,
            "cached": False,
            "abstract_missing": not _has_abstract(parsed),
        }

    if not _has_abstract(parsed):
        result = _title_only_result(
            parsed,
            target=target,
            translation_style=translation_style,
            profile=profile,
            title_zh=title_zh,
            title_result=title_result,
            warnings=warnings,
        )
        if _cacheable(result):
            storage.upsert_translation_cache(
                cache_key=cache_key,
                paper_id=parsed.id,
                content_hash=content_hash,
                target_language=target,
                style=translation_style,
                payload=result,
                path=cache_path,
            )
        return result

    brief_result = complete_chat(
        [
            {
                "role": "system",
                "content": profile.body_prompt if profile is not None else (
                    "你是科研快讯编辑，将英文论文标题+摘要转写为中文快讯。"
                    "输出严格单个 JSON 对象，字段包括 cn_flash_180、card_headline、card_bullets、card_tags。"
                    "只使用输入标题和摘要，严禁编造。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(_brief_input(parsed), ensure_ascii=False),
            },
        ],
        temperature=0.1,
        max_tokens=profile.max_tokens if profile is not None else 1200,
    )
    warnings += list(brief_result.get("warnings") or [])
    raw_brief = _text(brief_result.get("answer"))
    parsed_brief = _extract_json_object(raw_brief)
    if parsed_brief is None:
        warnings.append("brief_json_parse_failed")
        brief = _fallback_brief(parsed, title_zh)
    else:
        brief = _normalize_brief(parsed_brief)
        if not brief["cn_flash_180"] and not brief["card_headline"]:
            warnings.append("brief_json_empty")
            brief = _fallback_brief(parsed, title_zh)

    result = {
        "paper": parsed.to_dict(),
        "target_language": target,
        "style": translation_style,
        "title_zh": title_zh,
        "brief": brief,
        "cn_flash_180": brief["cn_flash_180"],
        "card_headline": brief["card_headline"],
        "card_bullets": brief["card_bullets"],
        "card_tags": brief["card_tags"],
        "translation": _format_brief_translation(title_zh, brief),
        **_profile_result_fields(profile),
        "model": brief_result.get("model") or title_result.get("model"),
        "configured": bool(title_result.get("configured")) and bool(brief_result.get("configured")),
        "warnings": warnings,
        "cached": False,
        "abstract_missing": False,
    }
    if _cacheable(result):
        storage.upsert_translation_cache(
            cache_key=cache_key,
            paper_id=parsed.id,
            content_hash=content_hash,
            target_language=target,
            style=translation_style,
            payload=result,
            path=cache_path,
        )
    return result
