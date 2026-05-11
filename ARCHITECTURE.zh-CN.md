# 架构说明

English version: [ARCHITECTURE.md](ARCHITECTURE.md)

PaperLite 围绕一个原则组织：外部工作必须明确触发，本地阅读默认 cache-first。

## 数据流

```text
YAML catalog
  -> 学科范围 crawl
  -> SQLite 元数据缓存
  -> /daily, REST, MCP, CLI
  -> export, Zotero 元数据, 可选 metadata-only RAG
```

来源目录保存在可 review 的 YAML 文件里：`sources.yaml`、`endpoints.yaml`、`taxonomy.yaml` 和 `profiles.yaml`。抓取任务读取这些目录，从选择的来源抓取论文元数据，并写入 SQLite。

## 运行入口

- `/daily` 是给人看的研究工作台。页面加载、筛选、分页、导出和复核都读 SQLite。
- `/ops` 展示运行历史、schedule、来源健康、doctor 检查和 catalog 状态。
- REST 端点给 HTTP agent 和集成使用。
- MCP 工具是默认 agent 接入路径。
- CLI 命令支持本地维护、catalog 检查、RAG 和服务启动。

## 存储

SQLite 存储：

- 论文元数据缓存；
- crawl run 和 source run 结果；
- schedules；
- 收藏、已读、隐藏等 library state；
- saved views 和偏好信号；
- 翻译缓存；
- Research Missions、mission run 摘要和 mission 级已见论文记忆。

Run history 只保存轻量摘要和 paper IDs。完整论文元数据仍保存在现有 cache 表里。

## Agent 流程

普通研究请求应该调用 `paper_research`。长期关注方向应该使用 Research Missions：`paper_mission_save`、`paper_missions`、`paper_mission_run` 和 `paper_mission_delete`。

Agent 应该直接返回真实论文列表、scope、warnings 和 next actions，不要用 `/daily` 链接当结果。

## AI 和 RAG 边界

LLM 筛选、翻译、embedding 和 RAG 都是可选功能。它们需要用户明确操作或 agent 明确调用工具。Metadata RAG 只索引缓存元数据：标题、摘要、作者、标识符、DOI、URL、来源、venue 和相关元数据。

## 硬边界

- 不下载、缓存、代理、上传或解析 PDF/全文。
- 不在页面加载时隐藏执行 crawl、LLM、embedding、source audit、health check 或 RAG。
- 不默认全来源抓取。
- 不把新工作接到旧 `app/`、旧 `/v1` 路由、旧 worker 或旧数据库表。

