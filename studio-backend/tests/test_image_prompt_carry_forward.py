"""Hash-gated image-prompt carry-forward (design item C, gate-approved).

A new board version mints brand-new shot IDs; without carry-forward the new
version's image prompts start missing and the D4 gate blocks approval until a
human re-saves every prompt. Carry-forward copies an APPROVED row onto the
clone's new ID only when the clone's live canonical sha256 still equals the
row's source_prompt_sha256. Nothing else carries; proposed is never upgraded;
the D4 gate is unchanged.

Covers every version-creating path: explicit create_version, Scene Direction /
coverage saves (same save), and camera approval (which mints via
create_version).
"""

from __future__ import annotations

import json

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.previs_service import PrevisService
from app.services.project_store import ProjectStore
from app.services.scene_direction_service import SceneDirectionService
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.storyboard_image_prompt_service import (
    storyboard_image_prompt_service,
)


SCENE_TEXT = """INT. ROOM - NIGHT
Maya stands by the door.
MAYA
Keep it.
JULES
I will."""


def _fixture(tmp_path, shot_count: int = 2):
    storage = DatabaseStorage(str(tmp_path / "db"))
    project = StudioProject(
        project_id="carry-film",
        title="Carry",
        script_text=SCENE_TEXT,
        execution_summary={
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "description": "Maya passes a key to Jules.",
                    "text": SCENE_TEXT,
                    "characters": ["Maya", "Jules"],
                }
            ],
            "dialogue_lines": [
                {"line_id": "a", "scene_id": "scene_001", "character_name": "MAYA", "text": "Keep it."},
                {"line_id": "b", "scene_id": "scene_001", "character_name": "JULES", "text": "I will."},
            ],
        },
    )
    storage.save_project(project)
    service = StoryboardBlueprintService(storage=storage)
    service.project_store = ProjectStore(str(tmp_path / "state.json"))
    service.project_store.save_project(project.model_dump())
    detail = service.get_or_create_blueprint(
        project_id="carry-film", scene_id="scene_001", shot_count=shot_count
    )
    storyboard_image_prompt_service.set_storage(storage)
    return service, storage, detail


def _approve_all_human(storage, detail, prefix: str = "Approved human prompt") -> list:
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        storyboard_image_prompt_service.edit_for_shot(
            shot, image_prompt=f"{prefix} for {shot.shot_id}", edited_by="creator"
        )
        storyboard_image_prompt_service.approve_for_shot(shot, approved_by="creator")
    return shots


def _approve_board(storage, detail) -> None:
    version = storage.get_storyboard_blueprint_version(detail["version"].version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = "2026-10-18T00:00:00+00:00"
    version.approved_by = "test-creator"
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.approved_version_id = version.version_id
    storage.save_storyboard_blueprint(blueprint)


def test_carry_on_equal_hash_via_create_version(tmp_path):
    service, storage, detail = _fixture(tmp_path)
    _approve_all_human(storage, detail)
    source_rows = {
        row["shot_id"]: row
        for row in storage.list_storyboard_image_prompts(
            detail["blueprint"].blueprint_id, detail["version"].version_id
        )
    }
    assert all(row["status"] == "approved" for row in source_rows.values())

    service.create_version(blueprint_id=detail["blueprint"].blueprint_id)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    clones = storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id)
    assert len(clones) == 2
    for clone in clones:
        row = storage.get_storyboard_image_prompt(clone.storyboard_shot_id)
        assert row is not None, f"missing carried row for {clone.shot_id}"
        assert row["status"] == "approved"
        assert row["image_prompt"] == source_rows[clone.shot_id]["image_prompt"]
        assert row["approved_by"] == "creator"
        assert row["origin"] == "human"
        assert row["storyboard_shot_id"] != source_rows[clone.shot_id]["storyboard_shot_id"]
        assert row["version_id"] == blueprint.current_version_id
        rules = json.loads(row["rules_applied_json"])
        assert any(str(item).startswith("carried_from:") for item in rules)
    # Gate parity: the carried version approves without further human clicks.
    gate = storyboard_image_prompt_service.gate_for_version(clones)
    assert gate["approved"] is True


