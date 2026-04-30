# PaperLite

[中文说明](README.zh-CN.md)

PaperLite is a local-first paper metadata workbench for researchers who want a calmer daily reading queue.

Current release: `0.2.7`. See [CHANGELOG.md](CHANGELOG.md).

Give it a discipline and sources; it fetches paper metadata into SQLite, lets you review and export the results in `/daily`, and can optionally use your own LLM or embedding provider for translation, recommendation, and metadata-only RAG.

In the first few minutes, you can:

- start it with Docker Compose;
- open `/daily`, choose a discipline, and crawl a small source set;
- filter papers by date, source, discipline, and keyword;
- export RIS, BibTeX, Markdown, JSON, JSONL, or RSS;
- optionally connect Zotero, LLM filtering, translation, or metadata RAG.

No API key is required for browsing, crawling, filtering, export, or the Zotero fallback. Keys are only for optional LLM, embedding, and Zotero sync features.

PaperLite is deliberately metadata-only: no silent network calls on page load, no default all-source crawl, no PDF/full-text handling, and no hidden LLM automation.

## What It Does

- Daily workbench at `/daily`: choose scope, crawl/cache, review, enrich/translate/filter, export, or send metadata to Zotero.
- Local persistence: SQLite stores cached paper metadata, crawl runs, schedules, library state, saved views, translations, and preference signals.
- AI filtering: optional OpenAI-compatible LLM calls classify the current cached results into recommend / maybe / not recommended, using public quality rules plus local user preference signals.
- Metadata RAG: explicit vector indexing and question answering over cached paper metadata only.
- Related papers: `/daily` details can use the configured embedding provider to fill local cached-paper vectors and recommend similar cached metadata.
- Source operations: `/ops`, `paperlite doctor`, catalog validation, endpoint health checks, and source content audit help maintain hundreds of sources without checking them one by one.
- Metadata only: PaperLite never downloads, caches, proxies, uploads, or parses PDFs/full text.

## At A Glance

| Surface | Role | Design line |
| --- | --- | --- |
| `/daily` | Research workbench | SQLite-first browsing, filtering, enrichment, translation, export, and Zotero metadata flow. |
| `/daily/crawl` | Cache writer | Manual and scheduled fetching stay discipline-scoped; page load never crawls. |
| `/ops` | Operations panel | Doctor checks, run history, schedules, source health, and audit snapshots stay visible. |
| YAML catalog | Source truth | `sources.yaml`, `endpoints.yaml`, `taxonomy.yaml`, and `profiles.yaml` remain reviewable data files. |
| SQLite | Local memory | Cache, runs, schedules, library state, saved views, translations, and preference signals are local. |

## Quick Start

Most users only need Docker Compose:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
test -f .env || cp .env.example .env
docker compose up -d --build
```

Edit `.env` only if you want optional LLM, embedding, Zotero, or training-data export settings. If you are on Windows, create `.env` from `.env.example` once and keep the same Docker command; do not overwrite an existing `.env`.

Open `http://127.0.0.1:8000/daily`. If you change `.env` after PaperLite is already running, run `docker compose up -d` again so the container receives the new values.

First crawl:

1. Open `/daily`.
2. Click `学科：全部`, choose a discipline, and use `完成`.
3. Optionally click `来源：全部` to narrow the source list.
4. Click `抓取`; after it finishes, use `刷新` or filters to read the local cache.

For local Python development:

```bash
cd paperlite
python -m pip install -e ".[dev]"
python -m paperlite.cli serve --host 127.0.0.1 --port 8768
```

Open:

```text
http://127.0.0.1:8768/daily
http://127.0.0.1:8768/ops
```

The repository root keeps a compatibility ASGI entrypoint for deployment tools:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Before publishing a fork, keep `.env` local and rotate any real keys that were ever stored there.

## Main Interfaces

