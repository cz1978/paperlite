import json
from datetime import datetime

import pytest

import paperlite.agent as agent
import paperlite.ai_filter as ai_filter
import paperlite.llm as llm
import paperlite.translation as translation
import paperlite.translation_profiles as translation_profiles
from paperlite import storage
from paperlite.models import Paper


def make_paper():
    return Paper(
        id="arxiv:1",
        source="arxiv",
        source_type="preprint",
        title="A useful paper",
        abstract=(
            "This paper presents a compact evaluation setting for validating metadata translation, "
            "including a clear method description and enough context to support a brief summary."
        ),
        authors=["Ada Lovelace"],
        url="https://arxiv.org/abs/1",
        published_at=datetime(2024, 1, 2),
        categories=["cs.LG"],
    )


def make_material_paper(index: int = 1):
    return Paper(
        id=f"doi:10.1038/material-{index}",
        source="acs_chem_materials",
        source_type="journal",
        title=f"Useful materials paper {index}",
        abstract="A materials study with metadata enough for a one sentence summary.",
        authors=["Marie Curie"],
        url=f"https://doi.org/10.1038/material-{index}",
        doi=f"10.1038/material-{index}",
        published_at=datetime(2024, 1, 2),
        categories=["materials"],
        journal="Chemistry of Materials",
    )


def test_research_scope_resolves_chinese_topics():
    assert agent.resolve_research_scope(topic="材料")["discipline"] == "materials"
    assert agent.resolve_research_scope(topic="材料")["q"] is None
    assert agent.resolve_research_scope(topic="材料科学")["discipline"] == "materials"
    assert agent.resolve_research_scope(topic="纳米材料")["discipline"] == "materials"

    renewable = agent.resolve_research_scope(topic="今天关于新能源材料的文章", date_value="2024-01-02")

    assert renewable["discipline"] == "materials"
    assert renewable["q"] == "renewable energy"
    assert renewable["date_from"] == "2024-01-02"
    assert renewable["date_to"] == "2024-01-02"


