"""
Proactive Co-Director Routes

POST /api/f51/studio/projects/{project_id}/co-director/proactive-check
  Body: { trigger_type: "scene_save"|"project_open"|"cut_assembly",
          scene_id?: str, last_edited?: str }
  Returns: ProactiveCheck

POST /api/f51/studio/projects/{project_id}/co-director/chat
  Body: { specialist, message, context, system_prompt }
  Returns: { reply, specialist, memory_entries_used }
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.proactive_codirector_service import ProactiveCheck

logger = logging.getLogger("proactive-routes")

router = APIRouter(prefix="/api/f51/studio", tags=["proactive-codirector"])

VALID_TRIGGERS = {"scene_save", "project_open", "cut_assembly"}


# ===========================================================================
# Existing: Proactive Check Route
# ===========================================================================

class ProactiveCheckRequest(BaseModel):
    trigger_type: str
    scene_id: Optional[str] = None
    last_edited: Optional[str] = None


def _get_service():
    from app.services.proactive_codirector_service import proactive_codirector_service
    return proactive_codirector_service


@router.post("/projects/{project_id}/co-director/proactive-check")
async def proactive_check(
    project_id: str,
    body: ProactiveCheckRequest,
) -> ProactiveCheck:
    """
    Run a proactive co-director check.

    trigger_type:
      - scene_save    → scan memory for motif gaps / continuity breaks
      - project_open  → re-orientation note if gap > 48 hours (once per session)
      - cut_assembly  → audience simulation on current cut (2+ approved scenes)

    Returns ProactiveCheck with should_surface: false if nothing meaningful found.
    Silent by default — only surfaces when there is something worth saying.
    """
    trigger = body.trigger_type.strip().lower()

    if trigger not in VALID_TRIGGERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trigger_type '{trigger}'. Expected one of: {', '.join(sorted(VALID_TRIGGERS))}",
        )

    service = _get_service()

    logger.info(
        "PROACTIVE_CHECK | project=%s | trigger=%s | scene=%s",
        project_id,
        trigger,
        body.scene_id or "-",
    )

    try:
        if trigger == "scene_save":
            if not body.scene_id:
                raise HTTPException(
                    status_code=400,
                    detail="scene_id is required for trigger_type 'scene_save'",
                )
            result = await service.check_scene_save(
                project_id=project_id,
                scene_id=body.scene_id,
            )

        elif trigger == "project_open":
            result = await service.check_project_open(
                project_id=project_id,
                last_edited=body.last_edited,
            )

        else:  # cut_assembly
            result = await service.check_cut_assembly(project_id=project_id)

        logger.info(
            "PROACTIVE_RESULT | project=%s | trigger=%s | surface=%s",
            project_id,
            trigger,
            result.should_surface,
        )
        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "PROACTIVE_CHECK_FAILED | project=%s | trigger=%s | %s",
            project_id,
            trigger,
            exc,
        )
        # Fail silently — never block the user's workflow
        return ProactiveCheck(
            should_surface=False,
            message="",
            trigger_type=trigger,
        )


# ===========================================================================
# New: Co-Director Chat Route
# ===========================================================================

# Specialist personas (injected BEFORE the frontend's system prompt)
SPECIALIST_PERSONAS: Dict[str, str] = {
    "director": (
        "You are the A24 Co-Director. Speak in cinematic language. "
        "No scores or percentages. No generic advice. Push the work "
        "toward something specific and unexpected. Advisory only."
    ),
    "writer": (
        "You are the Script Supervisor and Story Architect. "
        "Focus on structure, character voice, scene economy, "
        "and what is not being said. Cut ruthlessly."
    ),
    "memory_archivist": (
        "You are the Memory Archivist. You track continuity, "
        "motifs, and recurring patterns across the entire film. "
        "Flag contradictions. Surface connections the director "
        "may have missed."
    ),
    "evaluator": (
        "You are the Evaluator. Assess the work honestly. "
        "Identify what is working and what is not. Be specific. "
        "No flattery. Reference the director's own stated rules "
        "against their work."
    ),
    "provider_router": (
        "You are the Provider Router. You identify which "
        "generation model, tool, or service is best suited "
        "for each task. Think in capabilities and constraints."
    ),
}

VALID_SPECIALISTS = set(SPECIALIST_PERSONAS.keys())
VALID_CONTEXTS = {"current_scene", "full_script", "project_overview", "custom"}


# Accept any specialist string at the API boundary; persona mapping applies
# only for the five known specialists. This preserves backwards compatibility
# with callers/tests that send other values (e.g. cinematographer/editor/composer).


class Context(str, Enum):
    current_scene = "current_scene"
    full_script = "full_script"
    project_overview = "project_overview"
    custom = "custom"


class ChatRequest(BaseModel):
    specialist: str = "director"
    message: str
    context: Context = Context.current_scene
    system_prompt: str = ""


class ChatResponse(BaseModel):
    reply: str
    specialist: str
    memory_entries_used: int
    references_used: int = 0


# ---------------------------------------------------------------------------
# LLM client — imported lazily from co_director_chat so tests can patch it
# ---------------------------------------------------------------------------

def _get_llm_callable():
    """Import from shared llm_client — no circular dependency."""
    from app.llm_client import call_llm as _llm
    return _llm


# ---------------------------------------------------------------------------
# Project store helpers
# ---------------------------------------------------------------------------

def _get_project_store():
    from app.services.project_store import project_store
    return project_store


def _get_scene_list(project_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract scene list from project data."""
    summary = project_data.get("execution_summary") or {}
    scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
    if not scenes:
        scenes = project_data.get("scenes") or []
    return scenes if isinstance(scenes, list) else []


