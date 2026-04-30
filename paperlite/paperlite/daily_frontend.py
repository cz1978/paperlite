from __future__ import annotations

from paperlite.frontend import render_frontend_page


def render_daily_frontend() -> str:
    return render_frontend_page(
        "daily.html",
        styles=("daily.css",),
        scripts=(
            "daily_state.js",
            "daily_sources.js",
            "daily_cards.js",
            "daily_detail.js",
            "daily_requests.js",
            "daily_cache_library.js",
            "daily_workflows.js",
            "daily_preferences.js",
            "daily_boot.js",
        ),
    )
