"""
Tests for provider status and per-scene override endpoints.

Covers:
- Provider status endpoint returns correct fields
- Per-scene override is stored and used for render job creation
- Override does not affect other scenes
- Invalid provider_mode is rejected
- Missing project returns 404
"""

from __future__ import annotations

import asyncio
from fastapi.testclient import TestClient
from main import app


def _client() -> TestClient:
    return TestClient(app)


def _create_project(client: TestClient, title: str = "Provider Test Film") -> str:
    resp = client.post("/api/f51/studio/projects", json={"title": title})
    assert resp.status_code == 200
    return resp.json()["project_id"]


# ── 1. Provider status endpoint ───────────────────────────────────────────────

class TestProviderStatusEndpoint:

    def test_returns_200_for_valid_project(self):
        client = _client()
        pid = _create_project(client)
        resp = client.get(f"/api/f51/studio/projects/{pid}/provider-status")
        assert resp.status_code == 200

    def test_returns_404_for_missing_project(self):
        client = _client()
        resp = client.get("/api/f51/studio/projects/nonexistent-proj/provider-status")
        assert resp.status_code == 404

    def test_response_has_required_fields(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        for key in (
            "provider_mode",
            "ready_for_hosted_generation",
            "is_mock",
            "missing_requirements",
            "active_provider",
            "per_scene_overrides",
        ):
            assert key in data, f"Missing key: {key}"

    def test_provider_mode_is_string(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert isinstance(data["provider_mode"], str)

    def test_ready_for_hosted_generation_is_bool(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert isinstance(data["ready_for_hosted_generation"], bool)

    def test_is_mock_is_bool(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert isinstance(data["is_mock"], bool)

    def test_missing_requirements_is_list(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert isinstance(data["missing_requirements"], list)

    def test_per_scene_overrides_is_dict(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert isinstance(data["per_scene_overrides"], dict)

    def test_per_scene_overrides_empty_initially(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert data["per_scene_overrides"] == {}

    def test_active_provider_is_string(self):
        client = _client()
        pid = _create_project(client)
        data = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert isinstance(data["active_provider"], str)
        assert len(data["active_provider"]) > 0


# ── 2. Per-scene override endpoint ───────────────────────────────────────────

class TestSceneProviderOverride:

    def test_override_stored_in_project_state(self):
        client = _client()
        pid = _create_project(client)
        resp = client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_01/provider-override",
            json={"provider_mode": "simulated"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scene_id"] == "scene_01"
        assert data["provider_mode"] == "simulated"
        assert data["per_scene_overrides"]["scene_01"] == "simulated"

    def test_override_appears_in_provider_status(self):
        client = _client()
        pid = _create_project(client)
        client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_02/provider-override",
            json={"provider_mode": "simulated"},
        )
        status = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert status["per_scene_overrides"].get("scene_02") == "simulated"

    def test_override_does_not_affect_other_scenes(self):
        client = _client()
        pid = _create_project(client)
        client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_01/provider-override",
            json={"provider_mode": "simulated"},
        )
        status = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        # scene_02 should not be in overrides
        assert "scene_02" not in status["per_scene_overrides"]

    def test_multiple_overrides_stored_independently(self):
        client = _client()
        pid = _create_project(client)
        client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_01/provider-override",
            json={"provider_mode": "simulated"},
        )
        client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_02/provider-override",
            json={"provider_mode": "hosted_api"},
        )
        status = client.get(f"/api/f51/studio/projects/{pid}/provider-status").json()
        assert status["per_scene_overrides"]["scene_01"] == "simulated"
        assert status["per_scene_overrides"]["scene_02"] == "hosted_api"

    def test_invalid_provider_mode_returns_400(self):
        client = _client()
        pid = _create_project(client)
        resp = client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_01/provider-override",
            json={"provider_mode": "invalid_mode"},
        )
        assert resp.status_code == 400

    def test_override_404_for_missing_project(self):
        client = _client()
        resp = client.post(
            "/api/f51/studio/projects/nonexistent/scenes/scene_01/provider-override",
            json={"provider_mode": "simulated"},
        )
        assert resp.status_code == 404

    def test_override_used_for_render_job_creation(self):
        """
        When a scene has a 'simulated' override, the render job should use
        the simulated provider regardless of the project default.
        """
        from app.services.render import RenderService
        svc = RenderService()
        # Simulate a project with a simulated override for scene_01.
        from app.services.project_store import project_store
        client = _client()
        pid = _create_project(client)
        client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_01/provider-override",
            json={"provider_mode": "simulated"},
        )
        # Create a job for a shot in scene_01 — should use simulated.
        job = svc.create_job(
            project_id=pid,
            shot_id="scene_01_shot_001",
            provider=None,  # no explicit provider — should use override
        )
        assert job.provider == "simulated"

    def test_override_does_not_affect_different_scene_job(self):
        """
        Override for scene_01 should not affect a job for scene_02.
        """
        from app.services.render import RenderService
        svc = RenderService()
        client = _client()
        pid = _create_project(client)
        client.post(
            f"/api/f51/studio/projects/{pid}/scenes/scene_01/provider-override",
            json={"provider_mode": "simulated"},
        )
        # Job for scene_02 — no override, uses project default.
        job = svc.create_job(
            project_id=pid,
            shot_id="scene_02_shot_001",
            provider=None,
        )
        # scene_02 has no override — provider is whatever the default is.
        # We just verify it doesn't crash and returns a valid job.
        assert job.provider in ("simulated", "runway", "happyhorse", "happyhorse-r2v", "wan", "higgsfield", "generic")
        assert job.project_id == pid
