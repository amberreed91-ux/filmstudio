from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from app.services.visual_embedding_service import visual_embedding_service


def _client() -> TestClient:
    return TestClient(app)


def _create_sample_video(path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=24", str(path)], check=True)


def test_visual_embedding_endpoints(monkeypatch):
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "mock_local")
    visual_embedding_service._embedding_adapter = None
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Embeddings Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    generated_dir = Path(__file__).resolve().parents[2] / "outputs" / "final_films"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated = generated_dir / "embed_route_demo.mp4"
    _create_sample_video(generated)

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "generated_output", "source_url": "/outputs/final_films/embed_route_demo.mp4", "title": "Demo"},
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    extracted = client.post(f"/api/f51/studio/video-assets/{asset_id}/extract-keyframes", json={"interval_seconds": 2, "max_frames": 3, "overwrite": True})
    assert extracted.status_code == 200
    keyframes = extracted.json().get("keyframes") or []
    assert keyframes
    keyframe_id = keyframes[0]["keyframe_id"]

    embedded = client.post(f"/api/f51/studio/video-keyframes/{keyframe_id}/embed")
    assert embedded.status_code == 200

    bulk = client.post(f"/api/f51/studio/video-assets/{asset_id}/embed-keyframes")
    assert bulk.status_code == 200
    assert len(bulk.json().get("embeddings") or []) >= 1

    by_asset = client.get(f"/api/f51/studio/video-assets/{asset_id}/embeddings")
    assert by_asset.status_code == 200
    assert len(by_asset.json().get("embeddings") or []) >= 1

    by_project = client.get(f"/api/f51/studio/projects/{project_id}/embeddings")
    assert by_project.status_code == 200
    assert len(by_project.json().get("embeddings") or []) >= 1

    similar = client.post(
        f"/api/f51/studio/video-keyframes/{keyframe_id}/similar",
        json={"top_k": 3, "project_id": project_id},
    )
    assert similar.status_code == 200
    assert isinstance(similar.json().get("results") or [], list)
