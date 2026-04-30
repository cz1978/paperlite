from datetime import datetime
import time

from paperlite.connectors.base import EndpointConfig, SourceRecord
from paperlite.models import Paper
from paperlite.profiles import SourceProfile
from paperlite import runner


def make_source(key):
    return SourceRecord(key=key, name=key.title(), source_kind="journal")


def make_endpoint(key, source_key=None, mode="rss", **overrides):
    values = {
        "key": key,
        "source_key": source_key or key,
        "mode": mode,
        "url": f"https://example.com/{key}.xml",
    }
    values.update(overrides)
    return EndpointConfig(**values)


def make_paper(source):
    return Paper(
        id=f"{source}:1",
        source=source,
        source_type="journal",
        title=f"{source} paper",
        url=f"https://example.com/{source}",
        published_at=datetime(2024, 1, 2),
    )


def test_resolve_selection_precedence(monkeypatch):
    sources = {key: make_source(key) for key in ["arxiv", "nature", "science"]}
    endpoints = {
        "arxiv-api": make_endpoint("arxiv-api", "arxiv", "api"),
        "nature-rss": make_endpoint("nature-rss", "nature"),
        "science-rss": make_endpoint("science-rss", "science"),
    }
    profile = SourceProfile(
        key="my-lab",
        label="My Lab",
        sources=("nature",),
        endpoints=("science-rss",),
        metadata={"discipline": "custom"},
    )
    monkeypatch.setattr(runner, "_catalog", lambda: (sources, endpoints))
    monkeypatch.setattr(runner, "get_profile", lambda _key=None: profile)

    by_endpoint = runner.resolve_selection(endpoint="arxiv-api", source="nature", profile="my-lab")
    by_source = runner.resolve_selection(source="nature", profile="my-lab")
    by_profile = runner.resolve_selection(profile="my-lab")

    assert by_endpoint.selection_mode == "endpoint"
    assert by_endpoint.endpoints == ["arxiv-api"]
    assert by_source.selection_mode == "source"
    assert by_source.endpoints == ["nature-rss"]
    assert by_profile.selection_mode == "profile_endpoint"
    assert by_profile.endpoints == ["science-rss"]
    assert by_profile.profile.metadata["discipline"] == "custom"


def test_resolve_selection_skips_non_runnable_defaults_but_keeps_explicit_endpoint(monkeypatch):
    sources = {key: make_source(key) for key in ["active", "candidate", "manual"]}
    endpoints = {
        "active-rss": make_endpoint("active-rss", "active"),
        "candidate-rss": make_endpoint("candidate-rss", "candidate", status="candidate"),
        "manual-link": make_endpoint("manual-link", "manual", mode="manual"),
    }
    profile = SourceProfile(key="mixed", label="Mixed", sources=("active", "candidate", "manual"))
    monkeypatch.setattr(runner, "_catalog", lambda: (sources, endpoints))
    monkeypatch.setattr(runner, "get_profile", lambda _key=None: profile)

    by_source = runner.resolve_selection(source="active,candidate,manual")
    by_profile = runner.resolve_selection(profile="mixed")
    by_endpoint = runner.resolve_selection(endpoint="candidate-rss,manual-link")

    assert by_source.endpoints == ["active-rss"]
    assert by_profile.endpoints == ["active-rss"]
    assert by_endpoint.endpoints == ["candidate-rss", "manual-link"]


def test_run_tasks_keeps_manual_warning_without_fetch():
    task = runner.EndpointTask(
        source=make_source("manual-journal"),
        endpoint=EndpointConfig(
            key="manual-journal",
            source_key="manual-journal",
            mode="manual",
            url="https://example.com/current",
        ),
    )

    results = runner.run_tasks([task], since=None, until=None, limit=10)

    assert results[0].source_key == "manual-journal"
    assert results[0].papers == []
    assert "manual endpoint" in results[0].warnings[0]


def test_run_tasks_returns_timeout_without_waiting_for_workers(monkeypatch):
    completed = []
    started = []

    def slow_fetch(task, *_args, **_kwargs):
        started.append(task.endpoint_key)
        time.sleep(0.2)
        completed.append(task.endpoint_key)
        return runner.FetchResult(
            task.source_key,
            task.source.name,
            task.endpoint_key,
            task.endpoint.mode,
            [make_paper(task.source_key)],
            [],
        )

    monkeypatch.setattr(runner, "fetch_endpoint", slow_fetch)
    task = runner.EndpointTask(
        source=make_source("slow"),
        endpoint=make_endpoint("slow-rss", "slow"),
    )

    started_at = time.perf_counter()
    results = runner.run_tasks([task], since=None, until=None, limit=10, timeout_seconds=0.01)
    elapsed = time.perf_counter() - started_at

    assert started == ["slow-rss"]
    assert completed == []
    assert elapsed < 0.15
    assert results[0].papers == []
    assert results[0].error == "slow-rss: timed out after 0.01s"


