from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from paperlite.daily_crawl import create_daily_crawl, run_daily_crawl
from paperlite.daily_export import daily_cache_export_papers, daily_date_range
from paperlite.integrations import agent_result_policy
from paperlite.llm import LLMRequestError, complete_chat, create_embeddings, embedding_status
from paperlite.models import Paper
from paperlite.registry import list_sources
from paperlite.runner import split_keys
from paperlite.storage import (
    daily_cache_papers_for_rag,
    get_crawl_run,
    get_paper_embedding,
    paper_embedding_hash,
    paper_embedding_text,
    upsert_paper_embedding,
)
from paperlite.taxonomy import discipline_record, load_taxonomy, taxonomy_key_for_discipline

RESEARCH_DEFAULT_LIMIT = 15
RESEARCH_MAX_LIMIT = 50
RESEARCH_SOURCE_LIMIT = 15
RESEARCH_CACHE_LIMIT_PER_SOURCE = 500

_RESEARCH_QUERY_HINTS: tuple[tuple[str, str], ...] = (
    ("新能源材料", "renewable energy"),
    ("可再生能源材料", "renewable energy"),
    ("材料里的电池", "battery"),
    ("材料中的电池", "battery"),
    ("材料 电池", "battery"),
    ("电池材料", "battery"),
    ("储能材料", "energy storage"),
    ("催化材料", "catalyst"),
    ("高分子材料", "polymer"),
    ("聚合物材料", "polymer"),
    ("半导体材料", "semiconductor"),
    ("陶瓷材料", "ceramic"),
    ("光伏材料", "photovoltaic"),
    ("battery materials", "battery"),
    ("energy storage materials", "energy storage"),
    ("catalyst materials", "catalyst"),
    ("polymer materials", "polymer"),
    ("semiconductor materials", "semiconductor"),
    ("ceramic materials", "ceramic"),
    ("photovoltaic materials", "photovoltaic"),
)

_BROAD_MATERIAL_TOPICS = {"材料", "材料科学", "纳米材料", "materials", "material science", "materials science"}


def parse_paper(value: dict[str, Any] | Paper) -> Paper:
    if isinstance(value, Paper):
        return value
    if hasattr(Paper, "model_validate"):
        return Paper.model_validate(value)
    return Paper.parse_obj(value)


def paper_prompt(paper: Paper) -> str:
    authors = ", ".join(paper.authors[:10])
    categories = ", ".join(paper.categories or paper.concepts)
    fields = [
        f"Title: {paper.title}",
        f"Source: {paper.source}",
        f"Venue: {paper.venue or paper.journal or ''}",
        f"Date: {paper.published_at.isoformat() if paper.published_at else ''}",
        f"Authors: {authors}",
        f"DOI: {paper.doi or ''}",
        f"URL: {paper.url}",
        f"Categories: {categories}",
        f"Abstract: {paper.abstract}",
    ]
    return "\n".join(fields)


def _result(papers: list[Paper], llm_result: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "papers": [paper.to_dict() for paper in papers],
        "answer": llm_result.get("answer", ""),
        "model": llm_result.get("model"),
        "configured": bool(llm_result.get("configured")),
        "warnings": list(warnings or []) + list(llm_result.get("warnings") or []),
    }


def _host_context_result(
    *,
    action: str,
    messages: list[dict[str, str]],
    papers: list[Paper],
    retrieval: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "configured": True,
        "model_source": "agent_host",
        "paperlite_llm_used": False,
        "action": action,
        "messages": messages,
        "papers": [paper.to_dict() for paper in papers],
        "retrieval": retrieval or {},
        "result_contract": agent_result_policy(),
        "warnings": list(warnings or []),
    }


def _single_paper_context(
    *,
    action: str,
    paper: dict[str, Any] | Paper,
    question: str | None,
    query: str | None,
    target_language: str,
    style: str,
) -> dict[str, Any]:
    parsed = parse_paper(paper)
    metadata = paper_prompt(parsed)
    if action == "explain":
        messages = [
            {
                "role": "system",
                "content": "Explain research paper metadata using only the supplied metadata. Do not use PDFs, full text, or outside knowledge.",
            },
            {
                "role": "user",
                "content": (
                    f"Explain this paper in a {style} style. "
                    f"Question: {question or 'What is this paper about and why might it matter?'}\n\n"
                    f"{metadata}"
                ),
            },
        ]
    elif action == "filter":
        messages = [
            {
                "role": "system",
                "content": (
                    "Classify this paper metadata as recommend, maybe, or reject. "
                    "Return JSON with group, importance, reason, confidence, and noise_tags. "
                    "Use only supplied metadata."
                ),
            },
            {
                "role": "user",
                "content": f"Filter criteria: {query or 'prioritize clearly useful research papers for today'}\n\n{metadata}",
            },
        ]
    elif action == "translate":
        messages = [
            {
                "role": "system",
                "content": (
                    f"Translate research paper metadata into {target_language}. "
                    "Preserve technical terms when needed. Use only supplied metadata."
                ),
            },
            {
                "role": "user",
                "content": f"Style: {style}\n\n{metadata}",
            },
        ]
    else:
        raise ValueError("action must be explain, filter, translate, or ask")
    return _host_context_result(action=action, messages=messages, papers=[parsed])


