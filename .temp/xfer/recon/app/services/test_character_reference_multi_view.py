"""Tier 2 tests: multi-view reference sets, re-lock, and prominence weighting.

Before this, a character was represented by exactly one locked image, chosen by
the first passing render and never replaceable, and every reference in a shot
pulled with identical weight regardless of who the shot was about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.character_visual_reference_service import CharacterVisualReferenceService


def _storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "db"))


def _lock(project_id: str, character_id: str, role: str, image_url: str, **overrides) -> dict:
    payload = {
        "project_id": project_id,
        "character_id": character_id,
        "character_name": "Maya",
        "source_shot_id": "scene_001_shot_001",
        "image_url": image_url,
        "lock_status": "locked",
        "reference_role": role,
        "provider": "happyhorse",
        "capture_method": "representative_frame",
    }
    payload.update(overrides)
    return payload


def _job(project_id: str = "proj-multi") -> RenderJobModel:
    return RenderJobModel(
        id="job-multi-1",
        project_id=project_id,
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        status="complete",
        input_payload=RenderJobInput(shot_id="scene_001_shot_002", prompt="Maya turns."),
        output_payload=RenderJobOutput(
            asset_url="/outputs/renders/proj-multi/job.mp4",
            thumbnail_url="https://cdn.example.test/thumb.jpg",
            metadata={},
        ),
        created_at="2026-08-15T00:00:00",
        updated_at="2026-08-15T00:00:00",
        completed_at="2026-08-15T00:00:00",
    )


# ── schema: one locked reference per role, not per character ─────────────────


def test_multiple_roles_can_be_locked_for_one_character(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})

    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "/outputs/references/proj-multi/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "alternate_angle", "/outputs/references/proj-multi/b.jpg")
    )

    rows = storage.list_character_reference_locks_for_character("proj-multi", character["id"])
    assert {row["reference_role"] for row in rows} == {"general", "alternate_angle"}


def test_role_filter_targets_a_specific_lock(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "/outputs/references/proj-multi/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "alternate_angle", "/outputs/references/proj-multi/b.jpg")
    )

    found = storage.get_character_reference_lock(
        "proj-multi", character["id"], "locked", "alternate_angle"
    )
    assert found["image_url"] == "/outputs/references/proj-multi/b.jpg"


def test_multi_view_locks_stay_project_isolated(tmp_path):
    storage = _storage(tmp_path)
    here = storage.save_character("proj-a", "Maya", {})
    there = storage.save_character("proj-b", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-a", here["id"], "general", "/outputs/references/proj-a/a.jpg"))
    storage.save_character_reference_lock(_lock("proj-b", there["id"], "general", "/outputs/references/proj-b/b.jpg"))

    rows = storage.list_character_reference_locks_for_character("proj-a", here["id"])
    assert [row["image_url"] for row in rows] == ["/outputs/references/proj-a/a.jpg"]


# ── payload assembly ─────────────────────────────────────────────────────────


def _project_with_scene(monkeypatch, characters=("Maya",)):
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [{"scene_id": "scene_001", "characters": list(characters)}]
            },
        },
    )


def test_payload_sends_every_locked_view_for_a_character(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    _project_with_scene(monkeypatch)
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "https://cdn.example.test/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "alternate_angle", "https://cdn.example.test/b.jpg")
    )

    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="proj-multi",
        shot_id="scene_001_shot_002",
        storage=storage,
        prompt="Maya walks into frame.",
    )

    assert payload is not None
    # One image per character was the old behaviour; r2v accepts up to nine.
    assert len(payload.refs) == 2
    assert {ref.ref_id for ref in payload.refs} == {
        f"charlock:{character['id']}:general",
        f"charlock:{character['id']}:alternate_angle",
    }


def test_primary_view_outweighs_the_alternate_angle(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    _project_with_scene(monkeypatch)
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "https://cdn.example.test/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "alternate_angle", "https://cdn.example.test/b.jpg")
    )

    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="proj-multi",
        shot_id="scene_001_shot_002",
        storage=storage,
        prompt="Maya walks into frame.",
    )

    primary = payload.weights[f"charlock:{character['id']}:general"]
    alternate = payload.weights[f"charlock:{character['id']}:alternate_angle"]
    assert primary > alternate


def test_references_never_exceed_the_provider_limit(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    names = [f"Char{index}" for index in range(6)]
    _project_with_scene(monkeypatch, characters=names)
    for name in names:
        character = storage.save_character("proj-multi", name, {})
        for role in ("general", "alternate_angle", "wardrobe"):
            storage.save_character_reference_lock(
                _lock(
                    "proj-multi",
                    character["id"],
                    role,
                    f"https://cdn.example.test/{name}-{role}.jpg",
                    character_name=name,
                )
            )

    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="proj-multi",
        shot_id="scene_001_shot_002",
        storage=storage,
        prompt=" ".join(names),
    )

    assert payload is not None
    assert len(payload.refs) <= CharacterVisualReferenceService.MAX_PROVIDER_REFERENCES


# ── prominence weighting ─────────────────────────────────────────────────────


def test_subject_outweighs_background_character():
    characters = [
        {"id": "c-dre", "name": "DRE"},
        {"id": "c-maya", "name": "MAYA"},
    ]
    # MAYA is named first in the prompt, so she is the subject regardless of the
    # order the cast happened to resolve in.
    weights = CharacterVisualReferenceService.prominence_by_character(
        characters, "MAYA holds still while DRE waits in the doorway."
    )
    assert weights["c-maya"] > weights["c-dre"]


def test_characters_absent_from_the_prompt_rank_last():
    characters = [
        {"id": "c-extra", "name": "SIMONE"},
        {"id": "c-maya", "name": "MAYA"},
    ]
    weights = CharacterVisualReferenceService.prominence_by_character(
        characters, "MAYA holds still."
    )
    assert weights["c-maya"] > weights["c-extra"]


def test_third_and_later_characters_share_background_weight():
    characters = [
        {"id": "a", "name": "A"},
        {"id": "b", "name": "B"},
        {"id": "c", "name": "C"},
        {"id": "d", "name": "D"},
    ]
    weights = CharacterVisualReferenceService.prominence_by_character(characters, "A B C D")
    assert weights["a"] == CharacterVisualReferenceService.SUBJECT_PROMINENCE
    assert weights["b"] == CharacterVisualReferenceService.SECONDARY_PROMINENCE
    assert weights["c"] == weights["d"] == CharacterVisualReferenceService.BACKGROUND_PROMINENCE


def test_prominence_handles_an_empty_prompt():
    characters = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
    weights = CharacterVisualReferenceService.prominence_by_character(characters, "")
    # Falls back to resolved order rather than crashing or flattening.
    assert weights["a"] > weights["b"]


# ── re-lock / override ───────────────────────────────────────────────────────


def test_relock_replaces_the_locked_reference_and_supersedes_the_old_one(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "https://cdn.example.test/bad.jpg")
    )

    new_lock = CharacterVisualReferenceService().relock_character_reference(
        project_id="proj-multi",
        character_id=character["id"],
        image_url="https://cdn.example.test/good.jpg",
        storage=storage,
        reason="Director picked a cleaner frame",
    )

    assert new_lock is not None
    assert new_lock.image_url == "https://cdn.example.test/good.jpg"
    active = storage.get_character_reference_lock("proj-multi", character["id"], "locked", "general")
    assert active["image_url"] == "https://cdn.example.test/good.jpg"
    superseded = storage.list_character_reference_locks(
        "proj-multi", [character["id"]], "superseded"
    )
    assert [row["image_url"] for row in superseded] == ["https://cdn.example.test/bad.jpg"]


def test_relock_to_the_same_image_is_a_no_op(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "https://cdn.example.test/same.jpg")
    )

    CharacterVisualReferenceService().relock_character_reference(
        project_id="proj-multi",
        character_id=character["id"],
        image_url="https://cdn.example.test/same.jpg",
        storage=storage,
    )

    assert storage.list_character_reference_locks("proj-multi", [character["id"]], "superseded") == []


def test_relock_only_affects_the_named_role(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "general", "https://cdn.example.test/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-multi", character["id"], "alternate_angle", "https://cdn.example.test/b.jpg")
    )

    CharacterVisualReferenceService().relock_character_reference(
        project_id="proj-multi",
        character_id=character["id"],
        image_url="https://cdn.example.test/a2.jpg",
        storage=storage,
        reference_role="general",
    )

    untouched = storage.get_character_reference_lock(
        "proj-multi", character["id"], "locked", "alternate_angle"
    )
    assert untouched["image_url"] == "https://cdn.example.test/b.jpg"


def test_relock_rejects_an_empty_image(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-multi", "Maya", {})
    assert (
        CharacterVisualReferenceService().relock_character_reference(
            project_id="proj-multi",
            character_id=character["id"],
            image_url="   ",
            storage=storage,
        )
        is None
    )


# ── capture ──────────────────────────────────────────────────────────────────


def test_capture_collapses_to_one_view_without_a_local_video():
    captures = CharacterVisualReferenceService().capture_reference_images(_job(), count=3)
    # The fourth element is the capture quality score; a thumbnail is unscored.
    assert captures == [("https://cdn.example.test/thumb.jpg", "thumbnail", "general", 0.0)]


def test_capture_labels_additional_views_as_alternate_angles(monkeypatch, tmp_path):
    video = tmp_path / "job.mp4"
    video.write_bytes(b"stub")

    monkeypatch.setattr(
        CharacterVisualReferenceService, "_local_output_path", staticmethod(lambda url: video)
    )
    monkeypatch.setattr(
        CharacterVisualReferenceService,
        "_extract_reference_frames",
        classmethod(lambda cls, job, path, count=1: [("/outputs/references/p/a.jpg", 9.0), ("/outputs/references/p/b.jpg", 7.0)]),
    )

    captures = CharacterVisualReferenceService().capture_reference_images(_job(), count=3)
    assert [role for _, _, role, _score in captures] == ["general", "alternate_angle"]
    # Scores travel with the captures so an upgrade can be recognised later.
    assert [score for _, _, _, score in captures] == [9.0, 7.0]


def test_role_for_rank_is_honest_about_what_it_knows():
    # Without a face detector these frames cannot be called face/full_body.
    assert CharacterVisualReferenceService._role_for_rank(0) == "general"
    assert CharacterVisualReferenceService._role_for_rank(1) == "alternate_angle"
    assert CharacterVisualReferenceService._role_for_rank(5) == "alternate_angle"
