import pytest

from paperlite.catalog_quality import (
    build_catalog_coverage,
    build_catalog_summary,
    build_taxonomy_summary,
    canonical_disciplines,
    duplicate_endpoint_sources,
    endpoint_health_status,
    format_catalog_coverage_markdown,
    format_taxonomy_markdown,
    load_health_snapshot,
    source_quality_fields,
)
from paperlite.connectors.base import EndpointConfig, SourceRecord
from paperlite.sources import load_source_records
from paperlite.taxonomy import TAXONOMY_ENV_VAR, clear_taxonomy_cache, load_taxonomy


def make_source(**overrides):
    values = {
        "key": "source-a",
        "name": "Source A",
        "source_kind": "journal",
        "disciplines": ["chem", "EarthScience", "ComputerScience"],
        "tier": "T0",
    }
    values.update(overrides)
    return SourceRecord(**values)


def make_endpoint(**overrides):
    values = {
        "key": "endpoint-a",
        "source_key": "source-a",
        "mode": "rss",
        "url": "https://example.com/feed.xml",
        "enabled": True,
        "status": "active",
    }
    values.update(overrides)
    return EndpointConfig(**values)


def write_taxonomy(path, *, disciplines_extra=""):
    path.write_text(
        f"""
areas:
- key: general
  label: General
ignored_discipline_terms:
- preprint
disciplines:
- key: unclassified
  name: Unclassified
  label: Unclassified
  area_key: general
  description: Needs review.
  aliases:
  - unclassified
- key: custom_ai
  name: Custom AI
  label: Custom AI
  area_key: general
  description: Custom AI discipline.
  aliases:
  - ai
  - machine intelligence
{disciplines_extra}
source_kinds:
- key: journal
  label: Journal
  description: Journal feed.
""".strip(),
        encoding="utf-8",
    )


def test_canonical_disciplines_normalizes_aliases():
    assert canonical_disciplines(["chem", "EarthScience", "earth", "ComputerScience", "Chemistry"]) == [
        "Chemistry",
        "Earth Science",
        "Computer Science",
    ]


def test_taxonomy_loader_reads_default_and_env_override(tmp_path, monkeypatch):
    default_taxonomy = load_taxonomy()
    assert any(item["key"] == "medicine" for item in default_taxonomy.disciplines)

    override = tmp_path / "taxonomy.yaml"
    write_taxonomy(override)
    monkeypatch.setenv(TAXONOMY_ENV_VAR, str(override))
    clear_taxonomy_cache()

    assert canonical_disciplines(["ai", "machine intelligence", "preprint"]) == ["Custom AI"]

    monkeypatch.delenv(TAXONOMY_ENV_VAR)
    clear_taxonomy_cache()


def test_taxonomy_loader_validates_required_references(tmp_path):
    invalid = tmp_path / "taxonomy.yaml"
    write_taxonomy(
        invalid,
        disciplines_extra="""
- key: broken
  name: Broken
  label: Broken
  area_key: missing_area
  description: Broken area.
""",
    )
    clear_taxonomy_cache()

    with pytest.raises(ValueError, match="unknown area_key"):
        load_taxonomy(invalid)

    clear_taxonomy_cache()


