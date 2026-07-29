from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import render as render_routes


class _FakeRenderService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create_job(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "job-route",
            "project_id": kwargs["project_id"],
            "shot_id": kwargs["shot_id"],
            "provider": kwargs["provider"],
            "status": "pending",
            "progress": 0,
            "input_payload": {
                "shot_id": kwargs["shot_id"],
                "prompt": kwargs["prompt"],
                "referenceAssets": kwargs["reference_assets"],
                "parameters": kwargs["parameters"],
            },
            "retry_count": 0,
            "created_at": "2026-07-23T12:00:00",
            "updated_at": "2026-07-23T12:00:00",
        }


class _FakeStatusRenderService:
    def get_job(self, _job_id: str):
        return {
            "id": "job-status",
            "project_id": "project_1",
            "shot_id": "scene_001_shot_001",
            "provider": "happyhorse-r2v",
            "status": "needs_review",
            "progress": 0,
            "input_payload": {
                "shot_id": "scene_001_shot_001",
                "prompt": "A tight close-up and full body shot.",
                "referenceAssets": [],
                "parameters": {},
            },
            "output_payload": {
                "asset_url": "https://cdn.example.test/shot.mp4",
                "thumbnail_url": "https://cdn.example.test/shot.jpg",
                "metadata": {},
            },
            "metadata": {
                "zero_touch_pipeline": {
                    "phases": [
                        {"phase": "validate_input", "status": "complete"},
                        {"phase": "build_staging", "status": "complete"},
                        {"phase": "resolve_references", "status": "complete"},
                        {"phase": "prepare_provider_request", "status": "needs_review"},
                        {"phase": "render", "status": "skipped"},
                        {"phase": "evaluate", "status": "skipped"},
                        {"phase": "retry", "status": "skipped"},
                    ],
                    "provider_selection": {
                        "provider": "happyhorse-r2v",
                        "model": "happyhorse-1.1-r2v",
                        "reason": "configured default or caller-selected provider",
                    },
                    "staging": {
                        "applied": True,
                        "characters": ["Maya"],
                    },
                    "references": [
                        {
                            "reference_type": "character_full",
                            "reference_id": "charlock:maya",
                            "path": "https://cdn.example.test/maya.jpg",
                            "reason": "Use locked reference for Maya.",
                            "entity": "scene_001_shot_001",
                            "provider_supports_reference": True,
                            "injected_into_request": True,
                        }
                    ],
                    "retry": {"max_attempts": 2},
                },
                "adherence_review": {
                    "verdict": "manual_review",
                    "failed_slots": ["camera"],
                    "advisory_note": "Camera framing conflicts need review.",
                },
                "adherence_retry_cascade": {
                    "max_retries": 2,
                    "jobs_submitted": ["job-retry-1"],
                },
                "prompt_contradictions": [
                    {"code": "framing_closeup_full_body", "message": "Close-up conflicts with full body."}
                ],
            },
            "retry_count": 0,
            "created_at": "2026-07-23T12:00:00",
            "updated_at": "2026-07-23T12:00:00",
        }


def test_create_render_job_parses_json_query_parameters(monkeypatch) -> None:
    service = _FakeRenderService()
    monkeypatch.setattr(render_routes, "render_service", service)
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")

    response = TestClient(api).post(
        "/api/f51/studio/render/jobs",
        params={
            "project_id": "project_1",
            "shot_id": "scene_001_shot_001",
            "provider": "happyhorse",
            "prompt": "Maya crosses the hallway.",
            "reference_assets": '["/previs-assets/project_1/ref.png"]',
            "parameters": '{"duration_seconds":8,"fps":16,"resolution":"720p","structured_prompt":true}',
        },
    )

    assert response.status_code == 200
    assert service.calls[0]["reference_assets"] == ["/previs-assets/project_1/ref.png"]
    assert service.calls[0]["parameters"] == {
        "duration_seconds": 8,
        "fps": 16,
        "resolution": "720p",
        "structured_prompt": True,
    }


def test_render_job_response_includes_zero_touch_status_summary(monkeypatch) -> None:
    monkeypatch.setattr(render_routes, "render_service", _FakeStatusRenderService())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")

    response = TestClient(api).get("/api/f51/studio/render/jobs/job-status")

    assert response.status_code == 200
    data = response.json()
    summary = data["zero_touch_status"]
    assert summary["status"] == "needs_review"
    assert summary["active_phase"] == "prepare_provider_request"
    assert summary["phase_statuses"]["render"] == "skipped"
    assert summary["provider"] == "happyhorse-r2v"
    assert summary["model"] == "happyhorse-1.1-r2v"
    assert summary["staging_applied"] is True
    assert summary["staging_characters"] == ["Maya"]
    assert summary["references_applied"] is True
    assert summary["reference_count"] == 1
    assert summary["adherence"]["verdict"] == "manual_review"
    assert summary["adherence"]["failed_slots"] == ["camera"]
    assert summary["retry"]["occurred"] is True
    assert summary["retry"]["count"] == 1
    assert summary["output_url"] == "https://cdn.example.test/shot.mp4"
    assert summary["preview_url"] == "https://cdn.example.test/shot.jpg"
    assert summary["human_review_required"] is True
