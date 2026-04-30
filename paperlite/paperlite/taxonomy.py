from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from paperlite.config import TAXONOMY_ENV_VAR as TAXONOMY_ENV_VAR, runtime_config


@dataclass(frozen=True)
class Taxonomy:
    areas: tuple[dict[str, str], ...]
    disciplines: tuple[dict[str, str], ...]
    source_kinds: tuple[dict[str, str], ...]
    ignored_discipline_terms: frozenset[str]
    area_labels: dict[str, str]
    discipline_by_key: dict[str, dict[str, str]]
    discipline_by_name: dict[str, dict[str, str]]
    discipline_aliases: dict[str, str]
    source_kind_by_key: dict[str, dict[str, str]]


def _alias_key(value: str) -> str:
    return " ".join(str(value).replace("_", " ").replace("-", " ").strip().lower().split())


def _stable_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def taxonomy_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return runtime_config().taxonomy_path


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique_by_key(items: list[dict[str, Any]], section: str) -> None:
    seen: set[str] = set()
    for item in items:
        key = _stable_key(item.get("key"))
        if not key:
            raise ValueError(f"taxonomy {section} item is missing key")
        if key in seen:
            raise ValueError(f"taxonomy {section} has duplicate key: {key}")
        seen.add(key)


def _records(items: list[dict[str, Any]], section: str) -> tuple[dict[str, str], ...]:
    _unique_by_key(items, section)
    records: list[dict[str, str]] = []
    for item in items:
        record = {str(key): str(value) for key, value in item.items() if key != "aliases" and value is not None}
        record["key"] = _stable_key(record.get("key"))
        records.append(record)
    return tuple(records)


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"taxonomy file does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("taxonomy.yaml must contain a mapping")
    return data


def _build_aliases(raw_disciplines: list[dict[str, Any]], discipline_by_key: dict[str, dict[str, str]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in raw_disciplines:
        key = _stable_key(item.get("key"))
        record = discipline_by_key[key]
        terms = [key, record["name"], *_as_list(item.get("aliases"))]
        for term in terms:
            alias = _alias_key(str(term))
            compact_alias = alias.replace(" ", "")
            if alias:
                aliases[alias] = record["name"]
            if compact_alias:
                aliases[compact_alias] = record["name"]
    return aliases


@lru_cache(maxsize=8)
def load_taxonomy(path: str | Path | None = None) -> Taxonomy:
    data = _load_raw(taxonomy_path(path))
    raw_areas = _as_list(data.get("areas"))
    raw_disciplines = _as_list(data.get("disciplines"))
    raw_source_kinds = _as_list(data.get("source_kinds"))
    if not raw_areas:
        raise ValueError("taxonomy.yaml must contain areas")
    if not raw_disciplines:
        raise ValueError("taxonomy.yaml must contain disciplines")
    if not raw_source_kinds:
        raise ValueError("taxonomy.yaml must contain source_kinds")

    areas = _records(raw_areas, "areas")
    disciplines = _records(raw_disciplines, "disciplines")
    source_kinds = _records(raw_source_kinds, "source_kinds")
    area_labels = {item["key"]: item.get("label", item["key"]) for item in areas}
    discipline_by_key = {item["key"]: item for item in disciplines}
    discipline_by_name = {item["name"]: item for item in disciplines if item.get("name")}
    source_kind_by_key = {item["key"]: item for item in source_kinds}

    if "general" not in area_labels:
        raise ValueError("taxonomy areas must include key: general")
    if "unclassified" not in discipline_by_key:
        raise ValueError("taxonomy disciplines must include key: unclassified")
    missing_areas = sorted({item.get("area_key") for item in disciplines if item.get("area_key") not in area_labels})
    if missing_areas:
        raise ValueError(f"taxonomy disciplines reference unknown area_key: {', '.join(missing_areas)}")

    ignored = frozenset(_alias_key(str(item)) for item in _as_list(data.get("ignored_discipline_terms")))
    return Taxonomy(
        areas=areas,
        disciplines=disciplines,
        source_kinds=source_kinds,
        ignored_discipline_terms=ignored,
        area_labels=area_labels,
        discipline_by_key=discipline_by_key,
        discipline_by_name=discipline_by_name,
        discipline_aliases=_build_aliases(raw_disciplines, discipline_by_key),
        source_kind_by_key=source_kind_by_key,
    )


def clear_taxonomy_cache() -> None:
    load_taxonomy.cache_clear()


def canonicalize_discipline(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    taxonomy = load_taxonomy()
    key = _alias_key(raw)
    if key in taxonomy.ignored_discipline_terms:
        return None
    compact_key = key.replace(" ", "")
    return taxonomy.discipline_aliases.get(key) or taxonomy.discipline_aliases.get(compact_key) or raw


def canonical_disciplines(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        canonical = canonicalize_discipline(value)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def taxonomy_key_for_discipline(value: str | None) -> str:
    taxonomy = load_taxonomy()
    canonical = canonicalize_discipline(value)
    if not canonical:
        return "unclassified"
    raw_key = _stable_key(value)
    record = taxonomy.discipline_by_name.get(canonical) or taxonomy.discipline_by_key.get(raw_key)
    return str(record["key"]) if record else "unclassified"


def discipline_record(value: str | None) -> dict[str, str]:
    taxonomy = load_taxonomy()
    key = taxonomy_key_for_discipline(value)
    record = taxonomy.discipline_by_key.get(key) or taxonomy.discipline_by_key["unclassified"]
    area_key = str(record["area_key"])
    return {
        "key": str(record["key"]),
        "name": str(record["name"]),
        "label": str(record["label"]),
        "area_key": area_key,
        "area_label": taxonomy.area_labels.get(area_key, area_key),
        "description": str(record["description"]),
    }


def source_kind_record(source_kind: str | None) -> dict[str, str]:
    taxonomy = load_taxonomy()
    key = _stable_key(source_kind) or "publisher"
    record = taxonomy.source_kind_by_key.get(key)
    if record:
        return {
            "key": str(record["key"]),
            "label": str(record["label"]),
            "description": str(record["description"]),
        }
    return {
        "key": key,
        "label": key.replace("_", " "),
        "description": "未纳入内置类型表的来源类型，需要人工确认。",
    }


def taxonomy_areas() -> tuple[dict[str, str], ...]:
    return load_taxonomy().areas


def taxonomy_disciplines() -> tuple[dict[str, str], ...]:
    return load_taxonomy().disciplines


def taxonomy_source_kinds() -> tuple[dict[str, str], ...]:
    return load_taxonomy().source_kinds


def area_label(area_key: str) -> str:
    return load_taxonomy().area_labels.get(area_key, area_key)
