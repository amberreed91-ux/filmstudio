"""Tests for look-scoped reference locks and automatic reference upgrade.

A6: the lock key was (project, character, role), so a character with a costume
change had one canonical reference fighting every shot in the other look.

Automatic upgrade: a lock made from a mediocre frame stayed permanent, and
because a weak reference makes later shots more likely to fail, nothing ever
promoted a better one.
"""

from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.character_visual_reference_service import CharacterVisualReferenceService


def _storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "db"))


def _lock(project_id: str, character_id: str, **overrides) -> dict:
    payload = {
        "project_id": project_id,
        "character_id": character_id,
        "character_name": "Maya",
        "source_shot_id": "scene_001_shot_001",
        "image_url": "/outputs/references/p/a.jpg",
        "lock_status": "locked",
        "reference_role": "general",
        "look_id": "default",
        "capture_method": "representative_frame",
        "frame_score": 5.0,
    }
    payload.update(overrides)
    return payload


def _job(*, project_id="proj-look", shot_id="scene_002_shot_001") -> RenderJobModel:
    return RenderJobModel(
        id="job-look-1",
        project_id=project_id,
        shot_id=shot_id,
        provider="happyhorse",
        status="complete",
        input_payload=RenderJobInput(shot_id=shot_id, prompt="Maya turns."),
        output_payload=RenderJobOutput(asset_url="/outputs/renders/p/job.mp4", metadata={}),
        created_at="2026-08-16T00:00:00",
        updated_at="2026-08-16T00:00:00",
        completed_at="2026-08-16T00:00:00",
    )


# ── look resolution ──────────────────────────────────────────────────────────


def test_no_appearance_override_resolves_to_the_default_look(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    look = CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="proj-look",
        character_id=character["id"],
        shot_id="scene_001_shot_001",
        storage=storage,
    )
    assert look == "default"


def test_appearance_override_produces_a_distinct_look(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_staging(
        {
            "character_id": character["id"],
            "scene_id": "scene_008",
            "shot_id": None,
            "staging_prompt": "Maya at the door",
            "appearance_override": "soaked through, hair plastered down",
        }
    )
    look = CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="proj-look",
        character_id=character["id"],
        shot_id="scene_008_shot_001",
        storage=storage,
    )
    assert look != "default"
    assert look.startswith("look_")


def test_the_same_override_always_resolves_to_the_same_look(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    for scene in ("scene_008", "scene_009"):
        storage.save_character_staging(
            {
                "character_id": character["id"],
                "scene_id": scene,
                "shot_id": None,
                "staging_prompt": "Maya",
                # Same wardrobe note, differently spaced and cased.
                "appearance_override": "Soaked   through, hair plastered down"
                if scene == "scene_009"
                else "soaked through, hair plastered down",
            }
        )
    first = CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="proj-look", character_id=character["id"],
        shot_id="scene_008_shot_001", storage=storage,
    )
    second = CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="proj-look", character_id=character["id"],
        shot_id="scene_009_shot_001", storage=storage,
    )
    assert first == second


def test_different_overrides_resolve_to_different_looks(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_staging({
        "character_id": character["id"], "scene_id": "scene_008", "shot_id": None,
        "staging_prompt": "Maya", "appearance_override": "soaked through",
    })
    storage.save_character_staging({
        "character_id": character["id"], "scene_id": "scene_012", "shot_id": None,
        "staging_prompt": "Maya", "appearance_override": "bandaged forearm, torn sleeve",
    })
    rain = CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="proj-look", character_id=character["id"],
        shot_id="scene_008_shot_001", storage=storage,
    )
    injury = CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="proj-look", character_id=character["id"],
        shot_id="scene_012_shot_001", storage=storage,
    )
    assert rain != injury


def test_storage_without_staging_support_degrades_to_default():
    class Bare:
        pass

    assert CharacterVisualReferenceService.resolve_look_id_for_shot(
        project_id="p", character_id="c", shot_id="scene_001_shot_001", storage=Bare()
    ) == "default"


# ── look-scoped locks ────────────────────────────────────────────────────────


def test_two_looks_can_each_hold_a_canonical_reference(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-look", character["id"], look_id="default", image_url="/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-look", character["id"], look_id="look_rain", image_url="/b.jpg")
    )

    default_lock = storage.get_character_reference_lock(
        "proj-look", character["id"], "locked", "general", "default"
    )
    rain_lock = storage.get_character_reference_lock(
        "proj-look", character["id"], "locked", "general", "look_rain"
    )
    assert default_lock["image_url"] == "/a.jpg"
    assert rain_lock["image_url"] == "/b.jpg"


def test_a_look_with_no_reference_falls_back_to_the_default_look(tmp_path):
    """A character's first shot in a new costume still gets face and build."""
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-look", character["id"], look_id="default", image_url="/a.jpg")
    )

    rows = CharacterVisualReferenceService().get_reference_locks_for_character(
        storage, "proj-look", character["id"], "look_rain"
    )
    assert [row["image_url"] for row in rows] == ["/a.jpg"]


