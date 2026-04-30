# Source Catalog Maintenance

PaperLite keeps source identity and retrieval paths in YAML. SQLite is runtime cache/state, not the source directory.

## Current Snapshot

- Source IDs exposed by `/sources`: 814
- Endpoint IDs exposed by `/endpoints`: 814
- Source identity definitions in `paperlite/sources.yaml`: 814
- Retrieval definitions in `paperlite/endpoints.yaml`: 814
- Direct feed/API endpoints loadable by the generic runner: 669
- Built-in API-backed sources: arXiv, bioRxiv, medRxiv, ChemRxiv, OpenAlex, Crossref, PubMed, Europe PMC, and Semantic Scholar
- Default daily profiles remain curated; `/daily` manual and scheduled crawls require a selected discipline and only fetch latest-capable sources within that discipline.

## Provenance

- The import batch uses curated source URLs from repository CSV/SQL files as source-only metadata. The imported pool contains 797 valid unique URL candidates after dropping an invalid SQL placeholder.
- Imported source fields are limited to source ID, name, provider, type, tier, topics, and origin.
- Imported endpoint fields are limited to endpoint ID, source ID, direct feed/API URL, mode, provider, status, and method/format.
- Runtime code from prior loaders, SQL migrations, database tables, workers, jobs, fetch history, and scheduling chains is not imported.

## Files

- `paperlite/paperlite/sources.yaml`: source key, name, source kind, publisher, homepage, discipline, status, and provenance.
- `paperlite/paperlite/endpoints.yaml`: RSS/Atom/API/manual endpoint key, source key, URL/provider, mode, status, priority, and fetch settings.
- `paperlite/paperlite/taxonomy.yaml`: stable disciplines, areas, source kinds, and aliases.
- `paperlite/paperlite/profiles.yaml`: curated source groups for `/daily` and scheduled crawls.

## Validate

```bash
cd paperlite
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
```

Validation catches broken YAML structure, invalid keys, unknown source references, unsupported endpoint modes/source kinds, unknown disciplines, active feed endpoints without URLs, and unclear disabled/unavailable states.

## Add A Feed Source

Dry-run first:

```bash
python -m paperlite.cli catalog add-source \
  --key example_journal \
  --name "Example Journal" \
  --kind journal \
  --discipline Chemistry \
  --publisher "Example Publisher" \
  --url https://example.com/rss.xml
```

Apply only after reviewing the generated YAML:

```bash
python -m paperlite.cli catalog add-source \
  --key example_journal \
  --name "Example Journal" \
  --kind journal \
  --discipline Chemistry \
  --publisher "Example Publisher" \
  --url https://example.com/rss.xml \
  --write
```

The helper covers ordinary `rss`, `atom`, and `feed` endpoints. API-backed sources still need connector code.

## Audit Existing Sources

Content audit samples metadata from endpoints without writing daily cache, fetching PDFs, or calling the LLM:

```bash
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
python -m paperlite.cli endpoints audit --all --limit 100 --sample-size 3 --write-snapshot --format json
```

The audit flags fetch failures, zero items, missing DOI/title/URL/date/abstract, and duplicate-heavy samples. `/ops/source-audit` and `/ops/status` read the latest runtime snapshot from `.paperlite/`.

## Status Rules

- `active`: expected to work.
- `candidate`: discovered but not fully verified.
- `temporarily_unavailable`: known blocked, broken, or unreliable.
- `enabled: false` should be paired with a non-active status.

Do not add broad all-source crawls. Manual and scheduled crawls stay discipline scoped.

## External References

- [`sg-s/science-journal-feeds`](https://github.com/sg-s/science-journal-feeds) is a public-domain open-source catalog of 4700+ academic RSS/Atom feeds. It is a good future source for selective imports, not something PaperLite should ingest wholesale by default.
- RSSHub can be considered for sites without stable first-party RSS, but PaperLite should prefer official publisher/preprint feeds when available.

## Import Rule

Add sources gradually and keep source/endpoint separate:

- New research object: add it to `sources.yaml`.
- Direct RSS/Atom/API URL available: add it to `endpoints.yaml`.
- Only a directory/manual page/OPML exists: add a `manual` endpoint or keep as a candidate until a direct feed URL is known.
- Fetch fails at runtime: show a per-source warning and let other selected sources continue.
- Full text or PDF is available: expose `url` or `pdf_url` only; PaperLite still does not download or parse it.
