#!/usr/bin/env python3
"""
Quick verification that seeds are generated correctly.
Uses simulated provider to avoid consuming credits.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.script_guard import require_live_spend_gate

require_live_spend_gate(
    __file__,
    what="exercise the submit path with the simulated provider (no spend) + job-row writes",
    exposure="no provider spend (simulated submit); writes job rows to the resolved DB",
    provider="runway",
)

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.render import render_service
from app.services import render as render_module


async def main():
    print("=" * 80)
    print("SEED GENERATION VERIFICATION TEST")
    print("=" * 80)
    
    # Initialize storage
    storage = get_storage("sqlite")
    render_module.set_storage(storage)
    print("✓ Storage configured")
    
    # Get a project
    projects = storage.get_all_projects()
    if not projects:
        print("❌ No projects found")
        return
    
    project_id = list(projects.keys())[0]
    print(f"✓ Using project: {project_id}")
    
    # Create a job with simulated provider
    print("\n[1] Creating job with simulated provider...")
    job = render_service.create_job(
        project_id=project_id,
        shot_id="seed_test_shot_001",
        provider="simulated",
        prompt="Test scene for seed generation"
    )
    
    seed_after_create = job.input_payload.parameters.get('seed') if job.input_payload.parameters else None
    print(f"  Seed after create_job: {seed_after_create}")
    
    # Submit the job
    print("\n[2] Submitting job...")
    submitted_job = await render_service.submit_job(job.id)
    
    seed_after_submit = submitted_job.input_payload.parameters.get('seed') if submitted_job.input_payload.parameters else None
    print(f"  Seed after submit_job: {seed_after_submit}")
    print(f"  Seed type: {type(seed_after_submit)}")
    
    # Verify seed was generated
    if seed_after_submit is None:
        print("\n❌ SEED GENERATION FAILED")
        print("  This is a critical issue - seeds must be generated for retry loop")
        return 1
    
    if not isinstance(seed_after_submit, int):
        print(f"\n❌ SEED IS WRONG TYPE: {type(seed_after_submit)}")
        return 1
    
    print(f"\n✅ SEED GENERATION VERIFIED")
    print(f"  Seed value: {seed_after_submit}")
    print(f"  Seed is valid integer: ✓")
    
    # Check that seed was persisted
    print("\n[3] Verifying seed persistence in storage...")
    stored_seed = storage.get_shot_seed(project_id, "seed_test_shot_001")
    
    if stored_seed:
        print(f"  Stored seed record: {stored_seed}")
        if stored_seed.get('seed') == seed_after_submit:
            print(f"  ✓ Seed matches job parameter")
        else:
            print(f"  ❌ Seed mismatch!")
    else:
        print(f"  ❌ No seed record in storage!")
        return 1
    
    print("\n" + "=" * 80)
    print("✅ ALL CHECKS PASSED - SEED GENERATION WORKING")
    print("=" * 80)
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
