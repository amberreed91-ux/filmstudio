from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.production_design_intelligence import router
from app.services.production_design_intelligence_service import production_design_intelligence_service


def test_production_design_plan_render_context_and_signal_routes():
    with TemporaryDirectory() as tmp:
        production_design_intelligence_service._storage = DatabaseStorage(tmp)
        production_design_intelligence_service._crew_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/f51/studio/projects/project-pd/production-design/plans",
            json={
                "scene_id": "scene_001",
                "shot_id": "shot_001",
                "scene_context": {
                    "location": "INT. SAFEHOUSE - NIGHT",
                    "description": "A key and a cracked mirror sit beside a practical lamp.",
                    "characters": ["Mara"],
                    "wardrobe": ["gray coat"],
                    "props": ["key", "cracked mirror"],
                },
            },
        )

        assert response.status_code == 200
        plan = response.json()["plan"]
        assert plan["project_id"] == "project-pd"
        assert plan["advisory_only"] is True
        assert plan["prop_records"]

        render_context = client.post(
            "/api/f51/studio/projects/project-pd/production-design/render-context",
            json={"plan_id": plan["plan_id"], "provider": "runway"},
        )
        assert render_context.status_code == 200
        assert render_context.json()["environment_direction"]

        signal = client.get("/api/f51/studio/projects/project-pd/production-design/department-signal")
        assert signal.status_code == 200
        assert signal.json()["active_plan_count"] == 1


def test_production_design_observation_route_rejects_missing_target():
    with TemporaryDirectory() as tmp:
        production_design_intelligence_service._storage = DatabaseStorage(tmp)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/f51/studio/projects/project-pd/production-design/observations",
            json={"scene_id": "scene_001"},
        )

        assert response.status_code == 400
