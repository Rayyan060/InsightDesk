from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import NotImplementedFeatureError
from app.schemas.common import ErrorResponse
from app.schemas.ingestion import IngestRequest, IngestResponse

router = APIRouter(tags=["ingestion"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Index the knowledge base",
    description="**Returns HTTP 501 until Phase 3** (chunking, embeddings, ChromaDB indexing).",
    responses={501: {"model": ErrorResponse}},
)
async def ingest(payload: IngestRequest) -> IngestResponse:
    raise NotImplementedFeatureError("POST /ingest", planned_phase="Phase 3")
