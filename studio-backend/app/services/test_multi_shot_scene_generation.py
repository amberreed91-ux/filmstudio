from __future__ import annotations

import copy

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


def test_build_shot_candidates_single_shot_unchanged_without_shot_specs():
    parser = ScriptParser()
    scene_index = {"scene_001": {"scene_id": "scene_001"}}
    candidates = parser.build_shot_candidates(scene_index, {})
    assert candidates == [
        {"scene_id": "scene_001", "shot_id": "shot_scene_001_001", "source_refs": []}
    ]


def test_build_shot_candidates_empty_shot_specs_falls_through_to_single_shot():
    parser = ScriptParser()
    scene_index = {"scene_001": {"scene_id": "scene_001", "shot_specs": []}}
    candidates = parser.build_shot_candidates(scene_index, {})
    assert candidates == [
        {"scene_id": "scene_001", "shot_id": "shot_scene_001_001", "source_refs": []}
    ]


def test_build_shot_candidates_mixed_single_and_split_scenes_preserve_single_behavior():
    parser = ScriptParser()
    scene_index = {
        "scene_001": {"scene_id": "scene_001"},
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [
                {"shot_type": "establishing_medium", "dialogue_line_range": {"start": 0, "end": 2}, "speakers": ["DRE", "MAYA"]},
                {"shot_type": "close_up_reverse", "dialogue_line_range": {"start": 3, "end": 5}, "speakers": ["MAYA", "DRE"]},
            ],
        },
        "scene_003": {"scene_id": "scene_003"},
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert candidates[0] == {
        "scene_id": "scene_001",
        "shot_id": "shot_scene_001_001",
        "source_refs": [],
    }
    assert candidates[3] == {
        "scene_id": "scene_003",
        "shot_id": "shot_scene_003_001",
        "source_refs": [],
    }


def test_build_shot_candidates_generates_n_candidates_from_shot_specs():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [
                {
                    "shot_type": "establishing_medium",
                    "dialogue_line_range": {"start": 0, "end": 2},
                    "speakers": ["DRE", "MAYA"],
                    "estimated_seconds": 5.7,
                    "recommended_seconds": 5.7,
                    "split_reason": "speaker_turn_grouping",
                },
                {
                    "shot_type": "close_up_reverse",
                    "dialogue_line_range": {"start": 3, "end": 5},
                    "speakers": ["MAYA", "DRE"],
                    "estimated_seconds": 9.3,
                    "recommended_seconds": 9.3,
                    "split_reason": "speaker_turn_grouping",
                },
                {
                    "shot_type": "reaction_close",
                    "dialogue_line_range": {"start": 6, "end": 9},
                    "speakers": ["MAYA"],
                    "estimated_seconds": 9.7,
                    "recommended_seconds": 9.7,
                    "split_reason": "duration_ceiling",
                },
            ],
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert len(candidates) == 3
    assert [c["shot_id"] for c in candidates] == [
        "shot_scene_002_001",
        "shot_scene_002_002",
        "shot_scene_002_003",
    ]
    assert [c["shot_type"] for c in candidates] == [
        "establishing_medium",
        "close_up_reverse",
        "reaction_close",
    ]
    assert all(c["scene_id"] == "scene_002" for c in candidates)
    assert candidates[0]["dialogue_line_range"] == {"start": 0, "end": 2}
    assert candidates[0]["speakers"] == ["DRE", "MAYA"]
    assert candidates[0]["estimated_seconds"] == 5.7
    assert candidates[0]["split_reason"] == "speaker_turn_grouping"


def test_build_shot_candidates_shot_specs_share_source_refs_from_visual_links():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [
                {"shot_type": "establishing_medium"},
                {"shot_type": "close_up_reverse"},
            ],
        }
    }
    links = {"scene_002": ["ref_001", "ref_002"]}
    candidates = parser.build_shot_candidates(scene_index, links)
    assert len(candidates) == 2
    assert all(c["source_refs"] == ["ref_001", "ref_002"] for c in candidates)


def test_build_shot_candidates_shot_specs_defaults_shot_type_to_general_when_missing():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [{}, {"shot_type": "  "}],
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert [c["shot_type"] for c in candidates] == ["general", "general"]


def test_build_shot_candidates_shot_specs_forwards_identity_context_and_drift_warnings():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "provider_identity_context": {"advisory_only": True, "identity_lines": ["Dre | silhouette: long coat"]},
            "identity_drift_warnings": ["Dre: facial identity not set; drift risk across shots."],
            "shot_specs": [
                {"shot_type": "establishing_medium"},
                {"shot_type": "close_up_reverse"},
            ],
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert len(candidates) == 2
    assert all(c["provider_identity_context"]["advisory_only"] is True for c in candidates)
    assert all(c["identity_drift_warnings"] for c in candidates)


def test_build_shot_candidates_shot_specs_does_not_mutate_input():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [
                {"shot_type": "establishing_medium", "dialogue_line_range": {"start": 0, "end": 2}},
                {"shot_type": "close_up_reverse", "dialogue_line_range": {"start": 3, "end": 5}},
            ],
        }
    }
    original = copy.deepcopy(scene_index)
    parser.build_shot_candidates(scene_index, {"scene_002": ["ref_001"]})
    assert scene_index == original


def test_build_shot_candidates_shot_specs_skips_non_dict_specs():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [
                {"shot_type": "establishing_medium"},
                "not-a-dict",
                None,
                {"shot_type": "close_up_reverse"},
            ],
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert len(candidates) == 2
    assert [c["shot_type"] for c in candidates] == ["establishing_medium", "close_up_reverse"]


def test_build_shot_candidates_shot_specs_all_non_dict_falls_through_to_single_shot():
    parser = ScriptParser()
    scene_index = {
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": ["not-a-dict", None],
        }
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    assert candidates == [
        {"scene_id": "scene_002", "shot_id": "shot_scene_002_001", "source_refs": []}
    ]


def test_split_shot_candidates_flow_through_render_jobs_and_summary():
    parser = ScriptParser()
    candidates = parser.build_shot_candidates(
        {
            "scene_002": {
                "scene_id": "scene_002",
                "shot_specs": [
                    {"shot_type": "establishing_medium"},
                    {"shot_type": "close_up_reverse"},
                    {"shot_type": "reaction_close"},
                ],
            }
        },
        {},
    )
    jobs = parser.build_scene_render_jobs(candidates, "mock")["scene_render_jobs"]
    assert len(jobs) == 3
    assert [job["shot_id"] for job in jobs] == [
        "shot_scene_002_001",
        "shot_scene_002_002",
        "shot_scene_002_003",
    ]
    assert [job["shot_type"] for job in jobs] == [
        "establishing_medium",
        "close_up_reverse",
        "reaction_close",
    ]
    assert all(job["scene_id"] == "scene_002" for job in jobs)
    summary = parser.build_scene_render_job_summary(jobs)["scene_render_job_summary"]
    assert summary == {"total_jobs": 3, "jobs_per_scene": {"scene_002": 3}}


def test_split_shot_candidates_flow_through_shot_coverage():
    parser = ScriptParser()
    scene_index = {
        "scene_001": {"scene_id": "scene_001"},
        "scene_002": {
            "scene_id": "scene_002",
            "shot_specs": [
                {"shot_type": "establishing_medium"},
                {"shot_type": "close_up_reverse"},
            ],
        },
    }
    candidates = parser.build_shot_candidates(scene_index, {})
    coverage = parser.build_shot_coverage(scene_index, candidates)
    assert coverage == {
        "scene_001": {"candidate_count": 1},
        "scene_002": {"candidate_count": 2},
    }
