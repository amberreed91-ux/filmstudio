#!/usr/bin/env python3
"""
Full end-to-end retry loop test through production creation path.
Tests Loop 4's slot system in real Runway renders with actual adherence scoring.
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.render import render_service
from app.services.render_retry_service import render_retry_service


async def main():
    """Run full end-to-end test with real Runway renders."""
    
    print("=" * 80)
    print("FULL E2E RETRY LOOP TEST - Production Path")
    print("=" * 80)
    
    # Verify environment variables are loaded
    import os
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip() or os.getenv("RUNWAY_API_KEY", "").strip()
    test_mode = os.getenv("RENDER_PROVIDER_TEST_MODE", "").strip().lower()
    
    print(f"\n[ENV CHECK]")
    print(f"  RUNWAYML_API_SECRET present: {bool(runway_key)}")
    print(f"  Key length: {len(runway_key)}")
    print(f"  Key first 10 chars: {runway_key[:10] if runway_key else 'N/A'}")
    print(f"  RENDER_PROVIDER_TEST_MODE: {test_mode or 'not set'}")
    
    # Check provider status
    providers = render_service.list_providers()
    runway_provider = next((p for p in providers if p.provider_id == "runway"), None)
    
    print(f"\n[PROVIDER CHECK]")
    if runway_provider:
        print(f"  Runway provider found: {runway_provider.name}")
        print(f"  Enabled: {runway_provider.enabled}")
        print(f"  Is simulated: {runway_provider.is_simulated}")
        print(f"  Is mock: {runway_provider.is_mock}")
        print(f"  API key configured: {runway_provider.api_key_configured}")
        print(f"  Ready for hosted generation: {runway_provider.ready_for_hosted_generation}")
        print(f"  Provider mode: {runway_provider.provider_mode}")
        print(f"  Display label: {runway_provider.display_label}")
    else:
        print(f"  ❌ Runway provider NOT FOUND in provider list!")
        print(f"  Available providers: {[p.provider_id for p in providers]}")
    
    if not runway_key:
        print("\n❌ RUNWAYML_API_SECRET not loaded! This test cannot proceed.")
        print("   The .env file has the key but it's not in the process environment.")
        return
    
    if test_mode == "mock_success":
        print("\n❌ RENDER_PROVIDER_TEST_MODE is set to 'mock_success'!")
        print("   This forces simulated mode. Unset this variable to use real Runway.")
        return
    
    if not runway_provider or not runway_provider.ready_for_hosted_generation:
        print("\n❌ Runway provider is not ready for hosted generation!")
        print("   Check provider configuration above.")
        return
    
    print("\n✓ Environment and provider checks passed - ready for real Runway submission")
    
    # Initialize storage
    storage = get_storage("sqlite")
    
    # Initialize storage for both services
    from app.services import render as render_module
    render_module.set_storage(storage)
    print("✓ render service storage configured")
    
    render_retry_service.set_storage(storage)
    print("✓ render_retry_service storage configured")
    
    try:
        # Step 1: List available projects and scenes
        print("\n[STEP 1] Listing available projects...")
        projects = storage.get_all_projects()
        
        if not projects:
            print("❌ No projects found. Please create a project first.")
            return
        
        print(f"\nFound {len(projects)} project(s):")
        for pid, p in projects.items():
            print(f"  • {pid}: {p.title} ({getattr(p, 'status', 'unknown')})")
        
        # Pick the first project
        project_id = list(projects.keys())[0]
        project = projects[project_id]
        print(f"\n✓ Selected project: {project.title} (ID: {project_id})")
        
        # Get scenes from execution_summary
        exec_summary = project.execution_summary if hasattr(project, 'execution_summary') else {}
        if isinstance(exec_summary, str):
            exec_summary = json.loads(exec_summary)
        
        scenes = exec_summary.get('scenes', []) if isinstance(exec_summary, dict) else []
        
        if not scenes:
            print(f"❌ No scenes found in project {project_id}")
            return
        
        print(f"\n  Found {len(scenes)} scene(s):")
        for scene in scenes[:5]:  # Show first 5
            scene_id = scene.get('scene_id', '?')
            scene_num = scene.get('scene_number', '?')
            title = scene.get('title') or scene.get('heading', 'Untitled')
            print(f"    - Scene {scene_num} ({scene_id}): {title}")
        
        # Pick the first scene
        scene = scenes[0]
        scene_id = scene.get('scene_id', f'scene_001')
        scene_title = scene.get('title') or scene.get('heading', 'Untitled')
        print(f"\n✓ Selected scene: {scene_title} (ID: {scene_id})")
        
        # Step 2: Create render job
        print(f"\n[STEP 2] Creating render job for scene {scene_id}...")
        print("  (This will use build_slotted_prompt() for real)")
        
        # Use scene_id as shot_id for simplicity
        shot_id = scene_id
        
        job = render_service.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider="runway",  # Use runway for real test
            prompt=""  # Empty to trigger slotted prompt builder
        )
        job_id = job.id
        
        print(f"\n✓ Created job {job_id}")
        print(f"  Prompt (first 100 chars): {job.input_payload.prompt[:100]}...")
        print(f"  Prompt length: {len(job.input_payload.prompt)}")
        seed_after_create = job.input_payload.parameters.get('seed') if job.input_payload.parameters else None
        print(f"  Seed (after create_job): {seed_after_create}")
        print(f"  NOTE: Seed is generated during submit_job(), not create_job()")
        
        # Confirm before submitting
        print("\n" + "=" * 80)
        print("⚠️  ABOUT TO SUBMIT TO RUNWAY (WILL CONSUME CREDITS)")
        print("=" * 80)
        response = input("\nProceed with Runway submission? (yes/no): ").strip().lower()
        
        if response != 'yes':
            print("\n❌ Aborted by user")
            return
        
        # Step 3: Submit to Runway and poll
        print(f"\n[STEP 3] Submitting job {job_id} to Runway...")
        
        submitted_job = await render_service.submit_job(job_id)
        provider_id = submitted_job.provider_job_id
        
        # Check seed after submission
        seed_after_submit = submitted_job.input_payload.parameters.get('seed') if submitted_job.input_payload.parameters else None
        
        print(f"✓ Submitted to Runway")
        print(f"  Provider ID: {provider_id}")
        print(f"  Status: {submitted_job.status}")
        print(f"  Seed (after submit_job): {seed_after_submit}")
        
        if seed_after_submit is None:
            print(f"\n❌ SEED GENERATION FAILED!")
            print(f"  Expected: integer seed value")
            print(f"  Got: None")
            print(f"  This is a blocker - retry loop requires locked seeds")
            return
        
        print(f"\n✓ Seed generated successfully: {seed_after_submit}")
        
        # Poll until complete
        print("\n  Polling for completion (max 5 minutes)...")
        max_polls = 60  # 5 minutes at 5-second intervals
        poll_count = 0
        
        while poll_count < max_polls:
            await asyncio.sleep(5)
            poll_count += 1
            
            job_status = await render_service.get_job_status(job_id)
            status = job_status.status
            
            print(f"    [{poll_count * 5}s] Status: {status}")
            
            if status in ['completed', 'complete', 'failed', 'error']:
                break
        
        # Check final status
        final_job = await render_service.get_job_status(job_id)
        final_status = final_job.status
        output_url = final_job.output_payload.asset_url if final_job.output_payload else None
        
        if final_status not in ['completed', 'complete']:
            print(f"\n❌ Job did not complete successfully: {final_status}")
            if final_job.error_message:
                print(f"  Error: {final_job.error_message}")
            return
        
        if not output_url:
            print("\n❌ Job completed but no output_url")
            return
        
        print(f"\n✓ Render completed!")
        print(f"  Output URL: {output_url[:60]}...")
        
        # Step 4: Record attempt 1 with adherence scoring
        print(f"\n[STEP 4] Recording attempt 1 with adherence scoring...")
        print("  (This will download video, extract frames, and run scoring)")
        
        result = await render_retry_service.record_render_attempt(
            project_id=project_id,
            shot_id=shot_id,
            job_id=job_id,
            output_url=output_url,
            prompt=job.input_payload.prompt
        )
        
        print(f"\n✓ Scoring complete:")
        print(f"  Attempt ID: {result.get('attempt_id')}")
        print(f"  Attempt Number: {result.get('attempt_number')}")
        
        score_json = result.get('score_json', {})
        print(f"\n  Score JSON:")
        print(json.dumps(score_json, indent=2))
        
        # Extract verdict
        verdict = None
        if isinstance(score_json, dict):
            verdict = score_json.get('verdict')
            print(f"\n  Verdict: {verdict}")
        
        # Step 5: Evaluate retry decision
        print(f"\n[STEP 5] Evaluating retry decision...")
        
        retry_result = await render_retry_service.evaluate_and_retry(
            project_id=project_id,
            shot_id=shot_id
        )
        
        should_retry = retry_result.get('should_retry', False)
        print(f"\n  Should Retry: {should_retry}")
        print(f"  Reason: {retry_result.get('reason', 'N/A')}")
        
        if should_retry and verdict == 'correctable':
            print(f"\n  Verdict is 'correctable' - manual attempt 2 flow...")
            
            # Confirm attempt 2
            print("\n" + "=" * 80)
            print("⚠️  ABOUT TO SUBMIT ATTEMPT 2 TO RUNWAY (MORE CREDITS)")
            print("=" * 80)
            print(f"\n  Will:")
            print(f"    1. Extract corrective guidance from dimensions")
            print(f"    2. Generate improved prompt")
            print(f"    3. Submit new render with LOCKED SEED {seed}")
            print(f"    4. Poll and score attempt 2")
            
            response2 = input("\nProceed with attempt 2? (yes/no): ").strip().lower()
            
            if response2 != 'yes':
                print("\n⚠️  Stopped after attempt 1")
                print("\nAttempt 1 details saved - check render_attempts table")
                return
            
            # Build corrected prompt
            print("\n  Generating corrected prompt from score dimensions...")
            dimensions = score_json.get('dimensions', {})
            
            corrective_notes = []
            for dim_name, dim_data in dimensions.items():
                if dim_data.get('status') == 'needs_correction':
                    guidance = dim_data.get('corrective_guidance', '')
                    if guidance:
                        corrective_notes.append(f"{dim_name}: {guidance}")
            
            # Build corrected prompt (simplified version)
            corrected_prompt = job.input_payload.prompt
            if corrective_notes:
                corrections = ". ".join(corrective_notes)
                corrected_prompt = f"{job.input_payload.prompt} [Corrections: {corrections}]"[:512]  # Cap at 512
            
            print(f"\n  Corrected prompt (first 200 chars):")
            print(f"    {corrected_prompt[:200]}...")
            
            # Create attempt 2 job with same seed
            job2 = render_service.create_job(
                project_id=project_id,
                shot_id=shot_id,
                provider="runway",
                prompt=corrected_prompt,
                parameters={'seed': seed_after_submit}  # LOCK THE SEED
            )
            job2_id = job2.id
            
            print(f"\n✓ Created job {job2_id} (attempt 2) with locked seed {seed_after_submit}")
            
            # Submit attempt 2
            submitted_job2 = await render_service.submit_job(job2_id)
            print(f"✓ Submitted attempt 2 to Runway")
            
            # Poll attempt 2
            print("\n  Polling attempt 2 for completion...")
            poll_count = 0
            
            while poll_count < max_polls:
                await asyncio.sleep(5)
                poll_count += 1
                
                job2_status = await render_service.get_job_status(job2_id)
                status = job2_status.status
                
                print(f"    [{poll_count * 5}s] Status: {status}")
                
                if status in ['completed', 'complete', 'failed', 'error']:
                    break
            
            # Check attempt 2 final status
            final_job2 = await render_service.get_job_status(job2_id)
            final_status2 = final_job2.status
            output_url2 = final_job2.output_payload.asset_url if final_job2.output_payload else None
            
            if final_status2 not in ['completed', 'complete']:
                print(f"\n❌ Attempt 2 did not complete: {final_status2}")
                return
            
            print(f"\n✓ Attempt 2 completed!")
            print(f"  Output URL: {output_url2[:60]}...")
            
            # Score attempt 2
            print(f"\n[STEP 6] Recording attempt 2 with adherence scoring...")
            
            result2 = await render_retry_service.record_render_attempt(
                project_id=project_id,
                shot_id=shot_id,
                job_id=job2_id,
                output_url=output_url2,
                prompt=corrected_prompt
            )
            
            print(f"\n✓ Scoring complete:")
            print(f"  Attempt ID: {result2.get('attempt_id')}")
            print(f"  Attempt Number: {result2.get('attempt_number')}")
            
            score_json2 = result2.get('score_json', {})
            print(f"\n  Score JSON:")
            print(json.dumps(score_json2, indent=2))
            
            # Compare attempts
            print("\n" + "=" * 80)
            print("COMPARISON: ATTEMPT 1 vs ATTEMPT 2")
            print("=" * 80)
            
            # Fetch render_attempts rows
            attempts = storage.list_render_attempts(project_id=project_id, shot_id=shot_id)
            
            print(f"\nFound {len(attempts)} attempt(s) for shot {shot_id}:")
            for att in attempts:
                print(f"\n  Attempt {att.get('attempt_number')}:")
                print(f"    Attempt ID: {att.get('id')}")
                print(f"    Job ID: {att.get('job_id')}")
                print(f"    Output URL: {att.get('output_url', 'N/A')[:60]}...")
                
                # Show which dimensions changed
                att_score = att.get('score_json')
                if att_score and isinstance(att_score, dict):
                    att_verdict = att_score.get('verdict')
                    att_dims = att_score.get('dimensions', {})
                    print(f"    Verdict: {att_verdict}")
                    print(f"    Dimensions:")
                    for dim, data in att_dims.items():
                        status = data.get('status', 'unknown')
                        print(f"      - {dim}: {status}")
            
            print("\n✓ Full retry loop test complete!")
        
        else:
            print(f"\n✓ Verdict was '{verdict}' - no correction needed")
            print("  (Run test again on a different shot to see correction flow)")
        
        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
    
    except Exception as exc:
        print(f"\n❌ Test failed with exception:")
        import traceback
        traceback.print_exc()
        raise


if __name__ == '__main__':
    from app.script_guard import require_live_spend_gate

    require_live_spend_gate(
        __file__,
        what="full end-to-end retry loop with real Runway renders + adherence scoring",
        exposure="multiple Runway video renders + polls + Groq/Gemini scoring calls",
        provider="runway",
    )
    asyncio.run(main())
