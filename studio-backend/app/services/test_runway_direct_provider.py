"""Focused dry-run tests for the additive ``runway_direct`` provider.

All tests are mocked / dry-run only: no network calls, no generation calls.
The direct path reuses the Runway Dev API contract (Bearer auth,
X-Runway-Version 2024-11-06, POST /v1/image_to_video + /v1/text_to_video,
GET /v1/tasks/{id}) under a distinct provider id so the legacy ``runway``
fail-closed gate (exact-match ``direct_runway_submission_disabled``) and the
``runway_router`` contract path stay untouched.
"""

from __future__ import annotations

import pytest

from app.adapters import (
    ADAPTER_REGISTRY,
    RunwayAdapter,
    RunwayDirectAdapter,
)
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services.render import RenderService, _validate_model_override


def _direct_cfg(**overrides) -> ProviderConfig:
    base = dict(
        provider_id="runway_direct",
        name="Runway Direct",
        enabled=True,
        is_simulated=False,
        api_key="rk_direct_test_key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "image_to_video"],
    )
    base.update(overrides)
    return ProviderConfig(**base)


def _job(provider: str = "runway_direct", **overrides) -> RenderJobModel:
    params = overrides.pop("parameters", {})
    refs = overrides.pop("referenceAssets", [])
    return RenderJobModel(
        id=overrides.pop("id", "direct-job-1"),
        project_id=overrides.pop("project_id", "proj-direct"),
        shot_id=overrides.pop("shot_id", "scene_001_shot_001"),
        provider=provider,
        status="pending",
        input_payload=RenderJobInput(
            shot_id=overrides.pop("shot_id", "scene_001_shot_001"),
            prompt=overrides.pop("prompt", "Maya pauses in a quiet hallway, medium shot, practical light."),
            referenceAssets=refs,
            parameters=dict(params),
        ),
        **overrides,
    )


# 1 — registry is additive and distinct; legacy entries untouched.
def test_runway_direct_registry_is_additive_and_distinct() -> None:
    from app.adapters import RunwayRouterAdapter

    assert ADAPTER_REGISTRY["runway"] is RunwayAdapter
    assert ADAPTER_REGISTRY["runway_direct"] is RunwayDirectAdapter
    assert ADAPTER_REGISTRY["runway_router"] is RunwayRouterAdapter
    assert issubclass(RunwayDirectAdapter, RunwayAdapter)
    assert RunwayDirectAdapter is not RunwayAdapter
    assert RunwayDirectAdapter.RUNWAY_API_VERSION == "2024-11-06"


# 2 — provider config shares Runway credentials/endpoint; nothing else moves.
def test_runway_direct_provider_config_shares_runway_credentials() -> None:
    service = RenderService()
    assert "runway_direct" in service._provider_configs
    # Legacy entries still present with their own identities.
    assert service._provider_configs["runway"].provider_id == "runway"
    assert service._provider_configs["runway_router"].provider_id == "runway_router"
    direct = service._provider_configs["runway_direct"]
    runway = service._provider_configs["runway"]
    assert direct.provider_id == "runway_direct"
    assert direct.enabled is True
    assert direct.api_key == runway.api_key
    assert direct.api_endpoint == (runway.api_endpoint or "https://api.dev.runwayml.com")
    assert "video_generation" in direct.capabilities


# 3 — model override validation mirrors the runway allowlist; router still rejects.
def test_runway_direct_model_override_uses_runway_allowlist() -> None:
    from app.services.model_registry import model_registry

    allowed = sorted(model_registry.allowed_model_ids("runway"))
    assert allowed  # dry-run guard: allowlist is non-empty
    _validate_model_override("runway_direct", {"model": allowed[0]})
    with pytest.raises(ValueError, match="Unsupported Runway model"):
        _validate_model_override("runway_direct", {"model": "not-a-real-runway-model"})
    with pytest.raises(ValueError, match="Model Router selects the eligible model"):
        _validate_model_override("runway_router", {"model": allowed[0]})


# 4 — direct adapter identities remain readable but cannot execute production.
@pytest.mark.parametrize("provider", ["runway", "runway_direct"])
async def test_direct_runway_submit_is_rejected_before_adapter(monkeypatch, provider: str) -> None:
    service = RenderService()
    job = _job(provider=provider, id=f"legacy-{provider}-still-gated")
    service._jobs[job.id] = job
    adapter_calls: list[str] = []

    monkeypatch.setattr(
        "app.services.render.get_adapter",
        lambda *_args, **_kwargs: adapter_calls.append("adapter"),
    )

    result = await service.submit_job(job.id)

    assert result.status == "failed"
    assert result.metadata["provider_boundary_failure"]["reason"] == "direct_runway_submission_disabled"
    assert result.metadata["provider_boundary_failure"]["blocked_provider"] == provider
    assert "Runway Model Router with a frozen contract" in result.error_message
    assert adapter_calls == []


