"""Settings の基本動作テスト"""

from pathlib import Path

from src.app.config import Settings


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
