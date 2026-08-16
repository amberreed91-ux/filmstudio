"""Tests for the intent-fidelity check.

The gap this closes: every other check measures the render against the prompt.
None of them can see that budget compression removed something from the prompt
before it was ever sent — so a shot could score highly, pass, and promote a
reference lock while the detail the director asked for was already gone.
"""

from app.services.intent_fidelity_service import (
    MATERIAL_DROP_CHARS,
    build_advisory_note,
    build_intent_fidelity_report,
    diff_slot,
    dropped_elements,
    split_elements,
)
from app.services.shot_prompt_builder import SLOT_BUDGETS, build_slotted_prompt


# ── element splitting ────────────────────────────────────────────────────────


def test_splits_on_clause_boundaries():
    elements = split_elements("weathered hands, grey at the temples; never stops moving")
    assert "weathered hands" in elements
    assert "grey at the temples" in elements
    assert "never stops moving" in elements


def test_drops_fragments_too_short_to_be_an_idea():
    assert "a" not in split_elements("a, the, weathered hands")


def test_truncation_ellipsis_is_not_treated_as_content():
    assert split_elements("weathered hands, grey at the temp...") == ["weathered hands", "grey at the temp"]


def test_empty_text_yields_no_elements():
    assert split_elements("") == []
    assert split_elements("   ") == []


# ── dropped element detection ────────────────────────────────────────────────


def test_detects_an_element_removed_by_compression():
    source = "MAYA: weathered hands, grey at the temples, never stops moving"
    final = "MAYA: weathered hands, grey at the temples"
    assert dropped_elements(source, final) == ["never stops moving"]


def test_nothing_dropped_when_text_is_unchanged():
    text = "MAYA: weathered hands, grey at the temples"
    assert dropped_elements(text, text) == []


def test_everything_dropped_when_final_is_empty():
    assert dropped_elements("weathered hands, grey at the temples", "") == [
        "weathered hands",
        "grey at the temples",
    ]


def test_half_surviving_element_still_counts_as_dropped():
    # A clause cut mid-phrase does not reliably render, so it is a loss.
    source = "weathered hands, never stops moving her hands"
    final = "weathered hands, never stops mov..."
    assert dropped_elements(source, final) == ["never stops moving her hands"]


def test_comparison_is_case_insensitive():
    assert dropped_elements("Weathered Hands", "weathered hands") == []


# ── slot diff ────────────────────────────────────────────────────────────────


def test_diff_reports_characters_removed():
    report = diff_slot("a" * 100, "a" * 40)
    assert report["chars_dropped"] == 60
    assert report["material"] is True


def test_small_drop_is_not_material():
    report = diff_slot("weathered hands and a steady gaze", "weathered hands and a steady")
    assert report["chars_dropped"] < MATERIAL_DROP_CHARS


def test_unchanged_slot_is_not_material():
    text = "MAYA: weathered hands"
    report = diff_slot(text, text)
    assert report["material"] is False
    assert report["chars_dropped"] == 0


def test_truncation_flag_is_set():
    assert diff_slot("a" * 100, "a" * 37 + "...")["truncated"] is True


# ── advisory note (AGENTS.md voice rules) ────────────────────────────────────


def test_note_is_silent_when_nothing_material_was_lost():
    assert build_advisory_note({"action": diff_slot("she turns", "she turns")}) == ""


def test_note_quotes_the_directors_own_words():
    reports = {
        "character_state": diff_slot(
            "MAYA: weathered hands, never stops moving", "MAYA: weathered hands"
        )
    }
    note = build_advisory_note(reports)
    assert "never stops moving" in note


def test_note_carries_no_scores_or_percentages():
    # AGENTS.md: no scores, ratings, or percentages in director-facing output.
    reports = {
        "character_state": diff_slot("MAYA: weathered hands, never stops moving", "MAYA: weathered"),
        "action": diff_slot("she crosses the room and stops at the window", "she crosses the room"),
    }
    note = build_advisory_note(reports)
    assert "%" not in note
    assert "score" not in note.lower()
    assert "rating" not in note.lower()
    assert not any(char.isdigit() for char in note)


def test_note_leads_with_the_highest_weighted_slot():
    reports = {
        "lighting": diff_slot("hard late sun, deep shadow under the eaves", "hard late sun"),
        "character_state": diff_slot("MAYA: weathered hands, never stops moving", "MAYA: weathered hands"),
    }
    note = build_advisory_note(reports)
    assert note.index("never stops moving") < note.index("deep shadow under the eaves")


