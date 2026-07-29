#!/usr/bin/env python3
"""
Test apply_diff deduplication logic - ensures original text appears exactly once.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.adherence_service import adherence_service, CorrectiveDiff, CorrectionOp


def test_prepend_emphasis_no_duplication():
    """Test that prepend_emphasis doesn't duplicate original text when LLM includes it"""
    
    original_text = "A displaced musician uncovers a citywide memory glitch one song at a time"
    
    # LLM generated new_text that includes the original (with lowercase 'a')
    new_text_with_original = "Continuously focused on playing the guitar, a displaced musician uncovers a citywide memory glitch one song at a time"
    
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="description",
                op="prepend_emphasis",
                old_text=original_text,
                new_text=new_text_with_original,
                reason="Test",
                char_delta=50,
            )
        ],
        chars_remaining=400,
    )
    
    base_slots = {"description": original_text}
    
    result = adherence_service.apply_diff(base_slots, diff, max_prompt_length=512)
    
    result_text = result["description"]
    
    print("Test: prepend_emphasis with LLM including original text")
    print(f"  Original: {original_text}")
    print(f"  New text: {new_text_with_original}")
    print(f"  Result:   {result_text}")
    print()
    
    # Count occurrences of the core phrase
    core_phrase = "displaced musician uncovers a citywide memory glitch"
    occurrences = result_text.lower().count(core_phrase.lower())
    
    print(f"  Occurrences of '{core_phrase}': {occurrences}")
    
    assert occurrences == 1, f"Expected 1 occurrence, got {occurrences} - duplication bug!"
    assert result_text == new_text_with_original, "Result should match new_text exactly (no append)"
    
    print("  ✓ PASS: No duplication")
    print()


def test_prepend_emphasis_does_append_when_different():
    """Test that prepend_emphasis DOES append when new_text doesn't include original"""
    
    original_text = "A displaced musician walks through the city"
    new_text_without_original = "Continuously focused on playing the guitar"
    
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="description",
                op="prepend_emphasis",
                old_text=original_text,
                new_text=new_text_without_original,
                reason="Test",
                char_delta=20,
            )
        ],
        chars_remaining=400,
    )
    
    base_slots = {"description": original_text}
    
    result = adherence_service.apply_diff(base_slots, diff, max_prompt_length=512)
    
    result_text = result["description"]
    
    print("Test: prepend_emphasis when new_text is genuinely different")
    print(f"  Original: {original_text}")
    print(f"  New text: {new_text_without_original}")
    print(f"  Result:   {result_text}")
    print()
    
    expected = f"{new_text_without_original}, {original_text}"
    assert result_text == expected, f"Expected '{expected}', got '{result_text}'"
    
    print("  ✓ PASS: Correctly appended")
    print()


def test_strengthen_no_duplication():
    """Test that strengthen doesn't duplicate when LLM includes original"""
    
    original_text = "Man walking through street"
    new_text_with_original = "Weathered and determined, man walking through street"
    
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text=original_text,
                new_text=new_text_with_original,
                reason="Test",
                char_delta=20,
            )
        ],
        chars_remaining=400,
    )
    
    base_slots = {"character_state": original_text}
    
    result = adherence_service.apply_diff(base_slots, diff, max_prompt_length=512)
    
    result_text = result["character_state"]
    
    print("Test: strengthen with LLM including original text")
    print(f"  Original: {original_text}")
    print(f"  New text: {new_text_with_original}")
    print(f"  Result:   {result_text}")
    print()
    
    core_phrase = "walking through"
    occurrences = result_text.lower().count(core_phrase.lower())
    
    print(f"  Occurrences of '{core_phrase}': {occurrences}")
    
    assert occurrences == 1, f"Expected 1 occurrence, got {occurrences} - duplication bug!"
    assert result_text == new_text_with_original, "Result should match new_text exactly (no append)"
    
    print("  ✓ PASS: No duplication")
    print()


def test_case_insensitive_dedup():
    """Test that deduplication works regardless of capitalization differences"""
    
    original_text = "A Musician Plays Guitar"  # Mixed case
    new_text_lowercase = "continuously focused, a musician plays guitar"  # Lowercase version
    
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="description",
                op="prepend_emphasis",
                old_text=original_text,
                new_text=new_text_lowercase,
                reason="Test",
                char_delta=20,
            )
        ],
        chars_remaining=400,
    )
    
    base_slots = {"description": original_text}
    
    result = adherence_service.apply_diff(base_slots, diff, max_prompt_length=512)
    
    result_text = result["description"]
    
    print("Test: case-insensitive deduplication")
    print(f"  Original: {original_text}")
    print(f"  New text: {new_text_lowercase}")
    print(f"  Result:   {result_text}")
    print()
    
    core_phrase = "musician plays guitar"
    occurrences = result_text.lower().count(core_phrase.lower())
    
    print(f"  Occurrences of '{core_phrase}': {occurrences}")
    
    assert occurrences == 1, f"Expected 1 occurrence, got {occurrences} - case-sensitive bug!"
    
    print("  ✓ PASS: Case-insensitive dedup works")
    print()


if __name__ == "__main__":
    print("=" * 80)
    print("APPLY_DIFF DEDUPLICATION TESTS")
    print("=" * 80)
    print()
    
    try:
        test_prepend_emphasis_no_duplication()
        test_prepend_emphasis_does_append_when_different()
        test_strengthen_no_duplication()
        test_case_insensitive_dedup()
        
        print("=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        sys.exit(0)
        
    except AssertionError as e:
        print()
        print("=" * 80)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 80)
        sys.exit(1)
