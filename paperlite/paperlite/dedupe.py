from __future__ import annotations

import re

from paperlite.identity import normalize_doi
from paperlite.models import Paper

LIST_FIELDS = ("authors", "categories", "issn", "concepts", "source_records")
SCALAR_FIELDS = (
    "abstract",
    "pdf_url",
    "doi",
    "published_at",
    "journal",
    "venue",
    "publisher",
    "pmid",
    "pmcid",
    "openalex_id",
)


def _paper_data(paper: Paper) -> dict:
    if hasattr(paper, "model_dump"):
        return paper.model_dump()
    return paper.dict()


def _present(value) -> bool:
    return value not in (None, "", [], {})


def _dedupe_list(values: list) -> list:
    out = []
    seen = set()
    for value in values:
        key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _title_fingerprint(title: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    return re.sub(r"\s+", " ", text)


def _paper_year(paper: Paper) -> str:
    if not paper.published_at:
        return ""
    return str(paper.published_at.year)


def title_year_key(paper: Paper) -> str:
    title = _title_fingerprint(paper.title)
    tokens = title.split()
    year = _paper_year(paper)
    if not year or len(tokens) < 4 or len(title) < 16:
        return ""
    return f"title-year:{year}:{title}"


def dedupe_key(paper: Paper) -> str:
    return (
        (f"doi:{normalize_doi(paper.doi)}" if normalize_doi(paper.doi) else "")
        or (f"pmid:{paper.pmid}" if paper.pmid else "")
        or (f"pmcid:{paper.pmcid}" if paper.pmcid else "")
        or (f"openalex:{paper.openalex_id}" if paper.openalex_id else "")
        or title_year_key(paper)
        or paper.id
    )


def merge_papers(primary: Paper, secondary: Paper) -> Paper:
    data = _paper_data(primary)
    other = _paper_data(secondary)

    for field in SCALAR_FIELDS:
        if not _present(data.get(field)) and _present(other.get(field)):
            data[field] = other[field]

    if secondary.citation_count is not None:
        if primary.citation_count is None:
            data["citation_count"] = secondary.citation_count
        else:
            data["citation_count"] = max(primary.citation_count, secondary.citation_count)

    for field in LIST_FIELDS:
        data[field] = _dedupe_list(list(data.get(field) or []) + list(other.get(field) or []))

    data["raw"] = {
        **(other.get("raw") or {}),
        **(data.get("raw") or {}),
    }
    return Paper(**data)


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    seen: dict[str, int] = {}
    out: list[Paper] = []

    for paper in papers:
        key = dedupe_key(paper)
        if key in seen:
            out[seen[key]] = merge_papers(out[seen[key]], paper)
            continue
        seen[key] = len(out)
        out.append(paper)

    return out
