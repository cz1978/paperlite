from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from paperlite.api_common import wants_html
from paperlite.catalog_quality import (
    build_catalog_coverage,
    build_catalog_summary,
    build_taxonomy_summary,
    format_catalog_coverage_markdown,
    format_catalog_summary_markdown,
    format_taxonomy_markdown,
)
from paperlite.category_view import render_categories_page
from paperlite.endpoint_view import render_endpoints_page
from paperlite.registry import list_sources
from paperlite.source_view import render_catalog_summary_page, render_sources_page
from paperlite.sources import endpoint_mode_counts, list_endpoints

router = APIRouter()

@router.get("/catalog/summary")
def catalog_summary(request: Request, format: str | None = Query(default=None)):
    summary = build_catalog_summary()
    if format in {"markdown", "md"}:
        return Response(content=format_catalog_summary_markdown(summary), media_type="text/markdown")
    if wants_html(request.headers.get("accept", ""), format):
        return HTMLResponse(render_catalog_summary_page(summary))
    return summary

@router.get("/catalog/coverage")
def catalog_coverage(format: str | None = Query(default=None)):
    coverage = build_catalog_coverage()
    if format in {"markdown", "md"}:
        return Response(content=format_catalog_coverage_markdown(coverage), media_type="text/markdown")
    return coverage

@router.get("/categories")
def categories(request: Request, format: str | None = Query(default=None)):
    summary = build_taxonomy_summary()
    if format in {"markdown", "md"}:
        return Response(content=format_taxonomy_markdown(summary), media_type="text/markdown")
    if wants_html(request.headers.get("accept", ""), format):
        return HTMLResponse(render_categories_page(summary))
    return summary

@router.get("/sources")
def sources(
    request: Request,
    format: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    area: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    core: bool | None = Query(default=None),
    health: str | None = Query(default=None),
):
    items = list_sources(discipline=discipline, area=area, kind=kind, core=core, health=health)
    if wants_html(request.headers.get("accept", ""), format):
        return HTMLResponse(
            render_sources_page(
                items,
                summary=build_catalog_summary(),
                selected_filters={
                    "discipline": discipline,
                    "area": area,
                    "kind": kind,
                    "core": core,
                    "health": health,
                },
            )
        )
    return {"sources": items}

@router.get("/endpoints")
def endpoints(
    request: Request,
    format: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    try:
        items = list_endpoints(mode=mode, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if wants_html(request.headers.get("accept", ""), format):
        summary = build_catalog_summary()
        return HTMLResponse(
            render_endpoints_page(
                items,
                selected_mode=mode,
                selected_status=status,
                mode_counts=endpoint_mode_counts(),
                status_counts=summary["endpoint_status_counts"],
                summary=summary,
            )
        )
    return {"endpoints": items}