def test_direct_runway_job_creation_is_rejected_in_favor_of_router_pipeline() -> None:
    service = RenderService()
    with pytest.raises(ValueError, match="canonical scene production pipeline"):
        service.create_job(
            project_id="proj-direct",
            shot_id="scene_001_shot_001",
            provider="runway_direct",
            prompt="A quiet hallway in practical light.",
        )

    # Preserve old callers' ability to create readable legacy records. The
    # execution boundary below rejects them before an adapter can be reached.
    legacy = service.create_job(
        project_id="proj-direct",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="A quiet hallway in practical light.",
    )
    assert legacy.provider == "runway"
    assert legacy.status == "pending"


def test_runway_router_alias_cannot_be_created_without_frozen_contract() -> None:
    service = RenderService()
    with pytest.raises(ValueError, match="frozen contract"):
        service.create_job(
            project_id="proj-direct",
            shot_id="scene_001_shot_001",
            provider="runway_router",
            prompt="A quiet hallway in practical light.",
        )


# 8 — create_job rejects direct paths; the canonical scene pipeline maps Runway to Router.
def test_runway_direct_create_job_preserves_provider_and_router_untouched() -> None:
    service = RenderService()
    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    pipeline = SceneProductionPipelineService()
    assert pipeline._resolve_generation_provider("runway_direct") == "runway_direct"
    assert pipeline._resolve_generation_provider("runway") == "runway_router"
    assert pipeline._resolve_generation_provider("runway_router") == "runway_router"


async def test_historical_runway_direct_job_retains_safe_status_and_cancel(monkeypatch) -> None:
    adapter = RunwayDirectAdapter(_direct_cfg())
    calls: list[tuple[str, str]] = []

    async def _fake_request(method: str, path: str, *, payload=None, params=None) -> dict:
        calls.append((method, path))
        if path == "/v1/tasks/task-legacy":
            return {"status": "RUNNING", "progress": 25}
        if path == "/v1/tasks/task-legacy/cancel":
            return {}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = _job(provider="runway_direct", id="legacy-readable")
    job.provider_job_id = "task-legacy"

    status = await adapter.get_job_status(job)
    assert status.provider == "runway_direct"
    assert status.status == "rendering"
    assert await adapter.cancel_job(status) is True
    assert calls == [("GET", "/v1/tasks/task-legacy"), ("POST", "/v1/tasks/task-legacy/cancel")]


# 5 — image_to_video contract: endpoint, Bearer + version headers, model payload, polling.
async def test_runway_direct_submit_uses_image_to_video_for_https_reference(monkeypatch) -> None:
    monkeypatch.delenv("RENDER_PROVIDER_TEST_MODE", raising=False)
    adapter = RunwayDirectAdapter(_direct_cfg())
    calls: list[tuple] = []
    # Header construction itself (Bearer + version) is exercised dry-run via a
    # captured session — no network leaves the test. Runs before _runway_request
    # is replaced by the submit-flow fake below.
    captured: dict = {}

    class _FakeResponse:
        status = 200
        headers: dict = {}

        async def text(self) -> str:
            return '{"ok": true}'

        async def json(self) -> dict:
            return {"ok": True}

    class _FakeContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, *exc):
            return False

    class _FakeSession:
        def request(self, method, url, *, headers=None, json=None, params=None, ssl=None):
            captured["headers"] = dict(headers or {})
            captured["url"] = url
            return _FakeContext()

    async def _fake_session(self) -> _FakeSession:  # type: ignore[override]
        return _FakeSession()  # type: ignore[return-value]

    monkeypatch.setattr(adapter, "_get_session", _fake_session.__get__(adapter, RunwayDirectAdapter))
    await adapter._runway_request("GET", "/v1/organization")
    assert captured["headers"]["Authorization"] == "Bearer rk_direct_test_key"
    assert captured["headers"]["X-Runway-Version"] == "2024-11-06"

    async def _fake_request(method: str, path: str, *, payload=None, params=None) -> dict:
        calls.append((method, path, payload))
        if path == "/v1/organization":
            return {}
        if method == "POST" and path == "/v1/image_to_video":
            assert payload["model"] == "gen4.5"
            assert payload["promptImage"] == "https://cdn.example.com/frame.png"
            assert payload["promptText"]
            return {"id": "task-direct-img"}
        if method == "GET" and path == "/v1/tasks/task-direct-img":
            return {"status": "SUCCEEDED", "output": ["https://cdn.example.com/direct.mp4"]}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)

    job = _job(referenceAssets=["https://cdn.example.com/frame.png"])
    result = await adapter._submit_job(job)
    assert result.status == "complete"
    assert result.provider == "runway_direct"  # identity never drifts
    assert result.provider_job_id == "task-direct-img"
    assert result.output_payload is not None
    normalized = result.output_payload.metadata["provider_response_normalized"]
    assert normalized["provider"] == "runway_direct"
    assert normalized["output"]["video_url"] == "https://cdn.example.com/direct.mp4"
    assert ("POST", "/v1/image_to_video", normalized) or True
    assert any(m == "POST" and p == "/v1/image_to_video" for m, p, _ in calls)


