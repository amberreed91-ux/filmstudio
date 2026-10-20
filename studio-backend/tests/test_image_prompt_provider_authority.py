"""Provider-bound text comes ONLY from the approved image prompt.

Regression lock for the stale-prompt fix: the generation manifest
("Prompt (sent verbatim)"), the frozen contract, the Router wire body, the
board-shot render path, and the take-box prefill must all read the approved,
hash-linked image prompt — never the board's provider_neutral_prompt.

All fixtures are hermetic temp DBs. No provider is called, no live DB is
touched (the storyboard singleton's storage is rebound and restored).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.storyboard_blueprint import StoryboardBlueprintStatus, StoryboardShotStatus
from app.services.runway_prompt_length import utf16_length
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.stability import StateError
from app.services.storyboard_blueprint_service import (
    StoryboardBlueprintService,
    storyboard_blueprint_service as storyboard_singleton,
)
from app.services.storyboard_image_prompt_service import storyboard_image_prompt_service

PROJECT_ID = "authority-film"
SCENE_ID = "scene_001"

SCENE_TEXT = """INT. OFFICE - DAY
DRE
You heard that too, right?
Dre listens before answering. Maya holds the look by the doorway."""

# Hand-written Maya image prompts, deliberately distinct from whatever the
# board builder mints for the canonical text.
IMAGE_TEXTS = {
    1: "Wide shot of Maya by the office doorway, daylight. A lean Black woman in her late 20s, still and watching.",
    2: "Medium shot, Maya listens before answering, daylight through blinds. Same woman, same doorway.",
    3: "Close-up of Maya's eyes, quiet and searching, office daylight soft behind her.",
}


def _fixture(tmp_path: Path, shot_count: int = 3):
    storage = DatabaseStorage(str(tmp_path / "db"))
    project = StudioProject(
        project_id=PROJECT_ID,
        title="Authority",
        script_text=SCENE_TEXT,
        execution_summary={
            "scenes": [{"scene_id": SCENE_ID, "description": "Office.", "text": SCENE_TEXT}],
        },
    )
    storage.save_project(project)
    service = StoryboardBlueprintService(storage=storage)
    detail = service.get_or_create_blueprint(
        project_id=PROJECT_ID, scene_id=SCENE_ID, shot_count=shot_count
    )
    storyboard_image_prompt_service.set_storage(storage)
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    for shot in shots:
        storyboard_image_prompt_service.edit_for_shot(
            shot, image_prompt=IMAGE_TEXTS[shot.shot_number], edited_by="creator"
        )
        storyboard_image_prompt_service.approve_for_shot(shot, approved_by="creator")
    # Approve the board without the continuity-review ceremony (unit bypass,
    # same pattern as test_prompt_rebuild._approve_manually).
    version = storage.get_storyboard_blueprint_version(detail["version"].version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = "2026-10-20T00:00:00+00:00"
    version.approved_by = "test-creator"
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.approved_version_id = version.version_id
    storage.save_storyboard_blueprint(blueprint)
    for shot in shots:
        shot.status = StoryboardShotStatus.APPROVED
        storage.save_storyboard_shot(shot)
    storyboard_image_prompt_service.set_storage(storage)
    return storage, detail


@pytest.fixture()
def bound_singleton(tmp_path, monkeypatch):
    """Bind the storyboard singleton + global storage lookup to a temp DB."""
    storage, detail = _fixture(tmp_path)
    previous = storyboard_singleton.storage
    storyboard_singleton.storage = storage
    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: storage)
    try:
        yield storage, detail
    finally:
        storyboard_singleton.storage = previous


def _project() -> dict:
    return {
        "project_id": PROJECT_ID,
        "script_text": SCENE_TEXT,
        "execution_summary": {
            "scenes": [{"scene_id": SCENE_ID, "description": "Office.", "text": SCENE_TEXT}],
        },
    }


def _prepare(tmp_path: Path, **kwargs):
    pipeline = SceneProductionPipelineService(backend_root=tmp_path)
    return pipeline.prepare_scene_batch(
        project_id=kwargs.pop("project_id", PROJECT_ID),
        scene_id=kwargs.pop("scene_id", SCENE_ID),
        project=kwargs.pop("project", _project()),
        provider=kwargs.pop("provider", "simulated"),
        **kwargs,
    )


def _board_texts(storage, detail) -> dict[str, str]:
    return {
        shot.shot_id: str(shot.render_contract.provider_neutral_prompt or "")
        for shot in storage.list_storyboard_shots(
            detail["blueprint"].blueprint_id, detail["version"].version_id
        )
    }


def _shot_number(shot_id: str) -> int:
    return int(shot_id.rsplit("_shot_", 1)[1])


# ----------------------------------------------------------------------
# 1. Manifest text equals the approved image prompt
# ----------------------------------------------------------------------


def test_manifest_text_equals_approved_image_prompt(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    board_texts = _board_texts(storage, detail)
    batch = _prepare(tmp_path)
    assert batch["source_kind"] == "storyboard"
    rows = {row["shot_id"]: row for row in batch["manifest"]["shots"]}
    assert set(rows) == set(board_texts)
    for shot_id, row in rows.items():
        assert row["shot_prompt"] == IMAGE_TEXTS[_shot_number(shot_id)]
        assert IMAGE_TEXTS[_shot_number(shot_id)] != board_texts[shot_id]


def test_entry_prompt_equals_approved_image_prompt(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    board_texts = _board_texts(storage, detail)
    batch = _prepare(tmp_path)
    for entry in batch["entries"]:
        assert entry["prompt"] == IMAGE_TEXTS[_shot_number(entry["shot_id"])]
        assert entry["prompt"] != board_texts[entry["shot_id"]]
        assert entry["image_prompt_ready"] is True


# ----------------------------------------------------------------------
# 2. A changed image prompt changes the shot version hash
# ----------------------------------------------------------------------


def test_changed_image_prompt_changes_shot_version_hash(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    before = _prepare(tmp_path)
    before_versions = {e["shot_id"]: e["shot_version"] for e in before["entries"]}
    before_fingerprint = before["manifest"]["manifest_fingerprint"]
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    first = next(s for s in shots if s.shot_number == 1)
    storyboard_image_prompt_service.edit_for_shot(
        first, image_prompt=IMAGE_TEXTS[1] + " She does not blink.", edited_by="creator"
    )
    storyboard_image_prompt_service.approve_for_shot(first, approved_by="creator")
    after = _prepare(tmp_path)
    after_versions = {e["shot_id"]: e["shot_version"] for e in after["entries"]}
    assert after_versions["scene_001_shot_001"] != before_versions["scene_001_shot_001"]
    # Untouched shots keep their version.
    assert after_versions["scene_001_shot_002"] == before_versions["scene_001_shot_002"]
    assert after["manifest"]["manifest_fingerprint"] != before_fingerprint
    assert after["entries"][0]["prompt"] != before["entries"][0]["prompt"]


# ----------------------------------------------------------------------
# 3. Missing / unapproved / stale / over-limit block without fallback
# ----------------------------------------------------------------------


def _blocked_entry(batch, shot_id: str) -> dict:
    return next(e for e in batch["entries"] if e["shot_id"] == shot_id)


def test_unapproved_image_prompt_blocks_with_clear_message(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    second = next(s for s in shots if s.shot_number == 2)
    # Back to proposal: save without approving.
    storyboard_image_prompt_service.edit_for_shot(
        second, image_prompt=IMAGE_TEXTS[2], edited_by="creator"
    )
    batch = _prepare(tmp_path)
    assert batch["ready"] is False
    blocked = _blocked_entry(batch, "scene_001_shot_002")
    assert blocked["prompt"] == ""
    assert blocked["image_prompt_ready"] is False
    assert blocked["generation_contract"] is None
    assert any("proposal" in b and "approv" in b for b in blocked["blockers"]), blocked["blockers"]
    row = next(r for r in batch["manifest"]["shots"] if r["shot_id"] == "scene_001_shot_002")
    assert row["shot_prompt"] == ""


def test_stale_image_prompt_blocks_and_names_reapproval(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    third = next(s for s in shots if s.shot_number == 3)
    third.render_contract.provider_neutral_prompt = (
        str(third.render_contract.provider_neutral_prompt or "") + " An added beat."
    )
    storage.save_storyboard_shot(third)
    batch = _prepare(tmp_path)
    assert batch["ready"] is False
    blocked = _blocked_entry(batch, "scene_001_shot_003")
    assert blocked["prompt"] == ""
    assert blocked["generation_contract"] is None
    assert any("stale" in b for b in blocked["blockers"]), blocked["blockers"]
    assert any("re-approve" in b or "Re-derive" in b for b in blocked["blockers"])


def test_over_limit_image_prompt_blocks_before_freeze(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    first = next(s for s in shots if s.shot_number == 1)
    record = storage.get_storyboard_image_prompt(first.storyboard_shot_id)
    assert record is not None
    long_text = "y" * 1001
    storage.save_storyboard_image_prompt(
        {**record, "image_prompt": long_text, "utf16_length": utf16_length(long_text)}
    )
    batch = _prepare(tmp_path)
    blocked = _blocked_entry(batch, "scene_001_shot_001")
    assert blocked["prompt"] == ""
    assert blocked["generation_contract"] is None
    assert any("1000" in b or "limit" in b for b in blocked["blockers"]), blocked["blockers"]


def test_unresolvable_board_shot_blocks_with_clear_message(tmp_path, bound_singleton):
    pipeline = SceneProductionPipelineService(backend_root=tmp_path)
    text, sha, error = pipeline._resolve_storyboard_send_prompt(
        shot_id="scene_001_shot_009", storyboard_shot_id="sbs_ghost", current_shot=None
    )
    assert text == "" and sha == ""
    assert "cannot be resolved" in error and "re-approve" in error


# ----------------------------------------------------------------------
# 4. The length gate covers the sent text
# ----------------------------------------------------------------------


def test_sent_text_is_within_runway_image_limit(tmp_path, bound_singleton):
    batch = _prepare(tmp_path)
    for entry in batch["entries"]:
        assert utf16_length(entry["prompt"]) <= 1000, entry["shot_id"]
    for row in batch["manifest"]["shots"]:
        assert utf16_length(row["shot_prompt"]) <= 1000, row["shot_id"]


# ----------------------------------------------------------------------
# 5. Guard: no provider-bound text is built from the board prompt field
# ----------------------------------------------------------------------


def test_board_text_appears_nowhere_provider_bound(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    board_texts = _board_texts(storage, detail)
    batch = _prepare(tmp_path)
    manifest_json = json.dumps(batch["manifest"], sort_keys=True)
    for shot_id, board_text in board_texts.items():
        assert board_text, "fixture must have board text to contrast against"
        assert board_text not in manifest_json, shot_id
    for entry in batch["entries"]:
        assert board_texts[entry["shot_id"]] != entry["prompt"]
        contract = entry.get("generation_contract")
        if contract:
            assert board_texts[entry["shot_id"]] not in json.dumps(contract)
    # The Router wire body is built from the frozen values only.
    from app.services.providers.runway_router_provider import build_runway_router_video_request

    for entry in batch["entries"]:
        body = build_runway_router_video_request(
            entry["prompt"], config_id="test-router", dry_run=True
        )
        assert body["input"]["promptText"] == entry["prompt"]
        assert board_texts[entry["shot_id"]] not in body["input"]["promptText"]


def test_render_storyboard_shot_sends_approved_prompt_for_runway(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    first = next(s for s in shots if s.shot_number == 1)
    captured: dict = {}

    class _Jobs:
        def create_job(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="job-test")

    service = StoryboardBlueprintService(storage=storage)
    job = service.render_storyboard_shot(
        blueprint_id=detail["blueprint"].blueprint_id,
        storyboard_shot_id=first.storyboard_shot_id,
        provider="runway",
        render_service=_Jobs(),
    )
    assert job.id == "job-test"
    assert captured["prompt"] == IMAGE_TEXTS[1]


def test_render_storyboard_shot_fails_closed_without_approval(tmp_path, bound_singleton):
    storage, detail = bound_singleton
    shots = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id
    )
    second = next(s for s in shots if s.shot_number == 2)
    storyboard_image_prompt_service.edit_for_shot(
        second, image_prompt=IMAGE_TEXTS[2], edited_by="creator"
    )

    called: list = []

    class _Jobs:
        def create_job(self, **kwargs):
            called.append(kwargs)
            raise AssertionError("no job may exist without an approved prompt")

    service = StoryboardBlueprintService(storage=storage)
    with pytest.raises(StateError):
        service.render_storyboard_shot(
            blueprint_id=detail["blueprint"].blueprint_id,
            storyboard_shot_id=second.storyboard_shot_id,
            provider="runway_router",
            render_service=_Jobs(),
        )
    assert called == []
