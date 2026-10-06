"""5 + 9: request validation, account context, size limits, and no fabricated answers."""

from __future__ import annotations

import pytest

SENTINEL = "PII-SENTINEL-7f3a9c"


def _assert_grounded_or_safe(body: dict) -> None:
    """/support never fabricates: an answer cites its sources inline; anything else is an explicit non-answer."""
    from app.schemas.support import SupportResponse

    response = SupportResponse.model_validate(body)
    if response.answer_type.value == "answered":
        assert response.citations, "an answer must cite its sources"
        for citation in response.citations:
            assert f"[{citation.source_id}]" in response.answer
    else:
        assert response.answer_type.value in {"refused", "not_found", "clarification_needed"}


def test_support_valid_request_returns_grounded_response(client) -> None:
    response = client.post(
        "/support",
        json={"message": "Why was I charged twice?", "conversation_id": "conv-1", "as_of_date": "2025-01-31"},
        headers={"X-Account-Id": "ACC-0001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trace_id"] == response.headers["X-Trace-Id"]
    assert (body["conversation_id"], body["as_of_date"]) == ("conv-1", "2025-01-31")
    _assert_grounded_or_safe(body)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/ingest", {}),
        ("get", "/handoffs", None),
        ("get", "/handoffs/HO-1", None),
        ("get", "/conversations/conv-1", None),
        ("get", "/audit/0123456789abcdef", None),
    ],
)
def test_other_unimplemented_endpoints_return_501(client, method, path, payload) -> None:
    response = client.request(method.upper(), path, json=payload)
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert set(body) == {"error", "trace_id"}


def test_missing_message_is_422(client) -> None:
    response = client.post("/support", json={"conversation_id": "c1"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert any(detail["loc"] == ["body", "message"] for detail in body["error"]["details"])


@pytest.mark.parametrize("message", ["", "    ", "\n\t"])
def test_blank_message_is_422(client, message) -> None:
    assert client.post("/support", json={"message": message}).status_code == 422


def test_message_over_char_limit_is_422_and_not_echoed(client) -> None:
    response = client.post("/support", json={"message": SENTINEL + "x" * 4100})
    assert response.status_code == 422
    assert SENTINEL not in response.text
    assert all(set(d) == {"loc", "msg", "type"} for d in response.json()["error"]["details"])


def test_invalid_as_of_date_is_422(client) -> None:
    assert client.post("/support", json={"message": "hi", "as_of_date": "31/01/2025"}).status_code == 422


def test_invalid_conversation_id_is_422(client) -> None:
    assert client.post("/support", json={"message": "hi", "conversation_id": "../etc/passwd"}).status_code == 422


def test_malformed_json_is_422(client) -> None:
    response = client.post("/support", content=b"{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_fields_are_ignored_for_compatibility(client) -> None:
    response = client.post("/support", json={"message": "hi", "channel": "web"})
    assert response.status_code == 200
    _assert_grounded_or_safe(response.json())


@pytest.mark.parametrize("header", ["bad id with spaces", "x" * 65, "-leading-dash", "acc;drop"])
def test_malformed_account_header_is_400(client, header) -> None:
    response = client.post("/support", json={"message": "hi"}, headers={"X-Account-Id": header})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_account_context"
    assert header not in body["error"]["message"]


def test_body_account_id_is_ignored_r8(client) -> None:
    # R8: the account comes only from X-Account-Id. A body account_id is not part of
    # the contract and is ignored (it can neither set nor contradict the header).
    response = client.post(
        "/support", json={"message": "hi", "account_id": "A1002"}, headers={"X-Account-Id": "A1001"}
    )
    assert response.status_code == 200
    malformed_body_id = client.post("/support", json={"message": "hi", "account_id": "not valid!"})
    assert malformed_body_id.status_code == 200  # ignored, so it cannot be "malformed"


def test_section_6_optional_body_fields_accepted(client) -> None:
    response = client.post(
        "/support",
        json={"message": "hi", "conversation_id": "C-0192", "channel": "web", "product_version": "4.3", "as_of_date": "2026-10-06"},
        headers={"X-Account-Id": "A1001"},
    )
    assert response.status_code == 200
    _assert_grounded_or_safe(response.json())


def test_invalid_product_version_is_422(client) -> None:
    assert client.post("/support", json={"message": "hi", "product_version": "latest"}).status_code == 422


def test_account_context_is_optional(client) -> None:
    response = client.post("/support", json={"message": "What are your plans?"})
    assert response.status_code == 200
    _assert_grounded_or_safe(response.json())


def test_oversized_body_rejected_by_content_length(make_settings, build_client) -> None:
    client = build_client(make_settings(max_request_bytes=2048))
    response = client.post("/support", json={"message": "a" * 3000})
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "payload_too_large"
    assert body["trace_id"] == response.headers["X-Trace-Id"]


def test_oversized_streamed_body_rejected(make_settings, build_client) -> None:
    client = build_client(make_settings(max_request_bytes=2048))

    def chunks():
        for _ in range(4):
            yield b"a" * 1024

    response = client.post("/support", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_streamed_body_under_limit_reaches_route(make_settings, build_client) -> None:
    client = build_client(make_settings(max_request_bytes=2048))

    def chunks():
        yield b'{"message": '
        yield b'"hello"}'

    response = client.post("/support", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 200  # parsed and validated after replay
