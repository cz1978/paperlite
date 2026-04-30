from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from paperlite.api_common import parse_paper_items
from paperlite.core import export
from paperlite.zotero import ZoteroNotConfiguredError, ZoteroRequestError

router = APIRouter()


def _api_facade():
    from paperlite import api

    return api


@router.get("/zotero/status")
def zotero_config_status():
    return _api_facade().zotero_status()

@router.post("/zotero/items")
def zotero_items(payload: dict):
    papers = parse_paper_items(payload)
    try:
        return _api_facade().create_zotero_items(papers)
    except ZoteroNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZoteroRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.post("/zotero/export")
def zotero_export(payload: dict, format: str = Query(default="ris")):
    fmt = format.lower()
    if fmt not in {"ris", "bib", "bibtex"}:
        raise HTTPException(status_code=400, detail="format must be ris or bibtex")
    papers = parse_paper_items(payload)
    body = export(papers, format=fmt)
    extension = "bib" if fmt in {"bib", "bibtex"} else "ris"
    media_type = "application/x-bibtex" if extension == "bib" else "application/x-research-info-systems"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="paperlite-zotero.{extension}"'},
    )
