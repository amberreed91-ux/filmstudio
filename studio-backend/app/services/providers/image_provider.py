from __future__ import annotations

from typing import Any, Dict


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def build_image_render_payload(scene: Any, shot: Any, prompt_pack: Any) -> Dict[str, Any]:
    scene_dict = scene if isinstance(scene, dict) else {}
    shot_dict = shot if isinstance(shot, dict) else {}
    prompt_dict = prompt_pack if isinstance(prompt_pack, dict) else {}

    scene_id = _as_clean_str(scene_dict.get("scene_id")) or "scene_001"
    shot_id = _as_clean_str(shot_dict.get("shot_id")) or "shot_001"
    base_prompt = _as_clean_str(prompt_dict.get("base_prompt"))

    return {
        "scene_id": scene_id,
        "shot_id": shot_id,
        "base_prompt": base_prompt,
        "style_tags": prompt_dict.get("style_tags") if isinstance(prompt_dict.get("style_tags"), list) else [],
        "meta": {
            "heading": _as_clean_str(scene_dict.get("heading")),
            "location": _as_clean_str(scene_dict.get("location")),
            "time_of_day": _as_clean_str(scene_dict.get("time_of_day")),
        },
    }


def submit_image_render(payload: Any, config: Any) -> Dict[str, Any]:
    payload_dict = payload if isinstance(payload, dict) else {}
    config_dict = config if isinstance(config, dict) else {}

    enabled = config_dict.get("image_provider_enabled") is True
    provider_name = _as_clean_str(config_dict.get("image_provider_name")) or "local_image"
    api_key = _as_clean_str(config_dict.get("image_provider_api_key"))

    scene_id = _as_clean_str(payload_dict.get("scene_id")) or "scene_001"
    shot_id = _as_clean_str(payload_dict.get("shot_id")) or "shot_001"
    render_id = f"image_{scene_id}_{shot_id}"

    if not enabled:
        return {
            "render_id": render_id,
            "status": "success",
            "provider": "local_image",
            "url": f"https://picsum.photos/seed/{render_id}/800/450",
            "file_path": None,
            "error": None,
            "meta": {"reason": "provider_disabled_local_fallback"},
        }

    if not api_key:
        return {
            "render_id": render_id,
            "status": "failed",
            "provider": provider_name,
            "url": None,
            "file_path": None,
            "error": "Missing image provider API key",
            "meta": {"reason": "missing_api_key"},
        }

    return {
        "render_id": render_id,
        "status": "pending",
        "provider": provider_name,
        "url": None,
        "file_path": None,
        "error": None,
        "meta": {"reason": "submission_stubbed"},
    }


def normalize_image_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "render_id": "",
            "status": "failed",
            "provider": "unknown",
            "url": None,
            "file_path": None,
            "error": "Invalid provider image response",
            "meta": {},
        }

    status = _as_clean_str(result.get("status")).lower() or "failed"
    if status not in {"success", "failed", "pending", "not_executed"}:
        status = "failed"

    return {
        "render_id": _as_clean_str(result.get("render_id")),
        "status": status,
        "provider": _as_clean_str(result.get("provider")) or "unknown",
        "url": _as_clean_str(result.get("url")) or None,
        "file_path": _as_clean_str(result.get("file_path")) or None,
        "error": str(result.get("error")).strip() if result.get("error") is not None and str(result.get("error")).strip() else None,
        "meta": result.get("meta") if isinstance(result.get("meta"), dict) else {},
    }
