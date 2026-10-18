from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import RenderJobModel
from app.services.render import RenderService
from app.services.stability import PersistenceError, StateError


@pytest.fixture
def deletion(tmp_path, monkeypatch):
    import app.services.render as module
    storage = DatabaseStorage(str(tmp_path / 'database'))
    monkeypatch.setattr(module, '_storage', storage)
    service = RenderService.__new__(RenderService)
    service._jobs = {}
    job = RenderJobModel(id='old-job', project_id='film', shot_id='scene_001_shot_001', provider='simulated', status='failed')
    storage.save_job(job)
    storage.save_previs_image(project_id='film', scene_id='scene_001', shot_id=job.shot_id,
                             image_path='', job_id=job.id, status='failed', prompt_used='A shot', fallback=False)
    return service, storage, job


def test_persisted_only_render_and_take_are_deleted_across_restart(deletion):
    service, storage, job = deletion
    assert service.delete_job(job.id)
    assert storage.get_job(job.id) is None
    assert storage.get_previs_image_by_job(job.id) is None
    assert service.list_jobs('film') == []
    assert not service.delete_job(job.id)


def test_failed_delete_keeps_job_available(deletion, monkeypatch):
    service, storage, job = deletion
    monkeypatch.setattr(storage, 'delete_job', Mock(side_effect=OSError('database busy')))
    with pytest.raises(PersistenceError):
        service.delete_job(job.id)
    assert service.get_job(job.id) is not None
    assert storage.get_job(job.id) is not None


def test_active_render_requires_cancellation(deletion):
    service, storage, job = deletion
    job.status = 'rendering'
    storage.save_job(job)
    with pytest.raises(StateError, match='Cancel'):
        service.delete_job(job.id)
    assert storage.get_job(job.id) is not None


def test_delete_route_handles_persisted_job_and_failure(deletion, monkeypatch):
    from app.routes import render as routes
    service, storage, job = deletion
    monkeypatch.setattr(routes, 'render_service', service)
    api = FastAPI()
    api.include_router(routes.router)
    client = TestClient(api)
    assert client.delete(f'/jobs/{job.id}').status_code == 200
    assert client.delete(f'/jobs/{job.id}').status_code == 404
    storage.save_job(job)
    monkeypatch.setattr(storage, 'delete_job', Mock(side_effect=OSError('busy')))
    response = client.delete(f'/jobs/{job.id}')
    assert response.status_code == 503
    assert response.json()['detail']['error_type'] == 'persistence_error'
