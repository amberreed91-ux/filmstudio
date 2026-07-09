#!/usr/bin/env python3
"""
Re-run Attempt 2 with identical prompt and seed to test consistency.
"""
import asyncio
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import os
from app.data.storage import get_storage
from app.services.render import render_service
from app.services.adherence_service import AdherenceService


async def extract_frames_ffmpeg(video_path: str, output_dir: str, suffix: str) -> list[str]:
    """Extract 3 frames at 10%, 50%, 90% using ffmpeg."""
    
    # Get video duration
    duration_cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    
    result = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration = float(result.stdout.strip())
    
    print(f"  Video duration: {duration:.2f} seconds")
    
    # Calculate timestamps for 10%, 50%, 90%
    timestamps = [
        duration * 0.1,
        duration * 0.5,
        duration * 0.9,
    ]
    
    frame_paths = []
    
    for idx, ts in enumerate(timestamps, 1):
        frame_path = f"{output_dir}/frame_attempt2_{suffix}_{idx}.jpg"
        
        extract_cmd = [
            'ffmpeg',
            '-ss', str(ts),
            '-i', video_path,
            '-frames:v', '1',
            '-y',
            frame_path
        ]
        
        subprocess.run(extract_cmd, capture_output=True, check=True)
        frame_paths.append(frame_path)
        print(f"  Extracted frame {idx} at {ts:.2f}s -> {frame_path}")
    
    return frame_paths


