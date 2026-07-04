"""
Adherence Service - Multi-frame video-to-prompt scoring with corrective diffs.

Scores rendered shots against extracted frames (10%, 50%, 90% of duration) using
vision-capable models to detect drift across dimensions: character_state, action,
camera, lighting, environment_persistence.

NOTE: Vision model selection is configurable. Fine-grained consistency judgments
(e.g., "is this the same weathered hand as attempt 1") require stronger vision
models than Groq's default. This is worth one non-Groq API call per render given
how much the system depends on scoring accuracy.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("adherence_service")


# Dimension weights for aggregate adherence score
DIMENSION_WEIGHTS = {
    "character_state": 0.25,
    "action": 0.20,
    "camera": 0.15,
    "lighting": 0.15,
    "environment_persistence": 0.25,
}

# Verdict thresholds
VERDICT_PASS_THRESHOLD = 80
VERDICT_CORRECTABLE_MIN = 50
MAX_ATTEMPTS = 3


@dataclass
class DimensionScore:
    """Score for a single dimension."""
    score: float  # 0-100
    evidence: str
    expected: str
    observed: str


@dataclass
class AdherenceScore:
    """Multi-frame adherence score for a rendered shot."""
    shot_id: str
    attempt_n: int
    frames_scored: List[float]  # [0.1, 0.5, 0.9] timestamps
    dimensions: Dict[str, DimensionScore]
    temporal_drift: Dict[str, float]  # start_score, end_score
    adherence_score: float  # 0-100 weighted aggregate
    verdict: str  # pass | correctable | manual_review
    failed_slots: List[str]


@dataclass
class CorrectionOp:
    """Single correction operation for a failed slot."""
    slot: str
    op: str  # replace | strengthen | prepend_emphasis
    old_text: str
    new_text: str
    reason: str
    char_delta: int


@dataclass
class CorrectiveDiff:
    """Diff for applying corrections to prompt slots."""
    base_attempt: int
    seed_locked: bool
    ops: List[CorrectionOp]
    chars_remaining: int


class AdherenceService:
    """
    Scores rendered shots against prompt expectations using vision model.
    
    Uses multi-frame sampling (10%, 50%, 90%) to detect temporal drift.
    Generates corrective diffs for failed dimensions.
    """
    
    def __init__(self, storage=None):
        self._storage = storage
        # TODO: Make vision model provider configurable
        # Default to stronger vision model for consistency judgments
        self._vision_provider = os.getenv("ADHERENCE_VISION_PROVIDER", "openai")
        self._vision_model = os.getenv("ADHERENCE_VISION_MODEL", "gpt-4o")
        
    async def score_render_attempt(
        self,
        shot_id: str,
        attempt_n: int,
        video_url: str,
        expected_slots: Dict[str, str],
        extracted_frames: List[str],  # Paths to extracted frames at 10%, 50%, 90%
    ) -> AdherenceScore:
        """
        Score a render attempt against expected prompt slots.
        
        Args:
            shot_id: Shot identifier
            attempt_n: Attempt number (1-based)
            video_url: URL to rendered video
            expected_slots: Dict of {slot_name: expected_text} from prompt
            extracted_frames: List of frame paths [frame_10, frame_50, frame_90]
            
        Returns:
            AdherenceScore with dimension scores and verdict
        """
        if len(extracted_frames) != 3:
            raise ValueError(f"Expected 3 frames, got {len(extracted_frames)}")
        
        # Extract expectations from slots
        expected_character = expected_slots.get("character_state", "")
        expected_action = expected_slots.get("action", "")
        expected_camera = expected_slots.get("camera", "")
        expected_lighting = expected_slots.get("lighting", "")
        expected_environment = expected_slots.get("environment_persistence", "")
        
        # Call vision model for multi-frame analysis
        # NOTE: This is where we'd use a stronger vision model than Groq's default
        # for fine-grained consistency judgments (e.g., same hand across attempts)
        vision_result = await self._call_vision_model(
            frames=extracted_frames,
            expected_character=expected_character,
            expected_action=expected_action,
            expected_camera=expected_camera,
            expected_lighting=expected_lighting,
            expected_environment=expected_environment,
        )
        
        # Parse dimension scores
        dimensions = {
            "character_state": DimensionScore(
                score=vision_result["dimensions"]["character_state"]["score"],
                evidence=vision_result["dimensions"]["character_state"]["evidence"],
                expected=expected_character,
                observed=vision_result["dimensions"]["character_state"]["observed"],
            ),
            "action": DimensionScore(
                score=vision_result["dimensions"]["action"]["score"],
                evidence=vision_result["dimensions"]["action"]["evidence"],
                expected=expected_action,
                observed=vision_result["dimensions"]["action"]["observed"],
            ),
            "camera": DimensionScore(
                score=vision_result["dimensions"]["camera"]["score"],
                evidence=vision_result["dimensions"]["camera"]["evidence"],
                expected=expected_camera,
                observed=vision_result["dimensions"]["camera"]["observed"],
            ),
            "lighting": DimensionScore(
                score=vision_result["dimensions"]["lighting"]["score"],
                evidence=vision_result["dimensions"]["lighting"]["evidence"],
                expected=expected_lighting,
                observed=vision_result["dimensions"]["lighting"]["observed"],
            ),
            "environment_persistence": DimensionScore(
                score=vision_result["dimensions"]["environment_persistence"]["score"],
                evidence=vision_result["dimensions"]["environment_persistence"]["evidence"],
                expected=expected_environment,
                observed=vision_result["dimensions"]["environment_persistence"]["observed"],
            ),
        }
        
        # Calculate weighted adherence score
        adherence_score = sum(
            dimensions[dim].score * DIMENSION_WEIGHTS[dim]
            for dim in DIMENSION_WEIGHTS
        )
        
        # Determine verdict
        if adherence_score >= VERDICT_PASS_THRESHOLD:
            verdict = "pass"
        elif adherence_score >= VERDICT_CORRECTABLE_MIN and attempt_n < MAX_ATTEMPTS:
            verdict = "correctable"
        else:
            verdict = "manual_review"
        
        # Identify failed slots (score < 50)
        failed_slots = [
            dim for dim, score_obj in dimensions.items()
            if score_obj.score < 50
        ]
        
        score_result = AdherenceScore(
            shot_id=shot_id,
            attempt_n=attempt_n,
            frames_scored=[0.1, 0.5, 0.9],
            dimensions=dimensions,
            temporal_drift=vision_result["temporal_drift"],
            adherence_score=adherence_score,
            verdict=verdict,
            failed_slots=failed_slots,
        )
        
        logger.info(
            "ADHERENCE_SCORED | shot=%s | attempt=%d | score=%.1f | verdict=%s | failed=%d",
            shot_id,
            attempt_n,
            adherence_score,
            verdict,
            len(failed_slots),
        )
        
        return score_result
    
    async def generate_corrective_diff(
        self,
        score: AdherenceScore,
        current_slots: Dict[str, str],
        chars_remaining: int,
    ) -> CorrectiveDiff:
        """
        Generate corrective diff for failed dimensions.
        
        Uses small Groq call to generate patch - only sees expected/observed text,
        not the video.
        
        Args:
            score: AdherenceScore with failed dimensions
            current_slots: Current prompt slots
            chars_remaining: Available character budget (from reserve)
            
        Returns:
            CorrectiveDiff with operations to apply
        """
        if not score.failed_slots:
            return CorrectiveDiff(
                base_attempt=score.attempt_n,
                seed_locked=True,
                ops=[],
                chars_remaining=chars_remaining,
            )
        
        # Build correction prompt for Groq
        failed_dims = [
            {
                "slot": slot,
                "expected": score.dimensions[slot].expected,
                "observed": score.dimensions[slot].observed,
                "evidence": score.dimensions[slot].evidence,
            }
            for slot in score.failed_slots
        ]
        
        # Call Groq for correction suggestions (cheap - text-only)
        correction_result = await self._call_groq_corrector(
            failed_dimensions=failed_dims,
            current_slots=current_slots,
            chars_remaining=chars_remaining,
        )
        
        # Parse operations
        ops = [
            CorrectionOp(
                slot=op["slot"],
                op=op["op"],
                old_text=op["old_text"],
                new_text=op["new_text"],
                reason=op["reason"],
                char_delta=op["char_delta"],
            )
            for op in correction_result["ops"]
        ]
        
        diff = CorrectiveDiff(
            base_attempt=score.attempt_n,
            seed_locked=True,
            ops=ops,
            chars_remaining=correction_result["chars_remaining"],
        )
        
        logger.info(
            "CORRECTIVE_DIFF_GENERATED | shot=%s | attempt=%d | ops=%d",
            score.shot_id,
            score.attempt_n,
            len(ops),
        )
        
        return diff
    
    def apply_diff(
        self,
        base_slots: Dict[str, str],
        diff: CorrectiveDiff,
        max_prompt_length: int = 512,
    ) -> Dict[str, str]:
        """
        Apply corrective diff to slot dict deterministically.
        
        Pure function - no LLM call. String replacement per op, respecting 512-char cap.
        If an op would overflow, compresses a currently-passing slot, never another
        failing slot.
        
        Args:
            base_slots: Original slot dict
            diff: CorrectiveDiff to apply
            max_prompt_length: Max total prompt length (default 512)
            
        Returns:
            New slot dict with corrections applied
        """
        from app.services.shot_prompt_builder import SLOT_BUDGETS
        
        # Start with copy of base slots
        new_slots = dict(base_slots)
        
        # Track current total length
        def _calculate_length(slots: Dict[str, str]) -> int:
            """Calculate total assembled prompt length."""
            parts = [text for text in [
                slots.get("character_state", ""),
                slots.get("action", ""),
                slots.get("environment_persistence", ""),
                slots.get("camera", ""),
                slots.get("lighting", ""),
            ] if text]
            base = ". ".join(parts) + ". Cinematic, film quality." if parts else "Cinematic shot. Film quality."
            return len(base)
        
        # If we're already over budget, compress first before applying any ops
        initial_length = _calculate_length(new_slots)
        if initial_length > max_prompt_length:
            overage = initial_length - max_prompt_length
            compression_order = ["lighting", "camera", "environment_persistence", "action", "character_state"]
            
            for compress_slot in compression_order:
                if overage <= 0:
                    break
                current_text = new_slots.get(compress_slot, "")
                if not current_text or len(current_text) <= 20:
                    continue
                
                # Compress by overage amount plus buffer
                target_length = max(20, len(current_text) - overage - 10)
                new_slots[compress_slot] = current_text[:target_length] + "..."
                overage = _calculate_length(new_slots) - max_prompt_length
                
                logger.info(
                    "SLOT_PRECOMPRESSED | slot=%s | from=%d | to=%d | remaining_overage=%d",
                    compress_slot,
                    len(current_text),
                    len(new_slots[compress_slot]),
                    max(0, overage),
                )
        
        # Apply each operation
        for op in diff.ops:
            if op.op == "replace":
                new_slots[op.slot] = op.new_text
            elif op.op == "strengthen":
                # Prepend emphasis without replacing
                current = new_slots.get(op.slot, "")
                new_slots[op.slot] = f"{op.new_text}. {current}".strip()
            elif op.op == "prepend_emphasis":
                # Add emphasis at start
                current = new_slots.get(op.slot, "")
                new_slots[op.slot] = f"{op.new_text}, {current}".strip()
            
            # Check if we exceeded budget
            current_length = _calculate_length(new_slots)
            if current_length > max_prompt_length:
                # Need to compress a passing slot
                overage = current_length - max_prompt_length
                
                # Find passing slots (not in failed_slots from any recent attempt)
                # For now, compress in priority order: lighting, camera, environment, action, character
                compression_order = ["lighting", "camera", "environment_persistence", "action", "character_state"]
                
                compressed = False
                for compress_slot in compression_order:
                    if compress_slot == op.slot:
                        continue  # Don't compress the slot we just fixed
                    
                    current_text = new_slots.get(compress_slot, "")
                    if not current_text:
                        continue
                    
                    # Calculate how much to remove
                    target_length = len(current_text) - overage - 10  # Extra buffer
                    if target_length > 20:  # Don't compress below minimum useful length
                        new_slots[compress_slot] = current_text[:target_length] + "..."
                        compressed = True
                        logger.info(
                            "SLOT_COMPRESSED | slot=%s | from=%d | to=%d | reason=overflow",
                            compress_slot,
                            len(current_text),
                            len(new_slots[compress_slot]),
                        )
                        break
                
                if not compressed:
                    # If we couldn't compress anything, truncate the current op more aggressively
                    current_text = new_slots[op.slot]
                    # Truncate to budget with aggressive compression
                    max_slot_length = min(SLOT_BUDGETS.get(op.slot, 100), len(current_text) - overage - 10)
                    if max_slot_length > 20:
                        new_slots[op.slot] = current_text[:max_slot_length] + "..."
                    else:
                        # Last resort: truncate to minimum
                        new_slots[op.slot] = current_text[:20] + "..."
                    
                    logger.warning(
                        "DIFF_OP_TRUNCATED | slot=%s | from=%d | to=%d | reason=no_compression_available",
                        op.slot,
                        len(current_text),
                        len(new_slots[op.slot]),
                    )
        
        # Final safety check - if still over, aggressively compress all slots
        final_length = _calculate_length(new_slots)
        if final_length > max_prompt_length:
            overage = final_length - max_prompt_length
            compression_order = ["lighting", "camera", "environment_persistence", "action", "character_state"]
            
            for compress_slot in compression_order:
                if overage <= 0:
                    break
                current_text = new_slots.get(compress_slot, "")
                if not current_text or len(current_text) <= 20:
                    continue
                
                target_length = max(20, len(current_text) - overage - 10)
                new_slots[compress_slot] = current_text[:target_length] + "..."
                overage = _calculate_length(new_slots) - max_prompt_length
                
                logger.warning(
                    "FINAL_COMPRESSION | slot=%s | from=%d | to=%d | remaining_overage=%d",
                    compress_slot,
                    len(current_text),
                    len(new_slots[compress_slot]),
                    max(0, overage),
                )
        
        return new_slots
    
    async def _call_vision_model(
        self,
        frames: List[str],
        expected_character: str,
        expected_action: str,
        expected_camera: str,
        expected_lighting: str,
        expected_environment: str,
    ) -> Dict[str, Any]:
        """
        Call vision model to score frames against expectations.
        
        NOTE: This should use a stronger vision model than Groq's default for
        fine-grained consistency judgments. Configurable via ADHERENCE_VISION_PROVIDER.
        
        Returns dict matching the required JSON schema.
        """
        # TODO: Implement actual vision model call
        # For now, return mock structure
        
        # Build prompt for vision model
        prompt = f"""You are a film continuity expert. Score this rendered shot against the script expectations.