def test_explicit_non_runnable_endpoint_returns_warning_without_fetch(monkeypatch):
    def fail_fetch(*_args, **_kwargs):
        raise AssertionError("non-runnable endpoint should not fetch")

    monkeypatch.setattr(runner.JournalFeedConnector, "fetch_latest", fail_fetch)
    task = runner.EndpointTask(
        source=make_source("candidate-journal"),
        endpoint=make_endpoint("candidate-rss", "candidate-journal", status="candidate"),
    )

    result = runner.fetch_endpoint(task, since=None, until=None, limit=10)

    assert result.papers == []
    assert "endpoint status is candidate" in result.warnings[0]
    assert result.error is None


def test_fetch_endpoint_exception_sets_error(monkeypatch):
    class FailingJournalFeedConnector:
        def __init__(self, config):
            self.config = config

        def fetch_latest(self, **_kwargs):
            raise RuntimeError("feed failed")

    monkeypatch.setattr(runner, "JournalFeedConnector", FailingJournalFeedConnector)
    task = runner.EndpointTask(
        source=make_source("journal"),
        endpoint=make_endpoint("journal-rss", "journal"),
    )

    result = runner.fetch_endpoint(task, since=None, until=None, limit=10)

    assert result.papers == []
    assert result.error == "journal-rss: feed failed"
    assert result.warnings == ["journal-rss: feed failed"]


def test_feed_endpoint_timeout_uses_endpoint_config(monkeypatch):
    captured = {}

    class FakeJournalFeedConnector:
        def __init__(self, config):
            captured["config"] = config

        def fetch_latest(self, *, since=None, until=None, limit=50, timeout_seconds=30.0, request_profile="paperlite"):
            captured["timeout_seconds"] = timeout_seconds
            captured["request_profile"] = request_profile
            return [make_paper("journal")]

    monkeypatch.setattr(runner, "JournalFeedConnector", FakeJournalFeedConnector)
    task = runner.EndpointTask(
        source=make_source("journal"),
        endpoint=make_endpoint("journal-rss", "journal", timeout_seconds=4.5),
    )

    result = runner.fetch_endpoint(task, since=None, until=None, limit=10, timeout_seconds=18)

    assert result.papers[0].source == "journal"
    assert captured["timeout_seconds"] == 4.5
    assert captured["request_profile"] == "paperlite"


def test_feed_endpoint_request_profile_uses_endpoint_config(monkeypatch):
    captured = {}

    class FakeJournalFeedConnector:
        def __init__(self, config):
            captured["config"] = config

        def fetch_latest(self, *, since=None, until=None, limit=50, timeout_seconds=30.0, request_profile="paperlite"):
            captured["request_profile"] = request_profile
            return [make_paper("journal")]

    monkeypatch.setattr(runner, "JournalFeedConnector", FakeJournalFeedConnector)
    task = runner.EndpointTask(
        source=make_source("journal"),
        endpoint=make_endpoint("journal-rss", "journal", request_profile="browser_compat"),
    )

    result = runner.fetch_endpoint(task, since=None, until=None, limit=10, timeout_seconds=18)

    assert result.papers[0].source == "journal"
    assert captured["request_profile"] == "browser_compat"


def test_api_endpoint_timeout_uses_endpoint_config(monkeypatch):
    captured = {}

    class FakeApiConnector:
        def fetch_latest(self, *, since=None, until=None, limit=50, timeout_seconds=None):
            captured["timeout_seconds"] = timeout_seconds
            return [make_paper("api")]

    monkeypatch.setattr("paperlite.registry.get_connector", lambda _source: FakeApiConnector())
    task = runner.EndpointTask(
        source=make_source("api"),
        endpoint=make_endpoint("api", "api", mode="api", timeout_seconds=3.0),
    )

    result = runner.fetch_endpoint(task, since=None, until=None, limit=10, timeout_seconds=18)

    assert result.papers[0].source == "api"
    assert captured["timeout_seconds"] == 3.0


def test_flatten_results_dedupes_and_limits():
    results = [
        runner.FetchResult("a", "A", "a-rss", "rss", [make_paper("a")], []),
        runner.FetchResult("b", "B", "b-rss", "rss", [make_paper("a"), make_paper("b")], []),
    ]

    assert [paper.source for paper in runner.flatten_results(results, limit=2)] == ["a", "b"]
