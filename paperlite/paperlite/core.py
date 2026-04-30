from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from paperlite.config import runtime_config
from paperlite.dedupe import merge_papers
from paperlite.exporters import export_papers
from paperlite.models import Paper
from paperlite.registry import get_enricher

DEFAULT_ENRICHERS = ["openalex", "crossref"]


def _normalize_enrichers(enrichers: Optional[str | Iterable[str]]) -> list[str]:
    if enrichers is None:
        return []
    if isinstance(enrichers, str):
        raw = enrichers.strip()
        if raw.lower() in {"1", "true", "yes", "default"}:
            return DEFAULT_ENRICHERS
        return [s.strip() for s in raw.split(",") if s.strip()]
    return [str(s).strip() for s in enrichers if str(s).strip()]


def enrich_timeout_seconds() -> float:
    return runtime_config().enrich_timeout_seconds


def _copy_paper(paper: Paper, update: dict) -> Paper:
    return paper.model_copy(update=update) if hasattr(paper, "model_copy") else paper.copy(update=update)


def _with_enrich_warning(paper: Paper, warning: str) -> Paper:
    raw = dict(paper.raw or {})
    warnings = list(raw.get("enrich_warnings") or [])
    warnings.append(warning)
    raw["enrich_warnings"] = warnings
    return _copy_paper(paper, {"raw": raw})


def _enrich_one(connector, paper: Paper, timeout_seconds: float) -> Paper:
    try:
        return connector.enrich(paper, timeout_seconds=timeout_seconds)
    except TypeError as exc:
        if "timeout_seconds" not in str(exc):
            raise
        return connector.enrich(paper)


def _run_enrichers_concurrently(paper: Paper, names: list[str], timeout: float) -> Paper:
    if not names:
        return paper
    jobs = []
    warnings: dict[str, str] = {}
    for name in names:
        try:
            jobs.append((name, get_enricher(name)))
        except Exception as exc:
            warnings[name] = f"{name}: {type(exc).__name__}: {exc}"

    results: dict[str, Paper] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(len(jobs), 4))) as executor:
        futures = {
            executor.submit(_enrich_one, connector, paper, timeout): name
            for name, connector in jobs
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                warnings[name] = f"{name}: {type(exc).__name__}: {exc}"

    enriched = paper
    for name in names:
        if name in results:
            enriched = merge_papers(enriched, results[name])
    for name in names:
        if name in warnings:
            enriched = _with_enrich_warning(enriched, warnings[name])
    return enriched


def enrich_paper(
    paper: Paper,
    enrichers: Optional[str | Iterable[str]] = None,
    *,
    timeout_seconds: float | None = None,
) -> Paper:
    names = _normalize_enrichers(enrichers)
    if not names:
        return paper
    timeout = enrich_timeout_seconds() if timeout_seconds is None else timeout_seconds
    if "openalex" in names and not paper.doi and len(names) > 1:
        first_pass = [name for name in names if name != "openalex"]
        enriched = _run_enrichers_concurrently(paper, first_pass, timeout)
        return _run_enrichers_concurrently(enriched, ["openalex"], timeout)
    return _run_enrichers_concurrently(paper, names, timeout)


def enrich_papers(papers: list[Paper], enrichers: Optional[str | Iterable[str]] = None) -> list[Paper]:
    names = _normalize_enrichers(enrichers)
    if not names:
        return papers
    return [enrich_paper(paper, names) for paper in papers]


def export(papers: list[Paper], format: str = "json") -> str:
    return export_papers(papers, format=format)
