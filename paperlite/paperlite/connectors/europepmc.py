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

EUROPEPMC_SEARCH_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y %b %d", "%Y"):
        try:
            parsed = datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt)
            return parsed
        except ValueError:
            continue
    return None


def _list_from_field(value: Any, key: str | None = None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        if key and key in value:
            return _list_from_field(value[key])
        out = []
        for item in value.values():
            out.extend(_list_from_field(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_list_from_field(item, key))
        return out
    text = str(value).strip()
    return [text] if text else []


def _full_text_url(item: dict[str, Any]) -> str | None:
    urls = item.get("fullTextUrlList", {})
    if not isinstance(urls, dict):
        return None
    value = urls.get("fullTextUrl")
    if isinstance(value, dict):
        return value.get("url")
    if isinstance(value, list) and value:
        first = value[0]
        return first.get("url") if isinstance(first, dict) else None
    return None


def paper_from_europepmc_item(item: dict[str, Any]) -> Paper | None:
    title = " ".join(str(item.get("title") or "").split())
    if not title:
        return None
    doi = normalize_doi(item.get("doi"))
    pmid = item.get("pmid") or (item.get("id") if item.get("source") == "MED" else None)
    pmcid = item.get("pmcid")
    url = _full_text_url(item)
    url = url or (f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}" if item.get("id") else None)
    if not url:
        return None

    source_type = "preprint" if str(item.get("source") or "").upper() == "PPR" else "journal"
    categories = _list_from_field(item.get("keywordList"), "keyword")
    categories.extend(_list_from_field(item.get("meshHeadingList"), "meshHeading"))
    categories = list(dict.fromkeys(categories))
    authors = [part.strip() for part in str(item.get("authorString") or "").split(",") if part.strip()]

    return Paper(
        id=paper_id("europepmc", url, doi) if doi else f"europepmc:{item.get('source')}:{item.get('id')}",
        source="europepmc",
        source_type=source_type,
        title=title,
        abstract=" ".join(str(item.get("abstractText") or "").split()),
        authors=authors,
        url=url,
        doi=doi,
        published_at=_date(item.get("firstPublicationDate") or item.get("firstIndexDate") or item.get("pubYear")),
        categories=categories,
        journal=item.get("journalTitle"),
        venue=item.get("journalTitle"),
        publisher=item.get("publisher"),
        pmid=pmid,
        pmcid=pmcid,
        concepts=categories,
        source_records=[
            {
                "source": "europepmc",
                "id": item.get("id"),
                "source_id": item.get("source"),
                "pmid": pmid,
                "pmcid": pmcid,
                "doi": doi,
            }
        ],
        raw={"source": "europepmc", "id": item.get("id"), "source_id": item.get("source")},
    )


class EuropePMCConnector(ApiConnector, Enricher):
    name = "europepmc"
    source_type = "metadata"
    capabilities = ("latest", "search", "enrich")

    def _request(self, query: str, limit: int, timeout_seconds: float | None = None) -> list[Paper]:
        response = httpx.get(
            EUROPEPMC_SEARCH_API,
            params={
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": max(1, min(limit, 200)),
            },
            timeout=timeout_seconds or 30,
        )
        response.raise_for_status()
        items = response.json().get("resultList", {}).get("result") or []
        return [
            paper for item in items
            if (paper := paper_from_europepmc_item(item))
        ]

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        since = since or (utcnow_naive() - timedelta(days=7))
        until = until or utcnow_naive()
        query = f"FIRST_PDATE:[{since.date().isoformat()} TO {until.date().isoformat()}] sort_date:y"
        papers = self._request(query, limit, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        search_query = f"({query}) sort_date:y"
        papers = self._request(search_query, limit, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def enrich(self, paper: Paper, timeout_seconds: float | None = None) -> Paper:
        if paper.pmid:
            results = self.search(f"EXT_ID:{paper.pmid}", limit=1, timeout_seconds=timeout_seconds)
        elif paper.doi:
            results = self.search(f"DOI:{paper.doi}", limit=1, timeout_seconds=timeout_seconds)
        else:
            results = self.search(paper.title, limit=1, timeout_seconds=timeout_seconds) if paper.title else []
        return merge_papers(paper, results[0]) if results and confident_enrichment_match(paper, results[0]) else paper
