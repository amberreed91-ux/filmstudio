from __future__ import annotations

from app.services.editing_intelligence_service import editing_intelligence_service
from app.services.script_parser import ScriptParser


def test_editing_intelligence_generates_advisory_suggestions_for_key_editing_axes():
    result = editing_intelligence_service.build_editing_intelligence(
        screening_playlist=[
            {"scene_id": "scene_001", "status": "complete", "verdict": "strong", "duration_estimate": 4},
            {"scene_id": "scene_002", "status": "partial", "verdict": "needs_revision", "duration_estimate": 5},
            {"scene_id": "scene_003", "status": "failed", "verdict": "failed", "duration_estimate": 3},
        ],
        scene_transitions=[
            {"scene_id": "scene_001", "transition": "hold", "duration": 4},
            {"scene_id": "scene_002", "transition": "hold", "duration": 5},
        ],
        emotional_continuity={"score": 0.62, "status": "drifting", "issues": ["abrupt swings"]},
        sequence_flow={"flow_score": 0.48, "issues": ["Repeated hold transitions reduce momentum"]},
    )
    editing = result["editing_intelligence"]
    suggestions = editing["suggestions"]

    assert editing["advisory_only"] is True
    assert editing["suggestion_count"] >= 3
    types = {row.get("suggestion_type") for row in suggestions}
    assert "pacing_trims" in types
    assert "transition_improvements" in types
    assert "emotional_timing" in types
    assert all(row.get("advisory_only") is True for row in suggestions)


def test_script_breakdown_bundle_includes_editing_intelligence_fields():
    bundle = ScriptParser().build_script_breakdown_bundle(
        """
INT. LOFT - NIGHT
NORA hesitates at the door while rain drills the glass.

EXT. OVERPASS - NIGHT
A train screams by as she chooses silence.

INT. STAIRWELL - DAWN
She exhales and steps into pale light.
"""
    )

    assert isinstance(bundle.get("editing_intelligence"), dict)
    assert isinstance(bundle.get("editing_suggestions"), list)
    assert bundle["editing_intelligence"].get("advisory_only") is True
    assert isinstance(bundle["editing_intelligence"].get("suggestion_count"), int)

