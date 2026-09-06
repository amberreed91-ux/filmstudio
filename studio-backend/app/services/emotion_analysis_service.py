from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Awaitable, Callable

from app.config import get_settings
from app.data.storage import DatabaseStorage, get_storage
from app.llm_client import get_llm_completion_with_fallback
from app.services.project_store import ProjectStore, project_store
from app.services.stability import (
    PersistenceError,
    ProviderError,
    StateError,
    ValidationError,
    elapsed_ms,
    log_stage_event,
    start_timer,
)
from app.services.study_context import fetch_active_memories, fetch_scene_content

logger = logging.getLogger("emotion-analysis")

PROMPT_VERSION = "emotion-analysis-v2"
LLMCompletion = Callable[..., Awaitable[tuple[str, str]]]


class EmotionAnalysisService:
    def __init__(
        self,
        storage: DatabaseStorage | None = None,
        project_store_service: ProjectStore | None = None,
        llm_completion: LLMCompletion | None = None,
        scene_content_fetcher: Callable[[str, str], str] | None = None,
        memory_fetcher: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._storage = storage
        self._project_store = project_store_service or project_store
        self._llm_completion = llm_completion or get_llm_completion_with_fallback
        self._scene_content_fetcher = scene_content_fetcher or fetch_scene_content
        self._memory_fetcher = memory_fetcher or fetch_active_memories
        self._inflight: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self._inflight_guard = Lock()

    @property
    def storage(self) -> DatabaseStorage:
        if self._storage is None:
            self._storage = get_storage("sqlite")
        return self._storage

    async def analyze_scene(
        self,
        project_id: str,
        scene_id: str,
        *,
        confirmed: bool,
        force: bool = False,
    ) -> dict[str, Any]:
        if not confirmed:
            raise ValidationError(
                "Creator confirmation is required before external emotion analysis",
                stage="emotion_analysis_confirmation",
            )

        context = self._build_context(project_id, scene_id)
        context_hash = self._context_hash(context)
        if not force:
            cached = self._load_cached(project_id, scene_id, context_hash)
            if cached is not None:
                return self._as_envelope(cached, cached=True, provider_call=False)

        task_key = f"{project_id}:{scene_id}:{context_hash}"
        with self._inflight_guard:
            task = self._inflight.get(task_key)
            owner = task is None
            if task is None:
                task = asyncio.create_task(self._generate_and_persist(context, context_hash))
                self._inflight[task_key] = task
                task.add_done_callback(
                    lambda completed, key=task_key: self._clear_inflight(key, completed)
                )

        record = await asyncio.shield(task)
        return self._as_envelope(
            record,
            cached=not owner,
            provider_call=owner,
        )

    def get_cached_scene(self, project_id: str, scene_id: str) -> dict[str, Any]:
        context = self._build_context(project_id, scene_id)
        context_hash = self._context_hash(context)
        cached = self._load_cached(project_id, scene_id, context_hash)
        if cached is None:
            raise StateError(
                "No current emotion analysis is cached for this scene",
                stage="emotion_analysis_cache_lookup",
                metadata={"project_id": project_id, "scene_id": scene_id},
            )
        return self._as_envelope(cached, cached=True, provider_call=False)

    def _build_context(self, project_id: str, scene_id: str) -> dict[str, Any]:
        project_key = str(project_id or "").strip()
        scene_key = str(scene_id or "").strip()
        if not project_key or not scene_key:
            raise ValidationError(
                "project_id and scene_id are required",
                stage="emotion_analysis_context",
            )

        project = self._project_store.get_project(project_key)
        if not project:
            raise StateError(
                "Project not found",
                stage="emotion_analysis_context",
                metadata={"project_id": project_key},
            )

        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") or []
        scene_index = next(
            (index for index, candidate in enumerate(scenes) if str(candidate.get("scene_id")) == scene_key),
            None,
        )
        if scene_index is None:
            raise StateError(
                "Scene not found in project",
                stage="emotion_analysis_context",
                metadata={"project_id": project_key, "scene_id": scene_key},
            )

        scene = scenes[scene_index]
        memories = self._memory_fetcher(project_key)
        tone_rules = memories.get("tone", []) if isinstance(memories, dict) else []
        settings = get_settings()
        return {
            "prompt_version": PROMPT_VERSION,
            "project_id": project_key,
            "project_title": str(project.get("title") or project_key),
            "scene_id": scene_key,
            "scene_heading": str(scene.get("heading") or scene.get("scene_name") or ""),
            "scene_content": self._scene_content_fetcher(project_key, scene_key),
            "scene_index": scene_index + 1,
            "total_scenes": len(scenes),
            "tone_rules": [str(rule) for rule in tone_rules if str(rule).strip()],
            "primary_model": settings.qwen_llm_model.strip() or "qwen3.7-max",
        }

    @staticmethod
    def _context_hash(context: dict[str, Any]) -> str:
        payload = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_cached(
        self,
        project_id: str,
        scene_id: str,
        context_hash: str,
    ) -> dict[str, Any] | None:
        started = start_timer()
        try:
            return self.storage.get_emotion_analysis_result(project_id, scene_id, context_hash)
        except Exception as exc:
            raise PersistenceError(
                "Emotion analysis cache could not be read",
                stage="emotion_analysis_cache_read",
                metadata={"cause": type(exc).__name__},
            ) from exc
        finally:
            log_stage_event(
                project_id=project_id,
                job_id="",
                provider="sqlite",
                stage="emotion_analysis_cache_read",
                duration_ms=elapsed_ms(started),
            )

    async def _generate_and_persist(
        self,
        context: dict[str, Any],
        context_hash: str,
    ) -> dict[str, Any]:
        project_id = context["project_id"]
        scene_id = context["scene_id"]
        started = start_timer()
        provider = "qwen"
        try:
            raw, provider = await self._llm_completion(
                "You are a film analytics assistant. Return only valid JSON.",
                self._prompt(context),
                max_tokens=512,
                context={"project_id": project_id, "scene_id": scene_id},
            )
            analysis = self._parse(raw, scene_id)
            now = datetime.now(timezone.utc).isoformat()
            record = {
                "analysis_id": f"emotion-{context_hash[:24]}",
                "project_id": project_id,
                "scene_id": scene_id,
                "context_hash": context_hash,
                "provider": provider,
                "model": self._model_for_provider(provider, context["primary_model"]),
                "analysis": analysis,
                "created_at": now,
                "updated_at": now,
            }
            try:
                return self.storage.save_emotion_analysis_result(record)
            except Exception as exc:
                raise PersistenceError(
                    "Emotion analysis result could not be saved",
                    stage="emotion_analysis_cache_write",
                    metadata={"cause": type(exc).__name__},
                ) from exc
        except (ProviderError, PersistenceError):
            raise
        except Exception as exc:
            raise ProviderError(
                "Emotion analysis provider failed",
                stage="emotion_analysis_provider",
                metadata={"cause": type(exc).__name__},
            ) from exc
        finally:
            log_stage_event(
                project_id=project_id,
                job_id="",
                provider=provider,
                stage="emotion_analysis_provider",
                duration_ms=elapsed_ms(started),
            )

    @staticmethod
    def _prompt(context: dict[str, Any]) -> str:
        tone_context = "; ".join(context["tone_rules"]) or "No specific tone rules established"
        return (
            f"Analyze this scene from {context['project_title']} and estimate the likely emotional "
            "response for each audience type on a 0-100 scale.\n\n"
            f"Scene: {context['scene_heading']}\n"
            f"Content: {context['scene_content']}\n"
            f"Position: Scene {context['scene_index']} of {context['total_scenes']}\n"
            f"Tone context: {tone_context}\n\n"
            "Return exactly this JSON shape using numeric values:\n"
            '{"general":{"engagement":N,"tension":N,"emotional_impact":N},'
            '"cinephile":{"engagement":N,"tension":N,"emotional_impact":N},'
            '"genre_fan":{"engagement":N,"tension":N,"emotional_impact":N}}'
        )

    @staticmethod
    def _parse(raw: str, scene_id: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse emotion analysis response: %s", raw[:300])
            raise ProviderError(
                "Emotion analysis provider returned invalid data",
                stage="emotion_analysis_parse",
            ) from exc

        def _metric(value: Any) -> int:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderError(
                    "Emotion analysis provider returned invalid metrics",
                    stage="emotion_analysis_parse",
                )
            return max(0, min(100, int(value)))

        def _group(key: str) -> dict[str, int]:
            group = data.get(key)
            if not isinstance(group, dict):
                raise ProviderError(
                    "Emotion analysis provider returned incomplete data",
                    stage="emotion_analysis_parse",
                )
            return {
                "engagement": _metric(group.get("engagement")),
                "tension": _metric(group.get("tension")),
                "emotional_impact": _metric(group.get("emotional_impact")),
            }

        return {
            "scene_id": scene_id,
            "general": _group("general"),
            "cinephile": _group("cinephile"),
            "genre_fan": _group("genre_fan"),
        }

    @staticmethod
    def _model_for_provider(provider: str, primary_model: str) -> str:
        settings = get_settings()
        if provider == "openrouter":
            return settings.openrouter_llm_model.strip() or "configured-openrouter-model"
        if provider == "groq":
            return str(getattr(settings, "groq_llm_model", "") or "llama-3.3-70b-versatile")
        return primary_model

    @staticmethod
    def _as_envelope(
        record: dict[str, Any],
        *,
        cached: bool,
        provider_call: bool,
    ) -> dict[str, Any]:
        return {**record, "cached": cached, "provider_call": provider_call}

    def _clear_inflight(self, key: str, completed: asyncio.Task[dict[str, Any]]) -> None:
        with self._inflight_guard:
            if self._inflight.get(key) is completed:
                self._inflight.pop(key, None)


emotion_analysis_service = EmotionAnalysisService()
