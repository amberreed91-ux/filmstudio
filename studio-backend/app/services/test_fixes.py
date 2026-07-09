"""Tests for the 5 targeted fixes applied in the film-studio session.

FIX 1: Character re-extraction endpoint (POST /admin/migrate-characters)
FIX 2: Render URL recovery endpoint (POST /recover-output-urls)
       + list_jobs in-memory overlay fix
FIX 3: Theater video wiring (frontend-only, checked by tsc)
FIX 4: Previs Bay layout (frontend-only, checked by tsc)
FIX 5: Cascade delete project (DELETE /projects/{id} + cascade)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.data import get_storage
from copy import deepcopy

from app.data import get_storage
from app.models import RenderJobOutput
from app.services import render as render_module
from app.services import render_service


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_project_with_scenes(client: TestClient, project_id: str, title: str) -> None:
    """Create a project, then add scenes via PUT."""
    # Step 1: Create with just title
    resp = client.post("/api/f51/studio/projects", json={"project_id": project_id, "title": title})
    assert resp.status_code in (200, 201), resp.text

    # Step 2: Add execution_summary with scenes
    resp = client.put(f"/api/f51/studio/projects/{project_id}", json={
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": f"{project_id}_scene_001",
                    "heading": "EXT. SHORELINE - DAWN",
                    "location": "SHORELINE",
                    "time_of_day": "DAWN",
                    "emotional_tone": "melancholic",
                    "characters": ["MARA", "ELI", "COASTAL RENEWAL PROJECT", "OWNER"],
                    "text": "EXT. SHORELINE - DAWN\n\nThe shoreline stretches under pale morning light.\n\nMARA\n(whispering)\nLook at the water.\n\nELI\n(nodding)\nIt's beautiful.\n\nCOASTAL RENEWAL PROJECT aims to restore the beach.\n\nOWNER\nWe need a plan.",
                },
                {
                    "scene_id": f"{project_id}_scene_002",
                    "heading": "INT. CABIN - NIGHT",
                    "location": "CABIN",
                    "time_of_day": "NIGHT",
                    "emotional_tone": "tense",
                    "characters": ["ELI", "REPRESENTATIVE", "THE LAST TIDE"],
                    "text": "INT. CABIN - NIGHT\n\nA fire crackles.\n\nELI\n(staring into flames)\nWhat news?\n\nREPRESENTATIVE\n(gravely)\nIt's over.\n\nTHE LAST TIDE washes over the rocks in the distance.",
                },
            ],
        },
    })
    assert resp.status_code == 200, resp.text


def _render_job_payload(
    job_id: str,
    project_id: str,
    shot_id: str,
    status: str = "complete",
    provider: str = "simulated",
    asset_url: str = "",
) -> Dict[str, Any]:
    return {
        "id": job_id,
        "project_id": project_id,
        "shot_id": shot_id,
        "status": status,
        "provider": provider,
        "progress": 100,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "output_payload": {"asset_url": asset_url, "metadata": {}} if asset_url else None,
    }


# ── FIX 1: Character Migration ──────────────────────────────────────────────

class TestFix1CharacterMigration:
    """POST /admin/migrate-characters removes invalid character names."""

    def test_migrate_characters_removes_invalid(self, client: TestClient):
        pid = f"test-fix1-{int(time.time())}"
        _create_project_with_scenes(client, pid, "Fix 1 Test")

        # Run migration
        resp = client.post("/api/f51/studio/admin/migrate-characters")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["projects_checked"] >= 1
        assert data["characters_removed"] >= 3

        # Verify scene 1: COASTAL RENEWAL PROJECT and OWNER removed, MARA/ELI kept
        resp = client.get(f"/api/f51/studio/projects/{pid}/scenes/{pid}_scene_001")
        assert resp.status_code == 200, resp.text
        chars = resp.json()["scene"].get("characters", [])
        assert "MARA" in chars
        assert "ELI" in chars
        assert "COASTAL RENEWAL PROJECT" not in chars
        assert "OWNER" not in chars

        # Verify scene 2: REPRESENTATIVE is kept (it's a dialogue cue in the text),
        # THE LAST TIDE removed (it's not a dialogue cue), ELI kept
        resp = client.get(f"/api/f51/studio/projects/{pid}/scenes/{pid}_scene_002")
        assert resp.status_code == 200, resp.text
        chars = resp.json()["scene"].get("characters", [])
        assert "ELI" in chars
        assert "REPRESENTATIVE" in chars  # dialogue cue in scene text
        assert "THE LAST TIDE" not in chars

    def test_migrate_characters_empty_db_does_not_crash(self, client: TestClient):
        # Should handle empty/no project gracefully
        resp = client.post("/api/f51/studio/admin/migrate-characters")
        assert resp.status_code == 200, resp.text


# ── FIX 2: Render URL Recovery ──────────────────────────────────────────────

class TestFix2RenderUrlRecovery:
    """POST /recover-output-urls restores URLs for simulated jobs,
    demotes real-provider stale jobs, and list_jobs preserves in-memory."""

    SIMULATED_PLACEHOLDER = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"

    def test_recover_simulated_job_without_url(self, client: TestClient):
        pid = f"test-fix2a-{int(time.time())}"
        _create_project_with_scenes(client, pid, "Fix 2a Test")

        # Create a simulated job without output URL
        job = render_service.create_job(
            project_id=pid,
            shot_id=f"{pid}_scene_001_shot_001",
            provider="simulated",
            prompt="test prompt",
        )
        # Manually mark it complete with no output_url
        job.status = "complete"
        job.output_payload = None
        # Save to storage
        render_module._storage.save_job(job)

        # Recover
        resp = client.post("/api/f51/studio/render/recover-output-urls")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["recovered"] >= 1

        # Verify the job now has a URL
        jobs = render_service.list_jobs(pid)
        recovered_job = next((j for j in jobs if j.id == job.id), None)
        assert recovered_job is not None
        assert recovered_job.output_payload is not None
        assert recovered_job.output_payload.asset_url == self.SIMULATED_PLACEHOLDER

    def test_demote_real_provider_stale_complete(self, client: TestClient):
        pid = f"test-fix2b-{int(time.time())}"
        _create_project_with_scenes(client, pid, "Fix 2b Test")

        # Create a job and set to real provider (create_job overrides "runway" -> "local")
        job = render_service.create_job(
            project_id=pid,
            shot_id=f"{pid}_scene_001_shot_001",
            provider="runway",
            prompt="test prompt",
        )
        job.provider = "runway_hq"  # bypass the create_job override
        job.status = "complete"
        job.output_payload = None
        render_module._storage.save_job(job)

        # Recover — should demote to failed
        resp = client.post("/api/f51/studio/render/recover-output-urls")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["demoted"] >= 1

        # Verify job is now failed
        jobs = render_service.list_jobs(pid)
        demoted_job = next((j for j in jobs if j.id == job.id), None)
        assert demoted_job is not None
        assert demoted_job.status == "failed"

    def test_list_jobs_in_memory_overlay(self, client: TestClient):
        """In-memory jobs should overlay persisted jobs — not be overwritten."""
        pid = f"test-fix2c-{int(time.time())}"
        _create_project_with_scenes(client, pid, "Fix 2c Test")

        # Create a job via service (in-memory + persisted)
        job = render_service.create_job(
            project_id=pid,
            shot_id=f"{pid}_scene_001_shot_001",
            provider="simulated",
            prompt="test prompt",
        )
        job.status = "complete"
        job.output_payload = RenderJobOutput(asset_url="http://example.com/video.mp4")

        # Simulate stale DB record — save old version without URL to storage
        job_stale = deepcopy(job)
        job_stale.output_payload = None
        render_module._storage.save_job(job_stale)

        # Now update in-memory with correct URL
        render_service._jobs[job.id] = job

        # list_jobs should return in-memory version (with URL), not stale DB
        jobs = render_service.list_jobs(pid)
        live = next((j for j in jobs if j.id == job.id), None)
        assert live is not None
        assert live.output_payload is not None
        assert live.output_payload.asset_url == "http://example.com/video.mp4"


# ── FIX 5: Cascade Delete ───────────────────────────────────────────────────

class TestFix5CascadeDelete:
    """DELETE /projects/{id} cascades to all child tables."""

    def _count_child_records(self, storage, project_id: str) -> int:
        """Count records across all child tables for a project."""
        child_tables = [
            "render_jobs", "universe_nodes", "universe_relationships",
            "project_memories", "memory_versions", "scene_memories",
            "character_memories", "style_memories", "review_memories",
            "crew_tasks", "crew_task_log", "visual_embeddings",
            "cinematic_memory_records", "continuity_issues",
            "director_signatures", "style_signatures", "style_drift_issues",
            "short_film_reviews", "clip_revisions", "final_short_film_packages",
            "workflow_executions", "video_keyframes", "video_frame_analyses",
            "session_debriefs", "export_packages", "pitch_decks",
            "previs_images", "surfaced_disagreements",
        ]
        total = 0
        for table in child_tables:
            try:
                with storage._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE project_id = ?", (project_id,))
                    row = cursor.fetchone()
                    total += row["cnt"] if row else 0
            except Exception:
                pass
        return total

    def test_cascade_delete_removes_child_records(self, client: TestClient):
        pid = f"test-fix5-{int(time.time())}"
        _create_project_with_scenes(client, pid, "Fix 5 Test")

        # Create a render job to verify child record cleanup
        job = render_service.create_job(
            project_id=pid,
            shot_id=f"{pid}_scene_001_shot_001",
            provider="simulated",
            prompt="test prompt",
        )
        render_module._storage.save_job(job)

        storage = get_storage("sqlite")

        # Verify records exist
        pre_count = self._count_child_records(storage, pid)
        assert pre_count >= 1, f"Expected at least 1 child record, got {pre_count}"

        # Delete project via API
        resp = client.delete(f"/api/f51/studio/projects/{pid}")
        assert resp.status_code == 200, resp.text

        # Verify project is gone
        resp = client.get(f"/api/f51/studio/projects/{pid}")
        assert resp.status_code == 404

        # Verify no child records remain
        post_count = self._count_child_records(storage, pid)
        assert post_count == 0, f"Expected 0 child records after cascade delete, got {post_count}"

    def test_cascade_delete_nonexistent_project_returns_404(self, client: TestClient):
        resp = client.delete("/api/f51/studio/projects/nonexistent-project-id")
        assert resp.status_code == 404


# ── Conftest override ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create a TestClient for the FastAPI app, initializing render storage."""
    import app.services.render
    from app.data import get_storage as _get_storage
    storage = _get_storage("sqlite")
    if storage:
        app.services.render.set_storage(storage)

    from main import app
    return TestClient(app)
