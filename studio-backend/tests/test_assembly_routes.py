from unittest.mock import AsyncMock
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routes.assembly import router, get_film_delivery_service
from app.models.film_delivery import AssemblyStatusResponse, AssembleFilmResponse
from app.services.stability import StateError, PlaybackError


def client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_film_delivery_service] = lambda: service
    return TestClient(app)


def test_assembly_status_contract():
    status = AssemblyStatusResponse(scenes_with_compositions=1, scenes_total=2, film_assembled=False, film_url=None, has_audio=False, scenes_needing_assembly=['scene_002'])
    service = SimpleNamespace(status=lambda _: status)
    response = client(service).get('/api/f51/studio/projects/p/assembly-status')
    assert response.status_code == 200
    assert response.json() == status.model_dump()


def test_assemble_film_contract():
    result = AssembleFilmResponse(film_url='/static/film.mp4', scene_count=2, total_duration_seconds=6.0, has_audio=True)
    service = SimpleNamespace(assemble=AsyncMock(return_value=result))
    response = client(service).post('/api/f51/studio/projects/p/assemble-film')
    assert response.status_code == 200
    assert response.json() == result.model_dump()
    service.assemble.assert_awaited_once_with('p')


def test_assembly_failure_is_structured():
    for error, status in [(StateError('Missing scene'), 409), (PlaybackError('Missing file'), 500)]:
        service = SimpleNamespace(assemble=AsyncMock(side_effect=error))
        response = client(service).post('/api/f51/studio/projects/p/assemble-film')
        assert response.status_code == status
        assert response.json()['detail']['error_type'] == error.error_type