- Browser: `/daily`, `/ops`, `/sources`, `/endpoints`
- Cache/export: `/daily/cache`, `/daily/export`
- Related cached papers: `/daily/related`
- Crawl/schedule: `/daily/crawl`, `/daily/schedules`
- Library/preferences: `/library/*`, `/preferences/*`
- Agent/LLM: `/agent/filter`, `/agent/translate`, `/agent/explain`, `/agent/translation-profiles`
- One-shot agent research: `/agent/research`
- Metadata RAG: `/agent/rag/index`, `/agent/ask`
- CLI RAG: `python -m paperlite.cli rag index ...`, `python -m paperlite.cli rag ask ...`
- CLI sources: `python -m paperlite.cli sources --format markdown`
- Enrichment/Zotero: `/daily/enrich`, `/zotero/status`, `/zotero/items`, `/zotero/export`
- Discovery: `/agent/manifest`, `/.well-known/paperlite.json`

## Agent Setup

PaperLite supports two agent integration modes. Agents should not use `/daily`; that page is the human UI. `/daily/crawl` and `/daily/cache` are JSON API endpoints for HTTP fallback, not browser frontend steps.

For skill-based runtimes or agent marketplaces, start with [`SKILL.md`](SKILL.md). It is the short agent-facing entrypoint; this README is the human-facing guide.

Default MCP mode does not need Docker. The agent runs `python -m paperlite.mcp_server` as a local stdio process, reads local `.env` if present, and stores metadata in local SQLite. Use Docker only for HTTP API mode or for the human `/daily` browser UI.

Default agent workflow: call `paper_research` or `POST /agent/research` for natural-language requests such as "show today's materials papers". It resolves the discipline, checks today's SQLite cache, runs one explicit discipline-scoped crawl only when that cache is missing, requests the `research_card_cn` brief translation by default, then returns papers, count, crawl warnings, and a `result_contract`. Use the host agent's own model to render any missing brief fields. Use `paper_agent_context` or `POST /agent/context` only when the host agent needs prepared messages for explain/filter/ask workflows.

Agents should not open `/daily` to crawl or finish by sending users to a `/daily` link. Prefer MCP tools. For ordinary topic requests, call `paper_research(topic="材料", date="<today>")` and answer from its returned scope, papers, counts, warnings, and next actions. Return the selected papers and summary directly in the agent response. Use `paper_sources`, `paper_crawl`, `paper_crawl_status`, and `paper_cache` only for manual fallback or when the user asks for a specific source/run. Use HTTP JSON endpoints such as `POST /daily/crawl` only when MCP is unavailable.

Agent result rule: the user's current prompt wins. If no different format is requested, after crawling, organizing, filtering, or ranking papers, the agent should state the scope first: discipline, source key/name, date range, query, run status, warnings, and total count. Then it should list the actual papers. If there are 15 or fewer papers, list all of them with title, source/venue, date, URL/DOI, reason, and a brief abstract/summary. If more than 15 papers match, list at most 15, state the remaining count, and ask whether to AI-rank/optimize or add search keywords to narrow the set. In Chinese answers, use `paper.brief_translation.title_zh` and `paper.brief_translation.cn_flash_180` first; if missing, include a host-model brief Chinese title translation and one-sentence Chinese abstract/summary for every listed paper unless the user asks otherwise. Highlights come after the list, never instead of it.

Unconfigured PaperLite LLM, AI filter, or brief translation is not a blocker for host agents such as QClaw, Hermes, or OpenClaw. Use the host model over returned metadata instead. Do not claim cached papers were lost, the database was rebuilt, or a reinstall/reset happened unless a PaperLite tool explicitly says so.

If your agent can fetch and deploy GitHub repositories, this prompt is enough:

```text
https://github.com/cz1978/paperlite/ 把项目拉下来部署了
```

HTTP/browser deploy command, only when you need HTTP API mode or `/daily`:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && ([ -f .env ] || cp .env.example .env) && docker compose up -d --build
```

### MCP Mode

Use this when OpenClaw, QClaw, Hermes, or another agent can run stdio MCP servers.

No Docker is required for MCP mode.

One-line MCP install:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && python -m pip install -e ".[mcp]"
```

Or, from an existing checkout:

```bash
cd paperlite
python -m pip install -e ".[mcp]"
```

Add this MCP server to your agent config:

```json
{
  "mcpServers": {
    "paperlite": {
      "command": "python",
      "args": ["-m", "paperlite.mcp_server"],
      "cwd": "<repo>/paperlite"
    }
  }
}
```

