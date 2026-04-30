from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from paperlite.connectors.base import ApiConnector, Enricher
from paperlite.dedupe import merge_papers
from paperlite.enrichment_matching import confident_enrichment_match
from paperlite.identity import normalize_doi, paper_id
from paperlite.models import Paper
from paperlite.timeparse import in_window, utcnow_naive

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _text(node: ET.Element | None, path: str | None = None) -> str:
    target = node.find(path) if node is not None and path else node
    if target is None:
        return ""
    return " ".join("".join(target.itertext()).split())


def _pub_date(article: ET.Element | None) -> datetime | None:
    pub_date = article.find("./Journal/JournalIssue/PubDate") if article is not None else None
    if pub_date is None:
        return None
    year = _text(pub_date, "Year")
    month = _text(pub_date, "Month") or "1"
    day = _text(pub_date, "Day") or "1"
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    try:
        month_num = int(month)
    except ValueError:
        month_num = month_map.get(month[:3].lower(), 1)
    try:
        return datetime(int(year), month_num, int(day))
    except (TypeError, ValueError):
        return None


def _authors(article: ET.Element | None) -> list[str]:
    out = []
    for author in article.findall("./AuthorList/Author") if article is not None else []:
        collective = _text(author, "CollectiveName")
        if collective:
            out.append(collective)
            continue
        name = " ".join(part for part in [_text(author, "ForeName"), _text(author, "LastName")] if part)
        if name:
            out.append(name)
    return out


def _ids(pubmed_article: ET.Element) -> tuple[str | None, str | None, str | None]:
    pmid = _text(pubmed_article, "./MedlineCitation/PMID") or None
    doi = None
    pmcid = None
    for article_id in pubmed_article.findall("./PubmedData/ArticleIdList/ArticleId"):
        id_type = (article_id.attrib.get("IdType") or "").lower()
        value = _text(article_id) or None
        if id_type == "doi":
            doi = normalize_doi(value)
        elif id_type == "pmc":
            pmcid = value
    return pmid, doi, pmcid


def _categories(pubmed_article: ET.Element) -> list[str]:
    out = []
    for descriptor in pubmed_article.findall("./MedlineCitation/MeshHeadingList/MeshHeading/DescriptorName"):
        value = _text(descriptor)
        if value and value not in out:
            out.append(value)
    for keyword in pubmed_article.findall("./MedlineCitation/KeywordList/Keyword"):
        value = _text(keyword)
        if value and value not in out:
            out.append(value)
    return out


def paper_from_pubmed_article(pubmed_article: ET.Element) -> Paper | None:
    citation = pubmed_article.find("./MedlineCitation")
    article = citation.find("./Article") if citation is not None else None
    pmid, doi, pmcid = _ids(pubmed_article)
    title = _text(article, "ArticleTitle")
    if not title or not pmid:
        return None
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    journal = _text(article, "./Journal/Title") or None
    issn = _text(article, "./Journal/ISSN")
    abstract = "\n".join(
        _text(node) for node in article.findall("./Abstract/AbstractText")
    ) if article is not None else ""
    categories = _categories(pubmed_article)

    return Paper(
        id=paper_id("pubmed", url, doi) if doi else f"pmid:{pmid}",
        source="pubmed",
        source_type="journal",
        title=title,
        abstract=abstract,
        authors=_authors(article),
        url=url,
        doi=doi,
        published_at=_pub_date(article),
        categories=categories,
        journal=journal,
        venue=journal,
        issn=[issn] if issn else [],
        pmid=pmid,
        pmcid=pmcid,
        concepts=categories,
        source_records=[{"source": "pubmed", "pmid": pmid, "pmcid": pmcid, "doi": doi}],
        raw={"source": "pubmed", "pmid": pmid},
    )


class PubMedConnector(ApiConnector, Enricher):
    name = "pubmed"
    source_type = "journal"
    capabilities = ("latest", "search", "enrich")

    def _search_ids(
        self,
        term: str,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        timeout_seconds: float | None = None,
    ) -> list[str]:
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": term,
            "retmax": max(1, min(limit, 200)),
            "retmode": "json",
            "sort": "pub date",
        }
        if since or until:
            params["datetype"] = "pdat"
            if since:
                params["mindate"] = since.strftime("%Y/%m/%d")
            if until:
                params["maxdate"] = until.strftime("%Y/%m/%d")
        response = httpx.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=timeout_seconds or 30)
        response.raise_for_status()
        return response.json().get("esearchresult", {}).get("idlist") or []

    def _fetch(self, ids: list[str], timeout_seconds: float | None = None) -> list[Paper]:
        if not ids:
            return []
        response = httpx.get(
            f"{EUTILS}/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            timeout=timeout_seconds or 30,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        return [
            paper for article in root.findall("./PubmedArticle")
            if (paper := paper_from_pubmed_article(article))
        ]

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        since = since or (utcnow_naive() - timedelta(days=7))
        ids = self._search_ids("all[sb]", since, until, limit, timeout_seconds=timeout_seconds)
        papers = self._fetch(ids, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def search(
        self,
        query: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 20,
        timeout_seconds: float | None = None,
    ) -> list[Paper]:
        ids = self._search_ids(str(query), since, until, limit, timeout_seconds=timeout_seconds)
        papers = self._fetch(ids, timeout_seconds=timeout_seconds)
        return [paper for paper in papers if in_window(paper.published_at, since, until)][:limit]

    def enrich(self, paper: Paper, timeout_seconds: float | None = None) -> Paper:
        if paper.pmid:
            found = self._fetch([paper.pmid], timeout_seconds=timeout_seconds)
            return merge_papers(paper, found[0]) if found and confident_enrichment_match(paper, found[0]) else paper
        term = f"{paper.doi}[doi]" if paper.doi else paper.title
        results = self.search(term, limit=1, timeout_seconds=timeout_seconds) if term else []
        return merge_papers(paper, results[0]) if results and confident_enrichment_match(paper, results[0]) else paper
