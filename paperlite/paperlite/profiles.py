from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from paperlite.config import runtime_config
from paperlite.identity import normalize_source

DEFAULT_PROFILE_KEY = "mixed"
MULTIDISCIPLINARY_SUPPLEMENT_PROFILE_KEY = "multidisciplinary"


@dataclass(frozen=True)
class SourceProfile:
    key: str
    label: str
    sources: tuple[str, ...]
    endpoints: tuple[str, ...] = ()
    description: str | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"key": self.key, "label": self.label, "sources": list(self.sources)}
        if self.endpoints:
            payload["endpoints"] = list(self.endpoints)
        if self.description:
            payload["description"] = self.description
        if self.tags:
            payload["tags"] = list(self.tags)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def _as_sources(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(normalize_source(str(item)) for item in value if str(item).strip())
    raw = str(value).strip()
    if not raw:
        return ()
    return tuple(normalize_source(part) for part in raw.split(",") if part.strip())


def _as_endpoints(value: Any) -> tuple[str, ...]:
    return _as_sources(value)


def _unique_sources(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _as_tags(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raw = str(value).strip()
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _profiles_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return runtime_config().profiles_path


def profile_from_dict(item: dict[str, Any]) -> SourceProfile:
    key = normalize_source(str(item.get("key", "")))
    if not key:
        raise ValueError("profile config is missing key")
    exclude = set(_as_sources(item.get("exclude")))
    sources = tuple(
        source
        for source in _unique_sources(_as_sources(item.get("sources")) + _as_sources(item.get("include")))
        if source not in exclude
    )
    endpoints = _unique_sources(_as_endpoints(item.get("endpoints")))
    if not sources and not endpoints:
        raise ValueError(f"profile config {key} has no sources or endpoints")
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return SourceProfile(
        key=key,
        label=str(item.get("label") or key),
        sources=sources,
        endpoints=endpoints,
        description=str(item.get("description") or "").strip() or None,
        tags=_as_tags(item.get("tags")),
        metadata=dict(metadata),
    )


def load_profiles(path: str | Path | None = None) -> tuple[SourceProfile, ...]:
    data = yaml.safe_load(_profiles_path(path).read_text(encoding="utf-8")) or {}
    items = data.get("profiles") or []
    if not isinstance(items, list):
        raise ValueError("profiles.yaml must contain a list under 'profiles'")
    return tuple(profile_from_dict(item) for item in items)


def list_profiles(path: str | Path | None = None) -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in load_profiles(path)]


def get_profile(key: str | None = None, path: str | Path | None = None) -> SourceProfile:
    wanted = normalize_source(key or DEFAULT_PROFILE_KEY)
    profiles = {profile.key: profile for profile in load_profiles(path)}
    return profiles.get(wanted) or profiles[DEFAULT_PROFILE_KEY]


def profile_sources(key: str | None = None, path: str | Path | None = None) -> list[str]:
    return list(get_profile(key, path).sources)


def multidisciplinary_supplement_source_keys(path: str | Path | None = None) -> set[str]:
    try:
        return set(profile_sources(MULTIDISCIPLINARY_SUPPLEMENT_PROFILE_KEY, path))
    except Exception:
        return set()