Useful MCP tools:

- `paper_sources`
- `paper_research`
- `paper_crawl`
- `paper_crawl_status`
- `paper_cache`
- `paper_agent_context`
- `paper_rag_index`
- `paper_ask`
- `paper_filter`
- `paper_translate`
- `paper_zotero_status`
- `paper_zotero_items`
- `paper_zotero_export`

Typical agent flow:

1. For natural-language requests, call `paper_research(topic="<topic>", date="<today>")`.
2. If `papers` is non-empty, reply with the actual paper list first: titles, sources, dates, links, reasons, and brief abstracts/summaries. In Chinese answers, add Chinese title translations and one-sentence Chinese summaries for every paper.
3. If `remaining_count` is greater than 0, list only the returned papers and ask whether to AI-rank or add keywords.
4. If `warnings` or `crawl.source_warnings` are present, mention them instead of pretending the crawl fully succeeded.
5. Use `paper_sources`, `paper_crawl`, `paper_crawl_status`, and `paper_cache` only for manual fallback, source-specific requests, or troubleshooting.
6. Full translation only when requested. Run RAG only for explicit questions. Use Zotero only when the user asks to save or export papers.

Zotero flow:

1. Call `paper_zotero_status()`.
2. If configured, call `paper_zotero_items([paper_metadata])` to sync selected metadata.
3. If not configured, or if the user wants manual import, call `paper_zotero_export([paper_metadata], format="ris")` or `format="bibtex"` and return the filename plus content.
4. Real Zotero sync needs local `.env` values: `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_TYPE`, `ZOTERO_LIBRARY_ID`, and optional `ZOTERO_COLLECTION_KEY`.
5. Zotero remains metadata-only; no PDF or full text is uploaded.

### HTTP API Mode

Use this when the agent can call HTTP endpoints. Start PaperLite first:

```bash
docker compose up -d --build
```

Agent base URL on the same machine:

```text
http://127.0.0.1:8000
```

If the agent runs elsewhere, use your public reverse-proxy URL instead, for example `https://your-domain.example`.

Useful JSON endpoints:

- `POST /agent/context`
- `POST /agent/research`
- `GET /sources`
- `POST /daily/crawl`
- `GET /daily/crawl/{run_id}`
- `GET /daily/cache?format=json`
- `GET /daily/export?format=markdown`
- `POST /agent/rag/index`
- `POST /agent/ask`
- `POST /agent/filter`
- `POST /agent/translate`

Optional discovery endpoint for agents that support capability discovery:

```text
GET /agent/manifest
```

Use port `8768` instead of `8000` when running with `python -m paperlite.cli serve --host 127.0.0.1 --port 8768`.

## Maintenance

```bash
cd paperlite
python -m pytest -q
python -m compileall paperlite
ruff check paperlite tests
python -m paperlite.cli doctor --format markdown
python -m paperlite.cli sources --format markdown
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

## Quality Gates

- Narrow code edits should run the nearest targeted tests first.
- Release hygiene should include `python -m pytest -q`, `python -m compileall paperlite`, `ruff check paperlite tests`, and catalog validation.
- Source catalog work should dry-run generated YAML before writing and then run catalog coverage or endpoint audit for the changed slice.

Runtime data lives under `.paperlite/` by default and is ignored by Git. Start from `.env.example` for local configuration; when you run from `paperlite/`, PaperLite reads `paperlite/.env` first and falls back to the repository root `.env`.

`GET /preferences/training-data` exports local learning data only when `PAPERLITE_TRAINING_EXPORT_TOKEN` is configured and the request sends `Authorization: Bearer <token>`.

## Troubleshooting

- Crawl completed with 0 items: the selected date window may have no matching metadata, the source may be temporarily unavailable, or the upstream feed/API may have timed out. Check `/ops` or the crawl run source results before widening the date range or changing sources.
- `Embedding 未配置`: related papers and metadata RAG need `PAPERLITE_EMBEDDING_*`; normal cache browsing, export, and Zotero fallback still work.
- `Zotero is not fully configured`: PaperLite can still export RIS/BibTeX metadata without a Zotero API key.
