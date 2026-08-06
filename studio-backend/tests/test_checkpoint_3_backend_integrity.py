from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.routes import projects as project_routes
from app.routes import studio_workflow as workflow_routes
from app.services.project_persistence_service import ProjectPersistenceService
from app.services.project_store import ProjectStore
from app.services.stability import PersistenceError, StateError
from app.services.editorial_timeline_context_service import EditorialTimelineContextService
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.studio_workflow_service import StudioWorkflowService


def _workflow_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, DatabaseStorage, ProjectStore]:
    storage = DatabaseStorage(str(tmp_path / "workflow-db"))
    state_store = ProjectStore(str(tmp_path / "workflow-projects.json"))
    state_store.create_project("Project A", project_id="project_a")
    state_store.create_project("Project B", project_id="project_b")
    service = StudioWorkflowService(storage=storage, project_store_service=state_store)
    monkeypatch.setattr(workflow_routes, "studio_workflow_service", service)
    app = FastAPI()
    app.include_router(workflow_routes.router)
    return TestClient(app), storage, state_store


def _project_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, DatabaseStorage, ProjectPersistenceService]:
    storage = DatabaseStorage(str(tmp_path / "project-route-db"))
    state_store = ProjectStore(str(tmp_path / "project-route-state.json"))
    service = ProjectPersistenceService(state_store=state_store, storage=storage)
    monkeypatch.setattr(project_routes, "project_persistence_service", service)
    monkeypatch.setattr(project_routes, "project_store", state_store)
    app = FastAPI()
    app.include_router(project_routes.router)
    return TestClient(app), storage, service


def _create_version(client: TestClient, project_id: str, artifact_id: str) -> str:
    response = client.post(
        f"/api/f51/studio/projects/{project_id}/workflow/versions",
        json={"artifact_type": "scene", "artifact_id": artifact_id},
    )
    assert response.status_code == 200
    return response.json()["version_id"]


def _create_gate(client: TestClient, project_id: str, target_id: str, version_id: str | None = None) -> str:
    payload = {
        "gate_type": "scene_review",
        "target_type": "scene",
        "target_id": target_id,
        "required_role": "producer",
    }
    if version_id:
        payload["version_id"] = version_id
    response = client.post(
        f"/api/f51/studio/projects/{project_id}/workflow/gates",
        json=payload,
    )
    assert response.status_code == 200
    return response.json()["gate_id"]


def test_workflow_rejects_cross_project_and_missing_version_references(tmp_path, monkeypatch):
    client, storage, _ = _workflow_client(tmp_path, monkeypatch)
    project_b_version = _create_version(client, "project_b", "scene_b")

    cross_project_gate = client.post(
        "/api/f51/studio/projects/project_a/workflow/gates",
        json={
            "gate_type": "scene_review",
            "target_type": "scene",
            "target_id": "scene_a",
            "version_id": project_b_version,
        },
    )
    missing_parent = client.post(
        "/api/f51/studio/projects/project_a/workflow/versions",
        json={
            "artifact_type": "scene",
            "artifact_id": "scene_a",
            "source_version_id": "missing_version",
        },
    )
    cross_project_parent = client.post(
        "/api/f51/studio/projects/project_a/workflow/versions",
        json={
            "artifact_type": "scene",
            "artifact_id": "scene_a",
            "source_version_id": project_b_version,
        },
    )

    assert cross_project_gate.status_code == 404
    assert cross_project_gate.json()["detail"]["error_type"] == "validation_error"
    assert missing_parent.status_code == 404
    assert cross_project_parent.status_code == 404
    assert storage.list_studio_artifact_versions("project_a") == []
    assert storage.list_studio_approval_gates("project_a") == []


