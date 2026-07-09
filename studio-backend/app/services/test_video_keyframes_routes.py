from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def _create_sample_video(video_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=320x240:rate=24",
            str(video_path),
        ],
        check=True,
    )


def test_extract_and_list_video_keyframes_route(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Keyframe Route Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    generated_dir = Path(__file__).resolve().parents[2] / "outputs" / "final_films"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_path = generated_dir / "route_keyframe_demo.mp4"
    _create_sample_video(generated_path)

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "generated_output",
            "source_url": "/outputs/final_films/route_keyframe_demo.mp4",
            "title": "Route Demo",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    extracted = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/extract-keyframes",
        json={"interval_seconds": 2, "max_frames": 3},
    )
    assert extracted.status_code == 200
    keyframes = extracted.json()["keyframes"]
    assert len(keyframes) == 3

    listed = client.get(f"/api/f51/studio/video-assets/{asset_id}/keyframes")
    assert listed.status_code == 200
    assert len(listed.json()["keyframes"]) == 3

    first_keyframe_id = keyframes[0]["keyframe_id"]
    fetched = client.get(f"/api/f51/studio/video-keyframes/{first_keyframe_id}")
    assert fetched.status_code == 200
    assert fetched.json()["keyframe"]["frame_url"].startswith(f"/outputs/keyframes/{asset_id}/")


def test_extract_keyframes_missing_asset_returns_400():
    client = _client()
    response = client.post(
        "/api/f51/studio/video-assets/asset-does-not-exist/extract-keyframes",
        json={"interval_seconds": 5, "max_frames": 2},
    )
    assert response.status_code == 400
    assert "Video asset not found" in response.json()["detail"]
