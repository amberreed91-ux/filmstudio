from typing import Optional, Callable, Awaitable
from datetime import datetime
import os
import uuid
from app.models import (
    RenderJobModel, RenderJobInput, RenderJobOutput, RenderAsset,
    ProviderConfig, ProviderStatus, StudioProject
)
from app.adapters import RenderProviderAdapter, get_adapter, ADAPTER_REGISTRY
from app.services.project_store import project_store
import logging
import asyncio

logger = logging.getLogger("studio-render")

_CONTINUITY_CONTEXT_BLOCK = (
    "\n\n[CINEMATIC CONTEXT]"
    "\nEmotional register: {emotional_register}"
    "\nActive visual motifs: {active_motifs}"
    "\nTonal direction: {tonal_direction}"
    "\nContinuity anchors: {continuity_anchors}"
)

# WebSocket notification callback - will be set by main.py
_job_update_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None

# Database storage reference - will be set by main.py
_storage = None

# Job retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds, exponential backoff
STALE_RENDER_THRESHOLD_SECONDS = 15 * 60


def set_storage(storage):
    """Set the database storage"""
    global _storage
    _storage = storage


def set_job_update_callback(callback: Callable[[str, dict], Awaitable[None]]):
    """Set the WebSocket broadcast callback"""
    global _job_update_callback
    _job_update_callback = callback


async def _run_continuity_review(job: RenderJobModel) -> None:
    """
    Run advisory continuity review after a job completes.
    Attaches result to job.continuity_review and logs outcome.
    Never raises — silent fallback on any error.
    """
    try:
        from app.services.continuity_intelligence_service import (
            continuity_intelligence_service as _cont_svc,
        )
        output_url = ""
        if job.output_payload:
            output_url = str(job.output_payload.asset_url or "").strip()
        # Derive scene_id from shot_id (e.g. "scene_001_shot_001" → "scene_001")
        shot_id = job.shot_id or ""
        scene_id = "_".join(shot_id.split("_")[:2]) if "_" in shot_id else shot_id
        review = await _cont_svc.review_render_output(
            scene_id=scene_id,
            film_id=job.project_id,
            render_job_id=job.id,
            render_output_url=output_url,
            scene_data={},
        )
        job.continuity_review = review
        if review.get("drift_detected"):
            logger.info(
                "CONTINUITY_DRIFT_DETECTED | scene=%s | job=%s | flags=%d",
                scene_id,
                job.id,
                len(review.get("continuity_flags") or []),
            )
        else:
            logger.info(
                "CONTINUITY_REVIEW_PASSED | scene=%s | job=%s",
                scene_id,
                job.id,
            )
    except Exception as exc:
        logger.debug("Continuity review skipped for job %s: %s", job.id, exc)


async def _notify_update(job_id: str, job_data: dict):
    """Notify subscribers of job update"""
    if _job_update_callback:
        try:
            await _job_update_callback(job_id, job_data)
        except Exception as e:
            logger.error(f"Failed to notify job update: {e}")


def _persist_job(job: RenderJobModel):
    """Persist job to database with error handling"""
    if _storage:
        try:
            _storage.save_job(job)
        except Exception as e:
            error_text = str(e)
            if "FOREIGN KEY constraint failed" in error_text:
                parent_project_exists = False
                try:
                    parent_project_exists = _storage.get_project(job.project_id) is not None
                except Exception:
                    parent_project_exists = False
                logger.error(
                    "Render FK failure job_id=%s project_id=%s shot_id=%s parent_project_exists=%s error=%s",
                    job.id,
                    job.project_id,
                    job.shot_id,
                    parent_project_exists,
                    error_text,
                )
                try:
                    project = project_store.get_project(job.project_id)
                    if isinstance(project, dict):
                        from app.models import StudioProject
                        _storage.save_project(
                            StudioProject(
                                project_id=str(project.get("project_id") or job.project_id),
                                title=str(project.get("title") or job.project_id),
                                updated_at=str(project.get("updated_at") or datetime.now().isoformat()),
                            )
                        )
                        _storage.save_job(job)
                        logger.info("Recovered FK persistence for job %s by syncing project %s", job.id, job.project_id)
                        return
                except Exception as retry_exc:
                    logger.error("FK recovery failed for job %s project %s: %s", job.id, job.project_id, retry_exc)
            logger.error(f"Failed to persist job {job.id}: {e}")


def _log_audit(action: str, resource_type: str, resource_id: str, user_id: str = None, details: str = None):
    """Log audit event"""
    if _storage:
        try:
            # Would use storage.audit_log() in production
            logger.info(f"AUDIT: {action} {resource_type}:{resource_id} by {user_id} - {details}")
        except Exception as e:
            logger.error(f"Failed to log audit: {e}")


# ── Prompt-budget constants ─────────────────────────────────────────────────
# Runway (and most video providers) enforce a 512-character prompt limit.
_PROMPT_BUDGET = 512
_CINEMATIC_TAG = "Cinematic, film quality, single continuous shot."


def _extract_visual_action(text: str, max_chars: int = 280) -> str:
    """Extract visual action/description from scene text, stripping dialogue.

    Screenplay format has character names in ALL CAPS on their own line
    followed by dialogue.  Section headers (e.g. ``THE FIRST TIMELINE``)
    are also ALL CAPS but longer.  This helper keeps only the action
    paragraphs that describe what the camera sees — which is all that
    matters for a video-generation prompt.
    """
    import re as _re

    lines = text.split("\n")
    action_parts: list[str] = []
    skip_dialogue = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank line ends dialogue-skip mode
            skip_dialogue = False
            continue

        # ── Character cue detection ──────────────────────────────────────
        # Short ALL-CAPS line that looks like a character name.
        # Strip parentheticals like "(V.O.)" before testing.
        clean = _re.sub(r"\(.*?\)", "", stripped).strip().rstrip(".")
        is_char_cue = (
            len(stripped) < 35
            and len(clean) >= 2
            and clean.replace(" ", "").replace("'", "").isalpha()
            and clean.isupper()
            and not clean.startswith(("THE ", "ACT ", "INT ", "EXT ", "CUT ", "FADE"))
        )
        if is_char_cue:
            skip_dialogue = True
            continue

        # ── Skip dialogue lines following a character cue ────────────────
        if skip_dialogue:
            # Parenthetical stage direction — skip
            if stripped.startswith("(") and stripped.endswith(")"):
                continue
            # Dialogue text — skip (but a new ALL-CAPS cue resets)
            continue

        # ── Section headers (longer ALL-CAPS phrases) — skip ─────────────
        if stripped.isupper() and len(stripped) > 15:
            continue

        action_parts.append(stripped)

    result = " ".join(action_parts)
    if len(result) > max_chars:
        result = result[:max_chars]
        # Truncate at last word boundary for clean cutoff
        last_space = result.rfind(" ")
        if last_space > int(max_chars * 0.6):
            result = result[:last_space]

    return result.strip()


