from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.llm_client import call_llm
from app.services.stability import PersistenceError, StateError, ValidationError, elapsed_ms, log_stage_event, start_timer
from app.utils.character_appearance import APPEARANCE_FIELDS, appearance_approval

logger = logging.getLogger(__name__)

VALID_CASTING_VOICE_PROVIDERS = {"cosyvoice", "fish_audio", "elevenlabs"}
INVALID_CHARACTER_NAMES = {
    "THE HOMESTEAD", "THE COUNTDOWN", "THE FIRST TIMELINE", "THE SECOND CHANCE",
    "THE WEIGHT OF KNOWING", "THE APOCALYPSE BEGINS", "THE LAST NORMAL DAYS",
    "THE HOMESTEAD COMMUNITY", "FINAL CONFRONTATION", "MAYA AND HER MOM",
    "DRE NOTICES", "ENDING", "SUPPLIES", "CUT TO", "FADE IN", "FADE OUT",
    "SMASH CUT", "TITLE CARD", "MONTAGE", "INTERCUT",
}
CHARACTER_DESCRIPTOR_SYSTEM_PROMPT = (
    "You are a film character analyst. Extract character information "
    "from the provided text and return ONLY valid JSON with these exact "
    "fields: name (string), age (string), look (string, physical appearance), "
    "energy (string, personality and presence), core_wound (string), "
    "visual_prompt_summary (string, one sentence suitable for AI image generation). "
    "If a field cannot be determined, return an empty string."
)


class CharacterDescriptorProviderError(RuntimeError):
    pass


