#!/usr/bin/env python3
"""
Phase 1 only: Generate the full-corrected prompt via REAL Groq call and verify
verbatim carry-forward. Does NOT submit to Runway. Used to show the user the
assembled prompt before they authorize real render spend.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.services.adherence_service import (
    AdherenceService,
    AdherenceScore,
    DimensionScore,
    FullCorrectedPrompt,
)

SHOT_ID = "scene_001"

ATTEMPT1_SLOTS = {
    "character_state": "People fill the streets",
    "action": "Music, laughter, food stands. Everything is vibrant",
    "environment_persistence": "Chicago is alive. The L train moves through the skyline",
    "camera": "Wide shot",
    "lighting": "golden hour light",
}

ATTEMPT1_SCORE_JSON = {
    "shot_id": SHOT_ID,
    "attempt_n": 1,
    "frames_scored": [0.1, 0.5, 0.9],
    "dimensions": {
        "character_state": {
            "score": 0,
            "evidence": "Render focused on cityscape without showing people at human scale",
            "expected": "People fill the streets",
            "observed": "Wide cityscape with no visible human figures at scale",
        },
        "action": {
            "score": 0,
            "evidence": "No human activity shown - only static urban environment",
            "expected": "Music, laughter, food stands. Everything is vibrant",
            "observed": "Static city view with no human activity visible",
        },
        "camera": {
            "score": 100,
            "evidence": "Wide shot executed correctly",
            "expected": "Wide shot",
            "observed": "Wide shot of cityscape",
        },
        "lighting": {
            "score": 100,
            "evidence": "Golden hour lighting captured accurately",
            "expected": "golden hour light",
            "observed": "Golden hour light on buildings",
        },
        "environment_persistence": {
            "score": 100,
            "evidence": "Chicago cityscape with L train and skyline visible throughout",
            "expected": "Chicago is alive. The L train moves through the skyline",
            "observed": "Chicago skyline with L train visible",
        },
    },
    "temporal_drift": {"start_score": 100, "end_score": 100},
    "adherence_score": 55.0,
    "verdict": "correctable",
    "failed_slots": ["character_state", "action"],
}


def reconstruct_attempt1_score() -> AdherenceScore:
    dims = {}
    for name, data in ATTEMPT1_SCORE_JSON["dimensions"].items():
        dims[name] = DimensionScore(
            score=data["score"],
            evidence=data["evidence"],
            expected=data["expected"],
            observed=data["observed"],
        )
    return AdherenceScore(
        shot_id=ATTEMPT1_SCORE_JSON["shot_id"],
        attempt_n=ATTEMPT1_SCORE_JSON["attempt_n"],
        frames_scored=ATTEMPT1_SCORE_JSON["frames_scored"],
        dimensions=dims,
        temporal_drift=ATTEMPT1_SCORE_JSON["temporal_drift"],
        adherence_score=ATTEMPT1_SCORE_JSON["adherence_score"],
        verdict=ATTEMPT1_SCORE_JSON["verdict"],
        failed_slots=ATTEMPT1_SCORE_JSON["failed_slots"],
    )


async def main():
    print("=" * 80)
    print("PHASE 1: GENERATE FULL-CORRECTED PROMPT (REAL Groq call — NO Runway spend)")
    print("=" * 80)

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    print(f"\n[ENV CHECK] GROQ_API_KEY present: {bool(groq_key)}")
    if not groq_key:
        print("❌ Missing GROQ_API_KEY!")
        return

    # Reconstruct attempt 1 score
    print(f"\n{'─' * 80}")
    print("RECONSTRUCTING ATTEMPT 1 SCORE")
    print(f"{'─' * 80}")

    attempt1_score = reconstruct_attempt1_score()
    print(f"  Adherence Score: {attempt1_score.adherence_score}/100")
    print(f"  Verdict: {attempt1_score.verdict}")
    print(f"  Failed Slots: {attempt1_score.failed_slots}")
    print(f"\n  Dimension Scores:")
    for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
        dim = attempt1_score.dimensions[dim_name]
        status = "FAILED" if dim_name in attempt1_score.failed_slots else "PASSED"
        print(f"    - {dim_name}: {dim.score}/100  [{status}]")

    # Generate full-corrected prompt via REAL Groq call
    print(f"\n{'─' * 80}")
    print("GENERATING FULL-CORRECTED PROMPT (REAL Groq call — NOT mocked)")
    print(f"{'─' * 80}")

    adherence_service = AdherenceService()

    print("\n[STEP 1] Calling build_full_corrected_prompt() → _call_groq_full_corrector()...")
    full_prompt: FullCorrectedPrompt = await adherence_service.build_full_corrected_prompt(
        score=attempt1_score,
        current_slots=ATTEMPT1_SLOTS,
        max_prompt_length=512,
    )

    # Show the assembled prompt text
    print(f"\n{'═' * 80}")
    print("ASSEMBLED FULL-CORRECTED PROMPT")
    print(f"{'═' * 80}")
    print(f"\n  Prompt ({len(full_prompt.prompt)} chars):")
    print(f"  \"{full_prompt.prompt}\"")
    print(f"\n  Chars remaining: {full_prompt.chars_remaining}")
    print(f"  Compressed slots: {full_prompt.compressed_slots}")

    print(f"\n  Final slots:")
    for slot_name in ['character_state', 'action', 'environment_persistence', 'camera', 'lighting']:
        val = full_prompt.slots.get(slot_name, "")
        prov = full_prompt.provenance.get(slot_name, "?")
        print(f"    {slot_name}: \"{val}\"  [{prov}]")

    # Verify verbatim carry-forward
    print(f"\n{'═' * 80}")
    print("VERBATIM CARRY-FORWARD VERIFICATION")
    print(f"{'═' * 80}")

    passing_slots = {
        "camera": "Wide shot",
        "lighting": "golden hour light",
        "environment_persistence": "Chicago is alive. The L train moves through the skyline",
    }

    all_verbatim = True
    for slot_name, expected_text in passing_slots.items():
        actual = full_prompt.slots.get(slot_name, "")
        is_verbatim = actual == expected_text
        in_prompt = expected_text in full_prompt.prompt
        status = "✓ VERBATIM" if is_verbatim else "✗ MISMATCH"
        prompt_status = "✓ in prompt" if in_prompt else "✗ NOT in prompt"
        print(f"  {slot_name}:")
        print(f"    Expected (attempt 1): \"{expected_text}\"")
        print(f"    Actual (attempt 4):   \"{actual}\"")
        print(f"    {status}  |  {prompt_status}")
        if not is_verbatim or not in_prompt:
            all_verbatim = False

    print(f"\n  Failing slots (should be corrected, not verbatim):")
    for slot_name in ["character_state", "action"]:
        original = ATTEMPT1_SLOTS.get(slot_name, "")
        corrected = full_prompt.slots.get(slot_name, "")
        changed = "← CHANGED" if original != corrected else "(unchanged — fallback)"
        print(f"    {slot_name}:")
        print(f"      Original:  \"{original}\"")
        print(f"      Corrected: \"{corrected}\"  {changed}")

    if not all_verbatim:
        print("\n❌ VERBATIM CARRY-FORWARD FAILED!")
    else:
        print("\n✓ All passing slots carried forward VERBATIM, exactly as they appeared in attempt 1.")

    # Output machine-readable JSON for downstream consumption
    print(f"\n{'═' * 80}")
    print("MACHINE-READABLE OUTPUT (for downstream consumption)")
    print(f"{'═' * 80}")
    output = {
        "prompt": full_prompt.prompt,
        "slots": full_prompt.slots,
        "provenance": full_prompt.provenance,
        "chars_remaining": full_prompt.chars_remaining,
        "compressed_slots": full_prompt.compressed_slots,
        "verbatim_verified": all_verbatim,
    }
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    asyncio.run(main())