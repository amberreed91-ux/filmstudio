"""
Study Context — Active Memory + Scene Content for LLM injection.

Shared utility that wires The Study's Active Memory (Director's Memory)
and full scene script content into LLM system prompt context blocks.

Used by:
  - Previs Bay (enhance prompt, director notes, shot count)
  - Production Readiness Scan (co-director summary)
  - Co-Director Chat (proactive.py)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from app.data import get_storage
from app.services.project_store import project_store
from app.services.director_memory_service import director_memory_service
from app.services.study_memory_service import get_study_memory_service

logger = logging.getLogger("study-context")


@dataclass(frozen=True)
class StudyContextSnapshot:
    """The exact context assembled for one generation request."""

    block: str
    memory_entries: tuple[tuple[str, str], ...]
    scene_content_included: bool
    character_count: int

    @property
    def memory_entries_supplied(self) -> int:
        return len(self.memory_entries)


# ---------------------------------------------------------------------------
# Active Memory categorization (mirrors frontend StudyRoom.tsx logic)
# ---------------------------------------------------------------------------

_MEMORY_KINDS_STYLE = {"symbols", "motifs"}
_MEMORY_KINDS_TONE = {"themes"}
_STYLE_KEYWORDS = frozenset({
    "style", "visual", "composition", "light", "color", "frame", "camera",
})
_TONE_KEYWORDS = frozenset({
    "tone", "mood", "emotion", "feel", "tension", "atmosphere",
})
_PACING_KEYWORDS = frozenset({
    "pace", "rhythm", "tempo", "cut timing", "editing speed",
})
_DEBATE_STYLE_KW = frozenset({
    "style", "visual", "composition", "look", "aesthetic",
})
_DEBATE_TONE_KW = frozenset({
    "tone", "mood", "emotion", "tension",
})
_DEBATE_PACING_KW = frozenset({
    "pace", "rhythm", "tempo", "cut", "timing",
})


def _entry_text(entry: Dict[str, Any], kind: str) -> str:
    if kind == "symbols":
        sym = entry.get("symbol") or "(unnamed symbol)"
        meaning = entry.get("meaning") or ""
        return f"{sym}" + (f" ({meaning})" if meaning else "")
    if kind == "motifs":
        return str(entry.get("motif") or entry.get("name") or "(unnamed motif)")
    if kind == "themes":
        return str(entry.get("theme") or entry.get("name") or "(unnamed theme)")
    if kind == "notes":
        headline = str(entry.get("headline") or "").strip()
        note = str(entry.get("note") or "").strip()
        if headline:
            return f"{headline}: {note[:200]}"
        return note[:240]
    if kind == "debates":
        synthesis = entry.get("synthesis") or ""
        query = entry.get("query") or ""
        return (synthesis or query)[:240]
    return str(entry.get("content") or "")[:240]


def _categorize_memories(
    bundle: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[str]]:
    """Categorize Director's Memory entries into STYLE, TONE, PACING.

    Returns { "style": [text, ...], "tone": [text, ...], "pacing": [text, ...] }
    """
    result: Dict[str, List[str]] = {"style": [], "tone": [], "pacing": []}

    for kind in _MEMORY_KINDS_STYLE:
        for entry in bundle.get(kind, []):
            text = _entry_text(entry, kind)
            if text:
                result["style"].append(text)

    for kind in _MEMORY_KINDS_TONE:
        for entry in bundle.get(kind, []):
            text = _entry_text(entry, kind)
            if text:
                result["tone"].append(text)

    for entry in bundle.get("notes", []):
        text = _entry_text(entry, "notes")
        if not text:
            continue
        hay = f"{entry.get('headline', '')} {entry.get('note', '')} {entry.get('keyword', '')}".lower()
        if any(kw in hay for kw in _PACING_KEYWORDS):
            result["pacing"].append(text)
        elif any(kw in hay for kw in _TONE_KEYWORDS):
            result["tone"].append(text)
        else:
            result["style"].append(text)

    for entry in bundle.get("debates", []):
        text = _entry_text(entry, "debates")
        if not text:
            continue
        hay = f"{entry.get('query', '')} {entry.get('synthesis', '')}".lower()
        if any(kw in hay for kw in _DEBATE_PACING_KW):
            result["pacing"].append(text)
        elif any(kw in hay for kw in _DEBATE_TONE_KW):
            result["tone"].append(text)
        elif any(kw in hay for kw in _DEBATE_STYLE_KW):
            result["style"].append(text)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_active_memories(
    project_id: str,
) -> Dict[str, List[str]]:
    """Fetch and categorize active Study memories for a project.

    Reads from two sources:
      1. Director's Memory (user-saved entries via JSON-backed store)
      2. study_memories table (auto-extracted entries via SQLite)

    Merges them into a single categorized block.
    Returns {
        "style": [...],
        "tone": [...],
        "pacing": [...],
        "raw_count": int,
        "found": bool,
    }
    """
    # Source 1: Director's Memory (JSON-backed, user-saved)
    bundle = director_memory_service.get_memory(project_id)
    categorized = _categorize_memories(bundle)

    # Source 2: study_memories table (SQLite-backed, auto-extracted)
    try:
        svc = get_study_memory_service()
        db_memories = svc.get_memories(project_id)
        for key in ("style", "tone", "pacing"):
            categorized.setdefault(key, [])
            for item in db_memories.get(key, []):
                if item not in categorized[key]:
                    categorized[key].append(item)
    except Exception as exc:
        logger.debug("Could not load study_memories: %s", exc)

    for key in ("style", "tone", "pacing"):
        # A memory can exist in both the JSON director-memory bundle and the
        # SQLite Study table. It is supplied only once to a model request.
        categorized[key] = list(dict.fromkeys(categorized.get(key, [])))

    included_count = sum(len(categorized[key]) for key in ("style", "tone", "pacing"))
    categorized["raw_count"] = included_count
    categorized["included_count"] = included_count
    categorized["found"] = included_count > 0
    return categorized


def select_relevant_memory_entries(
    project_id: str,
    query: str,
    *,
    max_entries: int = 8,
) -> list[tuple[str, str]]:
    """Return the bounded memory entries that will actually enter a prompt.

    Relevance is intentionally lexical and inspectable. Category diversity is
    preserved so a generic question still receives visual, tonal, and pacing
    evidence instead of whichever records happen to be stored first.
    """
    memories = fetch_active_memories(project_id)
    candidates = [
        (category, text)
        for category in ("style", "tone", "pacing")
        for text in memories.get(category, [])
        if str(text).strip()
    ]
    if max_entries <= 0:
        return []
    if len(candidates) <= max_entries:
        return candidates

    query_words = {
        word
        for word in re.findall(r"[a-z0-9']+", str(query).lower())
        if len(word) >= 4
    }
    craft_words = {
        "camera", "composition", "frame", "framing", "lens", "light",
        "lighting", "color", "visual", "movement", "location", "blocking",
        "rhythm", "pacing", "tone", "mood", "sound", "production",
    }

    def score(item: tuple[str, str]) -> tuple[int, int]:
        category, text = item
        words = set(re.findall(r"[a-z0-9']+", text.lower()))
        direct = len(query_words & words)
        craft = len(craft_words & words)
        # Visual craft is especially actionable for prompt enhancement, while
        # tone and pacing each receive a small diversity prior.
        prior = 2 if category == "style" else 1
        return direct * 4 + min(craft, 4) + prior, -candidates.index(item)

    selected: list[tuple[str, str]] = []
    for category in ("style", "tone", "pacing"):
        category_rows = [item for item in candidates if item[0] == category]
        if category_rows:
            selected.append(max(category_rows, key=score))

    for item in sorted(candidates, key=score, reverse=True):
        if item not in selected:
            selected.append(item)
        if len(selected) >= max_entries:
            break
    return selected[:max_entries]


def fetch_scene_content(
    project_id: str,
    scene_id: str,
) -> str:
    """Fetch full script content for a scene from the project store.

    Returns formatted text with heading, location, characters, and body.
    Returns empty string if scene not found.
    """
    project_data = project_store.get_project(project_id)
    if not project_data:
        return ""

    summary = project_data.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    if not isinstance(scenes, list):
        return ""

    script_text = project_data.get("script_text") or ""

    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id") or scene.get("id") or ""
        if sid == scene_id:
            return _format_scene_text(scene, script_text)

    return ""


def _format_scene_text(scene: Dict[str, Any], _full_script: str = "") -> str:
    """Build a readable scene text block from scene data dict."""
    parts: List[str] = []

    heading = scene.get("heading") or scene.get("scene_name") or ""
    if heading:
        parts.append(f"HEADING: {heading}")

    location = scene.get("location") or ""
    time_of_day = scene.get("time_of_day") or ""
    if location and time_of_day:
        parts.append(f"SETTING: {location}, {time_of_day}")
    elif location:
        parts.append(f"SETTING: {location}")

    characters = scene.get("characters") or []
    if characters:
        char_list = ", ".join(str(c) for c in characters if isinstance(c, str) and c.strip())
        if char_list:
            parts.append(f"CHARACTERS: {char_list}")

    tone = scene.get("emotional_tone") or ""
    if tone:
        parts.append(f"TONE: {tone}")

    # Full body text — prefer 'text' or 'script', fall back to 'description'
    body = (
        scene.get("text")
        or scene.get("script")
        or scene.get("description")
        or ""
    )
    if body:
        parts.append(f"\nSCENE TEXT:\n{body}")

    return "\n".join(parts)


def build_study_context_block(
    project_id: str,
    scene_id: str | None = None,
) -> str:
    """Build a complete context block prepending Study memory + scene content.

    This is the main entry point for injecting Study context into LLM calls.
    """
    return build_study_context(project_id, scene_id).block


def build_study_context(
    project_id: str,
    scene_id: str | None = None,
    *,
    relevance_query: str = "",
    max_memories: int = 8,
) -> StudyContextSnapshot:
    """Build context and provenance from the same immutable snapshot."""
    blocks: List[str] = []

    # 1. Active memories
    scene_text = fetch_scene_content(project_id, scene_id) if scene_id else ""
    entries = select_relevant_memory_entries(
        project_id,
        f"{relevance_query}\n{scene_text}",
        max_entries=max_memories,
    )
    if entries:
        mem_blocks: List[str] = []
        for category, label in [("style", "LEARNED STYLE"), ("tone", "TONE RULES"), ("pacing", "PACING")]:
            items = [text for entry_category, text in entries if entry_category == category]
            if items:
                mem_blocks.append(f"--- {label} ---\n" + "\n".join(f"- {item}" for item in items))
        if mem_blocks:
            blocks.append("DIRECTOR'S ACTIVE MEMORY:\n" + "\n\n".join(mem_blocks))

    # 2. Character descriptions
    char_block = build_characters_context_block(project_id)
    if char_block:
        blocks.append(char_block)
    character_count = max(0, len(char_block.splitlines()) - 1) if char_block else 0

    # 3. Scene content
    if scene_text:
        blocks.append(f"CURRENT SCENE:\n{scene_text}")

    return StudyContextSnapshot(
        block="\n\n".join(blocks),
        memory_entries=tuple(entries),
        scene_content_included=bool(scene_text),
        character_count=character_count,
    )


def build_characters_context_block(project_id: str) -> str:
    """Build a CHARACTERS IN THIS FILM context block from the characters table."""
    try:
        storage = get_storage("sqlite")
        characters = storage.get_characters(project_id)
        if not characters:
            return ""
        lines: list[str] = ["CHARACTERS IN THIS FILM:"]
        for c in characters:
            name = c.get("name") or "?"
            age = c.get("age") or ""
            vps = (c.get("visual_prompt_summary") or "").strip()
            if age and vps:
                lines.append(f"- {name} ({age}): {vps}")
            elif age:
                lines.append(f"- {name} ({age})")
            elif vps:
                lines.append(f"- {name}: {vps}")
            else:
                lines.append(f"- {name}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Could not load characters for context: %s", exc)
        return ""
