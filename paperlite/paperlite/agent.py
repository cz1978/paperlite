from __future__ import annotations

import math
from typing import Any

from paperlite.daily_export import daily_cache_export_papers, daily_date_range
from paperlite.llm import complete_chat, create_embeddings, embedding_status
from paperlite.models import Paper
from paperlite.storage import (
    daily_cache_papers_for_rag,
    get_paper_embedding,
    paper_embedding_hash,
    paper_embedding_text,
    upsert_paper_embedding,
)


def parse_paper(value: dict[str, Any] | Paper) -> Paper:
    if isinstance(value, Paper):
        return value
    if hasattr(Paper, "model_validate"):
        return Paper.model_validate(value)
    return Paper.parse_obj(value)


def paper_prompt(paper: Paper) -> str:
    authors = ", ".join(paper.authors[:10])
    categories = ", ".join(paper.categories or paper.concepts)
    fields = [
        f"Title: {paper.title}",
        f"Source: {paper.source}",
        f"Venue: {paper.venue or paper.journal or ''}",
        f"Date: {paper.published_at.isoformat() if paper.published_at else ''}",
        f"Authors: {authors}",
        f"DOI: {paper.doi or ''}",
        f"URL: {paper.url}",
        f"Categories: {categories}",
        f"Abstract: {paper.abstract}",
    ]
    return "\n".join(fields)


def _result(papers: list[Paper], llm_result: dict[str, Any], warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "papers": [paper.to_dict() for paper in papers],
        "answer": llm_result.get("answer", ""),
        "model": llm_result.get("model"),
        "configured": bool(llm_result.get("configured")),
        "warnings": list(warnings or []) + list(llm_result.get("warnings") or []),
    }


def paper_explain(
    paper: dict[str, Any] | Paper,
    question: str | None = None,
    style: str = "plain",
) -> dict[str, Any]:
    parsed = parse_paper(paper)
    messages = [
        {
            "role": "system",
            "content": "You explain research papers in English using only the supplied metadata. Do not translate.",
        },
        {
            "role": "user",
            "content": (
                f"Explain this paper in a {style} style. "
                f"Question: {question or 'What is this paper about and why might it matter?'}\n\n"
                f"{paper_prompt(parsed)}"
            ),
        },
    ]
    return _result([parsed], complete_chat(messages))


def _date_scope(
    *,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, str]:
    days = daily_date_range(date_value=date_value, date_from=date_from, date_to=date_to)
    return days[0], days[-1]


