"""Shared response envelopes (errors)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    loc: list[str] = Field(default_factory=list, description="Location of the invalid field.")
    msg: str
    type: str


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code, e.g. 'not_implemented'.")
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Envelope for every non-2xx response."""

    error: ErrorBody
    trace_id: str | None = None
