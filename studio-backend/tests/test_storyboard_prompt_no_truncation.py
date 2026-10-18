"""Phase 1/6 — storyboard prompt regeneration must never silently truncate.

Locks in the Multi Shot integrity audit findings:

1. ``build_shot_aware_prompt`` (the storyboard blueprint regeneration path) must
   not cut canonical prompt text at a 512-character ceiling or produce severed
   terminal fragments. Provider budgets are an explicit downstream concern
   (``prompt_budget_service``), evaluated at job creation — never a silent edit
   of canonical creative content.
2. A prompt longer than the legacy application ceiling survives regeneration
   intact (byte-for-byte content, no ellipsis, no severed fragment).
3. Historical corruption artifacts still fail CLOSED via
   ``prompt_integrity.detect_prompt_corruption``.
4. A clean regenerated prompt passes prompt integrity.
5. The deterministic slot preview remains deterministic.
6. The explicit provider budget boundary (prompt_budget_service) still stops
   generation when required facts exceed a provider budget instead of silently
   shortening them.
"""
from __future__ import annotations

import re

from app.services.prompt_integrity import detect_prompt_corruption
from app.services.shot_prompt_builder import (
    MAX_PROMPT_LENGTH,
    build_shot_aware_prompt,
    build_slotted_prompt,
)

# Longer than the legacy 512-char ceiling that used to silently cut prompts.
# Two long action lines: the builder keeps the first two action lines of the
# shot segment, so each line must individually be long enough to push the
# assembled prompt past the old ceiling.
_LINE_A = (
    "Maya moves through the frozen ruin of the L platform, boots crunching over "
    "shattered glass, while ivy splits the concrete and the skyline holds its breath "
    "above a graveyard of stalled cars, every window a dark eye refusing to reflect her."
)
_LINE_B = (
    "She counts the stalled cars the way she once counted birthday candles, one for "
    "every neighbor who did not make it to the river, and the river keeps moving as "
    "if nothing downriver of the bridges has ever been asked to remember anything."
)
_LONG_SCENE_TEXT = "\n".join(
    [
        _LINE_A,
        _LINE_B,
        _LINE_A,
        _LINE_B,
        _LINE_A,
        _LINE_B,
        _LINE_A,
        _LINE_B,
    ]
)
_LONG_LINES = (_LINE_A, _LINE_B)


def _scene() -> dict:
    return {
        "scene_id": "scene_002",
        "heading": "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE",
        "text": _LONG_SCENE_TEXT,
        "location": "Downtown Chicago",
        "time_of_day": "dusk",
        "emotional_tone": "graveyard quiet",
        "characters": ["DRE", "MAYA"],
    }


def test_build_shot_aware_prompt_does_not_truncate_long_prompts():
    """A canonical prompt longer than 512 chars is returned whole."""
    prompt = build_shot_aware_prompt(
        scene_data=_scene(),
        shot_number=5,
        take_number=1,
        total_shots=5,
    )
    assert len(prompt) > MAX_PROMPT_LENGTH
    assert "..." not in prompt
    assert "\u2026" not in prompt


def test_build_shot_aware_prompt_produces_no_severed_terminal_fragment():
    prompt = build_shot_aware_prompt(
        scene_data=_scene(),
        shot_number=2,
        take_number=1,
        total_shots=5,
    )
    assert prompt == prompt.strip()
    # The historical corruption signature: sentence punctuation followed by a
    # 1-2 letter orphan (e.g. "stands . e"). Must never be produced.
    assert not re.search(r"[.!?]\s*[A-Za-z]{1,2}$", prompt)
    # And the prompt must not end mid-word (last character is a letter that
    # directly follows a lowercase letter within the same word is fine — we
    # assert the terminal fragment shape instead).


def test_canonical_prompt_text_remains_intact_across_rebuilds():
    scene = _scene()
    first = build_shot_aware_prompt(
        scene_data=scene, shot_number=5, take_number=1, total_shots=5
    )
    second = build_shot_aware_prompt(
        scene_data=dict(scene), shot_number=5, take_number=1, total_shots=5
    )
    assert first == second
    # Every action sentence the builder selected survives regeneration whole —
    # none may be silently dropped or cut by a length limit.
    assert _LINE_A in first
    assert len(first) > MAX_PROMPT_LENGTH