def test_paper_research_uses_existing_cache_without_crawl(tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    run = storage.create_crawl_run(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="materials",
        source_keys=["acs_chem_materials"],
        limit_per_source=10,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2024-01-02",
        discipline_key="materials",
        source_key="acs_chem_materials",
        papers=[make_material_paper()],
        path=db_path,
    )

    result = agent.paper_research(
        topic="材料",
        date_value="2024-01-02",
        translate_brief=False,
        cache_path=db_path,
    )

    assert result["scope"]["discipline"] == "materials"
    assert result["cache"]["used_existing"] is True
    assert result["crawl"]["triggered"] is False
    assert result["total_count"] == 1
    assert result["papers"][0]["source"] == "acs_chem_materials"
    assert result["papers"][0]["summary_or_point"]


def test_paper_research_includes_default_brief_translation(monkeypatch):
    paper = make_material_paper()
    monkeypatch.setattr(agent, "daily_cache_export_papers", lambda **_kwargs: [paper])

    def fake_brief(paper_item, **kwargs):
        assert paper_item.id == paper.id
        assert kwargs["enabled"] is True
        assert kwargs["target_language"] == "zh-CN"
        return {
            "requested": True,
            "status": "ok",
            "target_language": "zh-CN",
            "style": "brief",
            "translation_profile": "research_card_cn",
            "configured": True,
            "title_zh": "材料论文中文题目",
            "cn_flash_180": "这篇研究材料结构和性能之间的关系。",
            "card_headline": "材料结构研究",
            "card_bullets": [],
            "card_tags": [],
            "translation": "标题：材料论文中文题目\n摘要：这篇研究材料结构和性能之间的关系。",
            "warnings": [],
            "cached": False,
        }

    monkeypatch.setattr(agent, "_research_brief_translation", fake_brief)

    result = agent.paper_research(topic="材料", date_value="2024-01-02", crawl_if_missing=False)

    item = result["papers"][0]
    assert item["short_title_zh"] == "材料论文中文题目"
    assert item["summary_or_point"] == "这篇研究材料结构和性能之间的关系。"
    assert item["brief_translation"]["translation_profile"] == "research_card_cn"
    assert result["translation"]["brief_requested"] is True
    assert result["translation"]["attempted_count"] == 1
    assert result["translation"]["translated_count"] == 1


def test_paper_research_scopes_unconfigured_brief_warning(monkeypatch):
    paper = make_material_paper()
    monkeypatch.setattr(agent, "daily_cache_export_papers", lambda **_kwargs: [paper])

    def fake_brief(*_args, **_kwargs):
        return {
            "requested": True,
            "status": "unconfigured",
            "target_language": "zh-CN",
            "style": "brief",
            "translation_profile": "research_card_cn",
            "configured": False,
            "title_zh": "",
            "cn_flash_180": "",
            "card_headline": "",
            "card_bullets": [],
            "card_tags": [],
            "translation": "",
            "warnings": ["llm_not_configured"],
            "cached": False,
        }

    monkeypatch.setattr(agent, "_research_brief_translation", fake_brief)

    result = agent.paper_research(topic="材料", date_value="2024-01-02", crawl_if_missing=False)

    assert result["warnings"] == []
    assert result["translation"]["warnings"] == ["llm_not_configured"]
    assert result["papers"][0]["brief_translation"]["status"] == "unconfigured"
    assert "host model" in result["result_contract"]["host_agent_rendering"]


def test_paper_research_crawls_when_scope_cache_missing(monkeypatch):
    calls = {"exports": 0, "created": None, "ran": None}
    paper = make_material_paper()

    def fake_export(**kwargs):
        calls["exports"] += 1
        assert kwargs["discipline"] == "materials"
        return [] if calls["exports"] == 1 else [paper]

    def fake_create(**kwargs):
        calls["created"] = kwargs
        return {"run_id": "run-1", "status": "queued", "reused": False, "source_keys": kwargs["source"]}

    def fake_run(run_id, **kwargs):
        calls["ran"] = {"run_id": run_id, **kwargs}

    monkeypatch.setattr(agent, "daily_cache_export_papers", fake_export)
    monkeypatch.setattr(agent, "create_daily_crawl", fake_create)
    monkeypatch.setattr(agent, "run_daily_crawl", fake_run)
    monkeypatch.setattr(
        agent,
        "get_crawl_run",
        lambda run_id, **_kwargs: {"run_id": run_id, "status": "completed", "total_items": 1, "warnings": []},
    )

    result = agent.paper_research(topic="材料", date_value="2024-01-02", translate_brief=False)

    assert result["crawl"]["triggered"] is True
    assert calls["created"]["discipline"] == "materials"
    assert calls["created"]["source"]
    assert calls["ran"]["run_id"] == "run-1"
    assert result["total_count"] == 1


def test_paper_research_surfaces_empty_crawl_warnings(monkeypatch):
    monkeypatch.setattr(agent, "daily_cache_export_papers", lambda **_kwargs: [])
    monkeypatch.setattr(
        agent,
        "create_daily_crawl",
        lambda **kwargs: {"run_id": "run-empty", "status": "queued", "reused": False, "source_keys": kwargs["source"]},
    )
    monkeypatch.setattr(agent, "run_daily_crawl", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        agent,
        "get_crawl_run",
        lambda run_id, **_kwargs: {
            "run_id": run_id,
            "status": "completed",
            "total_items": 0,
            "warnings": ["no_items_matched_date_range"],
            "source_results": [
                {
                    "source_key": "acs_chem_materials",
                    "endpoint_key": "acs_chem_materials",
                    "warnings": ["empty_feed_window"],
                    "error": None,
                }
            ],
        },
    )

    result = agent.paper_research(topic="材料", date_value="2024-01-02", translate_brief=False)

    assert result["crawl"]["triggered"] is True
    assert result["total_count"] == 0
    assert "no_items_matched_date_range" in result["warnings"]
    assert "research_no_cached_papers" in result["warnings"]
    assert result["crawl"]["source_warnings"][0]["source"] == "acs_chem_materials"
    assert "Mention crawl/source warnings" in result["next_actions"][1]


def test_paper_research_caps_overflow(monkeypatch):
    papers = [make_material_paper(index) for index in range(1, 17)]
    monkeypatch.setattr(agent, "daily_cache_export_papers", lambda **_kwargs: papers)

    result = agent.paper_research(
        topic="材料",
        date_value="2024-01-02",
        crawl_if_missing=False,
        translate_brief=False,
    )

    assert result["returned_count"] == 15
    assert result["total_count"] == 16
    assert result["remaining_count"] == 1
    assert result["overflow"]["has_more"] is True
    assert "AI-rank" in result["overflow"]["message"]


def test_llm_unconfigured_returns_stable_shape(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_MODEL", raising=False)

    result = llm.complete_chat([{"role": "user", "content": "hello"}])

    assert result["configured"] is False
    assert result["answer"] == ""
    assert result["warnings"] == ["llm_not_configured"]


def test_embedding_unconfigured_returns_stable_shape(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PAPERLITE_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERLITE_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_EMBEDDING_MODEL", raising=False)

    result = llm.create_embeddings(["hello"])

    assert result["configured"] is False
    assert result["embeddings"] == []
    assert result["warnings"] == ["embedding_not_configured"]


def test_llm_mock_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Digest text."}}]}

    calls = {}

    def fake_post(url, headers, json, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("PAPERLITE_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("PAPERLITE_LLM_API_KEY", "secret")
    monkeypatch.setenv("PAPERLITE_LLM_MODEL", "hermes-test")
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    result = llm.complete_chat([{"role": "user", "content": "hello"}])

    assert result["configured"] is True
    assert result["model"] == "hermes-test"
    assert result["answer"] == "Digest text."
    assert calls["url"] == "http://llm.local/v1/chat/completions"
    assert calls["headers"]["Authorization"] == "Bearer secret"


def test_embedding_mock_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "model": "mock-embed",
                "data": [
                    {"index": 1, "embedding": [0, 1]},
                    {"index": 0, "embedding": [1, 0]},
                ],
            }

    calls = {}

    def fake_post(url, headers, json, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("PAPERLITE_EMBEDDING_BASE_URL", "http://embed.local/v1")
    monkeypatch.setenv("PAPERLITE_EMBEDDING_API_KEY", "secret")
    monkeypatch.setenv("PAPERLITE_EMBEDDING_MODEL", "embed-model")
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    result = llm.create_embeddings(["first", "second"])

    assert result["configured"] is True
    assert result["model"] == "mock-embed"
    assert result["embeddings"] == [[1.0, 0.0], [0.0, 1.0]]
    assert calls["url"] == "http://embed.local/v1/embeddings"
    assert calls["headers"]["Authorization"] == "Bearer secret"
    assert calls["json"]["input"] == ["first", "second"]


def test_llm_http_error_is_not_swallowed(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            request = llm.httpx.Request("POST", "http://llm.local/v1/chat/completions")
            response = llm.httpx.Response(429, request=request)
            raise llm.httpx.HTTPStatusError("too many requests", request=request, response=response)

        def json(self):
            return {}

    monkeypatch.setenv("PAPERLITE_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("PAPERLITE_LLM_MODEL", "hermes-test")
    monkeypatch.setattr(llm.httpx, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(llm.LLMRequestError) as exc_info:
        llm.complete_chat([{"role": "user", "content": "hello"}])

    assert exc_info.value.api_status_code == 429
    assert exc_info.value.provider_status_code == 429
    assert exc_info.value.retryable is True


def test_agent_explain_uses_mock_llm(monkeypatch):
    monkeypatch.setattr(agent, "complete_chat", lambda _messages: {
        "configured": True,
        "model": "mock",
        "answer": "Agent answer.",
        "warnings": [],
    })

    explain = agent.paper_explain(make_paper().to_dict())

    assert explain["answer"] == "Agent answer."
    assert explain["papers"][0]["id"] == "arxiv:1"


def test_paper_agent_context_uses_host_model_without_llm(monkeypatch, tmp_path):
    def fail_complete(*_args, **_kwargs):
        raise AssertionError("paper_agent_context must not call PaperLite LLM")

    monkeypatch.setattr(agent, "complete_chat", fail_complete)
    explain = agent.paper_agent_context(action="explain", paper=make_paper().to_dict(), question="Why read it?")

    assert explain["model_source"] == "agent_host"
    assert explain["paperlite_llm_used"] is False
    assert explain["action"] == "explain"
    assert explain["papers"][0]["id"] == "arxiv:1"
    assert "Why read it?" in explain["messages"][1]["content"]
    assert "brief_abstract_or_summary" in explain["result_contract"]["paper_fields"]

    db_path = tmp_path / "paperlite.sqlite3"
    rag = make_paper()
    rag.id = "arxiv:rag"
    rag.title = "RAG agent benchmark"
    rag.abstract = "Retrieval augmented generation benchmark with agent evaluation."
    run = storage.create_crawl_run(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        source_keys=["arxiv"],
        limit_per_source=10,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2024-01-02",
        discipline_key="computer_science",
        source_key="arxiv",
        papers=[rag],
        path=db_path,
    )

    ask = agent.paper_agent_context(
        action="ask",
        question="Which RAG paper should I read?",
        date_value="2024-01-02",
        discipline="computer_science",
        q="RAG",
        cache_path=db_path,
    )

    assert ask["model_source"] == "agent_host"
    assert ask["retrieval"]["q"] == "RAG"
    assert ask["retrieval"]["semantic_search"] is False
    assert ask["retrieval"]["candidates"] == 1
    assert ask["papers"][0]["id"] == "arxiv:rag"
    assert "RAG agent benchmark" in ask["messages"][1]["content"]
    assert "one-sentence Chinese abstract/summary" in ask["result_contract"]["brief_translation_default"]
    assert "agent_host_model_required" in ask["warnings"]


def test_paper_ask_uses_indexed_metadata_only(monkeypatch, tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    rag = make_paper()
    rag.id = "arxiv:rag"
    rag.title = "RAG agent benchmark"
    rag.abstract = "Retrieval augmented generation benchmark with agent evaluation."
    rag.doi = "10.1234/rag"
    other = make_paper()
    other.id = "arxiv:protein"
    other.title = "Protein folding assay"
    other.abstract = "A biology assay unrelated to retrieval systems."
    other.doi = "10.1234/protein"
    run = storage.create_crawl_run(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        source_keys=["arxiv"],
        limit_per_source=10,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2024-01-02",
        discipline_key="computer_science",
        source_key="arxiv",
        papers=[rag, other],
        path=db_path,
    )
    cached = storage.daily_cache_papers_for_rag(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        path=db_path,
    )
    rag = next(paper for paper in cached if paper.id == "arxiv:rag")
    other = next(paper for paper in cached if paper.id == "arxiv:protein")
    storage.upsert_paper_embedding(
        paper_id=rag.id,
        content_hash=storage.paper_embedding_hash(rag),
        embedding_model="mock-embed",
        embedding=[1.0, 0.0],
        path=db_path,
    )
    storage.upsert_paper_embedding(
        paper_id=other.id,
        content_hash=storage.paper_embedding_hash(other),
        embedding_model="mock-embed",
        embedding=[0.0, 1.0],
        path=db_path,
    )
    calls = []
    monkeypatch.setattr(
        agent,
        "create_embeddings",
        lambda inputs: {
            "configured": True,
            "model": "mock-embed",
            "embeddings": [[1.0, 0.0] for _item in inputs],
            "warnings": [],
        },
    )

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {"configured": True, "model": "mock-chat", "answer": "Use the RAG paper [1].", "warnings": []}

    monkeypatch.setattr(agent, "complete_chat", fake_complete)

    result = agent.paper_ask(
        question="Which RAG agent benchmark is relevant?",
        date_value="2024-01-02",
        discipline="computer_science",
        q="RAG",
        top_k=1,
        cache_path=db_path,
    )

    assert result["configured"] is True
    assert result["embedding_model"] == "mock-embed"
    assert result["citations"][0]["paper"]["id"] == "arxiv:rag"
    assert result["citations"][0]["index"] == 1
    assert result["retrieval"]["q"] == "RAG"
    assert result["retrieval"]["candidates"] == 1
    assert result["retrieval"]["matches"] == 1
    prompt = calls[0]["messages"][1]["content"]
    assert "RAG agent benchmark" in prompt
    assert "Protein folding assay" not in prompt
    assert "Do not infer from PDFs or full text" in calls[0]["messages"][0]["content"]


def test_paper_rag_index_uses_embedding_cache(monkeypatch, tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    paper = make_paper()
    other = make_paper()
    other.id = "arxiv:protein"
    other.title = "Protein folding assay"
    other.abstract = "Biology assay metadata outside the requested topic."
    run = storage.create_crawl_run(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        source_keys=["arxiv"],
        limit_per_source=10,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2024-01-02",
        discipline_key="computer_science",
        source_key="arxiv",
        papers=[paper, other],
        path=db_path,
    )
    calls = []

    def fake_embeddings(inputs):
        calls.append(inputs)
        return {
            "configured": True,
            "model": "mock-embed",
            "embeddings": [[1.0, 0.0] for _item in inputs],
            "warnings": [],
        }

    monkeypatch.setattr(agent, "create_embeddings", fake_embeddings)
    monkeypatch.setattr(
        agent,
        "embedding_status",
        lambda: {"configured": True, "model": "mock-embed", "base_url": "http://embed.local/v1"},
    )

    first = agent.paper_rag_index(
        date_value="2024-01-02",
        discipline="computer_science",
        q="useful",
        cache_path=db_path,
    )
    second = agent.paper_rag_index(
        date_value="2024-01-02",
        discipline="computer_science",
        q="useful",
        cache_path=db_path,
    )

    assert first["q"] == "useful"
    assert first["candidates"] == 1
    assert first["indexed"] == 1
    assert first["skipped"] == 0
    assert second["q"] == "useful"
    assert second["candidates"] == 1
    assert second["indexed"] == 0
    assert second["skipped"] == 1
    assert len(calls) == 1


def test_paper_related_auto_fills_embeddings_and_excludes_target(monkeypatch, tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    target = make_paper()
    target.id = "arxiv:target"
    target.title = "RAG agent planning"
    target.abstract = "Retrieval augmented generation agents with planning and memory."
    similar = make_paper()
    similar.id = "arxiv:similar"
    similar.title = "RAG agent memory"
    similar.abstract = "Retrieval augmented generation memory for useful agents."
    other = make_paper()
    other.id = "arxiv:protein"
    other.title = "Protein folding assay"
    other.abstract = "Biology experiments about protein folding assays."
    run = storage.create_crawl_run(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        source_keys=["arxiv"],
        limit_per_source=10,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2024-01-02",
        discipline_key="computer_science",
        source_key="arxiv",
        papers=[target, similar, other],
        path=db_path,
    )
    cached = storage.daily_cache_papers_for_rag(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        path=db_path,
    )
    by_id = {paper.id: paper for paper in cached}
    storage.upsert_paper_embedding(
        paper_id="arxiv:target",
        content_hash=storage.paper_embedding_hash(by_id["arxiv:target"]),
        embedding_model="mock-embed",
        embedding=[1.0, 0.0],
        path=db_path,
    )
    storage.upsert_paper_embedding(
        paper_id="arxiv:similar",
        content_hash="stale-hash",
        embedding_model="mock-embed",
        embedding=[0.0, 1.0],
        path=db_path,
    )
    calls = []

    def fake_embeddings(inputs):
        calls.append(inputs)
        vectors = []
        for text in inputs:
            if "RAG agent memory" in text:
                vectors.append([0.95, 0.05])
            elif "Protein folding assay" in text:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([1.0, 0.0])
        return {"configured": True, "model": "mock-embed", "embeddings": vectors, "warnings": []}

    monkeypatch.setattr(agent, "create_embeddings", fake_embeddings)
    monkeypatch.setattr(
        agent,
        "embedding_status",
        lambda: {"configured": True, "model": "mock-embed", "base_url": "http://embed.local/v1"},
    )

    result = agent.paper_related(
        paper_id="arxiv:target",
        date_value="2024-01-02",
        discipline="computer_science",
        q="RAG",
        top_k=5,
        cache_path=db_path,
    )

    assert result["configured"] is True
    assert result["paper_id"] == "arxiv:target"
    assert result["retrieval"]["q"] == "RAG"
    assert result["retrieval"]["candidates"] == 2
    assert result["retrieval"]["indexed"] == 2
    assert result["retrieval"]["refreshed"] == 1
    assert result["retrieval"]["stale"] == 1
    assert [item["paper"]["id"] for item in result["related"]] == ["arxiv:similar"]
    assert all(item["paper"]["id"] != "arxiv:target" for item in result["related"])
    assert len(calls) == 1
    assert len(calls[0]) == 1
    refreshed = storage.get_paper_embedding("arxiv:similar", path=db_path)
    assert refreshed["content_hash"] == storage.paper_embedding_hash(by_id["arxiv:similar"])
    assert storage.get_paper_embedding("arxiv:protein", path=db_path) is None


def test_paper_related_returns_warnings_for_unconfigured_and_missing_target(monkeypatch, tmp_path):
    db_path = tmp_path / "paperlite.sqlite3"
    paper = make_paper()
    run = storage.create_crawl_run(
        date_from="2024-01-02",
        date_to="2024-01-02",
        discipline_key="computer_science",
        source_keys=["arxiv"],
        limit_per_source=10,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2024-01-02",
        discipline_key="computer_science",
        source_key="arxiv",
        papers=[paper],
        path=db_path,
    )
    monkeypatch.setattr(
        agent,
        "embedding_status",
        lambda: {"configured": False, "model": None, "base_url": None},
    )

    unconfigured = agent.paper_related(
        paper_id=paper.id,
        date_value="2024-01-02",
        discipline="computer_science",
        cache_path=db_path,
    )
    missing = agent.paper_related(
        paper_id="missing",
        date_value="2024-01-02",
        discipline="computer_science",
        cache_path=db_path,
    )

    assert unconfigured["configured"] is False
    assert unconfigured["warnings"] == ["embedding_not_configured"]
    assert missing["warnings"] == ["related_target_not_in_cache_scope"]


def test_ai_filter_groups_paper_with_importance(monkeypatch):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-filter",
            "answer": json.dumps(
                {
                    "group": "recommend",
                    "importance": 86,
                    "quality_score": 82,
                    "preference_score": 91,
                    "noise_tags": [],
                    "matched_preferences": ["metadata translation"],
                    "quality_reasons": ["方法描述清晰", "摘要信息充分"],
                    "reason": "主题和筛选要求高度相关",
                    "confidence": 0.82,
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        }

    monkeypatch.setattr(ai_filter, "complete_chat", fake_complete)

    result = ai_filter.filter_paper(make_paper(), "metadata translation")

    assert result["configured"] is True
    assert result["group"] == "recommend"
    assert result["importance"] == 86
    assert result["quality_score"] == 82
    assert result["preference_score"] == 91
    assert result["noise_tags"] == []
    assert result["matched_preferences"] == ["metadata translation"]
    assert result["quality_reasons"] == ["方法描述清晰", "摘要信息充分"]
    assert result["include"] is True
    assert result["reason"] == "主题和筛选要求高度相关"
    assert result["confidence"] == 0.82
    assert result["profile_used"] is False
    assert "公用默认标准" in result["effective_query"]
    assert "推荐分组" in calls[0]["messages"][0]["content"]
    assert "quality_score" in calls[0]["messages"][0]["content"]
    assert "noise_tags" in calls[0]["messages"][0]["content"]
    assert "筛选要求：metadata translation" in calls[0]["messages"][1]["content"]
    assert "公用默认标准" in calls[0]["messages"][1]["content"]
    assert calls[0]["kwargs"]["temperature"] == 0.1


def test_ai_filter_injects_preference_profile(monkeypatch):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-filter",
            "answer": json.dumps(
                {
                    "group": "recommend",
                    "importance": 88,
                    "reason": "符合个人长期偏好",
                    "confidence": 0.8,
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        }

    monkeypatch.setattr(ai_filter, "complete_chat", fake_complete)
    profile = {
        "profile": {
            "summary": "长期提示词：Prefer RAG agents",
            "manual_prompts": ["Prefer RAG agents"],
            "recent_queries": [{"text": "agent benchmark", "use_count": 2}],
            "positive_terms": [{"term": "rag", "weight": 8}, {"term": "agent", "weight": 8}],
            "negative_terms": [{"term": "announcement", "weight": 5}],
        }
    }

    result = ai_filter.filter_paper(make_paper(), "metadata translation", preference_profile=profile)

    assert result["profile_used"] is True
    assert result["profile_summary"] == "长期提示词：Prefer RAG agents"
    assert "个人偏好画像" in calls[0]["messages"][1]["content"]
    assert "Prefer RAG agents" in calls[0]["messages"][1]["content"]
    assert "agent benchmark" in calls[0]["messages"][1]["content"]
    assert "announcement" in calls[0]["messages"][1]["content"]


def test_ai_filter_uses_default_criteria_when_query_empty(monkeypatch):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-filter",
            "answer": json.dumps(
                {
                    "group": "maybe",
                    "importance": 55,
                    "reason": "默认标准下需要人工再看",
                    "confidence": 0.64,
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        }

    monkeypatch.setattr(ai_filter, "complete_chat", fake_complete)

    result = ai_filter.filter_paper(make_paper(), "")

    assert result["query"] == ai_filter.DEFAULT_AI_FILTER_QUERY
    assert result["group"] == "maybe"
    assert result["importance"] == 55
    assert "默认学术价值筛选" in calls[0]["messages"][1]["content"]


def test_ai_filter_defaults_new_fields_when_llm_omits_them(monkeypatch):
    monkeypatch.setattr(
        ai_filter,
        "complete_chat",
        lambda *_args, **_kwargs: {
            "configured": True,
            "model": "mock-filter",
            "answer": json.dumps(
                {
                    "group": "maybe",
                    "importance": 62,
                    "reason": "字段缺省也可解析",
                    "confidence": 0.4,
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        },
    )

    result = ai_filter.filter_paper(make_paper(), "metadata translation")

    assert result["group"] == "maybe"
    assert result["quality_score"] == 62
    assert result["preference_score"] == 50
    assert result["noise_tags"] == []
    assert result["matched_preferences"] == []
    assert result["quality_reasons"] == []


def test_ai_filter_noise_tags_are_whitelisted(monkeypatch):
    monkeypatch.setattr(
        ai_filter,
        "complete_chat",
        lambda *_args, **_kwargs: {
            "configured": True,
            "model": "mock-filter",
            "answer": json.dumps(
                {
                    "group": "reject",
                    "importance": 20,
                    "quality_score": 25,
                    "preference_score": 30,
                    "noise_tags": ["spam", "marketing", "weak_metadata", "marketing"],
                    "reason": "像营销材料且摘要不足",
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        },
    )

    result = ai_filter.filter_paper(make_paper(), "metadata translation")

    assert result["noise_tags"] == ["marketing", "weak_metadata"]
    assert set(result["noise_tags"]) <= ai_filter.NOISE_TAGS


def test_ai_filter_low_quality_high_preference_cannot_recommend(monkeypatch):
    monkeypatch.setattr(
        ai_filter,
        "complete_chat",
        lambda *_args, **_kwargs: {
            "configured": True,
            "model": "mock-filter",
            "answer": json.dumps(
                {
                    "group": "recommend",
                    "importance": 95,
                    "quality_score": 34,
                    "preference_score": 96,
                    "noise_tags": ["low_method_detail"],
                    "matched_preferences": ["RAG"],
                    "quality_reasons": ["主题相关但方法信息不足"],
                    "reason": "偏好很强但质量证据弱",
                    "confidence": 0.75,
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        },
    )

    result = ai_filter.filter_paper(make_paper(), "RAG")

    assert result["group"] == "reject"
    assert result["include"] is False
    assert result["quality_score"] == 34
    assert result["preference_score"] == 96


def test_ai_filter_unconfigured_keeps_stable_shape(monkeypatch):
    monkeypatch.setattr(
        ai_filter,
        "complete_chat",
        lambda *_args, **_kwargs: {
            "configured": False,
            "model": None,
            "answer": "",
            "warnings": ["llm_not_configured"],
        },
    )

    result = ai_filter.filter_paper(make_paper(), "clinical")

    assert result["configured"] is False
    assert result["group"] == "maybe"
    assert result["importance"] == 50
    assert result["quality_score"] == 50
    assert result["preference_score"] == 50
    assert result["noise_tags"] == []
    assert result["matched_preferences"] == []
    assert result["quality_reasons"] == []
    assert result["include"] is True
    assert result["warnings"] == ["llm_not_configured"]


def test_translate_paper_uses_optional_llm(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        if len(calls) == 1:
            return {
                "configured": True,
                "model": "mock-translator",
                "answer": "一篇有用的论文",
                "warnings": [],
            }
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": json.dumps(
                {
                    "cn_flash_180": "本文介绍一篇有用论文；摘要称其包含简短摘要。",
                    "card_headline": "有用论文",
                    "card_bullets": [{"label": "结论", "text": "论文主题清晰，信息来自摘要。"}],
                    "card_tags": ["#useful", "#paper", "#Abstract"],
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)

    cache_path = tmp_path / "paperlite.sqlite3"
    result = translation.translate_paper(make_paper(), target_language="zh-CN", cache_path=cache_path)

    assert result["configured"] is True
    assert result["model"] == "mock-translator"
    assert result["style"] == "brief"
    assert result["translation_profile"] == "research_card_cn"
    assert result["translation_profile_version"] == "research_card_cn_v1"
    assert result["translation_profile_hash"]
    assert result["title_zh"] == "一篇有用的论文"
    assert result["cn_flash_180"] == "本文介绍一篇有用论文；摘要称其包含简短摘要。"
    assert result["card_headline"] == "有用论文"
    assert result["card_bullets"] == [{"label": "结论", "text": "论文主题清晰，信息来自摘要。"}]
    assert result["card_tags"] == ["#useful", "#paper", "#Abstract"]
    assert result["translation"] == "标题：一篇有用的论文\n摘要：本文介绍一篇有用论文；摘要称其包含简短摘要。"
    assert result["paper"]["id"] == "arxiv:1"
    assert result["cached"] is False
    assert len(calls) == 2
    assert "学术翻译助手" in calls[0]["messages"][0]["content"]
    assert calls[0]["messages"][1]["content"] == "A useful paper"
    assert "科研快讯编辑" in calls[1]["messages"][0]["content"]
    assert "输出严格单个 JSON 对象" in calls[1]["messages"][0]["content"]
    brief_input = json.loads(calls[1]["messages"][1]["content"])
    assert brief_input == {
        "title": "A useful paper",
        "abstract": (
            "This paper presents a compact evaluation setting for validating metadata translation, "
            "including a clear method description and enough context to support a brief summary."
        ),
        "source_type": "preprint",
        "categories": ["cs.LG"],
        "authors": "Ada Lovelace",
        "id": "arxiv:1",
    }
    assert calls[0]["kwargs"]["temperature"] == 0.1
    assert calls[0]["kwargs"]["max_tokens"] == 120
    assert calls[1]["kwargs"]["temperature"] == 0.1
    assert calls[1]["kwargs"]["max_tokens"] == 1200

    calls.clear()
    cached = translation.translate_paper(make_paper(), target_language="zh-CN", cache_path=cache_path)

    assert calls == []
    assert cached["cached"] is True
    assert cached["translation_profile"] == "research_card_cn"
    assert cached["title_zh"] == "一篇有用的论文"
    assert cached["cn_flash_180"] == "本文介绍一篇有用论文；摘要称其包含简短摘要。"


def test_translate_paper_detail_style_directly_translates_abstract(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": "本文提出了一个紧凑的评估设置，用于验证元数据翻译。",
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)
    cache_path = tmp_path / "paperlite.sqlite3"

    result = translation.translate_paper(make_paper(), target_language="zh-CN", style="detail", cache_path=cache_path)

    assert len(calls) == 1
    assert "直译" in calls[0]["messages"][0]["content"]
    assert "可读" in calls[0]["messages"][0]["content"]
    assert "LaTeX" in calls[0]["messages"][0]["content"]
    assert "Announce Type" in calls[0]["messages"][0]["content"]
    assert "科研快讯编辑" not in calls[0]["messages"][0]["content"]
    assert calls[0]["messages"][1]["content"] == make_paper().abstract
    assert calls[0]["kwargs"]["temperature"] == 0.1
    assert calls[0]["kwargs"]["max_tokens"] == 1600
    assert result["style"] == "detail"
    assert result["translation_profile"] == "detail_cn"
    assert result["detail_translation"] == "本文提出了一个紧凑的评估设置，用于验证元数据翻译。"
    assert result["translation"] == "本文提出了一个紧凑的评估设置，用于验证元数据翻译。"
    assert result["cn_flash_180"] == ""
    assert result["card_bullets"] == []
    assert result["detail_skipped"] is False
    assert result["cached"] is False

    calls.clear()
    cached = translation.translate_paper(make_paper(), target_language="zh-CN", style="detail", cache_path=cache_path)

    assert calls == []
    assert cached["cached"] is True
    assert cached["translation_profile"] == "detail_cn"
    assert cached["detail_translation"] == "本文提出了一个紧凑的评估设置，用于验证元数据翻译。"


def test_translation_profiles_load_defaults_and_reject_invalid(tmp_path):
    profiles = translation_profiles.list_translation_profiles()

    keys = {profile["key"] for profile in profiles}
    assert {"research_card_cn", "detail_cn"} <= keys
    assert next(profile for profile in profiles if profile["key"] == "research_card_cn")["style"] == "brief"

    bad_path = tmp_path / "translation_profiles.yaml"
    bad_path.write_text(
        "profiles:\n"
        "  - key: broken\n"
        "    label: Broken\n"
        "    target_language: zh-CN\n"
        "    style: brief\n"
        "    version: v1\n"
        "    max_tokens: 100\n"
        "    body_prompt: Body only\n"
        "    output_schema: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing title_prompt"):
        translation_profiles.load_translation_profiles(bad_path)


def test_translate_paper_cache_key_includes_translation_profile_hash(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        if len(calls) % 2 == 1:
            return {"configured": True, "model": "mock-translator", "answer": "一篇有用的论文", "warnings": []}
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": json.dumps(
                {
                    "cn_flash_180": "本文介绍一篇有用论文。",
                    "card_headline": "有用论文",
                    "card_bullets": [{"label": "结论", "text": "论文主题清晰。"}],
                    "card_tags": ["#useful"],
                },
                ensure_ascii=False,
            ),
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)
    cache_path = tmp_path / "paperlite.sqlite3"

    first = translation.translate_paper(
        make_paper(),
        target_language="zh-CN",
        translation_profile="research_card_cn",
        cache_path=cache_path,
    )
    assert len(calls) == 2

    custom_path = tmp_path / "translation_profiles.yaml"
    custom_path.write_text(
        "profiles:\n"
        "  - key: research_card_cn\n"
        "    label: Custom card\n"
        "    target_language: zh-CN\n"
        "    style: brief\n"
        "    version: research_card_cn_v2\n"
        "    max_tokens: 777\n"
        "    title_prompt: 自定义标题提示词\n"
        "    body_prompt: 自定义科研卡片提示词\n"
        "    output_schema:\n"
        "      type: object\n"
        "  - key: detail_cn\n"
        "    label: Detail\n"
        "    target_language: zh-CN\n"
        "    style: detail\n"
        "    version: detail_v1\n"
        "    max_tokens: 1600\n"
        "    title_prompt: ''\n"
        "    body_prompt: 详情提示词\n"
        "    output_schema:\n"
        "      type: string\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERLITE_TRANSLATION_PROFILES_PATH", str(custom_path))

    second = translation.translate_paper(
        make_paper(),
        target_language="zh-CN",
        translation_profile="research_card_cn",
        cache_path=cache_path,
    )

    assert len(calls) == 4
    assert first["translation_profile_hash"] != second["translation_profile_hash"]
    assert second["translation_profile_version"] == "research_card_cn_v2"
    assert calls[2]["messages"][0]["content"] == "自定义标题提示词"
    assert calls[3]["messages"][0]["content"] == "自定义科研卡片提示词"
    assert calls[3]["kwargs"]["max_tokens"] == 777


def test_translate_paper_unconfigured_keeps_original_metadata_only(monkeypatch, tmp_path):
    monkeypatch.setattr(
        translation,
        "complete_chat",
        lambda *args, **kwargs: {
            "configured": False,
            "model": None,
            "answer": "",
            "warnings": ["llm_not_configured"],
        },
    )

    result = translation.translate_paper(make_paper(), target_language="zh-CN", cache_path=tmp_path / "paperlite.sqlite3")

    assert result["configured"] is False
    assert result["warnings"] == ["llm_not_configured"]
    assert result["translation_profile"] == "research_card_cn"
    assert result["paper"]["title"] == "A useful paper"
    assert result["title_zh"] == ""
    assert result["cn_flash_180"] == ""
    assert result["card_headline"] == ""
    assert result["card_bullets"] == []
    assert result["translation"] == ""


def test_translate_paper_detail_style_strips_arxiv_boilerplate(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": "对于固定的正整数 $d$ 和小的实数 $p>0$，作者证明了一个格点近似结果。",
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)
    paper = make_paper()
    paper.id = "arxiv:2604.24891v1"
    paper.doi = ""
    paper.abstract = (
        "arXiv:2604.24891v1 Announce Type: new Abstract: "
        "For a fixed positive integer $d$ and small real $p>0$, we sample a $p$-random subset "
        "$A \\subseteq \\mathbb{Z}_{\\geq 0}^d$ and prove that a generated semigroup has a "
        "well approximated region with high probability. The result extends prior work in one dimension."
    )

    result = translation.translate_paper(paper, target_language="zh-CN", style="detail", cache_path=tmp_path / "paperlite.sqlite3")

    assert result["detail_translation"].startswith("对于固定的正整数")
    prompt_text = calls[0]["messages"][1]["content"]
    assert prompt_text.startswith("For a fixed positive integer")
    assert "arXiv:2604.24891v1" not in prompt_text
    assert "Announce Type" not in prompt_text
    assert "Abstract:" not in prompt_text


def test_translate_paper_detail_style_skips_without_abstract(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(translation, "complete_chat", lambda *args, **kwargs: calls.append((args, kwargs)))
    paper = make_paper()
    paper.abstract = ""

    result = translation.translate_paper(paper, target_language="zh-CN", style="detail", cache_path=tmp_path / "paperlite.sqlite3")

    assert calls == []
    assert result["style"] == "detail"
    assert result["translation"] == ""
    assert result["detail_translation"] == ""
    assert result["detail_skipped"] is True
    assert result["skip_reason"] == "abstract_missing"
    assert result["warnings"] == ["abstract_missing_detail_skipped"]


def test_translate_paper_without_abstract_translates_title_only(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": "膦离子导向的区域控制Minisci烷基化反应",
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)
    paper = make_paper()
    paper.abstract = ""
    paper.id = "chemrxiv:10.26434/chemrxiv.15002473/"
    paper.title = "Regiocontrolled Minisci Alkylations Guided by Phosphonium Ions"
    cache_path = tmp_path / "paperlite.sqlite3"

    result = translation.translate_paper(paper, target_language="zh-CN", cache_path=cache_path)

    assert len(calls) == 1
    assert "学术翻译助手" in calls[0]["messages"][0]["content"]
    assert calls[0]["messages"][1]["content"] == "Regiocontrolled Minisci Alkylations Guided by Phosphonium Ions"
    assert result["configured"] is True
    assert result["brief_skipped"] is True
    assert result["skip_reason"] == "abstract_missing"
    assert result["abstract_missing"] is True
    assert result["title_zh"] == "膦离子导向的区域控制Minisci烷基化反应"
    assert result["cn_flash_180"] == ""
    assert result["card_bullets"] == []
    assert result["translation"] == "标题：膦离子导向的区域控制Minisci烷基化反应"
    assert result["warnings"] == ["abstract_missing_brief_skipped"]

    calls.clear()
    cached = translation.translate_paper(paper, target_language="zh-CN", cache_path=cache_path)

    assert calls == []
    assert cached["cached"] is True
    assert cached["brief_skipped"] is True
    assert cached["title_zh"] == "膦离子导向的区域控制Minisci烷基化反应"
    assert cached["cn_flash_180"] == ""


def test_translate_paper_with_toc_html_skips_brief(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": "高温电解过程中的原位X射线衍射",
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)
    paper = make_paper()
    paper.id = "doi:10.1021/acs.chemmater.5c03240"
    paper.title = "[ASAP] Operando X-ray Diffraction during High Temperature Electrolysis"
    paper.abstract = (
        '<p><img alt="TOC Graphic" src="https://pubs.acs.org/cms/10.1021/acs.chemmater.5c03240/'
        'asset/images/medium/cm5c03240_0013.gif" /></p><div><cite>Chemistry of Materials</cite></div>'
        "<div>DOI: 10.1021/acs.chemmater.5c03240</div>"
    )
    cache_path = tmp_path / "paperlite.sqlite3"

    result = translation.translate_paper(paper, target_language="zh-CN", cache_path=cache_path)

    assert len(calls) == 1
    assert result["brief_skipped"] is True
    assert result["skip_reason"] == "abstract_missing"
    assert result["title_zh"] == "高温电解过程中的原位X射线衍射"
    assert result["cn_flash_180"] == ""
    assert result["card_bullets"] == []


def test_translate_paper_with_published_online_html_skips_brief(monkeypatch, tmp_path):
    calls = []

    def fake_complete(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        return {
            "configured": True,
            "model": "mock-translator",
            "answer": "钠不是锂",
            "warnings": [],
        }

    monkeypatch.setattr(translation, "complete_chat", fake_complete)
    paper = make_paper()
    paper.id = "doi:10.1038/s41560-026-02057-y"
    paper.title = "Sodium is not lithium"
    paper.doi = "10.1038/s41560-026-02057-y"
    paper.journal = "Nature Energy"
    paper.venue = "Nature Energy"
    paper.abstract = (
        '<p>Nature Energy, Published online: 27 April 2026; '
        '<a href="https://www.nature.com/articles/s41560-026-02057-y">'
        "doi:10.1038/s41560-026-02057-y</a></p>Sodium is not lithium"
    )
    cache_path = tmp_path / "paperlite.sqlite3"

    result = translation.translate_paper(paper, target_language="zh-CN", cache_path=cache_path)

    assert len(calls) == 1
    assert result["brief_skipped"] is True
    assert result["skip_reason"] == "abstract_missing"
    assert result["title_zh"] == "钠不是锂"
    assert result["cn_flash_180"] == ""
    assert result["card_bullets"] == []
