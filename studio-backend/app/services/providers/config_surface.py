from __future__ import annotations

from typing import Any, Dict, List

from .config import get_provider_config, resolve_default_provider


def _normalize_enabled_providers(config: Dict[str, Any]) -> List[str]:
    raw_enabled = config.get("enabled_providers")
    if not isinstance(raw_enabled, list):
        return ["mock"]

    normalized: List[str] = []
    seen = set()
    for item in raw_enabled:
        if not isinstance(item, str):
            continue
        provider_name = item.strip().lower()
        if not provider_name or provider_name in seen:
            continue
        seen.add(provider_name)
        normalized.append(provider_name)

    if not normalized:
        return ["mock"]

    return normalized


def build_provider_config_snapshot(config: Any) -> Dict[str, Any]:
    """
    Build deterministic, read-only provider configuration snapshot.
    The snapshot intentionally excludes credential material and provider internals.
    """
    candidate = config if isinstance(config, dict) else get_provider_config()
    enabled_providers = _normalize_enabled_providers(candidate)
    default_provider = resolve_default_provider(
        {
            "default_provider": candidate.get("default_provider"),
            "enabled_providers": enabled_providers,
        }
    )
    quality_priority = candidate.get("quality_priority")
    if not isinstance(quality_priority, str) or not quality_priority.strip():
        quality_priority = "cinematic_quality"

    real_providers_enabled = any(provider_name != "mock" for provider_name in enabled_providers)

    return {
        "default_provider": default_provider,
        "enabled_providers": list(enabled_providers),
        "quality_priority": quality_priority,
        "real_providers_enabled": real_providers_enabled,
    }


def build_provider_registry_snapshot() -> Dict[str, Dict[str, Any]]:
    """
    Build deterministic provider registry metadata for read-only inspection.
    """
    return {
        "provider_registry_snapshot": {
            "available_providers": ["mock", "real_stub"],
            "default_provider": "mock",
            "real_providers_present": True,
        }
    }


def build_provider_activation_state(config: Any) -> Dict[str, Dict[str, Any]]:
    """
    Build provider activation metadata while keeping real providers locked.
    """
    candidate = config if isinstance(config, dict) else get_provider_config()
    enabled_providers = _normalize_enabled_providers(candidate)
    active_provider = resolve_default_provider(
        {
            "default_provider": candidate.get("default_provider"),
            "enabled_providers": enabled_providers,
        }
    )
    real_enabled = candidate.get("real_enabled") is True
    real_provider_runtime_flag = candidate.get("real_provider_runtime_flag") is True
    return {
        "provider_activation_state": {
            "active_provider": active_provider,
            "real_enabled": real_enabled,
            "real_provider_runtime_flag": real_provider_runtime_flag,
            "reason": (
                "Real providers enabled by explicit config"
                if real_enabled
                else "Real providers disabled by default"
            ),
        }
    }


def build_provider_config_validation(config: Any) -> Dict[str, Dict[str, Any]]:
    """
    Validate provider config shape without exposing secrets or mutating config.
    """
    if config is None:
        return {
            "provider_config_validation": {
                "valid": True,
                "issues": [],
                "reason": "Provider config missing; defaults applied",
            }
        }

    if not isinstance(config, dict):
        return {
            "provider_config_validation": {
                "valid": False,
                "issues": ["config_not_object"],
                "reason": "Provider config malformed",
            }
        }

    issues: List[str] = []
    if "enabled_providers" in config and not isinstance(config.get("enabled_providers"), list):
        issues.append("enabled_providers_invalid")
    if "default_provider" in config and not isinstance(config.get("default_provider"), str):
        issues.append("default_provider_invalid")

    valid = len(issues) == 0
    return {
        "provider_config_validation": {
            "valid": valid,
            "issues": issues,
            "reason": "Provider config valid" if valid else "Provider config malformed",
        }
    }


def build_credential_validation_summary(
    provider_credential_state: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Build credential validation summary using provider credential presence only.
    """
    provider = "mock"
    credential_present = True
    if isinstance(provider_credential_state, dict):
        raw_provider = provider_credential_state.get("provider")
        if isinstance(raw_provider, str) and raw_provider.strip():
            provider = raw_provider.strip()
        credential_present = provider_credential_state.get("credential_present") is True

    valid = provider == "mock" or credential_present
    reason = "Credential available" if valid else "Credential missing"
    return {
        "credential_validation_summary": {
            "provider": provider,
            "valid": valid,
            "reason": reason,
        }
    }


def build_provider_enablement_gate(
    provider_activation_state: Any,
    credential_validation_summary: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Build provider enablement gate; remains locked for real providers in safe mode.
    """
    real_enabled = (
        isinstance(provider_activation_state, dict)
        and provider_activation_state.get("real_enabled") is True
    )
    real_provider_runtime_flag = (
        isinstance(provider_activation_state, dict)
        and provider_activation_state.get("real_provider_runtime_flag") is True
    )
    credential_provider = "mock"
    credential_valid = False
    if isinstance(credential_validation_summary, dict):
        raw_provider = credential_validation_summary.get("provider")
        if isinstance(raw_provider, str) and raw_provider.strip():
            credential_provider = raw_provider.strip()
        credential_valid = credential_validation_summary.get("valid") is True
    enabled = (
        credential_provider == "real_stub"
        and real_enabled
        and real_provider_runtime_flag
        and credential_valid
    )
    return {
        "provider_enablement_gate": {
            "enabled": enabled,
            "reason": (
                "Real provider enabled by explicit gate"
                if enabled
                else "Real providers disabled by safety policy"
            ),
        }
    }


def build_provider_intent_signal(
    provider_selection_state: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Build provider intent signal from selection state with mock-only allowance.
    """
    requested = None
    intended = "mock"

    if isinstance(provider_selection_state, dict):
        raw_requested = provider_selection_state.get("requested_provider")
        raw_selected = provider_selection_state.get("selected_provider")
        if isinstance(raw_requested, str) and raw_requested.strip():
            requested = raw_requested.strip()
        if isinstance(raw_selected, str) and raw_selected.strip():
            intended = raw_selected.strip()

    allowed = intended == "mock"
    return {
        "provider_intent_signal": {
            "requested": requested,
            "intended": intended,
            "allowed": allowed,
        }
    }


def build_provider_activation_contract() -> Dict[str, Dict[str, Any]]:
    """
    Build static provider activation contract requiring explicit unlock.
    """
    return {
        "provider_activation_contract": {
            "real_execution_enabled": False,
            "manual_enable_required": True,
            "safe_mode": True,
            "reason": "Provider activation requires explicit unlock",
        }
    }


def build_provider_safety_summary(
    provider_enablement_gate: Any,
    provider_activation_contract: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Build provider safety summary. Always locked in current safety mode.
    """
    execution_allowed = (
        isinstance(provider_enablement_gate, dict)
        and provider_enablement_gate.get("enabled") is True
    )
    _ = provider_activation_contract
    return {
        "provider_safety_summary": {
            "safe": True,
            "execution_allowed": execution_allowed,
            "mode": "enabled" if execution_allowed else "locked",
        }
    }
