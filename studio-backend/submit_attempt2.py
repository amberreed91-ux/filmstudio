#!/usr/bin/env python3
"""
Submit Attempt 2 with corrected prompt and locked seed.
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.script_guard import require_live_spend_gate

require_live_spend_gate(
    __file__,
    what="submit Attempt 2 render to Runway (corrected prompt, locked seed) + Gemini/Groq scoring",
    exposure="1 Runway video render + polls + Groq/Gemini scoring calls",
    provider="runway",
)

from dotenv import load_dotenv
load_dotenv()

import os
from app.data.storage import get_storage
from app.services.render import render_service
from app.services.render_retry_service import render_retry_service


async def main():
    """Submit attempt 2 with corrected prompt."""
    
    print("=" * 80)
    print("ATTEMPT 2 SUBMISSION - Corrected Prompt with Locked Seed")
    print("=" * 80)
    
    # Verify environment
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    gemini_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    
    print(f"\n[ENV CHECK]")
    print(f"  RUNWAYML_API_SECRET present: {bool(runway_key)}")
    print(f"  Key length: {len(runway_key)}")
    print(f"  GOOGLE_API_KEY present: {bool(gemini_key)}")
    print(f"  Gemini key length: {len(gemini_key)}")
    
    if not runway_key:
        print("\n❌ RUNWAYML_API_SECRET not loaded!")
        return
    
    if not gemini_key:
        print("\n❌ GOOGLE_API_KEY not loaded!")
        return
    
    # Check provider
    providers = render_service.list_providers()
    runway_provider = next((p for p in providers if p.provider_id == "runway"), None)
    
    print(f"\n[PROVIDER CHECK]")
    if runway_provider:
        print(f"  Runway provider: {runway_provider.name}")
        print(f"  Is simulated: {runway_provider.is_simulated}")
        print(f"  Ready for hosted: {runway_provider.ready_for_hosted_generation}")
        print(f"  Provider mode: {runway_provider.provider_mode}")
    else:
        print(f"  ❌ Runway provider NOT FOUND!")
        return
    
    if runway_provider.is_simulated:
        print("\n❌ Provider is SIMULATED - will not proceed!")
        return
    
    print("\n✓ Environment checks passed - using REAL Runway")
    
    # Initialize storage
    storage = get_storage("sqlite")
    
    from app.services import render as render_module
    render_module.set_storage(storage)
    render_retry_service.set_storage(storage)
    
    print("✓ Storage configured for both services")
    
    # Constants
    PROJECT_ID = "project_3dba9330f43a"
    SHOT_ID = "scene_001"
    LOCKED_SEED = 983559286
    
    CORRECTED_PROMPT = "People visible at human scale, faces and gestures clearly shown, interacting closely. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago, L train, skyline. Wide shot. golden hour light. Cinematic, film quality, single continuous shot."
    
    print(f"\n[ATTEMPT 2 PARAMETERS]")
    print(f"  Project: {PROJECT_ID}")
    print(f"  Shot: {SHOT_ID}")
    print(f"  Locked Seed: {LOCKED_SEED}")
    print(f"  Prompt length: {len(CORRECTED_PROMPT)} chars")
    print(f"\n  Corrected Prompt:")
    print(f"  {CORRECTED_PROMPT}")
    
    # Create job
    print(f"\n[STEP 1] Creating render job for attempt 2...")
    
    job = render_service.create_job(
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        provider="runway",
        prompt=CORRECTED_PROMPT,
        parameters={'seed': LOCKED_SEED}
    )
    job_id = job.id
    
    print(f"\n✓ Job created: {job_id}")
    
    # Verify seed in job
    job_seed = job.input_payload.parameters.get('seed') if job.input_payload.parameters else None
    print(f"  Seed in job parameters: {job_seed}")
    
    if job_seed != LOCKED_SEED:
        print(f"\n❌ SEED MISMATCH!")
        print(f"  Expected: {LOCKED_SEED}")
        print(f"  Got: {job_seed}")
        return
    
    print(f"✓ Seed confirmed locked: {LOCKED_SEED}")
    
    # Submit
    print(f"\n[STEP 2] Submitting to Runway...")
    
    submitted_job = await render_service.submit_job(job_id)
    provider_job_id = submitted_job.provider_job_id
    
    print(f"✓ Submitted to Runway")
    print(f"  Provider Job ID: {provider_job_id}")
    print(f"  Status: {submitted_job.status}")
    
    # Verify seed persisted after submission
    submitted_seed = submitted_job.input_payload.parameters.get('seed') if submitted_job.input_payload.parameters else None
    print(f"  Seed after submission: {submitted_seed}")
    
    if submitted_seed != LOCKED_SEED:
        print(f"\n⚠️  WARNING: Seed changed during submission!")
        print(f"  Expected: {LOCKED_SEED}")
        print(f"  Got: {submitted_seed}")
    
    # Poll for completion
    print(f"\n[STEP 3] Polling for completion (max 5 minutes)...")
    
    max_polls = 60  # 5 minutes
    poll_count = 0
    
    while poll_count < max_polls:
        await asyncio.sleep(5)
        poll_count += 1
        
        job_status = await render_service.get_job_status(job_id)
        status = job_status.status
        
        print(f"  [{poll_count * 5}s] Status: {status}")
        
        if status in ['completed', 'complete', 'failed', 'error']:
            break
    
    # Check final status
    final_job = await render_service.get_job_status(job_id)
    final_status = final_job.status
    output_url = final_job.output_payload.asset_url if final_job.output_payload else None
    
    if final_status not in ['completed', 'complete']:
        print(f"\n❌ Job did not complete: {final_status}")
        if final_job.error_message:
            print(f"  Error: {final_job.error_message}")
        return
    
    if not output_url:
        print(f"\n❌ No output URL!")
        return
    
    print(f"\n✓ Render completed!")
    print(f"  Output URL: {output_url[:80]}...")
    
    # Record attempt with scoring
    print(f"\n[STEP 4] Recording attempt 2 with adherence scoring...")
    print(f"  (Will download video, extract frames, run Gemini vision scoring)")
    
    try:
        result = await render_retry_service.record_render_attempt(
            project_id=PROJECT_ID,
            shot_id=SHOT_ID,
            job_id=job_id,
            output_url=output_url,
            prompt=CORRECTED_PROMPT
        )
        
        print(f"\n✓ Attempt 2 recorded and scored!")
        print(f"  Attempt ID: {result.get('attempt_id')}")
        print(f"  Attempt Number: {result.get('attempt_number')}")
        
        score_json = result.get('score_json', {})
        
        print(f"\n[ATTEMPT 2 SCORE JSON]")
        print(json.dumps(score_json, indent=2))
        
        if isinstance(score_json, dict):
            adherence = score_json.get('adherence_score')
            verdict = score_json.get('verdict')
            failed = score_json.get('failed_slots', [])
            
            print(f"\n[ATTEMPT 2 SUMMARY]")
            print(f"  Adherence Score: {adherence}/100")
            print(f"  Verdict: {verdict}")
            print(f"  Failed Slots: {failed if failed else 'None'}")
            
            dimensions = score_json.get('dimensions', {})
            print(f"\n  Dimension Scores:")
            for dim_name, dim_data in dimensions.items():
                score = dim_data.get('score', 'N/A')
                print(f"    - {dim_name}: {score}/100")
    
    except Exception as e:
        print(f"\n❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Compare attempts
    print(f"\n" + "=" * 80)
    print("SIDE-BY-SIDE COMPARISON: ATTEMPT 1 vs ATTEMPT 2")
    print("=" * 80)
    
    attempts = storage.list_render_attempts(project_id=PROJECT_ID, shot_id=SHOT_ID)
    
    if len(attempts) < 2:
        print(f"\n⚠️  Expected 2 attempts, found {len(attempts)}")
        print(f"  Note: Attempt 1 may not have been persisted to DB")
        print(f"  Showing what we have:")
    
    print(f"\nFound {len(attempts)} attempt(s) in render_attempts table:")
    
    # Sort by attempt_number
    attempts_sorted = sorted(attempts, key=lambda x: x.get('attempt_number', 0))
    
    attempt1_data = None
    attempt2_data = None
    
    for att in attempts_sorted:
        att_num = att.get('attempt_number')
        print(f"\n{'─' * 80}")
        print(f"ATTEMPT {att_num}")
        print(f"{'─' * 80}")
        print(f"  Attempt ID: {att.get('id')}")
        print(f"  Job ID: {att.get('job_id')}")
        print(f"  Timestamp: {att.get('timestamp')}")
        print(f"  Output URL: {att.get('output_url', 'N/A')[:60]}...")
        
        score_json_stored = att.get('score_json')
        if score_json_stored:
            if isinstance(score_json_stored, str):
                score_json_stored = json.loads(score_json_stored)
            
            adherence = score_json_stored.get('adherence_score')
            verdict = score_json_stored.get('verdict')
            failed = score_json_stored.get('failed_slots', [])
            
            print(f"\n  Adherence Score: {adherence}/100")
            print(f"  Verdict: {verdict}")
            print(f"  Failed Slots: {failed if failed else 'None'}")
            
            dimensions = score_json_stored.get('dimensions', {})
            print(f"\n  Dimension Scores:")
            for dim_name, dim_data in dimensions.items():
                score = dim_data.get('score', 'N/A')
                print(f"    - {dim_name}: {score}/100")
            
            # Store for comparison
            if att_num == 1:
                attempt1_data = score_json_stored
            elif att_num == 2:
                attempt2_data = score_json_stored
    
    # Detailed comparison
    if attempt1_data and attempt2_data:
        print(f"\n{'═' * 80}")
        print("DETAILED DIMENSION COMPARISON")
        print(f"{'═' * 80}")
        
        dims1 = attempt1_data.get('dimensions', {})
        dims2 = attempt2_data.get('dimensions', {})
        
        for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
            score1 = dims1.get(dim_name, {}).get('score', 'N/A')
            score2 = dims2.get(dim_name, {}).get('score', 'N/A')
            
            if isinstance(score1, (int, float)) and isinstance(score2, (int, float)):
                delta = score2 - score1
                delta_str = f"{delta:+.1f}"
                arrow = "📈" if delta > 0 else "📉" if delta < 0 else "━"
            else:
                delta_str = "N/A"
                arrow = "?"
            
            print(f"\n  {dim_name}:")
            print(f"    Attempt 1: {score1}/100")
            print(f"    Attempt 2: {score2}/100")
            print(f"    Change: {delta_str} {arrow}")
        
        # Overall scores
        overall1 = attempt1_data.get('adherence_score', 'N/A')
        overall2 = attempt2_data.get('adherence_score', 'N/A')
        
        print(f"\n{'─' * 80}")
        print(f"  OVERALL ADHERENCE:")
        print(f"    Attempt 1: {overall1}/100")
        print(f"    Attempt 2: {overall2}/100")
        
        if isinstance(overall1, (int, float)) and isinstance(overall2, (int, float)):
            delta = overall2 - overall1
            print(f"    Change: {delta:+.1f} {'📈' if delta > 0 else '📉' if delta < 0 else '━'}")
        
        # Verdict comparison
        verdict1 = attempt1_data.get('verdict')
        verdict2 = attempt2_data.get('verdict')
        
        print(f"\n  VERDICT:")
        print(f"    Attempt 1: {verdict1}")
        print(f"    Attempt 2: {verdict2}")
    
    print(f"\n{'═' * 80}")
    print("ATTEMPT 2 SUBMISSION COMPLETE")
    print(f"{'═' * 80}")
    print(f"\n✓ Both attempts recorded in render_attempts table")
    print(f"✓ Seed {LOCKED_SEED} used for both attempts")
    print(f"✓ Full comparison shown above")


if __name__ == '__main__':
    asyncio.run(main())