def test_workflow_rejects_cross_project_and_repeated_gate_decisions(tmp_path, monkeypatch):
    client, storage, _ = _workflow_client(tmp_path, monkeypatch)
    gate_id = _create_gate(client, "project_b", "scene_b")
    decision_payload = {
        "actor_id": "producer_a",
        "actor_role": "producer",
        "decision": "approve",
    }

    cross_project = client.post(
        f"/api/f51/studio/projects/project_a/workflow/gates/{gate_id}/decisions",
        json=decision_payload,
    )
    first = client.post(
        f"/api/f51/studio/projects/project_b/workflow/gates/{gate_id}/decisions",
        json=decision_payload,
    )
    repeated = client.post(
        f"/api/f51/studio/projects/project_b/workflow/gates/{gate_id}/decisions",
        json=decision_payload,
    )

    assert cross_project.status_code == 404
    assert storage.get_studio_approval_gate(gate_id).status.value == "approved"
    assert first.status_code == 200
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["error_type"] == "state_error"
    assert len(storage.list_studio_approval_decisions("project_b", gate_id=gate_id)) == 1
    assert storage.list_studio_approval_decisions("project_a", gate_id=gate_id) == []


def test_workflow_rejects_stale_active_gate_and_cross_project_comment_version(tmp_path, monkeypatch):
    client, _, _ = _workflow_client(tmp_path, monkeypatch)
    version_one = _create_version(client, "project_a", "scene_a")
    _create_gate(client, "project_a", "scene_a", version_one)
    version_two = _create_version(client, "project_a", "scene_a")
    project_b_version = _create_version(client, "project_b", "scene_b")

    stale_gate = client.post(
        "/api/f51/studio/projects/project_a/workflow/gates",
        json={
            "gate_type": "scene_review",
            "target_type": "scene",
            "target_id": "scene_a",
            "version_id": version_two,
        },
    )
    cross_project_comment = client.post(
        "/api/f51/studio/projects/project_a/workflow/comments",
        json={
            "target_type": "scene",
            "target_id": "scene_a",
            "version_id": project_b_version,
            "actor_id": "editor",
            "actor_role": "editor",
            "body": "This note must remain scoped to its own cut.",
        },
    )

    assert stale_gate.status_code == 409
    assert stale_gate.json()["detail"]["error_type"] == "state_error"
    assert cross_project_comment.status_code == 404


def test_workflow_rejects_same_project_version_bound_to_another_artifact(tmp_path, monkeypatch):
    client, storage, _ = _workflow_client(tmp_path, monkeypatch)
    other_scene_version = _create_version(client, "project_a", "scene_other")

    wrong_parent = client.post(
        "/api/f51/studio/projects/project_a/workflow/versions",
        json={
            "artifact_type": "scene",
            "artifact_id": "scene_target",
            "source_version_id": other_scene_version,
        },
    )
    wrong_gate = client.post(
        "/api/f51/studio/projects/project_a/workflow/gates",
        json={
            "gate_type": "scene_review",
            "target_type": "scene",
            "target_id": "scene_target",
            "version_id": other_scene_version,
        },
    )
    wrong_comment = client.post(
        "/api/f51/studio/projects/project_a/workflow/comments",
        json={
            "target_type": "scene",
            "target_id": "scene_target",
            "version_id": other_scene_version,
            "actor_id": "editor",
            "actor_role": "editor",
            "body": "This must not attach to another scene's version.",
        },
    )

    assert wrong_parent.status_code == 422
    assert wrong_gate.status_code == 422
    assert wrong_comment.status_code == 422
    assert storage.list_studio_approval_gates("project_a") == []
    assert storage.list_studio_workflow_comments("project_a") == []
    versions = storage.list_studio_artifact_versions("project_a")
    assert [version.artifact_id for version in versions] == ["scene_other"]


