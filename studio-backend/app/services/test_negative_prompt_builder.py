"""Tests for the negative prompt channel."""

from app.services.negative_prompt_builder import (
    MAX_NEGATIVE_PROMPT_LENGTH,
    build_cast_exclusion_terms,
    build_negative_prompt,
    provider_supports_negative_prompt,
)


def _terms(negative: str) -> list[str]:
    return [part.strip() for part in negative.split(",") if part.strip()]


def test_build_negative_prompt_includes_core_artifact_and_quality_terms():
    negative = build_negative_prompt(cast_names=["MAYA", "DRE"])
    terms = _terms(negative)

    assert "text overlay" in terms
    assert "watermark" in terms
    assert "deformed hands" in terms
    assert "extra people" in terms


def test_single_character_shot_guards_against_a_second_person():
    negative = build_negative_prompt(cast_names=["MAYA"])
    assert "second person in frame" in _terms(negative)


def test_multi_character_shot_does_not_guard_against_a_second_person():
    negative = build_negative_prompt(cast_names=["MAYA", "DRE"])
    assert "second person in frame" not in _terms(negative)


def test_cast_names_are_never_emitted_as_negative_terms():
    # Naming a required character in a negative prompt is how you lose them.
    negative = build_negative_prompt(cast_names=["MAYA", "DRE"]).lower()
    assert "maya" not in negative
    assert "dre" not in negative


def test_cast_exclusion_terms_do_not_name_the_cast():
    terms = [term.lower() for term in build_cast_exclusion_terms(["MAYA"])]
    assert not any("maya" in term for term in terms)


def test_disabled_group_is_omitted():
    negative = build_negative_prompt(cast_names=["MAYA"], disabled_groups=["camera"])
    terms = _terms(negative)
    assert "shaky camera" not in terms
    # Other groups are unaffected.
    assert "watermark" in terms


def test_extra_terms_are_appended():
    negative = build_negative_prompt(cast_names=["MAYA"], extra_terms=["rain", "snow"])
    terms = _terms(negative)
    assert "rain" in terms
    assert "snow" in terms


def test_duplicate_terms_are_collapsed_case_insensitively():
    negative = build_negative_prompt(cast_names=["MAYA"], extra_terms=["Watermark", "watermark"])
    terms = [term.lower() for term in _terms(negative)]
    assert terms.count("watermark") == 1


def test_length_guard_trims_whole_terms_not_partial_phrases():
    negative = build_negative_prompt(
        cast_names=["MAYA"],
        extra_terms=[f"artifact number {index}" for index in range(200)],
    )
    assert len(negative) <= MAX_NEGATIVE_PROMPT_LENGTH
    # Every surviving term is intact — no mid-phrase cut.
    for term in _terms(negative):
        assert not term.endswith("...")
        assert term == term.strip()


def test_empty_cast_still_produces_a_usable_negative_prompt():
    negative = build_negative_prompt(cast_names=[])
    assert "watermark" in _terms(negative)


def test_all_groups_disabled_and_no_extras_still_keeps_cast_exclusions():
    negative = build_negative_prompt(
        cast_names=["MAYA", "DRE"],
        disabled_groups=["artifacts", "quality", "camera", "staging"],
    )
    assert _terms(negative) == [
        "extra people",
        "background crowd",
        "bystanders",
        "additional characters",
    ]


def test_provider_support_gate():
    assert provider_supports_negative_prompt("happyhorse")
    assert provider_supports_negative_prompt("happyhorse-r2v")
    assert provider_supports_negative_prompt("HappyHorse")
    # Runway Gen-4 has no negative prompt parameter — building one would be
    # silently discarded.
    assert not provider_supports_negative_prompt("runway")
    assert not provider_supports_negative_prompt("")
