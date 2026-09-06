from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from app.services.character_name_matching import text_mentions_character


_SUPPORTED_SOURCE_TYPES = {"bible", "creative_spine"}
_SLOT_BY_ATOM_TYPE = {
    "character_fact": "character_state",
    "story_rule": "action",
    "pacing_rule": "action",
    "emotional_arc": "action",
    "restraint_rule": "action",
    "approved_decision": "action",
    "motif": "environment_persistence",
    "world_fact": "environment_persistence",
    "continuity_fact": "environment_persistence",
    "tone_rule": "lighting",
    "style_rule": "lighting",
    "department_guidance": "camera",
}
_AUTHORITY_PRIORITY = {
    "creator_approved": 7,
    "spine_frozen": 7,
    "bible_committed": 6,
    "spine_revisable": 5,
    "canonical_memory": 4,
    "bible_inferred": 3,
    "advisory_inference": 1,
}
_ATOM_PRIORITY = {
    "character_fact": 8,
    "continuity_fact": 8,
    "story_rule": 7,
    "style_rule": 7,
    "tone_rule": 7,
    "restraint_rule": 6,
    "emotional_arc": 6,
    "motif": 6,
    "pacing_rule": 5,
    "world_fact": 5,
    "approved_decision": 5,
    "department_guidance": 4,
}


def _enum_value(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    return str(raw or "").strip().lower()


def _source_value(atom: Any, key: str) -> str:
    source_ref = getattr(atom, "source_ref", None)
    if source_ref is None and isinstance(atom, dict):
        source_ref = atom.get("source_ref")
    if isinstance(source_ref, dict):
        return _enum_value(source_ref.get(key))
    return _enum_value(getattr(source_ref, key, ""))


def _atom_value(atom: Any, key: str) -> Any:
    if isinstance(atom, dict):
        return atom.get(key)
    return getattr(atom, key, None)


def _bible_value(bible: Any, key: str) -> str:
    if isinstance(bible, dict):
        value = bible.get(key)
    else:
        value = getattr(bible, key, "")
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip()


def _compact(text: str, limit: int = 92) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    clean = clean.replace("**", "").replace("__", "").replace("*", "")
    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get() or len(clean) <= limit:
        return clean
    shortened = clean[: limit - 3]
    last_space = shortened.rfind(" ")
    if last_space >= int(limit * 0.55):
        shortened = shortened[:last_space]
    return shortened.rstrip(" ,;:.") + "..."


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9']+", value.lower())
        if len(token) >= 4
    }


@dataclass
class RenderKnowledgeContext:
    slot_guidance: dict[str, str] = field(default_factory=dict)
    selected_atom_ids: list[str] = field(default_factory=list)
    selected_sources: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.selected_atom_ids

    def as_metadata(self) -> dict[str, Any]:
        return {
            "selected_atom_ids": list(self.selected_atom_ids),
            "selected_sources": list(self.selected_sources),
            "source_counts": dict(self.source_counts),
            "slot_guidance": dict(self.slot_guidance),
        }


