from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.previs_routes as previs_routes
from app.services.previs_generation_settings_service import (
    GenerationSettingsRecommendation,
    GenerationSettingsResult,
    ProviderDurationConstraint,
)


class _StubSettingsService:
    async def recommend(self, **kwargs):
        return GenerationSettingsResult(
            scene_id=kwargs["scene_id"],
            shot_number=kwargs["shot_number"],
            recommended=GenerationSettingsRecommendation(
                duration_seconds=6,
                fps=16,
                resolution="720p",
                model="Wan 2.2",
            ),
            duration_constraint=ProviderDurationConstraint(
                provider="Wan 2.2",
                supports_custom_duration=True,
                valid_durations_seconds=(4, 8, 12, 16, 20),
                nearest_valid_duration_seconds=8,
                advisory="Treat this as a starting rhythm.",
            ),
            reasoning="Enough time for the push-in to register without releasing tension too early.",
            study_memories_used=2,
        )


def test_generation_settings_route_returns_duration_constraints(monkeypatch):
    api = FastAPI()
    api.include_router(previs_routes.router, prefix="/api/f51/studio")
    monkeypatch.setattr(
        previs_routes,
        "_get_generation_settings_service",
        lambda: _StubSettingsService(),
    )

    response = TestClient(api).post(
        "/api/f51/studio/projects/proj-1/previs/generation-settings",
        json={"scene_id": "scene_001", "shot_number": 2, "shot_type": "close"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["recommended"]["duration_seconds"] == 6
    assert data["duration_constraint"]["provider"] == "Wan 2.2"
    assert data["duration_constraint"]["nearest_valid_duration_seconds"] == 8
    assert data["reasoning"].startswith("Enough time")


def test_shot_count_route_accepts_fenced_json(monkeypatch):
    api = FastAPI()
    api.include_router(previs_routes.router, prefix="/api/f51/studio")
    llm = AsyncMock(
        return_value=(
            '```json\n{"shot_count": 4, "reasoning": "Four beats preserve the scene rhythm."}\n```',
            "openrouter",
        )
    )
    monkeypatch.setattr(previs_routes, "_get_llm_with_fallback", lambda: llm)

    response = TestClient(api).post(
        "/api/f51/studio/projects/project_3dba9330f43a/previs/shot-count",
        json={"scene_id": "scene_001"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["recommended_shot_count"] == 4
    assert data["reasoning"] == "Four beats preserve the scene rhythm."
