#!/usr/bin/env python3
"""
Score the completed attempt 1 render directly.
Job already completed: job-20260705022017-acd09648-scene_001
Output URL already exists.
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.adherence_service import adherence_service
from app.services.render_retry_service import render_retry_service


async def main():
    print("=" * 80)
    print("SCORE ATTEMPT 1 - Direct Adherence Scoring")
    print("=" * 80)
    
    # Initialize storage
    storage = get_storage("sqlite")
    render_retry_service.set_storage(storage)
    
    # Job details from the completed run
    project_id = "project_3dba9330f43a"
    shot_id = "scene_001"
    job_id = "job-20260705022017-acd09648-scene_001"
    output_url = "https://dnznrvs05pmza.cloudfront.net/e355fc61-729d-4472-9044-942abdc74a27.mp4?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiNzJkNzVjZDRmOTczMGNlMiIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4MzM3OTAyOH0.uWVTJb2JuqA2AfjzXwn7tRk3cmyjTSIOHhR_HRXHclo"
    prompt = "Chicago is alive. The L train moves through the skyline. People fill the streets. Music, laughter, food stands. Everything is vibrant. Wide shot, golden hour light. Cinematic, film quality, single continuous shot."
    seed = 983559286
    
    print(f"\nAttempt 1 Details:")
    print(f"  Project: {project_id}")
    print(f"  Shot: {shot_id}")
    print(f"  Job ID: {job_id}")
    print(f"  Seed: {seed}")
    print(f"  Output URL: {output_url[:60]}...")
    print(f"  Prompt: {prompt[:100]}...")
    
    print(f"\n[STEP 1] Downloading video...")
    
    try:
        video_path = await render_retry_service.download_runway_video(
            video_url=output_url,
            project_id=project_id,
            shot_id=shot_id,
            job_id=job_id
        )
        print(f"✓ Downloaded to: {video_path}")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n[STEP 2] Extracting keyframes...")
    
    try:
        asset_id = f"{shot_id}_{job_id}"
        frame_paths = await render_retry_service.extract_representative_frames(
            video_path=video_path,
            asset_id=asset_id
        )
        print(f"✓ Extracted {len(frame_paths)} frames:")
        for i, frame_path in enumerate(frame_paths, 1):
            print(f"    Frame {i}: {frame_path}")
    except Exception as e:
        print(f"❌ Frame extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n[STEP 3] Running adherence scoring...")
    
    try:
        # Parse prompt into slots (simplified)
        prompt_slots = {
            "description": prompt,
            "camera": "wide shot",
            "lighting": "golden hour light"
        }
        
        score = await adherence_service.score_render_attempt(
            shot_id=shot_id,
            attempt_n=1,
            video_url=output_url,
            expected_slots=prompt_slots,
            extracted_frames=frame_paths
        )
        
        print(f"✓ Scoring complete!")
        print(f"\n  Overall adherence score: {score.adherence_score}")
        print(f"  Verdict: {score.verdict}")
        print(f"  Frames scored: {score.frames_scored}")
        print(f"  Failed slots: {score.failed_slots}")
        
        print(f"\n  Dimensions:")
        for dim_name, dim_score in score.dimensions.items():
            print(f"    - {dim_name}:")
            print(f"        Score: {dim_score.score}")
            print(f"        Expected: {dim_score.expected}")
            print(f"        Observed: {dim_score.observed}")
            print(f"        Evidence: {dim_score.evidence[:100] if dim_score.evidence else 'N/A'}...")
        
        print(f"\n  Temporal drift: {score.temporal_drift}")
        
        # Build full score_json
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
                    "status": score_obj.status if hasattr(score_obj, 'status') else None,
                    "corrective_guidance": score_obj.corrective_guidance if hasattr(score_obj, 'corrective_guidance') else None
                }
                for dim, score_obj in score.dimensions.items()
            },
            "temporal_drift": score.temporal_drift,
            "adherence_score": score.adherence_score,
            "verdict": score.verdict,
            "failed_slots": score.failed_slots,
        }
        
        print(f"\n" + "=" * 80)
        print("FULL SCORE JSON:")
        print("=" * 80)
        print(json.dumps(score_json, indent=2))
        
        # Check if correctable
        if score.verdict == "correctable":
            print(f"\n" + "=" * 80)
            print("VERDICT: CORRECTABLE - Generating Corrective Diff")
            print("=" * 80)
            
            # Extract corrective notes from dimensions
            corrective_notes = []
            for dim_name, dim_data in score_json["dimensions"].items():
                if dim_data.get("status") == "needs_correction":
                    guidance = dim_data.get("corrective_guidance", "")
                    if guidance:
                        corrective_notes.append(f"{dim_name}: {guidance}")
            
            if corrective_notes:
                corrections = ". ".join(corrective_notes)
                corrected_prompt = f"{prompt} [Corrections: {corrections}]"[:512]
                
                print(f"\nCorrective notes identified:")
                for note in corrective_notes:
                    print(f"  - {note}")
                
                print(f"\nCorrected prompt (truncated to 512 chars):")
                print(f"  {corrected_prompt}")
                
                print(f"\nLocked seed for attempt 2: {seed}")
                
                print(f"\n⚠️  READY FOR ATTEMPT 2")
                print(f"  Waiting for user authorization before submitting...")
            else:
                print(f"\n⚠️  Verdict is 'correctable' but no corrective guidance found in dimensions")
        
        elif score.verdict == "pass":
            print(f"\n✅ VERDICT: PASS - No correction needed")
            print(f"  Attempt 1 passed adherence checks")
        
        else:
            print(f"\n⚠️  VERDICT: {score.verdict}")
            print(f"  May require manual review or retry")
        
    except Exception as e:
        print(f"❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n" + "=" * 80)
    print("SCORING COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    from app.script_guard import refuse_non_approved_provider

    refuse_non_approved_provider(
        __file__,
        what="download a prior Runway clip + score it with Gemini/Groq vision calls",
        provider="gemini",
    )
    asyncio.run(main())
