from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_mock_video_route_exists():
    client = TestClient(app)
    response = client.get("/outputs/mock-video/sample.mp4")
    assert response.status_code == 200
    assert "X-Mock-Video-Blocker" in response.headers
