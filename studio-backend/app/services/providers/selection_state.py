from __future__ import annotations

from typing import Any, Dict, Optional

from .selection_audit import select_provider_with_audit
from .selection_request import normalize_selection_request


def build_provider_selection_state(requested_provider: Any, config: Any) -> Dict[str, Any]:
    """
    Build deterministic provider selection state without executing providers.
    """
    audit = select_provider_with_audit(requested_provider, config)
    return {
        "requested_provider": audit.get("requested_provider", "mock"),
        "selected_provider": audit.get("selected_provider", "mock"),
        "allowed": bool(audit.get("allowed", False)),
        "fallback_used": bool(audit.get("fallback_used", False)),
        "reason": audit.get("reason", "Requested provider disabled"),
    }


def resolve_provider_selection(requested_provider: Optional[str], config: Optional[dict]) -> Dict[str, Any]:
    """
    Resolve provider selection deterministically, non-throwing.

    Output shape:
    {
      "requested_provider": str | None,
      "selected_provider": str,
      "allowed": bool,
      "fallback_used": bool,
      "reason": str
    }
    """
    request = normalize_selection_request(requested_provider)
    normalized_requested = request.get("requested_provider")
    try:
        audit = select_provider_with_audit(normalized_requested, config if isinstance(config, dict) else {})
    except Exception:
        return {
            "requested_provider": normalized_requested,
            "selected_provider": "mock",
            "allowed": False,
            "fallback_used": True,
            "reason": "Requested provider disabled",
        }

    selected_provider = audit.get("selected_provider")
    if not isinstance(selected_provider, str) or not selected_provider.strip():
        selected_provider = "mock"
    else:
        selected_provider = selected_provider.strip().lower()

    reason = audit.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "Requested provider disabled"

    return {
        "requested_provider": normalized_requested,
        "selected_provider": selected_provider,
        "allowed": bool(audit.get("allowed", False)),
        "fallback_used": bool(audit.get("fallback_used", False)),
        "reason": reason,
    }
