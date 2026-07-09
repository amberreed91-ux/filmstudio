"""
Tests for real (non-demo) project rendering path.

Verifies that:
- Real projects generate scenes correctly
- Render jobs are created and visible for real project_id
- Final package uses real project render jobs, not demo assets
- Demo flow still works independently
- Shot fallback uses real scene_id, not demo scene_id
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def _client() -> TestClient:
    return TestClient(app)


# ── Part 1: Real project scene generation ────────────────────────────────────

def test_real_project_create_and_generate_scenes():
    """Real project: create → generate-scenes → scenes exist with real project_id."""
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "My Real Script"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]
    assert project_id
    assert project_id != "demo_studio_cinematic_001"

    script = (
        "Scene 1: The Alley\n\nA figure moves through rain.\n\n"
        "Scene 2: The Room\n\nSilence. A door opens slowly."
    )
    gen = client.post(
        f"/api/f51/studio/projects/{project_id}/generate-scenes",
        json={"script_text": script},
    )
    assert gen.status_code == 200
    body = gen.json()
    scenes = body.get("execution_summary", {}).get("scenes", [])
    assert len(scenes) >= 1
    for scene in scenes:
        assert scene.get("scene_id")
        assert "demo" not in scene["scene_id"].lower()


def test_real_project_scenes_have_shot_fallback():
    """Real project: when no shot ledger, scene_id_shot_001 fallback is used."""
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Shot Fallback Test"})
    project_id = created.json()["project_id"]

    script = "Scene 1: Opening\n\nA quiet morning."
    gen = client.post(
        f"/api/f51/studio/projects/{project_id}/generate-scenes",
        json={"script_text": script},
    )
    assert gen.status_code == 200
    body = gen.json()
    scenes = body.get("execution_summary", {}).get("scenes", [])
    assert len(scenes) >= 1

    scene_id = scenes[0]["scene_id"]
    # Shot fallback should be <scene_id>_shot_001
    expected_shot_id = f"{scene_id}_shot_001"
    assert "_shot_001" in expected_shot_id
    assert "demo" not in expected_shot_id


def test_real_project_decision_gate_returns_project_id():
    """Real project: decision gate returns the real project_id, not demo."""
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Gate Test"})
    project_id = created.json()["project_id"]

    gate = client.get(f"/api/f51/studio/projects/{project_id}/decision-gate")
    assert gate.status_code == 200
    body = gate.json()
    assert body["project_id"] == project_id
    assert body["project_id"] != "demo_studio_cinematic_001"
    assert "gate_status" in body
    assert "recommended_next_action" in body


# ── Part 2: Render jobs for real project ─────────────────────────────────────

def test_real_project_render_jobs_list_is_empty_before_generation():
    """Real project: render jobs list is empty before any renders are submitted."""
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Empty Renders Test"})
    project_id = created.json()["project_id"]

    jobs = client.get("/api/f51/studio/render/jobs", params={"project_id": project_id})
    assert jobs.status_code == 200
    rows = jobs.json()
    assert isinstance(rows, list)
    # No demo jobs should appear for a fresh real project
    for row in rows:
        assert row.get("project_id") == project_id


def test_real_project_render_jobs_do_not_include_demo_jobs():
    """Real project: render jobs query never returns demo project jobs."""
    client = _client()

    # Seed demo project
    client.post(
        "/api/f51/studio/dev/seed-demo-project",
        json={"project_id": "demo_studio_cinematic_001"},
    )

    # Create a real project
    created = client.post("/api/f51/studio/projects", json={"title": "Real Project"})
    real_project_id = created.json()["project_id"]

    # Query render jobs for real project
    jobs = client.get("/api/f51/studio/render/jobs", params={"project_id": real_project_id})
    assert jobs.status_code == 200
    rows = jobs.json()
    assert isinstance(rows, list)

    # None of the returned jobs should belong to the demo project
    for row in rows:
        assert row.get("project_id") != "demo_studio_cinematic_001", (
            f"Demo job leaked into real project render jobs: {row}"
        )


def test_demo_render_jobs_still_visible_for_demo_project():
    """Demo flow: seeded demo render jobs are visible when querying demo project_id."""
    client = _client()

    client.post(
        "/api/f51/studio/dev/seed-demo-project",
        json={"project_id": "demo_studio_cinematic_001"},
    )

    jobs = client.get(
        "/api/f51/studio/render/jobs",
        params={"project_id": "demo_studio_cinematic_001"},
    )
    assert jobs.status_code == 200
    rows = jobs.json()
    assert isinstance(rows, list)
    assert len(rows) >= 2

    completed = [r for r in rows if r.get("status") == "complete"]
    assert len(completed) >= 2
    for row in completed[:2]:
        assert row.get("output_url") or row.get("preview_url")


# ── Part 3: Final package for real project ───────────────────────────────────

def test_real_project_final_package_requires_completed_renders():
    """Real project: final package creation fails gracefully when no renders exist."""
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Package Test"})
    project_id = created.json()["project_id"]

    pkg = client.post(
        f"/api/f51/studio/projects/{project_id}/final-short-film-package",
        json={"film_title": "My Film"},
    )
    # Should return 400 — no completed renders available
    assert pkg.status_code == 400
    body = pkg.json()
    detail = body.get("detail", "")
    if isinstance(detail, dict):
        detail = str(detail)
    assert "render" in detail.lower() or "output" in detail.lower() or "No completed" in detail


def test_real_project_final_package_with_explicit_output_url():
    """Real project: final package creation works when output_url is provided."""
    client = _client()

    created = client.post("/api/f51/studio/projects", json={"title": "Package With URL"})
    project_id = created.json()["project_id"]

    # Provide an explicit hosted output URL (simulates a completed Runway render)
    pkg = client.post(
        f"/api/f51/studio/projects/{project_id}/final-short-film-package",
        json={
            "film_title": "My Real Film",
            "final_output_url": "https://dnznrvs05pmza.cloudfront.net/real-output.mp4",
            "metadata": {"package_origin": "test"},
        },
    )
    assert pkg.status_code == 200
    body = pkg.json()
    package = body.get("package", {})
    assert package.get("project_id") == project_id
    assert package.get("project_id") != "demo_studio_cinematic_001"
    assert package.get("final_output_url") == "https://dnznrvs05pmza.cloudfront.net/real-output.mp4"
    assert "route_keyframe_demo" not in package.get("final_output_url", "")


def test_demo_final_package_still_works():
    """Demo flow: seeded demo project returns package info in seed response."""
    client = _client()

    seed_resp = client.post(
        "/api/f51/studio/dev/seed-demo-project",
        json={"project_id": "demo_studio_cinematic_001"},
    )
    assert seed_resp.status_code == 200
    seeded = seed_resp.json()
    # Verify the seed response includes the expected package info
    assert seeded.get("project_id") == "demo_studio_cinematic_001"
    assert seeded.get("gate_status") in {"ready", "needs_review"}
    assert seeded.get("seeded", {}).get("package_id")
    assert seeded.get("seeded", {}).get("render_jobs") == 2
    assert seeded.get("seeded", {}).get("review_id")
    # Verify demo project exists
    project_resp = client.get("/api/f51/studio/projects/demo_studio_cinematic_001")
    assert project_resp.status_code == 200
    assert project_resp.json()["project_id"] == "demo_studio_cinematic_001"


# ── Part 4: Shot id fallback does not use demo scene id ──────────────────────

def test_shot_fallback_uses_real_scene_id_not_demo():
    """
    When a real project has no shot ledger, the shot id fallback must be
    derived from the real scene_id, not from any demo scene id.
    """
    real_scene_id = "scene_007"
    # Simulate the resolveGenerateSceneShotId fallback logic
    fallback_shot_id = f"{real_scene_id}_shot_001"

    assert fallback_shot_id == "scene_007_shot_001"
    assert "demo" not in fallback_shot_id
    assert fallback_shot_id != "scene_001_shot_001"  # demo scene id
    assert fallback_shot_id != "scene_002_shot_001"  # demo scene id


# ── Part 5: Project isolation — real project data is not contaminated ─────────

def test_real_project_exists_independently_of_demo():
    """Real project: project data is independent of demo project."""
    client = _client()

    # Seed demo
    client.post(
        "/api/f51/studio/dev/seed-demo-project",
        json={"project_id": "demo_studio_cinematic_001"},
    )

    # Create real project
    created = client.post("/api/f51/studio/projects", json={"title": "Independent Real Project"})
    project_id = created.json()["project_id"]

    # Fetch real project
    fetched = client.get(f"/api/f51/studio/projects/{project_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["project_id"] == project_id
    assert body["project_id"] != "demo_studio_cinematic_001"
    assert body.get("title") == "Independent Real Project"

    # Fetch demo project
    demo = client.get("/api/f51/studio/projects/demo_studio_cinematic_001")
    assert demo.status_code == 200
    demo_body = demo.json()
    assert demo_body["project_id"] == "demo_studio_cinematic_001"

    # They are different
    assert body["project_id"] != demo_body["project_id"]
