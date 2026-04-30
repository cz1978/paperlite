from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

import httpx

from paperlite.connectors.base import ApiConnector
from paperlite.identity import normalize_doi, paper_id
from paperlite.models import Paper
from paperlite.timeparse import in_window, utcnow_naive

XRXIV_API = "https://api.biorxiv.org/details/{server}/{start}/{end}/{cursor}/json"


def paper_from_xrxiv_item(item: dict, server: str) -> Optional[Paper]:
    source = server.lower()
    doi = normalize_doi(item.get("doi"))
    if not doi:
        return None
    version = str(item.get("version") or "1")
    host = "www.biorxiv.org" if source == "biorxiv" else "www.medrxiv.org"
    url = f"https://{host}/content/{doi}v{version}"
    published_at = None
    if item.get("date"):
        try:
            published_at = datetime.strptime(str(item["date"]), "%Y-%m-%d")
        except ValueError:
            published_at = None
    authors_raw = item.get("authors", "")
    if isinstance(authors_raw, list):
        authors = [str(x).strip() for x in authors_raw if str(x).strip()]
    else:
        authors = [x.strip() for x in str(authors_raw).split(";") if x.strip()]
    category = " ".join(str(item.get("category", "")).split())
    categories = [category] if category else []

    return Paper(
        id=paper_id(source, url, doi),
        source=source,
        source_type="preprint",
        title=" ".join(str(item.get("title", "")).split()),
        abstract=" ".join(str(item.get("abstract", "")).split()),
        authors=authors,
        url=url,
        pdf_url=f"{url}.full.pdf",
        doi=doi,
        published_at=published_at,
        categories=categories,
        journal=None,
        venue="bioRxiv" if source == "biorxiv" else "medRxiv",
        publisher="Cold Spring Harbor Laboratory",
        source_records=[{"source": source, "doi": doi, "version": version}],
        raw={"source": source, "version": version},
    )


class XrxivConnector(ApiConnector):
    source_type = "preprint"
    capabilities = ("latest", "search")

    def __init__(self, server: str):
        if server not in {"biorxiv", "medrxiv"}:
            raise ValueError("server must be biorxiv or medrxiv")
        self.name = server
        self.server = server

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        until = until or utcnow_naive()
        since = since or (until - timedelta(days=1))
        since = datetime.combine(since.date(), time.min)
        until = datetime.combine(until.date(), time.max)
        cursor = 0
        papers: list[Paper] = []

        while len(papers) < limit:
            url = XRXIV_API.format(
                server=self.server,
                start=since.strftime("%Y-%m-%d"),
                end=until.strftime("%Y-%m-%d"),
                cursor=cursor,
            )
            response = httpx.get(url, timeout=timeout_seconds or 30)
            response.raise_for_status()
            collection = response.json().get("collection") or []
            if not collection:
                break
            for item in collection:
                paper = paper_from_xrxiv_item(item, self.server)
                if paper and in_window(paper.published_at, since, until):
                    papers.append(paper)
            if len(collection) < 100:
                break
            cursor += len(collection)

        papers.sort(key=lambda p: p.published_at or datetime.min, reverse=True)
        return papers[:limit]

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
    ) -> list[Paper]:
        q = str(query).lower()
        papers = self.fetch_latest(since=since, until=until, limit=max(limit * 5, 50))
        return [
            p for p in papers
            if q in p.title.lower() or q in p.abstract.lower()
        ][:limit]
