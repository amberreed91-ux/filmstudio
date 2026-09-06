from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app, storage
from app.auth import AuthService, auth_service
from app.config import settings
from app.models import RenderJobModel


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setattr(settings, 'studio_access_mode', 'authenticated')
    monkeypatch.setattr(settings, 'demo_mode', True)  # must not weaken authenticated mode
    monkeypatch.setattr(auth_service, 'storage', storage)
    client = TestClient(app)
    identities = []
    for prefix in ('alice', 'bobby'):
        username = prefix + uuid4().hex[:8]
        response = client.post('/api/f51/studio/auth/register', json={'username': username, 'email': f'{username}@example.test', 'password': 'SafePassword123!'})
        assert response.status_code == 200, response.text
        data = response.json()
        headers = {'Authorization': f"Bearer {data['session_id']}"}
        response = client.post('/api/f51/studio/projects', json={'title': prefix}, headers=headers)
        assert response.status_code == 200, response.text
        identities.append((headers, response.json()['project_id'], data))
    client.cookies.clear()
    return client, identities


@pytest.mark.parametrize('method,suffix,payload', [
    ('GET', '', None), ('PUT', '', {'title': 'stolen'}), ('DELETE', '', None),
    ('GET', '/characters', None), ('GET', '/video-assets', None),
    ('GET', '/scenes/scene_001', None), ('POST', '/scenes', {'text': 'injected'}),
    ('POST', '/scenes/scene_001/pipeline/generate', {}),
    ('GET', '/director-memory', None),
])
def test_project_ids_do_not_grant_access(secured, method, suffix, payload):
    client, ((alice, project, _), (bob, _, _)) = secured
    url = f'/api/f51/studio/projects/{project}{suffix}'
    assert client.request(method, url, json=payload).status_code == 401
    assert client.request(method, url, json=payload, headers=bob).status_code == 403
    assert client.get(f'/api/f51/studio/projects/{project}', headers=alice).status_code == 200


def test_lists_and_overview_only_include_owned_projects(secured):
    client, ((alice, project, _), (_, other, _)) = secured
    for path in ('projects', 'overview'):
        data = client.get(f'/api/f51/studio/{path}', headers=alice).json()
        assert {row['project_id'] for row in data['projects']} == {project}
        assert other not in str(data)


def test_opaque_jobs_nested_ids_and_global_scope_fail_closed(secured):
    client, ((alice, own, _), (bob, other, _)) = secured
    job = RenderJobModel(id=uuid4().hex, project_id=other, shot_id='scene_001_shot_001', provider='simulated')
    storage.save_job(job)
    assert client.get(f'/api/f51/studio/render/jobs/{job.id}', headers=alice).status_code == 403
    response = client.post('/api/f51/studio/render/jobs', headers=alice, json={'project_id': own, 'shot_id': 'scene_001_shot_001', 'parameters': {'original_job_id': job.id}})
    assert response.status_code == 403
    assert client.get('/api/f51/studio/render/jobs', headers=alice).status_code == 403
    assert client.post('/api/f51/studio/admin/restart', headers=alice, json={'project_id': own}).status_code == 403


def test_registered_media_and_websocket_are_protected(secured):
    from app.models import RenderJobOutput
    client, ((alice, own, _), (bob, _, _)) = secured
    path = f'/outputs/security-{uuid4().hex}.mp4'
    storage.save_job(RenderJobModel(id=uuid4().hex, project_id=own, shot_id='s', provider='simulated', output_payload=RenderJobOutput(asset_url=path)))
    assert client.get(path).status_code == 401
    assert client.get(path, headers=bob).status_code == 403
    # Authorized but absent bytes: static router returns 404, not an auth denial.
    assert client.get(path, headers=alice).status_code == 404
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/jobs', headers=alice):
            pass


def test_cannot_forge_ownership_or_claim_existing_project(secured):
    client, ((alice, own, _), (bob, _, data)) = secured
    assert client.post('/api/f51/studio/projects', headers=bob, json={'title': 'overwrite', 'project_id': own}).status_code == 422
    assert client.put(f'/api/f51/studio/projects/{own}', headers=alice, json={'collaboration': {'owner_user_id': data['user']['user_id']}}).status_code == 403


def test_logout_revokes_durable_session_and_restart_keeps_user(secured):
    client, ((headers, project, data), _) = secured
    restarted = AuthService(storage)
    assert restarted.get_user(data['user']['user_id'])
    assert restarted.get_session(data['session_id'])
    assert client.post('/api/f51/studio/auth/logout', headers=headers).status_code == 200
    assert restarted.get_session(data['session_id']) is None
    assert client.get(f'/api/f51/studio/projects/{project}', headers=headers).status_code == 401


def test_local_mode_never_bypasses_for_remote_clients_or_production(secured, monkeypatch):
    client, ((_, project, _), _) = secured
    monkeypatch.setattr(settings, 'studio_access_mode', 'local')
    monkeypatch.setenv('APP_ENV', 'production')
    assert client.get(f'/api/f51/studio/projects/{project}').status_code == 401
    monkeypatch.setenv('APP_ENV', 'test')
    assert client.get(f'/api/f51/studio/projects/{project}', headers={'X-Forwarded-For': '203.0.113.1'}).status_code == 401


def test_anonymous_create_is_rejected(secured):
    client, _ = secured
    assert client.post('/api/f51/studio/projects', json={'title': 'anonymous'}).status_code == 401


def test_saving_scene_plan_keeps_creator_access_and_excludes_other_users(secured):
    client, ((alice, project, _), (bob, _, _)) = secured
    path = f'/api/f51/studio/projects/{project}'
    for title in ['Revised scene plan', 'Locked scene plan']:
        assert client.put(path, headers=alice, json={'title': title}).status_code == 200
        result = client.get(path, headers=alice)
        assert result.status_code == 200
        assert result.json()['title'] == title
        assert client.get(path, headers=bob).status_code == 403
