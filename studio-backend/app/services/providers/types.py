from __future__ import annotations

from typing import Any, Dict, Literal, Optional, TypedDict


ProviderStatus = Literal["success", "failed", "not_executed", "skipped"]


class ProviderPayload(TypedDict):
    shot_id: str
    prompt: Dict[str, Any]


class ProviderResult(TypedDict):
    render_id: Optional[str]
    status: ProviderStatus
    provider: str
    error: Optional[str]
    error_code: Optional[str]
    meta: Dict[str, Any]


class ProviderCapability(TypedDict):
    provider: str
    enabled: bool
    network_required: bool
    supports_render: bool
    supports_streaming: bool
    supports_sync: bool
    supports_multi_shot: bool
    requires_credentials: bool


class ProviderSelectionAudit(TypedDict):
    requested_provider: str
    selected_provider: str
    allowed: bool
    reason: str
    fallback_used: bool


def validate_provider_payload(payload: Any) -> bool:
    """Return True when payload has valid shot_id + prompt structure."""
    if not isinstance(payload, dict):
        return False

    shot_id = payload.get("shot_id")
    prompt = payload.get("prompt")

    if not isinstance(shot_id, str) or not shot_id.strip():
        return False
    if not isinstance(prompt, dict):
        return False

    return True
