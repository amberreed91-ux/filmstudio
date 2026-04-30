from __future__ import annotations

from typing import Any

from .base import RenderProvider
from .types import ProviderPayload, ProviderResult


class MockProvider(RenderProvider):
    """Deterministic non-network mock provider."""

    name = "mock"

    def render(self, payload: ProviderPayload) -> ProviderResult:
        shot_id: Any = payload.get("shot_id") if isinstance(payload, dict) else None

        if not isinstance(shot_id, str) or not shot_id.strip():
            return {
                "render_id": None,
                "status": "not_executed",
                "provider": self.name,
                "error": None,
                "error_code": None,
                "meta": {"file_path": None, "url": None},
            }

        cleaned_shot_id = shot_id.strip()
        return {
            "render_id": f"mock_{cleaned_shot_id}",
            "status": "success",
            "provider": self.name,
            "error": None,
            "error_code": None,
            "meta": {"file_path": None, "url": None},
        }
