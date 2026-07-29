"""Tests for the shot-duration recommendation estimator.

Verifies:
- The estimation function produces ordered, sensibly different durations for
  known word counts (10-word vs 40-word lines).
- No-dialogue shots fall back to the minimum viable clip length.
- Estimates that exceed the provider max are clamped while the raw estimate
  stays visible.
- Scene/shot resolution handles the real shot_id formats in the system.
- The service returns real data for a real shot ID from an existing project.
"""
from __future__ import annotations

import pytest

from app.services.shot_duration_estimator_service import (
    ACTION_PADDING_SECONDS,
    CURRENT_DEFAULT_DURATION_SECONDS,
    MAX_RECOMMENDED_SECONDS,
    MIN_RECOMMENDED_SECONDS,
    PER_LINE_BUFFER_SECONDS,
    SPEECH_WPM_BALANCED,
    SPEECH_WPM_FAST,
    SPEECH_WPM_SLOW,
    estimate_duration_from_dialogue,
    resolve_scene_id_for_shot,
    shot_duration_estimator_service,
)


def _line(text: str) -> dict:
    return {"character": "MAYA", "text": text}


# ── Estimation function ─────────────────────────────────────────────────────

def test_ten_word_line_produces_sensible_duration():
    ten_words = "one two three four five six seven eight nine ten"
    result = estimate_duration_from_dialogue([_line(ten_words)])
    expected = (10 / SPEECH_WPM_BALANCED) * 60.0 + PER_LINE_BUFFER_SECONDS + ACTION_PADDING_SECONDS
    assert result["dialogue_word_count"] == 10
    assert result["estimated_seconds"] == round(expected, 2)
    # 10 words @ 150 wpm = 4.0s + 0.2 + 1.5 = 5.7s -> above min, below max
    assert result["recommended_seconds"] == round(expected, 2)


def test_forty_word_line_is_longer_than_ten_word_line():
    ten = "one two three four five six seven eight nine ten"
    forty = " ".join([ten, ten, ten, ten])  # 40 words
    short = estimate_duration_from_dialogue([_line(ten)])
    long = estimate_duration_from_dialogue([_line(forty)])
    assert long["estimated_seconds"] > short["estimated_seconds"]
    assert long["dialogue_word_count"] == 40
    assert short["dialogue_word_count"] == 10
    # 40 words @ 150 wpm = 16s + 0.2 + 1.5 = 17.7s -> clamped to provider max
    assert long["recommended_seconds"] == MAX_RECOMMENDED_SECONDS
    assert long["estimated_seconds"] > MAX_RECOMMENDED_SECONDS
    assert long["exceeds_provider_max"] is True


def test_no_dialogue_falls_back_to_minimum_clip():
    result = estimate_duration_from_dialogue([])
    assert result["dialogue_word_count"] == 0
    assert result["dialogue_line_count"] == 0
    assert result["speech_seconds"] == 0.0
    # action padding only, clamped up to the minimum viable clip
    assert result["estimated_seconds"] == round(ACTION_PADDING_SECONDS, 2)
    assert result["recommended_seconds"] == MIN_RECOMMENDED_SECONDS


def test_more_lines_add_per_line_buffer_and_stay_ordered():
    single = " ".join(["word"] * 20)  # 20 words, 1 line
    split = [" ".join(["word"] * 10), " ".join(["word"] * 10)]  # 20 words, 2 lines
    a = estimate_duration_from_dialogue([_line(single)])
    b = estimate_duration_from_dialogue([_line(split[0]), _line(split[1])])
    # same word count, but two lines carry one extra per-line buffer
    assert b["dialogue_word_count"] == a["dialogue_word_count"]
    assert b["speech_seconds"] > a["speech_seconds"]
    assert b["estimated_seconds"] > a["estimated_seconds"]


def test_pacing_changes_wpm_and_orders_durations():
    text = " ".join(["word"] * 30)  # 30 words
    slow = estimate_duration_from_dialogue([_line(text)], pacing="slow")
    fast = estimate_duration_from_dialogue([_line(text)], pacing="fast")
    assert slow["speech_wpm"] == SPEECH_WPM_SLOW
    assert fast["speech_wpm"] == SPEECH_WPM_FAST
    assert slow["estimated_seconds"] > fast["estimated_seconds"]


def test_current_default_is_surfaced():
    result = estimate_duration_from_dialogue([_line("a short line")])
    assert result["current_default_seconds"] == CURRENT_DEFAULT_DURATION_SECONDS


def test_provider_duration_constraint_returns_nearest_supported_option():
    from app.services.previs_generation_settings_service import (
        PrevisGenerationSettingsService,
    )

    constraint = PrevisGenerationSettingsService.provider_duration_constraint("Wan 2.2", 7)
    assert constraint.provider == "Wan 2.2"
    assert constraint.supports_custom_duration is True
    assert constraint.valid_durations_seconds == (4, 8, 12, 16, 20)
    assert constraint.nearest_valid_duration_seconds == 8
    assert "starting rhythm" in constraint.advisory


