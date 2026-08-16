"""Tests for director intent in render-prompt form.

Director intent was already reaching the render prompt — but via
`build_director_intent_prefix`, which is written for Claude system prompts. On a
video prompt that block is actively harmful: the provider weights early tokens
most heavily (POSITIONAL_WEIGHTING_FINDING.md), so prepending it put genre and
"what success looks like" ahead of who is on screen, and with a realistic intent
the prefix ran longer than the entire slotted prompt it was prefixing.
"""

from app.utils.director_intent_injection import (
    DIRECTOR_INTENT_RENDER_BUDGET,
    build_director_intent_prefix,
    build_director_intent_render_guidance,
    director_intent_negative_terms,
)


FULL_INTENT = {
    "genre": "Neo-noir thriller",
    "tone_references": ["Arrival", "Blade Runner 2049"],
    "emotional_target": "contemplative unease",
    "visual_references": ["Deakins lighting", "handheld intimacy"],
    "what_success_looks_like": "A film that lingers in memory",
    "what_to_avoid": ["heavy-handed exposition", "melodrama"],
}


# ── render guidance keeps only what a video model can act on ─────────────────


def test_guidance_keeps_emotional_target_and_visual_references():
    guidance = build_director_intent_render_guidance(FULL_INTENT)
    assert "contemplative unease" in guidance
    assert "Deakins lighting" in guidance


def test_guidance_drops_fields_a_video_model_cannot_render():
    guidance = build_director_intent_render_guidance(FULL_INTENT)
    # A genre label is a category, not a visual instruction.
    assert "Neo-noir" not in guidance
    # A judgement about the finished film cannot be rendered into one shot.
    assert "lingers in memory" not in guidance


def test_guidance_never_contains_the_avoid_list():
    # Negations belong in the negative prompt, not here.
    guidance = build_director_intent_render_guidance(FULL_INTENT)
    assert "melodrama" not in guidance
    assert "exposition" not in guidance


def test_guidance_respects_its_budget():
    intent = {
        "emotional_target": "a" * 300,
        "visual_references": ["b" * 300],
    }
    assert len(build_director_intent_render_guidance(intent)) <= DIRECTOR_INTENT_RENDER_BUDGET


def test_guidance_is_far_smaller_than_the_prose_prefix():
    """The regression that motivated this: the prefix outweighed the shot."""
    prefix = build_director_intent_prefix(FULL_INTENT)
    guidance = build_director_intent_render_guidance(FULL_INTENT)
    assert len(guidance) < len(prefix) / 2


def test_empty_intent_yields_no_guidance():
    assert build_director_intent_render_guidance(None) == ""
    assert build_director_intent_render_guidance({}) == ""


def test_intent_with_only_unrenderable_fields_yields_no_guidance():
    assert build_director_intent_render_guidance(
        {"genre": "Thriller", "what_success_looks_like": "greatness"}
    ) == ""


def test_guidance_trims_whole_clauses_not_mid_phrase():
    intent = {"emotional_target": "short", "visual_references": ["x" * 200]}
    guidance = build_director_intent_render_guidance(intent)
    assert guidance == "short"


# ── avoid list routes to the negative channel ────────────────────────────────


def test_avoid_list_becomes_negative_terms():
    assert director_intent_negative_terms(FULL_INTENT) == [
        "heavy-handed exposition",
        "melodrama",
    ]


def test_missing_avoid_list_yields_no_negative_terms():
    assert director_intent_negative_terms({"genre": "Thriller"}) == []
    assert director_intent_negative_terms(None) == []


def test_malformed_avoid_list_is_ignored():
    assert director_intent_negative_terms({"what_to_avoid": "melodrama"}) == []


def test_blank_avoid_entries_are_dropped():
    assert director_intent_negative_terms({"what_to_avoid": ["", "  ", "melodrama"]}) == ["melodrama"]


def test_avoid_terms_survive_the_negative_prompt_builder():
    from app.services.negative_prompt_builder import build_negative_prompt

    negative = build_negative_prompt(
        cast_names=["MAYA"],
        extra_terms=director_intent_negative_terms(FULL_INTENT),
    )
    assert "melodrama" in negative


# ── ordering: the shot must lead the prompt ──────────────────────────────────


def test_shot_content_leads_when_guidance_is_appended():
    """Placement is the whole point — early tokens carry the most weight."""
    shot = "Only MAYA visible; no extras.; MAYA: lean, late 20s. She sets the kettle down."
    guidance = build_director_intent_render_guidance(FULL_INTENT)
    assembled = f"{shot} Tone: {guidance}."

    assert assembled.startswith("Only MAYA visible")
    assert assembled.index("MAYA") < assembled.index("contemplative unease")


def test_old_prepend_form_would_have_buried_the_shot():
    """Documents the behaviour being replaced, so a regression is visible."""
    shot = "Only MAYA visible; no extras.; MAYA: lean, late 20s. She sets the kettle down."
    old_form = build_director_intent_prefix(FULL_INTENT) + shot

    # The shot did not start the prompt, and the prefix outweighed it.
    assert not old_form.startswith("Only MAYA visible")
    assert len(build_director_intent_prefix(FULL_INTENT)) > len(shot)


def test_guidance_plus_shot_stays_within_the_render_budget():
    shot = "x" * 400
    guidance = build_director_intent_render_guidance(FULL_INTENT)
    assert len(f"{shot}. Tone: {guidance}.") <= 512
