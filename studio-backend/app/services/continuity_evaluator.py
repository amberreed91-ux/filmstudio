from typing import Any, Dict, List

from .film_memory import FilmMemory, EmotionalArcPoint, MotifRecord, UnresolvedTension


def _normalize_memory(film_memory: Any) -> FilmMemory:
    if isinstance(film_memory, FilmMemory):
        return film_memory
    return FilmMemory(motifs=[], emotional_arcs=[], unresolved_tensions=[])


def _scene_emotion(scene: Any) -> str:
    if not isinstance(scene, dict):
        return ""
    value = scene.get("dominant_emotion")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return ""


def evaluate_scene_continuity(
    current_scene: Any,
    previous_scenes: Any,
    film_memory: Any,
    iteration_impact: Any = None,
) -> Dict[str, Any]:
    memory = _normalize_memory(film_memory)
    score = 1.0
    issues: List[str] = []
    impact = iteration_impact if isinstance(iteration_impact, dict) else {}
    continuity_pressure = (
        impact.get("continuity_pressure").strip().lower()
        if isinstance(impact.get("continuity_pressure"), str)
        else "normal"
    )
    motif_strength = (
        impact.get("motif_strength").strip().lower()
        if isinstance(impact.get("motif_strength"), str)
        else "stable"
    )

    current_emotion = _scene_emotion(current_scene)
    prev_scenes = previous_scenes if isinstance(previous_scenes, list) else []
    prev_emotions = [
        _scene_emotion(scene)
        for scene in prev_scenes
        if _scene_emotion(scene)
    ]

    if current_emotion and len(prev_emotions) >= 2:
        last_two = prev_emotions[-2:]
        if all(emotion == current_emotion for emotion in last_two):
            score -= 0.35
            issues.append("Emotion repeats across consecutive scenes")

    unresolved_count = sum(
        1
        for tension in memory.unresolved_tensions
        if isinstance(tension, UnresolvedTension) and tension.resolved is False
    )
    if unresolved_count > 0:
        unresolved_penalty = min(0.25, unresolved_count * 0.08)
        if continuity_pressure == "strict":
            unresolved_penalty += 0.08
        score -= unresolved_penalty
        issues.append("Unresolved tensions persist across scenes")

    motif_inconsistency_count = sum(
        1
        for motif in memory.motifs
        if isinstance(motif, MotifRecord) and motif.evolution in {"repeated", "stagnant"}
    )
    if continuity_pressure == "strict" and motif_inconsistency_count > 0:
        score -= min(0.2, motif_inconsistency_count * 0.07)
        issues.append("Strict continuity mode penalizes motif inconsistencies")
    if motif_strength == "enhanced" and motif_inconsistency_count == 0 and len(memory.motifs) > 0:
        score += 0.05

    score = max(0.0, min(1.0, round(score, 3)))
    return {
        "continuity_score": score,
        "issues": issues,
    }


def evaluate_motif_evolution(film_memory: Any) -> Dict[str, Any]:
    memory = _normalize_memory(film_memory)

    motifs: List[Dict[str, str]] = []
    for motif in memory.motifs:
        if not isinstance(motif, MotifRecord):
            continue

        occurrences = motif.occurrences if isinstance(motif.occurrences, list) else []
        states = [
            entry.get("state", "unchanged")
            for entry in occurrences
            if isinstance(entry, dict)
        ]
        unchanged = len(states) > 0 and len(set(states)) == 1 and states[0] == "unchanged"

        if len(occurrences) >= 3 and unchanged:
            status = "stagnant"
        elif len(occurrences) >= 2 and unchanged:
            status = "repeated"
        elif len(occurrences) >= 2:
            status = "evolving"
        else:
            status = "introduced"

        motifs.append({"motif": motif.motif, "status": status})

    return {"motifs": motifs}


def evaluate_narrative_progression(film_memory: Any) -> Dict[str, Any]:
    memory = _normalize_memory(film_memory)
    arc_points = [
        point for point in memory.emotional_arcs if isinstance(point, EmotionalArcPoint)
    ]

    if len(arc_points) < 2:
        return {
            "progression_score": 0.8,
            "status": "improving",
        }

    intensities = [point.intensity for point in arc_points]
    emotions = [point.dominant_emotion for point in arc_points]

    deltas = [
        intensities[index] - intensities[index - 1]
        for index in range(1, len(intensities))
    ]
    all_flat = all(abs(delta) <= 0.05 for delta in deltas)
    all_same_emotion = len(set(emotions)) == 1

    if all_flat or all_same_emotion:
        return {
            "progression_score": 0.6,
            "status": "plateauing",
        }

    negative_deltas = sum(1 for delta in deltas if delta < -0.05)
    positive_deltas = sum(1 for delta in deltas if delta > 0.05)

    if negative_deltas > positive_deltas:
        return {
            "progression_score": 0.45,
            "status": "regressing",
        }

    return {
        "progression_score": 0.85,
        "status": "improving",
    }
