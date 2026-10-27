#!/usr/bin/env python3
"""
Test render_retry_service with a local video file.
Bypasses download to test the actual scoring/persistence logic.
"""
import asyncio
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.data.storage import get_storage
from app.services.render_retry_service import render_retry_service
from app.services.adherence_service import adherence_service
from app.services.keyframe_extraction_service import keyframe_extraction_service


async def main():
    print("=" * 80)
    print("LOCAL VIDEO TEST: render_retry_service scoring + persistence")
    print("=" * 80)
    print()
    
    # Find a local video
    local_video = Path(__file__).parent / "outputs" / "qa_semantic_memory.mp4"
    if not local_video.exists():
        print(f"✗ Local video not found: {local_video}")
        return 1
    
    print(f"✓ Using local video: {local_video}")
    print()
    
    # Initialize storage and services
    storage = get_storage("sqlite")
    
    from app.services.video_asset_service import video_asset_service
    video_asset_service._storage = storage
    
    keyframe_extraction_service._storage = storage
    keyframe_extraction_service._video_asset_service = video_asset_service
    
    render_retry_service.set_storage(storage)
    render_retry_service._adherence_service = adherence_service
    render_retry_service._keyframe_service = keyframe_extraction_service
    render_retry_service._video_asset_service = video_asset_service
    
    print("✓ Storage and services initialized")
    print()
    
    # Test parameters
    project_id = "test_project_local"
    shot_id = "scene_001_shot_001"
    job_id = "test_job_local_001"
    prompt = "A musician discovers a memory glitch in the city, cinematic wide shot"
    asset_id = f"{shot_id}_{job_id}"
    
    print(f"Test Parameters:")
    print(f"  Project: {project_id}")
    print(f"  Shot: {shot_id}")
    print(f"  Job: {job_id}")
    print(f"  Prompt: {prompt}")
    print(f"  Video Path: {local_video}")
    print()
    
    print("=" * 80)
    print("PHASE 1: Extract Keyframes")
    print("=" * 80)
    print()
    
    try:
        frame_paths = await render_retry_service.extract_representative_frames(
            video_path=str(local_video),
            asset_id=asset_id,
        )
        print(f"✓ Extracted {len(frame_paths)} keyframes:")
        for i, path in enumerate(frame_paths, 1):
            print(f"  {i}. {path}")
        print()
    except Exception as exc:
        print(f"✗ Keyframe extraction failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("PHASE 2: Score Prompt Adherence (REAL Groq API Call)")
    print("=" * 80)
    print()
    print("⚠️  This will call Groq API for vision analysis...")
    print()
    
    try:
        # Manually call adherence service
        prompt_slots = {"description": prompt}
        
        score = await adherence_service.score_render_attempt(
            shot_id=shot_id,
            attempt_n=1,
            video_url="file://" + str(local_video),
            expected_slots=prompt_slots,
            extracted_frames=frame_paths,
        )
        
        print("✓ Adherence scoring complete")
        print()
        print(f"Score Summary:")
        print(f"  Overall Score: {score.adherence_score}")
        print(f"  Verdict: {score.verdict}")
        print(f"  Frames Scored: {score.frames_scored}")
        print(f"  Temporal Drift: {score.temporal_drift}")
        print()
        
        if score.dimensions:
            print("Dimension Scores:")
            for dim, dim_score in score.dimensions.items():
                print(f"  {dim}:")
                print(f"    Score: {dim_score.score}")
                print(f"    Expected: {dim_score.expected}")
                print(f"    Observed: {dim_score.observed}")
                print(f"    Evidence: {dim_score.evidence}")
                print()
        
        # Serialize for persistence
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
        
    except Exception as exc:
        print(f"✗ Adherence scoring failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("PHASE 3: Persist to Database")
    print("=" * 80)
    print()
    
    try:
        attempt_id = render_retry_service._persist_attempt(
            shot_id=shot_id,
            attempt_n=1,
            prompt_text=prompt,
            provider="runway",
            adherence_score=score.adherence_score,
            score_json=score_json,
            diff_json=None,
            job_id=job_id,
            project_id=project_id,
        )
        
        print(f"✓ Persisted attempt: {attempt_id}")
        print()
        
    except Exception as exc:
        print(f"✗ Persistence failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("PHASE 4: Query Database")
    print("=" * 80)
    print()
    
    try:
        attempts = storage.list_render_attempts(
            project_id=project_id,
            shot_id=shot_id,
        )
        
        print(f"✓ Found {len(attempts)} attempt(s) in database")
        print()
        
        if attempts:
            for attempt in attempts:
                print(f"DATABASE ROW:")
                print(f"  Shot ID: {attempt.get('shot_id')}")
                print(f"  Attempt #: {attempt.get('attempt_n')}")
                print(f"  Provider: {attempt.get('provider')}")
                print(f"  Adherence Score: {attempt.get('adherence_score')}")
                print(f"  Created: {attempt.get('created_at')}")
                print(f"  Prompt: {attempt.get('prompt_text', '')[:80]}...")
                print()
                
                if attempt.get('score_json'):
                    print("SCORE_JSON (persisted):")
                    print(json.dumps(attempt['score_json'], indent=2))
                    print()
        else:
            print("⚠️  No attempts found!")
            return 1
            
    except Exception as exc:
        print(f"✗ Database query failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("=" * 80)
    print("✅ TEST COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  ✓ Keyframes extracted from local video")
    print(f"  ✓ Real Groq API call for adherence scoring")
    print(f"  ✓ Score persisted to render_attempts table")
    print(f"  ✓ Database row verified with full score_json")
    print()
    
    return 0


if __name__ == "__main__":
    from app.script_guard import refuse_non_approved_provider

    refuse_non_approved_provider(
        __file__,
        what="score a local video via the retry service with a real Groq scoring call",
        provider="groq",
    )
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