def test_workflow_storage_failure_is_not_reported_as_not_found(tmp_path, monkeypatch):
    class FailingStorage:
        def get_project(self, project_id: str):
            raise OSError("database unavailable")

    state_store = ProjectStore(str(tmp_path / "empty-projects.json"))
    service = StudioWorkflowService(storage=FailingStorage(), project_store_service=state_store)
    monkeypatch.setattr(workflow_routes, "studio_workflow_service", service)
    app = FastAPI()
    app.include_router(workflow_routes.router)

    response = TestClient(app).get("/api/f51/studio/projects/unknown/workflow")

    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "persistence_error"
    assert "database unavailable" not in response.text


def test_project_update_rolls_back_state_when_canonical_write_fails(tmp_path, monkeypatch):
    state_store = ProjectStore(str(tmp_path / "project-state.json"))
    storage = DatabaseStorage(str(tmp_path / "project-db"))
    original = state_store.create_project("Original Title", project_id="project_rollback")
    storage.save_project(StudioProject(**original))
    service = ProjectPersistenceService(state_store=state_store, storage=storage)

    def fail_save(project):
        raise OSError("disk full at a sensitive path")

    monkeypatch.setattr(storage, "save_project", fail_save)

    with pytest.raises(PersistenceError) as raised:
        service.update("project_rollback", {"title": "Title That Must Roll Back"})

    assert raised.value.message == "Canonical project persistence failed"
    assert "sensitive path" not in raised.value.message
    assert state_store.get_project("project_rollback")["title"] == "Original Title"
    assert storage.get_project("project_rollback").title == "Original Title"


