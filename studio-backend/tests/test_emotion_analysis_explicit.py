from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.routes.emotion_analysis import get_emotion_analysis_service, router
from app.services.emotion_analysis_service import EmotionAnalysisService
from app.services.stability import ProviderError, StateError, ValidationError


ANALYSIS_JSON = json.dumps(
    {
        "general": {"engagement": 70, "tension": 60, "emotional_impact": 65},
        "cinephile": {"engagement": 75, "tension": 64, "emotional_impact": 72},
        "genre_fan": {"engagement": 68, "tension": 70, "emotional_impact": 66},
    }
)


class FakeProjectStore:
    def __init__(self) -> None:
        self.project = {
            "project_id": "project-emotion",
            "title": "Held Light",
            "execution_summary": {
                "scenes": [
                    {"scene_id": "scene-1", "heading": "INT. EDIT BAY - NIGHT"},
                    {"scene_id": "scene-2", "heading": "EXT. WATER - DAWN"},
                ]
            },
        }
        self.reads = 0

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        self.reads += 1
        return self.project if project_id == self.project["project_id"] else None


def _service(
    tmp_path: Path,
    llm,
    *,
    memory: dict[str, Any] | None = None,
    content: dict[str, str] | None = None,
) -> tuple[EmotionAnalysisService, DatabaseStorage, FakeProjectStore]:
    storage = DatabaseStorage(str(tmp_path / "emotion-db"))
    store = FakeProjectStore()
    memory_state = memory if memory is not None else {"tone": ["Hold the silence"]}
    content_state = content if content is not None else {
        "scene-1": "Mara watches the last frame without speaking.",
        "scene-2": "The horizon opens.",
    }
    service = EmotionAnalysisService(
        storage=storage,
        project_store_service=store,  # type: ignore[arg-type]
        llm_completion=llm,
        scene_content_fetcher=lambda _project_id, scene_id: content_state[scene_id],
        memory_fetcher=lambda _project_id: memory_state,
    )
    return service, storage, store


@pytest.mark.asyncio
async def test_external_analysis_requires_creator_confirmation_before_context_or_provider(
    tmp_path: Path,
) -> None:
    calls = 0

    async def llm(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return ANALYSIS_JSON, "qwen"

    service, _, store = _service(tmp_path, llm)

    with pytest.raises(ValidationError) as caught:
        await service.analyze_scene("project-emotion", "scene-1", confirmed=False)

    assert caught.value.stage == "emotion_analysis_confirmation"
    assert calls == 0
    assert store.reads == 0


@pytest.mark.asyncio
async def test_confirmed_analysis_is_persisted_and_reused_without_another_provider_call(
    tmp_path: Path,
) -> None:
    calls = 0

    async def llm(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return ANALYSIS_JSON, "qwen"

    service, storage, _ = _service(tmp_path, llm)

    first = await service.analyze_scene("project-emotion", "scene-1", confirmed=True)
    second = await service.analyze_scene("project-emotion", "scene-1", confirmed=True)
    loaded = service.get_cached_scene("project-emotion", "scene-1")

    assert calls == 1
    assert first["provider_call"] is True
    assert first["cached"] is False
    assert second["provider_call"] is False
    assert second["cached"] is True
    assert loaded["provider_call"] is False
    assert loaded["analysis"] == first["analysis"]
    assert storage.get_emotion_analysis_result(
        "project-emotion", "scene-1", first["context_hash"]
    ) is not None


@pytest.mark.asyncio
async def test_context_change_invalidates_cache_and_requires_a_new_explicit_call(tmp_path: Path) -> None:
    calls = 0
    memory = {"tone": ["Hold the silence"]}

    async def llm(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return ANALYSIS_JSON, "qwen"

    service, _, _ = _service(tmp_path, llm, memory=memory)
    first = await service.analyze_scene("project-emotion", "scene-1", confirmed=True)
    memory["tone"] = ["Release the tension earlier"]

    with pytest.raises(StateError):
        service.get_cached_scene("project-emotion", "scene-1")

    second = await service.analyze_scene("project-emotion", "scene-1", confirmed=True)
    assert calls == 2
    assert first["context_hash"] != second["context_hash"]


@pytest.mark.asyncio
async def test_concurrent_confirmed_requests_share_one_provider_call(tmp_path: Path) -> None:
    calls = 0

    async def llm(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return ANALYSIS_JSON, "qwen"

    service, _, _ = _service(tmp_path, llm)
    first, second = await asyncio.gather(
        service.analyze_scene("project-emotion", "scene-1", confirmed=True),
        service.analyze_scene("project-emotion", "scene-1", confirmed=True),
    )

    assert calls == 1
    assert sorted([first["provider_call"], second["provider_call"]]) == [False, True]
    assert first["analysis_id"] == second["analysis_id"]


@pytest.mark.asyncio
async def test_invalid_provider_output_is_not_cached_as_a_success(tmp_path: Path) -> None:
    async def llm(*_args, **_kwargs):
        return "not-json", "qwen"

    service, storage, _ = _service(tmp_path, llm)

    with pytest.raises(ProviderError) as caught:
        await service.analyze_scene("project-emotion", "scene-1", confirmed=True)

    assert caught.value.stage == "emotion_analysis_parse"
    assert storage.get_emotion_analysis_result("project-emotion", "scene-1") is None


class RouteService:
    def __init__(self) -> None:
        self.calls = 0
        self.envelope = {
            "analysis_id": "emotion-route",
            "project_id": "project-emotion",
            "scene_id": "scene-1",
            "context_hash": "a" * 64,
            "provider": "qwen",
            "model": "qwen3.7-max",
            "cached": True,
            "provider_call": False,
            "created_at": "2026-08-06T12:00:00+00:00",
            "updated_at": "2026-08-06T12:00:00+00:00",
            "analysis": json.loads(ANALYSIS_JSON) | {"scene_id": "scene-1"},
        }

    def get_cached_scene(self, project_id: str, scene_id: str):
        assert (project_id, scene_id) == ("project-emotion", "scene-1")
        return self.envelope

    async def analyze_scene(self, project_id: str, scene_id: str, *, confirmed: bool, force: bool):
        if not confirmed:
            raise ValidationError("Confirmation required", stage="emotion_analysis_confirmation")
        self.calls += 1
        return {**self.envelope, "cached": False, "provider_call": True}


def test_routes_keep_cache_reads_separate_from_confirmed_provider_actions() -> None:
    fake = RouteService()
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[get_emotion_analysis_service] = lambda: fake
    client = TestClient(api)
    path = "/api/f51/studio/emotion-analysis/projects/project-emotion/scenes/scene-1"

    cached = client.get(path)
    unconfirmed = client.post(f"{path}/analyze", json={})
    confirmed = client.post(f"{path}/analyze", json={"confirmed": True})

    assert cached.status_code == 200
    assert cached.json()["provider_call"] is False
    assert fake.calls == 1
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["detail"]["error_type"] == "validation_error"
    assert confirmed.status_code == 200
    assert confirmed.json()["provider_call"] is True
