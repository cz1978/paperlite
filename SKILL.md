---
name: paperlite
description: Use PaperLite as a local-first scholarly metadata workbench. Trigger when an agent needs to install or connect PaperLite, list scholarly sources, crawl discipline-scoped paper metadata, query cached papers, export metadata, use metadata-only RAG, or integrate Zotero metadata. Do not use for PDF/full-text crawling, automatic all-source crawling, or hidden page-load LLM work.
---

# PaperLite

PaperLite helps a research agent work with paper metadata that is stored locally in SQLite. It is useful for building a daily reading queue, filtering cached scholarly metadata, exporting references, syncing Zotero metadata, and running explicit metadata-only RAG.

Default agent path: use `paper_agent_context` or `POST /agent/context` to get metadata-backed messages, then let the host agent use its own model. PaperLite's built-in LLM endpoints are optional fallback tools for deployments that configure `.env` LLM keys.

Do not tell users to open `/daily` for agent tasks. Use the tools below.

## Start PaperLite

If the host can fetch and deploy GitHub repositories, this prompt is enough:

```text
https://github.com/cz1978/paperlite/ 把项目拉下来部署了
```

Fallback shell deploy command:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && ([ -f .env ] || cp .env.example .env) && docker compose up -d --build
```

Prefer Docker Compose for a fresh checkout:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
test -f .env || cp .env.example .env
docker compose up -d --build
```

No key is required for browsing, source listing, metadata crawl, ordinary cached-result filtering, or export. Put optional LLM, embedding, or Zotero credentials only in the local `.env`.

## Connect Through MCP

One-line MCP install from the GitHub repository:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && python -m pip install -e ".[mcp]"
```

Use MCP when the host can run a stdio server:

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
- `paper_zotero_items` - read Zotero metadata.

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
- `POST /daily/crawl`
- `POST /agent/filter`
- `POST /agent/translate`
- `POST /agent/rag/index`
- `POST /agent/ask`
- `GET /agent/manifest`

## Agent Recipes

### Find and crawl today's energy papers

1. Call `paper_sources(discipline="energy", q="energy", latest=true, limit=20)`.
2. Pick one or a few source keys from `sources[*].name`, for example `nature_nature_energy_aop` when present.
3. Call `paper_crawl(discipline="energy", source="<source_key>", limit_per_source=20, run_now=true)`.
4. If the run is still queued/running, call `paper_crawl_status(run_id="<run_id>")`.
5. Call `paper_cache(discipline="energy", source="<source_key>", q="energy", limit_per_source=20)`.
6. Use your own host model to summarize, rank, or translate the returned papers. For a ready prompt, call `paper_agent_context(action="ask", question="Summarize today's energy papers", discipline="energy", source="<source_key>", q="energy")`.

### Use HTTP instead of MCP

1. `GET /sources?discipline=Energy&format=json`
2. `POST /daily/crawl` with `{"discipline":"energy","source":"<source_key>","limit_per_source":20}`
3. `GET /daily/crawl/{run_id}` until done.
4. `GET /daily/cache?format=json&discipline=energy&source=<source_key>`
5. `POST /agent/context` when the host agent should use its own model.

## Operating Rules

- Treat `/daily` as the human web UI, not an agent control surface.
- Use MCP tools or JSON endpoints for agent actions.
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
