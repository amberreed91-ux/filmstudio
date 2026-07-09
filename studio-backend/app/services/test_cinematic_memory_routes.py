from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from app.services.frame_analysis_service import frame_analysis_service
from app.services.visual_embedding_service import visual_embedding_service


def _client() -> TestClient:
    return TestClient(app)


def _make_video(path: Path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=24", str(path)], check=True)


def test_build_and_search_memory_routes(monkeypatch):
    monkeypatch.setenv("VISION_ANALYSIS_PROVIDER", "mock_local")
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "mock_local")
    frame_analysis_service._vision_adapter = None
    visual_embedding_service._embedding_adapter = None

    client = _client()
    created = client.post('/api/f51/studio/projects', json={'title': 'Memory Route Film'})
    assert created.status_code == 200
    project_id = created.json()['project_id']

    generated_dir = Path(__file__).resolve().parents[2] / 'outputs' / 'final_films'
    generated_dir.mkdir(parents=True, exist_ok=True)
    video = generated_dir / 'memory_route_demo.mp4'
    _make_video(video)

    registered = client.post(
        f'/api/f51/studio/projects/{project_id}/video-assets',
        json={'source_type': 'generated_output', 'source_url': '/outputs/final_films/memory_route_demo.mp4', 'title': 'Memory Demo'},
    )
    assert registered.status_code == 200
    asset_id = registered.json()['asset']['asset_id']

    extracted = client.post(f'/api/f51/studio/video-assets/{asset_id}/extract-keyframes', json={'interval_seconds': 2, 'max_frames': 3, 'overwrite': True})
    assert extracted.status_code == 200
    keyframe_id = (extracted.json().get('keyframes') or [])[0]['keyframe_id']

    analyzed = client.post(f'/api/f51/studio/video-assets/{asset_id}/analyze-keyframes', json={})
    assert analyzed.status_code == 200

    embedded = client.post(f'/api/f51/studio/video-assets/{asset_id}/embed-keyframes')
    assert embedded.status_code == 200

    built = client.post(f'/api/f51/studio/projects/{project_id}/build-memory', json={'asset_id': asset_id})
    assert built.status_code == 200
    assert len(built.json().get('memory_records') or []) >= 1

    listed = client.get(f'/api/f51/studio/projects/{project_id}/memory')
    assert listed.status_code == 200
    assert len(listed.json().get('memory_records') or []) >= 1

    searched = client.post(f'/api/f51/studio/projects/{project_id}/search-memory', json={'query': 'soft natural lighting', 'top_k': 5})
    assert searched.status_code == 200
    assert isinstance(searched.json().get('results') or [], list)

    related = client.get(f'/api/f51/studio/video-keyframes/{keyframe_id}/related-memory')
    assert related.status_code == 200
    assert isinstance(related.json().get('results') or [], list)
