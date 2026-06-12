from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def _create_video(video_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=24",
            str(video_path),
        ],
        check=True,
    )


def test_detect_and_list_shots_route(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Shot Route Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    generated_dir = Path(__file__).resolve().parents[2] / "outputs" / "final_films"
    generated_dir.mkdir(parents=True, exist_ok=True)
    video_path = generated_dir / "route_shot_demo.mp4"
    _create_video(video_path)

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "generated_output",
            "source_url": "/outputs/final_films/route_shot_demo.mp4",
            "title": "Route Shot Demo",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    detected = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/detect-shots",
        json={"threshold": 0.2, "overwrite": True},
    )
    assert detected.status_code == 200
    assert isinstance(detected.json()["shots"], list)

    listed = client.get(f"/api/f51/studio/video-assets/{asset_id}/shots")
    assert listed.status_code == 200
    assert isinstance(listed.json()["shots"], list)


def test_detect_shots_invalid_threshold():
    client = _client()
    response = client.post(
        "/api/f51/studio/video-assets/asset-does-not-exist/detect-shots",
        json={"threshold": 2.0},
    )
    assert response.status_code == 400
    assert "threshold" in response.json()["detail"]
