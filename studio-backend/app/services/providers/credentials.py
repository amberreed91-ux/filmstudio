from __future__ import annotations

import os
from typing import Any, Dict

from .config import is_provider_config_enabled


def _normalize_provider_name(provider_name: Any) -> str:
    if isinstance(provider_name, str) and provider_name.strip():
        return provider_name.strip().lower()
    return "mock"


def _provider_credential_config(provider: str, config: Dict[str, Any]) -> Dict[str, Any] | None:
    root = config.get("provider_credentials")
    if not isinstance(root, dict):
        return None
    provider_cfg = root.get(provider)
    if not isinstance(provider_cfg, dict):
        return None
    return provider_cfg


def _is_present_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _detect_credential_source(provider: str, config: Dict[str, Any]) -> tuple[bool, str]:
    provider_cfg = _provider_credential_config(provider, config)
    if not provider_cfg:
        return False, "none"

    env_var = provider_cfg.get("env_var")
    if isinstance(env_var, str) and env_var.strip():
        if bool(os.getenv(env_var.strip())):
            return True, "env"

    for key in ("credential", "api_key", "token", "secret", "placeholder"):
        if key in provider_cfg and _is_present_value(provider_cfg.get(key)):
            return True, "config_present"

    return False, "none"


def get_provider_credential_state(provider_name: Any, config: Any) -> Dict[str, Any]:
    """Return provider credential state without exposing credential material."""
    provider = _normalize_provider_name(provider_name)
    cfg = config if isinstance(config, dict) else {}

    if provider == "mock":
        return {
            "provider": "mock",
            "enabled": True,
            "credential_present": True,
            "credential_source": "none",
            "reason": "Mock provider does not require credentials",
        }

    enabled = is_provider_config_enabled(provider, cfg)
    if not enabled:
        return {
            "provider": provider,
            "enabled": False,
            "credential_present": False,
            "credential_source": "none",
            "reason": "Provider disabled by config",
        }

    credential_present, credential_source = _detect_credential_source(provider, cfg)
    if credential_present:
        return {
            "provider": provider,
            "enabled": True,
            "credential_present": True,
            "credential_source": credential_source,
            "reason": "Provider credentials available",
        }

    return {
        "provider": provider,
        "enabled": True,
        "credential_present": False,
        "credential_source": "none",
        "reason": "Provider credentials missing",
    }
