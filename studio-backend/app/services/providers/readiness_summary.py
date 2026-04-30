from __future__ import annotations

from typing import Any, Dict

from .capabilities import build_provider_capability
from .config import is_provider_config_enabled
from .credentials import get_provider_credential_state


def _normalize_provider_name(provider_name: Any) -> str:
    if isinstance(provider_name, str) and provider_name.strip():
        return provider_name.strip().lower()
    return "mock"


def build_provider_readiness_summary(provider_name: Any, config: Any) -> Dict[str, Any]:
    """
    Build deterministic provider readiness summary with no execution side effects.
    """
    provider = _normalize_provider_name(provider_name)
    config_object = config if isinstance(config, dict) else {}
    capability = build_provider_capability(provider, config_object)
    credential_state = get_provider_credential_state(provider, config_object)
    config_enabled = is_provider_config_enabled(provider, config_object)
    capability_enabled = bool(capability.get("enabled") is True)

    enabled = bool(config_enabled and capability_enabled)
    credential_present = bool(credential_state.get("credential_present") is True)
    can_execute = False

    if not enabled:
        reason = "Provider disabled by config"
    elif not credential_present:
        reason = "Missing credentials"
    elif enabled and credential_present:
        reason = "Execution not enabled"
    else:
        reason = "Provider unavailable"

    return {
        "provider": provider,
        "enabled": enabled,
        "credential_present": credential_present,
        "can_execute": can_execute,
        "reason": reason,
    }
