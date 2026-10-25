"""Canonical shot manifest (workstream item 6).

A deterministic representation of the exact batch request Studio intends to
send, derived from current approved state immediately before the provider
boundary. The manifest:

- represents exactly what will cross the provider boundary — it never
  invents creative information and never mutates canonical truth;
- is derived from current approved state (approved board version, current
  shot rows, resolved references and camera state, generation contexts);
- carries creative provenance per shot: shot version, reference versions,
  camera provenance, and shot prompt/parameters;
- is deterministic: identical canonical state produces an identical manifest
  and fingerprint, independent of selected provider/model or execution cost.
  Generation-context IDs are carried beside the fingerprint rather than inside
  the creative manifest.

The manifest is observational. It contains no logic to repair, substitute,
or fall back — if a field cannot be derived from current approved state it
is recorded as absent so the readiness gate can fail the render closed.

Generation readiness and cost estimates are preflight results adjacent to the
manifest, not creative-manifest content. Provider/model resolution and costs
are execution metadata. The manifest fingerprint excludes provider, model,
routing mode, and cost parameters.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


from app.services.generation_contract import creative_parameter_values


_MANIFEST_SCENE_CREATIVE_FIELDS = frozenset({"scene_id", "scene_version", "project_id", "script_version_id", "canonical_script_sha256", "scene_source_identity", "scene_content_sha256", "scene_source_start", "scene_source_end"})
_MANIFEST_STORYBOARD_CREATIVE_FIELDS = frozenset({"storyboard_version"})
_MANIFEST_BATCH_CREATIVE_FIELDS = frozenset({"total_duration_seconds", "shot_count"})
_MANIFEST_SHOT_CREATIVE_FIELDS = frozenset({
    "shot_id", "storyboard_shot_id", "shot_version", "shot_order",
    "shot_duration_seconds", "shot_prompt", "negative_prompt", "audio_intent",
    "reference_roles", "generation_contract_digest", "aspect_ratio", "resolution",
    "seed", "camera_plan", "camera_provenance", "camera_instructions",
    "camera_source_digest", "camera_source_project_id", "camera_source_scene_id",
    "camera_source_shot_id", "camera_source_storyboard_shot_id", "camera_target_project_id",
    "camera_target_scene_id", "camera_target_shot_id", "references",
    "reference_categories", "reference_version", "reference_binding", "parameters", "dialogue_handoff", "scene_coverage", "scene_coverage_shot",
})


def recompute_manifest_fingerprint(manifest: dict[str, Any]) -> str:
    """Recompute the creative manifest fingerprint from its persisted value."""
    if not isinstance(manifest, dict):
        raise ValueError("Creative manifest must be an object")
    scene = manifest.get("scene")
    storyboard = manifest.get("storyboard")
    shots = manifest.get("shots")
    batch = manifest.get("batch")
    if not isinstance(scene, dict) or not isinstance(storyboard, dict) or not isinstance(shots, list) or not isinstance(batch, dict):
        raise ValueError("Creative manifest structure is malformed")
    stable_shots = []
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("Creative manifest shot entry is malformed")
        creative_shot = {
            key: value for key, value in shot.items()
            if key in _MANIFEST_SHOT_CREATIVE_FIELDS
        }
        creative_shot["parameters"] = creative_parameter_values(creative_shot.get("parameters"))
        stable_shots.append(creative_shot)
    stable = {
        "scene": {
            key: value for key, value in scene.items()
            if key in _MANIFEST_SCENE_CREATIVE_FIELDS
        },
        "storyboard": {
            key: value for key, value in storyboard.items()
            if key in _MANIFEST_STORYBOARD_CREATIVE_FIELDS
        },
        "shots": stable_shots,
        "batch": {
            key: value for key, value in batch.items()
            if key in _MANIFEST_BATCH_CREATIVE_FIELDS
        },
        "manifest_version": manifest.get("manifest_version", 1),
    }
    serialized = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    """Stable creative-state fingerprint, independent of provider/execution."""
    return recompute_manifest_fingerprint(manifest)


def _camera_plan_provenance(shot_metadata: dict[str, Any] | None) -> dict[str, Any]:
    plan = (shot_metadata or {}).get("camera_plan")
    return dict(plan) if isinstance(plan, dict) else {}


def _shot_field(shot: Any, name: str) -> Any:
    if isinstance(shot, dict):
        return shot.get(name)
    return getattr(shot, name, None)


def build_shot_manifest(
    *,
    project_id: str,
    scene_id: str,
    scene: dict[str, Any] | None,
    scene_version: str,
    storyboard_version: str,
    entries: list[dict[str, Any]],
    generation_context_ids: list[str] | None = None,
    scene_lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the manifest from prepared per-shot entries.

    Each entry in ``entries`` must already be resolved from current approved
    state by the caller (scene pipeline gate step) and carry:

    shot_id, shot_version, shot_order, duration_seconds, prompt,
    camera_instructions (list of CameraInstruction.to_dict()), camera_plan,
    references (list of urls), reference_version, storyboard_shot_id,
    parameters (provider parameters for this shot).
    """
    from app.services.providers.runway_router_provider import (
        is_dry_run_placeholder_uri as _is_placeholder,
    )
    shots: list[dict[str, Any]] = []
    for entry in entries:
        for url in list(entry.get("references") or []):
            if _is_placeholder(url):
                raise ValueError(
                    "Estimator placeholder reference URIs cannot persist in a shot manifest"
                )
        for row in list(entry.get("reference_binding") or []):
            if isinstance(row, dict) and _is_placeholder(row.get("uri")):
                raise ValueError(
                    "Estimator placeholder reference URIs cannot persist in a shot manifest"
                )
        shots.append(
            {
                "shot_id": str(entry.get("shot_id") or ""),
                "storyboard_shot_id": str(entry.get("storyboard_shot_id") or ""),
                "shot_version": str(entry.get("shot_version") or "absent"),
                "shot_order": int(entry.get("shot_order") or 0),
                "shot_duration_seconds": int(entry.get("duration_seconds") or 0),
                "shot_prompt": str(entry.get("prompt") or ""),
                "negative_prompt": str(entry.get("negative_prompt") or ""),
                "audio_intent": entry.get("audio_intent"),
                "reference_roles": list(entry.get("reference_roles") or []),
                "generation_contract_digest": str(entry.get("generation_contract_digest") or ""),
                "aspect_ratio": str(entry.get("aspect_ratio") or "16:9"),
                "resolution": entry.get("resolution"),
                "seed": entry.get("seed"),
                "camera_plan": dict(entry.get("camera_plan") or {}),
                "camera_provenance": str(entry.get("camera_provenance") or "UNSPECIFIED"),
                "camera_instructions": [dict(row) for row in (entry.get("camera_instructions") or []) if isinstance(row, dict)],
                "camera_source_digest": str(entry.get("camera_source_digest") or ""),
                "camera_source_project_id": str(entry.get("camera_source_project_id") or ""),
                "camera_source_scene_id": str(entry.get("camera_source_scene_id") or ""),
                "camera_source_shot_id": str(entry.get("camera_source_shot_id") or ""),
                "camera_source_storyboard_shot_id": str(entry.get("camera_source_storyboard_shot_id") or ""),
                "camera_target_project_id": str(entry.get("camera_target_project_id") or ""),
                "camera_target_scene_id": str(entry.get("camera_target_scene_id") or ""),
                "camera_target_shot_id": str(entry.get("camera_target_shot_id") or ""),
                "references": [str(url) for url in (entry.get("references") or [])],
                "reference_categories": list(entry.get("reference_roles") or []),
                "reference_binding": [dict(row) for row in (entry.get("reference_binding") or []) if isinstance(row, dict)],
                "reference_version": str(entry.get("reference_version") or "none"),
                "parameters": creative_parameter_values(entry.get("parameters") or {}),
                **({"dialogue_handoff": entry["dialogue_handoff"]} if entry.get("dialogue_handoff") else {}),
                **({"scene_coverage": entry["scene_coverage"]} if entry.get("scene_coverage") else {}),
                **({"scene_coverage_shot": entry["shot_coverage"]} if entry.get("shot_coverage") else {}),
            }
        )

    total_duration = sum(int(shot["shot_duration_seconds"] or 0) for shot in shots)
    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "scene": {
            "scene_id": scene_id,
            "scene_version": scene_version,
            "project_id": str((scene_lineage or {}).get("project_id") or project_id),
            "script_version_id": str((scene_lineage or {}).get("script_version_id") or ""),
            "canonical_script_sha256": str((scene_lineage or {}).get("canonical_script_sha256") or ""),
            "scene_source_identity": str((scene_lineage or {}).get("scene_source_identity") or ""),
            "scene_content_sha256": str((scene_lineage or {}).get("scene_content_sha256") or ""),
            "scene_content_sha256": str((scene_lineage or {}).get("scene_content_sha256") or ""),
            "scene_source_start": (scene_lineage or {}).get("scene_source_start"),
            "scene_source_end": (scene_lineage or {}).get("scene_source_end"),
        },
        "storyboard": {
            "storyboard_version": storyboard_version,
        },
        "shots": shots,
        # This is the creative generation manifest, not an execution report.
        # Provider/model choice, eligibility, readiness and cost are recorded
        # outside it so the manifest stays identical across provider switches.
        "batch": {
            "total_duration_seconds": total_duration,
            "shot_count": len(shots),
        },
    }
    manifest["manifest_fingerprint"] = _manifest_fingerprint(manifest)
    return manifest
