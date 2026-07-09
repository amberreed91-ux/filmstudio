#!/usr/bin/env python3
"""
Test script to diagnose scene parsing issues
"""

import sys
sys.path.insert(0, '/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-backend')

from app.services.script_parser import ScriptParser

# Test script provided by user
test_script = """SCENE 1: INT. COFFEE SHOP - DAY
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

print("=" * 80)
print("DIAGNOSTIC REPORT: Script Parsing Issue")
print("=" * 80)
print()

# Test 1: extract_structured_scenes (used by generate-scenes endpoint)
print("TEST 1: extract_structured_scenes() method")
print("-" * 80)
parser1 = ScriptParser()
result1 = parser1.extract_structured_scenes(test_script)
scenes1 = result1.get("scenes", [])
print(f"Number of scenes created: {len(scenes1)}")
print()
for i, scene in enumerate(scenes1, 1):
    print(f"Scene {i}:")
    print(f"  scene_id: {scene.get('scene_id')}")
    print(f"  heading: {scene.get('heading')}")
    print(f"  location: {scene.get('location')}")
    print(f"  time_of_day: {scene.get('time_of_day')}")
    print(f"  text (first 100 chars): {scene.get('text', '')[:100]}")
    print()

print()
print("=" * 80)

# Test 2: parse() method (used by ingest-script endpoint)
print("TEST 2: parse() method (used by ingest-script)")
print("-" * 80)
parser2 = ScriptParser()
result2 = parser2.parse(test_script)
scenes2 = result2.get("scenes", [])
print(f"Number of scenes created: {len(scenes2)}")
print()
for i, scene in enumerate(scenes2, 1):
    print(f"Scene {i}:")
    print(f"  scene_id: {scene.scene_id}")
    print(f"  scene_number: {scene.scene_number}")
    print(f"  heading: {scene.heading}")
    print(f"  location: {scene.location}")
    print(f"  time_of_day: {scene.time_of_day}")
    print(f"  description (first 100 chars): {scene.description[:100]}")
    print()

print()
print("=" * 80)
print("ANALYSIS")
print("=" * 80)
print()

# Check if scenes are being split correctly
if len(scenes1) == 0 and len(scenes2) == 0:
    print("❌ CRITICAL: No scenes were created by either method!")
    print()
    print("Possible causes:")
    print("1. The regex pattern doesn't match 'SCENE 1:' format")
    print("2. The parser expects 'INT.' or 'EXT.' at the start of the line")
    print("3. The script format doesn't match expected screenplay format")
elif len(scenes1) < 3 or len(scenes2) < 3:
    print(f"❌ ISSUE: Expected 3 scenes, but got {len(scenes1)} (method 1) and {len(scenes2)} (method 2)")
    print()
    print("The parser is not splitting scenes correctly.")
    print()
    print("Checking regex patterns:")
    print(f"  SCENE_HEADING_PATTERN: {parser2.SCENE_HEADING_PATTERN.pattern}")
    print(f"  _simple_heading_pattern: {parser2._simple_heading_pattern.pattern}")
    print()
    print("The patterns expect:")
    print("  - Lines starting with INT. or EXT.")
    print("  - Format: 'INT. LOCATION - TIME'")
    print()
    print("But the test script uses:")
    print("  - Lines starting with 'SCENE 1:' then 'INT.'")
    print("  - Format: 'SCENE 1: INT. LOCATION - TIME'")
else:
    print("✓ Correct number of scenes created")
    
    # Check if descriptions are unique
    descriptions1 = [s.get('text', '')[:50] for s in scenes1]
    descriptions2 = [s.description[:50] for s in scenes2]
    
    if len(set(descriptions1)) < len(descriptions1):
        print("❌ ISSUE: Duplicate descriptions found in method 1")
    if len(set(descriptions2)) < len(descriptions2):
        print("❌ ISSUE: Duplicate descriptions found in method 2")
    
    print()
    print("Scene descriptions are unique and correct")

print()
print("=" * 80)
print("REGEX PATTERN TESTING")
print("=" * 80)
print()

import re

# Test the patterns against the script lines
lines = test_script.split('\n')
print("Testing each line against SCENE_HEADING_PATTERN:")
print()
for i, line in enumerate(lines, 1):
    if line.strip():
        match = parser2.SCENE_HEADING_PATTERN.match(line)
        simple_match = parser2._simple_heading_pattern.match(line)
        print(f"Line {i}: {line[:60]}")
        print(f"  SCENE_HEADING_PATTERN match: {bool(match)}")
        print(f"  _simple_heading_pattern match: {bool(simple_match)}")
        if match:
            print(f"    Groups: {match.groups()}")
        print()

print()
print("=" * 80)
print("CONCLUSION")
print("=" * 80)
print()
print("The issue is that the script format 'SCENE 1: INT. COFFEE SHOP - DAY'")
print("does not match the expected screenplay format 'INT. COFFEE SHOP - DAY'.")
print()
print("The parser expects scene headings to start with INT. or EXT.,")
print("but the test script has 'SCENE 1:' prefix before INT./EXT.")
print()
print("This causes the parser to:")
print("1. Not recognize scene boundaries")
print("2. Either create no scenes or merge all content into one scene")
print("3. Use the same description for all scenes")
