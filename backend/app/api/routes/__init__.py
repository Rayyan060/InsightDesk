from fastapi import APIRouter

from app.api.routes import audit, conversations, handoffs, health, ingest, sources, support

api_router = APIRouter()
for _module in (health, support, ingest, conversations, handoffs, audit, sources):
    api_router.include_router(_module.router)

__all__ = ["api_router"]
