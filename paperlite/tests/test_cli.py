import json

import pytest

from paperlite import cli
from paperlite.endpoint_health import EndpointHealthResult


def test_cli_endpoints_filters_by_mode(capsys):
    cli.main(["endpoints", "--mode", "rss", "--format", "markdown"])

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines
    assert all("(rss/" in line for line in lines)


def test_cli_endpoints_filters_by_status(capsys):
    cli.main(["endpoints", "--status", "temporarily_unavailable", "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload
    assert all(item["status"] == "temporarily_unavailable" for item in payload)


def test_cli_endpoints_help_names_health_and_audit_filters(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["endpoints", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "Filter health/audit endpoints by canonical discipline" in output
    assert "Filter health/audit endpoints by source key" in output


def test_cli_sources_lists_catalog_in_json_and_markdown(capsys):
    cli.main(["sources", "--discipline", "computer_science", "--kind", "preprint", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload
    assert all("computer_science" in item["discipline_keys"] for item in payload)
    assert all(item["source_kind_key"] == "preprint" for item in payload)
    assert any(item["name"] == "arxiv_cs_lg" for item in payload)

    cli.main(["sources", "--health", "active", "--core", "true", "--format", "markdown"])
    markdown = capsys.readouterr().out
    assert "# PaperLite Sources" in markdown
    assert "health=active" in markdown
    assert "endpoint=" in markdown


def test_cli_sources_can_write_output(tmp_path):
    output = tmp_path / "sources.json"

    cli.main(["sources", "--area", "computing_math", "--format", "json", "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload
    assert all("computing_math" in item["area_keys"] for item in payload)


def test_cli_catalog_coverage_outputs_json_and_markdown(capsys):
    cli.main(["catalog", "coverage", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["totals"]["source_count"] >= 800
    assert payload["totals"]["runnable_source_count"] > 0
    assert "not auto-expanded" in payload["general_policy"]

    cli.main(["catalog", "coverage", "--format", "markdown"])
    markdown = capsys.readouterr().out
    assert "PaperLite 来源覆盖" in markdown
    assert "| discipline | sources | runnable |" in markdown


def test_cli_endpoint_health_uses_explicit_action(monkeypatch, capsys):
    captured = {}

    def fake_check_endpoint_health(*, mode, limit, timeout_seconds, request_profile):
        captured.update(
            {
                "mode": mode,
                "limit": limit,
                "timeout_seconds": timeout_seconds,
                "request_profile": request_profile,
            }
        )
        return [
            EndpointHealthResult(
                key="rss-a",
                source_key="source-a",
                mode="rss",
                url="https://example.com/a.xml",
                ok=True,
                checked_at="2026-04-27T00:00:00Z",
                status_code=200,
                elapsed_ms=42,
            )
        ]

    monkeypatch.setattr(cli, "check_endpoint_health", fake_check_endpoint_health)

    cli.main(
        [
            "endpoints",
            "health",
            "--mode",
            "rss",
            "--limit",
            "1",
            "--timeout",
            "2",
            "--request-profile",
            "browser_compat",
            "--format",
            "markdown",
        ]
    )

    assert captured == {"mode": "rss", "limit": 1, "timeout_seconds": 2.0, "request_profile": "browser_compat"}
    assert "OK rss-a -> source-a (rss)" in capsys.readouterr().out


def test_cli_endpoint_health_can_write_output(monkeypatch, tmp_path):
    def fake_check_endpoint_health(*, mode, limit, timeout_seconds, request_profile):
        return [
            EndpointHealthResult(
                key="rss-a",
                source_key="source-a",
                mode="rss",
                url="https://example.com/a.xml",
                ok=True,
                checked_at="2026-04-27T00:00:00Z",
                status_code=200,
                elapsed_ms=42,
            )
        ]

    monkeypatch.setattr(cli, "check_endpoint_health", fake_check_endpoint_health)
    output = tmp_path / "health.json"

    cli.main(["endpoints", "health", "--limit", "1", "--format", "json", "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["health"][0]["key"] == "rss-a"


def test_cli_endpoint_health_filters_selected_sources(monkeypatch, capsys):
    captured = {}

    def fake_check_selected_endpoint_health(*, discipline, source, mode, limit, timeout_seconds, request_profile):
        captured.update(
            {
                "discipline": discipline,
                "source": source,
                "mode": mode,
                "limit": limit,
                "timeout_seconds": timeout_seconds,
                "request_profile": request_profile,
            }
        )
        return [
            EndpointHealthResult(
                key="arxiv_cs_lg",
                source_key="arxiv_cs_lg",
                mode="rss",
                url="https://rss.arxiv.org/rss/cs.LG",
                ok=True,
                checked_at="2026-04-27T00:00:00Z",
                status_code=200,
                elapsed_ms=42,
            )
        ]

    monkeypatch.setattr(cli, "check_selected_endpoint_health", fake_check_selected_endpoint_health)

    cli.main(
        [
            "endpoints",
            "health",
            "--discipline",
            "computer_science",
            "--source",
            "arxiv_cs_lg",
            "--limit",
            "3",
            "--timeout",
            "15",
            "--format",
            "markdown",
        ]
    )

    assert captured == {
        "discipline": "computer_science",
        "source": "arxiv_cs_lg",
        "mode": "rss",
        "limit": 3,
        "timeout_seconds": 15.0,
        "request_profile": "paperlite",
    }
    assert "OK arxiv_cs_lg -> arxiv_cs_lg (rss)" in capsys.readouterr().out


def test_cli_endpoint_audit_uses_explicit_action(monkeypatch, capsys):
    captured = {}

    def fake_run_source_audit(**kwargs):
        captured.update(kwargs)
        return {
            "checked": 1,
            "next_offset": None,
            "results": [{"endpoint_key": "rss-a", "source_key": "source-a", "status": "ok", "issue_tags": [], "item_count": 1}],
            "summary": {"checked_count": 1, "ok": 1, "warn": 0, "fail": 0, "problem_count": 0, "issue_counts": {}},
        }

    monkeypatch.setattr(cli, "run_source_audit", fake_run_source_audit)
    monkeypatch.setattr(cli, "format_source_audit_markdown", lambda payload: "audit markdown")
    monkeypatch.setattr(cli, "summarize_audit_results", lambda rows: {"checked_count": len(rows)})

    cli.main(
        [
            "endpoints",
            "audit",
            "--mode",
            "rss",
            "--source",
            "nature",
            "--limit",
            "2",
            "--offset",
            "4",
            "--sample-size",
            "3",
            "--timeout",
            "5",
            "--write-snapshot",
            "--format",
            "markdown",
        ]
    )

    assert captured == {
        "discipline": None,
        "source": "nature",
        "mode": "rss",
        "limit": 2,
        "offset": 4,
        "sample_size": 3,
        "timeout_seconds": 5.0,
        "request_profile": "paperlite",
        "write_snapshot": True,
    }
    assert "audit markdown" in capsys.readouterr().out


def test_cli_rag_index_uses_core_with_explicit_scope(monkeypatch, capsys):
    captured = {}

    def fake_paper_rag_index(**kwargs):
        captured.update(kwargs)
        return {
            "configured": True,
            "embedding_model": "embed-test",
            "date_from": "2026-04-30",
            "date_to": "2026-04-30",
            "discipline": "computer_science",
            "source": "arxiv",
            "q": "RAG",
            "limit_per_source": 25,
            "candidates": 4,
            "indexed": 2,
            "skipped": 2,
            "warnings": [],
        }

    monkeypatch.setattr(cli, "paper_rag_index", fake_paper_rag_index)

    cli.main(
        [
            "rag",
            "index",
            "--date",
            "2026-04-30",
            "--discipline",
            "computer_science",
            "--source",
            "arxiv",
            "--q",
            "RAG",
            "--limit-per-source",
            "25",
            "--format",
            "markdown",
        ]
    )

    assert captured == {
        "date_value": "2026-04-30",
        "date_from": None,
        "date_to": None,
        "discipline": "computer_science",
        "source": "arxiv",
        "q": "RAG",
        "limit_per_source": 25,
    }
    output = capsys.readouterr().out
    assert "PaperLite RAG index" in output
    assert "- q: RAG" in output
    assert "- indexed: 2" in output


def test_cli_rag_ask_outputs_json_and_can_write_markdown(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_paper_ask(**kwargs):
        calls.append(kwargs)
        return {
            "configured": True,
            "answer": "Only supplied metadata supports answer [1].",
            "model": "chat-test",
            "embedding_model": "embed-test",
            "citations": [
                {
                    "index": 1,
                    "score": 0.9,
                    "paper": {
                        "title": "A RAG paper",
                        "source": "arxiv",
                        "published_at": "2026-04-30T00:00:00",
                        "doi": "10.1000/rag",
                        "url": "https://example.com/rag",
                    },
                }
            ],
            "retrieval": {"q": kwargs.get("q"), "candidates": 3, "indexed": 2, "stale": 0, "matches": 1},
            "warnings": [],
        }

    monkeypatch.setattr(cli, "paper_ask", fake_paper_ask)

    cli.main(
        [
            "rag",
            "ask",
            "What changed?",
            "--date-from",
            "2026-04-29",
            "--date-to",
            "2026-04-30",
            "--top-k",
            "5",
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["answer"].startswith("Only supplied metadata")
    assert calls[0]["question"] == "What changed?"
    assert calls[0]["top_k"] == 5
    assert calls[0]["date_from"] == "2026-04-29"
    assert calls[0]["date_to"] == "2026-04-30"
    assert calls[0]["q"] is None

    output = tmp_path / "rag.md"
    cli.main(["rag", "ask", "--question", "write me", "--q", "RAG", "--format", "markdown", "--output", str(output)])

    assert calls[1]["question"] == "write me"
    assert calls[1]["q"] == "RAG"
    markdown = output.read_text(encoding="utf-8")
    assert "PaperLite RAG answer" in markdown
    assert "- q: RAG" in markdown
    assert "A RAG paper" in markdown
