"""R4.3L (Policy A): legacy non-canonical previs rejects Runway-family providers.

The legacy previs path (POST .../previs/generate-scene -> PrevisService.generate_scene)
rejects runway / runway_router / runway_direct with a 4xx before any job exists,
and leaves every other provider's behavior unchanged. Production render and
revision behavior must not change.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.previs_service import PrevisService
from app.services.stability import ProviderError, ValidationError


class FakeRenderer:
    def __init__(self) -> None:
        self.jobs: dict[str, SimpleNamespace] = {}
        self.created = 0
        self.submitted: list[str] = []

    def get_default_provider(self):
        return "simulated"

    def create_job(self, **kwargs):
        self.created += 1
        job_id = f"previs-job-{self.created}"
        provider = kwargs.pop("provider", "simulated")
        job = SimpleNamespace(
            id=job_id,
            status="pending",
            provider=provider,
            output_payload=None,
            error_message=None,
            **kwargs,
        )
        self.jobs[job_id] = job
        return job

    async def submit_job(self, job_id: str):
        self.submitted.append(job_id)
        return self.jobs[job_id]

    async def get_job_status(self, job_id: str):
        return self.jobs[job_id]

    async def cancel_job(self, job_id: str) -> bool:
        self.jobs[job_id].status = "cancelled"
        return True


class RunwayDeadRenderer(FakeRenderer):
    """Simulates a dead Runway adapter: non-simulated creates raise before a job exists."""

    def create_job(self, **kwargs):
        provider = kwargs.get("provider", "simulated")
        if provider != "simulated":
            raise ProviderError(
                "Runway adapter unavailable",
                stage="previs_job_create",
                metadata={"provider": provider},
            )
        return super().create_job(**kwargs)


def _storage(tmp_path: Path) -> DatabaseStorage:
    storage = DatabaseStorage(str(tmp_path / "r43l-db"))
    storage.save_project(
        StudioProject(
            project_id="project_previs",
            title="R4.3L legacy previs",
            execution_summary={
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "heading": "INT. EDIT BAY - NIGHT",
                        "description": "Maya holds the cut one breath longer.",
                        "location": "Edit bay",
                        "time_of_day": "night",
                        "emotional_tone": "contained dread",
                        "characters": ["MAYA"],
                    }
                ]
            },
        )
    )
    return storage


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, "simulated"])
async def test_legacy_service_allows_omitted_and_simulated(tmp_path: Path, provider: str | None) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)
    kwargs = {} if provider is None else {"provider": provider}
    result = await service.generate_scene("project_previs", "scene_001", **kwargs)
    assert result["job_id"] in renderer.jobs
    assert renderer.created == 1
    assert renderer.jobs[result["job_id"]].provider == "simulated"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["runway", "runway_router", "runway_direct"])
async def test_legacy_service_rejects_runway_family_before_any_create_job(
    tmp_path: Path, provider: str
) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    renderer._provider_configs = {"simulated": {}, "runway": {}, "runway_router": {}, "runway_direct": {}}
    service = PrevisService(storage, renderer)
    with pytest.raises(ValidationError, match="Runway is not used for previs"):
        await service.generate_scene("project_previs", "scene_001", provider=provider)
    assert renderer.created == 0
    assert renderer.jobs == {}
    assert renderer.submitted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["runway", "runway_router", "runway_direct"])
async def test_legacy_service_rejection_carries_stable_code(tmp_path: Path, provider: str) -> None:
    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    service = PrevisService(storage, renderer)
    with pytest.raises(ValidationError) as raised:
        await service.generate_scene("project_previs", "scene_001", provider=provider)
    assert raised.value.stage == "previs_generate"
    assert raised.value.metadata.get("code") == "legacy_previs_runway_rejected"
    assert raised.value.metadata.get("rejected_provider") == provider
    assert "simulated" in raised.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, "simulated"])
async def test_legacy_allowed_previs_completes_with_runway_dead(tmp_path: Path, provider: str | None) -> None:
    """Allowed providers never touch the Runway adapter, so they complete even dead."""
    storage = _storage(tmp_path)
    renderer = RunwayDeadRenderer()
    service = PrevisService(storage, renderer)
    kwargs = {} if provider is None else {"provider": provider}
    result = await service.generate_scene("project_previs", "scene_001", **kwargs)
    assert result["job_id"] in renderer.jobs
    assert renderer.jobs[result["job_id"]].provider == "simulated"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["happyhorse", "happyhorse-r2v", "wan"])
async def test_legacy_service_leaves_other_providers_unchanged(tmp_path: Path, provider: str) -> None:
    from app.models.previs_render import PrevisRenderSettings

    storage = _storage(tmp_path)
    renderer = FakeRenderer()
    renderer._provider_configs = {"simulated": {}, provider: {}, "runway": {}}
    service = PrevisService(storage, renderer)
    # wan only renders 5/10/15s; the storyboard-less default is 3s, so pass a
    # valid duration to prove the provider itself is still served.
    settings = PrevisRenderSettings(duration_seconds=5) if provider == "wan" else None
    kwargs = {"provider": provider} if settings is None else {"provider": provider, "render_settings": settings}
    result = await service.generate_scene("project_previs", "scene_001", **kwargs)
    assert renderer.created == 1
    assert renderer.jobs[result["job_id"]].provider == provider


@pytest.mark.parametrize("provider", ["runway", "runway_router", "runway_direct"])
def test_legacy_route_rejects_runway_family_before_service(monkeypatch, provider: str) -> None:
    from app.routes import previs_routes

    calls: list[dict] = []

    class SpyService:
        async def generate_scene(self, *args, **kwargs):
            calls.append(kwargs)
            return {"job_id": "j", "status": "pending", "scene_id": "scene_001"}

    monkeypatch.setattr(previs_routes, "previs_service", SpyService())
    app = FastAPI()
    app.include_router(previs_routes.router)
    response = TestClient(app).post(
        "/projects/project_previs/previs/generate-scene/scene_001",
        params={"provider": provider},
    )
    assert response.status_code == 422
    assert "Runway is not used for previs" in response.text
    assert calls == []


@pytest.mark.parametrize("provider", [None, "simulated"])
def test_legacy_route_passes_allowed_providers_to_service(monkeypatch, provider: str | None) -> None:
    from app.routes import previs_routes

    calls: list[dict] = []

    class SpyService:
        async def generate_scene(self, *args, **kwargs):
            calls.append(kwargs)
            return {"job_id": "j", "status": "pending", "scene_id": "scene_001"}

    monkeypatch.setattr(previs_routes, "previs_service", SpyService())
    app = FastAPI()
    app.include_router(previs_routes.router)
    params = {} if provider is None else {"provider": provider}
    response = TestClient(app).post(
        "/projects/project_previs/previs/generate-scene/scene_001",
        params=params,
    )
    assert response.status_code == 200
    assert len(calls) == 1
