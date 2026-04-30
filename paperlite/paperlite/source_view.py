from __future__ import annotations

from html import escape
from urllib.parse import urlencode


GROUP_LABELS = {
    "api": "API",
    "journal": "顶刊 / RSS",
    "metadata": "元数据",
    "news": "科研资讯",
    "publisher": "出版社",
    "preprint": "预印本",
    "working_papers": "工作论文",
}

SEARCH_MODE_LABELS = {
    "metadata_enrich": "资料补充",
    "native_api": "可搜索",
    "recent_feed_filter": "最近快讯",
}


def _yes(value: object) -> str:
    return "是" if bool(value) else "否"


def _source_url(**params: object) -> str:
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    return "/sources" if not clean else f"/sources?{urlencode(clean)}"


def _summary_panel(summary: dict[str, object] | None) -> str:
    if not summary:
        return ""
    return f"""
    <div class="summary-grid">
      <div><strong>{summary.get('source_count', 0)}</strong><span>来源</span></div>
      <div><strong>{summary.get('enabled_endpoint_count', 0)}</strong><span>启用 endpoint</span></div>
      <div><strong>{summary.get('temporarily_unavailable_endpoint_count', 0)}</strong><span>暂不可用</span></div>
      <div><strong>{summary.get('core_source_count', 0)}</strong><span>核心源</span></div>
      <div><strong>{summary.get('needs_review_source_count', 0)}</strong><span>待复核</span></div>
      <div><strong>{summary.get('duplicate_url_groups', 0)}</strong><span>重复 URL 组</span></div>
    </div>
    """


def _filter_links(selected: dict[str, object] | None) -> str:
    selected = selected or {}
    filters = [
        ("全部", _source_url()),
        ("核心源", _source_url(core="true")),
        ("生命医学", _source_url(area="life_health")),
        ("数理化材料", _source_url(area="physical_sciences")),
        ("地球环境", _source_url(area="earth_environment")),
        ("计算数学", _source_url(area="computing_math")),
        ("工程技术", _source_url(area="engineering_technology")),
        ("社科人文", _source_url(area="social_humanities")),
        ("医学", _source_url(discipline="Medicine")),
        ("化学", _source_url(discipline="Chemistry")),
        ("材料", _source_url(discipline="Materials")),
        ("物理", _source_url(discipline="Physics")),
        ("地球科学", _source_url(discipline="Earth Science")),
        ("预印本", _source_url(kind="preprint")),
        ("期刊", _source_url(kind="journal")),
        ("暂不可用", _source_url(health="temporarily_unavailable")),
        ("待候选", _source_url(health="candidate")),
    ]
    active_query = _source_url(
        discipline=selected.get("discipline"),
        area=selected.get("area"),
        kind=selected.get("kind"),
        core=str(selected.get("core")).lower() if selected.get("core") is not None else None,
        health=selected.get("health"),
    )
    links = []
    for label, href in filters:
        active = ' class="active"' if href == active_query else ""
        links.append(f'<a{active} href="{escape(href)}">{escape(label)}</a>')
    return '<div class="filters">' + "\n".join(links) + "</div>"


