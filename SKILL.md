---
name: paperlite
description: Use PaperLite as a local-first scholarly metadata workbench. Trigger when an agent needs to install or connect PaperLite, list scholarly sources, crawl discipline-scoped paper metadata, query cached papers, export metadata, use metadata-only RAG, or integrate Zotero metadata. Do not use for PDF/full-text crawling, automatic all-source crawling, or hidden page-load LLM work.
---

# PaperLite

PaperLite helps a research agent work with paper metadata that is stored locally in SQLite. It is useful for building a daily reading queue, filtering cached scholarly metadata, exporting references, syncing Zotero metadata, and running explicit metadata-only RAG.

Default agent path: use `paper_agent_context` or `POST /agent/context` to get metadata-backed messages, then let the host agent use its own model. PaperLite's built-in LLM endpoints are optional fallback tools for deployments that configure `.env` LLM keys.

Do not tell users to open `/daily` for agent tasks. Do not finish with a `/daily` link as the result. Use the tools below and answer with the actual papers, counts, source keys, warnings, and next actions.

## Choose MCP Or HTTP

Default agent use is MCP stdio. It does not need Docker, does not start `/daily`, and does not require a running HTTP server. Install the package, then let the host agent launch `python -m paperlite.mcp_server`.

If the host can fetch GitHub repositories and install MCP servers from natural language, this prompt is enough:

```text
https://github.com/cz1978/paperlite/ 把 PaperLite MCP 安装好
```

One-line MCP install from the GitHub repository:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && python -m pip install -e ".[mcp]"
```

Use Docker only when the host needs HTTP endpoints or a human browser UI. HTTP/browser deploy command:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && ([ -f .env ] || cp .env.example .env) && docker compose up -d --build
```

No key is required for browsing, source listing, metadata crawl, ordinary cached-result filtering, or export. Put optional LLM, embedding, or Zotero credentials only in the local `.env`.

## Connect Through MCP

Use MCP when the host can run a local stdio server:

```bash
python -m paperlite.mcp_server
```

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

Useful tools:

- `paper_sources` - list available sources; for crawl planning pass filters such as `discipline`, `q`, `latest=true`, and `limit`.
- `paper_crawl` - explicitly crawl a discipline/source/date range and write metadata to SQLite.
- `paper_crawl_status` - inspect a crawl run.
- `paper_cache` - read cached metadata from SQLite after a crawl.
- `paper_agent_context` - return metadata-backed messages for the host agent model; no PaperLite LLM key needed.
- `paper_rag_index` - explicitly index cached metadata for a scoped query.
- `paper_ask` - ask questions over indexed cached metadata.
- `paper_filter` - classify cached papers with the configured LLM.
- `paper_translate` - translate cached paper metadata.
- `paper_zotero_status` - inspect Zotero configuration.
- `paper_zotero_items` - create Zotero metadata items when Zotero is configured.
- `paper_zotero_export` - export selected metadata as RIS or BibTeX when Zotero is not configured or the user wants a file-style import.

## Connect Through HTTP

Use HTTP when the host can call JSON endpoints. On the same machine, the default Docker base URL is:

```text
http://127.0.0.1:8000
```

Use a public reverse-proxy URL instead when the agent runs on another machine.

Useful endpoints:

- `POST /agent/context`
- `GET /sources`
- `POST /daily/crawl`
- `GET /daily/crawl/{run_id}`
- `GET /daily/cache?format=json`
- `GET /daily/export?format=ris|bibtex|markdown|json|jsonl|rss`
- `GET /daily/related`
- `POST /agent/filter`
- `POST /agent/translate`
- `POST /agent/rag/index`
- `POST /agent/ask`
- `GET /agent/manifest`

## Agent Recipes

## Result Output Contract

- After any crawl, cache read, organize, filter, rank, or topic search with nonzero results, send the paper list in the chat response.
- Start the answer with the scope used: discipline, source key/name, date or date range, query `q`, crawl run id/status, total count, and any warnings.
- If there are 20 or fewer papers, list every paper. If there are more than 20, list the first 20 and state exactly how many more are available in `paper_cache` or export output.
- Each listed paper should include title, source or venue, date when present, DOI/URL when present, and one short reason it matched the user's request.
- Put any synthesis, highlights, translation, or trend summary after the list. Do not replace the list with highlights.
- Do not answer only "整理完成", "已筛选出 N 篇", or "完整列表见 /daily".
- If zero papers match, say zero, include crawl/source warnings when available, and suggest changing date/source/query.

### Default research workflow

