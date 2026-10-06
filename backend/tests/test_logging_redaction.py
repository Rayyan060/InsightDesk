"""10: logs never expose customer messages, credentials or PII."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI

from app.core.security import redact, scrub_text

MESSAGE_SENTINEL = "CUSTOMER-SECRET-MESSAGE-91c2"
ACCOUNT_SENTINEL = "ACC-SENTINEL-5531"
PASSWORD = "hunter2-PW-sentinel"
EMAIL = "jane.doe@example.com"
PHONE = "+1 (415) 555-0199"
CARD = "4111 1111 1111 1111"


def _records(stream) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_scrub_text_masks_pii_and_secrets() -> None:
    text = f"email {EMAIL} phone {PHONE} card {CARD} password={PASSWORD} Bearer abc.def.ghi"
    scrubbed = scrub_text(text)
    for secret in (EMAIL, PHONE, CARD, PASSWORD, "abc.def.ghi"):
        assert secret not in scrubbed


def test_scrub_text_keeps_trace_ids_and_numbers() -> None:
    text = "trace 3f2a9c1b0d4e5f60718293a4b5c6d7e8 took 1234 ms"
    assert scrub_text(text) == text


def test_redact_removes_sensitive_keys_recursively() -> None:
    data = {
        "message": MESSAGE_SENTINEL,
        "nested": {"api_key": "k-123", "access_token": "tok", "account_id": ACCOUNT_SENTINEL},
        "prompt_tokens": 12,
        "status_code": 200,
    }
    result = redact(data)
    dumped = json.dumps(result)
    assert MESSAGE_SENTINEL not in dumped and "k-123" not in dumped and ACCOUNT_SENTINEL not in dumped
    assert result["prompt_tokens"] == 12 and result["status_code"] == 200


def test_formatter_redacts_extras_message_and_exception(log_output) -> None:
    logger = logging.getLogger("insightdesk.test")
    logger.info(
        "user %s called from %s",
        EMAIL,
        PHONE,
        extra={"customer_message": MESSAGE_SENTINEL, "password": PASSWORD, "account_id": ACCOUNT_SENTINEL},
    )
    try:
        raise ValueError(f"bad card {CARD} password={PASSWORD}")
    except ValueError:
        logger.exception("failure")

    output = log_output.getvalue()
    for secret in (MESSAGE_SENTINEL, PASSWORD, ACCOUNT_SENTINEL, EMAIL, PHONE, CARD):
        assert secret not in output, secret
    records = _records(log_output)
    assert records[0]["context"]["customer_message"] == "[REDACTED]"
    assert "exception" in records[1]


def test_request_logs_do_not_contain_message_or_account(make_settings, build_client, log_output) -> None:
    client = build_client(make_settings())
    payload = {"message": f"{MESSAGE_SENTINEL} my email is {EMAIL}, password={PASSWORD}"}
    client.post("/support", json=payload, headers={"X-Account-Id": ACCOUNT_SENTINEL})
    client.post("/support", json={"message": MESSAGE_SENTINEL * 200})  # validation failure path
    client.post("/support?token=QUERY-SECRET", json=payload)

    output = log_output.getvalue()
    for secret in (MESSAGE_SENTINEL, EMAIL, PASSWORD, ACCOUNT_SENTINEL, "QUERY-SECRET"):
        assert secret not in output, secret

    completed = [r for r in _records(log_output) if r["message"] == "request_completed"]
    assert len(completed) == 3
    assert all(r["trace_id"] for r in completed)
    assert {r["context"]["status_code"] for r in completed} == {200, 422}


def test_crash_logs_are_scrubbed(make_settings, build_client, log_output) -> None:
    def add_route(app: FastAPI) -> None:
        @app.get("/_crash")
        async def crash() -> None:
            raise RuntimeError(f"failed for {EMAIL} with password={PASSWORD}")

    client = build_client(make_settings(), configure=add_route)
    assert client.get("/_crash").status_code == 500
    output = log_output.getvalue()
    assert "unhandled_exception" in output
    assert EMAIL not in output and PASSWORD not in output
