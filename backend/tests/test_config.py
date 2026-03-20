"""Settings の基本動作テスト"""

from pathlib import Path

from src.app.config import Settings, _resolve_project_root


def test_settings_defaults():
    s = Settings(
        openai_api_key="test",
        _env_file=None,
    )
    assert s.openai_api_key == "test"
    assert s.llm_model == "gpt-4o"
    assert s.cognitive_mode == "legacy"
    assert s.max_concurrent_colonies == 5
    assert s.max_active_agents == 100


def test_settings_is_sqlite():
    s = Settings(
        database_url="sqlite+aiosqlite:///test.db",
        _env_file=None,
    )
    assert s.is_sqlite is True


def test_settings_is_not_sqlite():
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        _env_file=None,
    )
    assert s.is_sqlite is False


def test_load_model_config_missing_file():
    s = Settings(
        config_dir=Path("/nonexistent/path"),
        _env_file=None,
    )
    config = s.load_model_config()
    assert "default_model" in config
    assert config["default_model"] == "gpt-4o"


def test_load_graphrag_config_missing_file():
    s = Settings(
        config_dir=Path("/nonexistent/path"),
        _env_file=None,
    )
    config = s.load_graphrag_config()
    assert config == {}


def test_load_cognitive_config_missing_file():
    s = Settings(
        config_dir=Path("/nonexistent/path"),
        _env_file=None,
    )
    config = s.load_cognitive_config()
    assert config == {}


def test_resolve_project_root_finds_repo_root(tmp_path):
    repo_root = tmp_path / "repo"
    target = repo_root / "backend" / "src" / "app" / "config.py"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "templates").mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.touch()

    assert _resolve_project_root(target) == repo_root


def test_live_simulation_unavailable_without_openai_key(monkeypatch):
    monkeypatch.setattr(Settings, "load_model_config", lambda self: {"provider": "openai"})
    s = Settings(
        openai_api_key="",
        _env_file=None,
    )

    assert s.llm_provider() == "openai"
    assert s.live_simulation_available() is False
    assert "OPENAI_API_KEY" in s.live_simulation_message()


def test_live_simulation_available_for_non_openai_provider(monkeypatch):
    monkeypatch.setattr(Settings, "load_model_config", lambda self: {"provider": "ollama"})
    s = Settings(
        openai_api_key="",
        _env_file=None,
    )

    assert s.llm_provider() == "ollama"
    assert s.live_simulation_available() is True
