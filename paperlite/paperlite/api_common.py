from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

from paperlite.config import runtime_config
from paperlite.llm import LLMRequestError
from paperlite.models import Paper

def wants_html(accept_header: str, output_format: str | None) -> bool:
    if output_format == "html":
        return True
    if output_format == "json":
        return False
    return "text/html" in accept_header

def parse_paper_items(payload: dict) -> list[Paper]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=422, detail="items must be a list of Paper dictionaries")
    try:
        return [
            Paper.model_validate(item) if hasattr(Paper, "model_validate") else Paper.parse_obj(item)
            for item in raw_items
        ]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

def parse_library_paper_items(payload: dict) -> list[Paper]:
    raw_items = payload.get("items")
    if raw_items is None and isinstance(payload.get("paper"), dict):
        raw_items = [payload.get("paper")]
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=422, detail="items must be a list of Paper dictionaries")
    return parse_paper_items({"items": raw_items})

def parse_single_paper(payload: dict) -> Paper:
    try:
        return Paper.model_validate(payload) if hasattr(Paper, "model_validate") else Paper.parse_obj(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

def parse_utc_datetime(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def age_seconds(value: str | None) -> int | None:
    parsed = parse_utc_datetime(value)
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))

def payload_bool(payload: dict, key: str, *, default: bool = True) -> bool:
    if key not in payload:
        return default
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"false", "0", "no", "n", "off", "禁用", "关闭"}:
        return False
    if text in {"true", "1", "yes", "y", "on", "启用", "开启"}:
        return True
    return default

def llm_http_exception(exc: LLMRequestError) -> HTTPException:
    return HTTPException(status_code=exc.api_status_code, detail=str(exc))

def payload_int(
    payload: dict,
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = payload.get(key, default)
    if raw is None or raw == "":
        raw = default
    if isinstance(raw, bool):
        raise HTTPException(status_code=422, detail=f"{key} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{key} must be an integer") from exc
    return max(minimum, min(value, maximum))

def payload_float(
    payload: dict,
    key: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = payload.get(key, default)
    if raw is None or raw == "":
        raw = default
    if isinstance(raw, bool):
        raise HTTPException(status_code=422, detail=f"{key} must be a number")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{key} must be a number") from exc
    return max(minimum, min(value, maximum))

def require_training_export_token(authorization: str | None) -> None:
    token = runtime_config().training_export_token
    if not token:
        raise HTTPException(status_code=403, detail="training data export token is not configured")
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=403, detail="valid bearer token is required")
    provided = authorization[len(prefix) :].strip()
    if not secrets.compare_digest(provided, token):
        raise HTTPException(status_code=403, detail="valid bearer token is required")
