from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.character_visual_reference_service import CharacterVisualReferenceService


def _storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "db"))


def _completed_job(project_id: str = "proj-lock") -> RenderJobModel:
    return RenderJobModel(
        id="job-lock-1",
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="simulated",
        status="complete",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="Maya turns toward the window.",
        ),
        output_payload=RenderJobOutput(
            asset_url="/outputs/renders/proj-lock/job.mp4",
            thumbnail_url="https://cdn.example.test/maya-thumb.jpg",
            metadata={},
        ),
        created_at="2026-07-23T00:00:00",
        updated_at="2026-07-23T00:00:00",
        completed_at="2026-07-23T00:00:00",
    )


def test_storage_character_reference_lock_project_and_character_isolation(tmp_path):
    storage = _storage(tmp_path)
    maya = storage.save_character(
        "proj-a",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    other = storage.save_character(
        "proj-b",
        "Maya",
        {"visual_prompt_summary": "different project character"},
    )

    saved = storage.save_character_reference_lock(
        {
            "project_id": "proj-a",
            "character_id": maya["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "image_url": "https://cdn.example.test/maya.jpg",
            "provider": "simulated",
            "capture_method": "thumbnail",
        }
    )

    assert saved["lock_status"] == "locked"
    assert storage.get_character_reference_lock("proj-a", maya["id"])["image_url"] == "https://cdn.example.test/maya.jpg"
    assert storage.get_character_reference_lock("proj-a", other["id"]) is None
    assert storage.list_character_reference_locks("proj-b") == []


def test_service_locks_first_completed_shot_once(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        },
    )

    service = CharacterVisualReferenceService()
    first = service.lock_first_references_for_completed_job(
        job=_completed_job(),
        storage=storage,
    )
    second = service.lock_first_references_for_completed_job(
        job=_completed_job(),
        storage=storage,
    )

    assert len(first) == 1
    assert first[0].character_id == character["id"]
    assert first[0].image_url == "https://cdn.example.test/maya-thumb.jpg"
    assert first[0].capture_method == "thumbnail"
    assert second == []


def test_service_creates_provisional_lock_from_exact_storyboard_shot(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    storage.save_previs_image(
        project_id="proj-lock",
        scene_id="scene_001",
        shot_id="scene_001_shot_001",
        image_path="/previs-assets/proj-lock/maya-storyboard.png",
        job_id="storyboard_scene_001_shot_001_dashscope",
        status="complete",
        prompt_used="Maya storyboard prompt",
        fallback=False,
    )
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        },
    )

    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="proj-lock",
        shot_id="scene_001_shot_001",
        storage=storage,
        prompt="Maya turns toward the window.",
    )

    provisional = storage.get_character_reference_lock("proj-lock", character["id"], "provisional")
    assert provisional is not None
    assert provisional["image_url"] == "/previs-assets/proj-lock/maya-storyboard.png"
    assert provisional["capture_method"] == "storyboard"
    assert payload is not None
    assert payload.refs[0].image_url == "/previs-assets/proj-lock/maya-storyboard.png"
    assert "provisional storyboard reference" in payload.fallback_text[payload.refs[0].ref_id]


def test_service_promotes_provisional_to_locked_after_passing_render(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-lock",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "image_url": "/previs-assets/proj-lock/maya-storyboard.png",
            "provider": "qwen-image-max",
            "capture_method": "storyboard",
            "lock_status": "provisional",
        }
    )
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        },
    )
    job = _completed_job()
    job.metadata = {"adherence_review": {"verdict": "pass", "failed_slots": []}}

    promoted = CharacterVisualReferenceService().lock_first_references_for_completed_job(
        job=job,
        storage=storage,
    )

    assert len(promoted) == 1
    locked = storage.get_character_reference_lock("proj-lock", character["id"], "locked")
    assert locked is not None
    assert locked["image_url"] == "https://cdn.example.test/maya-thumb.jpg"
    assert locked["capture_method"] == "thumbnail"
    assert storage.get_character_reference_lock("proj-lock", character["id"], "provisional") is None
    superseded = storage.list_character_reference_locks("proj-lock", [character["id"]], "superseded")
    assert len(superseded) == 1
    assert superseded[0]["image_url"] == "/previs-assets/proj-lock/maya-storyboard.png"


def test_service_retains_provisional_after_failed_quality_review(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-lock",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "image_url": "/previs-assets/proj-lock/maya-storyboard.png",
            "provider": "qwen-image-max",
            "capture_method": "storyboard",
            "lock_status": "provisional",
        }
    )
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        },
    )
    job = _completed_job()
    job.metadata = {
        "adherence_review": {
            "verdict": "fail",
            "failed_slots": ["character_state"],
        }
    }

    promoted = CharacterVisualReferenceService().lock_first_references_for_completed_job(
        job=job,
        storage=storage,
    )

    assert promoted == []
    assert storage.get_character_reference_lock("proj-lock", character["id"], "locked") is None
    provisional = storage.get_character_reference_lock("proj-lock", character["id"], "provisional")
    assert provisional is not None
    assert provisional["image_url"] == "/previs-assets/proj-lock/maya-storyboard.png"


def test_service_builds_character_scoped_consistency_payload(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-lock",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "image_url": "https://cdn.example.test/maya.jpg",
            "provider": "simulated",
            "capture_method": "thumbnail",
        }
    )
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        },
    )

    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="proj-lock",
        shot_id="scene_001_shot_002",
        storage=storage,
        prompt="Maya walks into frame.",
    )

    assert payload is not None
    assert payload.project_id == "proj-lock"
    assert len(payload.refs) == 1
    assert payload.refs[0].ref_id == f"charlock:{character['id']}"
    assert payload.refs[0].image_url == "https://cdn.example.test/maya.jpg"
    assert "Maya" in payload.fallback_text[payload.refs[0].ref_id]
