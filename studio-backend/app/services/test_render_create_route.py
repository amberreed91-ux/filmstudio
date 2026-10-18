from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import RenderJobModel
from app.routes import render as render_routes
from app.services import render as render_module


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
                "character_identity_warnings": [
                    "Maya: conflicting facial identity evidence needs review."
                ],
                "environment_continuity_context": {
                    "location_id": "harbor-house-kitchen",
                    "warnings": [
                        "destruction_damage: window was previously broken and has no restored-state record"
                    ],
                    "recognizability": {
                        "recognizable": False,
                        "status": "needs_review",
                        "preserved_anchors": ["Harbor House Kitchen"],
                        "missing_anchors": ["blue enamel mug"],
                        "basis": "Environment prompt does not carry enough canonical anchors to prove recognizability.",
                    },
                    "reference_explanations": [
                        {
                            "source_shot_id": "scene_001_shot_001",
                            "role": "establishing",
                            "reason": "selected because approved establishing shots are preferred as environment anchors",
                        }
                    ],
                },
            },
            "retry_count": 0,
            "created_at": "2026-07-23T12:00:00",
            "updated_at": "2026-07-23T12:00:00",
        }


class _FakeAdherenceRetryRenderService:
    def get_job(self, _job_id: str):
        return SimpleNamespace(
            id="job-adherence",
            project_id="project_1",
            shot_id="scene_001_shot_001",
            status="complete",
            input_payload=SimpleNamespace(
                parameters={
                    "prompt_slots": {
                        "character_state": "Maya carries the prior tension.",
                        "action": "Maya watches the train pass.",
                    }
                }
            ),
        )


class _FakeAdherenceRetryService:
    def __init__(self):
        self.calls = []

    async def evaluate_and_select_best(self, **kwargs):
        self.calls.append(kwargs)
        from app.services.adherence_service import FullCorrectedPrompt

        return {
            "strategy": kwargs["submission_strategy"],
            "corrected_prompt": FullCorrectedPrompt(
                base_attempt=0,
                seed_locked=False,
                slots=kwargs["original_slots"],
                provenance={"character_state": "original", "action": "original"},
                prompt="Maya watches the train pass.",
                chars_remaining=480,
                compressed_slots=[],
            ),
            "seeds_used": [123],
            "jobs_submitted": [{"job_id": "job-retry", "seed": 123, "status": "submitted"}],
            "submission_errors": [],
            "all_scored_attempts": [],
            "best_attempt": None,
            "source_job_id": kwargs["source_job_id"],
        }


class _FakeFailedAdherenceRetryService:
    async def evaluate_and_select_best(self, **_kwargs):
        return {
            "strategy": "combined_reorder_and_fresh_seeds",
            "seeds_used": [123],
            "jobs_submitted": [],
            "submission_errors": [{"attempt": 1, "seed": 123, "error": "Provider rejected retry payload"}],
            "all_scored_attempts": [],
            "best_attempt": None,
        }


