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
    job = RenderJobModel(id='provider-safety-job', project_id='safety-project', shot_id='scene_001_shot_001', provider='runway')
    service._jobs[job.id] = job
    return service, job, saved


def test_unknown_adapter_never_becomes_simulated():
    with pytest.raises(ValueError, match='Unknown provider'):
        get_adapter('removed-provider', ProviderConfig(provider_id='removed-provider', name='Removed'))


def test_explicit_simulated_adapter_remains_available():
    assert isinstance(get_adapter('simulated', ProviderConfig(provider_id='simulated', name='Simulated')), SimulatedProviderAdapter)


@pytest.mark.asyncio
async def test_missing_provider_configuration_preserves_job_and_fails(isolated_render, monkeypatch):
    service, job, saved = isolated_render
    del service._provider_configs['runway']
    adapter_factory = Mock()
    monkeypatch.setattr(render_module, 'get_adapter', adapter_factory)
    with pytest.raises(ProviderError):
        await service.submit_job(job.id)
    adapter_factory.assert_not_called()
    assert job.provider == 'runway'
    assert saved[job.id].status == 'failed'
    assert saved[job.id].provider_job_id is None
    assert job.id not in service._submit_locks


@pytest.mark.asyncio
async def test_poll_missing_provider_configuration_fails_recoverably(isolated_render):
    service, job, saved = isolated_render
    job.status = 'rendering'
    job.provider_job_id = 'original-hosted-task'
    del service._provider_configs['runway']
    result = await service.get_job_status(job.id)
    assert result.status == 'failed'
    assert saved[job.id].provider == 'runway'
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
    del service._provider_configs['runway']
    monkeypatch.setattr(routes, 'render_service', service)
    app = FastAPI()
    app.include_router(routes.router)
    response = TestClient(app, raise_server_exceptions=False).post(f'/jobs/{job.id}/submit')
    assert response.status_code == 502
    assert response.json()['detail']['error_type'] == 'provider_error'


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
