from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

import httpx

from paperlite.config import ZOTERO_API_BASE_URL, load_config
from paperlite.models import Paper

ZOTERO_BATCH_LIMIT = 50


class ZoteroNotConfiguredError(RuntimeError):
    pass


class ZoteroRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZoteroConfig:
    api_key: str
    library_type: str
    library_id: str
    collection_key: str | None = None
    api_base_url: str = ZOTERO_API_BASE_URL

    @property
    def library_path(self) -> str:
        prefix = "groups" if self.library_type == "group" else "users"
        return f"/{prefix}/{self.library_id}"


def load_zotero_config(env: Mapping[str, str] | None = None) -> ZoteroConfig:
    settings = load_config(env)
    api_key = settings.zotero_api_key or ""
    library_type = settings.zotero_library_type
    library_id = settings.zotero_library_id or ""
    collection_key = settings.zotero_collection_key
    if not api_key or not library_id:
        raise ZoteroNotConfiguredError("Zotero API key and library id are required")
    if library_type not in {"user", "group"}:
        raise ZoteroNotConfiguredError("ZOTERO_LIBRARY_TYPE must be user or group")
    return ZoteroConfig(
        api_key=api_key,
        library_type=library_type,
        library_id=library_id,
        collection_key=collection_key,
        api_base_url=settings.zotero_api_base_url,
    )


def zotero_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    try:
        config = load_zotero_config(env)
    except ZoteroNotConfiguredError as exc:
        return {
            "configured": False,
            "reason": str(exc),
        }
    return {
        "configured": True,
        "library_type": config.library_type,
        "library_id": config.library_id,
        "collection_key": config.collection_key,
    }


def _paper_date(value: datetime | None) -> str:
    return value.date().isoformat() if value else ""


def _item_type(paper: Paper) -> str:
    if paper.source_type == "preprint":
        return "preprint"
    if paper.source_type == "journal" or paper.journal or paper.venue:
        return "journalArticle"
    return "webpage"


def _creators(authors: Iterable[str]) -> list[dict[str, str]]:
    return [
        {
            "creatorType": "author",
            "name": str(author).strip(),
        }
        for author in authors
        if str(author).strip()
    ]


def _tags(paper: Paper) -> list[dict[str, str]]:
    raw_tags = ["paperlite", f"source:{paper.source}", *paper.categories, *paper.concepts]
    seen: set[str] = set()
    tags: list[dict[str, str]] = []
    for tag in raw_tags:
        value = str(tag).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        tags.append({"tag": value})
    return tags


def _extra(paper: Paper) -> str:
    fields = [
        ("PaperLite ID", paper.id),
        ("PaperLite source", paper.source),
        ("PMID", paper.pmid),
        ("PMCID", paper.pmcid),
        ("OpenAlex", paper.openalex_id),
        ("External PDF URL", paper.pdf_url),
    ]
    return "\n".join(f"{label}: {value}" for label, value in fields if value)


def paper_to_zotero_item(paper: Paper, collection_key: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "itemType": _item_type(paper),
        "title": paper.title,
        "creators": _creators(paper.authors),
        "abstractNote": paper.abstract or "",
        "date": _paper_date(paper.published_at),
        "url": paper.url,
        "DOI": paper.doi or "",
        "publicationTitle": paper.venue or paper.journal or "",
        "publisher": paper.publisher or "",
        "tags": _tags(paper),
        "collections": [collection_key] if collection_key else [],
        "extra": _extra(paper),
    }
    return item


def _chunks(items: list[Paper], size: int) -> Iterable[tuple[int, list[Paper]]]:
    for start in range(0, len(items), size):
        yield start, items[start:start + size]


PostFunc = Callable[..., httpx.Response]


def create_zotero_items(
    papers: list[Paper],
    *,
    config: ZoteroConfig | None = None,
    post: PostFunc = httpx.post,
    timeout_seconds: float = 20.0,
) -> dict[str, object]:
    cfg = config or load_zotero_config()
    created: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    headers_base = {
        "Zotero-API-Key": cfg.api_key,
        "Zotero-API-Version": "3",
        "content-type": "application/json",
    }
    url = f"{cfg.api_base_url}{cfg.library_path}/items"
    for offset, batch in _chunks(papers, ZOTERO_BATCH_LIMIT):
        payload = [paper_to_zotero_item(paper, cfg.collection_key) for paper in batch]
        headers = dict(headers_base)
        headers["Zotero-Write-Token"] = uuid.uuid4().hex
        try:
            response = post(url, headers=headers, json=payload, timeout=timeout_seconds)
        except httpx.TimeoutException as exc:
            raise ZoteroRequestError("Zotero API request timed out") from exc
        except httpx.RequestError as exc:
            raise ZoteroRequestError(f"Zotero API request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise ZoteroRequestError(f"Zotero API returned HTTP {response.status_code}: {response.text[:240]}")
        try:
            body = response.json() if response.content else {}
        except ValueError as exc:
            raise ZoteroRequestError("Zotero API returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise ZoteroRequestError("Zotero API returned invalid JSON object")
        successes = body.get("successful") or {}
        failures = body.get("failed") or {}
        for index_text, value in successes.items():
            index = offset + int(index_text)
            item_key = value.get("key") if isinstance(value, dict) else value
            created.append(
                {
                    "index": index,
                    "paper_id": papers[index].id,
                    "zotero_key": item_key,
                }
            )
        for index_text, value in failures.items():
            index = offset + int(index_text)
            failed.append(
                {
                    "index": index,
                    "paper_id": papers[index].id,
                    "error": value,
                }
            )
    return {
        "configured": True,
        "submitted": len(papers),
        "created": created,
        "failed": failed,
        "library": {
            "type": cfg.library_type,
            "id": cfg.library_id,
            "collection_key": cfg.collection_key,
        },
    }
