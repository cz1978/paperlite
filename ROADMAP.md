# Roadmap

Chinese version: [ROADMAP.zh-CN.md](ROADMAP.zh-CN.md)

PaperLite is a local-first scholarly metadata workbench. The roadmap favors explicit, inspectable workflows over hidden automation.

## v0.3: Research Missions

The main v0.3 direction is agent-first long-running research radar:

- save durable Research Missions with topic, discipline, sources, include/exclude/prefer terms, and instructions;
- run mission radar updates through MCP or REST;
- remember mission-level seen papers;
- return new papers, important papers, excluded summary, topic signals, warnings, and next actions;
- keep mission runs cache-first and metadata-only.

## Next Directions

- Make mission setup easier for agents and humans without turning it into a page-load crawler.
- Improve mission-level summaries and topic drift signals from metadata and run history.
- Add optional schedule integration for missions while preserving explicit scope and local control.
- Improve source maintenance workflows, endpoint diagnostics, and catalog contribution ergonomics.
- Polish `/daily` for repeated work: clearer grouping, less visual density, and better empty states.
- Keep metadata export and Zotero workflows reliable and easy to verify.

## Non-Goals

- No PDF or full-text download, cache, proxy, upload, or parsing.
- No hidden all-source crawling.
- No crawl, LLM, embedding, source audit, health check, or RAG work on page load.
- No default public auth/password layer in the open-source runtime.
- No replacement for Zotero, arXiv, Crossref, OpenAlex, or publisher sites.

## Contribution Ideas

- Add or repair source endpoints with reproducible catalog checks.
- Improve docs and examples for MCP agents.
- Add focused tests for mission scoring, storage, source warnings, and export payloads.
- Improve accessibility and density in `/daily` without changing the cache-first contract.

