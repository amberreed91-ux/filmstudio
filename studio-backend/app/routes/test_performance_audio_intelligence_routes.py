from __future__ import annotations

from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.performance_audio_intelligence import router
from app.services.performance_audio_intelligence_service import performance_audio_intelligence_service


def test_performance_audio_plan_execution_and_signal_routes():
    with TemporaryDirectory() as tmp:
        performance_audio_intelligence_service._storage = DatabaseStorage(tmp)
        performance_audio_intelligence_service._crew_intelligence_service = None
        performance_audio_intelligence_service._memory_service = None
        performance_audio_intelligence_service._performance_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/f51/studio/projects/project-audio/audio-intelligence/plans",
            json={
                "scene_id": "scene_001",
                "shot_id": "shot_001",
                "scene_context": {
                    "scene_id": "scene_001",
                    "characters": ["Mara"],
                    "dialogue_lines": [{"character_name": "Mara", "text": "Keep your voice down."}],
                    "description": "A tense room with distant traffic.",
                },
            },
        )

        assert response.status_code == 200
        plan = response.json()["plan"]
        assert plan["project_id"] == "project-audio"
        assert plan["advisory_only"] is True

        cues = client.get(
            f"/api/f51/studio/projects/project-audio/audio-intelligence/dialogue-cues?plan_id={plan['plan_id']}"
        )
        assert cues.status_code == 200
        assert cues.json()["dialogue_cues"][0]["text"] == "Keep your voice down."

        layers = client.get(
            f"/api/f51/studio/projects/project-audio/audio-intelligence/soundscape-layers?plan_id={plan['plan_id']}"
        )
        assert layers.status_code == 200
        assert layers.json()["soundscape_layers"]

        execution = client.post(
            f"/api/f51/studio/projects/project-audio/audio-intelligence/plans/{plan['plan_id']}/execution-request"
        )
        assert execution.status_code == 200
        assert execution.json()["dialogue_lines"][0]["text"] == "Keep your voice down."

        signal = client.get("/api/f51/studio/projects/project-audio/audio-intelligence/department-signal")
        assert signal.status_code == 200
        assert signal.json()["plan_count"] == 1

        decision = client.post(
            "/api/f51/studio/projects/project-audio/audio-intelligence/decisions",
            json={"decision_text": "Let traffic stay under the confession."},
        )
        assert decision.status_code == 200
        decision_id = decision.json()["decision_id"]

        update = client.patch(
            f"/api/f51/studio/projects/project-audio/audio-intelligence/decisions/{decision_id}",
            json={"decision_text": "Let traffic stay under the confession until the last pause."},
        )
        assert update.status_code == 200
        assert update.json()["decision_text"].endswith("last pause.")

        forget = client.delete(
            f"/api/f51/studio/projects/project-audio/audio-intelligence/decisions/{decision_id}"
        )
        assert forget.status_code == 200
        assert forget.json()["forgotten_at"]


def test_performance_audio_assessment_route_requires_existing_plan():
    with TemporaryDirectory() as tmp:
        performance_audio_intelligence_service._storage = DatabaseStorage(tmp)
        performance_audio_intelligence_service._crew_intelligence_service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/f51/studio/projects/project-audio/audio-intelligence/assessments",
            json={"plan_id": "missing-plan", "asset_id": "asset-1"},
        )

        assert response.status_code == 404