class _FakeRenderJob:
    def __init__(self, job_id: str, created_at: str, status: str = "pending") -> None:
        self.id = job_id
        self.project_id = "project_1"
        self.shot_id = f"shot_{job_id}"
        self.provider = "happyhorse-r2v"
        self.status = status
        self.progress = 0
        self.input_payload = None
        self.output_payload = None
        self.error_message = None
        self.retry_count = 0
        self.created_at = created_at
        self.updated_at = created_at

    def model_dump(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "shot_id": self.shot_id,
            "provider": self.provider,
            "status": self.status,
            "progress": self.progress,
            "input_payload": None,
            "output_payload": None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class _FakePaginatedRenderStorage:
    def list_jobs_page(self, **kwargs):
        assert kwargs == {
            "project_id": "project_1",
            "status": "pending",
            "cursor": None,
            "limit": 2,
        }
        return {
            "items": [
                _FakeRenderJob("job_002", "2026-07-23T12:02:00"),
                _FakeRenderJob("job_001", "2026-07-23T12:01:00"),
            ],
            "next_cursor": "2026-07-23T12:01:00|job_001",
            "total_visible": 2,
            "has_more": True,
            "filters": {"project_id": "project_1", "status": "pending"},
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
    assert summary["character_identity_warnings"] == [
        "Maya: conflicting facial identity evidence needs review."
    ]
    assert summary["environment_continuity"]["location_id"] == "harbor-house-kitchen"
    assert summary["environment_continuity"]["warnings"] == [
        "destruction_damage: window was previously broken and has no restored-state record"
    ]
    assert summary["environment_continuity"]["human_review_required"] is True
    assert summary["environment_continuity"]["recognizability"]["status"] == "needs_review"
    assert summary["environment_continuity"]["reference_explanations"][0]["role"] == "establishing"
    assert summary["human_review_required"] is True


def test_adherence_retry_returns_json_safe_payload(monkeypatch) -> None:
    monkeypatch.setattr(render_routes, "render_service", _FakeAdherenceRetryRenderService())
    import app.services.render_retry_service as retry_module

    retry_service = _FakeAdherenceRetryService()
    monkeypatch.setattr(retry_module, "render_retry_service", retry_service)
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")

    response = TestClient(api).post(
        "/api/f51/studio/render/jobs/job-adherence/adherence-retry",
        json={"max_attempts": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["corrected_prompt"]["prompt"] == "Maya watches the train pass."
    assert data["jobs_submitted"] == [{"job_id": "job-retry", "seed": 123, "status": "submitted"}]
    assert data["source_job_id"] == "job-adherence"
    assert retry_service.calls[0]["provider_override"] is None


def test_adherence_retry_explicit_provider_override_is_forwarded(monkeypatch) -> None:
    monkeypatch.setattr(render_routes, "render_service", _FakeAdherenceRetryRenderService())
    import app.services.render_retry_service as retry_module

    retry_service = _FakeAdherenceRetryService()
    monkeypatch.setattr(retry_module, "render_retry_service", retry_service)
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")

    response = TestClient(api).post(
        "/api/f51/studio/render/jobs/job-adherence/adherence-retry",
        json={"max_attempts": 1, "provider_override": "happyhorse"},
    )

    assert response.status_code == 200
    assert retry_service.calls[0]["provider_override"] == "happyhorse"


def test_adherence_retry_reports_provider_queue_failure(monkeypatch) -> None:
    monkeypatch.setattr(render_routes, "render_service", _FakeAdherenceRetryRenderService())
    import app.services.render_retry_service as retry_module

    monkeypatch.setattr(retry_module, "render_retry_service", _FakeFailedAdherenceRetryService())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")

    response = TestClient(api).post(
        "/api/f51/studio/render/jobs/job-adherence/adherence-retry",
        json={"max_attempts": 1},
    )

    assert response.status_code == 502
    assert "Provider rejected retry payload" in response.json()["detail"]


def test_list_render_jobs_can_return_paginated_contract(monkeypatch) -> None:
    monkeypatch.setattr(render_module, "_storage", _FakePaginatedRenderStorage())
    api = FastAPI()
    api.include_router(render_routes.router, prefix="/api/f51/studio/render")

    response = TestClient(api).get(
        "/api/f51/studio/render/jobs",
        params={"project_id": "project_1", "status": "pending", "limit": 2, "paginated": "true"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["has_more"] is True
    assert data["next_cursor"] == "2026-07-23T12:01:00|job_001"
    assert [item["job_id"] for item in data["items"]] == ["job_002", "job_001"]
    assert data["filters"] == {"project_id": "project_1", "status": "pending"}


def test_render_job_storage_pagination_keeps_same_timestamp_rows(tmp_path) -> None:
    storage = DatabaseStorage(str(tmp_path))
    created_at = "2026-07-23T12:00:00"
    for index in range(450):
        storage.save_job(
            RenderJobModel(
                id=f"job_{index:04d}",
                project_id="project_page",
                shot_id=f"shot_{index:04d}",
                provider="simulated",
                status="pending",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    first_page = storage.list_jobs_page(project_id="project_page", limit=200)
    second_page = storage.list_jobs_page(
        project_id="project_page",
        cursor=first_page["next_cursor"],
        limit=200,
    )

    assert len(first_page["items"]) == 200
    assert len(second_page["items"]) == 200
    assert first_page["has_more"] is True
    assert second_page["has_more"] is True
    assert {job.id for job in first_page["items"]}.isdisjoint(job.id for job in second_page["items"])
