"""Tests for RevisionIdentityComparisonService."""

from __future__ import annotations

from app.services.revision_identity_comparison import (
    RevisionIdentityComparisonService,
)


def _snapshot(**overrides):
    base = {
        "snapshot_id": "sig_001",
        "dominant_mood_tags": ["melancholic"],
        "dominant_lighting_tags": ["low_key"],
        "dominant_composition_tags": ["centered"],
        "dominant_palette": ["amber"],
    }
    base.update(overrides)
    return base


def test_identical_snapshots_report_that_identity_holds():
    service = RevisionIdentityComparisonService()
    result = service.compare(_snapshot(), _snapshot())
    assert result["drift_notes"] == []
    assert "holds" in result["summary"]
    assert result["advisory_only"] is True


def test_lighting_shift_names_concrete_tags():
    service = RevisionIdentityComparisonService()
    original = _snapshot(dominant_lighting_tags=["low_key"])
    revision = _snapshot(dominant_lighting_tags=["high_key"])
    result = service.compare(original, revision)
    assert len(result["drift_notes"]) == 1
    note = result["drift_notes"][0]
    assert "lighting" in note
    assert "low_key" in note
    assert "high_key" in note


def test_added_tag_only():
    service = RevisionIdentityComparisonService()
    original = _snapshot(dominant_palette=[])
    revision = _snapshot(dominant_palette=["amber"])
    result = service.compare(original, revision)
    assert "introduces" in result["drift_notes"][0]


def test_dropped_tag_only():
    service = RevisionIdentityComparisonService()
    original = _snapshot(dominant_mood_tags=["melancholic", "tense"])
    revision = _snapshot(dominant_mood_tags=["melancholic"])
    result = service.compare(original, revision)
    assert "drops" in result["drift_notes"][0]
    assert "tense" in result["drift_notes"][0]


def test_missing_snapshot_stays_silent():
    service = RevisionIdentityComparisonService()
    result = service.compare(None, _snapshot())
    assert result["drift_notes"] == []
    assert result["summary"] == ""


def test_output_never_contains_scores_or_percentages():
    service = RevisionIdentityComparisonService()
    original = _snapshot(dominant_lighting_tags=["low_key"], dominant_palette=["amber"])
    revision = _snapshot(dominant_lighting_tags=["high_key"], dominant_palette=["cyan"])
    result = service.compare(original, revision)
    for note in result["drift_notes"] + [result["summary"]]:
        assert "%" not in note
        assert "/10" not in note
        assert "score" not in note.lower()
