from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from paperlite import api, daily_crawl, runner, storage
from paperlite.endpoint_health import EndpointHealthResult
from paperlite.models import Paper


SOURCE_KEY = "philarchive_philarchive_recent_additions_rss"


def make_paper(
    id="philarchive:1",
    title="A cached humanities paper",
    abstract="Cached abstract.",
    doi=None,
    categories=None,
):
    return Paper(
        id=id,
        source=id.split(":", 1)[0],
        source_type="working_papers",
        title=title,
        abstract=abstract,
        authors=["Ada Lovelace"],
        url="https://example.com/philarchive/1",
        doi=doi,
        categories=categories or [],
        published_at=datetime(2026, 4, 28, 9),
    )


def seed_daily_cache(db_path, papers, *, discipline="humanities", source_key=SOURCE_KEY):
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key=discipline,
        source_keys=[source_key],
        limit_per_source=500,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key=discipline,
        source_key=source_key,
        papers=papers,
        path=db_path,
    )
    storage.finish_crawl_run(run["run_id"], status="completed", total_items=len(papers), path=db_path)


def test_daily_crawl_requires_discipline(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    client = TestClient(api.create_app())

    response = client.post(
        "/daily/crawl",
        json={"date_from": "2026-04-28", "date_to": "2026-04-28", "limit_per_source": 1},
    )

    assert response.status_code == 422
    assert "discipline" in response.text


def test_daily_crawl_creates_run_and_cache_reads_database(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))

    def fake_run_daily_crawl(run_id):
        storage.mark_crawl_running(run_id)
        storage.store_daily_papers(
            run_id=run_id,
            entry_date="2026-04-28",
            discipline_key="humanities",
            source_key=SOURCE_KEY,
            papers=[make_paper()],
        )
        storage.record_source_result(
            run_id=run_id,
            source_key=SOURCE_KEY,
            endpoint_key=SOURCE_KEY,
            endpoint_mode="rss",
            count=1,
        )
        storage.finish_crawl_run(run_id, status="completed", total_items=1)

    monkeypatch.setattr(api, "run_daily_crawl", fake_run_daily_crawl)
    client = TestClient(api.create_app())

    created = client.post(
        "/daily/crawl",
        json={
            "date_from": "2026-04-28",
            "date_to": "2026-04-28",
            "discipline": "humanities",
            "limit_per_source": 1,
        },
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    status = client.get(f"/daily/crawl/{run_id}")
    cache = client.get("/daily/cache?date=2026-04-28&discipline=humanities&format=json")

    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert cache.status_code == 200
    assert cache.json()["selection_mode"] == "cache"
    assert cache.json()["groups"][0]["items"][0]["title"] == "A cached humanities paper"


def test_daily_export_reads_cache_for_supported_formats(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    seed_daily_cache(
        db_path,
        [make_paper(doi="10.123/cache", categories=["humanities"])],
    )

    client = TestClient(api.create_app())

    for fmt in ["ris", "bibtex", "markdown", "json", "jsonl", "rss"]:
        response = client.get(
            f"/daily/export?date_from=2026-04-28&date_to=2026-04-28&discipline=humanities&format={fmt}"
        )

        assert response.status_code == 200
        assert response.headers["x-paperlite-export-count"] == "1"
        assert "paperlite-daily-20260428-20260428" in response.headers["content-disposition"]
        assert "A cached humanities paper" in response.text


def test_daily_export_dedupes_same_doi_across_sources(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["source-a", "source-b"],
        limit_per_source=500,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="source-a",
        papers=[make_paper(id="source-a:1", title="Shared export paper", doi="10.123/shared")],
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key="source-b",
        papers=[make_paper(id="source-b:2", title="Shared export paper", doi="10.123/shared")],
        path=db_path,
    )
    storage.finish_crawl_run(run["run_id"], status="completed", total_items=2, path=db_path)
    client = TestClient(api.create_app())

    response = client.get("/daily/export?date=2026-04-28&discipline=humanities&format=json&q=source-b")

    assert response.status_code == 200
    assert response.headers["x-paperlite-export-count"] == "1"
    assert response.json()[0]["doi"] == "10.123/shared"


def test_daily_export_filters_cache_by_query(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    seed_daily_cache(
        db_path,
        [
            make_paper(id="philarchive:1", title="A cached humanities paper", doi="10.123/cache"),
            make_paper(id="philarchive:2", title="A unique export result", doi="10.123/unique"),
        ],
    )
    client = TestClient(api.create_app())

    response = client.get("/daily/export?date=2026-04-28&discipline=humanities&format=json&q=unique")

    assert response.status_code == 200
    assert response.headers["x-paperlite-export-count"] == "1"
    assert response.json()[0]["title"] == "A unique export result"


def test_daily_export_rejects_unsupported_format(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    client = TestClient(api.create_app())

    response = client.get("/daily/export?date=2026-04-28&format=docx")

    assert response.status_code == 400
    assert "format must be" in response.text


def test_run_daily_crawl_records_source_errors_for_ops(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["source-a"],
        limit_per_source=1,
        path=db_path,
    )
    monkeypatch.setattr(
        daily_crawl,
        "resolve_selection",
        lambda **_kwargs: SimpleNamespace(tasks=[SimpleNamespace(source_key="source-a")]),
    )
    monkeypatch.setattr(
        daily_crawl,
        "run_tasks",
        lambda *_args, **_kwargs: [
            runner.FetchResult("source-a", "Source A", "source-a-rss", "rss", [], ["source-a-rss: feed failed"], "source-a-rss: feed failed")
        ],
    )

    daily_crawl.run_daily_crawl(run["run_id"], db_path=db_path)
    stored = storage.get_crawl_run(run["run_id"], path=db_path)
    status = TestClient(api.create_app()).get("/ops/status")

    assert stored["status"] == "failed"
    assert stored["error"] == "source-a-rss: feed failed"
    assert stored["source_results"][0]["error"] == "source-a-rss: feed failed"
    assert status.json()["run_summary"]["failed_source_count"] == 1
    assert any(item["kind"] == "source" for item in status.json()["recent_errors"])

    retry = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["source-a"],
        limit_per_source=1,
        reuse_within_seconds=600,
        path=db_path,
    )
    assert retry["run_id"] != run["run_id"]
    assert retry["reused"] is False


def test_run_daily_crawl_completes_partial_source_errors(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["source-a", "source-b"],
        limit_per_source=1,
        path=db_path,
    )
    monkeypatch.setattr(
        daily_crawl,
        "resolve_selection",
        lambda **_kwargs: SimpleNamespace(
            tasks=[
                SimpleNamespace(source_key="source-a"),
                SimpleNamespace(source_key="source-b"),
            ]
        ),
    )

    def fake_run_tasks(tasks, *_args, **_kwargs):
        source_key = tasks[0].source_key
        if source_key == "source-a":
            return [
                runner.FetchResult(
                    "source-a",
                    "Source A",
                    "source-a-rss",
                    "rss",
                    [make_paper(id="source-a:1", title="Successful source paper")],
                    [],
                )
            ]
        return [
            runner.FetchResult(
                "source-b",
                "Source B",
                "source-b-rss",
                "rss",
                [],
                ["source-b-rss: feed failed"],
                "source-b-rss: feed failed",
            )
        ]

    monkeypatch.setattr(daily_crawl, "run_tasks", fake_run_tasks)

    daily_crawl.run_daily_crawl(run["run_id"], db_path=db_path)
    stored = storage.get_crawl_run(run["run_id"], path=db_path)

    assert stored["status"] == "completed"
    assert stored["total_items"] == 1
    assert stored["error"] is None
    assert [item["error"] for item in stored["source_results"]] == [None, "source-b-rss: feed failed"]


def test_run_daily_crawl_warns_when_completed_with_zero_items(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=["source-a"],
        limit_per_source=1,
        path=db_path,
    )
    monkeypatch.setattr(
        daily_crawl,
        "resolve_selection",
        lambda **_kwargs: SimpleNamespace(tasks=[SimpleNamespace(source_key="source-a")]),
    )
    monkeypatch.setattr(
        daily_crawl,
        "run_tasks",
        lambda *_args, **_kwargs: [runner.FetchResult("source-a", "Source A", "source-a-rss", "rss", [], [])],
    )

    daily_crawl.run_daily_crawl(run["run_id"], db_path=db_path)
    stored = storage.get_crawl_run(run["run_id"], path=db_path)

    assert stored["status"] == "completed"
    assert stored["total_items"] == 0
    assert stored["error"] is None
    assert "no_items_matched_date_range" in stored["warnings"]
    assert stored["source_results"][0]["count"] == 0
    assert stored["source_results"][0]["error"] is None


def test_daily_crawl_reuses_recent_run_without_second_background_task(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    calls = []

    def fake_run_daily_crawl(run_id):
        calls.append(run_id)
        storage.mark_crawl_running(run_id)
        storage.finish_crawl_run(run_id, status="completed", total_items=0)

    monkeypatch.setattr(api, "run_daily_crawl", fake_run_daily_crawl)
    client = TestClient(api.create_app())

    payload = {
        "date_from": "2026-04-28",
        "date_to": "2026-04-28",
        "discipline": "humanities",
        "source": SOURCE_KEY,
        "limit_per_source": 1,
    }
    first = client.post("/daily/crawl", json=payload)
    second = client.post("/daily/crawl", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["run_id"] == first.json()["run_id"]
    assert second.json()["reused"] is True
    assert second.json()["reuse_reason"] == "cooldown"
    assert calls == [first.json()["run_id"]]


def test_daily_crawl_adds_curated_multidisciplinary_supplements_for_concrete_disciplines():
    medicine_sources = daily_crawl.resolve_crawl_source_keys(discipline_key="medicine")
    multidisciplinary_sources = daily_crawl.resolve_crawl_source_keys(discipline_key="multidisciplinary")

    assert "nature-medicine" in medicine_sources
    assert "nature" in medicine_sources
    assert "science" in medicine_sources
    assert "nature_commschem" not in medicine_sources
    assert "nature" in multidisciplinary_sources


def test_daily_crawl_keeps_field_specific_communications_sources_in_their_disciplines():
    chemistry_sources = daily_crawl.resolve_crawl_source_keys(discipline_key="chemistry")
    medicine_sources = daily_crawl.resolve_crawl_source_keys(discipline_key="medicine")

    assert "nature_commschem" in chemistry_sources
    assert "nature_commsmed" in medicine_sources


def test_daily_crawl_accepts_explicit_multidisciplinary_supplement_with_concrete_discipline():
    assert daily_crawl.resolve_crawl_source_keys(discipline_key="medicine", source="nature") == ["nature"]


def test_daily_crawl_lists_recent_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=[SOURCE_KEY],
        limit_per_source=1,
        path=db_path,
    )
    storage.finish_crawl_run(run["run_id"], status="completed", total_items=0, path=db_path)
    client = TestClient(api.create_app())

    listed = client.get("/daily/crawl?limit=5&status=completed&discipline=humanities")
    single = client.get(f"/daily/crawl/{run['run_id']}")

    assert listed.status_code == 200
    assert listed.json()["runs"][0]["run_id"] == run["run_id"]
    assert single.status_code == 200
    assert single.json()["run_id"] == run["run_id"]


def test_app_startup_marks_interrupted_crawl_runs_failed(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("PAPERLITE_SCHEDULER_ENABLED", "0")
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=[SOURCE_KEY],
        limit_per_source=1,
        path=db_path,
    )
    storage.mark_crawl_running(run["run_id"], path=db_path)

    with TestClient(api.create_app()) as client:
        response = client.get(f"/daily/crawl/{run['run_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["finished_at"]
    assert "interrupted" in payload["error"]


def test_daily_schedule_requires_discipline_and_lists_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    monkeypatch.setenv("PAPERLITE_SCHEDULER_ENABLED", "0")
    client = TestClient(api.create_app())

    missing = client.post("/daily/schedules", json={"interval_minutes": 30})
    created = client.post(
        "/daily/schedules",
        json={
            "discipline": "humanities",
            "source": SOURCE_KEY,
            "interval_minutes": 30,
            "lookback_days": 1,
            "limit_per_source": 1,
        },
    )
    listed = client.get("/daily/schedules")

    assert missing.status_code == 422
    assert created.status_code == 200
    assert created.json()["discipline_key"] == "humanities"
    assert created.json()["source_keys"] == [SOURCE_KEY]
    assert listed.json()["schedules"][0]["schedule_id"] == created.json()["schedule_id"]


def test_daily_crawl_and_schedule_numeric_validation_returns_422():
    client = TestClient(api.create_app())

    crawl = client.post(
        "/daily/crawl",
        json={
            "date": "2026-04-28",
            "discipline": "humanities",
            "limit_per_source": "many",
        },
    )
    schedule = client.post(
        "/daily/schedules",
        json={
            "discipline": "humanities",
            "interval_minutes": "soon",
        },
    )

    assert crawl.status_code == 422
    assert "limit_per_source must be an integer" in crawl.text
    assert schedule.status_code == 422
    assert "interval_minutes must be an integer" in schedule.text


def test_daily_schedule_run_now_string_false_stays_false(monkeypatch):
    captured = []

    def fake_create_daily_schedule(**kwargs):
        captured.append(kwargs)
        return {
            "schedule_id": f"schedule-{len(captured)}",
            "discipline_key": kwargs["discipline"],
            "source_keys": [],
            "interval_minutes": kwargs["interval_minutes"],
            "run_now": kwargs["run_now"],
        }

    monkeypatch.setattr(api, "create_daily_schedule", fake_create_daily_schedule)
    client = TestClient(api.create_app())

    false_response = client.post(
        "/daily/schedules",
        json={"discipline": "humanities", "interval_minutes": 30, "run_now": "false"},
    )
    true_response = client.post(
        "/daily/schedules",
        json={"discipline": "humanities", "interval_minutes": 30, "run_now": "true"},
    )

    assert false_response.status_code == 200
    assert true_response.status_code == 200
    assert captured[0]["run_now"] is False
    assert captured[1]["run_now"] is True


def test_daily_schedule_can_pause_resume_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    monkeypatch.setenv("PAPERLITE_SCHEDULER_ENABLED", "0")
    client = TestClient(api.create_app())

    created = client.post(
        "/daily/schedules",
        json={
            "discipline": "humanities",
            "source": SOURCE_KEY,
            "interval_minutes": 30,
            "lookback_days": 1,
            "limit_per_source": 1,
        },
    )
    schedule_id = created.json()["schedule_id"]
    paused = client.patch(f"/daily/schedules/{schedule_id}", json={"status": "paused"})
    resumed = client.patch(f"/daily/schedules/{schedule_id}", json={"status": "active"})
    deleted = client.delete(f"/daily/schedules/{schedule_id}")
    missing = client.delete(f"/daily/schedules/{schedule_id}")

    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert missing.status_code == 404


def test_ops_status_and_health_check_are_explicit(tmp_path, monkeypatch):
    db_path = tmp_path / "paperlite.sqlite3"
    health_path = tmp_path / "health.json"
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(db_path))
    monkeypatch.setenv("PAPERLITE_HEALTH_SNAPSHOT_PATH", str(health_path))
    monkeypatch.setenv("PAPERLITE_SCHEDULER_ENABLED", "0")
    captured = {}
    audit_captured = {}
    doctor_payload = {
        "overall": "warn",
        "generated_at": "2026-04-29T00:00:00+00:00",
        "summary": {"ok": 8, "warn": 2, "fail": 0},
        "checks": [
            {"id": "llm", "label": "LLM", "status": "warn", "message": "optional"},
            {"id": "zotero", "label": "Zotero", "status": "warn", "message": "optional"},
        ],
    }

    def fake_check_selected_endpoint_health(**kwargs):
        captured.update(kwargs)
        return [
            EndpointHealthResult(
                key="rss-a",
                source_key="source-a",
                mode="rss",
                url="https://example.com/a.xml",
                ok=True,
                checked_at="2026-04-27T00:00:00Z",
                status_code=200,
                elapsed_ms=12,
            )
        ]

    def fake_read_source_audit_snapshot():
        return {
            "loaded": True,
            "path": str(tmp_path / "source_audit.json"),
            "updated_at": "2026-04-29T00:00:00Z",
            "audit": [],
            "summary": {"checked_count": 2, "ok": 1, "warn": 1, "fail": 0, "problem_count": 1, "issue_counts": {"missing_doi": 1}},
        }

    def fake_run_source_audit(**kwargs):
        audit_captured.update(kwargs)
        return {
            "checked": 1,
            "total_selected": 2,
            "offset": 0,
            "limit": kwargs["limit"],
            "next_offset": 1,
            "results": [{"endpoint_key": "rss-a", "source_key": "source-a", "status": "warn", "issue_tags": ["missing_doi"], "item_count": 3}],
            "summary": {"checked_count": 1, "ok": 0, "warn": 1, "fail": 0, "problem_count": 1, "issue_counts": {"missing_doi": 1}},
            "snapshot": {"updated": 1, "count": 1},
        }

    doctor_calls = []

    def fake_run_doctor():
        doctor_calls.append("run")
        return doctor_payload

    monkeypatch.setattr(api, "check_selected_endpoint_health", fake_check_selected_endpoint_health)
    monkeypatch.setattr(api, "read_source_audit_snapshot", fake_read_source_audit_snapshot)
    monkeypatch.setattr(api, "run_source_audit", fake_run_source_audit)
    monkeypatch.setattr(api, "run_doctor", fake_run_doctor)
    run = storage.create_crawl_run(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
        source_keys=[SOURCE_KEY],
        limit_per_source=1,
        path=db_path,
    )
    storage.store_daily_papers(
        run_id=run["run_id"],
        entry_date="2026-04-28",
        discipline_key="humanities",
        source_key=SOURCE_KEY,
        papers=[make_paper()],
        path=db_path,
    )
    storage.record_source_result(
        run_id=run["run_id"],
        source_key=SOURCE_KEY,
        endpoint_key=SOURCE_KEY,
        endpoint_mode="rss",
        count=0,
        error="source failed",
        path=db_path,
    )
    storage.finish_crawl_run(run["run_id"], status="failed", total_items=0, error="run failed", path=db_path)
    storage.create_or_update_crawl_schedule(
        discipline_key="humanities",
        source_keys=[SOURCE_KEY],
        limit_per_source=1,
        interval_minutes=60,
        lookback_days=0,
        path=db_path,
    )
    paused = storage.create_or_update_crawl_schedule(
        discipline_key="humanities",
        source_keys=["source-b"],
        limit_per_source=1,
        interval_minutes=120,
        lookback_days=0,
        path=db_path,
    )
    storage.update_crawl_schedule_status(paused["schedule_id"], status="paused", path=db_path)
    with TestClient(api.create_app()) as client:
        status = client.get("/ops/status")
        second_status = client.get("/ops/status")
        doctor_response = client.get("/ops/doctor")
        manual_status = client.get("/ops/status")
        checked = client.post(
            "/ops/health/check",
            json={"discipline": "humanities", "source": "source-a", "limit": 999, "timeout_seconds": 99},
        )
        audit_snapshot = client.get("/ops/source-audit")
        audited = client.post(
            "/ops/source-audit/check",
            json={"discipline": "humanities", "source": "source-a", "limit": 999, "sample_size": 30, "timeout_seconds": 99},
        )

    assert status.status_code == 200
    assert "recent_runs" in status.json()
    assert status.json()["catalog_coverage"]["totals"]["source_count"] >= 800
    assert status.json()["doctor"]["overall"] == "warn"
    assert status.json()["doctor"]["warnings"] == ["llm", "zotero"]
    assert status.json()["doctor"]["snapshot_source"] == "startup"
    assert second_status.json()["doctor"]["snapshot_source"] == "startup"
    assert manual_status.json()["doctor"]["snapshot_source"] == "manual"
    assert len(doctor_calls) == 2
    assert status.json()["cache_summary"]["latest_cache_date"] == "2026-04-28"
    assert status.json()["cache_summary"]["table_counts"]["daily_entries"] == 1
    assert status.json()["run_summary"]["failed_source_count"] == 1
    assert status.json()["run_summary"]["latest_duration_seconds"] is not None
    assert status.json()["schedule_summary"]["active_count"] == 1
    assert status.json()["schedule_summary"]["paused_count"] == 1
    assert status.json()["schedule_summary"]["next_active_schedule"]["discipline_key"] == "humanities"
    assert status.json()["recent_errors"]
    assert status.json()["source_audit_summary"]["loaded"] is True
    assert status.json()["source_audit_summary"]["problem_count"] == 1
    assert status.json()["source_audit_summary"]["issue_counts"] == {"missing_doi": 1}
    assert status.json()["health_snapshot"]["path"] == str(health_path)
    assert "age_seconds" in status.json()["health_snapshot"]
    assert doctor_response.status_code == 200
    assert doctor_response.json() == doctor_payload
    assert checked.status_code == 200
    assert checked.json()["checked"] == 1
    assert checked.json()["snapshot"]["updated"] == 1
    assert captured["limit"] == 200
    assert captured["timeout_seconds"] == 30.0
    assert audit_snapshot.status_code == 200
    assert audit_snapshot.json()["summary"]["checked_count"] == 2
    assert audited.status_code == 200
    assert audited.json()["checked"] == 1
    assert audit_captured["limit"] == 200
    assert audit_captured["sample_size"] == 20
    assert audit_captured["timeout_seconds"] == 30.0
    assert audit_captured["write_snapshot"] is True
    assert health_path.exists()


def test_ops_post_numeric_validation_returns_422():
    client = TestClient(api.create_app())

    audit = client.post("/ops/source-audit/check", json={"limit": "abc"})
    health = client.post("/ops/health/check", json={"timeout_seconds": "slow"})

    assert audit.status_code == 422
    assert "limit must be an integer" in audit.text
    assert health.status_code == 422
    assert "timeout_seconds must be a number" in health.text


def test_due_schedule_runs_through_cache_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    monkeypatch.setenv("PAPERLITE_SCHEDULE_MIN_INTERVAL_MINUTES", "1")

    def fake_run_daily_crawl(run_id, *, db_path=None):
        storage.mark_crawl_running(run_id, path=db_path)
        storage.store_daily_papers(
            run_id=run_id,
            entry_date="2026-04-28",
            discipline_key="humanities",
            source_key=SOURCE_KEY,
            papers=[make_paper()],
            path=db_path,
        )
        storage.finish_crawl_run(run_id, status="completed", total_items=1, path=db_path)

    monkeypatch.setattr(daily_crawl, "today_local", lambda: datetime(2026, 4, 28).date())
    monkeypatch.setattr(daily_crawl, "run_daily_crawl", fake_run_daily_crawl)
    daily_crawl.create_daily_schedule(
        discipline="humanities",
        source=SOURCE_KEY,
        interval_minutes=1,
        lookback_days=0,
        limit_per_source=1,
        run_now=True,
    )

    ran = daily_crawl.run_due_schedules_once()
    cache = storage.query_daily_cache(
        date_from="2026-04-28",
        date_to="2026-04-28",
        discipline_key="humanities",
    )

    assert ran[0]["run"]["status"] == "completed"
    assert cache["groups"][0]["items"][0]["title"] == "A cached humanities paper"


def test_scheduler_poll_records_top_level_failure(monkeypatch):
    daily_crawl.reset_scheduler_loop_status()

    def fail_run_due_schedules_once(**_kwargs):
        raise RuntimeError("database locked")

    monkeypatch.setattr(daily_crawl, "run_due_schedules_once", fail_run_due_schedules_once)

    ran = daily_crawl.run_scheduler_poll_once()
    status = daily_crawl.scheduler_loop_status()

    assert ran == [{"scheduler_error": "database locked", "exception_type": "RuntimeError"}]
    assert status["last_error"] == "database locked"
    assert status["last_exception_type"] == "RuntimeError"

    daily_crawl.reset_scheduler_loop_status()


def test_ops_status_includes_scheduler_loop_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERLITE_DB_PATH", str(tmp_path / "paperlite.sqlite3"))
    monkeypatch.setenv("PAPERLITE_SCHEDULER_ENABLED", "0")
    monkeypatch.setattr(
        api,
        "scheduler_loop_status",
        lambda: {
            "last_poll_started_at": "2026-04-28T00:00:00+00:00",
            "last_success_at": None,
            "last_error_at": "2026-04-28T00:00:01+00:00",
            "last_error": "database locked",
            "last_exception_type": "RuntimeError",
        },
    )

    response = TestClient(api.create_app()).get("/ops/status")
    payload = response.json()

    assert response.status_code == 200
    assert payload["scheduler"]["loop"]["last_error"] == "database locked"
    assert any(
        item["kind"] == "scheduler" and item["message"] == "database locked"
        for item in payload["recent_errors"]
    )