def test_historical_corruption_still_fails_closed():
    corrupted = (
        "Wide establishing shot. DOWNTOWN CHICAGO. The same city. Different world. "
        "Only DRE and MAYA visible. Characters: DRE (Early 30s): A broad-shouldered "
        "Black man in his early 30s with a grown-out fade and mismatched worn layers "
        "stands . e"
    )
    issues = detect_prompt_corruption(corrupted, source="BOARD")
    assert issues, "corrupted historical prompt must be flagged"
    assert any("severed_terminal_fragment" in issue for issue in issues)

    ellipsized = "She remembers everything. The. ..."
    issues = detect_prompt_corruption(ellipsized, source="BOARD")
    assert issues
    assert any("legacy_truncation_artifact" in issue for issue in issues)


def test_regenerated_clean_prompt_passes_integrity():
    prompt = build_shot_aware_prompt(
        scene_data=_scene(),
        shot_number=1,
        take_number=1,
        total_shots=5,
    )
    assert detect_prompt_corruption(prompt, source="BOARD") == []


def test_deterministic_slot_preview_is_deterministic():
    scene = _scene()
    one = build_slotted_prompt(
        scene_data=scene,
        shot_number=2,
        character_visual_canon="Maya in worn field jacket.",
        action_text="Maya crosses the rubble toward the river.",
        environment_motifs="Frozen L train; ivy over concrete.",
        camera_direction="Medium shot.",
        lighting_direction="Overcast diffusion.",
    )
    two = build_slotted_prompt(
        scene_data=dict(scene),
        shot_number=2,
        character_visual_canon="Maya in worn field jacket.",
        action_text="Maya crosses the rubble toward the river.",
        environment_motifs="Frozen L train; ivy over concrete.",
        camera_direction="Medium shot.",
        lighting_direction="Overcast diffusion.",
    )
    assert one == two


def test_provider_budget_boundary_still_fails_closed_not_silently_shortens():
    """The explicit provider boundary refuses oversized required facts — it
    never silently shortens the canonical text behind the filmmaker's back."""
    from app.models.prompt_budget import PromptFact, PromptPriority
    from app.services.prompt_budget_service import allocate

    required = PromptFact(
        fact_id="intent:canon",
        text=_LONG_SCENE_TEXT.strip(),
        priority=PromptPriority.INTENT,
        source="creator_prompt",
    )
    result = allocate([required], "runway", "gen4.5")
    assert not result.ready
    assert result.required_overflow_ids == ["intent:canon"]
    assert result.prompt == ""


def test_no_generation_prompt_path_silently_truncates():
    """Both builder entry points return full-length content; the only remaining
    truncation sites are display/preview budgets fed by lossless collection mode
    or the explicit prompt_budget boundary (covered above)."""
    prompt = build_shot_aware_prompt(
        scene_data=_scene(),
        shot_number=5,
        take_number=2,
        total_shots=5,
    )
    assert len(prompt) > MAX_PROMPT_LENGTH
    assert not prompt.endswith("...")
    for line in _LONG_LINES:
        assert line in prompt
    slotted = build_slotted_prompt(
        scene_data=_scene(),
        shot_number=5,
        character_visual_canon="x " * 300,
        action_text="y " * 300,
    )
    # The slotted preview keeps its legacy display budget, but in lossless
    # (generation) collection mode it must not cut either.
    from contextlib import contextmanager

    from app.prompt_assembly_context import collecting_generation_prompt

    @contextmanager
    def _collecting():
        token = collecting_generation_prompt.set(True)
        try:
            yield
        finally:
            collecting_generation_prompt.reset(token)

    with _collecting():
        lossless = build_slotted_prompt(
            scene_data=_scene(),
            shot_number=5,
            character_visual_canon="x " * 300,
            action_text="y " * 300,
        )
    assert len(lossless["prompt"]) >= len(slotted["prompt"])
    assert "..." not in lossless["prompt"]
