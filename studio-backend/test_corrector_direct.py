#!/usr/bin/env python3
"""
Direct Corrector Test - Tests the Groq corrector in isolation.

This script tests the corrective diff generator without needing actual video frames.
It simulates a failed adherence score and calls the corrector directly.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.adherence_service import AdherenceService, AdherenceScore, DimensionScore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_corrector")


async def test_corrector():
    """Test the Groq corrector with a simulated failed adherence score."""
    
    # Check for GROQ_API_KEY
    if not os.getenv("GROQ_API_KEY"):
        raise EnvironmentError(
            "GROQ_API_KEY not found in environment. "
            "Please set it before running this script."
        )
    
    # Simulate a failed adherence score (the "red jacket in desert" vs "fishing village" case)
    current_slots = {
        "character_state": "woman wearing bright red jacket, blonde hair",
        "action": "walking through sandy desert dunes",
        "camera": "wide establishing shot, drone perspective",
        "lighting": "harsh midday sun, deep shadows",
        "environment_persistence": "vast empty desert, no vegetation",
    }
    
    # Create mock dimension scores for failed dimensions
    failed_dimensions = {
        "character_state": DimensionScore(
            score=15.0,
            evidence="Character is wearing dark blue clothing, not red. Hair appears dark, not blonde.",
            expected="woman wearing bright red jacket, blonde hair",
            observed="woman in dark blue coat, dark hair, walking along coastal path",
        ),
        "action": DimensionScore(
            score=30.0,
            evidence="Character is walking along a coastal path, not through desert dunes.",
            expected="walking through sandy desert dunes",
            observed="walking along rocky coastal cliffside path",
        ),
        "environment_persistence": DimensionScore(
            score=5.0,
            evidence="Environment is coastal village with buildings and ocean, completely different from desert.",
            expected="vast empty desert, no vegetation",
            observed="coastal fishing village, stone buildings, ocean visible, lush vegetation",
        ),
        "lighting": DimensionScore(
            score=40.0,
            evidence="Lighting is soft overcast, not harsh midday sun. No deep shadows visible.",
            expected="harsh midday sun, deep shadows",
            observed="soft overcast daylight, diffused shadows",
        ),
    }
    
    # Create mock AdherenceScore
    mock_score = AdherenceScore(
        shot_id="test_corrector",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={**failed_dimensions, "camera": DimensionScore(
            score=65.0,  # This one passes
            evidence="Camera work is reasonably wide, but more handheld than drone",
            expected="wide establishing shot, drone perspective",
            observed="wide handheld shot, tracking character",
        )},
        temporal_drift={"start_score": 20.0, "end_score": 25.0},
        adherence_score=28.0,  # Would be "correctable" (between 50-80)
        verdict="correctable",
        failed_slots=["character_state", "action", "environment_persistence", "lighting"],
    )
    
    # Print the mock scenario
    print("=" * 80)
    print("TESTING CORRECTIVE DIFF GENERATOR")
    print("=" * 80)
    print("\nCurrent Slots (Deliberately Wrong for Testing):")
    for slot, text in current_slots.items():
        print(f"  {slot}: {text}")
    
    print("\nFailed Dimensions:")
    for slot in mock_score.failed_slots:
        dim = mock_score.dimensions[slot]
        print(f"\n  {slot.upper().replace('_', ' ')} (Score: {dim.score:.1f})")
        print(f"    Expected:  {dim.expected}")
        print(f"    Observed:  {dim.observed}")
        print(f"    Evidence:  {dim.evidence}")
    
    print("\n" + "=" * 80)
    print("CALLING GROQ CORRECTOR...")
    print("=" * 80 + "\n")
    
    # Create service and call corrector
    service = AdherenceService()
    
    diff = await service.generate_corrective_diff(
        score=mock_score,
        current_slots=current_slots,
        chars_remaining=200,
    )
    
    # Print results
    print("\n" + "=" * 80)
    print("CORRECTIVE DIFF RESULT")
    print("=" * 80)
    print(f"Base Attempt: {diff.base_attempt}")
    print(f"Seed Locked: {diff.seed_locked}")
    print(f"Operations: {len(diff.ops)}")
    print(f"Characters Remaining: {diff.chars_remaining}")
    
    if diff.ops:
        print("\nCORRECTION OPERATIONS:")
        print("-" * 80)
        for idx, op in enumerate(diff.ops, 1):
            print(f"\nOperation {idx}: {op.slot.upper().replace('_', ' ')}")
            print(f"  Type:       {op.op}")
            print(f"  Old Text:   {op.old_text}")
            print(f"  New Text:   {op.new_text}")
            print(f"  Reason:     {op.reason}")
            print(f"  Char Delta: {op.char_delta:+d}")
    else:
        print("\nNo correction operations generated.")
    
    print("\n" + "=" * 80)
    print("APPLYING DIFF TO SLOTS...")
    print("=" * 80 + "\n")
    
    # Apply the diff
    new_slots = service.apply_diff(current_slots, diff, max_prompt_length=512)
    
    print("UPDATED SLOTS:")
    print("-" * 80)
    for slot, text in new_slots.items():
        if slot in [op.slot for op in diff.ops]:
            print(f"\n  {slot} [MODIFIED]:")
            print(f"    OLD: {current_slots[slot]}")
            print(f"    NEW: {text}")
        else:
            print(f"\n  {slot} [unchanged]:")
            print(f"    {text}")
    
    # Calculate prompt length
    parts = [text for text in [
        new_slots.get("character_state", ""),
        new_slots.get("action", ""),
        new_slots.get("environment_persistence", ""),
        new_slots.get("camera", ""),
        new_slots.get("lighting", ""),
    ] if text]
    assembled = ". ".join(parts) + ". Cinematic, film quality." if parts else "Cinematic shot. Film quality."
    
    print("\n" + "=" * 80)
    print(f"ASSEMBLED PROMPT ({len(assembled)} chars):")
    print("=" * 80)
    print(assembled)
    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(test_corrector())
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
