from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


def test_style_signature_build_list_compare_routes(tmp_path: Path):
    client = _client()
    created = client.post("/api/f51/studio/projects", json={"title": "Style Route Film"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    local_file = tmp_path / "route_style.mp4"
    local_file.write_text("video")

    registered = client.post(
        f"/api/f51/studio/projects/{project_id}/video-assets",
        json={"source_type": "local_file", "local_path": str(local_file), "title": "Style Clip"},
    )
    assert registered.status_code == 200
    asset_id = registered.json()["asset"]["asset_id"]

    ingest = client.post(
        f"/api/f51/studio/video-assets/{asset_id}/scene-memory/ingest",
        json={
            "visual_style": "warm neon",
            "lighting_style": "low-key",
            "pacing_profile": "slow-burn",
            "composition_patterns": ["symmetry", "static"],
            "cinematic_notes": "warm neon static dolly-in rhythm",
        },
    )
    assert ingest.status_code == 200

    built = client.post(f"/api/f51/studio/projects/{project_id}/style-signatures/build")
    assert built.status_code == 200
    sig1 = built.json()["signature"]["signature_id"]

    built2 = client.post(f"/api/f51/studio/projects/{project_id}/style-signatures/build")
    assert built2.status_code == 200
    sig2 = built2.json()["signature"]["signature_id"]

    listed = client.get(f"/api/f51/studio/projects/{project_id}/style-signatures")
    assert listed.status_code == 200
    assert len(listed.json()["signatures"]) >= 2

    fetched = client.get(f"/api/f51/studio/style-signatures/{sig1}")
    assert fetched.status_code == 200
    assert fetched.json()["signature"]["signature_id"] == sig1

    compared = client.post(
        "/api/f51/studio/style-signatures/compare",
        json={"left_signature_id": sig1, "right_signature_id": sig2},
    )
    assert compared.status_code == 200
    assert compared.json()["advisory_only"] is True
    assert compared.json()["auto_regeneration_triggered"] is False

    patterns = client.get(f"/api/f51/studio/projects/{project_id}/style-patterns")
    assert patterns.status_code == 200
    assert patterns.json()["signature_count"] >= 2
    assert patterns.json()["advisory_only"] is True