1. Install/connect through MCP unless the user specifically needs HTTP or `/daily`.
2. Use `paper_sources(discipline="<discipline>", q="<topic>", latest=true, limit=20)` to find crawl-capable source keys.
3. Use `paper_crawl(discipline="<discipline>", source="<source_key>", limit_per_source=20, run_now=true)`.
4. Use `paper_crawl_status(run_id="<run_id>")` when the run is not clearly completed or has warnings.
5. Use `paper_cache(discipline="<discipline>", source="<source_key>", q="<topic>", limit_per_source=50)` to read the actual papers.
6. Follow the Result Output Contract: list the actual papers first, then add a short synthesis.

### What to do after crawling

- Summarize or rank by default with the host agent model over `paper_cache` results; no PaperLite LLM key is needed.
- Translate only when the user asks for translation or Chinese research cards. If PaperLite LLM is configured, use `paper_translate`; otherwise translate with the host agent model from `paper_cache` or `paper_agent_context`.
- Filter with `paper_filter` only when the user asks for LLM-based recommendation; otherwise use the host agent model to rank from metadata.
- Run RAG only when the user asks a question over the cached papers. Use `paper_rag_index` and `paper_ask`; do not auto-index after every crawl.
- Sync to Zotero only when the user asks to save/send papers. Use the Zotero workflow below.

### Find and crawl today's energy papers

1. Call `paper_sources(discipline="energy", q="energy", latest=true, limit=20)`.
2. Pick one or a few source keys from `sources[*].name`, for example `nature_nature_energy_aop` when present.
3. Call `paper_crawl(discipline="energy", source="<source_key>", limit_per_source=20, run_now=true)`.
4. Call `paper_cache(discipline="energy", source="<source_key>", q="energy", limit_per_source=20)`.
5. Reply with the actual paper list and a short synthesis. If the user asked for Chinese, translate the summary and titles in the final answer.

### Save selected papers to Zotero

1. Start from selected paper objects returned by `paper_cache`; do not invent Zotero items from text-only summaries.
2. Call `paper_zotero_status()`.
3. If `configured` is true, call `paper_zotero_items([<selected_paper_dicts>])` and report created/failed counts plus failed reasons.
4. If Zotero is not configured, call `paper_zotero_export([<selected_paper_dicts>], format="ris")` or `format="bibtex"` and return the filename plus content for import.
5. Tell the user Zotero sync needs local `.env` values: `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_TYPE`, `ZOTERO_LIBRARY_ID`, and optional `ZOTERO_COLLECTION_KEY`.
6. Zotero flow is metadata-only; do not upload PDFs or full text.

### Use HTTP instead of MCP

1. `GET /sources?discipline=Energy&format=json`
2. `POST /daily/crawl` with `{"discipline":"energy","source":"<source_key>","limit_per_source":20}`
3. `GET /daily/crawl/{run_id}` until done.
4. `GET /daily/cache?format=json&discipline=energy&source=<source_key>`
5. `POST /agent/context` when the host agent should use its own model.
6. `POST /zotero/items` to sync selected metadata, or `POST /zotero/export?format=ris` to produce a Zotero import file.

## Operating Rules

- Treat `/daily` as the human web UI, not an agent control surface.
- Use MCP tools or JSON endpoints for agent actions.
- Return task results directly in the conversation. Mention `/daily` only if the user explicitly asks for the human browser interface.
- For long result sets, show the top items and say how many more are in `paper_cache`; offer `daily/export` formats instead of a frontend link.
- Prefer `paper_agent_context` or `/agent/context` when OpenClaw, QClaw, Hermes, or another host agent should use its own model.
- Keep crawls discipline-scoped; do not default to all-source crawls.
- Do not crawl on page load or without explicit user intent.
- Do not download, cache, upload, or parse PDFs or full text.
- Do not auto-index or auto-ask RAG; RAG must be explicit and metadata-only.
- Prefer narrow filters: `date`, `date_from`, `date_to`, `discipline`, `source`, `q`, and `latest=true` when choosing crawl sources.
- If a crawl returns zero items, inspect `/ops/status` or source warnings before assuming failure.

## Optional Credentials

DeepSeek users usually only need:

```env
DEEPSEEK_API_KEY=
```

Other OpenAI-compatible LLM providers use:

```env
PAPERLITE_LLM_API_KEY=
PAPERLITE_LLM_BASE_URL=
PAPERLITE_LLM_MODEL=
```

Embedding-backed metadata RAG uses:

```env
PAPERLITE_EMBEDDING_API_KEY=
PAPERLITE_EMBEDDING_BASE_URL=
PAPERLITE_EMBEDDING_MODEL=
```

Zotero metadata sync uses:

```env
ZOTERO_API_KEY=
ZOTERO_LIBRARY_TYPE=user
ZOTERO_LIBRARY_ID=
ZOTERO_COLLECTION_KEY=
```
