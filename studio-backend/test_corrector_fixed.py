#!/usr/bin/env python3
"""
Test corrector with fixed threshold against real AdherenceScore.
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.adherence_service import adherence_service, AdherenceScore, DimensionScore


async def main():
    print("=" * 80)
    print("CORRECTOR TEST WITH FIXED THRESHOLD")
    print("=" * 80)
    print()
    
    storage = get_storage("sqlite")
    
    # Get the real attempt 1 from database
    shot_id = "scene_001_shot_001"
    attempts = storage.list_render_attempts(shot_id=shot_id)
    
    if not attempts:
        print("✗ No attempts found - run test_adherence_direct.py first")
        return 1
    
    attempt_1 = attempts[0]
    score_1_json = attempt_1['score_json']
    
    print("ATTEMPT 1 (from database):")
    print(f"  Shot: {score_1_json['shot_id']}")
    print(f"  Score: {score_1_json['adherence_score']}")
    print(f"  Verdict: {score_1_json['verdict']}")
    print()
    print("Dimension Scores:")
    for dim, data in score_1_json['dimensions'].items():
        marker = "✗" if data['score'] <= 70 else "✓"
        print(f"  {marker} {dim}: {data['score']}")
    print()
    
    # Reconstruct AdherenceScore object
    dimensions = {}
    for dim_name, dim_data in score_1_json['dimensions'].items():
        dimensions[dim_name] = DimensionScore(
            score=dim_data['score'],
            evidence=dim_data['evidence'],
            expected=dim_data['expected'],
            observed=dim_data['observed'],
        )
    
    score_1 = AdherenceScore(
        shot_id=score_1_json['shot_id'],
        attempt_n=score_1_json['attempt_n'],
        frames_scored=score_1_json['frames_scored'],
        dimensions=dimensions,
        temporal_drift=score_1_json.get('temporal_drift', {}),
        adherence_score=score_1_json['adherence_score'],
        verdict=score_1_json['verdict'],
        failed_slots=score_1_json.get('failed_slots', []),
    )
    
    print("=" * 80)
    print("RE-SCORING WITH FIXED THRESHOLD (score <= 70)")
    print("=" * 80)
    print()
    
    # The fixed threshold is now in the code, but failed_slots in our loaded
    # score is stale. Let's manually compute what it should be:
    fixed_failed_slots = [
        dim for dim, score_obj in dimensions.items()
        if score_obj.score <= 70
    ]
    
    print(f"With OLD threshold (< 50): {score_1.failed_slots}")
    print(f"With NEW threshold (<= 70): {fixed_failed_slots}")
    print()
    
    # Update the score object with corrected failed_slots
    score_1.failed_slots = fixed_failed_slots
    
    if not fixed_failed_slots:
        print("⚠️  Still no failed slots!")
        return 1
    
    print("=" * 80)
    print("GENERATE CORRECTIVE DIFF")
    print("=" * 80)
    print()
    
    original_prompt = attempt_1['prompt_text']
    prompt_slots = {"description": original_prompt}
    chars_remaining = 512 - len(original_prompt) + 50
    
    print(f"Original prompt: {original_prompt}")
    print(f"Failed dimensions: {fixed_failed_slots}")
    print(f"Chars remaining: {chars_remaining}")
    print()
    
    try:
        diff = await adherence_service.generate_corrective_diff(
            score=score_1,
            current_slots=prompt_slots,
            chars_remaining=chars_remaining,
        )
        
        print(f"✓ Generated {len(diff.ops)} correction operation(s)")
        print()
        
        if diff.ops:
            for i, op in enumerate(diff.ops, 1):
                print(f"Operation {i}:")
                print(f"  Type: {op.op}")
                print(f"  Slot: {op.slot}")
                print(f"  Reason: {op.reason}")
                print(f"  Char Delta: {op.char_delta:+d}")
                print(f"  Old: {op.old_text}")
                print(f"  New: {op.new_text}")
                print()
        else:
            print("⚠️  No operations generated (check corrector logic)")
            return 1
        
        # Apply diff
        corrected_slots = adherence_service.apply_diff(
            base_slots=prompt_slots,
            diff=diff,
            max_prompt_length=512,
        )
        
        corrected_prompt = corrected_slots.get("description", original_prompt)
        
        print("=" * 80)
        print("RESULT")
        print("=" * 80)
        print()
        print(f"Original:  {original_prompt}")
        print(f"Corrected: {corrected_prompt}")
        print()
        
        if corrected_prompt != original_prompt:
            print("✅ SUCCESS: Corrector generated actual changes!")
            print()
            print("Changes made:")
            if len(corrected_prompt) > len(original_prompt):
                print(f"  - Added {len(corrected_prompt) - len(original_prompt)} characters")
            elif len(corrected_prompt) < len(original_prompt):
                print(f"  - Removed {len(original_prompt) - len(corrected_prompt)} characters")
            print()
            
            # Show diff
            import difflib
            diff_lines = list(difflib.unified_diff(
                [original_prompt],
                [corrected_prompt],
                lineterm='',
                fromfile='original',
                tofile='corrected',
            ))
            if len(diff_lines) > 2:
                print("Unified diff:")
                for line in diff_lines[2:]:
                    print(f"  {line}")
            print()
        else:
            print("⚠️  Corrector made no changes")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"✗ Corrector failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
