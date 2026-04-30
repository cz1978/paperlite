# PaperLite 中文说明

PaperLite 是一个自托管的论文元数据工作台。它把已配置的学术来源抓取到本地 SQLite，让你在 `/daily` 里按学科、来源、日期和关键词筛选，做翻译、AI 筛选、元数据 RAG、导出和 Zotero 元数据同步。

PaperLite 的边界很明确：不下载 PDF，不读取全文，不在页面加载时自动抓取，不在页面加载时自动调用 LLM 或 RAG。所有外部网络抓取都需要你明确选择学科后手动触发，或通过你配置的计划任务触发。

## 快速开始

多数人只需要 Docker Compose：

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
test -f .env || cp .env.example .env
docker compose up -d --build
```

打开：

```text
http://127.0.0.1:8000/daily
```

如果你在 Windows 上，就手动把 `.env.example` 复制成 `.env` 一次，然后照样运行 `docker compose up -d --build`。如果你已经有 `.env`，不要覆盖。真实 API key 只放在本地 `.env`，不要提交到 GitHub。

## 第一次抓取

1. 打开 `/daily`。
2. 点 `学科：全部`，选择一个学科，点 `完成`。
3. 可选：点 `来源：全部`，缩小来源范围。
4. 点 `抓取`。
5. 抓取结束后点 `刷新`，或直接用页面筛选当前本地缓存。

如果抓取完成但 0 条，不一定是故障。常见原因是日期窗口没有新元数据、来源临时不可用、上游超时。去 `/ops` 看运行状态和来源警告，再决定是否放宽日期或换来源。

## 本地 Python 运行

```bash
cd paperlite
python -m pip install -e ".[dev]"
python -m paperlite.cli serve --host 127.0.0.1 --port 8768
```

打开：

```text
http://127.0.0.1:8768/daily
http://127.0.0.1:8768/ops
```

仓库根目录也保留了部署工具常用入口：

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## LLM 和密钥安全

LLM 是可选功能。普通浏览、抓取、筛选、导出和 Zotero fallback 不需要 LLM key。

不是 4 个 API 都要填。常用情况只填一个 key。

DeepSeek 最简配置：

```env
DEEPSEEK_API_KEY=
```

填了 `DEEPSEEK_API_KEY` 后，PaperLite 会默认使用 `https://api.deepseek.com` 和 `deepseek-chat`。

其他 OpenAI-compatible 服务才需要这一组：

```env
PAPERLITE_LLM_API_KEY=
PAPERLITE_LLM_BASE_URL=
PAPERLITE_LLM_MODEL=
```

`PAPERLITE_LLM_BASE_URL` 是服务地址，`PAPERLITE_LLM_MODEL` 是模型名，它们不是 API key。`PAPERLITE_LLM_API_KEY` 会优先于 `DEEPSEEK_API_KEY`。

公开仓库只包含空的 `.env.example`。不要把真实 `.env` 推到 GitHub。当前 Docker Compose 默认只绑定 `127.0.0.1:8000`；如果要公网部署，请放在 Caddy、Nginx、Cloudflare Tunnel、Tailscale 等鉴权层后面，否则别人可能通过你的服务消耗 LLM 额度。

## 常用入口

- `/daily`：论文元数据工作台。
- `/ops`：运行状态、来源健康、抓取历史和诊断。
- `/sources`：来源目录。
- `/endpoints`：抓取端点目录。
- `/daily/export`：导出 RIS、BibTeX、Markdown、JSON、JSONL、RSS。
- `/agent/rag/index`、`/agent/ask`：手动元数据 RAG。
- `/zotero/status`、`/zotero/items`、`/zotero/export`：Zotero 元数据流。

## Agent 安装和使用

PaperLite 给 agent 的入口有两种：MCP 和 HTTP API。agent 不访问 `/daily` 网页，`/daily` 是给人看的。

### MCP 模式

OpenClaw、QClaw、Hermes 或其他 agent 支持 stdio MCP server 时，用这个方式。

安装 PaperLite MCP 依赖：

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
python -m pip install -e ".[mcp]"
```

在 agent 的 MCP 配置里加入：

```json
{
  "mcpServers": {
    "paperlite": {
      "command": "python",
      "args": ["-m", "paperlite.mcp_server"],
      "cwd": "<repo>/paperlite"
    }
  }
}
```

常用工具：

- `paper_sources`
- `paper_rag_index`
- `paper_ask`
- `paper_filter`
- `paper_translate`
- `paper_zotero_status`
- `paper_zotero_items`

### HTTP API 模式

agent 能调用 HTTP 接口时，用这个方式。先启动 PaperLite：

```bash
docker compose up -d --build
```

agent 和 PaperLite 在同一台机器时，服务地址填：

```text
http://127.0.0.1:8000
```

agent 在另一台机器或云端时，填你的公网反代地址，例如：

```text
https://your-domain.example
```

常用 JSON 接口：

- `GET /daily/cache?format=json`
- `GET /sources`
- `POST /agent/rag/index`
- `POST /agent/ask`
- `POST /agent/filter`
- `POST /agent/translate`

支持能力发现的 agent 可以读取：

```text
GET /agent/manifest
```

如果你用本地 Python 运行，把端口改成 `8768`。

## 常用检查

```bash
cd paperlite
python -m pytest -q
python -m compileall paperlite
ruff check paperlite tests
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli endpoints health --source arxiv_cs_lg --timeout 15 --format markdown
```

## 数据位置

- 默认运行数据在 `.paperlite/`，已被 Git 忽略。
- SQLite 存论文元数据缓存、抓取记录、收藏/已读状态、保存视图、翻译缓存和本地偏好信号。
- PaperLite 只处理元数据和外部链接，不缓存 PDF 或全文。