class RenderService:
    """Service for managing render jobs across providers"""

    def __init__(self):
        self._provider_configs: dict[str, ProviderConfig] = {}
        self._jobs: dict[str, RenderJobModel] = {}
        self._submit_locks: set[str] = set()
        # In-memory batch store: batch_id -> batch metadata dict
        self._batches: dict[str, dict] = {}
        self._initialize_providers()

    def _initialize_providers(self):
        """Initialize default provider configurations"""
        runway_api_key = (
            os.getenv("RUNWAYML_API_SECRET", "").strip()
            or os.getenv("RUNWAY_API_KEY", "").strip()
            or os.getenv("VIDEO_PROVIDER_API_KEY", "").strip()
        )
        runway_api_endpoint = os.getenv("RUNWAY_API_BASE_URL", "").strip() or os.getenv("VIDEO_PROVIDER_BASE_URL", "").strip()
        runway_key_source = (
            "RUNWAYML_API_SECRET"
            if os.getenv("RUNWAYML_API_SECRET", "").strip()
            else ("RUNWAY_API_KEY" if os.getenv("RUNWAY_API_KEY", "").strip() else ("VIDEO_PROVIDER_API_KEY" if os.getenv("VIDEO_PROVIDER_API_KEY", "").strip() else "none"))
        )
        logger.info(
            "Runway key source=%s exists=%s length=%s first4=%s last4=%s",
            runway_key_source,
            bool(runway_api_key),
            len(runway_api_key),
            runway_api_key[:4] if runway_api_key else "",
            runway_api_key[-4:] if runway_api_key else "",
        )

        # Runway primary path for active video requests.
        self._provider_configs["runway"] = ProviderConfig(
            provider_id="runway",
            name="Runway",
            enabled=True,
            is_simulated=False,
            api_key=runway_api_key or None,
            api_endpoint=runway_api_endpoint or "https://api.dev.runwayml.com",
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"],
        )

        # Simulated provider remains available fallback.
        self._provider_configs["simulated"] = ProviderConfig(
            provider_id="simulated",
            name="Simulated Provider",
            enabled=True,
            is_simulated=True,
            requires=[],
            capabilities=["video_generation", "image_to_video", "style_transfer"]
        )

        # Local provider for fallback when Runway is not configured
        self._provider_configs["local"] = ProviderConfig(
            provider_id="local",
            name="Local (Simulated)",
            enabled=True,
            is_simulated=True,
            requires=[],
            capabilities=["video_generation", "image_to_video"]
        )

        # Higgsfield placeholder
        self._provider_configs["higgsfield"] = ProviderConfig(
            provider_id="higgsfield",
            name="Higgsfield",
            enabled=False,  # Disabled until API key provided
            is_simulated=False,
            api_key=None,
            api_endpoint=None,
            requires=["api_key"],
            capabilities=["video_generation", "image_to_video"]
        )

        # Generic video provider placeholder
        self._provider_configs["generic"] = ProviderConfig(
            provider_id="generic",
            name="Generic Video Provider",
            enabled=False,
            is_simulated=False,
            api_key=None,
            api_endpoint=None,
            requires=["api_key", "api_endpoint"],
            capabilities=["video_generation"]
        )

        # AMD MI300X ROCm provider for LTX-2 and HunyuanVideo
        self._provider_configs["amd"] = ProviderConfig(
            provider_id="amd",
            name="AMD MI300X",
            enabled=False,
            is_simulated=True,  # Mock for Phase 1
            api_key=None,
            api_endpoint=None,
            requires=["api_key", "api_endpoint"],
            capabilities=["video_generation", "image_to_video"],
            gpu="MI300X",
            runtime="ROCm",
            models=["ltx-2", "hunyuan-video"]
        )

    def list_providers(self) -> list[ProviderStatus]:
        """List all available providers with status"""
        statuses = []
        test_mode = str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()
        for provider_id, config in self._provider_configs.items():
            missing_requirements: list[str] = []
            if "api_key" in config.requires and not (config.api_key or "").strip():
                missing_requirements.append("api_key")
            if "api_endpoint" in config.requires and not (config.api_endpoint or "").strip():
                missing_requirements.append("api_endpoint")

            provider_mode = "hosted_api"
            if provider_id == "runway" and test_mode == "mock_success":
                provider_mode = "mock_success"
            elif config.is_simulated:
                provider_mode = "mock_success"
            elif not config.enabled or missing_requirements:
                provider_mode = "unavailable"

            api_key_configured = "api_key" not in missing_requirements
            ready_for_hosted_generation = bool(
                config.enabled
                and not config.is_simulated
                and api_key_configured
                and not (provider_id == "runway" and test_mode == "mock_success")
            )
            is_mock = provider_mode == "mock_success" or config.is_simulated

            if provider_mode == "mock_success":
                display_label = f"{config.name}: Mock Success Mode"
            elif ready_for_hosted_generation:
                display_label = f"{config.name}: Real provider mode active"
            elif missing_requirements:
                joined = ", ".join(missing_requirements)
                display_label = f"{config.name}: hosted unavailable ({joined} required)"
            elif not config.enabled:
                display_label = f"{config.name}: disabled"
            else:
                display_label = f"{config.name}: unavailable"

            # Add AMD-specific metadata if available
            gpu = getattr(config, 'gpu', None)
            runtime = getattr(config, 'runtime', None)
            models = getattr(config, 'models', [])
            
            # Enhance display label for AMD with ROCm badge
            if provider_id == "amd":
                display_label = f"{config.name}: ROCm / Open Source"
                if missing_requirements:
                    joined = ", ".join(missing_requirements)
                    display_label = f"{config.name}: ROCm / Open Source (hosted unavailable - {joined} required)"
                elif not config.enabled:
                    display_label = f"{config.name}: ROCm / Open Source (disabled)"
            
            statuses.append(ProviderStatus(
                provider_key=provider_id,
                provider_id=provider_id,
                name=config.name,
                status="available" if config.enabled else "disabled",
                is_simulated=config.is_simulated,
                is_mock=is_mock,
                enabled=config.enabled,
                ready_for_hosted_generation=ready_for_hosted_generation,
                api_key_configured=api_key_configured,
                provider_mode=provider_mode,
                missing_requirements=missing_requirements,
                display_label=display_label,
                capabilities=config.capabilities,
                active_jobs=0,
                queued_jobs=0,
                gpu=gpu,
                runtime=runtime,
                models=models
            ))
        return statuses

    def get_provider_config(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get configuration for a provider"""
        return self._provider_configs.get(provider_id)

    def set_provider_config(self, config: ProviderConfig) -> ProviderConfig:
        """Update provider configuration"""
        self._provider_configs[config.provider_id] = config
        return config

    def get_default_provider(self) -> str:
        """Get the default provider based on available API keys"""
        import os
        return "runway" if (os.getenv("RUNWAY_API_KEY") or os.getenv("RUNWAYML_API_SECRET")) else "local"

    async def create_and_submit_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list = None,
        parameters: dict = None
    ) -> RenderJobModel:
        """Create and submit a job in one call"""
        job = self.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        return await self.submit_job(job.id)

    async def create_and_submit_job_with_polling(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None,
        max_polls: int = 3,
        poll_interval: float = 0.25,
    ) -> RenderJobModel:
        """Create and submit a render job with polling for completion"""
        created_job = self.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets,
            parameters=parameters
        )
        submitted_job = await self.submit_job(created_job.id)
        polled_job = submitted_job
        
        for _ in range(max_polls):
            if polled_job.is_terminal():
                break
            await asyncio.sleep(poll_interval)
            polled_job = await self.get_job_status(created_job.id)
            
        return polled_job

    def create_job(
        self,
        project_id: str,
        shot_id: str,
        provider: Optional[str] = None,
        prompt: str = "",
        reference_assets: list[str] = None,
        parameters: dict = None
    ) -> RenderJobModel:
        """Create a new render job with validation"""
        # Validate shot_id is not empty
        if not shot_id or not shot_id.strip():
            raise ValueError("shot_id cannot be empty")

        # ── Per-scene provider override ───────────────────────────────────────
        # If the project has a per-scene override for this shot's scene, use it
        # instead of the caller-supplied provider (unless the caller explicitly
        # passed one, which takes precedence).
        if provider is None:
            try:
                _scene_id_for_override = (
                    "_".join(shot_id.split("_")[:2]) if "_" in shot_id else shot_id
                )
                _project = project_store.get_project(project_id)
                if isinstance(_project, dict):
                    _overrides = _project.get("provider_overrides") or {}
                    if isinstance(_overrides, dict):
                        _override_mode = _overrides.get(_scene_id_for_override)
                        if _override_mode == "hosted_api":
                            # Use the first non-simulated enabled provider.
                            for _pid, _cfg in self._provider_configs.items():
                                if _cfg.enabled and not _cfg.is_simulated:
                                    provider = _pid
                                    break
                        elif _override_mode in ("simulated", "mock_success"):
                            provider = "simulated"
            except Exception:
                pass  # Never block a render due to override lookup failure
        
        # Normalize provider for consistent lookup
        if provider:
            provider = provider.strip().lower()
            if provider == "simulated provider":
                provider = "simulated"
        
        # Validate provider against known providers
        if provider:
            if provider not in self._provider_configs:
                raise ValueError(f"Unknown provider '{provider}'. Available providers: {list(self._provider_configs.keys())}")
        else:
            provider = self.get_default_provider()

        # ── Replace generic prompts with real scene descriptions ──────────────
        # If prompt is generic or too short, fetch the actual scene description
        _scene_id = "_".join(shot_id.split("_")[:2]) if "_" in shot_id else shot_id
        _is_generic = (
            not prompt.strip()
            or len(prompt.strip()) < 50
            or "Generate scene" in prompt
            or "Cinematic quality" in prompt
        )
        
        if _is_generic:
            try:
                _project = project_store.get_project(project_id)
                if isinstance(_project, dict):
                    _summary = _project.get("execution_summary") or {}
                    _scenes = _summary.get("scenes") or []
                    _scene = next(
                        (s for s in _scenes if isinstance(s, dict) and s.get("scene_id") == _scene_id),
                        None
                    )
                    if _scene:
                        _heading = str(_scene.get("heading") or "").strip()
                        # Pull scene text from any of the supported fields so the full
                        # scene block (action lines + dialogue) feeds the render prompt,
                        # not just the heading.
                        _scene_text = (
                            str(_scene.get("text") or "")
                            or str(_scene.get("content") or "")
                            or str(_scene.get("description") or "")
                            or str(_scene.get("scene_text") or "")
                        ).strip()
                        _full_content = f"{_heading}\n{_scene_text}".strip() if _heading else _scene_text
                        _location = str(_scene.get("location") or "").strip()
                        _time_of_day = str(_scene.get("time_of_day") or "").strip()
                        _tone = str(_scene.get("emotional_tone") or "").strip()

                        # Fall back to project-level script_text when the scene record
                        # itself has no content — this keeps the Board from showing
                        # "No description yet" while the script clearly has content.
                        if not _scene_text:
                            try:
                                _script_text = str(_project.get("script_text") or "").strip()
                                if _script_text:
                                    _scene_text = _script_text
                                    _full_content = (
                                        f"{_heading}\n{_scene_text}".strip()
                                        if _heading
                                        else _scene_text
                                    )
                            except Exception:
                                pass

                        if _full_content:
                            # ── Budget-aware prompt assembly ─────────────────
                            # Runway enforces a 512-char prompt limit.  The old
                            # code dumped the entire scene text (often 1000+
                            # chars) into the prompt and truncated at 512, which
                            # dropped character descriptions and the cinematic
                            # quality tag.  The new logic strips dialogue (useless
                            # for video generation), then fits heading + visual
                            # action + character descriptions + cinematic tag
                            # within the budget.

                            # 1. Build character visual descriptions FIRST
                            #    so we can calculate the action text budget
                            #    dynamically — character descriptions get
                            #    priority for remaining space.
                            _char_block = ""
                            try:
                                from app.data.storage import get_storage as _get_storage
                                _active_storage = _get_storage()
                            except Exception:
                                _active_storage = _storage
                            _scene_chars = _scene.get("characters") or []
                            if _scene_chars and _active_storage:
                                _char_summaries: list[str] = []
                                for _char_name in _scene_chars:
                                    _char_name_str = str(_char_name).strip()
                                    if _char_name_str:
                                        _char_record = _active_storage.get_character_by_name(
                                            project_id, _char_name_str
                                        )
                                        if _char_record:
                                            _vps = (
                                                _char_record.get("visual_prompt_summary")
                                                or ""
                                            ).strip()
                                            if _vps:
                                                _char_summaries.append(
                                                    f"{_char_name_str}: {_vps}"
                                                )
                                if _char_summaries:
                                    _char_block = "Characters: " + "; ".join(_char_summaries)
                                    logger.info(
                                        "CHARACTER_PROMPT_INJECTION | scene=%s | chars=%d",
                                        _scene_id,
                                        len(_char_summaries),
                                    )

                            # 2. Calculate action text budget dynamically.
                            #    Reserve space for heading + chars + cinematic tag
                            #    so character descriptions are not truncated when
                            #    the scene text is long.
                            _reserved = len(_CINEMATIC_TAG) + 2  # ". " separator
                            _available = _PROMPT_BUDGET - _reserved
                            _char_reserve = min(len(_char_block), 250) + 2 if _char_block else 0
                            _heading_len = len(_heading or "")
                            _action_budget = _available - _heading_len - _char_reserve - 6  # separators
                            _action_budget = max(100, min(280, _action_budget))

                            # 3. Extract visual action (strip dialogue)
                            _action_text = _extract_visual_action(
                                _scene_text, max_chars=_action_budget
                            ) if _scene_text else ""

                            # 4. Assemble prompt in priority order within budget
                            #    Priority: heading > action > characters > cinematic tag
                            #    The cinematic tag is always reserved.

                            def _smart_sep(parts: list[str]) -> str:
                                """Return '. ' or ' ' to avoid double periods."""
                                if not parts:
                                    return ""
                                last = parts[-1].rstrip()
                                if last.endswith((".", "!", "?")):
                                    return " "
                                return ". "

                            # Start with heading
                            _prompt_parts: list[str] = []
                            _used = 0

                            if _heading:
                                _prompt_parts.append(_heading)
                                _used += len(_heading)

                            # Add location if not already in heading
                            _loc_suffix = ""
                            if _location and _location.lower() not in (_heading or "").lower():
                                _loc_suffix = f"Location: {_location}"

                            # Add action text
                            if _action_text:
                                _sep = _smart_sep(_prompt_parts)
                                _action_piece = f"{_sep}{_action_text}"
                                if _used + len(_action_piece) <= _available:
                                    _prompt_parts.append(_action_piece)
                                    _used += len(_action_piece)
                                else:
                                    # Truncate action to fit
                                    _room = _available - _used - len(_sep)
                                    if _room > 40:
                                        _truncated = _action_text[:_room]
                                        _last_sp = _truncated.rfind(" ")
                                        if _last_sp > int(_room * 0.6):
                                            _truncated = _truncated[:_last_sp]
                                        _prompt_parts.append(f"{_sep}{_truncated}")
                                        _used += len(_sep) + len(_truncated)

                            # Add location suffix if it fits
                            if _loc_suffix:
                                _sep = _smart_sep(_prompt_parts)
                                _piece = f"{_sep}{_loc_suffix}"
                                if _used + len(_piece) <= _available:
                                    _prompt_parts.append(_piece)
                                    _used += len(_piece)

                            # Add time of day
                            if _time_of_day:
                                _sep = _smart_sep(_prompt_parts)
                                _piece = f"{_sep}{_time_of_day}"
                                if _used + len(_piece) <= _available:
                                    _prompt_parts.append(_piece)
                                    _used += len(_piece)

                            # Add mood/tone
                            if _tone:
                                _sep = _smart_sep(_prompt_parts)
                                _piece = f"{_sep}Mood: {_tone}"
                                if _used + len(_piece) <= _available:
                                    _prompt_parts.append(_piece)
                                    _used += len(_piece)

                            # Add character descriptions if they fit
                            if _char_block:
                                _sep = _smart_sep(_prompt_parts)
                                _piece = f"{_sep}{_char_block}"
                                if _used + len(_piece) <= _available:
                                    _prompt_parts.append(_piece)
                                    _used += len(_piece)
                                else:
                                    # Truncate character block to fit
                                    _room = _available - _used - len(_sep)
                                    if _room > 30:
                                        _truncated = _char_block[:_room]
                                        _last_sp = _truncated.rfind(" ")
                                        if _last_sp > int(_room * 0.5):
                                            _truncated = _truncated[:_last_sp]
                                        _prompt_parts.append(f"{_sep}{_truncated}")
                                        _used += len(_sep) + len(_truncated)

                            # Always append cinematic tag (reserved space)
                            _sep = _smart_sep(_prompt_parts)
                            _prompt_parts.append(f"{_sep}{_CINEMATIC_TAG}")

                            prompt = "".join(_prompt_parts)

                            # Hard safety cap at provider limit
                            if len(prompt) > _PROMPT_BUDGET:
                                prompt = prompt[:_PROMPT_BUDGET - 3] + "..."

                            logger.info(
                                "RENDER_PROMPT_FROM_SCENE | scene=%s | content_length=%d | action_length=%d | prompt_length=%d",
                                _scene_id,
                                len(_full_content),
                                len(_action_text),
                                len(prompt),
                            )
            except Exception as _exc:
                logger.warning("Failed to fetch scene description for prompt: %s", _exc)
        
        job_id = f"job-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}-{shot_id}"
        
        job = RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=prompt,
                referenceAssets=reference_assets or [],
                parameters=parameters or {}
            ),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )

        # ── Character visual description injection (non-generic prompts) ──────
        # For prompts that already have content (e.g., from Previs Room's
        # Generation Settings panel with duration/fps/resolution/seed), inject
        # character visual descriptions so the video provider generates the
        # correct character appearance.  This mirrors the storyboard/Pollinations
        # fix but for the video render path.  Generic prompts are already
        # handled by the block above; this covers the Previs Room render path.
        if not _is_generic:
            try:
                from app.data.storage import get_storage as _get_storage
                _active_storage = _get_storage()
                _project = project_store.get_project(project_id)
                _scene_chars: list[str] = []
                if isinstance(_project, dict):
                    _summary = _project.get("execution_summary") or {}
                    _scenes = _summary.get("scenes") or []
                    _scene = next(
                        (s for s in _scenes if isinstance(s, dict) and s.get("scene_id") == _scene_id),
                        None,
                    )
                    if _scene:
                        _scene_chars = list(_scene.get("characters") or [])
                        # If no characters array, try to identify from scene text
                        if not _scene_chars:
                            try:
                                _all_chars = _active_storage.get_characters(project_id)
                                _scene_text_lower = (
                                    str(_scene.get("text") or "")
                                    or str(_scene.get("content") or "")
                                    or str(_scene.get("description") or "")
                                    or str(_scene.get("scene_text") or "")
                                ).lower()
                                for _char in _all_chars:
                                    _char_name = _char.get("name", "")
                                    if _char_name and _char_name.lower() in _scene_text_lower:
                                        _scene_chars.append(_char_name)
                            except Exception:
                                pass

                if _scene_chars and _active_storage:
                    _char_summaries: list[str] = []
                    for _char_name in _scene_chars:
                        _char_name_str = str(_char_name).strip()
                        if _char_name_str:
                            _char_record = _active_storage.get_character_by_name(
                                project_id, _char_name_str
                            )
                            if _char_record:
                                _vps = (
                                    _char_record.get("visual_prompt_summary")
                                    or ""
                                ).strip()
                                if _vps:
                                    _char_summaries.append(
                                        f"{_char_name_str}: {_vps}"
                                    )
                    if _char_summaries:
                        _char_block = "Characters: " + "; ".join(_char_summaries)
                        _current_prompt = job.input_payload.prompt or ""
                        # Skip if characters already present (e.g., generic prompt path)
                        if "Characters:" not in _current_prompt:
                            _sep = ". " if not _current_prompt.rstrip().endswith((".", "!", "?")) else " "
                            _new_prompt = f"{_current_prompt}{_sep}{_char_block}"
                            # If over budget, truncate original prompt to fit characters
                            if len(_new_prompt) > _PROMPT_BUDGET:
                                _char_len = len(_sep) + len(_char_block)
                                _orig_budget = _PROMPT_BUDGET - _char_len
                                if _orig_budget > 50:
                                    _truncated_orig = _current_prompt[:_orig_budget]
                                    _last_sp = _truncated_orig.rfind(" ")
                                    if _last_sp > int(_orig_budget * 0.6):
                                        _truncated_orig = _truncated_orig[:_last_sp]
                                    _new_prompt = f"{_truncated_orig}{_sep}{_char_block}"
                                else:
                                    # Not enough room for both; prioritize characters
                                    _new_prompt = _char_block[:_PROMPT_BUDGET]
                            job.input_payload.prompt = _new_prompt
                            logger.info(
                                "CHARACTER_PROMPT_INJECTION | scene=%s | chars=%d | source=previs_prompt",
                                _scene_id,
                                len(_char_summaries),
                            )
            except Exception as _exc:
                logger.debug("Character injection for non-generic prompt skipped: %s", _exc)

        # ── Continuity context injection ──────────────────────────────────────
        # Derive scene_id from shot_id (e.g. "scene_001_shot_001" → "scene_001").
        # film_id is the project_id — they are the same identifier here.
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            from app.utils.director_intent_injection import build_director_intent_prefix
            from app.data.storage import get_storage
            
            _scene_id = "_".join(shot_id.split("_")[:2]) if "_" in shot_id else shot_id
            _ctx = _cont_svc.build_prompt_context(scene_id=_scene_id, film_id=project_id)
            _has_context = bool(
                _ctx.get("emotional_register")
                or _ctx.get("active_motifs")
                or _ctx.get("tonal_direction")
                or _ctx.get("continuity_anchors")
            )
            
            # Build director intent prefix
            _storage = get_storage()
            _intent = _storage.load_director_intent(project_id)
            _intent_prefix = build_director_intent_prefix(_intent)
            
            # Prepend director intent if it exists
            if _intent_prefix:
                job.input_payload.prompt = _intent_prefix + (job.input_payload.prompt or "")
                logger.info("DIRECTOR_INTENT_INJECTION | project=%s", project_id)
            
            # Append continuity context if it exists
            if _has_context:
                _motifs = _ctx["active_motifs"]
                _anchors = _ctx["continuity_anchors"]
                _block = _CONTINUITY_CONTEXT_BLOCK.format(
                    emotional_register=_ctx["emotional_register"] or "unspecified",
                    active_motifs=", ".join(_motifs) if _motifs else "none",
                    tonal_direction=_ctx["tonal_direction"] or "unspecified",
                    continuity_anchors=", ".join(_anchors) if _anchors else "none",
                )
                job.input_payload.prompt = (job.input_payload.prompt or "") + _block
                job.continuity_context_injected = True
                logger.info(
                    "CONTINUITY_PROMPT_INJECTION | scene=%s | motifs=%d | anchors=%d",
                    _scene_id,
                    len(_motifs),
                    len(_anchors),
                )
        except Exception as _exc:  # never block a render
            logger.debug("Continuity context injection skipped: %s", _exc)

        # Diagnostic logging for provider status
        config = self._provider_configs.get(provider)
        runway_api_key = (
            os.getenv("RUNWAYML_API_SECRET", "").strip()
            or os.getenv("RUNWAY_API_KEY", "").strip()
        )
        test_mode = str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()
        use_mock_success = bool(parameters and parameters.get("use_mock_success"))
        
        # Calculate ready_for_hosted_generation for this provider
        missing_requirements = []
        if config and "api_key" in config.requires and not (config.api_key or "").strip():
            missing_requirements.append("api_key")
        
        ready_for_hosted = bool(
            config
            and config.enabled
            and not config.is_simulated
            and not missing_requirements
            and not (provider == "runway" and test_mode == "mock_success")
            and not use_mock_success
        )
        
        logger.info(
            "RENDER_JOB_CREATED | job_id=%s | provider=%s | hosted=%s | key_present=%s | test_mode=%s | use_mock=%s | missing=%s",
            job_id,
            provider,
            ready_for_hosted,
            bool(runway_api_key),
            test_mode or "none",
            use_mock_success,
            missing_requirements or "none"
        )
        
        # Log final prompt to verify description is included
        final_prompt = job.input_payload.prompt or ""
        logger.info(
            "FINAL_RENDER_PROMPT | scene=%s | prompt=%s",
            _scene_id,
            final_prompt[:150]
        )

        self._jobs[job_id] = job
        _persist_job(job)
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        """Submit a job to its provider with error handling"""
        job = self._jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for submission")
            raise ValueError(f"Job {job_id} not found")
        if job_id in self._submit_locks:
            logger.info("Duplicate submit blocked for %s", job_id)
            return job
        if job.status in {"rendering", "complete"}:
            logger.info("Submit skipped for %s because status=%s", job_id, job.status)
            return job
        if job.status == "failed" and job.retry_count >= MAX_RETRIES:
            raise ValueError(f"Job {job_id} exceeded max retries")
        self._submit_locks.add(job_id)

        try:
            config = self._provider_configs.get(job.provider)
            if not config:
                config = self._provider_configs["simulated"]
                job.provider = "simulated"
                logger.warning(f"Provider {job.provider} not found, falling back to simulated")

            adapter = get_adapter(job.provider, config)
            logger.info(f"Submitting job {job_id} to provider {job.provider}")

            # ── Seed locking: generate on first render, reuse on subsequent ──
            try:
                if _storage:
                    shot_seed = _storage.get_shot_seed(job.project_id, job.shot_id)
                    if shot_seed and shot_seed.get("seed") is not None:
                        seed_val = int(shot_seed["seed"])
                        logger.info(
                            "SEED_REUSED | job=%s | shot=%s | seed=%d | locked=%s",
                            job_id, job.shot_id, seed_val,
                            bool(shot_seed.get("seed_locked")),
                        )
                    else:
                        seed_val = int.from_bytes(os.urandom(4), byteorder="big", signed=False) % (2**31)
                        _storage.save_shot_seed(job.project_id, job.shot_id, seed_val)
                        logger.info(
                            "SEED_GENERATED | job=%s | shot=%s | seed=%d",
                            job_id, job.shot_id, seed_val,
                        )
                    if job.input_payload and job.input_payload.parameters:
                        job.input_payload.parameters["seed"] = seed_val
                    elif job.input_payload:
                        job.input_payload.parameters = {"seed": seed_val}
            except Exception as _exc:
                logger.debug("Seed injection skipped for %s: %s", job_id, _exc)
            
            job.recovery_status = "active"
            submitted_job = await adapter.submit_job(job)
            
            # Ensure provider is set on the returned job
            if not submitted_job.provider or submitted_job.provider.strip() == "":
                submitted_job.provider = job.provider
                logger.info(f"Provider field set to {job.provider} for job {job_id}")
            
            submitted_job.recovery_status = "active"
            submitted_job.updated_at = datetime.now().isoformat()
            
            self._jobs[job_id] = submitted_job
            _persist_job(submitted_job)
            _log_audit("submit_job", "render_job", job_id, details=f"provider={submitted_job.provider}")
            
            await _notify_update(job_id, submitted_job.model_dump())
            return submitted_job
            
        except Exception as e:
            logger.error(f"Failed to submit job {job_id}: {e}")
            job.status = "failed"
            job.error_message = str(e)
            job.updated_at = datetime.now().isoformat()
            self._jobs[job_id] = job
            _persist_job(job)
            raise
        finally:
            self._submit_locks.discard(job_id)

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        """Get job status with storage fallback, caching, and recovery

        For non-terminal jobs, delegates to the provider adapter so simulated
        providers can progress through stages (pending → rendering → complete).
        """
        job = self._jobs.get(job_id)
        if not job and _storage:
            job = _storage.get_job(job_id)
            if job:
                self._jobs[job_id] = job

        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Delegate to adapter for live status on non-terminal jobs
        if not job.is_terminal():
            try:
                config = self._provider_configs.get(job.provider)
                if config:
                    adapter = get_adapter(job.provider, config)
                    updated = await adapter.get_job_status(job)
                    updated.updated_at = datetime.now().isoformat()
                    self._jobs[job_id] = updated
                    _persist_job(updated)
                    if updated.status != job.status:
                        await _notify_update(job_id, updated.model_dump())
                    return updated
            except Exception as _exc:
                logger.debug("Adapter status poll failed for %s: %s", job_id, _exc)

        # Safeguard: if a job reports "complete" but has no output URL, demote to "failed"
        # so the UI doesn't show false COMPLETE badges with no playable video.
        if job.status == "complete":
            has_url = (
                job.output_payload
                and isinstance(job.output_payload.asset_url, str)
                and job.output_payload.asset_url.strip()
            )
            if not has_url:
                logger.warning(
                    "JOB_COMPLETE_WITHOUT_URL | job=%s | project=%s | shot=%s | demoting to failed",
                    job.id, job.project_id, job.shot_id,
                )
                job.status = "failed"
                job.error_message = "Job completed without output URL"
                self._jobs[job_id] = job
                _persist_job(job)

        return job

    def delete_job(self, job_id: str) -> bool:
        """Delete a render job record from both memory and storage."""
        existed = job_id in self._jobs
        self._jobs.pop(job_id, None)
        if _storage:
            try:
                _storage.delete_job(job_id)
            except Exception as e:
                logger.error(f"Failed to delete job {job_id} from storage: {e}")
        return existed

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        job = self._jobs.get(job_id)
        if not job:
            return False

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        result = await adapter.cancel_job(job)
        
        if result:
            job.status = "cancelled"
            job.updated_at = datetime.now().isoformat()
            self._jobs[job_id] = job
            _persist_job(job)
            await _notify_update(job_id, job.model_dump())
        
        return result

    async def retry_job(self, job_id: str) -> RenderJobModel:
        """Retry a failed job"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.retry_count += 1
        job.status = "pending"
        job.error_message = None
        job.recovery_status = "retrying"
        job.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = job
        _persist_job(job)
        
        return await self.submit_job(job_id)

    async def retry_with_continuity_context(
        self,
        job_id: str,
        film_id: str,
        scene_id: str,
    ) -> dict:
        """
        Retry a failed render job with a graph-informed prompt adjustment.

        Keeps the original shot description unchanged, replaces the previous
        continuity context block with a fresh one (the graph may have been
        updated since the original render), and appends a retry note that
        highlights the dominant motif or emotional register.

        Caps retries at 3.  When the cap is reached, returns the failed job
        unchanged with retry_advisory set.

        Args:
            job_id:   The ID of the failed job to retry.
            film_id:  The film/project identifier (used for graph lookup).
            scene_id: The scene identifier (used for context lookup).

        Returns:
            dict with the new job (or the original job when cap is reached),
            plus an "advisory" key.
        """
        MAX_RETRIES = 3

        # ── Load the failed job ───────────────────────────────────────────────
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        current_retry_count = job.retry_count or 0

        # ── Enforce cap ───────────────────────────────────────────────────────
        if current_retry_count >= MAX_RETRIES:
            advisory = "Maximum retries reached. Manual review recommended."
            job.retry_advisory = advisory
            self._jobs[job_id] = job
            _persist_job(job)
            return {
                "job": job.model_dump(),
                "advisory": advisory,
                "capped": True,
            }

        # ── Load fresh continuity context ─────────────────────────────────────
        fresh_context: dict = {}
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            fresh_context = _cont_svc.build_prompt_context(
                scene_id=scene_id,
                film_id=film_id,
            )
        except Exception as _exc:
            logger.debug("Continuity context unavailable for retry %s: %s", job_id, _exc)

        # ── Strip old context blocks from the original prompt ─────────────────
        original_prompt = ""
        if job.input_payload and job.input_payload.prompt:
            original_prompt = job.input_payload.prompt

        # Remove any existing [CINEMATIC CONTEXT] and [SHOT POSITION] blocks
        # so we can replace them with fresh ones.
        clean_prompt = original_prompt
        for marker in ("[CINEMATIC CONTEXT]", "[SHOT POSITION]", "[RETRY CONTEXT]"):
            if marker in clean_prompt:
                clean_prompt = clean_prompt[: clean_prompt.index(marker)].rstrip()

        # ── Build fresh context block ─────────────────────────────────────────
        _motifs = fresh_context.get("active_motifs") or []
        _anchors = fresh_context.get("continuity_anchors") or []
        _has_ctx = bool(
            fresh_context.get("emotional_register")
            or _motifs
            or fresh_context.get("tonal_direction")
            or _anchors
        )
        fresh_block = ""
        if _has_ctx:
            fresh_block = _CONTINUITY_CONTEXT_BLOCK.format(
                emotional_register=fresh_context.get("emotional_register") or "unspecified",
                active_motifs=", ".join(_motifs) if _motifs else "none",
                tonal_direction=fresh_context.get("tonal_direction") or "unspecified",
                continuity_anchors=", ".join(_anchors) if _anchors else "none",
            )

        # ── Build retry note ──────────────────────────────────────────────────
        # Use dominant_motif from motif analysis if available, else emotional_register.
        priority_signal = ""
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc2,
            )
            motif_analysis = _cont_svc2.get_motif_thread_analysis(film_id)
            priority_signal = motif_analysis.get("dominant_motif") or ""
        except Exception:
            pass
        if not priority_signal:
            priority_signal = fresh_context.get("emotional_register") or "established visual language"

        retry_note = (
            f"\n\n[RETRY CONTEXT]"
            f"\nPrevious attempt failed. "
            f"Prioritize: {priority_signal}. "
            f"Keep composition consistent with established visual language."
        )

        new_prompt = clean_prompt + fresh_block + retry_note

        # ── Create new job ────────────────────────────────────────────────────
        new_job = self.create_job(
            project_id=film_id,
            shot_id=job.shot_id,
            provider=job.provider,
            prompt=new_prompt,
            reference_assets=list(job.input_payload.referenceAssets or []),
            parameters=dict(job.input_payload.parameters or {}),
        )
        new_job.retry_of = job_id
        new_job.retry_count = current_retry_count + 1
        new_job.batch_id = job.batch_id  # preserve batch membership
        self._jobs[new_job.id] = new_job
        _persist_job(new_job)

        # Submit the new job.
        try:
            submitted = await self.submit_job(new_job.id)
        except Exception as _exc:
            logger.warning("Retry job %s submit failed: %s", new_job.id, _exc)
            submitted = new_job

        advisory = (
            f"Retry {current_retry_count + 1} of {MAX_RETRIES} submitted "
            f"with fresh continuity context."
        )
        return {
            "job": submitted.model_dump(),
            "advisory": advisory,
            "capped": False,
        }

    def _get_jobs_by_status(self, statuses: list[str]) -> list[RenderJobModel]:
        """Get all jobs matching any of the given statuses"""
        return [job for job in self._jobs.values() if job.status in statuses]

    def get_job(self, job_id: str) -> Optional[RenderJobModel]:
        """Get a job by ID"""
        job = self._jobs.get(job_id)
        if job:
            return job
        if _storage:
            job = _storage.get_job(job_id)
            if job:
                self._jobs[job_id] = job
            return job
        return None

    def list_jobs(self, project_id: Optional[str] = None) -> list[RenderJobModel]:
        """List all jobs, optionally filtered by project.
        
        In-memory jobs take priority over persisted ones — this ensures
        the output_payload from a just-completed job (e.g. simulated provider)
        is not overwritten by a stale DB record that hasn't been updated yet.
        """
        jobs_by_id: dict[str, RenderJobModel] = {}

        # Always load persisted jobs first as the baseline.
        if _storage:
            try:
                persisted = _storage.list_jobs(project_id=project_id, limit=5000)
                for job in persisted:
                    jobs_by_id[job.id] = job
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to load persisted jobs for list_jobs: %s", exc)

        # Then overlay in-memory jobs — these have the freshest state.
        for job in self._jobs.values():
            jobs_by_id[job.id] = job

        jobs = list(jobs_by_id.values())
        if project_id:
            jobs = [j for j in jobs if j.project_id == project_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def get_job_outputs(self, job_id: str) -> list[RenderAsset]:
        """Get outputs for a completed job"""
        job = self.get_job(job_id)
        if not job:
            return []

        config = self._provider_configs.get(job.provider)
        if not config:
            config = self._provider_configs["simulated"]

        adapter = get_adapter(job.provider, config)
        return await adapter.fetch_outputs(job)

    async def reconcile_completed_runway_task(self, job_id: str) -> RenderJobModel:
        """Reconcile a runway job against upstream Runway task status.

        Works for any job status (pending, rendering, complete, failed):
        - If task succeeded: attach output_url and mark complete
        - If task still running/pending: preserve running state with clear status
        - If task failed: preserve structured failure
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.provider != "runway":
            return job

        task_id = job.provider_job_id
        if not task_id and job.output_payload and isinstance(job.output_payload.metadata, dict):
            normalized = job.output_payload.metadata.get("provider_response_normalized") or {}
            metadata = normalized.get("metadata") if isinstance(normalized, dict) else {}
            if isinstance(metadata, dict):
                task_id = metadata.get("task_id")

        if not isinstance(task_id, str) or not task_id.strip():
            return job

        job.provider_job_id = task_id.strip()
        config = self._provider_configs.get("runway")
        if not config:
            return job

        adapter = get_adapter("runway", config)
        updated = await adapter.get_job_status(job)
        updated.last_polled_at = datetime.now().isoformat()
        updated.updated_at = updated.last_polled_at

        if updated.status == "complete":
            # Safeguard: verify the completed job has an output URL before persisting
            has_url = (
                updated.output_payload
                and isinstance(updated.output_payload.asset_url, str)
                and updated.output_payload.asset_url.strip()
            )
            if not has_url:
                logger.warning(
                    "RECONCILE_COMPLETE_WITHOUT_URL | job=%s | project=%s | shot=%s | demoting to failed",
                    job_id, job.project_id, job.shot_id,
                )
                updated.status = "failed"
                updated.error_message = "Reconciled job completed without output URL"
                updated.recovery_status = "recovery_failed"
                self._jobs[job_id] = updated
                _persist_job(updated)
                return updated

            normalized = (
                ((updated.output_payload or RenderJobOutput(asset_url="", thumbnail_url="", metadata={})).metadata or {})
                .get("provider_response_normalized", {})
            )
            if isinstance(normalized, dict):
                output = normalized.get("output") if isinstance(normalized.get("output"), dict) else {}
                metadata = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}
                output["status"] = "completed"
                normalized["output"] = output
                metadata["provider_status"] = "completed"
                normalized["metadata"] = metadata
                if updated.output_payload:
                    updated.output_payload.metadata["provider_response_normalized"] = normalized
            updated.recovery_status = "orphan_reconciled"
            if not updated.completed_at:
                updated.completed_at = updated.last_polled_at

            await _run_continuity_review(updated)
            self._jobs[job_id] = updated
            _persist_job(updated)
            await _notify_update(job_id, updated.model_dump())
            return updated

        if updated.status == "failed":
            updated.recovery_status = "recovery_failed"
        elif updated.is_terminal():
            updated.recovery_status = "recovered_terminal"
        else:
            updated.recovery_status = "active"
        self._jobs[job_id] = updated
        _persist_job(updated)
        await _notify_update(job_id, updated.model_dump())
        return updated

    async def refresh_output_url(self, job_id: str) -> Optional[str]:
        """Refresh an expired hosted output URL from the upstream Runway task."""
        job = self.get_job(job_id)
        if not job or job.provider != "runway" or not job.provider_job_id:
            return None

        config = self._provider_configs.get("runway")
        if not config:
            return None

        adapter = get_adapter("runway", config)
        refreshed = await adapter.get_job_status(job)
        fresh_url = ""
        if refreshed.output_payload:
            fresh_url = str(refreshed.output_payload.asset_url or "").strip()
            if not fresh_url and isinstance(refreshed.output_payload.metadata, dict):
                normalized = refreshed.output_payload.metadata.get("provider_response_normalized")
                if isinstance(normalized, dict):
                    output = normalized.get("output")
                    if isinstance(output, dict):
                        fresh_url = str(output.get("video_url") or "").strip()

        if not fresh_url:
            return None

        refreshed.output_payload = refreshed.output_payload or RenderJobOutput(asset_url=fresh_url, thumbnail_url=None, metadata={})
        refreshed.output_payload.asset_url = fresh_url
        refreshed.updated_at = datetime.now().isoformat()
        self._jobs[job_id] = refreshed
        _persist_job(refreshed)
        await _notify_update(job_id, refreshed.model_dump())
        return fresh_url

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @classmethod
    def _is_stale(cls, job: RenderJobModel) -> bool:
        baseline = cls._parse_iso(job.last_polled_at) or cls._parse_iso(job.updated_at) or cls._parse_iso(job.created_at)
        if baseline is None:
            return False
        return (datetime.now(baseline.tzinfo) - baseline).total_seconds() >= STALE_RENDER_THRESHOLD_SECONDS

    async def create_scene_batch(
        self,
        film_id: str,
        scene_id: str,
        scene_data: dict,
        shots: list,
        provider: Optional[str] = None,
    ) -> dict:
        """
        Create a coordinated batch of render jobs for all shots in a scene.

        Calls build_prompt_context() once for the scene so every shot in the
        batch shares the same visual continuity context.  Each shot also
        receives a position note (opening / continuation / closing) so the
        provider understands its role in the sequence.

        Jobs are created in order and submitted in parallel.

        Args:
            film_id:    The film/project identifier.
            scene_id:   The scene identifier.
            scene_data: Scene metadata dict (description, emotional_tone, etc.).
            shots:      Ordered list of shot dicts.  Each dict should contain at
                        least a ``shot_id`` and optionally ``description``,
                        ``camera``, ``prompt``.
            provider:   Optional provider override; falls back to default.

        Returns:
            {
                "batch_id":       str,
                "scene_id":       str,
                "job_ids":        list[str],
                "shared_context": dict,   # continuity context applied to all shots
                "status":         "pending"
            }
        """
        import uuid as _uuid

        batch_id = f"batch-{_uuid.uuid4().hex[:16]}"
        total = len(shots)

        # ── Build shared continuity context once for the whole scene ─────────
        shared_context: dict = {}
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service as _cont_svc,
            )
            shared_context = _cont_svc.build_prompt_context(
                scene_id=scene_id,
                film_id=film_id,
            )
        except Exception as _exc:
            logger.debug("Batch shared context unavailable for scene %s: %s", scene_id, _exc)

        # ── Build the shared context block string ─────────────────────────────
        _motifs = shared_context.get("active_motifs") or []
        _anchors = shared_context.get("continuity_anchors") or []
        _has_ctx = bool(
            shared_context.get("emotional_register")
            or _motifs
            or shared_context.get("tonal_direction")
            or _anchors
        )
        shared_context_block = ""
        if _has_ctx:
            shared_context_block = _CONTINUITY_CONTEXT_BLOCK.format(
                emotional_register=shared_context.get("emotional_register") or "unspecified",
                active_motifs=", ".join(_motifs) if _motifs else "none",
                tonal_direction=shared_context.get("tonal_direction") or "unspecified",
                continuity_anchors=", ".join(_anchors) if _anchors else "none",
            )

        # ── Create one job per shot ───────────────────────────────────────────
        job_ids: list[str] = []
        for index, shot in enumerate(shots):
            shot_id = str(shot.get("shot_id") or f"{scene_id}_shot_{index + 1:03d}")
            base_prompt = str(
                shot.get("prompt")
                or shot.get("description")
                or shot.get("visual_description")
                or ""
            ).strip()
            camera = str(shot.get("camera") or shot.get("camera_notes") or "").strip()
            if camera:
                base_prompt = f"{base_prompt}. Camera: {camera}".strip(". ")

            # Shot position note
            if total == 1:
                position_note = "Single shot — establish the space and carry the full emotional register."
            elif index == 0:
                position_note = f"Shot 1 of {total} in scene. Opening shot — establish the space."
            elif index == total - 1:
                position_note = f"Shot {index + 1} of {total} in scene. Closing shot — carry emotional register forward."
            else:
                position_note = f"Shot {index + 1} of {total} in scene. Continuation — maintain visual consistency with prior shot."

            full_prompt = base_prompt
            if shared_context_block:
                full_prompt = full_prompt + shared_context_block
            full_prompt = full_prompt + f"\n\n[SHOT POSITION]\n{position_note}"

            job = self.create_job(
                project_id=film_id,
                shot_id=shot_id,
                provider=provider,
                prompt=full_prompt,
                reference_assets=shot.get("reference_assets") or [],
                parameters=shot.get("parameters") or {},
            )
            # Tag the job with the batch_id
            job.batch_id = batch_id
            self._jobs[job.id] = job
            _persist_job(job)
            job_ids.append(job.id)

        # ── Submit all jobs in parallel ───────────────────────────────────────
        submit_tasks = [self.submit_job(jid) for jid in job_ids]
        results = await asyncio.gather(*submit_tasks, return_exceptions=True)
        for jid, result in zip(job_ids, results):
            if isinstance(result, Exception):
                logger.warning("Batch job %s submit failed: %s", jid, result)

        # ── Store batch metadata ──────────────────────────────────────────────
        batch = {
            "batch_id": batch_id,
            "scene_id": scene_id,
            "film_id": film_id,
            "job_ids": job_ids,
            "shared_context": shared_context,
            "status": "pending",
        }
        self._batches[batch_id] = batch
        logger.info(
            "SCENE_BATCH_CREATED | batch=%s | scene=%s | shots=%d",
            batch_id, scene_id, total,
        )
        return batch

    def get_batch_status(self, batch_id: str) -> Optional[dict]:
        """
        Return the current status of a render batch.

        Counts jobs by terminal state and returns a summary.

        Args:
            batch_id: The batch identifier.

        Returns:
            {
                "batch_id":  str,
                "scene_id":  str,
                "total":     int,
                "complete":  int,
                "pending":   int,
                "failed":    int,
                "jobs":      list[dict]
            }
            or None if the batch_id is not found.
        """
        batch = self._batches.get(batch_id)
        if not batch:
            return None

        job_dicts: list[dict] = []
        complete = pending = failed = 0
        for jid in batch["job_ids"]:
            job = self.get_job(jid)
            if job:
                d = job.model_dump()
                job_dicts.append(d)
                if job.status == "complete":
                    complete += 1
                elif job.status in ("failed", "cancelled"):
                    failed += 1
                else:
                    pending += 1
            else:
                pending += 1

        return {
            "batch_id": batch_id,
            "scene_id": batch.get("scene_id", ""),
            "total": len(batch["job_ids"]),
            "complete": complete,
            "pending": pending,
            "failed": failed,
            "jobs": job_dicts,
        }

    async def recover_jobs_after_restart(self) -> dict:
        """Recover rendering/pending jobs and reconcile orphaned provider tasks after restart."""
        recovered = 0
        stale_recovered = 0
        orphan_reconciled = 0
        errors: list[str] = []

        for job in list(self._jobs.values()):
            try:
                if job.status in {"pending", "rendering"}:
                    if not job.provider_job_id and self._is_stale(job):
                        job.status = "failed"
                        job.error_message = "Stale job with no provider task id after restart"
                        job.recovery_status = "stale_recovered"
                        job.updated_at = datetime.now().isoformat()
                        _persist_job(job)
                        stale_recovered += 1
                        continue
                    if job.provider_job_id:
                        config = self._provider_configs.get(job.provider) or self._provider_configs.get("simulated")
                        adapter = get_adapter(job.provider, config)
                        updated = await adapter.get_job_status(job)
                        updated.updated_at = datetime.now().isoformat()
                        if updated.status == "complete" and not updated.completed_at:
                            updated.completed_at = updated.updated_at
                        if updated.status == "complete":
                            updated.recovery_status = "recovered_terminal"
                            await _run_continuity_review(updated)
                        elif updated.is_terminal():
                            updated.recovery_status = "recovery_failed"
                        else:
                            updated.recovery_status = "active"
                        self._jobs[job.id] = updated
                        _persist_job(updated)
                        if self._is_stale(updated) and not updated.is_terminal():
                            updated.status = "failed"
                            updated.error_message = "Stale job — exceeded render timeout after restart"
                            updated.recovery_status = "stale_recovered"
                            updated.updated_at = datetime.now().isoformat()
                            _persist_job(updated)
                            stale_recovered += 1
                        recovered += 1

                if job.status == "failed" and job.provider == "runway" and job.provider_job_id:
                    updated = await self.reconcile_completed_runway_task(job.id)
                    if updated.status == "complete":
                        orphan_reconciled += 1
            except Exception as exc:
                errors.append(f"{job.id}: {exc}")

        return {
            "recovered_jobs": recovered,
            "stale_recovered_jobs": stale_recovered,
            "orphan_reconciled_jobs": orphan_reconciled,
            "error_count": len(errors),
            "errors": errors,
        }

    async def poll_active_runway_jobs(self) -> None:
        """
        Background loop that polls Runway for all jobs in incomplete states.
        Runs every 10 seconds. Never raises — logs errors and continues.
        """
        POLL_STATUSES = ["queued", "pending", "rendering", "processing", "submitted"]
        logger.info("POLLING_LOOP_STARTED | interval=10s | statuses=%s", POLL_STATUSES)
        
        while True:
            try:
                active_jobs = self._get_jobs_by_status(POLL_STATUSES)
                logger.info("POLLING_CYCLE | checking=%d jobs", len(active_jobs))

                for job in active_jobs:
                    try:
                        # Hard timeout: any active job older than threshold is stuck
                        created = self._parse_iso(job.created_at)
                        if created and (datetime.now(created.tzinfo) - created).total_seconds() >= STALE_RENDER_THRESHOLD_SECONDS:
                            job.status = "failed"
                            job.error_message = "Stale job — exceeded render timeout"
                            job.recovery_status = "stale_recovered"
                            job.updated_at = datetime.now().isoformat()
                            self._jobs[job.id] = job
                            _persist_job(job)
                            logger.info("POLLING_STALE_CANCEL | job=%s | provider=%s", job.id, job.provider)
                            continue
                        if job.provider == "runway":
                            await self.reconcile_completed_runway_task(job.id)
                    except Exception as e:
                        logger.debug("Polling error for job %s: %s", job.id, e)
            except Exception as e:
                logger.error("Polling loop error: %s", e)
            await asyncio.sleep(10)


# Global service instance
render_service = RenderService()


def backfill_render_jobs_from_project_state() -> dict:
    """Backfill canonical render_jobs rows from project_state_store.json."""
    if _storage is None:
        return {
            "created_count": 0,
            "skipped_count": 0,
            "created_job_ids": [],
            "skipped_job_ids": [],
            "errors": ["Render job storage is not initialized"],
        }

    from app.services.render_job_backfill import (
        backfill_render_jobs_from_project_state as _backfill_render_jobs_from_project_state,
    )

    result = _backfill_render_jobs_from_project_state(
        storage=_storage,
        render_service=render_service,
    )
    return {
        **result,
        "backfilled_count": result.get("created_count", 0),
        "already_exists_count": result.get("skipped_count", 0),
        "errors": result.get("errors", []),
    }
