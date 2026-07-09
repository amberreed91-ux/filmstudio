"""
Test defensive validation logic extracted from _call_vision_model().

This test directly exercises the validation logic (lines 1082-1144 in adherence_service.py)
without calling any real API. It verifies that malformed Gemini responses produce
clear, specific ValueError messages.
"""

import pytest


def validate_vision_response(result: dict) -> None:
    """
    Extracted defensive validation logic from _call_vision_model().
    
    This mirrors the validation at lines 1094-1144 of adherence_service.py.
    Raises ValueError with specific messages for each type of malformed input.
    """
    # 1. "dimensions" must exist and be a dict
    if "dimensions" not in result:
        raise ValueError(
            "Gemini response missing required key 'dimensions'. "
            f"Available keys: {list(result.keys())}"
        )
    if not isinstance(result["dimensions"], dict):
        raise ValueError(
            f"Gemini returned 'dimensions' as type {type(result['dimensions']).__name__}, "
            f"expected dict. Value: {result['dimensions']!r}"
        )

    # 2. "temporal_drift" must exist and be a dict
    if "temporal_drift" not in result:
        raise ValueError(
            "Gemini response missing required key 'temporal_drift'. "
            f"Available keys: {list(result.keys())}"
        )
    if not isinstance(result["temporal_drift"], dict):
        raise ValueError(
            f"Gemini returned 'temporal_drift' as type {type(result['temporal_drift']).__name__}, "
            f"expected dict. Value: {result['temporal_drift']!r}"
        )

    # 3. Each required dimension must exist, be a dict, and contain "score"
    required_dimensions = [
        "character_state", "action", "camera",
        "lighting", "environment_persistence",
    ]
    for dim in required_dimensions:
        if dim not in result["dimensions"]:
            raise ValueError(
                f"Gemini response missing required dimension '{dim}' in 'dimensions'. "
                f"Available dimensions: {list(result['dimensions'].keys())}"
            )
        dim_value = result["dimensions"][dim]
        if not isinstance(dim_value, dict):
            raise ValueError(
                f"Gemini returned dimension '{dim}' as type {type(dim_value).__name__}, "
                f"expected dict. Value: {dim_value!r}"
            )
        if "score" not in dim_value:
            raise ValueError(
                f"Dimension '{dim}' missing required 'score' field. "
                f"Available fields: {list(dim_value.keys())}. Value: {dim_value!r}"
            )
        if not isinstance(dim_value["score"], (int, float)):
            raise ValueError(
                f"Dimension '{dim}' has 'score' of type {type(dim_value['score']).__name__}, "
                f"expected int or float. Value: {dim_value['score']!r}"
            )


# --- Test cases matching tonight's real Gemini failures ---

def test_dimensions_as_list_raises_value_error():
    """Case 1: 'dimensions' as a list instead of dict."""
    bad_response = {
        "dimensions": [
            {"score": 85, "evidence": "...", "expected": "...", "observed": "..."},
            {"score": 72, "evidence": "...", "expected": "...", "observed": "..."},
        ],
        "temporal_drift": {"start_score": 85, "end_score": 72},
    }
    
    with pytest.raises(ValueError) as exc_info:
        validate_vision_response(bad_response)
    
    msg = str(exc_info.value)
    assert "'dimensions' as type list" in msg
    assert "expected dict" in msg
    print(f"Case 1 (dimensions as list): {msg}")


def test_dimension_score_missing_raises_value_error():
    """Case 2: A dimension value is a raw float instead of dict with 'score'."""
    bad_response = {
        "dimensions": {
            "character_state": 85.5,  # raw float, missing "score" key
            "action": {"score": 72, "evidence": "...", "expected": "...", "observed": "..."},
            "camera": {"score": 90, "evidence": "...", "expected": "...", "observed": "..."},
            "lighting": {"score": 88, "evidence": "...", "expected": "...", "observed": "..."},
            "environment_persistence": {"score": 80, "evidence": "...", "expected": "...", "observed": "..."},
        },
        "temporal_drift": {"start_score": 85, "end_score": 72},
    }
    
    with pytest.raises(ValueError) as exc_info:
        validate_vision_response(bad_response)
    
    msg = str(exc_info.value)
    assert "'character_state' as type float" in msg
    assert "expected dict" in msg
    print(f"Case 2 (dimension as raw float): {msg}")


def test_missing_dimensions_key_raises_value_error():
    """Case 3: 'dimensions' key missing entirely."""
    bad_response = {
        "temporal_drift": {"start_score": 85, "end_score": 72},
        "some_other_key": "unexpected",
    }
    
    with pytest.raises(ValueError) as exc_info:
        validate_vision_response(bad_response)
    
    msg = str(exc_info.value)
    assert "missing required key 'dimensions'" in msg
    assert "Available keys:" in msg
    print(f"Case 3 (missing 'dimensions' key): {msg}")


def test_valid_response_passes():
    """Sanity check: a well-formed response should not raise."""
    good_response = {
        "dimensions": {
            "character_state": {"score": 85, "evidence": "...", "expected": "...", "observed": "..."},
            "action": {"score": 72, "evidence": "...", "expected": "...", "observed": "..."},
            "camera": {"score": 90, "evidence": "...", "expected": "...", "observed": "..."},
            "lighting": {"score": 88, "evidence": "...", "expected": "...", "observed": "..."},
            "environment_persistence": {"score": 80, "evidence": "...", "expected": "...", "observed": "..."},
        },
        "temporal_drift": {"start_score": 85, "end_score": 72},
    }
    
    # Should not raise
    validate_vision_response(good_response)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])