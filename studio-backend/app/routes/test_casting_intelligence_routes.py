from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.casting_intelligence import router
from app.services.casting_intelligence_service import casting_intelligence_service
from app.services.project_store import ProjectStore


def test_casting_routes_cover_role_talent_decision_projection():
    with TemporaryDirectory() as tmp:
        storage = DatabaseStorage(tmp)
        store = ProjectStore(f"{tmp}/projects.json")
        store.save_project(
            {
                "project_id": "project-casting",
                "title": "Casting Route Fixture",
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "description": "Mara hides grief in a quiet room.",
                        "characters": ["Mara"],
                    }
                ],
            }
        )
        casting_intelligence_service._storage = storage
        casting_intelligence_service.project_store = store
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        roles_response = client.post(
            "/api/f51/studio/projects/project-casting/casting/roles/build",
            json={"persist": True},
        )
        assert roles_response.status_code == 200
        role = roles_response.json()["roles"][0]
        assert role["character_name"] == "Mara"

        talent_response = client.post(
            "/api/f51/studio/projects/project-casting/casting/talent",
            json={
                "display_name": "AI Stand-In",
                "modality": "placeholder",
                "provider_bindings": [{"provider": "local_tts", "voice_id": "standin-voice"}],
            },
        )
        assert talent_response.status_code == 200
        talent = talent_response.json()

        rec_response = client.post(
            f"/api/f51/studio/projects/project-casting/casting/roles/{role['role_id']}/recommendations",
            json={"candidate_talent_ids": [talent["talent_id"]], "persist": True},
        )
        assert rec_response.status_code == 200
        assert rec_response.json()[0]["evidence_refs"]

        decision_response = client.post(
            "/api/f51/studio/projects/project-casting/casting/decisions",
            json={
                "role_id": role["role_id"],
                "talent_id": talent["talent_id"],
                "recommendation_id": rec_response.json()[0]["recommendation_id"],
            },
        )
        assert decision_response.status_code == 200
        assert decision_response.json()["active"] is True

        projection_response = client.get(
            f"/api/f51/studio/projects/project-casting/casting/projection?role_id={role['role_id']}"
        )
        assert projection_response.status_code == 200
        assert projection_response.json()["active_decisions"][0]["talent_id"] == talent["talent_id"]

        signal_response = client.get("/api/f51/studio/projects/project-casting/casting/department-signal")
        assert signal_response.status_code == 200
        assert signal_response.json()["covered_roles"] == 1
