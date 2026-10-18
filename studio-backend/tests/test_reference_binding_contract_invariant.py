"""Regression coverage for the deterministic reference binding contract.

Covers the repair at ``scene_production_pipeline_service.py`` (prepare path):
the raw canonical binding (character rows: 10 keys; setting rows: 11 keys with
``project_id``) must be compared via an explicit same-shape projection onto the
frozen contract representation -- never by strict dict equality -- and
storyboard composition references appended by ``freeze_generation_contract()``
must not fail the canonical invariant.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.services.generation_contract import freeze_generation_contract
from app.services.scene_production_pipeline_service import (
    _canonical_binding_to_contract_references,
    _canonical_frozen_references,
)

PROJECT_ID = "project_binding_contract"
CHARACTER_ID = "char-dre"
SETTING_ID = "set-office"
STORYBOARD_URL = "https://cdn.example.test/storyboard-frame-not-canonical.png"


def _character_binding_row() -> dict[str, Any]:
    # 10 keys: no project_id on character rows.
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
    # 11 keys: setting rows carry project_id and must keep it.
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
    """Mirror the service's reference_rows projection (freeze input shape)."""
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


def _freeze(binding: list[dict[str, Any]], *, storyboard_url: str | None = STORYBOARD_URL):
    params: dict[str, Any] = {
        "duration": 5,
        "aspect_ratio": "16:9",
        "reference_roles": [row.get("role") or "reference" for row in binding],
    }
    if storyboard_url is not None:
        params["storyboard_frame_url"] = storyboard_url
    return freeze_generation_contract(
        shot_id="scene_001_shot_001",
        prompt="Approved prompt bytes.",
        reference_assets=_freeze_input_rows(binding),
        parameters=params,
    )


def test_canonical_projection_preserves_setting_project_id_and_order():
    binding = [_character_binding_row(), _setting_binding_row()]
    projected = _canonical_binding_to_contract_references(binding)
    assert [row["ref_id"] for row in projected] == ["ref-dre-face", "ref-office-env"]
    assert projected[0]["studio_role"] == "face"
    assert projected[1]["studio_role"] == "environment"
    assert all(row["source"] == "canonical_reference_binding" for row in projected)
    assert all(row["role"] == "reference" for row in projected)
    # The raw binding itself is untouched: setting keeps project_id.
    assert binding[1]["project_id"] == PROJECT_ID
    assert "project_id" not in binding[0]


def test_frozen_contract_contains_canonical_and_storyboard_composition():
    binding = [_character_binding_row(), _setting_binding_row()]
    frozen = _freeze(binding, storyboard_url=STORYBOARD_URL)
    assert len(frozen.references) == 3
    canonical = _canonical_frozen_references(frozen)
    assert len(canonical) == 2
    # Ordering preserved: canonical anchors first in binding order, storyboard last.
    assert [row["uri"] for row in canonical] == [binding[0]["uri"], binding[1]["uri"]]
    storyboard = [ref for ref in frozen.references if ref.source == "storyboard_frame_url"]
    assert len(storyboard) == 1
    assert storyboard[0].uri == STORYBOARD_URL
    assert storyboard[0].studio_role == "storyboard"
    # The storyboard frame URL is not itself an approved canonical reference.
    assert STORYBOARD_URL not in {row["uri"] for row in binding}


def test_invariant_passes_when_canonical_references_are_equivalent():
    binding = [_character_binding_row(), _setting_binding_row()]
    frozen = _freeze(binding, storyboard_url=STORYBOARD_URL)
    expected = _canonical_binding_to_contract_references(binding)
    assert _canonical_frozen_references(frozen) == expected


@pytest.mark.parametrize(
    "field",
    ["ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind"],
)
def test_invariant_fails_closed_on_genuine_canonical_difference(field: str):
    binding = [_character_binding_row(), _setting_binding_row()]
    frozen = _freeze(binding, storyboard_url=STORYBOARD_URL)
    mutated = deepcopy(binding)
    if field == "ref_id":
        mutated[0]["ref_id"] = "ref-tampered"
    elif field == "uri":
        mutated[0]["uri"] = "https://cdn.example.test/tampered.png"
    elif field == "target_type":
        mutated[0]["target_type"] = "setting"
    elif field == "target_id":
        mutated[0]["target_id"] = "char-other"
    elif field == "role":
        mutated[0]["role"] = "full_body"
    elif field == "category":
        mutated[0]["category"] = "full_body"
    elif field == "canonical":
        mutated[0]["canonical"] = False
    elif field == "approval_state":
        mutated[0]["approval_state"] = "candidate"
    elif field == "source_kind":
        mutated[0]["source_kind"] = "unconfirmed"
    elif field == "kind":
        mutated[0]["kind"] = "character_full"
    else:  # pragma: no cover
        raise AssertionError(field)
    assert _canonical_frozen_references(frozen) != _canonical_binding_to_contract_references(mutated)


