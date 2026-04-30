from fastapi.testclient import TestClient

from paperlite import api
from paperlite.llm import LLMRequestError


def paper_payload():
    return {
        "id": "arxiv:1",
        "source": "arxiv",
        "source_type": "preprint",
        "title": "Paper",
        "url": "https://arxiv.org/abs/1",
    }


def test_removed_old_agent_endpoints_return_404():
    client = TestClient(api.create_app())

    digest = client.post("/agent/digest", json={"sources": "arxiv", "limit": 1})
    rank = client.post("/agent/rank", json={"query": "diffusion", "sources": "arxiv"})

    assert digest.status_code == 404
    assert rank.status_code == 404


def test_agent_explain_endpoint(monkeypatch):
    monkeypatch.setattr(api, "paper_explain", lambda **kwargs: {
        "papers": [kwargs["paper"]],
        "answer": "Explanation.",
        "model": "mock",
        "configured": True,
        "warnings": [],
    })
    client = TestClient(api.create_app())

    response = client.post(
        "/agent/explain",
        json={
            "paper": {
                **paper_payload(),
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Explanation."


def test_agent_context_endpoint_uses_host_model(monkeypatch):
    calls = []

    def fake_context(**kwargs):
        calls.append(kwargs)
        return {
            "configured": True,
            "model_source": "agent_host",
            "paperlite_llm_used": False,
            "action": kwargs["action"],
            "messages": [{"role": "user", "content": "Use host model."}],
            "papers": [kwargs["paper"]],
            "retrieval": {},
            "warnings": ["agent_host_model_required"],
        }

    monkeypatch.setattr(api, "paper_agent_context", fake_context)
    client = TestClient(api.create_app())

    response = client.post(
        "/agent/context",
        json={
            "action": "filter",
            "paper": paper_payload(),
            "query": "important",
        },
    )

    assert response.status_code == 200
    assert response.json()["model_source"] == "agent_host"
    assert response.json()["paperlite_llm_used"] is False
    assert calls[0]["action"] == "filter"
    assert calls[0]["query"] == "important"


def test_agent_research_endpoint(monkeypatch):
    calls = []

    def fake_research(**kwargs):
        calls.append(kwargs)
        return {
            "status": "ok",
            "scope": {"discipline": kwargs["discipline"], "q": kwargs["q"]},
            "total_count": 0,
            "returned_count": 0,
            "papers": [],
            "warnings": [],
        }

    monkeypatch.setattr(api, "paper_research", fake_research)
    client = TestClient(api.create_app())

    response = client.post(
        "/agent/research",
        json={
            "topic": "材料里的电池",
            "discipline": "materials",
            "q": "battery",
            "date": "2026-04-30",
            "limit": 12,
            "crawl_if_missing": True,
            "translate_brief": False,
            "target_language": "zh-CN",
            "translation_profile": "research_card_cn",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert calls[0]["topic"] == "材料里的电池"
    assert calls[0]["discipline"] == "materials"
    assert calls[0]["q"] == "battery"
    assert calls[0]["date_value"] == "2026-04-30"
    assert calls[0]["limit"] == 12
    assert calls[0]["crawl_if_missing"] is True
    assert calls[0]["translate_brief"] is False
    assert calls[0]["target_language"] == "zh-CN"
    assert calls[0]["translation_profile"] == "research_card_cn"


def test_agent_rag_endpoints(monkeypatch):
    index_calls = []
    ask_calls = []

    def fake_index(**kwargs):
        index_calls.append(kwargs)
        return {
            "configured": True,
            "embedding_model": "mock-embed",
            "candidates": 1,
            "indexed": 1,
            "skipped": 0,
            "warnings": [],
        }

    def fake_ask(**kwargs):
        ask_calls.append(kwargs)
        return {
            "configured": True,
            "answer": "Answer [1].",
            "model": "mock-chat",
            "embedding_model": "mock-embed",
            "citations": [{"index": 1, "score": 0.9, "paper": paper_payload()}],
            "retrieval": {"matches": 1},
            "warnings": [],
        }

    monkeypatch.setattr(api, "paper_rag_index", fake_index)
    monkeypatch.setattr(api, "paper_ask", fake_ask)
    client = TestClient(api.create_app())

    indexed = client.post(
        "/agent/rag/index",
        json={"date": "2026-04-29", "discipline": "computer_science", "source": "arxiv", "q": "RAG", "limit": 7},
    )
    asked = client.post(
        "/agent/ask",
        json={
            "question": "Which paper is relevant?",
            "date": "2026-04-29",
            "discipline": "computer_science",
            "q": "RAG",
            "top_k": 3,
        },
    )

    assert indexed.status_code == 200
    assert indexed.json()["indexed"] == 1
    assert asked.status_code == 200
    assert asked.json()["answer"] == "Answer [1]."
    assert index_calls[0]["date_value"] == "2026-04-29"
    assert index_calls[0]["q"] == "RAG"
    assert index_calls[0]["limit_per_source"] == 7
    assert ask_calls[0]["question"] == "Which paper is relevant?"
    assert ask_calls[0]["q"] == "RAG"
    assert ask_calls[0]["top_k"] == 3


def test_daily_related_endpoint(monkeypatch):
    calls = []

    def fake_related(**kwargs):
        calls.append(kwargs)
        return {
            "configured": True,
            "paper_id": kwargs["paper_id"],
            "embedding_model": "mock-embed",
            "related": [{"index": 1, "score": 0.91, "paper": paper_payload()}],
            "retrieval": {"matches": 1, "candidates": 2, "refreshed": 1},
            "warnings": [],
        }

    monkeypatch.setattr(api, "paper_related", fake_related)
    client = TestClient(api.create_app())

    response = client.get(
        "/daily/related",
        params={
            "paper_id": "arxiv:1",
            "date": "2026-04-29",
            "discipline": "computer_science",
            "source": "arxiv",
            "q": "RAG",
            "top_k": "5",
            "limit_per_source": "12",
        },
    )

    assert response.status_code == 200
    assert response.json()["related"][0]["paper"]["id"] == "arxiv:1"
    assert calls == [
        {
            "paper_id": "arxiv:1",
            "date_value": "2026-04-29",
            "date_from": None,
            "date_to": None,
            "discipline": "computer_science",
            "source": "arxiv",
            "q": "RAG",
            "top_k": 5,
            "limit_per_source": 12,
        }
    ]


def test_agent_endpoints_surface_llm_errors(monkeypatch):
    query_calls = []

    def raise_timeout(**_kwargs):
        raise LLMRequestError("llm_timeout", api_status_code=503)

    def raise_rate_limit(**_kwargs):
        raise LLMRequestError("llm_http_error: provider returned 429", api_status_code=429, provider_status_code=429)

    monkeypatch.setattr(api, "paper_explain", raise_timeout)
    monkeypatch.setattr(api, "paper_rag_index", raise_timeout)
    monkeypatch.setattr(api, "paper_ask", raise_timeout)
    monkeypatch.setattr(api, "paper_related", raise_timeout)
    monkeypatch.setattr(api, "translate_paper", raise_timeout)
    monkeypatch.setattr(api, "filter_paper", raise_rate_limit)
    monkeypatch.setattr(api, "get_relevant_preference_profile", lambda **_kwargs: None)
    monkeypatch.setattr(api, "record_preference_query", lambda **kwargs: query_calls.append(kwargs))
    client = TestClient(api.create_app())

    explain = client.post("/agent/explain", json={"paper": paper_payload()})
    indexed = client.post("/agent/rag/index", json={"date": "2026-04-29"})
    asked = client.post("/agent/ask", json={"question": "important?"})
    related = client.get("/daily/related", params={"paper_id": "arxiv:1", "date": "2026-04-29"})
    translate = client.post("/agent/translate", json={"paper": paper_payload()})
    filtered = client.post("/agent/filter", json={"paper": paper_payload(), "query": "important"})

    assert explain.status_code == 503
    assert indexed.status_code == 503
    assert asked.status_code == 503
    assert related.status_code == 503
    assert translate.status_code == 503
    assert filtered.status_code == 429
    assert "llm_http_error" in filtered.json()["detail"]
    assert query_calls == []
