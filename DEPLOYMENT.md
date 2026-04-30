# PaperLite Deployment

PaperLite is designed for owner-operated self-hosting. It does not ship a default login system; put public deployments behind Caddy, Nginx, Cloudflare Tunnel, Tailscale, or another reverse proxy if you need access control.

## Local

```bash
cd paperlite
python -m pip install -e ".[dev]"
python -m paperlite.cli serve --host 127.0.0.1 --port 8768
```

Open `http://127.0.0.1:8768/daily`.

From the repository root, the compatibility entrypoint is:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## Docker Compose

From a GitHub checkout, this is the intended local machine or VPS path with Docker installed:

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
test -f .env || cp .env.example .env
docker compose up -d --build
```

On Windows, create `.env` from `.env.example` once, then run the same Docker Compose command from your shell. Keep an existing `.env` if you already configured one.

The compose file mounts `./.paperlite:/data` and binds the app to `127.0.0.1:8000`. Open `http://127.0.0.1:8000/daily` after the container starts. For public access, keep the app behind reverse proxy authentication.

Before publishing or copying a deployment folder, keep `.env` out of Git and rotate any real keys that were present in local files or terminal history.

## systemd

Use `deploy/systemd/paperlite.service` as a template. Adjust `WorkingDirectory`, `EnvironmentFile`, `ExecStart`, and the Unix user/group, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now paperlite
sudo systemctl status paperlite
```

## Runtime Data

- `PAPERLITE_DB_PATH`: SQLite database for cache, library, preferences, schedules, and translations.
- `PAPERLITE_HEALTH_SNAPSHOT_PATH`: optional endpoint health snapshot path.
- `PAPERLITE_SOURCES_PATH`, `PAPERLITE_ENDPOINTS_PATH`, `PAPERLITE_TAXONOMY_PATH`, `PAPERLITE_PROFILES_PATH`, `PAPERLITE_TRANSLATION_PROFILES_PATH`: optional catalog and translation-template overrides.
- `DEEPSEEK_API_KEY` or `PAPERLITE_LLM_*`: optional OpenAI-compatible LLM settings.
- `PAPERLITE_EMBEDDING_*`: optional OpenAI-compatible embedding settings for explicit metadata RAG.
- `ZOTERO_*`: optional Zotero metadata sync.

PaperLite stores paper metadata and external links only. It does not download PDFs or full text.

## Operational Checks

```bash
curl http://127.0.0.1:8000/ops/status
curl http://127.0.0.1:8000/ops/doctor
python -m paperlite.cli doctor --format markdown
python -m paperlite.cli sources --format markdown
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

`/ops` reads the latest snapshots. It does not automatically run source audit, health checks, crawls, or LLM calls on page load.
