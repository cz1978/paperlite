from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from paperlite.config import DEFAULT_HEALTH_SNAPSHOT_PATH, load_config
from paperlite.storage import EXPECTED_SCHEMA_COLUMNS, SCHEMA_VERSION

REQUIRED_PACKAGES = {
    "feedparser": "feedparser",
    "httpx": "httpx",
    "pydantic": "pydantic",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "PyYAML": "yaml",
}
OPTIONAL_PACKAGES = {"mcp": "mcp"}

EXPECTED_TABLES = tuple(EXPECTED_SCHEMA_COLUMNS)

STATUS_RANK = {"ok": 0, "warn": 1, "fail": 2}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _check(check_id: str, label: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": check_id,
        "label": label,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = _sanitize(details)
    return payload


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(token in lowered for token in ("api_key", "token", "secret", "password", "authorization")):
                sanitized[key_text] = bool(item)
            else:
                sanitized[key_text] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _path_writable_or_creatable(path: Path) -> bool:
    target = path if path.exists() else path.parent
    while not target.exists() and target.parent != target:
        target = target.parent
    return target.exists() and os.access(target, os.W_OK)


def _table_count(connection: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return None


def _expected_column_names(table: str) -> set[str]:
    return {definition.split(maxsplit=1)[0].strip('"') for definition in EXPECTED_SCHEMA_COLUMNS.get(table, ())}


def _table_column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _parse_schema_version(value: str | None) -> int | None:
    try:
        return int(str(value or ""))
    except ValueError:
        return None


def _inspect_sqlite(path: Path) -> dict[str, Any]:
    details: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "parent_exists": path.parent.exists(),
        "creatable": _path_writable_or_creatable(path),
    }
    if not path.exists():
        status = "warn" if details["creatable"] else "fail"
        message = "SQLite DB does not exist yet; parent path is writable." if details["creatable"] else "SQLite DB path is not creatable."
        return _check("sqlite_db", "SQLite DB", status, message, details)

    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            tables = sorted(str(row["name"]) for row in rows)
            missing_tables = [table for table in EXPECTED_TABLES if table not in tables]
            schema_row = connection.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone() if "schema_meta" in tables else None
            schema_version = schema_row["value"] if schema_row else None
            missing_columns = {
                table: sorted(_expected_column_names(table) - _table_column_names(connection, table))
                for table in EXPECTED_TABLES
                if table in tables and (_expected_column_names(table) - _table_column_names(connection, table))
            }
            details.update(
                {
                    "tables": tables,
                    "missing_tables": missing_tables,
                    "missing_columns": missing_columns,
                    "schema_version": schema_version,
                    "expected_schema_version": SCHEMA_VERSION,
                    "table_counts": {table: _table_count(connection, table) for table in tables if table in EXPECTED_TABLES},
                }
            )
        finally:
            connection.close()
    except sqlite3.Error as exc:
        details["error"] = str(exc)
        return _check("sqlite_db", "SQLite DB", "fail", "Existing SQLite DB could not be inspected read-only.", details)

    parsed_version = _parse_schema_version(details.get("schema_version"))
    if parsed_version is not None and parsed_version > SCHEMA_VERSION:
        return _check("sqlite_db", "SQLite DB", "fail", "Existing SQLite DB schema is newer than this PaperLite build.", details)
    if details.get("missing_tables") or details.get("missing_columns"):
        return _check("sqlite_db", "SQLite DB", "warn", "Existing SQLite DB is readable but requires additive migration on app startup.", details)
    if parsed_version is None or parsed_version < SCHEMA_VERSION:
        return _check("sqlite_db", "SQLite DB", "warn", "Existing SQLite DB schema version is older than this PaperLite build; startup will confirm or migrate it.", details)
    return _check("sqlite_db", "SQLite DB", "ok", "Existing SQLite DB opened read-only and schema was inspected.", details)


def _catalog_validation_check(paths: dict[str, Path], package_status: str) -> dict[str, Any]:
    if package_status == "fail":
        return _check(
            "catalog_validation",
            "Catalog validation",
            "warn",
            "Skipped catalog validation because required Python packages are missing.",
        )
    if any(not path.exists() for path in (paths["sources"], paths["endpoints"], paths["taxonomy"])):
        return _check("catalog_validation", "Catalog validation", "fail", "Skipped catalog validation because catalog files are missing.")
    try:
        from paperlite.catalog_maintenance import validate_catalog

        result = validate_catalog(
            sources_path=paths["sources"],
            endpoints_path=paths["endpoints"],
            taxonomy_path=paths["taxonomy"],
        )
    except Exception as exc:
        return _check("catalog_validation", "Catalog validation", "fail", "Catalog validation raised an exception.", {"error": str(exc)})

    details = result.to_dict()
    if not result.ok:
        return _check("catalog_validation", "Catalog validation", "fail", "Catalog validation found errors.", details)
    if result.warnings:
        return _check("catalog_validation", "Catalog validation", "warn", "Catalog validation passed with warnings.", details)
    return _check("catalog_validation", "Catalog validation", "ok", "Catalog validation passed.", details)


def run_doctor(env: Mapping[str, str] | None = None, *, cwd: str | Path | None = None) -> dict[str, Any]:
    root = Path(cwd) if cwd is not None else Path.cwd()
    config = load_config(env, cwd=root)
    checks: list[dict[str, Any]] = []

    python_ok = sys.version_info >= (3, 11)
    checks.append(
        _check(
            "python",
            "Python",
            "ok" if python_ok else "fail",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            {"required": ">=3.11", "executable": sys.executable},
        )
    )

    missing_required = [name for name, module in REQUIRED_PACKAGES.items() if not _module_available(module)]
    package_status = "fail" if missing_required else "ok"
    checks.append(
        _check(
            "required_packages",
            "Required packages",
            package_status,
            "All required packages are importable." if not missing_required else "Required packages are missing.",
            {"required": sorted(REQUIRED_PACKAGES), "missing": missing_required},
        )
    )

    missing_optional = [name for name, module in OPTIONAL_PACKAGES.items() if not _module_available(module)]
    checks.append(
        _check(
            "optional_packages",
            "Optional packages",
            "warn" if missing_optional else "ok",
            "Optional packages are missing." if missing_optional else "Optional packages are importable.",
            {"optional": sorted(OPTIONAL_PACKAGES), "missing": missing_optional},
        )
    )

    dotenv_path = root / ".env"
    paths = {
        "sources": config.sources_path,
        "endpoints": config.endpoints_path,
        "profiles": config.profiles_path,
        "taxonomy": config.taxonomy_path,
    }
    missing_catalog_files = [name for name, path in paths.items() if not path.exists()]
    checks.append(
        _check(
            "config_paths",
            "Config paths",
            "fail" if missing_catalog_files else "ok",
            "Config and catalog paths are present." if not missing_catalog_files else "Some config/catalog files are missing.",
            {
                "cwd": str(root),
                "dotenv_path": str(dotenv_path),
                "dotenv_loaded": dotenv_path.exists(),
                "paths": {name: str(path) for name, path in paths.items()},
                "missing": missing_catalog_files,
            },
        )
    )

    checks.append(_catalog_validation_check(paths, package_status))
    checks.append(_inspect_sqlite(config.db_path))

    llm_configured = bool(config.llm_base_url and config.llm_model)
    checks.append(
        _check(
            "llm",
            "LLM",
            "ok" if llm_configured else "warn",
            "LLM is configured." if llm_configured else "LLM is not configured; related features will stay optional.",
            {
                "configured": llm_configured,
                "base_url": config.llm_base_url,
                "model": config.llm_model,
                "credential_present": bool(config.llm_api_key),
            },
        )
    )

    zotero_configured = bool(config.zotero_api_key and config.zotero_library_id)
    zotero_valid_type = config.zotero_library_type in {"user", "group"}
    zotero_status = "ok" if zotero_configured and zotero_valid_type else "warn"
    checks.append(
        _check(
            "zotero",
            "Zotero",
            zotero_status,
            "Zotero metadata export is configured." if zotero_configured and zotero_valid_type else "Zotero is not fully configured; RIS/BibTeX fallback remains available.",
            {
                "configured": zotero_configured and zotero_valid_type,
                "library_type": config.zotero_library_type,
                "library_id_present": bool(config.zotero_library_id),
                "collection_key_present": bool(config.zotero_collection_key),
                "credential_present": bool(config.zotero_api_key),
            },
        )
    )

    checks.append(
        _check(
            "scheduler",
            "Scheduler and crawl timing",
            "ok",
            "Scheduler and crawl timing configuration loaded.",
            {
                "scheduler_enabled": config.scheduler_enabled,
                "scheduler_poll_seconds": config.scheduler_poll_seconds,
                "schedule_min_interval_minutes": config.schedule_min_interval_minutes,
                "crawl_cooldown_seconds": config.crawl_cooldown_seconds,
                "crawl_source_delay_seconds": config.crawl_source_delay_seconds,
            },
        )
    )

    health_path = config.health_snapshot_path
    if health_path is None:
        checks.append(_check("health_snapshot", "Health snapshot", "ok", "Health snapshot is optional and not configured."))
    elif not health_path.exists():
        default_missing = health_path == DEFAULT_HEALTH_SNAPSHOT_PATH
        checks.append(
            _check(
                "health_snapshot",
                "Health snapshot",
                "ok" if default_missing else "warn",
                "Health snapshot has not been generated yet; endpoint health checks are optional."
                if default_missing
                else "Configured health snapshot does not exist yet.",
                {"path": str(health_path), "exists": False},
            )
        )
    else:
        details: dict[str, Any] = {"path": str(health_path), "size_bytes": health_path.stat().st_size}
        try:
            data = json.loads(health_path.read_text(encoding="utf-8"))
            details["entry_count"] = len(data) if isinstance(data, dict) else None
        except Exception as exc:
            details["error"] = str(exc)
            checks.append(_check("health_snapshot", "Health snapshot", "warn", "Health snapshot exists but could not be parsed.", details))
        else:
            checks.append(_check("health_snapshot", "Health snapshot", "ok", "Health snapshot exists and is readable.", details))

    summary = {"ok": 0, "warn": 0, "fail": 0}
    for item in checks:
        summary[str(item["status"])] += 1
    overall = max((str(item["status"]) for item in checks), key=lambda value: STATUS_RANK[value])

    return {
        "overall": overall,
        "summary": summary,
        "generated_at": _utc_now(),
        "checks": checks,
        "config": {
            "db_path": str(config.db_path),
            "sources_path": str(config.sources_path),
            "endpoints_path": str(config.endpoints_path),
            "profiles_path": str(config.profiles_path),
            "taxonomy_path": str(config.taxonomy_path),
            "health_snapshot_path": str(config.health_snapshot_path) if config.health_snapshot_path else None,
        },
    }


def doctor_summary(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") or []
    return {
        "overall": payload.get("overall"),
        "generated_at": payload.get("generated_at"),
        "ok": payload.get("summary", {}).get("ok", 0),
        "warn": payload.get("summary", {}).get("warn", 0),
        "fail": payload.get("summary", {}).get("fail", 0),
        "failures": [item.get("id") for item in checks if item.get("status") == "fail"],
        "warnings": [item.get("id") for item in checks if item.get("status") == "warn"],
    }


def format_doctor_json(payload: dict[str, Any]) -> str:
    return json.dumps(_sanitize(payload), ensure_ascii=False, indent=2)


def format_doctor_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PaperLite Doctor",
        "",
        f"Status: {str(payload.get('overall', 'unknown')).upper()}",
        f"Generated: {payload.get('generated_at', '-')}",
        "",
        "## Checks",
    ]
    for item in payload.get("checks") or []:
        status = str(item.get("status", "")).upper()
        lines.append(f"- [{status}] {item.get('label')}: {item.get('message')}")
        details = item.get("details")
        if details:
            lines.append(f"  - details: `{json.dumps(_sanitize(details), ensure_ascii=False, sort_keys=True)}`")
    return "\n".join(lines)
