from datetime import datetime

from fastapi.testclient import TestClient

from paperlite import api, storage
from paperlite.models import Paper


def make_paper(id="arxiv:1", title="Library paper"):
    return Paper(
        id=id,
        source=id.split(":", 1)[0],
        source_type="preprint",
        title=title,
        abstract="Useful abstract.",
        authors=["Ada Lovelace"],
        url=f"https://example.com/{id}",
        doi="10.1234/library",
        published_at=datetime(2026, 4, 28, 9),
        categories=["cs.LG"],
    )


def test_library_state_is_read_only(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())

    response = client.post("/library/state", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 200
    assert response.json()["items"][0]["read"] is False
    with storage.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM library_events").fetchone()[0] == 0


def test_library_action_and_items_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())
    paper = make_paper()

    read = client.post("/library/action", json={"action": "read", "items": [paper.to_dict()]})
    favorite = client.post("/library/action", json={"action": "favorite", "items": [paper.to_dict()]})
    hidden = client.post("/library/action", json={"action": "hide", "items": [paper.to_dict()]})
    state = client.post("/library/state", json={"items": [paper.to_dict()]})
    favorites = client.get("/library/items?state=favorite")

    assert read.status_code == 200
    assert favorite.status_code == 200
    assert hidden.status_code == 200
    assert hidden.json()["updated"][0]["hidden"] is True
    assert state.json()["items"][0]["read"] is True
    assert state.json()["items"][0]["favorite"] is True
    assert state.json()["items"][0]["hidden"] is True
    assert favorites.json()["count"] == 1
    with storage.connect(db_path) as connection:
        actions = [row[0] for row in connection.execute("SELECT action FROM library_events").fetchall()]
    assert set(actions) == {"read", "favorite", "hide"}
    assert len(actions) == 3


def test_library_saved_views_endpoints(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())

    saved = client.post(
        "/library/views",
        json={"name": "Today AI", "filters": {"date_from": "2026-04-28", "discipline": "computer_science"}},
    )
    listed = client.get("/library/views")
    deleted = client.delete("/library/views?name=Today%20AI")

    assert saved.status_code == 200
    assert saved.json()["name"] == "Today AI"
    assert listed.status_code == 200
    assert listed.json()["views"][0]["filters"]["discipline"] == "computer_science"
    assert deleted.status_code == 200
    assert client.get("/library/views").json()["views"] == []


def test_preferences_prompts_and_profile_endpoints(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())
    paper = make_paper(title="RAG agent benchmark")

    client.post("/library/action", json={"action": "favorite", "items": [paper.to_dict()]})
    created = client.post("/preferences/prompts", json={"text": "Prefer RAG agents api_key=secret", "weight": 2})
    listed = client.get("/preferences/prompts")
    profile = client.get("/preferences/profile")
    patched = client.patch(f"/preferences/prompts/{created.json()['prompt_id']}", json={"enabled": False})
    disabled = client.get("/preferences/prompts?enabled=false")
    rebuilt = client.post("/preferences/rebuild")
    deleted = client.delete(f"/preferences/prompts/{created.json()['prompt_id']}")

    assert created.status_code == 200
    assert "secret" not in created.json()["text"]
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert profile.status_code == 200
    assert profile.json()["signal_counts"]["favorite_count"] == 1
    assert profile.json()["signal_counts"]["enabled_prompt_count"] == 1
    assert "rag" in {item["term"] for item in profile.json()["profile"]["positive_terms"]}
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    assert disabled.json()["prompts"][0]["prompt_id"] == created.json()["prompt_id"]
    assert rebuilt.status_code == 200
    assert rebuilt.json()["signal_counts"]["enabled_prompt_count"] == 0
    assert deleted.status_code == 200
    assert client.delete(f"/preferences/prompts/{created.json()['prompt_id']}").status_code == 404


def test_preferences_prompt_weight_rejects_invalid_payloads(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())

    bool_create = client.post("/preferences/prompts", json={"text": "Prefer RAG", "weight": True})
    text_create = client.post("/preferences/prompts", json={"text": "Prefer RAG", "weight": "many"})
    created = client.post("/preferences/prompts", json={"text": "Prefer RAG", "weight": 5})
    bool_patch = client.patch(f"/preferences/prompts/{created.json()['prompt_id']}", json={"weight": False})

    assert bool_create.status_code == 422
    assert "weight must be an integer" in bool_create.text
    assert text_create.status_code == 422
    assert "weight must be an integer" in text_create.text
    assert created.status_code == 200
    assert created.json()["weight"] == 5
    assert bool_patch.status_code == 422
    assert "weight must be an integer" in bool_patch.text


