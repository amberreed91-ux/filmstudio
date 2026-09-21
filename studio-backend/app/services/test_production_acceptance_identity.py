"""Tests for the identity-continuity advisory check in production acceptance."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.production_acceptance import ProductionAcceptanceContextSnapshot
from app.services.production_acceptance_service import (
    ProductionAcceptanceContext,
    production_acceptance_service,
)


def _context(render_jobs=None, revisions=None):
    return ProductionAcceptanceContext(
        project_id="proj-1",
        package=None,
        project={},
        render_jobs=render_jobs or [],
        render_attempts=[],
        reviews=[],
        revisions=revisions or [],
        production_scan=None,
        decision_gate=None,
        continuity_issues=[],
        style_drift_issues=[],
        memories=[],
        video_assets=[],
        keyframes=[],
        frame_analyses=[],
        scene_ids=[],
        snapshot=ProductionAcceptanceContextSnapshot(project_id="proj-1"),
    )


def _item(created_at, snapshot):
    return SimpleNamespace(
        created_at=created_at,
        metadata={"cinematic_identity_snapshot": snapshot},
    )


def _snapshot(lighting):
    return {
        "snapshot_id": "sig",
        "dominant_mood_tags": [],
        "dominant_lighting_tags": lighting,
        "dominant_composition_tags": [],
        "dominant_palette": [],
    }


def test_thin_evidence_is_not_applicable():
    context = _context(render_jobs=[_item("2026-01-01T00:00:00", _snapshot(["low_key"]))])
    result = production_acceptance_service._check_identity_continuity(context)
    assert result.severity == "not_applicable"
    assert result.co_director_note == ""


def test_identity_shift_surfaces_warning_note():
    context = _context(
        render_jobs=[
            _item("2026-01-01T00:00:00", _snapshot(["low_key"])),
            _item("2026-01-02T00:00:00", _snapshot(["high_key"])),
        ]
    )
    result = production_acceptance_service._check_identity_continuity(context)
    assert result.severity == "warning"
    assert result.co_director_note
    assert "low_key" in result.co_director_note
    assert "%" not in result.co_director_note
    assert "score" not in result.co_director_note.lower()


def test_identity_holds_is_a_pass():
    context = _context(
        render_jobs=[
            _item("2026-01-01T00:00:00", _snapshot(["low_key"])),
            _item("2026-01-02T00:00:00", _snapshot(["low_key"])),
        ]
    )
    result = production_acceptance_service._check_identity_continuity(context)
    assert result.severity == "pass"


def test_revisions_are_compared_too():
    context = _context(
        revisions=[
            _item("2026-01-01T00:00:00", _snapshot(["low_key"])),
            _item("2026-01-02T00:00:00", _snapshot(["high_key"])),
        ]
    )
    result = production_acceptance_service._check_identity_continuity(context)
    assert result.severity == "warning"


def test_items_without_snapshots_are_ignored():
    context = _context(
        render_jobs=[
            SimpleNamespace(created_at="2026-01-01T00:00:00", metadata={}),
            SimpleNamespace(created_at="2026-01-02T00:00:00", metadata=None),
        ]
    )
    result = production_acceptance_service._check_identity_continuity(context)
    assert result.severity == "not_applicable"
