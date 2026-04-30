# PaperLite Package

PaperLite is a lightweight research metadata workbench for self-hosted daily reading. It combines YAML source catalogs, local SQLite cache/state, optional LLM-assisted filtering/translation, Zotero metadata export, REST, CLI, and MCP discovery.

The launch surface is intentionally narrow:

- `/daily`: cache-backed review workbench.
- `/daily/related`: embedding-backed related-paper recommendations from cached metadata.
- `/ops`: doctor, cache/run/schedule/source-audit visibility.
- `/sources`, `/endpoints`, `/catalog/*`: catalog inspection.
- `/library/*`, `/preferences/*`: single-user local library and learning state.
- `/agent/filter`, `/agent/translate`, `/agent/explain`, `/agent/translation-profiles`: explicit manual LLM actions and server-registered translation formats.
- `/agent/rag/index`, `/agent/ask`: explicit metadata-only vector RAG over cached papers.
- `/daily/enrich`, `/zotero/*`: metadata enrichment and Zotero metadata sync/export.

PaperLite does not provide the old reader/search API, JSONL dump connector, experimental rank endpoint, account system, default all-source crawl, or PDF/full-text fetching.

## Design Shape

- `api.py` keeps FastAPI app creation, lifespan startup, and router inclusion.
- `api_daily.py`, `api_ops.py`, `api_library.py`, `api_catalog.py`, `api_agent.py`, and `api_zotero.py` own grouped REST routes.
- `api_common.py` owns shared request parsing, coercion, and auth helpers.
- `daily_export.py` owns daily date resolution, SQLite cache payload shaping, and export helper policy.
- `daily_crawl.py` owns manual/scheduled cache writes and keeps every crawl discipline-scoped.
- `storage.py` is an import-compatible SQLite facade; focused `storage_*` modules own schema/connection, crawl+schedules, translation cache, library, preferences, saved views, and daily cache queries.
- `frontend.py` loads package assets from `frontend_assets/`; `daily_frontend.py` and `ops_frontend.py` remain thin render wrappers.
- Browser pages are self-contained package HTML returned by Python so the open-source runtime has no asset build step.

## Install

```bash
pip install -e ".[dev]"
```

Optional MCP dependency:

```bash
pip install -e ".[mcp]"
```

## Run

```bash
python -m paperlite.cli serve --host 127.0.0.1 --port 8768
```

Open `http://127.0.0.1:8768/daily`.

Configuration is read from the current working directory `.env`. If you serve from this package directory and no `paperlite/.env` exists, PaperLite falls back to the parent repository `.env`.

## CLI

```bash
python -m paperlite.cli doctor --format markdown
python -m paperlite.cli sources --format markdown
python -m paperlite.cli sources --discipline computer_science --kind preprint --format json
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli catalog add-source --key example_journal --name "Example Journal" --kind journal --discipline Chemistry --url https://example.com/rss.xml
python -m paperlite.cli endpoints --mode rss --format markdown
python -m paperlite.cli endpoints health --limit 50 --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
python -m paperlite.cli rag index --date 2026-04-30 --discipline computer_science --source arxiv_cs_lg --q RAG --limit-per-source 100 --format markdown
python -m paperlite.cli rag ask "What is new about RAG agents?" --date 2026-04-30 --discipline computer_science --source arxiv_cs_lg --q RAG --top-k 8 --format markdown
python -m paperlite.cli serve --port 8768
python -m paperlite.cli mcp
```

## REST

- `GET /daily`
- `GET /daily/cache`, `GET /daily/cache?format=json`
- `GET /daily/related`
- `GET /daily/export?format=ris|bibtex|markdown|json|jsonl|rss`
- `GET /daily/crawl`, `POST /daily/crawl`
- `GET /daily/crawl/{run_id}`
- `GET|POST /daily/schedules`
- `PATCH|DELETE /daily/schedules/{schedule_id}`
- `POST /daily/enrich`
- `GET /ops`, `GET /ops/status`, `GET /ops/doctor`
- `POST /ops/health/check`
- `GET /ops/source-audit`, `POST /ops/source-audit/check`
- `GET /sources`, `GET /endpoints`, `GET /categories`, `GET /catalog/summary`, `GET /catalog/coverage`
- `POST /library/state`, `POST /library/action`, `GET /library/items`, `GET|POST|DELETE /library/views`
- `GET /preferences/profile`, `GET|PATCH /preferences/settings`
- `GET|POST /preferences/prompts`, `PATCH|DELETE /preferences/prompts/{prompt_id}`
- `POST /preferences/rebuild`, `POST /preferences/purify`, `POST /preferences/learning-data/clear`, `GET /preferences/evaluation`, `GET /preferences/training-data`
- `POST /agent/filter`, `POST /agent/translate`, `POST /agent/explain`, `GET /agent/translation-profiles`
- `POST /agent/rag/index`, `POST /agent/ask`
- `GET /zotero/status`, `POST /zotero/items`, `POST /zotero/export?format=ris|bibtex`
- `GET /agent/manifest`, `GET /.well-known/paperlite.json`