def test_project_create_rolls_back_state_when_canonical_write_fails(tmp_path, monkeypatch):
    state_store = ProjectStore(str(tmp_path / "project-state.json"))
    storage = DatabaseStorage(str(tmp_path / "project-db"))
    service = ProjectPersistenceService(state_store=state_store, storage=storage)

    monkeypatch.setattr(storage, "save_project", lambda project: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(PersistenceError):
        service.create(title="Must Not Survive", project_id="project_failed_create")

    assert state_store.get_project("project_failed_create") is None
    assert storage.get_project("project_failed_create") is None


def test_project_state_reloads_from_canonical_storage_after_state_store_loss(tmp_path):
    state_path = tmp_path / "project-state.json"
    storage = DatabaseStorage(str(tmp_path / "project-db"))
    first_store = ProjectStore(str(state_path))
    first_service = ProjectPersistenceService(state_store=first_store, storage=storage)
    first_service.create(title="Reloadable Film", project_id="project_reload")
    first_service.update("project_reload", {"film_cut": {"cut_id": "cut_v2", "scene_order": []}})

    state_path.unlink()
    recreated_service = ProjectPersistenceService(
        state_store=ProjectStore(str(state_path)),
        storage=storage,
    )
    reloaded = recreated_service.load("project_reload")

    assert reloaded is not None
    assert reloaded["title"] == "Reloadable Film"
    assert reloaded["film_cut"]["cut_id"] == "cut_v2"
    assert ProjectStore(str(state_path)).get_project("project_reload") is not None


def test_duplicate_project_creation_is_rejected_without_overwrite(tmp_path):
    state_store = ProjectStore(str(tmp_path / "project-state.json"))
    storage = DatabaseStorage(str(tmp_path / "project-db"))
    service = ProjectPersistenceService(state_store=state_store, storage=storage)
    service.create(title="Original", project_id="project_duplicate")

    with pytest.raises(StateError):
        service.create(title="Replacement", project_id="project_duplicate")

    assert service.load("project_duplicate")["title"] == "Original"
    assert storage.get_project("project_duplicate").title == "Original"


def test_corrupt_project_state_returns_deliberate_storage_error_not_empty_success(tmp_path, monkeypatch):
    state_path = tmp_path / "corrupt-project-state.json"
    state_path.write_text("{not valid json", encoding="utf-8")
    service = ProjectPersistenceService(
        state_store=ProjectStore(str(state_path)),
        storage=DatabaseStorage(str(tmp_path / "project-db")),
    )
    monkeypatch.setattr(project_routes, "project_persistence_service", service)
    app = FastAPI()
    app.include_router(project_routes.router)

    response = TestClient(app).get("/api/f51/studio/projects")

    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "persistence_error"
    assert response.json()["detail"]["stage"] == "project_state_read"
    assert response.json()["detail"]["metadata"]["cause"] == "JSONDecodeError"


def test_project_list_restores_canonical_only_records(tmp_path):
    state_path = tmp_path / "empty-project-state.json"
    state_store = ProjectStore(str(state_path))
    storage = DatabaseStorage(str(tmp_path / "project-db"))
    storage.save_project(StudioProject(project_id="canonical_only", title="Canonical Only"))
    service = ProjectPersistenceService(state_store=state_store, storage=storage)

    listed = service.list()

    assert "canonical_only" in {project["project_id"] for project in listed}
    assert ProjectStore(str(state_path)).get_project("canonical_only")["title"] == "Canonical Only"


def test_project_create_validates_title_and_prevents_duplicate_ids(tmp_path, monkeypatch):
    client, storage, _ = _project_client(tmp_path, monkeypatch)

    missing_title = client.post("/api/f51/studio/projects", json={})
    blank_title = client.post("/api/f51/studio/projects", json={"title": "   "})
    created = client.post(
        "/api/f51/studio/projects",
        json={"title": "Original", "project_id": "project_contract"},
    )
    duplicate = client.post(
        "/api/f51/studio/projects",
        json={"title": "Replacement", "project_id": "project_contract"},
    )

    assert missing_title.status_code == 422
    assert blank_title.status_code == 422
    assert blank_title.json()["detail"]["error_type"] == "validation_error"
    assert created.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error_type"] == "state_error"
    assert storage.get_project("project_contract").title == "Original"


def test_scene_review_and_film_cut_reject_cross_project_scene_ids(tmp_path, monkeypatch):
    client, storage, service = _project_client(tmp_path, monkeypatch)
    service.create(title="Scoped Film", project_id="project_scoped")
    service.update(
        "project_scoped",
        {
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_owned", "heading": "INT. ROOM - NIGHT"},
                ]
            }
        },
    )

    bad_review = client.put(
        "/api/f51/studio/projects/project_scoped/scene-review",
        json={
            "approved_scenes": ["scene_other_project"],
            "reviewed_scenes": ["scene_other_project"],
            "scene_review_status": {"scene_other_project": "approved"},
        },
    )
    bad_cut = client.put(
        "/api/f51/studio/projects/project_scoped/film-cut",
        json={
            "film_cut": {
                "cut_id": "cut_cross_project",
                "scene_order": ["scene_other_project"],
                "included_scenes": ["scene_other_project"],
                "excluded_scenes": [],
            }
        },
    )

    assert bad_review.status_code == 422
    assert bad_review.json()["detail"]["metadata"]["scene_ids"] == ["scene_other_project"]
    assert bad_cut.status_code == 422
    assert bad_cut.json()["detail"]["metadata"]["scene_ids"] == ["scene_other_project"]
    persisted = storage.get_project("project_scoped")
    assert persisted.approved_scenes == []
    assert persisted.film_cut["included_scenes"] == []


def test_film_cut_rejects_conflicting_and_duplicate_scene_membership(tmp_path, monkeypatch):
    client, _, service = _project_client(tmp_path, monkeypatch)
    service.create(title="Cut Contract", project_id="project_cut")
    service.update(
        "project_cut",
        {"execution_summary": {"scenes": [{"scene_id": "scene_001"}]}},
    )

    conflict = client.put(
        "/api/f51/studio/projects/project_cut/film-cut",
        json={
            "film_cut": {
                "cut_id": "cut_conflict",
                "scene_order": ["scene_001"],
                "included_scenes": ["scene_001"],
                "excluded_scenes": ["scene_001"],
            }
        },
    )
    duplicate = client.put(
        "/api/f51/studio/projects/project_cut/film-cut",
        json={
            "film_cut": {
                "cut_id": "cut_duplicate",
                "scene_order": ["scene_001", "scene_001"],
                "included_scenes": ["scene_001"],
                "excluded_scenes": [],
            }
        },
    )

    assert conflict.status_code == 422
    assert conflict.json()["detail"]["error_type"] == "validation_error"
    assert duplicate.status_code == 422


