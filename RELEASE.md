# Release Checklist

Chinese version: [RELEASE.zh-CN.md](RELEASE.zh-CN.md)

Use this checklist before tagging a PaperLite release.

## Prepare

- Confirm the release scope is documented in `CHANGELOG.md`.
- Update `paperlite/pyproject.toml` only when publishing a package/runtime version.
- Update `README.md`, `README.zh-CN.md`, and agent docs when public behavior changes.
- Keep `.env`, SQLite files, runtime caches, logs, and screenshots with private paths out of the release.

## Verify

```bash
cd paperlite
python -m pytest -q
ruff check paperlite tests
python -m compileall paperlite
python -m paperlite.cli catalog validate --format markdown
```

For release hygiene from the repository root:

```bash
git diff --check
docker build -t paperlite-release-smoke:local .
```

Optional source checks:

```bash
cd paperlite
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

## Secret Check

- Search changed files for real keys, tokens, private URLs, local paths, and SQLite files.
- Rotate any key that was ever committed or shared publicly.
- Confirm screenshots show empty or non-sensitive local data.

## Tag and Publish

```bash
git status --short
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

Create a GitHub Release from the tag and paste the relevant `CHANGELOG.md` section. Do not move an already published tag.

## After Release

- Smoke the documented install path.
- Confirm `/agent/manifest` and OpenAPI report the intended version.
- Check that the latest release is clear in README and changelog.

