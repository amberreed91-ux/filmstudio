#!/usr/bin/env python3
"""
Test script to verify the complete render prompt pipeline:
1. Script parsing stores scene descriptions
2. Scene retrieval returns full data
3. Render jobs use real scene descriptions as prompts
"""

import sys
import os

# Add the studio-backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'studio-backend'))

from app.services.script_parser import ScriptParser
from app.services.render import RenderService
from app.services.project_store import project_store
from app.models import ProviderConfig

# Test script with 3 scenes
TEST_SCRIPT = """SCENE 1: INT. COFFEE SHOP - DAY
A woman sits alone at a corner table reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.
Emotional tone: quiet, isolated, contemplative.

SCENE 2: EXT. STREET - NIGHT
She steps outside into heavy rain pulling her coat tight.
The street is deserted except for distant headlights.
Emotional tone: uneasy, exposed, transitional.

SCENE 3: INT. APARTMENT - NIGHT
She pushes open the door to a dark apartment.
A single envelope sits on the floor beneath the mail slot.
She stares at it without picking it up.
Emotional tone: dread, stillness, arriving at something."""

def test_script_parsing():
    """Test that script parser extracts and stores scene descriptions correctly"""
    print("\n" + "="*80)
    print("TEST 1: Script Parsing and Scene Storage")
    print("="*80)
    
    parser = ScriptParser()
    result = parser.extract_structured_scenes(TEST_SCRIPT)
    
    scenes = result.get("scenes", [])
    print(f"\n✓ Parsed {len(scenes)} scenes")
    
    if len(scenes) != 3:
        print(f"✗ FAIL: Expected 3 scenes, got {len(scenes)}")
        return False
    
    # Verify each scene has required fields
    for i, scene in enumerate(scenes, 1):
        scene_id = scene.get("scene_id", "")
        heading = scene.get("heading", "")
        text = scene.get("text", "")
        location = scene.get("location", "")
        time_of_day = scene.get("time_of_day", "")
        emotional_tone = scene.get("emotional_tone", "")
        
        print(f"\nScene {i} ({scene_id}):")
        print(f"  Heading: {heading[:50]}...")
        print(f"  Description length: {len(text)} characters")
        print(f"  Location: {location}")
        print(f"  Time of day: {time_of_day}")
        print(f"  Emotional tone: {emotional_tone}")
        
        if not text:
            print(f"  ✗ FAIL: Scene {i} has no description/text")
            return False
        
        if not location:
            print(f"  ⚠ WARNING: Scene {i} has no location")
        
        if not emotional_tone:
            print(f"  ⚠ WARNING: Scene {i} has no emotional tone")
    
    print("\n✓ All scenes have descriptions")
    return True


def test_scene_retrieval():
    """Test that scenes can be retrieved with full data"""
    print("\n" + "="*80)
    print("TEST 2: Scene Retrieval")
    print("="*80)
    
    # Create a test project
    project_id = "test_project_render_prompt"
    
    # Parse script
    parser = ScriptParser()
    summary = parser.build_script_breakdown_bundle(TEST_SCRIPT)
    
    # Store project using update_project (create if doesn't exist)
    project_store.update_project(
        project_id=project_id,
        updates={
            "title": "Test Render Prompt Pipeline",
            "execution_summary": summary
        }
    )
    
    # Retrieve scenes
    project = project_store.get_project(project_id)
    if not project:
        print("✗ FAIL: Could not retrieve project")
        return False
    
    scenes = project.get("execution_summary", {}).get("scenes", [])
    print(f"\n✓ Retrieved {len(scenes)} scenes from project")
    
    # Verify first scene has all data
    if scenes:
        scene = scenes[0]
        scene_id = scene.get("scene_id", "")
        description = scene.get("text", "") or scene.get("description", "")
        location = scene.get("location", "")
        
        print(f"\nFirst scene ({scene_id}):")
        print(f"  Description: {description[:100]}...")
        print(f"  Location: {location}")
        
        if not description:
            print("  ✗ FAIL: Scene has no description")
            return False
        
        print("  ✓ Scene has description")
    
    # Cleanup
    project_store.delete_project(project_id)
    
    return True


