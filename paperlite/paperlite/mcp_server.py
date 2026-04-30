from __future__ import annotations

from typing import Any

from paperlite.agent import paper_agent_context as run_paper_agent_context
from paperlite.agent import paper_ask as run_paper_ask
from paperlite.agent import paper_explain as run_paper_explain
from paperlite.agent import paper_rag_index as run_paper_rag_index
from paperlite.agent import paper_research as run_paper_research
from paperlite.ai_filter import DEFAULT_AI_FILTER_QUERY, filter_paper as run_filter_paper
from paperlite.core import enrich_paper
from paperlite.core import export as export_paper_metadata
from paperlite.daily_crawl import create_daily_crawl as run_create_daily_crawl
from paperlite.daily_crawl import run_daily_crawl
from paperlite.daily_export import daily_cache_export_papers, daily_cache_payload, daily_date_range
from paperlite.integrations import agent_manifest
from paperlite.models import Paper
from paperlite.registry import list_sources
from paperlite.storage import get_crawl_run, get_relevant_preference_profile, record_preference_query
from paperlite.translation import translate_paper as run_translate_paper
from paperlite.translation_profiles import list_translation_profiles as run_list_translation_profiles
from paperlite.zotero import (
    ZoteroNotConfiguredError,
    ZoteroRequestError,
    create_zotero_items as run_create_zotero_items,
    zotero_status as run_zotero_status,
)


def paper_enrich(paper: dict, sources: str | None = None) -> dict:
    parsed = Paper.model_validate(paper) if hasattr(Paper, "model_validate") else Paper.parse_obj(paper)
    return enrich_paper(parsed, sources).to_dict()


def _matches_text(item: dict[str, Any], query: str | None) -> bool:
    q = str(query or "").strip().lower()
    if not q:
        return True
    haystack = " ".join(
        str(value)
        for value in [
            item.get("name"),
            item.get("display_name"),
            item.get("source_type"),
            item.get("source_kind_label"),
            item.get("primary_area_label"),
            item.get("primary_discipline_label"),
            *(item.get("discipline_keys") or []),
            *(item.get("canonical_disciplines") or []),
            *(item.get("topics") or []),
        ]
        if value
    ).lower()
    return q in haystack


def _bounded_limit(value: int | str | None, *, default: int = 50, maximum: int = 500) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, parsed))


