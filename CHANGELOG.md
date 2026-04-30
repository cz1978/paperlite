# Changelog

## 0.2.2 - 2026-04-30

- Tightened the agent skill instructions so agents return papers and summaries directly instead of linking users to `/daily`.
- Changed the agent manifest `reader` interface to JSON cache output and moved the browser workbench to `human_ui`.
- Added manifest and docs guardrails for the no-frontend agent result policy.

## 0.2.1 - 2026-04-30

- Added agent-first MCP crawl/cache tools: `paper_crawl`, `paper_crawl_status`, and `paper_cache`.
- Made `paper_sources` filterable, bounded by default, and able to return only crawl-capable sources.
- Updated `SKILL.md` and README agent guidance so agents use MCP/JSON tools instead of opening the human `/daily` page.

## 0.2.0 - 2026-04-30

- Added host-agent context mode with `paper_agent_context` and `POST /agent/context`, so OpenClaw, QClaw, Hermes, and other agents can use their own model over PaperLite metadata without configuring a PaperLite LLM key.
- Added public `SKILL.md` for agent/skill runtimes.
- Clarified that `/daily` is the human UI, while agents should use MCP tools or JSON endpoints.
- Simplified Docker quick start and agent deployment instructions.
- Hardened release hygiene: ignored local secrets/runtime data, added Docker context exclusions, cleaned storage imports, and kept PaperLite metadata-only boundaries explicit.
- Added `paperlite sources` CLI alias and CI/docs guardrails.

## 0.1.0 - 2026-04-30

- Initial PaperLite open-source release candidate.
- Self-hosted `/daily` metadata workbench backed by local SQLite.
- Discipline-scoped manual/scheduled metadata crawl, source catalog, ops panel, exports, Zotero metadata flow, optional LLM filtering/translation, and explicit metadata RAG.
