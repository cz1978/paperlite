from pathlib import Path

from paperlite.config import load_config


def test_runtime_config_defaults_are_open_source_friendly(tmp_path):
    config = load_config({}, cwd=tmp_path)

    assert config.sources_path.name == "sources.yaml"
    assert config.endpoints_path.name == "endpoints.yaml"
    assert config.profiles_path.name == "profiles.yaml"
    assert config.taxonomy_path.name == "taxonomy.yaml"
    assert config.db_path == tmp_path / ".paperlite" / "paperlite.sqlite3"
    assert config.crawl_cooldown_seconds == 600
    assert config.crawl_source_delay_seconds == 2.0
    assert config.enrich_timeout_seconds == 6.0
    assert config.schedule_min_interval_minutes == 15
    assert config.scheduler_poll_seconds == 30
    assert config.scheduler_enabled is True
    assert config.embedding_base_url is None
    assert config.embedding_api_key is None
    assert config.embedding_model is None


def test_deepseek_key_enables_default_openai_compatible_settings(tmp_path):
    config = load_config({"DEEPSEEK_API_KEY": "ds-secret"}, cwd=tmp_path)

    assert config.llm_base_url == "https://api.deepseek.com"
    assert config.llm_model == "deepseek-chat"
    assert config.llm_api_key == "ds-secret"


def test_deepseek_provider_without_key_does_not_enable_llm(tmp_path):
    config = load_config({"PAPERLITE_LLM_PROVIDER": "deepseek"}, cwd=tmp_path)

    assert config.llm_base_url is None
    assert config.llm_model is None
    assert config.llm_api_key is None


def test_dotenv_values_are_loaded_when_env_not_passed(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")

    config = load_config(None, cwd=tmp_path)

    assert config.llm_api_key == "from-dotenv"
    assert config.llm_base_url == "https://api.deepseek.com"
    assert config.llm_model == "deepseek-chat"


def test_dotenv_falls_back_to_parent_when_serving_from_package_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_TRAINING_EXPORT_TOKEN", raising=False)
    repo = tmp_path / "repo"
    package_dir = repo / "paperlite"
    package_dir.mkdir(parents=True)
    (repo / ".env").write_text(
        "DEEPSEEK_API_KEY=from-parent\nPAPERLITE_TRAINING_EXPORT_TOKEN=parent-token\n",
        encoding="utf-8",
    )

    config = load_config(None, cwd=package_dir)

    assert config.llm_api_key == "from-parent"
    assert config.llm_base_url == "https://api.deepseek.com"
    assert config.training_export_token == "parent-token"


def test_dotenv_current_directory_wins_over_parent(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_API_KEY", raising=False)
    repo = tmp_path / "repo"
    package_dir = repo / "paperlite"
    package_dir.mkdir(parents=True)
    (repo / ".env").write_text("DEEPSEEK_API_KEY=from-parent\n", encoding="utf-8")
    (package_dir / ".env").write_text("DEEPSEEK_API_KEY=from-package\n", encoding="utf-8")

    config = load_config(None, cwd=package_dir)

    assert config.llm_api_key == "from-package"


def test_environment_variables_override_parent_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("PAPERLITE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PAPERLITE_LLM_API_KEY", raising=False)
    repo = tmp_path / "repo"
    package_dir = repo / "paperlite"
    package_dir.mkdir(parents=True)
    (repo / ".env").write_text("DEEPSEEK_API_KEY=from-parent\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")

    config = load_config(None, cwd=package_dir)

    assert config.llm_api_key == "from-env"


def test_runtime_config_env_overrides_are_centralized(tmp_path):
    config = load_config(
        {
            "PAPERLITE_SOURCES_PATH": str(tmp_path / "sources.yaml"),
            "PAPERLITE_ENDPOINTS_PATH": str(tmp_path / "endpoints.yaml"),
            "PAPERLITE_PROFILES_PATH": str(tmp_path / "profiles.yaml"),
            "PAPERLITE_TAXONOMY_PATH": str(tmp_path / "taxonomy.yaml"),
            "PAPERLITE_DB_PATH": str(tmp_path / "db.sqlite3"),
            "PAPERLITE_CRAWL_COOLDOWN_SECONDS": "30",
            "PAPERLITE_CRAWL_SOURCE_DELAY_SECONDS": "0.5",
            "PAPERLITE_ENRICH_TIMEOUT_SECONDS": "3.5",
            "PAPERLITE_SCHEDULE_MIN_INTERVAL_MINUTES": "5",
            "PAPERLITE_SCHEDULER_POLL_SECONDS": "8",
            "PAPERLITE_SCHEDULER_ENABLED": "false",
            "PAPERLITE_LLM_BASE_URL": "http://llm.local/v1",
            "PAPERLITE_LLM_API_KEY": "secret",
            "PAPERLITE_LLM_MODEL": "model",
            "PAPERLITE_EMBEDDING_BASE_URL": "http://embed.local/v1",
            "PAPERLITE_EMBEDDING_API_KEY": "embed-secret",
            "PAPERLITE_EMBEDDING_MODEL": "embed-model",
            "PAPERLITE_TRAINING_EXPORT_TOKEN": "training-secret",
            "ZOTERO_API_KEY": "z-secret",
            "ZOTERO_LIBRARY_TYPE": "group",
            "ZOTERO_LIBRARY_ID": "42",
            "ZOTERO_COLLECTION_KEY": "ABC",
        },
        cwd=Path.cwd(),
    )

    assert config.sources_path == tmp_path / "sources.yaml"
    assert config.endpoints_path == tmp_path / "endpoints.yaml"
    assert config.db_path == tmp_path / "db.sqlite3"
    assert config.crawl_cooldown_seconds == 30
    assert config.crawl_source_delay_seconds == 0.5
    assert config.enrich_timeout_seconds == 3.5
    assert config.schedule_min_interval_minutes == 5
    assert config.scheduler_poll_seconds == 8
    assert config.scheduler_enabled is False
    assert config.llm_model == "model"
    assert config.embedding_base_url == "http://embed.local/v1"
    assert config.embedding_api_key == "embed-secret"
    assert config.embedding_model == "embed-model"
    assert config.training_export_token == "training-secret"
    assert config.zotero_library_type == "group"
    assert config.zotero_collection_key == "ABC"
