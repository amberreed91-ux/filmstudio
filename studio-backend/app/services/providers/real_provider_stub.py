from __future__ import annotations

from typing import Any, Dict

from .base import RenderProvider
from .credentials import get_provider_credential_state
from .types import ProviderPayload, ProviderResult


class RealProviderStub(RenderProvider):
    """
    Real-provider adapter stub.
    It never executes network/provider calls; it only reports deterministic state.
    """

    name = "real_stub"

    def __init__(self, config: Any = None) -> None:
        self._config = config if isinstance(config, dict) else {}

    def render(self, payload: ProviderPayload) -> ProviderResult:
        _ = payload
        credential_state: Dict[str, Any] = get_provider_credential_state(
            self.name, self._config
        )

        if credential_state.get("enabled") is not True:
            return {
                "render_id": None,
                "status": "failed",
                "provider": self.name,
                "error": "Real provider disabled",
                "error_code": "provider_disabled",
                "meta": {"file_path": None, "url": None},
            }

        if credential_state.get("credential_present") is not True:
            return {
                "render_id": None,
                "status": "failed",
                "provider": self.name,
                "error": "Missing credentials",
                "error_code": "missing_credentials",
                "meta": {"file_path": None, "url": None},
            }

        return {
            "render_id": None,
            "status": "failed",
            "provider": self.name,
            "error": "Execution not implemented",
            "error_code": "not_implemented",
            "meta": {"file_path": None, "url": None},
        }
