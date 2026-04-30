from __future__ import annotations

from typing import Any, Dict


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def build_video_render_payload(scene: Any, shot: Any, prompt_pack: Any) -> Dict[str, Any]:
    """Build deterministic provider-agnostic payload for a video render request."""
    scene_dict = scene if isinstance(scene, dict) else {}
    shot_dict = shot if isinstance(shot, dict) else {}
    prompt_dict = prompt_pack if isinstance(prompt_pack, dict) else {}

    scene_id = _as_clean_str(scene_dict.get("scene_id")) or "scene_001"
    shot_id = _as_clean_str(shot_dict.get("shot_id")) or "shot_001"

    return {
        "scene_id": scene_id,
        "shot_id": shot_id,
        "prompt": {
            "base_prompt": _as_clean_str(prompt_dict.get("base_prompt")),
            "style_tags": prompt_dict.get("style_tags") if isinstance(prompt_dict.get("style_tags"), list) else [],
            "negative_prompt": (
                prompt_dict.get("negative_prompt")
                if isinstance(prompt_dict.get("negative_prompt"), list)
                else []
            ),
        },
        "meta": {
            "heading": _as_clean_str(scene_dict.get("heading")),
            "time_of_day": _as_clean_str(scene_dict.get("time_of_day")),
        },
    }


def submit_video_render(payload: Any, config: Any) -> Dict[str, Any]:
    """
    Safe submit wrapper.

    This function intentionally does not execute external network calls.
    It returns deterministic pending/failed responses based on config gates.
    """
    payload_dict = payload if isinstance(payload, dict) else {}
    config_dict = config if isinstance(config, dict) else {}

    enabled = config_dict.get("video_provider_enabled") is True
    provider_name = _as_clean_str(config_dict.get("video_provider_name")) or "disabled"
    api_key = _as_clean_str(config_dict.get("video_provider_api_key"))

    scene_id = _as_clean_str(payload_dict.get("scene_id")) or "scene_001"
    shot_id = _as_clean_str(payload_dict.get("shot_id")) or "shot_001"
    render_id = f"video_{scene_id}_{shot_id}"

    if not enabled:
        return {
            "render_id": render_id,
            "status": "pending",
            "provider": provider_name,
            "video_url": None,
            "thumbnail_url": None,
            "error": "Video provider disabled",
            "meta": {"reason": "provider_disabled"},
        }

    if not api_key:
        return {
            "render_id": render_id,
            "status": "failed",
            "provider": provider_name,
            "video_url": None,
            "thumbnail_url": None,
            "error": "Missing video provider API key",
            "meta": {"reason": "missing_api_key"},
        }

    return {
        "render_id": render_id,
        "status": "pending",
        "provider": provider_name,
        "video_url": None,
        "thumbnail_url": None,
        "error": None,
        "meta": {"reason": "submission_stubbed"},
    }


def normalize_video_result(result: Any) -> Dict[str, Any]:
    """Normalize provider response to stable video result contract."""
    if isinstance(result, dict):
        render_id = _as_clean_str(result.get("render_id")) or ""
        status_raw = _as_clean_str(result.get("status")).lower() or "failed"
        provider = _as_clean_str(result.get("provider")) or "unknown"
        video_url = _as_clean_str(result.get("video_url")) or None
        thumbnail_url = _as_clean_str(result.get("thumbnail_url")) or None
        error_value = result.get("error")
        error = str(error_value) if error_value is not None and str(error_value).strip() else None
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}

        if status_raw not in {"success", "failed", "pending"}:
            status_raw = "failed"

        return {
            "render_id": render_id,
            "status": status_raw,
            "provider": provider,
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
            "error": error,
            "meta": meta,
        }

    return {
        "render_id": "",
        "status": "failed",
        "provider": "unknown",
        "video_url": None,
        "thumbnail_url": None,
        "error": "Invalid provider video response",
        "meta": {},
    }
