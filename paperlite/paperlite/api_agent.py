from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from paperlite.ai_filter import DEFAULT_AI_FILTER_QUERY
from paperlite.api_common import llm_http_exception, payload_bool, payload_int
from paperlite.integrations import agent_manifest
from paperlite.llm import LLMRequestError
from paperlite.translation_profiles import list_translation_profiles

router = APIRouter()


def _api_facade():
    from paperlite import api

    return api


@router.get("/agent/manifest")
def manifest(request: Request):
    return agent_manifest(str(request.base_url).rstrip("/"))

@router.get("/.well-known/paperlite.json")
def well_known_manifest(request: Request):
    return agent_manifest(str(request.base_url).rstrip("/"))

@router.post("/agent/explain")
def agent_explain(payload: dict):
    paper = payload.get("paper") or payload
    try:
        return _api_facade().paper_explain(
            paper=paper,
            question=payload.get("question"),
            style=payload.get("style") or "plain",
        )
    except LLMRequestError as exc:
        raise llm_http_exception(exc) from exc

@router.post("/agent/context")
def agent_context(payload: dict):
    try:
        limit_key = "limit_per_source" if "limit_per_source" in payload else "limit"
        return _api_facade().paper_agent_context(
            action=str(payload.get("action") or ""),
            paper=payload.get("paper"),
            question=payload.get("question"),
            query=payload.get("query") or payload.get("criteria"),
            target_language=payload.get("target_language") or "zh-CN",
            style=payload.get("style") or "plain",
            date_value=payload.get("date"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            q=payload.get("q"),
            top_k=payload_int(payload, "top_k", default=8, minimum=1, maximum=20),
            limit_per_source=payload_int(payload, limit_key, default=100, minimum=1, maximum=500),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/agent/research")
def agent_research(payload: dict):
    try:
        return _api_facade().paper_research(
            topic=payload.get("topic"),
            discipline=payload.get("discipline"),
            q=payload.get("q"),
            date_value=payload.get("date"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            source=payload.get("source"),
            limit=payload_int(payload, "limit", default=15, minimum=1, maximum=50),
            crawl_if_missing=payload_bool(payload, "crawl_if_missing", default=True),
            source_limit=payload_int(payload, "source_limit", default=15, minimum=1, maximum=50),
            limit_per_source=payload_int(payload, "limit_per_source", default=15, minimum=1, maximum=500),
            translate_brief=payload_bool(payload, "translate_brief", default=True),
            target_language=payload.get("target_language") or "zh-CN",
            translation_profile=payload.get("translation_profile"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/agent/missions")
def agent_missions(status: str | None = "active"):
    return _api_facade().paper_missions(status=status)

@router.post("/agent/missions")
def agent_mission_save(payload: dict):
    try:
        return _api_facade().paper_mission_save(
            mission_id=payload.get("mission_id"),
            name=payload.get("name"),
            topic=payload.get("topic"),
            discipline=payload.get("discipline"),
            source=payload.get("source") or payload.get("source_keys"),
            q=payload.get("q"),
            include_terms=payload.get("include_terms"),
            exclude_terms=payload.get("exclude_terms"),
            prefer_terms=payload.get("prefer_terms"),
            instructions=payload.get("instructions"),
            crawl_if_missing=(
                payload_bool(payload, "crawl_if_missing", default=True)
                if "crawl_if_missing" in payload
                else None
            ),
            limit_per_source=(
                payload_int(payload, "limit_per_source", default=15, minimum=1, maximum=500)
                if "limit_per_source" in payload
                else None
            ),
            status=payload.get("status"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/agent/missions/{mission_id}")
def agent_mission_get(mission_id: str):
    result = _api_facade().paper_mission_get(mission_id=mission_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="research mission not found")
    return result

@router.post("/agent/missions/{mission_id}/run")
def agent_mission_run(mission_id: str, payload: dict | None = None):
    body = payload or {}
    crawl_override = (
        payload_bool(body, "crawl_if_missing", default=True)
        if "crawl_if_missing" in body
        else None
    )
    try:
        return _api_facade().paper_mission_run(
            mission_id=mission_id,
            date_value=body.get("date"),
            date_from=body.get("date_from"),
            date_to=body.get("date_to"),
            limit=payload_int(body, "limit", default=15, minimum=1, maximum=50),
            crawl_if_missing=crawl_override,
            source_limit=payload_int(body, "source_limit", default=15, minimum=1, maximum=50),
            use_llm=payload_bool(body, "use_llm", default=False),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.delete("/agent/missions/{mission_id}")
def agent_mission_delete(mission_id: str):
    result = _api_facade().paper_mission_delete(mission_id=mission_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="research mission not found")
    return result

@router.post("/agent/rag/index")
def agent_rag_index(payload: dict):
    try:
        limit_key = "limit_per_source" if "limit_per_source" in payload else "limit"
        return _api_facade().paper_rag_index(
            date_value=payload.get("date"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            q=payload.get("q"),
            limit_per_source=payload_int(
                payload,
                limit_key,
                default=100,
                minimum=1,
                maximum=500,
            ),
        )
    except LLMRequestError as exc:
        raise llm_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/agent/ask")
def agent_ask(payload: dict):
    try:
        limit_key = "limit_per_source" if "limit_per_source" in payload else "limit"
        return _api_facade().paper_ask(
            question=str(payload.get("question") or ""),
            date_value=payload.get("date"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            discipline=payload.get("discipline"),
            source=payload.get("source"),
            q=payload.get("q"),
            top_k=payload_int(payload, "top_k", default=8, minimum=1, maximum=20),
            limit_per_source=payload_int(
                payload,
                limit_key,
                default=100,
                minimum=1,
                maximum=500,
            ),
        )
    except LLMRequestError as exc:
        raise llm_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/agent/translate")
def agent_translate(payload: dict):
    paper = payload.get("paper") or payload
    try:
        return _api_facade().translate_paper(
            paper=paper,
            target_language=payload.get("target_language") or "zh-CN",
            style=payload.get("style"),
            translation_profile=payload.get("translation_profile"),
        )
    except LLMRequestError as exc:
        raise llm_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/agent/translation-profiles")
def agent_translation_profiles():
    try:
        profiles = list_translation_profiles()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(profiles), "profiles": profiles}

@router.post("/agent/filter")
def agent_filter(payload: dict):
    raw_query = str(payload.get("query") or payload.get("criteria") or "").strip()
    query = raw_query or DEFAULT_AI_FILTER_QUERY
    paper = payload.get("paper") or payload
    use_profile = payload_bool(payload, "use_profile", default=True)
    api_facade = _api_facade()
    preference_profile = api_facade.get_relevant_preference_profile(query=query, paper=paper) if use_profile else None
    try:
        result = api_facade.filter_paper(
            paper=paper,
            query=query,
            preference_profile=preference_profile,
            use_profile=use_profile,
        )
        if use_profile and raw_query:
                api_facade.record_preference_query(text=raw_query, source="agent_filter")
        return result
    except LLMRequestError as exc:
        raise llm_http_exception(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
