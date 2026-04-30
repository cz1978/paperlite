# Changelog

## 0.2.7 - 2026-04-30

- Added `paper_research` and `POST /agent/research` for one-shot natural-language research requests.
- Added deterministic Chinese/common topic resolution, including broad materials requests that map to `discipline=materials` without adding `q=materials`.
- When a requested discipline/date scope has no cache, `paper_research` performs one explicit discipline-scoped crawl, then rereads SQLite and returns papers, counts, warnings, overflow guidance, and next actions.
- Updated agent manifests and `SKILL.md` so MCP agents use `paper_research` first instead of manually opening `/daily` or stitching crawl/cache steps for ordinary requests.

## 0.2.6 - 2026-04-30

- Lowered the default agent chat output cap to 15 papers.
- Added overflow guidance: when more papers match, ask whether to AI-rank/optimize or narrow with more keywords instead of dumping the whole set.
- Clarified that `/daily/crawl` is a JSON API endpoint for HTTP fallback, while MCP tools remain the default agent path and `/daily` is only the human UI.

## 0.2.5 - 2026-04-30

- Clarified that the current user prompt overrides default skill formatting rules.
- Tightened Chinese agent output: every listed paper should include a brief Chinese title translation and one-sentence abstract/summary when the user has not asked otherwise.
- Added manifest and `paper_agent_context` policy fields for brief translation and abstract/summary output.

## 0.2.4 - 2026-04-30

- Tightened agent result output rules: agents must state crawl/cache scope and list actual papers before summaries or highlights.
- Added manifest scope fields so agents report discipline, source, date range, query, run status, warnings, and total count.

## 0.2.3 - 2026-04-30

- Added `paper_zotero_export` for MCP-only RIS/BibTeX export when Zotero sync is not configured.
- Expanded agent skill guidance with setup, crawl, post-crawl translation/RAG decisions, and Zotero sync/export workflows.
- Clarified that translation, filtering, RAG, and Zotero actions stay explicit after crawl.

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
