from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ResourcesDep, TraceIdDep
from app.schemas.health import HealthResponse, LivenessResponse
from app.services.health import build_health_report

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Component readiness",
    description=(
        "Probes the API, SQLite, ChromaDB and Ollama. Each component reports "
        "`healthy`, `unavailable` or `not_configured`. Overall status is `ok` only "
        "when every component is healthy, otherwise `degraded`. Always HTTP 200 so "
        "the report itself is readable when dependencies are down."
    ),
)
async def health(resources: ResourcesDep, trace_id: TraceIdDep) -> HealthResponse:
    return await build_health_report(resources, trace_id)


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Cheap process liveness check with no dependency probes. Used by the Docker HEALTHCHECK.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()
