"""1-2: application imports and initialises; OpenAPI docs are served."""

from __future__ import annotations

import importlib


def test_application_module_imports() -> None:
    module = importlib.import_module("app.main")
    assert module.app.title == "InsightDesk"


def test_all_packages_import() -> None:
    for name in [
        "app.agents.graph",
        "app.agents.state",
        "app.rag.chunking",
        "app.rag.embeddings",
        "app.rag.ingestion",
        "app.rag.precedence",
        "app.rag.retriever",
        "app.tools.account",
        "app.tools.billing",
        "app.tools.usage",
        "app.tools.platform",
        "app.tools.handoff",
        "app.services.policy",
        "app.services.audit",
        "app.database.repositories",
    ]:
        importlib.import_module(name)


def test_server_initialises_and_runs_lifespan(client) -> None:
    resources = client.app.state.resources
    assert resources.database is not None
    assert resources.settings.app_env == "test"


def test_openapi_docs_available(client) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    for path in ["/health", "/support", "/ingest", "/handoffs", "/sources", "/audit/{trace_id}"]:
        assert path in schema["paths"]
    answer_types = schema["components"]["schemas"]["AnswerType"]["enum"]
    assert set(answer_types) == {
        "answered",
        "clarification_needed",
        "escalated",
        "not_found",
        "refused",
        "out_of_scope",
    }


def test_unknown_route_returns_structured_404(client) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["trace_id"] == response.headers["X-Trace-Id"]


def test_cors_allows_streamlit_origin(client) -> None:
    response = client.options(
        "/support",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-account-id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8501"


def test_cors_rejects_unknown_origin(client) -> None:
    response = client.options(
        "/support",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
