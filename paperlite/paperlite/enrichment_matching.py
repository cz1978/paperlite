from __future__ import annotations

import re
from difflib import SequenceMatcher

from paperlite.identity import normalize_doi
from paperlite.models import Paper


def _compact_title(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def title_similarity(left: str | None, right: str | None) -> float:
    a = _compact_title(left)
    b = _compact_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _year(paper: Paper) -> int | None:
    return paper.published_at.year if paper.published_at else None


def _years_compatible(primary: Paper, candidate: Paper) -> bool:
    primary_year = _year(primary)
    candidate_year = _year(candidate)
    if primary_year is None or candidate_year is None:
        return True
    return abs(primary_year - candidate_year) <= 1


def confident_enrichment_match(primary: Paper, candidate: Paper) -> bool:
    primary_doi = normalize_doi(primary.doi)
    candidate_doi = normalize_doi(candidate.doi)
    if primary_doi and candidate_doi:
        return primary_doi == candidate_doi
    if primary.pmid and candidate.pmid:
        return primary.pmid == candidate.pmid
    if primary.pmcid and candidate.pmcid:
        return primary.pmcid == candidate.pmcid
    if primary.openalex_id and candidate.openalex_id:
        return primary.openalex_id == candidate.openalex_id

    similarity = title_similarity(primary.title, candidate.title)
    if not _years_compatible(primary, candidate):
        return False
    if primary_doi and not candidate_doi:
        return similarity >= 0.92
    if candidate_doi and not primary_doi:
        return similarity >= 0.86
    return similarity >= 0.9
