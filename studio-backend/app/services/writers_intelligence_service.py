from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.llm_client import get_llm_completion_with_fallback
from app.services.project_store import ProjectStore, project_store

logger = logging.getLogger("writers-intelligence")

Completion = Callable[[str, str], Awaitable[tuple[str, str]]]


class WritersIntelligenceService:
    def __init__(
        self,
        state_store: ProjectStore | None = None,
        storage: StorageInterface | None = None,
        completion: Completion | None = None,
    ):
        self._state_store = state_store or project_store
        self._storage = storage
        self._completion = completion or get_llm_completion_with_fallback

    def _find_scene(self, project_id: str, scene_id: str) -> dict[str, Any] | None:
        project = self._state_store.get_project(project_id)
        if not project:
            return None
        summary = project.get("execution_summary") or {}
        for scene in summary.get("scenes") or []:
            if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                return scene
        for scene in project.get("scenes") or []:
            if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                return scene
        return None

    def _find_character(self, project_id: str, character_name: str) -> dict[str, Any] | None:
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            return None
        for character in storage.get_characters(project_id):
            if character.get("name", "").upper() == character_name.upper():
                return character
        return None

    @staticmethod
    def _scene_text(scene: dict[str, Any]) -> str:
        return scene.get("text") or scene.get("description") or ""

    async def simulate_character_mind(
        self,
        project_id: str,
        scene_id: str,
        character_name: str,
    ) -> dict[str, str]:
        scene = self._find_scene(project_id, scene_id)
        if not scene:
            raise LookupError("Scene not found")
        scene_text = self._scene_text(scene)
        if not scene_text:
            raise ValueError("Scene has no content")

        char_data = self._find_character(project_id, character_name)
        char_age = str(char_data.get("age", "")) if char_data else ""
        char_look = char_data.get("look", "") if char_data else ""
        char_energy = char_data.get("energy", "") if char_data else ""
        char_wound = char_data.get("core_wound", "") if char_data else ""
        char_desire = char_data.get("core_desire", "") if char_data else ""
        char_description = ". ".join(part for part in [char_look, char_energy] if part)
        wound_line = f" Core wound: {char_wound}" if char_wound else ""
        desire_line = f" Core desire: {char_desire}" if char_desire else ""

        system_prompt = "You are simulating the inner thoughts and emotional state of a film character."
        user_prompt = (
            f"Character: {character_name}, Age: {char_age}\n"
            f"Description: {char_description}{wound_line}{desire_line}\n"
            f"Scene they are in:\n{scene_text}\n\n"
            "Simulate what this character is thinking and feeling right now in this moment. "
            "Write in first person, present tense, 3-4 sentences. "
            "Be specific to this character's core wound and desires."
        )

        simulation, provider = await self._completion(system_prompt, user_prompt)
        logger.info(
            "project_id=%s job_id=- provider=%s stage=character_mind duration_ms=0",
            project_id,
            provider,
        )
        return {"simulation": simulation, "character": character_name, "scene_id": scene_id}

    async def debate_scene(self, project_id: str, scene_id: str) -> dict[str, str]:
        scene = self._find_scene(project_id, scene_id)
        if not scene:
            raise LookupError("Scene not found")
        scene_text = self._scene_text(scene)
        if not scene_text:
            raise ValueError("Scene has no content")

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
            "Provide your perspective on how this scene should be approached. "
            "Be specific about pacing, emotion, and visual language."
        )

        (restraint, restraint_provider), (urgency, urgency_provider) = await asyncio.gather(
            self._completion(restraint_system, user_prompt),
            self._completion(urgency_system, user_prompt),
        )
        logger.info(
            "project_id=%s job_id=- provider=%s/%s stage=scene_debate duration_ms=0",
            project_id,
            restraint_provider,
            urgency_provider,
        )
        return {"restraint": restraint, "urgency": urgency, "scene_id": scene_id}


writers_intelligence_service = WritersIntelligenceService()
