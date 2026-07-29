from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.cinematography import router
from app.services.cinematographer_intelligence_service import cinematographer_intelligence_service


def test_camera_grammar_plan_and_render_context_routes():
    with TemporaryDirectory() as tmp:
        cinematographer_intelligence_service._storage = DatabaseStorage(tmp)
        cinematographer_intelligence_service._crew_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/projects/project-cam/cinematography/plans",
            json={
                "scene_id": "scene_001",
                "shot_id": "shot_001",
                "plan_scope": "shot",
                "scene_context": {
                    "visual_description": "A tense close-up by a practical lamp.",
                    "camera_work": "static close-up",
                    "lighting": "practical lamp",
                },
            },
        )

        assert response.status_code == 200
        plan = response.json()["plan"]
        assert plan["project_id"] == "project-cam"
        assert plan["advisory_only"] is True

        render_context = client.post(
            "/api/projects/project-cam/cinematography/render-context",
            json={"plan_id": plan["plan_id"], "provider": "runway"},
        )

        assert render_context.status_code == 200
        body = render_context.json()
        assert body["plan_id"] == plan["plan_id"]
        assert body["budget"]["camera_limit"] == 70


def test_camera_grammar_route_rejects_missing_observation_target():
    with TemporaryDirectory() as tmp:
        cinematographer_intelligence_service._storage = DatabaseStorage(tmp)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/projects/project-cam/cinematography/observations",
            json={"scene_id": "scene_001"},
        )

        assert response.status_code == 400
