"""Phase A: shared creative-parameter classification correction.

Proves, without rendering or provider calls:
- ``project_id`` is orchestration metadata, excluded from creative parameters;
- ``storyboard_frame_identity_collision`` is provenance/coverage metadata,
  excluded from creative parameters but preserved in coverage;
- manifest and contract creative derivations converge;
- Router fail-closed behaviour for non-empty creative_parameters is intact;
- no Scene 002 specific logic is introduced;
- frozen-contract integrity is never bypassed.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.generation_contract import (
    EXECUTION_ONLY_PARAMETER_KEYS,
    FrozenGenerationContract,
    creative_parameter_values,
    freeze_dialogue_handoff,
    freeze_generation_contract,
)


PROJECT_ID = "project-phase-a"
SCENE_ID = "scene_001"
SHOT_ID = "scene_001_shot_001"
SETTING_ID = "set-test-room"


def _binding_rows() -> list[dict[str, Any]]:
    return [
        {
            "ref_id": "ref-face-a",
            "uri": "https://cdn.example.test/face-a.png",
            "target_type": "character",
            "target_id": "char-a",
            "role": "face",
            "category": "face",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "ref-env-a",
            "uri": "https://cdn.example.test/env-a.png",
            "target_type": "setting",
            "target_id": SETTING_ID,
            "role": "environment",
            "category": "environment",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "environment",
        },
    ]


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


def test_01_project_id_excluded_from_creative_parameter_values():
    assert "project_id" in EXECUTION_ONLY_PARAMETER_KEYS
    result = creative_parameter_values({"project_id": PROJECT_ID, "style_hint": "noir"})
    assert "project_id" not in result
    assert result["style_hint"] == "noir"


def test_02_real_creative_parameters_remain_included():
    params = {"style_hint": "noir", "mood": "tense", "project_id": PROJECT_ID}
    result = creative_parameter_values(params)
    assert result == {"style_hint": "noir", "mood": "tense"}


def test_03_scene_id_remains_execution_only():
    assert "scene_id" in EXECUTION_ONLY_PARAMETER_KEYS
    result = creative_parameter_values({"scene_id": SCENE_ID, "style_hint": "noir"})
    assert "scene_id" not in result
    assert result == {"style_hint": "noir"}


def test_04_existing_execution_only_keys_retain_behavior():
    params: dict[str, Any] = {
        "duration": 5,
        "duration_seconds": 5,
        "aspect_ratio": "16:9",
        "ratio": "16:9",
        "resolution": "720p",
        "seed": 7,
        "camera_plan": {"camera": "Hold"},
        "camera_provenance": "USER_SPECIFIED",
        "camera_instructions": [{"kind": "hold"}],
        "camera_source_digest": "abc",
        "dialogue_lines": [{"text": "hi"}],
        "dialogue_handoff": {"payload": {}},
        "reference_assets": ["https://cdn.example.test/x.png"],
        "reference_roles": ["face"],
        "reference_count": 1,
        "shot_id": SHOT_ID,
        "scene_id": SCENE_ID,
        "project_id": PROJECT_ID,
        "storyboard_frame_url": "https://cdn.example.test/board.png",
        "storyboard": {"version": "v1"},
        "style_hint": "noir",
    }
    result = creative_parameter_values(params)
    # Every execution-only key above is filtered; only genuinely creative keys survive.
    assert result == {"style_hint": "noir"}
    for key in (
        "duration", "duration_seconds", "aspect_ratio", "ratio", "resolution",
        "seed", "camera_plan", "camera_provenance", "camera_instructions",
        "camera_source_digest", "dialogue_lines", "dialogue_handoff",
        "reference_assets", "reference_roles", "reference_count",
        "shot_id", "scene_id", "project_id", "storyboard_frame_url",
        "storyboard",
    ):
        assert key not in result


def test_05_collision_does_not_enter_creative_parameters():
    assert "storyboard_frame_identity_collision" in EXECUTION_ONLY_PARAMETER_KEYS
    collision = {"uri": "https://cdn.example.test/board.png", "source": "storyboard_frame_url"}
    result = creative_parameter_values(
        {"storyboard_frame_identity_collision": collision, "style_hint": "noir"}
    )
    assert "storyboard_frame_identity_collision" not in result
    assert result == {"style_hint": "noir"}
    # Nested occurrences are also stripped by the shared classifier.
    nested = creative_parameter_values({"outer": {"storyboard_frame_identity_collision": collision}})
    assert nested == {"outer": {}}


def _resolved_coverage(binding: list[dict[str, Any]]):
    from app.services.scene_coverage_contract import build_scene_coverage_contract
    from app.services.camera_provenance import camera_plan_digest

    scene = {
        "scene_id": SCENE_ID,
        "heading": "INT. TEST ROOM - DAY",
        "text": "A single lamp glows beside a closed book.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": PROJECT_ID,
        "script_text": "INT. TEST ROOM - DAY\nA single lamp glows beside a closed book.",
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
        camera_plan, "USER_SPECIFIED", source_project_id=PROJECT_ID,
        source_scene_id=SCENE_ID, source_shot_id=SHOT_ID,
    )
    shots = [{"shot_id": SHOT_ID, "scene_id": SCENE_ID, "parameters": dict(shot_params)}]
    requirements = {
        "setting_id": SETTING_ID,
        "characters": {"char-a": {"name": "A", "urls": [binding[0]["uri"]], "references": [dict(binding[0])]}},
        "reference_binding": binding,
    }
    probe, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID, project=project, scene=scene, shots=shots,
        reference_requirements={"setting_id": SETTING_ID, "characters": requirements["characters"], "reference_binding": binding},
    )
    decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"], "status": "ASSIGNED", "shot_id": SHOT_ID, "reason": ""}
        for row in probe["content_units"]
    ]
    decisions.extend([
        {"obligation_type": "shot_content", "obligation_id": SHOT_ID, "status": "UNRESOLVED", "shot_id": None, "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": SHOT_ID, "status": "INTENTIONAL_SILENCE",
         "reason": "The approved shot contains no spoken dialogue."},
    ])
    coverage, blockers, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID, project=project, scene=scene, shots=shots,
        reference_requirements={"setting_id": SETTING_ID, "characters": requirements["characters"], "reference_binding": binding},
        creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_coverage = next(r for r in coverage["shots"] if r["shot_id"] == SHOT_ID)
    handoff = freeze_dialogue_handoff(scene_id=SCENE_ID, shot_id=SHOT_ID, lines=[])
    return coverage, shot_coverage, handoff


def test_06_collision_preserved_in_coverage_not_in_creative():
    """Collision provenance survives in scene coverage while staying out of creative input."""
    binding = _binding_rows()
    collision_url = binding[0]["uri"]
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    approved_parameters: dict[str, Any] = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "duration": 5,
        "aspect_ratio": "16:9",
        "reference_roles": ["face"],
        "storyboard_frame_url": collision_url,
        "storyboard_frame_identity_collision": {"uri": collision_url, "source": "storyboard_frame_url"},
    }
    frozen = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved prompt bytes.",
        reference_assets=_freeze_input_rows(binding),
        parameters=approved_parameters,
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    payload = frozen.payload()
    # Creative generation input carries neither orchestration nor provenance metadata.
    assert "project_id" not in payload["creative_parameters"]
    assert "storyboard_frame_identity_collision" not in payload["creative_parameters"]
    # The provenance record is preserved in its coverage home, not discarded.
    collision = payload["scene_coverage_shot"].get("storyboard_frame_identity_collision") or {}
    assert collision.get("uri") == collision_url
    assert collision.get("identity_refs")
    # Frozen integrity round-trips without bypass.
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert restored.payload()["scene_coverage_shot"]["storyboard_frame_identity_collision"]["uri"] == collision_url


def test_07_manifest_and_contract_creative_derivation_converge():
    """The pipeline injects project_id into approved params but the manifest
    derives from pre-injection params; after the fix both classify identically."""
    from app.services.shot_manifest import build_shot_manifest

    entry_parameters: dict[str, Any] = {}
    # Pre-injection shot parameters (what the manifest sees).
    manifest_params = creative_parameter_values(dict(entry_parameters))
    # Post-injection approved parameters (what the frozen contract sees).
    approved_parameters = {**entry_parameters, "project_id": PROJECT_ID, "scene_id": SCENE_ID,
                           "duration": 5, "aspect_ratio": "16:9", "reference_roles": []}
    binding = _binding_rows()
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    frozen = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved prompt bytes.",
        reference_assets=_freeze_input_rows(binding),
        parameters=approved_parameters,
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    contract_params = frozen.payload()["creative_parameters"]
    assert manifest_params == contract_params == {}
    # A manifest built from the same entry parameters agrees as well.
    manifest = build_shot_manifest(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        scene=None,
        scene_version="v1",
        storyboard_version="sb-v1",
        entries=[{
            "shot_id": SHOT_ID, "storyboard_shot_id": "", "shot_version": "v1",
            "shot_order": 1, "duration_seconds": 5, "prompt": "Approved prompt bytes.",
            "negative_prompt": "", "audio_intent": False, "reference_roles": [],
            "generation_contract_digest": frozen.creative_digest(),
            "aspect_ratio": "16:9", "resolution": None, "seed": None,
            "camera_plan": {}, "camera_provenance": "UNSPECIFIED",
            "camera_instructions": [], "camera_source_digest": "",
            "camera_source_project_id": "", "camera_source_scene_id": "",
            "camera_source_shot_id": "", "camera_source_storyboard_shot_id": "",
            "camera_target_project_id": "", "camera_target_scene_id": "",
            "camera_target_shot_id": "", "references": [],
            "reference_binding": [], "reference_version": "none",
            "parameters": dict(entry_parameters),
        }],
    )
    assert manifest["shots"][0]["parameters"] == contract_params


def test_08_router_fail_closed_for_nonempty_creative_parameters_intact():
    """The Router rejection of non-empty creative_parameters is not weakened."""
    adapter_path = Path(__file__).resolve().parents[1] / "app" / "adapters" / "__init__.py"
    source = adapter_path.read_text(encoding="utf-8")
    assert "unsupported_creative_parameters" in source
    assert "if creative_parameters:" in source
    # Functional shape of the gate: empty passes, non-empty fails.
    assert not creative_parameter_values({"project_id": PROJECT_ID})
    assert creative_parameter_values({"style_hint": "noir"}) != {}
    # The provider-side reconstruction guard is also intact.
    provider_path = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "providers" / "runway_router_provider.py"
    )
    provider_source = provider_path.read_text(encoding="utf-8")
    assert "cannot represent frozen creative parameters without loss" in provider_source


def test_09_frozen_integrity_never_bypassed():
    binding = _binding_rows()
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    frozen = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved prompt bytes.",
        reference_assets=_freeze_input_rows(binding),
        parameters={"project_id": PROJECT_ID, "duration": 5, "aspect_ratio": "16:9", "reference_roles": ["face"]},
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    record = frozen.to_record()
    restored = FrozenGenerationContract.from_record(deepcopy(record))
    assert restored.creative_digest() == frozen.creative_digest()
    tampered = deepcopy(record)
    tampered["payload"]["prompt"] = "Tampered prompt bytes."
    try:
        FrozenGenerationContract.from_record(tampered)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered frozen contract must fail closed")


def test_10_no_scene002_specific_logic_introduced():
    contract_path = Path(__file__).resolve().parents[1] / "app" / "services" / "generation_contract.py"
    source = contract_path.read_text(encoding="utf-8")
    assert "scene_002" not in source
    assert "scene002" not in source
    pipeline_path = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "scene_production_pipeline_service.py"
    )
    pipeline_source = pipeline_path.read_text(encoding="utf-8")
    # The collision record no longer rides the canonical creative-parameters path.
    assert 'parameters["storyboard_frame_identity_collision"]' not in pipeline_source
    # All Phase A tests use a generic scene, never the protected Scene 002 identity.
    assert SCENE_ID != "scene_002"
    assert SHOT_ID != "scene_002_shot_001"
