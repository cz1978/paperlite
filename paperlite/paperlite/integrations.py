from __future__ import annotations

from typing import Any

from paperlite.llm import embedding_status, llm_status


def agent_result_policy() -> dict[str, Any]:
    return {
        "prompt_priority": "User prompt overrides defaults.",
        "default": (
            "Return the actual paper list first, then summaries, selected highlights, "
            "and source/run status directly from MCP tools or JSON endpoints."
        ),
        "list_all_until": 15,
        "overflow_policy": (
            "If more than 15 papers match, list at most 15 in the chat response, "
            "state the remaining count, and ask whether to AI-rank/optimize the "
            "set or add more search keywords to narrow it."
        ),
        "scope_fields": [
            "discipline",
            "source_key_or_name",
            "date_range",
            "query",
            "run_id",
            "run_status",
            "warnings",
            "total_count",
        ],
        "paper_fields": [
            "title",
            "source_or_venue",
            "date",
            "doi_or_url",
            "match_reason",
            "brief_translation",
            "brief_abstract_or_summary",
        ],
        "brief_translation_default": (
            "When responding in Chinese and the user did not ask otherwise, include "
            "a brief Chinese title translation and one-sentence Chinese "
            "abstract/summary for every listed paper. If metadata has no abstract, "
            "say it is unavailable and provide a title/metadata-based note."
        ),
        "transport_policy": (
            "Prefer MCP tools. Use REST JSON endpoints such as /daily/crawl only "
            "when MCP is unavailable; they are API endpoints, not the /daily "
            "browser frontend."
        ),
        "do_not": (
            "Do not replace the paper list with highlights, and do not use /daily "
            "as the completion link unless the user explicitly asks for the human "
            "interface."
        ),
    }


def agent_manifest(base_url: str = "http://127.0.0.1:8765") -> dict[str, Any]:
    root = base_url.rstrip("/")
    rest = {
        "daily": f"{root}/daily",
        "daily_cache": f"{root}/daily/cache",
        "daily_cache_json": f"{root}/daily/cache?format=json",
        "daily_related": f"{root}/daily/related",
        "daily_export": f"{root}/daily/export",
        "daily_export_rss": f"{root}/daily/export?format=rss",
        "daily_crawl": f"{root}/daily/crawl",
        "daily_crawl_status": f"{root}/daily/crawl/{{run_id}}",
        "daily_schedules": f"{root}/daily/schedules",
        "daily_enrich": f"{root}/daily/enrich",
        "ops": f"{root}/ops",
        "ops_status": f"{root}/ops/status",
        "ops_doctor": f"{root}/ops/doctor",
        "sources": f"{root}/sources",
        "endpoints": f"{root}/endpoints",
        "catalog_summary": f"{root}/catalog/summary",
        "catalog_coverage": f"{root}/catalog/coverage",
        "zotero_status": f"{root}/zotero/status",
        "zotero_items": f"{root}/zotero/items",
        "zotero_export": f"{root}/zotero/export",
        "agent_context": f"{root}/agent/context",
        "agent_explain": f"{root}/agent/explain",
        "agent_translate": f"{root}/agent/translate",
        "agent_translation_profiles": f"{root}/agent/translation-profiles",
        "agent_filter": f"{root}/agent/filter",
        "agent_research": f"{root}/agent/research",
        "agent_ask": f"{root}/agent/ask",
        "agent_rag_index": f"{root}/agent/rag/index",
    }
    tools = [
        "paper_enrich",
        "paper_sources",
        "paper_crawl",
        "paper_crawl_status",
        "paper_cache",
        "paper_agent_context",
        "paper_research",
        "paper_explain",
        "paper_translate",
        "paper_translation_profiles",
        "paper_filter",
        "paper_ask",
        "paper_rag_index",
        "paper_zotero_status",
        "paper_zotero_items",
        "paper_zotero_export",
        "paper_agent_manifest",
    ]
    capabilities = [
        "preprint_latest",
        "journal_latest",
        "daily_source_radar",
        "endpoint_catalog",
        "metadata_search",
        "json_export",
        "mcp_tools",
        "host_agent_model_context",
        "one_shot_research",
        "sqlite_daily_cache",
        "cache_export",
        "manual_discipline_crawl",
        "scheduled_discipline_crawl",
        "ops_panel",
        "catalog_validate",
        "catalog_coverage",
        "doctor_diagnostics",
        "deployment_handoff",
        "optional_llm_explain",
        "optional_llm_translate",
        "translation_profiles",
        "optional_llm_filter",
        "metadata_rag",
        "vector_cache_search",
        "cached_related_papers",
        "zotero_metadata_import",
    ]

    return {
        "name": "paperlite",
        "version": "0.2.7",
        "description": "Agent-ready research feed for preprints, top journals, and scholarly metadata.",
        "interfaces": {
            "reader": f"{root}/daily/cache?format=json",
            "human_ui": f"{root}/daily",
            "agent_default": {
                "mcp_tool": "paper_research",
                "rest": f"{root}/agent/research",
                "model_source": "agent_host",
                "context_tool": "paper_agent_context",
                "note": "Use this first for natural-language research requests. Return results in chat/tool output; /daily is only the human web UI.",
            },
            "agent_result_policy": agent_result_policy(),
            "rest": rest,
            "mcp": {
                "command": "python -m paperlite.mcp_server",
                "tools": tools,
            },
            "cli": {
                "serve": "python -m paperlite.cli serve --host 127.0.0.1 --port 8768",
                "catalog_validate": "python -m paperlite.cli catalog validate --format markdown",
                "catalog_coverage": "python -m paperlite.cli catalog coverage --format markdown",
                "doctor": "python -m paperlite.cli doctor --format markdown",
                "endpoints_health": "python -m paperlite.cli endpoints health --limit 50 --format markdown",
                "rag_index": "python -m paperlite.cli rag index --date YYYY-MM-DD --discipline computer_science --source arxiv --limit-per-source 100 --format markdown",
                "rag_ask": 'python -m paperlite.cli rag ask "question" --date YYYY-MM-DD --discipline computer_science --source arxiv --top-k 8 --format markdown',
            },
        },
        "capabilities": capabilities,
        "compatible_with": [
            "MCP-compatible agents",
            "ZeroTo-style agents",
            "Hermes-style agents",
            "OpenClaw-style agents",
            "QClaw-style agents",
        ],
        "llm": llm_status(),
        "embedding": embedding_status(),
        "non_goals": [
            "bridge",
            "webhook",
            "email",
            "messaging_platform_adapter",
            "automatic_translation_worker",
            "database_required",
        ],
    }