def test_generation_settings_local_recommendation_handles_wide_shot_without_llm():
    from app.services.previs_generation_settings_service import (
        PrevisGenerationSettingsService,
    )

    recommendation, reasoning = PrevisGenerationSettingsService._local_recommendation(
        scene_text="A quiet kitchen beat with no dialogue.",
        shot_number=1,
        shot_type="wide",
    )

    assert recommendation.duration_seconds == 8
    assert recommendation.fps == 16
    assert recommendation.resolution == "720p"
    assert "first wide beat" in reasoning


# ── Scene / shot resolution ─────────────────────────────────────────────────

def test_resolve_scene_id_from_shot_id_formats():
    summary = {"scenes": [{"scene_id": "scene_002"}]}
    assert resolve_scene_id_for_shot("scene_002_shot_001", summary) == "scene_002"
    assert resolve_scene_id_for_shot("shot_scene_002_001", summary) == "scene_002"


def test_resolve_scene_id_via_explicit_beat_map():
    summary = {
        "previs_beat_shot_map": {
            "scene_007": [{"beat_index": 0, "shot_id": "shot_scene_007_001"}],
        },
    }
    assert resolve_scene_id_for_shot("shot_scene_007_001", summary) == "scene_007"


def test_resolve_scene_id_via_scene_sequence():
    summary = {
        "scene_sequence": [
            {"scene_id": "scene_005", "shots": ["scene_005_shot_001", "scene_005_shot_002"]},
        ],
    }
    assert resolve_scene_id_for_shot("scene_005_shot_002", summary) == "scene_005"


def test_resolve_scene_id_returns_none_for_unknown():
    assert resolve_scene_id_for_shot("previs_gen_1782459612201_shot_001", {"scenes": []}) is None


# ── Real-project integration ────────────────────────────────────────────────
# Under pytest, get_storage() redirects to an isolated temp DB, so we seed it
# with the REAL scene_002 dialogue from project_3dba9330f43a ("I Was Reborn")
# and a real shot_id. This exercises the full service -> storage -> estimation
# path with real dialogue content (the DRE/MAYA confrontation: 10 lines).

REAL_PROJECT_ID = "project_3dba9330f43a"
REAL_SCENE_002_TEXT = (
    "The same city. Different world. The L train is frozen. Buildings are cracked.\n"
    "Maya walks through the ruins. She reaches the Chicago River.\n"
    "DRE\nI need you to understand something.\n"
    "MAYA\nThat's funny.\n"
    "DRE\nWhat?\n"
    "MAYA\nYou always say that right before you do something\nyou know is wrong.\n"
    "DRE\nThings changed.\n"
    "MAYA\nNo. People changed.\n"
    "DRE\n(raises the gun)\nThere's not enough. You have to understand that.\nThere is not enough for everyone.\n"
    "MAYA\nSo you decided that for all of us.\n"
    "DRE\nSomeone had to.\n"
    "MAYA\nI remember dying. So why am I here?"
)


def test_service_returns_real_data_for_real_shot_id():
    from app.data.storage import get_storage
    from app.models import StudioProject

    storage = get_storage()
    storage.save_project(StudioProject(
        project_id=REAL_PROJECT_ID,
        title="I Was Reborn",
        execution_summary={
            "scenes": [
                {"scene_id": "scene_001", "text": "Chicago is alive. MAYA (V.O.)\nPeople think the end of the world is fire."},
                {"scene_id": "scene_002", "text": REAL_SCENE_002_TEXT},
            ],
        },
    ))

    result = shot_duration_estimator_service.estimate_for_shot(
        project_id=REAL_PROJECT_ID, shot_id="scene_002_shot_001",
    )
    assert result["found"] is True
    assert result["scene_id"] == "scene_002"
    assert result["advisory_only"] is True
    # scene_002 carries the multi-line DRE/MAYA confrontation -> real dialogue
    assert result["dialogue_line_count"] >= 8
    assert result["dialogue_word_count"] >= 50
    # the raw estimate must exceed the 5s fixed default (the root-cause signal)
    assert result["estimated_seconds"] > CURRENT_DEFAULT_DURATION_SECONDS
    assert result["recommended_seconds"] == MAX_RECOMMENDED_SECONDS
    assert result["exceeds_provider_max"] is True
    assert result["dialogue_excerpt"]


def test_service_handles_shot_with_no_resolved_scene():
    from app.data.storage import get_storage
    from app.models import StudioProject

    storage = get_storage()
    storage.save_project(StudioProject(
        project_id="proj-estimator-sparse",
        execution_summary={"scenes": [{"scene_id": "scene_001", "text": "A quiet beat."}]},
    ))
    result = shot_duration_estimator_service.estimate_for_shot(
        project_id="proj-estimator-sparse", shot_id="previs_gen_9999_shot_001",
    )
    assert result["found"] is False
    assert result["current_default_seconds"] == CURRENT_DEFAULT_DURATION_SECONDS
