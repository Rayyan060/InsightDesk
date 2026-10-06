"""Request/response contract for ``POST /support`` (guide Section 6, 6.1, 6.2, Annex D).

Request (Section 6): header ``X-Account-Id`` identifies the customer. Body:
``message`` plus optional ``conversation_id``, ``channel``,
``product_version`` and ``as_of_date`` (YYYY-MM-DD, defaults to today).

There is deliberately **no** ``account_id`` body field (R8: the account comes
only from the header). Unknown fields are ignored, so a client that sends one
gets no account context from it.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

from app.core.security import IDENTIFIER_PATTERN
from app.schemas.handoff import HandoffBundle
from app.schemas.tools import ToolInvocation

MAX_MESSAGE_CHARS = 4000


class AnswerType(str, Enum):
    """Section 6.2."""

    ANSWERED = "answered"
    CLARIFICATION_NEEDED = "clarification_needed"
    ESCALATED = "escalated"
    NOT_FOUND = "not_found"
    REFUSED = "refused"
    OUT_OF_SCOPE = "out_of_scope"


class SupportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS, description="Customer message. Never logged verbatim.")
    conversation_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    channel: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]{0,31}$", description="e.g. web, email, chat")
    product_version: str | None = Field(
        default=None, pattern=r"^\d+(\.\d+){0,2}$", description="Customer-stated product version, e.g. 4.3"
    )
    as_of_date: date | None = Field(default=None, description="YYYY-MM-DD; the server uses today's date when omitted.")


# --- intent (R1) ------------------------------------------------------------
class IntentType(str, Enum):
    HOW_TO = "how_to"
    TROUBLESHOOTING = "troubleshooting"
    ACCOUNT = "account"
    BILLING = "billing"
    COMPLAINT = "complaint"
    SECURITY = "security"
    OUT_OF_SCOPE = "out_of_scope"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    ANGRY = "angry"


class IntentInfo(BaseModel):
    type: IntentType
    urgency: Urgency
    sentiment: Sentiment
    pii_detected: bool
    confidence: float = Field(ge=0, le=1)
    product_version: str | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_product_version(self, handler):  # type: ignore[no-untyped-def]
        # Keep the exact Section 6.1 shape when the version is unknown.
        data = handler(self)
        if data.get("product_version") is None:
            data.pop("product_version", None)
        return data


# --- citations (R3) ---------------------------------------------------------
class DocType(str, Enum):
    """Annex B doc_type values."""

    ARTICLE = "article"
    POLICY = "policy"
    RELEASE_NOTE = "release_note"
    TICKET = "ticket"
    COMMUNITY = "community"


class Citation(BaseModel):
    source_id: str
    doc_type: DocType
    section: str | None = None
    product_versions: str | None = Field(default=None, description="e.g. 4.2+ or 3.x")
    last_updated: date | None = None


# --- critic (R4) ------------------------------------------------------------
class CriticDecision(str, Enum):
    ANSWER = "answer"
    REVISE = "revise"
    ESCALATE = "escalate"


class CriticReport(BaseModel):
    groundedness: float = Field(ge=0, le=1)
    coverage: str = Field(description="e.g. complete, partial, none")
    pii_risk: str = Field(description="e.g. none, low, high")
    policy_risk: str = Field(description="e.g. none, low, high")
    decision: CriticDecision
    revisions: int = Field(default=0, ge=0, le=1, description="R4: at most one revision.")


class ConflictRecord(BaseModel):
    """A source conflict resolved (or not) by the Annex A precedence rules."""

    description: str
    source_ids: list[str] = Field(default_factory=list)
    resolution: str | None = None


class SupportResponse(BaseModel):
    trace_id: str
    conversation_id: str
    answer_type: AnswerType
    answer: str
    intent: IntentInfo | None = None
    citations: list[Citation] = Field(default_factory=list)
    tools_invoked: list[ToolInvocation] = Field(default_factory=list)
    critic: CriticReport | None = None
    conflicts_detected: list[ConflictRecord] = Field(default_factory=list)
    handoff_id: str | None = None
    handoff: HandoffBundle | None = Field(default=None, description="Present when escalated (Annex D).")
    as_of_date: date

    @field_validator("answer")
    @classmethod
    def _answer_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value

    @model_validator(mode="after")
    def _escalation_requires_handoff(self) -> "SupportResponse":
        if self.answer_type is AnswerType.ESCALATED and not (self.handoff_id and self.handoff):
            raise ValueError("handoff_id and handoff bundle are required when answer_type is 'escalated'")
        if self.answer_type is not AnswerType.ESCALATED and self.handoff is not None:
            raise ValueError("a handoff bundle is only present when answer_type is 'escalated'")
        return self
