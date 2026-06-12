#!/usr/bin/env python3
"""
Test script to verify script parser handles multiple formats correctly.
"""

import sys
import os

# Add the studio-backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'studio-backend'))

from app.services.script_parser import ScriptParser

# Test Format A: "SCENE X: INT. LOCATION - TIME"
format_a_script = """SCENE 1: INT. COFFEE SHOP - DAY
A woman sits alone at a corner table, reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.

Emotional tone: quiet, isolated, contemplative.

SCENE 2: EXT. STREET - NIGHT
She steps outside into heavy rain, pulling her coat tight.
The street is deserted except for distant headlights.

Emotional tone: uneasy, exposed, transitional.

SCENE 3: INT. APARTMENT - NIGHT
She pushes open the door to a dark apartment.
A single envelope sits on the floor beneath the mail slot.
She stares at it without picking it up.

Emotional tone: dread, stillness, arriving at something."""

# Test Format B: Standard "INT. LOCATION - TIME"
format_b_script = """INT. COFFEE SHOP - DAY
A woman sits alone at a corner table, reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.

Emotional tone: quiet, isolated, contemplative.

EXT. STREET - NIGHT
She steps outside into heavy rain, pulling her coat tight.
The street is deserted except for distant headlights.

Emotional tone: uneasy, exposed, transitional.

INT. APARTMENT - NIGHT
She pushes open the door to a dark apartment.
A single envelope sits on the floor beneath the mail slot.
She stares at it without picking it up.

Emotional tone: dread, stillness, arriving at something."""

# Test Format C: Numbered list "1. Title"
format_c_script = """1. Coffee Shop
A woman sits alone at a corner table, reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.

Emotional tone: quiet, isolated, contemplative.

2. Street at Night
She steps outside into heavy rain, pulling her coat tight.
The street is deserted except for distant headlights.

Emotional tone: uneasy, exposed, transitional.

3. Dark Apartment
She pushes open the door to a dark apartment.
A single envelope sits on the floor beneath the mail slot.
She stares at it without picking it up.

Emotional tone: dread, stillness, arriving at something."""


def test_format(name: str, script_text: str, expected_count: int):
    """Test a script format and report results."""
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"{'='*60}")
    
    parser = ScriptParser()
    result = parser.extract_structured_scenes(script_text)
    scenes = result.get("scenes", [])
    
    print(f"Expected scenes: {expected_count}")
    print(f"Actual scenes: {len(scenes)}")
    
    if len(scenes) == expected_count:
        print("✅ PASS: Correct scene count")
    else:
        print("❌ FAIL: Incorrect scene count")
        return False
    
    # Check each scene
    for i, scene in enumerate(scenes, 1):
        print(f"\nScene {i}:")
        print(f"  scene_id: {scene.get('scene_id')}")
        print(f"  heading: {scene.get('heading')}")
        print(f"  location: {scene.get('location')}")
        print(f"  time_of_day: {scene.get('time_of_day')}")
        print(f"  emotional_tone: {scene.get('emotional_tone', 'N/A')}")
        print(f"  text length: {len(scene.get('text', ''))}")
        
        # Verify heading doesn't contain "SCENE X:" prefix
        heading = scene.get('heading', '')
        if heading.upper().startswith('SCENE '):
            print(f"  ⚠️  WARNING: Heading still contains 'SCENE X:' prefix")
    
    return True


def main():
    """Run all tests."""
    print("Script Parser Format Tests")
    print("="*60)
    
    all_passed = True
    
    # Test Format A: SCENE X: INT. LOCATION - TIME
    if not test_format("Format A (SCENE X: INT. LOCATION - TIME)", format_a_script, 3):
        all_passed = False
    
    # Test Format B: Standard INT. LOCATION - TIME
    if not test_format("Format B (Standard INT. LOCATION - TIME)", format_b_script, 3):
        all_passed = False
    
    # Test Format C: Numbered list
    if not test_format("Format C (Numbered List)", format_c_script, 3):
        all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