def _source_rows(sources: list[dict]) -> str:
    rows = []
    for item in sorted(sources, key=lambda source: (str(source.get("group") or ""), str(source.get("name") or ""))):
        limitations = "；".join(str(value) for value in item.get("limitations") or [])
        access_modes = ", ".join(str(value) for value in item.get("access_modes") or [])
        disciplines = ", ".join(str(value) for value in item.get("canonical_disciplines") or item.get("disciplines") or [])
        governance = " · ".join(
            str(value)
            for value in [
                item.get("category_key"),
                item.get("quality_status"),
                "核心" if item.get("core") else None,
                f"重复于 {item.get('duplicate_of')}" if item.get("duplicate_of") else None,
                item.get("health_status"),
            ]
            if value
        )
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(item.get('display_name') or item.get('name') or ''))}</strong><br><code>{escape(str(item.get('name') or ''))}</code></td>"
            f"<td>{escape(GROUP_LABELS.get(str(item.get('group') or ''), str(item.get('group') or '')))}</td>"
            f"<td>{escape(str(item.get('primary_area_label') or ''))} / {escape(disciplines)}<br><code>{escape(governance)}</code></td>"
            f"<td>{escape(access_modes)}<br><code>{escape(str(item.get('primary_endpoint') or ''))}</code></td>"
            f"<td>{escape(SEARCH_MODE_LABELS.get(str(item.get('search_mode') or ''), str(item.get('search_mode') or '')))}</td>"
            f"<td>{_yes(item.get('supports_latest'))}</td>"
            f"<td>{_yes(item.get('supports_search'))}</td>"
            f"<td>{_yes(item.get('supports_enrich'))}</td>"
            f"<td>{_yes(item.get('supports_pdf_link'))}</td>"
            f"<td>{escape(limitations)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_sources_page(
    sources: list[dict],
    *,
    summary: dict[str, object] | None = None,
    selected_filters: dict[str, object] | None = None,
) -> str:
    rows = _source_rows(sources)
    summary_html = _summary_panel(summary)
    filter_html = _filter_links(selected_filters)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperLite 来源说明</title>
  <style>
    :root {{ color-scheme: light; --fg: #182026; --muted: #62707c; --line: #dbe3e8; --bg: #f6f8f9; --panel: #fff; --accent: #0f766e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: var(--fg); background: var(--bg); }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 20px; }}
    header {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
    h1 {{ margin: 0; font-size: 25px; }}
    a {{ color: #2f5f9f; }}
    .note {{ background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; color: var(--muted); line-height: 1.55; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .summary-grid div {{ border: 1px solid var(--line); border-radius: 8px; background: #fff; padding: 12px; }}
    .summary-grid strong {{ display: block; font-size: 22px; color: var(--accent); }}
    .summary-grid span {{ color: var(--muted); font-size: 13px; }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
    .filters a {{ border: 1px solid var(--line); border-radius: 6px; padding: 7px 10px; background: #fff; text-decoration: none; color: var(--fg); }}
    .filters a.active {{ border-color: var(--accent); color: var(--accent); font-weight: 700; }}
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
    <h1>PaperLite 来源说明</h1>
    <nav><a href="/daily">返回 Daily</a> · <a href="/categories">分类映射</a> · <a href="/endpoints">获取方式</a> · <a href="/sources?format=json">JSON</a></nav>
  </header>
  <main>
    <div class="note">
      <strong>外链优先：</strong>PaperLite 只聚合论文标题、摘要和资料字段，不下载、不缓存、不代理全文或 PDF。来源说明“关注谁”，获取方式说明“怎么拿”；分类映射提供稳定 key，方便长期维护、profile、OpenClaw 和训练数据对齐。
    </div>
    {summary_html}
    {filter_html}
    <table>
      <thead>
        <tr>
          <th>来源</th>
          <th>分组</th>
          <th>治理状态</th>
          <th>获取方式</th>
          <th>能力</th>
          <th>最新</th>
          <th>搜索</th>
          <th>补资料</th>
          <th>PDF 链接</th>
          <th>限制说明</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </main>
</body>
</html>"""


def render_catalog_summary_page(summary: dict[str, object]) -> str:
    rows = []
    for key, value in summary.items():
        if isinstance(value, dict):
            display = ", ".join(f"{k}: {v}" for k, v in value.items())
        else:
            display = value
        rows.append(f"<tr><th>{escape(str(key))}</th><td>{escape(str(display))}</td></tr>")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperLite 源目录体检</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #182026; background: #f6f8f9; }}
    header, main {{ max-width: 980px; margin: 0 auto; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dbe3e8; }}
    th, td {{ border-bottom: 1px solid #dbe3e8; padding: 10px 12px; text-align: left; vertical-align: top; }}
    th {{ width: 260px; color: #164e49; background: #eef6f4; }}
    a {{ color: #2f5f9f; }}
  </style>
</head>
<body>
  <header>
    <h1>PaperLite 源目录体检</h1>
    <nav><a href="/sources">来源</a> · <a href="/endpoints">获取方式</a> · <a href="/catalog/summary?format=json">JSON</a></nav>
  </header>
  <main><table>{"".join(rows)}</table></main>
</body>
</html>"""
