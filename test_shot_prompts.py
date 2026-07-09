#!/usr/bin/env python3
"""
Test script to verify shot-aware prompt generation.

Tests the new shot_prompt_builder service with realistic scene data.
"""

import sys
sys.path.insert(0, '/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-backend')

from app.services.shot_prompt_builder import build_shot_aware_prompt, get_shot_type_label


# Sample scene data from project_3dba9330f43a Scene 2
SAMPLE_SCENE = {
    "scene_id": "scene_002",
    "heading": "INT. COFFEE SHOP - DAY",
    "location": "Coffee shop",
    "time_of_day": "day",
    "emotional_tone": "tense",
    "text": """INT. COFFEE SHOP - DAY

A small downtown café. Warm light through the windows. ALEX (30s, nervous energy) sits at a corner table, checking their phone repeatedly.

JORDAN (40s, composed) enters and walks directly to the table.

JORDAN
You wanted to talk.

ALEX
(defensive)
I didn't think you'd actually show up.

JORDAN
I'm here. What is this about?

ALEX
(hesitates)
I found the letters. The ones you said you destroyed.

Jordan's expression doesn't change, but there's a flicker in their eyes.

JORDAN
You shouldn't have gone through my things.

ALEX
You shouldn't have lied to me."""
}

SAMPLE_CHARACTERS = [
    {
        "name": "Alex",
        "age": "30s",
        "visual_prompt_summary": "nervous energy, casual clothing, constantly checking phone"
    },
    {
        "name": "Jordan",
        "age": "40s",
        "visual_prompt_summary": "composed demeanor, professional attire, controlled expressions"
    }
]


def test_shot_aware_prompts():
    """Test shot-aware prompt generation for multiple shots and takes."""
    
    print("=" * 80)
    print("SHOT-AWARE PROMPT GENERATION TEST")
    print("=" * 80)
    print(f"\nScene: {SAMPLE_SCENE['heading']}")
    print(f"Location: {SAMPLE_SCENE['location']}, {SAMPLE_SCENE['time_of_day']}")
    print(f"Tone: {SAMPLE_SCENE['emotional_tone']}")
    print("\n" + "=" * 80)
    
    # Test Shot 1, Take 1 (Wide establishing)
    print("\n🎬 SHOT 1, TAKE 1 (WIDE - Establishing)")
    print("-" * 80)
    prompt_1_1 = build_shot_aware_prompt(
        scene_data=SAMPLE_SCENE,
        shot_number=1,
        take_number=1,
        all_characters=SAMPLE_CHARACTERS,
        audio_brief=None,
        max_length=512
    )
    print(f"Label: {get_shot_type_label(1)}")
    print(f"Prompt:\n{prompt_1_1}")
    print(f"Length: {len(prompt_1_1)} chars")
    
    # Test Shot 2, Take 1 (Medium coverage)
    print("\n" + "=" * 80)
    print("\n🎬 SHOT 2, TAKE 1 (MEDIUM - Action/Dialogue)")
    print("-" * 80)
    prompt_2_1 = build_shot_aware_prompt(
        scene_data=SAMPLE_SCENE,
        shot_number=2,
        take_number=1,
        all_characters=SAMPLE_CHARACTERS,
        audio_brief=None,
        max_length=512
    )
    print(f"Label: {get_shot_type_label(2)}")
    print(f"Prompt:\n{prompt_2_1}")
    print(f"Length: {len(prompt_2_1)} chars")
    
    # Test Shot 2, Take 2 (Alternative angle)
    print("\n" + "=" * 80)
    print("\n🎬 SHOT 2, TAKE 2 (MEDIUM - Alternative Angle)")
    print("-" * 80)
    prompt_2_2 = build_shot_aware_prompt(
        scene_data=SAMPLE_SCENE,
        shot_number=2,
        take_number=2,
        all_characters=SAMPLE_CHARACTERS,
        audio_brief=None,
        max_length=512
    )
    print(f"Label: {get_shot_type_label(2)}")
    print(f"Prompt:\n{prompt_2_2}")
    print(f"Length: {len(prompt_2_2)} chars")
    
    # Test Shot 3, Take 1 (Close-up)
    print("\n" + "=" * 80)
    print("\n🎬 SHOT 3, TAKE 1 (CLOSE - Emotional beats)")
    print("-" * 80)
    prompt_3_1 = build_shot_aware_prompt(
        scene_data=SAMPLE_SCENE,
        shot_number=3,
        take_number=1,
        all_characters=SAMPLE_CHARACTERS,
        audio_brief=None,
        max_length=512
    )
    print(f"Label: {get_shot_type_label(3)}")
    print(f"Prompt:\n{prompt_3_1}")
    print(f"Length: {len(prompt_3_1)} chars")
    
    # Verify prompts are different
    print("\n" + "=" * 80)
    print("\n✅ VERIFICATION")
    print("-" * 80)
    
    prompts = [prompt_1_1, prompt_2_1, prompt_2_2, prompt_3_1]
    unique_prompts = len(set(prompts))
    
    print(f"Total prompts generated: {len(prompts)}")
    print(f"Unique prompts: {unique_prompts}")
    
    if unique_prompts == len(prompts):
        print("✅ All prompts are unique and shot-specific")
    else:
        print("❌ Some prompts are identical (should be different)")
    
    # Check that Shot 1 contains establishing language
    if "establishing" in prompt_1_1.lower() or "wide" in prompt_1_1.lower():
        print("✅ Shot 1 contains establishing shot language")
    else:
        print("⚠️  Shot 1 may not contain establishing shot language")
    
    # Check that Take 2 contains alternative angle instruction
    if "alternative angle" in prompt_2_2.lower() or "90 degrees" in prompt_2_2.lower():
        print("✅ Take 2 contains alternative angle instruction")
    else:
        print("❌ Take 2 missing alternative angle instruction")
    
    # Check character injection
    if "Alex" in prompt_1_1 or "Jordan" in prompt_1_1:
        print("✅ Characters are injected into prompts")
    else:
        print("⚠️  Characters may not be appearing in prompts")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_shot_aware_prompts()