class CharacterProfileService:
    def __init__(
        self,
        storage: StorageInterface | None = None,
        llm_completion: Callable[..., Awaitable[str]] | None = None,
    ):
        self._storage = storage
        self._llm_completion = llm_completion or call_llm

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    def list_characters(self, project_id: str) -> list[dict]:
        storage = self._require_storage()
        try:
            storage.seed_demo_characters(project_id)
        except Exception:
            logger.debug("Demo character seed skipped for %s", project_id)
        return storage.get_characters(project_id)

    def get_character(self, project_id: str, character_id: str) -> dict:
        character = self._require_storage().get_character(character_id, project_id)
        if not character:
            raise LookupError("Character not found")
        return character

    def update_character(
        self,
        project_id: str,
        character_id: str,
        updates: dict[str, Any],
    ) -> dict:
        timer = start_timer()
        existing = self.get_character(project_id, character_id)
        editable = {"name", "age", "look", "energy", "core_wound", "core_desire", "relationship_notes", "visual_prompt_summary"}
        if set(updates) - editable:
            raise ValidationError("Only character profile fields can be changed here.", stage="character_profile_update")
        if any(value is not None and not isinstance(value, str) for value in updates.values()):
            raise ValidationError("Character profile fields must be text.", stage="character_profile_update")
        if "name" in updates and not str(updates["name"] or "").strip():
            raise ValidationError("A character name is required.", stage="character_profile_update")
        if appearance_approval(existing).get("status") == "locked" and any(
            field in updates and updates[field] != existing.get(field) for field in APPEARANCE_FIELDS
        ):
            raise StateError("This appearance is locked. Choose Revise look in The Page before changing it.", stage="character_profile_update")
        if not updates:
            return existing
        try:
            # Patch only provided columns, by ID. Omitted appearance fields stay intact,
            # and the revision check prevents a concurrent approval being overwritten.
            saved = self._require_storage().patch_character_revision(project_id, character_id, updates, existing["updated_at"])
        except Exception as exc:
            raise PersistenceError("The character profile could not be saved.", stage="character_profile_update") from exc
        if not saved:
            raise StateError("This profile changed. Refresh it before saving again.", stage="character_profile_update")
        log_stage_event(project_id=project_id, job_id=None, provider=None, stage="character_profile_update",
                        duration_ms=elapsed_ms(timer), extra={"character_id": character_id})
        return saved

    def create_skeleton(self, project_id: str, name: str) -> dict:
        name_upper = (name or "").strip().upper()
        first_word = name_upper.split()[0] if name_upper.split() else ""
        if (
            not name_upper
            or name_upper in INVALID_CHARACTER_NAMES
            or first_word in {"THE", "A", "AN", "INT.", "EXT."}
        ):
            raise ValueError("Invalid character name")
        storage = self._require_storage()
        existing = storage.get_character_by_name(project_id, name)
        return existing or storage.save_character(project_id, name, {"name": name})

    @staticmethod
    def _strip_markdown_fences(raw: str) -> str:
        value = raw.strip()
        if value.startswith("```"):
            first_newline = value.find("\n")
            if first_newline != -1:
                value = value[first_newline + 1 :]
            if value.endswith("```"):
                value = value[:-3].strip()
        return value

    async def apply_descriptor(
        self,
        project_id: str,
        character_id: str,
        text_content: str,
    ) -> dict:
        existing = self.get_character(project_id, character_id)
        if appearance_approval(existing).get("status") == "locked":
            raise StateError("Choose Revise look before importing a new character description.", stage="character_descriptor")
        try:
            raw_response = await self._llm_completion(
                system_prompt=CHARACTER_DESCRIPTOR_SYSTEM_PROMPT,
                message=text_content,
            )
        except Exception as exc:
            raise CharacterDescriptorProviderError("AI analysis service unavailable") from exc
        try:
            extracted = json.loads(self._strip_markdown_fences(raw_response))
        except json.JSONDecodeError as exc:
            raise CharacterDescriptorProviderError("AI returned invalid JSON") from exc
        merged = dict(existing)
        for field in ("name", "age", "look", "energy", "core_wound", "visual_prompt_summary"):
            if extracted.get(field) and not merged.get(field):
                merged[field] = extracted[field]
        updates = {field: merged[field] for field in ("name", "age", "look", "energy", "core_wound", "visual_prompt_summary") if merged.get(field) != existing.get(field)}
        if not updates:
            return self.get_character(project_id, character_id)
        # An approval or edit may arrive while the provider is working.
        saved = self._require_storage().patch_character_revision(project_id, character_id, updates, existing["updated_at"])
        if not saved:
            raise StateError("This profile changed while the description was being read. Refresh and try again.", stage="character_descriptor")
        return saved

    @staticmethod
    def _voice_response(project_id: str, character_id: str, character: dict) -> dict:
        return {
            "character_id": character_id,
            "project_id": project_id,
            "voice_provider": character.get("voice_provider"),
            "voice_id": character.get("voice_id"),
            "voice_name": character.get("voice_name"),
            "voice_source_type": character.get("voice_source_type"),
            "voice_style_prompt": character.get("voice_style_prompt"),
            "elevenlabs_voice_id": character.get("elevenlabs_voice_id"),
            "elevenlabs_voice_name": character.get("elevenlabs_voice_name"),
        }

    def get_voice(self, project_id: str, character_id: str) -> dict:
        return self._voice_response(
            project_id,
            character_id,
            self.get_character(project_id, character_id),
        )

    def set_voice(
        self,
        project_id: str,
        character_id: str,
        *,
        provider: str,
        voice_id: str,
        voice_name: str | None,
        source_type: str | None,
        style_prompt: str | None,
    ) -> dict:
        self.get_character(project_id, character_id)
        normalized_provider = (provider or "elevenlabs").strip().lower()
        if normalized_provider not in VALID_CASTING_VOICE_PROVIDERS:
            raise ValueError(f"Unsupported Casting voice provider: {normalized_provider}")
        storage = self._require_storage()
        if normalized_provider == "elevenlabs":
            updated = storage.set_character_voice(
                character_id, project_id, voice_id, voice_name
            )
            if updated and hasattr(storage, "set_character_voice_casting"):
                updated = storage.set_character_voice_casting(
                    character_id=character_id,
                    project_id=project_id,
                    provider=normalized_provider,
                    voice_id=voice_id,
                    voice_name=voice_name,
                    source_type=source_type or "library",
                    style_prompt=style_prompt,
                )
        else:
            if not hasattr(storage, "set_character_voice_casting"):
                raise RuntimeError("Provider-aware voice casting storage unavailable")
            updated = storage.set_character_voice_casting(
                character_id=character_id,
                project_id=project_id,
                provider=normalized_provider,
                voice_id=voice_id,
                voice_name=voice_name,
                source_type=source_type,
                style_prompt=style_prompt,
            )
        if not updated:
            raise LookupError("Character not found")
        return self._voice_response(project_id, character_id, updated)


character_profile_service = CharacterProfileService()
