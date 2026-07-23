"""
Verification script for Step 3: _assemble_prompt_from_slots order parameter.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.render_retry_service import render_retry_service


def test_backward_compatibility():
    """Call with no order argument, confirm exact same output as before."""
    slots = {
        "character_state": "A lone figure stands in the rain",
        "action": "slow pan across the city skyline",
        "environment_persistence": "neon lights reflecting on wet streets",
        "camera": "wide angle lens",
        "lighting": "blue hour with soft practicals",
    }
    
    result = render_retry_service._assemble_prompt_from_slots(slots)
    expected = "A lone figure stands in the rain. slow pan across the city skyline. neon lights reflecting on wet streets. wide angle lens. blue hour with soft practicals. Cinematic, film quality."
    
    print("=== BACKWARD COMPATIBILITY TEST ===")
    print(f"Result:   {result!r}")
    print(f"Expected: {expected!r}")
    assert result == expected, "FAIL: Output changed without order parameter!"
    print("PASS: Behavior unchanged when order is None.\n")


def test_custom_order():
    """Call with custom order, confirm slots appear in requested order."""
    slots = {
        "character_state": "A lone figure stands in the rain",
        "action": "slow pan across the city skyline",
        "environment_persistence": "neon lights reflecting on wet streets",
        "camera": "wide angle lens",
        "lighting": "blue hour with soft practicals",
    }
    
    # Custom order: lighting first, then action, then others
    custom_order = ["lighting", "action", "camera", "character_state", "environment_persistence"]
    
    result = render_retry_service._assemble_prompt_from_slots(slots, order=custom_order)
    
    print("=== CUSTOM ORDER TEST ===")
    print(f"Custom order: {custom_order}")
    print(f"Result: {result!r}")
    
    # Verify the order of parts in the result
    parts = result.replace(". Cinematic, film quality.", "").split(". ")
    assert parts[0] == "blue hour with soft practicals", f"First slot should be lighting, got {parts[0]!r}"
    assert parts[1] == "slow pan across the city skyline", f"Second slot should be action, got {parts[1]!r}"
    assert parts[2] == "wide angle lens", f"Third slot should be camera, got {parts[2]!r}"
    assert parts[3] == "A lone figure stands in the rain", f"Fourth slot should be character_state, got {parts[3]!r}"
    assert parts[4] == "neon lights reflecting on wet streets", f"Fifth slot should be environment_persistence, got {parts[4]!r}"
    print("PASS: Slots appear in custom order.\n")


def test_empty_slots_default():
    """Empty slots with default order returns fallback."""
    result = render_retry_service._assemble_prompt_from_slots({})
    expected = "Cinematic shot. Film quality."
    print("=== EMPTY SLOTS DEFAULT TEST ===")
    print(f"Result:   {result!r}")
    print(f"Expected: {expected!r}")
    assert result == expected, "FAIL: Empty slots fallback changed!"
    print("PASS: Empty slots fallback unchanged.\n")


def test_reorder_slots_by_failure_integration():
    """Test that _reorder_slots_by_failure output can be used as order."""
    from app.services.adherence_service import DimensionScore
    
    dimension_scores = {
        "character_state": DimensionScore(score=90, evidence="ok", expected="", observed=""),
        "action": DimensionScore(score=50, evidence="fail", expected="", observed=""),
        "environment_persistence": DimensionScore(score=30, evidence="fail", expected="", observed=""),
        "camera": DimensionScore(score=85, evidence="ok", expected="", observed=""),
        "lighting": DimensionScore(score=95, evidence="ok", expected="", observed=""),
    }
    
    slots = {
        "character_state": "hero standing tall",
        "action": "walking through door",
        "environment_persistence": "rainy night street",
        "camera": "overhead drone shot",
        "lighting": "golden hour warmth",
    }
    
    order = render_retry_service._reorder_slots_by_failure(dimension_scores)
    result = render_retry_service._assemble_prompt_from_slots(slots, order=order)
    
    print("=== REORDER SLOTS BY FAILURE INTEGRATION TEST ===")
    print(f"Reorder result: {order}")
    print(f"Assembled prompt: {result!r}")
    
    # failing slots should come first, ordered weakest score first
    parts = result.replace(". Cinematic, film quality.", "").split(". ")
    assert parts[0] == "rainy night street", f"Expected weakest failing slot 'environment_persistence' first, got {parts[0]!r}"
    assert parts[1] == "walking through door", f"Expected next failing slot 'action' second, got {parts[1]!r}"
    print("PASS: _reorder_slots_by_failure output works as order parameter.\n")


if __name__ == "__main__":
    test_backward_compatibility()
    test_custom_order()
    test_empty_slots_default()
    test_reorder_slots_by_failure_integration()
    print("ALL TESTS PASSED.")
