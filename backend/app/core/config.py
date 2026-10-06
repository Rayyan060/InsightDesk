"""Environment-based application settings.

All configuration is read from environment variables (and an optional ``.env``
file at the project root). Nothing machine-specific or secret is hard-coded.

Optional infrastructure settings (``DATABASE_URL``, ``OLLAMA_BASE_URL``,
``CHROMA_PERSIST_DIR``) may be left blank. A blank value means the component is
"not configured", and ``/health`` reports it that way, separately from
"unavailable".
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict, SettingsError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.exceptions import ConfigurationError

# backend/app/core/config.py -> parents[3] is the repository root ("insightdesk/").
# In the Docker image the same layout is preserved (/app/backend/app/core/...),
# so the root resolves to /app. PROJECT_ROOT can override this explicitly.
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", _DEFAULT_PROJECT_ROOT)).resolve()

_VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class Settings(BaseSettings):
    """Typed application settings. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "InsightDesk"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    # NoDecode: let the validator below parse "a,b" as well as JSON arrays.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:8501", "http://127.0.0.1:8501"],
        description="Comma-separated list or JSON array of allowed CORS origins.",
    )

    # --- Persistence -----------------------------------------------------
    database_url: str | None = "sqlite:///./data/insightdesk.db"
    # Load data/reference (plan_limits, policy_registry) at startup. Idempotent;
    # never overwrites existing rows.
    seed_reference_data: bool = True

    # --- LLM (Ollama) ----------------------------------------------------
    ollama_base_url: str | None = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_seconds: float = Field(default=60.0, gt=0)

    # --- Retrieval -------------------------------------------------------
    chroma_persist_dir: str | None = "./data/chroma"
    embedding_model: str = "all-MiniLM-L6-v2"

    # --- Agent -----------------------------------------------------------
    # R4: "Allow at most one revision before escalating."
    max_critic_revisions: int = Field(default=1, ge=0, le=1)

    # --- Security / limits -----------------------------------------------
    max_request_bytes: int = Field(default=65_536, ge=1_024, le=10_485_760)
    health_check_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    # --- Logging ---------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("database_url", "ollama_base_url", "chroma_persist_dir", mode="before")
    @classmethod
    def _optional_blank(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    raise ValueError("must be a JSON array or comma-separated list") from None
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: object) -> str:
        level = str(value).strip().upper()
        if level not in _VALID_LOG_LEVELS:
            raise ValueError(f"must be one of {sorted(_VALID_LOG_LEVELS)}")
        return level

    @field_validator("ollama_base_url")
    @classmethod
    def _validate_ollama_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute http(s) URL")
        return value.rstrip("/")

    @field_validator("ollama_model", "embedding_model", "app_name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            url = make_url(value)
        except ArgumentError:
            raise ValueError("is not a valid SQLAlchemy URL") from None
        if url.get_backend_name() != "sqlite":
            raise ValueError("only SQLite URLs are supported (sqlite:///path/to/file.db)")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.app_env == "production" and self.debug:
            raise ValueError("DEBUG must be false when APP_ENV=production")
        return self

    # ------------------------------------------------------------------ #
    # Derived values
    # ------------------------------------------------------------------ #
    @property
    def resolved_database_url(self) -> str | None:
        """Database URL with relative SQLite paths anchored at PROJECT_ROOT."""
        if self.database_url is None:
            return None
        url = make_url(self.database_url)
        database = url.database
        if not database or database == ":memory:":
            return self.database_url
        path = Path(database)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return url.set(database=path.as_posix()).render_as_string(hide_password=False)

    @property
    def sqlite_path(self) -> Path | None:
        """Filesystem path of the SQLite database, or None for in-memory/unset."""
        resolved = self.resolved_database_url
        if resolved is None:
            return None
        database = make_url(resolved).database
        if not database or database == ":memory:":
            return None
        return Path(database)

    @property
    def resolved_chroma_dir(self) -> Path | None:
        if self.chroma_persist_dir is None:
            return None
        path = Path(self.chroma_persist_dir)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_settings(**overrides: object) -> Settings:
    """Build settings, converting validation failures into ConfigurationError.

    The error lists offending field names and reasons but never echoes the
    supplied values, which could contain credentials.
    """
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_input=False, include_url=False):
            field = ".".join(str(part) for part in error.get("loc", ())) or "settings"
            problems.append(f"{field.upper()}: {error.get('msg', 'invalid value')}")
        raise ConfigurationError("Invalid configuration: " + "; ".join(problems)) from None
    except SettingsError as exc:
        # Raised when an env value cannot be decoded at all; the message names
        # the field and source only.
        raise ConfigurationError(f"Invalid configuration: {exc}") from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings (cleared in tests via get_settings.cache_clear())."""
    return load_settings()
