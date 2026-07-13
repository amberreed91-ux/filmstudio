"""
Standing Corrections Service — propose-then-confirm slot-level corrections.

Phase 1 (Propose): Reads repeated slot-failure patterns from render_attempts,
calls Groq to analyze them, and returns a candidate CorrectionProposal.
Nothing is written — this is read-only analysis.

Phase 2 (Confirm): Explicitly persists a previously-proposed CorrectionProposal
as a StandingCorrection row. This is the ONLY code path that creates live rows.

Phase 3 (Injection): At prompt-assembly time, queries active corrections whose
trigger_json matches the current shot context, and injects injection_text into
the relevant slots.

Phase 4 (Lifecycle): After a render's adherence score comes back, updates
hits/misses/confidence/status for every correction that was injected, and
auto-retires redundant corrections (5 consecutive passes without injection).
"""

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from groq import Groq

from app.data import get_storage
from app.models.standing_corrections import (
    CorrectionProposal,
    StandingCorrection,
)

logger = logging.getLogger(__name__)

# Required fields in the Groq correction-analysis JSON response
REQUIRED_PROPOSAL_FIELDS = [
    "trigger_json",
    "injection_text",
    "reasoning",
]

# ── In-memory tracking (non-persistent — reset on restart) ──────────────────
# Maps job_id -> dict with:
#   "applied": {slot_name: [injection_text, ...]}
#   "evaluated_ids": {correction_id, ...}  — corrections whose trigger matched shot_context
# Populated at injection time, consumed at lifecycle time.
_injected_corrections: dict[str, dict] = {}

# Maps correction_id -> int (consecutive passes where trigger matched but
# the correction was not injected AND the slot passed).
# Used for the 5-consecutive-pass redundancy retirement rule.
_consecutive_passes: dict[str, int] = {}


