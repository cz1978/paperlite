from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from paperlite.connectors.base import ApiConnector, Enricher
from paperlite.dedupe import merge_papers
from paperlite.enrichment_matching import confident_enrichment_match
from paperlite.identity import normalize_doi, paper_id
from paperlite.models import Paper
from paperlite.timeparse import in_window, utcnow_naive

CROSSREF_WORKS_API = "https://api.crossref.org/works"


def _clean(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return re.sub(r"<[^>]+>", "", text)


def _first(values: Any) -> str | None:
    if isinstance(values, list) and values:
        return str(values[0])
    if values:
        return str(values)
    return None


def _date_from_parts(value: Any) -> datetime | None:
    if not isinstance(value, dict):
        return None
    parts_list = value.get("date-parts") or []
    if not parts_list or not parts_list[0]:
        return None
    parts = list(parts_list[0])
    while len(parts) < 3:
        parts.append(1)
    try:
        return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None


def _authors(item: dict[str, Any]) -> list[str]:
    out = []
    for author in item.get("author") or []:
        name = " ".join(
            part for part in [
                str(author.get("given") or "").strip(),
                str(author.get("family") or "").strip(),
            ]
            if part
        )
        if name:
            out.append(name)
    return out


def _source_type(item: dict[str, Any]) -> str:
    item_type = str(item.get("type") or "").lower()
    if item_type == "posted-content":
        return "preprint"
    if item_type in {"journal-article", "journal-issue"}:
        return "journal"
    return "metadata"


def paper_from_crossref_item(
    item: dict[str, Any],
    source: str = "crossref",
    source_type: str | None = None,
) -> Paper | None:
    title = _clean(_first(item.get("title")))
    doi = normalize_doi(item.get("DOI") or item.get("doi"))
    url = item.get("URL") or (f"https://doi.org/{doi}" if doi else None)
    if not title or not url:
        return None

    journal = _first(item.get("container-title"))
    published_at = (
        _date_from_parts(item.get("published-print"))
        or _date_from_parts(item.get("published-online"))
        or _date_from_parts(item.get("published"))
        or _date_from_parts(item.get("issued"))
    )
    categories = [str(x) for x in item.get("subject") or [] if str(x).strip()]
    issn = [str(x) for x in item.get("ISSN") or [] if str(x).strip()]

    return Paper(
        id=paper_id(source, url, doi),
        source=source,
        source_type=source_type or _source_type(item),
        title=title,
        abstract=_clean(item.get("abstract")),
        authors=_authors(item),
        url=url,
        doi=doi,
        published_at=published_at,
        categories=categories,
        journal=journal,
        venue=journal,
        publisher=item.get("publisher"),
        issn=issn,
        concepts=categories,
        source_records=[
            {
                "source": "crossref",
                "doi": doi,
                "type": item.get("type"),
                "publisher": item.get("publisher"),
            }
        ],
        raw={"source": "crossref", "doi": doi, "type": item.get("type")},
    )


class CrossrefConnector(ApiConnector, Enricher):
    name = "crossref"
    source_type = "metadata"
    capabilities = ("latest", "search", "enrich")

    def _filters(self, since: datetime | None, until: datetime | None, extra: list[str] | None = None) -> str | None:
        parts = list(extra or [])
        if since:
            parts.append(f"from-pub-date:{since.date().isoformat()}")
        if until:
            parts.append(f"until-pub-date:{until.date().isoformat()}")
        return ",".join(parts) if parts else None

    def _request(self, params: dict[str, Any], timeout_seconds: float | None = None) -> list[Paper]:
        response = httpx.get(CROSSREF_WORKS_API, params=params, timeout=timeout_seconds or 30)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items") or []
        return [
            paper for item in items
            if (paper := paper_from_crossref_item(item))
        ]

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        since = since or (utcnow_naive() - timedelta(days=7))
        params: dict[str, Any] = {
            "rows": max(1, min(limit, 200)),
            "sort": "published",
            "order": "desc",
        }
        if filters := self._filters(since, until):
            params["filter"] = filters
        papers = self._request(params, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        params: dict[str, Any] = {
            "query.bibliographic": " ".join(str(query).split()),
            "rows": max(1, min(limit, 200)),
            "sort": "score",
            "order": "desc",
        }
        if filters := self._filters(since, until):
            params["filter"] = filters
        papers = self._request(params, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def _work_by_doi(self, doi: str, timeout_seconds: float | None = None) -> Paper | None:
        response = httpx.get(f"{CROSSREF_WORKS_API}/{quote(doi, safe='')}", timeout=timeout_seconds or 30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json().get("message") or {}
        return paper_from_crossref_item(item)

    def enrich(self, paper: Paper, timeout_seconds: float | None = None) -> Paper:
        if paper.doi:
            found = self._work_by_doi(paper.doi, timeout_seconds=timeout_seconds)
            return merge_papers(paper, found) if found and confident_enrichment_match(paper, found) else paper
        found = None
        if paper.title:
            results = self.search(paper.title, limit=1, timeout_seconds=timeout_seconds)
            found = results[0] if results else None
        return merge_papers(paper, found) if found and confident_enrichment_match(paper, found) else paper
