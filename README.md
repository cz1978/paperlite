# PaperLite

[中文说明](README.zh-CN.md)

PaperLite is a self-hosted research-noise reducer: it crawls configured scholarly metadata sources into local SQLite, lets you review them in `/daily`, learns a local single-user preference profile from reading actions, and keeps source/catalog operations visible in `/ops`.

It is the active runtime in this repository. The old app, route chain, publishing workers, and retired reader are not part of the launch surface.

## At A Glance

| Surface | Role | Design line |
| --- | --- | --- |
| `/daily` | Research workbench | SQLite-first browsing, filtering, enrichment, translation, export, and Zotero metadata flow. |
| `/daily/crawl` | Cache writer | Manual and scheduled fetching stay discipline-scoped; page load never crawls. |
| `/ops` | Operations panel | Doctor checks, run history, schedules, source health, and audit snapshots stay visible. |
| YAML catalog | Source truth | `sources.yaml`, `endpoints.yaml`, `taxonomy.yaml`, and `profiles.yaml` remain reviewable data files. |
| SQLite | Local memory | Cache, runs, schedules, library state, saved views, translations, and preference signals are local. |

PaperLite's bias is explicit work: no silent network calls, no default all-source crawl, no PDF/full-text handling, and no hidden LLM automation.

## What It Does

- Daily workbench at `/daily`: choose scope, crawl/cache, review, enrich/translate/filter, export, or send metadata to Zotero.
- Local persistence: SQLite stores cached paper metadata, crawl runs, schedules, library state, saved views, translations, and preference signals.
- AI filtering: optional OpenAI-compatible LLM calls classify the current cached results into recommend / maybe / not recommended, using public quality rules plus local user preference signals.
- Metadata RAG: explicit vector indexing and question answering over cached paper metadata only.
- Related papers: `/daily` details can use the configured embedding provider to fill local cached-paper vectors and recommend similar cached metadata.
- Source operations: `/ops`, `paperlite doctor`, catalog validation, endpoint health checks, and source content audit help maintain hundreds of sources without checking them one by one.
- Metadata only: PaperLite never downloads, caches, proxies, uploads, or parses PDFs/full text.

## Quick Start

From GitHub with Docker Compose:

Linux/macOS:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
test -f .env || cp .env.example .env
docker compose up -d --build
```

PowerShell:

```powershell
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
```

Edit `.env` before the first start if you want LLM, Zotero, or training-data export settings.

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
- Metadata RAG: `/agent/rag/index`, `/agent/ask`
- CLI RAG: `python -m paperlite.cli rag index ...`, `python -m paperlite.cli rag ask ...`
- CLI sources: `python -m paperlite.cli sources --format markdown`
- Enrichment/Zotero: `/daily/enrich`, `/zotero/status`, `/zotero/items`, `/zotero/export`
- Discovery: `/agent/manifest`, `/.well-known/paperlite.json`

## External Agents

OpenClaw, QClaw, Hermes, and similar external agents normally only need this URL:

```text
http://127.0.0.1:8000/agent/manifest
```

If the agent asks for a service base URL instead, use `http://127.0.0.1:8000`. Use port `8768` when running with `python -m paperlite.cli serve --host 127.0.0.1 --port 8768`.

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
