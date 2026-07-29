from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.studio_workflow import router, studio_workflow_service
from app.services.project_store import ProjectStore


def _client(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "db"))
    project_store = ProjectStore(str(tmp_path / "project_state_store.json"))
    project_store.create_project("Route Project", project_id="project_routes")
    studio_workflow_service.set_storage(storage)
    studio_workflow_service._project_store_service = project_store
    studio_workflow_service._queue_service = None
    studio_workflow_service._decision_gate_service = None
    studio_workflow_service._acceptance_service = None
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), storage, project_store


def test_workflow_summary_initializes_project(tmp_path):
    client, storage, _ = _client(tmp_path)

    response = client.get("/api/f51/studio/projects/project_routes/workflow")

    assert response.status_code == 200
    body = response.json()
    assert body["project_state"]["project_id"] == "project_routes"
    assert body["project_state"]["workflow_status"] == "active"
    assert storage.get_studio_workflow_project_state("project_routes") is not None


def test_route_creates_version_gate_and_records_approval(tmp_path):
    client, _, project_store = _client(tmp_path)
    version_response = client.post(
        "/api/f51/studio/projects/project_routes/workflow/versions",
        json={
            "artifact_type": "scene",
            "artifact_id": "scene_001",
            "title": "Scene 1",
            "created_by": "owner",
        },
    )
    assert version_response.status_code == 200
    version_id = version_response.json()["version_id"]

    gate_response = client.post(
        "/api/f51/studio/projects/project_routes/workflow/gates",
        json={
            "gate_type": "scene_review",
            "target_type": "scene",
            "target_id": "scene_001",
            "version_id": version_id,
            "required_role": "producer",
            "opened_by": "owner",
        },
    )
    assert gate_response.status_code == 200
    gate_id = gate_response.json()["gate_id"]

    decision_response = client.post(
        f"/api/f51/studio/projects/project_routes/workflow/gates/{gate_id}/decisions",
        json={
            "actor_id": "owner",
            "actor_role": "owner",
            "decision": "approve",
            "rationale": "The cut earns its stillness.",
        },
    )

    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "approve"
    assert project_store.get_project("project_routes")["scene_review_status"]["scene_001"] == "approved"


def test_route_rejects_unauthorized_decision(tmp_path):
    client, _, _ = _client(tmp_path)
    version_id = client.post(
        "/api/f51/studio/projects/project_routes/workflow/versions",
        json={"artifact_type": "scene", "artifact_id": "scene_001"},
    ).json()["version_id"]
    gate_id = client.post(
        "/api/f51/studio/projects/project_routes/workflow/gates",
        json={
            "gate_type": "scene_review",
            "target_type": "scene",
            "target_id": "scene_001",
            "version_id": version_id,
            "required_role": "producer",
        },
    ).json()["gate_id"]

    response = client.post(
        f"/api/f51/studio/projects/project_routes/workflow/gates/{gate_id}/decisions",
        json={"actor_id": "reviewer", "actor_role": "reviewer", "decision": "approve"},
    )

    assert response.status_code == 403


def test_route_returns_404_for_missing_project(tmp_path):
    client, _, _ = _client(tmp_path)

    response = client.get("/api/f51/studio/projects/missing_project/workflow")

    assert response.status_code == 404


def test_route_posts_and_resolves_scoped_comment(tmp_path):
    client, _, _ = _client(tmp_path)

    comment_response = client.post(
        "/api/f51/studio/projects/project_routes/workflow/comments",
        json={
            "target_type": "scene",
            "target_id": "scene_001",
            "actor_id": "editor",
            "actor_role": "editor",
            "body": "Trim the entry by a breath, not a beat.",
        },
    )

    assert comment_response.status_code == 200
    comment_id = comment_response.json()["comment_id"]
    resolve_response = client.post(
        f"/api/f51/studio/projects/project_routes/workflow/comments/{comment_id}/resolve",
        json={"actor_id": "producer"},
    )

    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "resolved"


def test_route_updates_workflow_phase(tmp_path):
    client, _, _ = _client(tmp_path)

    response = client.put(
        "/api/f51/studio/projects/project_routes/workflow/phase",
        json={"actor_id": "producer", "phase": "screening", "workflow_status": "waiting_creator"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == "screening"
    assert body["workflow_status"] == "waiting_creator"
