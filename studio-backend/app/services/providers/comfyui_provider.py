from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .config import get_provider_config

_LAST_RENDER_ERROR: str = ""
logger = logging.getLogger(__name__)

COMFYUI_EXPORT_INSTRUCTIONS = """
In ComfyUI:
1. Click settings (gear icon)
2. Enable 'Dev Mode Options'
3. Load your workflow
4. Click 'Save (API format)'
5. Use that JSON file for COMFYUI_MOTION_WORKFLOW_PATH
""".strip()


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _post_json(url: str, payload: Dict[str, Any], timeout: float = 2.5) -> Optional[Dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    return parsed if isinstance(parsed, dict) else None


def _get_json(url: str, timeout: float = 2.5) -> Optional[Dict[str, Any]]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    return parsed if isinstance(parsed, dict) else None


def _post_json_with_detail(
    url: str,
    payload: Dict[str, Any],
    timeout: float = 2.5,
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        if isinstance(parsed, dict):
            return {
                "ok": True,
                "status_code": 200,
                "body": parsed,
            }
        return {
            "ok": False,
            "status_code": 200,
            "body": raw,
            "error_message": "invalid_json_response",
        }
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        return {
            "ok": False,
            "status_code": int(getattr(exc, "code", 500)),
            "body": body,
            "error_message": str(exc),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status_code": 0,
            "body": "",
            "error_message": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "body": "",
            "error_message": str(exc),
        }


def _get_available_checkpoint(base_url: str) -> str:
    try:
        object_info = _get_json(f"{base_url}/object_info")
        node_info = object_info.get("CheckpointLoaderSimple") if isinstance(object_info, dict) else None
        input_info = node_info.get("input") if isinstance(node_info, dict) else None
        required = input_info.get("required") if isinstance(input_info, dict) else None
        ckpt_spec = required.get("ckpt_name") if isinstance(required, dict) else None
        if isinstance(ckpt_spec, list) and ckpt_spec and isinstance(ckpt_spec[0], list):
            options = ckpt_spec[0]
            if isinstance(options, list):
                for item in options:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
    except Exception:
        return ""
    return ""


def derive_deterministic_seed(scene_id: str = "", shot_id: str = "", prompt: str = "") -> int:
    token = f"{scene_id.strip().lower()}::{shot_id.strip().lower()}::{prompt.strip().lower()}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _build_basic_workflow(
    prompt: str,
    ckpt_name: str,
    negative_prompt: str,
    cfg: float,
    steps: int,
    width: int,
    height: int,
    seed: int,
) -> Dict[str, Any]:
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(seed),
                "steps": max(1, int(steps)),
                "cfg": max(1.0, float(cfg)),
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": max(64, int(width)),
                "height": max(64, int(height)),
                "batch_size": 1,
            },
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["4", 1]},
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "studio_previs",
            },
        },
    }


