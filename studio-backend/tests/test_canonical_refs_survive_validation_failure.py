"""Regression: canonical refs must survive a validation failure (generic, not Scene 002-specific).

Historical bug shape (Scene 002):
  a storyboard image was mixed into the canonical supplied URLs, a validation
  exception then cleared the canonical references, and only the storyboard
  frame remained -- a silent reduction instead of a structured rejection.

This suite is intentionally generic (synthetic project/scene/shot IDs, no real
project data, no provider calls). It proves at the frozen-contract boundary:

  1. canonical character + setting refs plus a storyboard frame coexist with
     separate provenance (canonical vs composition);
  2. mixing the storyboard URL into the canonical supplied URLs is a
     structured rejection (ValueError), not a silent reduction;
  3. with a validation failure injected after freeze, the original frozen
     contract's canonical refs are never cleared, the storyboard stays
     separate, and re-validation is a structured GenerationContractError
     rather than a contract reduced to the storyboard frame.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import pytest

from app.services.generation_contract import (
    FrozenGenerationContract,
    GenerationContractError,
    freeze_dialogue_handoff,
    freeze_generation_contract,
)
from app.services.reference_validation import reference_binding_for_requirements

PROJECT_ID = "project-canonical-survival-regression"
SCENE_ID = "scene_regression_001"
SHOT_ID = "scene_regression_001_shot_001"
CHARACTER_ID = "char-regression-ava"
SETTING_ID = "set-regression-harbor"
CHARACTER_URL = "https://cdn.example.test/regression-ava-face.png"
SETTING_URL = "https://cdn.example.test/regression-harbor-env.png"
STORYBOARD_URL = "https://cdn.example.test/regression-board-frame.png"


def _character_row() -> dict[str, Any]:
    return {
        "ref_id": "ref-regression-ava-face",
        "uri": CHARACTER_URL,
        "target_type": "character",
        "target_id": CHARACTER_ID,
        "role": "face",
        "category": "face",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "character_face",
    }


def _setting_row() -> dict[str, Any]:
    return {
        "ref_id": "ref-regression-harbor-env",
        "project_id": PROJECT_ID,
        "uri": SETTING_URL,
        "target_type": "setting",
        "target_id": SETTING_ID,
        "role": "environment",
        "category": "environment",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "environment",
    }


def _requirements(binding: list[dict[str, Any]]) -> dict[str, Any]:
    char_rows = [dict(r) for r in binding if r.get("target_type") == "character"]
    setting_rows = [dict(r) for r in binding if r.get("target_type") == "setting"]
    return {
        "scene_id": SCENE_ID,
        "character_ids": [CHARACTER_ID],
        "characters": {
            CHARACTER_ID: {
                "name": "Ava",
                "urls": [r["uri"] for r in char_rows],
                "references": char_rows,
            }
        },
        "setting_id": SETTING_ID,
        "setting_urls": [r["uri"] for r in setting_rows],
        "setting_references": setting_rows,
        "allowed_urls": [r["uri"] for r in binding],
    }


def _freeze_input_rows(binding: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "uri": row["uri"],
            "studio_role": row.get("role") or "reference",
            "source": "canonical_reference_binding",
            "ref_id": row.get("ref_id") or "",
            "target_type": row.get("target_type") or "",
            "target_id": row.get("target_id") or "",
            "category": row.get("category") or "",
            "canonical": bool(row.get("canonical")),
            "approval_state": row.get("approval_state") or "approved",
            "source_kind": row.get("source_kind") or "confirmed",
            "kind": row.get("kind") or "character_face",
        }
        for row in binding
    ]


def _resolved_coverage(binding: list[dict[str, Any]]):
    from app.services.camera_provenance import camera_plan_digest
    from app.services.scene_coverage_contract import build_scene_coverage_contract

    scene = {
        "scene_id": SCENE_ID,
        "heading": "INT. REGRESSION ROOM - DAY",
        "text": "A lamp glows beside a closed book.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": PROJECT_ID,
        "script_text": "INT. REGRESSION ROOM - DAY\nA lamp glows beside a closed book.",
        "execution_summary": {"scenes": [scene]},
    }
    camera_plan = {"camera": "Hold", "framing": "Wide"}
    shot_params = {
        "camera_plan": camera_plan,
        "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": PROJECT_ID,
        "camera_source_scene_id": SCENE_ID,
        "camera_source_shot_id": SHOT_ID,
        "camera_target_project_id": PROJECT_ID,
        "camera_target_scene_id": SCENE_ID,
        "camera_target_shot_id": SHOT_ID,
    }
    shot_params["camera_source_digest"] = camera_plan_digest(
        camera_plan,
        "USER_SPECIFIED",
        source_project_id=PROJECT_ID,
        source_scene_id=SCENE_ID,
        source_shot_id=SHOT_ID,
    )
    shots = [{"shot_id": SHOT_ID, "scene_id": SCENE_ID, "parameters": dict(shot_params)}]
    char_rows = [r for r in binding if r.get("target_type") == "character"]
    requirements = {
        "setting_id": SETTING_ID,
        "characters": (
            {CHARACTER_ID: {"name": "Ava", "urls": [char_rows[0]["uri"]], "references": [dict(char_rows[0])]}}
            if char_rows
            else {}
        ),
        "reference_binding": binding,
    }
    probe, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID,
        project=project,
        scene=scene,
        shots=shots,
        reference_requirements={
            "setting_id": requirements["setting_id"],
            "characters": requirements["characters"],
            "reference_binding": binding,
        },
    )
    decisions = [
        {
            "obligation_type": "content",
            "obligation_id": row["content_id"],
            "status": "ASSIGNED",
            "shot_id": SHOT_ID,
            "reason": "",
        }
        for row in probe["content_units"]
    ]
    decisions.extend(
        [
            {
                "obligation_type": "shot_content",
                "obligation_id": SHOT_ID,
                "status": "UNRESOLVED",
                "shot_id": None,
                "reason": "",
            },
            {
                "obligation_type": "shot_dialogue",
                "obligation_id": SHOT_ID,
                "status": "INTENTIONAL_SILENCE",
                "reason": "The approved shot contains no spoken dialogue.",
            },
        ]
    )
    coverage, blockers, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID,
        project=project,
        scene=scene,
        shots=shots,
        reference_requirements={
            "setting_id": requirements["setting_id"],
            "characters": requirements["characters"],
            "reference_binding": binding,
        },
        creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_coverage = next(r for r in coverage["shots"] if r["shot_id"] == SHOT_ID)
    handoff = freeze_dialogue_handoff(scene_id=SCENE_ID, shot_id=SHOT_ID, lines=[])
    return coverage, shot_coverage, handoff


def _freeze_canonical_plus_storyboard(binding: list[dict[str, Any]]):
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    return freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved regression prompt bytes.",
        reference_assets=_freeze_input_rows(binding),
        parameters={
            "duration": 5,
            "aspect_ratio": "16:9",
            "reference_roles": [row.get("role") or "reference" for row in binding],
            "storyboard_frame_url": STORYBOARD_URL,
        },
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )


def _canonical_refs(frozen: FrozenGenerationContract) -> list:
    return [r for r in frozen.references if r.source == "canonical_reference_binding"]


def _composition_refs(frozen: FrozenGenerationContract) -> list:
    return [r for r in frozen.references if r.source == "storyboard_frame_url"]


def test_storyboard_mixed_into_supplied_urls_is_structured_rejection():
    """The old bug mixed the board frame into canonical supplied URLs.

    The validator must raise (structured rejection) rather than return a
    silently reduced binding. The caller's canonical list must be untouched.
    """
    binding = [_character_row(), _setting_row()]
    before = deepcopy(binding)
    supplied = [row["uri"] for row in binding] + [STORYBOARD_URL]
    with pytest.raises(ValueError, match="not one of the prepared canonical"):
        reference_binding_for_requirements(
            _requirements(binding),
            supplied_urls=supplied,
        )
    # Canonical refs are never cleared/mutated by the rejected call.
    assert binding == before
    assert [row["uri"] for row in binding] == [CHARACTER_URL, SETTING_URL]


def test_canonical_and_storyboard_coexist_with_separate_provenance():
    """Canonical character + setting refs plus a storyboard frame coexist."""
    frozen = _freeze_canonical_plus_storyboard([_character_row(), _setting_row()])
    canonical = _canonical_refs(frozen)
    composition = _composition_refs(frozen)
    assert {r.uri for r in canonical} == {CHARACTER_URL, SETTING_URL}
    assert len(composition) == 1 and composition[0].uri == STORYBOARD_URL
    # Storyboard stays separate: empty ref_id, composition source/category.
    assert composition[0].ref_id == ""
    assert composition[0].source == "storyboard_frame_url"
    assert STORYBOARD_URL not in {r.uri for r in canonical}


def test_validation_failure_never_clears_canonical_refs():
    """Inject a validation failure; assert no silent reduction to storyboard-only.

    Tampering one canonical ref_id simulates the historical validation
    exception. Re-validation must raise a structured GenerationContractError,
    the original frozen contract must retain both canonical refs plus the
    separate storyboard frame, and the failure must never resolve to a
    contract containing only the storyboard frame.
    """
    frozen = _freeze_canonical_plus_storyboard([_character_row(), _setting_row()])
    canonical_before = [(r.ref_id, r.uri) for r in _canonical_refs(frozen)]
    assert len(canonical_before) == 2

    record = frozen.to_record()
    tampered = deepcopy(record)
    tampered["payload"]["references"][0] = {
        **tampered["payload"]["references"][0],
        "ref_id": "ref-tampered",
    }
    canonical = json.dumps(tampered["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    tampered["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(GenerationContractError):
        FrozenGenerationContract.from_record(tampered)

    # Original is untouched: canonical refs are never cleared by the failure.
    assert [(r.ref_id, r.uri) for r in _canonical_refs(frozen)] == canonical_before
    # Storyboard stays separate on the original.
    composition = _composition_refs(frozen)
    assert len(composition) == 1 and composition[0].uri == STORYBOARD_URL
    assert composition[0].ref_id == ""
    # Guard the exact historical outcome: a contract reduced to only the
    # storyboard frame must never validate.
    assert len(frozen.references) == 3
