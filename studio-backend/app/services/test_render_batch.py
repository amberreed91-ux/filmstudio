"""
Tests for scene batch rendering.

Covers:
- create_scene_batch creates one job per shot
- Shared context is identical across all jobs in a batch
- Shot position notes are correct for first, middle, last shots
- Single-shot scenes work correctly (no "continuation" note)
- Batch status endpoint returns correct counts
- batch_id is set on all jobs in the batch
- get_batch_status returns None for unknown batch_id
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.batch

from app.models import RenderJobModel
from app.services.render import RenderService
from conftest import run_async


# ── Monkeypatch for deterministic testing ───────────────────────────────────

@pytest.fixture
def _isolate_continuity_intelligence(monkeypatch):
    """
    Monkeypatch continuity_intelligence_service to prevent environment continuity
    from modifying shot totals. This ensures deterministic test behavior.
    """
    import app.services.render as render_module

    # Mock the service at the point where render.py imports it
    class MockContinuityService:
        def build_prompt_context(self, scene_id, film_id):
            return {
                "emotional_register": "",
                "active_motifs": [],
                "character_states": {},
                "tonal_direction": "",
                "continuity_anchors": [],
            }

        def resolve_environment_context(self, scene_id, film_id, shot_id, prompt, scene_data, parameters=None):
            return {
                "location_id": "",
                "prompt_lines": [],
                "selected_references": [],
                "reference_explanations": [],
                "warnings": [],
            }

    # Patch the import inside render.py's create_scene_batch function
    # We need to patch it at the module level where it's actually used
    original_import = None

    def mock_import_continuity():
        return MockContinuityService()

    # Use monkeypatch to replace the service when it's imported
    monkeypatch.setattr(
        'app.services.render._cont_svc',
        MockContinuityService(),
        raising=False
    )

    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _shots(n: int) -> List[Dict[str, Any]]:
    return [
        {
            "shot_id": f"scene_01_shot_{i+1:03d}",
            "description": f"Shot {i+1} description",
            "camera": "wide",
        }
        for i in range(n)
    ]


# ── 1. One job per shot ───────────────────────────────────────────────────────

class TestCreateSceneBatch:

    def test_creates_one_job_per_shot(self, render_service):
        svc = render_service
        shots = _shots(3)
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=shots,
        ))
        assert len(batch["job_ids"]) == 3

    def test_batch_id_is_present(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(2),
        ))
        assert batch["batch_id"]
        assert batch["batch_id"].startswith("batch-")

    def test_scene_id_in_batch(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_42",
            scene_data={}, shots=_shots(2),
        ))
        assert batch["scene_id"] == "scene_42"

    def test_status_is_pending(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(1),
        ))
        assert batch["status"] == "pending"

    def test_batch_id_set_on_all_jobs(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(3),
        ))
        for jid in batch["job_ids"]:
            job = svc.get_job(jid)
            assert job is not None
            assert job.batch_id == batch["batch_id"]

    def test_all_jobs_belong_to_correct_project(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="proj-xyz", scene_id="scene_01",
            scene_data={}, shots=_shots(2),
        ))
        for jid in batch["job_ids"]:
            job = svc.get_job(jid)
            assert job.project_id == "proj-xyz"


# ── 2. Shared context identical across all jobs ───────────────────────────────

class TestSharedContext:

    def test_shared_context_key_present(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(2),
        ))
        assert "shared_context" in batch
        assert isinstance(batch["shared_context"], dict)

    def test_shared_context_block_identical_across_jobs(self, render_service):
        """
        The continuity context block appended to each prompt must be the same
        for all shots in the batch (it's built once and reused).
        """
        svc = render_service
        shots = _shots(3)
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=shots,
        ))
        # Extract the [CINEMATIC CONTEXT] block from each job's prompt.
        context_blocks = []
        for jid in batch["job_ids"]:
            job = svc.get_job(jid)
            prompt = job.input_payload.prompt or ""
            # Find the block between [CINEMATIC CONTEXT] and [SHOT POSITION]
            if "[CINEMATIC CONTEXT]" in prompt:
                start = prompt.index("[CINEMATIC CONTEXT]")
                end = prompt.index("[SHOT POSITION]") if "[SHOT POSITION]" in prompt else len(prompt)
                context_blocks.append(prompt[start:end])
            else:
                context_blocks.append("")

        # All context blocks must be identical.
        assert len(set(context_blocks)) == 1, "Context blocks differ across jobs"


# ── 3. Shot position notes ────────────────────────────────────────────────────

class TestShotPositionNotes:
    @pytest.fixture(autouse=True)
    def _isolate(self, _isolate_continuity_intelligence):
        pass

    def _get_position_note(self, svc: RenderService, job_id: str) -> str:
        job = svc.get_job(job_id)
        prompt = job.input_payload.prompt or ""
        if "[SHOT POSITION]" in prompt:
            return prompt[prompt.index("[SHOT POSITION]"):]
        return ""

    def test_first_shot_has_opening_note(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(3),
        ))
        note = self._get_position_note(svc, batch["job_ids"][0])
        assert "Opening shot" in note
        assert "establish the space" in note.lower()

    def test_last_shot_has_closing_note(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(3),
        ))
        note = self._get_position_note(svc, batch["job_ids"][-1])
        assert "Closing shot" in note
        assert "carry emotional register forward" in note.lower()

    def test_middle_shot_has_continuation_note(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(3),
        ))
        note = self._get_position_note(svc, batch["job_ids"][1])
        assert "Continuation" in note
        assert "maintain visual consistency" in note.lower()

    def test_shot_index_and_total_in_note(self, render_service):
        svc = render_service
        # Use unique film_id to avoid state collision with other tests
        batch = run_async(svc.create_scene_batch(
            film_id="test_render_batch_film_4_shots", scene_id="scene_01",
            scene_data={}, shots=_shots(4),
        ))
        # Second shot: exact "Shot 2 of 4 in scene"
        note = self._get_position_note(svc, batch["job_ids"][1])
        assert "Shot 2 of 4 in scene" in note

    def test_five_shot_scene_middle_shots_all_continuation(self, render_service):
        svc = render_service
        # Use unique film_id to avoid state collision with other tests
        batch = run_async(svc.create_scene_batch(
            film_id="test_render_batch_film_5_shots", scene_id="scene_01",
            scene_data={}, shots=_shots(5),
        ))
        # Verify we got exactly 5 shots
        assert len(batch["job_ids"]) == 5
        # Check that middle shots (indices 1, 2, 3) have Continuation with exact totals
        note_2 = self._get_position_note(svc, batch["job_ids"][1])
        assert "Shot 2 of 5 in scene" in note_2
        assert "Continuation" in note_2
        note_3 = self._get_position_note(svc, batch["job_ids"][2])
        assert "Shot 3 of 5 in scene" in note_3
        assert "Continuation" in note_3
        note_4 = self._get_position_note(svc, batch["job_ids"][3])
        assert "Shot 4 of 5 in scene" in note_4
        assert "Continuation" in note_4


# ── 4. Single-shot scene ──────────────────────────────────────────────────────

class TestSingleShotScene:
    @pytest.fixture(autouse=True)
    def _isolate(self, _isolate_continuity_intelligence):
        pass

    def test_single_shot_creates_one_job(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(1),
        ))
        assert len(batch["job_ids"]) == 1

    def test_single_shot_has_no_continuation_note(self, render_service):
        svc = render_service
        # Use unique film_id to avoid state collision with other tests
        batch = run_async(svc.create_scene_batch(
            film_id="test_render_batch_film_1_shot", scene_id="scene_01",
            scene_data={}, shots=_shots(1),
        ))
        job = svc.get_job(batch["job_ids"][0])
        prompt = job.input_payload.prompt or ""
        assert "Continuation" not in prompt
        assert "Closing shot" not in prompt
        # Single shot uses exact "Single shot" format
        assert "Single shot — establish the space and carry the full emotional register" in prompt



# ── 5. Batch status endpoint ──────────────────────────────────────────────────

class TestBatchStatus:

    def test_get_batch_status_returns_correct_total(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(3),
        ))
        status = svc.get_batch_status(batch["batch_id"])
        assert status is not None
        assert status["total"] == 3

    def test_get_batch_status_has_required_keys(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(2),
        ))
        status = svc.get_batch_status(batch["batch_id"])
        for key in ("batch_id", "scene_id", "total", "complete", "pending", "failed", "jobs"):
            assert key in status

    def test_get_batch_status_returns_none_for_unknown_batch(self, render_service):
        svc = render_service
        result = svc.get_batch_status("nonexistent-batch-id")
        assert result is None

    def test_get_batch_status_jobs_list_length_matches_total(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(4),
        ))
        status = svc.get_batch_status(batch["batch_id"])
        assert len(status["jobs"]) == status["total"]

    def test_get_batch_status_scene_id_matches(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_99",
            scene_data={}, shots=_shots(2),
        ))
        status = svc.get_batch_status(batch["batch_id"])
        assert status["scene_id"] == "scene_99"

    def test_counts_sum_to_total(self, render_service):
        svc = render_service
        batch = run_async(svc.create_scene_batch(
            film_id="film1", scene_id="scene_01",
            scene_data={}, shots=_shots(3),
        ))
        status = svc.get_batch_status(batch["batch_id"])
        assert status["complete"] + status["pending"] + status["failed"] == status["total"]


# ── 6. Route integration ──────────────────────────────────────────────────────

class TestBatchRoutes:

    def test_render_batch_endpoint_returns_200(self, render_service):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Batch Test Film"})
        assert created.status_code == 200
        project_id = created.json()["project_id"]

        resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scenes/scene_01/render-batch",
            json={"shots": [
                {"shot_id": "scene_01_shot_001", "description": "Wide establishing shot"},
                {"shot_id": "scene_01_shot_002", "description": "Close-up on face"},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "batch_id" in data
        assert len(data["job_ids"]) == 2

    def test_render_batch_endpoint_404_for_missing_project(self, render_service):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        resp = client.post(
            "/api/f51/studio/projects/nonexistent/scenes/scene_01/render-batch",
            json={"shots": [{"shot_id": "s1", "description": "test"}]},
        )
        assert resp.status_code == 404

    def test_render_batch_endpoint_400_for_empty_shots(self, render_service):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Empty Shots Film"})
        project_id = created.json()["project_id"]
        resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scenes/scene_01/render-batch",
            json={"shots": []},
        )
        assert resp.status_code == 400

    def test_batch_status_endpoint_returns_200(self, render_service):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Status Test Film"})
        project_id = created.json()["project_id"]

        batch_resp = client.post(
            f"/api/f51/studio/projects/{project_id}/scenes/scene_01/render-batch",
            json={"shots": [{"shot_id": "scene_01_shot_001", "description": "test"}]},
        )
        batch_id = batch_resp.json()["batch_id"]

        status_resp = client.get(
            f"/api/f51/studio/projects/{project_id}/render-batch/{batch_id}",
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["batch_id"] == batch_id
        assert data["total"] == 1

    def test_batch_status_endpoint_404_for_missing_batch(self, render_service):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        created = client.post("/api/f51/studio/projects", json={"title": "Missing Batch Film"})
        project_id = created.json()["project_id"]
        resp = client.get(
            f"/api/f51/studio/projects/{project_id}/render-batch/nonexistent-batch",
        )
        assert resp.status_code == 404

    def test_batch_id_field_on_render_job_model(self, render_service):
        """RenderJobModel must have a batch_id field."""
        from app.models import RenderJobModel
        job = RenderJobModel(
            id="j1", project_id="p1", shot_id="s1", provider="simulated",
            batch_id="batch-abc123",
        )
        assert job.batch_id == "batch-abc123"

    def test_batch_id_defaults_to_none(self, render_service):
        from app.models import RenderJobModel
        job = RenderJobModel(
            id="j1", project_id="p1", shot_id="s1", provider="simulated",
        )
        assert job.batch_id is None
