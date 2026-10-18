"""
R4.3G Step 3 — HTTP-level refusal tests (route layer only).

``POST /projects/{project_id}/scenes/{scene_id}/render-batch`` is retired:
it must refuse with a structured error, persist zero jobs, and never reach
``RenderService.create_scene_batch`` (hence never any provider). The service
method itself is untouched; its bypass behavior is documented (not
re-authorized) by ``test_render_batch_preflight_bypass.py``.

Uses a live TestClient against the real app with isolated test storage no
mocks on the HTTP path except a tripwire on the service method proving the
route returns before the service is ever entered.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.batch


def _client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _create_project(client) -> str:
    created = client.post("/api/f51/studio/projects", json={"title": "Retired Batch Film"})
    assert created.status_code == 200
    return created.json()["project_id"]


class TestRenderBatchRouteRefusal:
    def test_post_is_retired_with_structured_refusal(self):
        client = _client()
        project_id = _create_project(client)
        resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scenes/scene_01/render-batch",
            json={"shots": [
                {"shot_id": "scene_01_shot_001", "description": "Wide establishing shot"},
                {"shot_id": "scene_01_shot_002", "description": "Close-up on face"},
            ]},
        )
        assert resp.status_code == 410
        detail = resp.json()["detail"]
        assert detail["code"] == "render_batch_retired"
        assert "pipeline/generate" in detail["message"]
        assert "preflight" in detail["message"]

    def test_refusal_creates_zero_jobs_and_never_enters_service(self, monkeypatch):
        import app.routes.scene_continuity_intelligence as route_module

        async def _forbidden_service_call(*args, **kwargs):
            raise AssertionError("retired route must not enter the service")

        monkeypatch.setattr(
            route_module.render_service, "create_scene_batch", _forbidden_service_call
        )
        client = _client()
        project_id = _create_project(client)
        resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scenes/scene_01/render-batch",
            json={"shots": [{"shot_id": "scene_01_shot_001", "description": "test"}]},
        )
        assert resp.status_code == 410

        jobs_resp = client.get(f"/api/f51/studio/render/jobs?project_id={project_id}")
        assert jobs_resp.status_code == 200
        assert jobs_resp.json() == []

    def test_missing_project_still_404_and_empty_shots_still_400(self):
        client = _client()
        missing = client.post(
            "/api/f51/studio/projects/nonexistent/scenes/scene_01/render-batch",
            json={"shots": [{"shot_id": "s1", "description": "test"}]},
        )
        assert missing.status_code == 404

        project_id = _create_project(client)
        empty = client.post(
            f"/api/f51/studio/projects/{project_id}/scenes/scene_01/render-batch",
            json={"shots": []},
        )
        assert empty.status_code == 400