class StandingCorrectionsService:
    """Service for slot-level standing corrections.

    Storage is injected at startup via the lifespan handler (see main.py).
    """

    def __init__(self, storage=None):
        self._storage = storage

    # ── Phase 1: Propose (read-only Groq analysis) ──────────────────────────

    async def propose_correction(
        self,
        project_id: str,
        slot: str,
        min_failures: int = 2,
    ) -> CorrectionProposal | None:
        """Analyze repeated slot failures via Groq and return a proposal.

        Args:
            project_id: The project to analyze.
            slot: The prompt dimension slot to inspect (e.g. 'character_state').
            min_failures: Minimum failed attempts to trigger analysis.

        Returns:
            A CorrectionProposal if qualifying failures found, else None.
            Never writes anything to the database.
        """
        storage = self._storage or get_storage("sqlite")
        attempts = storage.list_render_attempts(
            project_id=project_id, limit=50,
        )

        # Filter to attempts where this slot failed
        failed: list[dict] = []
        for att in attempts:
            score_json = att.get("score_json") or {}
            dimensions = score_json.get("dimensions") or {}
            slot_data = dimensions.get(slot)
            if isinstance(slot_data, dict):
                score = slot_data.get("score", 100)
                evidence = slot_data.get("evidence", "")
                if score < 80:
                    failed.append({
                        "attempt_n": att.get("attempt_n"),
                        "shot_id": att.get("shot_id"),
                        "score": score,
                        "evidence": evidence,
                        "prompt_text": att.get("prompt_text", ""),
                    })

        if len(failed) < min_failures:
            logger.info(
                "STANDING_CORRECTION_INSUFFICIENT_FAILURES | project=%s | slot=%s | "
                "failed_count=%d | min_required=%d",
                project_id, slot, len(failed), min_failures,
            )
            return None

        logger.info(
            "STANDING_CORRECTION_PROPOSE | project=%s | slot=%s | failed_count=%d",
            project_id, slot, len(failed),
        )

        # Build the Groq prompt
        failures_text = json.dumps(failed, indent=2)
        system_prompt = (
            "You are a prompt-failure analyst for a video generation pipeline. "
            "A 'slot' is a dimension of a prompt (e.g. character_state, action, "
            "camera, lighting, environment_persistence). "
            "You will receive a list of render attempts where a specific slot scored "
            "below 80 — meaning the generated video did not match what the prompt "
            "asked for in that dimension.\n\n"
            "Your job: analyze the failure pattern and propose a corrective "
            "injection_text that, if injected into the prompt for this slot, would "
            "prevent the same class of failure in future renders.\n\n"
            "Rules:\n"
            "1. Identify what is COMMON across the failed attempts (same missing "
            "visual element, same vague phrasing, same type of evidence gap).\n"
            "2. Write injection_text as an additive phrase — something that "
            "strengthens or clarifies the existing prompt for that slot. It must "
            "be concise (under 200 characters) and prescriptive.\n"
            "3. trigger_json should contain a dict with keys describing the "
            "conditions under which this correction should activate (e.g. "
            "{\"trigger_evidence\": [\"missing person\", \"no faces visible\"], "
            "\"slot_name\": \"...\"}).\n"
            "4. reasoning should explain (in 1-3 sentences) what pattern you "
            "observed and why this injection fixes it.\n\n"
            "Respond ONLY with valid JSON matching this exact schema:\n"
            "{\n"
            '  "trigger_json": {"trigger_evidence": [...], "slot_name": "..."},\n'
            '  "injection_text": "...",\n'
            '  "reasoning": "..."\n'
            "}"
        )
        user_prompt = (
            f"Project: {project_id}\n"
            f"Slot: {slot}\n\n"
            f"Failed attempts:\n{failures_text}\n\n"
            "Generate a proposed correction."
        )

        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason

            logger.info(
                "STANDING_CORRECTION_GROQ_RESPONSE | finish_reason=%s | length=%d",
                finish_reason, len(response_text),
            )

            result = json.loads(response_text)

            # ── Defensive response-shape validation ─────────────────────────
            # Groq (like Gemini) has returned structurally inconsistent JSON.
            # Every field is validated for existence and type before use.
            # This block follows the same pattern as _call_vision_model in
            # adherence_service.py (lines 1084-1155).
            # ──────────────────────────────────────────────────────────────────

            # Top-level must be a dict (not list, string, etc.)
            if not isinstance(result, dict):
                raise ValueError(
                    f"Groq proposal response is type {type(result).__name__}, "
                    f"expected dict. Value: {result!r}"
                )

            for field in REQUIRED_PROPOSAL_FIELDS:
                if field not in result:
                    raise ValueError(
                        f"Groq proposal response missing required key '{field}'. "
                        f"Available keys: {list(result.keys())}"
                    )

            # Validate trigger_json is a dict
            if not isinstance(result["trigger_json"], dict):
                raise ValueError(
                    f"Groq returned 'trigger_json' as type "
                    f"{type(result['trigger_json']).__name__}, expected dict. "
                    f"Value: {result['trigger_json']!r}"
                )

            # Validate injection_text is a non-empty string
            if not isinstance(result["injection_text"], str):
                raise ValueError(
                    f"Groq returned 'injection_text' as type "
                    f"{type(result['injection_text']).__name__}, expected str. "
                    f"Value: {result['injection_text']!r}"
                )
            if not result["injection_text"].strip():
                raise ValueError(
                    "Groq returned empty 'injection_text'."
                )

            # Validate reasoning is a non-empty string
            if not isinstance(result["reasoning"], str):
                raise ValueError(
                    f"Groq returned 'reasoning' as type "
                    f"{type(result['reasoning']).__name__}, expected str. "
                    f"Value: {result['reasoning']!r}"
                )
            if not result["reasoning"].strip():
                raise ValueError(
                    "Groq returned empty 'reasoning'."
                )

            # ── Validation passed ──────────────────────────────────────────

            logger.info(
                "STANDING_CORRECTION_PROPOSAL_GENERATED | project=%s | slot=%s | "
                "injection_text_len=%d",
                project_id, slot, len(result["injection_text"]),
            )

            return CorrectionProposal(
                slot=slot,
                trigger_json=result["trigger_json"],
                injection_text=result["injection_text"],
                reasoning=result["reasoning"],
                qualifying_attempts=failed,
            )

        except json.JSONDecodeError as e:
            logger.error(
                "STANDING_CORRECTION_GROQ_JSON_ERROR | project=%s | slot=%s | error=%s",
                project_id, slot, e,
            )
            logger.error(
                "Raw response (first 500 chars): %s", response_text[:500]
            )
            raise ValueError(
                f"Groq returned invalid JSON: {e}"
            )
        except Exception as e:
            logger.error(
                "STANDING_CORRECTION_GROQ_ERROR | project=%s | slot=%s | error=%s",
                project_id, slot, e,
            )
            raise

    # ── Phase 3: Trigger Matching ─────────────────────────────────────────

    @staticmethod
    def match_value(trigger_value: Any, context_value: Any) -> bool:
        """Match a single trigger value against a context value.

        Over-broad prevention:
          - Key must exist in shot_context (enforced by the caller)
          - String triggers use case-insensitive substring (not regex)
          - Booleans require exact bool match (prevents 1/True coercion)

        Over-narrow prevention:
          - Lists use OR semantics: ANY element matching suffices
          - Strings: case-insensitive substring ("tense" matches
            "Tense atmosphere")
          - Context lists: string trigger searches ALL elements

        Rules:
          trigger=list     → ANY element match (OR within list)
          trigger=str      → case-insensitive substring of context
                                or any context list element
          trigger=bool     → exact type-and-value match
          trigger=number   → numeric equality (with str-to-float coercion
                                for context values that look numeric)
        """
        if isinstance(trigger_value, list):
            return any(
                StandingCorrectionsService.match_value(item, context_value)
                for item in trigger_value
            )

        if isinstance(trigger_value, str):
            if isinstance(context_value, str):
                return trigger_value.lower() in context_value.lower()
            if isinstance(context_value, (int, float)):
                return str(context_value).lower() == trigger_value.lower()
            if isinstance(context_value, list):
                return any(
                    trigger_value.lower() in str(item).lower()
                    for item in context_value
                )
            return str(trigger_value) == str(context_value)

        if isinstance(trigger_value, bool):
            return (
                isinstance(context_value, bool)
                and trigger_value == context_value
            )

        if isinstance(trigger_value, (int, float)):
            if isinstance(context_value, (int, float)):
                return trigger_value == context_value
            if isinstance(context_value, str):
                try:
                    return float(context_value) == float(trigger_value)
                except (ValueError, TypeError):
                    return False
            return False

        return trigger_value == context_value

    @staticmethod
    def trigger_matches_shot_context(
        trigger_json: dict[str, Any],
        shot_context: dict[str, Any],
    ) -> bool:
        """Check if ALL keys in trigger_json match the shot context.

        AND across keys (all must match). Empty trigger = always match
        (catch-all correction).

        Safety: if trigger_json has a key NOT IN shot_context, return False.
        This prevents corrections from firing on shots where the relevant
        metadata simply isn't available — the primary over-brought guard.
        """
        if not trigger_json:
            return True
        for key, trigger_value in trigger_json.items():
            if key not in shot_context:
                return False
            if not StandingCorrectionsService.match_value(
                trigger_value, shot_context[key]
            ):
                return False
        return True

    def _get_qualifying_corrections(
        self,
        project_id: str,
        slot_name: str,
        shot_context: dict[str, Any],
    ) -> list[dict]:
        """Get active + qualifying-probation corrections for a slot/context.

        - Active corrections: returned if trigger matches shot_context
        - Probation corrections: returned ONLY if trigger matches AND
          the immediately preceding attempt for this specific shot had
          this specific slot fail (score <= 70). This prevents re-injecting
          a correction that already proved ineffective for the same shot.
        """
        storage = self._storage or get_storage("sqlite")

        active = storage.list_standing_corrections(
            project_id=project_id, slot=slot_name, status="active",
        )
        probation = storage.list_standing_corrections(
            project_id=project_id, slot=slot_name, status="probation",
        )

        qualifying: list[dict] = []

        for corr in active:
            trigger = corr.get("trigger_json", {})
            if self.trigger_matches_shot_context(trigger, shot_context):
                qualifying.append(corr)

        shot_id = shot_context.get("shot_id", "")
        for corr in probation:
            trigger = corr.get("trigger_json", {})
            if not self.trigger_matches_shot_context(trigger, shot_context):
                continue
            last = self._get_most_recent_slot_score(
                project_id, shot_id, slot_name,
            )
            if last is not None and last <= 70:
                qualifying.append(corr)
                logger.info(
                    "STANDING_CORRECTION_PROBATION_REINJECT | "
                    "project=%s | slot=%s | shot=%s",
                    project_id, slot_name, shot_id,
                )

        return qualifying

    # ── Phase 3b: Injection ────────────────────────────────────────────────

    def inject_into_slots(
        self,
        project_id: str,
        slots: dict[str, str],
        shot_context: dict[str, Any],
        job_id: str | None = None,
    ) -> dict[str, list[str]]:
        """Query active corrections and inject matching text into slots.

        Args:
            project_id: Project to query corrections for.
            slots: Dict of slot_name -> slot_text (mutated in-place).
            shot_context: Dict of shot metadata for trigger matching.
            job_id: If provided, records injection for lifecycle tracking.

        Returns:
            Dict of {slot_name: [injection_text, ...]} for every slot
            that was modified. Empty dict if no corrections matched.
        """
        storage = self._storage or get_storage("sqlite")
        applied: dict[str, list[str]] = {}

        for slot_name in list(slots.keys()):
            slot_context = {
                **shot_context,
                "slot": slot_name,
                "slot_text": slots[slot_name] or "",
            }
            corrections = self._get_qualifying_corrections(
                project_id, slot_name, slot_context,
            )

            if not corrections:
                continue

            injection_texts = [c["injection_text"] for c in corrections]

            # Inject: prepend with ". " separator
            if slots[slot_name]:
                prefix = ". ".join(injection_texts)
                slots[slot_name] = f"{prefix}. {slots[slot_name]}"
            else:
                slots[slot_name] = ". ".join(injection_texts)

            # Update last_applied on each matched correction
            now = datetime.now().isoformat()
            for corr in corrections:
                corr["last_applied"] = now
                corr["trigger_json"] = corr.get("trigger_json", {})
                storage.save_standing_correction(corr)

            applied[slot_name] = injection_texts

            logger.info(
                "STANDING_CORRECTION_INJECTED | project=%s | slot=%s | "
                "count=%d | injections=%s",
                project_id, slot_name, len(injection_texts),
                injection_texts,
            )

        # ── Gather evaluated correction_ids for redundancy tracking ─────
        # Every active+probation correction whose trigger matches the base
        # shot_context is "evaluated" — even if it wasn't injected (e.g.
        # suppressed probation or active corrections that lost the cap/merge).
        # This prevents redundancy retirement from counting renders where
        # the correction's trigger conditions simply weren't met.
        evaluated_ids: set[str] = set()
        storage = self._storage or get_storage("sqlite")
        for status_filter in ("active", "probation"):
            all_corrs = storage.list_standing_corrections(
                project_id=project_id, status=status_filter,
            )
            for corr in all_corrs:
                trigger = corr.get("trigger_json", {})
                if self.trigger_matches_shot_context(trigger, shot_context):
                    evaluated_ids.add(corr["correction_id"])

        if job_id and (applied or evaluated_ids):
            _injected_corrections[job_id] = {
                "applied": applied,
                "evaluated_ids": evaluated_ids,
            }

        return applied

    # ── Phase 4: Lifecycle ─────────────────────────────────────────────────

    def record_render_outcome(
        self,
        project_id: str,
        shot_id: str,
        job_id: str,
        score_json: dict,
    ) -> None:
        """Update hits/misses/confidence/status after a render is scored.

        Called from the render quality check after adherence scoring completes.
        Looks up which corrections were injected for this job_id (from the
        in-memory _injected_corrections dict), then for each one:

          Slot passed → hits += 1, confidence = min(1.0, confidence + 0.05)
          Slot failed → misses += 1, confidence *= 0.8
          confidence < 0.4 → status = "probation"
          confidence < 0.2 → status = "retired"

        Always runs the redundancy check afterward — even if no corrections
        were injected — to detect the 5-consecutive-pass retirement condition.
        """
        storage = self._storage or get_storage("sqlite")
        dimensions = score_json.get("dimensions", {})
        tracking = _injected_corrections.pop(job_id, None) or {}
        if isinstance(tracking, dict) and "applied" in tracking:
            applied = tracking["applied"]
            evaluated_ids = tracking.get("evaluated_ids", set())
        else:
            # Backward compat: old format was direct slot->texts mapping
            applied = tracking
            evaluated_ids = set()

        for slot_name, injection_texts in applied.items():
            slot_data = dimensions.get(slot_name, {})
            score = slot_data.get("score", 100)
            slot_passed = score > 70

            all_corrections = storage.list_standing_corrections(
                project_id=project_id, slot=slot_name,
            )

            for corr in all_corrections:
                if corr.get("injection_text") not in injection_texts:
                    continue
                if corr.get("status") not in ("active", "probation"):
                    continue

                cid = corr["correction_id"]
                hits = corr.get("hits", 0)
                misses = corr.get("misses", 0)
                confidence = corr.get("confidence", 0.5)

                if slot_passed:
                    hits += 1
                    confidence = min(1.0, confidence + 0.05)
                else:
                    misses += 1
                    confidence = round(confidence * 0.8, 4)

                status = corr.get("status", "active")
                if confidence < 0.2:
                    status = "retired"
                elif confidence < 0.4 and status != "retired":
                    status = "probation"

                # Reset per-correction consecutive-pass counter
                _consecutive_passes.pop(cid, None)

                storage.save_standing_correction({
                    **corr,
                    "hits": hits,
                    "misses": misses,
                    "confidence": confidence,
                    "status": status,
                    "trigger_json": corr.get("trigger_json", {}),
                })

                logger.info(
                    "STANDING_CORRECTION_LIFECYCLE | correction=%s | "
                    "slot=%s | passed=%s | hits=%d | misses=%d | "
                    "confidence=%.3f | status=%s",
                    cid, slot_name, slot_passed, hits, misses,
                    confidence, status,
                )

        # Always run redundancy check — even when no corrections were
        # injected — to detect 5-consecutive-pass retirement.
        self._check_redundancy_retirement(project_id, applied, dimensions, evaluated_ids)

    def _check_redundancy_retirement(
        self,
        project_id: str,
        applied: dict[str, list[str]],
        dimensions: dict,
        evaluated_ids: set[str] | None = None,
    ) -> None:
        """Auto-retire corrections whose trigger keeps matching but the slot
        passes without them being injected — per-correction, not per-slot.

        Rule: for each correction whose trigger matched the shot_context
        (tracked in evaluated_ids at injection time), if it was NOT injected
        AND the slot passed, increment a per-correction counter. At 5
        consecutive such passes, retire that specific correction.

        Corrections whose trigger did NOT match the current shot_context are
        never counted — they weren't relevant to this render and we cannot
        conclude they are redundant.

        Theory: something else (retry loop, prompt improvement, Groq corrector)
        is now handling the issue — the standing correction is redundant.
        """
        storage = self._storage or get_storage("sqlite")
        evaluated_ids = evaluated_ids or set()

        # Query all active + probation corrections for the project
        all_corrs = storage.list_standing_corrections(
            project_id=project_id,
        )

        for corr in all_corrs:
            cid = corr["correction_id"]
            status = corr.get("status", "active")
            if status not in ("active", "probation"):
                continue

            slot_name = corr["slot"]
            slot_data = dimensions.get(slot_name, {})
            score = slot_data.get("score", 100)
            slot_passed = score > 70

            # Check if this correction was injected
            slot_texts = applied.get(slot_name, [])
            was_injected = corr.get("injection_text") in slot_texts

            if was_injected:
                # Correction was injected — reset its personal counter
                _consecutive_passes.pop(cid, None)
                continue

            if not slot_passed:
                # Slot failed — reset counter (chain broken)
                _consecutive_passes.pop(cid, None)
                continue

            if cid not in evaluated_ids:
                # Correction's trigger didn't match the shot context —
                # it wasn't relevant to this render, so don't count it.
                continue

            # Slot passed, trigger matched, correction NOT injected
            count = _consecutive_passes.get(cid, 0) + 1
            _consecutive_passes[cid] = count

            if count >= 5:
                storage.save_standing_correction({
                    **corr,
                    "status": "retired",
                    "trigger_json": corr.get("trigger_json", {}),
                })
                logger.info(
                    "STANDING_CORRECTION_RETIRED_REDUNDANT | "
                    "correction=%s | slot=%s | consecutive_passes=%d",
                    cid, slot_name, count,
                )
                _consecutive_passes.pop(cid, None)

    def _get_most_recent_slot_score(
        self,
        project_id: str,
        shot_id: str,
        slot_name: str,
    ) -> float | None:
        """Get the score for a slot from the most recent render attempt."""
        if not shot_id:
            return None
        storage = self._storage or get_storage("sqlite")
        attempts = storage.list_render_attempts(
            project_id=project_id, shot_id=shot_id, limit=1,
        )
        if not attempts:
            return None
        score_json = attempts[0].get("score_json") or {}
        dims = score_json.get("dimensions") or {}
        slot_data = dims.get(slot_name)
        if isinstance(slot_data, dict):
            return slot_data.get("score")
        return None

    # ── Piece 3: Cap Enforcement + Merge ───────────────────────────────────

    CAP_LIMIT = 3

    @staticmethod
    def _trigger_jaccard_similarity(
        trigger_a: dict[str, Any],
        trigger_b: dict[str, Any],
    ) -> float:
        """Compute Jaccard similarity of two trigger_json dicts.

        Keys match if StandingCorrectionsService.match_value() returns True
        in either direction (a matches b OR b matches a).

        score = matched_keys / total_keys (union of all keys in both triggers)

        Both empty → score = 1.0 (both are catch-all).
        One empty → score = 0.0 (catch-all vs specific are dissimilar).
        """
        if not trigger_a and not trigger_b:
            return 1.0
        if not trigger_a or not trigger_b:
            return 0.0

        all_keys = set(trigger_a.keys()) | set(trigger_b.keys())
        matched = 0
        for key in all_keys:
            val_a = trigger_a.get(key)
            val_b = trigger_b.get(key)
            if val_a is not None and val_b is not None:
                if (
                    StandingCorrectionsService.match_value(val_a, val_b)
                    or StandingCorrectionsService.match_value(val_b, val_a)
                ):
                    matched += 1

        return matched / len(all_keys)

    @staticmethod
    def _find_merge_candidates(
        active: list[dict],
    ) -> tuple[dict, dict]:
        """Find the two most similar active corrections among the list.

        Uses _trigger_jaccard_similarity to score every pair. Ties broken
        by lexicographic correction_id order.
        """
        if len(active) < 2:
            raise ValueError(
                f"Need at least 2 active corrections to merge, got {len(active)}"
            )

        best_pair: tuple[dict, dict] | None = None
        best_score = -1.0

        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                score = StandingCorrectionsService._trigger_jaccard_similarity(
                    active[i].get("trigger_json", {}),
                    active[j].get("trigger_json", {}),
                )
                if score > best_score or (
                    score == best_score
                    and best_pair is not None
                    and sorted([active[i]["correction_id"], active[j]["correction_id"]])
                    < sorted([best_pair[0]["correction_id"], best_pair[1]["correction_id"]])
                ):
                    best_score = score
                    best_pair = (active[i], active[j])

        if best_pair is None:
            best_pair = (active[0], active[1])

        return best_pair

    def _merge_corrections(
        self,
        project_id: str,
        slot: str,
        candidates: tuple[dict, dict],
    ) -> StandingCorrection:
        """Call Groq to merge two corrections and return the merged result.

        The merged correction is NOT persisted — the caller is responsible
        for saving it (and retiring originals with superseded_by).

        Defensive response validation follows the same pattern as
        propose_correction (check types, non-empty strings, etc.).
        """
        corr_a, corr_b = candidates

        merge_prompt = (
            f"You are a correction merger for a video generation pipeline. "
            f"Two standing corrections exist for the same slot ('{slot}') and "
            f"need to be merged into one combined correction.\n\n"
            f"Correction A:\n"
            f"  trigger_json: {json.dumps(corr_a.get('trigger_json', {}))}\n"
            f"  injection_text: {corr_a.get('injection_text', '')}\n"
            f"  reasoning: {corr_a.get('reasoning', 'N/A')}\n\n"
            f"Correction B:\n"
            f"  trigger_json: {json.dumps(corr_b.get('trigger_json', {}))}\n"
            f"  injection_text: {corr_b.get('injection_text', '')}\n"
            f"  reasoning: {corr_b.get('reasoning', 'N/A')}\n\n"
            f"Your job: produce a single merged correction that subsumes both. "
            f"The merged trigger_json should fire when EITHER original would "
            f"have fired (union of conditions). The merged injection_text "
            f"should combine both corrections into one concise instruction "
            f"(under 300 characters). The reasoning should explain why the "
            f"merge is coherent.\n\n"
            f"Respond ONLY with valid JSON matching this exact schema:\n"
            f"{{\n"
            f'  "trigger_json": {{...}},\n'
            f'  "injection_text": "...",\n'
            f'  "reasoning": "..."\n'
            f"}}"
        )

        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You merge standing corrections for a video generation "
                            "pipeline. Always produce a correction whose trigger_json "
                            "covers the union of both originals' conditions. The "
                            "injection_text must be a single concise instruction "
                            "combining both intents."
                        ),
                    },
                    {"role": "user", "content": merge_prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason

            logger.info(
                "STANDING_CORRECTION_MERGE_GROQ | finish_reason=%s | length=%d",
                finish_reason, len(response_text),
            )

            result = json.loads(response_text)

            if not isinstance(result, dict):
                raise ValueError(
                    f"Groq merge response is type {type(result).__name__}, "
                    f"expected dict. Value: {result!r}"
                )

            for field in REQUIRED_PROPOSAL_FIELDS:
                if field not in result:
                    raise ValueError(
                        f"Groq merge response missing required key '{field}'. "
                        f"Available keys: {list(result.keys())}"
                    )

            if not isinstance(result["trigger_json"], dict):
                raise ValueError(
                    f"Groq merge returned 'trigger_json' as type "
                    f"{type(result['trigger_json']).__name__}, expected dict. "
                    f"Value: {result['trigger_json']!r}"
                )

            if not isinstance(result["injection_text"], str):
                raise ValueError(
                    f"Groq merge returned 'injection_text' as type "
                    f"{type(result['injection_text']).__name__}, expected str. "
                    f"Value: {result['injection_text']!r}"
                )
            if not result["injection_text"].strip():
                raise ValueError("Groq merge returned empty 'injection_text'.")

            if not isinstance(result["reasoning"], str):
                raise ValueError(
                    f"Groq merge returned 'reasoning' as type "
                    f"{type(result['reasoning']).__name__}, expected str. "
                    f"Value: {result['reasoning']!r}"
                )
            if not result["reasoning"].strip():
                raise ValueError("Groq merge returned empty 'reasoning'.")

            merged = StandingCorrection(
                correction_id=f"sc_merged_{uuid4().hex[:24]}",
                project_id=project_id,
                slot=slot,
                trigger_json=result["trigger_json"],
                injection_text=result["injection_text"],
                confidence=max(
                    corr_a.get("confidence", 0.5),
                    corr_b.get("confidence", 0.5),
                ),
                hits=corr_a.get("hits", 0) + corr_b.get("hits", 0),
                misses=corr_a.get("misses", 0) + corr_b.get("misses", 0),
                last_applied=None,
                status="active",
            )

            logger.info(
                "STANDING_CORRECTION_MERGED | project=%s | slot=%s | "
                "merged_id=%s | a=%s | b=%s",
                project_id, slot, merged.correction_id,
                corr_a["correction_id"], corr_b["correction_id"],
            )

            return merged

        except json.JSONDecodeError as e:
            logger.error(
                "STANDING_CORRECTION_MERGE_JSON_ERROR | project=%s | slot=%s | error=%s",
                project_id, slot, e,
            )
            raise ValueError(f"Groq merge returned invalid JSON: {e}")
        except Exception as e:
            logger.error(
                "STANDING_CORRECTION_MERGE_ERROR | project=%s | slot=%s | error=%s",
                project_id, slot, e,
            )
            raise

    # ── Phase 2: Confirm (explicit write, the ONLY persistence path) ────────

    def confirm_correction(
        self,
        project_id: str,
        proposal: CorrectionProposal,
    ) -> StandingCorrection:
        """Persist a previously-proposed CorrectionProposal.

        This is the ONLY code path that creates a StandingCorrection row.
        There is no auto-promotion, no background job, no hook from the
        propose endpoint, and no middleware that calls this implicitly.

        New rows always start with:
          - status = "active"
          - confidence = 0.5 (neutral — hasn't proven itself yet)
          - hits = 0
          - misses = 0

        Cap enforcement (Piece 3): if the slot already has 3 active corrections,
        the two most similar are merged via Groq, originals are retired with
        superseded_by, and the merged correction is persisted alongside the
        proposed correction — keeping the total at exactly 3 active.
        """
        storage = self._storage or get_storage("sqlite")

        # ── Cap check: merge if at limit ───────────────────────────────────
        active = storage.list_standing_corrections(
            project_id=project_id, slot=proposal.slot, status="active",
        )

        if len(active) >= self.CAP_LIMIT:
            logger.info(
                "STANDING_CORRECTION_CAP_REACHED | project=%s | slot=%s | "
                "active_count=%d | limit=%d",
                project_id, proposal.slot, len(active), self.CAP_LIMIT,
            )

            # Include the new proposal as a merge candidate alongside the
            # 3 existing actives. This ensures a near-identical proposal
            # gets folded into a merge instead of creating a duplicate row.
            proposal_tag = f"__proposal_{uuid4().hex[:12]}__"
            proposal_as_dict = {
                "correction_id": proposal_tag,
                "trigger_json": proposal.trigger_json,
                "injection_text": proposal.injection_text,
            }
            candidates_pool = active + [proposal_as_dict]
            candidates = self._find_merge_candidates(candidates_pool)
            merged = self._merge_corrections(
                project_id, proposal.slot, candidates,
            )

            # Retire originals with superseded_by trace
            merged_id = merged.correction_id
            for corr in candidates:
                if corr["correction_id"] == proposal_tag:
                    continue  # proposal dict isn't a stored correction
                corr["status"] = "retired"
                corr["superseded_by"] = merged_id
                corr["trigger_json"] = corr.get("trigger_json", {})
                storage.save_standing_correction(corr)
                logger.info(
                    "STANDING_CORRECTION_RETIRED_MERGE | correction=%s | "
                    "superseded_by=%s",
                    corr["correction_id"], merged_id,
                )

            # Persist merged correction
            storage.save_standing_correction(merged.model_dump(mode="json"))

            logger.info(
                "STANDING_CORRECTION_MERGE_PERSISTED | project=%s | slot=%s | "
                "merged_id=%s",
                project_id, proposal.slot, merged_id,
            )

            # If the proposal was one of the merge candidates, don't persist
            # it separately — it was already folded into the merged correction.
            proposal_was_merged = any(
                c["correction_id"] == proposal_tag for c in candidates
            )
            if proposal_was_merged:
                return merged

        # ── Persist the proposed correction ─────────────────────────────────
        correction = StandingCorrection(
            correction_id=f"sc_{uuid4().hex[:24]}",
            project_id=project_id,
            slot=proposal.slot,
            trigger_json=proposal.trigger_json,
            injection_text=proposal.injection_text,
            confidence=0.5,
            hits=0,
            misses=0,
            last_applied=None,
            status="active",
        )

        saved = storage.save_standing_correction(correction.model_dump(mode="json"))
        if not saved:
            raise RuntimeError(
                f"Failed to persist standing correction for project={project_id} "
                f"slot={proposal.slot}"
            )

        logger.info(
            "STANDING_CORRECTION_CONFIRMED | project=%s | correction_id=%s | slot=%s",
            project_id, correction.correction_id, correction.slot,
        )

        return correction


standing_corrections_service = StandingCorrectionsService()
