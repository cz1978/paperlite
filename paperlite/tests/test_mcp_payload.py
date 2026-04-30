from paperlite.models import Paper
from paperlite import mcp_server


def test_mcp_sources_returns_capabilities():
    result = mcp_server.paper_sources()

    assert any(item["name"] == "openalex" and "enrich" in item["capabilities"] for item in result)


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
    monkeypatch.setattr(mcp_server, "run_translate_paper", fake_translate)
    monkeypatch.setattr(
        mcp_server,
        "run_list_translation_profiles",
        lambda: [{"key": "research_card_cn", "style": "brief"}],
    )
    monkeypatch.setattr(mcp_server, "run_filter_paper", lambda **kwargs: {"group": "recommend", "paper": kwargs["paper"]})
    monkeypatch.setattr(mcp_server, "run_paper_ask", lambda **kwargs: {"answer": "Answer [1].", "question": kwargs["question"]})
    monkeypatch.setattr(mcp_server, "run_paper_rag_index", lambda **kwargs: {"indexed": 1, "date_from": kwargs["date_value"]})
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
    assert mcp_server.paper_translate(paper.to_dict(), translation_profile="research_card_cn") == payload
    assert translate_call["style"] is None
    assert translate_call["translation_profile"] == "research_card_cn"
    assert mcp_server.paper_translation_profiles()["profiles"][0]["key"] == "research_card_cn"
    assert mcp_server.paper_filter(paper.to_dict(), query="useful")["group"] == "recommend"
    assert mcp_server.paper_ask("question?", date="2026-04-29")["answer"] == "Answer [1]."
    assert mcp_server.paper_rag_index(date="2026-04-29")["indexed"] == 1
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