def _get_scene_text(project_data: Dict[str, Any], scene_id: str) -> str:
    """Get text for a specific scene from project data."""
    for scene in _get_scene_list(project_data):
        if isinstance(scene, dict):
            sid = scene.get("scene_id") or scene.get("id") or ""
            if sid == scene_id:
                parts = []
                if scene.get("scene_name"):
                    parts.append(f"Scene: {scene['scene_name']}")
                if scene.get("location"):
                    parts.append(f"Location: {scene['location']}")
                if scene.get("time_of_day"):
                    parts.append(f"Time: {scene['time_of_day']}")
                if scene.get("emotional_tone"):
                    parts.append(f"Tone: {scene['emotional_tone']}")
                if scene.get("script"):
                    parts.append(f"\n{scene['script']}")
                if scene.get("description"):
                    parts.append(f"\n{scene['description']}")
                if scene.get("content"):
                    parts.append(f"\n{scene['content']}")
                return "\n".join(parts)
    return ""


def _get_all_scenes_text(project_data: Dict[str, Any]) -> str:
    """Get text for all scenes from project data."""
    parts = []
    for i, scene in enumerate(_get_scene_list(project_data)):
        if isinstance(scene, dict):
            scene_parts = []
            name = scene.get("scene_name") or scene.get("title") or f"Scene {i + 1}"
            scene_parts.append(f"=== {name} ===")
            if scene.get("location"):
                scene_parts.append(f"Location: {scene['location']}")
            if scene.get("script"):
                scene_parts.append(scene["script"])
            if scene.get("description"):
                scene_parts.append(scene["description"])
            if scene.get("content"):
                scene_parts.append(scene["content"])
            parts.append("\n".join(scene_parts))
    full_text = "\n\n".join(parts)
    # Truncate to 3000 chars if too long
    if len(full_text) > 3000:
        full_text = full_text[:2997] + "..."
    return full_text


