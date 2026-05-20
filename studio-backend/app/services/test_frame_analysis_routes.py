from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from app.services.frame_analysis_service import frame_analysis_service


def _client() -> TestClient:
    return TestClient(app)


def _create_sample_video(path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=24",
            str(path),
        ],
        check=True,
    )


def test_analyze_keyframes_and_list_routes(monkeypatch):
    monkeypatch.setenv("VISION_ANALYSIS_PROVIDER", "mock_local")
    frame_analysis_service._vision_adapter = None
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Frame Analysis Route Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    generated_dir = Path(__file__).resolve().parents[2] / "outputs" / "final_films"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_path = generated_dir / "route_frame_analysis_demo.mp4"
    _create_sample_video(generated_path)

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "generated_output",
            "source_url": "/outputs/final_films/route_frame_analysis_demo.mp4",
            "title": "Route Demo",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    extracted = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/extract-keyframes",
        json={"interval_seconds": 2, "max_frames": 3, "overwrite": True},
    )
    assert extracted.status_code == 200
    keyframes = extracted.json().get("keyframes") or []
    assert len(keyframes) >= 1

    analyzed = client.post(f"/api/f51/studio/video-assets/{asset_id}/analyze-keyframes", json={})
    assert analyzed.status_code == 200
    analyses = analyzed.json().get("analyses") or []
    assert len(analyses) >= 1

    listed_asset = client.get(f"/api/f51/studio/video-assets/{asset_id}/frame-analyses")
    assert listed_asset.status_code == 200
    assert len(listed_asset.json().get("analyses") or []) >= 1

    listed_project = client.get(f"/api/f51/studio/projects/{project_id}/frame-analyses")
    assert listed_project.status_code == 200
    assert len(listed_project.json().get("analyses") or []) >= 1


def test_unavailable_analysis_route(monkeypatch):
    monkeypatch.delenv("VISION_ANALYSIS_PROVIDER", raising=False)
    frame_analysis_service._vision_adapter = None
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Frame Analysis Unavailable"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    generated_dir = Path(__file__).resolve().parents[2] / "outputs" / "final_films"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_path = generated_dir / "route_frame_analysis_unavailable.mp4"
    _create_sample_video(generated_path)

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={
            "source_type": "generated_output",
            "source_url": "/outputs/final_films/route_frame_analysis_unavailable.mp4",
            "title": "Route Demo",
        },
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    extracted = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/extract-keyframes",
        json={"interval_seconds": 2, "max_frames": 3, "overwrite": True},
    )
    assert extracted.status_code == 200
    keyframe_id = (extracted.json().get("keyframes") or [])[0]["keyframe_id"]

    row = client.post(f"/api/f51/studio/video-keyframes/{keyframe_id}/analyze")
    assert row.status_code == 200
    payload = row.json().get("analysis") or {}
    assert payload.get("status") == "unavailable"
    assert (payload.get("metadata") or {}).get("message") == "vision analysis not configured"