def _bounded_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clean_query(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _papers_for_rag_scope(
    *,
    start: str,
    end: str,
    discipline: str | None,
    source: str | list[str] | None,
    limit_per_source: int,
    q: str | None,
    cache_path: str | None,
) -> list[Paper]:
    clean_q = _clean_query(q)
    if clean_q:
        return daily_cache_export_papers(
            date_from=start,
            date_to=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            limit_per_source=limit_per_source,
            path=cache_path,
        )
    return daily_cache_papers_for_rag(
        date_from=start,
        date_to=end,
        discipline_key=discipline,
        source_keys=source,
        limit_per_source=limit_per_source,
        path=cache_path,
    )


def _search_cached_embeddings(
    *,
    papers: list[Paper],
    query_embedding: list[float],
    embedding_model: str,
    top_k: int,
    cache_path: str | None,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    indexed = 0
    stale = 0
    for paper in papers:
        existing = get_paper_embedding(paper.id, path=cache_path)
        if not existing or existing.get("embedding_model") != embedding_model:
            continue
        indexed += 1
        if existing.get("content_hash") != paper_embedding_hash(paper):
            stale += 1
            continue
        scored.append(
            {
                "paper": paper,
                "score": _cosine_similarity(query_embedding, list(existing.get("embedding") or [])),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {
        "candidates": len(papers),
        "indexed": indexed,
        "stale": stale,
        "matches": scored[: max(1, int(top_k))],
    }


def _citation_paper(paper: Paper) -> dict[str, Any]:
    payload = paper.to_dict()
    return {
        key: payload.get(key)
        for key in [
            "id",
            "source",
            "source_type",
            "title",
            "abstract",
            "authors",
            "url",
            "doi",
            "published_at",
            "categories",
            "journal",
            "venue",
            "publisher",
            "pmid",
            "pmcid",
            "openalex_id",
            "citation_count",
            "concepts",
        ]
        if payload.get(key) not in (None, "", [], {})
    }


def _clip(value: str, limit: int = 1600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _evidence_block(citations: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for citation in citations:
        paper = citation["paper"]
        authors = ", ".join(paper.get("authors") or [])
        categories = ", ".join(paper.get("categories") or paper.get("concepts") or [])
        fields = [
            f"[{citation['index']}]",
            f"Title: {paper.get('title') or ''}",
            f"Source: {paper.get('source') or ''}",
            f"Venue: {paper.get('venue') or paper.get('journal') or ''}",
            f"Date: {paper.get('published_at') or ''}",
            f"Authors: {authors}",
            f"DOI: {paper.get('doi') or ''}",
            f"URL: {paper.get('url') or ''}",
            f"Categories: {categories}",
            f"Abstract: {_clip(str(paper.get('abstract') or ''))}",
        ]
        blocks.append("\n".join(fields))
    return "\n\n".join(blocks)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _embedding_current(
    paper: Paper,
    *,
    embedding_model: str | None,
    cache_path: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    content_hash = paper_embedding_hash(paper)
    existing = get_paper_embedding(paper.id, path=cache_path)
    if (
        existing
        and existing.get("content_hash") == content_hash
        and existing.get("embedding_model") == embedding_model
        and existing.get("embedding")
    ):
        return existing, content_hash
    return None, content_hash


def _base_related_response(
    *,
    configured: bool,
    paper_id: str,
    embedding_model: str | None,
    start: str,
    end: str,
    discipline: str | None,
    source: str | list[str] | None,
    q: str | None,
    top_k: int,
    limit_per_source: int,
    candidates: int = 0,
    indexed: int = 0,
    refreshed: int = 0,
    stale: int = 0,
    matches: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "paper_id": paper_id,
        "embedding_model": embedding_model,
        "related": [],
        "retrieval": {
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": q,
            "top_k": top_k,
            "limit_per_source": limit_per_source,
            "candidates": candidates,
            "indexed": indexed,
            "refreshed": refreshed,
            "stale": stale,
            "matches": matches,
        },
        "warnings": list(warnings or []),
    }


def paper_related(
    *,
    paper_id: str,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 5,
    limit_per_source: int = 500,
    cache_path: str | None = None,
) -> dict[str, Any]:
    clean_paper_id = str(paper_id or "").strip()
    if not clean_paper_id:
        raise ValueError("paper_id is required")
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_top_k = _bounded_int(top_k, default=5, minimum=1, maximum=20)
    selected_limit = _bounded_int(limit_per_source, default=500, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    settings = embedding_status()
    settings_model = str(settings.get("model") or "")
    target = next((paper for paper in papers if paper.id == clean_paper_id), None)
    if target is None:
        return _base_related_response(
            configured=bool(settings.get("configured")),
            paper_id=clean_paper_id,
            embedding_model=settings.get("model"),
            start=start,
            end=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            top_k=selected_top_k,
            limit_per_source=selected_limit,
            candidates=len(papers),
            warnings=["related_target_not_in_cache_scope"],
        )
    if not settings.get("configured"):
        return _base_related_response(
            configured=False,
            paper_id=clean_paper_id,
            embedding_model=settings.get("model"),
            start=start,
            end=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            top_k=selected_top_k,
            limit_per_source=selected_limit,
            candidates=len(papers),
            warnings=["embedding_not_configured"],
        )

    pending: list[tuple[Paper, str, str]] = []
    skipped = 0
    stale = 0
    for paper in papers:
        existing, content_hash = _embedding_current(paper, embedding_model=settings_model, cache_path=cache_path)
        if existing is not None:
            skipped += 1
            continue
        if get_paper_embedding(paper.id, path=cache_path):
            stale += 1
        pending.append((paper, content_hash, paper_embedding_text(paper)))

    embedding_model = settings_model
    embedding_warnings: list[str] = []
    refreshed = 0
    if pending:
        embedding_result = create_embeddings([item[2] for item in pending])
        if not embedding_result.get("configured"):
            return _base_related_response(
                configured=False,
                paper_id=clean_paper_id,
                embedding_model=embedding_result.get("model"),
                start=start,
                end=end,
                discipline=discipline,
                source=source,
                q=clean_q,
                top_k=selected_top_k,
                limit_per_source=selected_limit,
                candidates=len(papers),
                indexed=skipped,
                stale=stale,
                warnings=list(embedding_result.get("warnings") or []),
            )
        embedding_model = str(embedding_result.get("model") or embedding_model)
        embedding_warnings = list(embedding_result.get("warnings") or [])
        for (paper, content_hash, _text), embedding in zip(pending, embedding_result.get("embeddings") or []):
            upsert_paper_embedding(
                paper_id=paper.id,
                content_hash=content_hash,
                embedding_model=embedding_model,
                embedding=embedding,
                path=cache_path,
            )
            refreshed += 1

    vectors: dict[str, list[float]] = {}
    for paper in papers:
        existing, _content_hash = _embedding_current(paper, embedding_model=embedding_model, cache_path=cache_path)
        if existing is not None:
            vectors[paper.id] = list(existing.get("embedding") or [])
    target_vector = vectors.get(clean_paper_id)
    if not target_vector:
        return _base_related_response(
            configured=True,
            paper_id=clean_paper_id,
            embedding_model=embedding_model,
            start=start,
            end=end,
            discipline=discipline,
            source=source,
            q=clean_q,
            top_k=selected_top_k,
            limit_per_source=selected_limit,
            candidates=len(papers),
            indexed=len(vectors),
            refreshed=refreshed,
            stale=stale,
            warnings=embedding_warnings + ["related_target_embedding_missing"],
        )

    scored: list[dict[str, Any]] = []
    for paper in papers:
        if paper.id == clean_paper_id:
            continue
        vector = vectors.get(paper.id)
        if not vector:
            continue
        scored.append(
            {
                "score": _cosine_similarity(target_vector, vector),
                "paper": _citation_paper(paper),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    related = [
        {
            "index": index,
            "score": item["score"],
            "paper": item["paper"],
        }
        for index, item in enumerate(scored[:selected_top_k], start=1)
    ]
    warnings = embedding_warnings[:]
    if len(papers) <= 1:
        warnings.append("related_no_candidate_papers")
    elif not related:
        warnings.append("related_no_matches")
    return {
        "configured": True,
        "paper_id": clean_paper_id,
        "embedding_model": embedding_model,
        "related": related,
        "retrieval": {
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": clean_q,
            "top_k": selected_top_k,
            "limit_per_source": selected_limit,
            "candidates": len(papers),
            "indexed": len(vectors),
            "refreshed": refreshed,
            "stale": stale,
            "matches": len(related),
        },
        "warnings": warnings,
    }


def paper_rag_index(
    *,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    limit_per_source: int = 100,
    cache_path: str | None = None,
) -> dict[str, Any]:
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_limit = _bounded_int(limit_per_source, default=100, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    settings = embedding_status()
    pending: list[tuple[Paper, str, str]] = []
    skipped = 0
    for paper in papers:
        content_hash = paper_embedding_hash(paper)
        existing = get_paper_embedding(paper.id, path=cache_path)
        if (
            existing
            and existing.get("content_hash") == content_hash
            and existing.get("embedding_model") == settings.get("model")
        ):
            skipped += 1
            continue
        pending.append((paper, content_hash, paper_embedding_text(paper)))

    if not pending:
        return {
            "configured": bool(settings.get("configured")),
            "embedding_model": settings.get("model"),
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": clean_q,
            "limit_per_source": selected_limit,
            "candidates": len(papers),
            "indexed": 0,
            "skipped": skipped,
            "warnings": [] if settings.get("configured") else ["embedding_not_configured"],
        }

    embedding_result = create_embeddings([item[2] for item in pending])
    if not embedding_result.get("configured"):
        return {
            "configured": False,
            "embedding_model": embedding_result.get("model"),
            "date_from": start,
            "date_to": end,
            "discipline": discipline,
            "source": source,
            "q": clean_q,
            "limit_per_source": selected_limit,
            "candidates": len(papers),
            "indexed": 0,
            "skipped": skipped,
            "warnings": list(embedding_result.get("warnings") or []),
        }

    embedding_model = str(embedding_result.get("model") or "")
    indexed = 0
    for (paper, content_hash, _text), embedding in zip(pending, embedding_result.get("embeddings") or []):
        upsert_paper_embedding(
            paper_id=paper.id,
            content_hash=content_hash,
            embedding_model=embedding_model,
            embedding=embedding,
            path=cache_path,
        )
        indexed += 1
    return {
        "configured": True,
        "embedding_model": embedding_model,
        "date_from": start,
        "date_to": end,
        "discipline": discipline,
        "source": source,
        "q": clean_q,
        "limit_per_source": selected_limit,
        "candidates": len(papers),
        "indexed": indexed,
        "skipped": skipped,
        "warnings": list(embedding_result.get("warnings") or []),
    }


def paper_ask(
    *,
    question: str,
    date_value: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    discipline: str | None = None,
    source: str | list[str] | None = None,
    q: str | None = None,
    top_k: int = 8,
    limit_per_source: int = 100,
    cache_path: str | None = None,
) -> dict[str, Any]:
    clean_question = str(question or "").strip()
    if not clean_question:
        raise ValueError("question is required")
    start, end = _date_scope(date_value=date_value, date_from=date_from, date_to=date_to)
    selected_top_k = _bounded_int(top_k, default=8, minimum=1, maximum=20)
    selected_limit = _bounded_int(limit_per_source, default=100, minimum=1, maximum=500)
    clean_q = _clean_query(q)
    embedding_result = create_embeddings([clean_question])
    base_retrieval = {
        "date_from": start,
        "date_to": end,
        "discipline": discipline,
        "source": source,
        "q": clean_q,
        "top_k": selected_top_k,
        "limit_per_source": selected_limit,
        "candidates": 0,
        "indexed": 0,
        "stale": 0,
        "matches": 0,
    }
    if not embedding_result.get("configured"):
        return {
            "configured": False,
            "answer": "",
            "model": None,
            "embedding_model": embedding_result.get("model"),
            "citations": [],
            "retrieval": base_retrieval,
            "warnings": list(embedding_result.get("warnings") or []),
        }

    query_embedding = (embedding_result.get("embeddings") or [[]])[0]
    embedding_model = str(embedding_result.get("model") or "")
    papers = _papers_for_rag_scope(
        start=start,
        end=end,
        discipline=discipline,
        source=source,
        limit_per_source=selected_limit,
        q=clean_q,
        cache_path=cache_path,
    )
    search = _search_cached_embeddings(
        papers=papers,
        query_embedding=query_embedding,
        embedding_model=embedding_model,
        top_k=selected_top_k,
        cache_path=cache_path,
    )
    citations = [
        {
            "index": index,
            "score": item["score"],
            "paper": _citation_paper(item["paper"]),
        }
        for index, item in enumerate(search.get("matches") or [], start=1)
    ]
    retrieval = {
        **base_retrieval,
        "candidates": search.get("candidates", 0),
        "indexed": search.get("indexed", 0),
        "stale": search.get("stale", 0),
        "matches": len(citations),
    }
    warnings = list(embedding_result.get("warnings") or [])
    if search.get("stale"):
        warnings.append("rag_index_stale_entries_skipped")
    if not citations:
        warnings.append("rag_index_empty_or_no_matches")
        return {
            "configured": True,
            "answer": "",
            "model": None,
            "embedding_model": embedding_model,
            "citations": [],
            "retrieval": retrieval,
            "warnings": warnings,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You answer research questions using only the supplied PaperLite paper metadata. "
                "Do not use outside knowledge. Do not infer from PDFs or full text. "
                "If the supplied metadata is insufficient, say so. "
                "Cite concrete claims with bracketed citation numbers like [1]."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {clean_question}\n\n"
                "PaperLite metadata evidence:\n\n"
                f"{_evidence_block(citations)}"
            ),
        },
    ]
    llm_result = complete_chat(messages, temperature=0.1, max_tokens=1600)
    return {
        "configured": bool(llm_result.get("configured")),
        "answer": llm_result.get("answer", ""),
        "model": llm_result.get("model"),
        "embedding_model": embedding_model,
        "citations": citations,
        "retrieval": retrieval,
        "warnings": warnings + list(llm_result.get("warnings") or []),
    }
