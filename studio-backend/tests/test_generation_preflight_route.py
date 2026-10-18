"""Read-only generation preflight route — Generation Preflight UI workstream.

The endpoint exposes the backend's EXISTING pre-flight
(SceneProductionPipelineService.prepare_scene_batch) over HTTP. These tests
verify the safety contract the UI depends on:

- the verdict, per-shot blockers, cost estimate, and shot manifest all come
  from the backend's own gates (no second evaluator);
- the endpoint never creates a render job (no provider request, no credits);
- the endpoint never mutates canonical creative state;
- unknown project/scene fail honestly with 404;
- the ready path passes the prepared batch record through unchanged.
"""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from main import app
from app.data.storage import get_storage
from app.models import StudioProject
from app.services.project_store import project_store
from app.services.render import render_service
from app.services.scene_production_pipeline_service import scene_production_pipeline_service
from app.services.storyboard_blueprint_service import storyboard_blueprint_service


def _seed_project(project_id: str, scene_id: str = "scene_001") -> dict[str, Any]:
    project = {
        "project_id": project_id,
        "title": "Preflight Route Test",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": scene_id,
                    "heading": "INT. EDIT BAY - NIGHT",
                    "text": "Maya holds the cut one breath longer. The room hums.",
                    "characters": ["MAYA"],
                    "updated_at": "2026-09-26T00:00:00Z",
                }
            ]
        },
    }
    project_store.save_project(project)
    storage = get_storage()
    storage.save_project(StudioProject(**project))
    return project


def _approve_storyboard(project_id: str, scene_id: str, shot_count: int) -> dict[str, Any]:
    """Approve a fresh board version. The reference gate stays unresolved on
    purpose: a fresh project has no approved canonical references, so the
    backend's own gates must report the batch as BLOCKED."""
    detail = storyboard_blueprint_service.get_or_create_blueprint(
        project_id=project_id, scene_id=scene_id, shot_count=shot_count
    )
    storyboard_blueprint_service.run_continuity_review(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )
    storyboard_blueprint_service.derive_and_approve_image_prompts_for_version(version_id=detail["version"].version_id)
    return storyboard_blueprint_service.approve_version(
        blueprint_id=detail["blueprint"].blueprint_id,
        version_id=detail["version"].version_id,
    )


def test_generation_preflight_route_reports_backend_blocked_verdict() -> None:
    client = TestClient(app)
    project_id = "project_preflight_route_blocked"
    scene_id = "scene_001"
    _seed_project(project_id, scene_id)
    approved = _approve_storyboard(project_id, scene_id, shot_count=3)

    jobs_before = list(render_service.list_jobs(project_id=project_id))
    scene_before = project_store.get_project(project_id)["execution_summary"]["scenes"][0]

    response = client.get(
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/generation-preflight"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["scene_id"] == scene_id

    # The verdict is the backend's own fail-closed result, not a UI heuristic.
    assert payload["ready"] is False
    assert payload["blockers"], "backend gates must report blockers for an unreferenced scene"
    assert payload["shot_count"] == 3
    assert len(payload["entries"]) == 3
    for entry in payload["entries"]:
        assert entry["blockers"], "every fresh shot must carry the backend's blockers"
    assert set(payload["manifest"]["batch"]) == {"total_duration_seconds", "shot_count"}
    assert "selected_model" not in payload["manifest"]["batch"]
    assert "estimated_total_credits" not in payload["manifest"]["batch"]
    assert payload["manifest"]["storyboard"]["storyboard_version"] == approved["version"].version_id
    # G1 [A: router jobs honestly unpriced] per FINAL_ARCHITECTURE_GATE §H:
    # routed shots carry no invented local model cost.
    assert payload["cost_estimate"]["estimated"] is False
    assert payload["cost_estimate"]["estimated_total_credits"] is None
    assert payload["cost_estimate"]["unpriced_shot_count"] == 3
    assert len(payload["cost_estimate"]["per_shot"]) == 3
    for row in payload["cost_estimate"]["per_shot"]:
        assert row["estimated"] is False
        assert row["estimated_credits"] is None
    # The preflight must never report a zero or numeric cost for unpriced routed shots.
    for row in payload["cost_estimate"]["per_shot"]:
        assert not isinstance(row["estimated_credits"], (int, float)), "unpriced routed shot must not carry numeric cost"
    assert not isinstance(payload["cost_estimate"]["estimated_total_credits"], (int, float)), "unpriced batch must not carry numeric total"

    # Read-only guarantee: no render job was created for this project.
    jobs_after = list(render_service.list_jobs(project_id=project_id))
    assert len(jobs_after) == len(jobs_before)

    # Read-only guarantee: canonical creative state is untouched.
    scene_after = project_store.get_project(project_id)["execution_summary"]["scenes"][0]
    assert scene_after == scene_before


def test_generation_preflight_route_is_read_only_across_the_whole_project() -> None:
    client = TestClient(app)
    project_id = "project_preflight_route_readonly"
    scene_id = "scene_001"
    _seed_project(project_id, scene_id)
    _approve_storyboard(project_id, scene_id, shot_count=2)

    project_before = project_store.get_project(project_id)
    client.get(
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/generation-preflight"
    )

    project_after = project_store.get_project(project_id)
    assert project_after == project_before


def test_generation_preflight_route_unknown_project_returns_404() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/f51/studio/projects/project_missing/scenes/scene_001/generation-preflight"
    )
    assert response.status_code == 404


