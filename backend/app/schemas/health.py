"""Health-check response models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ComponentStatus(str, Enum):
    HEALTHY = "healthy"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class OverallStatus(str, Enum):
    OK = "ok"  # every component healthy
    DEGRADED = "degraded"  # API is up, at least one component is not healthy


class ComponentHealth(BaseModel):
    status: ComponentStatus
    detail: str | None = Field(default=None, description="Human-readable explanation.")
    latency_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: OverallStatus
    app_name: str
    version: str
    environment: str
    checked_at: datetime
    components: dict[str, ComponentHealth]
    trace_id: str | None = None


class LivenessResponse(BaseModel):
    status: str = "alive"
