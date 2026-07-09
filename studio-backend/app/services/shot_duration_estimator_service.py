"""Shot-duration recommendation estimator.

Standalone, ADVISORY-ONLY estimator that surfaces how long a render SHOULD be
for a given shot, derived from the dialogue/script content of that shot's scene
- BEFORE rendering, not after.

This targets the root cause behind a known audio/video mismatch: the Runway
adapter renders a fixed-length clip (default 5s, see
``app/adapters/__init__.py``: ``parameters.get("duration") or 5``) with no
awareness of dialogue length. When dialogue is longer than the clip, the
mismatch is currently patched after the fact via ``freeze_last_frame`` in
``audio_pipeline_service``. This estimator surfaces the right number up front
so the mismatch can be avoided at submit time rather than frozen-frame patched
downstream.

The estimator does NOT modify any render behaviour. It only computes and
returns a recommended duration for human review. Wiring it into actual render
duration is an explicit, separate decision.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.services.audio_pipeline_service import _extract_dialogue_lines

logger = logging.getLogger(__name__)


# ── Named constants ─────────────────────────────────────────────────────────
# Speech pace in words-per-minute. These mirror the existing convention in
# ``dialogue_voice_service.build_dialogue_timing_metadata`` so the system
# speaks with one voice about spoken duration rather than inventing a second,
# divergent pace model.
SPEECH_WPM_BALANCED = 150   # average conversational spoken pace (wpm)
SPEECH_WPM_FAST = 180       # brisk / urgent delivery
SPEECH_WPM_SLOW = 120       # measured / heavy delivery

# Per-line buffer: a short breath/pause between consecutive dialogue lines.
# Mirrors dialogue_voice_service (+0.2s per line).
PER_LINE_BUFFER_SECONDS = 0.2

# Non-dialogue action padding: room for action, reaction, and pacing around
# the spoken content (a beat before the first line, a tail after the last).
# Deliberately small and additive so dialogue length remains the dominant
# signal - this is a recommendation, not a pacing director.
ACTION_PADDING_SECONDS = 1.5

# Runway Gen-3 viable clip-length bounds. The recommendation is clamped to
# this range so it stays actionable as a future render-duration input. The raw
# (unclamped) estimate is also returned so the true mismatch is visible.
MIN_RECOMMENDED_SECONDS = 5.0
MAX_RECOMMENDED_SECONDS = 10.0

# The current fixed default the Runway adapter falls back to when no duration
# is supplied. Surfaced alongside the recommendation so the gap is explicit.
CURRENT_DEFAULT_DURATION_SECONDS = 5.0


def _wpm_for_pacing(pacing: Optional[str]) -> int:
    """Map a pacing label to a words-per-minute value (balanced default)."""
    p = (pacing or "").strip().lower()
    if p == "fast":
        return SPEECH_WPM_FAST
    if p == "slow":
        return SPEECH_WPM_SLOW
    return SPEECH_WPM_BALANCED


def estimate_duration_from_dialogue(
    dialogue_lines: List[Dict[str, str]],
    pacing: Optional[str] = None,
) -> Dict[str, Any]:
    """Estimate shot duration from extracted dialogue lines.

    Formula (all constants named above, no magic numbers):

        speech_seconds = Σ ( max(1, word_count_i) / wpm * 60
                             + PER_LINE_BUFFER_SECONDS )
        estimated_seconds = speech_seconds + ACTION_PADDING_SECONDS
        recommended_seconds = clamp(estimated_seconds,
                                    MIN_RECOMMENDED_SECONDS,
                                    MAX_RECOMMENDED_SECONDS)

    For a shot with no dialogue, speech_seconds is 0, so the estimate is just
    the action padding - clamped up to the minimum viable clip length.

    Returns a dict with both the raw estimate and the clamped recommendation so
    the true dialogue/clip mismatch stays visible even when the raw estimate
    exceeds the provider's maximum clip length.
    """
    wpm = _wpm_for_pacing(pacing)
    word_count = 0
    speech_seconds = 0.0
    for line in dialogue_lines:
        text = str(line.get("text", "")).strip()
        wc = max(1, len(text.split()))
        word_count += wc
        speech_seconds += (wc / wpm) * 60.0 + PER_LINE_BUFFER_SECONDS

    estimated_seconds = speech_seconds + ACTION_PADDING_SECONDS
    recommended_seconds = max(
        MIN_RECOMMENDED_SECONDS,
        min(MAX_RECOMMENDED_SECONDS, estimated_seconds),
    )

    return {
        "dialogue_line_count": len(dialogue_lines),
        "dialogue_word_count": word_count,
        "speech_seconds": round(speech_seconds, 2),
        "estimated_seconds": round(estimated_seconds, 2),
        "recommended_seconds": round(recommended_seconds, 2),
        "current_default_seconds": CURRENT_DEFAULT_DURATION_SECONDS,
        "min_viable_seconds": MIN_RECOMMENDED_SECONDS,
        "max_viable_seconds": MAX_RECOMMENDED_SECONDS,
        "pacing": (pacing or "balanced").lower(),
        "speech_wpm": wpm,
        "exceeds_provider_max": estimated_seconds > MAX_RECOMMENDED_SECONDS,
    }


# ── Scene / shot resolution ─────────────────────────────────────────────────

_SCENE_ID_PATTERN = re.compile(r"scene_\d+")


def resolve_scene_id_for_shot(shot_id: str, summary: Dict[str, Any]) -> Optional[str]:
    """Resolve which scene a shot belongs to from the project execution summary.

    Strategy (first hit wins):
      1. Explicit shot->scene maps: ``previs_beat_shot_map`` and
         ``scene_sequence`` (both carry shot_id lists keyed by scene_id).
      2. Lexical: a ``scene_\\d+`` segment embedded in the shot_id
         (covers ``scene_002_shot_001`` and ``shot_scene_002_001``).
      3. Prefix: any scene_id that is a substring of the shot_id.
    """
    if not shot_id:
        return None

    # 1. Explicit maps (reverse lookup scene_id -> [shot_id]).
    for key in ("previs_beat_shot_map", "scene_sequence"):
        node = summary.get(key)
        if isinstance(node, dict):
            for scene_id, value in node.items():
                shot_ids = (
                    [b.get("shot_id") for b in value if isinstance(b, dict)]
                    if isinstance(value, list)
                    else (value if isinstance(value, list) else [])
                )
                if shot_id in [s for s in shot_ids if s]:
                    return scene_id
        elif isinstance(node, list):
            for entry in node:
                if not isinstance(entry, dict):
                    continue
                scene_id = entry.get("scene_id")
                shots = entry.get("shots")
                if scene_id and isinstance(shots, list) and shot_id in shots:
                    return scene_id

    # 2. Lexical scene_NNN segment.
    m = _SCENE_ID_PATTERN.search(shot_id)
    if m:
        return m.group(0)

    # 3. Prefix match against known scene_ids.
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    for scene in scenes:
        if isinstance(scene, dict):
            sid = scene.get("scene_id")
            if sid and isinstance(sid, str) and sid in shot_id:
                return sid

    return None


class ShotDurationEstimatorService:
    """Service-mediated estimator. Reads scene dialogue via storage, never
    touches render state. Advisory only."""

    def _load_project_dict(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load project as a plain dict, preferring the canonical JSON
        project_store and falling back to SQLite storage so projects that live
        only in SQLite still resolve."""
        try:
            from app.services.project_store import project_store
            project = project_store.get_project(project_id)
            if project and isinstance(project, dict):
                summary = project.get("execution_summary") or {}
                if isinstance(summary.get("scenes"), list) and summary["scenes"]:
                    return project
        except Exception as exc:
            logger.debug("project_store miss for %s: %s", project_id, exc)

        try:
            from app.data.storage import get_storage
            stored = get_storage().get_project(project_id)
            if stored is None:
                return None
            data = stored.model_dump(mode="json")
            if not isinstance(data.get("execution_summary"), dict):
                data["execution_summary"] = {}
            return data
        except Exception as exc:
            logger.warning("Could not load project %s from storage: %s", project_id, exc)
            return None

    def _scene_text(self, scene: Dict[str, Any]) -> str:
        """Pull the screenplay text for a scene from any of the fields the
        system writes it to."""
        for key in ("text", "content", "scene_text", "description", "intent"):
            value = scene.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def estimate_for_shot(
        self,
        project_id: str,
        shot_id: str,
        pacing: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Estimate and return a recommended render duration for a shot.

        Surfaces the dialogue excerpt and resolution trace so the number is
        auditable. Never mutates render state.
        """
        project = self._load_project_dict(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        scene_id = resolve_scene_id_for_shot(shot_id, summary)
        scene = next(
            (s for s in scenes if isinstance(s, dict) and s.get("scene_id") == scene_id),
            None,
        ) if scene_id else None

        if not scene:
            return {
                "project_id": project_id,
                "shot_id": shot_id,
                "scene_id": scene_id,
                "found": False,
                "advisory": (
                    f"No scene resolved for shot {shot_id}; cannot estimate "
                    "duration from dialogue."
                ),
                "current_default_seconds": CURRENT_DEFAULT_DURATION_SECONDS,
            }

        scene_text = self._scene_text(scene)
        scene_characters = scene.get("characters") if isinstance(scene.get("characters"), list) else None
        dialogue_lines = _extract_dialogue_lines(scene_text, characters=scene_characters)
        estimate = estimate_duration_from_dialogue(dialogue_lines, pacing=pacing)

        excerpt = (
            dialogue_lines[0]["text"][:120] if dialogue_lines else ""
        )

        return {
            "project_id": project_id,
            "shot_id": shot_id,
            "scene_id": scene_id,
            "found": True,
            "advisory_only": True,
            "dialogue_excerpt": excerpt,
            **estimate,
        }


shot_duration_estimator_service = ShotDurationEstimatorService()
