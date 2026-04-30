from __future__ import annotations

from typing import Any, Dict, List


def build_provider_selection_audit(
    requested_provider: Any,
    selected_provider: Any,
    allowed: bool,
    reason: str,
    fallback_used: bool,
) -> Dict[str, Any]:
    """Build deterministic provider selection audit payload."""
    requested = (
        requested_provider.strip().lower()
        if isinstance(requested_provider, str) and requested_provider.strip()
        else "mock"
    )
    selected = (
        selected_provider.strip().lower()
        if isinstance(selected_provider, str) and selected_provider.strip()
        else "mock"
    )

    return {
        "requested_provider": requested,
        "selected_provider": selected,
        "allowed": bool(allowed),
        "reason": reason if isinstance(reason, str) and reason.strip() else "Provider selection resolved",
        "fallback_used": bool(fallback_used),
    }


def _enabled_provider_names(config: Any) -> List[str]:
    if not isinstance(config, dict):
        return ["mock"]
    raw = config.get("enabled_providers")
    if not isinstance(raw, list):
        return ["mock"]

    names = [
        item.strip().lower() for item in raw if isinstance(item, str) and item.strip()
    ]
    if not names:
        return ["mock"]
    return names


def select_provider_with_audit(requested_provider: Any, config: Any) -> Dict[str, Any]:
    """Select provider deterministically and emit audit metadata."""
    requested = (
        requested_provider.strip().lower()
        if isinstance(requested_provider, str) and requested_provider.strip()
        else "mock"
    )

    enabled_providers = _enabled_provider_names(config)

    if requested == "mock":
        return build_provider_selection_audit(
            requested_provider="mock",
            selected_provider="mock",
            allowed=True,
            reason="Default provider selected",
            fallback_used=False,
        )

    if requested in enabled_providers:
        return build_provider_selection_audit(
            requested_provider=requested,
            selected_provider=requested,
            allowed=True,
            reason="Requested provider enabled",
            fallback_used=False,
        )

    return build_provider_selection_audit(
        requested_provider=requested,
        selected_provider="mock",
        allowed=False,
        reason="Requested provider disabled",
        fallback_used=True,
    )
