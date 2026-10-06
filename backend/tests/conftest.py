from __future__ import annotations

import io
import logging
from collections.abc import Callable, Iterator
from functools import partial
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import lifecycle
from app.core.config import Settings, get_settings, load_settings
from app.core.logging import build_handler
from app.main import create_app
from app.services.llm import OllamaClient

# Env vars that would otherwise leak from the developer machine into tests.
_SETTINGS_ENV_VARS = [name.upper() for name in Settings.model_fields] + ["PROJECT_ROOT"]


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def make_settings(tmp_path) -> Callable[..., Settings]:
    """Settings for tests: temp SQLite, Chroma and Ollama off unless overridden."""

    def _make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "_env_file": None,
            "app_env": "test",
            "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "chroma_persist_dir": "",
            "ollama_base_url": "",
            "log_level": "INFO",
            "log_format": "json",
        }
        values.update(overrides)
        return load_settings(**values)

    return _make


@pytest.fixture
def ollama_transport(monkeypatch: pytest.MonkeyPatch) -> Callable[[httpx.MockTransport], None]:
    """Route the app's Ollama client through a mock transport."""

    def _install(transport: httpx.MockTransport) -> None:
        monkeypatch.setattr(lifecycle, "OllamaClient", partial(OllamaClient, transport=transport))

    return _install


@pytest.fixture
def build_client() -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def _build(settings: Settings, configure: Callable[[FastAPI], None] | None = None) -> TestClient:
        app = create_app(settings)
        if configure:
            configure(app)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()  # run lifespan
        clients.append(client)
        return client

    yield _build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_settings, build_client) -> TestClient:
    return build_client(make_settings())


@pytest.fixture(scope="session")
def reference_data():
    """(plan_limits by plan, policy rules) from data/reference."""
    from app.synthetic.pipeline import load_reference

    plan_limits, rules, issues = load_reference()
    assert not issues, issues
    return plan_limits, rules


@pytest.fixture(scope="session")
def seeded_data(reference_data):
    from app.synthetic.generator import generate_seeded
    from app.synthetic.scenarios import DEFAULT_REFERENCE_DATE, DEFAULT_SEED

    plan_limits, rules = reference_data
    return generate_seeded(seed=DEFAULT_SEED, reference_date=DEFAULT_REFERENCE_DATE, plan_limits=plan_limits, policy_rules=rules)


@pytest.fixture
def db(tmp_path):
    """Fresh file-backed SQLite database with the Annex C schema (no data)."""
    from app.database.connection import Database

    database = Database(f"sqlite:///{(tmp_path / 'phase2.db').as_posix()}")
    database.init_schema()
    yield database
    database.dispose()


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    """Capture everything written through the production formatter/filters."""
    stream = io.StringIO()
    handler = build_handler("json", stream=stream)
    handler.set_name("test-capture")
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield stream
    root.removeHandler(handler)
    root.setLevel(previous_level)
