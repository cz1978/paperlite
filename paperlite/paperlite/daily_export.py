from __future__ import annotations

from pathlib import Path
from typing import Iterable

from paperlite.daily_dates import today_local
from paperlite.daily_crawl import iter_days
from paperlite.dedupe import dedupe_papers
from paperlite.models import Paper
from paperlite.registry import list_sources
from paperlite.storage import query_daily_cache


def daily_date_range(
    *,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[str]:
    start = date_from or date_value or today_local().isoformat()
    end = date_to or start
    return iter_days(start, end)


def paper_matches_export_query(
    paper: Paper,
    query: str | None,
    *,
    daily_source_display: str = "",
) -> bool:
    q = str(query or "").strip().lower()
    if not q:
        return True
    haystack = " ".join(
        str(value)
        for value in [
            paper.title,
            paper.abstract,
            paper.source,
            daily_source_display,
            paper.venue,
            paper.journal,
            paper.publisher,
            paper.doi,
            *paper.categories,
            *paper.concepts,
        ]
        if value
    ).lower()
    return q in haystack


def daily_cache_payload(
    *,
    date_from: str,
    date_to: str,
    discipline: str | None = None,
    source: str | Iterable[str] | None = None,
    limit_per_source: int = 50,
) -> dict:
    result = query_daily_cache(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline,
        source_keys=source,
        limit_per_source=limit_per_source,
    )
    display_names = {
        str(item.get("name") or ""): str(item.get("display_name") or item.get("name") or "")
        for item in list_sources()
    }
    for group in result["groups"]:
        group["display_name"] = display_names.get(str(group["source"]), str(group["source"]))
    return result


def daily_cache_export_papers(
    *,
    date_from: str,
    date_to: str,
    discipline: str | None = None,
    source: str | Iterable[str] | None = None,
    q: str | None = None,
    limit_per_source: int = 500,
    path: str | Path | None = None,
) -> list[Paper]:
    payload = query_daily_cache(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline,
        source_keys=source,
        limit_per_source=limit_per_source,
        path=path,
    )
    papers: list[Paper] = []
    for group in payload.get("groups") or []:
        display = str(group.get("display_name") or group.get("source") or "")
        for item in group.get("items") or []:
            try:
                paper = Paper.model_validate(item) if hasattr(Paper, "model_validate") else Paper.parse_obj(item)
            except Exception:
                continue
            source_display = " ".join([display, *[str(value) for value in item.get("_daily_sources") or []]])
            if paper_matches_export_query(paper, q, daily_source_display=source_display):
                papers.append(paper)
    return sorted(
        dedupe_papers(papers),
        key=lambda item: item.published_at.isoformat() if item.published_at else "",
        reverse=True,
    )


def export_media_type(fmt: str) -> tuple[str, str]:
    if fmt == "ris":
        return "ris", "application/x-research-info-systems"
    if fmt in {"bib", "bibtex"}:
        return "bib", "application/x-bibtex"
    if fmt in {"md", "markdown"}:
        return "md", "text/markdown; charset=utf-8"
    if fmt == "json":
        return "json", "application/json"
    if fmt == "jsonl":
        return "jsonl", "application/x-ndjson"
    if fmt == "rss":
        return "rss", "application/rss+xml"
    raise ValueError("format must be ris, bibtex, markdown, json, jsonl, or rss")


def daily_export_filename(date_from: str, date_to: str, extension: str) -> str:
    start = str(date_from).replace("-", "")
    end = str(date_to).replace("-", "")
    return f"paperlite-daily-{start}-{end}.{extension}"
