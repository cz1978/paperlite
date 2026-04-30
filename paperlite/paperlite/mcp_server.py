from __future__ import annotations

from typing import Any

from paperlite.agent import paper_agent_context as run_paper_agent_context
from paperlite.agent import paper_ask as run_paper_ask
from paperlite.agent import paper_explain as run_paper_explain
from paperlite.agent import paper_rag_index as run_paper_rag_index
from paperlite.ai_filter import DEFAULT_AI_FILTER_QUERY, filter_paper as run_filter_paper
from paperlite.core import enrich_paper
from paperlite.integrations import agent_manifest
from paperlite.models import Paper
from paperlite.registry import list_sources
from paperlite.storage import get_relevant_preference_profile, record_preference_query
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


def paper_sources() -> list[dict]:
    return list_sources()


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
    limit_per_source: int = 100,
) -> dict[str, Any]:
    return run_paper_rag_index(
        date_value=date,
        date_from=date_from,
        date_to=date_to,
        discipline=discipline,
        source=source,
        limit_per_source=limit_per_source,
    )


def paper_ask(
    question: str,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
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
    mcp.tool(name="paper_explain")(paper_explain)
    mcp.tool(name="paper_agent_context")(paper_agent_context)
    mcp.tool(name="paper_translate")(paper_translate)
    mcp.tool(name="paper_translation_profiles")(paper_translation_profiles)
    mcp.tool(name="paper_filter")(paper_filter)
    mcp.tool(name="paper_ask")(paper_ask)
    mcp.tool(name="paper_rag_index")(paper_rag_index)
    mcp.tool(name="paper_zotero_status")(paper_zotero_status)
    mcp.tool(name="paper_zotero_items")(paper_zotero_items)
    mcp.tool(name="paper_agent_manifest")(paper_agent_manifest)
    return mcp


def run() -> None:
    build_mcp().run()


if __name__ == "__main__":
    run()
