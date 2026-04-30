from __future__ import annotations

import copy
from typing import Any, Dict

from .config import is_provider_config_enabled


_DEFAULT_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "mock": {
        "provider": "mock",
        "enabled": True,
        "network_required": False,
        "supports_render": True,
        "supports_streaming": False,
        "supports_sync": True,
        "supports_multi_shot": False,
        "requires_credentials": False,
    },
    "local_image": {
        "provider": "local_image",
        "enabled": True,
        "network_required": False,
        "supports_render": True,
        "supports_streaming": False,
        "supports_sync": True,
        "supports_multi_shot": False,
        "requires_credentials": False,
    },
    "real_stub": {
        "provider": "real_stub",
        "enabled": False,
        "network_required": False,
        "supports_render": False,
        "supports_streaming": False,
        "supports_sync": False,
        "supports_multi_shot": False,
        "requires_credentials": True,
    },
}


def get_default_capabilities() -> Dict[str, Dict[str, Any]]:
    """Return deterministic baseline provider capability map."""
    return copy.deepcopy(_DEFAULT_CAPABILITIES)


def build_provider_capability(provider_name: Any, config: Any = None) -> Dict[str, Any]:
    """Build provider capability model; unknown providers are safely disabled."""
    normalized_name = (
        provider_name.strip().lower()
        if isinstance(provider_name, str) and provider_name.strip()
        else "mock"
    )

    defaults = get_default_capabilities()
    if normalized_name in defaults:
        capability = defaults[normalized_name]
        if normalized_name == "real_stub":
            capability["enabled"] = is_provider_config_enabled(
                "real_stub",
                config if isinstance(config, dict) else {},
            )
        return capability

    return {
        "provider": normalized_name,
        "enabled": False,
        "network_required": False,
        "supports_render": False,
        "supports_streaming": False,
        "supports_sync": False,
        "supports_multi_shot": False,
        "requires_credentials": False,
    }
