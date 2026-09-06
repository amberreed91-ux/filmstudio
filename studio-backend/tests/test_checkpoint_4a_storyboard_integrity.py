from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.services.project_store import ProjectStore
from app.services.stability import PersistenceError, StateError, ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService


def _service(tmp_path: Path, *, project_id: str = "project_storyboard") -> tuple[StoryboardBlueprintService, DatabaseStorage]:
    storage = DatabaseStorage(str(tmp_path / "storyboard-db"))
    state = ProjectStore(str(tmp_path / "storyboard-projects.json"))
    state.save_project(
        {
            "project_id": project_id,
            "title": "Checkpoint 4 Storyboard",
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "heading": "INT. EDIT BAY - NIGHT",
                        "description": "Maya chooses whether to hold the silence.",
                        "location": "Edit bay",
                        "time_of_day": "night",
                        "emotional_tone": "contained dread",
                        "characters": ["MAYA"],
                    }
                ]
            },
        }
    )
    service = StoryboardBlueprintService(storage)
    service.project_store = state
    return service, storage


def test_missing_scene_cannot_create_fallback_canonical_blueprint(tmp_path: Path) -> None:
    service, storage = _service(tmp_path)

    with pytest.raises(StateError) as raised:
        service.get_or_create_blueprint(
            project_id="project_storyboard",
            scene_id="scene_missing",
            shot_count=1,
        )

    assert raised.value.message == "Scene not found"
    assert storage.list_storyboard_blueprints("project_storyboard") == []


def test_regeneration_creates_distinct_version_and_preserves_approved_history(tmp_path: Path) -> None:
    service, storage = _service(tmp_path)
    first = service.get_or_create_blueprint(
        project_id="project_storyboard",
        scene_id="scene_001",
        shot_count=2,
    )
    locked = service.lock_shot(
        blueprint_id=first["blueprint"].blueprint_id,
        storyboard_shot_id=first["shots"][0].storyboard_shot_id,
        locked=True,
    )
    service.run_continuity_review(
        blueprint_id=first["blueprint"].blueprint_id,
        version_id=first["version"].version_id,
    )
    approved = service.approve_version(
        blueprint_id=first["blueprint"].blueprint_id,
        version_id=first["version"].version_id,
        approved_by="creator",
    )

    regenerated = service.create_version(
        blueprint_id=first["blueprint"].blueprint_id,
        shot_count=3,
        change_reason="explore_patient_coverage",
        preserve_locked_shots=True,
    )

    versions = service.list_versions(first["blueprint"].blueprint_id)
    assert [version.version_number for version in versions] == [1, 2]
    assert versions[0].status.value == "approved"
    assert versions[1].status.value == "draft"
    assert versions[1].source_version_id == versions[0].version_id
    assert regenerated["blueprint"].approved_version_id == approved["version"].version_id
    assert regenerated["blueprint"].current_version_id == versions[1].version_id

    regenerated_locked = next(shot for shot in regenerated["shots"] if shot.shot_id == locked.shot_id)
    assert regenerated_locked.storyboard_shot_id != locked.storyboard_shot_id
    assert regenerated_locked.locked is True
    assert regenerated_locked.metadata["source_version_id"] == versions[0].version_id

    old_shots = storage.list_storyboard_shots(first["blueprint"].blueprint_id, versions[0].version_id)
    assert all(shot.status.value == "approved" for shot in old_shots)
    reloaded = StoryboardBlueprintService(storage)
    reloaded.project_store = service.project_store
    assert reloaded.get_blueprint_detail(
        project_id="project_storyboard",
        scene_id="scene_001",
    )["version"].version_id == versions[1].version_id


def test_draft_shot_create_reorder_delete_is_deterministic(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    detail = service.get_or_create_blueprint(
        project_id="project_storyboard",
        scene_id="scene_001",
        shot_count=2,
    )
    blueprint_id = detail["blueprint"].blueprint_id
    created = service.create_shot(
        blueprint_id=blueprint_id,
        shot_id="scene_001_insert_reaction",
        intent={"purpose": "reaction", "emotional_target": "the silence finally registers"},
        render_contract={"provider_neutral_prompt": "Maya absorbs the consequence in a held close-up.", "render_readiness": "ready"},
    )
    current_ids = [shot.storyboard_shot_id for shot in [*detail["shots"], created]]

    reordered = service.reorder_shots(
        blueprint_id=blueprint_id,
        ordered_storyboard_shot_ids=list(reversed(current_ids)),
    )
    assert [shot.storyboard_shot_id for shot in reordered] == list(reversed(current_ids))
    assert [shot.shot_number for shot in reordered] == [1, 2, 3]
    assert [shot.shot_id for shot in reordered][-1] == detail["shots"][0].shot_id

    remaining = service.delete_shot(
        blueprint_id=blueprint_id,
        storyboard_shot_id=reordered[1].storyboard_shot_id,
    )
    assert [shot.shot_number for shot in remaining] == [1, 2]
    assert reordered[1].storyboard_shot_id not in {shot.storyboard_shot_id for shot in remaining}

    with pytest.raises(StateError):
        service.create_shot(blueprint_id=blueprint_id, shot_id=remaining[0].shot_id)
    with pytest.raises(ValidationError):
        service.reorder_shots(
            blueprint_id=blueprint_id,
            ordered_storyboard_shot_ids=[remaining[0].storyboard_shot_id] * 2,
        )


def test_approved_version_rejects_shot_mutation_and_image_replacement(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    detail = service.get_or_create_blueprint(
        project_id="project_storyboard",
        scene_id="scene_001",
        shot_count=2,
    )
    service.run_continuity_review(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    approved = service.approve_version(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    shot = approved["shots"][0]

    with pytest.raises(StateError):
        service.lock_shot(
            blueprint_id=approved["blueprint"].blueprint_id,
            storyboard_shot_id=shot.storyboard_shot_id,
            locked=False,
        )
    with pytest.raises(StateError):
        service.delete_shot(
            blueprint_id=approved["blueprint"].blueprint_id,
            storyboard_shot_id=shot.storyboard_shot_id,
        )
    with pytest.raises(StateError):
        service.generate_storyboard_image_for_scene_shot(
            project_id=shot.project_id,
            scene_id=shot.scene_id,
            provider="pollinations",
            storyboard_shot_id=shot.storyboard_shot_id,
        )


def test_atomic_blueprint_creation_rolls_back_on_duplicate_shot_record(tmp_path: Path, monkeypatch) -> None:
    service, storage = _service(tmp_path)
    original = service._build_initial_shots

    def duplicate_primary_key(**kwargs):
        shots = original(**kwargs)
        duplicate = shots[0].model_copy(deep=True)
        duplicate.shot_id = "different_business_shot"
        shots.append(duplicate)
        return shots

    monkeypatch.setattr(service, "_build_initial_shots", duplicate_primary_key)

    with pytest.raises(PersistenceError):
        service.get_or_create_blueprint(
            project_id="project_storyboard",
            scene_id="scene_001",
            shot_count=1,
        )

    assert storage.list_storyboard_blueprints("project_storyboard") == []
