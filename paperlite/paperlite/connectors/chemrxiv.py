from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from paperlite.connectors.base import ApiConnector
from paperlite.connectors.crossref import CROSSREF_WORKS_API, paper_from_crossref_item
from paperlite.timeparse import in_window, utcnow_naive
from paperlite.models import Paper

CHEMRXIV_CROSSREF_FILTERS = ["type:posted-content", "prefix:10.26434"]


class ChemrxivConnector(ApiConnector):
    name = "chemrxiv"
    source_type = "preprint"
    capabilities = ("latest", "search")

    def _filters(self, since: datetime | None, until: datetime | None) -> str:
        parts = list(CHEMRXIV_CROSSREF_FILTERS)
        if since:
            parts.append(f"from-pub-date:{since.date().isoformat()}")
        if until:
            parts.append(f"until-pub-date:{until.date().isoformat()}")
        return ",".join(parts)

    def _request(self, params: dict[str, Any], timeout_seconds: float | None = None) -> list[Paper]:
        response = httpx.get(CROSSREF_WORKS_API, params=params, timeout=timeout_seconds or 30)
        response.raise_for_status()
        items = response.json().get("message", {}).get("items") or []
        papers = []
        for item in items:
            paper = paper_from_crossref_item(item, source="chemrxiv", source_type="preprint")
            if paper:
                paper.venue = "ChemRxiv"
                paper.journal = None
                paper.source_records.append(
                    {
                        "source": "chemrxiv",
                        "doi": paper.doi,
                        "via": "crossref",
                    }
                )
                papers.append(paper)
        return papers

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        since = since or (utcnow_naive() - timedelta(days=30))
        params: dict[str, Any] = {
            "rows": max(1, min(limit, 200)),
            "sort": "published",
            "order": "desc",
            "filter": self._filters(since, until),
        }
        papers = self._request(params, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
    ) -> list[Paper]:
        params: dict[str, Any] = {
            "query.bibliographic": " ".join(str(query).split()),
            "rows": max(1, min(limit, 200)),
            "sort": "score",
            "order": "desc",
            "filter": self._filters(since, until),
        }
        papers = self._request(params)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]
