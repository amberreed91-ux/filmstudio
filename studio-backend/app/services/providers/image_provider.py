from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.reference_validation import authorize_runway_router_image_references
from app.services.stability import ValidationError

logger = logging.getLogger("image-provider")

# Registered hosted image providers (provider registry additions). Selection
# stays config-gated: an entry is only used when the operator sets
# IMAGE_PROVIDER_NAME to it, so existing defaults are unchanged.
# Additive: "runway" joins NVIDIA behind the same seam; nothing about the
# NVIDIA selection path changes. "runway_router" adds the Runway Model Router
# (configId-based, model-agnostic) without touching either existing path.
_IMAGE_PROVIDER_REGISTRY = frozenset({"local_image", "nvidia", "runway", "runway_router"})


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def build_image_render_payload(scene: Any, shot: Any, prompt_pack: Any) -> Dict[str, Any]:
    scene_dict = scene if isinstance(scene, dict) else {}
    shot_dict = shot if isinstance(shot, dict) else {}
    prompt_dict = prompt_pack if isinstance(prompt_pack, dict) else {}

    scene_id = _as_clean_str(scene_dict.get("scene_id")) or "scene_001"
    shot_id = _as_clean_str(shot_dict.get("shot_id")) or "shot_001"
    raw_base_prompt = prompt_dict.get("base_prompt")
    base_prompt = raw_base_prompt if isinstance(raw_base_prompt, str) else ""
    reference_sets = [
        shot_dict.get(key)
        for key in ("reference_assets", "referenceAssets", "references")
        if isinstance(shot_dict.get(key), list)
    ]
    references = []
    seen_references: set[str] = set()
    for reference_set in reference_sets:
        for reference in reference_set:
            uri = str(reference.get("image_url") or reference.get("url") or reference.get("uri") or reference.get("asset_url") or "").strip() if isinstance(reference, dict) else str(reference or "").strip()
            # De-duplicate only identical fetchable URIs across the separate
            # canonical source lists. Preserve malformed entries so the Router
            # boundary rejects them instead of silently dropping them.
            if uri and uri in seen_references:
                continue
            if uri:
                seen_references.add(uri)
            references.append(reference)

    payload = {
        "scene_id": scene_id,
        "shot_id": shot_id,
        "storyboard_shot_id": _as_clean_str(shot_dict.get("storyboard_shot_id")),
        "base_prompt": base_prompt,
        "style_tags": prompt_dict.get("style_tags") if isinstance(prompt_dict.get("style_tags"), list) else [],
        "meta": {
            "heading": _as_clean_str(scene_dict.get("heading")),
            "location": _as_clean_str(scene_dict.get("location")),
            "time_of_day": _as_clean_str(scene_dict.get("time_of_day")),
        },
    }
    if references:
        # Preserve the canonical reference set at the provider seam. Each
        # hosted provider is responsible for its own documented cap and must
        # fail closed instead of silently clipping the list.
        payload["references"] = references
    return payload


