from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.performance_intelligence import PerformanceAnalysisResponse
from app.routes import performance_intelligence as route_module


def test_performance_analyze_route_is_thin_and_returns_service_payload(monkeypatch):
    app = FastAPI()
    app.include_router(route_module.router)

    async def fake_analyze_scene_performance(project_id, scene_id, character_ids=None, persist=False, include_context_bundles=True):
        return PerformanceAnalysisResponse(
            analysis_id="analysis_1",
            project_id=project_id,
            scene_id=scene_id,
            analysis_scope="scene",
            status="complete",
            generated_at="2026-07-28T00:00:00Z",
            source_signature="sig",
            summary="Performance reasoning is available.",
            briefs=[],
            relationship_reads=[],
            reasoning_trace=[],
            guardrail_report={"public_precision_language": "clear"},
        )

    monkeypatch.setattr(route_module.performance_intelligence_service, "analyze_scene_performance", fake_analyze_scene_performance)

    client = TestClient(app)
    response = client.post(
        "/api/projects/project_1/performance-intelligence/analyze",
        json={"scene_id": "scene_001", "scope": "scene", "persist": True},
    )

    assert response.status_code == 200
    assert response.json()["project_id"] == "project_1"
    assert response.json()["scene_id"] == "scene_001"


def test_performance_analyze_route_requires_scene_for_scene_scope():
    app = FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app)

    response = client.post(
        "/api/projects/project_1/performance-intelligence/analyze",
        json={"scope": "scene"},
    )

    assert response.status_code == 400
