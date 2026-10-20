"""Scene 002 composition-vs-identity boundary regression.

Covers the surgical repair in
``SceneProductionPipelineService.prepare_scene_batch``: composition
conditioning URLs (``parameters["storyboard_frame_url"]`` and symmetrically
``parameters["last_frame_reference_url"]``) must be excluded from the
``supplied_urls`` passed to the canonical identity validator
``reference_binding_for_requirements()``.

The validator itself stays strict: a storyboard frame claimed directly as an
identity reference must still be rejected. The pipeline boundary filters
composition URLs before validation so a legitimate board frame cannot empty
the canonical binding for ``scene_002_shot_001``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.generation_contract import (
    FrozenGenerationContract,
    GenerationContractError,
    freeze_generation_contract,
)
from app.services.reference_validation import reference_binding_for_requirements
from app.services.scene_production_pipeline_service import (
    _canonical_binding_to_contract_references,
    _canonical_frozen_references,
)

PROJECT_ID = "project_5907c60cddbc"
SCENE_ID = "scene_002"
SHOT_ID = "scene_002_shot_001"
CHARACTER_ID = "chr_3c9e91741ef3"
SETTING_ID = "loc-c8f88b9c"
STORYBOARD_FRAME_URL = "https://cdn.example.test/scene002-shot001-board-frame.png"
LAST_FRAME_URL = "https://cdn.example.test/scene002-shot001-last-frame.png"
EVIL_URL = "https://cdn.example.test/not-a-canonical-reference.png"

EXPECTED_CANONICAL_REF_IDS = [
    "ref_look_005f852638f5d162",
    "ref_look_e46ec07463f33414",
    "charlock:chr_3c9e91741ef3:general",
    "charlock:chr_3c9e91741ef3:alternate_angle",
    "ref_set_0ac27f51f04d4bc982fc75c8ad87371e",
]


def _scene002_binding() -> list[dict[str, Any]]:
    return [
        {
            "ref_id": "ref_look_005f852638f5d162",
            "uri": "https://cdn.example.test/scene002-look-1.png",
            "target_type": "character",
            "target_id": CHARACTER_ID,
            "role": "general",
            "category": "general",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "ref_look_e46ec07463f33414",
            "uri": "https://cdn.example.test/scene002-look-2.png",
            "target_type": "character",
            "target_id": CHARACTER_ID,
            "role": "general",
            "category": "general",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "charlock:chr_3c9e91741ef3:general",
            "uri": "https://cdn.example.test/scene002-charlock-general.png",
            "target_type": "character",
            "target_id": CHARACTER_ID,
            "role": "general",
            "category": "general",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "charlock:chr_3c9e91741ef3:alternate_angle",
            "uri": "https://cdn.example.test/scene002-charlock-alt.png",
            "target_type": "character",
            "target_id": CHARACTER_ID,
            "role": "alternate_angle",
            "category": "alternate_angle",
            "canonical": True,
            "approval_state": "approved",
            "source_kind": "confirmed",
            "kind": "character_face",
        },
        {
            "ref_id": "ref_set_0ac27f51f04d4bc982fc75c8ad87371e",
            "project_id": PROJECT_ID,
            "uri": "https://cdn.example.test/scene002-set-env.png",
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


def _requirements(binding: list[dict[str, Any]]) -> dict[str, Any]:
    char_rows = [dict(row) for row in binding if row.get("target_type") == "character"]
    setting_rows = [dict(row) for row in binding if row.get("target_type") == "setting"]
    return {
        "scene_id": SCENE_ID,
        "character_ids": [CHARACTER_ID],
        "characters": {
            CHARACTER_ID: {
                "name": "Scene002 Character",
                "urls": [row["uri"] for row in char_rows],
                "references": char_rows,
            }
        },
        "setting_id": SETTING_ID,
        "setting_urls": [row["uri"] for row in setting_rows],
        "setting_references": setting_rows,
        "allowed_urls": [row["uri"] for row in binding],
    }


def test_validator_still_rejects_storyboard_frame_as_identity_claim():
    """The canonical validator stays strict when a frame is claimed directly."""
    binding = _scene002_binding()
    with pytest.raises(ValueError, match="not one of the prepared canonical"):
        reference_binding_for_requirements(
            _requirements(binding),
            supplied_urls=[row["uri"] for row in binding] + [STORYBOARD_FRAME_URL],
        )


def test_validator_still_rejects_last_frame_as_identity_claim():
    binding = _scene002_binding()
    with pytest.raises(ValueError, match="not one of the prepared canonical"):
        reference_binding_for_requirements(
            _requirements(binding),
            supplied_urls=[row["uri"] for row in binding] + [LAST_FRAME_URL],
        )


def test_validator_still_rejects_genuine_noncanonical_identity_claim():
    """Genuine explicit identity references still go through the validator."""
    binding = _scene002_binding()
    with pytest.raises(ValueError, match="not one of the prepared canonical"):
        reference_binding_for_requirements(
            _requirements(binding),
            supplied_urls=[row["uri"] for row in binding] + [EVIL_URL],
        )


def _run_prepare(*, reference_assets: list[str], parameters_extra: dict[str, Any], monkeypatch) -> dict[str, Any]:
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    binding = _scene002_binding()
    scene = {
        "scene_id": SCENE_ID,
        "heading": "INT. SCENE 002 ROOM - DAY",
        "text": "A lamp glows beside a closed book.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": PROJECT_ID,
        "script_text": "INT. SCENE 002 ROOM - DAY\nA lamp glows beside a closed book.",
        "execution_summary": {"scenes": [scene]},
    }
    board_parameters: dict[str, Any] = {
        "duration": 5,
        "ratio": "16:9",
        "storyboard": {
            "version_id": "approved-scene002-version",
            "storyboard_shot_id": "board-scene002-shot-1",
        },
    }
    board_parameters.update(parameters_extra)
    board_shot = SimpleNamespace(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        shot_id=SHOT_ID,
        shot_number=1,
        storyboard_shot_id="board-scene002-shot-1",
        version_id="approved-scene002-version",
        status="approved",
        updated_at="2026-10-01T00:00:01+00:00",
        prompt="originating-scene002-prompt-1",
        duration_seconds=5,
        parameters=board_parameters,
        reference_assets=list(reference_assets),
        source_refs=list(reference_assets),
        camera_plan={"camera": "Hold", "framing": "Wide"},
        render_contract=SimpleNamespace(
            provider_neutral_prompt="originating-scene002-prompt-1",
            structured_parameters={"camera_plan": {"camera": "Hold", "framing": "Wide"}},
            duration_seconds=5,
            aspect_ratio="16:9",
            reference_assets=list(reference_assets),
        ),
        metadata={},
    )
    monkeypatch.setattr(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.scene_render_inputs",
        lambda _project_id, _scene_id: [board_shot],
    )

    def _resolve_requirements(**kwargs):
        return _requirements(binding)

    monkeypatch.setattr(
        "app.services.reference_validation.resolve_scene_reference_requirements",
        _resolve_requirements,
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.validate_generation_context",
        lambda **kwargs: SimpleNamespace(blockers=[]),
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.create_generation_context",
        lambda **kwargs: SimpleNamespace(
            generation_context_id=f"ctx-{kwargs['shot_id']}",
            scene_version="scene-version",
            shot_version=f"version-{kwargs['shot_id']}",
            reference_version="test",
            to_dict=lambda: {"shot_id": kwargs["shot_id"]},
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.reference_version",
        lambda **kwargs: "test",
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.enforce_shot_limit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.estimate_batch",
        lambda *, provider, shots: {"provider": provider, "per_shot": [], "estimated": False},
    )
    from app.services.storyboard_blueprint_service import storyboard_blueprint_service

    monkeypatch.setattr(
        storyboard_blueprint_service.storage,
        "get_storyboard_shot",
        lambda storyboard_shot_id: board_shot,
    )
    # The storyboard-sourced shot record already carries reference_assets
    # (simulating storyboard_render_inputs prepending the board frame for
    # composition while parameters carry the composition URL), so no
    # snapshot override is needed.

    from app.services.scene_coverage_contract import build_scene_coverage_contract

    probe_coverage, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID,
        project=project,
        scene=scene,
        shots=[{"shot_id": SHOT_ID, "scene_id": SCENE_ID, "parameters": {}}],
        reference_requirements={
            "setting_id": SETTING_ID,
            "characters": _requirements(binding)["characters"],
            "reference_binding": binding,
        },
    )
    creator_decisions = [
        {
            "obligation_type": "content",
            "obligation_id": row["content_id"],
            "status": "ASSIGNED",
            "shot_id": SHOT_ID,
            "reason": "",
        }
        for row in probe_coverage["content_units"]
    ]
    creator_decisions.extend(
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
    board_shot.parameters["creator_coverage_decisions"] = creator_decisions

    import tempfile

    # Image-prompt authority: composition boundary covers reference binding,
    # so satisfy the fail-closed send-prompt gate with fixed approved text.
    monkeypatch.setattr(
        SceneProductionPipelineService,
        "_resolve_storyboard_send_prompt",
        lambda self, **kwargs: ("Approved Scene 002 image prompt bytes.", "abc123", ""),
    )
    service = SceneProductionPipelineService(backend_root=tempfile.gettempdir())  # type: ignore[arg-type]
    batch = service.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=project,
        provider="simulated",
    )
    entries = [row for row in batch["entries"] if row.get("shot_id") == SHOT_ID]
    assert len(entries) == 1
    return entries[0]


def test_prepare_retains_five_canonical_refs_with_storyboard_frame(monkeypatch):
    binding = _scene002_binding()
    canonical_uris = [row["uri"] for row in binding]
    entry = _run_prepare(
        reference_assets=[STORYBOARD_FRAME_URL, *canonical_uris],
        parameters_extra={"storyboard_frame_url": STORYBOARD_FRAME_URL},
        monkeypatch=monkeypatch,
    )
    assert [row["ref_id"] for row in entry["reference_binding"]] == EXPECTED_CANONICAL_REF_IDS
    assert STORYBOARD_FRAME_URL not in {row["uri"] for row in entry["reference_binding"]}
    # Composition conditioning stays intact in render parameters.
    assert entry["parameters"]["storyboard_frame_url"] == STORYBOARD_FRAME_URL
    frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
    canonical = _canonical_frozen_references(frozen)
    assert [row["ref_id"] for row in canonical] == EXPECTED_CANONICAL_REF_IDS
    composition = [ref for ref in frozen.references if ref.source == "storyboard_frame_url"]
    assert len(composition) == 1 and composition[0].uri == STORYBOARD_FRAME_URL
    assert composition[0].ref_id == ""


def test_prepare_retains_five_canonical_refs_with_last_frame(monkeypatch):
    binding = _scene002_binding()
    canonical_uris = [row["uri"] for row in binding]
    entry = _run_prepare(
        reference_assets=[LAST_FRAME_URL, *canonical_uris],
        parameters_extra={"last_frame_reference_url": LAST_FRAME_URL},
        monkeypatch=monkeypatch,
    )
    assert [row["ref_id"] for row in entry["reference_binding"]] == EXPECTED_CANONICAL_REF_IDS
    frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
    assert [row["ref_id"] for row in _canonical_frozen_references(frozen)] == EXPECTED_CANONICAL_REF_IDS
    composition = [ref for ref in frozen.references if ref.source == "last_frame_reference_url"]
    assert len(composition) == 1 and composition[0].uri == LAST_FRAME_URL


def _freeze_rows(binding: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    from app.services.scene_coverage_contract import build_scene_coverage_contract
    from app.services.generation_contract import freeze_dialogue_handoff
    from app.services.camera_provenance import camera_plan_digest

    scene = {
        "scene_id": SCENE_ID,
        "heading": "INT. SCENE 002 ROOM - DAY",
        "text": "A lamp glows beside a closed book.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": PROJECT_ID,
        "script_text": "INT. SCENE 002 ROOM - DAY\nA lamp glows beside a closed book.",
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
    probe, _, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID,
        project=project,
        scene=scene,
        shots=shots,
        reference_requirements={
            "setting_id": SETTING_ID,
            "characters": _requirements(binding)["characters"],
            "reference_binding": binding,
        },
    )
    decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"],
         "status": "ASSIGNED", "shot_id": SHOT_ID, "reason": ""}
        for row in probe["content_units"]
    ]
    decisions.extend([
        {"obligation_type": "shot_content", "obligation_id": SHOT_ID,
         "status": "UNRESOLVED", "shot_id": None, "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": SHOT_ID,
         "status": "INTENTIONAL_SILENCE",
         "reason": "The approved shot contains no spoken dialogue."},
    ])
    coverage, blockers, _ = build_scene_coverage_contract(
        project_id=PROJECT_ID,
        project=project,
        scene=scene,
        shots=shots,
        reference_requirements={
            "setting_id": SETTING_ID,
            "characters": _requirements(binding)["characters"],
            "reference_binding": binding,
        },
        creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_coverage = next(r for r in coverage["shots"] if r["shot_id"] == SHOT_ID)
    handoff = freeze_dialogue_handoff(scene_id=SCENE_ID, shot_id=SHOT_ID, lines=[])
    return coverage, shot_coverage, handoff


def test_frozen_contract_distinguishes_canonical_from_composition():
    binding = _scene002_binding()
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    frozen = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved Scene 002 prompt bytes.",
        reference_assets=_freeze_rows(binding),
        parameters={
            "duration": 5,
            "aspect_ratio": "16:9",
            "reference_roles": [row.get("role") or "reference" for row in binding],
            "storyboard_frame_url": STORYBOARD_FRAME_URL,
        },
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert [row["ref_id"] for row in _canonical_frozen_references(restored)] == EXPECTED_CANONICAL_REF_IDS
    assert STORYBOARD_FRAME_URL not in {
        row["uri"] for row in _canonical_binding_to_contract_references(binding)
    }
    storyboard = [ref for ref in restored.references if ref.source == "storyboard_frame_url"]
    assert len(storyboard) == 1 and storyboard[0].uri == STORYBOARD_FRAME_URL


def test_411_invariant_still_rejects_genuinely_incomplete_binding():
    """The frozen coverage invariant must still fail a truly missing anchor."""
    binding = _scene002_binding()
    coverage, shot_coverage, handoff = _resolved_coverage(binding)
    incomplete = [row for row in binding if row["ref_id"] != EXPECTED_CANONICAL_REF_IDS[-1]]
    frozen = freeze_generation_contract(
        shot_id=SHOT_ID,
        prompt="Approved Scene 002 prompt bytes.",
        reference_assets=_freeze_rows(incomplete),
        parameters={
            "duration": 5,
            "aspect_ratio": "16:9",
            "reference_roles": [row.get("role") or "reference" for row in incomplete],
            "storyboard_frame_url": STORYBOARD_FRAME_URL,
        },
        dialogue_handoff=handoff,
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    with pytest.raises(GenerationContractError, match="omits an approved reference"):
        FrozenGenerationContract.from_record(frozen.to_record())
