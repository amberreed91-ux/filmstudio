from __future__ import annotations

from typing import Any, Dict

from .base import RenderProvider
from .config import is_provider_config_enabled
from .mock_provider import MockProvider
from .real_provider_stub import RealProviderStub


class ProviderRegistry:
    """In-memory provider registry with deterministic lookup behavior."""

    def __init__(self) -> None:
        self._providers: Dict[str, RenderProvider] = {}

    def register_provider(self, name: str, provider: RenderProvider) -> None:
        normalized_name = name.strip().lower() if isinstance(name, str) else ""
        if not normalized_name:
            raise ValueError("Provider name must be a non-empty string")
        if not isinstance(provider, RenderProvider):
            raise ValueError("Provider must implement RenderProvider")
        self._providers[normalized_name] = provider

    def get_provider(self, name: str) -> RenderProvider:
        normalized_name = name.strip().lower() if isinstance(name, str) else ""
        provider = self._providers.get(normalized_name)
        if provider is None:
            raise ValueError(f"Unknown provider: {name}")
        return provider

    def list_provider_names(self) -> list[str]:
        return list(self._providers.keys())


def build_default_registry(config: Any = None) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_provider("mock", MockProvider())
    config_obj = config if isinstance(config, dict) else {}
    if is_provider_config_enabled("real_stub", config_obj):
        registry.register_provider("real_stub", RealProviderStub(config_obj))
    return registry
