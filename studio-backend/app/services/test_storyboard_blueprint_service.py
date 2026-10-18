from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.stability import StateError


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def test_create_approve_and_render_storyboard_blueprint(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    storage.save_project(
        StudioProject(
            project_id="project-test",
            title="Storyboard Test",
            execution_summary={"scenes": [{"scene_id": "scene_001", "description": "A held look."}]},
        )
    )
    service = StoryboardBlueprintService(storage)

    detail = service.get_or_create_blueprint(
        project_id="project-test",
        scene_id="scene_001",
        shot_count=2,
    )

    blueprint = detail["blueprint"]
    version = detail["version"]
    shots = detail["shots"]

    assert blueprint.current_version_id == version.version_id
    assert len(shots) == 2
    assert shots[0].render_contract.render_readiness == "ready"
    assert shots[0].render_contract.provider_neutral_prompt

    review = service.run_continuity_review(
        blueprint_id=blueprint.blueprint_id,
        version_id=version.version_id,
        reviewer="continuity_test",
    )
    assert review["status"] == "completed"

    # D4: image prompts must be human-approved before board approval.
    service.derive_and_approve_image_prompts_for_version(version_id=version.version_id)
    approved = service.approve_version(
        blueprint_id=blueprint.blueprint_id,
        version_id=version.version_id,
        approved_by="creator",
    )
    assert approved["blueprint"].approved_version_id == version.version_id
    assert all(shot.status == "approved" for shot in approved["shots"])
    approved_version = storage.get_storyboard_blueprint_version(version.version_id)
    assert approved_version.metadata["production_approval"] == {
        "actor_id": "creator",
        "actor_authenticated": False,
    }

    authenticated_approval = service.approve_version(
        blueprint_id=blueprint.blueprint_id,
        version_id=version.version_id,
        approved_by="owner-1",
        approval_actor_authenticated=True,
    )
    assert authenticated_approval["version"].metadata["production_approval"] == {
        "actor_id": "owner-1",
        "actor_authenticated": True,
    }


    class MockRenderService:
        def __init__(self) -> None:
            self.jobs = {}

        def create_job(self, project_id, shot_id, provider=None, prompt="", reference_assets=None, parameters=None):
            job = type(
                "MockJob",
                (),
                {
                    "id": "job-storyboard-1",
                    "project_id": project_id,
                    "shot_id": shot_id,
                    "provider": provider or "simulated",
                    "input_payload": type(
                        "MockInput",
                        (),
                        {
                            "prompt": prompt,
                            "referenceAssets": reference_assets or [],
                            "parameters": parameters or {},
                        },
                    )(),
                },
            )()
            self.jobs[job.id] = job
            return job

    render = MockRenderService()
    job = service.render_storyboard_shot(
        blueprint_id=blueprint.blueprint_id,
        storyboard_shot_id=shots[0].storyboard_shot_id,
        render_service=render,
    )

    assert job.id == "job-storyboard-1"
    assert job.input_payload.parameters["storyboard"]["blueprint_id"] == blueprint.blueprint_id
    links = storage.list_storyboard_render_links(
        project_id="project-test",
        render_job_id=job.id,
    )
    assert len(links) == 1
    assert links[0]["version_id"] == version.version_id

    revision_link = service.link_revision_from_job(
        project_id="project-test",
        revision_id="revision-storyboard-1",
        original_job=job,
        change_scope={"visual_plan": ["framing"]},
    )
    assert revision_link is not None
    assert revision_link.original_version_id == version.version_id
    stored_revision_links = storage.list_storyboard_revision_links(project_id="project-test")
    assert stored_revision_links[0]["revision_id"] == "revision-storyboard-1"

    memory = storage.get_scene_memory("project-test", "scene_001") or {}
    assert memory["approved_shots"][0]["version_id"] == version.version_id


def test_update_and_lock_storyboard_shot_preserves_editable_contract(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    storage.save_project(
        StudioProject(
            project_id="project-edit",
            title="Storyboard Edit",
            execution_summary={"scenes": [{"scene_id": "scene_001", "description": "A quiet reset."}]},
        )
    )
    service = StoryboardBlueprintService(storage)

    detail = service.get_or_create_blueprint(
        project_id="project-edit",
        scene_id="scene_001",
        shot_count=1,
    )
    blueprint = detail["blueprint"]
    shot = detail["shots"][0]

    updated = service.update_shot(
        blueprint_id=blueprint.blueprint_id,
        storyboard_shot_id=shot.storyboard_shot_id,
        visual_plan={"framing": "tight profile"},
        change_reason="tighten_scene_subjectivity",
    )
    assert updated.visual_plan.framing == "tight profile"
    assert updated.metadata["last_change_reason"] == "tighten_scene_subjectivity"

    locked = service.lock_shot(
        blueprint_id=blueprint.blueprint_id,
        storyboard_shot_id=shot.storyboard_shot_id,
        locked=True,
    )
    assert locked.locked is True
    assert locked.status.value == "locked"

    try:
        service.update_shot(
            blueprint_id=blueprint.blueprint_id,
            storyboard_shot_id=shot.storyboard_shot_id,
            visual_plan={"framing": "wide reset"},
        )
    except StateError as exc:
        assert "locked" in exc.message.lower()
    else:
        raise AssertionError("locked storyboard shot should reject updates")


def test_storyboard_prompt_includes_project_character_identity_without_cross_project_leak(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    service = StoryboardBlueprintService(storage)
    storage.save_character(
        "reborn-project",
        "MAYA",
        {
            "age": "Late 20s",
            "visual_prompt_summary": "A lean Black woman with deep brown skin and natural locs.",
        },
    )
    storage.save_character(
        "other-project",
        "ELI",
        {
            "age": "67",
            "visual_prompt_summary": "A fisherman from a different story.",
        },
    )

    class ProjectStore:
        def get_project(self, project_id: str) -> dict:
            return {
                "project_id": project_id,
                "execution_summary": {
                    "scenes": [
                        {
                            "scene_id": "scene_001",
                            "heading": "EXT. DOWNTOWN CHICAGO - GOLDEN HOUR",
                            "text": "Maya walks through the city watching small moments people take for granted.",
                            "location": "Downtown Chicago",
                            "time_of_day": "golden hour",
                            "emotional_tone": "haunted clarity",
                            "characters": ["MAYA"],
                        }
                    ]
                },
            }

    service.project_store = ProjectStore()

    detail = service.get_or_create_blueprint(
        project_id="reborn-project",
        scene_id="scene_001",
        shot_count=1,
    )

    prompt = detail["shots"][0].render_contract.provider_neutral_prompt
    assert "Black woman" in prompt
    assert "deep brown skin" in prompt
    assert "ELI" not in prompt
    assert "fisherman" not in prompt


def _seed_approved_then_draft_board(tmp_path: Path):
    storage = _make_storage(tmp_path)
    storage.save_project(
        StudioProject(
            project_id="project-version-select",
            title="Version Selection",
            execution_summary={"scenes": [{"scene_id": "scene_001", "description": "A held look."}]},
        )
    )
    service = StoryboardBlueprintService(storage)
    created = service.get_or_create_blueprint(
        project_id="project-version-select",
        scene_id="scene_001",
        shot_count=2,
    )
    review = service.run_continuity_review(
        blueprint_id=created["blueprint"].blueprint_id,
        version_id=created["version"].version_id,
        reviewer="version_select_test",
    )
    assert review["status"] == "completed"
    service.derive_and_approve_image_prompts_for_version(version_id=created["version"].version_id)
    approved = service.approve_version(
        blueprint_id=created["blueprint"].blueprint_id,
        version_id=created["version"].version_id,
        approved_by="creator",
    )
    draft = service.create_version(blueprint_id=created["blueprint"].blueprint_id)
    return storage, service, approved["version"], draft["version"]


def test_get_blueprint_detail_defaults_to_current_draft(tmp_path: Path) -> None:
    _, service, approved_version, draft_version = _seed_approved_then_draft_board(tmp_path)
    assert draft_version.version_id != approved_version.version_id
    detail = service.get_blueprint_detail(project_id="project-version-select", scene_id="scene_001")
    assert detail["version"].version_id == draft_version.version_id
    assert detail["blueprint"].current_version_id == draft_version.version_id
    assert {shot.version_id for shot in detail["shots"]} == {draft_version.version_id}


def test_get_blueprint_detail_approved_selection_resolves_approved(tmp_path: Path) -> None:
    _, service, approved_version, draft_version = _seed_approved_then_draft_board(tmp_path)
    detail = service.get_blueprint_detail(
        project_id="project-version-select", scene_id="scene_001", version_selection="approved"
    )
    assert detail["version"].version_id == approved_version.version_id
    assert detail["version"].version_id != draft_version.version_id
    assert {shot.version_id for shot in detail["shots"]} == {approved_version.version_id}


def test_get_blueprint_detail_approved_selection_fails_closed_without_approval(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    storage.save_project(
        StudioProject(
            project_id="project-no-approval",
            title="No Approval",
            execution_summary={"scenes": [{"scene_id": "scene_001", "description": "A held look."}]},
        )
    )
    service = StoryboardBlueprintService(storage)
    service.get_or_create_blueprint(project_id="project-no-approval", scene_id="scene_001", shot_count=1)
    try:
        service.get_blueprint_detail(
            project_id="project-no-approval", scene_id="scene_001", version_selection="approved"
        )
        assert False, "Approved selection without an approved version must fail closed"
    except StateError as exc:
        assert "No approved storyboard version" in str(exc)


def test_get_blueprint_detail_rejects_unknown_selection(tmp_path: Path) -> None:
    _, service, _, _ = _seed_approved_then_draft_board(tmp_path)
    try:
        service.get_blueprint_detail(
            project_id="project-version-select", scene_id="scene_001", version_selection="newest"
        )
        assert False, "Unknown version selection must fail closed, never silently substitute"
    except StateError as exc:
        assert "Unknown version selection" in str(exc)
