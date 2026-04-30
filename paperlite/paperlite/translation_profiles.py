from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from paperlite.config import runtime_config

DEFAULT_BRIEF_TRANSLATION_PROFILE = "research_card_cn"
DEFAULT_DETAIL_TRANSLATION_PROFILE = "detail_cn"
DETAIL_TRANSLATION_STYLES = {"detail", "detail_literal", "literal_detail"}


@dataclass(frozen=True)
class TranslationProfile:
    key: str
    label: str
    target_language: str
    style: str
    title_prompt: str
    body_prompt: str
    output_schema: dict[str, Any]
    max_tokens: int
    version: str

    @property
    def prompt_hash(self) -> str:
        material = {
            "key": self.key,
            "target_language": self.target_language,
            "style": self.style,
            "title_prompt": self.title_prompt,
            "body_prompt": self.body_prompt,
            "output_schema": self.output_schema,
            "max_tokens": self.max_tokens,
            "version": self.version,
        }
        content = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_dict(self, *, include_prompts: bool = False) -> dict[str, Any]:
        payload = {
            "key": self.key,
            "label": self.label,
            "target_language": self.target_language,
            "style": self.style,
            "output_schema": self.output_schema,
            "max_tokens": self.max_tokens,
            "version": self.version,
            "prompt_hash": self.prompt_hash,
        }
        if include_prompts:
            payload["title_prompt"] = self.title_prompt
            payload["body_prompt"] = self.body_prompt
        return payload


def _profiles_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return runtime_config().translation_profiles_path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _profile_from_dict(item: dict[str, Any], *, index: int) -> TranslationProfile:
    key = _text(item.get("key"))
    if not key:
        raise ValueError(f"translation profile at index {index} is missing key")
    label = _text(item.get("label")) or key
    target_language = _text(item.get("target_language")) or "zh-CN"
    style = _text(item.get("style")) or "brief"
    title_prompt = _text(item.get("title_prompt"))
    body_prompt = _text(item.get("body_prompt"))
    if not body_prompt:
        raise ValueError(f"translation profile {key} is missing body_prompt")
    if style.lower() == "brief" and not title_prompt:
        raise ValueError(f"translation profile {key} is missing title_prompt")
    output_schema = item.get("output_schema")
    if not isinstance(output_schema, dict):
        raise ValueError(f"translation profile {key} output_schema must be an object")
    try:
        max_tokens = int(item.get("max_tokens") or 1200)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"translation profile {key} max_tokens must be an integer") from exc
    if max_tokens <= 0:
        raise ValueError(f"translation profile {key} max_tokens must be positive")
    version = _text(item.get("version"))
    if not version:
        raise ValueError(f"translation profile {key} is missing version")
    return TranslationProfile(
        key=key,
        label=label,
        target_language=target_language,
        style=style,
        title_prompt=title_prompt,
        body_prompt=body_prompt,
        output_schema=output_schema,
        max_tokens=max_tokens,
        version=version,
    )


def load_translation_profiles(path: str | Path | None = None) -> tuple[TranslationProfile, ...]:
    data = yaml.safe_load(_profiles_path(path).read_text(encoding="utf-8")) or {}
    items = data.get("profiles") or []
    if not isinstance(items, list):
        raise ValueError("translation_profiles.yaml must contain a list under 'profiles'")
    profiles = tuple(_profile_from_dict(item, index=index) for index, item in enumerate(items) if isinstance(item, dict))
    if len(profiles) != len(items):
        raise ValueError("translation profile entries must be objects")
    keys = [profile.key for profile in profiles]
    if len(keys) != len(set(keys)):
        raise ValueError("translation profile keys must be unique")
    return profiles


def list_translation_profiles(path: str | Path | None = None) -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in load_translation_profiles(path)]


def get_translation_profile(key: str, path: str | Path | None = None) -> TranslationProfile:
    selected = _text(key)
    profiles = {profile.key: profile for profile in load_translation_profiles(path)}
    if selected not in profiles:
        raise ValueError(f"unknown translation profile: {selected}")
    return profiles[selected]


def default_translation_profile_for_style(style: str | None) -> str | None:
    selected = _text(style).lower() or "brief"
    if selected == "brief":
        return DEFAULT_BRIEF_TRANSLATION_PROFILE
    if selected in DETAIL_TRANSLATION_STYLES:
        return DEFAULT_DETAIL_TRANSLATION_PROFILE
    return None


def resolve_translation_profile(
    *,
    translation_profile: str | None = None,
    style: str | None = None,
    path: str | Path | None = None,
) -> TranslationProfile | None:
    selected_key = _text(translation_profile) or default_translation_profile_for_style(style)
    if not selected_key:
        return None
    profile = get_translation_profile(selected_key, path)
    requested_style = _text(style)
    profile_style = profile.style.lower()
    requested_style_lower = requested_style.lower()
    style_matches = requested_style_lower == profile_style or (
        profile_style == "detail" and requested_style_lower in DETAIL_TRANSLATION_STYLES
    )
    if requested_style and not style_matches:
        raise ValueError(
            f"translation_profile {profile.key} has style {profile.style}; requested style {requested_style}"
        )
    return profile
