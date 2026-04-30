import re

import pytest

from paperlite.registry import clear_registry_cache, get_connector, get_enricher, list_sources
from paperlite.sources import (
    ENDPOINTS_ENV_VAR,
    SOURCES_ENV_VAR,
    clear_catalog_cache,
    endpoint_mode_counts,
    load_endpoint_configs,
    load_feed_source_configs,
    load_source_configs,
    load_source_records,
    list_endpoints,
)


def test_sources_yaml_loads_core_journals():
    configs = {config.key: config for config in load_source_configs()}

    assert configs["nature"].journal == "Nature"
    assert configs["science-advances"].publisher == "AAAS"
    assert configs["cell"].url.startswith("https://www.cell.com/")
    assert "medicine" in configs["nejm"].topics


def test_feed_configs_are_valid():
    configs = load_feed_source_configs()

    assert configs
    assert len(configs) >= 600
    assert {config.type for config in configs} >= {"journal", "preprint", "news", "working_papers"}
    assert all(config.key and config.journal and config.url for config in configs)


def test_source_and_endpoint_catalogs_are_split():
    sources = {source.key: source for source in load_source_records()}
    endpoints = {endpoint.key: endpoint for endpoint in load_endpoint_configs()}
    feed_configs = {config.endpoint_key: config for config in load_feed_source_configs()}

    assert sources["nature"].name == "Nature"
    assert sources["nature"].homepage is None
    assert "url" not in sources["nature"].raw
    assert endpoints["nature"].source_key == "nature"
    assert endpoints["nature"].mode == "rss"
    assert endpoints["nature"].url == "https://www.nature.com/nature.rss"
    assert endpoints["openalex"].mode == "api"
    assert endpoints["iop_erl"].url == "https://iopscience.iop.org/journal/rss/1748-9326"
    assert endpoints["jama"].url == "https://jamanetwork.com/rss/site_3/67.xml"
    assert endpoints["jama-network-open"].url == "https://jamanetwork.com/rss/site_214/187.xml"
    assert endpoints["lancet_langast"].url == "https://www.thelancet.com/rssfeed/langas_current.xml"
    assert endpoints["repec_nep_all"].url == "https://nep.repec.org/rss/nep-all.rss.xml"
    assert endpoints["repec_nep_mac"].url == "https://nep.repec.org/rss/nep-mac.rss.xml"
    assert endpoints["science_scisignal"].url == "http://stke.sciencemag.org/rss/current.xml"
    assert endpoints["science_scitranslmed"].url == "http://stm.sciencemag.org/rss/current.xml"
    assert sources["cellpress_trends_analytical_chemistry"].name == "TrAC Trends in Analytical Chemistry"
    assert sources["cellpress_trends_analytical_chemistry"].publisher == "Elsevier"
    assert endpoints["cellpress_trends_analytical_chemistry"].url == "https://rss.sciencedirect.com/publication/science/01659936"
    assert endpoints["bmj_bmj_surgery_interventions_health_technologies"].url == "https://sit.bmj.com/rss/current.xml"
    assert endpoints["cen_feedburner_latest"].url == "https://cen.acs.org/feeds/rss/latestnews.xml"
    assert endpoints["cellpress_trends_endocrinology_and_metabolism"].mode == "manual"
    assert endpoints["cellpress_trends_endocrinology_and_metabolism"].enabled is False
    assert endpoints["cellpress_trends_ecology_and_evolution"].mode == "manual"
    assert endpoints["cellpress_trends_ecology_and_evolution"].status == "candidate"
    assert endpoints["bmj_heart"].status == "temporarily_unavailable"
    assert endpoints["bmj_heart"].enabled is False
    assert endpoints["mdpi_sensors"].status == "temporarily_unavailable"
    assert endpoints["mdpi_sensors"].enabled is False
    assert endpoints["cell_reports"].status == "temporarily_unavailable"
    assert endpoints["cell_reports"].enabled is False
    assert endpoints["chemrxiv_all"].status == "temporarily_unavailable"
    assert endpoints["chemrxiv_all"].enabled is False
    assert endpoints["bmj_journal_of_investigative_medicine"].mode == "manual"
    assert endpoints["bmj_journal_of_investigative_medicine"].enabled is False
    assert endpoints["cen_environment"].mode == "manual"
    assert endpoints["cen_environment"].enabled is False
    assert endpoints["cen_jacs"].mode == "manual"
    assert endpoints["cen_jacs"].status == "candidate"
    assert "cellpress_trends_endocrinology_and_metabolism" not in feed_configs
    assert "cellpress_trends_ecology_and_evolution" not in feed_configs
    assert "bmj_heart" not in feed_configs
    assert "mdpi_sensors" not in feed_configs
    assert "cell_reports" not in feed_configs
    assert "chemrxiv_all" not in feed_configs
    assert "bmj_journal_of_investigative_medicine" not in feed_configs
    assert "cen_environment" not in feed_configs
    assert "cen_jacs" not in feed_configs
    assert len(list_endpoints()) >= 700
    rss_endpoints = list_endpoints(mode="rss")
    assert rss_endpoints
    assert all(item["mode"] == "rss" for item in rss_endpoints)
    counts = endpoint_mode_counts()
    assert counts["rss"] == len(rss_endpoints)
    with pytest.raises(ValueError, match="unknown endpoint mode"):
        list_endpoints(mode="bad")
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", source.key) for source in sources.values())
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", endpoint.key) for endpoint in endpoints.values())


