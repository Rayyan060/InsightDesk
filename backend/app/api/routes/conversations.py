from __future__ import annotations

from fastapi import APIRouter, Path

from app.core.exceptions import NotImplementedFeatureError
from app.core.security import IDENTIFIER_PATTERN
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get(
    "/{conversation_id}",
    summary="Conversation history",
    description="**Returns HTTP 501 until Phase 4** (conversation persistence).",
    responses={501: {"model": ErrorResponse}},
)
async def get_conversation(
    conversation_id: str = Path(pattern=IDENTIFIER_PATTERN),
) -> None:
    raise NotImplementedFeatureError("GET /conversations/{conversation_id}", planned_phase="Phase 4")