def test_note_stays_short_when_many_slots_are_affected():
    reports = {
        slot: diff_slot(f"{slot} first idea, {slot} second idea", slot)
        for slot in ("character_state", "action", "environment_persistence", "lighting")
    }
    note = build_advisory_note(reports)
    assert "Other detail was trimmed" in note
    # Only the two most important slots are named outright.
    assert note.count("The prompt no longer carries") == 2


# ── full report ──────────────────────────────────────────────────────────────


def test_report_is_intact_when_nothing_was_compressed():
    slots = {"character_state": "MAYA", "action": "she turns", "camera": "medium"}
    report = build_intent_fidelity_report(source_slots=slots, final_slots=slots)
    assert report["status"] == "intact"
    assert report["advisory_note"] == ""


def test_report_is_reduced_when_intent_was_lost():
    report = build_intent_fidelity_report(
        source_slots={"character_state": "MAYA: weathered hands, never stops moving"},
        final_slots={"character_state": "MAYA: weathered hands"},
    )
    assert report["status"] == "reduced"
    assert "character_state" in report["reduced_slots"]
    assert report["advisory_note"]


def test_missing_source_slots_is_unknown_not_a_failure():
    # This check is advisory. It must never gate a render.
    report = build_intent_fidelity_report(source_slots=None, final_slots={"action": "x"})
    assert report["status"] == "unknown"
    assert report["advisory_note"] == ""


def test_defaulted_slots_are_ignored():
    """Trimming a builder default is not losing the director's intent.

    The camera default is longer than its 70-char budget, so without this the
    check would report a loss on nearly every shot and become noise.
    """
    report = build_intent_fidelity_report(
        source_slots={"camera": "Wide establishing shot. Camera far back. Characters small in frame."},
        final_slots={"camera": "Wide establishing shot. Camera far back."},
        defaulted_slots=["camera"],
    )
    assert report["status"] == "intact"
    assert "camera" in report["skipped_defaulted_slots"]


def test_defaulted_slot_would_otherwise_have_been_reported():
    report = build_intent_fidelity_report(
        source_slots={"camera": "Wide establishing shot. Camera far back. Characters small in frame."},
        final_slots={"camera": "Wide establishing shot. Camera far back."},
    )
    assert report["status"] == "reduced"


# ── integration with the real builder ────────────────────────────────────────


def test_builder_returns_uncompressed_source_slots():
    long_canon = (
        "MAYA: a lean woman in her late 20s, deep brown skin, natural locs pulled back, "
        "weathered hands that never stop moving, a grey work jacket two sizes too big, "
        "a thin scar across her left eyebrow, boots caked in dry mud"
    )
    result = build_slotted_prompt(
        scene_data={"location": "Kitchen"},
        shot_number=2,
        character_visual_canon=long_canon,
        action_text="she sets the kettle down",
    )
    assert len(result["source_slots"]["character_state"]) > SLOT_BUDGETS["character_state"]
    assert len(result["slots"]["character_state"]) <= SLOT_BUDGETS["character_state"]


def test_real_compression_is_caught_end_to_end():
    """The scenario the module exists for, run through the actual builder."""
    long_canon = (
        "MAYA: a lean woman in her late 20s, deep brown skin, natural locs pulled back, "
        "weathered hands that never stop moving, a grey work jacket two sizes too big, "
        "a thin scar across her left eyebrow, boots caked in dry mud"
    )
    result = build_slotted_prompt(
        scene_data={"location": "Kitchen"},
        shot_number=2,
        character_visual_canon=long_canon,
        action_text="she sets the kettle down",
    )
    report = build_intent_fidelity_report(
        source_slots=result["source_slots"],
        final_slots=result["slots"],
        prompt=result["prompt"],
        shot_id="scene_001_shot_002",
        defaulted_slots=result["defaulted_slots"],
    )

    assert report["status"] == "reduced"
    assert "character_state" in report["reduced_slots"]
    # The prompt itself is still within budget — nothing looks wrong downstream,
    # which is exactly why this check has to happen here.
    assert len(result["prompt"]) <= 512


def test_short_prompt_passes_through_the_real_builder_intact():
    result = build_slotted_prompt(
        scene_data={"location": "Kitchen"},
        shot_number=2,
        character_visual_canon="MAYA: weathered hands",
        action_text="she turns",
        camera_direction="medium close-up",
        lighting_direction="late afternoon",
    )
    report = build_intent_fidelity_report(
        source_slots=result["source_slots"],
        final_slots=result["slots"],
        prompt=result["prompt"],
        defaulted_slots=result["defaulted_slots"],
    )
    assert report["status"] == "intact"
