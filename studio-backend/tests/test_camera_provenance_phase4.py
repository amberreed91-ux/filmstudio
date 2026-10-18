from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.camera_provenance import (
    CAMERA_PROVENANCE_AI,
    CAMERA_PROVENANCE_CREATOR,
    CAMERA_PROVENANCE_STORYBOARD,
    CAMERA_PROVENANCE_UNSPECIFIED,
    authoritative_camera_source,
    camera_plan_digest,
    verify_camera_source_identity,
)
from app.services.generation_context_service import (
    CAMERA_SOURCE_AI_SUGGESTED,
    GenerationContextService,
)
from app.services.generation_contract import (
    FrozenGenerationContract,
    GenerationContractError,
    freeze_generation_contract,
)


PROJECT = "project-phase4"
SCENE = "scene_012"
SHOT = "scene_012_shot_003"
BOARD_SHOT = "storyboard-shot-003"
PLAN = {"camera": "Measured dolly in", "framing": "Medium close-up"}


def _board_shot(*, project_id=PROJECT, scene_id=SCENE, shot_id=SHOT, board_shot_id=BOARD_SHOT, plan=None):
    return SimpleNamespace(
        project_id=project_id,
        scene_id=scene_id,
        shot_id=shot_id,
        storyboard_shot_id=board_shot_id,
        render_contract=SimpleNamespace(
            structured_parameters={"camera_plan": plan if plan is not None else PLAN}
        ),
    )


def _freeze(plan, provenance, *, storyboard_shot_id="", source_scene=SCENE, source_shot=SHOT, extra=None):
    params = {
        "camera_plan": plan,
        "camera_provenance": provenance,
        "camera_source_project_id": PROJECT,
        "camera_source_scene_id": source_scene,
        "camera_source_shot_id": source_shot,
        "camera_source_storyboard_shot_id": storyboard_shot_id,
        "camera_target_project_id": PROJECT,
        "camera_target_scene_id": SCENE,
        "camera_target_shot_id": SHOT,
        **(extra or {}),
    }
    params["camera_source_digest"] = camera_plan_digest(
        plan,
        provenance,
        source_project_id=PROJECT,
        source_scene_id=source_scene,
        source_shot_id=source_shot,
        source_storyboard_shot_id=storyboard_shot_id,
    )
    return freeze_generation_contract(shot_id=SHOT, prompt="approved shot", parameters=params)


