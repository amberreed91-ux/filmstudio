from __future__ import annotations

from datetime import datetime
import logging
from time import perf_counter
from typing import Any

from app.data.storage import StorageInterface, get_storage
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.models.previs_render import PrevisRenderSettings, PrevisDurationOptions
from app.prompt_assembly_context import preserve_generation_facts
from app.services.storyboard_render_inputs import storyboard_render_inputs, append_shot_handoff
from app.services.render import RenderService, render_service
from app.services.shot_prompt_builder import build_shot_aware_prompt, get_shot_type_label
from app.services.stability import PersistenceError, ProviderError, StateError, ValidationError


logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"queued", "pending", "submitted", "generating", "processing", "rendering", "retrying"}
TERMINAL_STATUSES = {"complete", "approved", "failed", "cancelled", "superseded", "rejected", "needs_review"}

_build_generation_prompt = preserve_generation_facts(build_shot_aware_prompt)


class PrevisService:
    # Cost protection: automatic generation stops before a paid call when the
    # estimated cost exceeds these limits (credits). Zero disables the limit.
    MAX_COST_PER_GENERATION_CREDITS = 0
    MAX_DAILY_GENERATION_BUDGET_CREDITS = 0

    def __init__(
        self,
        storage: StorageInterface | None = None,
        renderer: RenderService | None = None,
    ):
        self._storage = storage
        self._renderer = renderer or render_service

    def _enforce_cost_limit(
        self,
        project_id: str,
        provider: str,
        parameters: dict[str, Any],
        user_model: str,
    ) -> None:
        """Stop automatic generation when the estimated cost exceeds limits.

        Delegates to the SHARED cost gate (generation_cost_gate) so the previs
        and batch paths cannot drift: one implementation of credit protection.
        The estimate comes from the model registry's published per-second
        rates. No automatic spend loop exists anywhere in Studio; when a limit
        is configured and hit, the caller must explicitly confirm by raising
        the limit — never by retrying.
        """
        from app.services.generation_cost_gate import generation_cost_gate

        generation_cost_gate.enforce_shot_limit(project_id, provider, parameters, user_model)

    @staticmethod
    def _resolve_execution_provider(provider: str) -> str:
        """Keep the Runway operator alias on the frozen Model Router path."""
        selected = str(provider or "").strip().lower()
        return "runway_router" if selected == "runway" else selected

    def duration_options(self, provider: str = "") -> PrevisDurationOptions:
        requested = provider.strip().lower()
        if requested in {"openrouter", "openrouter-video"}:
            raise ValidationError(
                f"Video provider '{requested}' is retired and cannot be used for Previs generation",
                stage="previs_settings",
                metadata={"provider": requested},
            )
        if requested:
            resolved = requested
        elif hasattr(self._renderer, "get_default_provider"):
            try:
                resolved = self._renderer.get_default_provider()
            except ValueError as exc:
                raise ValidationError(str(exc), stage="previs_settings") from exc
        else:
            resolved = "runway"
        if resolved in {"openrouter", "openrouter-video"}:
            raise ValidationError(
                f"Video provider '{resolved}' is retired and cannot be used for Previs generation",
                stage="previs_settings",
                metadata={"provider": resolved},
            )
        if resolved in {"happyhorse", "happyhorse-r2v"}:
            durations = list(range(3, 16))
        elif resolved == "wan":
            durations = [5, 10, 15]
        else:
            durations = [4, 8, 12, 16, 20]
        return PrevisDurationOptions(provider=resolved, valid_durations_seconds=durations)

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise PersistenceError("Storage not configured", stage="previs_storage")
        return storage

    def _project_data(self, project_id: str) -> dict[str, Any]:
        if not str(project_id or "").strip():
            raise ValidationError("project_id is required", stage="previs_ownership")
        try:
            project = self._require_storage().get_project(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Previs project lookup failed",
                stage="previs_ownership",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if project is None:
            raise StateError("Project not found", stage="previs_ownership")
        data = project.model_dump(mode="json") if hasattr(project, "model_dump") else project
        if not isinstance(data, dict) or data.get("project_id") != project_id:
            raise StateError("Project not found", stage="previs_ownership")
        return data

    def _scenes(self, project_id: str) -> list[dict[str, Any]]:
        project = self._project_data(project_id)
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("scene_id") or "").strip()]

    def _scene(self, project_id: str, scene_id: str) -> dict[str, Any]:
        if not str(scene_id or "").strip():
            raise ValidationError("scene_id is required", stage="previs_ownership")
        for scene in self._scenes(project_id):
            if scene.get("scene_id") == scene_id:
                return scene
        raise StateError("Scene not found in project", stage="previs_ownership")

    def _storyboard_context(self, project_id: str, scene_id: str, storyboard_shot_id: str) -> dict[str, Any]:
        storage = self._require_storage()
        shot = storage.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.project_id != project_id or shot.scene_id != scene_id:
            raise StateError("Storyboard shot not found in project scene", stage="previs_storyboard_reference")
        blueprint = storage.get_storyboard_blueprint_by_id(shot.blueprint_id)
        version = storage.get_storyboard_blueprint_version(shot.version_id)
        if (
            blueprint is None
            or version is None
            or blueprint.project_id != project_id
            or blueprint.scene_id != scene_id
            or version.blueprint_id != blueprint.blueprint_id
        ):
            raise StateError("Storyboard provenance is invalid", stage="previs_storyboard_reference")
        if (
            blueprint.approved_version_id != version.version_id
            or blueprint.current_version_id != version.version_id
            or version.status != StoryboardBlueprintStatus.APPROVED
        ):
            raise StateError("Previs requires an approved storyboard version", stage="previs_storyboard_reference")
        prompt = str(shot.render_contract.provider_neutral_prompt or "").strip()
        if not prompt:
            raise ValidationError("Storyboard shot has no render prompt", stage="previs_storyboard_reference")
        # P0-3: a corrupted approved prompt must never become generation input.
        # Fail closed with the artifact named; regeneration/re-approval is the
        # only path forward. Never silently repaired here.
        from app.services.prompt_integrity import detect_prompt_corruption

        corruption = detect_prompt_corruption(prompt, source="BOARD")
        if corruption:
            raise ValidationError(
                "Generation blocked: the approved storyboard prompt is corrupted. "
                + " ".join(corruption),
                stage="prompt_integrity",
                metadata={
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "version_id": shot.version_id,
                    "issues": corruption,
                },
            )
        inputs = storyboard_render_inputs(shot)
        return {
            "shot": shot,
            "blueprint": blueprint,
            "version": version,
            "prompt": inputs["prompt"],
            "reference_assets": inputs["reference_assets"],
            "parameters": inputs["parameters"],
        }

    async def generate_scene(
        self,
        project_id: str,
        scene_id: str,
        shot_number: int = 1,
        take_number: int = 1,
        *,
        storyboard_shot_id: str | None = None,
        allow_approved_revision: bool = False,
        source_previs_image_id: str | None = None,
        attempt_number: int = 1,
        provider: str | None = None,
        render_settings: PrevisRenderSettings | None = None,
    ) -> dict:
        started = perf_counter()
        requested_provider = str(provider or "").strip().lower()
        # R4.3L (Policy A, additive): the legacy previs path rejects
        # Runway-family providers before any job exists. Mirrors the
        # canonical generate_previs fail-closed structure; every other
        # provider value falls through unchanged. The standalone
        # runway_router guard below is untouched.
        if requested_provider in {"runway", "runway_router", "runway_direct"}:
            raise ValidationError(
                "Runway is not used for previs; use simulated previs (instant, no cost). "
                "Runway video generation requires the canonical scene pipeline's READY frozen contract; "
                "the standalone Previs path cannot authorize a mutable request.",
                stage="previs_generate",
                metadata={"rejected_provider": requested_provider, "code": "legacy_previs_runway_rejected"},
            )
        if requested_provider in {"openrouter", "openrouter-video"}:
            raise ValidationError(
                f"Video provider '{requested_provider}' is retired and cannot be used for Previs generation",
                stage="previs_generate",
                metadata={"provider": requested_provider},
            )
        if shot_number < 1 or take_number < 1:
            raise ValidationError("shot_number and take_number must be positive", stage="previs_generate")

        # Resolve this boundary before touching existing Previs state (including
        # superseding/cancelling an active take). Runway must enter through the
        # canonical scene pipeline, which owns READY and the frozen contract.
        requested = requested_provider
        provider_configs = getattr(self._renderer, "_provider_configs", None)
        if requested:
            if isinstance(provider_configs, dict) and requested not in provider_configs:
                raise ValidationError("Unknown render provider", stage="previs_generate")
            render_provider = requested
        elif hasattr(self._renderer, "get_default_provider"):
            try:
                render_provider = self._renderer.get_default_provider()
            except ValueError as exc:
                raise ValidationError(str(exc), stage="previs_generate") from exc
        else:
            render_provider = "runway"
        render_provider = self._resolve_execution_provider(render_provider)
        if render_provider == "runway_router":
            raise ValidationError(
                "Runway video generation requires the canonical scene pipeline's READY frozen contract; "
                "the standalone Previs path cannot authorize a mutable request.",
                stage="generation_readiness",
                metadata={"required_provider": "runway_router", "required_contract": "frozen_generation_contract"},
            )

        storage = self._require_storage()
        scene = self._scene(project_id, scene_id)
        if not storyboard_shot_id:
            blueprint = storage.get_storyboard_blueprint(project_id, scene_id)
            if blueprint is not None:
                shots = storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id)
                selected = next((shot for shot in shots if shot.shot_number == shot_number), None)
                if selected is None:
                    raise StateError("Requested shot is missing from the current storyboard", stage="previs_storyboard_reference")
                storyboard_shot_id = selected.storyboard_shot_id
        storyboard = (
            self._storyboard_context(project_id, scene_id, storyboard_shot_id)
            if storyboard_shot_id
            else None
        )
        if storyboard:
            shot = storyboard["shot"]
            shot_id = shot.shot_id
            prompt = storyboard["prompt"]
            reference_assets = storyboard["reference_assets"]
            blueprint_id = shot.blueprint_id
            blueprint_version_id = shot.version_id
            shot_number = shot.shot_number
        else:
            try:
                characters = storage.get_characters(project_id)
            except Exception as exc:
                raise PersistenceError(
                    "Previs character reference lookup failed",
                    stage="previs_prompt_context",
                    metadata={"cause": type(exc).__name__},
                ) from exc
            # total_shots is left to resolve_total_shots, which reads shot_count /
            # shots off the execution_summary scene dict. Previs has no separate
            # shot list of its own, and the scene dict is the authoritative count.
            prompt = _build_generation_prompt(
                scene_data=scene,
                shot_number=shot_number,
                take_number=take_number,
                all_characters=[item for item in characters if isinstance(item, dict)],
                audio_brief=None,
                max_length=512,
            )
            shot_id = f"{scene_id}_shot_{shot_number:03d}_take_{take_number}"
            reference_assets = []
            try:
                from app.services.shot_prompt_builder import locked_appearance_characters
                from app.utils.character_appearance import appearance_approval

                for _char in locked_appearance_characters(
                    [item for item in characters if isinstance(item, dict)]
                )[:3]:
                    for _field in ("face_image_url", "body_image_url"):
                        try:
                            _url = str(appearance_approval(_char).get(_field) or "").strip()
                        except Exception:
                            _url = ""
                        if _url and _url not in reference_assets:
                            reference_assets.append(_url)
                        if len(reference_assets) >= 3:
                            break
                    if len(reference_assets) >= 3:
                        break
            except Exception:
                pass
            blueprint_id = None
            blueprint_version_id = None

        parameters = dict(storyboard["parameters"] if storyboard else {"duration": 3, "ratio": "1280:720"})
        if render_settings is not None:
            if render_settings.prompt is not None:
                prompt = render_settings.prompt
            explicit_planning = {key: value.strip() for key, value in render_settings.shot_planning.items() if value.strip()}
            if explicit_planning:
                prompt += "\n\n[CREATOR SHOT DIRECTIONS]\n" + "\n".join(f"{key}: {value}" for key, value in explicit_planning.items())
                parameters["creator_shot_planning"] = explicit_planning
            for field, key in (("duration_seconds", "duration"), ("resolution", "resolution"), ("seed", "seed"), ("visual_model_id", "visual_model_id")):
                value = getattr(render_settings, field)
                if value is not None:
                    parameters[key] = value
            parameters["strict_render_settings"] = True
            if render_settings.prompt is not None or explicit_planning:
                parameters["preserve_shot_prompt"] = True
        # Frontend sends a stale editable copy of the Step-1 plan (promptText)
        # that predates later look approvals. Re-attach current locked looks
        # server-side so Step 1 planning + locks always reach the render,
        # whether or not the board version is approved yet.
        try:
            from app.services.shot_prompt_builder import ensure_locked_appearance_in_prompt

            try:
                _fresh_characters = storage.get_characters(project_id)
            except Exception:
                _fresh_characters = []
            prompt = ensure_locked_appearance_in_prompt(prompt, _fresh_characters, scene)
        except Exception:
            pass
        prompt = append_shot_handoff(prompt, parameters.get("continuity_handoff") or {})
        parameters.update(previs=True, blueprint_id=blueprint_id,
                          blueprint_version_id=blueprint_version_id, storyboard_shot_id=storyboard_shot_id)
        parameters.update(shot_number=shot_number, take_number=take_number)

        existing = storage.load_previs_images(project_id, scene_id)
        target_key = storyboard_shot_id or shot_id
        matching = [
            image for image in existing
            if (image.get("storyboard_shot_id") or image.get("shot_id")) == target_key
        ]
        active = next((image for image in matching if image.get("status") in ACTIVE_STATUSES), None)
        if active:
            fresh_requested = bool(render_settings is not None and render_settings.fresh_render)
            if not fresh_requested:
                active_take = int((active.get("metadata") or {}).get("take_number") or take_number)
                return self._generation_response(active, shot_number, active_take, duplicate=True)
            # Fresh Render: the user explicitly asked for a new generation
            # context, so an active job for this shot is superseded rather
            # than silently reused. The old job and its outputs stay in the
            # project history (The Vault) — nothing is deleted.
            try:
                active_job_id = str(active.get("job_id") or "")
                if active_job_id:
                    cancelled = self._renderer.cancel_job(active_job_id)
                    logger.info(
                        "FRESH_RENDER_SUPERSEDED_ACTIVE | project_id=%s | job_id=%s | cancelled=%s",
                        project_id, active_job_id, cancelled,
                    )
            except Exception as exc:  # noqa: BLE001 — supersede is best-effort; never block the fresh render
                logger.warning(
                    "FRESH_RENDER_SUPERSEDE_FAILED | project_id=%s | job_id=%s | cause=%s",
                    project_id, active.get("job_id"), type(exc).__name__,
                )
        approved = next((image for image in matching if image.get("approved")), None)
        if approved and not allow_approved_revision:
            raise StateError(
                "Approved Previs is protected; explicitly request a revision",
                stage="previs_generate",
                metadata={"previs_image_id": approved["id"]},
            )

        if render_provider in {"happyhorse", "happyhorse-r2v", "wan"}:
            options = self.duration_options(render_provider)
            duration = parameters.get("duration")
            if duration is not None and duration not in options.valid_durations_seconds:
                logger.warning(
                    "project_id=%s job_id=- provider=%s stage=previs_settings duration_ms=%d",
                    project_id, render_provider, int((perf_counter() - started) * 1000),
                )
                raise ValidationError(
                    f"{render_provider} cannot render {duration} seconds. Choose one of: "
                    + ", ".join(str(value) for value in options.valid_durations_seconds)
                    + " seconds.",
                    stage="previs_settings",
                    metadata={"provider": render_provider, "valid_durations_seconds": options.valid_durations_seconds},
                )

        if render_provider in {"openrouter", "openrouter-video"}:
            raise ValidationError(
                f"Video provider '{render_provider}' is retired and cannot be used for Previs generation",
                stage="previs_generate",
                metadata={"provider": render_provider},
            )

        # ── Model routing (registry-backed) ─────────────────────────────────
        # A user-selected model is authoritative and is never replaced; an
        # incompatible selection blocks the render with the capability conflict
        # named. "auto"/omitted routes over verified registry capabilities.
        user_model = str(render_settings.model or "").strip() if render_settings is not None else ""
        if user_model and user_model.lower() != "auto":
            parameters["model"] = user_model
        elif render_provider == "runway_router":
            parameters.pop("model", None)  # let the Router select an eligible model

        # ── Generation readiness gate (fresh render protection) ────────────
        # Build the versioned generation context from CURRENT authoritative
        # state and validate the camera provenance before any provider call.
        # Stale or unapproved input blocks here, honestly, with the reason.
        from app.services.generation_context_service import generation_context_service

        # P0-1: the shot version MUST come from the canonical shot record,
        # never from frontend state and never as a stub. When an approved
        # board exists the shot is MANDATORY: ``_storyboard_context`` already
        # failed closed above if it could not be resolved/renderable. When no
        # board exists at all, the legacy scene-text previs path has no
        # canonical shot row — the absent axis is recorded explicitly in the
        # context metadata rather than silently stubbed.
        current_shot = storyboard["shot"] if storyboard else None
        shot_axis_required = current_shot is not None

        camera_instructions = generation_context_service.derive_camera_instructions(
            creator_planning=parameters.get("creator_shot_planning"),
            storyboard_shot=current_shot,
        )
        context = generation_context_service.create_generation_context(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            scene=scene,
            storyboard_context=storyboard,
            reference_assets=reference_assets,
            camera_instructions=camera_instructions,
            prompt_source="USER_EDITED" if (render_settings is not None and render_settings.prompt is not None) else ("BOARD" if storyboard else "DERIVED"),
            shot=current_shot,
            require_shot_version=shot_axis_required,
        )
        if not shot_axis_required:
            context.metadata["shot_version_source"] = "no_storyboard_context"
        readiness = generation_context_service.validate_generation_context(
            context=context,
            current_scene=scene,
            current_storyboard_context=storyboard,
            current_reference_assets=reference_assets,
            expected_scene_id=scene_id,
            expected_shot_id=shot_id,
            current_shot=current_shot,
        )
        if not readiness.ready:
            raise ValidationError(
                "Generation blocked: " + " ".join(readiness.blockers),
                stage="generation_readiness",
                metadata={"blockers": readiness.blockers, "generation_context_id": context.generation_context_id},
            )
        # The passing gate's context id is recorded with the job by
        # RenderService.create_job (job.metadata.generation_context) — it must
        # NOT enter parameters, which feed stable request/idempotency hashing
        # and must stay byte-identical across a retry of the same take.

        # ── Cost protection ────────────────────────────────────────────────
        # Estimate the credit cost from the registry's published rates and
        # stop before a paid call when it exceeds the configured limit. There
        # is deliberately no automatic retry loop around this.
        from app.services.generation_cost_gate import generation_cost_gate

        generation_cost_gate.enforce_shot_limit(project_id, render_provider, parameters, user_model)

        try:
            job = self._renderer.create_job(
                project_id=project_id,
                shot_id=shot_id,
                provider=render_provider,
                prompt=prompt,
                reference_assets=reference_assets,
                parameters=parameters,
            )
        except (ValidationError, StateError):
            raise
        except Exception as exc:
            raise ProviderError(
                "Unable to create Previs render job",
                stage="previs_job_create",
                metadata={"cause": type(exc).__name__},
            ) from exc

        image_id = f"previs_{project_id}_{scene_id}_{job.id}"
        try:
            storage.save_previs_image(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=shot_id,
                image_path="",
                job_id=job.id,
                status="queued",
                prompt_used=prompt,
                fallback=False,
                image_id=image_id,
                blueprint_id=blueprint_id,
                blueprint_version_id=blueprint_version_id,
                storyboard_shot_id=storyboard_shot_id,
                source_previs_image_id=source_previs_image_id,
                attempt_number=attempt_number,
                metadata={
                    "shot_number": shot_number,
                    "take_number": take_number,
                    "reference_assets": reference_assets,
                    "scene_context": scene,
                    "render_provider": render_provider,
                    "render_settings": render_settings.model_dump(exclude_none=True) if render_settings else None,
                    "render_parameters": parameters,
                },
            )
        except Exception as exc:
            raise PersistenceError(
                "Unable to persist Previs job before submission",
                stage="previs_job_persist",
                metadata={"job_id": job.id, "cause": type(exc).__name__},
            ) from exc

        try:
            submitted = await self._renderer.submit_job(job.id)
            submitted_status = str(getattr(submitted, "status", "pending") or "pending")
            if submitted_status == "complete":
                output = getattr(submitted, "output_payload", None)
                asset_url = str(getattr(output, "asset_url", "") or "").strip()
                if not asset_url:
                    storage.update_previs_image_status(
                        job.id,
                        "failed",
                        failure_reason="Provider completed without an output asset",
                    )
                    raise ProviderError(
                        "Previs provider completed without an output asset",
                        stage="previs_submit",
                        metadata={"job_id": job.id, "provider": render_provider},
                    )
                persisted_status = "complete"
                storage.update_previs_image_status(job.id, persisted_status, image_path=asset_url)
            elif submitted_status == "needs_review":
                persisted_status = "needs_review"
                storage.update_previs_image_status(job.id, persisted_status, failure_reason=str(getattr(submitted, "error_message", "") or "Review required shot facts before rendering"))
            elif submitted_status in {"failed", "cancelled"}:
                reason = str(getattr(submitted, "error_message", "") or f"Provider job {submitted_status}")
                storage.update_previs_image_status(job.id, submitted_status, failure_reason=reason)
                raise ProviderError(
                    f"Could not render this take: {reason}",
                    stage="previs_submit",
                    metadata={"job_id": job.id, "provider": render_provider, "status": submitted_status},
                )
            else:
                persisted_status = submitted_status if submitted_status in ACTIVE_STATUSES else "pending"
                storage.update_previs_image_status(job.id, persisted_status)
        except ProviderError:
            raise
        except Exception as exc:
            storage.update_previs_image_status(
                job.id,
                "failed",
                failure_reason="Provider submission failed",
            )
            raise ProviderError(
                "Previs provider submission failed",
                stage="previs_submit",
                metadata={"job_id": job.id, "provider": render_provider, "cause": type(exc).__name__},
            ) from exc

        logger.info(
            "project_id=%s job_id=%s provider=%s stage=previs_submit duration_ms=%d",
            project_id,
            job.id,
            render_provider,
            int((perf_counter() - started) * 1000),
        )
        record = storage.get_previs_image(image_id)
        return self._generation_response(record or {"job_id": job.id, "status": persisted_status, "scene_id": scene_id}, shot_number, take_number)

    async def list_scene_images(
        self,
        project_id: str,
        scene_id: str,
        *,
        use_video_url_fallback: bool,
    ) -> list[dict]:
        self._scene(project_id, scene_id)
        storage = self._require_storage()
        images = storage.load_previs_images(project_id, scene_id)
        for image in images:
            if image["status"] not in ACTIVE_STATUSES:
                continue
            try:
                job = await self._renderer.get_job_status(image["job_id"])
            except Exception as exc:
                raise ProviderError(
                    "Previs provider status check failed",
                    stage="previs_poll",
                    metadata={"job_id": image["job_id"], "cause": type(exc).__name__},
                ) from exc
            status = str(job.status or "pending")
            if status == "complete":
                asset_url = str(
                    job.output_payload.asset_url
                    if job.output_payload and job.output_payload.asset_url
                    else ""
                ).strip()
                if not asset_url:
                    storage.update_previs_image_status(
                        image["job_id"], "failed", failure_reason="Provider completed without an output asset"
                    )
                    image["status"] = "failed"
                    image["failure_reason"] = "Provider completed without an output asset"
                else:
                    storage.update_previs_image_status(image["job_id"], "complete", image_path=asset_url)
                    image["status"] = "complete"
                    image["image_path"] = asset_url
                    if use_video_url_fallback:
                        logger.info(
                            "project_id=%s job_id=%s provider=%s stage=previs_frame_fallback duration_ms=0",
                            project_id,
                            job.id,
                            getattr(job, "provider", ""),
                        )
            elif status in {"failed", "cancelled", "needs_review"}:
                reason = str(getattr(job, "error_message", "") or f"Provider job {status}")
                storage.update_previs_image_status(image["job_id"], status, failure_reason=reason)
                image["status"] = status
                image["failure_reason"] = reason
            else:
                normalized = status if status in ACTIVE_STATUSES else "processing"
                storage.update_previs_image_status(image["job_id"], normalized)
                image["status"] = normalized
        return images

    def get_image(self, project_id: str, image_id: str) -> dict[str, Any]:
        image = self._require_storage().get_previs_image(image_id)
        if image is None or image["project_id"] != project_id:
            raise StateError("Previs image not found", stage="previs_get")
        return image

    def approve_image(self, project_id: str, image_id: str, approved_by: str = "creator") -> dict[str, Any]:
        self.get_image(project_id, image_id)
        try:
            approved = self._require_storage().approve_previs_image(image_id, project_id, approved_by)
        except ValueError as exc:
            raise StateError(str(exc), stage="previs_approve") from exc
        if approved is None:
            raise StateError("Previs image not found", stage="previs_approve")
        return approved

    def approve_ai_camera(
        self,
        project_id: str,
        scene_id: str,
        storyboard_shot_id: str,
        approved_by: str = "creator",
        expected_version_id: str | None = None,
    ) -> dict[str, Any]:
        """Explicitly approve the board shot's AI-suggested camera values (P0-2).

        This is the ONLY path from AI_SUGGESTED to renderable camera data. It
        records the user's approval durably on the current board shot by
        writing the creator camera plan provenance that
        ``derive_camera_instructions`` requires before stamping APPROVED.
        A new board version is created first because an approved board is
        immutable — approval is a deliberate edit with an audit trail, never a
        silent mutation of approved state.

        ``expected_version_id`` binds the decision to the exact board version
        the creator saw when preparing it. When given and the shot no longer
        belongs to that version (superseded, re-drafted, or otherwise changed),
        the approval is refused instead of being applied to another version.
        """
        storage = self._require_storage()
        from app.services.generation_context_service import (
            AI_CAMERA_APPROVAL_PROVENANCE,
            pending_ai_camera_suggestions,
        )
        from app.services.storyboard_blueprint_service import storyboard_blueprint_service

        shot = storage.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.project_id != project_id or shot.scene_id != scene_id:
            raise StateError("Storyboard shot not found in project scene", stage="previs_camera_approval")

        # Stale-version protection: the creator is approving what they saw on
        # one specific version. Never re-target the decision onto a version
        # they were not shown.
        if expected_version_id is not None and str(shot.version_id or "") != str(expected_version_id):
            raise StateError(
                "Camera approval refused: this shot no longer belongs to the "
                "board version the decision was prepared against",
                stage="previs_camera_approval",
                metadata={
                    "expected_version_id": str(expected_version_id),
                    "shot_version_id": str(shot.version_id or ""),
                },
            )

        # The pending AI suggestion view is the read-only authority for what
        # approval may lock: non-empty visual-plan values that are NOT already
        # written by a creator camera plan (edit-grammar excluded). Passing
        # ``derive_camera_instructions(storyboard_shot=…)`` alone would find
        # nothing — P0-2 deliberately holds pending suggestions out of the
        # instruction list, so the approval flow reads this view instead.
        ai_values = pending_ai_camera_suggestions(shot)
        if not ai_values:
            raise StateError(
                "No AI-suggested camera values are pending approval for this shot",
                stage="previs_camera_approval",
            )

        service = storyboard_blueprint_service
        if service.storage is not storage:
            service = type(service)(storage)
        blueprint = storage.get_storyboard_blueprint_by_id(shot.blueprint_id)
        if blueprint is not None and blueprint.approved_version_id == shot.version_id:
            # Approved boards are immutable: approval creates a new draft
            # version (history preserved) and the plan lands on the clone.
            service.create_version(
                blueprint_id=shot.blueprint_id,
                change_reason="ai_camera_approval",
                preserve_locked_shots=True,
            )
            # Re-read the blueprint AFTER create_version: the clone shots live
            # on the version create_version just minted, not on the snapshot
            # taken before it.
            fresh_blueprint = storage.get_storyboard_blueprint_by_id(shot.blueprint_id)
            current_version_id = str(getattr(fresh_blueprint, "current_version_id", "") or "")
            clones = storage.list_storyboard_shots(shot.blueprint_id, current_version_id) if current_version_id else []
            shot = next(
                (item for item in clones if item.shot_id == shot.shot_id),
                None,
            )
            if shot is None:
                raise StateError(
                    "Camera approval failed: the approved shot clone could not be "
                    "resolved on the new draft version",
                    stage="previs_camera_approval",
                )
        if shot.locked:
            raise StateError("Storyboard shot is locked", stage="previs_camera_approval")

        approved_plan = dict(ai_values)
        updated = service.update_shot(
            blueprint_id=shot.blueprint_id,
            storyboard_shot_id=shot.storyboard_shot_id,
            render_contract={
                "structured_parameters": {
                    **(shot.render_contract.structured_parameters or {}),
                    "camera_plan": approved_plan,
                }
            },
            change_reason=f"{AI_CAMERA_APPROVAL_PROVENANCE}:{approved_by}",
        )
        return {
            "storyboard_shot_id": updated.storyboard_shot_id,
            "version_id": updated.version_id,
            "approved_camera": approved_plan,
            "approved_by": approved_by,
        }

    async def cancel_image(self, project_id: str, image_id: str) -> dict[str, Any]:
        image = self.get_image(project_id, image_id)
        if image["status"] not in ACTIVE_STATUSES:
            raise StateError("Only active Previs jobs can be cancelled", stage="previs_cancel")
        try:
            cancelled = await self._renderer.cancel_job(image["job_id"])
        except Exception as exc:
            raise ProviderError(
                "Previs provider cancellation failed",
                stage="previs_cancel",
                metadata={"job_id": image["job_id"], "cause": type(exc).__name__},
            ) from exc
        if not cancelled:
            raise StateError("Previs job could not be cancelled", stage="previs_cancel")
        self._require_storage().update_previs_image_status(image["job_id"], "cancelled")
        return self.get_image(project_id, image_id)

    async def retry_image(self, project_id: str, image_id: str) -> dict[str, Any]:
        image = self.get_image(project_id, image_id)
        if image["approved"]:
            raise StateError("Approved Previs cannot be retried", stage="previs_retry")
        if image["status"] not in {"failed", "cancelled"}:
            raise StateError("Only failed or cancelled Previs can be retried", stage="previs_retry")
        metadata = image.get("metadata") or {}
        return await self.generate_scene(
            project_id,
            image["scene_id"],
            int(metadata.get("shot_number") or 1),
            int(metadata.get("take_number") or 1),
            storyboard_shot_id=image.get("storyboard_shot_id"),
            allow_approved_revision=False,
            source_previs_image_id=image["id"],
            attempt_number=int(image.get("attempt_number") or 1) + 1,
            provider=metadata.get("render_provider"),
            render_settings=PrevisRenderSettings.model_validate(metadata["render_settings"]) if metadata.get("render_settings") else None,
        )

    def create_production_package(self, project_id: str, scene_id: str) -> dict[str, Any]:
        self._scene(project_id, scene_id)
        storage = self._require_storage()
        blueprint = storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None or not blueprint.approved_version_id:
            raise StateError("Approved storyboard version is required", stage="previs_package")
        version = storage.get_storyboard_blueprint_version(blueprint.approved_version_id)
        if version is None or version.status != StoryboardBlueprintStatus.APPROVED:
            raise StateError("Approved storyboard version is invalid", stage="previs_package")
        shots = storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)
        approved_images = [
            image for image in storage.load_previs_images(project_id, scene_id)
            if image.get("approved") and image.get("blueprint_version_id") == version.version_id
        ]
        approved_by_shot = {image.get("storyboard_shot_id"): image for image in approved_images}
        missing = [shot.storyboard_shot_id for shot in shots if shot.storyboard_shot_id not in approved_by_shot]
        if missing:
            raise StateError(
                "Every storyboard shot requires approved Previs before packaging",
                stage="previs_package",
                metadata={"missing_storyboard_shot_ids": missing},
            )
        payload = {
            "upstream": {
                "blueprint_id": blueprint.blueprint_id,
                "blueprint_version_id": version.version_id,
            },
            "shots": [
                {
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "shot_id": shot.shot_id,
                    "previs_image_id": approved_by_shot[shot.storyboard_shot_id]["id"],
                    "previs_job_id": approved_by_shot[shot.storyboard_shot_id]["job_id"],
                    "image_path": approved_by_shot[shot.storyboard_shot_id]["image_path"],
                    **self._packaged_render_inputs(shot, approved_by_shot[shot.storyboard_shot_id]),
                    "continuity": shot.continuity_plan.model_dump(mode="json"),
                    "staging": shot.visual_plan.blocking,
                }
                for shot in shots
            ],
        }
        return storage.save_previs_production_package(
            {
                "project_id": project_id,
                "scene_id": scene_id,
                "blueprint_id": blueprint.blueprint_id,
                "blueprint_version_id": version.version_id,
                "status": "ready",
                "payload": payload,
            }
        )

    def _packaged_render_inputs(self, shot, image: dict) -> dict:
        """Freeze the approved take's effective inputs for the production handoff."""
        inputs = storyboard_render_inputs(shot)
        metadata = image.get("metadata") or {}
        parameters = {**inputs["parameters"], **(metadata.get("render_parameters") or {})}
        prompt = image.get("prompt_used") or inputs["prompt"]
        references = list(metadata.get("reference_assets") or inputs["reference_assets"])
        provider = metadata.get("render_provider")
        job = self._require_storage().get_job(image["job_id"])
        if job is not None:
            if job.project_id != shot.project_id or job.shot_id != shot.shot_id:
                raise StateError("Approved Previs job does not belong to this storyboard shot", stage="previs_package")
            # Includes the seed resolved at submission, not merely the UI input.
            for key in ("duration", "duration_seconds", "ratio", "resolution", "seed", "storyboard_frame_url"):
                if key in (job.input_payload.parameters or {}):
                    parameters[key] = job.input_payload.parameters[key]
            prompt = job.input_payload.prompt or prompt
            references = list(job.input_payload.referenceAssets or references)
            provider = job.provider
        parameters.pop("previs", None)
        parameters.pop("idempotency_key", None)
        parameters["preserve_shot_prompt"] = True
        return {"prompt": prompt, "reference_assets": references, "parameters": parameters, "render_provider": provider}

    async def generate_all(self, project_id: str) -> dict:
        scenes = self._scenes(project_id)
        if not scenes:
            raise StateError("No scenes found for project", stage="previs_generate_all")
        jobs = []
        for scene in scenes:
            scene_id = str(scene["scene_id"])
            try:
                jobs.append(await self.generate_scene(project_id, scene_id))
            except (ValidationError, StateError, PersistenceError, ProviderError) as exc:
                jobs.append(
                    {
                        "scene_id": scene_id,
                        "job_id": None,
                        "status": "failed",
                        "error": exc.to_dict(),
                    }
                )
        return {"project_id": project_id, "total_scenes": len(scenes), "jobs": jobs}

    @staticmethod
    def _generation_response(record: dict[str, Any], shot_number: int, take_number: int, duplicate: bool = False) -> dict[str, Any]:
        return {
            "job_id": record["job_id"],
            "status": record.get("status") or "pending",
            "scene_id": record["scene_id"],
            "previs_image_id": record.get("id"),
            "blueprint_id": record.get("blueprint_id"),
            "blueprint_version_id": record.get("blueprint_version_id"),
            "storyboard_shot_id": record.get("storyboard_shot_id"),
            "duplicate": duplicate,
            "message": (
                record.get("failure_reason") or f"Preview generation {'already active' if duplicate else 'started'} for Shot "
                f"{shot_number}, Take {take_number} ({get_shot_type_label(shot_number)})"
            ),
        }


previs_service = PrevisService()
