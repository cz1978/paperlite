# 安全策略

English version: [SECURITY.md](SECURITY.md)

## 支持版本

安全修复面向 `main` 和最新 GitHub Release。除非维护者在 release note 里明确说明，旧版本不承诺安全 backport。

## 报告漏洞

请通过本仓库的 GitHub Security Advisories 报告安全问题。涉及密钥、认证绕过、远程执行风险或数据暴露时，不要开公开 issue。

报告中请包含：

- 受影响版本或 commit；
- 部署方式，例如 Docker Compose、本地 Python、systemd、MCP-only 或反向代理；
- 复现步骤；
- 影响范围，以及是否可能暴露凭证、`.env`、SQLite 数据或 Zotero/LLM key；
- 不包含第三方数据或真实密钥的安全 proof of concept。

## 密钥和本地数据

PaperLite 是本地优先项目，但可选集成会使用敏感凭证。不要在公开 issue、截图或 PR 中包含：

- `.env` 和 `paperlite/.env`；
- `DEEPSEEK_API_KEY`、`PAPERLITE_LLM_*`、`PAPERLITE_EMBEDDING_*`；
- `ZOTERO_API_KEY`、`ZOTERO_LIBRARY_ID`、`ZOTERO_COLLECTION_KEY`；
- SQLite 数据库、日志、运行缓存和本地偏好数据导出；
- 会暴露身份的私有反代 URL、主机名和本地文件路径。

如果真实 key 已经提交或公开分享，请先去对应 provider 旋转密钥，再报告问题。

## 部署注意事项

- 默认 Docker Compose 只绑定 `127.0.0.1`。
- 公网部署应放在反向代理、VPN、tunnel 或私有网络等鉴权层后面。
- PaperLite 默认开源运行时不内置公网认证系统。
- 配置了 LLM、embedding 或 Zotero 凭证的服务不要无鉴权暴露。

## 项目边界

PaperLite 不应下载、缓存、代理、上传或解析 PDF/全文。页面加载时不应隐藏执行 crawl、LLM、embedding、source audit、health check 或 RAG。

