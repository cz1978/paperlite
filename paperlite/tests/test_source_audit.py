from datetime import datetime

from paperlite import source_audit
from paperlite.connectors.base import EndpointConfig, SourceRecord
from paperlite.models import Paper
from paperlite.runner import EndpointTask, FetchResult


def source_record(key="nature", source_kind="journal"):
    return SourceRecord(key=key, name=key.title(), source_kind=source_kind, disciplines=["Medicine"])


def endpoint_config(key="nature", source_key="nature", mode="rss"):
    return EndpointConfig(key=key, source_key=source_key, mode=mode, url=f"https://example.com/{key}.xml")


def make_task(key="nature", source_kind="journal"):
    source = source_record(key, source_kind)
    endpoint = endpoint_config(key, key)
    return EndpointTask(source=source, endpoint=endpoint)


def make_paper(**overrides):
    payload = {
        "id": "doi:10.1038/test",
        "source": "nature",
        "source_type": "journal",
        "title": "A useful paper",
        "abstract": "A useful abstract.",
        "authors": ["Ada Lovelace"],
        "url": "https://www.nature.com/articles/test",
        "doi": "10.1038/test",
        "published_at": datetime(2026, 4, 29, 9),
    }
    payload.update(overrides)
    return Paper(**payload)


def test_audit_fetch_result_classifies_ok_warn_and_fail():
    task = make_task()
    ok = source_audit.audit_fetch_result(
        task,
        FetchResult("nature", "Nature", "nature", "rss", [make_paper()], []),
        sample_size=3,
        checked_at="2026-04-29T00:00:00Z",
    )
    warn = source_audit.audit_fetch_result(
        task,
        FetchResult(
            "nature",
            "Nature",
            "nature",
            "rss",
            [
                make_paper(id="url:1", doi=None, abstract="", published_at=None),
                make_paper(id="url:2", doi=None, abstract="", published_at=None),
            ],
            [],
        ),
        sample_size=3,
        checked_at="2026-04-29T00:00:00Z",
    )
    fail = source_audit.audit_fetch_result(
        task,
        FetchResult("nature", "Nature", "nature", "rss", [], ["nature: timed out"]),
        sample_size=3,
        checked_at="2026-04-29T00:00:00Z",
    )

    assert ok.status == "ok"
    assert warn.status == "warn"
    assert "missing_doi" in warn.issue_tags
    assert "missing_abstract" in warn.issue_tags
    assert "missing_date" in warn.issue_tags
    assert fail.status == "fail"
    assert fail.issue_tags == ["fetch_failed"]


def test_audit_treats_arxiv_doi_fallback_as_complete():
    task = make_task("arxiv_cs", "preprint")
    result = source_audit.audit_fetch_result(
        task,
        FetchResult(
            "arxiv_cs",
            "arXiv CS",
            "arxiv_cs",
            "rss",
            [
                make_paper(
                    id="doi:10.48550/arxiv.2604.24766",
                    source="arxiv_cs",
                    source_type="preprint",
                    url="https://arxiv.org/abs/2604.24766",
                    doi="10.48550/arxiv.2604.24766",
                )
            ],
            [],
        ),
        sample_size=3,
        checked_at="2026-04-29T00:00:00Z",
    )

    assert result.status == "ok"
    assert "missing_doi" not in result.issue_tags


def test_fetch_audit_endpoint_uses_endpoint_request_profile(monkeypatch):
    captured = {}

    class FakeJournalFeedConnector:
        def __init__(self, config):
            captured["config"] = config

        def fetch_latest(self, *, limit, timeout_seconds, request_profile):
            captured["request_profile"] = request_profile
            return [make_paper()]

    monkeypatch.setattr(source_audit, "JournalFeedConnector", FakeJournalFeedConnector)
    task = EndpointTask(
        source=source_record("cell_inpress"),
        endpoint=EndpointConfig(
            key="cell_inpress",
            source_key="cell_inpress",
            mode="rss",
            url="https://www.cell.com/cell/inpress.rss",
            request_profile="browser_compat",
        ),
    )

    result = source_audit.fetch_audit_endpoint(task, sample_size=1, timeout_seconds=5, request_profile="paperlite")

    assert result.papers
    assert captured["request_profile"] == "browser_compat"


def test_run_source_audit_batches_and_writes_snapshot(monkeypatch, tmp_path):
    sources = (source_record("nature"), source_record("science"))
    endpoints = (
        endpoint_config("nature", "nature"),
        endpoint_config("science", "science"),
    )
    calls = []

    def fake_fetcher(task, sample_size, timeout_seconds, request_profile):
        calls.append((task.endpoint_key, sample_size, timeout_seconds, request_profile))
        return FetchResult(
            task.source_key,
            task.source.name,
            task.endpoint_key,
            task.endpoint.mode,
            [make_paper(id=f"doi:10.1234/{task.endpoint_key}", doi=f"10.1234/{task.endpoint_key}")],
            [],
        )

    monkeypatch.setattr(source_audit, "load_source_records", lambda: sources)
    monkeypatch.setattr(source_audit, "load_endpoint_configs", lambda: endpoints)
    snapshot = tmp_path / "source_audit.json"

    payload = source_audit.run_source_audit(
        limit=1,
        sample_size=2,
        timeout_seconds=4,
        request_profile="browser_compat",
        write_snapshot=True,
        snapshot_path=snapshot,
        fetcher=fake_fetcher,
    )
    loaded = source_audit.read_source_audit_snapshot(snapshot)

    assert payload["checked"] == 1
    assert payload["total_selected"] == 2
    assert payload["next_offset"] == 1
    assert calls == [("nature", 2, 4.0, "browser_compat")]
    assert payload["snapshot"]["updated"] == 1
    assert loaded["loaded"] is True
    assert loaded["summary"]["checked_count"] == 1
    assert loaded["audit"][0]["endpoint_key"] == "nature"


def test_source_audit_summary_reports_top_problem_sources():
    summary = source_audit.summarize_audit_results(
        [
            {"endpoint_key": "ok", "source_key": "ok", "source_name": "OK", "status": "ok", "issue_tags": []},
            {
                "endpoint_key": "bad",
                "source_key": "bad",
                "source_name": "Bad",
                "status": "fail",
                "issue_tags": ["fetch_failed"],
                "message": "timed out",
                "item_count": 0,
            },
        ]
    )

    assert summary["checked_count"] == 2
    assert summary["ok"] == 1
    assert summary["fail"] == 1
    assert summary["issue_counts"] == {"fetch_failed": 1}
    assert summary["top_problem_sources"][0]["endpoint_key"] == "bad"


def test_replace_source_audit_snapshot_drops_stale_rows(tmp_path):
    snapshot = tmp_path / "source_audit.json"
    snapshot.write_text(
        '{"audit":[{"endpoint_key":"old","source_key":"old","source_name":"Old","status":"warn","issue_tags":["zero_items"],"item_count":0}]}',
        encoding="utf-8",
    )
    result = source_audit.audit_fetch_result(
        make_task("fresh"),
        FetchResult("fresh", "Fresh", "fresh", "rss", [make_paper()], []),
        sample_size=3,
        checked_at="2026-04-29T00:00:00Z",
    )

    source_audit.replace_source_audit_snapshot([result], path=snapshot)
    loaded = source_audit.read_source_audit_snapshot(snapshot)

    assert loaded["summary"]["checked_count"] == 1
    assert loaded["summary"]["ok"] == 1
    assert loaded["summary"]["issue_counts"] == {}
    assert [row["endpoint_key"] for row in loaded["audit"]] == ["fresh"]
