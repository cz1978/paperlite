from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from paperlite.api_common import llm_http_exception, parse_single_paper, payload_bool, payload_int
from paperlite.core import export
from paperlite.daily_crawl import (
    create_daily_crawl,
    delete_daily_schedule,
    list_daily_schedules,
    update_daily_schedule_status,
)
from paperlite.daily_export import (
    daily_cache_export_papers,
    daily_cache_payload,
    daily_date_range,
    daily_export_filename,
    export_media_type,
)
from paperlite.daily_frontend import render_daily_frontend
from paperlite.llm import LLMRequestError
from paperlite.storage import get_crawl_run, list_crawl_runs

router = APIRouter()


def _api_facade():
    from paperlite import api

    return api


@router.get("/")
def home():
    return HTMLResponse(render_daily_frontend())

@router.get("/daily")
def daily(
    format: str | None = Query(default=None),
):
    if format and format != "html":
        raise HTTPException(
            status_code=410,
            detail="The /daily live data API was removed for PaperLite v1. Use /daily/cache?format=json for SQLite cache reads or /daily/export?format=rss for RSS export.",
        )
    return HTMLResponse(render_daily_frontend())

@router.get("/daily/crawl")
def crawl_runs(
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
):
    return {"runs": list_crawl_runs(limit=limit, status=status, discipline_key=discipline)}

@router.get("/daily/export")
def daily_export(
    date_value: str | None = Query(default=None, alias="date"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit_per_source: int = Query(default=500, ge=1, le=500),
    format: str = Query(default="ris"),
):
    try:
        days = daily_date_range(date_value=date_value, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        fmt = format.lower()
        extension, media_type = export_media_type(fmt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    papers = daily_cache_export_papers(
        date_from=days[0],
        date_to=days[-1],
        discipline=discipline,
        source=source,
        q=q,
        limit_per_source=limit_per_source,
    )
    body = export(papers, format=fmt)
    filename = daily_export_filename(days[0], days[-1], extension)
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-PaperLite-Export-Count": str(len(papers)),
        },
    )

@router.get("/daily/cache")
def daily_cache(
    date_value: str | None = Query(default=None, alias="date"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit_per_source: int = Query(default=50, ge=1, le=500),
    format: str | None = Query(default="json"),
):
    try:
        days = daily_date_range(date_value=date_value, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return daily_cache_payload(
        date_from=days[0],
        date_to=days[-1],
        discipline=discipline,
        source=source,
        limit_per_source=limit_per_source,
    )

@router.get("/daily/related")
def daily_related(
    paper_id: str = Query(...),
    date_value: str | None = Query(default=None, alias="date"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    top_k: int = Query(default=5, ge=1, le=20),
    limit_per_source: int = Query(default=500, ge=1, le=500),
):
    try:
        return _api_facade().paper_related(
            paper_id=paper_id,
            date_value=date_value,
            date_from=date_from,
            date_to=date_to,
            discipline=discipline,
            source=source,
            q=q,
            top_k=top_k,
            limit_per_source=limit_per_source,
        )
    except LLMRequestError as exc:
        raise llm_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/daily/crawl")
def create_crawl(payload: dict, background_tasks: BackgroundTasks):
    try:
        limit_per_source = payload_int(
            payload,
            "limit_per_source",
            default=100,
            minimum=1,
            maximum=500,
        )
        run = create_daily_crawl(
            date_from=payload.get("date_from") or payload.get("date"),
            date_to=payload.get("date_to") or payload.get("date_from") or payload.get("date"),
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            limit_per_source=limit_per_source,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not run.get("reused") and run.get("status") == "queued":
        background_tasks.add_task(_api_facade().run_daily_crawl, run["run_id"])
    return run

@router.get("/daily/crawl/{run_id}")
def crawl_status(run_id: str):
    run = get_crawl_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="crawl run not found")
    return run

@router.get("/daily/schedules")
def crawl_schedules():
    return {"schedules": list_daily_schedules()}

@router.post("/daily/schedules")
def create_schedule(payload: dict):
    try:
        interval_minutes = payload_int(
            payload,
            "interval_minutes",
            default=180,
            minimum=1,
            maximum=100_000,
        )
        lookback_days = payload_int(
            payload,
            "lookback_days",
            default=0,
            minimum=0,
            maximum=30,
        )
        limit_per_source = payload_int(
            payload,
            "limit_per_source",
            default=100,
            minimum=1,
            maximum=500,
        )
        schedule = _api_facade().create_daily_schedule(
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            interval_minutes=interval_minutes,
            lookback_days=lookback_days,
            limit_per_source=limit_per_source,
            run_now=payload_bool(payload, "run_now", default=False),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schedule

@router.patch("/daily/schedules/{schedule_id}")
def update_schedule(schedule_id: str, payload: dict):
    try:
        schedule = update_daily_schedule_status(schedule_id, status=payload.get("status"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return schedule

@router.delete("/daily/schedules/{schedule_id}")
def remove_schedule(schedule_id: str):
    if not delete_daily_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="schedule not found")
    return {"deleted": True, "schedule_id": schedule_id}

@router.post("/daily/enrich")
def daily_enrich(payload: dict, source: str | None = Query(default=None)):
    paper = parse_single_paper(payload)
    return _api_facade().enrich_paper(paper, source).to_dict()
