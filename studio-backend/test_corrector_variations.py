#!/usr/bin/env python3
"""
Corrector Variation Test - Tests different failure scenarios.

Tests the corrector with various failure types to see operation type selection:
1. Minor failure (score ~55) - should use strengthen/prepend_emphasis
2. Moderate failure (score ~35) - might use replace
3. Severe failure (score <20) - should use replace
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from app.services.adherence_service import AdherenceService, AdherenceScore, DimensionScore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_corrector_variations")


@pytest.mark.skipif(not os.environ.get("STUDIO_ALLOW_LIVE_NETWORK_TESTS"), reason="makes a live network call (LLM); run only with owner authorization")
async def test_minor_failure():
    """Test with minor failures - should see strengthen/prepend_emphasis ops."""
    print("\n" + "=" * 80)
    print("TEST CASE 1: MINOR FAILURE (Score ~55)")
    print("=" * 80)
    
    current_slots = {
        "character_state": "elderly man, weathered face, gray hair",
        "action": "sitting quietly at wooden table",
        "camera": "medium closeup, static",
        "lighting": "soft natural window light",
        "environment_persistence": "rustic kitchen interior",
    }
    
    # Only lighting is slightly off
    failed_dimensions = {
        "lighting": DimensionScore(
            score=55.0,
            evidence="Lighting is present but appears slightly cooler/bluer than expected soft warm window light",
            expected="soft natural window light",
            observed="soft natural window light with slight blue tint",
        ),
    }
    
    mock_score = AdherenceScore(
        shot_id="test_minor",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            **failed_dimensions,
            "character_state": DimensionScore(score=85.0, evidence="Good", expected="", observed=""),
            "action": DimensionScore(score=80.0, evidence="Good", expected="", observed=""),
            "camera": DimensionScore(score=75.0, evidence="Good", expected="", observed=""),
            "environment_persistence": DimensionScore(score=90.0, evidence="Good", expected="", observed=""),
        },
        temporal_drift={"start_score": 75.0, "end_score": 78.0},
        adherence_score=77.0,
        verdict="correctable",
        failed_slots=["lighting"],
    )
    
    print("\nFailed Dimension:")
    for slot in mock_score.failed_slots:
        dim = mock_score.dimensions[slot]
        print(f"  {slot}: Score {dim.score:.1f}")
        print(f"    Expected: {dim.expected}")
        print(f"    Observed: {dim.observed}")
    
    service = AdherenceService()
    diff = await service.generate_corrective_diff(mock_score, current_slots, 200)
    
    print(f"\nGenerated {len(diff.ops)} operation(s):")
    for op in diff.ops:
        print(f"  - {op.slot}: {op.op}")
        print(f"    Old: {op.old_text}")
        print(f"    New: {op.new_text}")
        print(f"    Reason: {op.reason}")
        print(f"    Delta: {op.char_delta:+d}")


@pytest.mark.skipif(not os.environ.get("STUDIO_ALLOW_LIVE_NETWORK_TESTS"), reason="makes a live network call (LLM); run only with owner authorization")
async def test_moderate_failure():
    """Test with moderate failure - character exists but details wrong."""
    print("\n" + "=" * 80)
    print("TEST CASE 2: MODERATE FAILURE (Score ~35)")
    print("=" * 80)
    
    current_slots = {
        "character_state": "young woman, red dress, long dark hair",
        "action": "dancing gracefully in center of room",
        "camera": "tracking shot, circling subject",
        "lighting": "dramatic spotlight from above",
        "environment_persistence": "elegant ballroom",
    }
    
    # Character and action moderately off
    failed_dimensions = {
        "character_state": DimensionScore(
            score=35.0,
            evidence="Character is female and has long dark hair, but wearing blue dress not red",
            expected="young woman, red dress, long dark hair",
            observed="young woman, blue dress, long dark hair",
        ),
        "action": DimensionScore(
            score=40.0,
            evidence="Character is moving but appears to be walking slowly, not dancing gracefully",
            expected="dancing gracefully in center of room",
            observed="walking slowly across the room",
        ),
    }
    
    mock_score = AdherenceScore(
        shot_id="test_moderate",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            **failed_dimensions,
            "camera": DimensionScore(score=70.0, evidence="Good", expected="", observed=""),
            "lighting": DimensionScore(score=65.0, evidence="Good", expected="", observed=""),
            "environment_persistence": DimensionScore(score=80.0, evidence="Good", expected="", observed=""),
        },
        temporal_drift={"start_score": 60.0, "end_score": 58.0},
        adherence_score=58.0,
        verdict="correctable",
        failed_slots=["character_state", "action"],
    )
    
    print("\nFailed Dimensions:")
    for slot in mock_score.failed_slots:
        dim = mock_score.dimensions[slot]
        print(f"  {slot}: Score {dim.score:.1f}")
        print(f"    Expected: {dim.expected}")
        print(f"    Observed: {dim.observed}")
    
    service = AdherenceService()
    diff = await service.generate_corrective_diff(mock_score, current_slots, 200)
    
    print(f"\nGenerated {len(diff.ops)} operation(s):")
    for op in diff.ops:
        print(f"  - {op.slot}: {op.op}")
        print(f"    Old: {op.old_text}")
        print(f"    New: {op.new_text}")
        print(f"    Reason: {op.reason}")
        print(f"    Delta: {op.char_delta:+d}")


async def main():
    if not os.getenv("GROQ_API_KEY"):
        raise EnvironmentError("GROQ_API_KEY required")
    
    print("\nTESTING CORRECTOR WITH DIFFERENT FAILURE SEVERITIES")
    print("=" * 80)
    
    await test_minor_failure()
    await asyncio.sleep(1)  # Rate limiting
    
    await test_moderate_failure()
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
