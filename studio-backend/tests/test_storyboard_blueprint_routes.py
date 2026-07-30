from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from main import app
from app.services.project_store import project_store
from app.services.render import render_service
from app.services.storyboard_blueprint_service import storyboard_blueprint_service


def test_storyboard_blueprint_route_create_approve_and_render_contract() -> None:
    client = TestClient(app)
    project_id = f"project_route_{uuid4().hex[:8]}"
    scene_id = "scene_001"

    create_response = client.post(
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint",
        json={"shot_count": 2, "regeneration_reason": "route_test"},
    )
    assert create_response.status_code == 200, create_response.text
    detail = create_response.json()
    assert detail["blueprint"]["project_id"] == project_id
    assert detail["version"]["version_number"] == 1
    assert len(detail["shots"]) == 2

    blueprint_id = detail["blueprint"]["blueprint_id"]
    version_id = detail["version"]["version_id"]
    storyboard_shot_id = detail["shots"][0]["storyboard_shot_id"]

    contract_response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render-contract"
    )
    assert contract_response.status_code == 200, contract_response.text
    contract = contract_response.json()
    assert contract["provider_neutral_prompt"]
    assert contract["render_readiness"] == "ready"

    draft_render_response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render",
        json={"provider": "simulated", "submit": False},
    )
    assert draft_render_response.status_code == 422, draft_render_response.text
    assert "Approve storyboard version" in draft_render_response.text
    assert render_service.list_jobs(project_id=project_id) == []
    assert (
        storyboard_blueprint_service.storage.list_storyboard_render_links(
            project_id=project_id,
            shot_id=detail["shots"][0]["shot_id"],
        )
        == []
    )

    approve_response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/approve",
        json={"approved_by": "creator"},
    )
    assert approve_response.status_code == 200, approve_response.text
    approved = approve_response.json()
    assert approved["blueprint"]["approved_version_id"] == version_id
    assert all(shot["status"] == "approved" for shot in approved["shots"])

    list_response = client.get(f"/api/f51/studio/projects/{project_id}/storyboard-blueprints")
    assert list_response.status_code == 200, list_response.text
    summaries = list_response.json()
    assert summaries[0]["scene_id"] == scene_id
    assert summaries[0]["status"] == "approved"

    render_response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render",
        json={"provider": "simulated", "submit": False},
    )
    assert render_response.status_code == 200, render_response.text
    job = render_response.json()
    storyboard_meta = job["input_payload"]["parameters"]["storyboard"]
    assert storyboard_meta["blueprint_id"] == blueprint_id
    assert storyboard_meta["version_id"] == version_id
    links = storyboard_blueprint_service.storage.list_storyboard_render_links(
        project_id=project_id,
        render_job_id=job["id"],
    )
    assert links
    assert links[0]["version_id"] == version_id


def test_storyboard_render_rejects_stale_approved_version() -> None:
    client = TestClient(app)
    project_id = f"project_stale_{uuid4().hex[:8]}"
    scene_id = "scene_001"

    create_response = client.post(
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint",
        json={"shot_count": 1, "regeneration_reason": "stale_version_test"},
    )
    assert create_response.status_code == 200, create_response.text
    detail = create_response.json()
    blueprint_id = detail["blueprint"]["blueprint_id"]
    version_id = detail["version"]["version_id"]
    storyboard_shot_id = detail["shots"][0]["storyboard_shot_id"]

    approve_response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/approve",
        json={"approved_by": "creator"},
    )
    assert approve_response.status_code == 200, approve_response.text

    blueprint = storyboard_blueprint_service.storage.get_storyboard_blueprint_by_id(blueprint_id)
    assert blueprint is not None
    blueprint.current_version_id = "sbv_newer_current_version"
    storyboard_blueprint_service.storage.save_storyboard_blueprint(blueprint)

    stale_render_response = client.post(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render",
        json={"provider": "simulated", "submit": False},
    )
    assert stale_render_response.status_code == 409, stale_render_response.text
    assert "stale storyboard version" in stale_render_response.text


def test_storyboard_blueprint_route_update_lock_and_backfill() -> None:
    client = TestClient(app)
    project_id = f"project_backfill_{uuid4().hex[:8]}"
    project_store.save_project(
        {
            "project_id": project_id,
            "title": "Storyboard Backfill",
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene_001", "heading": "INT. ROOM - NIGHT", "description": "A quiet choice."},
                    {"scene_id": "scene_002", "heading": "EXT. STREET - DAWN", "description": "The consequence arrives."},
                ]
            },
        }
    )

    backfill_response = client.post(
        f"/api/f51/studio/projects/{project_id}/storyboard-blueprints/backfill",
        json={"shot_count": 1},
    )
    assert backfill_response.status_code == 200, backfill_response.text
    backfill = backfill_response.json()
    assert backfill["scene_count"] == 2
    assert len(backfill["created"]) == 2

    detail_response = client.get(
        f"/api/f51/studio/projects/{project_id}/scenes/scene_001/storyboard-blueprint"
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    blueprint_id = detail["blueprint"]["blueprint_id"]
    shot_id = detail["shots"][0]["storyboard_shot_id"]

    update_response = client.patch(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{shot_id}",
        json={
            "visual_plan": {"framing": "close profile"},
            "change_reason": "route_storyboard_refinement",
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["visual_plan"]["framing"] == "close profile"

    lock_response = client.patch(
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{shot_id}/lock",
        json={"locked": True},
    )
    assert lock_response.status_code == 200, lock_response.text
    assert lock_response.json()["locked"] is True
