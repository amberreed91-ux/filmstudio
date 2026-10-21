from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# The template filler minted by earlier board builds when a scene carried no
# emotional/character signal. Stored board rows still contain it baked into
# ``rationale`` / ``shot_planning.rationale`` / the provider-neutral prompt
# tail, so the plan/manifest path must detect it rather than trust it.
# Newly minted rationale must never contain it (see _build_sentence).
GENERIC_FALLBACK_SENTENCE = "A beat that earns its place in the larger composition."

# Explicit empty state shown when a scene genuinely carries no importance
# signal. Displayed verbatim so an unset field can never read as content.
SCENE_IMPORTANCE_NOT_SET = "Scene importance not set."


def is_generic_fallback(text: Any) -> bool:
    """True when text carries the retired template-filler sentence."""
    return GENERIC_FALLBACK_SENTENCE.lower() in str(text or "").lower()


def strip_generic_fallback(text: Any) -> str:
    """Remove the retired filler sentence from (usually stored) text."""
    cleaned = re.sub(re.escape(GENERIC_FALLBACK_SENTENCE), "", str(text or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    return cleaned.strip()


def _first_sentence(text: str, limit: int = 240) -> str:
    """First sentence of free text, capped at a word boundary."""
    raw = re.split(r"[.!?\n]+", str(text or "").strip())[0].strip() if str(text or "").strip() else ""
    if not raw:
        return ""
    if len(raw) > limit:
        cut = raw[:limit].rsplit(" ", 1)[0].strip() or raw[:limit].strip()
        raw = cut
    return raw if raw.endswith((".", "!", "?")) else f"{raw}."


class ShotRationaleService:
    """Builds a one-sentence 'Why this shot matters' rationale from existing signals.

    Uses scene data, continuity context, scene intelligence, and render job
    status — no new API calls or LLM invocations needed.
    """

    def __init__(self, storage=None):
        self._storage = storage

    def get_rationale(
        self,
        project_id: str,
        scene_id: str,
        scene_data: Dict[str, Any],
        continuity_context: Optional[Dict[str, Any]] = None,
        scene_intent: Optional[Dict[str, Any]] = None,
        scene_position: Optional[int] = None,
        total_scenes: Optional[int] = None,
    ) -> Dict[str, Any]:
        sentence = self._build_sentence(
            scene_data=scene_data,
            continuity_context=continuity_context,
            scene_intent=scene_intent,
            scene_position=scene_position,
            total_scenes=total_scenes,
        )
        description = str(scene_data.get("description") or scene_data.get("text") or "").strip()
        return {
            "rationale": sentence,
            # Explicit empty state for plan surfaces: "set" when the sentence
            # carries real scene content, "not_set" when only the label (or
            # nothing) was available. UIs must render "not_set" verbatim
            # instead of substituting silent filler.
            "importance_state": "not_set" if SCENE_IMPORTANCE_NOT_SET in sentence else "set",
            "importance_source": (
                "description"
                if description and _first_sentence(description) in sentence
                else ("signals" if SCENE_IMPORTANCE_NOT_SET not in sentence else "none")
            ),
            "contains_generic_fallback": is_generic_fallback(sentence),
            "scene_context": {
                "scene_id": scene_id,
                "characters": scene_data.get("characters", []),
                "location": scene_data.get("location", ""),
                "emotional_tone": scene_data.get("emotional_tone", ""),
                "scene_heading": scene_data.get("heading", ""),
            },
            "emotional_context": {
                "emotional_register": (continuity_context or {}).get("emotional_register", ""),
                "tonal_direction": (continuity_context or {}).get("tonal_direction", ""),
                "active_motifs": (continuity_context or {}).get("active_motifs", []),
            },
        }

    def _build_sentence(
        self,
        scene_data: Dict[str, Any],
        continuity_context: Optional[Dict[str, Any]] = None,
        scene_intent: Optional[Dict[str, Any]] = None,
        scene_position: Optional[int] = None,
        total_scenes: Optional[int] = None,
    ) -> str:
        scene_id = str(scene_data.get("scene_id") or "").strip()
        emotional_tone = str(scene_data.get("emotional_tone") or "").strip().lower()
        location = str(scene_data.get("location") or "").strip()
        characters = scene_data.get("characters", [])
        if isinstance(characters, str):
            characters = [c.strip() for c in characters.split(",") if c.strip()]
        heading = str(scene_data.get("heading") or "").strip()
        description = str(scene_data.get("description") or scene_data.get("text") or "").strip()
        scene_name = str(scene_data.get("scene_name") or "").strip()
        # Stored scenes sometimes persist an empty cast as the literal string
        # "[]". That is absence, not a character named "[]".
        raw_characters = scene_data.get("characters", [])
        if isinstance(raw_characters, str) and raw_characters.strip().lower() in ("", "[]", "none", "null"):
            characters = []

        emotional_register = ""
        active_motifs: List[str] = []
        tonal_direction = ""
        if continuity_context:
            emotional_register = str(continuity_context.get("emotional_register") or "").strip()
            active_motifs = continuity_context.get("active_motifs", []) or []
            tonal_direction = str(continuity_context.get("tonal_direction") or "").strip()

        intent = ""
        if scene_intent:
            intent = str(scene_intent.get("intent") or "").strip()

        scene_label = scene_name or heading or f"Scene {scene_id}"

        if intent and characters:
            return (
                f"{intent} "
                f"A {emotional_tone or 'charged'} scene with {self._format_characters(characters)} at {location or 'this space'}, "
                f"grounded in {emotional_register or emotional_tone or 'its emotional core'}."
            )

        if characters and location and emotional_tone:
            verb = "take" if len(characters) != 1 else "takes"
            base = f"A {emotional_tone} scene at {location} where {self._format_characters(characters)} {verb} the frame"
            if emotional_register:
                base += f", carrying the {emotional_register} of the journey so far"
            if active_motifs:
                base += f" and weaving in the {active_motifs[0]} motif"
            base += "."
            return base

        if emotional_register or tonal_direction:
            base = f"This {scene_label} reads in {emotional_register or emotional_tone or 'a measured'} register"
            if tonal_direction:
                base += f", with the arc {tonal_direction}"
            if active_motifs:
                base += f" as the {active_motifs[0]} motif lingers"
            base += "."
            return base

        # The scene's own description IS its importance statement and must be
        # read before giving up: earlier builds ignored it (assigned but never
        # referenced), so described scenes fell through to template filler.
        first = _first_sentence(description)
        if first:
            return f"{scene_label}. {first}" if scene_label else first

        # No generic filler, ever: when the field is genuinely empty the plan
        # surfaces an explicit not-set state instead of silent filler.
        # Template sentences ("A beat that earns its place...") read as
        # provider-bound prompt text on the board path, so they must never be
        # minted here; use is_generic_fallback/strip_generic_fallback to
        # detect them in stored rows.
        if scene_label:
            return f"{scene_label}. {SCENE_IMPORTANCE_NOT_SET}"
        return SCENE_IMPORTANCE_NOT_SET

    def _format_characters(self, characters: List[str]) -> str:
        if not characters:
            return "the characters"
        if len(characters) == 1:
            return characters[0]
        if len(characters) == 2:
            return f"{characters[0]} and {characters[1]}"
        return f"{', '.join(characters[:-1])}, and {characters[-1]}"


shot_rationale_service = ShotRationaleService()
