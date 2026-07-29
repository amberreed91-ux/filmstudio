from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from time import perf_counter
from typing import Awaitable, Callable

from app.services.stability import ProviderError, ValidationError
from app.services.study_context import StudyContextSnapshot, build_study_context


LLMCallable = Callable[..., Awaitable[str]]
logger = logging.getLogger("previs-prompt-enhancement-service")


@dataclass(frozen=True)
class PromptEnhancementResult:
    enhanced_prompt: str
    original_prompt: str
    memory_entries_supplied: int
    scene_content_supplied: bool
    character_profiles_supplied: int
    attempts: int


_CRAFT_CATEGORIES = (
    {"frame", "framing", "composition", "close-up", "wide", "profile", "foreground", "background"},
    {"lens", "mm", "depth", "focus", "handheld", "dolly", "tracking", "camera", "push-in"},
    {"light", "lighting", "backlight", "shadow", "silhouette", "golden", "practical", "contrast"},
    {"block", "blocking", "crosses", "holds", "turns", "walks", "moves", "stops", "watches"},
    {"texture", "weathered", "decay", "dust", "glass", "concrete", "street", "production"},
)


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", value.lower())


def is_material_enhancement(original: str, candidate: str) -> bool:
    """Reject copy edits and near-verbatim provider responses."""
    original_tokens = _tokens(original)
    candidate_tokens = _tokens(candidate)
    if not candidate_tokens or len(candidate_tokens) < len(original_tokens) + 8:
        return False

    original_set = set(original_tokens)
    novel_tokens = {token for token in candidate_tokens if token not in original_set}
    if len(novel_tokens) < 8:
        return False

    normalized_original = " ".join(original_tokens)
    normalized_candidate = " ".join(candidate_tokens)
    if SequenceMatcher(a=normalized_original, b=normalized_candidate).ratio() >= 0.9:
        return False

    added_craft_categories = sum(
        bool(novel_tokens & category) for category in _CRAFT_CATEGORIES
    )
    return added_craft_categories >= 2


