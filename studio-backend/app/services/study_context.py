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
from typing import Any, Dict, List, Tuple

from app.data import get_storage
from app.services.project_store import project_store
from app.services.director_memory_service import director_memory_service
from app.services.study_memory_service import get_study_memory_service

logger = logging.getLogger("study-context")


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
    total = sum(len(v) for v in bundle.values())
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
        total += db_memories.get("raw_count", 0)
    except Exception as exc:
        logger.debug("Could not load study_memories: %s", exc)

    categorized["raw_count"] = total
    categorized["found"] = total > 0
    return categorized


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
    blocks: List[str] = []

    # 1. Active memories
    memories = fetch_active_memories(project_id)
    if memories["found"]:
        mem_blocks: List[str] = []
        for category, label in [("style", "LEARNED STYLE"), ("tone", "TONE RULES"), ("pacing", "PACING")]:
            items = memories.get(category, [])
            if items:
                mem_blocks.append(f"--- {label} ---\n" + "\n".join(f"- {item}" for item in items))
        if mem_blocks:
            blocks.append("DIRECTOR'S ACTIVE MEMORY:\n" + "\n\n".join(mem_blocks))

    # 2. Character descriptions
    char_block = build_characters_context_block(project_id)
    if char_block:
        blocks.append(char_block)

    # 3. Scene content
    if scene_id:
        scene_text = fetch_scene_content(project_id, scene_id)
        if scene_text:
            blocks.append(f"CURRENT SCENE:\n{scene_text}")

    return "\n\n".join(blocks)


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