def test_relock_is_scoped_to_one_look(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-look", character["id"], look_id="default", image_url="/a.jpg")
    )
    storage.save_character_reference_lock(
        _lock("proj-look", character["id"], look_id="look_rain", image_url="/b.jpg")
    )

    CharacterVisualReferenceService().relock_character_reference(
        project_id="proj-look",
        character_id=character["id"],
        image_url="/b2.jpg",
        storage=storage,
        look_id="look_rain",
    )

    untouched = storage.get_character_reference_lock(
        "proj-look", character["id"], "locked", "general", "default"
    )
    assert untouched["image_url"] == "/a.jpg"


# ── automatic upgrade ────────────────────────────────────────────────────────


def _identity(status: str, character_id: str) -> dict:
    return {
        "status": status,
        "measures_identity": True,
        "characters": [
            {"character_id": character_id, "character_name": "Maya", "status": "consistent"}
        ],
    }


def _capture(monkeypatch, score: float):
    monkeypatch.setattr(
        CharacterVisualReferenceService,
        "capture_reference_images",
        lambda self, job, count=None: [("/outputs/references/p/better.jpg", "representative_frame", "general", score)],
    )


def test_a_materially_cleaner_frame_replaces_the_lock(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-look", character["id"], frame_score=5.0))
    _capture(monkeypatch, 20.0)

    upgraded = CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=_job(), storage=storage, identity_report=_identity("consistent", character["id"])
    )

    assert len(upgraded) == 1
    active = storage.get_character_reference_lock(
        "proj-look", character["id"], "locked", "general", "default"
    )
    assert active["image_url"] == "/outputs/references/p/better.jpg"


def test_a_marginally_better_frame_does_not_churn_the_lock(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-look", character["id"], frame_score=5.0))
    _capture(monkeypatch, 5.5)  # below FRAME_UPGRADE_RATIO

    assert CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=_job(), storage=storage, identity_report=_identity("consistent", character["id"])
    ) == []


def test_a_drifted_render_never_upgrades(tmp_path, monkeypatch):
    """A shot that drifted is not evidence of a better likeness."""
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-look", character["id"], frame_score=5.0))
    _capture(monkeypatch, 50.0)

    assert CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=_job(), storage=storage, identity_report=_identity("identity_drift", character["id"])
    ) == []


def test_unmeasured_identity_never_upgrades(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-look", character["id"], frame_score=5.0))
    _capture(monkeypatch, 50.0)

    assert CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=_job(), storage=storage, identity_report={"status": "unavailable"}
    ) == []


def test_automation_never_overwrites_a_director_override(tmp_path, monkeypatch):
    """A human's explicit choice outranks any frame score."""
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(
        _lock(
            "proj-look",
            character["id"],
            capture_method="director_override",
            image_url="/chosen-by-hand.jpg",
            frame_score=1.0,
        )
    )
    _capture(monkeypatch, 99.0)

    CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=_job(), storage=storage, identity_report=_identity("consistent", character["id"])
    )

    active = storage.get_character_reference_lock(
        "proj-look", character["id"], "locked", "general", "default"
    )
    assert active["image_url"] == "/chosen-by-hand.jpg"


def test_a_director_can_still_override_their_own_choice(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(
        _lock("proj-look", character["id"], capture_method="director_override", image_url="/first.jpg")
    )

    CharacterVisualReferenceService().relock_character_reference(
        project_id="proj-look",
        character_id=character["id"],
        image_url="/second.jpg",
        storage=storage,
        capture_method="director_override",
    )

    active = storage.get_character_reference_lock(
        "proj-look", character["id"], "locked", "general", "default"
    )
    assert active["image_url"] == "/second.jpg"


def test_an_incomplete_render_never_upgrades(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-look", character["id"], frame_score=5.0))
    _capture(monkeypatch, 99.0)
    job = _job()
    job.status = "running"

    assert CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=job, storage=storage, identity_report=_identity("consistent", character["id"])
    ) == []


def test_an_unscored_capture_never_upgrades(tmp_path, monkeypatch):
    """A thumbnail says nothing about quality relative to what is locked."""
    storage = _storage(tmp_path)
    character = storage.save_character("proj-look", "Maya", {})
    storage.save_character_reference_lock(_lock("proj-look", character["id"], frame_score=5.0))
    monkeypatch.setattr(
        CharacterVisualReferenceService,
        "capture_reference_images",
        lambda self, job, count=None: [("https://cdn.example.test/t.jpg", "thumbnail", "general", 0.0)],
    )

    assert CharacterVisualReferenceService().upgrade_references_from_verified_job(
        job=_job(), storage=storage, identity_report=_identity("consistent", character["id"])
    ) == []
