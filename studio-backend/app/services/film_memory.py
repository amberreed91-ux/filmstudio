from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class MotifRecord:
    motif: str
    first_seen_scene: str
    occurrences: list
    evolution: str


@dataclass(frozen=True)
class EmotionalArcPoint:
    scene_id: str
    dominant_emotion: str
    intensity: float


@dataclass(frozen=True)
class UnresolvedTension:
    tension: str
    introduced_in: str
    resolved: bool


@dataclass(frozen=True)
class FilmMemory:
    motifs: list = field(default_factory=list)
    emotional_arcs: list = field(default_factory=list)
    unresolved_tensions: list = field(default_factory=list)
    motif_state: dict = field(
        default_factory=lambda: {
            "intensity": 0.0,
            "forms": ["drawn", "appearing", "embedded", "transferred"],
            "current_form": "drawn",
        }
    )


def _to_film_memory(memory: Any) -> FilmMemory:
    if isinstance(memory, FilmMemory):
        return memory
    return FilmMemory(motifs=[], emotional_arcs=[], unresolved_tensions=[], motif_state={
        "intensity": 0.0,
        "forms": ["drawn", "appearing", "embedded", "transferred"],
        "current_form": "drawn",
    })


def _normalize_scene_id(scene_data: Any) -> str:
    if isinstance(scene_data, dict):
        scene_id = scene_data.get("scene_id")
        if isinstance(scene_id, str) and scene_id.strip():
            return scene_id.strip()
    return "unknown_scene"