def test_production_prepare_path_passes_invariant_with_storyboard_composition(tmp_path, monkeypatch):
    """Exercise the real ``prepare_scene_batch`` comparison (not _noop_prepare).

    A character anchor (10 keys) plus a setting anchor carrying ``project_id``
    (11 keys) plus a non-canonical storyboard frame URL must pass the
    deterministic reference binding invariant at prepare time: the raw binding
    is projected (never stripped of ``project_id``) and only canonical frozen
    references are compared, so the storyboard composition reference cannot
    fail that invariant.

    Provenance-aware contract: a distinct (non-collision) storyboard
    composition reference is a separate provenance (``source ==
    "storyboard_frame_url"``, ``ref_id == ""``). It must NOT satisfy canonical
    identity coverage, but it must NOT fail the canonical invariant either:
    canonical frozen refs equal the canonical expected projection while the
    composition ref coexists for Router payload construction. The pipeline
    therefore progresses past both the binding invariant and the frozen
    coverage identity gate when canonical references are valid.
    """
    from types import SimpleNamespace

    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    project_id = PROJECT_ID
    scene_id = "scene_001"
    shot_id = "scene_001_shot_001"
    binding = [_character_binding_row(), _setting_binding_row()]
    # Keep the setting row project-scoped to this fixture project.
    binding[1]["project_id"] = project_id

    scene = {
        "scene_id": scene_id,
        "heading": "INT. TEST ROOM - DAY",
        "text": "A single lamp glows beside a closed book.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": project_id,
        "script_text": "INT. TEST ROOM - DAY\nA single lamp glows beside a closed book.",
        "execution_summary": {"scenes": [scene]},
    }
    board_shot = SimpleNamespace(
        project_id=project_id,
        scene_id=scene_id,
        shot_id=shot_id,
        shot_number=1,
        storyboard_shot_id="board-shot-1",
        version_id="approved-test-version",
        status="approved",
        updated_at="2026-10-01T00:00:01+00:00",
        prompt="originating-prompt-1",
        duration_seconds=5,
        parameters={
            "duration": 5,
            "ratio": "16:9",
            "storyboard_frame_url": STORYBOARD_URL,
            "storyboard": {
                "version_id": "approved-test-version",
                "storyboard_shot_id": "board-shot-1",
            },
        },
        camera_plan={"camera": "Hold", "framing": "Wide"},
        render_contract=SimpleNamespace(
            provider_neutral_prompt="originating-prompt-1",
            structured_parameters={"camera_plan": {"camera": "Hold", "framing": "Wide"}},
            duration_seconds=5,
            aspect_ratio="16:9",
        ),
        metadata={},
    )
    monkeypatch.setattr(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.scene_render_inputs",
        lambda _project_id, _scene_id: [board_shot],
    )

    def _resolve_requirements(**kwargs):
        return {
            "scene_id": scene_id,
            "character_ids": [CHARACTER_ID],
            "characters": {
                CHARACTER_ID: {"name": "Dre", "urls": [binding[0]["uri"]], "references": [dict(binding[0])]},
            },
            "setting_id": SETTING_ID,
            "setting_urls": [binding[1]["uri"]],
            "setting_references": [dict(binding[1])],
            "allowed_urls": [binding[0]["uri"], binding[1]["uri"]],
        }

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

    # Resolve creator coverage decisions via a probe so the real coverage
    # builder (and therefore the real freeze path) has no blockers. Single
    # shot, single content line, intentional silence for dialogue.
    from app.services.scene_coverage_contract import build_scene_coverage_contract

    probe_requirements = _resolve_requirements()
    probe_coverage, _, _ = build_scene_coverage_contract(
        project_id=project_id,
        project=project,
        scene=scene,
        shots=[{"shot_id": shot_id, "scene_id": scene_id, "parameters": {}}],
        reference_requirements={
            "setting_id": probe_requirements["setting_id"],
            "characters": probe_requirements["characters"],
            "reference_binding": binding,
        },
    )
    creator_decisions = [
        {
            "obligation_type": "content",
            "obligation_id": row["content_id"],
            "status": "ASSIGNED",
            "shot_id": shot_id,
            "reason": "",
        }
        for row in probe_coverage["content_units"]
    ]
    creator_decisions.extend(
        [
            {
                "obligation_type": "shot_content",
                "obligation_id": shot_id,
                "status": "UNRESOLVED",
                "shot_id": None,
                "reason": "",
            },
            {
                "obligation_type": "shot_dialogue",
                "obligation_id": shot_id,
                "status": "INTENTIONAL_SILENCE",
                "reason": "The approved shot contains no spoken dialogue.",
            },
        ]
    )
    board_shot.parameters["creator_coverage_decisions"] = creator_decisions

    service = SceneProductionPipelineService(backend_root=tmp_path)
    from app.services.generation_contract import GenerationContractError

    try:
        batch = service.prepare_scene_batch(
            project_id=project_id,
            scene_id=scene_id,
            project=project,
            provider="simulated",
        )
    except GenerationContractError as exc:
        raise AssertionError(
            "provenance-aware contract must pass prepare with valid canonical "
            f"refs plus distinct storyboard composition: {exc}"
        ) from exc

    entries = [row for row in batch["entries"] if row.get("shot_id") == shot_id]
    assert len(entries) == 1
    entry = entries[0]
    # The canonical binding survives verbatim: setting keeps project_id, order kept.
    assert entry["reference_binding"] == binding
    assert entry["reference_binding"][1]["project_id"] == project_id
    assert entry["generation_settings"]["frozen_reference_binding"] == binding

    from app.services.generation_contract import FrozenGenerationContract

    frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
    assert len(frozen.references) == 3
    assert _canonical_frozen_references(frozen) == _canonical_binding_to_contract_references(binding)
    storyboard = [ref for ref in frozen.references if ref.source == "storyboard_frame_url"]
    assert len(storyboard) == 1
    assert storyboard[0].uri == STORYBOARD_URL
