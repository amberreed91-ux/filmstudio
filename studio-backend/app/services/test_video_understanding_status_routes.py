from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.data import get_storage
from app.models import VideoKeyframe
from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_video_understanding_status_routes_show_incomplete_then_complete(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "VU Route Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    local_file = tmp_path / "vu_route.mp4"
    local_file.write_text("video")
    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "local_file", "local_path": str(local_file), "title": "VU Clip"},
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    incomplete = client.get(f"/api/f51/studio/video-assets/{asset_id}/understanding-status")
    assert incomplete.status_code == 200
    assert incomplete.json()["status"]["understanding_enabled"] is False

    storage = get_storage("sqlite")
    keyframe = storage.save_video_keyframe(
        VideoKeyframe(
            keyframe_id="kf-route-1",
            asset_id=asset_id,
            project_id=project_id,
            timestamp_seconds=0.0,
            frame_path="/tmp/fake-route.jpg",
            frame_url=None,
            frame_index=0,
            extraction_reason="interval",
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={},
        )
    )

    frame_analysis = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/frame-analysis",
        json={
            "keyframe_id": keyframe.keyframe_id,
            "caption": "Frame caption",
            "mood_tags": ["tense"],
            "lighting_tags": ["low-key"],
            "camera_tags": ["static"],
        },
    )
    assert frame_analysis.status_code == 200

    memory = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/scene-memory/ingest",
        json={
            "dominant_mood": "tense",
            "visual_style": "noir",
            "lighting_style": "low-key",
            "pacing_profile": "slow",
            "composition_patterns": ["symmetry"],
            "cinematic_notes": "memory note",
        },
    )
    assert memory.status_code == 200

    complete = client.get(f"/api/f51/studio/video-assets/{asset_id}/understanding-status")
    assert complete.status_code == 200
    assert complete.json()["status"]["understanding_enabled"] is True

    project_status = client.get(f"/api/f51/studio/projects/{project_id}/video-understanding-status")
    assert project_status.status_code == 200
    assert project_status.json()["understanding_enabled"] is True
