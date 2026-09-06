"""
Render Retry Service - Automated prompt adherence retry loop for Previs Bay.

STRATEGY: "best-of-N with fresh seeds" (from SEED_NON_DETERMINISM_FINDING.md)
Due to empirical evidence that seed locking does NOT guarantee reproducibility,
the retry strategy now:

1. Build a full corrected prompt (build_full_corrected_prompt) that restates
   all 5 slots — passing slots verbatim, failing slots corrected
2. Generate FRESH random seeds for each retry attempt (NOT locked)
3. Submit N parallel attempts with the corrected prompt but different seeds
4. Score all N attempts and select whichever scored highest

This avoids the trap of: lock seed → apply diff → re-render → hope for improvement
Instead: fresh seeds give us variety, best-of-N selects the best result

The old `evaluate_and_retry()` method is kept for backward compatibility but
the new `evaluate_and_select_best()` implements the redesigned strategy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.adherence_service import AdherenceService, adherence_service, DimensionScore, AdherenceScore, FullCorrectedPrompt
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService

logger = logging.getLogger("render_retry_service")

MAX_ATTEMPTS = 3
STUCK_SHOT_THRESHOLD = 5.0  # If score improves by < 5 points, stop (legacy)
BEST_OF_N_DEFAULT = 3  # Default number of parallel attempts for best-of-N strategy
AUTO_RETRY_DEFAULT = 2
ALL_SLOTS = [
    "character_state",
    "action",
    "environment_persistence",
    "camera",
    "lighting",
]


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

    @staticmethod
    def _dimension_label(slot: str) -> str:
        labels = {
            "character_state": "Character presence",
            "identity_continuity": "Character likeness",
            "action": "Action",
            "camera": "Camera language",
            "lighting": "Light and tone",
            "environment_persistence": "Setting continuity",
        }
        return labels.get(slot, slot.replace("_", " ").title())

    def build_advisory_note(self, score_json: Optional[Dict[str, Any]]) -> str:
        """Turn a structured adherence result into Studio Brain advisory language."""
        if not isinstance(score_json, dict):
            return ""

        dimensions = score_json.get("dimensions") or {}
        failed_slots = [
            str(slot)
            for slot in (score_json.get("failed_slots") or [])
            if isinstance(slot, str)
        ]
        if not failed_slots:
            return (
                "No prompt-adherence mismatch surfaced across the sampled frames; "
                "the blocking, setting, and tonal register stay close enough for review."
            )

        notes: list[str] = []
        for slot in failed_slots[:2]:
            dim = dimensions.get(slot) if isinstance(dimensions, dict) else None
            if not isinstance(dim, dict):
                continue
            observed = str(dim.get("observed") or "").strip()
            expected = str(dim.get("expected") or "").strip()
            label = self._dimension_label(slot)
            if observed and expected:
                notes.append(f"{label}: the frame reads as {observed}, while the shot asks for {expected}.")
            elif observed:
                notes.append(f"{label}: the frame reads as {observed}.")
            elif expected:
                notes.append(f"{label}: the shot asks for {expected}, but the frame does not make it legible.")

        if not notes:
            notes.append("The render drifts from the intended shot language in a way worth correcting before review.")

        if len(failed_slots) > 2:
            notes.append("The correction should stay focused; fix the clearest mismatch before widening the note.")

        return " ".join(notes)

    def _mismatch_description(self, score_json: Optional[Dict[str, Any]]) -> str:
        if not isinstance(score_json, dict):
            return ""
        failed_slots = score_json.get("failed_slots") or []
        dimensions = score_json.get("dimensions") or {}
        descriptions: list[str] = []
        for slot in failed_slots:
            dim = dimensions.get(slot) if isinstance(dimensions, dict) else None
            if isinstance(dim, dict):
                observed = str(dim.get("observed") or "").strip()
                expected = str(dim.get("expected") or "").strip()
                if observed and expected:
                    descriptions.append(f"{slot}: expected {expected}; observed {observed}")
                elif observed or expected:
                    descriptions.append(f"{slot}: {observed or expected}")
        return " | ".join(descriptions)

    async def record_render_attempt(
        self,
        project_id: str,
        shot_id: str,
        job_id: str,
        output_url: str,
        prompt: str,
        expected_slots: Optional[Dict[str, str]] = None,
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
            if self._video_asset_service:
                from app.models.video_assets import VideoAsset

                now = datetime.now().isoformat()
                self._video_asset_service._save_asset(VideoAsset(
                    asset_id=asset_id,
                    project_id=project_id,
                    source_type="local_file",
                    local_path=video_path,
                    title=f"Render attempt {attempt_number} for {shot_id}",
                    description="Downloaded provider output for adherence scoring",
                    file_size_bytes=Path(video_path).stat().st_size,
                    status="available",
                    created_at=now,
                    updated_at=now,
                    metadata={
                        "job_id": job_id,
                        "shot_id": shot_id,
                        "attempt_number": attempt_number,
                        "source_url": output_url,
                    },
                ))
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
                prompt_slots = expected_slots or {"description": prompt}
                
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
                advisory_note = self.build_advisory_note(score_json)
                score_json["advisory_note"] = advisory_note
                score_json["mismatch_description"] = self._mismatch_description(score_json)
                score_json["retry_number"] = max(attempt_number - 1, 0)
                score_json["outcome"] = (
                    "matched"
                    if not score.failed_slots
                    else ("correctable_mismatch" if score.verdict == "correctable" else score.verdict)
                )
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
            mismatch_description=score_json.get("mismatch_description") if score_json else None,
            retry_number=score_json.get("retry_number") if score_json else None,
            outcome=score_json.get("outcome") if score_json else None,
            advisory_note=score_json.get("advisory_note") if score_json else None,
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
        import shutil
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

        if video_url.startswith("/outputs/"):
            source_path = outputs_root / video_url.removeprefix("/outputs/")
            if not source_path.exists() or not source_path.is_file():
                raise ValueError(f"Generated output not found: {video_url}")
            local_path = renders_dir / source_path.name
            if source_path.resolve() != local_path.resolve():
                shutil.copy2(source_path, local_path)
            logger.info(
                "LOCAL_RENDER_VIDEO_REGISTERED | shot=%s | source=%s | local_path=%s",
                shot_id,
                source_path,
                local_path,
            )
            return str(local_path)
        
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
        mismatch_description: Optional[str] = None,
        retry_number: Optional[int] = None,
        outcome: Optional[str] = None,
        advisory_note: Optional[str] = None,
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

                if "mismatch_description" in available_columns and mismatch_description:
                    columns.append("mismatch_description")
                    values.append(mismatch_description)

                if "retry_number" in available_columns and retry_number is not None:
                    columns.append("retry_number")
                    values.append(int(retry_number))

                if "outcome" in available_columns and outcome:
                    columns.append("outcome")
                    values.append(outcome)

                if "advisory_note" in available_columns and advisory_note:
                    columns.append("advisory_note")
                    values.append(advisory_note)
                
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

    def _dropped_elements_for_shot(
        self,
        shot_id: str,
        project_id: str = "",
    ) -> Dict[str, List[str]]:
        """Phrasing that budget compression removed before the original render.

        The intent-fidelity check records what it cut (see
        intent_fidelity_service). Handing that to the correction path means a
        retry can put the director's own words back rather than inventing
        replacement text for something that was never wrong — it was only too
        long to fit.

        Returns {} when nothing was recorded, which leaves correction behaviour
        exactly as it was.
        """
        if not self._storage:
            return {}
        try:
            # Storage has no by-shot job accessor, so filter a scoped list.
            # The record lives on the render job rather than render_attempts,
            # because it is produced at prompt-assembly time, before an attempt
            # exists.
            #
            # Scoped by project: an unscoped fetch takes the most recent jobs
            # across every project, so on a busy install this shot's jobs can
            # fall outside the window and the restoration silently does nothing.
            jobs = [
                job
                for job in (
                    self._storage.list_jobs(project_id=project_id or None, limit=200) or []
                )
                if getattr(job, "shot_id", None) == shot_id
            ]
        except Exception:
            return {}

        # list_jobs returns newest-first. The render being corrected is the most
        # recent one for this shot, so take that record — not the oldest, which
        # would restore phrasing from a superseded assembly.
        for job in jobs:
            parameters = getattr(getattr(job, "input_payload", None), "parameters", None)
            if not isinstance(parameters, dict):
                continue
            record = parameters.get("intent_fidelity")
            if not isinstance(record, dict) or record.get("status") != "reduced":
                continue
            dropped: Dict[str, List[str]] = {}
            for slot, slot_report in (record.get("slots") or {}).items():
                if not isinstance(slot_report, dict):
                    continue
                phrases = [
                    str(item).strip()
                    for item in (slot_report.get("dropped_elements") or [])
                    if str(item or "").strip()
                ]
                if phrases:
                    dropped[str(slot)] = phrases
            if dropped:
                return dropped
        return {}

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


    # =========================================================================
    # NEW STRATEGY: "best-of-N with fresh seeds"
    # =========================================================================

    def _generate_fresh_seed(self) -> int:
        """
        Generate a fresh random seed for a render attempt.

        Based on SEED_NON_DETERMINISM_FINDING.md, seed locking does NOT guarantee
        reproducibility. Instead of locking a seed, we generate fresh random seeds
        for each attempt to get variety in the output generation.

        Returns:
            Random integer in Runway's valid range (1 to 2^31-1)
        """
        # Runway accepts 1 to 4294967294 (unsigned 32-bit), but we use signed 32-bit max
        # for simplicity and compatibility
        seed = int.from_bytes(os.urandom(4), byteorder="big", signed=False) % 2147483647
        seed = max(1, seed)  # Ensure minimum is 1 (Runway valid range starts at 1)
        logger.info(
            "FRESH_SEED_GENERATED | seed=%d",
            seed,
        )
        return seed

    def _select_best_attempt(
        self,
        scored_attempts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Select the highest-scoring attempt from a list of scored attempts.

        This is the core selection logic for the "best-of-N" strategy:
        instead of iterative correction on a single seed, we submit N attempts
        with different seeds and pick whichever scored best.

        Args:
            scored_attempts: List of dicts with attempt_n, adherence_score, seed, job_id

        Returns:
            The attempt dict with highest adherence_score, or None if empty list
        """
        if not scored_attempts:
            return None

        best = max(scored_attempts, key=lambda x: x.get("adherence_score", 0))

        logger.info(
            "BEST_ATTEMPT_SELECTED | attempt=%d | score=%.1f | seed=%d | total_attempts=%d",
            best.get("attempt_n"),
            best.get("adherence_score"),
            best.get("seed"),
            len(scored_attempts),
        )

        return best

    async def evaluate_and_select_best(
        self,
        shot_id: str,
        project_id: str,
        original_slots: Dict[str, str],
        max_attempts: int = BEST_OF_N_DEFAULT,
        submission_strategy: str = "best_of_n",
        poll_timeout_seconds: float = 300.0,
        source_job_id: Optional[str] = None,
        cascade_depth: int = 1,
    ) -> Dict[str, Any]:
        """
        Evaluate original attempt and submit N parallel retries with fresh seeds.

        REDONE STRATEGY (from SEED_NON_DETERMINISM_FINDING.md):
        1. Build a full corrected prompt (build_full_corrected_prompt) that restates
           all 5 slots — passing slots verbatim, failing slots corrected
        2. Generate FRESH random seeds for each retry attempt (NOT locked)
        3. Submit N parallel attempts with the corrected prompt but different seeds
        4. Score all N attempts and select whichever scored highest

        This avoids the trap of: lock seed → apply diff → re-render → hope for improvement
        Instead: fresh seeds give us variety, best-of-N selects the best result

        Args:
            shot_id: Shot identifier
            project_id: Project ID
            original_slots: Original prompt slots (all 5 dimensions)
            max_attempts: Number of parallel attempts to submit (default 3)
            submission_strategy: "best_of_n" or other strategies for future extension
            poll_timeout_seconds: Max time to wait for all attempts to complete

        Returns:
            Dict with:
                - strategy: "best_of_n"
                - best_attempt: The selected attempt (or None if all failed)
                - all_scored_attempts: List of all scored attempts
                - corrected_prompt: FullCorrectedPrompt used for all attempts
                - seeds_used: List of seeds that were generated
        """
        from app.services.render import render_service

        logger.info(
            "BEST_OF_N_RETRY_STARTED | shot=%s | project=%s | max_attempts=%d",
            shot_id,
            project_id,
            max_attempts,
        )

        # Step 1: Build the full corrected prompt
        # Note: We use a score reconstructed from the original attempt's known issues
        original_score = await self._reconstruct_original_score(shot_id, original_slots)

        if original_score is None:
            # No previous attempt to correct - just generate with fresh seeds
            full_prompt = FullCorrectedPrompt(
                base_attempt=0,
                seed_locked=False,
                slots=original_slots,
                provenance={slot: "original" for slot in original_slots},
                prompt=self._assemble_prompt_from_slots(original_slots),
                chars_remaining=max(0, 512 - len(self._assemble_prompt_from_slots(original_slots))),
                compressed_slots=[],
            )
        else:
            slot_order = self._reorder_slots_by_failure(original_score.dimensions)
            try:
                full_prompt = await self._adherence_service.build_full_corrected_prompt(
                    score=original_score,
                    current_slots=original_slots,
                    dropped_elements=self._dropped_elements_for_shot(shot_id, project_id),
                )
            except Exception as exc:
                logger.warning(
                    "FULL_CORRECTED_PROMPT_FALLBACK | shot=%s | cause=%s",
                    shot_id,
                    type(exc).__name__,
                )
                fallback_prompt = self._assemble_prompt_from_slots(
                    original_slots,
                    slot_order,
                )
                full_prompt = FullCorrectedPrompt(
                    base_attempt=original_score.attempt_n,
                    seed_locked=False,
                    slots=original_slots,
                    provenance={
                        slot: "carried_forward_after_corrector_failure"
                        for slot in original_slots
                    },
                    prompt=fallback_prompt,
                    chars_remaining=max(0, 512 - len(fallback_prompt)),
                    compressed_slots=[],
                )
            full_prompt.prompt = self._assemble_prompt_from_slots(
                full_prompt.slots,
                slot_order,
            )
            full_prompt.slot_order = slot_order
            full_prompt.reorder_reason = {
                slot: (
                    "moved_early_for_attempt_%d_failure_score_%s"
                    % (
                        original_score.attempt_n,
                        original_score.dimensions[slot].score
                        if slot in original_score.dimensions else "missing",
                    )
                )
                for slot in slot_order
                if slot in original_score.failed_slots
            }
            full_prompt.chars_remaining = max(0, 512 - len(full_prompt.prompt))

        logger.info(
            "FULL_CORRECTED_PROMPT_BUILT | strategy=%s | prompt_len=%d",
            submission_strategy,
            len(full_prompt.prompt),
        )

        # Step 2: Generate fresh seeds for each attempt
        seeds = [self._generate_fresh_seed() for _ in range(max_attempts)]

        # Step 3: Submit N parallel attempts with the corrected prompt
        jobs = []
        for i, seed in enumerate(seeds):
            try:
                job = render_service.create_job(
                    project_id=project_id,
                    shot_id=f"{shot_id}",
                    provider=render_service.get_default_provider(),
                    prompt=full_prompt.prompt,
                    parameters={
                        "seed": seed,
                        "prompt_slots": full_prompt.slots,
                        "slot_order": full_prompt.slot_order,
                        "reorder_reason": full_prompt.reorder_reason,
                        "retry_strategy": submission_strategy,
                        "adherence_retry_parent_job_id": source_job_id,
                        "adherence_retry_cascade_depth": cascade_depth,
                        "skip_character_injection": True,
                    },
                )
                submitted_job = await render_service.submit_job(job.id)
                jobs.append({
                    "job_id": job.id,
                    "seed": seed,
                    "status": "submitted",
                })
                logger.info(
                    "RETRY_JOB_SUBMITTED | attempt=%d | job=%s | seed=%d",
                    i + 1,
                    job.id,
                    seed,
                )
            except Exception as e:
                logger.error(
                    "RETRY_JOB_SUBMISSION_FAILED | attempt=%d | seed=%d | error=%s",
                    i + 1,
                    seed,
                    e,
                )

        # Step 4: Wait for all jobs to complete and score them
        # For now, return the structure - actual polling/scoring happens in submit scripts
        result = {
            "strategy": submission_strategy,
            "corrected_prompt": full_prompt,
            "seeds_used": seeds,
            "jobs_submitted": jobs,
            "all_scored_attempts": [],  # Will be populated after scoring
            "best_attempt": None,  # Will be set after scoring
        }

        logger.info(
            "BEST_OF_N_RETRY_COMPLETE | jobs_submitted=%d | seeds=%s",
            len(jobs),
            seeds,
        )

        return result

    def _assemble_prompt_from_slots(self, slots: Dict[str, str], order: Optional[List[str]] = None) -> str:
        """
        Assemble a prompt string from a slot dict (helper for non-correcting scenarios).

        Args:
            slots: Dict of slot_name -> text
            order: Optional list of slot names to determine assembly order.

        Returns:
            Assembled prompt string
        """
        slot_order = order or ALL_SLOTS
        parts = [
            slots.get(slot, "")
            for slot in slot_order
            if slots.get(slot, "")
        ]
        if parts:
            return ". ".join(parts) + ". Cinematic, film quality."
        return "Cinematic shot. Film quality."

    def _reorder_slots_by_failure(self, dimension_scores: Dict[str, DimensionScore]) -> List[str]:
        """
        Order prompt slots from weakest-scoring to strongest-scoring.

        Ties preserve ALL_SLOTS order, which keeps behavior stable across runs.
        Missing scores are treated as passing so unscored slots do not jump ahead
        of known failures.

        identity_continuity is a dimension without a slot of its own; the prompt
        text it depends on lives in character_state. So character_state is ordered
        by the weaker of the two — otherwise a shot whose blocking read fine but
        whose face drifted would leave character_state at the back of the prompt,
        where the provider weights it least (POSITIONAL_WEIGHTING_FINDING.md).
        """
        def _score_for(slot: str) -> float:
            entry = dimension_scores.get(slot)
            base = entry.score if entry is not None else 100
            if slot != "character_state":
                return base
            identity = dimension_scores.get("identity_continuity")
            if identity is None:
                return base
            return min(base, identity.score)

        return sorted(ALL_SLOTS, key=_score_for)

    async def _reconstruct_original_score(
        self,
        shot_id: str,
        original_slots: Dict[str, str],
    ) -> Optional[AdherenceScore]:
        """
        Reconstruct the original AdherenceScore from stored data.

        This looks up the previous attempt's score to determine which slots failed,
        so we can pass that to build_full_corrected_prompt.

        Args:
            shot_id: Shot identifier
            original_slots: Original prompt slots

        Returns:
            AdherenceScore if found, None otherwise
        """
        if not self._storage:
            return None

        try:
            with self._storage._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT score_json FROM render_attempts
                    WHERE shot_id = ? AND attempt_n = 1
                    """,
                    (shot_id,),
                )
                row = cursor.fetchone()
                if row and row[0]:
                    score_data = json.loads(row[0])
                    dims = {}
                    for dim_name, dim_data in score_data.get("dimensions", {}).items():
                        dims[dim_name] = DimensionScore(
                            score=dim_data.get("score", 0),
                            evidence=dim_data.get("evidence", ""),
                            expected=dim_data.get("expected", ""),
                            observed=dim_data.get("observed", ""),
                        )

                    return AdherenceScore(
                        shot_id=shot_id,
                        attempt_n=1,
                        frames_scored=score_data.get("frames_scored", [0.1, 0.5, 0.9]),
                        dimensions=dims,
                        temporal_drift=score_data.get("temporal_drift", {"start_score": 100, "end_score": 100}),
                        adherence_score=score_data.get("adherence_score", 0),
                        verdict=score_data.get("verdict", "manual_review"),
                        failed_slots=score_data.get("failed_slots", []),
                    )
        except Exception as e:
            logger.warning(
                "ORIGINAL_SCORE_RECONSTRUCTION_FAILED | shot=%s | error=%s",
                shot_id,
                e,
            )

        return None


# Singleton instance
render_retry_service = RenderRetryService()