def test_approved_storyboard_camera_is_exact_shot_authority():
    plan, provenance = authoritative_camera_source(
        storyboard_shot_id=BOARD_SHOT,
        project_id=PROJECT,
        scene_id=SCENE,
        shot_id=SHOT,
        shot=_board_shot(),
        fallback_parameters={},
    )
    assert plan == PLAN
    assert provenance == CAMERA_PROVENANCE_STORYBOARD
    frozen = _freeze(plan, provenance, storyboard_shot_id=BOARD_SHOT)
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert restored.payload()["camera_plan"] == PLAN
    assert restored.payload()["camera_provenance"] == "APPROVED"
    assert restored.payload()["camera_source_project_id"] == restored.payload()["camera_target_project_id"] == PROJECT
    assert restored.payload()["camera_source_scene_id"] == restored.payload()["camera_target_scene_id"] == SCENE
    assert restored.payload()["camera_source_shot_id"] == restored.payload()["camera_target_shot_id"] == SHOT
    assert restored.payload()["camera_source_storyboard_shot_id"] == BOARD_SHOT
    assert restored.payload()["camera_instructions"] == [
        {"dimension": "camera", "value": "Measured dolly in", "instruction_source": "APPROVED", "source_version": ""},
        {"dimension": "framing", "value": "Medium close-up", "instruction_source": "APPROVED", "source_version": ""},
        {"dimension": "shot_size", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "angle", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "movement", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "lens", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
    ]


@pytest.mark.parametrize(
    "identity",
    [
        {"project_id": "project-other", "scene_id": SCENE, "shot_id": SHOT},
        {"project_id": PROJECT, "scene_id": "scene_other", "shot_id": SHOT},
        {"project_id": PROJECT, "scene_id": SCENE, "shot_id": "scene_012_shot_004"},
        {"project_id": PROJECT, "scene_id": SCENE, "shot_id": SHOT, "board_shot_id": "other-board-row"},
    ],
)
def test_storyboard_camera_from_another_project_scene_shot_or_row_is_rejected(identity):
    with pytest.raises(GenerationContractError, match="identity"):
        authoritative_camera_source(
            storyboard_shot_id=BOARD_SHOT,
            project_id=PROJECT,
            scene_id=SCENE,
            shot_id=SHOT,
            shot=_board_shot(**identity),
            fallback_parameters={},
        )


def test_creator_camera_plan_is_authoritative_without_board():
    plan, provenance = authoritative_camera_source(
        storyboard_shot_id="",
        project_id=PROJECT,
        scene_id=SCENE,
        shot_id=SHOT,
        shot=None,
        fallback_parameters={"creator_shot_planning": {"camera": "Locked-off", "framing": "Wide"}},
    )
    assert plan == {"camera": "Locked-off", "framing": "Wide"}
    assert provenance == CAMERA_PROVENANCE_CREATOR
    frozen = _freeze(plan, provenance)
    assert frozen.payload()["camera_provenance"] == "USER_SPECIFIED"
    instructions = frozen.payload()["camera_instructions"]
    assert {row["dimension"]: row["value"] for row in instructions if row["value"]} == plan
    assert all(row["instruction_source"] == CAMERA_PROVENANCE_CREATOR for row in instructions if row["value"])


def test_approved_storyboard_camera_preflight_context_reports_the_same_value():
    context_service = GenerationContextService()
    board = _board_shot()
    context = context_service.create_generation_context(
        project_id=PROJECT,
        scene_id=SCENE,
        shot_id=SHOT,
        scene={"scene_id": SCENE, "text": "scene"},
        storyboard_context={"version": "version-approved"},
        reference_assets=[],
        camera_instructions=context_service.derive_camera_instructions(
            approved_camera_plan=PLAN,
            storyboard_shot=board,
        ),
        shot=board,
        require_shot_version=True,
    )
    readiness = context_service.validate_generation_context(
        context=context,
        current_scene={"scene_id": SCENE, "text": "scene"},
        current_storyboard_context={"version": "version-approved"},
        current_reference_assets=[],
        expected_scene_id=SCENE,
        expected_shot_id=SHOT,
        current_shot=board,
    )
    assert readiness.ready
    assert {row.dimension: row.value for row in readiness.context.camera_instructions if row.value} == PLAN


def test_ai_camera_context_is_blocked_by_readiness_even_when_plan_not_frozen():
    context_service = GenerationContextService()
    board = _board_shot(plan={})
    context = context_service.create_generation_context(
        project_id=PROJECT,
        scene_id=SCENE,
        shot_id=SHOT,
        scene={"scene_id": SCENE, "text": "scene"},
        storyboard_context={"version": "version-approved"},
        reference_assets=[],
        camera_instructions=context_service.derive_camera_instructions(
            ai_suggested_camera={"camera": "Template pan"},
        ),
        shot=board,
        require_shot_version=True,
    )
    readiness = context_service.validate_generation_context(
        context=context,
        current_scene={"scene_id": SCENE, "text": "scene"},
        current_storyboard_context={"version": "version-approved"},
        current_reference_assets=[],
        expected_scene_id=SCENE,
        expected_shot_id=SHOT,
        current_shot=board,
    )
    assert not readiness.ready
    assert any("unapproved AI suggestion" in blocker for blocker in readiness.blockers)
    assert all(row.instruction_source == CAMERA_SOURCE_AI_SUGGESTED for row in context.camera_instructions if row.value)


def test_creator_camera_plan_remains_authoritative_when_selected_board_has_no_camera():
    plan, provenance = authoritative_camera_source(
        storyboard_shot_id=BOARD_SHOT,
        project_id=PROJECT,
        scene_id=SCENE,
        shot_id=SHOT,
        shot=_board_shot(plan={}),
        fallback_parameters={"creator_shot_planning": {"camera": "Locked-off"}},
    )
    assert plan == {"camera": "Locked-off"}
    assert provenance == CAMERA_PROVENANCE_CREATOR


def test_ai_only_and_unspecified_camera_contracts_are_distinct_and_non_authoritative():
    ai = _freeze({}, CAMERA_PROVENANCE_AI)
    unspecified = _freeze({}, CAMERA_PROVENANCE_UNSPECIFIED)
    assert ai.payload()["camera_provenance"] == "AI_SUGGESTED"
    assert unspecified.payload()["camera_provenance"] == "UNSPECIFIED"
    with pytest.raises(GenerationContractError, match="cannot carry"):
        _freeze(PLAN, CAMERA_PROVENANCE_AI)
    assert ai.payload()["camera_instructions"] == [
        {"dimension": "shot_size", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "angle", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "movement", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "lens", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
        {"dimension": "framing", "value": "", "instruction_source": "UNSPECIFIED", "source_version": ""},
    ]


def test_generic_fallback_camera_plan_is_not_a_camera_source():
    for board in (None, _board_shot(plan={})):
        with pytest.raises(GenerationContractError, match="Fallback camera_plan is not authoritative"):
            authoritative_camera_source(
                storyboard_shot_id="" if board is None else BOARD_SHOT,
                project_id=PROJECT,
                scene_id=SCENE,
                shot_id=SHOT,
                shot=board,
                fallback_parameters={"camera_plan": {"camera": "Injected crane"}},
            )


def test_creator_input_does_not_claim_unapproved_board_values():
    with pytest.raises(GenerationContractError, match="does not match"):
        authoritative_camera_source(
            storyboard_shot_id=BOARD_SHOT,
            project_id=PROJECT,
            scene_id=SCENE,
            shot_id=SHOT,
            shot=_board_shot(),
            fallback_parameters={"creator_shot_planning": {"camera": "Different move"}},
        )


def test_frozen_camera_instructions_are_bound_to_plan_provenance_and_shot():
    frozen = _freeze(PLAN, CAMERA_PROVENANCE_CREATOR)
    payload = frozen.payload()
    assert payload["camera_plan"] == PLAN
    assert payload["camera_provenance"] == CAMERA_PROVENANCE_CREATOR
    assert {row["dimension"]: row["value"] for row in payload["camera_instructions"] if row["value"]} == PLAN

    record = frozen.to_record()
    record["payload"]["camera_instructions"][0]["value"] = "different projection"
    import hashlib
    import json

    encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    with pytest.raises(GenerationContractError, match="camera instructions"):
        FrozenGenerationContract.from_record(record)


def test_contract_rejects_mutated_camera_digest_or_cross_shot_source():
    frozen = _freeze(PLAN, CAMERA_PROVENANCE_CREATOR)
    record = frozen.to_record()
    record["payload"]["camera_source_digest"] = "0" * 64
    import hashlib
    import json

    encoded = json.dumps(record["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    with pytest.raises(GenerationContractError, match="integrity check"):
        FrozenGenerationContract.from_record(record)

    with pytest.raises(GenerationContractError, match="source identity"):
        _freeze(PLAN, CAMERA_PROVENANCE_CREATOR, source_shot="scene_012_shot_099")


def test_verifier_rejects_contract_target_shot_mismatch():
    digest = camera_plan_digest(
        PLAN,
        CAMERA_PROVENANCE_CREATOR,
        source_project_id=PROJECT,
        source_scene_id=SCENE,
        source_shot_id=SHOT,
    )
    with pytest.raises(GenerationContractError, match="source identity"):
        verify_camera_source_identity(
            plan=PLAN,
            provenance=CAMERA_PROVENANCE_CREATOR,
            source_digest=digest,
            target_project_id=PROJECT,
            target_scene_id=SCENE,
            target_shot_id="scene_012_shot_004",
            source_project_id=PROJECT,
            source_scene_id=SCENE,
            source_shot_id=SHOT,
            source_storyboard_shot_id="",
        )
