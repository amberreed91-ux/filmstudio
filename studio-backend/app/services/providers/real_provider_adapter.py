from __future__ import annotations

from typing import Any, Dict


def execute_real_image_render(prompt: Any, shot_id: Any) -> Dict[str, Any]:
    """
    Deterministic real-provider image render stub.
    This function is single-shot, synchronous, and never performs retries.
    """
    normalized_shot_id = shot_id.strip() if isinstance(shot_id, str) and shot_id.strip() else None
    if normalized_shot_id is None:
        return {
            "render_id": None,
            "status": "failed",
            "provider": "real_stub",
            "error": "Missing shot_id",
            "error_code": "missing_shot_id",
            "meta": {
                "file_path": None,
                "url": None,
            },
        }

    if not isinstance(prompt, dict):
        return {
            "render_id": f"real_{normalized_shot_id}",
            "status": "failed",
            "provider": "real_stub",
            "error": "Invalid prompt payload",
            "error_code": "invalid_prompt_payload",
            "meta": {
                "file_path": None,
                "url": None,
            },
        }

    try:
        # Deterministic metadata-only output; no network/provider calls.
        return {
            "render_id": f"real_{normalized_shot_id}",
            "status": "success",
            "provider": "real_stub",
            "error": None,
            "error_code": None,
            "meta": {
                "file_path": f"/tmp/studio_renders/real_{normalized_shot_id}.png",
                "url": None,
            },
        }
    except Exception as exc:  # pragma: no cover - defensive normalization fallback
        return {
            "render_id": f"real_{normalized_shot_id}",
            "status": "failed",
            "provider": "real_stub",
            "error": str(exc) if isinstance(str(exc), str) and str(exc).strip() else "Real adapter failure",
            "error_code": "real_adapter_failure",
            "meta": {
                "file_path": None,
                "url": None,
            },
        }