def test_generation_preflight_route_unknown_scene_returns_404() -> None:
    client = TestClient(app)
    project_id = "project_preflight_route_no_scene"
    _seed_project(project_id, "scene_001")

    response = client.get(
        f"/api/f51/studio/projects/{project_id}/scenes/scene_404/generation-preflight"
    )
    assert response.status_code == 404


def test_generation_preflight_route_passes_ready_batch_through_unchanged() -> None:
    """When the backend pre-flight reports ready, the endpoint forwards the
    prepared record verbatim — no re-evaluation, no reshaping of the verdict."""
    client = TestClient(app)
    project_id = "project_preflight_route_ready"
    scene_id = "scene_001"
    _seed_project(project_id, scene_id)

    prepared = {
        "project_id": project_id,
        "scene_id": scene_id,
        "ready": True,
        "blockers": [],
        "shots": [{"shot_id": f"{scene_id}_shot_001"}],
        "entries": [
            {
                "shot_id": f"{scene_id}_shot_001",
                "shot_order": 1,
                "prompt": "Maya holds the cut.",
                "duration_seconds": 5,
                "blockers": [],
            }
        ],
        "manifest": {"manifest_fingerprint": "finger", "batch": {"readiness_status": "ready"}},
        "generation_context_ids": ["genctx_preflight"],
        "cost_estimate": {
            "provider": "runway",
            "per_shot": [{"model": "gen4.5", "duration_seconds": 5, "estimated_credits": 60, "estimated": True}],
            "total_duration_seconds": 5,
            "estimated_total_credits": 60,
            "estimated": True,
            "unpriced_shot_count": 0,
        },
        "prepared_snapshot_id": "snapshot-route-test",
    }
    original = scene_production_pipeline_service.prepare_scene_batch
    calls: list[dict[str, Any]] = []

    def _stub(*, project_id: str, scene_id: str, project: dict, provider: str | None = None, **_kwargs: Any):
        calls.append(
            {"project_id": project_id, "scene_id": scene_id, "provider": provider, "project": project}
        )
        return prepared

    scene_production_pipeline_service.prepare_scene_batch = _stub  # type: ignore[method-assign]
    try:
        response = client.get(
            f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/generation-preflight?provider=runway"
        )
    finally:
        scene_production_pipeline_service.prepare_scene_batch = original  # type: ignore[method-assign]

    assert response.status_code == 200
    payload = response.json()
    assert {key: payload[key] for key in (
        "project_id", "scene_id", "ready", "blockers", "shot_count",
        "entries", "manifest", "cost_estimate", "prepared_snapshot_id",
    )} == {
        "project_id": project_id,
        "scene_id": scene_id,
        "ready": True,
        "blockers": [],
        "shot_count": 1,
        "entries": prepared["entries"],
        "manifest": prepared["manifest"],
        "cost_estimate": prepared["cost_estimate"],
        "prepared_snapshot_id": "snapshot-route-test",
    }
    # R4.1A: the endpoint additionally surfaces batch authorization. The
    # stubbed shot has no manifest row, so authorization refuses exactly it.
    authorization = payload["authorization"]
    assert authorization["ready"] is False
    assert authorization["shot_count"] == 1
    assert authorization["shots"][0]["failure_code"] == "missing_generation_contract"
    assert calls[0]["provider"] == "runway"
