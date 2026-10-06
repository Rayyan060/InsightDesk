"""4: missing or invalid configuration is handled safely."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT, load_settings
from app.core.exceptions import ConfigurationError


def test_defaults_load_without_env_file() -> None:
    settings = load_settings(_env_file=None)
    assert settings.app_name == "InsightDesk"
    assert settings.ollama_model == "qwen2.5:7b"
    assert settings.embedding_model == "all-MiniLM-L6-v2"


def test_relative_paths_resolve_against_project_root() -> None:
    settings = load_settings(_env_file=None)
    assert settings.sqlite_path == (PROJECT_ROOT / "data" / "insightdesk.db").resolve()
    assert settings.resolved_chroma_dir == (PROJECT_ROOT / "data" / "chroma").resolve()


def test_blank_optional_values_mean_not_configured() -> None:
    settings = load_settings(_env_file=None, database_url="  ", ollama_base_url="", chroma_persist_dir="")
    assert settings.database_url is None
    assert settings.ollama_base_url is None
    assert settings.chroma_persist_dir is None
    assert settings.resolved_database_url is None


def test_ollama_model_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    assert load_settings(_env_file=None).ollama_model == "llama3.2:3b"


def test_env_file_is_read(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=FromEnvFile\nLOG_LEVEL=debug\n", encoding="utf-8")
    settings = load_settings(_env_file=env_file)
    assert settings.app_name == "FromEnvFile"
    assert settings.log_level == "DEBUG"


def test_cors_origins_accept_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert load_settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_accept_json_array(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test"]')
    assert load_settings(_env_file=None).cors_origins == ["http://a.test"]


def test_cors_origins_malformed_json_is_configuration_error(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.test"')
    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        load_settings(_env_file=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("log_level", "LOUD"),
        ("ollama_base_url", "not-a-url"),
        ("ollama_model", "   "),
        ("api_port", 70000),
        ("max_request_bytes", 10),
        ("app_env", "staging"),
    ],
)
def test_invalid_values_raise_configuration_error(field: str, value: object) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(_env_file=None, **{field: value})
    assert field.upper() in str(excinfo.value)


def test_invalid_env_var_raises_configuration_error(monkeypatch) -> None:
    monkeypatch.setenv("API_PORT", "not-a-port")
    with pytest.raises(ConfigurationError, match="API_PORT"):
        load_settings(_env_file=None)


def test_non_sqlite_database_rejected_without_leaking_secret() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(_env_file=None, database_url="postgresql://user:SuperSecretPw@db/insight")
    assert "DATABASE_URL" in str(excinfo.value)
    assert "SuperSecretPw" not in str(excinfo.value)


def test_error_message_does_not_echo_value() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(_env_file=None, ollama_base_url="ftp://token-abc123@host")
    assert "token-abc123" not in str(excinfo.value)


def test_production_requires_debug_off() -> None:
    with pytest.raises(ConfigurationError, match="DEBUG"):
        load_settings(_env_file=None, app_env="production", debug=True)
    assert load_settings(_env_file=None, app_env="production", debug=False).debug is False
