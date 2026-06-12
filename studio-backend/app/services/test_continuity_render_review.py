"""
Tests for post-render continuity review.

Covers:
- review_render_output returns passed=True with uncertainty when no graph exists
- review_render_output detects drift when scene contradicts active graph nodes
- review_render_output never throws — always returns a valid dict
- continuity_review is attached to completed render jobs
"""
from __future__ import annotations

import asyncio
from app.models import CinematicMemoryRecord, RenderJobModel, RenderJobOutput
from app.services.continuity_intelligence_service import ContinuityIntelligenceService
from app.services.render import RenderService, _run_continuity_review


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mem(
    memory_id: str,
    project_id: str,
    emotional_tags: list[str] | None = None,
    visual_tags: list[str] | None = None,
    composition_tags: list[str] | None = None,
    searchable_text: str = "",
) -> CinematicMemoryRecord:
    return CinematicMemoryRecord(
        memory_id=memory_id,
        project_id=project_id,
        asset_id="asset_001",
        keyframe_id="kf_001",
        emotional_tags=emotional_tags or [],
        visual_tags=visual_tags or [],
        composition_tags=composition_tags or [],
        searchable_text=searchable_text,
    )


class _StorageStub:
    def __init__(self, memories: list[CinematicMemoryRecord] | None = None):
        self._memories = memories or []

    def list_cinematic_memory_for_project(self, project_id: str) -> list[CinematicMemoryRecord]:
        return [m for m in self._memories if m.project_id == project_id]


def _run(coro):
    return asyncio.run(coro)


# ── review_render_output: no graph ────────────────────────────────────────────

def test_review_render_output_passed_when_no_storage():
    svc = ContinuityIntelligenceService(storage=None)
    result = _run(svc.review_render_output(
        scene_id="scene_001", film_id="film_001",
        render_job_id="job_001", render_output_url="https://cdn.example.com/out.mp4",
        scene_data={},
    ))
    assert result["passed"] is True
    assert result["drift_detected"] is False
    assert isinstance(result["uncertainty_notes"], list)
    assert len(result["uncertainty_notes"]) > 0


def test_review_render_output_passed_when_no_memories():
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories=[]))
    result = _run(svc.review_render_output(
        scene_id="scene_001", film_id="film_001",
        render_job_id="job_001", render_output_url="",
        scene_data={},
    ))
    assert result["passed"] is True
    assert result["drift_detected"] is False
    assert result["uncertainty_notes"]


def test_review_render_output_passed_when_film_id_empty():
    storage = _StorageStub(memories=[_mem("m1", "film_001", emotional_tags=["tense"])])
    svc = ContinuityIntelligenceService(storage=storage)
    result = _run(svc.review_render_output(
        scene_id="scene_001", film_id="",
        render_job_id="job_001", render_output_url="",
        scene_data={},
    ))
    assert result["passed"] is True


# ── review_render_output: drift detection ─────────────────────────────────────