def test_storyboard_storage_failure_is_not_disguised_as_missing_scene(tmp_path):
    class FailingStoryboardStorage:
        def get_storyboard_blueprint(self, project_id: str, scene_id: str):
            return None

        def get_project(self, project_id: str):
            raise OSError("storage unavailable")

    state_store = ProjectStore(str(tmp_path / "storyboard-projects.json"))
    state_store.create_project("Storyboard Film", project_id="project_storyboard")
    service = StoryboardBlueprintService(storage=FailingStoryboardStorage())
    service.project_store = state_store

    with pytest.raises(PersistenceError) as raised:
        service.get_or_create_blueprint(project_id="project_storyboard", scene_id="scene_missing")

    assert raised.value.error_type == "persistence_error"
    assert raised.value.stage == "storyboard_blueprint"


def test_editorial_optional_evidence_storage_failure_is_not_empty_success(tmp_path):
    class FailingEditorialStorage:
        def list_jobs(self, project_id: str, limit: int):
            return []

        def list_scene_compositions_for_project(self, project_id: str):
            return []

        def list_final_short_film_packages_for_project(self, project_id: str):
            return []

        def list_video_assets_for_project(self, project_id: str):
            raise OSError("storage unavailable")

    state_store = ProjectStore(str(tmp_path / "editorial-projects.json"))
    state_store.create_project("Editorial Film", project_id="project_editorial")
    service = EditorialTimelineContextService(
        storage=FailingEditorialStorage(),
        project_store_service=state_store,
    )

    with pytest.raises(PersistenceError) as raised:
        service.build_context("project_editorial")

    assert raised.value.error_type == "persistence_error"
    assert raised.value.metadata["source"] == "list_video_assets_for_project"


def test_atomic_approval_transition_rolls_back_all_records_on_mid_write_failure(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "workflow-transaction-db"))
    state_store = ProjectStore(str(tmp_path / "workflow-transaction-projects.json"))
    state_store.create_project("Transactional Film", project_id="project_transaction")
    service = StudioWorkflowService(storage=storage, project_store_service=state_store)
    version = service.create_artifact_version(
        "project_transaction",
        workflow_routes.StudioArtifactVersionCreate(
            artifact_type="scene",
            artifact_id="scene_001",
        ),
    )
    gate = service.create_approval_gate(
        "project_transaction",
        workflow_routes.StudioApprovalGateCreate(
            gate_type="scene_review",
            target_type="scene",
            target_id="scene_001",
            version_id=version.version_id,
        ),
    )
    gate.status = type(gate.status).APPROVED
    version.status = type(version.status).APPROVED
    decision = {
        "decision_id": "decision_rollback",
        "project_id": "project_transaction",
        "gate_id": gate.gate_id,
        "version_id": version.version_id,
        "actor_id": "producer",
        "actor_role": "producer",
        "decision": "approve",
        "evidence": [],
    }
    invalid_task = {
        "workflow_task_id": "task_invalid",
        "project_id": "project_transaction",
        "task_type": "revision",
    }

    with pytest.raises(KeyError):
        storage.commit_studio_approval_transition(
            decision=decision,
            gate=gate,
            version=version,
            task=invalid_task,
        )

    assert storage.list_studio_approval_decisions("project_transaction", gate_id=gate.gate_id) == []
    assert storage.get_studio_approval_gate(gate.gate_id).status.value == "ready"
    assert storage.get_studio_artifact_version(version.version_id).status.value == "draft"