class PrevisPromptEnhancementService:
    def build_prompt(
        self,
        *,
        project_id: str,
        scene_id: str,
        prompt_text: str,
    ) -> tuple[str, str, StudyContextSnapshot]:
        original = str(prompt_text or "").strip()
        if not original:
            raise ValidationError(
                "prompt_text must be non-empty",
                stage="previs_prompt_enhancement",
                metadata={"project_id": project_id, "scene_id": scene_id},
            )
        if not str(scene_id or "").strip():
            raise ValidationError(
                "scene_id must be non-empty",
                stage="previs_prompt_enhancement",
                metadata={"project_id": project_id},
            )

        context = build_study_context(
            project_id,
            scene_id,
            relevance_query=original,
            max_memories=8,
        )
        system_prompt = (
            "You are a cinematographer translating screenplay evidence into a "
            "production-ready text-to-video prompt. Rewrite the source prompt; "
            "a punctuation pass, synonym swap, or near-verbatim copy is a failure.\n\n"
            f"{context.block or 'No additional project context is available.'}\n\n"
            "Enhancement contract:\n"
            "- Preserve the shot's story action, setting, time, and spoken words.\n"
            "- Add concrete composition and subject placement or blocking.\n"
            "- Add motivated lighting, contrast, color, and production texture.\n"
            "- Add a specific lens/focal-depth choice and restrained camera behavior.\n"
            "- Clarify the beat's emotional intention and internal visual rhythm.\n"
            "- Translate relevant memory into visible choices; do not paste memory prose.\n"
            "- Treat scene/character facts as evidence and craft choices as cinematic "
            "inference. Never invent new canon.\n"
            "- Prefer one continuous, renderable shot over a list of disconnected options.\n"
            "- Produce 320-600 characters. Output only the rewritten prompt."
        )
        user_message = (
            "Rewrite this into a materially more specific cinematic prompt:\n"
            f"{original}"
        )
        return system_prompt, user_message, context

    async def enhance(
        self,
        *,
        project_id: str,
        scene_id: str,
        prompt_text: str,
        llm: LLMCallable,
    ) -> PromptEnhancementResult:
        system_prompt, user_message, context = self.build_prompt(
            project_id=project_id,
            scene_id=scene_id,
            prompt_text=prompt_text,
        )
        original = prompt_text.strip()
        started = perf_counter()
        attempts = 0
        try:
            attempts = 1
            candidate = await llm(system_prompt, user_message, max_tokens=768)
            enhanced = self._clean(candidate)
            if not is_material_enhancement(original, enhanced):
                attempts = 2
                retry_message = (
                    f"{user_message}\n\n"
                    "Your previous draft was too close to the source. Start over and make "
                    "the visual transformation unmistakable: specify spatial composition "
                    "or blocking, motivated light, lens/depth, camera behavior, and tactile "
                    "environmental detail while preserving the scene facts."
                )
                enhanced = self._clean(
                    await llm(system_prompt, retry_message, max_tokens=768)
                )
            if not is_material_enhancement(original, enhanced):
                enhanced = self._local_fallback_enhancement(original, context)
                if not is_material_enhancement(original, enhanced):
                    raise ProviderError(
                        "Prompt enhancement fallback could not materially expand the prompt",
                        stage="previs_prompt_enhancement",
                        metadata={
                            "project_id": project_id,
                            "scene_id": scene_id,
                            "attempts": attempts,
                        },
                    )
            return PromptEnhancementResult(
                enhanced_prompt=enhanced,
                original_prompt=original,
                memory_entries_supplied=context.memory_entries_supplied,
                scene_content_supplied=context.scene_content_included,
                character_profiles_supplied=context.character_count,
                attempts=attempts,
            )
        except ValidationError:
            raise
        except Exception as exc:
            enhanced = self._local_fallback_enhancement(original, context)
            if is_material_enhancement(original, enhanced):
                logger.warning(
                    "PROMPT_ENHANCEMENT_LOCAL_FALLBACK | project_id=%s scene_id=%s cause=%s",
                    project_id,
                    scene_id,
                    type(exc).__name__,
                )
                return PromptEnhancementResult(
                    enhanced_prompt=enhanced,
                    original_prompt=original,
                    memory_entries_supplied=context.memory_entries_supplied,
                    scene_content_supplied=context.scene_content_included,
                    character_profiles_supplied=context.character_count,
                    attempts=attempts,
                )
            raise ProviderError(
                "Prompt enhancement provider failed",
                stage="previs_prompt_enhancement",
                metadata={
                    "project_id": project_id,
                    "scene_id": scene_id,
                    "attempts": attempts,
                    "cause": type(exc).__name__,
                },
            ) from exc
        finally:
            logger.info(
                "project_id=%s job_id=- provider=fallback-aware stage=previs_prompt_enhancement "
                "duration_ms=%d attempts=%d memories_supplied=%d scene_supplied=%s",
                project_id,
                int((perf_counter() - started) * 1000),
                attempts,
                context.memory_entries_supplied,
                context.scene_content_included,
            )

    @staticmethod
    def _clean(value: str) -> str:
        return str(value or "").strip().strip('"').strip("'")

    @staticmethod
    def _local_fallback_enhancement(original: str, context: StudyContextSnapshot) -> str:
        block = context.block or ""
        heading_match = re.search(r"HEADING:\s*(.+)", block)
        setting_match = re.search(r"SETTING:\s*(.+)", block)
        tone_match = re.search(r"TONE:\s*(.+)", block)
        chars_match = re.search(r"CHARACTERS:\s*(.+)", block)
        memory_text = (
            PrevisPromptEnhancementService._trim_at_word_boundary(context.memory_entries[0][1], 110)
            if context.memory_entries
            else ""
        )

        setting = (setting_match or heading_match).group(1).strip() if (setting_match or heading_match) else "the established location"
        tone = tone_match.group(1).strip() if tone_match else "the scene's held emotional pressure"
        characters = chars_match.group(1).strip() if chars_match else "the subjects"
        memory_clause = f" Let the visual language echo {memory_text.rstrip('.')}." if memory_text else ""

        enhanced = (
            f"{original.strip()} Reframe it as one continuous 40mm observational shot in {setting}, "
            f"placing {characters} in layered foreground and background tension. Use motivated practical "
            f"light, shallow depth, and restrained camera drift so the blocking reads before the emotion "
            f"is explained. Hold tactile production details in the frame and let the {tone.lower()} pressure guide "
            f"the rhythm rather than extra coverage.{memory_clause}"
        )
        return enhanced[:720].strip()

    @staticmethod
    def _trim_at_word_boundary(value: str, max_chars: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        trimmed = text[:max_chars].rsplit(" ", 1)[0].strip()
        return trimmed or text[:max_chars].strip()


previs_prompt_enhancement_service = PrevisPromptEnhancementService()