def test_render_prompt_generation():
    """Test that render jobs use real scene descriptions as prompts"""
    print("\n" + "="*80)
    print("TEST 3: Render Prompt Generation")
    print("="*80)
    
    # Create a test project
    project_id = "test_project_render_prompt_2"
    
    # Parse script
    parser = ScriptParser()
    summary = parser.build_script_breakdown_bundle(TEST_SCRIPT)
    
    # Store project using update_project
    project_store.update_project(
        project_id=project_id,
        updates={
            "title": "Test Render Prompt Pipeline 2",
            "execution_summary": summary
        }
    )
    
    # Create render service
    provider_config = ProviderConfig(
        provider_id="simulated",
        provider_name="Simulated Provider",
        enabled=True,
        is_simulated=True,
        requires=[]
    )
    
    render_service = RenderService(provider_configs={"simulated": provider_config})
    
    # Test 1: Generic prompt should be replaced
    print("\n--- Test 3a: Generic prompt replacement ---")
    job1 = render_service.create_job(
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="Generate scene with cinematic quality"  # Generic prompt
    )
    
    prompt1 = job1.input_payload.prompt
    print(f"Original prompt: 'Generate scene with cinematic quality'")
    print(f"Final prompt length: {len(prompt1)} characters")
    print(f"Final prompt preview: {prompt1[:150]}...")
    
    if "woman sits alone" not in prompt1.lower():
        print("✗ FAIL: Prompt does not contain scene description")
        project_store.delete_project(project_id)
        return False
    
    if len(prompt1) < 50:
        print("✗ FAIL: Prompt is too short")
        project_store.delete_project(project_id)
        return False
    
    print("✓ Generic prompt was replaced with real scene description")
    
    # Test 2: Empty prompt should be replaced
    print("\n--- Test 3b: Empty prompt replacement ---")
    job2 = render_service.create_job(
        project_id=project_id,
        shot_id="scene_002_shot_001",
        provider="simulated",
        prompt=""  # Empty prompt
    )
    
    prompt2 = job2.input_payload.prompt
    print(f"Original prompt: (empty)")
    print(f"Final prompt length: {len(prompt2)} characters")
    print(f"Final prompt preview: {prompt2[:150]}...")
    
    if "steps outside" not in prompt2.lower():
        print("✗ FAIL: Prompt does not contain scene 2 description")
        project_store.delete_project(project_id)
        return False
    
    print("✓ Empty prompt was replaced with real scene description")
    
    # Test 3: Real prompt should be kept
    print("\n--- Test 3c: Real prompt preservation ---")
    real_prompt = "A detailed cinematic shot showing a woman reading in a coffee shop with rain visible through the window, moody lighting, film noir style, 35mm film grain"
    job3 = render_service.create_job(
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt=real_prompt
    )
    
    prompt3 = job3.input_payload.prompt
    print(f"Original prompt length: {len(real_prompt)} characters")
    print(f"Final prompt length: {len(prompt3)} characters")
    
    if prompt3 != real_prompt:
        print("⚠ WARNING: Real prompt was modified (may have continuity context added)")
        print(f"Original: {real_prompt[:100]}...")
        print(f"Final: {prompt3[:100]}...")
    else:
        print("✓ Real prompt was preserved")
    
    # Cleanup
    project_store.delete_project(project_id)
    
    return True


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("RENDER PROMPT PIPELINE TEST SUITE")
    print("="*80)
    
    tests = [
        ("Script Parsing", test_script_parsing),
        ("Scene Retrieval", test_scene_retrieval),
        ("Render Prompt Generation", test_render_prompt_generation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
