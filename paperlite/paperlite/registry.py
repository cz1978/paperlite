from __future__ import annotations

from functools import lru_cache
from typing import Any

from paperlite.connectors.arxiv import ArxivConnector
from paperlite.connectors.biorxiv import XrxivConnector
from paperlite.connectors.chemrxiv import ChemrxivConnector
from paperlite.connectors.crossref import CrossrefConnector
from paperlite.connectors.europepmc import EuropePMCConnector
from paperlite.connectors.journals import JournalFeedConnector
from paperlite.connectors.openalex import OpenAlexConnector
from paperlite.connectors.pubmed import PubMedConnector
from paperlite.catalog_quality import (
    discipline_record,
    duplicate_endpoint_sources,
    load_health_snapshot,
    profile_core_source_keys,
    source_quality_fields,
    source_kind_record,
)
from paperlite.identity import normalize_source
from paperlite.profiles import multidisciplinary_supplement_source_keys
from paperlite.sources import load_endpoint_configs, load_feed_source_configs, load_source_records


def build_registry():
    registry = {
        "arxiv": ArxivConnector(),
        "biorxiv": XrxivConnector("biorxiv"),
        "chemrxiv": ChemrxivConnector(),
        "crossref": CrossrefConnector(),
        "europepmc": EuropePMCConnector(),
        "medrxiv": XrxivConnector("medrxiv"),
        "openalex": OpenAlexConnector(),
        "pubmed": PubMedConnector(),
    }
    for config in load_feed_source_configs():
        if config.key in registry:
            continue
        registry[config.key] = JournalFeedConnector(config=config)
    return registry


@lru_cache(maxsize=1)
def connectors() -> dict[str, Any]:
    return build_registry()


@lru_cache(maxsize=1)
def enrichers() -> dict[str, Any]:
    return {
        name: connector
        for name, connector in connectors().items()
        if "enrich" in getattr(connector, "capabilities", ())
    }


def clear_registry_cache() -> None:
    connectors.cache_clear()
    enrichers.cache_clear()

DISPLAY_NAMES = {
    "arxiv": "arXiv",
    "biorxiv": "bioRxiv",
    "chemrxiv": "ChemRxiv",
    "crossref": "Crossref",
    "europepmc": "Europe PMC",
    "medrxiv": "medRxiv",
    "openalex": "OpenAlex",
    "pubmed": "PubMed",
}


def get_connector(name: str):
    key = normalize_source(name)
    try:
        return connectors()[key]
    except KeyError as exc:
        raise ValueError(f"unknown source: {name}") from exc


def get_enricher(name: str):
    key = normalize_source(name)
    try:
        return enrichers()[key]
    except KeyError as exc:
        raise ValueError(f"unknown enricher: {name}") from exc


def _display_name(name: str, connector: Any) -> str:
    journal = getattr(connector, "journal", None)
    return str(journal or DISPLAY_NAMES.get(name) or name)


def _group(connector: Any) -> str:
    kind = getattr(connector, "connector_kind", "")
    source_type = getattr(connector, "source_type", "")
    if source_type in {"preprint", "journal", "news", "publisher", "working_papers"}:
        return source_type
    if kind == "feed":
        return "journal"
    if source_type == "metadata":
        return "metadata"
    return "api"


def _search_mode(name: str, connector: Any) -> str:
    kind = getattr(connector, "connector_kind", "")
    if kind == "feed":
        return "recent_feed_filter"
    if name in {"crossref", "openalex"}:
        return "metadata_enrich"
    return "native_api"


def _limitations(name: str, connector: Any) -> list[str]:
    kind = getattr(connector, "connector_kind", "")
    source_type = getattr(connector, "source_type", "")
    if kind == "feed" or source_type == "journal":
        return ["只筛最近 RSS 条目，不是全站历史搜索", "全文和 PDF 均跳转源站"]
    if name in {"crossref", "openalex"}:
        return ["偏元数据补全和跨源发现", "全文阅读跳转 DOI、源站或开放 PDF 链接"]
    if name == "pubmed":
        return ["主要返回医学文献元数据", "多数全文需在 PubMed、PMC 或出版社站点阅读"]
    if name == "europepmc":
        return ["医学/生命科学覆盖强", "全文链接由 Europe PMC 或来源站点提供"]
    if source_type == "preprint":
        return ["预印本元数据和外链优先", "PDF/全文直接跳转预印本站点"]
    return ["外部来源能力可能受上游限制", "PaperLite 不代理全文或 PDF"]


def _supports_pdf_link(name: str, connector: Any) -> bool:
    source_type = getattr(connector, "source_type", "")
    return source_type == "preprint" or name in {"europepmc", "openalex"}


