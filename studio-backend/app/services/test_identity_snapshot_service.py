"""Tests for IdentitySnapshotService."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.identity_snapshot_service import (
    SNAPSHOT_METADATA_KEY,
    IdentitySnapshotService,
)


class _FakeStyle:
    def __init__(self, signature):
        self._signature = signature

    def get_latest_director_signature(self, project_id):
        return self._signature


class _BrokenStyle:
    def get_latest_director_signature(self, project_id):
        raise RuntimeError("storage offline")


def _signature(**overrides):
    base = {
        "signature_id": "sig_001",
        "visual_language_summary": "Low, warm, patient.",
        "dominant_mood_tags": ["melancholic", "tender"],
        "dominant_lighting_tags": ["low_key"],
        "dominant_composition_tags": ["centered"],
        "dominant_palette": ["amber"],
        "pacing_notes": "Long takes.",
        "metadata": {"insufficient_data": False},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_capture_builds_snapshot():
    service = IdentitySnapshotService(style_intelligence=_FakeStyle(_signature()))
    snapshot = service.capture("proj-1")
    assert snapshot["snapshot_id"] == "sig_001"
    assert snapshot["version"] == 1
    assert snapshot["advisory_only"] is True
    assert snapshot["dominant_lighting_tags"] == ["low_key"]
    assert "captured_at" in snapshot


def test_capture_silent_without_signature():
    service = IdentitySnapshotService(style_intelligence=_FakeStyle(None))
    assert service.capture("proj-1") is None


def test_capture_silent_when_insufficient_data():
    sig = _signature(metadata={"insufficient_data": True})
    service = IdentitySnapshotService(style_intelligence=_FakeStyle(sig))
    assert service.capture("proj-1") is None


def test_capture_silent_without_project_id():
    service = IdentitySnapshotService(style_intelligence=_FakeStyle(_signature()))
    assert service.capture("") is None


def test_capture_failure_is_non_blocking():
    service = IdentitySnapshotService(style_intelligence=_BrokenStyle())
    assert service.capture("proj-1") is None


def test_attach_to_metadata_preserves_existing_keys():
    service = IdentitySnapshotService(style_intelligence=_FakeStyle(_signature()))
    merged = service.attach_to_metadata({"existing": "keep"}, "proj-1")
    assert merged["existing"] == "keep"
    assert merged[SNAPSHOT_METADATA_KEY]["snapshot_id"] == "sig_001"


def test_attach_to_metadata_without_signature_leaves_metadata_unchanged():
    service = IdentitySnapshotService(style_intelligence=_FakeStyle(None))
    merged = service.attach_to_metadata({"existing": "keep"}, "proj-1")
    assert merged == {"existing": "keep"}
