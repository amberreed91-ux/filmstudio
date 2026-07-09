#!/usr/bin/env python3
"""
Test to verify the final prompt format sent to Runway.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.services.render import render_service
from app.data.storage import get_storage

def main():
    storage = get_storage("sqlite")
    
    # Get a project
    project_ids = storage.list_project_ids()
    if not project_ids:
        print("✗ No projects found - create a project first")
        return 1
    
    project_id = project_ids[0]
    print(f"Testing with project: {project_id}")
    print()
    
    # Create a job with empty prompt to trigger generic (scene-based) path
    print("Creating test render job...")
    print("  Shot ID: scene_001_shot_001")
    print("  Prompt: <empty> (will use scene description)")
    print("  Provider: simulated")
    print()
    
    try:
        job = render_service.create_job(
            project_id=project_id,
            shot_id="scene_001_shot_001",
            provider="simulated",
            prompt="",  # Empty to trigger generic path with build_slotted_prompt()
            parameters={"seed": 42}
        )
        
        final_prompt = job.input_payload.prompt
        
        print("=" * 80)
        print("FINAL PROMPT SENT TO RUNWAY")
        print("=" * 80)
        print(final_prompt)
        print("=" * 80)
        print()
        print(f"Prompt length: {len(final_prompt)} chars")
        print(f"Job ID: {job.id}")
        print()
        
        # Check if it looks like a slotted prompt (has slot markers or structured format)
        has_camera = "Camera:" in final_prompt or "camera" in final_prompt.lower()
        has_lighting = "Lighting:" in final_prompt or "light" in final_prompt.lower()
        has_character = "Character" in final_prompt or "musician" in final_prompt.lower()
        
        print("Prompt analysis:")
        print(f"  Contains camera info: {has_camera}")
        print(f"  Contains lighting info: {has_lighting}")
        print(f"  Contains character info: {has_character}")
        print(f"  Length within budget (≤512): {len(final_prompt) <= 512}")
        print()
        
        if len(final_prompt) > 512:
            print("⚠️  WARNING: Prompt exceeds 512 character budget!")
        else:
            print("✓ Prompt within character budget")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error creating job: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
