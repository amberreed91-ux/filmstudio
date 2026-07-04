"""
Render Retry Service - Automated prompt adherence retry loop for Previs Bay.

After a render completes:
1. Extract keyframes at 10%, 50%, 90%
2. Call vision scorer to get AdherenceScore
3. Persist attempt to render_attempts table
4. If verdict == "pass": stop, mark final
5. If verdict == "correctable" AND attempt_n < 3:
   - Call corrector to generate CorrectiveDiff
   - Apply diff to prompt slots
   - Keep seed locked
   - Submit new render with corrected prompt
6. If verdict == "manual_review" OR attempt_n == 3: stop, flag for review

Includes "stuck shot" detection: if adherence score improves by < 5 points
between consecutive attempts, stop immediately to avoid burning attempts on
an unresponsive seed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.adherence_service import AdherenceService, adherence_service
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService

logger = logging.getLogger("render_retry_service")

MAX_ATTEMPTS = 3
STUCK_SHOT_THRESHOLD = 5.0  # If score improves by less than this, stop


class RenderRetryService:
    """
    Manages automated render quality analysis and retry logic.
    
    Two main workflows:
    
    1. PASSIVE OBSERVATION (record_render_attempt):
       - Called automatically when any render completes
       - Downloads video, analyzes quality, persists results
       - No retry decisions or corrective actions
       - Used for: automatic quality tracking, historical data
    
    2. ACTIVE RETRY LOOP (evaluate_and_retry):
       - Called manually for iterative improvement workflows
       - Expects video already downloaded and structured prompt slots
       - Makes retry decisions and generates corrective diffs
       - Used for: automated re-render with prompt corrections
    
    These are separate use cases with different contracts - do not conflate them.
    """

    def __init__(
        self,
        storage=None,
        adherence_service: Optional[AdherenceService] = None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
        video_asset_service: Optional[VideoAssetService] = None,
    ):
        self._storage = storage
        self._adherence_service = adherence_service or adherence_service
        self._keyframe_service = keyframe_service
        self._video_asset_service = video_asset_service

    def set_storage(self, storage):
        """Set the storage instance (for dependency injection)"""
        self._storage = storage

    async def record_render_attempt(
        self,
        project_id: str,
        shot_id: str,
        job_id: str,
        output_url: str,
        prompt: str,
    ) -> Dict[str, Any]:
        """
        Record a completed render attempt with quality analysis (passive observation only).
        
        This is called automatically when a render job completes. It performs analysis
        and records results but does NOT make retry decisions or trigger new renders.
        
        For active retry loops with corrective diffs, use evaluate_and_retry() instead.
        
        Args:
            project_id: Project identifier
            shot_id: Shot identifier  
            job_id: Render job identifier
            output_url: URL to completed video
            prompt: Prompt text that was used
            
        Returns:
            Dict with attempt_id, scores, and analysis results
        """
        if not self._storage:
            logger.warning("No storage configured for render_retry_service")
            return {"error": "no_storage"}
        
        # Get current attempt number for this shot
        existing_attempts = self._storage.list_render_attempts(
            project_id=project_id,
            shot_id=shot_id,
        )
        attempt_number = len(existing_attempts) + 1
        
        # Download video for analysis
        try:
            video_path = await self.download_runway_video(
                video_url=output_url,
                project_id=project_id,
                shot_id=shot_id,
                job_id=job_id,  # Pass job_id to enable URL refresh
            )
        except Exception as e:
            logger.warning(
                "Failed to download video for quality check | job=%s | error=%s",
                job_id,
                e,
            )
            return {"error": f"download_failed: {e}"}
        
        # Extract keyframes
        try:
            asset_id = f"{shot_id}_{job_id}"
            frame_paths = await self.extract_representative_frames(
                video_path=video_path,
                asset_id=asset_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to extract frames for quality check | job=%s | error=%s",
                job_id,
                e,
            )
            return {"error": f"frame_extraction_failed: {e}"}
        
        # Score adherence (if service available)
        score_json = None
        adherence_score = None
        if self._adherence_service:
            try:
                # Parse prompt slots if available (simplified for now)
                prompt_slots = {"description": prompt}
                
                score = await self._adherence_service.score_render_attempt(
                    shot_id=shot_id,
                    attempt_n=attempt_number,
                    video_url=output_url,
                    expected_slots=prompt_slots,
                    extracted_frames=frame_paths,
                )
                
                adherence_score = score.adherence_score
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
            except Exception as e:
                logger.warning(
                    "Adherence scoring failed for job %s: %s",
                    job_id,
                    e,
                )
        
        # Analyze keyframe diff (if service available)
        diff_json = None
        if self._keyframe_service:
            try:
                diff_analysis = await self._keyframe_service.analyze_keyframe_variance(
                    frame_paths=frame_paths,
                    shot_id=shot_id,
                )
                diff_json = {
                    "frames_analyzed": len(frame_paths),
                    "avg_variance": diff_analysis.get("avg_variance"),
                    "max_variance": diff_analysis.get("max_variance"),
                    "stability_rating": diff_analysis.get("stability_rating"),
                    "frame_details": diff_analysis.get("frame_details", []),
                }
            except Exception as e:
                logger.warning(
                    "Keyframe diff analysis failed for job %s: %s",
                    job_id,
                    e,
                )
        
        # Persist the attempt
        attempt_id = self._persist_attempt(
            shot_id=shot_id,
            attempt_n=attempt_number,
            prompt_text=prompt,
            provider="runway",  # Default to runway
            adherence_score=adherence_score,
            score_json=score_json,
            diff_json=diff_json,
            job_id=job_id,
            project_id=project_id,
        )
        
        logger.info(
            "RENDER_ATTEMPT_RECORDED | job=%s | shot=%s | attempt=%d | score=%s",
            job_id,
            shot_id,
            attempt_number,
            adherence_score,
        )
        
        return {
            "attempt_id": attempt_id,
            "job_id": job_id,
            "attempt_number": attempt_number,
            "adherence_score": adherence_score,
            "score_json": score_json,
            "diff_json": diff_json,
        }

    async def download_runway_video(
        self,
        video_url: str,
        project_id: str,
        shot_id: str,
        job_id: Optional[str] = None,
    ) -> str:
        """
        Download Runway video to local storage.
        Refreshes URL if job_id provided to ensure non-expired CloudFront URL.
        
        Args:
            video_url: Runway video URL (may be expired)
            project_id: Project ID
            shot_id: Shot ID
            job_id: Optional job ID - if provided, will refresh URL first
            
        Returns:
            Local file path to downloaded video
        """
        import aiohttp
        import os
        from pathlib import Path
        
        # Refresh URL if job_id provided (prevents 403 on expired CloudFront URLs)
        if job_id:
            try:
                from app.services.render import render_service
                refreshed_url = await render_service.refresh_output_url(job_id)
                if refreshed_url:
                    logger.info(
                        "URL_REFRESHED | job=%s | old_url=%s | new_url=%s",
                        job_id,
                        video_url[:80],
                        refreshed_url[:80],
                    )
                    video_url = refreshed_url
            except Exception as e:
                logger.warning(
                    "URL_REFRESH_FAILED | job=%s | error=%s | attempting download with original URL",
                    job_id,
                    e,
                )
        
        # Create output directory
        outputs_root = Path(__file__).resolve().parents[2] / "outputs"
        renders_dir = outputs_root / "renders" / project_id
        renders_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate local filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_filename = f"{shot_id}_{timestamp}.mp4"
        local_path = renders_dir / local_filename
        
        # Download video
        logger.info(
            "DOWNLOADING_RUNWAY_VIDEO | shot=%s | url=%s | local_path=%s",
            shot_id,
            video_url[:80],
            local_path,
        )
        
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status != 200:
                    raise ValueError(
                        f"Failed to download video: HTTP {response.status}"
                    )
                
                content = await response.read()
                with open(local_path, "wb") as f:
                    f.write(content)
        
        logger.info(
            "VIDEO_DOWNLOADED | shot=%s | size_bytes=%d | path=%s",
            shot_id,
            len(content),
            local_path,
        )
        
        return str(local_path)

    async def extract_representative_frames(
        self,
        video_path: str,
        asset_id: str,
    ) -> List[str]:
        """
        Extract 3 frames at 10%, 50%, 90% of video duration.
        
        Args:
            video_path: Local path to video file
            asset_id: Asset ID for frame organization
            
        Returns:
            List of 3 frame paths [frame_10, frame_50, frame_90]
        """
        if not self._keyframe_service:
            raise ValueError("Keyframe extraction service not configured")
        
        # Extract keyframes - keyframe_service methods are sync, run in thread
        keyframes = await asyncio.to_thread(
            self._keyframe_service.extract_keyframes_representative,
            asset_id=asset_id,
            interval_seconds=5,
            max_frames=3,
            overwrite=True,
        )
        
        if len(keyframes) < 3:
            raise ValueError(
                f"Expected 3 keyframes, got {len(keyframes)}"
            )
        
        # Return paths to the 3 frames
        frame_paths = [kf.frame_path for kf in keyframes[:3]]
        
        logger.info(
            "FRAMES_EXTRACTED | asset=%s | count=%d | paths=%s",
            asset_id,
            len(frame_paths),
            frame_paths,
        )
        
        return frame_paths

    def _persist_attempt(
        self,
        shot_id: str,
        attempt_n: int,
        prompt_text: str,
        provider: str,
        adherence_score: Optional[float],
        score_json: Optional[Dict[str, Any]],
        diff_json: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Persist render attempt to render_attempts table.
        
        Args:
            shot_id: Shot identifier
            attempt_n: Attempt number (1-based)
            prompt_text: Full assembled prompt that was sent
            provider: Provider name (e.g., "runway")
            adherence_score: 0-100 adherence score (optional)
            score_json: Full AdherenceScore as JSON (optional)
            diff_json: Optional CorrectiveDiff as JSON (if correctable)
            job_id: Optional render job ID (stored if column exists)
            project_id: Optional project ID (stored if column exists)
            
        Returns:
            The generated attempt_id or composite key
        """
        if not self._storage:
            logger.warning("No storage configured, skipping attempt persistence")
            return ""
        
        try:
            import sqlite3
            import uuid
            
            with self._storage._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check which columns exist
                cursor.execute("PRAGMA table_info(render_attempts)")
                columns_info = cursor.fetchall()
                available_columns = {col[1] for col in columns_info}
                
                # Build dynamic INSERT based on available columns
                columns = ["shot_id", "attempt_n", "prompt_text", "provider"]
                values = [shot_id, attempt_n, prompt_text, provider]
                
                if "adherence_score" in available_columns and adherence_score is not None:
                    columns.append("adherence_score")
                    values.append(adherence_score)
                
                if "score_json" in available_columns and score_json:
                    columns.append("score_json")
                    values.append(json.dumps(score_json))
                
                if "diff_json" in available_columns and diff_json:
                    columns.append("diff_json")
                    values.append(json.dumps(diff_json))
                
                if "job_id" in available_columns and job_id:
                    columns.append("job_id")
                    values.append(job_id)
                
                if "project_id" in available_columns and project_id:
                    columns.append("project_id")
                    values.append(project_id)
                
                attempt_id = f"{shot_id}_{attempt_n}"
                if "id" in available_columns:
                    attempt_id = str(uuid.uuid4())
                    columns.append("id")
                    values.append(attempt_id)
                
                if "created_at" in available_columns:
                    columns.append("created_at")
                    values.append(datetime.now().isoformat())
                
                placeholders = ", ".join(["?"] * len(columns))
                columns_str = ", ".join(columns)
                
                query = f"INSERT OR REPLACE INTO render_attempts ({columns_str}) VALUES ({placeholders})"
                
                cursor.execute(query, values)
                conn.commit()
            
            logger.info(
                "ATTEMPT_PERSISTED | shot=%s | attempt=%d | score=%s | verdict=%s | id=%s",
                shot_id,
                attempt_n,
                adherence_score,
                score_json.get("verdict") if score_json else None,
                attempt_id,
            )
            
            return attempt_id
        
        except Exception as e:
            logger.error(
                "ATTEMPT_PERSISTENCE_FAILED | shot=%s | attempt=%d | error=%s",
                shot_id,
                attempt_n,
                e,
            )
            return ""

    def _get_previous_score(self, shot_id: str, attempt_n: int) -> Optional[float]:
        """
        Get adherence score from previous attempt for stuck shot detection.
        
        Args:
            shot_id: Shot identifier
            attempt_n: Current attempt number
            
        Returns:
            Previous attempt's adherence score, or None if no previous attempt
        """
        if not self._storage or attempt_n <= 1:
            return None
        
        try:
            with self._storage._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT adherence_score 
                    FROM render_attempts 
                    WHERE shot_id = ? AND attempt_n = ?
                    """,
                    (shot_id, attempt_n - 1),
                )
                row = cursor.fetchone()
                if row:
                    return float(row[0])
        except Exception as e:
            logger.warning(
                "PREVIOUS_SCORE_LOOKUP_FAILED | shot=%s | attempt=%d | error=%s",
                shot_id,
                attempt_n,
                e,
            )
        
        return None

    def _is_stuck_shot(
        self,
        shot_id: str,
        attempt_n: int,
        current_score: float,
    ) -> bool:
        """
        Detect if shot is stuck (score improving by < 5 points).
        
        Args:
            shot_id: Shot identifier
            attempt_n: Current attempt number
            current_score: Current adherence score
            
        Returns:
            True if shot is stuck and should stop retrying
        """
        if attempt_n <= 1:
            return False
        
        previous_score = self._get_previous_score(shot_id, attempt_n)
        if previous_score is None:
            return False
        
        improvement = current_score - previous_score
        is_stuck = improvement < STUCK_SHOT_THRESHOLD
        
        if is_stuck:
            logger.warning(
                "STUCK_SHOT_DETECTED | shot=%s | attempt=%d | "
                "prev_score=%.1f | current_score=%.1f | improvement=%.1f",
                shot_id,
                attempt_n,
                previous_score,
                current_score,
                improvement,
            )
        
        return is_stuck

    async def evaluate_and_retry(
        self,
        shot_id: str,
        attempt_n: int,
        video_url: str,
        video_path: str,
        asset_id: str,
        project_id: str,
        provider: str,
        current_prompt: str,
        prompt_slots: Dict[str, str],
        locked_seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate render and determine if retry is needed.
        
        Args:
            shot_id: Shot identifier
            attempt_n: Current attempt number (1-based)
            video_url: URL to rendered video
            video_path: Local path to video
            asset_id: Asset ID for frame extraction
            project_id: Project ID
            provider: Provider name
            current_prompt: Full assembled prompt that was used
            prompt_slots: Dict of prompt slots that can be corrected
            locked_seed: Locked random seed (must stay unchanged)
            
        Returns:
            Dict with:
                - verdict: "pass" | "correctable" | "manual_review" | "stuck"
                - adherence_score: float 0-100
                - should_retry: bool
                - corrected_slots: Optional[Dict[str, str]] (if should_retry)
                - diff: Optional[CorrectiveDiff] (if correctable)
                - score: AdherenceScore object
        """
        import asyncio
        
        # Extract frames at 10%, 50%, 90%
        try:
            frame_paths = await self.extract_representative_frames(
                video_path=video_path,
                asset_id=asset_id,
            )
        except Exception as e:
            logger.error(
                "FRAME_EXTRACTION_FAILED | shot=%s | attempt=%d | error=%s",
                shot_id,
                attempt_n,
                e,
            )
            return {
                "verdict": "manual_review",
                "adherence_score": 0.0,
                "should_retry": False,
                "error": f"Frame extraction failed: {e}",
            }
        
        # Score adherence
        try:
            score = await self._adherence_service.score_render_attempt(
                shot_id=shot_id,
                attempt_n=attempt_n,
                video_url=video_url,
                expected_slots=prompt_slots,
                extracted_frames=frame_paths,
            )
        except Exception as e:
            logger.error(
                "ADHERENCE_SCORING_FAILED | shot=%s | attempt=%d | error=%s",
                shot_id,
                attempt_n,
                e,
            )
            return {
                "verdict": "manual_review",
                "adherence_score": 0.0,
                "should_retry": False,
                "error": f"Adherence scoring failed: {e}",
            }
        
        # Serialize score for persistence
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
        
        # Check for stuck shot
        if self._is_stuck_shot(shot_id, attempt_n, score.adherence_score):
            # Persist attempt with stuck verdict
            self._persist_attempt(
                shot_id=shot_id,
                attempt_n=attempt_n,
                prompt_text=current_prompt,
                provider=provider,
                adherence_score=score.adherence_score,
                score_json={**score_json, "verdict": "stuck"},
            )
            
            return {
                "verdict": "stuck",
                "adherence_score": score.adherence_score,
                "should_retry": False,
                "score": score,
                "reason": "Score improvement < 5 points, seed unresponsive",
            }
        
        # Handle verdict
        if score.verdict == "pass":
            # Success! Persist and stop
            self._persist_attempt(
                shot_id=shot_id,
                attempt_n=attempt_n,
                prompt_text=current_prompt,
                provider=provider,
                adherence_score=score.adherence_score,
                score_json=score_json,
            )
            
            return {
                "verdict": "pass",
                "adherence_score": score.adherence_score,
                "should_retry": False,
                "score": score,
            }
        
        elif score.verdict == "correctable" and attempt_n < MAX_ATTEMPTS:
            # Generate corrective diff
            try:
                # Calculate available character budget (from reserve)
                current_length = len(current_prompt)
                chars_remaining = max(512 - current_length + 50, 0)  # 50-char reserve
                
                diff = await self._adherence_service.generate_corrective_diff(
                    score=score,
                    current_slots=prompt_slots,
                    chars_remaining=chars_remaining,
                )
                
                # Serialize diff for persistence
                diff_json = {
                    "base_attempt": diff.base_attempt,
                    "seed_locked": diff.seed_locked,
                    "ops": [
                        {
                            "slot": op.slot,
                            "op": op.op,
                            "old_text": op.old_text,
                            "new_text": op.new_text,
                            "reason": op.reason,
                            "char_delta": op.char_delta,
                        }
                        for op in diff.ops
                    ],
                    "chars_remaining": diff.chars_remaining,
                }
                
                # Apply diff to get corrected slots
                corrected_slots = self._adherence_service.apply_diff(
                    base_slots=prompt_slots,
                    diff=diff,
                    max_prompt_length=512,
                )
                
                # Persist attempt with diff
                self._persist_attempt(
                    shot_id=shot_id,
                    attempt_n=attempt_n,
                    prompt_text=current_prompt,
                    provider=provider,
                    adherence_score=score.adherence_score,
                    score_json=score_json,
                    diff_json=diff_json,
                )
                
                return {
                    "verdict": "correctable",
                    "adherence_score": score.adherence_score,
                    "should_retry": True,
                    "corrected_slots": corrected_slots,
                    "diff": diff,
                    "score": score,
                    "locked_seed": locked_seed,
                }
            
            except Exception as e:
                logger.error(
                    "DIFF_GENERATION_FAILED | shot=%s | attempt=%d | error=%s",
                    shot_id,
                    attempt_n,
                    e,
                )
                # Fall through to manual review
        
        # Default: manual review needed (or max attempts reached)
        self._persist_attempt(
            shot_id=shot_id,
            attempt_n=attempt_n,
            prompt_text=current_prompt,
            provider=provider,
            adherence_score=score.adherence_score,
            score_json=score_json,
        )
        
        reason = (
            "Max attempts reached"
            if attempt_n >= MAX_ATTEMPTS
            else "Score too low for auto-correction"
        )
        
        return {
            "verdict": "manual_review",
            "adherence_score": score.adherence_score,
            "should_retry": False,
            "score": score,
            "reason": reason,
        }


# Singleton instance
render_retry_service = RenderRetryService()
