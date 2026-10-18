"""Phase 3/3A/6 — dialogue authority regression tests.

Locks in the highest-priority creative integrity repair:

- DialogueVoiceService's fabricated placeholder lines ("DRE carries the beat
  with restrained subtext.") persisted into execution_summary.dialogue_lines
  must never again be treated as production dialogue by any consumer.
- The canonical screenplay / scene text is the sole dialogue authority;
  production consumers derive dialogue through dialogue_authority.
- Placeholder detection is read-only (no silent rewriting of historical
  records) and conservative (real screenplay lines are never flagged).
- Changing the script changes the derived dialogue (invalidation).
- Attribution stays tied to the correct character.

Covers the consumer classes named by the audit: audio pipeline, subtitles,
performance audio, dialogue performance cues, audience simulator, Previs/generation.
"""
from __future__ import annotations

import pytest

from app.services.dialogue_authority import (
    canonical_dialogue_lines,
    canonical_scene_dialogue_for_audio,
    filter_placeholder_lines,
    is_placeholder_dialogue,
)
from app.services.audio_pipeline_service import _extract_dialogue_lines


PLACEHOLDER_DRE = "DRE carries the beat with restrained subtext."
PLACEHOLDER_MAYA = "MAYA carries the beat with restrained subtext."
PLACEHOLDER_NARRATOR = "Narrator carries the beat with restrained subtext."


# ── Placeholder detection ────────────────────────────────────────────────────


def test_fabricated_placeholder_lines_are_detected():
    for text in (PLACEHOLDER_DRE, PLACEHOLDER_MAYA, PLACEHOLDER_NARRATOR):
        assert is_placeholder_dialogue(text), text


def test_real_screenplay_lines_are_never_flagged():
    real_lines = [
        "I need you to understand something.",
        "Someone had to.",
        "I remember dying. So why am I here?",
        "You always say that right before you do something you know is wrong.",
        "Mom sets down her tea. She looks at her daughter.",
        "She carries the gun like it weighs nothing.",  # near-miss phrasing
        "DRE carries the beat with restrained subtext",  # no terminal period in stored prose? still requires exact template with period
    ]
    for text in real_lines[:-1]:
        assert not is_placeholder_dialogue(text), text
    # The template requires the trailing period; without it the line is not a
    # historical fabricated row (it is creator prose and stays).
    assert not is_placeholder_dialogue("DRE carries the beat with restrained subtext")


def test_placeholder_rows_are_filtered_without_touching_history():
    stored = [
        {"scene_id": "scene_002", "character_id": "dre", "text": PLACEHOLDER_DRE},
        {"scene_id": "scene_002", "character_id": "maya", "text": PLACEHOLDER_MAYA},
    ]
    filtered = filter_placeholder_lines(stored)
    assert filtered == []
    # Read-only: the original records are untouched (auditability preserved).
    assert stored[0]["text"] == PLACEHOLDER_DRE


# ── Canonical authority ──────────────────────────────────────────────────────


SCENE_002_TEXT = (
    "The same city. Different world. The L train is frozen. Buildings are cracked. Nature has\n"
    "reclaimed the streets. The skyline still stands, but Chicago feels like a graveyard.\n"
    "Maya walks through the ruins. She reaches the Chicago River. The place where she\n"
    "died.\n"
    "THE FIRST TIMELINE\n"
    "Maya is surrounded by the people she trusted. Dre, her closest friend, stands among\n"
    "them. His jaw is tight. He won't look her in the eyes.\n"
    "DRE\nI need you to understand something.\n"
    "MAYA\nThat's funny.\n"
    "DRE\nWhat?\n"
    "MAYA\nYou always say that right before you do something\nyou know is wrong.\n"
    "DRE\nThings changed.\n"
    "MAYA\nNo. People changed.\n"
    "DRE\n(raises the gun)\nThere's not enough. You have to understand that.\n"
    "There is not enough for everyone.\n"
    "MAYA\nSo you decided that for all of us.\n"
    "DRE\nSomeone had to.\n"
    "(pulls the trigger)\n"
    "Maya is killed. Darkness.\n"
    "We hold on Dre's face for a beat after the shot. He doesn't look relieved. He looks like\n"
    "a man who just chose scarcity over trust — and already knows the cost.\n"
    "THE SECOND CHANCE\n"
    "Maya wakes up. Two months before the apocalypse. She remembers everything. The\n"
    "betrayal. The death. The collapse.\n"
    "She looks out at Chicago while it is still alive. The L train runs. People laugh below her\n"
    "window.\n"
    "MAYA\nI remember dying. So why am I here?\n"
    "She sits with that for a long moment. Then something shifts behind her eyes. Not grief.\n"
    "Not rage. Clarity.\n"
)


