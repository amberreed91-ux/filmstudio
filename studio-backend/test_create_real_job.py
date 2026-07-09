#!/usr/bin/env python3
"""
Create a real render job RIGHT NOW to see which code path it takes.
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
        print("✗ No projects found")
        return 1
    
    project_id = project_ids[0]
    
    print("=" * 80)
    print("CREATING REAL RENDER JOB RIGHT NOW")
    print("=" * 80)
    print()
    print(f"Project: {project_id}")
    print(f"Shot: scene_001_shot_001")
    print(f"Prompt input: <EMPTY> (to trigger generic/scene-based path)")
    print(f"Provider: simulated")
    print()
    
    # Create job with EMPTY prompt to trigger generic path
    job = render_service.create_job(
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="",  # EMPTY - should trigger generic path with build_slotted_prompt()
        parameters={"seed": 999}
    )
    
    print("=" * 80)
    print("JOB CREATED")
    print("=" * 80)
    print()
    print(f"Job ID: {job.id}")
    print(f"Shot ID: {job.shot_id}")
    print(f"Provider: {job.provider}")
    print()
    print("=" * 80)
    print("FINAL PROMPT IN JOB")
    print("=" * 80)
    print(job.input_payload.prompt)
    print("=" * 80)
    print()
    print(f"Length: {len(job.input_payload.prompt)} chars")
    print()
    
    # Analyze structure
    prompt = job.input_payload.prompt
    parts = prompt.split('. ')
    
    print("STRUCTURE ANALYSIS:")
    print(f"  Number of period-separated parts: {len(parts)}")
    print()
    
    if len(parts) >= 3:
        print("Parts breakdown:")
        for i, part in enumerate(parts[:6], 1):
            print(f"  {i}. {part[:70]}{'...' if len(part) > 70 else ''}")
        print()
    
    has_cinematic = 'Cinematic' in prompt or 'film quality' in prompt
    has_camera = any(term in prompt.lower() for term in ['wide', 'camera', 'establishing', 'close', 'medium', 'shot'])
    has_lighting = any(term in prompt.lower() for term in ['light', 'golden hour', 'night', 'dawn', 'dusk'])
    
    print(f"  Has cinematic suffix: {has_cinematic}")
    print(f"  Has camera vocabulary: {has_camera}")
    print(f"  Has lighting vocabulary: {has_lighting}")
    print()
    
    if len(parts) >= 3 and has_camera and has_cinematic:
        print("✅ VERDICT: SLOTTED (build_slotted_prompt)")
        print("   This job used the slot-based prompt assembly")
    elif len(prompt) < 100 and len(parts) < 3:
        print("❌ VERDICT: MONOLITHIC")
        print("   This job did NOT use slot-based assembly")
    else:
        print("? VERDICT: UNCLEAR")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
