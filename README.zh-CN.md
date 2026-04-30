# PaperLite 中文说明

PaperLite 是给科研人用的本地优先论文元数据工作台：每天打开 `/daily`，选学科和来源，把新论文元数据抓到 SQLite，再筛选、翻译、导出或同步到 Zotero。

当前版本：`0.2.7`。更新记录见 [CHANGELOG.md](CHANGELOG.md)。

第一次几分钟就能做：

- 用 Docker Compose 启动；
- 打开 `/daily`，选一个学科，抓一个小范围来源；
- 按日期、来源、学科、关键词筛论文；
- 导出 RIS、BibTeX、Markdown、JSON、JSONL 或 RSS；
- 可选接入 Zotero、LLM 筛选、翻译和元数据 RAG。

普通浏览、抓取、筛选、导出都不需要 API key。只有你主动使用 LLM、embedding 或 Zotero 同步时，才需要在本地 `.env` 里填密钥。

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

PaperLite 给 agent 的入口有两种：MCP 和 HTTP API。agent 不访问 `/daily` 网页，`/daily` 是给人看的。`/daily/crawl`、`/daily/cache` 是 HTTP 模式下的 JSON API，不是让 agent 操作网页前端。

如果是 skill 型 agent 或技能市场，先读 [`SKILL.md`](SKILL.md)。它是短的 agent 入口说明；README 是给人看的完整说明。

默认走 MCP 不需要 Docker。agent 会把 `python -m paperlite.mcp_server` 当成本地 stdio 进程启动；它会读取本地 `.env`，元数据写本地 SQLite。只有走 HTTP API，或者人要打开 `/daily` 网页时，才需要 Docker 或其他 Web 服务启动方式。

默认 agent 用法：普通自然语言请求先调用 `paper_research` 或 `POST /agent/research`，例如“看一下今天关于材料的文章”。它会确定学科、检查当天 SQLite 缓存；如果该学科今天还没有缓存，会执行一次明确的学科抓取，并默认请求 `research_card_cn` brief 翻译，然后返回论文、数量、抓取 warning 和 `result_contract`；缺失的 brief 字段由宿主 agent 用自己的大模型生成答案并补齐。`paper_agent_context` 或 `POST /agent/context` 只在 explain/filter/ask 这类需要构造 messages 的场景使用。

agent 抓取不要打开 `/daily`，也不要用 `/daily` 链接当最终答案。优先走 MCP 工具；普通主题请求直接 `paper_research(topic="材料", date="<today>")`，再根据返回的 scope、papers、count、warning 和 next_actions 回复。最终回复要直接给论文标题、来源、日期、链接和筛选理由。只有手动排错、指定来源、指定 run，或 MCP 不可用时，才用 `paper_sources`、`paper_crawl`、`paper_crawl_status`、`paper_cache` 或 `POST /daily/crawl` 这类 HTTP JSON API。

agent 输出规则：用户当次 prompt 优先。用户没有指定其他格式时，抓取、整理、筛选或排序后，必须先说明本次范围：学科、来源 key/来源名、日期范围、关键词 q、run 状态、warning 和总数。然后发真实论文清单。15 篇以内要全列，每篇至少给标题、来源/期刊、日期、URL/DOI、筛选理由、简短中文译名和一句中文摘要/要点。中文 brief 里的标题要中英都在，也要有身份号：先给中文题目，优先使用 `paper.display_title`、`paper.title_zh` 或 `paper.brief_translation.title_zh`；再给英文原题，使用 `paper.title_original` 或 `paper.title_en`；再给 `paper.identifier_label` + `paper.identifier`，用于 DOI、arXiv、PMID、PMCID、OpenAlex 或本地 ID。如果中文题目为空或未配置，宿主 agent 必须先把 `paper.title_original` 翻译成中文再展示，不能只把英文 `paper.title` 当标题行。中文 brief 优先使用 `paper.brief_translation.cn_flash_180`；如果为空或未配置，宿主 agent 仍必须基于返回的标题和摘要补出一句中文要点。如果超过 15 篇，只先列最多 15 篇，说明还剩多少篇，并询问用户要不要 AI 优化排序，或者追加搜索关键词继续筛选。如果元数据里没有 abstract，要写“摘要未提供”，再给基于标题/元数据的简短要点。亮点总结只能放在清单后面，不能代替清单。

PaperLite 自己的 LLM、AI 筛选或 brief 翻译未配置，不代表 QClaw、Hermes、OpenClaw 这类宿主 agent 不能继续；宿主 agent 要用自己的模型基于返回元数据完成排序、摘要和中文 brief。不要说缓存论文丢失、数据库重建、重装/reset，除非 PaperLite 工具明确返回了这个事实。

如果你的 agent 支持从 GitHub 拉取并部署项目，直接说这一句就行：

```text
https://github.com/cz1978/paperlite/ 把项目拉下来部署了
```

只有需要 HTTP API 或 `/daily` 网页时，才用这条 Docker 命令：

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && ([ -f .env ] || cp .env.example .env) && docker compose up -d --build
```

### MCP 模式

OpenClaw、QClaw、Hermes 或其他 agent 支持 stdio MCP server 时，用这个方式。

MCP 模式不需要 Docker。

一行安装 MCP 依赖：

```bash
git clone https://github.com/cz1978/paperlite.git paperlite && cd paperlite && python -m pip install -e ".[mcp]"
```

如果已经 clone 过：

```bash
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
- `paper_research`
- `paper_crawl`
- `paper_crawl_status`
- `paper_cache`
- `paper_agent_context`
- `paper_rag_index`
- `paper_ask`
- `paper_filter`
- `paper_translate`
- `paper_zotero_status`
- `paper_zotero_items`
- `paper_zotero_export`

agent 典型流程：

1. 普通自然语言请求先 `paper_research(topic="<主题>", date="<today>")`。
2. 有 `papers` 时，先给真实论文清单：标题、来源、日期、链接、筛选理由、简短中文译名和一句中文摘要/要点。
3. `remaining_count > 0` 时，只列返回的最多 15 篇，并询问要 AI 优化排序还是加关键词继续筛选。
4. 有 `warnings` 或 `crawl.source_warnings` 时，必须说明，不要假装完整成功。
5. 只有排错、指定来源或指定 run 时，才手动用 `paper_sources`、`paper_crawl`、`paper_crawl_status`、`paper_cache`。
6. 完整翻译只有用户明确要求时才做；只有用户要问答时才 RAG；只有用户要保存时才走 Zotero。

Zotero 用法：

1. 先 `paper_zotero_status()`。
2. 已配置就 `paper_zotero_items([论文元数据])` 同步到 Zotero。
3. 未配置或用户想手动导入，就 `paper_zotero_export([论文元数据], format="ris")` 或 `format="bibtex"`，把返回的内容给用户导入 Zotero。
4. 真同步需要本地 `.env` 填 `ZOTERO_API_KEY`、`ZOTERO_LIBRARY_TYPE`、`ZOTERO_LIBRARY_ID`，可选 `ZOTERO_COLLECTION_KEY`。
5. Zotero 只处理元数据，不上传 PDF 或全文。

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

- `POST /agent/context`
- `POST /agent/research`
- `GET /sources`
- `POST /daily/crawl`
- `GET /daily/crawl/{run_id}`
- `GET /daily/cache?format=json`
- `GET /daily/export?format=markdown`
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
