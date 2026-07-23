"""Shared utility functions for Studio backend."""

import re
from typing import Any, Dict, List


# Matches a scene_id token of the form ``scene_<digits>`` embedded anywhere
# in a shot_id. Both known shot_id formats carry this token:
#   * Old (manual):     scene_002_shot_001
#   * New (auto-split): shot_scene_002_001
_SCENE_ID_RE = re.compile(r"scene_\d+")
_SHOT_NUMBER_RE = re.compile(r"_(\d+)$")


def derive_scene_id_from_shot_id(shot_id: str) -> str:
    """Derive a ``scene_id`` from a ``shot_id``.

    Supports both shot_id formats produced by the pipeline:
      * Old (manual):       scene_002_shot_001  -> scene_002
      * New (auto-split):   shot_scene_002_001  -> scene_002

    The ``scene_<digits>`` token is located *anywhere* inside the shot_id so
    that future shot_id formats only need to update this single function.
    Falls back to the legacy first-two-segments heuristic when no scene token
    is found, and to the raw shot_id when it contains no underscore.
    """
    if not shot_id:
        return shot_id
    match = _SCENE_ID_RE.search(shot_id)
    if match:
        return match.group(0)
    return "_".join(shot_id.split("_")[:2]) if "_" in shot_id else shot_id


def derive_shot_number_from_shot_id(shot_id: str) -> int:
    """Return the trailing shot ordinal for manual and auto-split IDs."""
    if not shot_id:
        return 0
    match = _SHOT_NUMBER_RE.search(shot_id)
    return int(match.group(1)) if match else 0


def as_non_empty_string(value: Any) -> str:
    """Convert value to non-empty string, stripping whitespace."""
    text = str(value or "").strip()
    return text


def ensure_scene_fallback(summary: Dict[str, Any], concept: str) -> Dict[str, Any]:
    """Ensure scenes exist in summary, adding fallback if needed."""
    if not isinstance(summary, dict):
        summary = {}
    
    if not isinstance(summary.get("scenes"), list) or len(summary.get("scenes", [])) == 0:
        # Create fallback scene structure
        summary["scenes"] = [
            {
                "scene_id": "scene_001",
                "scene_title": concept[:100] if concept else "Opening Scene",
                "scene_description": concept[:500] if concept else "Main scene description",
                "scene_duration_seconds": 30,
                "scene_mood": "neutral",
                "scene_setting": "interior",
                "scene_characters": [],
                "scene_dialogue": "",
                "scene_action": "",
                "scene_transitions": {"in": "cut", "out": "cut"},
                "scene_notes": "Auto-generated fallback scene",
            }
        ]
    
    return summary


def scene_sequence_from_summary(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract scene sequence from summary for processing."""
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    shots = summary.get("shot_candidates") if isinstance(summary.get("shot_candidates"), list) else []
    by_scene: Dict[str, List[str]] = {}
    
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        scene_id = as_non_empty_string(shot.get("scene_id"))
        shot_id = as_non_empty_string(shot.get("shot_id"))
        if not scene_id or not shot_id:
            continue
        by_scene.setdefault(scene_id, []).append(shot_id)

    sequence: List[Dict[str, Any]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = as_non_empty_string(scene.get("scene_id"))
        if not scene_id:
            continue
        sequence.append({"scene_id": scene_id, "shots": by_scene.get(scene_id, [])})
    
    return sequence
