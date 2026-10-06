"""Security primitives: identifier validation, account context, and log redaction.

IMPORTANT: ``X-Account-Id`` is a *declared* account context supplied by the
caller (e.g. the support console). It is **not** proof of real-world identity
and is never treated as authentication. Its purpose is to make account tools
operate on an explicit, validated request field instead of an account ID the
model extracts from free-text customer messages.

R8 (participant guide): "The customer's account comes only from the
X-Account-Id header, never from the message text." There is no body field
for it and no other source of account context.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.core.exceptions import AccountContextError

# ---------------------------------------------------------------------- #
# Identifier validation
# ---------------------------------------------------------------------- #
# Conservative: alphanumerics, underscore, hyphen; 1-64 chars; must start with
# an alphanumeric. Covers the Annex C account format (A1001) and other IDs
# (conversation IDs such as C-0192). A well-formed header for an account that
# does not exist is a tool-level "account_not_found", not a 400.
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
_IDENTIFIER_RE = re.compile(IDENTIFIER_PATTERN)

ACCOUNT_ID_HEADER = "X-Account-Id"
TRACE_ID_HEADER = "X-Trace-Id"


def is_valid_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.fullmatch(value))


@dataclass(frozen=True, slots=True)
class AccountContext:
    """Validated account context for a single request.

    ``verified`` is always False in this prototype: no authentication is
    performed. Downstream code must not use this object to grant access to
    anything beyond the prototype's synthetic data.
    """

    account_id: str
    source: Literal["header"] = "header"
    verified: bool = False


def parse_account_id(raw: str | None, *, source: Literal["header"] = "header") -> AccountContext | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if not is_valid_identifier(value):
        # Do not include the rejected value in the message.
        raise AccountContextError(
            f"Account identifier from {source} is malformed. "
            "Expected 1-64 characters: letters, digits, '-' or '_'."
        )
    return AccountContext(account_id=value, source=source)



# ---------------------------------------------------------------------- #
# Redaction
# ---------------------------------------------------------------------- #
REDACTED = "[REDACTED]"

# Keys whose values are always removed from structured log data.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "message",
        "customer_message",
        "query",
        "answer",
        "draft_answer",
        "account_id",
        "x-account-id",
        "email",
        "phone",
        "address",
        "name",
        "customer_name",
        "card_number",
        "ssn",
        "password",
        "passwd",
        "credentials",
        "authorization",
        "cookie",
        "set-cookie",
    }
)
# Any key containing one of these fragments is treated as sensitive.
SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = ("password", "secret", "api_key", "apikey", "credential")
# Keys ending in "token" (access_token, refresh_token) are secrets; metric keys
# such as "prompt_tokens" are not.
SENSITIVE_KEY_SUFFIXES: tuple[str, ...] = ("token",)

_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # key=value / key: value secrets (password=..., api_key: ..., token=...)
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|api[_-]?key|token|authorization)\b(\s*[:=]\s*)(\S+)"
        ),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + REDACTED),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # Card-like numbers: 13-19 digits optionally separated by spaces/hyphens.
    (re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])"), "[NUMBER]"),
    # Phone-like numbers: 10+ digits with common separators.
    (re.compile(r"(?<![\w-])\+?\d[\d\s().-]{8,}\d(?![\w-])"), "[PHONE]"),
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in SENSITIVE_KEYS
        or any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)
        or lowered.endswith(SENSITIVE_KEY_SUFFIXES)
    )


def scrub_text(text: str) -> str:
    """Mask PII-like and secret-like substrings in free text."""
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact sensitive keys and scrub strings in a structure."""
    if _depth > 8:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(k): (REDACTED if is_sensitive_key(str(k)) else redact(v, _depth=_depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item, _depth=_depth + 1) for item in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value
