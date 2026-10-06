from __future__ import annotations

from fastapi import APIRouter, Path

from app.core.exceptions import NotImplementedFeatureError
from app.core.security import IDENTIFIER_PATTERN
from app.schemas.common import ErrorResponse
from app.schemas.handoff import HandoffList, HandoffRecord

router = APIRouter(prefix="/handoffs", tags=["handoffs"])


@router.get(
    "",
    response_model=HandoffList,
    summary="List human handoffs",
    description="**Returns HTTP 501 until Phase 5** (handoffs table per Annex C, escalation engine).",
    responses={501: {"model": ErrorResponse}},
)
async def list_handoffs() -> HandoffList:
    raise NotImplementedFeatureError("GET /handoffs", planned_phase="Phase 5")


@router.get(
    "/{handoff_id}",
    response_model=HandoffRecord,
    summary="Get a handoff",
    description="**Returns HTTP 501 until Phase 5.**",
    responses={501: {"model": ErrorResponse}},
)
async def get_handoff(handoff_id: str = Path(pattern=IDENTIFIER_PATTERN)) -> HandoffRecord:
    raise NotImplementedFeatureError("GET /handoffs/{handoff_id}", planned_phase="Phase 5")
