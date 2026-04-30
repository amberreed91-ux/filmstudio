from __future__ import annotations

from abc import ABC, abstractmethod

from .types import ProviderPayload, ProviderResult


class RenderProvider(ABC):
    """Provider abstraction contract for render execution."""

    name: str = "unknown"

    @abstractmethod
    def render(self, payload: ProviderPayload) -> ProviderResult:
        """Render request and return normalized provider result."""

    def execute(self, payload: ProviderPayload) -> ProviderResult:
        """
        Backward-compatible alias for render().
        Keep this as a thin passthrough to preserve earlier tests/callers.
        """
        return self.render(payload)