def test_review_render_output_detects_emotional_drift():
    # Prior arc is escalating (tense × 2), new scene is calm
    memories = [
        _mem("m1", "film_x", emotional_tags=["tense"], searchable_text="scene_001"),
        _mem("m2", "film_x", emotional_tags=["tense"], searchable_text="scene_002"),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    result = _run(svc.review_render_output(
        scene_id="scene_003", film_id="film_x",
        render_job_id="job_003", render_output_url="",
        scene_data={"emotionalTone": "calm"},
    ))
    assert result["drift_detected"] is True
    assert result["passed"] is False
    assert any("emotional_tone" in f for f in result["continuity_flags"])
    assert len(result["drift_notes"]) > 0


def test_review_render_output_detects_visual_motif_drift():
    # Established motifs: neon, rain (each ×2). New scene has completely different tags.
    memories = [
        _mem("m1", "film_x", visual_tags=["neon", "rain"], searchable_text="scene_001"),
        _mem("m2", "film_x", visual_tags=["neon", "rain"], searchable_text="scene_002"),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    result = _run(svc.review_render_output(
        scene_id="scene_003", film_id="film_x",
        render_job_id="job_003", render_output_url="",
        scene_data={"tags": ["sunlight", "desert", "wide_open"]},
    ))
    assert result["drift_detected"] is True
    assert any("visual_motifs" in f for f in result["continuity_flags"])


def test_review_render_output_no_drift_when_consistent():
    memories = [
        _mem("m1", "film_x", emotional_tags=["tense"], visual_tags=["neon"],
             searchable_text="scene_001"),
        _mem("m2", "film_x", emotional_tags=["tense"], visual_tags=["neon"],
             searchable_text="scene_002"),
    ]
    svc = ContinuityIntelligenceService(storage=_StorageStub(memories))
    result = _run(svc.review_render_output(
        scene_id="scene_003", film_id="film_x",
        render_job_id="job_003", render_output_url="",
        scene_data={"emotionalTone": "tense", "tags": ["neon"]},
    ))
    assert result["drift_detected"] is False
    assert result["passed"] is True


# ── review_render_output: never throws ───────────────────────────────────────

def test_review_render_output_never_throws_on_bad_scene_data():
    svc = ContinuityIntelligenceService(storage=None)
    # Deliberately malformed inputs
    result = _run(svc.review_render_output(
        scene_id="", film_id="",
        render_job_id="", render_output_url="",
        scene_data=None,  # type: ignore[arg-type]
    ))
    assert isinstance(result, dict)
    assert "passed" in result


def test_review_render_output_never_throws_when_storage_raises():
    class _BrokenStorage:
        def list_cinematic_memory_for_project(self, project_id: str):
            raise RuntimeError("db exploded")

    svc = ContinuityIntelligenceService(storage=_BrokenStorage())
    result = _run(svc.review_render_output(
        scene_id="scene_001", film_id="film_001",
        render_job_id="job_001", render_output_url="",
        scene_data={},
    ))
    assert isinstance(result, dict)
    assert result["passed"] is True


def test_review_render_output_result_always_has_required_keys():
    svc = ContinuityIntelligenceService(storage=None)
    result = _run(svc.review_render_output(
        scene_id="scene_001", film_id="film_001",
        render_job_id="job_001", render_output_url="",
        scene_data={},
    ))
    for key in ("passed", "drift_detected", "drift_notes",
                "continuity_flags", "advisory", "uncertainty_notes"):
        assert key in result, f"Missing key: {key}"


# ── continuity_review attached to completed jobs ──────────────────────────────

def test_run_continuity_review_attaches_result_to_job():
    job = RenderJobModel(
        id="job-review-1",
        project_id="proj_review",
        shot_id="scene_001_shot_001",
        provider="simulated",
        status="complete",
        output_payload=RenderJobOutput(
            asset_url="https://cdn.example.com/out.mp4",
            thumbnail_url="",
            metadata={},
        ),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    assert job.continuity_review is None
    _run(_run_continuity_review(job))
    assert job.continuity_review is not None
    assert "passed" in job.continuity_review


def test_run_continuity_review_never_raises():
    """_run_continuity_review must never raise even if the service is broken."""
    import app.services.continuity_intelligence_service as cont_module

    class _BrokenSvc:
        async def review_render_output(self, **kwargs):
            raise RuntimeError("broken")

    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _BrokenSvc()  # type: ignore[assignment]
    try:
        job = RenderJobModel(
            id="job-broken", project_id="p", shot_id="s",
            provider="simulated", status="complete",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        # Must not raise
        _run(_run_continuity_review(job))
        # continuity_review stays None when service fails
        assert job.continuity_review is None
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]


def test_render_job_model_has_continuity_review_field():
    job = RenderJobModel(id="j", project_id="p", shot_id="s", provider="runway")
    assert hasattr(job, "continuity_review")
    assert job.continuity_review is None
    job.continuity_review = {"passed": True, "drift_detected": False}
    assert job.continuity_review["passed"] is True
