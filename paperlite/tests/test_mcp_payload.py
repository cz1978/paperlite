from paperlite.models import Paper
from paperlite import mcp_server


def test_mcp_sources_returns_capabilities():
    result = mcp_server.paper_sources()

    assert result["count"] >= result["returned"] > 0
    assert len(result["sources"]) <= 50
    assert isinstance(result["truncated"], bool)

    openalex = mcp_server.paper_sources(q="openalex", limit=10)
    assert any(item["name"] == "openalex" and "enrich" in item["capabilities"] for item in openalex["sources"])


def test_mcp_sources_filters_and_limits_for_agents():
    result = mcp_server.paper_sources(discipline="energy", q="energy", latest=True, limit=5)

    assert result["returned"] <= 5
    assert result["filters"]["discipline"] == "energy"
    assert result["filters"]["latest"] is True
    assert result["filters"]["q"] == "energy"
    assert all(item["supports_latest"] is True for item in result["sources"])
    assert all("energy" in " ".join(str(value) for value in item.values()).lower() for item in result["sources"])


def test_mcp_enrich_returns_paper_dict(monkeypatch):
    paper = Paper(
        id="doi:10.1038/test",
        source="nature",
        source_type="journal",
        title="A paper",
        url="https://doi.org/10.1038/test",
        doi="10.1038/test",
    )
    enriched = paper.model_copy(update={"citation_count": 5}) if hasattr(paper, "model_copy") else paper.copy(update={"citation_count": 5})
    monkeypatch.setattr(mcp_server, "enrich_paper", lambda *args, **kwargs: enriched)

    result = mcp_server.paper_enrich(paper.to_dict(), sources="openalex")

    assert result["citation_count"] == 5


def test_mcp_agent_tools_return_json_serializable(monkeypatch):
    translate_call = {}
    payload = {
        "papers": [],
        "answer": "",
        "model": None,
        "configured": False,
        "warnings": ["llm_not_configured"],
    }
    def fake_translate(**kwargs):
        translate_call.update(kwargs)
        return payload

    monkeypatch.setattr(mcp_server, "run_paper_explain", lambda **kwargs: payload)
    monkeypatch.setattr(
        mcp_server,
        "run_paper_agent_context",
        lambda **kwargs: {"model_source": "agent_host", "action": kwargs["action"]},
    )
    monkeypatch.setattr(mcp_server, "run_translate_paper", fake_translate)
    monkeypatch.setattr(
        mcp_server,
        "run_list_translation_profiles",
        lambda: [{"key": "research_card_cn", "style": "brief"}],
    )
    monkeypatch.setattr(mcp_server, "run_filter_paper", lambda **kwargs: {"group": "recommend", "paper": kwargs["paper"]})
    monkeypatch.setattr(mcp_server, "run_paper_ask", lambda **kwargs: {"answer": "Answer [1].", "question": kwargs["question"]})
    monkeypatch.setattr(mcp_server, "run_paper_rag_index", lambda **kwargs: {"indexed": 1, "date_from": kwargs["date_value"]})
    monkeypatch.setattr(mcp_server, "run_create_daily_crawl", lambda **kwargs: {"run_id": "run-1", "status": "queued", "reused": False, **kwargs})
    monkeypatch.setattr(mcp_server, "run_daily_crawl", lambda run_id: None)
    monkeypatch.setattr(mcp_server, "get_crawl_run", lambda run_id: {"run_id": run_id, "status": "completed", "total_items": 2})
    monkeypatch.setattr(
        mcp_server,
        "daily_cache_payload",
        lambda **kwargs: {"groups": [], "total_items": 0, **kwargs},
    )
    monkeypatch.setattr(mcp_server, "get_relevant_preference_profile", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "record_preference_query", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "run_zotero_status", lambda: {"configured": True, "library_type": "user", "library_id": "1"})
    monkeypatch.setattr(
        mcp_server,
        "run_create_zotero_items",
        lambda papers: {"configured": True, "submitted": len(papers), "created": [{"paper_id": papers[0].id}], "failed": []},
    )

    paper = Paper(
        id="arxiv:1",
        source="arxiv",
        source_type="preprint",
        title="Paper",
        url="https://arxiv.org/abs/1",
    )

    assert mcp_server.paper_explain(paper.to_dict()) == payload
    assert mcp_server.paper_agent_context("explain", paper=paper.to_dict()) == {
        "model_source": "agent_host",
        "action": "explain",
    }
    assert mcp_server.paper_translate(paper.to_dict(), translation_profile="research_card_cn") == payload
    assert translate_call["style"] is None
    assert translate_call["translation_profile"] == "research_card_cn"
    assert mcp_server.paper_translation_profiles()["profiles"][0]["key"] == "research_card_cn"
    assert mcp_server.paper_filter(paper.to_dict(), query="useful")["group"] == "recommend"
    assert mcp_server.paper_ask("question?", date="2026-04-29")["answer"] == "Answer [1]."
    assert mcp_server.paper_rag_index(date="2026-04-29")["indexed"] == 1
    assert mcp_server.paper_crawl(discipline="energy", source="mdpi_energies", date="2026-04-29")["status"] == "completed"
    assert mcp_server.paper_crawl_status("run-1")["found"] is True
    assert mcp_server.paper_cache(date="2026-04-29", discipline="energy")["total_items"] == 0
    assert mcp_server.paper_cache(date_from="2026-04-30", date_to="2026-04-01")["status"] == "error"
    assert mcp_server.paper_zotero_status()["configured"] is True
    zotero_result = mcp_server.paper_zotero_items([paper.to_dict()])
    assert zotero_result["submitted"] == 1
    assert zotero_result["created"][0]["paper_id"] == "arxiv:1"


def test_mcp_zotero_items_returns_fallback_when_unconfigured(monkeypatch):
    paper = Paper(
        id="arxiv:1",
        source="arxiv",
        source_type="preprint",
        title="Paper",
        url="https://arxiv.org/abs/1",
    )
    monkeypatch.setattr(
        mcp_server,
        "run_create_zotero_items",
        lambda _papers: (_ for _ in ()).throw(mcp_server.ZoteroNotConfiguredError("missing zotero config")),
    )

    result = mcp_server.paper_zotero_items([paper.to_dict()])

    assert result["configured"] is False
    assert result["submitted"] == 1
    assert result["created"] == []
    assert result["fallback"] == "export RIS or BibTeX with /zotero/export"
