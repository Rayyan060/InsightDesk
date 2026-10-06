"""6: every request gets a trace ID, including error responses and crashes."""

from __future__ import annotations

import re

from fastapi import FastAPI

HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_trace_id_generated_per_request(client) -> None:
    first = client.get("/health/live").headers["X-Trace-Id"]
    second = client.get("/health/live").headers["X-Trace-Id"]
    assert HEX32.fullmatch(first) and HEX32.fullmatch(second)
    assert first != second


def test_trace_id_in_error_body_matches_header(client) -> None:
    response = client.post("/support", json={})
    assert response.json()["trace_id"] == response.headers["X-Trace-Id"]


def test_well_formed_inbound_trace_id_is_propagated(client) -> None:
    response = client.get("/health/live", headers={"X-Trace-Id": "frontend-trace-0001"})
    assert response.headers["X-Trace-Id"] == "frontend-trace-0001"


def test_malformed_inbound_trace_id_is_replaced(client) -> None:
    response = client.get("/health/live", headers={"X-Trace-Id": "bad\ttrace id; injected"})
    assert HEX32.fullmatch(response.headers["X-Trace-Id"])


def test_unhandled_exception_returns_structured_500_with_trace(make_settings, build_client) -> None:
    def add_crashing_route(app: FastAPI) -> None:
        @app.get("/_crash")
        async def crash() -> None:
            raise RuntimeError("internal detail that must not leak")

    client = build_client(make_settings(), configure=add_crashing_route)
    response = client.get("/_crash")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "internal detail" not in response.text
    assert body["trace_id"] == response.headers["X-Trace-Id"]
