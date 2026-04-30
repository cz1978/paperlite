from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from paperlite.connectors.base import ApiConnector, Enricher
from paperlite.dedupe import merge_papers
from paperlite.enrichment_matching import confident_enrichment_match
from paperlite.identity import normalize_doi, paper_id
from paperlite.models import Paper
from paperlite.timeparse import in_window, utcnow_naive

OPENALEX_WORKS_API = "https://api.openalex.org/works"


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10])
    except ValueError:
        return None


def _abstract_from_inverted_index(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            try:
                words.append((int(pos), str(word)))
            except (TypeError, ValueError):
                continue
    return " ".join(word for _, word in sorted(words))


def _source(work: dict[str, Any]) -> dict[str, Any]:
    primary = work.get("primary_location") or {}
    return primary.get("source") or {}


def _concepts(work: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in work.get("concepts") or []:
        name = item.get("display_name")
        if name:
            out.append(str(name))
    for topic in work.get("topics") or []:
        name = topic.get("display_name")
        if name and name not in out:
            out.append(str(name))
    return out


def paper_from_openalex_work(work: dict[str, Any], source: str = "openalex") -> Paper | None:
    title = " ".join(str(work.get("title") or work.get("display_name") or "").split())
    if not title:
        return None

    doi = normalize_doi(work.get("doi"))
    openalex_id = work.get("id")
    primary = work.get("primary_location") or {}
    landing_url = primary.get("landing_page_url") or work.get("doi") or openalex_id
    pdf_url = primary.get("pdf_url")
    if not landing_url:
        return None

    venue_source = _source(work)
    venue = venue_source.get("display_name")
    issn = venue_source.get("issn") or []
    issn_l = venue_source.get("issn_l")
    if issn_l and issn_l not in issn:
        issn = [issn_l, *issn]

    authors = [
        author.get("author", {}).get("display_name")
        for author in work.get("authorships") or []
        if author.get("author", {}).get("display_name")
    ]
    concepts = _concepts(work)

    if doi:
        pid = paper_id(source, landing_url, doi)
    else:
        openalex_suffix = str(openalex_id or "").rstrip("/").rsplit("/", 1)[-1]
        pid = f"openalex:{openalex_suffix}" if openalex_suffix else paper_id(source, landing_url)

    return Paper(
        id=pid,
        source=source,
        source_type="metadata",
        title=title,
        abstract=_abstract_from_inverted_index(work.get("abstract_inverted_index")),
        authors=authors,
        url=landing_url,
        pdf_url=pdf_url,
        doi=doi,
        published_at=_date(work.get("publication_date")),
        categories=concepts,
        journal=venue,
        venue=venue,
        publisher=venue_source.get("host_organization_name"),
        issn=issn,
        openalex_id=openalex_id,
        citation_count=work.get("cited_by_count"),
        concepts=concepts,
        source_records=[
            {
                "source": "openalex",
                "id": openalex_id,
                "doi": doi,
                "cited_by_count": work.get("cited_by_count"),
            }
        ],
        raw={"source": "openalex", "id": openalex_id},
    )


class OpenAlexConnector(ApiConnector, Enricher):
    name = "openalex"
    source_type = "metadata"
    capabilities = ("latest", "search", "enrich")

    def __init__(self, mailto: str | None = None):
        self.mailto = mailto

    def _params(self, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {"per-page": max(1, min(limit, 200))}
        if self.mailto:
            params["mailto"] = self.mailto
        return params

    def _filters(self, since: datetime | None, until: datetime | None) -> str | None:
        parts = []
        if since:
            parts.append(f"from_publication_date:{since.date().isoformat()}")
        if until:
            parts.append(f"until_publication_date:{until.date().isoformat()}")
        return ",".join(parts) if parts else None

    def _request(self, params: dict[str, Any], timeout_seconds: float | None = None) -> list[Paper]:
        response = httpx.get(OPENALEX_WORKS_API, params=params, timeout=timeout_seconds or 30)
        response.raise_for_status()
        data = response.json()
        return [
            paper for item in data.get("results") or []
            if (paper := paper_from_openalex_work(item))
        ]

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        since = since or (utcnow_naive() - timedelta(days=7))
        params = self._params(limit)
        params["sort"] = "publication_date:desc"
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
        params = self._params(limit)
        params["search"] = " ".join(str(query).split())
        params["sort"] = "relevance_score:desc"
        if filters := self._filters(since, until):
            params["filter"] = filters
        papers = self._request(params, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def _work_by_doi(self, doi: str, timeout_seconds: float | None = None) -> Paper | None:
        params = {}
        if self.mailto:
            params["mailto"] = self.mailto
        response = httpx.get(f"{OPENALEX_WORKS_API}/doi:{doi}", params=params, timeout=timeout_seconds or 30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return paper_from_openalex_work(response.json())

    def enrich(self, paper: Paper, timeout_seconds: float | None = None) -> Paper:
        if paper.doi:
            found = self._work_by_doi(paper.doi, timeout_seconds=timeout_seconds)
            return merge_papers(paper, found) if found and confident_enrichment_match(paper, found) else paper
        found = None
        if paper.title:
            results = self.search(paper.title, limit=1, timeout_seconds=timeout_seconds)
            found = results[0] if results else None
        return merge_papers(paper, found) if found and confident_enrichment_match(paper, found) else paper
