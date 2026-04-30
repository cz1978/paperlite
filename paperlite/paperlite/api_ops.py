from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from paperlite.api_common import age_seconds, payload_float, payload_int
from paperlite.catalog_quality import build_catalog_coverage, build_catalog_summary
from paperlite.config import runtime_config
from paperlite.daily_crawl import list_daily_schedules
from paperlite.doctor import doctor_summary, run_doctor
from paperlite.endpoint_health import health_snapshot_write_path, merge_health_snapshot
from paperlite.ops_frontend import render_ops_frontend
from paperlite.registry import list_sources
from paperlite.storage import list_crawl_runs, runtime_storage_summary

router = APIRouter()
_doctor_snapshot_lock = Lock()
_doctor_snapshot: dict | None = None
_catalog_snapshot_lock = Lock()
_catalog_snapshot: dict | None = None


def _api_facade():
    from paperlite import api

    return api


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _doctor_error_payload(exc: Exception) -> dict:
    message = str(exc) or exc.__class__.__name__
    return {
        "overall": "fail",
        "generated_at": _utc_now(),
        "summary": {"ok": 0, "warn": 0, "fail": 1},
        "checks": [
            {
                "id": "startup_doctor",
                "label": "Startup doctor",
                "status": "fail",
                "message": message,
                "details": {"exception_type": exc.__class__.__name__},
            }
        ],
    }


def set_doctor_snapshot(payload: dict, *, source: str) -> dict:
    snapshot = dict(payload)
    snapshot["snapshot_source"] = source
    snapshot["snapshot_captured_at"] = _utc_now()
    with _doctor_snapshot_lock:
        global _doctor_snapshot
        _doctor_snapshot = snapshot
    return snapshot


def refresh_doctor_snapshot(runner: Callable[[], dict] | None = None, *, source: str = "startup") -> dict:
    selected_runner = runner or run_doctor
    try:
        payload = selected_runner()
    except Exception as exc:  # pragma: no cover - defensive startup resilience
        payload = _doctor_error_payload(exc)
    return set_doctor_snapshot(payload, source=source)


def get_doctor_snapshot() -> dict:
    with _doctor_snapshot_lock:
        snapshot = dict(_doctor_snapshot) if _doctor_snapshot is not None else None
    if snapshot is None:
        snapshot = refresh_doctor_snapshot(lambda: _api_facade().run_doctor(), source="lazy")
    return snapshot


def clear_doctor_snapshot() -> None:
    with _doctor_snapshot_lock:
        global _doctor_snapshot
        _doctor_snapshot = None


def _catalog_snapshot_from_runtime() -> dict:
    summary = build_catalog_summary()
    coverage = build_catalog_coverage()
    health_checked_at = summary.get("health_checked_at_max")
    unavailable_sources = [
        {
            "name": str(item.get("name") or ""),
            "display_name": str(item.get("display_name") or item.get("name") or ""),
            "health_status": item.get("health_status"),
            "quality_status": item.get("quality_status"),
            "primary_discipline_key": item.get("primary_discipline_key"),
            "primary_discipline_label": item.get("primary_discipline_label"),
        }
        for item in list_sources()
        if item.get("health_status") not in {"active", "ok"}
        or item.get("quality_status") == "temporarily_unavailable"
    ][:50]
    return {
        "catalog_summary": summary,
        "catalog_coverage": coverage,
        "health_snapshot": {
            "loaded": bool(summary.get("health_snapshot_loaded")),
            "path": summary.get("health_snapshot_path") or str(health_snapshot_write_path()),
            "checked_at_min": summary.get("health_checked_at_min"),
            "checked_at_max": health_checked_at,
            "age_seconds": age_seconds(health_checked_at),
            "status_counts": summary.get("health_status_counts") or {},
        },
        "unavailable_sources": unavailable_sources,
        "snapshot_captured_at": _utc_now(),
    }


