"""Camera-plan provenance helpers for prepared and frozen generation inputs."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.generation_contract import GenerationContractError

# Reuse the existing GenerationContext provenance vocabulary. The explicit
# storyboard-shot source identity distinguishes board approval from creator input.
CAMERA_PROVENANCE_STORYBOARD = "APPROVED"
CAMERA_PROVENANCE_CREATOR = "USER_SPECIFIED"
CAMERA_PROVENANCE_UNSPECIFIED = "UNSPECIFIED"
CAMERA_PROVENANCE_AI = "AI_SUGGESTED"


def canonical_camera_plan(plan: Any) -> dict[str, str]:
    """Validate and normalize camera dimensions without coercing malformed data."""
    if not isinstance(plan, dict):
        raise GenerationContractError("Camera plan must be an object")
    normalized: dict[str, str] = {}
    allowed_dimensions = {"camera", "framing", "lens", "focal_length", "aperture", "composition", "blocking"}
    for dimension, value in plan.items():
        if not isinstance(dimension, str) or not dimension.strip():
            raise GenerationContractError("Camera plan dimensions must be non-empty strings")
        dimension = dimension.strip()
        if dimension not in allowed_dimensions:
            raise GenerationContractError(f"Camera plan dimension '{dimension}' is not supported")
        if not isinstance(value, str):
            raise GenerationContractError(f"Camera plan '{dimension}' must be a string")
        value = value.strip()
        if value:
            normalized[dimension] = value
    return normalized


def canonical_camera_instructions(plan: Any, provenance: str) -> list[dict[str, str]]:
    """Derive the structured camera projection from one frozen source.

    This deliberately delegates to the existing GenerationContext camera
    vocabulary/ordering rather than defining a second instruction schema.
    AI suggestions are non-authoritative and are never projected as camera
    plans; their advisory context may remain separately provenance-tagged.
    """
    from app.services.generation_context_service import generation_context_service

    normalized = canonical_camera_plan(plan)
    if provenance == CAMERA_PROVENANCE_CREATOR:
        instructions = generation_context_service.derive_camera_instructions(
            creator_planning=normalized
        )
    elif provenance == CAMERA_PROVENANCE_STORYBOARD:
        instructions = generation_context_service.derive_camera_instructions(
            approved_camera_plan=normalized
        )
    elif provenance in {CAMERA_PROVENANCE_UNSPECIFIED, CAMERA_PROVENANCE_AI}:
        instructions = generation_context_service.derive_camera_instructions()
    else:
        raise GenerationContractError("Frozen camera provenance is missing or invalid")
    return [instruction.to_dict() for instruction in instructions]


def verify_camera_instructions(plan: Any, provenance: str, instructions: Any) -> list[dict[str, str]]:
    """Ensure frozen instructions are canonical for the frozen plan/source."""
    if not isinstance(instructions, list) or any(not isinstance(row, dict) for row in instructions):
        raise GenerationContractError("Frozen camera instructions must be an ordered list of objects")
    expected = canonical_camera_instructions(plan, provenance)
    if instructions != expected:
        raise GenerationContractError(
            "Frozen camera instructions do not match the authoritative camera plan and provenance"
        )
    return expected


def camera_plan_digest(
    plan: Any,
    provenance: str,
    *,
    source_project_id: str,
    source_scene_id: str,
    source_shot_id: str,
    source_storyboard_shot_id: str = "",
) -> str:
    payload = {
        "camera_plan": canonical_camera_plan(plan),
        "camera_provenance": provenance,
        "source_project_id": source_project_id,
        "source_scene_id": source_scene_id,
        "source_shot_id": source_shot_id,
        "source_storyboard_shot_id": source_storyboard_shot_id,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def authoritative_camera_source(
    *,
    storyboard_shot_id: str,
    project_id: str,
    scene_id: str,
    shot_id: str,
    shot: Any,
    fallback_parameters: Any,
) -> tuple[dict[str, str], str]:
    """Resolve camera only from the exact current board shot or creator planning.

    A generic fallback camera_plan is never a source of authority. Where an
    identified board shot has a persisted creator plan, that board record wins.
    """
    params = fallback_parameters if isinstance(fallback_parameters, dict) else {}
    fallback_raw = params.get("camera_plan")
    fallback = canonical_camera_plan(fallback_raw) if fallback_raw is not None else None
    creator_raw = params.get("creator_shot_planning")
    creator = {}
    if creator_raw is not None:
        if not isinstance(creator_raw, dict):
            raise GenerationContractError("creator_shot_planning must be an object")
        creator_dimensions = {"camera", "framing", "lens", "composition", "blocking"}
        creator = canonical_camera_plan(
            {key: value for key, value in creator_raw.items() if key in creator_dimensions}
        )

    if shot is None:
        if storyboard_shot_id:
            raise GenerationContractError("The selected storyboard camera source could not be resolved")
        if fallback:
            raise GenerationContractError(
                "Fallback camera_plan is not authoritative; use creator_shot_planning or an approved storyboard shot"
            )
        return (creator, CAMERA_PROVENANCE_CREATOR) if creator else ({}, CAMERA_PROVENANCE_UNSPECIFIED)

    field = shot.get if isinstance(shot, dict) else lambda key, default=None: getattr(shot, key, default)
    if (
        str(field("project_id", "") or "") != project_id
        or str(field("scene_id", "") or "") != scene_id
        or str(field("shot_id", "") or "") != shot_id
        or (storyboard_shot_id and str(field("storyboard_shot_id", "") or "") != storyboard_shot_id)
    ):
        raise GenerationContractError(
            "Camera source identity does not match the selected project, scene, and shot"
        )

    if creator and not storyboard_shot_id:
        return creator, CAMERA_PROVENANCE_CREATOR

    contract = field("render_contract", None)
    structured = (
        contract.get("structured_parameters") if isinstance(contract, dict)
        else getattr(contract, "structured_parameters", None)
    )
    raw_board_plan = structured.get("camera_plan") if isinstance(structured, dict) else None
    board_plan = canonical_camera_plan(raw_board_plan) if raw_board_plan is not None else {}
    if board_plan:
        if creator and creator != board_plan:
            raise GenerationContractError("Creator camera plan does not match the approved storyboard camera plan")
        if fallback and fallback != board_plan:
            raise GenerationContractError("Fallback camera_plan does not match the exact approved storyboard camera plan")
        return board_plan, CAMERA_PROVENANCE_STORYBOARD
    if creator:
        return creator, CAMERA_PROVENANCE_CREATOR
    if fallback:
        raise GenerationContractError(
            "Fallback camera_plan is not authoritative; use creator_shot_planning or an approved storyboard camera"
        )
    return (creator, CAMERA_PROVENANCE_CREATOR) if creator else ({}, CAMERA_PROVENANCE_UNSPECIFIED)


def verify_camera_source_identity(
    *,
    plan: Any,
    provenance: Any,
    source_digest: Any,
    target_project_id: str,
    target_scene_id: str,
    target_shot_id: str,
    source_project_id: str,
    source_scene_id: str,
    source_shot_id: str,
    source_storyboard_shot_id: str,
) -> tuple[dict[str, str], str]:
    normalized = canonical_camera_plan(plan)
    if provenance not in {
        CAMERA_PROVENANCE_STORYBOARD,
        CAMERA_PROVENANCE_CREATOR,
        CAMERA_PROVENANCE_UNSPECIFIED,
        CAMERA_PROVENANCE_AI,
    }:
        raise GenerationContractError("Frozen camera provenance is missing or invalid")
    if provenance in {CAMERA_PROVENANCE_AI, CAMERA_PROVENANCE_UNSPECIFIED} and normalized:
        raise GenerationContractError(f"{provenance} camera provenance cannot carry an authoritative plan")
    if provenance in {CAMERA_PROVENANCE_STORYBOARD, CAMERA_PROVENANCE_CREATOR} and not normalized:
        raise GenerationContractError("Authoritative camera provenance requires a non-empty camera plan")
    has_target_identity = any((target_project_id, target_scene_id, target_shot_id))
    has_source_identity = any((source_project_id, source_scene_id, source_shot_id))
    if provenance in {CAMERA_PROVENANCE_STORYBOARD, CAMERA_PROVENANCE_CREATOR} and (
        not target_project_id or not target_scene_id or not target_shot_id
    ):
        raise GenerationContractError("Authoritative camera target identity is incomplete")
    if has_target_identity != has_source_identity:
        raise GenerationContractError("Frozen camera source and target identities are incomplete")
    if has_target_identity and (
        not all((target_project_id, target_scene_id, target_shot_id))
        or not all((source_project_id, source_scene_id, source_shot_id))
        or (source_project_id, source_scene_id, source_shot_id)
        != (target_project_id, target_scene_id, target_shot_id)
    ):
        raise GenerationContractError("Frozen camera source identity does not match the selected project, scene, and shot")
    if provenance == CAMERA_PROVENANCE_STORYBOARD and not source_storyboard_shot_id:
        raise GenerationContractError("Approved storyboard camera requires exact storyboard shot identity")
    if source_storyboard_shot_id and not has_target_identity:
        raise GenerationContractError("Storyboard source identity requires an exact camera target identity")
    expected = camera_plan_digest(
        normalized,
        str(provenance),
        source_project_id=source_project_id,
        source_scene_id=source_scene_id,
        source_shot_id=source_shot_id,
        source_storyboard_shot_id=source_storyboard_shot_id,
    )
    if source_digest != expected:
        raise GenerationContractError("Frozen camera plan provenance integrity check failed")
    return normalized, str(provenance)