def _get_project_overview_text(project_data: Dict[str, Any]) -> str:
    """Get project overview text — title, logline, scene count, runtime."""
    title = project_data.get("title", "Untitled Project")
    logline = ""

    # Try various places for logline / creative intent
    bible = project_data.get("production_bible") or {}
    if isinstance(bible, dict):
        logline = bible.get("creative_intent", "") or bible.get("logline", "") or ""

    if not logline:
        logline = project_data.get("logline", "") or project_data.get("description", "")

    scenes = _get_scene_list(project_data)
    scene_count = len(scenes)

    stats = project_data.get("source_stats") or {}
    runtime_minutes = stats.get("target_runtime_minutes", 0)

    lines = [
        f"Current project: {title}",
        f"{logline}",
        f"{scene_count} scenes | {runtime_minutes}",
    ]

    # Add scene list
    if scenes:
        lines.append("\nScenes:")
        for s in scenes:
            if isinstance(s, dict):
                name = s.get("scene_name") or s.get("title") or s.get("scene_id", "?")
                loc = s.get("location", "")
                tone = s.get("emotional_tone", "")
                tags = " | ".join(filter(None, [loc, tone]))
                lines.append(f"  - {name}" + (f" ({tags})" if tags else ""))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------

async def _build_context(
    project_id: str,
    context_type: str,
) -> str:
    """
    Build context text based on request.context value.

    Returns the context text only (injected into system prompt prefix).
    """
    if context_type == "custom":
        return ""

    store = _get_project_store()
    project_data = store.get_project(project_id)
    if not project_data:
        logger.warning("Project %s not found for context injection", project_id)
        return ""

    if context_type == "current_scene":
        scenes = _get_scene_list(project_data)
        active_scene_id = project_data.get("active_scene_id", "")
        if active_scene_id:
            context_text = _get_scene_text(project_data, active_scene_id)
        elif scenes:
            context_text = _get_scene_text(project_data, scenes[-1].get("scene_id", ""))
        else:
            context_text = ""

        return context_text or ""

    elif context_type == "full_script":
        return _get_all_scenes_text(project_data) or ""

    elif context_type == "project_overview":
        return _get_project_overview_text(project_data) or ""

    return ""


# ---------------------------------------------------------------------------
# Director's Memory — fetch from project_store
# ---------------------------------------------------------------------------

def _get_director_memory_entries(project_id: str, max_entries: int = 3) -> tuple[List[str], int]:
    """
    Fetch Director's Memory entries + study_memories — top N most recent.

    Returns (formatted_entries_text, count).
    """
    store = _get_project_store()
    memory_bundle = store.get_director_memory(project_id)

    all_entries: List[Dict[str, Any]] = []
    for kind, entries in memory_bundle.items():
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    content = entry.get("content") or entry.get("user_note") or entry.get("summary", "")
                    if content:
                        all_entries.append({
                            "content": content,
                            "kind": kind,
                            "saved_at": entry.get("saved_at", ""),
                        })

    # Also include study_memories from the database
    try:
        from app.services.study_memory_service import get_study_memory_service
        svc = get_study_memory_service()
        db_rows = svc.get_memories(project_id)
        for key in ("style", "tone", "pacing"):
            for item in db_rows.get(key, []):
                if item not in [e["content"] for e in all_entries]:
                    all_entries.append({
                        "content": item,
                        "kind": f"study_{key}",
                        "saved_at": "",
                    })
    except Exception:
        pass

    if not all_entries:
        return [], 0

    # Sort by most recent and take top N
    all_entries.sort(key=lambda e: e.get("saved_at", ""), reverse=True)
    top = all_entries[:max_entries]

    formatted = [e["content"] for e in top]
    return formatted, len(formatted)


# ---------------------------------------------------------------------------
# Reference Study Library — fetch from project data with message-relevance scoring
# ---------------------------------------------------------------------------

