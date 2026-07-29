from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobOutput
from app.services import render as render_module
from app.services.render import RenderService


def _storage(tmp_path: Path) -> DatabaseStorage:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return DatabaseStorage(str(db_dir))


def test_create_job_does_not_attach_project_wide_reference_assets(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    storage.save_reference_asset(
        {
            "ref_id": "full-dre",
            "project_id": "proj-ref",
            "kind": "character_full",
            "image_url": "https://cdn.example.com/dre-full.png",
        }
    )
    storage.save_reference_asset(
        {
            "ref_id": "face-dre",
            "project_id": "proj-ref",
            "kind": "character_face",
            "image_url": "https://cdn.example.com/dre-face.png",
        }
    )

    job = RenderService().create_job(
        project_id="proj-ref",
        shot_id="scene_003_shot_002",
        provider="simulated",
        prompt="A cinematic medium shot with enough detail to avoid generic prompt replacement.",
    )

    assert job.input_payload.consistency_payload is None


def test_create_job_without_reference_assets_has_no_consistency_payload(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)

    job = RenderService().create_job(
        project_id="proj-empty",
        shot_id="scene_003_shot_002",
        provider="simulated",
        prompt="A cinematic medium shot with enough detail to avoid generic prompt replacement.",
        reference_assets=["https://legacy.example.com/ref.png"],
    )

    assert job.input_payload.consistency_payload is None
    assert job.input_payload.referenceAssets == ["https://legacy.example.com/ref.png"]


def test_first_shot_with_storyboard_gets_provisional_reference_and_routes_to_r2v(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    character = storage.save_character(
        "proj-storyboard-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )
    storage.save_previs_image(
        project_id="proj-storyboard-lock",
        scene_id="scene_001",
        shot_id="scene_001_shot_001",
        image_path="/previs-assets/proj-storyboard-lock/maya-storyboard.png",
        job_id="storyboard_scene_001_shot_001_dashscope",
        status="complete",
        prompt_used="Maya storyboard prompt",
        fallback=False,
    )

    def fake_project(project_id):
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        fake_project,
    )
    monkeypatch.setattr(render_module.project_store, "get_project", fake_project)

    job = RenderService().create_job(
        project_id="proj-storyboard-lock",
        shot_id="scene_001_shot_001",
        provider="happyhorse",
        prompt="Maya turns toward the hallway window.",
    )

    assert job.provider == "happyhorse-r2v"
    provisional = storage.get_character_reference_lock(
        "proj-storyboard-lock",
        character["id"],
        "provisional",
    )
    assert provisional is not None
    assert provisional["image_url"] == "/previs-assets/proj-storyboard-lock/maya-storyboard.png"
    assert job.input_payload.consistency_payload is not None
    assert job.input_payload.consistency_payload.refs[0].image_url == provisional["image_url"]


def test_create_job_attaches_provider_aware_canonical_identity_context(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    character = storage.save_character(
        "proj-canonical-context",
        "Maya",
        {
            "identity_core_json": """
            {
              "facial_identity": "heart-shaped face",
              "body_and_silhouette": "compact frame",
              "skin_tone": "warm brown",
              "hair_style": "tight coils",
              "hair_length": "chin length",
              "hair_color": "black",
              "age_presentation": "late thirties"
            }
            """,
            "default_appearance_json": """
            {
              "wardrobe": ["charcoal work jacket"],
              "accessories": ["thin silver chain"],
              "persistent_props": ["brass lighter"],
              "emotional_state": "contained grief"
            }
            """,
        },
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-canonical-context",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "source_job_id": "job-approved-maya",
            "image_url": "/outputs/references/proj-canonical-context/maya.jpg",
            "lock_status": "locked",
            "source_status": "approved",
            "review_status": "approved",
            "reliability": "high",
        }
    )

    def fake_project(project_id):
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        fake_project,
    )
    monkeypatch.setattr(render_module.project_store, "get_project", fake_project)

    job = RenderService().create_job(
        project_id="proj-canonical-context",
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        prompt="Maya walks into the room, holding herself very still.",
    )

    context = job.input_payload.parameters["character_identity_context"]
    assert context["constraint_injection"]["strategy"] == "reference_images_and_text"
    assert "heart-shaped face" in context["identity_lines"][0]
    assert "charcoal work jacket" in context["identity_lines"][0]
    assert context["reference_images"][character["id"]][0]["source_job_id"] == "job-approved-maya"
    assert job.metadata["zero_touch_pipeline"]["character_identity_context"] == context
    assert job.metadata["character_identity_warnings"] == []


def test_first_shot_without_storyboard_stays_t2v_until_post_render_lock(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    storage.save_character(
        "proj-no-storyboard",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )

    def fake_project(project_id):
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        fake_project,
    )
    monkeypatch.setattr(render_module.project_store, "get_project", fake_project)

    job = RenderService().create_job(
        project_id="proj-no-storyboard",
        shot_id="scene_001_shot_001",
        provider="happyhorse",
        prompt="Maya turns toward the hallway window.",
    )

    assert job.provider == "happyhorse"
    assert job.input_payload.consistency_payload is None


@pytest.mark.asyncio
async def test_first_completed_character_shot_locks_reference_and_second_routes_to_r2v(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    character = storage.save_character(
        "proj-char-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )

    def fake_project(project_id):
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"]},
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        fake_project,
    )
    monkeypatch.setattr(render_module.project_store, "get_project", fake_project)

    async def no_op_review(job):
        return None

    monkeypatch.setattr(render_module, "_run_continuity_review", no_op_review)
    monkeypatch.setattr(render_module, "_run_render_quality_check", no_op_review)

    class ImmediateCompleteAdapter:
        async def submit_job(self, job):
            job.provider_job_id = f"fake-{job.id}"
            job.status = "complete"
            job.progress = 100
            job.output_payload = RenderJobOutput(
                asset_url="https://cdn.example.test/shot-one.mp4",
                thumbnail_url="https://cdn.example.test/maya-locked.jpg",
                metadata={"fake": True},
            )
            return job

    monkeypatch.setattr(render_module, "get_adapter", lambda provider, config: ImmediateCompleteAdapter())

    service = RenderService()
    first = service.create_job(
        project_id="proj-char-lock",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="Maya turns toward the window in a quiet medium shot.",
    )
    submitted = await service.submit_job(first.id)

    assert submitted.status == "complete"
    lock = storage.get_character_reference_lock("proj-char-lock", character["id"])
    assert lock is not None
    assert lock["source_shot_id"] == "scene_001_shot_001"
    assert lock["image_url"] == "https://cdn.example.test/maya-locked.jpg"

    second = service.create_job(
        project_id="proj-char-lock",
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        prompt="Maya steps into the hallway, same costume and tired eyes.",
    )

    assert second.provider == "happyhorse-r2v"
    assert second.input_payload.consistency_payload is not None
    refs = second.input_payload.consistency_payload.refs
    assert len(refs) == 1
    assert refs[0].image_url == "https://cdn.example.test/maya-locked.jpg"
    assert refs[0].source_shot_id == "scene_001_shot_001"