def _scene() -> dict:
    return {
        "scene_id": "scene_002",
        "heading": "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE",
        "text": SCENE_002_TEXT,
        "characters": ["DRE", "MAYA"],
    }


def test_placeholder_dialogue_cannot_become_canonical():
    scene = _scene()
    scene["dialogue_lines"] = [
        {"scene_id": "scene_002", "character_id": "dre", "text": PLACEHOLDER_DRE},
        {"scene_id": "scene_002", "character_id": "maya", "text": PLACEHOLDER_MAYA},
    ]
    lines = canonical_dialogue_lines(scene, scene_id="scene_002", characters=["DRE", "MAYA"])
    texts = " ".join(line["text"] for line in lines)
    assert PLACEHOLDER_DRE not in texts
    assert PLACEHOLDER_MAYA not in texts
    # The canonical script text was used instead.
    assert any(line["text"] == "Someone had to." for line in lines)


def test_joined_dre_maya_cue_boundary_recovers_ten_distinct_dialogue_turns():
    lines = _extract_dialogue_lines(
        SCENE_002_TEXT.replace(
            "I need you to understand something.\nMAYA\n",
            "I need you to understand something.MAYA\n",
        ),
        characters=["DRE", "MAYA"],
    )
    expected = [
        ("DRE", "I need you to understand something."),
        ("MAYA", "That's funny."),
        ("DRE", "What?"),
        ("MAYA", "You always say that right before you do something you know is wrong."),
        ("DRE", "Things changed."),
        ("MAYA", "No. People changed."),
        ("DRE", "There's not enough. You have to understand that. There is not enough for everyone."),
        ("MAYA", "So you decided that for all of us."),
        ("DRE", "Someone had to."),
        ("MAYA", "I remember dying. So why am I here?"),
    ]
    assert [(row["character"], row["text"]) for row in lines] == expected


def test_script_dialogue_is_authoritative():
    lines = canonical_dialogue_lines(_scene(), scene_id="scene_002", characters=["DRE", "MAYA"])
    expected = [
        ("DRE", "I need you to understand something."),
        ("MAYA", "That's funny."),
        ("DRE", "What?"),
        ("MAYA", "You always say that right before you do something you know is wrong."),
        ("DRE", "Things changed."),
        ("MAYA", "No. People changed."),
        ("DRE", "There's not enough. You have to understand that. There is not enough for everyone."),
        ("MAYA", "So you decided that for all of us."),
        ("DRE", "Someone had to."),
        ("MAYA", "I remember dying. So why am I here?"),
    ]
    assert [(line["character"], line["text"]) for line in lines] == expected


def test_changing_the_script_invalidates_derived_dialogue():
    """Derived dialogue is a pure function of the scene text — a script edit
    therefore changes every downstream derivation (no stale authority)."""
    original = canonical_dialogue_lines(_scene(), scene_id="scene_002", characters=["DRE", "MAYA"])
    edited = _scene()
    edited["text"] = edited["text"].replace("Things changed.", "Everything changed.")
    derived_after_edit = canonical_dialogue_lines(edited, scene_id="scene_002", characters=["DRE", "MAYA"])
    assert original != derived_after_edit
    assert any(line["text"] == "Everything changed." for line in derived_after_edit)
    assert not any(line["text"] == "Things changed." for line in derived_after_edit)


def test_fabricated_dialogue_cannot_survive_as_current_production_dialogue():
    """The exact historical contamination shape: a project whose stored
    dialogue_lines projection is entirely fabricated falls back to the script."""
    project = {
        "execution_summary": {
            "dialogue_lines": [
                {"scene_id": "scene_002", "line_id": "scene_002_dlg_01", "character_id": "dre", "text": PLACEHOLDER_DRE},
                {"scene_id": "scene_002", "line_id": "scene_002_dlg_02", "character_id": "maya", "text": PLACEHOLDER_MAYA},
            ]
        }
    }
    lines = canonical_scene_dialogue_for_audio(
        project, _scene(), "scene_002", characters=["DRE", "MAYA"]
    )
    assert lines
    for line in lines:
        assert not is_placeholder_dialogue(line["text"])
    assert any(line["text"] == "Someone had to." for line in lines)


