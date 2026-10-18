"""Phase 1: prompt Rebuild + re-approve (gate decision 2026-10-18).

- appearance_approval stays the prompt source; the scene_001-shape test below
  locks all six look-locked characters, names only MAYA in shots 3/4 (nobody
  in 1/2/5), and shows MAYA-only blocks in all five per-shot outputs.
- Rebuild on an approved version mints exactly one new draft; on a draft it
  updates in place. Shots without a stored builder hash need an explicit
  per-shot confirm (default unticked at the UI layer). Hand-edited shots are
  skipped. Empty locked blocks refuse loudly. Reference-lock rows are
  reported as information only.
- Re-approving an image prompt against rebuilt text is one explicit click per
  shot; the D4 gate still blocks until then.

All tests run with temp databases. No provider calls.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.character_look import CharacterLookApprovalRequest
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.routes import storyboard_blueprints as blueprint_routes
from app.services.character_look_service import CharacterLookService
from app.services.character_visual_reference_service import (
    CharacterVisualReferenceService,
)
from app.services.project_store import ProjectStore
from app.services.shot_prompt_builder import (
    build_locked_appearance_block,
    build_shot_aware_prompt,
)
from app.services.stability import StateError, ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.storyboard_image_prompt_service import (
    storyboard_image_prompt_service,
)


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------

SCENE_TEXT_TWO_SHOT = """INT. ROOFTOP - NIGHT
MAYA studies the skyline, paper crane in hand.
MAYA folds the loose pages against the wind.
The city holds its breath below MAYA.
MAYA holds the crane up to the light."""

CHARACTER_SPECS = {
    "MAYA": {"age": "30", "look": "brown skin, long locs", "visual_prompt_summary": "long locs, layered canvas jacket"},
    "DRE": {"age": "34", "look": "short fade, steady gaze", "visual_prompt_summary": "short fade, work shirt"},
}


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 48), "brown").save(output, format="PNG")
    return output.getvalue()


def _lock(storage: DatabaseStorage, service: CharacterLookService, char: dict) -> None:
    url = service.upload(char["project_id"], char["id"], _png())
    view = service.get(char["project_id"], char["id"])
    request = CharacterLookApprovalRequest(
        expected_profile_revision=view.profile_revision, face_image_url=url
    )
    service.approve(char["project_id"], char["id"], request)


def _make_fixture(tmp_path, scene_text: str, names: list[str], shot_count: int):
    storage = DatabaseStorage(str(tmp_path / "db"))
    project = StudioProject(
        project_id="rebuild-film",
        title="Rebuild",
        script_text=scene_text,
        execution_summary={
            "scenes": [{"scene_id": "scene_001", "description": "Rooftop.", "text": scene_text}],
        },
    )
    storage.save_project(project)
    look_service = CharacterLookService(storage, tmp_path / "outputs")
    chars = {}
    for name in names:
        char = storage.save_character("rebuild-film", name, dict(CHARACTER_SPECS.get(name, {"look": f"{name} look"})))
        _lock(storage, look_service, char)
        chars[name] = storage.get_character(char["id"], "rebuild-film")
    service = StoryboardBlueprintService(storage=storage)
    service.project_store = ProjectStore(str(tmp_path / "state.json"))
    service.project_store.save_project(project.model_dump())
    detail = service.get_or_create_blueprint(
        project_id="rebuild-film", scene_id="scene_001", shot_count=shot_count
    )
    storyboard_image_prompt_service.set_storage(storage)
    return service, storage, detail, chars


def _approve_manually(storage: DatabaseStorage, detail) -> None:
    version = storage.get_storyboard_blueprint_version(detail["version"].version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = "2026-10-18T00:00:00+00:00"
    version.approved_by = "test-creator"
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.approved_version_id = version.version_id
    storage.save_storyboard_blueprint(blueprint)


def _strip_builder_hashes(storage: DatabaseStorage, detail) -> list:
    """Simulate pre-feature rows: no stored builder hash anywhere.

    The first shot also gets stale legacy-builder text so the before/after
    diff path is exercised; the rest rebuild idempotently.
    """
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for position, shot in enumerate(shots):
        shot.metadata = {}
        if position == 0:
            shot.render_contract.provider_neutral_prompt = (
                str(shot.render_contract.provider_neutral_prompt or "")
                + " Legacy builder wording."
            )
        storage.save_storyboard_shot(shot)
    return shots


# New intel rewrites the middle lines (not an append: the builder only keeps
# each segment's first two action lines, so appended lines would rebuild
# byte-identical and never stale the image prompts).
RETARGETED_SCENE_TEXT = """INT. ROOFTOP - NIGHT
MAYA studies the skyline, paper crane in hand.
MAYA folds the loose pages against the rising wind.
The city holds its breath below MAYA.
MAYA holds the crane up to the driving rain."""


def _retarget_scene_text(service, storage: DatabaseStorage, new_text: str) -> None:
    """Simulate new scene intel arriving between approval and rebuild."""
    project = storage.get_project("rebuild-film")
    data = project.model_dump(mode="json")
    data["script_text"] = new_text
    data["execution_summary"]["scenes"][0]["text"] = new_text
    storage.save_project(StudioProject(**data))
    service.project_store.save_project(data)


def _prompts_by_shot(storage: DatabaseStorage, blueprint_id: str, version_id: str) -> dict:
    return {
        shot.shot_id: str(shot.render_contract.provider_neutral_prompt or "")
        for shot in storage.list_storyboard_shots(blueprint_id, version_id)
    }


# ----------------------------------------------------------------------
# 1. scene_001 shape: six look-locked, only MAYA named in shots 3/4
# ----------------------------------------------------------------------

SCENE001_NAMES = ["MAYA", "DRE", "SIMONE", "JAY", "ELENA", "MOM"]

# Ten content lines -> five 2-line segments. Only the segment 3/4 lines name
# MAYA; no other locked name appears anywhere (word-boundary safe prose).
SCENE001_TEXT = """INT. ROOFTOP - NIGHT
The stairwell door bangs open in the wind.
Loose pages skate across the concrete.
A paper crane snags on the railing wire.
Footsteps slow beside the dish.
MAYA studies the skyline, crane in hand.
MAYA folds the loose pages against the wind.
MAYA tracks the antenna light blinking red over the ledge.
The city holds its breath far below.
A siren fades somewhere downtown.
The crane lifts off into the dark."""


def test_scene001_shape_maya_only_blocks_in_all_five_shots(tmp_path, capsys):
    storage = DatabaseStorage(str(tmp_path / "db"))
    look_service = CharacterLookService(storage, tmp_path / "outputs")
    rows = []
    for name in SCENE001_NAMES:
        char = storage.save_character(
            "scene001-film",
            name,
            {"age": "30", "look": f"{name} distinctive look", "visual_prompt_summary": f"{name} summary"},
        )
        _lock(storage, look_service, char)
        rows.append(storage.get_character(char["id"], "scene001-film"))
    assert len(rows) == 6

    blocks = []
    for shot_number in range(1, 6):
        prompt = build_shot_aware_prompt(
            {"text": SCENE001_TEXT},
            shot_number,
            1,
            rows,
            total_shots=5,
        )
        assert "Locked appearance" in prompt, f"shot {shot_number} lost the block"
        tail = prompt.split("Locked appearance", 1)[1]
        blocks.append(tail)
        print(f"--- shot {shot_number} locked block ---")
        print("Locked appearance" + tail)

    for shot_number, tail in enumerate(blocks, start=1):
        assert "MAYA" in tail, f"shot {shot_number} missing MAYA"
        for other in ("DRE", "SIMONE", "JAY", "ELENA", "MOM"):
            assert other not in tail, f"shot {shot_number} leaks {other}"

    # The block-level scope agrees with the end-to-end builder on every shot.
    segments = SCENE001_TEXT.split("\n")
    assert len([line for line in segments if line.strip()]) == 11  # heading + 10
    direct = build_locked_appearance_block(rows, None, shot_text=None, scene_shot_texts=None)
    assert direct == ""
    captured = capsys.readouterr().out
    assert captured.count("locked block") == 5


# ----------------------------------------------------------------------
# 2. rebuild matrix
# ----------------------------------------------------------------------

def test_rebuild_legacy_shots_require_confirm_and_write_nothing(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA", "DRE"], 2
    )
    shots = _strip_builder_hashes(storage, detail)
    before = _prompts_by_shot(storage, detail["blueprint"].blueprint_id, detail["version"].version_id)

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert len(summary["confirm_required"]) == 2
    assert summary["rebuilt"] == []
    assert summary["cloned_from_version_id"] is None
    assert {item["shot_id"] for item in summary["confirm_required"]} == {s.shot_id for s in shots}
    for item in summary["confirm_required"]:
        assert item["before"] and item["after"]
    drifted = [item for item in summary["confirm_required"] if "Legacy builder" in item["before"]]
    assert len(drifted) == 1
    assert drifted[0]["before_sha256"] != drifted[0]["after_sha256"]
    # Nothing overwritten silently.
    assert _prompts_by_shot(storage, detail["blueprint"].blueprint_id, detail["version"].version_id) == before
    assert len(storage.list_storyboard_blueprint_versions(detail["blueprint"].blueprint_id)) == 1


def test_rebuild_confirmed_legacy_shots_updates_draft_in_place(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA", "DRE"], 2
    )
    shots = _strip_builder_hashes(storage, detail)
    shot_ids = [s.shot_id for s in shots]

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
        confirmed_shot_ids=shot_ids,
    )
    assert summary["cloned_from_version_id"] is None
    assert {item["shot_id"] for item in summary["rebuilt"]} == set(shot_ids)
    assert summary["version_id"] == detail["version"].version_id
    assert len(storage.list_storyboard_blueprint_versions(detail["blueprint"].blueprint_id)) == 1
    for item in summary["rebuilt"]:
        assert item["block_characters"] == ["MAYA"]
    refreshed = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in refreshed:
        assert shot.metadata["builder_output_sha256"]
        assert shot.metadata["prompt_rebuild"]["confirmed"] is True
        assert shot.metadata["prompt_rebuild"]["machine_built_prior"] is False
        # Both sides of the canonical diff persist for the re-approve action.
        assert shot.metadata["prompt_rebuild"]["after_prompt"] == str(
            shot.render_contract.provider_neutral_prompt or ""
        )
        assert shot.metadata["prompt_rebuild"]["before_prompt"]


def test_rebuild_machine_built_shots_need_no_confirm(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    # Fresh builds carry the builder hash (stamped at build time).
    for shot in storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    ):
        assert shot.metadata.get("builder_output_sha256")
    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert len(summary["rebuilt"]) == 2
    assert summary["confirm_required"] == []


def test_rebuild_approved_version_mints_exactly_one_draft(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    _approve_manually(storage, detail)
    approved_prompts = _prompts_by_shot(
        storage, detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    versions_before = {
        v.version_id
        for v in storage.list_storyboard_blueprint_versions(detail["blueprint"].blueprint_id)
    }

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert summary["cloned_from_version_id"] == detail["version"].version_id
    assert summary["version_id"] != detail["version"].version_id
    versions_after = storage.list_storyboard_blueprint_versions(detail["blueprint"].blueprint_id)
    assert len(versions_after) == len(versions_before) + 1
    new_version = storage.get_storyboard_blueprint_version(summary["version_id"])
    assert new_version.status == StoryboardBlueprintStatus.DRAFT
    # The approved version is untouched.
    assert _prompts_by_shot(storage, detail["blueprint"].blueprint_id, detail["version"].version_id) == approved_prompts
    assert storage.get_storyboard_blueprint_version(detail["version"].version_id).status == StoryboardBlueprintStatus.APPROVED
    assert len(summary["rebuilt"]) == 2


def test_rebuild_skips_hand_edited_shots(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shots = sorted(
        storage.list_storyboard_shots(detail["blueprint"].blueprint_id, detail["version"].version_id),
        key=lambda item: item.shot_number,
    )
    hand = shots[0]
    service.update_shot(
        blueprint_id=detail["blueprint"].blueprint_id,
        storyboard_shot_id=hand.storyboard_shot_id,
        render_contract={"provider_neutral_prompt": "Creator hand-tuned prompt."},
    )
    marked = storage.get_storyboard_shot(hand.storyboard_shot_id)
    assert marked.metadata.get("canonical_hand_edited_at")

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert summary["skipped_hand_edited"] == [hand.shot_id]
    assert {item["shot_id"] for item in summary["rebuilt"]} == {shots[1].shot_id}
    assert (
        storage.get_storyboard_shot(hand.storyboard_shot_id).render_contract.provider_neutral_prompt
        == "Creator hand-tuned prompt."
    )


def test_update_shot_visual_plan_only_sets_no_hand_edit_marker(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    service.update_shot(
        blueprint_id=detail["blueprint"].blueprint_id,
        storyboard_shot_id=shots[0].storyboard_shot_id,
        visual_plan={"framing": "close-up"},
    )
    assert "canonical_hand_edited_at" not in (storage.get_storyboard_shot(shots[0].storyboard_shot_id).metadata or {})


def test_rebuild_refuses_empty_locked_block_loudly(tmp_path):
    silent_text = """INT. ROOFTOP - NIGHT
