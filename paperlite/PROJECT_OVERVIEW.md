# PaperLite Project Overview

PaperLite is now organized around one product path: cache scholarly metadata, reduce research-feed noise, and help a single user review/export what matters.

## Runtime Shape

- `paperlite/api.py`: FastAPI app factory, lifespan startup, and router inclusion.
- `paperlite/api_common.py`: shared request parsing, type coercion, LLM error mapping, and protected export auth.
- `paperlite/api_daily.py`, `api_ops.py`, `api_library.py`, `api_catalog.py`, `api_agent.py`, `api_zotero.py`: grouped public REST route contracts.
- `paperlite/frontend.py`: package asset loader for no-build browser pages.
- `paperlite/frontend_assets/daily.html`, `frontend_assets/ops.html`: active browser HTML/CSS/JS.
- `paperlite/daily_frontend.py`, `ops_frontend.py`: thin render wrappers kept for import compatibility.
- `paperlite/daily_dates.py`: local daily date parsing and crawl window helpers.
- `paperlite/daily_export.py`: cache/export helper policy for `/daily/cache` and `/daily/export`.
- `paperlite/daily_crawl.py`: discipline-scoped manual and scheduled cache writer.
- `paperlite/agent.py`: explicit LLM filtering, translation, metadata RAG, and cached related-paper logic.
- `paperlite/translation_profiles.py`, `translation_profiles.yaml`: server-owned translation output profiles.
- `paperlite/cli.py`: local operations CLI, including read-only `paperlite sources` catalog listing.
- `paperlite/storage.py`: compatibility facade for existing imports.
- `paperlite/storage_schema.py`: SQLite connection, schema, migrations, shared serialization helpers.
- `paperlite/storage_crawl.py`: crawl runs, source results, schedules, and daily cache writes.
- `paperlite/storage_translation.py`: translation cache.
- `paperlite/storage_preference_core.py`, `storage_library.py`, `storage_preferences.py`: local library state and preference learning.
- `paperlite/storage_views.py`: saved views.
- `paperlite/storage_cache.py`: daily cache reads and grouping.
- `paperlite/ai_filter.py`: LLM-assisted paper filtering with public quality criteria and local preference context.
- `paperlite/source_audit.py`: metadata-only source content audit.
- `paperlite/doctor.py`: dependency/config/DB/LLM/Zotero/ops diagnostics.
- `paperlite/sources.yaml`, `endpoints.yaml`, `taxonomy.yaml`, `profiles.yaml`: source catalog and grouping data.

## Public Contract

Keep:

- `/daily`, `/daily/cache`, `/daily/export`, `/daily/crawl`, `/daily/schedules`, `/daily/enrich`
- `/daily/related`
- `/library/*`, `/preferences/*`
- `/ops/*`, `/ops/source-audit/*`
- `/sources`, `/endpoints`, `/catalog/*`
- `/agent/filter`, `/agent/translate`, `/agent/explain`, `/agent/translation-profiles`
- `/agent/rag/index`, `/agent/ask`
- `/zotero/status`, `/zotero/items`, `/zotero/export`
- `/agent/manifest`, `/.well-known/paperlite.json`

Removed:

- `/papers*`
- `/export/rss`
- `/agent/digest`
- `/agent/rank`
- JSONL dump connector/CLI
- experimental rank flag

CLI keepers:

- `paperlite sources`: read-only YAML catalog listing; no network or crawl.
- `paperlite catalog validate|coverage|add-source`: catalog maintenance.
- `paperlite endpoints health|audit`: explicit source checks.
- `paperlite rag index|ask`: explicit metadata-only RAG over cached papers.

## Boundaries

- No PDF/full-text fetching, caching, proxying, uploading, or parsing.
- No default all-source crawl.
- No account system in the open-source runtime.
- No automatic LLM, source audit, health check, or crawl on page load.
- Zotero receives metadata only.

## Design Principles

- Keep the browser path cache-backed and predictable.
- Keep network work explicit: manual crawl, due schedule, manual enrichment, manual audit, or manual health check.
- Keep source truth in YAML and user memory in SQLite.
- Keep adapters thin enough that route files read like contracts, not storage engines.
- Keep every export metadata-only and reproducible from local cache.

## Maintenance Loop

```bash
python -m paperlite.cli doctor --format markdown
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
python -m pytest -q
```