class RenderContextEnrichmentService:
    """Select relevant Bible and Creative Spine canon for provider prompts."""

    def build_context(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_id: str,
        scene_data: dict[str, Any] | None,
        character_names: list[str] | None,
        storage: Any,
    ) -> RenderKnowledgeContext:
        if storage is None or not hasattr(storage, "list_knowledge_atoms"):
            return RenderKnowledgeContext()

        try:
            atoms = list(
                storage.list_knowledge_atoms(
                    project_id,
                    filters={"status": "active"},
                    limit=500,
                )
            )
        except Exception:
            return RenderKnowledgeContext()

        bibles: list[Any] = []
        if hasattr(storage, "list_knowledge_bibles"):
            try:
                bibles = list(storage.list_knowledge_bibles(project_id, limit=500))
            except Exception:
                bibles = []
        bible_types = {
            _bible_value(bible, "bible_id").lower(): (
                _bible_value(bible, "bible_type").lower(),
                _bible_value(bible, "title"),
            )
            for bible in bibles
            if _bible_value(bible, "bible_id")
            and _bible_value(bible, "status").lower() not in {"archived", "failed"}
        }
        excluded_bible_ids = {
            _bible_value(bible, "bible_id").lower()
            for bible in bibles
            if _bible_value(bible, "bible_id")
            and _bible_value(bible, "status").lower() in {"archived", "failed"}
        }

        scene = scene_data if isinstance(scene_data, dict) else {}
        characters = {
            str(name).strip().lower()
            for name in (character_names or [])
            if str(name).strip()
        }
        location = str(scene.get("location") or scene.get("heading") or "").strip().lower()
        scene_text = " ".join(
            str(scene.get(key) or "")
            for key in (
                "heading",
                "text",
                "content",
                "description",
                "scene_text",
                "emotional_tone",
                "emotional_target",
                "location",
            )
        )
        relevance_tokens = _tokens(
            " ".join([scene_text, scene_id, shot_id, location, *characters])
        )

        ranked: list[tuple[int, str, str, str, str]] = []
        for atom in atoms:
            source_type = _source_value(atom, "source_type")
            source_id = _source_value(atom, "source_id")
            if source_id in excluded_bible_ids:
                continue
            bible_type, bible_title = bible_types.get(source_id, ("", ""))
            source_label = "creative_spine" if (
                source_type == "creative_spine"
                or "spine" in bible_type
                or "creative spine" in bible_title.lower()
            ) else "bible"
            if source_type not in _SUPPORTED_SOURCE_TYPES and not bible_type:
                continue

            atom_type = _enum_value(_atom_value(atom, "atom_type"))
            slot = self._slot_for_atom(atom_type, atom)
            if not slot:
                continue
            text = str(
                _atom_value(atom, "canonical_text")
                or _atom_value(atom, "summary")
                or ""
            ).strip()
            if not text:
                continue
            scope_type = _enum_value(_atom_value(atom, "scope_type")) or "project"
            scope_id = str(_atom_value(atom, "scope_id") or "").strip().lower()
            if atom_type == "character_fact":
                colon_index = text.find(":")
                subject_text = (
                    text[:colon_index]
                    if 0 < colon_index <= 100
                    else text[:100]
                )
                visible_character_fact = (
                    scope_type == "character"
                    and scope_id in characters
                ) or any(
                    text_mentions_character(subject_text, character_name)
                    for character_name in characters
                )
                location_fact = bool(
                    location
                    and (_tokens(location) & _tokens(text))
                )
                if visible_character_fact:
                    slot = "character_state"
                elif location_fact:
                    slot = "environment_persistence"
                else:
                    continue

            scope_score = self._scope_score(
                scope_type=scope_type,
                scope_id=scope_id,
                scene_id=scene_id.lower(),
                shot_id=shot_id.lower(),
                characters=characters,
                location=location,
            )
            if scope_score < 0:
                continue

            authority = _enum_value(_atom_value(atom, "authority_level"))
            overlap = len(_tokens(text) & relevance_tokens)
            score = (
                scope_score
                + _AUTHORITY_PRIORITY.get(authority, 0)
                + _ATOM_PRIORITY.get(atom_type, 0)
                + min(overlap, 3)
                + (2 if source_label == "creative_spine" else 1)
            )
            atom_id = str(_atom_value(atom, "atom_id") or "").strip()
            ranked.append((score, atom_id, source_label, slot, text))

        selected = self._select_balanced(ranked)
        slot_lines: dict[str, list[str]] = {}
        source_counts: dict[str, int] = {}
        selected_sources: list[str] = []
        for _, atom_id, source_label, slot, text in selected:
            slot_lines.setdefault(slot, []).append(_compact(text))
            source_counts[source_label] = source_counts.get(source_label, 0) + 1
            if source_label not in selected_sources:
                selected_sources.append(source_label)

        return RenderKnowledgeContext(
            slot_guidance={
                slot: " ".join(dict.fromkeys(lines))
                for slot, lines in slot_lines.items()
                if lines
            },
            selected_atom_ids=[item[1] for item in selected if item[1]],
            selected_sources=selected_sources,
            source_counts=source_counts,
        )

    @staticmethod
    def _scope_score(
        *,
        scope_type: str,
        scope_id: str,
        scene_id: str,
        shot_id: str,
        characters: set[str],
        location: str,
    ) -> int:
        if scope_type in {"project", "film", ""}:
            return 2
        if scope_type == "shot":
            return 12 if scope_id == shot_id else -1
        if scope_type == "scene":
            return 10 if scope_id == scene_id else -1
        if scope_type == "character":
            return 9 if scope_id in characters else -1
        if scope_type == "location":
            return 8 if scope_id and (scope_id == location or scope_id in location) else -1
        if scope_type in {"act", "sequence", "motif", "department"}:
            return 3
        return 0

    @staticmethod
    def _slot_for_atom(atom_type: str, atom: Any) -> str:
        if atom_type != "department_guidance":
            return _SLOT_BY_ATOM_TYPE.get(atom_type, "")
        department = str(_atom_value(atom, "department") or "").strip().lower()
        if department in {"lighting", "color", "cinematography"}:
            return "lighting"
        if department in {"camera", "director", "directing"}:
            return "camera"
        if department in {"production_design", "art", "locations"}:
            return "environment_persistence"
        if department in {"performance", "acting"}:
            return "action"
        return "camera"

    @staticmethod
    def _select_balanced(
        ranked: list[tuple[int, str, str, str, str]],
        limit: int = 5,
    ) -> list[tuple[int, str, str, str, str]]:
        ordered = sorted(ranked, key=lambda item: (-item[0], item[1], item[4]))
        selected: list[tuple[int, str, str, str, str]] = []
        selected_ids: set[str] = set()

        for source_label in ("creative_spine", "bible"):
            candidate = next(
                (item for item in ordered if item[2] == source_label),
                None,
            )
            if candidate is not None:
                selected.append(candidate)
                selected_ids.add(candidate[1])

        for item in ordered:
            if len(selected) >= limit:
                break
            if item[1] in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item[1])

        return selected


render_context_enrichment_service = RenderContextEnrichmentService()
