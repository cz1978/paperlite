from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any, Optional

import feedparser
import httpx

from paperlite.identity import normalize_doi, paper_id, pdf_url_for_arxiv
from paperlite.models import Paper
from paperlite.timeparse import in_window
from paperlite.connectors.base import ApiConnector

ARXIV_API = "https://export.arxiv.org/api/query"
DEFAULT_CATEGORIES = ("cs.AI", "cs.LG", "cs.CL", "stat.ML")


def _get(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _clean(value: Any, max_len: Optional[int] = None) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_len] if max_len else text


def _published(entry: Any) -> Optional[datetime]:
    raw = _get(entry, "published_parsed") or _get(entry, "updated_parsed")
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(raw), tz=timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _authors(entry: Any) -> list[str]:
    authors: list[str] = []
    for author in _get(entry, "authors", []) or []:
        name = author.get("name", "") if isinstance(author, dict) else str(author)
        name = name.strip()
        if name:
            authors.append(name)
    if not authors and _get(entry, "author"):
        authors = [x.strip() for x in str(_get(entry, "author")).split(",") if x.strip()]
    return authors


def _categories(entry: Any) -> list[str]:
    out: list[str] = []
    primary = _get(entry, "arxiv_primary_category")
    if isinstance(primary, dict) and primary.get("term"):
        out.append(str(primary["term"]))
    for tag in _get(entry, "tags", []) or []:
        term = tag.get("term", "") if isinstance(tag, dict) else getattr(tag, "term", "")
        if term and term not in out:
            out.append(str(term))
    return out


def paper_from_arxiv_entry(entry: Any) -> Optional[Paper]:
    url = str(_get(entry, "link", "") or "").strip()
    if not url:
        return None
    doi = normalize_doi(_get(entry, "doi", None))
    pid = paper_id("arxiv", url, doi)
    arxiv_id = pid.split(":", 1)[1] if pid.startswith("arxiv:") else None
    doi = doi or (f"10.48550/arXiv.{arxiv_id}" if arxiv_id else None)

    links = _get(entry, "links", []) or []
    pdf_url = None
    for link in links:
        if isinstance(link, dict) and link.get("type") == "application/pdf":
            pdf_url = link.get("href")
            break
    pdf_url = pdf_url or pdf_url_for_arxiv(url)

    return Paper(
        id=pid,
        source="arxiv",
        source_type="preprint",
        title=_clean(_get(entry, "title", "")),
        abstract=_clean(_get(entry, "summary", ""), 4000),
        authors=_authors(entry),
        url=url,
        pdf_url=pdf_url,
        doi=doi,
        published_at=_published(entry),
        categories=_categories(entry),
        journal=None,
        venue="arXiv",
        publisher="Cornell University",
        source_records=[{"source": "arxiv", "id": _get(entry, "id", None), "doi": doi}],
        raw={"source": "arxiv", "entry_id": _get(entry, "id", None)},
    )


class ArxivConnector(ApiConnector):
    name = "arxiv"
    source_type = "preprint"
    capabilities = ("latest", "search")

    def __init__(self, categories: tuple[str, ...] = DEFAULT_CATEGORIES):
        self.categories = categories

    def _query(self, search_query: str, limit: int, timeout_seconds: float | None = None) -> list[Paper]:
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max(1, min(limit, 200)),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        response = httpx.get(ARXIV_API, params=params, timeout=timeout_seconds or 30)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        papers = [paper for entry in feed.entries if (paper := paper_from_arxiv_entry(entry))]
        return papers

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        category_query = " OR ".join(f"cat:{cat}" for cat in self.categories)
        papers = self._query(category_query, limit=max(limit * 2, limit), timeout_seconds=timeout_seconds)
        return [p for p in papers if in_window(p.published_at, since, until)][:limit]

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
    ) -> list[Paper]:
        safe_query = " ".join(str(query).split())
        papers = self._query(f'all:"{safe_query}"', limit=max(limit * 2, limit))
        return [p for p in papers if in_window(p.published_at, since, until)][:limit]
