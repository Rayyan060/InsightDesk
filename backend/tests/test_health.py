"""3: /health returns valid, honest, structured output."""

from __future__ import annotations

import httpx
import pytest

from app.database.models import MANDATORY_TABLES
from app.schemas.health import HealthResponse


def _tags_handler(models: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": m} for m in models]})

    return handler


def test_health_structure_and_sqlite_probe(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    report = HealthResponse.model_validate(response.json())

    assert set(report.components) == {"api", "sqlite", "chromadb", "ollama"}
    assert report.components["api"].status == "healthy"
    assert report.trace_id == response.headers["X-Trace-Id"]

    sqlite = report.components["sqlite"]
    assert sqlite.status == "healthy"
    assert sqlite.metadata["foreign_keys_enabled"] is True
    # Verified against the Annex C transcription, not assumed.
    assert sqlite.metadata["schema_status"] == "matches_annex_c"
    assert sqlite.metadata["schema_problems"] == []
    assert sqlite.metadata["mandatory_tables_missing"] == []
    assert set(sqlite.metadata["row_counts"]) == set(MANDATORY_TABLES)
    # Reference data is seeded at startup (idempotently).
    assert sqlite.metadata["row_counts"]["plan_limits"] == 4


def test_blank_configuration_reports_not_configured(make_settings, build_client) -> None:
    client = build_client(make_settings(database_url="", chroma_persist_dir="", ollama_base_url=""))
    report = client.get("/health").json()
    for name in ("sqlite", "chromadb", "ollama"):
        assert report["components"][name]["status"] == "not_configured", name
    assert report["status"] == "degraded"


def test_sqlite_unavailable_when_path_unusable(make_settings, build_client, tmp_path) -> None:
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("x")
    bad_url = f"sqlite:///{(blocker / 'db.sqlite').as_posix()}"
    client = build_client(make_settings(database_url=bad_url))
    sqlite = client.get("/health").json()["components"]["sqlite"]
    assert sqlite["status"] == "unavailable"


def test_ollama_unreachable_is_unavailable(make_settings, build_client, ollama_transport) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    ollama_transport(httpx.MockTransport(refuse))
    client = build_client(make_settings(ollama_base_url="http://ollama.test:11434"))
    ollama = client.get("/health").json()["components"]["ollama"]
    assert ollama["status"] == "unavailable"
    assert "ConnectError" in ollama["detail"]


def test_ollama_healthy_when_model_present(make_settings, build_client, ollama_transport) -> None:
    ollama_transport(httpx.MockTransport(_tags_handler(["qwen2.5:7b", "llama3.2:3b"])))
    client = build_client(make_settings(ollama_base_url="http://ollama.test:11434", ollama_model="qwen2.5:7b"))
    ollama = client.get("/health").json()["components"]["ollama"]
    assert ollama["status"] == "healthy"


def test_ollama_model_not_pulled_is_not_configured(make_settings, build_client, ollama_transport) -> None:
    ollama_transport(httpx.MockTransport(_tags_handler(["llama3.2:3b"])))
    client = build_client(make_settings(ollama_base_url="http://ollama.test:11434", ollama_model="qwen2.5:7b"))
    ollama = client.get("/health").json()["components"]["ollama"]
    assert ollama["status"] == "not_configured"
    assert "ollama pull qwen2.5:7b" in ollama["detail"]


def test_ollama_server_error_is_unavailable(make_settings, build_client, ollama_transport) -> None:
    ollama_transport(httpx.MockTransport(lambda request: httpx.Response(500)))
    client = build_client(make_settings(ollama_base_url="http://ollama.test:11434"))
    assert client.get("/health").json()["components"]["ollama"]["status"] == "unavailable"


def test_chromadb_probe_when_configured(make_settings, build_client, tmp_path) -> None:
    pytest.importorskip("chromadb")
    client = build_client(make_settings(chroma_persist_dir=str(tmp_path / "chroma")))
    chroma = client.get("/health").json()["components"]["chromadb"]
    assert chroma["status"] == "healthy"
    assert chroma["metadata"]["collection_count"] == 0


def test_overall_ok_only_when_everything_healthy(make_settings, build_client, ollama_transport, tmp_path) -> None:
    pytest.importorskip("chromadb")
    ollama_transport(httpx.MockTransport(_tags_handler(["qwen2.5:7b"])))
    client = build_client(
        make_settings(
            chroma_persist_dir=str(tmp_path / "chroma"),
            ollama_base_url="http://ollama.test:11434",
        )
    )
    report = client.get("/health").json()
    assert {c["status"] for c in report["components"].values()} == {"healthy"}
    assert report["status"] == "ok"


def test_liveness(client) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
