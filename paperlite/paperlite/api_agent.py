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
