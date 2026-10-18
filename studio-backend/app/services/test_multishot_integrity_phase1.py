from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.stability import ValidationError
from app.utils.helpers import derive_scene_id_from_shot_id


def _pipeline(tmp_path: Path) -> SceneProductionPipelineService:
    return SceneProductionPipelineService(backend_root=tmp_path)


def _scene(scene_id: str = "scene_001", shots: list[dict] | None = None) -> dict:
    return {"scene_id": scene_id, "description": "A scene description.", "shots": shots or []}


def _project(scene: dict, *, project_id: str = "project_phase1", candidates: list[dict] | None = None) -> dict:
    return {
        "project_id": project_id,
        "execution_summary": {
            "scenes": [scene],
            "shot_candidates": candidates or [],
        },
    }


def test_selected_scene_shots_with_matching_ids_are_accepted(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene(
        shots=[
            {"shot_id": "scene_001_shot_002", "scene_id": "scene_001"},
            {"shot_id": "scene_001_shot_001", "scene_id": "scene_001"},
        ]
    )

    shots = service._resolve_ordered_shots(_project(scene), scene)

    assert [shot["shot_id"] for shot in shots] == ["scene_001_shot_001", "scene_001_shot_002"]


def test_slugged_scene_shots_are_accepted_and_foreign_slug_is_rejected(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    selected_scene = _scene(
        "scene_lantern_17",
        shots=[{"shot_id": "scene_lantern_17_shot_001", "scene_id": "scene_lantern_17"}],
    )

    shots = service._resolve_ordered_shots(_project(selected_scene), selected_scene)
    assert [shot["shot_id"] for shot in shots] == ["scene_lantern_17_shot_001"]

    foreign_scene = _scene(
        "scene_lantern_17",
        shots=[
            {"shot_id": "scene_lantern_17_shot_001", "scene_id": "scene_lantern_17"},
            {"shot_id": "scene_other_9_shot_001", "scene_id": "scene_lantern_17"},
        ],
    )
    with pytest.raises(ValidationError, match="contains shots owned by another scene"):
        service._resolve_ordered_shots(_project(foreign_scene), foreign_scene)


def test_foreign_shot_in_scene_shots_is_rejected(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene(
        shots=[
            {"shot_id": "scene_001_shot_001", "scene_id": "scene_001"},
            {"shot_id": "scene_002_shot_001", "scene_id": "scene_001"},
        ]
    )

    with pytest.raises(ValidationError, match="contains shots owned by another scene"):
        service._resolve_ordered_shots(_project(scene), scene)


def test_mixed_scene_candidate_set_rejects_conflicting_explicit_and_encoded_owner(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene("scene_001")
    project = _project(
        scene,
        candidates=[
            {"shot_id": "scene_001_shot_001", "scene_id": "scene_001"},
            {"shot_id": "scene_002_shot_001", "scene_id": "scene_001"},
        ],
    )

    with pytest.raises(ValidationError, match="contains shots owned by another scene"):
        service._resolve_ordered_shots(project, scene)


def test_encoded_foreign_shot_cannot_override_selected_scene_in_scene_shot_list(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene(
        shots=[
            {"shot_id": "scene_001_shot_001", "scene_id": "scene_001"},
            {"shot_id": "scene_002_shot_009", "scene_id": "scene_001"},
        ]
    )

    with pytest.raises(ValidationError):
        service._resolve_ordered_shots(_project(scene), scene)


def test_reference_lookup_cannot_derive_foreign_scene_after_ownership_validation(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    foreign_shot = {"shot_id": "scene_002_shot_001", "scene_id": "scene_001"}

    assert not service._scene_ownership_matches(selected_scene_id="scene_001", shot=foreign_shot)
    assert derive_scene_id_from_shot_id(foreign_shot["shot_id"]) == "scene_002"


def test_approved_storyboard_resolution_precedes_scene_shots_unchanged(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene("scene_001", shots=[{"shot_id": "scene_001_shot_099", "scene_id": "scene_001"}])
    board_inputs = [{
        "scene_id": "scene_001",
        "shot_id": "scene_001_shot_001",
        "parameters": {},
    }]
    with patch(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.scene_render_inputs",
        return_value=board_inputs,
    ):
        shots = service._resolve_ordered_shots(_project(scene), scene)

    assert shots == board_inputs


def test_prepared_snapshot_is_consumed_without_a_second_shot_resolution_and_keeps_inputs(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene(shots=[{
        "shot_id": "scene_001_shot_001",
        "scene_id": "scene_001",
        "prompt": "prepared prompt",
        "parameters": {"negative_prompt": "no text"},
    }])
    project = _project(scene)
    entry = {
        "project_id": "project_phase1",
        "scene_id": "scene_001",
        "shot_id": "scene_001_shot_001",
        "shot_order": 1,
        "prompt": "prepared prompt",
        "negative_prompt": "no text",
        "camera_plan": {"framing": "wide"},
        "camera_instructions": [{"dimension": "framing", "value": "wide", "instruction_source": "APPROVED"}],
        "dialogue_lines": [],
        "references": ["approved://ref"],
        "reference_roles": ["character"],
        "generation_settings": {"negative_prompt": "no text", "camera_plan": {"framing": "wide"}},
        "generation_context_id": "context-1",
        "generation_context": {"scene_version": "scene-v1", "shot_version": "shot-v1"},
        "scene_version": "scene-v1",
        "shot_version": "shot-v1",
        "generation_contract": {"shot_id": "scene_001_shot_001"},
        "manifest_fingerprint": "manifest-1",
        "duration_seconds": 5,
        "blockers": [],
    }
    snapshot = {
        "project_id": "project_phase1",
        "scene_id": "scene_001",
        "provider": None,
        "expires_at": 10**12,
        "ready": True,
        "blockers": [],
        "shots": deepcopy([scene["shots"][0]]),
        "entries": [entry],
        "manifest": {"shots": [], "manifest_fingerprint": "manifest-1"},
        "scene_snapshot": deepcopy(scene),
        "scene_snapshot_fingerprint": service._snapshot_fingerprint(scene),
        "source_kind": "scene_shots",
        "shot_source_fingerprint": service._snapshot_fingerprint(scene["shots"]),
        "canonical_script_sha256": hashlib.sha256(str(project.get("script_text") or "").encode("utf-8")).hexdigest(),
    }
    service._prepared_scene_batches["snapshot"] = snapshot

    with patch.object(service, "_resolve_ordered_shots", side_effect=AssertionError("must not resolve again")):
        consumed = service._consume_prepared_scene_batch(
            "snapshot",
            project_id="project_phase1",
            scene_id="scene_001",
            provider=None,
            project=project,
        )

    assert consumed["entries"][0]["prompt"] == "prepared prompt"
    assert consumed["entries"][0]["generation_context_id"] == "context-1"
    assert consumed["manifest"]["manifest_fingerprint"] == "manifest-1"
    assert entry["negative_prompt"] == "no text"
    assert entry["camera_plan"] == {"framing": "wide"}
    assert entry["references"] == ["approved://ref"]
    assert entry["generation_contract"]["shot_id"] == "scene_001_shot_001"


def test_scene_shot_mutation_after_preparation_is_rejected(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene(shots=[{"shot_id": "scene_001_shot_001", "scene_id": "scene_001", "prompt": "old"}])
    project = _project(scene)
    prepared_scene = deepcopy(scene)
    batch = {
        "project_id": "project_phase1",
        "scene_id": "scene_001",
        "scene_snapshot_fingerprint": service._snapshot_fingerprint(prepared_scene),
        "source_kind": "scene_shots",
        "shot_source_fingerprint": service._snapshot_fingerprint(prepared_scene["shots"]),
    }
    project["execution_summary"]["scenes"][0]["shots"][0]["prompt"] = "changed after preflight"

    with pytest.raises(ValidationError, match="scene changed after preflight"):
        service._assert_prepared_scene_batch_current(batch, project=project, scene_id="scene_001")


def test_camera_source_mutation_after_preflight_invalidates_snapshot(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene(shots=[{
        "shot_id": "scene_001_shot_001",
        "scene_id": "scene_001",
        "parameters": {"creator_shot_planning": {"camera": "locked off"}},
    }])
    project = _project(scene)
    prepared_source = deepcopy(scene["shots"])
    batch = {
        "project_id": "project_phase1",
        "scene_id": "scene_001",
        "scene_snapshot_fingerprint": service._snapshot_fingerprint(scene),
        "source_kind": "scene_shots",
        "shot_source_fingerprint": service._snapshot_fingerprint(prepared_source),
    }
    project["execution_summary"]["scenes"][0]["shots"][0]["parameters"]["creator_shot_planning"]["camera"] = "crane up"

    with pytest.raises(ValidationError, match="scene changed after preflight"):
        service._assert_prepared_scene_batch_current(batch, project=project, scene_id="scene_001")


def test_canonical_screenplay_mutation_after_preparation_is_rejected(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene()
    project = _project(scene)
    project["script_text"] = "INT. TEST ROOM - DAY\\nA person waits."
    original_hash = hashlib.sha256(project["script_text"].encode("utf-8")).hexdigest()
    batch = {
        "project_id": "project_phase1",
        "scene_id": "scene_001",
        "scene_snapshot_fingerprint": service._snapshot_fingerprint(scene),
        "source_kind": "scene_shots",
        "shot_source_fingerprint": service._snapshot_fingerprint(scene["shots"]),
        "canonical_script_sha256": original_hash,
    }
    project["script_text"] = project["script_text"].replace("A person waits", "A person leaves")

    with pytest.raises(ValidationError, match="canonical screenplay changed after preflight") as exc_info:
        service._assert_prepared_scene_batch_current(batch, project=project, scene_id="scene_001")

    assert exc_info.value.stage == "scene_pipeline_lineage"
    assert exc_info.value.metadata["failure_type"] == "stale_canonical_script"


def test_storyboard_version_mutation_after_preparation_is_rejected(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene()
    board = [{"shot_id": "scene_001_shot_001", "version_id": "board-v1", "prompt": "approved"}]
    batch = {
        "project_id": "project_phase1",
        "scene_id": "scene_001",
        "scene_snapshot_fingerprint": service._snapshot_fingerprint(scene),
        "source_kind": "storyboard",
        "shot_source_fingerprint": service._snapshot_fingerprint(board),
    }
    project = _project(scene)
    batch["canonical_script_sha256"] = hashlib.sha256(str(project.get("script_text") or "").encode("utf-8")).hexdigest()
    changed_board = [{"shot_id": "scene_001_shot_001", "version_id": "board-v2", "prompt": "changed"}]
    with patch(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.scene_render_inputs",
        return_value=changed_board,
    ), pytest.raises(ValidationError, match="shot set changed after preflight"):
        service._assert_prepared_scene_batch_current(batch, project=project, scene_id="scene_001")


def test_explicit_scene_identity_conflict_is_rejected_even_when_shot_id_matches(tmp_path: Path) -> None:
    service = _pipeline(tmp_path)
    scene = _scene("scene_001")
    project = _project(
        scene,
        candidates=[
            {"shot_id": "scene_001_shot_001", "scene_id": "scene_002"},
        ],
    )

    with pytest.raises(ValidationError, match="contains shots owned by another scene"):
        service._resolve_ordered_shots(project, scene)
