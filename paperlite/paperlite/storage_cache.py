from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from paperlite.dedupe import dedupe_key, merge_papers
from paperlite.metadata_cleaning import sanitize_paper_payload
from paperlite.models import Paper
from paperlite.storage_schema import _json_dumps, _json_loads, _now, connect, split_source_keys

@dataclass(frozen=True)
class CachedGroup:
    source: str
    items: list[dict[str, Any]]


def _paper_from_payload(payload: dict[str, Any]) -> Paper | None:
    try:
        return Paper.model_validate(payload) if hasattr(Paper, "model_validate") else Paper.parse_obj(payload)
    except Exception:
        return None


def _daily_source_record(source: str, entry_date: str, paper_id: str) -> dict[str, str]:
    return {"source": source, "entry_date": entry_date, "paper_id": paper_id}


def _dedupe_daily_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        key = (
            str(record.get("source") or ""),
            str(record.get("entry_date") or ""),
            str(record.get("paper_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(record))
    return out


def _merged_cache_payload(
    paper: Paper,
    *,
    canonical_key: str,
    cache_date: str,
    daily_records: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = paper.to_dict()
    records = _dedupe_daily_records(daily_records)
    sources = []
    for record in records:
        source = str(record.get("source") or "")
        if source and source not in sources:
            sources.append(source)
    payload["_cache_date"] = cache_date
    payload["_canonical_key"] = canonical_key
    payload["_daily_sources"] = sources
    payload["_daily_source_records"] = records
    return payload


def paper_embedding_text(paper: Paper) -> str:
    categories = ", ".join(paper.categories or [])
    concepts = ", ".join(paper.concepts or [])
    authors = ", ".join(paper.authors[:20])
    fields = [
        ("Title", paper.title),
        ("Abstract", paper.abstract),
        ("Source", paper.source),
        ("Source type", paper.source_type),
        ("Venue", paper.venue or paper.journal or ""),
        ("Publisher", paper.publisher or ""),
        ("Date", paper.published_at.isoformat() if paper.published_at else ""),
        ("Authors", authors),
        ("DOI", paper.doi or ""),
        ("URL", paper.url),
        ("Categories", categories),
        ("Concepts", concepts),
    ]
    return "\n".join(f"{label}: {value}" for label, value in fields if str(value or "").strip())


def paper_embedding_hash(paper: Paper) -> str:
    return hashlib.sha256(paper_embedding_text(paper).encode("utf-8")).hexdigest()


def daily_cache_papers_for_rag(
    *,
    date_from: str,
    date_to: str,
    discipline_key: str | None = None,
    source_keys: Iterable[str] | None = None,
    limit_per_source: int = 100,
    path: str | Path | None = None,
) -> list[Paper]:
    payload = query_daily_cache(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline_key,
        source_keys=source_keys,
        limit_per_source=limit_per_source,
        path=path,
    )
    papers: list[Paper] = []
    for group in payload.get("groups") or []:
        for item in group.get("items") or []:
            paper = _paper_from_payload(item) if isinstance(item, dict) else None
            if paper is not None:
                papers.append(paper)
    return papers


def _embedding_from_row(row: Any) -> dict[str, Any] | None:
    raw_embedding = _json_loads(row["embedding_json"], None)
    if not isinstance(raw_embedding, list):
        return None
    try:
        embedding = [float(value) for value in raw_embedding]
    except (TypeError, ValueError):
        return None
    return {
        "paper_id": row["paper_id"],
        "content_hash": row["content_hash"],
        "embedding_model": row["embedding_model"],
        "dimensions": int(row["dimensions"] or 0),
        "embedding": embedding,
        "updated_at": row["updated_at"],
    }


def get_paper_embedding(
    paper_id: str,
    *,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM paper_embeddings WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
    return _embedding_from_row(row) if row else None


def upsert_paper_embedding(
    *,
    paper_id: str,
    content_hash: str,
    embedding_model: str,
    embedding: list[float],
    path: str | Path | None = None,
) -> dict[str, Any]:
    clean_embedding = [float(value) for value in embedding]
    now = _now()
    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO paper_embeddings (
              paper_id, content_hash, embedding_model, dimensions, embedding_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
              content_hash = excluded.content_hash,
              embedding_model = excluded.embedding_model,
              dimensions = excluded.dimensions,
              embedding_json = excluded.embedding_json,
              updated_at = excluded.updated_at
            """,
            (
                paper_id,
                content_hash,
                embedding_model,
                len(clean_embedding),
                _json_dumps(clean_embedding),
                now,
            ),
        )
    return {
        "paper_id": paper_id,
        "content_hash": content_hash,
        "embedding_model": embedding_model,
        "dimensions": len(clean_embedding),
        "updated_at": now,
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _embedding_rows_for_paper_ids(
    paper_ids: list[str],
    *,
    embedding_model: str,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    rows: list[Any] = []
    with connect(path) as connection:
        for start in range(0, len(paper_ids), 800):
            chunk = paper_ids[start : start + 800]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                connection.execute(
                    f"""
                    SELECT * FROM paper_embeddings
                    WHERE embedding_model = ?
                      AND paper_id IN ({placeholders})
                    """,
                    [embedding_model, *chunk],
                ).fetchall()
            )
    out: list[dict[str, Any]] = []
    for row in rows:
        parsed = _embedding_from_row(row)
        if parsed is not None:
            out.append(parsed)
    return out


def search_paper_embeddings(
    *,
    query_embedding: list[float],
    embedding_model: str,
    date_from: str,
    date_to: str,
    discipline_key: str | None = None,
    source_keys: Iterable[str] | None = None,
    top_k: int = 8,
    limit_per_source: int = 100,
    path: str | Path | None = None,
) -> dict[str, Any]:
    papers = daily_cache_papers_for_rag(
        date_from=date_from,
        date_to=date_to,
        discipline_key=discipline_key,
        source_keys=source_keys,
        limit_per_source=limit_per_source,
        path=path,
    )
    by_id = {paper.id: paper for paper in papers if paper.id}
    rows = _embedding_rows_for_paper_ids(
        list(by_id),
        embedding_model=embedding_model,
        path=path,
    )
    scored: list[dict[str, Any]] = []
    stale_count = 0
    for row in rows:
        paper = by_id.get(str(row["paper_id"]))
        if paper is None:
            continue
        current_hash = paper_embedding_hash(paper)
        if row["content_hash"] != current_hash:
            stale_count += 1
            continue
        score = _cosine_similarity(query_embedding, row["embedding"])
        scored.append(
            {
                "paper": paper,
                "score": score,
                "content_hash": current_hash,
                "embedding_model": row["embedding_model"],
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {
        "candidates": len(papers),
        "indexed": len(rows),
        "stale": stale_count,
        "matches": scored[: max(1, int(top_k))],
    }


def query_daily_cache(
    *,
    date_from: str,
    date_to: str,
    discipline_key: str | None = None,
    source_keys: Iterable[str] | None = None,
    limit_per_source: int = 50,
    path: str | Path | None = None,
) -> dict[str, Any]:
    selected_sources = split_source_keys(source_keys)
    conditions = ["daily_entries.entry_date >= ?", "daily_entries.entry_date <= ?"]
    params: list[Any] = [date_from, date_to]
    if discipline_key:
        conditions.append("daily_entries.discipline_key = ?")
        params.append(discipline_key)
    if selected_sources:
        placeholders = ",".join("?" for _ in selected_sources)
        conditions.append(f"daily_entries.source_key IN ({placeholders})")
        params.extend(selected_sources)
    where_clause = " AND ".join(conditions)
    with connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT daily_entries.source_key, daily_entries.entry_date, paper_items.payload_json,
                   paper_items.published_at
            FROM daily_entries
            JOIN paper_items ON paper_items.paper_id = daily_entries.paper_id
            WHERE {where_clause}
            ORDER BY daily_entries.source_key ASC, paper_items.published_at DESC, paper_items.paper_id ASC
            """,
            params,
        ).fetchall()

    order = {source: index for index, source in enumerate(selected_sources)}
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[str]] = {}
    canonical_index: dict[str, tuple[str, int]] = {}
    canonical_papers: dict[str, Paper] = {}
    canonical_records: dict[str, list[dict[str, Any]]] = {}
    canonical_cache_dates: dict[str, str] = {}
    for row in rows:
        source = row["source_key"]
        items = grouped.setdefault(source, [])
        source_seen = seen.setdefault(source, set())
        payload = _json_loads(row["payload_json"], None)
        if not isinstance(payload, dict):
            continue
        payload = sanitize_paper_payload(payload)
        paper = _paper_from_payload(payload)
        if paper is None:
            continue
        paper_id = str(paper.id or "")
        canonical_key = dedupe_key(paper)
        if not paper_id or canonical_key in source_seen:
            continue
        source_seen.add(canonical_key)
        entry_date = str(row["entry_date"] or "")
        record = _daily_source_record(source, entry_date, paper_id)
        if canonical_key in canonical_index:
            target_source, target_index = canonical_index[canonical_key]
            merged = merge_papers(canonical_papers[canonical_key], paper)
            canonical_papers[canonical_key] = merged
            canonical_records[canonical_key].append(record)
            canonical_cache_dates[canonical_key] = max(canonical_cache_dates.get(canonical_key, entry_date), entry_date)
            grouped[target_source][target_index] = _merged_cache_payload(
                merged,
                canonical_key=canonical_key,
                cache_date=canonical_cache_dates[canonical_key],
                daily_records=canonical_records[canonical_key],
            )
            continue
        if len(items) >= limit_per_source:
            continue
        canonical_index[canonical_key] = (source, len(items))
        canonical_papers[canonical_key] = paper
        canonical_records[canonical_key] = [record]
        canonical_cache_dates[canonical_key] = entry_date
        items.append(
            _merged_cache_payload(
                paper,
                canonical_key=canonical_key,
                cache_date=entry_date,
                daily_records=[record],
            )
        )

    def source_sort_key(item: tuple[str, list[dict[str, Any]]]) -> tuple[int, str]:
        source = item[0]
        return (order.get(source, len(order)), source)

    groups = [
        {
            "source": source,
            "display_name": source,
            "count": len(items),
            "warnings": [],
            "endpoints": [],
            "items": items,
        }
        for source, items in sorted(grouped.items(), key=source_sort_key)
        if items
    ]
    return {
        "date": date_from if date_from == date_to else date_to,
        "date_from": date_from,
        "date_to": date_to,
        "timezone": "Asia/Shanghai",
        "profile": None,
        "profile_info": None,
        "sources": [group["source"] for group in groups],
        "endpoints": [],
        "selection_mode": "cache",
        "limit_per_source": limit_per_source,
        "warnings": [],
        "groups": groups,
    }
