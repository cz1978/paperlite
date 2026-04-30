from __future__ import annotations

from paperlite.frontend import render_frontend_page


def render_ops_frontend() -> str:
    return render_frontend_page("ops.html", styles=("ops.css",), scripts=("ops.js",))