def _as_bool(value: bool | str | None, *, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def paper_sources(
    discipline: str | None = None,
    area: str | None = None,
    kind: str | None = None,
    core: bool | str | None = None,
    health: str | None = None,
    latest: bool | str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    items = [
        item
        for item in list_sources(discipline=discipline, area=area, kind=kind, core=core, health=health)
        if _matches_text(item, q)
    ]
    if latest not in (None, ""):
        wanted_latest = _as_bool(latest)
        items = [item for item in items if bool(item.get("supports_latest")) is wanted_latest]
    selected_limit = _bounded_limit(limit)
    return {
        "count": len(items),
        "returned": min(len(items), selected_limit),
        "truncated": len(items) > selected_limit,
        "sources": items[:selected_limit],
        "filters": {
            "discipline": discipline,
            "area": area,
            "kind": kind,
            "core": core,
            "health": health,
            "latest": latest,
            "q": q,
            "limit": selected_limit,
        },
    }


def paper_crawl(
    discipline: str,
    source: str | list[str] | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit_per_source: int = 20,
    run_now: bool | str = True,
) -> dict[str, Any]:
    try:
        days = daily_date_range(date_value=date, date_from=date_from, date_to=date_to)
        run = run_create_daily_crawl(
            date_from=days[0],
            date_to=days[-1],
            discipline=discipline,
            source=source,
            limit_per_source=_bounded_limit(limit_per_source, default=20),
        )
    except ValueError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "discipline": discipline,
            "source": source,
        }
    if _as_bool(run_now) and not run.get("reused") and run.get("status") == "queued":
        run_daily_crawl(str(run["run_id"]))
        return get_crawl_run(str(run["run_id"])) or run
    return run


def paper_crawl_status(run_id: str) -> dict[str, Any]:
    run = get_crawl_run(str(run_id or "").strip())
    if run is None:
        return {"found": False, "run_id": run_id, "error": "crawl run not found"}
    return {"found": True, **run}


def paper_cache(
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    limit_per_source: int = 50,
) -> dict[str, Any]:
    try:
        days = daily_date_range(date_value=date, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "date": date,
            "date_from": date_from,
            "date_to": date_to,
        }
    selected_limit = _bounded_limit(limit_per_source)
    if q:
        papers = daily_cache_export_papers(
            date_from=days[0],
            date_to=days[-1],
            discipline=discipline,
            source=source,
            q=q,
            limit_per_source=selected_limit,
        )
        return {
            "date_from": days[0],
            "date_to": days[-1],
            "discipline": discipline,
            "source": source,
            "q": q,
            "limit_per_source": selected_limit,
            "count": len(papers),
            "papers": [paper.to_dict() for paper in papers],
        }
    return daily_cache_payload(
        date_from=days[0],
        date_to=days[-1],
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
    )


def paper_explain(
    paper: dict,
    question: str | None = None,
    style: str = "plain",
) -> dict[str, Any]:
    return run_paper_explain(paper=paper, question=question, style=style)


def paper_translate(
    paper: dict,
    target_language: str = "zh-CN",
    style: str | None = None,
    translation_profile: str | None = None,
) -> dict[str, Any]:
    return run_translate_paper(
        paper=paper,
        target_language=target_language,
        style=style,
        translation_profile=translation_profile,
    )


def paper_translation_profiles() -> dict[str, Any]:
    profiles = run_list_translation_profiles()
    return {"count": len(profiles), "profiles": profiles}


def paper_agent_context(
    action: str,
    paper: dict | None = None,
    question: str | None = None,
    query: str | None = None,
    target_language: str = "zh-CN",
    style: str = "plain",
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 8,
    limit_per_source: int = 100,
) -> dict[str, Any]:
    return run_paper_agent_context(
        action=action,
        paper=paper,
        question=question,
        query=query,
        target_language=target_language,
        style=style,
        date_value=date,
        date_from=date_from,
        date_to=date_to,
        discipline=discipline,
        source=source,
        q=q,
        top_k=top_k,
        limit_per_source=limit_per_source,
    )


def paper_research(
    topic: str | None = None,
    discipline: str | None = None,
    q: str | None = None,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source: str | list[str] | None = None,
    limit: int = 15,
    crawl_if_missing: bool | str = True,
    source_limit: int = 15,
    limit_per_source: int = 15,
    translate_brief: bool | str = True,
    target_language: str = "zh-CN",
    translation_profile: str | None = None,
) -> dict[str, Any]:
    return run_paper_research(
        topic=topic,
        discipline=discipline,
        q=q,
        date_value=date,
        date_from=date_from,
        date_to=date_to,
        source=source,
        limit=_bounded_limit(limit, default=15, maximum=50),
        crawl_if_missing=_as_bool(crawl_if_missing),
        source_limit=_bounded_limit(source_limit, default=15, maximum=50),
        limit_per_source=_bounded_limit(limit_per_source, default=15, maximum=500),
        translate_brief=_as_bool(translate_brief),
        target_language=target_language,
        translation_profile=translation_profile,
    )


def paper_filter(
    paper: dict,
    query: str | None = None,
    use_profile: bool = True,
) -> dict[str, Any]:
    raw_query = str(query or "").strip()
    selected_query = raw_query or DEFAULT_AI_FILTER_QUERY
    if use_profile and raw_query:
        record_preference_query(text=raw_query, source="mcp_filter")
    preference_profile = get_relevant_preference_profile(query=selected_query, paper=paper) if use_profile else None
    return run_filter_paper(
        paper=paper,
        query=selected_query,
        preference_profile=preference_profile,
        use_profile=use_profile,
    )


def paper_rag_index(
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    limit_per_source: int = 100,
) -> dict[str, Any]:
    return run_paper_rag_index(
        date_value=date,
        date_from=date_from,
        date_to=date_to,
        discipline=discipline,
        source=source,
        q=q,
        limit_per_source=limit_per_source,
    )


def paper_ask(
    question: str,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 8,
    limit_per_source: int = 100,
) -> dict[str, Any]:
    return run_paper_ask(
        question=question,
        date_value=date,
        date_from=date_from,
        date_to=date_to,
        discipline=discipline,
        source=source,
        q=q,
        top_k=top_k,
        limit_per_source=limit_per_source,
    )


def paper_zotero_status() -> dict[str, Any]:
    return run_zotero_status()


def paper_zotero_items(items: list[dict]) -> dict[str, Any]:
    papers = [Paper.model_validate(item) if hasattr(Paper, "model_validate") else Paper.parse_obj(item) for item in items]
    try:
        return run_create_zotero_items(papers)
    except ZoteroNotConfiguredError as exc:
        return {
            "configured": False,
            "submitted": len(papers),
            "created": [],
            "failed": [],
            "error": str(exc),
            "fallback": "export RIS or BibTeX with /zotero/export",
        }
    except ZoteroRequestError as exc:
        return {
            "configured": True,
            "submitted": len(papers),
            "created": [],
            "failed": [{"error": str(exc)}],
            "error": str(exc),
        }


def paper_zotero_export(items: list[dict], format: str = "ris") -> dict[str, Any]:
    fmt = str(format or "ris").strip().lower()
    if fmt not in {"ris", "bib", "bibtex"}:
        return {"status": "error", "error": "format must be ris or bibtex"}
    papers = [Paper.model_validate(item) if hasattr(Paper, "model_validate") else Paper.parse_obj(item) for item in items]
    extension = "bib" if fmt in {"bib", "bibtex"} else "ris"
    return {
        "status": "ok",
        "format": "bibtex" if extension == "bib" else "ris",
        "extension": extension,
        "filename": f"paperlite-zotero.{extension}",
        "count": len(papers),
        "content": export_paper_metadata(papers, format=fmt),
    }



def paper_agent_manifest(base_url: str = "http://127.0.0.1:8765") -> dict[str, Any]:
    return agent_manifest(base_url)


def build_mcp():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError("Install paperlite with the MCP extra: pip install -e '.[mcp]'") from exc

    mcp = FastMCP("paperlite")
    mcp.tool(name="paper_enrich")(paper_enrich)
    mcp.tool(name="paper_sources")(paper_sources)
    mcp.tool(name="paper_crawl")(paper_crawl)
    mcp.tool(name="paper_crawl_status")(paper_crawl_status)
    mcp.tool(name="paper_cache")(paper_cache)
    mcp.tool(name="paper_explain")(paper_explain)
    mcp.tool(name="paper_agent_context")(paper_agent_context)
    mcp.tool(name="paper_research")(paper_research)
    mcp.tool(name="paper_translate")(paper_translate)
    mcp.tool(name="paper_translation_profiles")(paper_translation_profiles)
    mcp.tool(name="paper_filter")(paper_filter)
    mcp.tool(name="paper_ask")(paper_ask)
    mcp.tool(name="paper_rag_index")(paper_rag_index)
    mcp.tool(name="paper_zotero_status")(paper_zotero_status)
    mcp.tool(name="paper_zotero_items")(paper_zotero_items)
    mcp.tool(name="paper_zotero_export")(paper_zotero_export)
    mcp.tool(name="paper_agent_manifest")(paper_agent_manifest)
    return mcp


def run() -> None:
    build_mcp().run()


if __name__ == "__main__":
    run()