`/daily` page load, filtering, pagination, and export read SQLite only. External source fetching happens only through discipline-scoped `POST /daily/crawl` or due schedules.

RAG and related-paper scope can include `date`, `date_from`, `date_to`, `discipline`, `source`, and optional `q` so browser, REST, and CLI flows can use the same filtered metadata range.

## LLM And Learning

LLM calls are explicit. Page load does not trigger filtering, translation, source audit, or health checks.

Translation prompts and output formats are server-registered profiles. `brief` defaults to `research_card_cn`, `detail` defaults to `detail_cn`, and agents should pass a `translation_profile` key instead of free-form prompts.

Set either the DeepSeek shortcut or generic OpenAI-compatible variables:

```bash
DEEPSEEK_API_KEY=
PAPERLITE_LLM_PROVIDER=deepseek
PAPERLITE_LLM_BASE_URL=
PAPERLITE_LLM_API_KEY=
PAPERLITE_LLM_MODEL=
```

Metadata RAG uses a separate OpenAI-compatible embedding model so chat and vector search can be configured independently:

```bash
PAPERLITE_EMBEDDING_BASE_URL=
PAPERLITE_EMBEDDING_API_KEY=
PAPERLITE_EMBEDDING_MODEL=
```

RAG is explicit: use the `/daily` RAG controls, call `POST /agent/rag/index`, or run `python -m paperlite.cli rag index` to index cached paper metadata. Then use `/daily` ask controls, call `POST /agent/ask`, or run `python -m paperlite.cli rag ask` to answer from indexed metadata with citations. It does not crawl, read PDFs, parse full text, or index automatically.

Related papers in `/daily` details call `GET /daily/related`. That endpoint may use the configured embedding provider to fill missing or stale vectors for local cached metadata, then scores similarity in SQLite/Python only. It does not crawl sources, visit paper URLs, read PDFs, parse full text, or call the chat LLM.

Preference learning is local SQLite state. It uses long-term prompts plus actions such as favorite, hide, read, export, Zotero, enrich, translate, and AI grouping to improve future filtering prompts. It is not model fine-tuning and does not upload user behavior.

Exporting local preference training data requires a server-side token:

```bash
PAPERLITE_TRAINING_EXPORT_TOKEN=
```

Send it as `Authorization: Bearer <token>` when calling `GET /preferences/training-data`.

## Zotero

```bash
ZOTERO_API_KEY=
ZOTERO_LIBRARY_TYPE=user
ZOTERO_LIBRARY_ID=
ZOTERO_COLLECTION_KEY=
```

The browser never receives the API key. Zotero integration sends or exports metadata only. `pdf_url` is an external metadata link; PaperLite does not download or upload PDFs.

## Source Catalog

Catalog files live in `paperlite/`:

- `sources.yaml`: source identity.
- `endpoints.yaml`: retrieval paths.
- `taxonomy.yaml`: stable categories and aliases.
- `profiles.yaml`: reusable source groups.

Validate and audit:

```bash
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

## MCP

MCP is optional. Install `.[mcp]` before running this command:

```bash
python -m paperlite.mcp_server
```

Tools:

- `paper_enrich`
- `paper_sources`
- `paper_explain`
- `paper_translate`
- `paper_translation_profiles`
- `paper_filter`
- `paper_ask`
- `paper_rag_index`
- `paper_zotero_status`
- `paper_zotero_items`
- `paper_agent_manifest`

## Paper Model

`Paper` carries normalized metadata: title, abstract, authors, URL, optional DOI, source, date, journal/venue/publisher, identifiers, concepts, citation count, source evidence, and raw diagnostic details. `doi` is first-class; `pdf_url` is external-only metadata; `raw` should not contain secrets.