def refresh_catalog_snapshot() -> dict:
    snapshot = _catalog_snapshot_from_runtime()
    with _catalog_snapshot_lock:
        global _catalog_snapshot
        _catalog_snapshot = snapshot
    return snapshot


def get_catalog_snapshot() -> dict:
    with _catalog_snapshot_lock:
        snapshot = dict(_catalog_snapshot) if _catalog_snapshot is not None else None
    if snapshot is None:
        snapshot = refresh_catalog_snapshot()
    return snapshot


def clear_catalog_snapshot() -> None:
    with _catalog_snapshot_lock:
        global _catalog_snapshot
        _catalog_snapshot = None


def recent_error_summary(
    runs: list[dict],
    schedules: list[dict],
    *,
    scheduler_status: dict | None = None,
    limit: int = 8,
) -> list[dict]:
    errors: list[dict] = []
    for run in runs:
        if run.get("error"):
            errors.append({"kind": "crawl_run", "id": run.get("run_id"), "message": run.get("error"), "at": run.get("finished_at") or run.get("started_at")})
        for source_result in run.get("source_results") or []:
            if source_result.get("error"):
                errors.append(
                    {
                        "kind": "source",
                        "id": source_result.get("endpoint") or source_result.get("source"),
                        "message": source_result.get("error"),
                        "at": run.get("finished_at") or run.get("started_at"),
                    }
                )
    for schedule in schedules:
        if schedule.get("error"):
            errors.append({"kind": "schedule", "id": schedule.get("schedule_id"), "message": schedule.get("error"), "at": schedule.get("updated_at")})
    if scheduler_status and scheduler_status.get("last_error"):
        errors.append(
            {
                "kind": "scheduler",
                "id": "paperlite-crawl-scheduler",
                "message": scheduler_status.get("last_error"),
                "at": scheduler_status.get("last_error_at"),
            }
        )
    return sorted(errors, key=lambda item: str(item.get("at") or ""), reverse=True)[:limit]

def summarize_runs(runs: list[dict]) -> dict:
    latest = runs[0] if runs else None
    failed_sources = sum(1 for run in runs for item in (run.get("source_results") or []) if item.get("error"))
    return {
        "latest_run_id": latest.get("run_id") if latest else None,
        "latest_status": latest.get("status") if latest else None,
        "latest_started_at": latest.get("started_at") if latest else None,
        "latest_finished_at": latest.get("finished_at") if latest else None,
        "latest_duration_seconds": latest.get("duration_seconds") if latest else None,
        "failed_source_count": failed_sources,
        "recent_run_count": len(runs),
    }

def summarize_schedules(schedules: list[dict]) -> dict:
    active = [item for item in schedules if item.get("status") == "active"]
    paused = [item for item in schedules if item.get("status") == "paused"]
    next_active = sorted(active, key=lambda item: str(item.get("next_run_at") or ""))[0] if active else None
    return {
        "active_count": len(active),
        "paused_count": len(paused),
        "next_active_schedule": next_active,
    }

