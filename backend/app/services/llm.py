"""Ollama client.

Phase 1 implements only connectivity/model-availability checks. Generation
(chat/structured output) is added in Phase 4 together with the agent nodes
that use it; until then ``chat`` raises ``NotImplementedFeatureError`` rather
than returning placeholder text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.exceptions import NotImplementedFeatureError


@dataclass
class OllamaStatus:
    reachable: bool
    model_available: bool = False
    available_models: list[str] = field(default_factory=list)
    error: str | None = None


def _model_matches(configured: str, installed: str) -> bool:
    """'qwen2.5:7b' matches exactly; an untagged name matches its ':latest' tag."""
    if configured == installed:
        return True
    if ":" not in configured and installed == f"{configured}:latest":
        return True
    return False


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout_seconds, transport=transport
        )

    async def status(self, *, timeout_seconds: float) -> OllamaStatus:
        """Query ``GET /api/tags``. Never raises."""
        try:
            response = await self._client.get("/api/tags", timeout=timeout_seconds)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except httpx.TimeoutException:
            return OllamaStatus(reachable=False, error="timeout")
        except httpx.HTTPStatusError as exc:
            return OllamaStatus(reachable=False, error=f"http_{exc.response.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            return OllamaStatus(reachable=False, error=type(exc).__name__)

        models = sorted(
            str(item.get("name") or item.get("model"))
            for item in payload.get("models", [])
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        )
        return OllamaStatus(
            reachable=True,
            model_available=any(_model_matches(self.model, name) for name in models),
            available_models=models,
        )

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedFeatureError("LLM generation", planned_phase="Phase 4")

    async def aclose(self) -> None:
        await self._client.aclose()
