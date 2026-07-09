#!/usr/bin/env python3
"""
Test the corrector on the real failed adherence score from manual_adherence_check.py

This script demonstrates what CorrectiveDiff would be generated from the real
0.0/100 score with all 5 dimensions failing, even though manual_review verdict
normally prevents auto-correction.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.adherence_service import AdherenceService, AdherenceScore, DimensionScore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_corrector")


async def main():
    """Test corrector on real failure from manual_adherence_check.py"""
    
    # Check for GROQ_API_KEY
    if not os.getenv("GROQ_API_KEY"):
        logger.error("GROQ_API_KEY not found - cannot generate corrective diff")
        sys.exit(1)
    
    # Recreate the real AdherenceScore from the manual test output
    # This is the REAL score from vision model, not mocked
    score = AdherenceScore(
        shot_id="manual_test",
        attempt_n=1,
        adherence_score=0.0,
        verdict="manual_review",
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=0.0,
                evidence="The shot features two older individuals (an older woman in a blue apron and an older man in a plaid shirt) on a beach/pier, not a young man alone. Neither is wearing a red jacket.",
                expected="young man alone, wearing a red jacket",
                observed="Two older individuals (woman in blue apron, man in plaid shirt) are present; they are not alone, nor young, nor wearing a red jacket.",
            ),
            "action": DimensionScore(
                score=0.0,
                evidence="The woman is standing and gesturing, while the man is bending over, appearing to sweep or clean on a wooden pier. Neither is running, and the beach is not empty, featuring boats and people.",
                expected="running along an empty beach",
                observed="An older woman is standing, and an older man is sweeping on a pier. No one is running, and the beach is occupied by boats and people.",
            ),
            "camera": DimensionScore(
                score=0.0,
                evidence="The shot is a wide or establishing shot, showing a broad view of the beach, boats, village, and people. It is far from an extreme close-up.",
                expected="extreme close-up",
                observed="A wide shot capturing a village, beach, boats, and individuals.",
            ),
            "lighting": DimensionScore(
                score=0.0,
                evidence="The scene is lit by a warm, golden sunset or sunrise, with clear skies and visible sunlight. This is the opposite of nighttime, dark, or stormy conditions.",
                expected="nighttime, dark and stormy",
                observed="Golden hour lighting (sunset/sunrise) with clear skies and bright, warm tones.",
            ),
            "environment_persistence": DimensionScore(
                score=0.0,
                evidence="The environment consists of a coastal village with numerous white buildings and red roofs, a sandy beach with several fishing boats, a wooden pier, and visible water (ocean/sea). This is a complete mismatch for an empty desert with no water and no buildings.",
                expected="empty desert, no water, no buildings",
                observed="A coastal village with multiple buildings, a sandy beach with boats, a wooden pier, and visible water.",
            ),
        },
        temporal_drift={
            "start_score": 0.0,
            "end_score": 0.0,
            "description": "No temporal drift detected",
        },
        failed_slots=["character_state", "action", "camera", "lighting", "environment_persistence"],
    )
    
    # Current slots (the deliberately wrong ones we provided)
    current_slots = {
        "character_state": "young man alone, wearing a red jacket",
        "action": "running along an empty beach",
        "camera": "extreme close-up",
        "lighting": "nighttime, dark and stormy",
        "environment_persistence": "empty desert, no water, no buildings",
    }
    
    logger.info("=" * 80)
    logger.info("TESTING CORRECTOR ON REAL FAILED ADHERENCE SCORE")
    logger.info("=" * 80)
    logger.info(f"Score: {score.adherence_score}/100")
    logger.info(f"Verdict: {score.verdict}")
    logger.info(f"Failed slots: {score.failed_slots}")
    logger.info("")
    logger.info("NOTE: This is manual_review (all 5 slots failed), so normally")
    logger.info("auto-correction would be SKIPPED. This test forces corrector")
    logger.info("to run to demonstrate what diff it would generate.")
    logger.info("=" * 80)
    logger.info("")
    
    # Create service and generate corrective diff
    service = AdherenceService()
    
    logger.info("Calling generate_corrective_diff() with real failure data...")
    diff = await service.generate_corrective_diff(
        score=score,
        current_slots=current_slots,
        chars_remaining=200,
    )
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("CORRECTIVE DIFF GENERATED")
    logger.info("=" * 80)
    logger.info(f"Base Attempt: {diff.base_attempt}")
    logger.info(f"Seed Locked: {diff.seed_locked}")
    logger.info(f"Operations: {len(diff.ops)}")
    logger.info(f"Characters Remaining: {diff.chars_remaining}")
    logger.info("")
    
    if not diff.ops:
        logger.info("⚠️  NO CORRECTION OPERATIONS GENERATED")
        logger.info("This means the corrector declined to make changes,")
        logger.info("likely because the failure is too severe.")
    else:
        logger.info("CORRECTION OPERATIONS:")
        logger.info("-" * 80)
        for idx, op in enumerate(diff.ops, 1):
            logger.info(f"\nOperation {idx}: {op.slot.upper().replace('_', ' ')}")
            logger.info(f"  Type: {op.op}")
            logger.info(f"  Old Text: {op.old_text}")
            logger.info(f"  New Text: {op.new_text}")
            logger.info(f"  Reason: {op.reason}")
            logger.info(f"  Char Delta: {op.char_delta:+d}")
    
    logger.info("")
    logger.info("=" * 80)
    
    # Also output as JSON for inspection
    logger.info("")
    logger.info("JSON OUTPUT:")
    logger.info("-" * 80)
    output = {
        "score": {
            "shot_id": score.shot_id,
            "attempt_n": score.attempt_n,
            "adherence_score": score.adherence_score,
            "verdict": score.verdict,
            "failed_slots": score.failed_slots,
        },
        "diff": {
            "base_attempt": diff.base_attempt,
            "seed_locked": diff.seed_locked,
            "chars_remaining": diff.chars_remaining,
            "ops": [
                {
                    "slot": op.slot,
                    "op": op.op,
                    "old_text": op.old_text,
                    "new_text": op.new_text,
                    "reason": op.reason,
                    "char_delta": op.char_delta,
                }
                for op in diff.ops
            ],
        },
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
