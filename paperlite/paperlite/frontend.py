from __future__ import annotations

from functools import lru_cache
from importlib import resources

ASSET_PACKAGE = "paperlite.frontend_assets"


@lru_cache(maxsize=None)
def render_frontend_asset(name: str) -> str:
    return resources.files(ASSET_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def render_frontend_page(template: str, *, styles: tuple[str, ...], scripts: tuple[str, ...]) -> str:
    html = render_frontend_asset(template)
    css = "\n".join(render_frontend_asset(name).rstrip() for name in styles)
    js = "\n".join(render_frontend_asset(name).rstrip() for name in scripts)
    return html.replace("{{ PAPERLITE_STYLES }}", css).replace("{{ PAPERLITE_SCRIPTS }}", js)
