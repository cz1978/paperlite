from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response

from paperlite.api_common import (
    parse_library_paper_items,
    payload_bool,
    payload_int,
    require_training_export_token,
)
from paperlite.storage import (
    apply_library_action,
    clear_preference_learning_data,
    delete_preference_prompt,
    delete_saved_view,
    evaluate_preference_learning,
    export_preference_training_data,
    get_library_state,
    get_preference_profile,
    get_preference_settings,
    list_library_items,
    list_preference_prompts,
    list_saved_views,
    purify_preference_signals,
    rebuild_preference_profile,
    save_preference_prompt,
    save_view,
    update_preference_prompt,
    update_preference_settings,
)

router = APIRouter()

@router.post("/library/state")
def library_state(payload: dict):
    papers = parse_library_paper_items(payload)
    return get_library_state(papers)

@router.post("/library/action")
def library_action(payload: dict):
    action = str(payload.get("action") or "").strip().lower()
    papers = parse_library_paper_items(payload)
    event_payload = payload.get("event") if isinstance(payload.get("event"), dict) else None
    try:
        return apply_library_action(action=action, papers=papers, event_payload=event_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/library/items")
def library_items(
    state: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        items = list_library_items(state=state, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"state": state, "count": len(items), "items": items}

@router.get("/library/views")
def library_views():
    return {"views": list_saved_views()}

@router.post("/library/views")
def create_library_view(payload: dict):
    try:
        return save_view(name=payload.get("name"), filters=payload.get("filters") or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.delete("/library/views")
def remove_library_view(
    view_id: str | None = Query(default=None),
    name: str | None = Query(default=None),
):
    try:
        deleted = delete_saved_view(view_id=view_id, name=name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="saved view not found")
    return {"deleted": True, "view_id": view_id, "name": name}

@router.get("/preferences/profile")
def preferences_profile():
    return get_preference_profile()

@router.get("/preferences/settings")
def preferences_settings():
    return get_preference_settings()

@router.patch("/preferences/settings")
def patch_preferences_settings(payload: dict):
    try:
        return update_preference_settings(updates=payload.get("settings") if isinstance(payload.get("settings"), dict) else payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/preferences/rebuild")
def preferences_rebuild():
    return rebuild_preference_profile()

@router.post("/preferences/purify")
def preferences_purify():
    return purify_preference_signals()

@router.post("/preferences/learning-data/clear")
def preferences_clear_learning_data():
    return clear_preference_learning_data()

@router.get("/preferences/evaluation")
def preferences_evaluation(
    limit: int = Query(default=1000, ge=1, le=5000),
    k: int = Query(default=10, ge=1, le=100),
):
    return evaluate_preference_learning(limit=limit, k=k)

@router.get("/preferences/prompts")
def preferences_prompts(enabled: bool | None = Query(default=None)):
    prompts = list_preference_prompts(enabled=enabled)
    return {"count": len(prompts), "prompts": prompts}

@router.post("/preferences/prompts")
def create_preference_prompt(payload: dict):
    try:
        return save_preference_prompt(
            text=payload.get("text") or payload.get("prompt") or "",
            enabled=payload_bool(payload, "enabled", default=True),
            weight=payload_int(payload, "weight", default=1, minimum=1, maximum=5),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.patch("/preferences/prompts/{prompt_id}")
def patch_preference_prompt(prompt_id: str, payload: dict):
    try:
        return update_preference_prompt(
            prompt_id=prompt_id,
            text=payload.get("text") if "text" in payload else payload.get("prompt") if "prompt" in payload else None,
            enabled=payload_bool(payload, "enabled") if "enabled" in payload else None,
            weight=payload_int(payload, "weight", default=1, minimum=1, maximum=5) if "weight" in payload else None,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

@router.delete("/preferences/prompts/{prompt_id}")
def remove_preference_prompt(prompt_id: str):
    try:
        deleted = delete_preference_prompt(prompt_id=prompt_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="preference prompt not found")
    return {"deleted": True, "prompt_id": prompt_id}

@router.get("/preferences/training-data")
def preferences_training_data(
    authorized: bool = Query(default=False),
    format: str = Query(default="json"),
    limit: int = Query(default=1000, ge=1, le=5000),
    include_weak: bool = Query(default=True),
    include_model_assisted: bool = Query(default=True),
    authorization: str | None = Header(default=None),
):
    require_training_export_token(authorization)
    payload = export_preference_training_data(
        limit=limit,
        include_weak=include_weak,
        include_model_assisted=include_model_assisted,
    )
    selected_format = str(format or "json").strip().lower()
    if selected_format == "json":
        return payload
    if selected_format == "jsonl":
        rows = [
            *payload.get("examples", []),
            *[
                {"kind": "manual_prompt", **item}
                for item in payload.get("manual_prompts", [])
            ],
            *[
                {"kind": "manual_filter_query", **item}
                for item in payload.get("query_history", [])
            ],
        ]
        body = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        return Response(content=body + ("\n" if body else ""), media_type="application/x-ndjson")
    raise HTTPException(status_code=400, detail="format must be json or jsonl")
