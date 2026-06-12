"""Shared utility functions for Studio backend."""

from typing import Any, Dict, List


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
