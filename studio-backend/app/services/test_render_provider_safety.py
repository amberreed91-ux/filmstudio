"""Provider truth and completion transitions must survive adapter mutation."""
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters import get_adapter, SimulatedProviderAdapter
from app.models import ProviderConfig, RenderJobModel, RenderJobOutput
from app.services import render as render_module
from app.services.stability import ProviderError


@pytest.fixture
def isolated_render(monkeypatch):
    service = render_module.RenderService()
    saved = {}
    monkeypatch.setattr(render_module, '_storage', None)
    monkeypatch.setattr(render_module, '_persist_job', lambda job: saved.update({job.id: job.model_copy(deep=True)}))
    for name in ('_run_continuity_review', '_run_render_quality_check', '_run_character_reference_lock', '_notify_update'):
        monkeypatch.setattr(render_module, name, AsyncMock())
    job = RenderJobModel(id='provider-safety-job', project_id='safety-project', shot_id='scene_001_shot_001', provider='simulated', metadata={})
    service._jobs[job.id] = job
    return service, job, saved


def test_unknown_adapter_never_becomes_simulated():
    with pytest.raises(ValueError, match='Unknown provider'):
        get_adapter('removed-provider', ProviderConfig(provider_id='removed-provider', name='Removed'))


def test_explicit_simulated_adapter_remains_available():
    assert isinstance(get_adapter('simulated', ProviderConfig(provider_id='simulated', name='Simulated')), SimulatedProviderAdapter)


