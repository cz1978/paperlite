from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNTIME_DIR = Path(".paperlite")

DEFAULT_SOURCES_PATH = PACKAGE_ROOT / "sources.yaml"
DEFAULT_ENDPOINTS_PATH = PACKAGE_ROOT / "endpoints.yaml"
DEFAULT_PROFILES_PATH = PACKAGE_ROOT / "profiles.yaml"
DEFAULT_TRANSLATION_PROFILES_PATH = PACKAGE_ROOT / "translation_profiles.yaml"
DEFAULT_TAXONOMY_PATH = PACKAGE_ROOT / "taxonomy.yaml"
DEFAULT_HEALTH_SNAPSHOT_PATH = DEFAULT_RUNTIME_DIR / "endpoint_health_snapshot.json"
DEFAULT_DB_RELATIVE_PATH = DEFAULT_RUNTIME_DIR / "paperlite.sqlite3"

SOURCES_ENV_VAR = "PAPERLITE_SOURCES_PATH"
ENDPOINTS_ENV_VAR = "PAPERLITE_ENDPOINTS_PATH"
PROFILES_ENV_VAR = "PAPERLITE_PROFILES_PATH"
TRANSLATION_PROFILES_ENV_VAR = "PAPERLITE_TRANSLATION_PROFILES_PATH"
TAXONOMY_ENV_VAR = "PAPERLITE_TAXONOMY_PATH"
HEALTH_SNAPSHOT_ENV_VAR = "PAPERLITE_HEALTH_SNAPSHOT_PATH"
DB_ENV_VAR = "PAPERLITE_DB_PATH"

CRAWL_COOLDOWN_ENV = "PAPERLITE_CRAWL_COOLDOWN_SECONDS"
CRAWL_SOURCE_DELAY_ENV = "PAPERLITE_CRAWL_SOURCE_DELAY_SECONDS"
SCHEDULE_MIN_INTERVAL_ENV = "PAPERLITE_SCHEDULE_MIN_INTERVAL_MINUTES"
SCHEDULER_POLL_ENV = "PAPERLITE_SCHEDULER_POLL_SECONDS"
SCHEDULER_ENABLED_ENV = "PAPERLITE_SCHEDULER_ENABLED"
ENRICH_TIMEOUT_ENV = "PAPERLITE_ENRICH_TIMEOUT_SECONDS"
TRAINING_EXPORT_TOKEN_ENV = "PAPERLITE_TRAINING_EXPORT_TOKEN"

LLM_BASE_URL_ENV = "PAPERLITE_LLM_BASE_URL"
LLM_API_KEY_ENV = "PAPERLITE_LLM_API_KEY"
LLM_MODEL_ENV = "PAPERLITE_LLM_MODEL"
LLM_PROVIDER_ENV = "PAPERLITE_LLM_PROVIDER"
DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

EMBEDDING_BASE_URL_ENV = "PAPERLITE_EMBEDDING_BASE_URL"
EMBEDDING_API_KEY_ENV = "PAPERLITE_EMBEDDING_API_KEY"
EMBEDDING_MODEL_ENV = "PAPERLITE_EMBEDDING_MODEL"

ZOTERO_API_KEY_ENV = "ZOTERO_API_KEY"
ZOTERO_LIBRARY_TYPE_ENV = "ZOTERO_LIBRARY_TYPE"
ZOTERO_LIBRARY_ID_ENV = "ZOTERO_LIBRARY_ID"
ZOTERO_COLLECTION_KEY_ENV = "ZOTERO_COLLECTION_KEY"
ZOTERO_API_BASE_URL = "https://api.zotero.org"

DEFAULT_CRAWL_COOLDOWN_SECONDS = 600
DEFAULT_CRAWL_SOURCE_DELAY_SECONDS = 2.0
DEFAULT_SCHEDULE_MIN_INTERVAL_MINUTES = 15
DEFAULT_SCHEDULER_POLL_SECONDS = 30
DEFAULT_ENRICH_TIMEOUT_SECONDS = 6.0

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class PaperLiteConfig:
    sources_path: Path = DEFAULT_SOURCES_PATH
    endpoints_path: Path = DEFAULT_ENDPOINTS_PATH
    profiles_path: Path = DEFAULT_PROFILES_PATH
    translation_profiles_path: Path = DEFAULT_TRANSLATION_PROFILES_PATH
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    health_snapshot_path: Path | None = None
    db_path: Path = DEFAULT_DB_RELATIVE_PATH
    crawl_cooldown_seconds: int = DEFAULT_CRAWL_COOLDOWN_SECONDS
    crawl_source_delay_seconds: float = DEFAULT_CRAWL_SOURCE_DELAY_SECONDS
    schedule_min_interval_minutes: int = DEFAULT_SCHEDULE_MIN_INTERVAL_MINUTES
    scheduler_poll_seconds: int = DEFAULT_SCHEDULER_POLL_SECONDS
    scheduler_enabled: bool = True
    enrich_timeout_seconds: float = DEFAULT_ENRICH_TIMEOUT_SECONDS
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    training_export_token: str | None = None
    zotero_api_key: str | None = None
    zotero_library_type: str = "user"
    zotero_library_id: str | None = None
    zotero_collection_key: str | None = None
    zotero_api_base_url: str = ZOTERO_API_BASE_URL


def _value(env: Mapping[str, str], key: str) -> str:
    return str(env.get(key) or "").strip()