def ops_status_payload(
    *,
    limit: int = 20,
    status: str | None = None,
    discipline: str | None = None,
) -> dict:
    max_rows = max(1, min(int(limit), 200))
    config = runtime_config()
    catalog_snapshot = get_catalog_snapshot()
    summary = catalog_snapshot["catalog_summary"]
    coverage = catalog_snapshot["catalog_coverage"]
    api_facade = _api_facade()
    doctor_payload = get_doctor_snapshot()
    recent_runs = list_crawl_runs(limit=max_rows, status=status, discipline_key=discipline)
    schedules = list_daily_schedules()
    scheduler_status = api_facade.scheduler_loop_status()
    storage_summary = runtime_storage_summary()
    source_audit_snapshot = api_facade.read_source_audit_snapshot()
    source_audit_summary = dict(source_audit_snapshot.get("summary") or {})
    source_audit_summary.update(
        {
            "loaded": bool(source_audit_snapshot.get("loaded")),
            "path": source_audit_snapshot.get("path"),
            "updated_at": source_audit_snapshot.get("updated_at"),
        }
    )
    doctor_status = doctor_summary(doctor_payload)
    doctor_status["snapshot_source"] = doctor_payload.get("snapshot_source", "unknown")
    doctor_status["snapshot_captured_at"] = doctor_payload.get("snapshot_captured_at")
    return {
        "recent_runs": recent_runs,
        "schedules": schedules,
        "catalog_summary": summary,
        "catalog_coverage": coverage,
        "doctor": doctor_status,
        "cache_summary": storage_summary,
        "run_summary": summarize_runs(recent_runs),
        "schedule_summary": summarize_schedules(schedules),
        "recent_errors": recent_error_summary(recent_runs, schedules, scheduler_status=scheduler_status),
        "source_audit_summary": source_audit_summary,
        "health_snapshot": catalog_snapshot["health_snapshot"],
        "scheduler": {
            "enabled": config.scheduler_enabled,
            "poll_seconds": config.scheduler_poll_seconds,
            "min_interval_minutes": config.schedule_min_interval_minutes,
            "crawl_cooldown_seconds": config.crawl_cooldown_seconds,
            "crawl_source_delay_seconds": config.crawl_source_delay_seconds,
            "db_path": str(config.db_path),
            "loop": scheduler_status,
        },
        "unavailable_sources": catalog_snapshot["unavailable_sources"],
    }

@router.get("/ops")
def ops():
    return HTMLResponse(render_ops_frontend())

@router.get("/ops/status")
def ops_status(
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
):
    return ops_status_payload(limit=limit, status=status, discipline=discipline)

@router.get("/ops/doctor")
def ops_doctor():
    payload = _api_facade().run_doctor()
    set_doctor_snapshot(payload, source="manual")
    return payload

@router.get("/ops/source-audit")
def ops_source_audit():
    return _api_facade().read_source_audit_snapshot()

@router.post("/ops/source-audit/check")
def ops_source_audit_check(payload: dict):
    limit = payload_int(payload, "limit", default=100, minimum=1, maximum=200)
    offset = payload_int(payload, "offset", default=0, minimum=0, maximum=1_000_000)
    sample_size = payload_int(payload, "sample_size", default=3, minimum=1, maximum=20)
    timeout_seconds = payload_float(payload, "timeout_seconds", default=5.0, minimum=1.0, maximum=30.0)
    request_profile = str(payload.get("request_profile") or "paperlite").strip()
    if request_profile not in {"paperlite", "browser_compat"}:
        raise HTTPException(status_code=422, detail="request_profile must be paperlite or browser_compat")
    try:
        return _api_facade().run_source_audit(
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            mode=payload.get("mode"),
            limit=limit,
            offset=offset,
            sample_size=sample_size,
            timeout_seconds=timeout_seconds,
            request_profile=request_profile,
            write_snapshot=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/ops/health/check")
def ops_health_check(payload: dict):
    limit = payload_int(payload, "limit", default=50, minimum=1, maximum=200)
    timeout_seconds = payload_float(payload, "timeout_seconds", default=5.0, minimum=1.0, maximum=30.0)
    request_profile = str(payload.get("request_profile") or "paperlite").strip()
    if request_profile not in {"paperlite", "browser_compat"}:
        raise HTTPException(status_code=422, detail="request_profile must be paperlite or browser_compat")
    try:
        results = _api_facade().check_selected_endpoint_health(
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            mode=payload.get("mode"),
            limit=limit,
            timeout_seconds=timeout_seconds,
            request_profile=request_profile,
        )
        snapshot = merge_health_snapshot(results)
        refresh_catalog_snapshot()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "checked": len(results),
        "health": [result.to_dict() for result in results],
        "snapshot": snapshot,
    }