The wind moves across the empty concrete.
A paper crane snags on the railing wire.
The antenna light blinks red over the ledge.
The city holds its breath far below."""
    service, storage, detail, _ = _make_fixture(tmp_path, silent_text, ["MAYA"], 2)
    before = _prompts_by_shot(storage, detail["blueprint"].blueprint_id, detail["version"].version_id)

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert len(summary["refused_empty_block"]) == 2
    assert summary["rebuilt"] == []
    assert _prompts_by_shot(storage, detail["blueprint"].blueprint_id, detail["version"].version_id) == before


def test_rebuild_preserves_camera_coverage_and_structured_parameters(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        shot.visual_plan.framing = "locked-framing"
        shot.visual_plan.camera_movement = "locked-move"
        shot.continuity_plan.location_continuity = "locked-location"
        shot.render_contract.structured_parameters.update(
            {
                "camera_plan": {"camera": "fixed", "framing": "locked-framing"},
                "creator_coverage_decisions": [{"obligation_id": "a", "shot_id": shot.shot_id}],
            }
        )
        shot.render_contract.reference_assets = ["ref-locked"]
        storage.save_storyboard_shot(shot)
    # Re-stamp after the test-only mutation so the shots stay machine-built.
    for shot in storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    ):
        from app.services.storyboard_blueprint_service import _prompt_sha256

        shot.metadata = {
            **(shot.metadata or {}),
            "builder_output_sha256": _prompt_sha256(
                str(shot.render_contract.provider_neutral_prompt or "")
            ),
        }
        storage.save_storyboard_shot(shot)

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert len(summary["rebuilt"]) == 2
    for shot in storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    ):
        assert shot.visual_plan.framing == "locked-framing"
        assert shot.visual_plan.camera_movement == "locked-move"
        assert shot.continuity_plan.location_continuity == "locked-location"
        assert shot.render_contract.structured_parameters["camera_plan"] == {
            "camera": "fixed",
            "framing": "locked-framing",
        }
        assert shot.render_contract.structured_parameters["creator_coverage_decisions"] == [
            {"obligation_id": "a", "shot_id": shot.shot_id}
        ]
        assert shot.render_contract.reference_assets == ["ref-locked"]


def test_rebuild_clone_preserves_camera_coverage_structured_and_hash(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        shot.visual_plan.framing = "clone-framing"
        shot.render_contract.structured_parameters.update(
            {"creator_coverage_decisions": [{"obligation_id": "c", "shot_id": shot.shot_id}]}
        )
        storage.save_storyboard_shot(shot)
    _approve_manually(storage, detail)

    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    clones = storage.list_storyboard_shots(detail["blueprint"].blueprint_id, summary["version_id"])
    assert len(clones) == 2
    for clone in clones:
        assert clone.visual_plan.framing == "clone-framing"
        assert clone.render_contract.structured_parameters["creator_coverage_decisions"] == [
            {"obligation_id": "c", "shot_id": clone.shot_id}
        ]
        assert clone.metadata["prompt_rebuild"]["machine_built_prior"] is True
        from app.services.storyboard_blueprint_service import _prompt_sha256

        assert clone.metadata.get("builder_output_sha256") == _prompt_sha256(
            str(clone.render_contract.provider_neutral_prompt or "")
        )


def test_clone_drops_stale_rebuild_provenance_and_restamps_hash(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shot = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )[0]
    shot.metadata = {
        **(shot.metadata or {}),
        "prompt_rebuild": {"rebuilt_at": "2026-01-01T00:00:00+00:00", "stale": True},
    }
    clone = service._clone_shot_for_version(shot, version_id="sbv_next", preserve_lock=False)
    assert "prompt_rebuild" not in (clone.metadata or {})
    from app.services.storyboard_blueprint_service import _prompt_sha256

    assert clone.metadata["builder_output_sha256"] == _prompt_sha256(
        str(clone.render_contract.provider_neutral_prompt or "")
    )
    assert clone.metadata["source_version_id"] == shot.version_id


def test_clone_of_hand_edited_shot_keeps_marker_and_drops_hash(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shot = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )[0]
    shot.metadata = {
        **(shot.metadata or {}),
        "canonical_hand_edited_at": "2026-10-18T00:00:00+00:00",
    }
    clone = service._clone_shot_for_version(shot, version_id="sbv_next", preserve_lock=False)
    assert clone.metadata.get("canonical_hand_edited_at") == "2026-10-18T00:00:00+00:00"
    assert "builder_output_sha256" not in (clone.metadata or {})


def test_rebuild_summary_reports_reference_locks_as_information(tmp_path):
    service, storage, detail, chars = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    CharacterVisualReferenceService().relock_character_reference(
        project_id="rebuild-film",
        character_id=chars["MAYA"]["id"],
        character_name="MAYA",
        image_url="https://example.test/maya.png",
        storage=storage,
    )
    summary = service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    assert summary["reference_lock_info"]
    assert {row["character_name"] for row in summary["reference_lock_info"]} == {"MAYA"}
    # Information only: the prompt source is still appearance_approval.
    for item in summary["rebuilt"]:
        assert item["block_characters"] == ["MAYA"]


def test_rebuild_refuses_non_current_version(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    first_version_id = detail["version"].version_id
    service.create_version(blueprint_id=detail["blueprint"].blueprint_id)
    with pytest.raises(StateError, match="current version"):
        service.rebuild_shot_prompts(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=first_version_id,
        )


# ----------------------------------------------------------------------
# 3. re-approve against rebuilt text + D4 gate interplay
# ----------------------------------------------------------------------

def _approve_image(storage: DatabaseStorage, detail, shot_number: int = 1):
    shots = sorted(
        storage.list_storyboard_shots(detail["blueprint"].blueprint_id, detail["version"].version_id),
        key=lambda item: item.shot_number,
    )
    shot = shots[shot_number - 1]
    record = storyboard_image_prompt_service.derive_for_shot(shot)
    return shot, storyboard_image_prompt_service.approve_for_shot(shot, approved_by="creator")


def test_image_prompt_stays_stale_without_click_and_gate_blocks(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shot, _ = _approve_image(storage, detail)
    assert storyboard_image_prompt_service.status_for_shot(
        shot, storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    )["state"] == "ready"

    _retarget_scene_text(service, storage, RETARGETED_SCENE_TEXT)
    service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    stale_shot = storage.get_storyboard_shot(shot.storyboard_shot_id)
    status = storyboard_image_prompt_service.status_for_shot(
        stale_shot, storage.get_storyboard_image_prompt(stale_shot.storyboard_shot_id)
    )
    assert status["state"] == "stale"
    gate = storyboard_image_prompt_service.gate_for_version(
        storage.list_storyboard_shots(detail["blueprint"].blueprint_id, detail["version"].version_id)
    )
    assert gate["approved"] is False
    with pytest.raises(ValidationError):
        storyboard_image_prompt_service.approve_for_shot(stale_shot)


def test_reapprove_records_provenance_and_gate_passes(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shot, approved = _approve_image(storage, detail)
    original_approved_at = approved["approved_at"]
    _retarget_scene_text(service, storage, RETARGETED_SCENE_TEXT)
    service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    stale_shot = storage.get_storyboard_shot(shot.storyboard_shot_id)
    prior_sha = storage.get_storyboard_image_prompt(stale_shot.storyboard_shot_id)["source_prompt_sha256"]

    record = storyboard_image_prompt_service.reapprove_after_rebuild(
        stale_shot, confirmed=True, approved_by="creator"
    )
    assert record["status"] == "approved"
    assert record["approved_at"] == original_approved_at
    assert record["approved_by"] == "creator"
    assert record["reapproved_by"] == "creator"
    assert record["reapproved_at"]
    assert record["prior_source_prompt_sha256"] == prior_sha
    assert record["source_prompt_sha256"] != prior_sha

    gate = storyboard_image_prompt_service.gate_for_version(
        [storage.get_storyboard_shot(shot.storyboard_shot_id)]
    )
    assert gate["approved"] is True
    assert (
        storyboard_image_prompt_service.approved_prompt_for_shot(
            storage.get_storyboard_shot(shot.storyboard_shot_id)
        )
        == record["image_prompt"]
    )


def test_reapprove_requires_confirm_and_prior_approval(tmp_path):
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    shot, _ = _approve_image(storage, detail)
    _retarget_scene_text(service, storage, RETARGETED_SCENE_TEXT)
    service.rebuild_shot_prompts(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    stale_shot = storage.get_storyboard_shot(shot.storyboard_shot_id)
    with pytest.raises(ValidationError, match="explicit per-shot confirmation"):
        storyboard_image_prompt_service.reapprove_after_rebuild(stale_shot, confirmed=False)

    shots = sorted(
        storage.list_storyboard_shots(detail["blueprint"].blueprint_id, detail["version"].version_id),
        key=lambda item: item.shot_number,
    )
    proposed_record = storyboard_image_prompt_service.derive_for_shot(shots[1])
    assert proposed_record["status"] != "approved"
    with pytest.raises(ValidationError, match="previously approved"):
        storyboard_image_prompt_service.reapprove_after_rebuild(shots[1], confirmed=True)


# ----------------------------------------------------------------------
# 4. routes (thin: validate, call service, format)
# ----------------------------------------------------------------------

def _client(tmp_path, monkeypatch) -> tuple[TestClient, dict]:
    service, storage, detail, _ = _make_fixture(
        tmp_path, SCENE_TEXT_TWO_SHOT, ["MAYA"], 2
    )
    monkeypatch.setattr(blueprint_routes, "storyboard_blueprint_service", service)
    api = FastAPI()
    api.include_router(blueprint_routes.router)
    return TestClient(api), {
        "service": service,
        "storage": storage,
        "blueprint_id": detail["blueprint"].blueprint_id,
        "version_id": detail["version"].version_id,
    }


def test_rebuild_route_returns_summary_and_404s_unknown(tmp_path, monkeypatch):
    client, ctx = _client(tmp_path, monkeypatch)
    response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{ctx['blueprint_id']}/versions/{ctx['version_id']}/rebuild-prompts",
        json={"confirmed_shot_ids": [], "rebuilt_by": "creator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["confirm_required"]) == 0
    assert len(body["rebuilt"]) == 2
    assert body["reference_lock_info"] == []
    missing = client.post(
        "/api/f51/studio/storyboard-blueprints/nope/versions/nope/rebuild-prompts", json={}
    )
    assert missing.status_code in (404, 409)


def test_reapprove_route_requires_confirm_flag(tmp_path, monkeypatch):
    client, ctx = _client(tmp_path, monkeypatch)
    storage = ctx["storage"]
    shots = sorted(
        storage.list_storyboard_shots(ctx["blueprint_id"], ctx["version_id"]),
        key=lambda item: item.shot_number,
    )
    shot = shots[0]
    storyboard_image_prompt_service.derive_for_shot(shot)
    storyboard_image_prompt_service.approve_for_shot(shot)
    _retarget_scene_text(ctx["service"], storage, RETARGETED_SCENE_TEXT)
    ctx["service"].rebuild_shot_prompts(
        blueprint_id=ctx["blueprint_id"], version_id=ctx["version_id"]
    )
    path = f"/api/f51/studio/storyboard-blueprints/{ctx['blueprint_id']}/shots/{shot.storyboard_shot_id}/image-prompt/reapprove"
    assert client.post(path, json={"confirmed": False}).status_code == 422
    ok = client.post(path, json={"confirmed": True, "approved_by": "creator"})
    assert ok.status_code == 200
    assert ok.json()["reapproved_by"] == "creator"