def _path(env: Mapping[str, str], key: str, default: Path, *, cwd: Path | None = None) -> Path:
    raw = _value(env, key)
    if raw:
        return Path(raw)
    if default.is_absolute():
        return default
    return (cwd or Path.cwd()) / default


def _optional_path(env: Mapping[str, str], key: str, default: Path | None = None) -> Path | None:
    raw = _value(env, key)
    if raw:
        return Path(raw)
    return default


def _optional_str(env: Mapping[str, str], key: str) -> str | None:
    raw = _value(env, key)
    return raw or None


def _int(env: Mapping[str, str], key: str, default: int, *, minimum: int | None = None) -> int:
    raw = _value(env, key)
    try:
        value = int(raw) if raw else int(default)
    except ValueError:
        value = int(default)
    return max(minimum, value) if minimum is not None else value


def _float(env: Mapping[str, str], key: str, default: float, *, minimum: float | None = None) -> float:
    raw = _value(env, key)
    try:
        value = float(raw) if raw else float(default)
    except ValueError:
        value = float(default)
    return max(minimum, value) if minimum is not None else value


def _bool(env: Mapping[str, str], key: str, default: bool = False) -> bool:
    raw = _value(env, key).lower()
    if not raw:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    return default


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _runtime_dotenv_path(cwd: Path | None = None) -> Path:
    root = cwd or Path.cwd()
    current = root / ".env"
    if current.exists():
        return current
    parent = root.parent / ".env"
    if root.parent != root and parent.exists():
        return parent
    return current


def _runtime_env(cwd: Path | None = None) -> Mapping[str, str]:
    return {**_dotenv_values(_runtime_dotenv_path(cwd)), **os.environ}


def load_config(env: Mapping[str, str] | None = None, *, cwd: Path | None = None) -> PaperLiteConfig:
    values = env if env is not None else _runtime_env(cwd)
    provider = _value(values, LLM_PROVIDER_ENV).lower()
    deepseek_key = _optional_str(values, DEEPSEEK_API_KEY_ENV)
    generic_llm_key = _optional_str(values, LLM_API_KEY_ENV)
    llm_api_key = generic_llm_key or deepseek_key
    use_deepseek_defaults = bool(deepseek_key) or (provider == "deepseek" and bool(generic_llm_key))
    return PaperLiteConfig(
        sources_path=_path(values, SOURCES_ENV_VAR, DEFAULT_SOURCES_PATH),
        endpoints_path=_path(values, ENDPOINTS_ENV_VAR, DEFAULT_ENDPOINTS_PATH),
        profiles_path=_path(values, PROFILES_ENV_VAR, DEFAULT_PROFILES_PATH),
        translation_profiles_path=_path(values, TRANSLATION_PROFILES_ENV_VAR, DEFAULT_TRANSLATION_PROFILES_PATH),
        taxonomy_path=_path(values, TAXONOMY_ENV_VAR, DEFAULT_TAXONOMY_PATH),
        health_snapshot_path=_optional_path(values, HEALTH_SNAPSHOT_ENV_VAR, DEFAULT_HEALTH_SNAPSHOT_PATH),
        db_path=_path(values, DB_ENV_VAR, DEFAULT_DB_RELATIVE_PATH, cwd=cwd),
        crawl_cooldown_seconds=_int(values, CRAWL_COOLDOWN_ENV, DEFAULT_CRAWL_COOLDOWN_SECONDS, minimum=0),
        crawl_source_delay_seconds=_float(values, CRAWL_SOURCE_DELAY_ENV, DEFAULT_CRAWL_SOURCE_DELAY_SECONDS, minimum=0.0),
        schedule_min_interval_minutes=_int(values, SCHEDULE_MIN_INTERVAL_ENV, DEFAULT_SCHEDULE_MIN_INTERVAL_MINUTES, minimum=1),
        scheduler_poll_seconds=_int(values, SCHEDULER_POLL_ENV, DEFAULT_SCHEDULER_POLL_SECONDS, minimum=5),
        scheduler_enabled=_bool(values, SCHEDULER_ENABLED_ENV, True),
        enrich_timeout_seconds=_float(values, ENRICH_TIMEOUT_ENV, DEFAULT_ENRICH_TIMEOUT_SECONDS, minimum=1.0),
        llm_base_url=_optional_str(values, LLM_BASE_URL_ENV)
        or (DEFAULT_DEEPSEEK_BASE_URL if use_deepseek_defaults else None),
        llm_api_key=llm_api_key,
        llm_model=_optional_str(values, LLM_MODEL_ENV)
        or (DEFAULT_DEEPSEEK_MODEL if use_deepseek_defaults else None),
        embedding_base_url=_optional_str(values, EMBEDDING_BASE_URL_ENV),
        embedding_api_key=_optional_str(values, EMBEDDING_API_KEY_ENV),
        embedding_model=_optional_str(values, EMBEDDING_MODEL_ENV),
        training_export_token=_optional_str(values, TRAINING_EXPORT_TOKEN_ENV),
        zotero_api_key=_optional_str(values, ZOTERO_API_KEY_ENV),
        zotero_library_type=_value(values, ZOTERO_LIBRARY_TYPE_ENV).lower() or "user",
        zotero_library_id=_optional_str(values, ZOTERO_LIBRARY_ID_ENV),
        zotero_collection_key=_optional_str(values, ZOTERO_COLLECTION_KEY_ENV),
    )


def runtime_config() -> PaperLiteConfig:
    return load_config()