def _latest_output_image(base_url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    output_dir = os.path.expanduser("~/ComfyUI/output")
    if not os.path.isdir(output_dir):
        return None
    candidates = [
        os.path.join(output_dir, name)
        for name in os.listdir(output_dir)
        if name.startswith("studio_previs_") and name.lower().endswith(".png")
    ]
    if not candidates:
        return None
    latest = max(candidates, key=os.path.getmtime)
    filename = os.path.basename(latest)
    query = urlencode({"filename": filename, "subfolder": "", "type": "output"})
    return {
        "url": f"{base_url}/view?{query}",
        "file_path": latest,
        "status": "success",
        **params,
    }


def render_image(
    prompt: str,
    negative_prompt: Optional[str] = None,
    scene_id: str = "",
    shot_id: str = "",
) -> Optional[Dict[str, Any]]:
    global _LAST_RENDER_ERROR
    _LAST_RENDER_ERROR = ""
    config = get_provider_config()
    if config.get("comfyui_enabled") is not True:
        _LAST_RENDER_ERROR = "comfyui_disabled"
        return None

    base_url = _as_clean_str(config.get("comfyui_base_url")) or "http://127.0.0.1:8188"
    clean_prompt = _as_clean_str(prompt)
    if not clean_prompt:
        _LAST_RENDER_ERROR = "comfyui_payload_failed"
        return None
    clean_negative_prompt = _as_clean_str(negative_prompt) or (
        "low quality, blurry, deformed, extra limbs, bad anatomy, distorted face, oversaturated"
    )

    cfg = float(config.get("comfyui_cfg", 7.0) or 7.0)
    steps = int(config.get("comfyui_steps", 25) or 25)
    width = int(config.get("comfyui_width", 832) or 832)
    height = int(config.get("comfyui_height", 468) or 468)
    seed_mode = _as_clean_str(config.get("comfyui_seed_mode")) or "deterministic"
    seed = derive_deterministic_seed(scene_id, shot_id, clean_prompt)
    if seed_mode not in {"deterministic", "locked"}:
        seed = derive_deterministic_seed(scene_id, shot_id, clean_prompt)

    meta_params = {
        "seed": seed,
        "cfg": cfg,
        "steps": steps,
        "width": width,
        "height": height,
    }

    try:
        ckpt_name = _get_available_checkpoint(base_url)
        if not ckpt_name:
            _LAST_RENDER_ERROR = "comfyui_payload_failed"
            return None
        payload = {
            "prompt": _build_basic_workflow(
                clean_prompt,
                ckpt_name,
                clean_negative_prompt,
                cfg,
                steps,
                width,
                height,
                seed,
            )
        }
        submit = _post_json(f"{base_url}/prompt", payload)
        if not isinstance(submit, dict):
            _LAST_RENDER_ERROR = "comfyui_payload_failed"
            return None

        prompt_id = _as_clean_str(submit.get("prompt_id"))
        if not prompt_id:
            _LAST_RENDER_ERROR = "comfyui_payload_failed"
            return None

        for _ in range(40):
            history = _get_json(f"{base_url}/history/{prompt_id}")
            prompt_block = history.get(prompt_id) if isinstance(history, dict) else None
            outputs = prompt_block.get("outputs") if isinstance(prompt_block, dict) else None
            if isinstance(outputs, dict):
                for node_value in outputs.values():
                    images = node_value.get("images") if isinstance(node_value, dict) else None
                    if isinstance(images, list) and images:
                        image = images[0] if isinstance(images[0], dict) else {}
                        filename = _as_clean_str(image.get("filename"))
                        subfolder = _as_clean_str(image.get("subfolder"))
                        image_type = _as_clean_str(image.get("type")) or "output"
                        if filename:
                            query = urlencode({"filename": filename, "subfolder": subfolder, "type": image_type})
                            return {
                                "url": f"{base_url}/view?{query}",
                                "prompt_id": prompt_id,
                                "status": "success",
                                **meta_params,
                            }
            time.sleep(0.5)
    except Exception:
        _LAST_RENDER_ERROR = "comfyui_unreachable"
        return None

    latest_output = _latest_output_image(base_url, meta_params)
    if isinstance(latest_output, dict):
        _LAST_RENDER_ERROR = ""
        return latest_output

    _LAST_RENDER_ERROR = "comfyui_no_image"
    return None


def get_last_render_error() -> str:
    return _LAST_RENDER_ERROR


def _build_comfyui_view_url(base_url: str, filename: str, subfolder: str, output_type: str) -> str:
    query = urlencode(
        {
            "filename": filename,
            "subfolder": subfolder,
            "type": output_type or "output",
        }
    )
    return f"{base_url}/view?{query}"


def detect_workflow_format(workflow_json: Any) -> str:
    if not isinstance(workflow_json, dict) or not workflow_json:
        return "unknown"
    if any(key in workflow_json for key in ("nodes", "links", "last_node_id")):
        return "ui"
    if all(
        isinstance(node_id, str) and node_id.isdigit() and isinstance(node_value, dict)
        for node_id, node_value in workflow_json.items()
    ):
        return "api"
    return "unknown"


def _pick_motion_output_from_outputs(
    outputs: Any,
    base_url: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(outputs, dict):
        return None

    # First, preserve legacy image parsing behavior.
    for node_value in outputs.values():
        if not isinstance(node_value, dict):
            continue
        images = node_value.get("images")
        if isinstance(images, list) and images:
            image = images[0] if isinstance(images[0], dict) else {}
            filename = _as_clean_str(image.get("filename"))
            subfolder = _as_clean_str(image.get("subfolder"))
            output_type = _as_clean_str(image.get("type")) or "output"
            if filename:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                return {
                    "video_url": _build_comfyui_view_url(base_url, filename, subfolder, output_type),
                    "thumbnail_url": None,
                    "file_path": None,
                    "error": None,
                    "meta": {
                        "format": ext or "image",
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": output_type,
                    },
                }

    # Then parse explicit animated/media keys from SaveAnimatedWEBP and related nodes.
    media_keys = ("animated", "gifs", "videos", "files", "webp")
    allowed_exts = {"webp", "gif", "mp4"}
    for node_value in outputs.values():
        if not isinstance(node_value, dict):
            continue
        for media_key in media_keys:
            media_items = node_value.get(media_key)
            if not isinstance(media_items, list) or not media_items:
                continue
            for media_entry in media_items:
                if not isinstance(media_entry, dict):
                    continue
                filename = _as_clean_str(media_entry.get("filename"))
                subfolder = _as_clean_str(media_entry.get("subfolder"))
                output_type = _as_clean_str(media_entry.get("type")) or "output"
                if not filename:
                    continue
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext and ext not in allowed_exts and media_key in {"animated", "gifs", "videos", "webp"}:
                    continue
                return {
                    "video_url": _build_comfyui_view_url(base_url, filename, subfolder, output_type),
                    "thumbnail_url": None,
                    "file_path": None,
                    "error": None,
                    "meta": {
                        "format": ext or media_key,
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": output_type,
                        "output_key": media_key,
                    },
                }

    return None


def validate_comfyui_api_workflow(workflow: Any) -> Dict[str, Any]:
    if not isinstance(workflow, dict) or not workflow:
        return {"valid": False, "reason": "comfyui_workflow_missing"}
    workflow_format = detect_workflow_format(workflow)
    if workflow_format == "ui":
        return {"valid": False, "reason": "comfyui_workflow_not_api_format"}
    if workflow_format != "api":
        return {"valid": False, "reason": "comfyui_workflow_not_api_format"}
    for node_id, node_value in workflow.items():
        if not isinstance(node_id, str) or not node_id.isdigit() or not isinstance(node_value, dict):
            return {"valid": False, "reason": "comfyui_workflow_not_api_format"}
        class_type = node_value.get("class_type")
        inputs = node_value.get("inputs")
        if not isinstance(class_type, str) or not class_type.strip() or not isinstance(inputs, dict):
            return {"valid": False, "reason": "comfyui_workflow_not_api_format"}
    return {"valid": True, "reason": "ok"}


def render_motion(image_url: str, prompt: str) -> Optional[Dict[str, Any]]:
    """
    Attempt a lightweight ComfyUI motion render pass (AnimateDiff/image-to-video style).
    Returns None on any failure so callers can preserve fallback behavior.
    """
    global _LAST_RENDER_ERROR
    _LAST_RENDER_ERROR = ""
    config = get_provider_config()
    if config.get("comfyui_enabled") is not True:
        _LAST_RENDER_ERROR = "comfyui_disabled"
        return None
    if config.get("comfyui_motion_enabled") is not True:
        _LAST_RENDER_ERROR = "comfyui_motion_disabled"
        return None

    base_url = _as_clean_str(config.get("comfyui_base_url")) or "http://127.0.0.1:8188"
    workflow_path = _as_clean_str(config.get("comfyui_motion_workflow_path"))
    if not workflow_path:
        _LAST_RENDER_ERROR = "no_motion_workflow_configured"
        return None
    if not os.path.isfile(workflow_path):
        _LAST_RENDER_ERROR = "no_motion_workflow_configured"
        return None
    workflow_payload: Dict[str, Any] = {}
    try:
        with open(workflow_path, "r", encoding="utf-8") as workflow_file:
            parsed_workflow = json.load(workflow_file)
            workflow_payload = parsed_workflow if isinstance(parsed_workflow, dict) else {}
    except Exception:
        _LAST_RENDER_ERROR = "comfyui_payload_failed"
        return None

    clean_prompt = _as_clean_str(prompt)
    clean_image_url = _as_clean_str(image_url)
    if not clean_prompt or not clean_image_url:
        _LAST_RENDER_ERROR = "comfyui_payload_failed"
        return None
    image_input_value = clean_image_url
    if clean_image_url.startswith("http://") or clean_image_url.startswith("https://"):
        try:
            input_dir = os.path.expanduser("~/ComfyUI/input")
            os.makedirs(input_dir, exist_ok=True)
            file_basename = "studio_motion_input.png"
            local_input_path = os.path.join(input_dir, file_basename)
            request = Request(clean_image_url, method="GET")
            with urlopen(request, timeout=10.0) as response:  # nosec B310
                data = response.read()
            with open(local_input_path, "wb") as output_file:
                output_file.write(data)
            image_input_value = file_basename
        except Exception:
            _LAST_RENDER_ERROR = "comfyui_payload_failed"
            return None

    try:
        workflow = workflow_payload.get("prompt") if isinstance(workflow_payload.get("prompt"), dict) else workflow_payload
        validation = validate_comfyui_api_workflow(workflow)
        if validation.get("valid") is not True:
            _LAST_RENDER_ERROR = str(validation.get("reason") or "comfyui_workflow_not_api_format")
            if _LAST_RENDER_ERROR == "comfyui_workflow_not_api_format":
                logger.error(
                    "ComfyUI motion workflow is not API format. %s",
                    COMFYUI_EXPORT_INSTRUCTIONS,
                )
            return None
        patched_workflow = json.loads(json.dumps(workflow))
        clip_text_nodes: list[Dict[str, Any]] = []
        for node in patched_workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            class_type = _as_clean_str(node.get("class_type"))
            if class_type == "CLIPTextEncode" and isinstance(inputs.get("text"), str):
                clip_text_nodes.append(inputs)
            if "image" in inputs and isinstance(inputs.get("image"), str):
                inputs["image"] = image_input_value
            if "filename_prefix" in inputs and isinstance(inputs.get("filename_prefix"), str):
                inputs["filename_prefix"] = "studio_motion"

        if not clip_text_nodes:
            _LAST_RENDER_ERROR = "comfyui_prompt_node_missing"
            return None

        negative_markers = ("low quality", "blurry", "deformed", "bad anatomy", "oversaturated")
        target_node_inputs = clip_text_nodes[0]
        for inputs in clip_text_nodes:
            text_value = _as_clean_str(inputs.get("text")).lower()
            if text_value and not any(marker in text_value for marker in negative_markers):
                target_node_inputs = inputs
                break
        target_node_inputs["text"] = clean_prompt

        payload = {"prompt": patched_workflow}
        submit = _post_json_with_detail(f"{base_url}/prompt", payload)
        if submit.get("ok") is not True:
            status_code = submit.get("status_code")
            body = submit.get("body")
            err_msg = submit.get("error_message")
            body_text = body if isinstance(body, str) else json.dumps(body) if isinstance(body, (dict, list)) else ""
            payload_preview = json.dumps(payload)[:500]
            payload_size = len(json.dumps(payload))
            failing_node_id = ""
            if isinstance(body, dict):
                if isinstance(body.get("node_id"), (str, int)):
                    failing_node_id = str(body.get("node_id"))
                elif isinstance(body.get("node_errors"), dict) and body.get("node_errors"):
                    failing_node_id = str(next(iter(body.get("node_errors"))))
            logger.error(
                "ComfyUI /prompt failed status=%s failing_node_id=%s payload_size=%s payload_preview=%s response=%s",
                status_code,
                failing_node_id or "unknown",
                payload_size,
                payload_preview,
                body_text or str(err_msg or ""),
            )
            detail = body_text or str(err_msg or "unknown_error")
            _LAST_RENDER_ERROR = f"comfyui_payload_failed:{status_code}:{detail}"
            return None
        submit_body = submit.get("body") if isinstance(submit.get("body"), dict) else {}
        prompt_id = _as_clean_str(submit_body.get("prompt_id")) if isinstance(submit_body, dict) else ""
        if not prompt_id:
            _LAST_RENDER_ERROR = "comfyui_payload_failed:missing_prompt_id"
            return None

        for _ in range(30):
            history = _get_json(f"{base_url}/history/{prompt_id}")
            prompt_block = history.get(prompt_id) if isinstance(history, dict) else None
            outputs = prompt_block.get("outputs") if isinstance(prompt_block, dict) else None
            parsed_output = _pick_motion_output_from_outputs(outputs, base_url)
            if isinstance(parsed_output, dict):
                merged_meta = parsed_output.get("meta") if isinstance(parsed_output.get("meta"), dict) else {}
                merged_meta = {"prompt_id": prompt_id, "source": "image_to_motion", **merged_meta}
                return {
                    "render_id": f"comfyui_motion_{prompt_id}",
                    "status": "success",
                    "provider": "comfyui_motion",
                    "video_url": parsed_output.get("video_url"),
                    "thumbnail_url": parsed_output.get("thumbnail_url"),
                    "file_path": parsed_output.get("file_path"),
                    "error": None,
                    "meta": merged_meta,
                }
            time.sleep(0.5)
    except Exception:
        _LAST_RENDER_ERROR = "comfyui_unreachable"
        return None

    _LAST_RENDER_ERROR = "comfyui_no_motion_output"
    return None