def test_no_carry_on_changed_hash(tmp_path):
    service, storage, detail = _fixture(tmp_path)
    shots = _approve_all_human(storage, detail)
    # Change one shot's canonical text on the current version: its approved
    # row goes stale, so the next version must not inherit it.
    service.update_shot(
        blueprint_id=detail["blueprint"].blueprint_id,
        storyboard_shot_id=shots[0].storyboard_shot_id,
        render_contract={"provider_neutral_prompt": shots[0].render_contract.provider_neutral_prompt + " Extra beat."},
        change_reason="shot_update",
    )
    service.create_version(blueprint_id=detail["blueprint"].blueprint_id)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    clones = {
        shot.shot_id: shot
        for shot in storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id)
    }
    changed = storage.get_storyboard_image_prompt(clones[shots[0].shot_id].storyboard_shot_id)
    assert changed["status"] == "proposed"  # fresh derive, never inherited
    unchanged = storage.get_storyboard_image_prompt(clones[shots[1].shot_id].storyboard_shot_id)
    assert unchanged["status"] == "approved"
    gate = storyboard_image_prompt_service.gate_for_version(list(clones.values()))
    assert gate["approved"] is False  # D4 still blocks on the changed shot


def test_never_upgrades_proposed_to_approved(tmp_path):
    service, storage, detail = _fixture(tmp_path)
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        storyboard_image_prompt_service.derive_for_shot(shot)  # proposed only
    service.create_version(blueprint_id=detail["blueprint"].blueprint_id)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    clones = storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id)
    rows = [storage.get_storyboard_image_prompt(shot.storyboard_shot_id) for shot in clones]
    assert all(row is not None and row["status"] == "proposed" for row in rows)
    assert storyboard_image_prompt_service.gate_for_version(clones)["approved"] is False


def test_scene_direction_save_carries_with_coverage_decisions(tmp_path):
    service, storage, detail = _fixture(tmp_path)
    _approve_all_human(storage, detail)
    _approve_board(storage, detail)
    direction = SceneDirectionService(storage)
    direction.blueprints.project_store = service.project_store
    data = direction.get("carry-film", "scene_001")
    from app.models.scene_direction import SaveSceneDirection

    payload = SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[
            shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
            for shot in data.shots
        ],
    )
    saved = direction.save("carry-film", "scene_001", payload)
    clones = storage.list_storyboard_shots(detail["blueprint"].blueprint_id, saved.version_id)
    assert len(clones) == 2
    for clone in clones:
        row = storage.get_storyboard_image_prompt(clone.storyboard_shot_id)
        assert row is not None and row["status"] == "approved"
    assert storyboard_image_prompt_service.gate_for_version(clones)["approved"] is True


def test_camera_approval_path_carries(tmp_path):
    service, storage, detail = _fixture(tmp_path)
    shots = _approve_all_human(storage, detail)
    _approve_board(storage, detail)
    # Stage a pending AI camera suggestion on shot 1 (template values, no
    # creator plan yet) so approve_ai_camera has something to lock.
    target = next(s for s in shots if s.shot_number == 1)
    target.visual_plan = target.visual_plan.model_copy(
        update={"framing": "wide shot", "camera_movement": "slow push in", "lens_language": "35mm"}
    )
    storage.save_storyboard_shot(target)
    result = PrevisService(storage).approve_ai_camera(
        "carry-film", "scene_001", target.storyboard_shot_id
    )
    clones = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, result["version_id"]
    )
    assert len(clones) == 2
    for clone in clones:
        row = storage.get_storyboard_image_prompt(clone.storyboard_shot_id)
        assert row is not None and row["status"] == "approved", (
            f"camera-approval mint dropped the prompt for {clone.shot_id}"
        )
    assert storyboard_image_prompt_service.gate_for_version(clones)["approved"] is True
    assert result["approved_camera"]