def submit_image_render(payload: Any, config: Any) -> Dict[str, Any]:
    """Provider-agnostic image submission seam.

    Adds the NVIDIA FLUX.2 Klein 4B hosted provider through this existing
    abstraction: NVIDIA-specific request/response handling lives entirely in
    ``providers/nvidia_image_provider.py`` and is only invoked when the
    operator configures ``image_provider_name = "nvidia"``. Every other
    provider selection (including the legacy default) keeps its existing
    behavior unchanged, and storyboard/reference/scene services never see an
    NVIDIA field — they call this seam exactly as before.
    """
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

    if provider_name not in _IMAGE_PROVIDER_REGISTRY:
        return {
            "render_id": render_id,
            "status": "failed",
            "provider": provider_name,
            "url": None,
            "file_path": None,
            "error": f"Unknown image provider '{provider_name}'",
            "meta": {"reason": "unknown_image_provider"},
        }

    if provider_name == "nvidia":
        # NVIDIA hosted path. Credential comes from NVIDIA_API_KEY via the
        # module's environment reader; the config-injected key is ignored for
        # this provider so credential handling has exactly one mechanism.
        from .nvidia_image_provider import submit_nvidia_image_render

        prompt_pack = payload_dict.get("prompt") if isinstance(payload_dict.get("prompt"), dict) else {}
        # Canonical prompt authority: build_image_render_payload emits the base
        # prompt at the payload top level, so that exact value is what NVIDIA
        # must consume. The nested prompt_pack["base_prompt"] shape is kept as
        # a legacy fallback for direct callers; no prompt is ever fabricated.
        base_prompt = _as_clean_str(payload_dict.get("base_prompt")) or _as_clean_str(prompt_pack.get("base_prompt"))
        meta = payload_dict.get("meta") if isinstance(payload_dict.get("meta"), dict) else {}
        aspect_ratio = _as_clean_str(meta.get("aspect_ratio")) or "1:1"
        seed = meta.get("seed")
        result = submit_nvidia_image_render(base_prompt, aspect_ratio=aspect_ratio, seed=seed)
        status = "success" if result.get("status") == "success" else "failed"
        return {
            "render_id": render_id,
            "status": status,
            "provider": "nvidia",
            "url": result.get("url"),
            "file_path": result.get("file_path"),
            "error": result.get("error"),
            "meta": {
                **(result.get("meta") or {}),
                "reason": "nvidia_image_generated" if status == "success" else "nvidia_image_failed",
            },
        }

    if provider_name == "runway":
        # Runway hosted path (gen4_image). Credential comes from RUNWAY_API_KEY
        # (or RUNWAYML_API_SECRET) via the module's environment reader; the
        # config-injected key is ignored for this provider so credential
        # handling has exactly one mechanism — mirroring the NVIDIA contract.
        from .runway_image_provider import submit_runway_image_render

        prompt_pack = payload_dict.get("prompt") if isinstance(payload_dict.get("prompt"), dict) else {}
        # Canonical prompt authority: build_image_render_payload emits the base
        # prompt at the payload top level, so that exact value is what Runway
        # must consume. The nested prompt_pack["base_prompt"] shape is kept as
        # a legacy fallback for direct callers; no prompt is ever fabricated.
        base_prompt = _as_clean_str(payload_dict.get("base_prompt")) or _as_clean_str(prompt_pack.get("base_prompt"))
        meta = payload_dict.get("meta") if isinstance(payload_dict.get("meta"), dict) else {}
        aspect_ratio = _as_clean_str(meta.get("aspect_ratio")) or "1:1"
        seed = meta.get("seed")
        references = payload_dict.get("references") if isinstance(payload_dict.get("references"), list) else None
        result = submit_runway_image_render(
            base_prompt, aspect_ratio=aspect_ratio, seed=seed, references=references
        )
        status = "success" if result.get("status") == "success" else "failed"
        return {
            "render_id": render_id,
            "status": status,
            "provider": "runway",
            "url": result.get("url"),
            "file_path": result.get("file_path"),
            "error": result.get("error"),
            "meta": {
                **(result.get("meta") or {}),
                "reason": "runway_image_generated" if status == "success" else "runway_image_failed",
            },
        }

    if provider_name == "runway_router":
        # Runway Model Router path: configId-based, model-agnostic. Credential
        # comes from RUNWAY_API_KEY (or RUNWAYML_API_SECRET) via the module's
        # environment reader — one credential mechanism across Runway surfaces.
        from .runway_router_provider import submit_runway_router_image_render

        prompt_pack = payload_dict.get("prompt") if isinstance(payload_dict.get("prompt"), dict) else {}
        top_level_prompt = payload_dict.get("base_prompt")
        nested_prompt = prompt_pack.get("base_prompt")
        base_prompt = (
            top_level_prompt
            if isinstance(top_level_prompt, str) and top_level_prompt
            else nested_prompt if isinstance(nested_prompt, str) else ""
        )
        meta = payload_dict.get("meta") if isinstance(payload_dict.get("meta"), dict) else {}
        aspect_ratio = _as_clean_str(meta.get("aspect_ratio")) or "16:9"
        seed = meta.get("seed")
        authorization_payload = {
            **payload_dict,
            "project_id": payload_dict.get("project_id") or meta.get("project_id"),
        }
        try:
            authorization = authorize_runway_router_image_references(payload=authorization_payload)
        except ValidationError as exc:
            return {
                "render_id": render_id,
                "status": "failed",
                "provider": "runway_router",
                "url": None,
                "file_path": None,
                "error": exc.message,
                "meta": {
                    "reason": "image_reference_authorization_failed",
                    "reference_authorization_error": exc.to_dict(),
                },
            }
        result = submit_runway_router_image_render(
            base_prompt,
            aspect_ratio=aspect_ratio,
            seed=seed,
            references=authorization["references"],
            dry_run=bool(payload_dict.get("dry_run") or meta.get("dry_run") or False),
        )
        result_meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        result_meta = {
            **result_meta,
            "reference_authorization": {
                "project_id": authorization["project_id"],
                "scene_id": authorization["scene_id"],
                "shot_id": authorization["shot_id"],
                "storyboard_version_id": authorization["storyboard_version_id"],
                "storyboard_shot_id": authorization["storyboard_shot_id"],
                "binding_sha256": authorization["binding_sha256"],
                "generation_context_id": authorization["generation_context_id"],
            },
            "authorized_references": authorization["references"],
        }
        if isinstance(result, dict):
            result["meta"] = result_meta
        else:
            result = {"status": "failed", "url": None, "file_path": None, "error": "Malformed Runway Router result", "meta": result_meta}
        if result.get("status") == "success":
            task_id = _as_clean_str(result_meta.get("runway_task_id"))
            output_url = _as_clean_str(result.get("url"))
            identity = result_meta.get("output_identity")
            identity = identity if isinstance(identity, dict) else None
            required_identity = (
                _as_clean_str(identity.get("provider_task_id")) if identity else "",
                _as_clean_str(identity.get("output_url")) if identity else "",
                _as_clean_str(identity.get("association_source")) if identity else "",
            )
            if not task_id or not output_url or identity is None or not all(required_identity):
                identity_reason = "provider_output_identity_missing"
                identity_error = "Runway Router image success did not carry a complete task/output association"
            elif (
                required_identity[0] != task_id
                or required_identity[1] != output_url
                or required_identity[2] != "runway_router_polled_task"
            ):
                identity_reason = "provider_output_identity_mismatch"
                identity_error = "Runway Router image output identity did not match its polled task and URL"
            else:
                identity_reason = ""
                identity_error = ""
            if identity_reason:
                result = {
                    **result,
                    "status": "failed",
                    "url": None,
                    "error": identity_error,
                    "meta": {**result_meta, "reason": identity_reason},
                }
        status = result.get("status")
        result_meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        if status == "dry_run":
            return {
                "render_id": render_id,
                "status": "dry_run",
                "provider": "runway_router",
                "url": None,
                "file_path": None,
                "error": None,
                "meta": {
                    **result_meta,
                    "reason": "runway_router_dry_run",
                },
            }
        success = status == "success"
        result_reason = "" if success else _as_clean_str(result_meta.get("reason"))
        if not result_reason:
            result_reason = "runway_router_image_generated" if success else "runway_router_image_failed"
        return {
            "render_id": render_id,
            "status": "success" if success else "failed",
            "provider": "runway_router",
            "url": result.get("url"),
            "file_path": result.get("file_path"),
            "error": result.get("error"),
            "meta": {
                **result_meta,
                "reason": result_reason,
            },
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
    if status not in {"success", "failed", "pending", "not_executed", "dry_run"}:
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
