"""Shared state for the InsightDesk LangGraph workflow.

LangGraph merges each node's returned partial dict into this state. List fields
that accumulate across nodes (tool results, escalation reasons, audit events)
use an ``operator.add`` reducer. Everything else is last-write-wins.

Nested items reuse the public API schemas (``Citation``, ``CriticReport``,
``ToolInvocation``) where possible, so the final response can be assembled
from state without field mapping.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field

from app.schemas.support import AnswerType, Citation, ConflictRecord, CriticReport
from app.schemas.tools import ToolInvocation, ToolResult


class RequestMetadata(BaseModel):
    trace_id: str
    conversation_id: str | None = None
    received_at: datetime
    as_of_date: date | None = None


class CustomerContext(BaseModel):
    """Validated account context taken from the request, never from message text."""

    account_id: str | None = None
    account_source: str | None = None  # "header" | "body" | None
    verified: bool = False  # always False in the prototype (no authentication)


class IntentCategory(str, Enum):
    """Planned coarse intent taxonomy. Refined against the guide in Phase 4."""

    KNOWLEDGE = "knowledge"  # answerable from the knowledge base
    ACCOUNT = "account"  # needs deterministic account tools
    MIXED = "mixed"  # needs both
    HUMAN_REQUEST = "human_request"  # customer explicitly asks for a person
    OUT_OF_SCOPE = "out_of_scope"
    UNSAFE = "unsafe"  # prompt injection, abuse, disallowed request
    UNCLEAR = "unclear"  # needs clarification


class IntentResult(BaseModel):
    category: IntentCategory
    label: str | None = Field(default=None, description="Fine-grained intent, e.g. 'billing.refund'.")
    confidence: float | None = Field(default=None, ge=0, le=1)
    requires_knowledge: bool = False
    requires_tools: bool = False
    requested_tools: list[str] = Field(default_factory=list)


class RetrievedDocument(BaseModel):
    doc_id: str
    chunk_id: str
    content: str
    score: float | None = None
    version: str | None = None
    effective_date: date | None = None
    superseded: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffInfo(BaseModel):
    handoff_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    priority: str | None = None
    summary: str | None = None


class AuditEvent(BaseModel):
    node: str
    started_at: datetime
    duration_ms: float
    outcome: str  # "ok" | "error" | "skipped"
    detail: str | None = None


class AgentState(TypedDict, total=False):
    # --- Request metadata & customer context ---------------------------
    request: RequestMetadata
    customer: CustomerContext
    message: str  # raw customer message; must never be logged

    # --- Input validation ----------------------------------------------
    input_valid: bool
    validation_errors: list[str]

    # --- Intent ---------------------------------------------------------
    intent: IntentResult

    # --- Retrieval & tools ---------------------------------------------
    retrieved_documents: list[RetrievedDocument]
    conflicts_detected: list[ConflictRecord]
    tool_results: Annotated[list[ToolResult], operator.add]
    tools_invoked: Annotated[list[ToolInvocation], operator.add]

    # --- Generation & critique -----------------------------------------
    draft_answer: str
    answer_type: AnswerType
    citations: list[Citation]
    critic_feedback: Annotated[list[CriticReport], operator.add]
    revision_count: int  # revisions performed (R4: at most one), incremented by generate_answer

    # --- Policy & escalation -------------------------------------------
    policy_decision: str  # "allow" | "escalate" | "refuse"
    applied_policy_ids: list[str]
    escalation_reasons: Annotated[list[str], operator.add]
    handoff: HandoffInfo

    # --- Audit -----------------------------------------------------------
    audit_events: Annotated[list[AuditEvent], operator.add]
    audit_persisted: bool


def initial_state(
    *,
    trace_id: str,
    message: str,
    received_at: datetime,
    conversation_id: str | None = None,
    as_of_date: date | None = None,
    account_id: str | None = None,
    account_source: str | None = None,
) -> AgentState:
    """Build the starting state for one support turn."""
    return AgentState(
        request=RequestMetadata(
            trace_id=trace_id,
            conversation_id=conversation_id,
            received_at=received_at,
            as_of_date=as_of_date,
        ),
        customer=CustomerContext(account_id=account_id, account_source=account_source),
        message=message,
        retrieved_documents=[],
        conflicts_detected=[],
        tool_results=[],
        tools_invoked=[],
        citations=[],
        critic_feedback=[],
        revision_count=0,
        escalation_reasons=[],
        audit_events=[],
    )