def _as_optional_bool(value: bool | str | None) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _source_matches_filters(
    item: dict[str, Any],
    *,
    discipline: str | None = None,
    area: str | None = None,
    kind: str | None = None,
    core: bool | str | None = None,
    health: str | None = None,
) -> bool:
    if discipline:
        wanted = discipline_record(discipline)
        discipline_keys = item.get("discipline_keys") or []
        discipline_names = item.get("canonical_disciplines") or []
        if wanted["key"] not in discipline_keys and wanted["name"] not in discipline_names:
            return False
    if area:
        wanted_area = str(area).strip().lower()
        area_keys = item.get("area_keys") or []
        if wanted_area not in area_keys and wanted_area != item.get("primary_area_key"):
            return False
    if kind and item.get("source_kind_key", item.get("catalog_kind")) != kind:
        return False
    core_value = _as_optional_bool(core)
    if core_value is not None and bool(item.get("core")) is not core_value:
        return False
    if health and item.get("health_status") != health:
        return False
    return True


def list_sources(
    *,
    discipline: str | None = None,
    area: str | None = None,
    kind: str | None = None,
    core: bool | str | None = None,
    health: str | None = None,
) -> list[dict[str, Any]]:
    records = {record.key: record for record in load_source_records()}
    registry = connectors()
    endpoints_by_source: dict[str, list[Any]] = {}
    endpoints = load_endpoint_configs()
    for endpoint in endpoints:
        endpoints_by_source.setdefault(endpoint.source_key, []).append(endpoint)
    duplicate_of = duplicate_endpoint_sources(endpoints)
    core_sources = profile_core_source_keys()
    supplement_sources = multidisciplinary_supplement_source_keys()
    health_snapshot = load_health_snapshot()
    sources = []
    for name in sorted(set(records) | set(registry)):
        connector = registry.get(name)
        record = records.get(name)
        endpoints = sorted(endpoints_by_source.get(name, []), key=lambda item: (item.priority, item.key))
        primary_endpoint = endpoints[0] if endpoints else None
        capabilities = tuple(getattr(connector, "capabilities", ())) if connector else ()
        if connector:
            item = connector.describe()
        else:
            source_type = record.source_kind if record else "source"
            item = {
                "name": name,
                "source_type": source_type,
                "connector_kind": primary_endpoint.mode if primary_endpoint else "manual",
                "capabilities": [],
            }
        source_type = record.source_kind if record else getattr(connector, "source_type", "")
        governance = (
            source_quality_fields(
                record,
                endpoints,
                duplicate_of=duplicate_of.get(name),
                profile_core_sources=core_sources,
                health_snapshot=health_snapshot,
            )
            if record
            else {
                "canonical_disciplines": [],
                "catalog_kind": item.get("source_type") or _group(connector),
                "quality_status": "connector_only",
                "core": False,
                "duplicate_of": None,
                "needs_review": True,
                "health_status": "missing_catalog_record",
                "discipline_keys": ["unclassified"],
                "primary_discipline": "Unclassified",
                "primary_discipline_key": "unclassified",
                "primary_discipline_label": "未分类",
                "area_keys": ["general"],
                "primary_area_key": "general",
                "primary_area_label": "综合与未分类",
                "source_kind_key": source_kind_record(item.get("source_type") or _group(connector))["key"],
                "source_kind_label": source_kind_record(item.get("source_type") or _group(connector))["label"],
                "multidisciplinary_supplement": False,
                "category_keys": [f"unclassified.{source_kind_record(item.get('source_type') or _group(connector))['key']}"],
                "category_labels": [f"未分类 · {source_kind_record(item.get('source_type') or _group(connector))['label']}"],
                "category_key": f"unclassified.{source_kind_record(item.get('source_type') or _group(connector))['key']}",
                "category_label": f"未分类 · {source_kind_record(item.get('source_type') or _group(connector))['label']}",
            }
        )
        item.update(
            {
                "display_name": record.name if record else _display_name(name, connector),
                "group": source_type if source_type in {"preprint", "journal", "news", "publisher", "working_papers", "metadata", "local"} else _group(connector),
                "search_mode": _search_mode(name, connector),
                "supports_latest": "latest" in capabilities,
                "supports_search": "search" in capabilities,
                "supports_enrich": "enrich" in capabilities,
                "supports_pdf_link": _supports_pdf_link(name, connector),
                "limitations": _limitations(name, connector),
                "full_text_policy": "external_only",
                "journal": record.name if record else getattr(connector, "journal", None),
                "publisher": record.publisher if record else getattr(connector, "publisher", None),
                "homepage": record.homepage if record else None,
                "url": primary_endpoint.url if primary_endpoint else getattr(connector, "feed_url", None),
                "issn": list(record.issn) if record else getattr(connector, "issn", []),
                "tier": record.tier if record else getattr(connector, "tier", None),
                "topics": list(record.topics) if record else getattr(connector, "topics", []),
                "disciplines": list(record.disciplines) if record else [],
                "status": record.status if record else "active",
                "origin": record.origin if record else None,
                "endpoint_count": len(endpoints),
                "access_modes": sorted({endpoint.mode for endpoint in endpoints}),
                "primary_endpoint": primary_endpoint.key if primary_endpoint else None,
                **governance,
            }
        )
        item["multidisciplinary_supplement"] = bool(
            name in supplement_sources and "multidisciplinary" in (item.get("discipline_keys") or [])
        )
        if _source_matches_filters(item, discipline=discipline, area=area, kind=kind, core=core, health=health):
            sources.append(item)
    return sources