async def main():
    """Re-run attempt 2 with same prompt and seed."""
    
    print("=" * 80)
    print("ATTEMPT 2 CONSISTENCY TEST - Same Prompt, Same Seed, Fresh Render")
    print("=" * 80)
    
    # Verify environment
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    gemini_key = os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    
    print(f"\n[ENV CHECK]")
    print(f"  RUNWAYML_API_SECRET present: {bool(runway_key)}")
    print(f"  GOOGLE_API_KEY present: {bool(gemini_key)}")
    
    if not runway_key or not gemini_key:
        print("\n❌ Missing API keys!")
        return
    
    # Check provider
    providers = render_service.list_providers()
    runway_provider = next((p for p in providers if p.provider_id == "runway"), None)
    
    print(f"\n[PROVIDER CHECK]")
    if runway_provider:
        print(f"  Provider: {runway_provider.name}")
        print(f"  Is simulated: {runway_provider.is_simulated}")
        print(f"  Ready: {runway_provider.ready_for_hosted_generation}")
    
    if not runway_provider or runway_provider.is_simulated:
        print("\n❌ Real Runway not available!")
        return
    
    print("\n✓ Using REAL Runway")
    
    # Initialize storage
    storage = get_storage("sqlite")
    
    from app.services import render as render_module
    render_module.set_storage(storage)
    
    # Constants - EXACT SAME as previous Attempt 2
    PROJECT_ID = "project_3dba9330f43a"
    SHOT_ID = "scene_001"
    LOCKED_SEED = 983559286
    
    CORRECTED_PROMPT = "People visible at human scale, faces and gestures clearly shown, interacting closely. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago, L train, skyline. Wide shot. golden hour light. Cinematic, film quality, single continuous shot."
    
    print(f"\n[RETRY PARAMETERS]")
    print(f"  Project: {PROJECT_ID}")
    print(f"  Shot: {SHOT_ID}")
    print(f"  Locked Seed: {LOCKED_SEED} (SAME as previous Attempt 2)")
    print(f"  Prompt: {CORRECTED_PROMPT}")
    print(f"  Prompt length: {len(CORRECTED_PROMPT)} chars")
    
    print("\n" + "=" * 80)
    print("⚠️  ABOUT TO SUBMIT ATTEMPT 2 RETRY TO RUNWAY (WILL CONSUME CREDITS)")
    print("=" * 80)
    print("\nThis will test if the nighttime rooftop scene repeats with same seed+prompt.")
    
    # Create job
    print(f"\n[STEP 1] Creating render job...")
    
    job = render_service.create_job(
        project_id=PROJECT_ID,
        shot_id=SHOT_ID,
        provider="runway",
        prompt=CORRECTED_PROMPT,
        parameters={'seed': LOCKED_SEED}
    )
    job_id = job.id
    
    print(f"✓ Job created: {job_id}")
    
    # Verify seed
    job_seed = job.input_payload.parameters.get('seed') if job.input_payload.parameters else None
    print(f"  Seed in job: {job_seed}")
    
    if job_seed != LOCKED_SEED:
        print(f"\n❌ SEED MISMATCH!")
        return
    
    # Submit
    print(f"\n[STEP 2] Submitting to Runway...")
    
    submitted_job = await render_service.submit_job(job_id)
    provider_job_id = submitted_job.provider_job_id
    
    print(f"✓ Submitted to Runway")
    print(f"  Provider Job ID: {provider_job_id}")
    print(f"  Status: {submitted_job.status}")
    
    # Verify seed persisted
    submitted_seed = submitted_job.input_payload.parameters.get('seed') if submitted_job.input_payload.parameters else None
    print(f"  Seed after submission: {submitted_seed}")
    
    if submitted_seed != LOCKED_SEED:
        print(f"\n⚠️  Seed changed during submission!")
    
    # Poll for completion
    print(f"\n[STEP 3] Polling for completion...")
    
    max_polls = 60
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
    
    # Download video
    print(f"\n[STEP 4] Downloading video...")
    
    from app.services.render_retry_service import render_retry_service
    
    try:
        video_path = await render_retry_service.download_runway_video(
            video_url=output_url,
            project_id=PROJECT_ID,
            shot_id=SHOT_ID,
            job_id=job_id,
        )
        print(f"✓ Downloaded: {video_path}")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return
    
    # Extract frames
    print(f"\n[STEP 5] Extracting frames...")
    
    output_dir = os.path.dirname(video_path)
    frame_paths = await extract_frames_ffmpeg(video_path, output_dir, "retry")
    
    print(f"\n✓ Extracted {len(frame_paths)} frames")
    
    # Score adherence
    print(f"\n[STEP 6] Running adherence scoring...")
    
    adherence_service = AdherenceService(storage=storage)
    
    expected_slots = {
        "character_state": "People visible at human scale, faces and gestures clearly shown, interacting closely",
        "action": "Vendors actively serving customers, people laughing and talking, continuous human activity",
        "environment_persistence": "Chicago, L train, skyline",
        "camera": "Wide shot",
        "lighting": "golden hour light",
    }
    
    try:
        score = await adherence_service.score_render_attempt(
            shot_id=SHOT_ID,
            attempt_n=2,  # Still calling it attempt 2
            video_url=output_url,
            expected_slots=expected_slots,
            extracted_frames=frame_paths,
        )
        
        print(f"\n✓ Scoring complete!")
        
        # Build score_json
        score_json = {
            "shot_id": score.shot_id,
            "attempt_n": score.attempt_n,
            "frames_scored": score.frames_scored,
            "dimensions": {
                dim: {
                    "score": score_obj.score,
                    "evidence": score_obj.evidence,
                    "expected": score_obj.expected,
                    "observed": score_obj.observed,
                }
                for dim, score_obj in score.dimensions.items()
            },
            "temporal_drift": score.temporal_drift,
            "adherence_score": score.adherence_score,
            "verdict": score.verdict,
            "failed_slots": score.failed_slots,
        }
        
        print(f"\n{'=' * 80}")
        print("ATTEMPT 2 RETRY - SCORE JSON")
        print(f"{'=' * 80}")
        print(json.dumps(score_json, indent=2))
        
        print(f"\n{'=' * 80}")
        print("COMPARISON: Original Attempt 2 vs Retry")
        print(f"{'=' * 80}")
        
        # Load original attempt 2 from database
        attempts = storage.list_render_attempts(project_id=PROJECT_ID, shot_id=SHOT_ID)
        attempt2_original = next((a for a in attempts if a.get('attempt_number') == 2), None)
        
        if attempt2_original:
            original_score_json = attempt2_original.get('score_json')
            if isinstance(original_score_json, str):
                original_score_json = json.loads(original_score_json)
            
            print(f"\nORIGINAL ATTEMPT 2:")
            print(f"  Adherence: {original_score_json.get('adherence_score')}/100")
            print(f"  Verdict: {original_score_json.get('verdict')}")
            
            original_dims = original_score_json.get('dimensions', {})
            print(f"  Dimensions:")
            for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
                if dim_name in original_dims:
                    score_val = original_dims[dim_name].get('score', 'N/A')
                    print(f"    - {dim_name}: {score_val}/100")
            
            print(f"\nRETRY ATTEMPT 2:")
            print(f"  Adherence: {score.adherence_score}/100")
            print(f"  Verdict: {score.verdict}")
            
            print(f"  Dimensions:")
            for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
                dim_data = score.dimensions.get(dim_name)
                if dim_data:
                    print(f"    - {dim_name}: {dim_data.score}/100")
            
            # Calculate deltas
            print(f"\n{'─' * 80}")
            print("DELTA (Retry - Original):")
            print(f"{'─' * 80}")
            
            for dim_name in ['character_state', 'action', 'camera', 'lighting', 'environment_persistence']:
                orig_score = original_dims.get(dim_name, {}).get('score', 0)
                retry_score = score.dimensions.get(dim_name).score if score.dimensions.get(dim_name) else 0
                delta = retry_score - orig_score
                
                if delta == 0:
                    status = "IDENTICAL"
                    arrow = "━"
                elif abs(delta) <= 10:
                    status = "SIMILAR"
                    arrow = "≈"
                else:
                    status = "DIFFERENT"
                    arrow = "≠"
                
                print(f"  {dim_name}: {orig_score} → {retry_score} ({delta:+.0f}) {arrow} {status}")
            
            # Overall delta
            orig_overall = original_score_json.get('adherence_score', 0)
            retry_overall = score.adherence_score
            overall_delta = retry_overall - orig_overall
            
            print(f"\n  OVERALL: {orig_overall} → {retry_overall} ({overall_delta:+.1f})")
            
            if abs(overall_delta) <= 5:
                print(f"\n  ✅ CONSISTENT: Retry produced similar score (±5 points)")
                print(f"     Seed locking is working for this prompt.")
            else:
                print(f"\n  ⚠️  DIVERGENT: Retry produced different score (>{5} point delta)")
                print(f"     Seed may not fully control generation for this prompt.")
        
        print(f"\n{'=' * 80}")
        print("KEY OBSERVATIONS")
        print(f"{'=' * 80}")
        
        # Check if it's nighttime again
        lighting_score = score.dimensions.get('lighting').score if score.dimensions.get('lighting') else None
        lighting_observed = score.dimensions.get('lighting').observed if score.dimensions.get('lighting') else ""
        
        camera_score = score.dimensions.get('camera').score if score.dimensions.get('camera') else None
        
        if lighting_score is not None and lighting_score < 20:
            print(f"\n  🌙 NIGHTTIME AGAIN: lighting score = {lighting_score}/100")
            print(f"     Observed: {lighting_observed[:80]}...")
            print(f"\n  ✅ REGRESSION IS CONSISTENT")
            print(f"     The corrected prompt + seed 983559286 reliably produces nighttime scene.")
        elif lighting_score is not None and lighting_score >= 80:
            print(f"\n  ☀️  GOLDEN HOUR: lighting score = {lighting_score}/100")
            print(f"     Observed: {lighting_observed[:80]}...")
            print(f"\n  ⚠️  REGRESSION NOT CONSISTENT")
            print(f"     This retry got golden hour, but original Attempt 2 was nighttime.")
        else:
            print(f"\n  ⚠️  LIGHTING UNCLEAR: score = {lighting_score}/100")
        
        if camera_score is not None and camera_score < 30:
            print(f"\n  📹 CLOSE/MEDIUM SHOT: camera score = {camera_score}/100")
            print(f"     (Expected wide shot)")
        elif camera_score is not None and camera_score >= 80:
            print(f"\n  📹 WIDE SHOT: camera score = {camera_score}/100")
            print(f"     (Matches expectation)")
        
        character_score = score.dimensions.get('character_state').score if score.dimensions.get('character_state') else None
        
        if character_score is not None and character_score < 20:
            print(f"\n  👤 NO CROWD: character_state score = {character_score}/100")
            print(f"     (Still failing to show people interacting)")
        elif character_score is not None and character_score >= 50:
            print(f"\n  👥 PEOPLE VISIBLE: character_state score = {character_score}/100")
            print(f"     (Some improvement)")
        
        print(f"\n{'═' * 80}")
        print("RETRY TEST COMPLETE")
        print(f"{'═' * 80}")
        
        print(f"\nVideo saved: {video_path}")
        print(f"Frames saved: {len(frame_paths)} JPGs in {output_dir}")
        
    except Exception as e:
        print(f"\n❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
