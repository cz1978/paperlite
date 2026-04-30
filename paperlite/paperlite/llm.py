from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from paperlite.config import runtime_config


class LLMRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        api_status_code: int = 502,
        provider_status_code: int | None = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.api_status_code = api_status_code
        self.provider_status_code = provider_status_code
        self.retryable = retryable


@dataclass(frozen=True)
class LLMSettings:
    base_url: str | None
    api_key: str | None
    model: str | None

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)


def llm_settings() -> LLMSettings:
    config = runtime_config()
    return LLMSettings(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model,
    )


def embedding_settings() -> LLMSettings:
    config = runtime_config()
    return LLMSettings(
        base_url=config.embedding_base_url,
        api_key=config.embedding_api_key,
        model=config.embedding_model,
    )


def llm_status() -> dict[str, Any]:
    settings = llm_settings()
    return {
        "configured": settings.configured,
        "model": settings.model,
        "base_url": settings.base_url,
    }


def embedding_status() -> dict[str, Any]:
    settings = embedding_settings()
    return {
        "configured": settings.configured,
        "model": settings.model,
        "base_url": settings.base_url,
    }


def _chat_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/chat/completions"
    return f"{clean}/v1/chat/completions"


def _embedding_url(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/embeddings"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/embeddings"
    return f"{clean}/v1/embeddings"


def _status_error(exc: httpx.HTTPStatusError) -> LLMRequestError:
    status_code = exc.response.status_code
    if status_code == 429:
        api_status = 429
    elif status_code == 503:
        api_status = 503
    else:
        api_status = 502
    retryable = status_code == 429 or status_code >= 500
    return LLMRequestError(
        f"llm_http_error: provider returned {status_code}",
        api_status_code=api_status,
        provider_status_code=status_code,
        retryable=retryable,
    )


def complete_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    settings = llm_settings()
    if not settings.configured:
        return {
            "configured": False,
            "model": settings.model,
            "answer": "",
            "warnings": ["llm_not_configured"],
        }

    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    try:
        response = httpx.post(
            _chat_url(settings.base_url or ""),
            headers=headers,
            json={
                "model": settings.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _status_error(exc) from exc
    except httpx.TimeoutException as exc:
        raise LLMRequestError("llm_timeout", api_status_code=503, retryable=True) from exc
    except httpx.RequestError as exc:
        raise LLMRequestError(f"llm_request_error: {exc}", api_status_code=503, retryable=True) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMRequestError("llm_invalid_json", api_status_code=502, retryable=True) from exc
    if not isinstance(data, dict):
        raise LLMRequestError("llm_invalid_response", api_status_code=502, retryable=True)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMRequestError("llm_invalid_response", api_status_code=502, retryable=True)
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LLMRequestError("llm_invalid_response", api_status_code=502, retryable=True)
    answer = message.get("content", "")
    if not isinstance(answer, str):
        raise LLMRequestError("llm_invalid_response", api_status_code=502, retryable=True)
    return {
        "configured": True,
        "model": settings.model,
        "answer": answer,
        "warnings": [],
    }


def create_embeddings(inputs: list[str]) -> dict[str, Any]:
    settings = embedding_settings()
    if not settings.configured:
        return {
            "configured": False,
            "model": settings.model,
            "embeddings": [],
            "warnings": ["embedding_not_configured"],
        }

    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"

    try:
        response = httpx.post(
            _embedding_url(settings.base_url or ""),
            headers=headers,
            json={
                "model": settings.model,
                "input": inputs,
            },
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _status_error(exc) from exc
    except httpx.TimeoutException as exc:
        raise LLMRequestError("embedding_timeout", api_status_code=503, retryable=True) from exc
    except httpx.RequestError as exc:
        raise LLMRequestError(f"embedding_request_error: {exc}", api_status_code=503, retryable=True) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMRequestError("embedding_invalid_json", api_status_code=502, retryable=True) from exc
    if not isinstance(data, dict):
        raise LLMRequestError("embedding_invalid_response", api_status_code=502, retryable=True)
    raw_items = data.get("data")
    if not isinstance(raw_items, list):
        raise LLMRequestError("embedding_invalid_response", api_status_code=502, retryable=True)
    ordered = sorted(
        (item for item in raw_items if isinstance(item, dict)),
        key=lambda item: int(item.get("index", 0) or 0),
    )
    embeddings: list[list[float]] = []
    for item in ordered:
        raw_embedding = item.get("embedding")
        if not isinstance(raw_embedding, list):
            raise LLMRequestError("embedding_invalid_response", api_status_code=502, retryable=True)
        try:
            vector = [float(value) for value in raw_embedding]
        except (TypeError, ValueError) as exc:
            raise LLMRequestError("embedding_invalid_response", api_status_code=502, retryable=True) from exc
        embeddings.append(vector)
    if len(embeddings) != len(inputs):
        raise LLMRequestError("embedding_invalid_response", api_status_code=502, retryable=True)
    return {
        "configured": True,
        "model": data.get("model") or settings.model,
        "embeddings": embeddings,
        "warnings": [],
    }
