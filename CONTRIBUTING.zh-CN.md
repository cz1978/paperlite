# 贡献 PaperLite

谢谢你愿意帮 PaperLite 变得更好。PaperLite 是一个本地优先的论文元数据工作台，所以小而清楚、带测试的改动比大范围重写更合适。

English version: [CONTRIBUTING.md](CONTRIBUTING.md)

## 项目边界

请保持这些边界不变：

- PaperLite 只处理论文元数据，不处理 PDF 或全文。
- 页面加载、刷新、筛选、分页、导出和相关论文浏览只读 SQLite。
- 外部抓取只能通过明确的学科范围 crawl 或到期 schedule 触发。
- 不要把全来源抓取设为默认行为。
- 不要在页面加载时隐藏执行 LLM、embedding、source audit、health check、crawl 或 RAG。
- Agent 工作流应该用 MCP 工具或 JSON 端点，不要操作给人看的 `/daily` UI。
- 不要把新工作接到旧 `app/`、旧 `/v1` 路由、旧 worker 或旧数据库表上。

## 本地开发

```bash
git clone https://github.com/cz1978/paperlite.git paperlite
cd paperlite
python -m pip install -e "paperlite[dev]"
```

从仓库根目录启动 Web 服务：

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

或使用包内命令：

```bash
cd paperlite
python -m paperlite.cli serve --host 127.0.0.1 --port 8768
```

`.env.example` 只是模板。不要提交真实 `.env`、SQLite 数据库、运行缓存、日志或包含密钥/私有路径的截图。

## 质量检查

大多数 PR 应该先跑覆盖改动路径的最小检查。提交评审前建议：

```bash
cd paperlite
python -m pytest -q
ruff check paperlite tests
python -m compileall paperlite
python -m paperlite.cli catalog validate --format markdown
```

纯文档改动至少跑：

```bash
cd paperlite
python -m pytest tests/test_agent_handoff_docs.py -q
ruff check tests/test_agent_handoff_docs.py
```

## 来源目录贡献

新增或修改来源时：

- 优先用 catalog 工具 dry run 生成普通 feed/API 来源。
- source key 保持稳定、小写、可读。
- crawl 保持学科范围和来源范围。
- 有 feed、API 或稳定 metadata endpoint 时，不要加脆弱的网页抓取。
- 不要加入 PDF 或全文抓取。

常用检查：

```bash
cd paperlite
python -m paperlite.cli catalog validate --format markdown
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

## PR Checklist

- 说明用户可见变化，以及为什么适合 PaperLite。
- 保持 diff 聚焦，避免无关重构。
- 改行为、路由、工具、manifest、schema 或来源目录契约时，同时更新文档和测试。
- 除非清楚写明迁移方式，否则保持兼容。
- 确认没有真实密钥、`.env` 值、本地数据库、运行缓存或私有路径。

## 获取帮助

请选择最接近的问题模板：

- Bug report：功能异常。
- Source request：新增来源或来源失效。
- Feature request：产品或工作流建议。