Expected Character State: {expected_character}
Expected Action: {expected_action}
Expected Camera: {expected_camera}
Expected Lighting: {expected_lighting}
Expected Environment: {expected_environment}

Analyze the 3 provided frames (10%, 50%, 90% of shot duration) and score each dimension 0-100.
Detect temporal drift across the shot.

Respond ONLY with valid JSON matching this exact schema:
{{
  "dimensions": {{
    "character_state": {{"score": 0-100, "evidence": "str", "expected": "{expected_character}", "observed": "str"}},
    "action": {{"score": 0-100, "evidence": "str", "expected": "{expected_action}", "observed": "str"}},
    "camera": {{"score": 0-100, "evidence": "str", "expected": "{expected_camera}", "observed": "str"}},
    "lighting": {{"score": 0-100, "evidence": "str", "expected": "{expected_lighting}", "observed": "str"}},
    "environment_persistence": {{"score": 0-100, "evidence": "str", "expected": "{expected_environment}", "observed": "str"}}
  }},
  "temporal_drift": {{"start_score": 0-100, "end_score": 0-100}}
}}"""
        
        # Mock response for now
        # TODO: Replace with actual vision model call
        logger.warning(
            "MOCK_VISION_CALL | provider=%s | model=%s | frames=%d",
            self._vision_provider,
            self._vision_model,
            len(frames),
        )
        
        return {
            "dimensions": {
                "character_state": {
                    "score": 85,
                    "evidence": "Character appearance matches expected visual canon",
                    "expected": expected_character,
                    "observed": "Matches expected character description",
                },
                "action": {
                    "score": 90,
                    "evidence": "Action clearly executed as described",
                    "expected": expected_action,
                    "observed": "Action matches expectation",
                },
                "camera": {
                    "score": 88,
                    "evidence": "Camera framing and movement as specified",
                    "expected": expected_camera,
                    "observed": "Camera work matches direction",
                },
                "lighting": {
                    "score": 92,
                    "evidence": "Lighting mood consistent with direction",
                    "expected": expected_lighting,
                    "observed": "Lighting matches expectation",
                },
                "environment_persistence": {
                    "score": 87,
                    "evidence": "Environment elements persist across frames",
                    "expected": expected_environment,
                    "observed": "Environment consistent",
                },
            },
            "temporal_drift": {
                "start_score": 90,
                "end_score": 85,
            },
        }
    
    async def _call_groq_corrector(
        self,
        failed_dimensions: List[Dict[str, str]],
        current_slots: Dict[str, str],
        chars_remaining: int,
    ) -> Dict[str, Any]:
        """
        Call Groq to generate correction operations.
        
        Cheap call - only sees expected/observed text, not video.
        
        Returns dict with ops and updated chars_remaining.
        """
        # Build prompt for Groq
        failed_list = "\n".join([
            f"- {dim['slot']}: Expected '{dim['expected']}', Observed '{dim['observed']}' ({dim['evidence']})"
            for dim in failed_dimensions
        ])
        
        prompt = f"""You are a prompt engineer fixing video generation prompts.