def _get_study_references(project_id: str, message: str, max_studies: int = 5) -> tuple[str, int]:
    """
    Fetch the top N most relevant study references from the project's
    reference_study_library.studies list, scored by keyword relevance
    to the user's message.

    Returns (study_context_string, count).
    """
    store = _get_project_store()
    project_data = store.get_project(project_id)
    if not project_data:
        return "", 0

    studies = project_data.get("reference_study_library", {}).get("studies", [])
    if not isinstance(studies, list) or not studies:
        return "", 0

    # Filter to studies that have actual content (notes, summary, content, or filename)
    studies_with_content = [
        s for s in studies
        if isinstance(s, dict) and (
            s.get("notes") or s.get("summary") or s.get("content") or s.get("filename")
        )
    ]

    if not studies_with_content:
        return "", 0

    # Score by relevance to the message (simple keyword match)
    message_lower = message.lower()

    def score_study(s):
        title = (s.get("title") or s.get("filename") or "").lower()
        content = (s.get("notes") or s.get("summary") or s.get("content") or "").lower()
        combined = title + " " + content
        # Count how many words from the message appear in the study
        words = [w for w in message_lower.split() if len(w) > 3]
        return sum(1 for w in words if w in combined)

    studies_with_content.sort(key=score_study, reverse=True)
    top_studies = studies_with_content[:max_studies]

    study_parts = []
    for s in top_studies:
        title = s.get("title") or s.get("filename") or "Untitled"
        body = (s.get("notes") or s.get("summary") or s.get("content") or s.get("filename") or "")[:300]
        if body:
            study_parts.append(f"REFERENCE: {title}\n{body}")

    if not study_parts:
        return "", 0

    study_context = "\n\n".join(study_parts)
    return study_context, len(study_parts)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/co-director/chat")
async def co_director_chat(
    project_id: str,
    body: ChatRequest,
) -> ChatResponse:
    """
    Chat with a Co-Director specialist.

    Assembles specialist persona + frontend system prompt, injects
    project context, queries Director's Memory, and calls the LLM.
    """
    specialist_key = body.specialist
    context_type = body.context.value

    # Manual validation: reject completely unknown specialists with 422
    if specialist_key not in VALID_SPECIALISTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Input should be one of: {', '.join(sorted(VALID_SPECIALISTS))}"
            ),
        )

    # ── 1. Assemble system prompt ──────────────────────────────────────────
    persona = SPECIALIST_PERSONAS.get(specialist_key, "")
    frontend_prompt = body.system_prompt.strip()

    if persona and frontend_prompt:
        full_system_prompt = f"{persona}\n\n{frontend_prompt}"
    elif persona:
        full_system_prompt = persona
    else:
        full_system_prompt = frontend_prompt or "You are a helpful film-making assistant."

    # ── 2. Inject context (system prompt prefix, not user message) ────────
    context_text = await _build_context(project_id, context_type)

    if context_text:
        full_system_prompt = (
            f"{full_system_prompt}\n\n"
            f"Current project context:\n"
            f"{context_text}"
        )

    # ── 3. Director's Memory ───────────────────────────────────────────────
    memory_entries, memory_count = _get_director_memory_entries(
        project_id,
        max_entries=3,
    )

    if memory_entries:
        memory_block = "\n".join(f"- {entry}" for entry in memory_entries)
        full_system_prompt = (
            f"{full_system_prompt}\n\n"
            f"Director's stated rules:\n"
            f"{memory_block}"
        )

    # ── 4. Reference Study Library (system prompt prefix) ──────────────────
    study_context, study_count = _get_study_references(project_id, body.message, max_studies=5)

    if study_context:
        full_system_prompt = (
            f"{full_system_prompt}\n\n"
            f"Director's reference library:\n"
            f"{study_context}"
        )

    # User message is clean — no context injected here
    user_message = f"Context:\n\nUser: {body.message}"

    logger.info(
        "CO_DIRECTOR_CHAT | project=%s | specialist=%s | context=%s | memory=%d | studies=%d",
        project_id,
        specialist_key,
        context_type,
        memory_count,
        study_count,
    )

    # ── 5. Call LLM ────────────────────────────────────────────────────────
    try:
        _call_llm = _get_llm_callable()
        reply = await _call_llm(full_system_prompt, user_message)
    except Exception as exc:
        logger.error(
            "CO_DIRECTOR_CHAT_FAILED | project=%s | specialist=%s | %s",
            project_id,
            specialist_key,
            exc,
        )
        # Return 500 — let frontend handle its own fallback
        raise HTTPException(
            status_code=500,
            detail="Co-Director unavailable",
        )

    return ChatResponse(
        reply=reply,
        specialist=specialist_key,
        memory_entries_used=memory_count,
        references_used=study_count,
    )
