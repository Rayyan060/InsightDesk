"""Component health checks used by ``GET /health``.

Every status is the result of a real check performed at request time:

* ``healthy``        - the component answered a live probe.
* ``unavailable``    - configured, but the probe failed (down, unreachable, error).
* ``not_configured`` - no configuration provided, or a required setup step is
                       missing (e.g. the Ollama model has not been pulled).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from app import __version__
from app.core.lifecycle import AppResources
from app.database.models import missing_mandatory_tables
from app.rag.vector_store import check_chroma
from app.schemas.health import ComponentHealth, ComponentStatus, HealthResponse, OverallStatus


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


async def check_sqlite(resources: AppResources) -> ComponentHealth:
    if resources.settings.database_url is None:
        return ComponentHealth(status=ComponentStatus.NOT_CONFIGURED, detail="DATABASE_URL is not set.")
    if resources.database is None:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail=f"Database failed to initialise ({resources.database_error or 'unknown error'}).",
        )

    started = time.perf_counter()
    timeout = resources.settings.health_check_timeout_seconds
    try:
        status = await asyncio.wait_for(asyncio.to_thread(resources.database.check), timeout)
    except asyncio.TimeoutError:
        return ComponentHealth(status=ComponentStatus.UNAVAILABLE, detail="Query timed out.", latency_ms=_ms(started))

    if not status.connected:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail=f"Query failed ({status.error}).",
            latency_ms=_ms(started),
        )
    if status.schema_problems:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail=f"Connected, but the schema does not match Annex C ({len(status.schema_problems)} problems).",
            latency_ms=_ms(started),
            metadata={"schema_problems": status.schema_problems},
        )
    if not status.foreign_keys_enabled:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail="Connected, but foreign-key enforcement is disabled.",
            latency_ms=_ms(started),
        )
    return ComponentHealth(
        status=ComponentStatus.HEALTHY,
        detail="SELECT 1 succeeded; foreign keys enforced.",
        latency_ms=_ms(started),
        metadata={
            "foreign_keys_enabled": True,
            "mandatory_tables_missing": missing_mandatory_tables(status.existing_tables),
            "schema_status": "matches_annex_c" if not status.schema_problems else "mismatch",
            "schema_problems": status.schema_problems,
            "row_counts": status.row_counts,
        },
    )


async def check_chromadb(resources: AppResources) -> ComponentHealth:
    if resources.settings.chroma_persist_dir is None:
        return ComponentHealth(status=ComponentStatus.NOT_CONFIGURED, detail="CHROMA_PERSIST_DIR is not set.")
    if resources.chroma_client is None:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail=f"Chroma client failed to initialise ({resources.chroma_error or 'unknown error'}).",
        )

    started = time.perf_counter()
    try:
        status = await asyncio.wait_for(
            asyncio.to_thread(check_chroma, resources.chroma_client),
            resources.settings.health_check_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return ComponentHealth(status=ComponentStatus.UNAVAILABLE, detail="Heartbeat timed out.", latency_ms=_ms(started))

    if not status.reachable:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail=f"Heartbeat failed ({status.error}).",
            latency_ms=_ms(started),
        )
    return ComponentHealth(
        status=ComponentStatus.HEALTHY,
        detail="Heartbeat succeeded.",
        latency_ms=_ms(started),
        metadata={"collection_count": status.collection_count},
    )


async def check_ollama(resources: AppResources) -> ComponentHealth:
    settings = resources.settings
    if settings.ollama_base_url is None or resources.ollama is None:
        return ComponentHealth(status=ComponentStatus.NOT_CONFIGURED, detail="OLLAMA_BASE_URL is not set.")

    started = time.perf_counter()
    status = await resources.ollama.status(timeout_seconds=settings.health_check_timeout_seconds)
    if not status.reachable:
        return ComponentHealth(
            status=ComponentStatus.UNAVAILABLE,
            detail=f"Ollama server unreachable ({status.error}).",
            latency_ms=_ms(started),
            metadata={"model": settings.ollama_model},
        )
    if not status.model_available:
        return ComponentHealth(
            status=ComponentStatus.NOT_CONFIGURED,
            detail=f"Ollama is reachable but model '{settings.ollama_model}' is not pulled "
            f"(run: ollama pull {settings.ollama_model}).",
            latency_ms=_ms(started),
            metadata={"model": settings.ollama_model, "available_models": status.available_models},
        )
    return ComponentHealth(
        status=ComponentStatus.HEALTHY,
        detail="Server reachable and model available.",
        latency_ms=_ms(started),
        metadata={"model": settings.ollama_model},
    )


async def build_health_report(resources: AppResources, trace_id: str | None) -> HealthResponse:
    sqlite, chroma, ollama = await asyncio.gather(
        check_sqlite(resources), check_chromadb(resources), check_ollama(resources)
    )
    components = {
        # The API is healthy by construction: this code is running inside a request.
        "api": ComponentHealth(status=ComponentStatus.HEALTHY, detail="Serving requests."),
        "sqlite": sqlite,
        "chromadb": chroma,
        "ollama": ollama,
    }
    overall = (
        OverallStatus.OK
        if all(c.status is ComponentStatus.HEALTHY for c in components.values())
        else OverallStatus.DEGRADED
    )
    return HealthResponse(
        status=overall,
        app_name=resources.settings.app_name,
        version=__version__,
        environment=resources.settings.app_env,
        checked_at=datetime.now(timezone.utc),
        components=components,
        trace_id=trace_id,
    )
