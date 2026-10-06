"""Handoff bundle (Annex D) and handoff API models.

The ``handoffs`` table (Annex C) stores the bundle as ``bundle_json``, with
PII redacted. ``GET /handoffs/{id}`` returns the full bundle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HandoffPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class HandoffQueue(str, Enum):
    """Queues used by the escalation policy. Annex C gives billing, technical, security as examples."""

    BILLING = "billing"
    TECHNICAL = "technical"
    SECURITY = "security"
    ACCOUNT = "account"
    LEGAL = "legal"
    GENERAL = "general"


class ToolEvidence(BaseModel):
    """Evidence from a tool call, e.g. ``{"tool": "get_invoices", "output": [...]}``."""

    model_config = ConfigDict(extra="forbid")
    tool: str
    output: Any


class SourceEvidence(BaseModel):
    """Evidence from a knowledge-base source, e.g. ``{"source_id": "KB-BIL-003", "section": "..."}``."""

    model_config = ConfigDict(extra="forbid")
    source_id: str
    section: str | None = None


class HandoffBundle(BaseModel):
    """Annex D handoff bundle: everything a human needs, with PII redacted."""

    queue: HandoffQueue
    priority: HandoffPriority
    intent: str = Field(description="Fine-grained intent, e.g. billing_dispute.")
    urgency: str
    sentiment: str
    escalation_reasons: list[str] = Field(min_length=1, description="Escalation policy reasons / rule IDs.")
    customer_summary: str
    evidence: list[ToolEvidence | SourceEvidence] = Field(default_factory=list)
    attempted_answer: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    pii_redacted: bool

    @model_validator(mode="after")
    def _must_be_redacted(self) -> "HandoffBundle":
        if not self.pii_redacted:
            raise ValueError("handoff bundles must be PII-redacted before they are stored or returned (R9)")
        return self


class HandoffRecord(BaseModel):
    """``GET /handoffs/{id}``: the stored row with its bundle."""

    handoff_id: str
    conversation_id: str | None = None
    account_id: str | None = None
    queue: str
    priority: HandoffPriority
    created_at: datetime
    bundle: HandoffBundle


class HandoffSummary(BaseModel):
    handoff_id: str
    conversation_id: str | None = None
    queue: str
    priority: HandoffPriority
    created_at: datetime


class HandoffList(BaseModel):
    items: list[HandoffSummary]
    total: int
