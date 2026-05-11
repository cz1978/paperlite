# Contributing to PaperLite

Thanks for helping PaperLite stay useful, calm, and local-first. This project is a scholarly metadata workbench, so small, well-tested changes are much better than broad rewrites.

Chinese version: [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)

## Project Boundaries

Keep these boundaries intact:

- PaperLite handles paper metadata, not PDFs or full text.
- Page load, refresh, filtering, pagination, export, and related paper browsing read SQLite only.
- External fetching happens only through explicit discipline-scoped crawl paths or due schedules.
- Do not make all-source crawl the default.
- Do not add hidden LLM, embedding, source audit, health check, crawl, or RAG work on page load.
- Agent workflows should use MCP tools or JSON endpoints, not the human `/daily` UI.
- Do not wire new work into old `app/`, old `/v1` routes, old workers, or old database tables.

## Local Setup

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
python -m pip install -e "paperlite[dev]"
```

Run the web app from the repository root:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Or run the package command:

```bash
cd paperlite
python -m paperlite.cli serve --host 127.0.0.1 --port 8768
```

Use `.env.example` as a template. Never commit a real `.env`, SQLite database, runtime cache, logs, or secret-bearing screenshots.

## Quality Gates

For most pull requests, run the narrowest checks that cover your change. Before asking for review, prefer:

```bash
cd paperlite
python -m pytest -q
ruff check paperlite tests
python -m compileall paperlite
python -m paperlite.cli catalog validate --format markdown
```

Docs-only changes should at least run:

```bash
cd paperlite
python -m pytest tests/test_agent_handoff_docs.py -q
ruff check tests/test_agent_handoff_docs.py
```

## Source Catalog Changes

For new or changed sources:

- Prefer adding ordinary feed/API sources through the catalog tooling with a dry run first.
- Keep source keys stable, lowercase, and descriptive.
- Keep crawls discipline scoped and source scoped.
- Do not add fragile screen scraping when a feed, API, or stable metadata endpoint exists.
- Do not add PDF or full-text fetching.

Useful checks:

```bash
cd paperlite
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

## Pull Request Checklist

- Explain the user-facing change and why it belongs in PaperLite.
- Keep diffs focused. Avoid unrelated refactors.
- Update docs and tests when behavior, routes, tools, manifests, schemas, or source catalog contracts change.
- Preserve backward compatibility unless the PR clearly documents a migration.
- Confirm no real secrets, `.env` values, local database files, runtime cache, or private paths are included.

## Getting Help

Open an issue with the closest template:

- Bug report for broken behavior.
- Source request for new or failing scholarly sources.
- Feature request for product or workflow proposals.

