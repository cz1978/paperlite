import json

import pytest

from paperlite.catalog_maintenance import add_feed_source, validate_catalog
from paperlite.cli import main
from paperlite.registry import clear_registry_cache
from paperlite.sources import ENDPOINTS_ENV_VAR, SOURCES_ENV_VAR, clear_catalog_cache, load_endpoint_configs, load_source_records


def write_catalog(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    endpoints_path = tmp_path / "endpoints.yaml"
    sources_path.write_text(
        """
sources:
- key: existing_journal
  name: Existing Journal
  source_kind: journal
  disciplines:
  - Chemistry
  status: active
""".strip(),
        encoding="utf-8",
    )
    endpoints_path.write_text(
        """
endpoints:
- key: existing_journal
  source_key: existing_journal
  mode: rss
  url: https://example.com/existing.xml
  status: active
""".strip(),
        encoding="utf-8",
    )
    return sources_path, endpoints_path


def test_validate_builtin_catalog_passes():
    result = validate_catalog()

    assert result.ok is True
    assert result.counts["source_count"] >= 800
    assert result.counts["endpoint_count"] >= 800
    assert result.to_dict()["ok"] is True


def test_validate_reports_common_catalog_errors(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    endpoints_path = tmp_path / "endpoints.yaml"
    sources_path.write_text(
        """
sources:
- key: bad key
  name: Bad Key
  source_kind: journal
  disciplines:
  - Chemistry
- key: bad_discipline
  name: Bad Discipline
  source_kind: journal
  disciplines:
  - Nopeology
- key: good_journal
  name: Good Journal
  source_kind: journal
  disciplines:
  - Chemistry
""".strip(),
        encoding="utf-8",
    )
    endpoints_path.write_text(
        """
endpoints:
- key: orphan
  source_key: missing_source
  mode: rss
  url: https://example.com/orphan.xml
  status: active
- key: no_url
  source_key: good_journal
  mode: rss
  status: active
- key: dup_a
  source_key: good_journal
  mode: rss
  url: https://example.com/dup.xml
  status: active
- key: dup_b
  source_key: good_journal
  mode: rss
  url: https://example.com/dup.xml
  status: active
""".strip(),
        encoding="utf-8",
    )

    result = validate_catalog(sources_path=sources_path, endpoints_path=endpoints_path)

    assert result.ok is False
    error_codes = {issue.code for issue in result.errors}
    warning_codes = {issue.code for issue in result.warnings}
    assert {"invalid_key", "invalid_discipline", "unknown_endpoint_source", "missing_endpoint_url"} <= error_codes
    assert "duplicate_endpoint_url" in warning_codes
    assert "FAILED" in result.to_markdown()


def test_validate_ignores_non_crawl_duplicate_urls(tmp_path):
    sources_path = tmp_path / "sources.yaml"
    endpoints_path = tmp_path / "endpoints.yaml"
    sources_path.write_text(
        """
sources:
- key: api_a
  name: API A
  source_kind: metadata
  disciplines:
  - Multidisciplinary
  status: active
- key: api_b
  name: API B
  source_kind: metadata
  disciplines:
  - Multidisciplinary
  status: active
- key: parked_feed
  name: Parked Feed
  source_kind: journal
  status: temporarily_unavailable
""".strip(),
        encoding="utf-8",
    )
    endpoints_path.write_text(
        """
endpoints:
- key: api_a
  source_key: api_a
  mode: api
  url: https://api.example.test/works
  status: active
- key: api_b
  source_key: api_b
  mode: api
  url: https://api.example.test/works
  status: active
- key: parked_feed
  source_key: parked_feed
  mode: rss
  url: https://example.test/feed.xml
  enabled: false
  status: temporarily_unavailable
""".strip(),
        encoding="utf-8",
    )

    result = validate_catalog(sources_path=sources_path, endpoints_path=endpoints_path)

    assert result.ok is True
    assert not result.warnings


def test_add_source_dry_run_does_not_write(tmp_path):
    sources_path, endpoints_path = write_catalog(tmp_path)
    before_sources = sources_path.read_text(encoding="utf-8")
    before_endpoints = endpoints_path.read_text(encoding="utf-8")

    result = add_feed_source(
        key="new_journal",
        name="New Journal",
        kind="journal",
        discipline="Chemistry",
        url="https://example.com/new.xml",
        publisher="Example Publisher",
        sources_path=sources_path,
        endpoints_path=endpoints_path,
    )

    assert result.wrote is False
    assert "dry-run only; use --write to apply" in result.to_markdown()
    assert "new_journal" in result.source_yaml
    assert sources_path.read_text(encoding="utf-8") == before_sources
    assert endpoints_path.read_text(encoding="utf-8") == before_endpoints


def test_add_source_write_appends_and_validates(tmp_path):
    sources_path, endpoints_path = write_catalog(tmp_path)

    result = add_feed_source(
        key="new_journal",
        name="New Journal",
        kind="journal",
        discipline="chem",
        url="https://example.com/new.xml",
        publisher="Example Publisher",
        mode="atom",
        write=True,
        sources_path=sources_path,
        endpoints_path=endpoints_path,
    )

    clear_catalog_cache()
    sources = {source.key: source for source in load_source_records(sources_path)}
    endpoints = {endpoint.key: endpoint for endpoint in load_endpoint_configs(sources_path, endpoints_path)}
    assert result.wrote is True
    assert result.validation.ok is True
    assert sources["new_journal"].disciplines == ["Chemistry"]
    assert endpoints["new_journal"].mode == "atom"
    assert endpoints["new_journal"].url == "https://example.com/new.xml"


def test_add_source_rejects_duplicate_url_and_bad_discipline(tmp_path):
    sources_path, endpoints_path = write_catalog(tmp_path)

    with pytest.raises(ValueError, match="duplicate_endpoint_url"):
        add_feed_source(
            key="duplicate_url",
            name="Duplicate URL",
            kind="journal",
            discipline="Chemistry",
            url="https://example.com/existing.xml",
            sources_path=sources_path,
            endpoints_path=endpoints_path,
        )

    with pytest.raises(ValueError, match="invalid_discipline"):
        add_feed_source(
            key="bad_discipline",
            name="Bad Discipline",
            kind="journal",
            discipline="Nopeology",
            url="https://example.com/bad.xml",
            sources_path=sources_path,
            endpoints_path=endpoints_path,
        )


def test_catalog_cli_validate_json_and_add_source_dry_run(tmp_path, monkeypatch, capsys):
    sources_path, endpoints_path = write_catalog(tmp_path)
    monkeypatch.setenv(SOURCES_ENV_VAR, str(sources_path))
    monkeypatch.setenv(ENDPOINTS_ENV_VAR, str(endpoints_path))
    clear_catalog_cache()
    clear_registry_cache()

    main(["catalog", "validate", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["counts"]["source_count"] == 1

    main(
        [
            "catalog",
            "add-source",
            "--key",
            "cli_journal",
            "--name",
            "CLI Journal",
            "--kind",
            "journal",
            "--discipline",
            "Chemistry",
            "--url",
            "https://example.com/cli.xml",
        ]
    )
    output = capsys.readouterr().out
    assert "dry-run only; use --write to apply" in output
    assert "cli_journal" in output
    assert "cli_journal" not in sources_path.read_text(encoding="utf-8")

    monkeypatch.delenv(SOURCES_ENV_VAR)
    monkeypatch.delenv(ENDPOINTS_ENV_VAR)
    clear_catalog_cache()
    clear_registry_cache()