def test_imported_source_catalog_is_exposed():
    configs = {config.key: config for config in load_source_configs()}

    assert configs["arxiv_cs_lg"].url == "https://rss.arxiv.org/rss/cs.LG"
    assert configs["biorxiv_all"].type == "preprint"
    assert configs["medrxiv_infectious_diseases"].publisher == "medRxiv"
    assert configs["science_express"].type == "journal"
    assert configs["lancet_laneur"].journal == "The Lancet Neurology"
    assert configs["bmj_the_bmj"].url == "http://feeds.bmj.com/bmj/recent"
    assert configs["sciencenet_hot_papers"].type == "news"
    assert configs["arxiv_cs_lg"].raw["origin"] == "catalog_csv_import"
    assert configs["mdpi_agriculture"].url == "https://www.mdpi.com/rss/journal/agriculture"
    assert configs["plos_plos_biology_newarticles"].url == "http://feeds.plos.org/plosbiology/NewArticles"
    assert configs["rsc_chem_science"].url == "http://feeds.rsc.org/rss/sc"
    assert configs["nature_nbt_current_feed"].url == "http://feeds.nature.com/nbt/rss/current"


def test_registry_exposes_connector_capabilities():
    sources = {item["name"]: item for item in list_sources()}

    assert len(sources) >= 700
    assert sources["openalex"]["connector_kind"] == "api"
    assert "enrich" in sources["openalex"]["capabilities"]
    assert sources["openalex"]["display_name"] == "OpenAlex"
    assert sources["openalex"]["group"] == "metadata"
    assert sources["openalex"]["search_mode"] == "metadata_enrich"
    assert sources["openalex"]["supports_search"] is True
    assert sources["openalex"]["supports_enrich"] is True
    assert sources["openalex"]["full_text_policy"] == "external_only"
    assert sources["nature"]["connector_kind"] == "feed"
    assert sources["nature"]["display_name"] == "Nature"
    assert sources["nature"]["group"] == "journal"
    assert sources["nature"]["search_mode"] == "recent_feed_filter"
    assert sources["nature"]["endpoint_count"] == 1
    assert sources["nature"]["access_modes"] == ["rss"]
    assert sources["nature"]["primary_endpoint"] == "nature"
    assert sources["nature"]["primary_discipline_key"] == "multidisciplinary"
    assert sources["nature"]["source_kind_key"] == "journal"
    assert sources["nature"]["category_key"] == "multidisciplinary.journal"
    assert "RSS" in sources["nature"]["limitations"][0]
    assert sources["arxiv"]["search_mode"] == "native_api"
    assert sources["arxiv"]["supports_pdf_link"] is True
    assert sources["arxiv"]["primary_discipline_key"] == "multidisciplinary"
    assert sources["arxiv_cs_lg"]["group"] == "preprint"
    assert sources["arxiv_cs_lg"]["category_key"] == "computer_science.preprint"
    assert sources["arxiv_cs_lg"]["search_mode"] == "recent_feed_filter"
    assert sources["sciencenet_hot_papers"]["group"] == "news"
    assert sources["chemrxiv"]["connector_kind"] == "api"
    assert "dump" not in sources
    assert get_connector("pubmed").name == "pubmed"
    assert get_enricher("crossref").name == "crossref"

    life_health = list_sources(area="life_health")
    assert life_health
    assert all("life_health" in source["area_keys"] for source in life_health)


def test_catalog_env_override_rebuilds_lazy_registry(tmp_path, monkeypatch):
    sources_path = tmp_path / "sources.yaml"
    endpoints_path = tmp_path / "endpoints.yaml"
    sources_path.write_text(
        """
sources:
- key: custom_journal
  name: Custom Journal
  source_kind: journal
  disciplines:
  - Chemistry
""".strip(),
        encoding="utf-8",
    )
    endpoints_path.write_text(
        """
endpoints:
- key: custom_journal
  source_key: custom_journal
  mode: rss
  url: https://example.com/custom.xml
  status: active
  timeout_seconds: 7.5
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(SOURCES_ENV_VAR, str(sources_path))
    monkeypatch.setenv(ENDPOINTS_ENV_VAR, str(endpoints_path))
    clear_catalog_cache()
    clear_registry_cache()

    records = {record.key: record for record in load_source_records()}
    endpoints = {endpoint.key: endpoint for endpoint in load_endpoint_configs()}
    configs = {config.key: config for config in load_source_configs()}
    connector = get_connector("custom_journal")

    assert list(records) == ["custom_journal"]
    assert endpoints["custom_journal"].url == "https://example.com/custom.xml"
    assert configs["custom_journal"].timeout_seconds == 7.5
    assert connector.feed_url == "https://example.com/custom.xml"
    assert connector.timeout_seconds == 7.5

    monkeypatch.delenv(SOURCES_ENV_VAR)
    monkeypatch.delenv(ENDPOINTS_ENV_VAR)
    clear_catalog_cache()
    clear_registry_cache()
