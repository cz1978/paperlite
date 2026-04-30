---
name: paperlite
description: Use PaperLite as a local-first scholarly metadata workbench. Trigger when an agent needs to install or connect PaperLite, list scholarly sources, crawl discipline-scoped paper metadata, query cached papers, export metadata, use metadata-only RAG, or integrate Zotero metadata. Do not use for PDF/full-text crawling, automatic all-source crawling, or hidden page-load LLM work.
---

# PaperLite

PaperLite helps a research agent work with paper metadata that is stored locally in SQLite. It is useful for building a daily reading queue, filtering cached scholarly metadata, exporting references, syncing Zotero metadata, and running explicit metadata-only RAG.

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

No key is required for browsing, source listing, metadata crawl, filtering, or export. Put optional LLM, embedding, or Zotero credentials only in the local `.env`.

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

- `paper_sources` - list available sources.
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

- `GET /sources`
- `GET /daily/cache?format=json`
- `GET /daily/export?format=ris|bibtex|markdown|json|jsonl|rss`
- `GET /daily/related`
- `POST /daily/crawl`
- `POST /agent/filter`
- `POST /agent/translate`
- `POST /agent/rag/index`
- `POST /agent/ask`
- `GET /agent/manifest`

## Operating Rules

- Treat `/daily` as the human web UI, not an agent control surface.
- Use MCP tools or JSON endpoints for agent actions.
- Keep crawls discipline-scoped; do not default to all-source crawls.
- Do not crawl on page load or without explicit user intent.
- Do not download, cache, upload, or parse PDFs or full text.
- Do not auto-index or auto-ask RAG; RAG must be explicit and metadata-only.
- Prefer narrow filters: `date`, `date_from`, `date_to`, `discipline`, `source`, and `q`.
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
