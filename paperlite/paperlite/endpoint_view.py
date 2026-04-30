from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from paperlite.sources import normalize_endpoint_mode


MODE_LABELS = {
    "api": "API",
    "atom": "Atom",
    "manual": "手动链接",
    "rss": "RSS",
    "toc_watch": "目录页观察",
}

MODE_ORDER = ("rss", "atom", "api", "manual", "toc_watch")


def _mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


def _endpoint_url(
    *,
    mode: str | None = None,
    status: str | None = None,
    format: str | None = None,
) -> str:
    params = {}
    if mode:
        params["mode"] = mode
    if status:
        params["status"] = status
    if format:
        params["format"] = format
    return "/endpoints" if not params else f"/endpoints?{urlencode(params)}"


def _mode_filters(mode_counts: dict[str, int], selected_mode: str | None) -> str:
    total = sum(mode_counts.values())
    all_class = ' class="active"' if selected_mode is None else ""
    links = [f'<a{all_class} href="/endpoints">全部 {total}</a>']
    modes = [mode for mode in MODE_ORDER if mode in mode_counts]
    modes.extend(sorted(mode for mode in mode_counts if mode not in modes))
    for mode in modes:
        active = ' class="active"' if mode == selected_mode else ""
        links.append(
            f'<a{active} href="{escape(_endpoint_url(mode=mode))}">{escape(_mode_label(mode))} {mode_counts[mode]}</a>'
        )
    return "\n".join(links)


def _status_filters(status_counts: dict[str, int], selected_status: str | None) -> str:
    all_active = ' class="active"' if selected_status is None else ""
    links = [f'<a{all_active} href="/endpoints">全部状态</a>']
    for status, count in sorted(status_counts.items()):
        active = ' class="active"' if status == selected_status else ""
        links.append(
            f'<a{active} href="{escape(_endpoint_url(status=status))}">{escape(status)} {count}</a>'
        )
    return "\n".join(links)


def _summary_panel(summary: dict[str, object] | None) -> str:
    if not summary:
        return ""
    return f"""
    <div class="summary-grid">
      <div><strong>{summary.get('endpoint_count', 0)}</strong><span>endpoint</span></div>
      <div><strong>{summary.get('enabled_endpoint_count', 0)}</strong><span>启用</span></div>
      <div><strong>{summary.get('temporarily_unavailable_endpoint_count', 0)}</strong><span>暂不可用</span></div>
      <div><strong>{summary.get('candidate_endpoint_count', 0)}</strong><span>candidate</span></div>
      <div><strong>{summary.get('duplicate_url_groups', 0)}</strong><span>重复 URL 组</span></div>
    </div>
    """


def _endpoint_rows(endpoints: list[dict]) -> str:
    rows = []
    for item in sorted(endpoints, key=lambda value: (str(value.get("source_key") or ""), str(value.get("key") or ""))):
        enabled = "是" if item.get("enabled") else "否"
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(item.get('source_name') or item.get('source_key') or ''))}</strong><br><code>{escape(str(item.get('source_key') or ''))}</code></td>"
            f"<td><code>{escape(str(item.get('key') or ''))}</code></td>"
            f"<td>{escape(_mode_label(str(item.get('mode') or '')))}</td>"
            f"<td>{enabled}</td>"
            f"<td>{escape(str(item.get('status') or ''))}</td>"
            f"<td>{escape(str(item.get('url') or ''))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_endpoints_page(
    endpoints: list[dict],
    *,
    selected_mode: str | None = None,
    selected_status: str | None = None,
    mode_counts: dict[str, int] | None = None,
    status_counts: dict[str, int] | None = None,
    summary: dict[str, object] | None = None,
) -> str:
    selected = normalize_endpoint_mode(selected_mode)
    counts = mode_counts or {}
    statuses = status_counts or {}
    rows = _endpoint_rows(endpoints)
    filters = _mode_filters(counts, selected)
    status_filters = _status_filters(statuses, selected_status)
    json_url = _endpoint_url(mode=selected, status=selected_status, format="json")
    selected_label = _mode_label(selected) if selected else "全部"
    status_label = selected_status or "全部状态"
    summary_html = _summary_panel(summary)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PaperLite 获取方式</title>
  <style>
    :root {{ color-scheme: light; --fg: #182026; --muted: #62707c; --line: #dbe3e8; --bg: #f6f8f9; --panel: #fff; --accent: #0f766e; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: var(--fg); background: var(--bg); }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 20px; }}
    header {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
    h1 {{ margin: 0; font-size: 25px; }}
    a {{ color: #2f5f9f; }}
    .note {{ background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin-bottom: 16px; color: var(--muted); line-height: 1.55; }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
    .filters a {{ border: 1px solid var(--line); border-radius: 6px; padding: 7px 10px; background: #fff; text-decoration: none; color: var(--fg); }}
    .filters a.active {{ border-color: var(--accent); color: var(--accent); font-weight: 700; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .summary-grid div {{ border: 1px solid var(--line); border-radius: 8px; background: #fff; padding: 12px; }}
    .summary-grid strong {{ display: block; font-size: 22px; color: var(--accent); }}
    .summary-grid span {{ color: var(--muted); font-size: 13px; }}
    .summary {{ margin: 0 0 10px; color: var(--muted); }}
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
    <h1>PaperLite 获取方式</h1>
    <nav><a href="/daily">每日</a> · <a href="/sources">来源</a> · <a href="{escape(json_url)}">JSON</a></nav>
  </header>
  <main>
    <div class="note">
      endpoint 是获取路径，不是科研分类。RSS/API 会被 runner 执行；manual/toc_watch 第一版只作为可发现入口，不抓取全文或目录页内容。
    </div>
    {summary_html}
    <div class="filters">{filters}</div>
    <div class="filters">{status_filters}</div>
    <p class="summary">当前筛选：{escape(selected_label)} · {escape(status_label)} · 显示 {len(endpoints)} 个 endpoint</p>
    <table>
      <thead>
        <tr>
          <th>来源</th>
          <th>Endpoint</th>
          <th>方式</th>
          <th>启用</th>
          <th>状态</th>
          <th>URL</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </main>
</body>
</html>"""