def test_preferences_training_data_requires_authorization(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("PAPERLITE_TRAINING_EXPORT_TOKEN", "training-secret")
    client = TestClient(api.create_app())
    paper = make_paper(title="RAG agent benchmark")

    client.post(
        "/library/action",
        json={
            "action": "ai_recommend",
            "items": [paper.to_dict()],
            "event": {"noise_tags": ["weak_metadata"], "quality_score": 55, "preference_score": 83},
        },
    )
    blocked = client.get("/preferences/training-data")
    old_authorized_param = client.get("/preferences/training-data?authorized=true")
    exported = client.get("/preferences/training-data", headers={"Authorization": "Bearer training-secret"})
    jsonl = client.get("/preferences/training-data?format=jsonl", headers={"Authorization": "Bearer training-secret"})

    assert blocked.status_code == 403
    assert "bearer token" in blocked.json()["detail"]
    assert old_authorized_param.status_code == 403
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["authorized"] is True
    assert payload["examples"][0]["label"] == "weak_positive"
    assert payload["examples"][0]["noise_tags"] == ["weak_metadata"]
    assert payload["examples"][0]["quality_score"] == 55
    assert payload["examples"][0]["preference_score"] == 83
    assert payload["examples"][0]["paper"]["title"] == "RAG agent benchmark"
    assert "raw" not in payload["examples"][0]["paper"]
    assert jsonl.status_code == 200
    assert "application/x-ndjson" in jsonl.headers["content-type"]
    assert '"kind": "paper_preference"' in jsonl.text


def test_preferences_settings_and_purify_endpoints(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())
    paper = make_paper(title="Agent evolution benchmark")

    initial = client.get("/preferences/settings")
    patched = client.patch("/preferences/settings", json={"learning_enabled": False, "model_signal_learning_enabled": False})
    skipped_query = client.post("/agent/filter", json={"paper": paper.to_dict(), "query": "agent evolution"})
    skipped_signal = client.post("/library/action", json={"action": "ai_recommend", "items": [paper.to_dict()]})
    profile = client.get("/preferences/profile")
    purify = client.post("/preferences/purify")

    assert initial.status_code == 200
    assert initial.json()["settings"]["learning_enabled"] is True
    assert patched.status_code == 200
    assert patched.json()["settings"]["learning_enabled"] is False
    assert patched.json()["settings"]["model_signal_learning_enabled"] is False
    assert skipped_query.status_code == 200
    assert skipped_signal.status_code == 200
    assert skipped_signal.json()["skipped"] is True
    assert profile.json()["signal_counts"]["learning_enabled"] is False
    assert purify.status_code == 200
    assert "purify" in purify.json()


def test_preferences_clear_learning_data_endpoint_preserves_library_state(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("PAPERLITE_TRAINING_EXPORT_TOKEN", "training-secret")
    client = TestClient(api.create_app())
    paper = make_paper(title="RAG agent benchmark")

    client.post("/preferences/prompts", json={"text": "Prefer RAG agents"})
    client.post("/agent/filter", json={"paper": paper.to_dict(), "query": "agent benchmark"})
    client.post("/library/action", json={"action": "favorite", "items": [paper.to_dict()]})
    before_eval = client.get("/preferences/evaluation")
    cleared = client.post("/preferences/learning-data/clear")
    favorites = client.get("/library/items?state=favorite")
    training = client.get("/preferences/training-data", headers={"Authorization": "Bearer training-secret"})
    after_eval = client.get("/preferences/evaluation")

    assert before_eval.status_code == 200
    assert before_eval.json()["example_count"] == 1
    assert cleared.status_code == 200
    payload = cleared.json()
    assert payload["cleared"] is True
    assert payload["removed_queries"] == 1
    assert payload["removed_events"] == 1
    assert payload["profile"]["signal_counts"]["query_count"] == 0
    assert payload["profile"]["signal_counts"]["events_considered"] == 0
    assert payload["profile"]["signal_counts"]["enabled_prompt_count"] == 1
    assert favorites.json()["items"][0]["favorite"] is True
    assert training.json()["example_count"] == 0
    assert after_eval.json()["example_count"] == 0


def test_preferences_evaluation_endpoint_summarizes_local_events(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    client = TestClient(api.create_app())
    positive = make_paper(id="arxiv:positive", title="RAG agent benchmark")
    positive.doi = "10.1234/api-positive"
    negative = make_paper(id="noise:negative", title="Conference announcement")
    negative.doi = "10.1234/api-negative"

    client.post("/library/action", json={"action": "favorite", "items": [positive.to_dict()]})
    client.post(
        "/library/action",
        json={"action": "hide", "items": [negative.to_dict()], "event": {"noise_tags": ["announcement"]}},
    )
    response = client.get("/preferences/evaluation?k=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["example_count"] == 2
    assert payload["positive_count"] == 1
    assert payload["negative_count"] == 1
    assert payload["precision_at_k"] == 0.5
    assert payload["noise_tag_distribution"] == {"announcement": 1}
