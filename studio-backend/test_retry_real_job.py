#!/usr/bin/env python3
"""
Test render_retry_service.record_render_attempt() with a real completed job.
Uses real API calls to Groq/Gemini for scoring.
"""
import asyncio
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Verify API keys loaded
print("Environment check:")
print(f"  GROQ_API_KEY: {'✓ loaded' if os.getenv('GROQ_API_KEY') else '✗ missing'}")
print(f"  GEMINI_API_KEY: {'✓ loaded' if os.getenv('GEMINI_API_KEY') else '✗ missing'}")
print(f"  RUNWAYML_API_SECRET: {'✓ loaded' if os.getenv('RUNWAYML_API_SECRET') else '✗ missing'}")
print()

from app.data.storage import get_storage
from app.services.render_retry_service import render_retry_service
from app.services.render import render_service, set_storage


async def main():
    print("=" * 80)
    print("REAL JOB TEST: render_retry_service.record_render_attempt()")
    print("=" * 80)
    print()
    
    # Initialize storage and services
    storage = get_storage("sqlite")
    set_storage(storage)
    
    # Initialize services needed for quality analysis
    from app.services.adherence_service import adherence_service
    from app.services.keyframe_extraction_service import keyframe_extraction_service
    from app.services.video_asset_service import video_asset_service
    
    video_asset_service._storage = storage
    keyframe_extraction_service._storage = storage
    keyframe_extraction_service._video_asset_service = video_asset_service
    
    render_retry_service.set_storage(storage)
    render_retry_service._adherence_service = adherence_service
    render_retry_service._keyframe_service = keyframe_extraction_service
    render_retry_service._video_asset_service = video_asset_service
    
    print("✓ Storage initialized")
    print()
    
    # Get a real completed job from database
    job_id = "job-20260528170029-c5ca66d8-scene_001_shot_001"
    
    job = storage.get_job(job_id)
    if not job:
        print(f"✗ Job {job_id} not found in database")
        return 1
    
    print(f"Found job:")
    print(f"  ID: {job.id}")
    print(f"  Project: {job.project_id}")
    print(f"  Shot: {job.shot_id}")
    print(f"  Status: {job.status}")
    print(f"  Provider: {job.provider}")
    
    if job.output_payload:
        output_url = job.output_payload.asset_url
        print(f"  Output URL: {output_url[:80]}...")
    else:
        print("✗ Job has no output_payload")
        return 1
    
    # Get prompt from input_payload or default
    prompt = "A cinematic shot"
    if job.input_payload and hasattr(job.input_payload, 'prompt'):
        prompt = job.input_payload.prompt or prompt
    
    print(f"  Prompt: {prompt[:100]}")
    print()
    
    print("=" * 80)
    print("RECORDING RENDER ATTEMPT with REAL API CALLS")
    print("=" * 80)
    print()
    print("⚠️  This will:")
    print("   1. Refresh the CloudFront URL (POST /jobs/{job_id}/refresh-url)")
    print("   2. Download the video")
    print("   3. Extract keyframes")
    print("   4. Call Groq API for prompt adherence scoring")
    print("   5. Call Gemini API for keyframe quality analysis")
    print("   6. Persist results to render_attempts table")
    print()
    print("Proceeding in 3 seconds...")
    await asyncio.sleep(3)
    print()
    
    try:
        result = await render_retry_service.record_render_attempt(
            project_id=job.project_id,
            shot_id=job.shot_id,
            job_id=job.id,
            output_url=output_url,
            prompt=prompt,
        )
        
        print("✓ Render attempt recorded successfully")
        print()
        print(f"Result:")
        print(f"  Attempt ID: {result.get('attempt_id')}")
        print(f"  Job ID: {result.get('job_id')}")
        print(f"  Attempt Number: {result.get('attempt_number')}")
        print(f"  Adherence Score: {result.get('adherence_score')}")
        print()
        
        if result.get('score_json'):
            print("Score JSON:")
            print(json.dumps(result['score_json'], indent=2))
            print()
        
        if result.get('diff_json'):
            print("Diff JSON:")
            print(json.dumps(result['diff_json'], indent=2))
            print()
        
    except Exception as exc:
        print(f"✗ Failed to record render attempt: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("QUERYING DATABASE")
    print("=" * 80)
    print()
    
    try:
        attempts = storage.list_render_attempts(
            project_id=job.project_id,
            shot_id=job.shot_id,
        )
        print(f"✓ Found {len(attempts)} attempt(s) for shot {job.shot_id}")
        print()
        
        if attempts:
            for attempt in attempts:
                print(f"Attempt {attempt.get('attempt_n')}:")
                print(f"  Created: {attempt.get('created_at')}")
                print(f"  Provider: {attempt.get('provider')}")
                print(f"  Adherence Score: {attempt.get('adherence_score')}")
                print(f"  Prompt: {attempt.get('prompt_text', '')[:80]}...")
                
                if attempt.get('score_json'):
                    score_json = attempt['score_json']
                    if isinstance(score_json, dict):
                        print(f"  Verdict: {score_json.get('verdict')}")
                        print(f"  Frames Scored: {score_json.get('frames_scored')}")
                        if score_json.get('dimensions'):
                            print(f"  Dimensions:")
                            for dim, data in score_json['dimensions'].items():
                                print(f"    - {dim}: {data.get('score')}")
                    else:
                        print(f"  Score JSON: {str(score_json)[:100]}")
                
                print()
        else:
            print("⚠️  No attempts found!")
            
    except Exception as exc:
        print(f"✗ Failed to query database: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("✅ REAL JOB TEST COMPLETE")
    print("=" * 80)
    print()
    
    return 0


if __name__ == "__main__":
    from app.script_guard import refuse_non_approved_provider

    refuse_non_approved_provider(
        __file__,
        what="record a render attempt with real Groq/Gemini scoring calls",
        provider="groq",
    )
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
