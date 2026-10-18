from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobOutput
from app.services import render as render_module
from app.services.render import RenderService
from app.services.stability import ValidationError


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
async def test_first_character_shot_without_approved_reference_fails_closed_before_provider(tmp_path, monkeypatch):
    """Retired first-shot-bootstrap premise (B9 product decision).

    Production submission requires an approved canonical character reference
    in addition to valid setting context and an approved canonical
    environment anchor; a provisional character lock never satisfies the
    submit-time gate and no first-shot exception exists. This test pins that
    fail-closed boundary: with setting context valid but no approved
    character reference, submit is rejected with
    canonical_character_reference_missing before the provider boundary, so
    the job fails, no lock is created, and the provider is never invoked.

    Narrower behaviors remain covered elsewhere: the no-reference-set
    bootstrap by test_reference_validation.py's
    test_bootstrap_without_reference_set_remains_allowed_for_existing_post_render_lock_flow,
    provisional first-shot routing by
    test_first_shot_with_storyboard_gets_provisional_reference_and_routes_to_r2v,
    and post-render lock creation by the character_visual_reference service
    tests. The end-to-end submit-to-lock-to-R2V path under full approvals
    has no isolated-storage test: the setting-coverage gate additionally
    requires continuity-resolved environment context that only full
    production topology provides.
    """
    storage = _storage(tmp_path)
    monkeypatch.setattr(render_module, "_storage", storage)
    character = storage.save_character(
        "proj-char-lock",
        "Maya",
        {"visual_prompt_summary": "short dark hair, blue jacket"},
    )

    # Submit-time reference validation is fail-closed: the scene resolves a
    # canonical setting entity plus an approved environment anchor, so the
    # submission reaches the character gate — which must reject it because
    # Maya has no approved canonical character reference. Seed that exact
    # context in the test's isolated storage.
    _setting_id = "proj-char-lock-setting"

    def fake_project(project_id):
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "characters": ["Maya"], "setting_id": _setting_id},
                ]
            },
        }

    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        fake_project,
    )
    monkeypatch.setattr(render_module.project_store, "get_project", fake_project)
    storage.save_universe_node({
        "node_id": _setting_id,
        "project_id": "proj-char-lock",
        "node_type": "location",
        "name": "Character lock setting",
        "first_scene": "scene_001",
        "last_scene": "scene_001",
    })
    storage.save_reference_asset({
        "ref_id": "proj-char-lock-setting-anchor",
        "project_id": "proj-char-lock",
        "target_type": "setting",
        "target_id": _setting_id,
        "kind": "environment",
        "image_url": "https://cdn.example.test/proj-char-lock-setting.png",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })

    async def no_op_review(job):
        return None

    monkeypatch.setattr(render_module, "_run_continuity_review", no_op_review)
    monkeypatch.setattr(render_module, "_run_render_quality_check", no_op_review)

    calls = []

    class ImmediateCompleteAdapter:
        async def submit_job(self, job):
            calls.append(job.id)
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
    with pytest.raises(ValidationError, match="no approved canonical reference"):
        await service.submit_job(first.id)

    assert calls == []
    assert service.get_job(first.id).status == "failed"
    assert storage.get_character_reference_lock("proj-char-lock", character["id"]) is None
