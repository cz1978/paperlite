from fastapi.testclient import TestClient

from paperlite import mcp_server
from paperlite.api import create_app
from paperlite.integrations import agent_manifest


def test_agent_manifest_declares_reserved_interfaces():
    manifest = agent_manifest("http://paperlite.local")

    assert manifest["name"] == "paperlite"
    assert manifest["version"] == "0.2.4"
    assert manifest["interfaces"]["reader"] == "http://paperlite.local/daily/cache?format=json"
    assert manifest["interfaces"]["human_ui"] == "http://paperlite.local/daily"
    assert manifest["interfaces"]["agent_default"]["mcp_tool"] == "paper_agent_context"
    assert manifest["interfaces"]["agent_default"]["rest"] == "http://paperlite.local/agent/context"
    assert "Return results in chat/tool output" in manifest["interfaces"]["agent_default"]["note"]
    result_policy = manifest["interfaces"]["agent_result_policy"]
    assert result_policy["list_all_until"] == 20
    assert "discipline" in result_policy["scope_fields"]
    assert "source_key_or_name" in result_policy["scope_fields"]
    assert "total_count" in result_policy["scope_fields"]
    assert "title" in result_policy["paper_fields"]
    assert "Do not replace the paper list with highlights" in result_policy["do_not"]
    assert manifest["interfaces"]["rest"]["daily"] == "http://paperlite.local/daily"
    assert manifest["interfaces"]["rest"]["daily_cache"] == "http://paperlite.local/daily/cache"
    assert manifest["interfaces"]["rest"]["daily_cache_json"] == "http://paperlite.local/daily/cache?format=json"
    assert manifest["interfaces"]["rest"]["daily_related"] == "http://paperlite.local/daily/related"
    assert manifest["interfaces"]["rest"]["daily_export"] == "http://paperlite.local/daily/export"
    assert manifest["interfaces"]["rest"]["daily_export_rss"] == "http://paperlite.local/daily/export?format=rss"
    assert manifest["interfaces"]["rest"]["daily_crawl"] == "http://paperlite.local/daily/crawl"
    assert manifest["interfaces"]["rest"]["daily_enrich"] == "http://paperlite.local/daily/enrich"
    assert manifest["interfaces"]["rest"]["agent_context"] == "http://paperlite.local/agent/context"
    assert manifest["interfaces"]["rest"]["agent_filter"] == "http://paperlite.local/agent/filter"
    assert manifest["interfaces"]["rest"]["agent_ask"] == "http://paperlite.local/agent/ask"
    assert manifest["interfaces"]["rest"]["agent_rag_index"] == "http://paperlite.local/agent/rag/index"
    assert manifest["interfaces"]["rest"]["agent_translation_profiles"] == "http://paperlite.local/agent/translation-profiles"
    assert manifest["interfaces"]["rest"]["zotero_items"] == "http://paperlite.local/zotero/items"
    assert manifest["interfaces"]["rest"]["ops"] == "http://paperlite.local/ops"
    assert manifest["interfaces"]["rest"]["ops_doctor"] == "http://paperlite.local/ops/doctor"
    assert manifest["interfaces"]["rest"]["endpoints"] == "http://paperlite.local/endpoints"
    assert manifest["interfaces"]["rest"]["catalog_coverage"] == "http://paperlite.local/catalog/coverage"
    assert manifest["interfaces"]["cli"]["catalog_validate"] == "python -m paperlite.cli catalog validate --format markdown"
    assert manifest["interfaces"]["cli"]["catalog_coverage"] == "python -m paperlite.cli catalog coverage --format markdown"
    assert manifest["interfaces"]["cli"]["doctor"] == "python -m paperlite.cli doctor --format markdown"
    assert manifest["interfaces"]["cli"]["rag_index"].startswith("python -m paperlite.cli rag index")
    assert manifest["interfaces"]["cli"]["rag_ask"].startswith("python -m paperlite.cli rag ask")
    assert "agent_rank" not in manifest["interfaces"]["rest"]
    assert "agent_digest" not in manifest["interfaces"]["rest"]
    assert "latest" not in manifest["interfaces"]["rest"]
    assert "search" not in manifest["interfaces"]["rest"]
    assert "daily_" + "json" not in manifest["interfaces"]["rest"]
    assert "daily_" + "rss" not in manifest["interfaces"]["rest"]
    assert "daily_source_radar" in manifest["capabilities"]
    assert "endpoint_catalog" in manifest["capabilities"]
    assert "sqlite_daily_cache" in manifest["capabilities"]
    assert "manual_discipline_crawl" in manifest["capabilities"]
    assert "catalog_coverage" in manifest["capabilities"]
    assert "doctor_diagnostics" in manifest["capabilities"]
    assert "host_agent_model_context" in manifest["capabilities"]
    assert "optional_llm_filter" in manifest["capabilities"]
    assert "metadata_rag" in manifest["capabilities"]
    assert "vector_cache_search" in manifest["capabilities"]
    assert "cached_related_papers" in manifest["capabilities"]
    assert "translation_profiles" in manifest["capabilities"]
    assert "zotero_metadata_import" in manifest["capabilities"]
    assert "paper_rank" not in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_latest" not in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_crawl" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_crawl_status" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_cache" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_agent_context" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_zotero_export" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_filter" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_ask" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_rag_index" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_translation_profiles" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_zotero_status" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_zotero_items" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_agent_manifest" in manifest["interfaces"]["mcp"]["tools"]
    assert "OpenClaw-style agents" in manifest["compatible_with"]
    assert "bridge" in manifest["non_goals"]

def test_agent_manifest_rest_endpoint():
    client = TestClient(create_app())

    response = client.get("/agent/manifest")

    assert response.status_code == 200
    assert response.json()["interfaces"]["rest"]["agent_translate"].endswith("/agent/translate")
    assert response.json()["interfaces"]["rest"]["agent_context"].endswith("/agent/context")
    assert response.json()["interfaces"]["rest"]["agent_translation_profiles"].endswith("/agent/translation-profiles")
    assert response.json()["interfaces"]["rest"]["agent_filter"].endswith("/agent/filter")
    assert response.json()["interfaces"]["rest"]["agent_ask"].endswith("/agent/ask")
    assert response.json()["interfaces"]["rest"]["agent_rag_index"].endswith("/agent/rag/index")


def test_well_known_manifest_endpoint():
    client = TestClient(create_app())

    response = client.get("/.well-known/paperlite.json")

    assert response.status_code == 200
    assert response.json()["capabilities"]


def test_mcp_agent_manifest_tool():
    manifest = mcp_server.paper_agent_manifest("http://paperlite.local")

    assert manifest["interfaces"]["mcp"]["command"] == "python -m paperlite.mcp_server"
    assert "Hermes-style agents" in manifest["compatible_with"]
    assert "paper_translate" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_crawl" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_cache" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_agent_context" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_zotero_export" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_translation_profiles" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_filter" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_ask" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_rag_index" in manifest["interfaces"]["mcp"]["tools"]
    assert "paper_zotero_items" in manifest["interfaces"]["mcp"]["tools"]
