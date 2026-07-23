from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.data.storage import get_storage
from app.llm_client import get_llm_completion_with_fallback
from app.services.project_store import project_store

logger = logging.getLogger("writers-intelligence")

router = APIRouter(prefix="/api/f51/studio/projects", tags=["writers-intelligence"])


# ── Models ────────────────────────────────────────────────────────────────────

class CharacterMindRequest(BaseModel):
    character_name: str
    scene_id: str


class CharacterMindResponse(BaseModel):
    simulation: str
    character: str
    scene_id: str


class DebateRequest(BaseModel):
    scene_id: str


class DebateResponse(BaseModel):
    restraint: str
    urgency: str
    scene_id: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_scene(project_id: str, scene_id: str) -> dict[str, Any] | None:
    project = project_store.get_project(project_id)
    if not project:
        return None
    summary = project.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    for s in scenes:
        if isinstance(s, dict) and s.get("scene_id") == scene_id:
            return s
    # Fallback to checking project scenes list
    scenes_list = project.get("scenes") or []
    for s in scenes_list:
        if isinstance(s, dict) and s.get("scene_id") == scene_id:
            return s
    return None


def _get_scene_text(scene: dict[str, Any]) -> str:
    return scene.get("text") or scene.get("description") or ""


def _find_character(project_id: str, character_name: str) -> dict[str, Any] | None:
    storage = get_storage("sqlite")
    characters = storage.get_characters(project_id)
    for c in characters:
        if c.get("name", "").upper() == character_name.upper():
            return c
    return None


# ── Character Mind Endpoint ───────────────────────────────────────────────────

@router.post("/{project_id}/character-mind", response_model=CharacterMindResponse)
async def simulate_character_mind(project_id: str, request: CharacterMindRequest):
    """Simulate a character's inner thoughts during a scene using the fallback LLM chain."""
    try:
        scene = _find_scene(project_id, request.scene_id)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        scene_text = _get_scene_text(scene)
        if not scene_text:
            raise HTTPException(status_code=400, detail="Scene has no content")

        char_data = _find_character(project_id, request.character_name)
        char_name = request.character_name
        char_age = str(char_data.get("age", "")) if char_data else ""
        char_look = char_data.get("look", "") if char_data else ""
        char_energy = char_data.get("energy", "") if char_data else ""
        char_wound = char_data.get("core_wound", "") if char_data else ""
        char_desire = char_data.get("core_desire", "") if char_data else ""

        description_parts = [p for p in [char_look, char_energy] if p]
        char_description = ". ".join(description_parts)

        system_prompt = "You are simulating the inner thoughts and emotional state of a film character."

        wound_line = f" Core wound: {char_wound}" if char_wound else ""
        desire_line = f" Core desire: {char_desire}" if char_desire else ""

        user_prompt = (
            f"Character: {char_name}, Age: {char_age}\n"
            f"Description: {char_description}{wound_line}{desire_line}\n"
            f"Scene they are in:\n{scene_text}\n\n"
            f"Simulate what this character is thinking and feeling right now in this moment. "
            f"Write in first person, present tense, 3-4 sentences. "
            f"Be specific to this character's core wound and desires."
        )

        logger.info("Character mind simulation: project=%s character=%s scene=%s",
                     project_id, char_name, request.scene_id)

        simulation, provider = await get_llm_completion_with_fallback(
            system_prompt, user_prompt
        )
        logger.info(
            "project_id=%s job_id=- provider=%s stage=character_mind duration_ms=0",
            project_id,
            provider,
        )

        return CharacterMindResponse(
            simulation=simulation,
            character=char_name,
            scene_id=request.scene_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Character mind simulation failed")
        raise HTTPException(status_code=500, detail=f"Character mind simulation failed: {str(e)}")


# ── Debate Endpoint ───────────────────────────────────────────────────────────

@router.post("/{project_id}/debate", response_model=DebateResponse)
async def debate_scene(project_id: str, request: DebateRequest):
    """Generate two opposing co-director perspectives using the fallback LLM chain."""
    try:
        scene = _find_scene(project_id, request.scene_id)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        scene_text = _get_scene_text(scene)
        if not scene_text:
            raise HTTPException(status_code=400, detail="Scene has no content")

        restraint_system = (
            "You are a minimalist filmmaker in the tradition of Terrence Malick. "
            "You believe less is more. "
            "Argue for a more restrained, slower, more contemplative approach to this scene."
        )

        urgency_system = (
            "You are a filmmaker who believes emotion must be earned quickly. "
            "Argue for a more dynamic, emotionally direct approach to this scene."
        )

        user_prompt = (
            f"Scene content:\n\n{scene_text}\n\n"
            f"Provide your perspective on how this scene should be approached. "
            f"Be specific about pacing, emotion, and visual language."
        )

        logger.info("Scene debate: project=%s scene=%s", project_id, request.scene_id)

        # Each perspective races Qwen against the internal timeout and falls
        # back to OpenRouter independently, so a single blocked provider call no
        # longer hangs the whole Intelligence tab to the frontend's 30s.
        (restraint, restraint_provider), (urgency, urgency_provider) = await asyncio.gather(
            get_llm_completion_with_fallback(restraint_system, user_prompt),
            get_llm_completion_with_fallback(urgency_system, user_prompt),
        )
        logger.info(
            "project_id=%s job_id=- provider=%s/%s stage=scene_debate duration_ms=0",
            project_id,
            restraint_provider,
            urgency_provider,
        )

        return DebateResponse(
            restraint=restraint,
            urgency=urgency,
            scene_id=request.scene_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Scene debate failed")
        raise HTTPException(status_code=500, detail=f"Scene debate failed: {str(e)}")
