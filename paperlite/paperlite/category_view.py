from __future__ import annotations

from html import escape


def _count(value: object) -> str:
    return escape(str(value or 0))


def _link(url: object, label: str = "查看源") -> str:
    href = str(url or "")
    if not href:
        return ""
    return f'<a href="{escape(href)}">{escape(label)}</a>'


def _area_rows(summary: dict[str, object]) -> str:
    rows = []
    for item in summary.get("areas", []):
        if int(item.get("source_count") or 0) <= 0:
            continue
        href = f"/sources?area={item.get('key')}"
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(item.get('label') or ''))}</strong><br><code>{escape(str(item.get('key') or ''))}</code></td>"
            f"<td>{_count(item.get('source_count'))}</td>"
            f"<td>{_count(item.get('core_source_count'))}</td>"
            f"<td>{_count(item.get('needs_review_source_count'))}</td>"
            f"<td>{_link(href)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _discipline_rows(summary: dict[str, object]) -> str:
    rows = []
    for item in summary.get("disciplines", []):
        if int(item.get("source_count") or 0) <= 0:
            continue
        kind_counts = ", ".join(f"{key}:{value}" for key, value in (item.get("source_kind_counts") or {}).items())
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('area_label') or ''))}<br><code>{escape(str(item.get('area_key') or ''))}</code></td>"
            f"<td><strong>{escape(str(item.get('label') or ''))}</strong><br><code>{escape(str(item.get('key') or ''))} / {escape(str(item.get('name') or ''))}</code></td>"
            f"<td>{escape(str(item.get('description') or ''))}</td>"
            f"<td>{_count(item.get('source_count'))}</td>"
            f"<td>{_count(item.get('core_source_count'))}</td>"
            f"<td>{_count(item.get('temporarily_unavailable_source_count'))}</td>"
            f"<td>{_count(item.get('needs_review_source_count'))}</td>"
            f"<td><code>{escape(kind_counts)}</code></td>"
            f"<td>{_link(item.get('sources_url'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _kind_rows(summary: dict[str, object]) -> str:
    rows = []
    for item in summary.get("source_kinds", []):
        if int(item.get("source_count") or 0) <= 0:
            continue
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(item.get('label') or ''))}</strong><br><code>{escape(str(item.get('key') or ''))}</code></td>"
            f"<td>{escape(str(item.get('description') or ''))}</td>"
            f"<td>{_count(item.get('source_count'))}</td>"
            f"<td>{_count(item.get('core_source_count'))}</td>"
            f"<td>{_count(item.get('needs_review_source_count'))}</td>"
            f"<td>{_link(item.get('sources_url'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _category_rows(summary: dict[str, object]) -> str:
    rows = []
    for item in summary.get("categories", []):
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('area_label') or ''))}<br><code>{escape(str(item.get('area_key') or ''))}</code></td>"
            f"<td><strong>{escape(str(item.get('label') or ''))}</strong><br><code>{escape(str(item.get('key') or ''))}</code></td>"
            f"<td>{_count(item.get('source_count'))}</td>"
            f"<td>{_count(item.get('core_source_count'))}</td>"
            f"<td>{_count(item.get('temporarily_unavailable_source_count'))}</td>"
            f"<td>{_count(item.get('needs_review_source_count'))}</td>"
            f"<td>{_link(item.get('sources_url'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_categories_page(summary: dict[str, object]) -> str:
    fields = ", ".join(str(value) for value in summary.get("maintenance_fields", []))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperLite 分类映射</title>
  <style>
    :root {{ color-scheme: light; --fg: #182026; --muted: #63717d; --line: #dbe3e8; --bg: #f6f8f9; --panel: #fff; --accent: #0f766e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: var(--fg); background: var(--bg); }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 20px; }}
    header {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
    h1 {{ margin: 0; font-size: 25px; }}
    h2 {{ margin: 28px 0 10px; font-size: 19px; }}
    a {{ color: #2f5f9f; }}
    .note {{ background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; color: var(--muted); line-height: 1.55; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 11px; text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #eef6f4; color: #164e49; white-space: nowrap; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ color: var(--muted); font-size: 12px; }}
    @media (max-width: 760px) {{ table {{ display: block; overflow-x: auto; }} header {{ display: block; }} }}
  </style>
</head>
<body>
  <header>
    <h1>PaperLite 分类映射</h1>
    <nav><a href="/daily">每日雷达</a> · <a href="/sources">来源</a> · <a href="/endpoints">获取方式</a> · <a href="/categories?format=json">JSON</a></nav>
  </header>
  <main>
    <div class="note">
      <strong>分类不是推荐：</strong>这里的 key 是长期维护和映射用的稳定字段，方便 profile、OpenClaw、训练数据、人工巡检复用同一套目录。PaperLite 不按分类自动替用户组源，也不打分。
      <br>建议外部系统优先使用这些字段：<code>{escape(fields)}</code>
    </div>

    <h2>大区</h2>
    <table>
      <thead><tr><th>大区</th><th>源数</th><th>核心</th><th>待复核</th><th>入口</th></tr></thead>
      <tbody>{_area_rows(summary)}</tbody>
    </table>

    <h2>学科</h2>
    <table>
      <thead><tr><th>大区</th><th>学科</th><th>说明</th><th>源数</th><th>核心</th><th>暂不可用</th><th>待复核</th><th>类型分布</th><th>入口</th></tr></thead>
      <tbody>{_discipline_rows(summary)}</tbody>
    </table>

    <h2>来源类型</h2>
    <table>
      <thead><tr><th>类型</th><th>说明</th><th>源数</th><th>核心</th><th>待复核</th><th>入口</th></tr></thead>
      <tbody>{_kind_rows(summary)}</tbody>
    </table>

    <h2>组合类目</h2>
    <table>
      <thead><tr><th>大区</th><th>category_key</th><th>源数</th><th>核心</th><th>暂不可用</th><th>待复核</th><th>入口</th></tr></thead>
      <tbody>{_category_rows(summary)}</tbody>
    </table>
  </main>
</body>
</html>"""
