from __future__ import annotations

from app.models.shot_sequence_plan import ShotSequencePlan
from app.services.script_parser import ScriptParser
from app.services.shot_sequence_service import shot_sequence_service


def test_shot_sequence_plan_contains_required_cinematic_shot_types():
    plan = shot_sequence_service.build_shot_sequence_plan(
        "scene_001",
        {"pacing": "balanced", "emotional_curve": "escalating"},
    )
    assert isinstance(plan, ShotSequencePlan)
    shot_types = [step.shot_type for step in plan.steps]
    assert shot_types == [
        "establishing_shot",
        "medium_shot",
        "close_up",
        "transition_shot",
        "emotional_detail_shot",
    ]


def test_shot_sequence_plan_fast_pacing_keeps_cinematic_flow_and_emotional_escalation():
    plan = shot_sequence_service.build_shot_sequence_plan(
        "scene_002",
        {"pacing": "fast", "emotional_curve": "escalating"},
    )
    shot_types = [step.shot_type for step in plan.steps]
    assert shot_types[0] == "establishing_shot"
    assert shot_types[-1] == "emotional_detail_shot"
    intensities = [step.emotional_intensity for step in plan.steps]
    assert intensities == sorted(intensities)


def test_build_shot_candidates_preserves_single_shot_default_compatibility():
    parser = ScriptParser()
    scene_index = {"scene_001": {"scene_id": "scene_001"}}
    candidates = parser.build_shot_candidates(scene_index, {})
    assert candidates == [
        {"scene_id": "scene_001", "shot_id": "shot_scene_001_001", "source_refs": []}
    ]


def test_build_shot_candidates_generates_multi_shot_sequence_when_enabled():
    parser = ScriptParser()
    scene_index = {
        "scene_001": {
            "scene_id": "scene_001",
            "multi_shot_enabled": True,
            "pacing": "balanced",
            "emotional_curve": "escalating",
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {"scene_001": ["ref_001"]})
    assert len(candidates) == 5
    assert [item["shot_type"] for item in candidates] == [
        "establishing_shot",
        "medium_shot",
        "close_up",
        "transition_shot",
        "emotional_detail_shot",
    ]
    assert [item["shot_id"] for item in candidates] == [
        "shot_scene_001_001",
        "shot_scene_001_002",
        "shot_scene_001_003",
        "shot_scene_001_004",
        "shot_scene_001_005",
    ]


def test_build_scene_render_jobs_generates_multiple_jobs_per_scene():
    parser = ScriptParser()
    shot_candidates = [
        {"scene_id": "scene_001", "shot_id": "shot_scene_001_001", "shot_type": "establishing_shot"},
        {"scene_id": "scene_001", "shot_id": "shot_scene_001_002", "shot_type": "medium_shot"},
        {"scene_id": "scene_001", "shot_id": "shot_scene_001_003", "shot_type": "close_up"},
    ]
    jobs = parser.build_scene_render_jobs(shot_candidates, "mock")["scene_render_jobs"]
    assert len(jobs) == 3
    assert all(job["status"] == "queued" for job in jobs)
    assert all(job["scene_id"] == "scene_001" for job in jobs)
    summary = parser.build_scene_render_job_summary(jobs)["scene_render_job_summary"]
    assert summary == {"total_jobs": 3, "jobs_per_scene": {"scene_001": 3}}


def test_shot_candidates_carry_identity_context_and_drift_warnings_when_present():
    parser = ScriptParser()
    scene_index = {
        "scene_001": {
            "scene_id": "scene_001",
            "provider_identity_context": {"advisory_only": True, "identity_lines": ["Elena | silhouette: long coat"]},
            "identity_drift_warnings": ["Elena: facial identity not set; drift risk across shots."],
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert candidates
    assert candidates[0]["provider_identity_context"]["advisory_only"] is True
    assert candidates[0]["identity_drift_warnings"]
