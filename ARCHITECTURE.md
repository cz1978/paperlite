# Architecture

Chinese version: [ARCHITECTURE.zh-CN.md](ARCHITECTURE.zh-CN.md)

PaperLite is organized around one rule: external work is explicit, local reading is cache-first.

## Data Flow

```text
YAML catalog
  -> discipline-scoped crawl
  -> SQLite metadata cache
  -> /daily, REST, MCP, CLI
  -> export, Zotero metadata, optional metadata-only RAG
```

The catalog lives in reviewable YAML files: `sources.yaml`, `endpoints.yaml`, `taxonomy.yaml`, and `profiles.yaml`. Crawl jobs read that catalog, fetch paper metadata from selected sources, and write normalized metadata into SQLite.

## Runtime Surfaces

- `/daily` is the human research workbench. It reads SQLite for page load, filtering, pagination, export, and review.
- `/ops` shows run history, schedules, source health, doctor checks, and catalog status.
- REST endpoints provide JSON access for HTTP agents and integrations.
- MCP tools are the default agent integration path.
- CLI commands support local maintenance, catalog checks, RAG, and server startup.

## Storage

SQLite stores:

- cached paper metadata;
- crawl runs and source run results;
- schedules;
- library state such as saved, read, and hidden papers;
- saved views and preference signals;
- translation cache;
- Research Missions, mission run summaries, and mission-level seen paper memory.

Run history stores lightweight summaries and paper IDs. Full paper metadata stays in the existing cache tables.

## Agent Flow

Ordinary research requests should call `paper_research`. Long-running interests should use Research Missions: `paper_mission_save`, `paper_missions`, `paper_mission_run`, and `paper_mission_delete`.

Agents should return the actual paper list, scope, warnings, and next actions directly. They should not use `/daily` as a result link.

## AI and RAG Boundaries

LLM filtering, translation, embeddings, and RAG are optional. They require explicit user action or explicit agent tool calls. Metadata RAG indexes cached metadata only: titles, abstracts, authors, identifiers, DOI, URL, source, venue, and related metadata.

## Hard Boundaries

- No PDF or full-text download, cache, proxy, upload, or parsing.
- No hidden crawl, LLM, embedding, source audit, health check, or RAG work on page load.
- No default all-source crawl.
- No new work in old `app/`, old `/v1` routes, old workers, or old database tables.

