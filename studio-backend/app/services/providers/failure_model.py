from __future__ import annotations

from typing import Any, Dict


_KNOWN_PROVIDERS = {"mock", "local_image", "real_stub"}


def _normalize_provider_name(provider: Any) -> str:
    if isinstance(provider, str) and provider.strip():
        normalized = provider.strip().lower()
        if normalized in _KNOWN_PROVIDERS:
            return normalized
    return "mock"


def _normalize_meta(meta: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {"file_path": None, "url": None}
    if not isinstance(meta, dict):
        return base
    normalized = dict(meta)
    file_path = normalized.get("file_path")
    url = normalized.get("url")
    base["file_path"] = file_path if isinstance(file_path, str) else None
    base["url"] = url if isinstance(url, str) else None
    for key, value in normalized.items():
        if key in {"file_path", "url"}:
            continue
        base[key] = value
    return base


def _normalize_error(value: Any, fallback: str = "Provider execution failed") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def normalize_provider_result(input_result: Any, provider_name: str) -> Dict[str, Any]:
    """Normalize any provider result/exception into a strict deterministic shape."""
    normalized_provider = _normalize_provider_name(provider_name)
    base = {
        "render_id": None,
        "status": "failed",
        "provider": normalized_provider,
        "error": "Malformed provider result",
        "error_code": "malformed_result",
        "meta": _normalize_meta(None),
    }

    if isinstance(input_result, Exception):
        return {
            "render_id": None,
            "status": "failed",
            "provider": normalized_provider,
            "error": _normalize_error(str(input_result), "Provider exception"),
            "error_code": "provider_exception",
            "meta": _normalize_meta(None),
        }

    if not isinstance(input_result, dict):
        return base

    provider = _normalize_provider_name(input_result.get("provider", normalized_provider))
    status = input_result.get("status")
    render_id = input_result.get("render_id")
    error = input_result.get("error")
    reason = input_result.get("reason")
    error_code = input_result.get("error_code")
    meta = _normalize_meta(input_result.get("meta"))

    if status == "success":
        if not isinstance(render_id, str) or not render_id.strip():
            return base | {"provider": provider}
        return {
            "render_id": render_id.strip(),
            "status": "success",
            "provider": provider,
            "error": None,
            "error_code": None,
            "meta": meta,
        }

    if status == "not_executed" or status == "skipped":
        return {
            "render_id": None,
            "status": "not_executed",
            "provider": provider,
            "error": None,
            "error_code": None,
            "meta": meta,
        }

    if status == "failed":
        normalized_error = _normalize_error(error or reason)
        normalized_error_code = (
            error_code.strip().lower()
            if isinstance(error_code, str) and error_code.strip()
            else None
        )
        return {
            "render_id": None,
            "status": "failed",
            "provider": provider,
            "error": normalized_error,
            "error_code": normalized_error_code,
            "meta": meta,
        }

    if error is not None or reason is not None or error_code is not None:
        normalized_error = _normalize_error(error or reason)
        normalized_error_code = (
            error_code.strip().lower()
            if isinstance(error_code, str) and error_code.strip()
            else None
        )
        return {
            "render_id": None,
            "status": "failed",
            "provider": provider,
            "error": normalized_error,
            "error_code": normalized_error_code,
            "meta": meta,
        }

    return base | {"provider": provider, "meta": meta}


def build_provider_failure(
    status: str,
    code: str,
    reason: str,
    provider: str = "unknown",
) -> Dict[str, Any]:
    """Build deterministic normalized provider failure payload."""
    normalized_provider = provider.strip().lower() if isinstance(provider, str) and provider.strip() else "unknown"
    normalized_code = code.strip().lower() if isinstance(code, str) and code.strip() else "unknown_error"
    normalized_reason = reason.strip() if isinstance(reason, str) and reason.strip() else "Provider execution failed"

    _ = status
    return {
        "render_id": None,
        "status": "failed",
        "provider": normalized_provider,
        "error": normalized_reason,
        "error_code": normalized_code,
        "meta": _normalize_meta(None),
    }


def normalize_provider_failure(raw: Any) -> Dict[str, Any]:
    """Normalize unknown failure input into deterministic provider failure shape."""
    if isinstance(raw, dict):
        normalized = normalize_provider_result(raw, raw.get("provider", "unknown"))
        return {
            "render_id": normalized["render_id"],
            "status": normalized["status"],
            "provider": normalized["provider"],
            "error": normalized["error"],
            "error_code": normalized["error_code"] or "unknown_error",
            "meta": normalized["meta"],
        }

    if isinstance(raw, Exception):
        normalized = normalize_provider_result(raw, "unknown")
        return {
            "render_id": normalized["render_id"],
            "status": normalized["status"],
            "provider": normalized["provider"],
            "error": normalized["error"],
            "error_code": normalized["error_code"] or "provider_exception",
            "meta": normalized["meta"],
        }

    if isinstance(raw, str):
        return build_provider_failure("failed", "unknown_error", raw, "unknown")

    return build_provider_failure("failed", "unknown_error", "Provider execution failed", "unknown")
