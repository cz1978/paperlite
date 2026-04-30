import json
import sqlite3

from paperlite import cli, doctor


def test_doctor_reports_missing_required_dependency(monkeypatch, tmp_path):
    real_find_spec = doctor.importlib.util.find_spec

    def fake_find_spec(name):
        if name == "pydantic":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(doctor.importlib.util, "find_spec", fake_find_spec)

    payload = doctor.run_doctor(env={"PAPERLITE_DB_PATH": str(tmp_path / "paperlite.sqlite3")})

    required = next(item for item in payload["checks"] if item["id"] == "required_packages")
    assert payload["overall"] == "fail"
    assert required["status"] == "fail"
    assert "pydantic" in required["details"]["missing"]


def test_doctor_optional_llm_and_zotero_are_warnings(tmp_path):
    payload = doctor.run_doctor(env={"PAPERLITE_DB_PATH": str(tmp_path / "paperlite.sqlite3")})

    checks = {item["id"]: item for item in payload["checks"]}
    assert checks["llm"]["status"] == "warn"
    assert checks["zotero"]["status"] == "warn"
    assert checks["health_snapshot"]["status"] == "ok"
    assert payload["summary"]["fail"] == 0


def test_doctor_never_prints_api_key_values(tmp_path):
    env = {
        "PAPERLITE_DB_PATH": str(tmp_path / "paperlite.sqlite3"),
        "PAPERLITE_LLM_BASE_URL": "https://llm.example.test",
        "PAPERLITE_LLM_MODEL": "test-model",
        "PAPERLITE_LLM_API_KEY": "super-secret-llm-key",
        "ZOTERO_API_KEY": "super-secret-zotero-key",
        "ZOTERO_LIBRARY_ID": "123",
        "ZOTERO_LIBRARY_TYPE": "user",
    }

    payload = doctor.run_doctor(env=env)
    markdown = doctor.format_doctor_markdown(payload)
    body = doctor.format_doctor_json(payload)

    assert "super-secret-llm-key" not in body
    assert "super-secret-zotero-key" not in body
    assert "super-secret-llm-key" not in markdown
    assert "super-secret-zotero-key" not in markdown


def test_doctor_inspects_existing_db_without_creating_missing_db(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    missing_payload = doctor.run_doctor(env={"PAPERLITE_DB_PATH": str(missing)})

    assert not missing.exists()
    assert next(item for item in missing_payload["checks"] if item["id"] == "sqlite_db")["status"] == "warn"

    existing = tmp_path / "existing.sqlite3"
    with sqlite3.connect(existing) as connection:
        connection.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO schema_meta (key, value) VALUES ('schema_version', '3')")

    existing_payload = doctor.run_doctor(env={"PAPERLITE_DB_PATH": str(existing)})
    db_check = next(item for item in existing_payload["checks"] if item["id"] == "sqlite_db")

    assert existing.exists()
    assert db_check["status"] == "warn"
    assert "requires additive migration" in db_check["message"]
    assert db_check["details"]["exists"] is True
    assert "schema_meta" in db_check["details"]["tables"]
    assert db_check["details"]["schema_version"] == "3"
    assert db_check["details"]["expected_schema_version"] == doctor.SCHEMA_VERSION
    assert db_check["details"]["missing_tables"]


def test_doctor_markdown_and_json_formatters(tmp_path):
    payload = doctor.run_doctor(env={"PAPERLITE_DB_PATH": str(tmp_path / "paperlite.sqlite3")})

    markdown = doctor.format_doctor_markdown(payload)
    parsed = json.loads(doctor.format_doctor_json(payload))

    assert markdown.startswith("# PaperLite Doctor")
    assert parsed["overall"] == payload["overall"]
    assert "checks" in parsed


def test_cli_doctor_outputs_markdown_and_json(monkeypatch, capsys):
    payload = {
        "overall": "warn",
        "generated_at": "2026-04-29T00:00:00+00:00",
        "summary": {"ok": 1, "warn": 1, "fail": 0},
        "checks": [{"id": "llm", "label": "LLM", "status": "warn", "message": "optional"}],
    }

    monkeypatch.setattr(cli, "run_doctor", lambda: payload)
    monkeypatch.setattr(cli, "format_doctor_markdown", doctor.format_doctor_markdown)
    monkeypatch.setattr(cli, "format_doctor_json", doctor.format_doctor_json)

    cli.main(["doctor", "--format", "markdown"])
    assert "# PaperLite Doctor" in capsys.readouterr().out

    cli.main(["doctor", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["overall"] == "warn"
