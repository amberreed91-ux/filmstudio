"""Provenance-aware repair regression: canonical vs composition references.

Canonical identity: source == "canonical_reference_binding" must satisfy
scene approved canonical identity coverage.
Composition: source in {"storyboard_frame_url","last_frame_reference_url",
"consistency_payload"} may have ref_id="" and must not be required to
satisfy canonical coverage. Router payload keeps ALL refs.
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
    freeze_generation_contract,
    freeze_dialogue_handoff,
)

PROJECT_ID = "project-provenance-repair"
CHARACTER_ID = "char-dre"
SETTING_ID = "set-office"
STORYBOARD_URL = "https://cdn.example.test/board-frame-composition.png"
LAST_FRAME_URL = "https://cdn.example.test/last-frame-composition.png"
CONSISTENCY_URL = "https://cdn.example.test/consistency-composition.png"


def _character_binding_row() -> dict[str, Any]:
    return {
        "ref_id": "ref-dre-face",
        "uri": "https://cdn.example.test/dre-face.png",
        "target_type": "character",
        "target_id": CHARACTER_ID,
        "role": "face",
        "category": "face",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "character_face",
    }


def _setting_binding_row() -> dict[str, Any]:
    return {
        "ref_id": "ref-office-env",
        "project_id": PROJECT_ID,
        "uri": "https://cdn.example.test/office-env.png",
        "target_type": "setting",
        "target_id": SETTING_ID,
        "role": "environment",
        "category": "environment",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
        "kind": "environment",
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


def _resolved_coverage(binding: list[dict[str, Any]], shot_id: str = "scene_001_shot_001"):
    from app.services.scene_coverage_contract import build_scene_coverage_contract
    from app.services.camera_provenance import camera_plan_digest

    scene_id = "scene_001"
    scene = {
        "scene_id": scene_id,
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
        "camera_source_scene_id": scene_id,
        "camera_source_shot_id": shot_id,
        "camera_target_project_id": PROJECT_ID,
        "camera_target_scene_id": scene_id,
        "camera_target_shot_id": shot_id,
    }
    shot_params["camera_source_digest"] = camera_plan_digest(
        camera_plan, "USER_SPECIFIED", source_project_id=PROJECT_ID,
        source_scene_id=scene_id, source_shot_id=shot_id,
    )
    shots = [{"shot_id": shot_id, "scene_id": scene_id, "parameters": dict(shot_params)}]
    char_rows = [r for r in binding if r.get("target_type") == "character"]
    setting_rows = [r for r in binding if r.get("target_type") == "setting"]
    requirements = {
        "setting_id": SETTING_ID if setting_rows else "",
        "characters": (
            {CHARACTER_ID: {"name": "Dre", "urls": [char_rows[0]["uri"]], "references": [dict(char_rows[0])]}}
            if char_rows else {}
        ),
        "reference_binding": binding,
    }
    probe, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID, project=project, scene=scene,
        shots=shots,
        reference_requirements={
            "setting_id": requirements["setting_id"],
            "characters": requirements["characters"],
            "reference_binding": binding,
        },
    )
    decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"],
         "status": "ASSIGNED", "shot_id": shot_id, "reason": ""}
        for row in probe["content_units"]
    ]
    decisions.extend([
        {"obligation_type": "shot_content", "obligation_id": shot_id,
         "status": "UNRESOLVED", "shot_id": None, "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shot_id,
         "status": "INTENTIONAL_SILENCE",
         "reason": "The approved shot contains no spoken dialogue."},
    ])
    coverage, blockers, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID, project=project, scene=scene,
        shots=shots,
        reference_requirements={
            "setting_id": requirements["setting_id"],
            "characters": requirements["characters"],
            "reference_binding": binding,
        },
        creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_coverage = next(r for r in coverage["shots"] if r["shot_id"] == shot_id)
    handoff = freeze_dialogue_handoff(scene_id=scene_id, shot_id=shot_id, lines=[])
    return coverage, shot_coverage, handoff


def _freeze(binding, shot_id="scene_001_shot_001", extra_params: dict | None = None):
    coverage, shot_coverage, handoff = _resolved_coverage(binding, shot_id)
    params: dict[str, Any] = {
        "duration": 5,
        "aspect_ratio": "16:9",
        "reference_roles": [row.get("role") or "reference" for row in binding],
    }
    if extra_params:
        params.update(extra_params)
    frozen = freeze_generation_contract(
        shot_id=shot_id,
        prompt="Approved prompt bytes.",
        reference_assets=_freeze_input_rows(binding),
        parameters=params,
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
        consistency_payload=extra_params.get("consistency_payload") if extra_params else None,
    )
    return frozen


def _retampered_record(record: dict, mutator) -> dict:
    rec = deepcopy(record)
    mutator(rec["payload"])
    canonical = json.dumps(rec["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    rec["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return rec


def test_01_canonical_character_reference_passes():
    frozen = _freeze([_character_binding_row(), _setting_binding_row()])
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert len([r for r in restored.references if r.source == "canonical_reference_binding"]) == 2


def test_02_canonical_setting_with_project_id_passes():
    binding = [_character_binding_row(), _setting_binding_row()]
    assert binding[1]["project_id"] == PROJECT_ID
    frozen = _freeze(binding)
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert restored is not None


def test_03_canonical_plus_storyboard_composition_passes():
    frozen = _freeze(
        [_character_binding_row(), _setting_binding_row()],
        extra_params={"storyboard_frame_url": STORYBOARD_URL},
    )
    assert len(frozen.references) == 3
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert len(restored.references) == 3
    assert restored.references[2].source == "storyboard_frame_url"
    assert restored.references[2].ref_id == ""


def test_04_canonical_plus_last_frame_passes():
    frozen = _freeze(
        [_character_binding_row(), _setting_binding_row()],
        extra_params={"last_frame_reference_url": LAST_FRAME_URL},
    )
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert any(r.source == "last_frame_reference_url" and r.ref_id == "" for r in restored.references)


def test_05_canonical_plus_consistency_passes():
    frozen = _freeze(
        [_character_binding_row(), _setting_binding_row()],
        extra_params={
            "consistency_payload": {"refs": [{"image_url": CONSISTENCY_URL, "studio_role": "reference"}]},
        },
    )
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert any(r.source == "consistency_payload" for r in restored.references)


def test_06_missing_canonical_identity_still_fails():
    binding = [_character_binding_row(), _setting_binding_row()]
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    # Freeze with only the character anchor; setting anchor missing.
    params = {"duration": 5, "aspect_ratio": "16:9", "reference_roles": ["face"]}
    frozen = freeze_generation_contract(
        shot_id="scene_001_shot_001",
        prompt="Approved prompt bytes.",
        reference_assets=_freeze_input_rows([_character_binding_row()]),
        parameters=params,
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    with pytest.raises(GenerationContractError, match="omits an approved reference"):
        FrozenGenerationContract.from_record(frozen.to_record())


def test_07_genuine_canonical_ref_id_mismatch_fails():
    frozen = _freeze([_character_binding_row(), _setting_binding_row()])
    tampered = _retampered_record(frozen.to_record(), lambda p: p["references"].__setitem__(0, {**p["references"][0], "ref_id": "ref-tampered"}))
    with pytest.raises(GenerationContractError, match="approved coverage IDs"):
        FrozenGenerationContract.from_record(tampered)


def test_08_genuine_canonical_uri_mismatch_fails():
    frozen = _freeze([_character_binding_row(), _setting_binding_row()])
    tampered = _retampered_record(
        frozen.to_record(),
        lambda p: p["references"].__setitem__(0, {**p["references"][0], "uri": "https://cdn.example.test/tampered.png"}),
    )
    with pytest.raises(GenerationContractError, match="approved coverage IDs"):
        FrozenGenerationContract.from_record(tampered)


def test_09_genuine_canonical_target_mismatch_fails():
    frozen = _freeze([_character_binding_row(), _setting_binding_row()])
    tampered = _retampered_record(
        frozen.to_record(),
        lambda p: p["references"].__setitem__(0, {**p["references"][0], "target_id": "char-other"}),
    )
    with pytest.raises(GenerationContractError, match="approved coverage IDs"):
        FrozenGenerationContract.from_record(tampered)


def test_10_genuine_canonical_category_or_role_mismatch_fails():
    frozen = _freeze([_character_binding_row(), _setting_binding_row()])
    tampered = _retampered_record(
        frozen.to_record(),
        lambda p: p["references"].__setitem__(0, {**p["references"][0], "category": "full_body", "studio_role": "full_body"}),
    )
    with pytest.raises(GenerationContractError, match="approved coverage IDs"):
        FrozenGenerationContract.from_record(tampered)


def test_11_storyboard_empty_ref_id_does_not_satisfy_coverage():
    binding = [_character_binding_row(), _setting_binding_row()]
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    storyboard_only_asset = [
        {
            "uri": STORYBOARD_URL,
            "studio_role": "storyboard",
            "source": "storyboard_frame_url",
            "ref_id": "",
            "target_type": "",
            "target_id": "",
            "category": "storyboard",
            "canonical": False,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "",
        }
    ]
    frozen = freeze_generation_contract(
        shot_id="scene_001_shot_001",
        prompt="Approved prompt bytes.",
        reference_assets=storyboard_only_asset,
        parameters={"duration": 5, "aspect_ratio": "16:9", "storyboard_frame_url": STORYBOARD_URL},
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    with pytest.raises(GenerationContractError, match="omits an approved reference"):
        FrozenGenerationContract.from_record(frozen.to_record())


def test_12_storyboard_preserved_and_available_to_router():
    frozen = _freeze(
        [_character_binding_row(), _setting_binding_row()],
        extra_params={"storyboard_frame_url": STORYBOARD_URL},
    )
    payload = frozen.payload()
    storyboard = [r for r in payload["references"] if r["source"] == "storyboard_frame_url"]
    assert len(storyboard) == 1 and storyboard[0]["uri"] == STORYBOARD_URL
    # Router payload uses all frozen refs (canonical + composition).
    router_uris = [r["uri"] for r in payload["references"]]
    assert STORYBOARD_URL in router_uris
    assert "https://cdn.example.test/dre-face.png" in router_uris
    # Router role allowlist already supports storyboard / storyboard_last.
    assert {r["studio_role"] for r in payload["references"]} >= {"face", "storyboard"}


def test_13_identity_collision_behavior_unchanged():
    binding = [_character_binding_row(), _setting_binding_row()]
    # Collision: storyboard URL equals the canonical setting URI.
    collision_url = binding[1]["uri"]
    frozen = _freeze(binding, extra_params={"storyboard_frame_url": collision_url})
    payload = frozen.payload()
    assert payload["scene_coverage_shot"].get("storyboard_frame_identity_collision", {}).get("uri") == collision_url
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert restored is not None
    # Both provenances coexist with the same URI.
    uris = [(r.uri, r.source) for r in restored.references]
    assert (collision_url, "canonical_reference_binding") in uris


def test_14_pipeline_canonical_projection_allows_composition_coexistence():
    """Mirrors the repaired generate-scene verification: canonical-only equality."""
    from app.services.scene_production_pipeline_service import (
        _canonical_binding_to_contract_references,
        _canonical_frozen_references,
    )

    binding = [_character_binding_row(), _setting_binding_row()]
    frozen = _freeze(binding, extra_params={"storyboard_frame_url": STORYBOARD_URL})
    expected = _canonical_binding_to_contract_references(binding)
    canonical_frozen = _canonical_frozen_references(frozen)
    assert canonical_frozen == expected
    # The stale all-refs equality would have failed here.
    assert frozen.payload()["references"] != expected
    # from_record (new coverage invariant) passes with composition present.
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert _canonical_frozen_references(restored) == expected
