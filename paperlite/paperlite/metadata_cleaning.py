from __future__ import annotations

import html
import re
from typing import Any

from paperlite.identity import doi_from_text, nature_doi_from_url
from paperlite.models import Paper

MIN_ABSTRACT_CHARS = 80
MIN_ABSTRACT_WORDS = 12
ARXIV_ID_RE = r"arxiv\s*:\s*\d{4}\.\d{4,5}(?:v\d+)?"


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _strip_leading_feed_boilerplate(text: str) -> str:
    text = re.sub(rf"^\s*{ARXIV_ID_RE}(?:\s*\[[^\]]+\])?\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*announce(?:ment)?\s+type\s*:?\s*[A-Za-z_-]{1,30}\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(?:abstract|summary)\s*:\s*", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _doi_from_value(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        for item in value.values():
            if doi := _doi_from_value(item):
                return doi
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if doi := _doi_from_value(item):
                return doi
        return None
    text = str(value)
    return doi_from_text(text) or nature_doi_from_url(text)


def _infer_payload_doi(payload: dict[str, Any]) -> str | None:
    candidates: list[Any] = [
        payload.get("doi"),
        payload.get("url"),
        payload.get("id"),
        payload.get("abstract"),
        payload.get("source_records"),
        payload.get("_daily_source_records"),
    ]
    for candidate in candidates:
        if doi := _doi_from_value(candidate):
            return doi
    return None


def clean_abstract_text(
    value: Any,
    *,
    title: str | None = None,
    doi: str | None = None,
    journal: str | None = None,
    venue: str | None = None,
) -> str:
    text = clean_text(value)
    if not text:
        return ""

    text = _strip_leading_feed_boilerplate(text)
    text = re.sub(r"\bTOC\s+Graphic\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bGraphical\s+abstract\b", " ", text, flags=re.IGNORECASE)
    if doi:
        text = re.sub(re.escape(str(doi)), " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\bdoi\s*:?\s*(?:https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"https?://(?:dx\.)?doi\.org/10\.\d{4,9}/\S+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bdoi\s*:?\s*", " ", text, flags=re.IGNORECASE)
    text = " ".join(text.split(" ;"))
    text = " ".join(text.split())

    text = re.sub(
        r"^[^.;]{0,140}\bPublished\s+online\s*:\s*[^.;]+[.;]?\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^Published\s+online\s*:\s*[^.;]+[.;]?\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^Online\s+ahead\s+of\s+print\s*[.;:]?\s*", " ", text, flags=re.IGNORECASE)
    text = " ".join(text.split())

    for label in (journal, venue):
        if label and _normalize_for_compare(text) == _normalize_for_compare(str(label)):
            return ""
    if title and _normalize_for_compare(text) == _normalize_for_compare(str(title)):
        return ""
    return text


def has_usable_abstract(
    value: Any,
    *,
    title: str | None = None,
    doi: str | None = None,
    journal: str | None = None,
    venue: str | None = None,
) -> bool:
    text = clean_abstract_text(value, title=title, doi=doi, journal=journal, venue=venue)
    if len(text) < MIN_ABSTRACT_CHARS:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z-]+", text)
    return len(words) >= MIN_ABSTRACT_WORDS


def sanitize_paper_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    doi = _infer_payload_doi(cleaned)
    if doi:
        cleaned["doi"] = doi
    title = clean_text(cleaned.get("title"))
    abstract = clean_abstract_text(
        cleaned.get("abstract"),
        title=title,
        doi=doi or cleaned.get("doi"),
        journal=cleaned.get("journal"),
        venue=cleaned.get("venue"),
    )
    cleaned["title"] = title
    cleaned["abstract"] = abstract if has_usable_abstract(abstract, title=title) else ""
    return cleaned


def sanitize_paper(paper: Paper) -> Paper:
    payload = sanitize_paper_payload(paper.to_dict())
    updates = {"title": payload["title"], "abstract": payload["abstract"], "doi": payload.get("doi")}
    if hasattr(paper, "model_copy"):
        return paper.model_copy(update=updates)
    return paper.copy(update=updates)
