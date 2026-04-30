# PaperLite Current State

PaperLite is in launch-cleanup mode. The active product is the self-hosted `/daily` research metadata workbench with local SQLite state, optional explicit LLM actions, Zotero metadata export, and `/ops` diagnostics.

This file is a short status pointer, not a second product contract:

- Start here for setup and first-run workflow: `README.md`.
- Use `paperlite/README.md` for package CLI, REST, MCP, LLM, Zotero, and model reference.
- Use `paperlite/PROJECT_OVERVIEW.md` for the architecture map and module ownership.
- Use `AGENTS.md` for agent constraints and active runtime boundaries.
- Use `SOURCES.md` for source catalog counts, provenance, validation, and maintenance.

## Runtime Data

`.paperlite/` is runtime-only and ignored by Git. It may contain SQLite, source audit snapshots, endpoint health snapshots, and local logs. These files are not part of the open-source source tree.

## Verification

```bash
cd paperlite
python -m pytest -q
python -m compileall paperlite
ruff check paperlite tests
python -m paperlite.cli doctor --format json
python -m paperlite.cli sources --format markdown
python -m paperlite.cli catalog validate --format markdown
```
