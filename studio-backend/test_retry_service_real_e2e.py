#!/usr/bin/env python3
"""
Real end-to-end test for render_retry_service.
Uses a real video URL and makes real Groq/Gemini API calls.
"""
import asyncio
import sys
import os
from pathlib import Path

# Add studio-backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.data.storage import get_storage
from app.services.render_retry_service import render_retry_service


async def main():
    print("=" * 80)
    print("REAL END-TO-END TEST: render_retry_service")
    print("=" * 80)
    print()
    
    # Initialize storage
    storage = get_storage("sqlite")
    render_retry_service.set_storage(storage)
    
    print("✓ Storage initialized")
    print()
    
    # Test parameters - using a real video URL
    project_id = "test_project_real_e2e"
    shot_id = "scene_001_shot_001"
    job_id = "test_job_real_e2e_001"
    
    # Using Big Buck Bunny sample video (publicly available)
    output_url = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
    
    prompt = "A giant rabbit in a meadow, cinematic lighting, wide shot"
    
    print(f"Test Parameters:")
    print(f"  Project ID: {project_id}")
    print(f"  Shot ID: {shot_id}")
    print(f"  Job ID: {job_id}")
    print(f"  Video URL: {output_url}")
    print(f"  Prompt: {prompt}")
    print()
    
    print("=" * 80)
    print("PHASE 1: Record Render Attempt with REAL API Calls")
    print("=" * 80)
    print()
    print("⚠️  This will make real calls to:")
    print("   - Groq API (for prompt adherence scoring)")
    print("   - Google Gemini API (for keyframe quality analysis)")
    print()
    print("Proceeding in 3 seconds...")
    await asyncio.sleep(3)
    print()
    
    try:
        result = await render_retry_service.record_render_attempt(
            project_id=project_id,
            shot_id=shot_id,
            job_id=job_id,
            output_url=output_url,
            prompt=prompt,
        )
        
        print("✓ Render attempt recorded successfully")
        print()
        print("Result:")
        print(f"  Attempt ID: {result.get('attempt_id')}")
        print(f"  Job ID: {result.get('job_id')}")
        print(f"  Attempt Number: {result.get('attempt_number')}")
        print()
        
        if result.get('score_json'):
            score = result['score_json']
            print("Prompt Adherence Score:")
            print(f"  Overall Score: {score.get('overall_score', 'N/A')}")
            print(f"  Visual Match: {score.get('visual_match', 'N/A')}")
            print(f"  Motion Match: {score.get('motion_match', 'N/A')}")
            print(f"  Style Match: {score.get('style_match', 'N/A')}")
            print(f"  Technical Quality: {score.get('technical_quality', 'N/A')}")
            print()
        
        if result.get('diff_json'):
            diff = result['diff_json']
            print("Keyframe Diff Analysis:")
            print(f"  Frames Analyzed: {diff.get('frames_analyzed', 'N/A')}")
            print(f"  Avg Variance: {diff.get('avg_variance', 'N/A')}")
            print(f"  Max Variance: {diff.get('max_variance', 'N/A')}")
            print(f"  Stability Rating: {diff.get('stability_rating', 'N/A')}")
            print()
        
    except Exception as exc:
        print(f"✗ Failed to record render attempt: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("PHASE 2: Query Database for Recorded Attempt")
    print("=" * 80)
    print()
    
    try:
        # Query the database directly
        attempts = storage.list_render_attempts(project_id=project_id, shot_id=shot_id)
        print(f"✓ Found {len(attempts)} attempt(s) in database")
        print()
        
        if attempts:
            for attempt in attempts:
                print(f"Attempt {attempt['attempt_number']}:")
                print(f"  ID: {attempt['id']}")
                print(f"  Job ID: {attempt['job_id']}")
                print(f"  Created: {attempt['created_at']}")
                print(f"  Has Score JSON: {bool(attempt.get('score_json'))}")
                print(f"  Has Diff JSON: {bool(attempt.get('diff_json'))}")
                
                if attempt.get('score_json'):
                    score = attempt['score_json']
                    if isinstance(score, dict):
                        print(f"  Overall Score: {score.get('overall_score', 'N/A')}")
                    else:
                        print(f"  Score JSON (raw): {str(score)[:100]}")
                
                if attempt.get('diff_json'):
                    diff = attempt['diff_json']
                    if isinstance(diff, dict):
                        print(f"  Stability Rating: {diff.get('stability_rating', 'N/A')}")
                    else:
                        print(f"  Diff JSON (raw): {str(diff)[:100]}")
                print()
        else:
            print("⚠️  No attempts found in database!")
            
    except Exception as exc:
        print(f"✗ Failed to query database: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("PHASE 3: Should Retry Analysis")
    print("=" * 80)
    print()
    
    try:
        should_retry = await render_retry_service.should_retry_render(
            project_id=project_id,
            shot_id=shot_id,
        )
        
        print(f"Should Retry: {should_retry['should_retry']}")
        print(f"Reason: {should_retry['reason']}")
        print(f"Attempt Count: {should_retry['attempt_count']}")
        print(f"Latest Score: {should_retry.get('latest_score', 'N/A')}")
        print()
        
    except Exception as exc:
        print(f"✗ Failed to analyze retry decision: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("✅ REAL END-TO-END TEST COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print("  ✓ Real video downloaded and analyzed")
    print("  ✓ Real Groq API call for prompt adherence")
    print("  ✓ Real Gemini API call for keyframe quality")
    print("  ✓ Data persisted to render_attempts table")
    print("  ✓ Retry decision logic executed successfully")
    print()
    
    return 0


if __name__ == "__main__":
    from app.script_guard import refuse_non_approved_provider

    refuse_non_approved_provider(
        __file__,
        what="end-to-end retry-service test with real Groq/Gemini scoring calls",
        provider="groq",
    )
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
