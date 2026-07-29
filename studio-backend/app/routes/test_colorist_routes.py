from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.colorist import router
from app.services.colorist_intelligence_service import colorist_intelligence_service


def test_colorist_look_plan_assessment_and_final_routes():
    with TemporaryDirectory() as tmp:
        colorist_intelligence_service._storage = DatabaseStorage(tmp)
        colorist_intelligence_service._crew_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        look_response = client.post(
            "/api/projects/project-color/colorist/look-bibles",
            json={
                "project_context": {
                    "color_palette": ["teal", "amber"],
                    "tone": "intimate noir",
                },
                "force_refresh": True,
            },
        )
        assert look_response.status_code == 200
        look_bible = look_response.json()["look_bible"]
        assert look_bible["advisory_only"] is True

        plan_response = client.post(
            "/api/projects/project-color/colorist/plans",
            json={
                "look_bible_id": look_bible["look_bible_id"],
                "scene_id": "scene_001",
                "scene_context": {
                    "description": "A cold hallway with amber practicals.",
                    "color_palette": ["teal", "amber"],
                },
                "force_refresh": True,
            },
        )
        assert plan_response.status_code == 200
        plan = plan_response.json()["plan"]
        assert plan["intended_palette"]

        render_response = client.post(
            "/api/projects/project-color/colorist/render-context",
            json={"plan_id": plan["plan_id"], "provider": "runway"},
        )
        assert render_response.status_code == 200
        assert render_response.json()["color_direction"]

        observation_response = client.post(
            "/api/projects/project-color/colorist/observations",
            json={"plan_id": plan["plan_id"], "asset_id": "asset-color-001"},
        )
        assert observation_response.status_code == 200
        observation = observation_response.json()["observation"]
        assert observation["status"] == "low_data"

        assessment_response = client.post(
            "/api/projects/project-color/colorist/assessments",
            json={"plan_id": plan["plan_id"], "observation_id": observation["observation_id"]},
        )
        assert assessment_response.status_code == 200
        assessment = assessment_response.json()["assessment"]
        assert assessment["advisory_only"] is True
        assert "score" not in assessment["match_summary"].lower()

        final_response = client.post(
            "/api/projects/project-color/colorist/final-verifications",
            json={"assessment_ids": [assessment["assessment_id"]]},
        )
        assert final_response.status_code == 200
        assert final_response.json()["verification"]["assessment_ids"] == [assessment["assessment_id"]]

        assert client.get("/api/projects/project-color/colorist/look-bibles").json()["look_bibles"]
        assert client.get(f"/api/projects/project-color/colorist/look-bibles/{look_bible['look_bible_id']}").json()["look_bible"]["look_bible_id"] == look_bible["look_bible_id"]
        assert client.get("/api/projects/project-color/colorist/plans", params={"scene_id": "scene_001"}).json()["plans"]
        assert client.get(f"/api/projects/project-color/colorist/plans/{plan['plan_id']}").json()["plan"]["plan_id"] == plan["plan_id"]
        assert client.get("/api/projects/project-color/colorist/palette-continuity", params={"scene_id": "scene_001"}).json()["records"]
        assert client.get("/api/projects/project-color/colorist/observations", params={"asset_id": "asset-color-001"}).json()["observations"]
        assert client.get("/api/projects/project-color/colorist/assessments", params={"plan_id": plan["plan_id"]}).json()["assessments"]
        assert client.get("/api/projects/project-color/colorist/final-verifications").json()["verifications"]


def test_colorist_story_arc_decision_and_signal_routes():
    with TemporaryDirectory() as tmp:
        colorist_intelligence_service._storage = DatabaseStorage(tmp)
        colorist_intelligence_service._crew_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        look_response = client.post(
            "/api/projects/project-color/colorist/look-bibles",
            json={"project_context": {"color_palette": ["bone white", "signal red"]}},
        )
        assert look_response.status_code == 200
        look_bible = look_response.json()["look_bible"]

        arc_response = client.post(
            "/api/projects/project-color/colorist/story-arcs",
            json={
                "look_bible_id": look_bible["look_bible_id"],
                "project_context": {"emotional_turns": ["arrival", "betrayal"]},
            },
        )
        assert arc_response.status_code == 200
        assert arc_response.json()["story_arc"]["advisory_only"] is True
        assert client.get("/api/projects/project-color/colorist/story-arcs").json()["story_arcs"]

        plan_response = client.post(
            "/api/projects/project-color/colorist/plans",
            json={
                "look_bible_id": look_bible["look_bible_id"],
                "scene_id": "scene_002",
                "scene_context": {"color_palette": ["bone white", "signal red"]},
            },
        )
        plan = plan_response.json()["plan"]

        decision_response = client.post(
            "/api/projects/project-color/colorist/decisions/save",
            json={
                "decision_text": "Keep signal red only for the betrayal motif.",
                "inferred_tradeoff": "motif discipline over broader palette freedom",
                "look_bible_id": look_bible["look_bible_id"],
                "plan_id": plan["plan_id"],
            },
        )
        assert decision_response.status_code == 200
        assert decision_response.json()["editable"] is True

        signal_response = client.get(
            "/api/projects/project-color/colorist/signal",
            params={"scene_id": "scene_002"},
        )
        assert signal_response.status_code == 200
        signal = signal_response.json()
        assert signal["latest_plan_id"] == plan["plan_id"]
        assert signal["advisory_only"] is True


def test_colorist_observation_requires_asset_or_render_job():
    with TemporaryDirectory() as tmp:
        colorist_intelligence_service._storage = DatabaseStorage(tmp)
        colorist_intelligence_service._crew_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/projects/project-color/colorist/observations",
            json={"scene_id": "scene_001"},
        )

        assert response.status_code == 400
