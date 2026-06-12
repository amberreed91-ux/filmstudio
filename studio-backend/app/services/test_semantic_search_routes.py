from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_semantic_search_routes(tmp_path: Path):
    client = _client()
    created = client.post('/api/f51/studio/projects', json={'title': 'Search Film'})
    assert created.status_code == 200
    project_id = created.json()['project_id']

    f1 = tmp_path / 's1.mp4'
    f2 = tmp_path / 's2.mp4'
    f1.write_text('1')
    f2.write_text('2')

    a1 = client.post(f'/api/f51/studio/projects/{project_id}/video-assets', json={'source_type':'local_file','local_path':str(f1),'title':'S1'})
    a2 = client.post(f'/api/f51/studio/projects/{project_id}/video-assets', json={'source_type':'local_file','local_path':str(f2),'title':'S2'})
    assert a1.status_code == 200 and a2.status_code == 200
    aid1 = a1.json()['asset']['asset_id']
    aid2 = a2.json()['asset']['asset_id']

    m1 = client.post(f'/api/f51/studio/video-assets/{aid1}/scene-memory/ingest', json={'dominant_mood':'tense','visual_style':'noir','lighting_style':'low-key','pacing_profile':'fast','cinematic_notes':'rain neon'})
    m2 = client.post(f'/api/f51/studio/video-assets/{aid2}/scene-memory/ingest', json={'dominant_mood':'tense','visual_style':'noir','lighting_style':'low-key','pacing_profile':'fast','cinematic_notes':'rain neon'})
    assert m1.status_code == 200 and m2.status_code == 200
    memory_id = m1.json()['memory']['memory_id']

    frame = client.post(f'/api/f51/studio/video-assets/{aid2}/frame-analysis', json={'caption':'rain neon closeup','mood_tags':['tense'],'lighting_tags':['low-key'],'camera_tags':['handheld']})
    assert frame.status_code == 200

    sim = client.get('/api/f51/studio/scene-search/similar', params={'memory_id': memory_id, 'limit': 10})
    assert sim.status_code == 200
    assert isinstance(sim.json()['results'], list)

    mood = client.get('/api/f51/studio/scene-search/by-mood', params={'mood':'tense'})
    style = client.get('/api/f51/studio/scene-search/by-visual-style', params={'style':'noir'})
    assert mood.status_code == 200 and style.status_code == 200
    assert len(mood.json()['memories']) >= 1
    assert len(style.json()['memories']) >= 1