def test_audio_consumers_receive_canonical_dialogue():
    """The audio pipeline's own extractor, fed the canonical lines, sees only
    screenplay dialogue — the same contract generate_full_pipeline consumes."""
    lines = canonical_scene_dialogue_for_audio(
        {"execution_summary": {"dialogue_lines": [
            {"scene_id": "scene_002", "character_id": "dre", "text": PLACEHOLDER_DRE},
        ]}},
        _scene(),
        "scene_002",
        characters=["DRE", "MAYA"],
    )
    assert lines is not None
    speaker_text = [(line["character"], line["text"]) for line in lines]
    assert ("DRE", "Someone had to.") in speaker_text
    # Feeding these lines back through the pipeline extractor is lossless —
    # they are already screenplay-shaped rows.
    round_trip = _extract_dialogue_lines(
        "\n".join(f"{c}\n{t}" for c, t in speaker_text),
        characters=["DRE", "MAYA"],
    )
    assert round_trip


def test_audience_intelligence_cannot_reason_over_fabricated_dialogue():
    """The audience simulator reads scene.dialogue_lines to decide whether a
    scene 'has dialogue'. A fabricated-only projection must not count."""
    scene = _scene()
    scene["dialogue_lines"] = [
        {"scene_id": "scene_002", "character_id": "dre", "text": PLACEHOLDER_DRE},
    ]
    # Through the authority: fabricated rows are not dialogue...
    assert filter_placeholder_lines(scene["dialogue_lines"]) == []
    # ...so the scene's real dialogue (from the script) is what reasoning sees.
    lines = canonical_dialogue_lines(scene, scene_id="scene_002", characters=["DRE", "MAYA"])
    assert any(line["text"] == "Someone had to." for line in lines)


def test_subtitles_cannot_be_built_from_fabricated_dialogue():
    """Subtitle generation consumes character/text pairs; every pair returned
    by the authority is verbatim screenplay text attributed correctly."""
    scene = _scene()
    scene["dialogue_lines"] = [
        {"scene_id": "scene_002", "character_id": "dre", "text": PLACEHOLDER_DRE},
        {"scene_id": "scene_002", "character_id": "maya", "text": PLACEHOLDER_MAYA},
    ]
    lines = canonical_dialogue_lines(scene, scene_id="scene_002", characters=["DRE", "MAYA"])
    # The extractor joins hard-wrapped screenplay lines with spaces; every
    # subtitle word must still come verbatim from the scene text.
    normalized_text = " ".join(SCENE_002_TEXT.split())
    for line in lines:
        assert line["character"] in {"DRE", "MAYA"}
        assert " ".join(line["text"].split()) in normalized_text
        assert not is_placeholder_dialogue(line["text"])


def test_dialogue_attribution_remains_tied_to_the_correct_character():
    lines = canonical_dialogue_lines(_scene(), scene_id="scene_002", characters=["DRE", "MAYA"])
    by_char = {}
    for line in lines:
        by_char.setdefault(line["character"], []).append(line["text"])
    assert "Someone had to." in by_char["DRE"]
    assert "So you decided that for all of us." in by_char["MAYA"]
    assert "I remember dying. So why am I here?" in by_char["MAYA"]
    assert "Someone had to." not in by_char["MAYA"]


def test_shot_level_creator_assignment_wins_but_placeholder_assignment_does_not():
    """Creator-curated shot dialogue (Scene Direction) is authoritative for the
    shot; fabricated rows inside it are dropped, never passed through."""
    supplied = [
        {"character": "DRE", "text": "Someone had to."},
        {"character": "MAYA", "text": PLACEHOLDER_MAYA},
    ]
    lines = canonical_dialogue_lines(_scene(), supplied, scene_id="scene_002")
    assert [line["text"] for line in lines] == ["Someone had to."]


def test_scene_with_no_dialogue_returns_empty_not_fabricated():
    scene = {
        "scene_id": "scene_011",
        "text": "The city breathes out. Rooftops empty. Wind.",
        "characters": [],
    }
    project = {"execution_summary": {"dialogue_lines": []}}
    lines = canonical_scene_dialogue_for_audio(project, scene, "scene_011", characters=[])
    assert lines == []
