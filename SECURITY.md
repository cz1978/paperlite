# Security Policy

Chinese version: [SECURITY.zh-CN.md](SECURITY.zh-CN.md)

## Supported Versions

Security fixes are handled for `main` and the latest GitHub release. Older releases do not receive guaranteed backports unless the maintainers explicitly say so in a release note.

## Reporting a Vulnerability

Please report security issues through GitHub Security Advisories for this repository. Do not open a public issue for secrets, authentication bypasses, remote execution risks, or data exposure reports.

Include:

- affected version or commit;
- deployment mode, such as Docker Compose, local Python, systemd, MCP-only, or reverse-proxy setup;
- steps to reproduce;
- impact and whether credentials, `.env`, SQLite data, or Zotero/LLM keys may be exposed;
- any safe proof of concept that does not expose third-party data or real secrets.

## Secrets and Local Data

PaperLite is local-first, but optional integrations can use sensitive credentials. Keep these out of public issues, screenshots, and pull requests:

- `.env` and `paperlite/.env`;
- `DEEPSEEK_API_KEY`, `PAPERLITE_LLM_*`, `PAPERLITE_EMBEDDING_*`;
- `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_ID`, `ZOTERO_COLLECTION_KEY`;
- SQLite databases, logs, runtime caches, and exported local preference data;
- private reverse-proxy URLs, hostnames, and local filesystem paths when they reveal user identity.

If a real key was committed or shared publicly, rotate it at the provider before opening an issue.

## Deployment Notes

- The default Docker Compose file binds PaperLite to `127.0.0.1`.
- Public deployments should sit behind an authentication layer such as a reverse proxy, VPN, tunnel, or private network.
- PaperLite does not ship public auth as the default open-source runtime.
- Do not expose a service configured with LLM, embedding, or Zotero credentials without access control.

## Project Boundaries

PaperLite should not download, cache, proxy, upload, or parse PDFs or full text. It should not perform hidden crawl, LLM, embedding, source audit, health check, or RAG work on page load.

