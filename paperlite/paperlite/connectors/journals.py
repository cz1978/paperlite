from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from xml.etree import ElementTree as ET

import feedparser

from paperlite.connectors.base import FeedConnector, SourceConfig
from paperlite.http_client import get_feed_url
from paperlite.identity import ams_doi_from_url, arxiv_doi_from_url, doi_from_text, nature_doi_from_url, paper_id
from paperlite.models import Paper
from paperlite.timeparse import in_window, parse_when, to_utc_naive


def _get(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _clean(value: Any, max_len: Optional[int] = None) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_len] if max_len else text


def _parse_date_text(value: Any) -> Optional[datetime]:
    text = _clean(re.sub(r"<[^>]+>", " ", str(value or "")))
    if not text:
        return None
    if match := re.search(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+)?Z?", text):
        if parsed := parse_when(match.group(0)):
            return parsed
    try:
        return to_utc_naive(parsedate_to_datetime(text))
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    if match := re.search(r"\b([A-Z][a-z]+)\s+(\d{4})\b", text):
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%B %Y")
        except ValueError:
            return None
    return None


def _description_publication_date(value: Any) -> Optional[datetime]:
    text = str(value or "")
    if "publication date" not in text.lower():
        return None
    return _parse_date_text(text)


def _published(entry: Any) -> Optional[datetime]:
    raw = _get(entry, "published_parsed") or _get(entry, "updated_parsed")
    if not raw:
        for key in ("published", "updated", "dc_date", "prism_publicationdate", "prism_coverdate"):
            if parsed := _parse_date_text(_get(entry, key)):
                return parsed
        for raw_date in _get(entry, "xml_dates", []) or []:
            if parsed := _parse_date_text(raw_date):
                return parsed
        return _description_publication_date(_get(entry, "summary")) or _description_publication_date(
            _get(entry, "description")
        )
    try:
        return datetime.fromtimestamp(calendar.timegm(raw), tz=timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def _xml_text(element: ET.Element) -> str:
    return _clean(" ".join(element.itertext()))


def _xml_entry_extras(xml_text: str) -> list[dict[str, list[str]]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    extras: list[dict[str, list[str]]] = []
    for item in root.findall(".//{*}item"):
        identifiers: list[str] = []
        dates: list[str] = []
        for child in list(item):
            local = child.tag.rsplit("}", 1)[-1].lower()
            text = _xml_text(child)
            if not text:
                continue
            if local in {"identifier", "doi"}:
                identifiers.append(text)
            elif local in {"date", "publicationdate", "coverdate", "coverdisplaydate"}:
                dates.append(text)
        extras.append({"xml_identifiers": identifiers, "xml_dates": dates})
    return extras


def _authors(entry: Any) -> list[str]:
    authors: list[str] = []
    for author in _get(entry, "authors", []) or []:
        name = author.get("name", "") if isinstance(author, dict) else str(author)
        if name.strip():
            authors.append(name.strip())
    if not authors and _get(entry, "author"):
        authors = [x.strip() for x in str(_get(entry, "author")).split(",") if x.strip()]
    return authors


def _categories(entry: Any) -> list[str]:
    out: list[str] = []
    for tag in _get(entry, "tags", []) or []:
        term = tag.get("term", "") if isinstance(tag, dict) else getattr(tag, "term", "")
        if term and term not in out:
            out.append(str(term))
    return out


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
    return doi_from_text(text) or nature_doi_from_url(text) or arxiv_doi_from_url(text) or ams_doi_from_url(text)


def _entry_doi(entry: Any, url: str) -> str | None:
    candidates = [
        _get(entry, "doi", None),
        _get(entry, "prism_doi", None),
        _get(entry, "dc_identifier", None),
        _get(entry, "dc_relation", None),
        _get(entry, "id", None),
        _get(entry, "guid", None),
        _get(entry, "link", None),
        _get(entry, "links", None),
        _get(entry, "xml_identifiers", None),
        _get(entry, "summary", None),
        _get(entry, "description", None),
    ]
    for candidate in candidates:
        if doi := _doi_from_value(candidate):
            return doi
    return nature_doi_from_url(url) or arxiv_doi_from_url(url) or ams_doi_from_url(url)


def paper_from_journal_entry(
    entry: Any,
    source: str,
    journal: str,
    config: SourceConfig | None = None,
) -> Optional[Paper]:
    url = str(_get(entry, "link", "") or _get(entry, "id", "") or "").strip()
    if not url:
        return None
    doi = _entry_doi(entry, url)
    title = _clean(_get(entry, "title", ""))
    abstract = _clean(_get(entry, "summary", "") or _get(entry, "description", ""), 4000)

    return Paper(
        id=paper_id(source, url, doi),
        source=source,
        source_type=config.type if config else "journal",
        title=title,
        abstract=abstract,
        authors=_authors(entry),
        url=url,
        pdf_url=None,
        doi=doi,
        published_at=_published(entry),
        categories=_categories(entry),
        journal=journal,
        venue=journal,
        publisher=config.publisher if config else None,
        issn=config.issn if config else [],
        source_records=[
            {
                "source": source,
                "endpoint": config.endpoint_key if config else source,
                "kind": "rss",
                "journal": journal,
                "url": url,
                "doi": doi,
                "entry_id": _get(entry, "id", None),
            }
        ],
        raw={"source": source, "journal": journal, "entry_id": _get(entry, "id", None)},
    )


class JournalFeedConnector(FeedConnector):
    source_type = "journal"
    capabilities = ("latest", "search")

    def __init__(
        self,
        name: str | None = None,
        feed_url: str | None = None,
        journal: str | None = None,
        config: SourceConfig | None = None,
    ):
        if config:
            self.name = config.key
            self.endpoint_key = config.endpoint_key or config.key
            self.source_type = config.type
            self.feed_url = config.url or ""
            self.journal = config.journal or config.key
            self.publisher = config.publisher
            self.issn = config.issn
            self.tier = config.tier
            self.topics = config.topics
            self.timeout_seconds = config.timeout_seconds
            self.config = config
            return

        self.name = name or ""
        self.endpoint_key = self.name
        self.feed_url = feed_url or ""
        self.journal = journal or self.name
        self.publisher = None
        self.issn = []
        self.tier = None
        self.topics = []
        self.timeout_seconds = None
        self.config = None

    def fetch_latest(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        timeout_seconds: float | None = None,
        request_profile: str = "paperlite",
    ) -> list[Paper]:
        response = get_feed_url(
            self.feed_url,
            timeout_seconds=timeout_seconds or self.timeout_seconds or 30.0,
            request_profile=request_profile,
        )
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        xml_extras = _xml_entry_extras(response.text)
        papers = []
        for index, entry in enumerate(feed.entries):
            entry_payload = entry
            if index < len(xml_extras) and any(xml_extras[index].values()):
                entry_payload = dict(entry)
                entry_payload.update(xml_extras[index])
            if paper := paper_from_journal_entry(entry_payload, self.name, self.journal, self.config):
                papers.append(paper)
        papers = [p for p in papers if in_window(p.published_at, since, until)]
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