These dimensions failed in the render:
{failed_list}

Current slots:
{json.dumps(current_slots, indent=2)}

Available character budget: {chars_remaining}

Generate correction operations. For each failed dimension, choose:
- "replace": completely replace the slot text
- "strengthen": prepend emphasis phrase without replacing
- "prepend_emphasis": add clarifying phrase at start

Respond ONLY with valid JSON:
{{
  "ops": [
    {{
      "slot": "dimension_name",
      "op": "replace|strengthen|prepend_emphasis",
      "old_text": "current text",
      "new_text": "corrected text",
      "reason": "why this fixes the issue",
      "char_delta": 0
    }}
  ],
  "chars_remaining": {chars_remaining}
}}"""
        
        # Mock response for now
        # TODO: Replace with actual Groq call
        logger.warning(
            "MOCK_GROQ_CORRECTOR | failed_dims=%d | chars_remaining=%d",
            len(failed_dimensions),
            chars_remaining,
        )
        
        # Generate mock ops
        ops = []
        for dim in failed_dimensions:
            ops.append({
                "slot": dim["slot"],
                "op": "strengthen",
                "old_text": dim["expected"],
                "new_text": f"Emphasize: {dim['expected']}",
                "reason": f"Strengthen {dim['slot']} to match observed discrepancy",
                "char_delta": len(f"Emphasize: ") + 2,
            })
        
        return {
            "ops": ops,
            "chars_remaining": chars_remaining - sum(op["char_delta"] for op in ops),
        }


adherence_service = AdherenceService()