def paper_agent_context(
    *,
    action: str,
    paper: dict[str, Any] | Paper | None = None,
    question: str | None = None,
    query: str | None = None,
    target_language: str = "zh-CN",
    style: str = "plain",
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 8,
    limit_per_source: int = 100,
    cache_path: str | None = None,
) -> dict[str, Any]:
    selected_action = str(action or "").strip().lower()
    if selected_action in {"explain", "filter", "translate"}:
        if paper is None:
            raise ValueError("paper is required for explain, filter, and translate context")
        return _single_paper_context(
            action=selected_action,
            paper=paper,
            question=question,
            query=query,
            target_language=target_language,
            style=style,
        )
    if selected_action != "ask":
        raise ValueError("action must be explain, filter, translate, or ask")
    clean_question = str(question or "").strip()
    if not clean_question:
        raise ValueError("question is required for ask context")
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_top_k = _bounded_int(top_k, default=8, minimum=1, maximum=20)
    selected_limit = _bounded_int(limit_per_source, default=100, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    selected_papers = papers[:selected_top_k]
    citations = [
        {
            "index": index,
            "score": None,
            "paper": _citation_paper(paper_item),
        }
        for index, paper_item in enumerate(selected_papers, start=1)
    ]
    retrieval = {
        "date_from": start,
        "date_to": end,
        "discipline": discipline,
        "source": source,
        "q": clean_q,
        "top_k": selected_top_k,
        "limit_per_source": selected_limit,
        "candidates": len(papers),
        "matches": len(citations),
        "semantic_search": False,
    }
    warnings: list[str] = ["agent_host_model_required", "agent_context_not_semantic_search"]
    if not citations:
        warnings.append("agent_context_empty")
    messages = [
        {
            "role": "system",
            "content": (
                "Answer using only the supplied PaperLite paper metadata. "
                "Do not use PDFs, full text, or outside knowledge. "
                "If the metadata is insufficient, say so. Cite claims with bracketed numbers like [1]."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {clean_question}\n\nPaperLite metadata evidence:\n\n{_evidence_block(citations)}",
        },
    ]
    return _host_context_result(
        action="ask",
        messages=messages,
        papers=selected_papers,
        retrieval=retrieval,
        warnings=warnings,
    )


def paper_explain(
    paper: dict[str, Any] | Paper,
    question: str | None = None,
    style: str = "plain",
) -> dict[str, Any]:
    parsed = parse_paper(paper)
    messages = [
        {
            "role": "system",
            "content": "You explain research papers in English using only the supplied metadata. Do not translate.",
        },
        {
            "role": "user",
            "content": (
                f"Explain this paper in a {style} style. "
                f"Question: {question or 'What is this paper about and why might it matter?'}\n\n"
                f"{paper_prompt(parsed)}"
            ),
        },
    ]
    return _result([parsed], complete_chat(messages))


def _date_scope(
    *,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, str]:
    days = daily_date_range(date_value=date_value, date_from=date_from, date_to=date_to)
    return days[0], days[-1]


def _bounded_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clean_query(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _scope_text(value: str | None) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").strip().lower().split())


def _compact_scope_text(value: str | None) -> str:
    return _scope_text(value).replace(" ", "")


def _resolve_research_discipline(topic: str | None, discipline: str | None) -> str:
    if discipline:
        key = taxonomy_key_for_discipline(discipline)
        if key != "unclassified":
            return key
    text = _scope_text(topic)
    compact_text = _compact_scope_text(topic)
    if not text and not compact_text:
        return "unclassified"
    aliases = sorted(load_taxonomy().discipline_aliases.items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in aliases:
        compact_alias = alias.replace(" ", "")
        if (alias and alias in text) or (compact_alias and compact_alias in compact_text):
            key = taxonomy_key_for_discipline(canonical)
            if key != "unclassified":
                return key
    return "unclassified"


def _derive_research_query(topic: str | None, q: str | None) -> str | None:
    explicit = _clean_query(q)
    if explicit:
        return explicit
    raw_topic = str(topic or "").strip()
    if raw_topic in _BROAD_MATERIAL_TOPICS or _scope_text(raw_topic) in _BROAD_MATERIAL_TOPICS:
        return None
    text = _scope_text(raw_topic)
    compact_text = _compact_scope_text(raw_topic)
    for phrase, query in _RESEARCH_QUERY_HINTS:
        clean_phrase = _scope_text(phrase)
        compact_phrase = _compact_scope_text(phrase)
        if clean_phrase in text or compact_phrase in compact_text:
            return query
    return None


def resolve_research_scope(
    *,
    topic: str | None = None,
    discipline: str | None = None,
    q: str | None = None,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    discipline_key = _resolve_research_discipline(topic, discipline)
    record = discipline_record(discipline_key)
    return {
        "topic": str(topic or "").strip() or None,
        "date_from": start,
        "date_to": end,
        "discipline": discipline_key if discipline_key != "unclassified" else None,
        "discipline_label": record["label"] if discipline_key != "unclassified" else None,
        "discipline_name": record["name"] if discipline_key != "unclassified" else None,
        "q": _derive_research_query(topic, q),
        "resolved": discipline_key != "unclassified",
    }


def _source_list(value: str | Iterable[str] | None) -> list[str]:
    if value is None or value == "":
        return []
    return split_keys(value)


def _research_source_selection(
    *,
    discipline: str,
    source: str | Iterable[str] | None,
    source_limit: int,
) -> dict[str, Any]:
    requested = _source_list(source)
    if requested:
        return {
            "source_keys": requested,
            "source_count": len(requested),
            "source_strategy": "requested",
            "truncated": False,
        }
    latest = [
        item
        for item in list_sources(discipline=discipline)
        if item.get("supports_latest") and str(item.get("status") or "active") == "active"
    ]
    core = [item for item in latest if item.get("core")]
    selected = core or latest
    limit = _bounded_int(source_limit, default=RESEARCH_SOURCE_LIMIT, minimum=1, maximum=50)
    keys = [str(item.get("name") or "") for item in selected[:limit] if item.get("name")]
    return {
        "source_keys": keys,
        "source_count": len(keys),
        "source_strategy": "active_core_latest" if core else "active_latest",
        "truncated": len(selected) > len(keys),
    }


def _papers_for_rag_scope(
    *,
    start: str,
    end: str,
    discipline: str | None,
    source: str | list[str] | None,
    limit_per_source: int,
    q: str | None,
    cache_path: str | None,
) -> list[Paper]:
    clean_q = _clean_query(q)
    if clean_q:
        return daily_cache_export_papers(
            date_from=start,
            date_to=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            limit_per_source=limit_per_source,
            path=cache_path,
        )
    return daily_cache_papers_for_rag(
        date_from=start,
        date_to=end,
        discipline_key=discipline,
        source_keys=source,
        limit_per_source=limit_per_source,
        path=cache_path,
    )


def _research_cache_papers(
    *,
    scope: dict[str, Any],
    source: str | Iterable[str] | None,
    limit_per_source: int,
    cache_path: str | None,
) -> list[Paper]:
    return daily_cache_export_papers(
        date_from=str(scope["date_from"]),
        date_to=str(scope["date_to"]),
        discipline=scope.get("discipline"),
        source=source,
        q=scope.get("q"),
        limit_per_source=limit_per_source,
        path=cache_path,
    )


def _research_crawl_warnings(run: dict[str, Any] | None) -> tuple[list[str], list[dict[str, Any]]]:
    if not run:
        return [], []
    warnings = [str(item) for item in run.get("warnings") or [] if item]
    source_warnings: list[dict[str, Any]] = []
    for item in run.get("source_results") or []:
        source_key = str(item.get("source_key") or "")
        error = str(item.get("error") or "").strip()
        item_warnings = [str(value) for value in item.get("warnings") or [] if value]
        if error or item_warnings:
            source_warnings.append(
                {
                    "source": source_key,
                    "endpoint": item.get("endpoint_key"),
                    "error": error or None,
                    "warnings": item_warnings,
                }
            )
            if error:
                warnings.append(f"{source_key}: {error}")
            warnings.extend(f"{source_key}: {warning}" for warning in item_warnings)
    return list(dict.fromkeys(warnings)), source_warnings


def _empty_research_brief_translation(
    *,
    requested: bool,
    target_language: str,
    translation_profile: str | None,
    status: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "requested": requested,
        "status": status,
        "target_language": target_language,
        "style": "brief",
        "translation_profile": translation_profile or "research_card_cn",
        "configured": False,
        "title_zh": "",
        "cn_flash_180": "",
        "card_headline": "",
        "card_bullets": [],
        "card_tags": [],
        "translation": "",
        "warnings": list(warnings or []),
        "cached": False,
    }


def _research_brief_translation(
    paper: Paper,
    *,
    enabled: bool,
    target_language: str,
    translation_profile: str | None,
    cache_path: str | None,
) -> dict[str, Any]:
    if not enabled:
        return _empty_research_brief_translation(
            requested=False,
            target_language=target_language,
            translation_profile=translation_profile,
            status="disabled",
        )
    try:
        from paperlite.translation import translate_paper

        result = translate_paper(
            paper,
            target_language=target_language,
            style="brief",
            translation_profile=translation_profile,
            cache_path=cache_path,
        )
    except (LLMRequestError, ValueError) as exc:
        return _empty_research_brief_translation(
            requested=True,
            target_language=target_language,
            translation_profile=translation_profile,
            status="error",
            warnings=[str(exc)],
        )

    brief = result.get("brief") if isinstance(result.get("brief"), dict) else {}
    title_zh = str(result.get("title_zh") or result.get("card_headline") or brief.get("card_headline") or "").strip()
    cn_flash = str(result.get("cn_flash_180") or brief.get("cn_flash_180") or "").strip()
    status = "ok" if title_zh or cn_flash else "empty"
    if not result.get("configured"):
        status = "unconfigured"
    return {
        "requested": True,
        "status": status,
        "target_language": result.get("target_language") or target_language,
        "style": result.get("style") or "brief",
        "translation_profile": result.get("translation_profile") or translation_profile or "research_card_cn",
        "translation_profile_version": result.get("translation_profile_version") or "",
        "translation_profile_hash": result.get("translation_profile_hash") or "",
        "configured": bool(result.get("configured")),
        "title_zh": title_zh,
        "cn_flash_180": cn_flash,
        "card_headline": str(result.get("card_headline") or brief.get("card_headline") or "").strip(),
        "card_bullets": list(result.get("card_bullets") or brief.get("card_bullets") or []),
        "card_tags": list(result.get("card_tags") or brief.get("card_tags") or []),
        "translation": str(result.get("translation") or "").strip(),
        "warnings": list(result.get("warnings") or []),
        "cached": bool(result.get("cached")),
        "abstract_missing": bool(result.get("abstract_missing")),
        "brief_skipped": bool(result.get("brief_skipped")),
    }


def _research_identifier(paper: Paper) -> dict[str, str]:
    if paper.doi:
        return {"identifier": paper.doi, "identifier_label": "DOI", "identifier_kind": "doi"}
    if paper.pmid:
        return {"identifier": paper.pmid, "identifier_label": "PMID", "identifier_kind": "pmid"}
    if paper.pmcid:
        return {"identifier": paper.pmcid, "identifier_label": "PMCID", "identifier_kind": "pmcid"}
    if paper.openalex_id:
        return {"identifier": paper.openalex_id, "identifier_label": "OpenAlex", "identifier_kind": "openalex"}
    paper_id = str(paper.id or "").strip()
    if paper_id.lower().startswith("arxiv:"):
        return {"identifier": paper_id.split(":", 1)[1], "identifier_label": "arXiv", "identifier_kind": "arxiv"}
    return {"identifier": paper_id, "identifier_label": "ID", "identifier_kind": "id"} if paper_id else {
        "identifier": "",
        "identifier_label": "",
        "identifier_kind": "",
    }


def _research_paper_item(
    paper: Paper,
    *,
    scope: dict[str, Any],
    display_names: dict[str, str],
    brief_translation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _citation_paper(paper)
    source_name = str(paper.source or "")
    venue = paper.venue or paper.journal or display_names.get(source_name) or source_name
    abstract = _clip(paper.abstract, limit=480)
    reason_bits = []
    if scope.get("discipline_label"):
        reason_bits.append(f"matches {scope['discipline_label']}")
    if scope.get("q"):
        reason_bits.append(f"matches query: {scope['q']}")
    reason = "; ".join(reason_bits) or "matches requested PaperLite scope"
    identifier = _research_identifier(paper)
    brief = brief_translation or _empty_research_brief_translation(
        requested=False,
        target_language="zh-CN",
        translation_profile=None,
        status="disabled",
    )
    title_zh = str(brief.get("title_zh") or brief.get("card_headline") or "").strip()
    cn_flash = str(brief.get("cn_flash_180") or "").strip()
    title_needs_host_translation = not bool(title_zh)
    title_instruction = (
        ""
        if title_zh
        else (
            "For Chinese brief answers, translate title_original into Chinese first, "
            "then include the original English title as a separate line; do not use "
            "the raw English title as the only item heading."
        )
    )
    if cn_flash:
        summary_or_point = cn_flash
    elif brief.get("requested") and not brief.get("configured"):
        summary_or_point = "中文 brief 未生成；请宿主 agent 基于标题和摘要给出一句中文说明。"
    else:
        summary_or_point = abstract or "摘要未提供；请宿主 agent 基于标题、期刊/来源和分类给出一句元数据要点。"
    return {
        "paper": payload,
        "paper_id": paper.id,
        **identifier,
        "title": paper.title,
        "title_original": paper.title,
        "title_en": paper.title,
        "title_zh": title_zh,
        "display_title": title_zh,
        "brief_title_format": "中文题目 + English title",
        "title_needs_host_translation": title_needs_host_translation,
        "title_display_instruction": title_instruction,
        "source": source_name,
        "source_display": display_names.get(source_name) or source_name,
        "venue": venue,
        "date": paper.published_at.date().isoformat() if paper.published_at else None,
        "url": paper.url,
        "doi": paper.doi,
        "reason": reason,
        "short_title_zh": title_zh,
        "summary_or_point": summary_or_point,
        "brief_translation": brief,
        "abstract_available": bool(abstract),
    }


def _research_next_actions(*, total: int, limit: int, scope: dict[str, Any], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if total > limit:
        actions.append("Ask whether to use the host model to rank/select highlights from the returned scope.")
        actions.append("Ask for an extra keyword to narrow the current scope before listing more papers.")
    if not total:
        actions.append("Check crawl warnings and consider widening the date range or choosing a source.")
    if warnings:
        actions.append("Mention crawl/source warnings instead of presenting the result as complete.")
    if not scope.get("q"):
        actions.append("If the user wants a subtopic, ask for a keyword such as battery, catalyst, polymer, or imaging.")
    return actions


def paper_research(
    *,
    topic: str | None = None,
    discipline: str | None = None,
    q: str | None = None,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source: str | Iterable[str] | None = None,
    limit: int = RESEARCH_DEFAULT_LIMIT,
    crawl_if_missing: bool = True,
    source_limit: int = RESEARCH_SOURCE_LIMIT,
    limit_per_source: int = RESEARCH_DEFAULT_LIMIT,
    translate_brief: bool = True,
    target_language: str = "zh-CN",
    translation_profile: str | None = None,
    cache_path: str | None = None,
) -> dict[str, Any]:
    scope = resolve_research_scope(
        topic=topic,
        discipline=discipline,
        q=q,
        date_value=date_value,
        date_from=date_from,
        date_to=date_to,
    )
    selected_limit = _bounded_int(limit, default=RESEARCH_DEFAULT_LIMIT, minimum=1, maximum=RESEARCH_MAX_LIMIT)
    selected_crawl_limit = _bounded_int(limit_per_source, default=RESEARCH_DEFAULT_LIMIT, minimum=1, maximum=500)
    if not scope["resolved"]:
        return {
            "status": "error",
            "error": "research_scope_unresolved",
            "scope": scope,
            "papers": [],
            "total_count": 0,
            "returned_count": 0,
            "warnings": ["research_scope_unresolved"],
            "next_actions": ["Ask the user for a PaperLite discipline or call paper_sources to inspect available disciplines."],
            "result_contract": agent_result_policy(),
        }

    read_limit = max(RESEARCH_CACHE_LIMIT_PER_SOURCE, selected_limit)
    before = _research_cache_papers(
        scope=scope,
        source=source,
        limit_per_source=read_limit,
        cache_path=cache_path,
    )
    crawl_triggered = False
    crawl_error: str | None = None
    crawl_run: dict[str, Any] | None = None
    selected_sources: dict[str, Any] = {
        "source_keys": _source_list(source),
        "source_count": len(_source_list(source)),
        "source_strategy": "requested" if source else "not_selected",
        "truncated": False,
    }
    warnings: list[str] = []
    source_warnings: list[dict[str, Any]] = []
    if not before and crawl_if_missing:
        selected_sources = _research_source_selection(
            discipline=str(scope["discipline"]),
            source=source,
            source_limit=source_limit,
        )
        if selected_sources["source_keys"]:
            crawl_triggered = True
            try:
                run = create_daily_crawl(
                    date_from=str(scope["date_from"]),
                    date_to=str(scope["date_to"]),
                    discipline=str(scope["discipline"]),
                    source=selected_sources["source_keys"],
                    limit_per_source=selected_crawl_limit,
                    db_path=cache_path,
                )
                if not run.get("reused") and run.get("status") == "queued":
                    run_daily_crawl(str(run["run_id"]), db_path=cache_path)
                crawl_run = get_crawl_run(str(run["run_id"]), path=cache_path) or run
            except ValueError as exc:
                crawl_error = str(exc)
                warnings.append(crawl_error)
        else:
            warnings.append("no_latest_capable_sources_found")

    after = _research_cache_papers(
        scope=scope,
        source=source,
        limit_per_source=read_limit,
        cache_path=cache_path,
    )
    crawl_warnings, source_warnings = _research_crawl_warnings(crawl_run)
    warnings.extend(crawl_warnings)
    if crawl_error:
        warnings.append(crawl_error)
    if not after:
        warnings.append("research_no_cached_papers")
    display_names = {
        str(item.get("name") or ""): str(item.get("display_name") or item.get("name") or "")
        for item in list_sources()
    }
    selected_papers = after[:selected_limit]
    brief_translations = [
        _research_brief_translation(
            paper,
            enabled=translate_brief,
            target_language=target_language,
            translation_profile=translation_profile,
            cache_path=cache_path,
        )
        for paper in selected_papers
    ]
    translation_warnings = list(
        dict.fromkeys(
            str(warning)
            for item in brief_translations
            for warning in item.get("warnings", [])
            if warning
        )
    )
    remaining = max(0, len(after) - len(selected_papers))
    unique_warnings = list(dict.fromkeys(warnings))
    return {
        "status": "ok",
        "topic": scope.get("topic"),
        "scope": scope,
        "cache": {
            "before_count": len(before),
            "after_count": len(after),
            "used_existing": bool(before),
        },
        "crawl": {
            "triggered": crawl_triggered,
            "run": crawl_run,
            "error": crawl_error,
            "source_keys": selected_sources["source_keys"],
            "source_count": selected_sources["source_count"],
            "source_strategy": selected_sources["source_strategy"],
            "sources_truncated": selected_sources["truncated"],
            "source_warnings": source_warnings,
            "warnings": crawl_warnings,
        },
        "total_count": len(after),
        "returned_count": len(selected_papers),
        "remaining_count": remaining,
        "overflow": {
            "limit": selected_limit,
            "has_more": remaining > 0,
            "message": (
                f"Returned the first {selected_limit} papers; {remaining} more match. "
                "Ask whether to AI-rank highlights or add keywords before returning more."
                if remaining
                else "Returned all matching papers."
            ),
        },
        "papers": [
            _research_paper_item(
                paper,
                scope=scope,
                display_names=display_names,
                brief_translation=brief_translation,
            )
            for paper, brief_translation in zip(selected_papers, brief_translations)
        ],
        "translation": {
            "brief_requested": translate_brief,
            "target_language": target_language,
            "translation_profile": translation_profile or "research_card_cn",
            "attempted_count": len(brief_translations) if translate_brief else 0,
            "translated_count": sum(
                1
                for item in brief_translations
                if item.get("title_zh") or item.get("cn_flash_180")
            ),
            "configured_count": sum(1 for item in brief_translations if item.get("configured")),
            "warnings": translation_warnings,
        },
        "result_contract": {
            **agent_result_policy(),
            "host_agent_rendering": (
                "Use each paper.brief_translation.title_zh and cn_flash_180 first when present. "
                "For Chinese brief answers, include both titles: show the Chinese title first, then the "
                "original English title from paper.title_original/title_en. If paper.display_title/title_zh "
                "is missing, translate paper.title_original with the host model before displaying. Do not "
                "display raw English paper.title as the only item heading. If brief translation is unconfigured "
                "or empty, use the host model to provide one concise Chinese point from the paper metadata; "
                "say '摘要未提供' when abstracts are missing."
            ),
        },
        "warnings": unique_warnings,
        "next_actions": _research_next_actions(
            total=len(after),
            limit=selected_limit,
            scope=scope,
            warnings=unique_warnings,
        ),
    }


def _search_cached_embeddings(
    *,
    papers: list[Paper],
    query_embedding: list[float],
    embedding_model: str,
    top_k: int,
    cache_path: str | None,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    indexed = 0
    stale = 0
    for paper in papers:
        existing = get_paper_embedding(paper.id, path=cache_path)
        if not existing or existing.get("embedding_model") != embedding_model:
            continue
        indexed += 1
        if existing.get("content_hash") != paper_embedding_hash(paper):
            stale += 1
            continue
        scored.append(
            {
                "paper": paper,
                "score": _cosine_similarity(query_embedding, list(existing.get("embedding") or [])),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {
        "candidates": len(papers),
        "indexed": indexed,
        "stale": stale,
        "matches": scored[: max(1, int(top_k))],
    }


def _citation_paper(paper: Paper) -> dict[str, Any]:
    payload = paper.to_dict()
    return {
        key: payload.get(key)
        for key in [
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
            "journal",
            "venue",
            "publisher",
            "pmid",
            "pmcid",
            "openalex_id",
            "citation_count",
            "concepts",
        ]
        if payload.get(key) not in (None, "", [], {})
    }


def _clip(value: str, limit: int = 1600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _evidence_block(citations: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for citation in citations:
        paper = citation["paper"]
        authors = ", ".join(paper.get("authors") or [])
        categories = ", ".join(paper.get("categories") or paper.get("concepts") or [])
        fields = [
            f"[{citation['index']}]",
            f"Title: {paper.get('title') or ''}",
            f"Source: {paper.get('source') or ''}",
            f"Venue: {paper.get('venue') or paper.get('journal') or ''}",
            f"Date: {paper.get('published_at') or ''}",
            f"Authors: {authors}",
            f"DOI: {paper.get('doi') or ''}",
            f"URL: {paper.get('url') or ''}",
            f"Categories: {categories}",
            f"Abstract: {_clip(str(paper.get('abstract') or ''))}",
        ]
        blocks.append("\n".join(fields))
    return "\n\n".join(blocks)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _embedding_current(
    paper: Paper,
    *,
    embedding_model: str | None,
    cache_path: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    content_hash = paper_embedding_hash(paper)
    existing = get_paper_embedding(paper.id, path=cache_path)
    if (
        existing
        and existing.get("content_hash") == content_hash
        and existing.get("embedding_model") == embedding_model
        and existing.get("embedding")
    ):
        return existing, content_hash
    return None, content_hash


def _base_related_response(
    *,
    configured: bool,
    paper_id: str,
    embedding_model: str | None,
    start: str,
    end: str,
    discipline: str | None,
    source: str | list[str] | None,
    q: str | None,
    top_k: int,
    limit_per_source: int,
    candidates: int = 0,
    indexed: int = 0,
    refreshed: int = 0,
    stale: int = 0,
    matches: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "paper_id": paper_id,
        "embedding_model": embedding_model,
        "related": [],
        "retrieval": {
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": q,
            "top_k": top_k,
            "limit_per_source": limit_per_source,
            "candidates": candidates,
            "indexed": indexed,
            "refreshed": refreshed,
            "stale": stale,
            "matches": matches,
        },
        "warnings": list(warnings or []),
    }


def paper_related(
    *,
    paper_id: str,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 5,
    limit_per_source: int = 500,
    cache_path: str | None = None,
) -> dict[str, Any]:
    clean_paper_id = str(paper_id or "").strip()
    if not clean_paper_id:
        raise ValueError("paper_id is required")
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_top_k = _bounded_int(top_k, default=5, minimum=1, maximum=20)
    selected_limit = _bounded_int(limit_per_source, default=500, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    settings = embedding_status()
    settings_model = str(settings.get("model") or "")
    target = next((paper for paper in papers if paper.id == clean_paper_id), None)
    if target is None:
        return _base_related_response(
            configured=bool(settings.get("configured")),
            paper_id=clean_paper_id,
            embedding_model=settings.get("model"),
            start=start,
            end=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            top_k=selected_top_k,
            limit_per_source=selected_limit,
            candidates=len(papers),
            warnings=["related_target_not_in_cache_scope"],
        )
    if not settings.get("configured"):
        return _base_related_response(
            configured=False,
            paper_id=clean_paper_id,
            embedding_model=settings.get("model"),
            start=start,
            end=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            top_k=selected_top_k,
            limit_per_source=selected_limit,
            candidates=len(papers),
            warnings=["embedding_not_configured"],
        )

    pending: list[tuple[Paper, str, str]] = []
    skipped = 0
    stale = 0
    for paper in papers:
        existing, content_hash = _embedding_current(paper, embedding_model=settings_model, cache_path=cache_path)
        if existing is not None:
            skipped += 1
            continue
        if get_paper_embedding(paper.id, path=cache_path):
            stale += 1
        pending.append((paper, content_hash, paper_embedding_text(paper)))

    embedding_model = settings_model
    embedding_warnings: list[str] = []
    refreshed = 0
    if pending:
        embedding_result = create_embeddings([item[2] for item in pending])
        if not embedding_result.get("configured"):
            return _base_related_response(
                configured=False,
                paper_id=clean_paper_id,
                embedding_model=embedding_result.get("model"),
                start=start,
                end=end,
                discipline=discipline,
                source=source,
                q=clean_q,
                top_k=selected_top_k,
                limit_per_source=selected_limit,
                candidates=len(papers),
                indexed=skipped,
                stale=stale,
                warnings=list(embedding_result.get("warnings") or []),
            )
        embedding_model = str(embedding_result.get("model") or embedding_model)
        embedding_warnings = list(embedding_result.get("warnings") or [])
        for (paper, content_hash, _text), embedding in zip(pending, embedding_result.get("embeddings") or []):
            upsert_paper_embedding(
                paper_id=paper.id,
                content_hash=content_hash,
                embedding_model=embedding_model,
                embedding=embedding,
                path=cache_path,
            )
            refreshed += 1

    vectors: dict[str, list[float]] = {}
    for paper in papers:
        existing, _content_hash = _embedding_current(paper, embedding_model=embedding_model, cache_path=cache_path)
        if existing is not None:
            vectors[paper.id] = list(existing.get("embedding") or [])
    target_vector = vectors.get(clean_paper_id)
    if not target_vector:
        return _base_related_response(
            configured=True,
            paper_id=clean_paper_id,
            embedding_model=embedding_model,
            start=start,
            end=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            top_k=selected_top_k,
            limit_per_source=selected_limit,
            candidates=len(papers),
            indexed=len(vectors),
            refreshed=refreshed,
            stale=stale,
            warnings=embedding_warnings + ["related_target_embedding_missing"],
        )

    scored: list[dict[str, Any]] = []
    for paper in papers:
        if paper.id == clean_paper_id:
            continue
        vector = vectors.get(paper.id)
        if not vector:
            continue
        scored.append(
            {
                "score": _cosine_similarity(target_vector, vector),
                "paper": _citation_paper(paper),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    related = [
        {
            "index": index,
            "score": item["score"],
            "paper": item["paper"],
        }
        for index, item in enumerate(scored[:selected_top_k], start=1)
    ]
    warnings = embedding_warnings[:]
    if len(papers) <= 1:
        warnings.append("related_no_candidate_papers")
    elif not related:
        warnings.append("related_no_matches")
    return {
        "configured": True,
        "paper_id": clean_paper_id,
        "embedding_model": embedding_model,
        "related": related,
        "retrieval": {
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": clean_q,
            "top_k": selected_top_k,
            "limit_per_source": selected_limit,
            "candidates": len(papers),
            "indexed": len(vectors),
            "refreshed": refreshed,
            "stale": stale,
            "matches": len(related),
        },
        "warnings": warnings,
    }


def paper_rag_index(
    *,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    limit_per_source: int = 100,
    cache_path: str | None = None,
) -> dict[str, Any]:
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_limit = _bounded_int(limit_per_source, default=100, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    settings = embedding_status()
    pending: list[tuple[Paper, str, str]] = []
    skipped = 0
    for paper in papers:
        content_hash = paper_embedding_hash(paper)
        existing = get_paper_embedding(paper.id, path=cache_path)
        if (
            existing
            and existing.get("content_hash") == content_hash
            and existing.get("embedding_model") == settings.get("model")
        ):
            skipped += 1
            continue
        pending.append((paper, content_hash, paper_embedding_text(paper)))

    if not pending:
        return {
            "configured": bool(settings.get("configured")),
            "embedding_model": settings.get("model"),
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": clean_q,
            "limit_per_source": selected_limit,
            "candidates": len(papers),
            "indexed": 0,
            "skipped": skipped,
            "warnings": [] if settings.get("configured") else ["embedding_not_configured"],
        }

    embedding_result = create_embeddings([item[2] for item in pending])
    if not embedding_result.get("configured"):
        return {
            "configured": False,
            "embedding_model": embedding_result.get("model"),
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": clean_q,
            "limit_per_source": selected_limit,
            "candidates": len(papers),
            "indexed": 0,
            "skipped": skipped,
            "warnings": list(embedding_result.get("warnings") or []),
        }

    embedding_model = str(embedding_result.get("model") or "")
    indexed = 0
    for (paper, content_hash, _text), embedding in zip(pending, embedding_result.get("embeddings") or []):
        upsert_paper_embedding(
            paper_id=paper.id,
            content_hash=content_hash,
            embedding_model=embedding_model,
            embedding=embedding,
            path=cache_path,
        )
        indexed += 1
    return {
        "configured": True,
        "embedding_model": embedding_model,
        "date_from": start,
        "date_to": end,
        "discipline": discipline,
        "source": source,
        "q": clean_q,
        "limit_per_source": selected_limit,
        "candidates": len(papers),
        "indexed": indexed,
        "skipped": skipped,
        "warnings": list(embedding_result.get("warnings") or []),
    }


def paper_ask(
    *,
    question: str,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 8,
    limit_per_source: int = 100,
    cache_path: str | None = None,
) -> dict[str, Any]:
    clean_question = str(question or "").strip()
    if not clean_question:
        raise ValueError("question is required")
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_top_k = _bounded_int(top_k, default=8, minimum=1, maximum=20)
    selected_limit = _bounded_int(limit_per_source, default=100, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    embedding_result = create_embeddings([clean_question])
    base_retrieval = {
        "date_from": start,
        "date_to": end,
        "discipline": discipline,
        "source": source,
        "q": clean_q,
        "top_k": selected_top_k,
        "limit_per_source": selected_limit,
        "candidates": 0,
        "indexed": 0,
        "stale": 0,
        "matches": 0,
    }
    if not embedding_result.get("configured"):
        return {
            "configured": False,
            "answer": "",
            "model": None,
            "embedding_model": embedding_result.get("model"),
            "citations": [],
            "retrieval": base_retrieval,
            "warnings": list(embedding_result.get("warnings") or []),
        }

    query_embedding = (embedding_result.get("embeddings") or [[]])[0]
    embedding_model = str(embedding_result.get("model") or "")
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    search = _search_cached_embeddings(
        papers=papers,
        query_embedding=query_embedding,
        embedding_model=embedding_model,
        top_k=selected_top_k,
        cache_path=cache_path,
    )
    citations = [
        {
            "index": index,
            "score": item["score"],
            "paper": _citation_paper(item["paper"]),
        }
        for index, item in enumerate(search.get("matches") or [], start=1)
    ]
    retrieval = {
        **base_retrieval,
        "candidates": search.get("candidates", 0),
        "indexed": search.get("indexed", 0),
        "stale": search.get("stale", 0),
        "matches": len(citations),
    }
    warnings = list(embedding_result.get("warnings") or [])
    if search.get("stale"):
        warnings.append("rag_index_stale_entries_skipped")
    if not citations:
        warnings.append("rag_index_empty_or_no_matches")
        return {
            "configured": True,
            "answer": "",
            "model": None,
            "embedding_model": embedding_model,
            "citations": [],
            "retrieval": retrieval,
            "warnings": warnings,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You answer research questions using only the supplied PaperLite paper metadata. "
                "Do not use outside knowledge. Do not infer from PDFs or full text. "
                "If the supplied metadata is insufficient, say so. "
                "Cite concrete claims with bracketed citation numbers like [1]."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {clean_question}\n\n"
                "PaperLite metadata evidence:\n\n"
                f"{_evidence_block(citations)}"
            ),
        },
    ]
    llm_result = complete_chat(messages, temperature=0.1, max_tokens=1600)
    return {
        "configured": bool(llm_result.get("configured")),
        "answer": llm_result.get("answer", ""),
        "model": llm_result.get("model"),
        "embedding_model": embedding_model,
        "citations": citations,
        "retrieval": retrieval,
        "warnings": warnings + list(llm_result.get("warnings") or []),
    }
