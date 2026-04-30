from __future__ import annotations

import copy
import os
from typing import Any, Dict


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default)
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"true", "1", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(float(str(raw).strip()))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(str(raw).strip())
    except Exception:
        return default


DEFAULT_PROVIDER_CONFIG: Dict[str, Any] = {
    "default_provider": "mock",
    "enabled_providers": ["mock"],
    "quality_priority": "cinematic_quality",
    "image_provider_enabled": _env_bool("IMAGE_PROVIDER_ENABLED", "false"),
    "image_provider_name": os.getenv("IMAGE_PROVIDER_NAME", "").strip(),
    "image_provider_api_key": os.getenv("IMAGE_PROVIDER_API_KEY", "").strip(),
    "image_provider_base_url": os.getenv("IMAGE_PROVIDER_BASE_URL", "").strip(),
    "comfyui_enabled": _env_bool("COMFYUI_ENABLED", "false"),
    "comfyui_base_url": os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").strip(),
    "comfyui_cfg": _env_float("COMFYUI_CFG", 7.0),
    "comfyui_steps": _env_int("COMFYUI_STEPS", 25),
    "comfyui_width": _env_int("COMFYUI_WIDTH", 832),
    "comfyui_height": _env_int("COMFYUI_HEIGHT", 468),
    "comfyui_seed_mode": os.getenv("COMFYUI_SEED_MODE", "deterministic").strip().lower() or "deterministic",
    "comfyui_motion_enabled": _env_bool("COMFYUI_MOTION_ENABLED", "false"),
    "comfyui_motion_workflow_path": os.getenv(
        "COMFYUI_MOTION_WORKFLOW_PATH",
        "/Users/amberreed/ComfyUI/workflows/animate_diff_basic.json",
    ).strip(),
    "video_provider_enabled": _env_bool("VIDEO_PROVIDER_ENABLED", "false"),
    "video_provider_name": os.getenv("VIDEO_PROVIDER_NAME", "").strip(),
    "video_provider_api_key": os.getenv("VIDEO_PROVIDER_API_KEY", "").strip(),
    "video_provider_base_url": os.getenv("VIDEO_PROVIDER_BASE_URL", "").strip(),
}


def get_provider_config() -> Dict[str, Any]:
    """Return deterministic provider config with no external dependencies."""
    config = copy.deepcopy(DEFAULT_PROVIDER_CONFIG)
    config["image_provider_enabled"] = _env_bool("IMAGE_PROVIDER_ENABLED", "false")
    config["image_provider_name"] = os.getenv("IMAGE_PROVIDER_NAME", "").strip()
    config["image_provider_api_key"] = os.getenv("IMAGE_PROVIDER_API_KEY", "").strip()
    config["image_provider_base_url"] = os.getenv("IMAGE_PROVIDER_BASE_URL", "").strip()
    config["comfyui_enabled"] = _env_bool("COMFYUI_ENABLED", "false")
    config["comfyui_base_url"] = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").strip()
    config["comfyui_cfg"] = _env_float("COMFYUI_CFG", 7.0)
    config["comfyui_steps"] = _env_int("COMFYUI_STEPS", 25)
    config["comfyui_width"] = _env_int("COMFYUI_WIDTH", 832)
    config["comfyui_height"] = _env_int("COMFYUI_HEIGHT", 468)
    config["comfyui_seed_mode"] = os.getenv("COMFYUI_SEED_MODE", "deterministic").strip().lower() or "deterministic"
    config["comfyui_motion_enabled"] = _env_bool("COMFYUI_MOTION_ENABLED", "false")
    config["comfyui_motion_workflow_path"] = os.getenv(
        "COMFYUI_MOTION_WORKFLOW_PATH",
        "/Users/amberreed/ComfyUI/workflows/animate_diff_basic.json",
    ).strip()
    config["video_provider_enabled"] = _env_bool("VIDEO_PROVIDER_ENABLED", "false")
    config["video_provider_name"] = os.getenv("VIDEO_PROVIDER_NAME", "").strip()
    config["video_provider_api_key"] = os.getenv("VIDEO_PROVIDER_API_KEY", "").strip()
    config["video_provider_base_url"] = os.getenv("VIDEO_PROVIDER_BASE_URL", "").strip()
    return config


def get_render_provider_config() -> Dict[str, Any]:
    """Compatibility alias for callers expecting render-layer naming."""
    return get_provider_config()


def resolve_default_provider(config: Dict[str, Any]) -> str:
    """Resolve default provider safely; fallback to mock when invalid."""
    if not isinstance(config, dict):
        return "mock"

    enabled = config.get("enabled_providers")
    if not isinstance(enabled, list):
        enabled_names: list[str] = []
    else:
        enabled_names = [
            item.strip().lower() for item in enabled if isinstance(item, str) and item.strip()
        ]

    default_provider = config.get("default_provider")
    if isinstance(default_provider, str) and default_provider.strip():
        normalized_default = default_provider.strip().lower()
        if normalized_default in enabled_names:
            return normalized_default

    if enabled_names:
        return enabled_names[0]

    return "mock"


def _enabled_provider_names(config: Dict[str, Any]) -> list[str]:
    if not isinstance(config, dict):
        return []
    enabled = config.get("enabled_providers")
    if not isinstance(enabled, list):
        return []
    return [
        item.strip().lower()
        for item in enabled
        if isinstance(item, str) and item.strip()
    ]


def is_provider_enabled(name: str, config: Dict[str, Any]) -> bool:
    """Return True when provider name is present in enabled_providers."""
    if not isinstance(name, str) or not name.strip():
        return False

    target = name.strip().lower()
    return target in _enabled_provider_names(config)


def is_provider_config_enabled(provider_name: str, config: Dict[str, Any]) -> bool:
    """Boundary-safe provider enablement check used by credential state logic."""
    return is_provider_enabled(provider_name, config)
