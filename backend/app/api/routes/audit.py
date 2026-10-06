from __future__ import annotations

from fastapi import APIRouter, Path

from app.core.exceptions import NotImplementedFeatureError
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/{trace_id}",
    summary="Audit trail for a request",
    description="**Returns HTTP 501 until Phase 5** (audit persistence node).",
    responses={501: {"model": ErrorResponse}},
)
async def get_audit_trail(trace_id: str = Path(pattern=r"^[A-Za-z0-9-]{8,64}$")) -> None:
    raise NotImplementedFeatureError("GET /audit/{trace_id}", planned_phase="Phase 5")
