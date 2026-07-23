"""
Casting service — the layer between The Page's casting UI and dialogue
generation.

Fits your thin-routes -> services -> storage rule from AGENTS.md:
  - route: POST /projects/{project_id}/characters/{character_id}/cast
  - service: CastingService (this file)
  - storage: character_voice_casting table/collection (SQLite, alongside
    your existing project/character storage)

Purpose: when a filmmaker casts a character on The Page (picks a voice, or
uploads a reference clip to clone), that decision needs to travel all the way
to the per-shot audio orchestrator so every line that character speaks uses
the right voice AND the right emotional baseline — not just a flat voice_id
with no emotional context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class VoiceProvider(str, Enum):
    CHATTERBOX = "chatterbox"
    KOKORO = "kokoro"
    FISH_AUDIO = "fish_audio"


@dataclass
class CharacterCasting:
    character_id: str
    project_id: str
    provider: VoiceProvider
    voice_id: str
    # Baseline emotional register for this character — e.g. a character who's
    # written as perpetually anxious might default to a mild "nervous" tag
    # rather than "neutral", so lines don't need per-line overrides to read
    # right. This is the hook that connects casting to the emotion problem
    # directly, instead of treating voice selection and emotion as unrelated.
    default_emotion_tag: Optional[str] = None
    default_emotion_intensity: Optional[float] = None
    reference_clip_path: Optional[str] = None  # if cloned rather than library


class CastingService:
    """
    Thin service — delegates persistence to storage, delegates actual audio
    generation to whichever provider is cast. Keeps casting decisions and
    generation decoupled so swapping providers later doesn't touch this layer.
    """

    def __init__(self, storage, provider_picker):
        self._storage = storage          # your existing storage layer
        self._provider_picker = provider_picker  # your existing ProviderPicker

    async def cast_character(
        self,
        project_id: str,
        character_id: str,
        provider: VoiceProvider,
        voice_id: str,
        default_emotion_tag: Optional[str] = None,
        default_emotion_intensity: Optional[float] = None,
    ) -> CharacterCasting:
        casting = CharacterCasting(
            character_id=character_id,
            project_id=project_id,
            provider=provider,
            voice_id=voice_id,
            default_emotion_tag=default_emotion_tag,
            default_emotion_intensity=default_emotion_intensity,
        )
        await self._storage.save_character_casting(casting)
        return casting

    async def cast_from_reference_clip(
        self,
        project_id: str,
        character_id: str,
        reference_clip_path: str,
        default_emotion_tag: Optional[str] = None,
    ) -> CharacterCasting:
        """
        For when a filmmaker uploads their own reference audio on The Page
        instead of picking a stock voice — clone it via Fish Audio, then cast
        the resulting voice_id to the character.
        """
        fish_provider = self._provider_picker.get(VoiceProvider.FISH_AUDIO)
        voice_id = await fish_provider.clone_voice(
            reference_audio_path=reference_clip_path,
            label=f"{project_id}_{character_id}",
        )
        return await self.cast_character(
            project_id=project_id,
            character_id=character_id,
            provider=VoiceProvider.FISH_AUDIO,
            voice_id=voice_id,
            default_emotion_tag=default_emotion_tag,
        )

    async def get_casting(
        self, project_id: str, character_id: str
    ) -> Optional[CharacterCasting]:
        return await self._storage.get_character_casting(project_id, character_id)

    async def resolve_line_audio_request(
        self,
        project_id: str,
        character_id: str,
        line_text: str,
        scene_emotion_tag: Optional[str] = None,
        scene_emotion_intensity: Optional[float] = None,
    ) -> dict:
        """
        Called by the per-shot audio orchestrator / Audio Director Agent for
        each dialogue line. Resolves casting + emotion into a single request
        the orchestrator can pass to the provider, with scene-level emotion
        (from the Co-Director Brain / Emotional Audience Simulator) overriding
        the character's default baseline when present.
        """
        casting = await self.get_casting(project_id, character_id)
        if casting is None:
            raise ValueError(
                f"Character {character_id} has not been cast yet — "
                f"prompt the user to cast it on The Page before rendering audio."
            )

        return {
            "text": line_text,
            "provider": casting.provider,
            "voice_id": casting.voice_id,
            "emotion_tag": scene_emotion_tag or casting.default_emotion_tag,
            "emotion_intensity": (
                scene_emotion_intensity
                if scene_emotion_intensity is not None
                else casting.default_emotion_intensity
            ),
        }