def test_health_snapshot_and_endpoint_status(tmp_path):
    path = tmp_path / "health.json"
    path.write_text(
        """
{
  "health": [
    {"key": "endpoint-a", "ok": false, "classification": "blocked_403", "checked_at": "2026-04-28T00:00:00Z"},
    {"key": "endpoint-b", "ok": true, "classification": "ok", "checked_at": "2026-04-28T00:00:01Z"}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    snapshot = load_health_snapshot(path)

    assert endpoint_health_status(make_endpoint(key="endpoint-a"), snapshot) == "blocked_403"
    assert endpoint_health_status(make_endpoint(key="endpoint-b"), snapshot) == "ok"
    assert endpoint_health_status(make_endpoint(key="missing", enabled=False, status="temporarily_unavailable"), snapshot) == "temporarily_unavailable"


def test_duplicate_endpoint_sources_maps_later_sources_to_first_source():
    endpoints = [
        make_endpoint(key="b", source_key="source-b", url="https://example.com/same.xml"),
        make_endpoint(key="a", source_key="source-a", url="https://example.com/same.xml"),
        make_endpoint(key="c", source_key="source-c", url="https://example.com/other.xml"),
    ]

    assert duplicate_endpoint_sources(endpoints) == {"source-b": "source-a"}


def test_source_quality_fields_marks_core_duplicate_and_review_states():
    source = make_source()
    endpoint = make_endpoint()

    fields = source_quality_fields(
        source,
        [endpoint],
        profile_core_sources=set(),
        health_snapshot={},
    )

    assert fields["canonical_disciplines"] == ["Chemistry", "Earth Science", "Computer Science"]
    assert fields["catalog_kind"] == "journal"
    assert fields["discipline_keys"] == ["chemistry", "earth_science", "computer_science"]
    assert fields["primary_discipline_key"] == "chemistry"
    assert fields["primary_area_key"] == "physical_sciences"
    assert fields["source_kind_key"] == "journal"
    assert fields["category_keys"] == [
        "chemistry.journal",
        "earth_science.journal",
        "computer_science.journal",
    ]
    assert fields["category_key"] == "chemistry.journal"
    assert fields["core"] is True
    assert fields["needs_review"] is False
    assert fields["quality_status"] == "core"

    duplicate = source_quality_fields(
        source,
        [endpoint],
        duplicate_of="source-other",
        profile_core_sources=set(),
        health_snapshot={},
    )
    assert duplicate["duplicate_of"] == "source-other"
    assert duplicate["quality_status"] == "duplicate"
    assert duplicate["needs_review"] is True

    missing = source_quality_fields(
        make_source(disciplines=[], tier=None),
        [make_endpoint(enabled=False, status="candidate")],
        profile_core_sources=set(),
        health_snapshot={},
    )
    assert missing["health_status"] == "candidate"
    assert missing["quality_status"] == "candidate"
    assert missing["needs_review"] is True


def test_source_health_snapshot_failure_is_not_masked_by_static_active():
    source = make_source()
    endpoint = make_endpoint(status="active", enabled=True)

    blocked = source_quality_fields(
        source,
        [endpoint],
        profile_core_sources=set(),
        health_snapshot={"endpoint-a": {"ok": False, "classification": "blocked_403"}},
    )
    assert blocked["health_status"] == "blocked_403"
    assert blocked["quality_status"] == "temporarily_unavailable"

    ok = source_quality_fields(
        source,
        [endpoint],
        profile_core_sources=set(),
        health_snapshot={"endpoint-a": {"ok": True, "classification": "ok"}},
    )
    assert ok["health_status"] == "ok"


def test_catalog_summary_reports_current_builtin_catalog():
    summary = build_catalog_summary()

    assert summary["source_count"] >= 800
    assert summary["endpoint_count"] >= 800
    assert summary["endpoint_mode_counts"]["rss"] >= 600
    assert summary["temporarily_unavailable_endpoint_count"] >= 100
    assert summary["missing_discipline_count"] == 0
    assert summary["duplicate_url_groups"] >= 1
    assert summary["health_snapshot_loaded"] is False


def test_active_builtin_sources_do_not_resolve_to_unclassified_disciplines():
    bad_sources = []
    for source in load_source_records():
        if source.status != "active":
            continue
        fields = source_quality_fields(
            source,
            [],
            profile_core_sources=set(),
            health_snapshot={},
        )
        if "unclassified" in fields["discipline_keys"]:
            bad_sources.append(source.key)

    assert bad_sources == []


def test_field_specific_communications_sources_have_concrete_disciplines():
    records = {source.key: source for source in load_source_records()}

    assert source_quality_fields(records["nature_commschem"], [], profile_core_sources=set())["primary_discipline_key"] == "chemistry"
    assert source_quality_fields(records["nature_commsmed"], [], profile_core_sources=set())["primary_discipline_key"] == "medicine"
    assert source_quality_fields(records["nature_commsaicomp"], [], profile_core_sources=set())["primary_discipline_key"] == "computer_science"


def test_catalog_coverage_reports_discipline_runnable_health_and_policy():
    coverage = build_catalog_coverage()

    assert coverage["generated_from"] == "yaml_catalog"
    assert coverage["totals"]["source_count"] >= 800
    assert coverage["totals"]["runnable_source_count"] > 0
    assert "not auto-expanded" in coverage["general_policy"]
    assert any(
        item["key"] == "energy" and item["source_count"] > 0 and "source_kind_counts" in item
        for item in coverage["disciplines"]
    )
    assert any(item["key"] == "multidisciplinary" for item in coverage["disciplines"])

    markdown = format_catalog_coverage_markdown(coverage)
    assert "PaperLite 来源覆盖" in markdown
    assert "runnable" in markdown


def test_taxonomy_summary_exposes_stable_mapping_fields():
    summary = build_taxonomy_summary()

    assert "primary_discipline_key" in summary["maintenance_fields"]
    assert "category_keys" in summary["maintenance_fields"]
    assert "category_key" in summary["maintenance_fields"]
    assert any(item["key"] == "medicine" and item["label"] == "医学" for item in summary["disciplines"])
    assert any(item["key"] == "journal" and item["label"] == "期刊" for item in summary["source_kinds"])
    assert any(item["key"].endswith(".journal") and item["sources_url"].startswith("/sources?") for item in summary["categories"])

    markdown = format_taxonomy_markdown(summary)
    assert "PaperLite 分类映射" in markdown
    assert "primary_discipline_key" in markdown