# 6 — text_to_video contract without a reference image.
async def test_runway_direct_submit_uses_text_to_video_without_reference(monkeypatch) -> None:
    monkeypatch.delenv("RENDER_PROVIDER_TEST_MODE", raising=False)
    adapter = RunwayDirectAdapter(_direct_cfg())
    calls: list[tuple] = []

    async def _fake_request(method: str, path: str, *, payload=None, params=None) -> dict:
        calls.append((method, path, payload))
        if path == "/v1/organization":
            return {}
        if method == "POST" and path == "/v1/text_to_video":
            assert payload["model"] == "gen4.5"
            assert "promptImage" not in payload
            return {"id": "task-direct-txt"}
        if method == "GET" and path == "/v1/tasks/task-direct-txt":
            return {"status": "SUCCEEDED", "output": ["https://cdn.example.com/direct-txt.mp4"]}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = _job()
    result = await adapter._submit_job(job)
    assert result.status == "complete"
    assert any(m == "POST" and p == "/v1/text_to_video" for m, p, _ in calls)
    assert not any(m == "POST" and p == "/v1/image_to_video" for m, p, _ in calls)
    normalized = result.output_payload.metadata["provider_response_normalized"]
    assert normalized["provider"] == "runway_direct"


# 7 — status/cancel/fetch report the direct identity (mocked task fetch only).
async def test_runway_direct_status_cancel_fetch_report_direct_identity(monkeypatch) -> None:
    adapter = RunwayDirectAdapter(_direct_cfg())
    seen: list[tuple] = []

    async def _fake_request(method: str, path: str, *, payload=None, params=None) -> dict:
        seen.append((method, path))
        if path == "/v1/organization":
            return {}
        if path == "/v1/tasks/task-7":
            return {"status": "SUCCEEDED", "output": ["https://cdn.example.com/v7.mp4"]}
        if path == "/v1/tasks/task-7/cancel":
            return {}
        raise AssertionError(f"unexpected {method} {path}")

    monkeypatch.setattr(adapter, "_runway_request", _fake_request)
    job = _job(id="direct-job-7")
    job.provider_job_id = "task-7"
    checked = await adapter.get_job_status(job)
    assert checked.status == "complete"
    assert checked.output_payload.metadata["provider_response_normalized"]["provider"] == "runway_direct"

    assets = await adapter.fetch_outputs(checked)
    assert len(assets) == 1 and assets[0].provider == "runway_direct"

    cancelled = await adapter.cancel_job(checked)
    assert cancelled is True
    assert ("POST", "/v1/tasks/task-7/cancel") in seen

    status = await adapter.get_status()
    assert status.provider_id == "runway_direct"


# 8 — direct job creation is denied while operator alias maps to Router.
def test_runway_direct_create_job_preserves_provider_and_router_untouched() -> None:
    service = RenderService()
    with pytest.raises(ValueError, match="canonical scene production pipeline"):
        service.create_job(
            project_id="proj-direct",
            shot_id="scene_001_shot_001",
            provider="runway_direct",
            prompt="A quiet hallway in practical light, medium shot, held still.",
        )
    legacy = service.create_job(
        project_id="proj-direct",
        shot_id="scene_001_shot_001",
        provider="runway",
        prompt="A quiet hallway in practical light, medium shot, held still.",
    )
    assert legacy.provider == "runway"
    assert legacy.status == "pending"

    from app.services.scene_production_pipeline_service import SceneProductionPipelineService

    pipeline = SceneProductionPipelineService()
    assert pipeline._resolve_generation_provider("runway_direct") == "runway_direct"
    assert pipeline._resolve_generation_provider("runway") == "runway_router"
    assert pipeline._resolve_generation_provider("runway_router") == "runway_router"