@pytest.mark.asyncio
async def test_enabled_provider_submits_through_its_adapter(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    calls = []

    class Adapter:
        async def submit_job(self, current):
            calls.append(current.provider)
            current.status = 'rendering'
            return current

    monkeypatch.setattr(render_module, 'validate_generation_payload', lambda **_kwargs: None)
    monkeypatch.setattr(render_module, 'get_adapter', lambda *args: Adapter())
    result = await service.submit_job(job.id)
    assert result.status == 'rendering'
    assert calls == ['simulated']
    assert saved[job.id].provider == 'simulated'


@pytest.mark.asyncio
async def test_disabled_provider_rejects_before_adapter_and_does_not_fallback(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    service._provider_configs['simulated'].enabled = False
    adapter_factory = Mock()
    monkeypatch.setattr(render_module, 'get_adapter', adapter_factory)
    with pytest.raises(ProviderError, match="Provider 'simulated' is disabled"):
        await service.submit_job(job.id)
    adapter_factory.assert_not_called()
    assert job.provider == 'simulated'
    assert saved[job.id].provider == 'simulated'
    assert saved[job.id].status == 'failed'
    assert saved[job.id].metadata['provider_failure']['error_type'] == 'provider_disabled'
    assert job.id not in service._submit_locks


@pytest.mark.asyncio
async def test_disabled_provider_blocks_retry_before_adapter(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    service._provider_configs['simulated'].enabled = False
    job.status = 'failed'
    adapter_factory = Mock()
    monkeypatch.setattr(render_module, 'get_adapter', adapter_factory)
    with pytest.raises(ProviderError, match="Provider 'simulated' is disabled"):
        await service.retry_job(job.id)
    adapter_factory.assert_not_called()
    assert job.provider == 'simulated'
    assert saved[job.id].provider == 'simulated'


@pytest.mark.asyncio
async def test_disabled_provider_blocks_canonical_workflow_submission(isolated_render, monkeypatch):
    from app.services.canonical_production_workflow_service import CanonicalProductionWorkflowService

    service, job, _ = isolated_render
    service._provider_configs['simulated'].enabled = False
    adapter_factory = Mock()
    monkeypatch.setattr(render_module, 'get_adapter', adapter_factory)
    workflow = CanonicalProductionWorkflowService(storage=Mock(), renderer=service)
    workflow._mark_render_failed = Mock()
    run = {
        'run_id': 'workflow-disabled-provider',
        'status': 'render_queued',
        'data': {'artifacts': {'render_jobs': [{'render_job_id': job.id}]}},
    }

    with pytest.raises(ProviderError, match="Provider 'simulated' is disabled"):
        await workflow._reconcile_renders(run, provider='simulated', started=0.0, submit=True)

    adapter_factory.assert_not_called()
    assert job.provider == 'simulated'
    workflow._mark_render_failed.assert_called_once()


@pytest.mark.asyncio
async def test_adapter_provider_mutation_is_rejected_and_identity_restored(isolated_render, monkeypatch):
    service, job, saved = isolated_render

    class MutatingAdapter:
        async def submit_job(self, current):
            current.provider = 'wan'
            current.status = 'rendering'
            return current

    monkeypatch.setattr(render_module, 'validate_generation_payload', lambda **_kwargs: None)
    monkeypatch.setattr(render_module, 'get_adapter', lambda *args: MutatingAdapter())
    with pytest.raises(ProviderError, match='Provider identity changed'):
        await service.submit_job(job.id)
    assert job.provider == 'simulated'
    assert saved[job.id].provider == 'simulated'
    assert saved[job.id].status == 'failed'


@pytest.mark.asyncio
async def test_failed_provider_submission_never_selects_or_invokes_another_provider(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    adapter_calls = []

    class FailingAdapter:
        async def submit_job(self, _current):
            raise RuntimeError("controlled provider failure")

    def factory(provider_id, _config):
        adapter_calls.append(provider_id)
        return FailingAdapter()

    monkeypatch.setattr(render_module, 'validate_generation_payload', lambda **_kwargs: None)
    monkeypatch.setattr(render_module, 'get_adapter', factory)
    with pytest.raises(RuntimeError, match="controlled provider failure"):
        await service.submit_job(job.id)
    assert adapter_calls == ['simulated']
    assert saved[job.id].provider == 'simulated'
    assert saved[job.id].status == 'failed'


@pytest.mark.asyncio
async def test_missing_provider_configuration_preserves_job_and_fails(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    del service._provider_configs['simulated']
    adapter_factory = Mock()
    monkeypatch.setattr(render_module, 'get_adapter', adapter_factory)
    with pytest.raises(ProviderError):
        await service.submit_job(job.id)
    adapter_factory.assert_not_called()
    assert job.provider == 'simulated'
    assert saved[job.id].status == 'failed'
    assert saved[job.id].provider_job_id is None
    assert job.id not in service._submit_locks


@pytest.mark.asyncio
async def test_poll_missing_provider_configuration_fails_recoverably(isolated_render):
    service, job, saved = isolated_render
    job.status = 'rendering'
    job.provider_job_id = 'original-hosted-task'
    del service._provider_configs['simulated']
    result = await service.get_job_status(job.id)
    assert result.status == 'failed'
    assert saved[job.id].provider == 'simulated'
    assert saved[job.id].provider_job_id == 'original-hosted-task'
    assert 'configuration' in result.error_message.lower()


@pytest.mark.asyncio
async def test_mutating_adapter_runs_completion_hooks_and_notifies_once(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    job.status = 'rendering'
    class Adapter:
        async def get_job_status(self, current):
            current.status = 'complete'
            current.output_payload = RenderJobOutput(asset_url='https://example.test/film.mp4')
            return current
    monkeypatch.setattr(render_module, 'get_adapter', lambda *args: Adapter())
    assert (await service.get_job_status(job.id)).status == 'complete'
    await service.get_job_status(job.id)
    for name in ('_run_continuity_review', '_run_render_quality_check', '_run_character_reference_lock', '_notify_update'):
        getattr(render_module, name).assert_awaited_once()
    assert saved[job.id].output_payload.asset_url == 'https://example.test/film.mp4'


def test_submit_route_formats_provider_error(isolated_render, monkeypatch):
    from app.routes import render as routes
    service, job, _ = isolated_render
    del service._provider_configs['simulated']
    monkeypatch.setattr(routes, 'render_service', service)
    app = FastAPI()
    app.include_router(routes.router)
    response = TestClient(app, raise_server_exceptions=False).post(f'/jobs/{job.id}/submit')
    assert response.status_code == 502
    assert response.json()['detail']['error_type'] == 'provider_error'


def test_submit_route_rejects_disabled_provider_without_adapter_call(isolated_render, monkeypatch):
    from app.routes import render as routes
    service, job, _ = isolated_render
    service._provider_configs['simulated'].enabled = False
    adapter_factory = Mock()
    monkeypatch.setattr(render_module, 'get_adapter', adapter_factory)
    monkeypatch.setattr(routes, 'render_service', service)
    app = FastAPI()
    app.include_router(routes.router)

    response = TestClient(app, raise_server_exceptions=False).post(f'/jobs/{job.id}/submit')

    assert response.status_code == 502
    assert "Provider 'simulated' is disabled" in response.json()['detail']['message']
    adapter_factory.assert_not_called()


def test_runway_direct_and_router_are_distinct_adapters_and_configurations():
    from app.adapters import ADAPTER_REGISTRY, RunwayAdapter, RunwayDirectAdapter, RunwayRouterAdapter
    from app.services.render import RenderService

    service = RenderService()
    assert ADAPTER_REGISTRY['runway'] is RunwayAdapter
    assert ADAPTER_REGISTRY['runway_direct'] is RunwayDirectAdapter
    assert ADAPTER_REGISTRY['runway_router'] is RunwayRouterAdapter
    assert service.get_provider_config('runway').provider_id == 'runway'
    assert service.get_provider_config('runway_router').provider_id == 'runway_router'
    assert service.get_provider_config('runway') is not service.get_provider_config('runway_router')


@pytest.mark.asyncio
async def test_direct_runway_adapter_call_is_blocked_before_provider_io(monkeypatch):
    from app.adapters import RunwayDirectAdapter
    from app.models import RenderJobInput

    config = ProviderConfig(
        provider_id='runway_direct', name='Runway Direct', enabled=True,
        is_simulated=False, api_key='test-key', api_endpoint='https://api.dev.runwayml.com',
        requires=['api_key'], capabilities=['video_generation'],
    )
    adapter = RunwayDirectAdapter(config)
    job = RenderJobModel(
        id='direct-boundary-job', project_id='project', shot_id='scene_1_shot_1',
        provider='runway_direct', input_payload=RenderJobInput(prompt='A test shot.'),
    )
    calls = []

    async def unexpected_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('direct production adapter must not make provider calls')

    monkeypatch.setattr(adapter, '_runway_request', unexpected_request)
    result = await adapter.submit_job(job)

    assert result.status == 'failed'
    assert result.metadata['provider_boundary_failure']['reason'] == 'direct_runway_submission_disabled'
    assert result.metadata['provider_boundary_failure']['required_provider'] == 'runway_router'
    assert calls == []


def test_adapter_factory_rejects_disabled_provider_before_construction():
    from app.adapters import get_adapter

    with pytest.raises(ValueError, match="Provider 'runway' is disabled"):
        get_adapter('runway', ProviderConfig(provider_id='runway', name='Runway', enabled=False))


def test_provider_initialization_never_logs_key_fragments(monkeypatch, caplog):
    key = "SENSITIVE-prefix-private-middle-SUFFIX"
    monkeypatch.setenv("RUNWAYML_API_SECRET", key)
    with caplog.at_level("INFO", logger="studio-render"):
        render_module.RenderService()
    assert key not in caplog.text
    assert key[:4] not in caplog.text
    assert key[-4:] not in caplog.text
    assert "configured=True" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('seed', [0, 1234])
async def test_explicit_take_seed_survives_stored_seed_injection(isolated_render, monkeypatch, seed):
    from app.models import RenderJobInput
    service, job, saved = isolated_render
    job.input_payload = RenderJobInput(prompt='The hand stays closed.', parameters={'seed': seed})
    storage = Mock()
    storage.get_shot_seed.return_value = {'seed': 99, 'seed_locked': True}
    monkeypatch.setattr(render_module, '_storage', storage)
    class Adapter:
        async def submit_job(self, current):
            assert current.input_payload.parameters['seed'] == seed
            current.status = 'rendering'
            return current
    monkeypatch.setattr(render_module, 'get_adapter', lambda *args: Adapter())
    result = await service.submit_job(job.id)
    assert result.input_payload.parameters['seed'] == seed
    storage.get_shot_seed.assert_not_called()
    storage.save_shot_seed.assert_not_called()
