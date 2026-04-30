# PaperLite Agent Handoff

This repository's active runtime is PaperLite, not the old app.

## Target Runtime

- Package root: `paperlite/`
- Python package: `paperlite/paperlite/`
- Browser entry: `/daily`
- Compatibility ASGI entrypoint: `main:app`
- Local command from repo root: `python -m uvicorn main:app --host 127.0.0.1 --port 8000`
- Package command: `cd paperlite && python -m paperlite.cli serve --host 127.0.0.1 --port 8768`

## Current Product Contract

- `/daily` is the cache-backed PaperLite research workbench.
- Page load, refresh, filtering, pagination, and export read SQLite only.
- External source fetching happens only through discipline-scoped `POST /daily/crawl` or due schedules.
- The catalog stays in YAML: `sources.yaml`, `endpoints.yaml`, `taxonomy.yaml`, `profiles.yaml`.
- SQLite stores crawl runs, cached paper metadata, translation cache, schedules, library state, saved views, and local preference learning data.
- PaperLite does not download, cache, proxy, upload, or parse PDF/full-text content.
- Zotero sends or exports metadata only.

## Agent Entry Points

- REST manifest: `GET /.well-known/paperlite.json`
- Agent manifest: `GET /agent/manifest`
- MCP command: `python -m paperlite.mcp_server`
- CLI RAG: `python -m paperlite.cli rag index`, `python -m paperlite.cli rag ask`
- Ops panel: `GET /ops`
- Ops status JSON: `GET /ops/status`
- Cache reader JSON: `GET /daily/cache?format=json`
- Related cached papers: `GET /daily/related`
- Batch export: `GET /daily/export?format=ris|bibtex|markdown|json|jsonl|rss`
- Metadata enrich: `POST /daily/enrich`
- Agent actions: `POST /agent/filter`, `POST /agent/translate`, `POST /agent/explain`, `POST /agent/rag/index`, `POST /agent/ask`, `GET /agent/translation-profiles`
- Source catalog: `GET /sources`, `GET /endpoints`, `GET /catalog/summary`, `GET /catalog/coverage`

## Maintenance Commands

Run these from `paperlite/` unless noted otherwise:

```bash
python -m pytest -q
python -m compileall paperlite
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints health --limit 50 --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
python -m paperlite.cli rag index --date YYYY-MM-DD --discipline computer_science --source arxiv --format markdown
python -m paperlite.cli rag ask "question" --date YYYY-MM-DD --discipline computer_science --source arxiv --format markdown
```

Add ordinary feed sources with a dry run first:

```bash
python -m paperlite.cli catalog add-source --key example_journal --name "Example Journal" --kind journal --discipline Chemistry --url https://example.com/rss.xml
```

Repeat with `--write` only after reviewing the generated YAML.

## Boundaries

- Do not wire new work into old `app/`, old `/v1` routes, old workers, or old database tables.
- Do not add automatic LLM filtering, translation, source audit, health checks, or crawls on page load.
- Do not auto-index or auto-ask RAG on page load; RAG must stay explicit and metadata-only.
- `GET /daily/related` may fill local cached metadata embeddings through the configured embedding provider, but must not crawl sources, visit paper URLs, read PDFs, parse full text, or call chat LLMs.
- Do not make all-source crawls the default; manual and scheduled crawl paths must stay discipline scoped.
- Public auth/password mode is not part of the default open-source runtime in this pass.
