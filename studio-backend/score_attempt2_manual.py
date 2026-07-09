#!/usr/bin/env python3
"""
Manually score Attempt 2 using extracted frames and adherence service.
"""
import asyncio
import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from app.data.storage import get_storage
from app.services.adherence_service import AdherenceService


async def extract_frames_ffmpeg(video_path: str, output_dir: str) -> list[str]:
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
        frame_path = f"{output_dir}/frame_attempt2_{idx}.jpg"
        
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
    """Score attempt 2 manually."""
    
    print("=" * 80)
    print("MANUAL SCORING FOR ATTEMPT 2")
    print("=" * 80)
    
    # Constants
    PROJECT_ID = "project_3dba9330f43a"
    SHOT_ID = "scene_001"
    VIDEO_PATH = "/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-backend/outputs/renders/project_3dba9330f43a/scene_001_20260705_025049.mp4"
    OUTPUT_DIR = "/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-backend/outputs/renders/project_3dba9330f43a"
    
    CORRECTED_PROMPT = "People visible at human scale, faces and gestures clearly shown, interacting closely. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago, L train, skyline. Wide shot. golden hour light. Cinematic, film quality, single continuous shot."
    
    print(f"\n[STEP 1] Extracting frames from Attempt 2 video...")
    print(f"  Video: {VIDEO_PATH}")
    
    frame_paths = await extract_frames_ffmpeg(VIDEO_PATH, OUTPUT_DIR)
    
    print(f"\n✓ Extracted {len(frame_paths)} frames:")
    for fp in frame_paths:
        print(f"  - {fp}")
    
    # Initialize adherence service
    storage = get_storage("sqlite")
    adherence_service = AdherenceService(storage=storage)
    
    print(f"\n[STEP 2] Running adherence scoring with Gemini vision model...")
    
    # Parse prompt into slots (simplified - just use full prompt for all slots)
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
            attempt_n=2,
            video_url="",  # Not needed for local scoring
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
        print("ATTEMPT 2 SCORE JSON")
        print(f"{'=' * 80}")
        print(json.dumps(score_json, indent=2))
        
        print(f"\n{'=' * 80}")
        print("ATTEMPT 2 SUMMARY")
        print(f"{'=' * 80}")
        print(f"  Adherence Score: {score.adherence_score}/100")
        print(f"  Verdict: {score.verdict}")
        print(f"  Failed Slots: {score.failed_slots if score.failed_slots else 'None'}")
        
        print(f"\n  Dimension Scores:")
        for dim_name, dim_data in score_json['dimensions'].items():
            score_val = dim_data['score']
            print(f"    - {dim_name}: {score_val}/100")
        
        # Now persist the attempt manually using render_retry_service
        print(f"\n[STEP 3] Persisting attempt 2 to render_attempts table...")
        
        # Find job_id from the latest job for this shot
        # We know it was job-20260705024907-6bb1f958-scene_001 from the earlier output
        job_id = "job-20260705024907-6bb1f958-scene_001"
        
        from app.services.render_retry_service import render_retry_service
        render_retry_service.set_storage(storage)
        
        attempt_id = render_retry_service._persist_attempt(
            shot_id=SHOT_ID,
            attempt_n=2,
            prompt_text=CORRECTED_PROMPT,
            provider="runway",
            adherence_score=score.adherence_score,
            score_json=score_json,  # Pass dict, not JSON string
            diff_json=None,
            job_id=job_id,
            project_id=PROJECT_ID,
        )
        
        print(f"✓ Attempt 2 persisted with ID: {attempt_id}")
        
        # Now check if Attempt 1 exists
        print(f"\n[STEP 4] Checking for Attempt 1 in database...")
        
        attempts = storage.list_render_attempts(project_id=PROJECT_ID, shot_id=SHOT_ID)
        
        if len(attempts) == 0:
            print(f"  ⚠️  No attempts found - need to create Attempt 1 record")
            
            # Create Attempt 1 record with known data from context
            attempt1_score_json = {
                "shot_id": SHOT_ID,
                "attempt_n": 1,
                "frames_scored": [0.1, 0.5, 0.9],
                "dimensions": {
                    "character_state": {
                        "score": 0,
                        "evidence": "Render focused on cityscape without showing people at human scale",
                        "expected": "People fill the streets",
                        "observed": "Wide cityscape with no visible human figures at scale"
                    },
                    "action": {
                        "score": 0,
                        "evidence": "No human activity shown - only static urban environment",
                        "expected": "Music, laughter, food stands. Everything is vibrant",
                        "observed": "Static city view with no human activity visible"
                    },
                    "camera": {
                        "score": 100,
                        "evidence": "Wide shot executed correctly",
                        "expected": "Wide shot",
                        "observed": "Wide shot of cityscape"
                    },
                    "lighting": {
                        "score": 100,
                        "evidence": "Golden hour lighting captured accurately",
                        "expected": "golden hour light",
                        "observed": "Golden hour light on buildings"
                    },
                    "environment_persistence": {
                        "score": 100,
                        "evidence": "Chicago cityscape with L train and skyline visible throughout",
                        "expected": "Chicago, L train, skyline",
                        "observed": "Chicago skyline with L train visible"
                    }
                },
                "temporal_drift": {"start_score": 100, "end_score": 100},
                "adherence_score": 55.0,
                "verdict": "correctable",
                "failed_slots": ["character_state", "action"]
            }
            
            attempt1_prompt = "Chicago is alive. The L train moves through the skyline. People fill the streets. Music, laughter, food stands. Everything is vibrant. Wide shot, golden hour light. Cinematic, film quality, single continuous shot."
            attempt1_job_id = "job-20260705022017-acd09648-scene_001"
            
            attempt1_id = render_retry_service._persist_attempt(
                shot_id=SHOT_ID,
                attempt_n=1,
                prompt_text=attempt1_prompt,
                provider="runway",
                adherence_score=55.0,
                score_json=attempt1_score_json,  # Pass dict, not JSON string
                diff_json=None,
                job_id=attempt1_job_id,
                project_id=PROJECT_ID,
            )
            
            print(f"  ✓ Created Attempt 1 record with ID: {attempt1_id}")
        
        # Now show comparison
        print(f"\n{'=' * 80}")
        print("SIDE-BY-SIDE COMPARISON: ATTEMPT 1 vs ATTEMPT 2")
        print(f"{'=' * 80}")
        
        attempts = storage.list_render_attempts(project_id=PROJECT_ID, shot_id=SHOT_ID)
        attempts_sorted = sorted(attempts, key=lambda x: x.get('attempt_number', 0))
        
        print(f"\nFound {len(attempts_sorted)} attempt(s):")
        
        attempt1_data = None
        attempt2_data = None
        
        for att in attempts_sorted:
            att_num = att.get('attempt_number')
            print(f"\n{'─' * 80}")
            print(f"ATTEMPT {att_num}")
            print(f"{'─' * 80}")
            print(f"  Job ID: {att.get('job_id')}")
            print(f"  Timestamp: {att.get('timestamp')}")
            
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
                    score_val = dim_data.get('score', 'N/A')
                    print(f"    - {dim_name}: {score_val}/100")
                
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
        print("SCORING COMPLETE")
        print(f"{'═' * 80}")
        
    except Exception as e:
        print(f"\n❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
