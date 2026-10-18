from __future__ import annotations

import copy
from typing import Any, Dict, List

from .config import get_provider_config
from .credentials import get_provider_credential_state
from .failure_model import normalize_provider_result
from .local_image_provider import execute_local_image_render
from .real_provider_adapter import execute_real_image_render
from .registry import ProviderRegistry, build_default_registry
from .selection_audit import select_provider_with_audit
from .types import validate_provider_payload


_DIRECT_PROVIDER_ADAPTERS = {
    "real_stub": execute_real_image_render,
    "local_image": execute_local_image_render,
}


def _normalize_provider_name(provider_name: Any) -> str:
    if isinstance(provider_name, str) and provider_name.strip():
        normalized = provider_name.strip().lower()
        return normalized
    return "mock"


def _is_real_provider_enabled(provider_name: str, config: Dict[str, Any]) -> bool:
    if provider_name != "real_stub":
        return False
    if config.get("real_enabled") is not True:
        return False
    if config.get("real_provider_runtime_flag") is not True:
        return False

    credential_state = get_provider_credential_state(provider_name, config)
    return credential_state.get("credential_present") is True


def build_execution_context(
    provider_name: Any,
    payload: Any,
    config: Any,
) -> Dict[str, Any]:
    """Build immutable execution context for isolated provider execution."""
    normalized_provider_name = _normalize_provider_name(provider_name)

    payload_copy = copy.deepcopy(payload) if isinstance(payload, dict) else payload
    config_object = config if isinstance(config, dict) else get_provider_config()
    context_config = dict(config_object)

    return {
        "requested_provider_name": normalized_provider_name,
        "payload": payload_copy,
        "config": context_config,
    }


def _get_registry(config: Dict[str, Any]) -> ProviderRegistry:
    candidate = config.get("provider_registry")
    if isinstance(candidate, ProviderRegistry):
        return candidate
    return build_default_registry(config)


def execute_provider_render(
    provider_name: Any,
    provider_payload: Any,
    config: Any,
) -> Dict[str, Any]:
    """Execute provider through isolated layer with deterministic failure normalization."""
    context = build_execution_context(provider_name, provider_payload, config)
    requested_provider_name = context["requested_provider_name"]
    payload = context["payload"]
    context_config = context["config"]
    def _selection_failure(error_code: str, message: str) -> Dict[str, Any]:
        return {
            "render_id": None,
            "status": "failed",
            "provider": requested_provider_name,
            "error": message,
            "error_code": error_code,
            "meta": {"file_path": None, "url": None},
        }

    selection_audit = select_provider_with_audit(requested_provider_name, context_config)
    if not selection_audit["allowed"]:
        return _selection_failure(
            "provider_disabled",
            f"Provider '{requested_provider_name}' is disabled and cannot execute generation requests.",
        )
    selected_provider_name = selection_audit["selected_provider"]
    # An allowed provider is authoritative for this render intent. Do not let
    # the registry silently substitute mock (or any other provider) when the
    # selected implementation is absent.
    if selected_provider_name not in _DIRECT_PROVIDER_ADAPTERS:
        try:
            provider = _get_registry(context_config).get_provider(selected_provider_name)
        except ValueError:
            return {
                "render_id": None,
                "status": "failed",
                "provider": selected_provider_name,
                "error": f"Unknown provider: {selected_provider_name}",
                "error_code": "unknown_provider",
                "meta": {"file_path": None, "url": None},
            }

    if not validate_provider_payload(payload):
        return normalize_provider_result(
            {
                "status": "failed",
                "error_code": "invalid_payload",
                "error": "Invalid provider payload",
            },
            selected_provider_name,
        )

    if selected_provider_name in _DIRECT_PROVIDER_ADAPTERS:
        if selected_provider_name == "real_stub" and not _is_real_provider_enabled(
            selected_provider_name, context_config
        ):
            return normalize_provider_result(
                {
                    "status": "failed",
                    "error_code": "real_provider_locked",
                    "error": "Real provider execution locked",
                    "provider": selected_provider_name,
                    "meta": {"file_path": None, "url": None},
                },
                selected_provider_name,
            )

        adapter = _DIRECT_PROVIDER_ADAPTERS[selected_provider_name]
        try:
            raw_result = adapter(
                payload.get("prompt") if isinstance(payload, dict) else None,
                payload.get("shot_id") if isinstance(payload, dict) else None,
            )
        except Exception as exc:  # pragma: no cover - deterministic exception normalization
            raw_result = exc
        return normalize_provider_result(raw_result, selected_provider_name)

    try:
        raw_result = provider.render(payload)
    except Exception as exc:  # pragma: no cover - covered by test via deterministic mapping
        return normalize_provider_result(exc, selected_provider_name)

    return normalize_provider_result(raw_result, selected_provider_name)


def execute_render(
    provider_name: Any,
    provider_payload: Any,
    config: Any = None,
) -> Dict[str, Any]:
    """Compatibility wrapper for direct execution-layer render calls."""
    return execute_provider_render(provider_name, provider_payload, config)


def execute_render_sequence(
    provider_name: Any,
    provider_payloads: Any,
    config: Any = None,
    max_shots: Any = 3,
) -> List[Dict[str, Any]]:
    """Execute provider renders sequentially with deterministic cap and normalized results."""
    if not isinstance(provider_payloads, list):
        return []

    cap = max_shots if isinstance(max_shots, int) and max_shots >= 0 else 0
    if cap == 0:
        return []

    normalized_provider_name = _normalize_provider_name(provider_name)
    results: List[Dict[str, Any]] = []
    for payload in provider_payloads:
        if len(results) >= cap:
            break
        payload_value = payload if isinstance(payload, dict) else {}
        try:
            result = execute_render(normalized_provider_name, payload_value, config)
        except Exception as exc:  # pragma: no cover - defensive fallback
            result = exc
        normalized_result = normalize_provider_result(result, normalized_provider_name)
        # Preserve the caller's execution intent across the compatibility
        # normalizer, whose legacy provider allowlist maps unknown IDs to mock.
        normalized_result["provider"] = normalized_provider_name
        results.append(normalized_result)
    return results
