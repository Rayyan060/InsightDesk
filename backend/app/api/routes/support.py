from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter

from app.api.dependencies import OptionalAccountDep, ResourcesDep, TraceIdDep, get_retriever
from app.schemas.common import ErrorResponse
from app.schemas.support import SupportRequest, SupportResponse
from app.services.answering import answer_question

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])


@router.post(
    "/support",
    response_model=SupportResponse,
    response_model_exclude_none=False,
    summary="Ask the support agent",
    description=(
        "Minimal grounded flow: account context from **X-Account-Id** only → safety and account-scope guards → "
        "version-aware retrieval (Annex A precedence) → extractive answer that cites its sources. Answers come only "
        "from authoritative documentation. Unsafe requests are refused, and account-specific questions get an "
        "insufficient-evidence answer until the account tools are implemented."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Malformed X-Account-Id header."},
        413: {"model": ErrorResponse, "description": "Request body too large."},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        503: {"model": ErrorResponse, "description": "Knowledge retrieval unavailable."},
    },
)
def support(payload: SupportRequest, account: OptionalAccountDep, trace_id: TraceIdDep, resources: ResourcesDep) -> SupportResponse:
    # Sync route: FastAPI runs it in a worker thread (the embedding model may load on first use).
    retriever = get_retriever(resources)
    as_of = payload.as_of_date or date.today()
    result = answer_question(
        payload.message,
        retriever=retriever,
        account_id=account.account_id if account else None,
        product_version=payload.product_version,
        as_of=as_of,
    )
    logger.info(
        "support_answered",
        extra={"answer_type": result.answer_type.value, "citations": len(result.citations),
               "retrieved": len(result.retrieved), "retriever": retriever.backend},
    )
    return SupportResponse(
        trace_id=trace_id,
        conversation_id=payload.conversation_id or f"C-{uuid.uuid4().hex[:8]}",
        answer_type=result.answer_type,
        answer=result.answer,
        intent=None,
        citations=result.citations,
        tools_invoked=[],
        critic=None,
        conflicts_detected=[],
        handoff_id=None,
        as_of_date=as_of,
    )
