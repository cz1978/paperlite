import httpx

from paperlite.endpoint_health import (
    CLASSIFICATION_BLOCKED_403,
    CLASSIFICATION_DEAD_404,
    CLASSIFICATION_HTML_NOT_FEED,
    CLASSIFICATION_REDIRECT_ERROR,
    CLASSIFICATION_TIMEOUT,
    CLASSIFICATION_TLS_ERROR,
    EndpointHealthResult,
    _looks_like_feed,
    check_endpoint_health,
    merge_health_snapshot,
    probe_endpoint,
)
from paperlite.catalog_quality import load_health_snapshot
from paperlite.http_client import feed_headers


def test_check_endpoint_health_filters_limits_and_preserves_order(monkeypatch):
    endpoints = [
        {"key": "rss-a", "source_key": "source-a", "mode": "rss", "url": "https://example.com/a.xml"},
        {"key": "rss-b", "source_key": "source-b", "mode": "rss", "url": "https://example.com/b.xml"},
        {"key": "rss-c", "source_key": "source-c", "mode": "rss", "url": "https://example.com/c.xml"},
    ]
    captured = {}

    def fake_list_endpoints(mode=None):
        captured["mode"] = mode
        return endpoints

    def fake_checker(endpoint, timeout_seconds, request_profile):
        return EndpointHealthResult(
            key=endpoint["key"],
            source_key=endpoint["source_key"],
            mode=endpoint["mode"],
            url=endpoint["url"],
            ok=True,
            checked_at="2026-04-27T00:00:00Z",
            status_code=200,
            elapsed_ms=int(timeout_seconds * 10),
        )

    monkeypatch.setattr("paperlite.endpoint_health.list_endpoints", fake_list_endpoints)

    results = check_endpoint_health(mode="rss", limit=2, timeout_seconds=1.5, checker=fake_checker)

    assert captured["mode"] == "rss"
    assert [result.key for result in results] == ["rss-a", "rss-b"]
    assert all(result.ok for result in results)
    assert all(result.elapsed_ms == 15 for result in results)


def test_looks_like_feed_detects_rss_and_atom():
    assert _looks_like_feed('<?xml version="1.0"?><rss version="2.0"></rss>')
    assert _looks_like_feed('<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    assert not _looks_like_feed("<html><title>not a feed</title></html>")


def response(status_code, body, content_type="application/xml"):
    return httpx.Response(
        status_code,
        text=body,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://example.com/feed.xml"),
    )


def endpoint():
    return {"key": "feed", "source_key": "source", "mode": "rss", "url": "https://example.com/feed.xml"}


def test_probe_endpoint_classifies_http_and_html_failures(monkeypatch):
    cases = [
        (response(404, "not found", "text/html"), CLASSIFICATION_DEAD_404),
        (response(403, "blocked", "text/html"), CLASSIFICATION_BLOCKED_403),
        (response(200, "<html>not a feed</html>", "text/html"), CLASSIFICATION_HTML_NOT_FEED),
    ]
    for fake_response, classification in cases:
        monkeypatch.setattr("paperlite.endpoint_health.get_feed_url", lambda *args, **kwargs: fake_response)
        result = probe_endpoint(endpoint(), 1)
        assert result.ok is False
        assert result.classification == classification


def test_probe_endpoint_classifies_request_failures(monkeypatch):
    cases = [
        (httpx.TimeoutException("timed out"), CLASSIFICATION_TIMEOUT),
        (httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]"), CLASSIFICATION_TLS_ERROR),
        (httpx.TooManyRedirects("Exceeded maximum allowed redirects."), CLASSIFICATION_REDIRECT_ERROR),
    ]
    for exc, classification in cases:
        def raise_exc(*args, **kwargs):
            raise exc

        monkeypatch.setattr("paperlite.endpoint_health.get_feed_url", raise_exc)
        result = probe_endpoint(endpoint(), 1)
        assert result.ok is False
        assert result.classification == classification


def test_request_profiles_change_headers_only():
    paperlite_headers = feed_headers("paperlite")
    browser_headers = feed_headers("browser_compat")

    assert "PaperLite" in paperlite_headers["user-agent"]
    assert "Mozilla" in browser_headers["user-agent"]
    assert paperlite_headers["accept-language"] == "en-US,en;q=0.9"
    assert browser_headers["accept-language"] == "en-US,en;q=0.9"


def test_probe_endpoint_uses_endpoint_request_profile(monkeypatch):
    captured = {}

    def fake_get_feed_url(url, *, timeout_seconds, request_profile):
        captured["request_profile"] = request_profile
        return response(200, "<rss></rss>")

    monkeypatch.setattr("paperlite.endpoint_health.get_feed_url", fake_get_feed_url)

    result = probe_endpoint({**endpoint(), "request_profile": "browser_compat"}, 1, request_profile="paperlite")

    assert result.ok is True
    assert captured["request_profile"] == "browser_compat"


def test_merge_health_snapshot_preserves_unchecked_rows(tmp_path):
    snapshot = tmp_path / "health.json"
    snapshot.write_text(
        '{"health":[{"key":"old","source_key":"old-source","mode":"rss","url":"https://example.com/old.xml","ok":true,"classification":"ok","checked_at":"2026-04-26T00:00:00Z"}]}',
        encoding="utf-8",
    )

    merged = merge_health_snapshot(
        [
            EndpointHealthResult(
                key="new",
                source_key="new-source",
                mode="rss",
                url="https://example.com/new.xml",
                ok=False,
                checked_at="2026-04-27T00:00:00Z",
                classification="timeout",
                error="timed out",
            )
        ],
        path=snapshot,
    )
    loaded = load_health_snapshot(snapshot)

    assert merged["updated"] == 1
    assert merged["count"] == 2
    assert loaded["old"]["ok"] is True
    assert loaded["new"]["classification"] == "timeout"
