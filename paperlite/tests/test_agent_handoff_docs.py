import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agent_handoff_docs_cover_current_runtime():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    skill_doc = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    package_readme = (ROOT / "paperlite" / "README.md").read_text(encoding="utf-8")
    overview = (ROOT / "paperlite" / "PROJECT_OVERVIEW.md").read_text(encoding="utf-8")
    sources_doc = (ROOT / "SOURCES.md").read_text(encoding="utf-8")
    source_catalog_pointer = (ROOT / "paperlite" / "SOURCE_CATALOG.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((ROOT / "paperlite" / "pyproject.toml").read_text(encoding="utf-8"))

    assert "PaperLite Agent Handoff" in agents
    assert "python -m uvicorn main:app" in agents
    assert "/daily/cache?format=json" in agents
    assert "/daily/export?format=ris|bibtex|markdown|json|jsonl|rss" in agents
    assert "python -m paperlite.cli rag index" in agents
    assert "python -m paperlite.cli rag ask" in agents
    assert "GET /daily/related" in agents
    assert "must not crawl sources, visit paper URLs, read PDFs, parse full text, or call chat LLMs" in agents
    assert "Do not auto-index or auto-ask RAG on page load" in agents
    assert "catalog coverage" in agents
    assert "Do not wire new work into old" in agents

    assert "## At A Glance" in readme
    assert "local-first paper metadata workbench for researchers" in readme
    assert "Current release: `0.2.0`" in readme
    assert "[CHANGELOG.md](CHANGELOG.md)" in readme
    assert "In the first few minutes, you can:" in readme
    assert "No API key is required for browsing, crawling, filtering, export" in readme
    assert "SQLite-first browsing" in readme
    assert "## Quality Gates" in readme
    assert "## Agent Setup" in readme
    assert "no silent network calls" in readme
    assert "CLI RAG" in readme
    assert "Related cached papers" in readme
    assert "python -m paperlite.cli sources --format markdown" in readme
    assert "test -f .env || cp .env.example .env" in readme
    assert "Most users only need Docker Compose" in readme
    assert "do not overwrite an existing `.env`" in readme
    assert "Click `学科：全部`" in readme
    assert "Click `抓取`" in readme
    assert "Crawl completed with 0 items" in readme
    assert "[中文说明](README.zh-CN.md)" in readme
    assert "Agents should not use `/daily`; that page is the human UI" in readme
    assert "[`SKILL.md`](SKILL.md)" in readme
    assert "Default agent workflow: call `paper_agent_context` or `POST /agent/context`" in readme
    assert "host agent's own model" in readme
    assert "this prompt is enough" in readme
    assert "https://github.com/cz1978/paperlite/ 把项目拉下来部署了" in readme
    assert "Fallback shell deploy command" in readme
    assert "([ -f .env ] || cp .env.example .env) && docker compose up -d --build" in readme
    assert "### MCP Mode" in readme
    assert "OpenClaw, QClaw, Hermes" in readme
    assert "One-line MCP install" in readme
    assert 'git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && python -m pip install -e ".[mcp]"' in readme
    assert "python -m pip install -e \".[mcp]\"" in readme
    assert '"command": "python"' in readme
    assert '"args": ["-m", "paperlite.mcp_server"]' in readme
    assert '"cwd": "<repo>/paperlite"' in readme
    assert "`paper_agent_context`" in readme
    assert "`paper_sources`" in readme
    assert "`paper_ask`" in readme
    assert "### HTTP API Mode" in readme
    assert "docker compose up -d --build" in readme
    assert "Agent base URL on the same machine" in readme
    assert "http://127.0.0.1:8000" in readme
    assert "Useful JSON endpoints" in readme
    assert "POST /agent/context" in readme
    assert "GET /daily/cache?format=json" in readme
    assert "POST /agent/ask" in readme
    assert "Optional discovery endpoint" in readme
    assert "GET /agent/manifest" in readme
    assert "stdio MCP server" in readme

    assert "PaperLite 中文说明" in readme_zh
    assert "给科研人用的本地优先论文元数据工作台" in readme_zh
    assert "当前版本：`0.2.0`" in readme_zh
    assert "[CHANGELOG.md](CHANGELOG.md)" in readme_zh
    assert "第一次几分钟就能做" in readme_zh
    assert "普通浏览、抓取、筛选、导出都不需要 API key" in readme_zh
    assert "git clone https://github.com/cz1978/paperlite.git paperlite" in readme_zh
    assert "test -f .env || cp .env.example .env" in readme_zh
    assert "多数人只需要 Docker Compose" in readme_zh
    assert "手动把 `.env.example` 复制成 `.env` 一次" in readme_zh
    assert "点 `学科：全部`" in readme_zh
    assert "点 `抓取`" in readme_zh
    assert "不要把真实 `.env` 推到 GitHub" in readme_zh
    assert "不是 4 个 API 都要填" in readme_zh
    assert "DeepSeek 最简配置" in readme_zh
    assert "`PAPERLITE_LLM_BASE_URL` 是服务地址" in readme_zh
    assert "不下载 PDF" in readme_zh
    assert "不在页面加载时自动调用 LLM 或 RAG" in readme_zh
    assert "127.0.0.1:8000" in readme_zh
    assert "## Agent 安装和使用" in readme_zh
    assert "agent 不访问 `/daily` 网页" in readme_zh
    assert "[`SKILL.md`](SKILL.md)" in readme_zh
    assert "默认 agent 用法：调用 `paper_agent_context` 或 `POST /agent/context`" in readme_zh
    assert "宿主 agent 用自己的大模型生成答案" in readme_zh
    assert "直接说这一句就行" in readme_zh
    assert "https://github.com/cz1978/paperlite/ 把项目拉下来部署了" in readme_zh
    assert "如果平台要求 shell 命令，再用这条兜底" in readme_zh
    assert "([ -f .env ] || cp .env.example .env) && docker compose up -d --build" in readme_zh
    assert "### MCP 模式" in readme_zh
    assert "OpenClaw、QClaw、Hermes" in readme_zh
    assert "一行安装 MCP 依赖" in readme_zh
    assert '"command": "python"' in readme_zh
    assert '"args": ["-m", "paperlite.mcp_server"]' in readme_zh
    assert '"cwd": "<repo>/paperlite"' in readme_zh
    assert "常用工具" in readme_zh
    assert "`paper_agent_context`" in readme_zh
    assert "`paper_sources`" in readme_zh
    assert "`paper_ask`" in readme_zh
    assert "### HTTP API 模式" in readme_zh
    assert "agent 能调用 HTTP 接口时" in readme_zh
    assert "docker compose up -d --build" in readme_zh
    assert "服务地址填" in readme_zh
    assert "常用 JSON 接口" in readme_zh
    assert "POST /agent/context" in readme_zh
    assert "GET /daily/cache?format=json" in readme_zh
    assert "POST /agent/ask" in readme_zh
    assert "https://your-domain.example" in readme_zh
    assert "支持能力发现的 agent 可以读取" in readme_zh
    assert "GET /agent/manifest" in readme_zh
    assert "stdio MCP server" in readme_zh

    assert "name: paperlite" in skill_doc
    assert "local-first scholarly metadata workbench" in skill_doc
    assert "Default agent path: use `paper_agent_context` or `POST /agent/context`" in skill_doc
    assert "PaperLite's built-in LLM endpoints are optional fallback tools" in skill_doc
    assert "If the host can fetch and deploy GitHub repositories" in skill_doc
    assert "https://github.com/cz1978/paperlite/ 把项目拉下来部署了" in skill_doc
    assert "Fallback shell deploy command" in skill_doc
    assert "([ -f .env ] || cp .env.example .env) && docker compose up -d --build" in skill_doc
    assert "One-line MCP install from the GitHub repository" in skill_doc
    assert 'git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && python -m pip install -e ".[mcp]"' in skill_doc
    assert "python -m paperlite.mcp_server" in skill_doc
    assert "`paper_agent_context`" in skill_doc
    assert "POST /agent/context" in skill_doc
    assert "`paper_sources`" in skill_doc
    assert "`paper_ask`" in skill_doc
    assert "GET /daily/cache?format=json" in skill_doc
    assert "POST /agent/ask" in skill_doc
    assert "Treat `/daily` as the human web UI" in skill_doc
    assert "Do not download, cache, upload, or parse PDFs or full text" in skill_doc
    assert "DEEPSEEK_API_KEY=" in skill_doc

    assert "## 0.2.0 - 2026-04-30" in changelog
    assert "host-agent context mode" in changelog
    assert "## 0.1.0 - 2026-04-30" in changelog

    assert "## Design Shape" in package_readme
    assert "`daily_export.py` owns daily date resolution" in package_readme
    assert "`api.py` keeps FastAPI app creation" in package_readme
    assert "`storage.py` is an import-compatible SQLite facade" in package_readme
    assert "`frontend.py` loads package assets" in package_readme
    assert "python -m paperlite.cli rag index" in package_readme
    assert "python -m paperlite.cli rag ask" in package_readme
    assert "--source arxiv_cs_lg --q RAG" in package_readme
    assert "optional `q`" in package_readme
    assert "python -m paperlite.cli sources --format markdown" in package_readme
    assert "GET /daily/related" in package_readme
    assert "fill missing or stale vectors for local cached metadata" in package_readme
    assert "index automatically" in package_readme

    assert "paperlite/daily_export.py" in overview
    assert "paperlite/api_daily.py" in overview
    assert "paperlite/frontend_assets/daily.html" in overview
    assert "paperlite/storage_schema.py" in overview
    assert "## Design Principles" in overview
    assert "Keep network work explicit" in overview

    assert "## Current Snapshot" in sources_doc
    assert "Source IDs exposed by `/sources`: 814" in sources_doc
    assert "Direct feed/API endpoints loadable by the generic runner: 669" in sources_doc
    assert "Manual and scheduled crawls stay discipline scoped" in sources_doc
    assert "../SOURCES.md" in source_catalog_pointer

    assert "Docker Compose" in deployment
    assert "git clone https://github.com/cz1978/paperlite.git paperlite" in deployment
    assert "test -f .env || cp .env.example .env" in deployment
    assert "create `.env` from `.env.example` once" in deployment
    assert "docker compose up -d --build" in deployment
    assert "systemd" in deployment
    assert "PAPERLITE_DB_PATH" in deployment
    assert "PAPERLITE_TRANSLATION_PROFILES_PATH" in deployment
    assert "DEEPSEEK_API_KEY" in deployment
    assert "ZOTERO_*" in deployment
    assert "does not ship a default login system" in deployment
    assert "rotate any real keys" in deployment

    assert "Copy this file to .env" in env_example
    assert "reverse proxy auth layer" in env_example
    assert "PAPERLITE_TRANSLATION_PROFILES_PATH" in env_example
    assert "DeepSeek users only need DEEPSEEK_API_KEY" in env_example
    assert "Other providers use PAPERLITE_LLM_API_KEY plus base URL/model" in env_example

    project = pyproject["project"]
    assert "research" in project["keywords"]
    assert "Framework :: FastAPI" in project["classifiers"]
    assert project["urls"]["Repository"].startswith("https://github.com/")
    assert "ruff>=0.15" in project["optional-dependencies"]["dev"]


def test_deployment_templates_are_present_and_localhost_bound():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    service = (ROOT / "deploy" / "systemd" / "paperlite.service").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "paperlite-ci.yml").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "uvicorn" in dockerfile
    assert "PAPERLITE_DB_PATH=/data/paperlite.sqlite3" in dockerfile
    assert "AGENTS.md" not in dockerfile
    assert "127.0.0.1:8000:8000" in compose
    assert "./.paperlite:/data" in compose
    assert "EnvironmentFile=/opt/paperlite/.env" in service
    assert "main:app" in service
    assert "python -m paperlite.cli sources --format markdown" in ci
    assert "python -m paperlite.cli catalog validate --format markdown" in ci
    assert "docker build -t paperlite-ci-smoke:local ." in ci
    assert "ruff check paperlite tests" in ci
    assert "TODO.md" not in ci
    assert ".env" in dockerignore
    assert "TODO.md" in dockerignore
    assert "paperlite/tests/" in dockerignore
    assert ".env" in gitignore
    assert "TODO.md" in gitignore
