# 路线图

English version: [ROADMAP.md](ROADMAP.md)

PaperLite 是本地优先的学术元数据工作台。路线图优先考虑明确、可检查的工作流，而不是隐藏自动化。

## v0.3：Research Missions

v0.3 的核心方向是 agent-first 的长期研究雷达：

- 持久保存 Research Mission，包括 topic、学科、来源、include/exclude/prefer terms 和 instructions；
- 通过 MCP 或 REST 运行 mission radar；
- 记住 mission 级别的已见论文；
- 返回新增论文、重要论文、排除摘要、主题信号、warning 和下一步建议；
- mission run 保持 cache-first 和 metadata-only。

## 后续方向

- 让 agent 和人类更容易创建 mission，但不把它变成页面加载自动抓取。
- 基于元数据和 run history 改进 mission 级摘要和主题变化信号。
- 可选地把 mission 和 schedule 关联，同时保持明确 scope 和本地控制。
- 改进来源维护、endpoint 诊断和 catalog 贡献体验。
- 打磨 `/daily` 的重复使用体验：分组更清楚、视觉密度更低、空状态更好。
- 让元数据导出和 Zotero 工作流更可靠、更容易验证。

## 非目标

- 不下载、缓存、代理、上传或解析 PDF/全文。
- 不做隐藏的全来源抓取。
- 不在页面加载时执行 crawl、LLM、embedding、source audit、health check 或 RAG。
- 默认开源运行时不内置公网认证/密码层。
- 不替代 Zotero、arXiv、Crossref、OpenAlex 或出版社网站。

## 可贡献方向

- 用可复现 catalog 检查新增或修复来源 endpoint。
- 改进 MCP agent 文档和示例。
- 为 mission scoring、storage、source warnings 和 export payload 增加聚焦测试。
- 在不改变 cache-first 契约的前提下改进 `/daily` 的可访问性和信息密度。

