from typing import Any, Dict, Optional

from .providers.execution_layer import execute_provider_render
from .providers.config import get_provider_config, resolve_default_provider
from .providers.config_surface import build_provider_config_snapshot
from .providers.credentials import get_provider_credential_state
from .providers.selection_state import build_provider_selection_state
from .providers.selection_request import normalize_selection_request
from .providers.selection_state import resolve_provider_selection
from .providers.readiness_summary import build_provider_readiness_summary
from .providers.selection_contract import build_manual_provider_selection_contract
from .providers.capabilities import build_provider_capability
from .providers.safety_contract import build_provider_safety_contract
from .providers.failure_model import normalize_provider_result


def execute_render(
    provider_payload: Any,
    provider_name: str = "mock",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Thin render execution wrapper delegating all provider logic
    to the isolated execution layer.
    """
    return normalize_provider_result(
        execute_provider_render(provider_name, provider_payload, config),
        provider_name if isinstance(provider_name, str) else "mock",
    )


def get_render_provider_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return deterministic provider config with safe fallback."""
    if isinstance(config, dict):
        return dict(config)
    return get_provider_config()


def get_render_default_provider(config: Optional[Dict[str, Any]] = None) -> str:
    """Resolve default provider from config with safe fallback to mock."""
    provider_config = get_render_provider_config(config)
    return resolve_default_provider(provider_config)


def get_render_provider_config_snapshot(
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return read-only provider config snapshot."""
    provider_config = get_render_provider_config(config)
    return build_provider_config_snapshot(provider_config)


def get_render_provider_credential_state(
    provider_name: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return provider credential presence state with no secret material."""
    provider_config = get_render_provider_config(config)
    return get_provider_credential_state(provider_name, provider_config)


def get_render_provider_selection_state(
    requested_provider: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return provider selection state with deterministic fallback."""
    provider_config = get_render_provider_config(config)
    return build_provider_selection_state(requested_provider, provider_config)


def get_render_selection_request(requested_provider: Optional[str]) -> Dict[str, Any]:
    """Return normalized selection request schema."""
    return normalize_selection_request(requested_provider)


def resolve_render_provider_selection(
    requested_provider: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve provider selection metadata without executing providers."""
    provider_config = get_render_provider_config(config)
    return resolve_provider_selection(requested_provider, provider_config)


def get_render_provider_readiness_summary(
    provider_name: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return provider readiness summary with execution blocked by design."""
    provider_config = get_render_provider_config(config)
    return build_provider_readiness_summary(provider_name, provider_config)


def get_render_provider_capability(
    provider_name: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return provider capability contract metadata."""
    provider_config = get_render_provider_config(config)
    return build_provider_capability(provider_name, provider_config)


def get_render_provider_control_contract() -> Dict[str, Any]:
    """Return static manual-only provider control contract."""
    return build_manual_provider_selection_contract()


def get_render_provider_safety_contract() -> Dict[str, Any]:
    """Return static real-provider execution safety boundary contract."""
    return build_provider_safety_contract()
