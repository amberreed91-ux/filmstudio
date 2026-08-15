"""
Adherence Service - Multi-frame video-to-prompt scoring with corrective diffs.

Scores rendered shots against extracted frames (10%, 50%, 90% of duration) using
vision-capable models to detect drift across dimensions: character_state, action,
camera, lighting, environment_persistence.

NOTE: Vision model selection is configurable. Default is Qwen-VL through
DashScope. The prior Gemini path remains available only when explicitly selected
via ADHERENCE_VISION_PROVIDER.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from groq import Groq

logger = logging.getLogger("adherence_service")


# Dimension weights for aggregate adherence score.
#
# identity_continuity carried weight 0.0 until Aug 2026, which meant a shot where
# the character rendered as a visibly different person scored identically to one
# where they did not — and, because the verdict derives from this weighted
# aggregate, identity drift could never trigger a retry. It now carries real
# weight, taken from character_state (the two overlap: character_state covers
# pose/wardrobe/expression as described, identity_continuity covers "is this the
# same person").
DIMENSION_WEIGHTS = {
    "character_state": 0.15,
    "identity_continuity": 0.20,
    "action": 0.20,
    "camera": 0.15,
    "lighting": 0.10,
    "environment_persistence": 0.20,
}

# Verdict thresholds
VERDICT_PASS_THRESHOLD = 80
VERDICT_CORRECTABLE_MIN = 50
MAX_ATTEMPTS = 3

# Identity is not a dimension that should average out against good lighting: a
# face that reads as a different actor fails the shot no matter how well the rest
# scored. Any *real* identity score at or below this floor forces a correctable
# verdict regardless of the weighted aggregate.
IDENTITY_HARD_GATE_THRESHOLD = 65

# Marker written by _ensure_identity_continuity_dimension when the evaluator did
# not return a separate identity dimension and it was back-filled from
# character_state. Inferred scores must not drive the hard gate or failed_slots —
# they are not evidence about identity.
IDENTITY_INFERRED_MARKER = "inferred from character_state"


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


@dataclass
class FullCorrectedPrompt:
    """
    Full corrected prompt with all 5 slots restated and provenance tracking.

    Implements the full-prompt regeneration strategy from SEED_NON_DETERMINISM_FINDING.md.
    Instead of patching only failing slots via diff operations (which relies on the
    seed to preserve passing dimensions), this structure carries a COMPLETE prompt
    that explicitly restates all 5 slots:

    - Passing slots → carried forward VERBATIM (exact original text)
    - Failing slots → corrected by the Groq corrector

    The `provenance` dict records which slots were touched on each attempt:
    - "carried_forward" for verbatim passing slots
    - "corrected" for failing slots that were rewritten

    This allows render_attempts to show which slots were touched on each attempt.
    """
    base_attempt: int
    seed_locked: bool
    slots: Dict[str, str]  # Final slot dict (all 5 slots)
    provenance: Dict[str, str]  # slot -> "carried_forward" | "corrected"
    prompt: str  # Assembled prompt string (<=512 chars)
    chars_remaining: int
    compressed_slots: List[str]  # Slots that were compressed due to budget
    slot_order: List[str] | None = None
    reorder_reason: Dict[str, str] | None = None


class AdherenceService:
    """
    Scores rendered shots against prompt expectations using vision model.
    
    Uses multi-frame sampling (10%, 50%, 90%) to detect temporal drift.
    Generates corrective diffs for failed dimensions.
    """
    
    def __init__(self, storage=None):
        self._storage = storage
        self._vision_provider = os.getenv("ADHERENCE_VISION_PROVIDER", "qwen").strip().lower()
        default_model = (
            "gemini-2.5-flash"
            if self._vision_provider == "gemini"
            else "qwen-vl-max"
        )
        self._vision_model = os.getenv("ADHERENCE_VISION_MODEL", default_model).strip()
        
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
        expected_identity = expected_slots.get("identity_continuity", expected_character)
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
            expected_identity=expected_identity,
        )
        self._ensure_identity_continuity_dimension(
            vision_result,
            expected_identity=expected_identity,
        )
        
        # Parse dimension scores
        dimensions = {
            "character_state": DimensionScore(
                score=vision_result["dimensions"]["character_state"]["score"],
                evidence=vision_result["dimensions"]["character_state"]["evidence"],
                expected=expected_character,
                observed=vision_result["dimensions"]["character_state"]["observed"],
            ),
            "identity_continuity": DimensionScore(
                score=vision_result["dimensions"]["identity_continuity"]["score"],
                evidence=vision_result["dimensions"]["identity_continuity"]["evidence"],
                expected=expected_identity,
                observed=vision_result["dimensions"]["identity_continuity"]["observed"],
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

        # Identity hard gate — independent of the weighted aggregate.
        #
        # A shot can score well overall while the character reads as a different
        # person; averaging hides exactly the failure the director most needs
        # caught. If the evaluator actually looked at identity and scored it at or
        # below the floor, the shot cannot pass on the strength of other
        # dimensions.
        identity_dim = dimensions.get("identity_continuity")
        identity_gate_tripped = (
            identity_dim is not None
            and not self._identity_score_is_inferred(identity_dim)
            and identity_dim.score <= IDENTITY_HARD_GATE_THRESHOLD
        )
        if identity_gate_tripped and verdict == "pass":
            verdict = "correctable" if attempt_n < MAX_ATTEMPTS else "manual_review"
            logger.info(
                "ADHERENCE_IDENTITY_GATE | shot=%s | attempt=%d | identity=%.1f | "
                "aggregate=%.1f | verdict_overridden_to=%s",
                shot_id,
                attempt_n,
                identity_dim.score,
                adherence_score,
                verdict,
            )

        # Identify failed slots (score <= 70)
        # Changed from < 50 to align with correctable range (50-79)
        # Any dimension scoring 70 or below is a correction candidate
        failed_slots = [
            dim for dim, score_obj in dimensions.items()
            if score_obj.score <= 70
            and not (
                dim == "identity_continuity"
                and self._identity_score_is_inferred(score_obj)
            )
        ]

        # identity_continuity is a scoring dimension, not a prompt slot — the
        # correction paths iterate ALL_SLOTS, so an identity-only failure would
        # otherwise carry every slot forward verbatim and retry the exact same
        # prompt. character_state is the slot that actually carries identity text,
        # so route the correction there.
        if "identity_continuity" in failed_slots and "character_state" not in failed_slots:
            failed_slots.append("character_state")
            logger.info(
                "ADHERENCE_IDENTITY_ROUTED_TO_CHARACTER_STATE | shot=%s | attempt=%d",
                shot_id,
                attempt_n,
            )
        
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
                # ADD emphasis while preserving original, but only if new_text is truly additive.
                # If new_text appears to be a complete rewrite/paraphrase of the original content,
                # treat it as a replace instead to avoid redundancy.
                current = new_slots.get(op.slot, "").strip()
                if not current:
                    # Empty slot — just use new_text
                    new_slots[op.slot] = op.new_text.strip()
                elif current.lower() in op.new_text.lower():
                    # new_text already contains the original (case-insensitive) — use it as-is
                    new_slots[op.slot] = op.new_text.strip()
                else:
                    # Check if new_text is a paraphrase by comparing key content words
                    # If they share significant overlap, it's likely a rewrite, not an addition
                    import re
                    def _extract_content_words(text):
                        # Extract meaningful words (not punctuation or stopwords)
                        words = re.findall(r'\b\w{4,}\b', text.lower())  # 4+ char words
                        return set(words)
                    
                    current_words = _extract_content_words(current)
                    new_words = _extract_content_words(op.new_text)
                    
                    # If 60%+ of current words appear in new_text, it's a paraphrase
                    if current_words and len(current_words & new_words) / len(current_words) >= 0.6:
                        # Paraphrase detected - use new_text only
                        new_slots[op.slot] = op.new_text.strip()
                        logger.info(
                            "STRENGTHEN_AS_REPLACE | slot=%s | reason=paraphrase_detected | overlap=%d%%",
                            op.slot,
                            int(100 * len(current_words & new_words) / len(current_words))
                        )
                    else:
                        # Truly additive - prepend new emphasis
                        new_slots[op.slot] = f"{op.new_text}. {current}".strip()
            elif op.op == "prepend_emphasis":
                # Add emphasis at start, preserving original text exactly once.
                # The LLM may already include the original slot text in new_text
                # (it's instructed to "prescribe desired behavior"), so we check
                # for overlap to avoid appending the original a second time.
                current = new_slots.get(op.slot, "").strip()
                if not current:
                    # Empty slot — just use new_text (no trailing comma)
                    new_slots[op.slot] = op.new_text.strip()
                elif current.lower() in op.new_text.lower():
                    # new_text already contains the original (case-insensitive) — use it as-is
                    new_slots[op.slot] = op.new_text.strip()
                else:
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

    # ------------------------------------------------------------------
    # Full-prompt regeneration (SEED_NON_DETERMINISM_FINDING.md redesign)
    # ------------------------------------------------------------------

    # Compression priority for passing slots under budget pressure.
    # Lowest priority (compressed first) → highest priority (protected longest).
    # Failing slots are NEVER compressed.
    PASSING_SLOT_COMPRESSION_ORDER = [
        "lighting",
        "camera",
        "environment_persistence",
        "action",
        "character_state",
    ]

    # The 5 canonical slots, in assembly order (matches build_slotted_prompt)
    ALL_SLOTS = [
        "character_state",
        "action",
        "environment_persistence",
        "camera",
        "lighting",
    ]

    async def build_full_corrected_prompt(
        self,
        score: AdherenceScore,
        current_slots: Dict[str, str],
        max_prompt_length: int = 512,
    ) -> FullCorrectedPrompt:
        """
        Build a complete corrected prompt that restates ALL 5 slots.

        Implements the full-prompt regeneration strategy from
        SEED_NON_DETERMINISM_FINDING.md. Instead of patching only failing slots
        via diff operations (which relies on the seed to preserve passing
        dimensions), this method assembles a COMPLETE prompt that explicitly
        restates all 5 slots:

        - Passing slots → carried forward VERBATIM (exact original text)
        - Failing slots → corrected by the Groq corrector

        Design decisions (resolving the open questions from the finding):
        1. Verbatim: passing slots are copied character-for-character from
           current_slots. Paraphrasing was rejected because it already caused
           a semantic-duplication bug earlier tonight.
        2. Budget pressure: if the full restated prompt exceeds max_prompt_length,
           passing slots are compressed first (priority order: lighting < camera
           < environment < action < character). Failing slots are NEVER compressed.
        3. Provenance: each slot is tagged "carried_forward" or "corrected" in
           the provenance dict so render_attempts can show which slots were
           touched on each attempt.
        4. The Groq corrector receives ALL 5 slots (not just failed ones) and
           explicitly outputs all 5, marking each as carried_forward or corrected.
           We then OVERRIDE passing slots with verbatim original text regardless
           of what the LLM returned, to guarantee no paraphrasing drift.

        Args:
            score: AdherenceScore with per-dimension scores and failed_slots
            current_slots: Current prompt slots (the original successful text
                           for passing slots is preserved verbatim from here)
            max_prompt_length: Hard char limit for the assembled prompt (default 512)

        Returns:
            FullCorrectedPrompt with slots, provenance, assembled prompt, and
            compression metadata.
        """
        # Step 1: Call the full corrector with ALL 5 slots + pass/fail status
        corrector_result = await self._call_groq_full_corrector(
            score=score,
            current_slots=current_slots,
        )

        # Step 2: Assemble final slots with verbatim enforcement
        #   - Passing slots: VERBATIM from current_slots (ignore LLM's version)
        #   - Failing slots: use the corrector's corrected text
        final_slots: Dict[str, str] = {}
        provenance: Dict[str, str] = {}

        for slot in self.ALL_SLOTS:
            if slot in score.failed_slots:
                # Failing slot — use corrected text from the corrector
                corrected_text = corrector_result.get("slots", {}).get(slot, "")
                if not corrected_text:
                    # Fallback: if corrector didn't return this slot, keep original
                    corrected_text = current_slots.get(slot, "")
                final_slots[slot] = corrected_text
                provenance[slot] = "corrected"
            else:
                # Passing slot — VERBATIM from current_slots
                final_slots[slot] = current_slots.get(slot, "")
                provenance[slot] = "carried_forward"

        # Step 3: Assemble the prompt string
        prompt = self._assemble_prompt(final_slots)

        # Step 4: Budget enforcement — compress passing slots first if over limit
        compressed_slots: List[str] = []
        if len(prompt) > max_prompt_length:
            final_slots, prompt, compressed_slots = self._compress_for_budget(
                slots=final_slots,
                failed_slots=score.failed_slots,
                max_prompt_length=max_prompt_length,
            )

        chars_remaining = max_prompt_length - len(prompt)

        logger.info(
            "FULL_CORRECTED_PROMPT_BUILT | shot=%s | attempt=%d | "
            "carried_forward=%d | corrected=%d | compressed=%d | "
            "prompt_len=%d | chars_remaining=%d",
            score.shot_id,
            score.attempt_n,
            sum(1 for v in provenance.values() if v == "carried_forward"),
            sum(1 for v in provenance.values() if v == "corrected"),
            len(compressed_slots),
            len(prompt),
            chars_remaining,
        )

        return FullCorrectedPrompt(
            base_attempt=score.attempt_n,
            seed_locked=True,
            slots=final_slots,
            provenance=provenance,
            prompt=prompt,
            chars_remaining=chars_remaining,
            compressed_slots=compressed_slots,
        )

    def _assemble_prompt(self, slots: Dict[str, str]) -> str:
        """
        Assemble a prompt string from a slot dict.

        Follows the same assembly order as build_slotted_prompt:
        character_state, action, environment_persistence, camera, lighting.
        Joins with ". " and appends the cinematic suffix.
        """
        parts = [
            slots.get(slot, "")
            for slot in self.ALL_SLOTS
            if slots.get(slot, "")
        ]
        if parts:
            return ". ".join(parts) + ". Cinematic, film quality."
        return "Cinematic shot. Film quality."

    def _compress_for_budget(
        self,
        slots: Dict[str, str],
        failed_slots: List[str],
        max_prompt_length: int,
    ) -> tuple[Dict[str, str], str, List[str]]:
        """
        Compress passing slots to fit within the char budget.

        Compression priority (compressed first → protected last):
            lighting < camera < environment < action < character

        Failing slots are NEVER compressed — they contain the corrected content
        that we need to fix the render.

        Args:
            slots: Current slot dict
            failed_slots: List of failing slot names (protected from compression)
            max_prompt_length: Hard char limit

        Returns:
            Tuple of (compressed_slots_dict, assembled_prompt, list_of_compressed_slot_names)
        """
        compressed_slots = dict(slots)  # work on a copy
        compressed_names: List[str] = []

        prompt = self._assemble_prompt(compressed_slots)

        while len(prompt) > max_prompt_length:
            overage = len(prompt) - max_prompt_length
            compressed_something = False

            for slot in self.PASSING_SLOT_COMPRESSION_ORDER:
                # Never compress a failing slot
                if slot in failed_slots:
                    continue

                current_text = compressed_slots.get(slot, "")
                if not current_text or len(current_text) <= 20:
                    continue

                # Compress: remove overage + 10-char buffer, floor at 20 chars
                target_length = max(20, len(current_text) - overage - 10)
                if target_length >= len(current_text):
                    continue  # can't help

                compressed_slots[slot] = current_text[:target_length] + "..."
                compressed_names.append(slot)
                compressed_something = True

                logger.info(
                    "FULL_PROMPT_SLOT_COMPRESSED | slot=%s | from=%d | to=%d | "
                    "overage=%d",
                    slot,
                    len(current_text),
                    len(compressed_slots[slot]),
                    overage,
                )

                # Recalculate prompt length after this compression
                prompt = self._assemble_prompt(compressed_slots)
                if len(prompt) <= max_prompt_length:
                    break

            if not compressed_something:
                # No passing slot could be compressed further.
                # Last resort: hard-truncate the assembled prompt.
                logger.warning(
                    "FULL_PROMPT_HARD_TRUNCATE | prompt_len=%d | max=%d | "
                    "no_passing_slots_compressible",
                    len(prompt),
                    max_prompt_length,
                )
                prompt = prompt[: max_prompt_length - 3] + "..."
                break

        return compressed_slots, prompt, compressed_names

    async def _call_groq_full_corrector(
        self,
        score: AdherenceScore,
        current_slots: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Call Groq to generate corrected text for ALL 5 slots.

        Unlike _call_groq_corrector (which only sees failed dimensions), this
        call receives ALL 5 slots with their pass/fail status and per-dimension
        scores. The corrector outputs all 5 slots, marking each as
        "carried_forward" or "corrected".

        Note: We do NOT trust the LLM's text for passing slots — build_full_corrected_prompt()
        overrides passing slots with verbatim original text regardless of what
        the LLM returns. The LLM's carried_forward text is informational only.
        We DO trust the LLM's corrected text for failing slots.

        Returns dict with:
            - "slots": {slot_name: text} for all 5 slots
            - "provenance": {slot_name: "carried_forward" | "corrected"}
        """
        # Build per-slot status for the corrector
        slot_status_lines = []
        for slot in self.ALL_SLOTS:
            dim_score = score.dimensions.get(slot)
            current_text = current_slots.get(slot, "")
            if slot in score.failed_slots:
                status = "FAILED"
                evidence = dim_score.evidence if dim_score else ""
                observed = dim_score.observed if dim_score else ""
                slot_status_lines.append(
                    f"  {slot} [FAILED] (score={dim_score.score if dim_score else 0}): "
                    f'current="{current_text}" | observed="{observed}" | '
                    f"evidence={evidence}"
                )
            else:
                status = "PASSED"
                slot_status_lines.append(
                    f"  {slot} [PASSED] (score={dim_score.score if dim_score else 100}): "
                    f'current="{current_text}"'
                )

        slot_status = "\n".join(slot_status_lines)

        system_prompt = """You are a prompt engineer fixing video generation prompts using full-prompt regeneration.

You receive ALL 5 prompt slots with their pass/fail status. You must output ALL 5 slots in your response, marking each as "carried_forward" or "corrected".

Rules:
1. For PASSED slots: mark them "carried_forward" and echo the current text. (The system will use the verbatim original regardless, so this is informational.)
2. For FAILED slots: mark them "corrected" and provide new text that prescribes what you WANT to see.
   - BAD: "No specific character is present" or "character state was not observed"
   - GOOD: "People visible at human scale, faces and gestures clearly shown, interacting closely"
   - BAD: "No specific action was expected"
   - GOOD: "Vendors actively serving customers, people laughing and talking, continuous human activity"
3. For character/action consistency issues: prescribe specific visible human elements and continuous behavior.
4. For camera/lighting issues: strengthen the technical directive (e.g., "smooth push-in", "consistent soft lighting").
5. Keep each slot within its character budget:
   - character_state: 140 chars
   - action: 110 chars
   - environment_persistence: 100 chars
   - camera: 70 chars
   - lighting: 60 chars
6. Respond ONLY with valid JSON matching the exact schema.

Response schema:
{
  "slots": {
    "character_state": {"text": "...", "source": "carried_forward|corrected"},
    "action": {"text": "...", "source": "carried_forward|corrected"},
    "environment_persistence": {"text": "...", "source": "carried_forward|corrected"},
    "camera": {"text": "...", "source": "carried_forward|corrected"},
    "lighting": {"text": "...", "source": "carried_forward|corrected"}
  },
  "provenance": {
    "character_state": "carried_forward|corrected",
    "action": "carried_forward|corrected",
    "environment_persistence": "carried_forward|corrected",
    "camera": "carried_forward|corrected",
    "lighting": "carried_forward|corrected"
  }
}"""

        user_prompt = f"""Here are all 5 prompt slots with their render scoring status:

{slot_status}

Regenerate all 5 slots. For PASSED slots, mark "carried_forward" and echo the current text. For FAILED slots, mark "corrected" and write new text that prescribes the desired visual behavior."""

        DEFAULT_MAX_OUTPUT_TOKENS = 2048
        RETRY_MAX_OUTPUT_TOKENS = 4096

        def _sync_groq_call(max_tokens: int) -> tuple[str, str]:
            """Make synchronous Groq API call and return (response_text, finish_reason)."""
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            return content, finish_reason

        logger.info(
            "GROQ_FULL_CORRECTOR_CALL | failed=%d | total_slots=5 | max_output_tokens=%d",
            len(score.failed_slots),
            DEFAULT_MAX_OUTPUT_TOKENS,
        )

        try:
            response_text, finish_reason = await asyncio.to_thread(
                _sync_groq_call, DEFAULT_MAX_OUTPUT_TOKENS
            )

            if finish_reason == "length":
                logger.warning(
                    "GROQ_FULL_CORRECTOR_TRUNCATED | finish_reason=%s | retrying with %d tokens",
                    finish_reason,
                    RETRY_MAX_OUTPUT_TOKENS,
                )
                response_text, finish_reason = await asyncio.to_thread(
                    _sync_groq_call, RETRY_MAX_OUTPUT_TOKENS
                )

            result = json.loads(response_text)

            # Validate schema
            if "slots" not in result:
                raise ValueError("Missing 'slots' key in Groq full corrector response")

            # Flatten the nested structure into {slot: text}
            flattened: Dict[str, str] = {}
            for slot in self.ALL_SLOTS:
                slot_data = result["slots"].get(slot, {})
                if isinstance(slot_data, dict):
                    flattened[slot] = slot_data.get("text", "")
                else:
                    # Handle case where LLM returns plain string instead of dict
                    flattened[slot] = str(slot_data)

            # Use provenance from result if present, else derive from failed_slots
            provenance = result.get("provenance", {})
            if not provenance:
                provenance = {
                    slot: ("corrected" if slot in score.failed_slots else "carried_forward")
                    for slot in self.ALL_SLOTS
                }

            logger.info(
                "GROQ_FULL_CORRECTOR_SUCCESS | slots=%d | finish_reason=%s",
                len(flattened),
                finish_reason,
            )

            return {"slots": flattened, "provenance": provenance}

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Groq full corrector JSON response: {e}")
            logger.error(f"Raw response (first 500 chars): {response_text[:500]}")
            raise ValueError(f"Groq full corrector returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Groq full corrector API call failed: {e}")
            raise

    async def _call_vision_model(
        self,
        frames: List[str],
        expected_character: str,
        expected_action: str,
        expected_camera: str,
        expected_lighting: str,
        expected_environment: str,
        expected_identity: str = "",
    ) -> Dict[str, Any]:
        """
        Call vision model to score frames against expectations.
        
        Returns dict matching the required JSON schema.
        """
        if self._vision_provider in {"qwen", "qwen-vl", "dashscope"}:
            from app.services.vision.qwen_vision_service import QwenVisionService

            service = QwenVisionService(model=self._vision_model or "qwen-vl-max")
            result = await service.score_adherence(
                frames=frames,
                expected_character=expected_character,
                expected_action=expected_action,
                expected_camera=expected_camera,
                expected_lighting=expected_lighting,
                expected_environment=expected_environment,
            )
            self._ensure_identity_continuity_dimension(
                result,
                expected_identity=expected_identity or expected_character,
            )
            return result

        import google.generativeai as genai

        # Build prompt for vision model
        prompt = f"""You are a film continuity expert. Score this rendered shot against the script expectations.

Expected Character State: {expected_character}
Expected Identity Continuity: {expected_identity or expected_character}
Expected Action: {expected_action}
Expected Camera: {expected_camera}
Expected Lighting: {expected_lighting}
Expected Environment: {expected_environment}

Analyze the 3 provided frames (10%, 50%, 90% of shot duration) and score each dimension 0-100.
Identity continuity means whether recurring characters remain recognizably the same actor and character across face, body, silhouette, skin tone, hair, age presentation, wardrobe continuity, accessories, persistent props, and temporary marks when those traits are expected.
Detect temporal drift across the shot.

Respond ONLY with valid JSON matching this exact schema:
{{
  "dimensions": {{
    "character_state": {{"score": 0-100, "evidence": "str", "expected": "{expected_character}", "observed": "str"}},
    "identity_continuity": {{"score": 0-100, "evidence": "str", "expected": "{expected_identity or expected_character}", "observed": "str"}},
    "action": {{"score": 0-100, "evidence": "str", "expected": "{expected_action}", "observed": "str"}},
    "camera": {{"score": 0-100, "evidence": "str", "expected": "{expected_camera}", "observed": "str"}},
    "lighting": {{"score": 0-100, "evidence": "str", "expected": "{expected_lighting}", "observed": "str"}},
    "environment_persistence": {{"score": 0-100, "evidence": "str", "expected": "{expected_environment}", "observed": "str"}}
  }},
  "temporal_drift": {{"start_score": 0-100, "end_score": 0-100}}
}}"""
        
        # Load frames as PIL Image objects for Gemini
        import PIL.Image
        frame_images = []
        for frame_path in frames:
            try:
                img = PIL.Image.open(frame_path)
                frame_images.append(img)
            except Exception as e:
                logger.error(f"Failed to load frame {frame_path}: {e}")
                raise ValueError(f"Could not read frame: {frame_path}")
        
        # Build content parts for Gemini API
        content_parts = []
        for idx, img in enumerate(frame_images):
            content_parts.append(f"Frame {idx + 1} ({['10%', '50%', '90%'][idx]} of shot):")
            content_parts.append(img)
        
        # Add the analysis prompt after all images
        content_parts.append(prompt)
        
        # Call Gemini vision model (sync call in thread pool)
        # Default token budget is generous (4096) because a full 5-dimension
        # response with detailed evidence/expected/observed text on every field
        # can easily exceed the previous 2048 limit, causing mid-response
        # truncation and "Unterminated string" JSON parse errors.
        DEFAULT_MAX_OUTPUT_TOKENS = 4096
        RETRY_MAX_OUTPUT_TOKENS = 8192

        def _sync_vision_call(max_output_tokens: int):
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel(self._vision_model)
            response = model.generate_content(
                content_parts,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Lower temp for structured output
                    max_output_tokens=max_output_tokens,
                ),
            )
            return response

        def _extract_text(response) -> str:
            """Safely extract text from a Gemini response object."""
            try:
                return response.text
            except (AttributeError, ValueError) as e:
                # response.text can raise ValueError if no candidates have content
                logger.warning("VISION_RESPONSE_TEXT_UNAVAILABLE | error=%s", e)
                if response.candidates:
                    parts = response.candidates[0].content.parts
                    return "".join(p.text for p in parts if hasattr(p, "text"))
                raise

        def _finish_reason_name(response) -> str:
            """Extract a human-readable finish_reason from the response."""
            try:
                fr = response.candidates[0].finish_reason
                # finish_reason may be an enum (e.g., FinishReason.MAX_TOKENS) or int
                return str(fr)
            except (IndexError, AttributeError):
                return "UNKNOWN"

        def _is_truncated(response) -> bool:
            """Check if the response was truncated due to max_output_tokens."""
            reason = _finish_reason_name(response)
            # Gemini finish_reason values: STOP, MAX_TOKENS, SAFETY, RECITATION, OTHER
            # MAX_TOKENS (2) indicates the response was cut off at the token limit.
            # The str() representation may be the enum name ("FinishReason.MAX_TOKENS")
            # or just the integer value ("2") depending on the SDK version.
            reason_upper = reason.upper()
            return "MAX_TOKENS" in reason_upper or reason_upper == "2"

        logger.info(
            "VISION_API_CALL | provider=%s | model=%s | frames=%d | max_output_tokens=%d",
            self._vision_provider,
            self._vision_model,
            len(frames),
            DEFAULT_MAX_OUTPUT_TOKENS,
        )

        try:
            response = await asyncio.to_thread(_sync_vision_call, DEFAULT_MAX_OUTPUT_TOKENS)
            finish_reason = _finish_reason_name(response)

            # Check for truncation and retry once with a higher token limit
            if _is_truncated(response):
                logger.warning(
                    "VISION_RESPONSE_TRUNCATED | finish_reason=%s | max_output_tokens=%d | "
                    "retrying with %d tokens",
                    finish_reason,
                    DEFAULT_MAX_OUTPUT_TOKENS,
                    RETRY_MAX_OUTPUT_TOKENS,
                )
                response = await asyncio.to_thread(_sync_vision_call, RETRY_MAX_OUTPUT_TOKENS)
                finish_reason = _finish_reason_name(response)

                if _is_truncated(response):
                    logger.error(
                        "VISION_RESPONSE_STILL_TRUNCATED | finish_reason=%s | max_output_tokens=%d | "
                        "response may be incomplete",
                        finish_reason,
                        RETRY_MAX_OUTPUT_TOKENS,
                    )
            else:
                logger.info("VISION_FINISH_REASON | reason=%s", finish_reason)

            response_text = _extract_text(response)

            # Parse JSON response
            # Try to extract JSON from markdown code blocks if present
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            result = json.loads(response_text)

            # Validate schema
            required_keys = ["dimensions", "temporal_drift"]
            if not all(key in result for key in required_keys):
                raise ValueError(f"Missing required keys in vision response: {required_keys}")

            self._ensure_identity_continuity_dimension(
                result,
                expected_identity=expected_identity or expected_character,
            )

            required_dimensions = ["character_state", "identity_continuity", "action", "camera", "lighting", "environment_persistence"]
            if not all(dim in result["dimensions"] for dim in required_dimensions):
                raise ValueError(f"Missing required dimensions: {required_dimensions}")

            logger.info(
                "VISION_API_SUCCESS | frames=%d | response_length=%d | finish_reason=%s",
                len(frames),
                len(response_text),
                finish_reason,
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse vision model JSON response: {e}")
            logger.error(f"Raw response (first 500 chars): {response_text[:500]}")
            raise ValueError(f"Vision model returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Vision API call failed: {e}")
            raise

    @staticmethod
    def _identity_score_is_inferred(score_obj: DimensionScore) -> bool:
        """True when this identity score was back-filled from character_state.

        An inferred score is not evidence about identity — it must not drive the
        hard gate or land in failed_slots, or every evaluator that omits the
        dimension would look like identity drift.
        """
        evidence = str(getattr(score_obj, "evidence", "") or "").lower()
        return IDENTITY_INFERRED_MARKER in evidence

    @staticmethod
    def _ensure_identity_continuity_dimension(
        result: Dict[str, Any],
        *,
        expected_identity: str,
    ) -> None:
        dimensions = result.get("dimensions")
        if not isinstance(dimensions, dict) or "identity_continuity" in dimensions:
            return
        character_dim = dimensions.get("character_state") if isinstance(dimensions.get("character_state"), dict) else {}
        dimensions["identity_continuity"] = {
            "score": character_dim.get("score", 0),
            "evidence": (
                f"Identity continuity {IDENTITY_INFERRED_MARKER} because this evaluator "
                "did not return a separate visual identity dimension."
            ),
            "expected": expected_identity,
            "observed": character_dim.get("observed", ""),
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
        Uses Llama 3.3 70B for text-only reasoning over scoring gaps.
        
        Returns dict with ops and updated chars_remaining.
        """
        # Build prompt for Groq
        failed_list = "\n".join([
            f"- {dim['slot']}: {dim['evidence']}"
            for dim in failed_dimensions
        ])
        
        current_slots_formatted = "\n".join([
            f"  {key}: {value}"
            for key, value in current_slots.items()
        ])
        
        system_prompt = """You are a prompt engineer fixing video generation prompts. You analyze vision scoring evidence to understand what went wrong and generate precise correction operations to fix it.

Rules:
1. Only generate ops for failed dimensions
2. CRITICAL: Prescribe what you WANT to see, never describe what's missing or what went wrong. 
   - BAD: "No specific character is present" or "character state was not observed"
   - GOOD: "People visible at human scale, faces and gestures clearly shown, interacting closely"
   - BAD: "No specific action was expected"  
   - GOOD: "Vendors actively serving customers, people laughing and talking, continuous human activity"
3. For character/action consistency issues: prescribe specific visible human elements and continuous behavior
4. For camera/lighting issues: strengthen the technical directive (e.g., "smooth push-in", "consistent soft lighting")
5. Choose the right operation type:
   - "replace": completely replace the slot text (use when current text is empty or completely wrong, or when new_text is a complete rewrite)
   - "strengthen": ONLY use when you want to ADD emphasis while keeping original text. If your new_text already covers the same content as old_text (even paraphrased), use "replace" instead
   - "prepend_emphasis": add short clarifying phrase at start (use for continuity emphasis like "Throughout the shot,")
6. Calculate char_delta accurately (new_text length - old_text length)
7. Be specific in reason - explain what gap you're fixing
8. Respect character budget - don't exceed chars_remaining
9. Respond ONLY with valid JSON matching the exact schema

Response schema:
{
  "ops": [
    {
      "slot": "dimension_name or 'description' for monolithic prompts",
      "op": "replace|strengthen|prepend_emphasis",
      "old_text": "current text",
      "new_text": "corrected text that prescribes desired behavior",
      "reason": "why this fixes the issue",
      "char_delta": 0
    }
  ],
  "chars_remaining": <updated_budget>
}"""
        
        user_prompt = f"""These dimensions failed in the render:
{failed_list}

Current slots:
{current_slots_formatted}

Available character budget: {chars_remaining}

Generate correction operations to fix the failed dimensions. 

IMPORTANT: If the current slots only contain a single "description" slot (not separate character_state, action, etc.), 
then target "description" with your ops, not the dimension names. The dimension names are what FAILED, but the slot name 
is where you apply the fix. If you see structured slots (character_state, action, camera, etc.), then use those slot names."""

        # Default token budget for corrector - should be enough for typical correction JSON
        DEFAULT_MAX_OUTPUT_TOKENS = 2048
        RETRY_MAX_OUTPUT_TOKENS = 4096

        def _sync_groq_call(max_tokens: int) -> tuple[str, str]:
            """Make synchronous Groq API call and return (response_text, finish_reason)."""
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3,  # Lower temp for structured output
                response_format={"type": "json_object"},  # Force JSON mode
            )
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            return content, finish_reason

        logger.info(
            "GROQ_CORRECTOR_CALL | failed_dims=%d | chars_remaining=%d | max_output_tokens=%d",
            len(failed_dimensions),
            chars_remaining,
            DEFAULT_MAX_OUTPUT_TOKENS,
        )

        try:
            response_text, finish_reason = await asyncio.to_thread(
                _sync_groq_call, DEFAULT_MAX_OUTPUT_TOKENS
            )
            
            # Check for truncation (finish_reason will be "length" if truncated)
            if finish_reason == "length":
                logger.warning(
                    "GROQ_CORRECTOR_TRUNCATED | finish_reason=%s | max_output_tokens=%d | "
                    "retrying with %d tokens",
                    finish_reason,
                    DEFAULT_MAX_OUTPUT_TOKENS,
                    RETRY_MAX_OUTPUT_TOKENS,
                )
                response_text, finish_reason = await asyncio.to_thread(
                    _sync_groq_call, RETRY_MAX_OUTPUT_TOKENS
                )
                
                if finish_reason == "length":
                    logger.error(
                        "GROQ_CORRECTOR_STILL_TRUNCATED | finish_reason=%s | max_output_tokens=%d | "
                        "response may be incomplete",
                        finish_reason,
                        RETRY_MAX_OUTPUT_TOKENS,
                    )
            else:
                logger.info("GROQ_CORRECTOR_FINISH_REASON | reason=%s", finish_reason)

            # Parse JSON response
            result = json.loads(response_text)

            # Validate schema
            if "ops" not in result:
                raise ValueError("Missing 'ops' key in Groq corrector response")
            
            if "chars_remaining" not in result:
                # Calculate it ourselves if model didn't provide it
                total_delta = sum(op.get("char_delta", 0) for op in result["ops"])
                result["chars_remaining"] = chars_remaining - total_delta
                logger.warning(
                    "GROQ_CORRECTOR_MISSING_CHARS_REMAINING | calculated=%d",
                    result["chars_remaining"]
                )

            # Validate each op has required fields
            required_op_fields = ["slot", "op", "old_text", "new_text", "reason", "char_delta"]
            for idx, op in enumerate(result["ops"]):
                missing = [field for field in required_op_fields if field not in op]
                if missing:
                    raise ValueError(f"Op {idx} missing required fields: {missing}")
                
                # Validate op type
                if op["op"] not in ["replace", "strengthen", "prepend_emphasis"]:
                    raise ValueError(f"Invalid op type: {op['op']}")

            logger.info(
                "GROQ_CORRECTOR_SUCCESS | ops=%d | chars_remaining=%d | finish_reason=%s",
                len(result["ops"]),
                result["chars_remaining"],
                finish_reason,
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Groq corrector JSON response: {e}")
            logger.error(f"Raw response (first 500 chars): {response_text[:500]}")
            raise ValueError(f"Groq corrector returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Groq corrector API call failed: {e}")
            raise


adherence_service = AdherenceService()