def _normalize_motif_entries(scene_data: Any) -> List[Dict[str, str]]:
    if not isinstance(scene_data, dict):
        return []

    raw_motifs = scene_data.get("motifs")
    if not isinstance(raw_motifs, list):
        return []

    motifs: List[Dict[str, str]] = []
    for entry in raw_motifs:
        if isinstance(entry, dict):
            motif_value = entry.get("motif")
            if not isinstance(motif_value, str) or not motif_value.strip():
                continue
            state_value = entry.get("state")
            state = state_value.strip().lower() if isinstance(state_value, str) and state_value.strip() else "unchanged"
            motifs.append({"motif": motif_value.strip().lower(), "state": state})
            continue
        if isinstance(entry, str) and entry.strip():
            motifs.append({"motif": entry.strip().lower(), "state": "unchanged"})

    deduped: List[Dict[str, str]] = []
    seen = set()
    for motif in motifs:
        key = motif["motif"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(motif)
    return deduped


def _infer_emotion(scene_data: Any) -> str:
    if not isinstance(scene_data, dict):
        return "neutral"

    dominant = scene_data.get("dominant_emotion")
    if isinstance(dominant, str) and dominant.strip():
        return dominant.strip().lower()

    description = scene_data.get("description")
    if not isinstance(description, str):
        return "neutral"

    lowered = description.lower()
    if "tension" in lowered or "fear" in lowered or "panic" in lowered:
        return "tense"
    if "sad" in lowered or "grief" in lowered:
        return "sad"
    if "joy" in lowered or "relief" in lowered:
        return "hopeful"
    if "anger" in lowered or "furious" in lowered:
        return "angry"
    return "neutral"


def _infer_intensity(scene_data: Any, emotion: str) -> float:
    if isinstance(scene_data, dict):
        raw_intensity = scene_data.get("intensity")
        if isinstance(raw_intensity, (int, float)):
            return max(0.0, min(1.0, round(float(raw_intensity), 3)))

    defaults = {
        "tense": 0.75,
        "angry": 0.8,
        "sad": 0.45,
        "hopeful": 0.6,
        "neutral": 0.5,
    }
    return defaults.get(emotion, 0.5)


def _normalize_tensions(scene_data: Any) -> List[Dict[str, Any]]:
    if not isinstance(scene_data, dict):
        return []

    raw_tensions = scene_data.get("tensions")
    if not isinstance(raw_tensions, list):
        raw_tensions = scene_data.get("unresolved_tensions")
    if not isinstance(raw_tensions, list):
        return []

    tensions: List[Dict[str, Any]] = []
    for entry in raw_tensions:
        if isinstance(entry, dict):
            tension_value = entry.get("tension")
            if not isinstance(tension_value, str) or not tension_value.strip():
                continue
            resolved = entry.get("resolved") is True
            tensions.append(
                {
                    "tension": tension_value.strip().lower(),
                    "resolved": resolved,
                }
            )
            continue
        if isinstance(entry, str) and entry.strip():
            tensions.append({"tension": entry.strip().lower(), "resolved": False})
    return tensions


def _motif_evolution(occurrences: List[Dict[str, str]]) -> str:
    count = len(occurrences)
    if count == 0:
        return "introduced"
    states = [
        item.get("state", "unchanged")
        for item in occurrences
        if isinstance(item, dict)
    ]
    unchanged = len(states) > 0 and len(set(states)) == 1 and states[0] == "unchanged"
    if count >= 3 and unchanged:
        return "stagnant"
    if count >= 2 and unchanged:
        return "repeated"
    if count >= 2:
        return "evolving"
    return "introduced"


def update_motifs(memory: Any, scene_data: Any, iteration_impact: Any = None) -> FilmMemory:
    current = _to_film_memory(memory)
    scene_id = _normalize_scene_id(scene_data)
    motif_entries = _normalize_motif_entries(scene_data)

    motif_records = [
        motif if isinstance(motif, MotifRecord) else None
        for motif in current.motifs
    ]
    motif_records = [motif for motif in motif_records if motif is not None]

    updated: List[MotifRecord] = []
    for record in motif_records:
        matching = next(
            (entry for entry in motif_entries if entry["motif"] == record.motif),
            None,
        )
        if matching is None:
            updated.append(record)
            continue
        new_occurrences = list(record.occurrences) + [
            {"scene_id": scene_id, "state": matching.get("state", "unchanged")}
        ]
        updated.append(
            MotifRecord(
                motif=record.motif,
                first_seen_scene=record.first_seen_scene,
                occurrences=new_occurrences,
                evolution=_motif_evolution(new_occurrences),
            )
        )

    known_motifs = {record.motif for record in updated}
    for entry in motif_entries:
        motif = entry["motif"]
        if motif in known_motifs:
            continue
        occurrences = [{"scene_id": scene_id, "state": entry.get("state", "unchanged")}]
        updated.append(
            MotifRecord(
                motif=motif,
                first_seen_scene=scene_id,
                occurrences=occurrences,
                evolution=_motif_evolution(occurrences),
            )
        )

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

    normalized_updated: List[MotifRecord] = []
    for record in updated:
        if not isinstance(record, MotifRecord):
            continue
        evolution = record.evolution
        if continuity_pressure == "strict" and evolution in {"repeated", "stagnant"}:
            evolution = "stagnant"
        if motif_strength == "enhanced" and evolution == "repeated":
            evolution = "evolving"
        normalized_updated.append(
            MotifRecord(
                motif=record.motif,
                first_seen_scene=record.first_seen_scene,
                occurrences=list(record.occurrences),
                evolution=evolution,
            )
        )

    motif_state = current.motif_state if isinstance(current.motif_state, dict) else {}
    motif_forms = ["drawn", "appearing", "embedded", "transferred"]
    scene_index = None
    total_scenes = None
    if isinstance(scene_data, dict):
        raw_scene_index = scene_data.get("scene_index")
        raw_total_scenes = scene_data.get("total_scenes")
        if isinstance(raw_scene_index, int):
            scene_index = max(0, raw_scene_index)
        if isinstance(raw_total_scenes, int):
            total_scenes = max(0, raw_total_scenes)
    if total_scenes is None:
        total_scenes = max(1, len(normalized_updated))
    if scene_index is None:
        scene_index = max(0, min(total_scenes - 1, len(normalized_updated) - 1))

    progress_denominator = max(1, total_scenes - 1)
    progress_ratio = scene_index / progress_denominator
    if progress_ratio < 0.34:
        current_form = "drawn"
    elif progress_ratio < 0.67:
        current_form = "appearing"
    elif progress_ratio < 0.9:
        current_form = "embedded"
    else:
        current_form = "transferred"
    motif_state = {
        "intensity": round(max(0.0, min(1.0, progress_ratio)), 3),
        "forms": motif_forms,
        "current_form": current_form,
    }

    return FilmMemory(
        motifs=normalized_updated,
        emotional_arcs=list(current.emotional_arcs),
        unresolved_tensions=list(current.unresolved_tensions),
        motif_state=motif_state,
    )


def update_emotional_arc(memory: Any, scene_data: Any, iteration_impact: Any = None) -> FilmMemory:
    current = _to_film_memory(memory)
    scene_id = _normalize_scene_id(scene_data)
    dominant_emotion = _infer_emotion(scene_data)
    intensity = _infer_intensity(scene_data, dominant_emotion)

    impact = iteration_impact if isinstance(iteration_impact, dict) else {}
    tone_shift = (
        impact.get("tone_shift").strip().lower()
        if isinstance(impact.get("tone_shift"), str)
        else "none"
    )
    pacing_shift = (
        impact.get("pacing_shift").strip().lower()
        if isinstance(impact.get("pacing_shift"), str)
        else "none"
    )

    adjusted_emotion = dominant_emotion
    adjusted_intensity = intensity
    if tone_shift == "darker":
        if adjusted_emotion in {"neutral", "hopeful"}:
            adjusted_emotion = "tense"
        adjusted_intensity = max(0.0, min(1.0, round(adjusted_intensity + 0.1, 3)))
    if pacing_shift == "faster":
        adjusted_intensity = max(0.0, min(1.0, round(adjusted_intensity + 0.05, 3)))

    new_point = EmotionalArcPoint(
        scene_id=scene_id,
        dominant_emotion=adjusted_emotion,
        intensity=adjusted_intensity,
    )

    next_arcs = list(current.emotional_arcs) + [new_point]
    if pacing_shift == "faster" and len(next_arcs) >= 2:
        prev = next_arcs[-2]
        if isinstance(prev, EmotionalArcPoint) and prev.scene_id == new_point.scene_id:
            next_arcs.pop(-2)

    return FilmMemory(
        motifs=list(current.motifs),
        emotional_arcs=next_arcs,
        unresolved_tensions=list(current.unresolved_tensions),
        motif_state=dict(current.motif_state) if isinstance(current.motif_state, dict) else {
            "intensity": 0.0,
            "forms": ["drawn", "appearing", "embedded", "transferred"],
            "current_form": "drawn",
        },
    )


def update_unresolved_tensions(memory: Any, scene_data: Any, iteration_impact: Any = None) -> FilmMemory:
    current = _to_film_memory(memory)
    scene_id = _normalize_scene_id(scene_data)
    new_tensions = _normalize_tensions(scene_data)

    existing = [
        tension if isinstance(tension, UnresolvedTension) else None
        for tension in current.unresolved_tensions
    ]
    existing = [item for item in existing if item is not None]

    updated: List[UnresolvedTension] = []
    for record in existing:
        incoming = next(
            (entry for entry in new_tensions if entry.get("tension") == record.tension),
            None,
        )
        if incoming is None:
            updated.append(record)
            continue
        updated.append(
            UnresolvedTension(
                tension=record.tension,
                introduced_in=record.introduced_in,
                resolved=record.resolved or incoming.get("resolved") is True,
            )
        )

    known = {record.tension for record in updated}
    for entry in new_tensions:
        tension = entry.get("tension")
        if not isinstance(tension, str) or tension in known:
            continue
        updated.append(
            UnresolvedTension(
                tension=tension,
                introduced_in=scene_id,
                resolved=entry.get("resolved") is True,
            )
        )

    return FilmMemory(
        motifs=list(current.motifs),
        emotional_arcs=list(current.emotional_arcs),
        unresolved_tensions=updated,
        motif_state=dict(current.motif_state) if isinstance(current.motif_state, dict) else {
            "intensity": 0.0,
            "forms": ["drawn", "appearing", "embedded", "transferred"],
            "current_form": "drawn",
        },
    )


def film_memory_to_dict(memory: Any) -> Dict[str, Any]:
    normalized = _to_film_memory(memory)
    return asdict(normalized)
