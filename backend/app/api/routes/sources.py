from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import ServiceUnavailableError
from app.knowledge.documents import read_register
from app.schemas.common import ErrorResponse
from app.schemas.ingestion import SourceList

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get(
    "",
    response_model=SourceList,
    summary="Source Register",
    description="All knowledge-base articles, policies, release notes, tickets and community posts with their Annex B metadata.",
    responses={503: {"model": ErrorResponse}},
)
def list_sources() -> SourceList:
    entries, issues, _ = read_register()
    if not entries and issues:
        raise ServiceUnavailableError("The Source Register is not available.")
    items = sorted(entries, key=lambda e: (e.authority_level, e.source_id))
    return SourceList(items=items, total=len(items))
