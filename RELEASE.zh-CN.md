# 发布 Checklist

English version: [RELEASE.md](RELEASE.md)

给 PaperLite 打 tag 前使用这份 checklist。

## 准备

- 确认 `CHANGELOG.md` 已记录发布范围。
- 只有发布 package/runtime 版本时才更新 `paperlite/pyproject.toml`。
- 公开行为变化时同步更新 `README.md`、`README.zh-CN.md` 和 agent 文档。
- 不要把 `.env`、SQLite 文件、运行缓存、日志或带私有路径的截图放进发布。

## 验证

```bash
cd paperlite
python -m pytest -q
ruff check paperlite tests
python -m compileall paperlite
python -m paperlite.cli catalog validate --format markdown
```

从仓库根目录做发布卫生检查：

```bash
git diff --check
docker build -t paperlite-release-smoke:local .
```

可选来源检查：

```bash
cd paperlite
python -m paperlite.cli catalog coverage --format markdown
python -m paperlite.cli endpoints audit --limit 100 --sample-size 3 --format markdown
```

## 密钥检查

- 检查变更文件里是否有真实 key、token、私有 URL、本地路径和 SQLite 文件。
- 任何曾经提交或公开分享过的 key 都要旋转。
- 确认截图只展示空数据或非敏感本地数据。

## 打 tag 和发布

```bash
git status --short
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

从 tag 创建 GitHub Release，并粘贴对应的 `CHANGELOG.md` 段落。不要移动已经发布的 tag。

## 发布后

- smoke 一遍文档里的安装路径。
- 确认 `/agent/manifest` 和 OpenAPI 返回预期版本。
- 检查 README 和 changelog 中最新版本是否清楚。

