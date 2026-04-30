from __future__ import annotations

import hashlib
import re
from typing import Optional

_ARXIV_LINK_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.IGNORECASE)
_ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.([^/?#\s]+)", re.IGNORECASE)
_NATURE_ARTICLE_RE = re.compile(r"nature\.com/articles/([^/?#\s]+)", re.IGNORECASE)
_AMS_ARTICLE_RE = re.compile(r"journals\.ametsoc\.org/view/journals/(?:[^/]+/)+([A-Z0-9-]+-[A-Z]-\d{2}-\d{4}\.\d+)\.xml", re.IGNORECASE)
_DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s?#<>\"]+)", re.IGNORECASE)


def normalize_source(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "bio-rxiv": "biorxiv",
        "bio rxiv": "biorxiv",
        "med-rxiv": "medrxiv",
        "med rxiv": "medrxiv",
        "new england journal of medicine": "nejm",
    }
    return aliases.get(raw, raw)


def normalize_doi(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip()
    raw = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", raw, flags=re.IGNORECASE)
    raw = raw.rstrip(".,;)")
    if raw.lower().startswith("10.1101/"):
        raw = re.sub(r"v\d+$", "", raw, flags=re.IGNORECASE)
    raw = raw.lower()
    return raw or None


def doi_from_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = _DOI_RE.search(value)
    if not match:
        return None
    return normalize_doi(match.group(1))


def nature_doi_from_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = _NATURE_ARTICLE_RE.search(value)
    if not match:
        return None
    article_id = match.group(1).rstrip(".,;)")
    if not article_id:
        return None
    return normalize_doi(f"10.1038/{article_id}")


def ams_doi_from_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = _AMS_ARTICLE_RE.search(value)
    if not match:
        return None
    suffix = match.group(1).rstrip(".,;)")
    if not suffix:
        return None
    return normalize_doi(f"10.1175/{suffix}")


def normalize_arxiv_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip()
    raw = raw.removeprefix("arXiv:").removeprefix("arxiv:")
    raw = re.sub(r"\.pdf$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"v\d+$", "", raw, flags=re.IGNORECASE)
    return raw or None


def arxiv_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    match = _ARXIV_LINK_RE.search(url)
    if not match:
        return None
    return normalize_arxiv_id(match.group(1))


def arxiv_doi_from_url(url: Optional[str]) -> Optional[str]:
    arxiv_id = arxiv_id_from_url(url)
    if not arxiv_id:
        return None
    return normalize_doi(f"10.48550/arXiv.{arxiv_id}")


def arxiv_id_from_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    match = _ARXIV_DOI_RE.search(doi)
    if not match:
        return None
    return normalize_arxiv_id(match.group(1))


def url_hash(url: Optional[str]) -> str:
    clean = (url or "").strip()
    return hashlib.sha1(clean.encode("utf-8")).hexdigest()[:16]


def paper_id(source: str, url: Optional[str], doi: Optional[str] = None) -> str:
    source_norm = normalize_source(source)
    doi_norm = normalize_doi(doi) or doi_from_text(url)

    if source_norm == "arxiv":
        arxiv_id = arxiv_id_from_doi(doi_norm) or arxiv_id_from_url(url)
        if arxiv_id:
            return f"arxiv:{arxiv_id}"

    if source_norm in {"biorxiv", "medrxiv", "chemrxiv"} and doi_norm:
        return f"{source_norm}:{doi_norm}"

    if doi_norm:
        return f"doi:{doi_norm}"

    return f"url:{url_hash(url)}"


def pdf_url_for_arxiv(url: Optional[str]) -> Optional[str]:
    arxiv_id = arxiv_id_from_url(url)
    if not arxiv_id:
        return None
    return f"https://arxiv.org/pdf/{arxiv_id}"
