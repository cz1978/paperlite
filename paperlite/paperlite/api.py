from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from paperlite.agent import paper_agent_context, paper_ask, paper_explain, paper_rag_index, paper_related
from paperlite.ai_filter import filter_paper
from paperlite.api_agent import router as agent_router
from paperlite.api_catalog import router as catalog_router
from paperlite.api_daily import router as daily_router
from paperlite.api_library import router as library_router
from paperlite.api_ops import (
    clear_catalog_snapshot,
    clear_doctor_snapshot,
    refresh_catalog_snapshot,
    refresh_doctor_snapshot,
    router as ops_router,
)
from paperlite.api_zotero import router as zotero_router
from paperlite.core import enrich_paper
from paperlite.daily_crawl import create_daily_schedule, run_daily_crawl, scheduler_loop_status, start_schedule_loop
from paperlite.doctor import run_doctor
from paperlite.endpoint_health import check_selected_endpoint_health
from paperlite.source_audit import read_source_audit_snapshot, run_source_audit
from paperlite.storage import (
    get_relevant_preference_profile,
    mark_interrupted_crawl_runs_failed,
    record_preference_query,
)
from paperlite.translation import translate_paper
from paperlite.zotero import ZoteroNotConfiguredError, ZoteroRequestError, create_zotero_items, zotero_status

__all__ = [
    "ZoteroNotConfiguredError",
    "ZoteroRequestError",
    "app",
    "check_selected_endpoint_health",
    "create_app",
    "create_daily_schedule",
    "create_zotero_items",
    "enrich_paper",
    "filter_paper",
    "get_relevant_preference_profile",
    "paper_ask",
    "paper_agent_context",
    "paper_explain",
    "paper_rag_index",
    "paper_related",
    "read_source_audit_snapshot",
    "record_preference_query",
    "run_daily_crawl",
    "run_doctor",
    "run_source_audit",
    "scheduler_loop_status",
    "translate_paper",
    "zotero_status",
]


def create_app() -> FastAPI:
    clear_catalog_snapshot()
    clear_doctor_snapshot()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        mark_interrupted_crawl_runs_failed()
        refresh_catalog_snapshot()
        refresh_doctor_snapshot(run_doctor)
        start_schedule_loop()
        yield

    app = FastAPI(title="PaperLite", version="0.2.0", lifespan=lifespan)
    app.include_router(daily_router)
    app.include_router(ops_router)
    app.include_router(library_router)
    app.include_router(catalog_router)
    app.include_router(agent_router)
    app.include_router(zotero_router)
    return app


app = create_app()
