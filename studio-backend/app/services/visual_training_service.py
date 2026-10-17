from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from app.adapters import get_training_adapter
from app.models import ProviderConfig
from app.models.visual_training import VisualModel, VisualTrainingJob
from app.services.project_store import project_store
from app.services.stability import ValidationError, log_stage_event

logger = logging.getLogger("studio-visual-training")

# Trigger tokens must be letters-only so they never collide with normal
# language tokens during LoRA training (Phosphene's trigger guidance). Studio
# validates up front so a doomed submission never reaches the provider.
_TRIGGER_RE = re.compile(r"^[A-Za-z]{3,32}$")

# Provider adapter modules currently registered do NOT implement
# VisualTrainingAdapter (training-capable adapters opt in). The registry in
# app/adapters is the single provider boundary; nothing here hardcodes a
# specific training provider.

VALID_TARGET_TYPES = ("character", "scene")


def normalize_training_config(
    *,
    target_type: str,
    trigger_word: str,
    source_assets: list[dict[str, Any]],
    provider: str,
    provider_model: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Normalize training configuration into a canonical form."""
    config: dict[str, Any] = {
        "target_type": target_type,
        "trigger_word": trigger_word,
        "source_assets": source_assets,
        "provider": provider,
        "provider_model": provider_model,
    }
    config.update(kwargs)
    return config


class VisualTrainingService:
    """Service owns visual training job lifecycle, provider abstraction, and artifact registration.

    Responsibilities:
    - training job creation and validation
    - source asset validation
    - training configuration normalization
    - provider training invocation (through VisualTrainingAdapter boundary)
    - job status tracking
    - failure handling (fail-closed)
    - trained artifact registration
    - association with canonical project/entity
    - audit/provenance information

    Does NOT mutate canonical FilmLevelMemory, FilmStructure, CreativeSpine, or other
    canonical story truth.

    All training job and trained model state is persisted in the visual_models table
    (migration 63/64), using the training_id field to link job state to the final
    registered visual model. The visual model is an artifact associated with
    canonical project entities, not a replacement source of truth.
    """

    def __init__(self, storage=None):
        self._storage = storage
        self._provider_configs: dict[str, ProviderConfig] = {}
        self._jobs: dict[str, VisualTrainingJob] = {}

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    def register_provider_config(self, config: ProviderConfig) -> None:
        """Register a provider configuration for later training invocation."""
        self._provider_configs[config.provider_id] = config

    def get_provider_config(self, provider_id: str) -> ProviderConfig | None:
        return self._provider_configs.get(provider_id)

    def list_provider_configs(self) -> dict[str, ProviderConfig]:
        """Return a snapshot of registered provider configs for the UI."""
        return dict(self._provider_configs)

    # ------------------------------------------------------------------
    # Job creation and validation
    # ------------------------------------------------------------------

    def create_training_job(
        self,
        *,
        project_id: str,
        visual_model_id: str | None,
        target_type: str,
        trigger_word: str,
        source_asset_ids: list[str],
        provider: str,
        provider_model: str,
        configuration: dict[str, Any] | None = None,
    ) -> VisualTrainingJob:
        """Create and validate a new visual training job.

        The job is immediately persisted to the visual_models table (migration
        63/64) with status="pending". The visual_model_id parameter, if provided,
        reuses an existing model ID; otherwise a new ID is generated.
        """
        project = self._get_project(project_id)
        if project is None:
            raise ValidationError(
                f"Project {project_id} not found",
                stage="training_job_creation",
                metadata={"project_id": project_id},
            )

        if target_type not in VALID_TARGET_TYPES:
            raise ValidationError(
                f"Invalid target_type {target_type!r}; expected 'character' or 'scene'",
                stage="training_job_creation",
                metadata={"target_type": target_type},
            )

        if self.get_provider_config(provider) is None:
            raise ValidationError(
                f"Provider {provider} not configured",
                stage="training_job_creation",
                metadata={"provider": provider},
            )

        if not trigger_word or not trigger_word.strip():
            raise ValidationError(
                "trigger_word must be a non-empty string",
                stage="training_job_creation",
            )
        if not _TRIGGER_RE.match(trigger_word.strip()):
            raise ValidationError(
                "trigger_word must be 3-32 letters only (no digits or symbols); "
                "LoRA trigger tokens must not collide with normal language",
                stage="training_job_creation",
                metadata={"trigger_word": trigger_word},
            )

        self._validate_source_assets(project_id, source_asset_ids)

        if visual_model_id is None:
            visual_model_id = f"vm_{uuid4().hex[:12]}"
        else:
            visual_model_id = str(visual_model_id)

        now = datetime.now(timezone.utc).isoformat()
        config: dict[str, Any] = dict(configuration or {})
        config["provider_model"] = provider_model

        job = VisualTrainingJob(
            id=str(uuid4()),
            project_id=project_id,
            target_type=cast(Any, target_type),
            target_id=visual_model_id,
            trigger=trigger_word,
            preset="medium",
            image_count=0,
            provider_train_type="character" if target_type == "character" else "style",
            rank=None,
            alpha=None,
            steps=None,
            learning_rate=None,
            resolution=None,
            provider=provider,
            provider_model=provider_model,
            provider_job_id="",
            source_asset_ids=list(source_asset_ids),
            configuration=config,
            status="pending",
            trained_model_id=None,
            updated_at=now,
            created_at=now,
            completed_at=None,
            error="",
        )

        # Persist job state in the visual_models table (migration 63/64)
        if self._storage is not None:        self._storage.upsert_visual_model(
            id=job.target_id or job.id,
            project_id=job.project_id,
            target_type=job.target_type,
            target_id=job.target_id or job.id,
            training_id=job.id,
            provider=job.provider,
            base_model=config.get("provider_model", ""),
            model_version=config.get("model_version", ""),
            trigger=job.trigger,
            dataset_reference=",".join(job.source_asset_ids) if job.source_asset_ids else None,
            output_reference="",
            status=job.status,
            configuration=config,
            created_at=job.created_at,
            completed_at=None,
            error="",
        )

        self._jobs[job.id] = job

        log_stage_event(
            project_id=project_id,
            job_id=job.id,
            provider=provider,
            stage="training_job_creation",
            duration_ms=0,
        )

        logger.info(
            "VISUAL_TRAINING_JOB_CREATED | project=%s | job=%s | model_id=%s | target_type=%s",
            project_id,
            job.id,
            visual_model_id,
            target_type,
        )

        return job

    # ------------------------------------------------------------------
    # Source asset validation
    # ------------------------------------------------------------------

    def _validate_source_assets(self, project_id: str, source_asset_ids: list[str]) -> None:
        """Validate that all source assets are approved references for the project.

        Reference assets live in the reference_assets table (migration 30),
        queried through the storage layer — the same registry the render
        pipeline uses for identity/environment locks. Registry presence alone
        is not enough: only assets whose authoritative ``approval_state`` is
        ``approved`` may train an identity. Candidates, rejected, revoked, or
        otherwise unapproved assets fail closed here — the request is rejected,
        never silently narrowed to an approved subset.
        """
        registry: dict[str, dict] | None = None
        if self._storage is not None:
            refs = self._storage.list_reference_assets(project_id)
            registry = {
                str(r.get("ref_id") or "").strip(): r
                for r in refs
                if r.get("ref_id")
            }

        for asset_id in source_asset_ids:
            asset_id_str = str(asset_id or "").strip()
            if not asset_id_str:
                raise ValidationError(
                    "Source asset IDs must be non-empty strings",
                    stage="source_asset_validation",
                )
            if registry is None:
                continue
            row = registry.get(asset_id_str)
            if row is None:
                raise ValidationError(
                    f"Source asset {asset_id_str!r} is not a confirmed reference for project {project_id}",
                    stage="source_asset_validation",
                    metadata={"project_id": project_id, "asset_id": asset_id_str},
                )
            state = str(row.get("approval_state") or "").strip().lower()
            if state != "approved":
                raise ValidationError(
                    f"Source asset {asset_id_str!r} is not approved for training "
                    f"(approval_state={state or 'unknown'!r}); approve it before training",
                    stage="source_asset_validation",
                    metadata={"project_id": project_id, "asset_id": asset_id_str, "approval_state": state or None},
                )

    def _get_project(self, project_id: str) -> dict[str, Any] | None:
        """Retrieve a project from storage."""
        if self._storage is not None:
            return self._storage.get_project(project_id)
        return project_store.get_project(project_id)

    # ------------------------------------------------------------------
    # Training invocation
    # ------------------------------------------------------------------

    async def submit_training_job(self, job_id: str) -> VisualTrainingJob | None:
        """Submit a visual training job to the provider (phase one of two).

        For real async providers the call returns as soon as the provider
        accepts the job: the provider id is persisted, the job is marked
        ``queued`` and completion is discovered later through
        :meth:`refresh_training_job` via the existing status mechanism. For
        synchronous stand-in adapters that already return the final artifact
        (the simulated ``local_training`` provider), the result is applied
        immediately, unchanged.

        Returns the updated job, or None if the job doesn't exist.
        Fail-closed: on any provider error the job is marked failed and
        returned. If the provider is unavailable the job fails honestly —
        there is never a simulated success.
        """
        job = self.get_training_job(job_id)
        if job is None:
            logger.error("VISUAL_TRAINING_JOB_NOT_FOUND | job_id=%s", job_id)
            return None

        provider = job.provider
        provider_config = self.get_provider_config(provider)

        if provider_config is None:
            job.status = "failed"
            job.error = f"Provider {provider} not configured"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.updated_at = job.completed_at
            self._persist_job_state(job)
            logger.error(
                "VISUAL_TRAINING_PROVIDER_NOT_CONFIGURED | project=%s | job=%s | provider=%s",
                job.project_id,
                job.id,
                provider,
            )
            return job

        try:
            adapter = get_training_adapter(provider, provider_config)
            training_config = self._normalize_training_for_provider(job)

            train_result = await adapter.submit_training_job(
                job=job,
                training_config=training_config,
            )

            result = train_result if isinstance(train_result, dict) else {}
            was_ok = bool(result.get("ok", False))
            if not was_ok:
                job.status = "failed"
                job.error = result.get("error") or "Provider returned failure"
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.updated_at = job.completed_at
                if isinstance(result.get("configuration"), dict):
                    job.configuration = {**job.configuration, **result["configuration"]}
                self._persist_job_state(job)

                log_stage_event(
                    project_id=job.project_id,
                    job_id=job.id,
                    provider=provider,
                    stage="training_job_submission_failure",
                    duration_ms=0,
                )
                logger.warning(
                    "VISUAL_TRAINING_JOB_FAILED | project=%s | job=%s | error=%s",
                    job.project_id,
                    job.id,
                    job.error,
                )
                return job

            provider_job_id = str(result.get("provider_job_id") or "").strip()
            if provider_job_id:
                # Real async provider: persist the external id, mark the job
                # accepted-but-not-finished, and return. Completion is polled
                # through refresh_training_job — never faked synchronously.
                job.provider_job_id = provider_job_id
                job.status = "queued"
                job.error = ""
                job.completed_at = None
                if isinstance(result.get("configuration"), dict):
                    job.configuration = {
                        **job.configuration,
                        **result["configuration"],
                        "provider_job_id": provider_job_id,
                    }
                else:
                    job.configuration = {
                        **job.configuration,
                        "provider_job_id": provider_job_id,
                    }
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist_job_state(job)

                log_stage_event(
                    project_id=job.project_id,
                    job_id=job.id,
                    provider=provider,
                    stage="training_job_submission",
                    duration_ms=0,
                )
                logger.info(
                    "VISUAL_TRAINING_JOB_ACCEPTED | project=%s | job=%s | provider=%s | provider_job_id=%s",
                    job.project_id,
                    job.id,
                    provider,
                    provider_job_id,
                )
                return job

            # No provider id: the adapter resolved training synchronously (the
            # simulated stand-in contract). Apply the final state unchanged.
            job.status = "complete"
            job.error = ""
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.updated_at = job.completed_at
            if isinstance(result.get("configuration"), dict):
                job.configuration = {**job.configuration, **result["configuration"]}
            if result.get("trained_model_id"):
                job.trained_model_id = str(result["trained_model_id"])

            self._persist_job_state(job)
            self._register_trained_model_from_job(job)

            log_stage_event(
                project_id=job.project_id,
                job_id=job.id,
                provider=provider,
                stage="training_job_submission",
                duration_ms=0,
            )
            logger.info(
                "VISUAL_TRAINING_JOB_FINISHED | project=%s | job=%s | status=%s | model_id=%s",
                job.project_id,
                job.id,
                job.status,
                job.trained_model_id or "none",
            )
            return job

        except Exception as exc:
            job.status = "failed"
            job.error = f"Training job submission failed: {exc!s}"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.updated_at = job.completed_at
            self._persist_job_state(job)

            log_stage_event(
                project_id=job.project_id,
                job_id=job.id,
                provider=provider,
                stage="training_job_submission_failure",
                duration_ms=0,
            )
            logger.exception(
                "VISUAL_TRAINING_JOB_FAILED | project=%s | job=%s",
                job.project_id,
                job.id,
            )
            return job

    # ------------------------------------------------------------------
    # Provider state polling (phase two of the async lifecycle)
    # ------------------------------------------------------------------

    async def refresh_training_job(self, job_id: str) -> VisualTrainingJob | None:
        """Poll the provider for the job's external training state.

        This is the honest completion path for real async providers: Studio's
        canonical job remains the source of truth, the provider id was stored
        at submission, and the provider state is folded back in here through
        the same VisualTrainingAdapter boundary used for submission.

        Idempotent: calling this on a job with no provider id, or already in a
        terminal state, is a no-op that returns the unchanged job. When the
        provider is unreachable the job keeps its current state (never
        guessed, never failed by a transient poll).

        On provider completion the resulting LoRA/character is discovered
        through the provider's character registry and persisted via the
        existing trained-model registration, so the artifact is immediately
        usable by the render pipeline's ``resolve_render_reference``.
        """
        job = self.get_training_job(job_id)
        if job is None:
            logger.error("VISUAL_TRAINING_JOB_NOT_FOUND_FOR_REFRESH | job_id=%s", job_id)
            return None

        # Idempotency: nothing to refresh without a provider id, or when the
        # job already reached a terminal state.
        if not job.provider_job_id:
            return job
        if job.status in {"complete", "failed", "cancelled"}:
            return job

        provider_config = self.get_provider_config(job.provider)
        if provider_config is None:
            # Configuration lost (e.g. after restart with a changed provider
            # registry): fail honestly instead of reporting a phantom state.
            job.status = "failed"
            job.error = f"Provider {job.provider} not configured"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.updated_at = job.completed_at
            self._persist_job_state(job)
            logger.error(
                "VISUAL_TRAINING_REFRESH_PROVIDER_NOT_CONFIGURED | project=%s | job=%s | provider=%s",
                job.project_id,
                job.id,
                job.provider,
            )
            return job

        try:
            adapter = get_training_adapter(job.provider, provider_config)
            status = await adapter.get_training_status(job)
        except Exception as exc:  # noqa: BLE001 — a poll failure must not crash the caller
            logger.warning(
                "VISUAL_TRAINING_REFRESH_POLL_FAILED | project=%s | job=%s | error=%s",
                job.project_id,
                job.id,
                exc,
            )
            return job

        if not isinstance(status, dict) or not status.get("found"):
            # Provider unreachable or job not visible yet: keep current state.
            return job

        state = str(status.get("state") or "")
        now = datetime.now(timezone.utc).isoformat()

        if state == "queued" and job.status == "pending":
            job.status = "queued"
            job.updated_at = now
            self._persist_job_state(job)
            return job
        if state == "running":
            job.status = "training"
            phase_label = status.get("phase_label")
            if phase_label:
                job.configuration = {**job.configuration, "provider_phase": str(phase_label)}
            job.updated_at = now
            self._persist_job_state(job)
            return job
        if state == "failed":
            job.status = "failed"
            job.error = str(status.get("error") or "Provider training failed")
            job.completed_at = now
            job.updated_at = now
            self._persist_job_state(job)
            logger.warning(
                "VISUAL_TRAINING_JOB_FAILED | project=%s | job=%s | provider_error=%s",
                job.project_id,
                job.id,
                job.error,
            )
            return job
        if state == "complete":
            return await self._complete_training_from_provider(job, adapter)

        # Unknown state: leave the job untouched rather than guessing.
        return job

    async def _complete_training_from_provider(self, job: VisualTrainingJob, adapter: Any) -> VisualTrainingJob:
        """Finalize a completed provider training run.

        Discovers the resulting LoRA/character through the provider's registry
        (Phosphene: ``GET /characters``), persists the trained artifact via
        the existing registration path, and marks the Studio job complete.
        """
        now = datetime.now(timezone.utc).isoformat()
        artifact_id = ""
        discovery: dict[str, Any] = {}

        finder = getattr(adapter, "find_provider_character", None)
        if callable(finder):
            try:
                discovery = await finder(job) or {}
            except Exception as exc:  # noqa: BLE001 — discovery failure must fail honestly, not silently
                logger.warning(
                    "VISUAL_TRAINING_LORA_DISCOVERY_FAILED | project=%s | job=%s | error=%s",
                    job.project_id,
                    job.id,
                    exc,
                )
                discovery = {}

        if discovery.get("found"):
            artifact_id = str(discovery.get("artifact_id") or "").strip()
            job.configuration = {
                **job.configuration,
                "trained_character": {
                    key: value
                    for key, value in {
                        "id": discovery.get("id"),
                        "trigger": discovery.get("trigger"),
                        "name": discovery.get("name"),
                        "face_lora_path": discovery.get("face_lora_path"),
                        "audio_lora_path": discovery.get("audio_lora_path"),
                        "adapter_verdict": discovery.get("adapter_verdict"),
                    }.items()
                    if value is not None
                },
            }

        if not artifact_id:
            # The provider said done but the artifact is not discoverable.
            # Never mark complete without a verified artifact (guardrail:
            # never claim LoRA availability without verification).
            job.status = "failed"
            job.error = (
                "Provider reported training complete but the resulting "
                f"LoRA/character {job.trigger!r} could not be discovered. "
                "Check the provider's character registry and retry."
            )
            job.completed_at = now
            job.updated_at = now
            self._persist_job_state(job)
            logger.warning(
                "VISUAL_TRAINING_COMPLETION_WITHOUT_ARTIFACT | project=%s | job=%s | trigger=%s",
                job.project_id,
                job.id,
                job.trigger,
            )
            return job

        job.status = "complete"
        job.trained_model_id = artifact_id
        job.error = ""
        job.completed_at = now
        job.updated_at = now
        self._persist_job_state(job)
        self._register_trained_model_from_job(job)

        log_stage_event(
            project_id=job.project_id,
            job_id=job.id,
            provider=job.provider,
            stage="training_job_completed",
            duration_ms=0,
        )
        logger.info(
            "VISUAL_TRAINING_JOB_COMPLETED | project=%s | job=%s | artifact=%s",
            job.project_id,
            job.id,
            artifact_id,
        )
        return job

    async def refresh_running_training_jobs(self) -> list[VisualTrainingJob]:
        """Refresh every non-terminal training job that has a provider id.

        Used by restart recovery and by any status sweep. There is deliberately
        no background loop behind this — callers (API status reads, startup
        recovery) invoke it explicitly.
        """
        if self._storage is None:
            return []
        refreshed: list[VisualTrainingJob] = []
        processed_job_ids: set[str] = set()
        for status in ("pending", "queued", "training"):
            for row in self._storage.list_visual_models(status=status):
                job = self._row_to_job(row)
                if job is None or not job.provider_job_id or job.id in processed_job_ids:
                    continue
                processed_job_ids.add(job.id)
                updated = await self.refresh_training_job(job.id)
                if updated is not None:
                    refreshed.append(updated)
        return refreshed

    def list_incomplete_training_jobs(self) -> list[VisualTrainingJob]:
        """List non-terminal training jobs (restart recovery aid)."""
        if self._storage is None:
            return []
        jobs: list[VisualTrainingJob] = []
        for status in ("pending", "queued", "training"):
            for row in self._storage.list_visual_models(status=status):
                job = self._row_to_job(row)
                if job is not None:
                    jobs.append(job)
        return jobs

    def _normalize_training_for_provider(self, job: VisualTrainingJob) -> dict[str, Any]:
        """Normalize the job's configuration for the provider's training API."""
        config = dict(job.configuration or {})
        if "trigger_word" not in config:
            config["trigger_word"] = job.trigger
        if "target_type" not in config:
            config["target_type"] = job.target_type
        config.setdefault("provider_model", job.provider_model)
        config.setdefault("preset", job.preset)
        if "source_assets" not in config:
            config["source_assets"] = [
                {"ref_id": aid, "kind": self._guess_asset_kind(job.target_type)}
                for aid in job.source_asset_ids
            ]
        return config

    @staticmethod
    def _guess_asset_kind(target_type: str) -> str:
        if target_type == "character":
            return "character_face"
        return "environment"

    # ------------------------------------------------------------------
    # Job state persistence in visual_models table
    # ------------------------------------------------------------------

    def _persist_job_state(self, job: VisualTrainingJob) -> None:
        """Persist the current job state to the visual_models table."""

        if self._storage is None:
            logger.warning("No storage backend; skipping job state persistence for job=%s", job.id)
            return

        config = job.configuration or {}

        self._storage.upsert_visual_model(
            id=job.target_id or job.id,
            project_id=job.project_id,
            target_type=job.target_type,
            target_id=job.target_id or job.id,
            training_id=job.id,
            provider=job.provider,
            base_model=config.get("provider_model", job.provider_model or ""),
            model_version=config.get("model_version", ""),
            trigger=job.trigger,
            dataset_reference=",".join(job.source_asset_ids) if job.source_asset_ids else None,
            output_reference=job.trained_model_id or "",
            status=job.status,
            configuration=config,
            created_at=job.created_at,
            completed_at=job.completed_at,
            error=job.error,
        )

        logger.debug(
            "VISUAL_TRAINING_STATE_PERSISTED | project=%s | job=%s | status=%s | model_id=%s",
            job.project_id,
            job.id,
            job.status,
            job.trained_model_id,
        )

    # ------------------------------------------------------------------
    # Job loading
    # ------------------------------------------------------------------

    def _load_job(self, job_id: str) -> VisualTrainingJob | None:
        """Load a training job from the visual_models table (lookup by training_id)."""
        if self._storage is None:
            return None

        row = self._storage.get_visual_training_job(job_id)
        if row is None:
            return None

        job = self._row_to_job(row)
        if job is not None:
            self._jobs[job.id] = job
        return job

    @staticmethod
    def _parse_config(row: dict[str, Any]) -> dict[str, Any]:
        configuration = row.get("configuration") or {}
        if isinstance(configuration, str):
            try:
                configuration = json.loads(configuration)
            except (ValueError, TypeError):
                configuration = {}
        return configuration if isinstance(configuration, dict) else {}

    def _row_to_job(self, row: dict[str, Any]) -> VisualTrainingJob | None:
        """Convert a visual_models row into a VisualTrainingJob."""
        target_type = str(row.get("target_type") or "")
        if target_type not in ("character", "scene", "location", "style"):
            return None

        configuration = self._parse_config(row)
        now = str(row.get("created_at") or datetime.now(timezone.utc).isoformat())

        job = VisualTrainingJob(
            id=str(row["training_id"]),
            project_id=row["project_id"],
            target_type=cast(Any, target_type),
            target_id=str(row["target_id"] or row["id"]),
            trigger=row["trigger"],
            preset="medium",
            image_count=0,
            provider_train_type="character" if target_type == "character" else "style",
            rank=None,
            alpha=None,
            steps=None,
            learning_rate=None,
            resolution=None,
            provider=str(row.get("provider") or ""),
            provider_model=str(configuration.get("provider_model") or row.get("base_model") or ""),
            provider_job_id=str(configuration.get("provider_job_id") or ""),
            source_asset_ids=[
                part for part in str(row.get("dataset_reference") or "").split(",") if part
            ],
            configuration=configuration,
            status=cast(Any, str(row.get("status") or "pending")),
            trained_model_id=str(row.get("output_reference") or "") or None,
            updated_at=str(row.get("updated_at") or now),
            created_at=now,
            completed_at=row.get("completed_at"),
            error=row.get("error"),
        )
        return job

    # ------------------------------------------------------------------
    # Visual model registration (from completed training job)
    # ------------------------------------------------------------------

    def _register_trained_model_from_job(self, job: VisualTrainingJob) -> None:
        """Register the trained visual model from a completed training job.

        Updates the visual_models row with the trained model/artifact reference,
        transforming the job record into a fully-registered visual model.
        """
        if self._storage is None:
            logger.warning("No storage backend; skipping trained model registration for job=%s", job.id)
            return

        config = job.configuration or {}
        model_id = job.trained_model_id or job.target_id

        self._storage.upsert_visual_model(
            id=job.target_id or job.id,
            project_id=job.project_id,
            target_type=job.target_type,
            target_id=job.target_id or job.id,
            training_id=job.id,
            provider=job.provider,
            base_model=config.get("provider_model", job.provider_model or ""),
            model_version=config.get("model_version", job.provider_model or ""),
            trigger=job.trigger,
            dataset_reference=",".join(job.source_asset_ids) if job.source_asset_ids else None,
            output_reference=model_id,
            status="complete",
            configuration=config,
            created_at=job.created_at,
            completed_at=job.completed_at,
            error="",
        )

        job.trained_model_id = model_id
        job.updated_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "VISUAL_MODEL_REGISTERED_FROM_JOB | project=%s | job=%s | model_id=%s | target_type=%s",
            job.project_id,
            job.id,
            job.trained_model_id,
            job.target_type,
        )

    # ------------------------------------------------------------------
    # Job status and retrieval
    # ------------------------------------------------------------------

    def get_training_job(self, job_id: str) -> VisualTrainingJob | None:
        """Get a training job by ID, loading from storage if not in memory."""
        job = self._jobs.get(job_id)
        if job is not None:
            return job
        return self._load_job(job_id)

    # ------------------------------------------------------------------
    # Visual model registration and retrieval
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_visual_model(row: dict[str, Any]) -> VisualModel:
        configuration = VisualTrainingService._parse_config(row)
        return VisualModel(
            id=row["id"],
            project_id=row["project_id"],
            target_type=row["target_type"],
            target_id=row["target_id"] or row["id"],
            training_id=row["training_id"],
            provider=row["provider"],
            base_model=row["base_model"],
            model_version=row["model_version"],
            trigger=row["trigger"],
            dataset_reference=row["dataset_reference"],
            output_reference=row["output_reference"],
            status=row["status"],
            configuration=configuration,
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
            error=row.get("error"),
        )

    def get_visual_model(self, model_id: str) -> VisualModel | None:
        """Get a registered visual model by ID. Returns None for non-complete rows."""
        if self._storage is None:
            return None

        row = self._storage.get_visual_model(model_id)
        if row is None or row.get("status") != "complete":
            return None
        return self._row_to_visual_model(row)

    def list_visual_models(
        self,
        project_id: str | None = None,
        target_type: str | None = None,
        status: str | None = None,
    ) -> list[VisualModel]:
        """List visual models, optionally filtered by project, target type, or status."""
        if self._storage is None:
            return []

        rows = self._storage.list_visual_models(
            project_id=project_id,
            target_type=target_type,
            status=status,
        )
        return [self._row_to_visual_model(row) for row in rows]

    def resolve_render_reference(
        self,
        *,
        project_id: str,
        visual_model_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the registered visual model reference for a render request.

        Rendering without a trained visual model stays unchanged: when no model
        is requested this returns None and the caller leaves the provider payload
        untouched.

        Fail-closed: an explicitly requested ``visual_model_id`` that is missing,
        still training, failed, or belongs to another project raises
        ValidationError. It never silently falls back to an untrained or
        unrelated visual model.
        """
        if not visual_model_id and not (target_type and target_id):
            return None

        if self._storage is None:
            raise ValidationError(
                "No storage backend available to resolve visual model reference",
                stage="visual_model_resolution",
                metadata={"project_id": project_id, "visual_model_id": visual_model_id},
            )

        model: VisualModel | None = None
        if visual_model_id:
            model = self.get_visual_model(str(visual_model_id))
            if model is None:
                raise ValidationError(
                    f"Visual model {visual_model_id!r} is not registered or not complete",
                    stage="visual_model_resolution",
                    metadata={"project_id": project_id, "visual_model_id": visual_model_id},
                )
        else:
            candidates = [
                candidate
                for candidate in self.list_visual_models(
                    project_id=project_id,
                    target_type=target_type,
                    status="complete",
                )
                if candidate.target_id == target_id
            ]
            if not candidates:
                return None
            model = candidates[-1]

        if model.project_id != project_id:
            raise ValidationError(
                f"Visual model {model.id!r} does not belong to project {project_id!r}",
                stage="visual_model_resolution",
                metadata={"project_id": project_id, "visual_model_id": model.id},
            )

        return {
            "model_id": model.id,
            "provider": model.provider,
            "base_model": model.base_model,
            "model_version": model.model_version,
            "output_reference": model.output_reference,
            "trigger": model.trigger,
            "target_type": model.target_type,
            "target_id": model.target_id,
        }

    def list_training_jobs(
        self,
        project_id: str | None = None,
        target_type: str | None = None,
        status: str | None = None,
    ) -> list[VisualTrainingJob]:
        """List training jobs, optionally filtered by project, target type, or status."""
        if self._storage is None:
            return []

        filter_status = status or "pending"
        rows = self._storage.list_visual_models(
            project_id=project_id,
            target_type=target_type,
            status=filter_status,
        )
        jobs: list[VisualTrainingJob] = []
        for row in rows:
            job = self._row_to_job(row)
            if job is not None:
                jobs.append(job)
        return jobs

    # ------------------------------------------------------------------
    # Job cancellation (through the training provider boundary)
    # ------------------------------------------------------------------

    async def cancel_training_job(self, job_id: str) -> bool:
        """Cancel a visual training job if the underlying provider supports cancellation."""
        job = self.get_training_job(job_id)
        if job is None:
            logger.error("VISUAL_TRAINING_JOB_NOT_FOUND_FOR_CANCELLATION | job_id=%s", job_id)
            return False

        provider_config = self.get_provider_config(job.provider)
        if provider_config is None:
            job.status = "cancelled"
            job.error = ""
            self._persist_job_state(job)
            logger.warning(
                "VISUAL_TRAINING_CANCEL_NO_PROVIDER_CFG | project=%s | job=%s | provider=%s",
                job.project_id,
                job.id,
                job.provider,
            )
            return True

        try:
            adapter = get_training_adapter(job.provider, provider_config)
            result = await adapter.cancel_training_job(job)
            job.status = "cancelled" if result else job.status
            job.error = ""
            job.updated_at = datetime.now(timezone.utc).isoformat()
            self._persist_job_state(job)
            logger.info(
                "VISUAL_TRAINING_JOB_CANCELLED | project=%s | job=%s | provider=%s",
                job.project_id,
                job.id,
                job.provider,
            )
            return True
        except Exception as exc:  # noqa: BLE001 — provider cancellation is best-effort; degrade to failed
            logger.warning(
                "VISUAL_TRAINING_CANCELLATION_FAILED | project=%s | job=%s | error=%s",
                job.project_id,
                job.id,
                exc,
            )
            job.status = "failed"
            job.error = f"Cancellation failed: {exc!s}"
            self._persist_job_state(job)
            return False

    # ------------------------------------------------------------------
    # Canonical story truth - deliberately NOT mutating
    # ------------------------------------------------------------------

    def associate_model_with_project(self, model_id: str, project_updates: dict[str, Any]) -> None:
        """Record that a visual model is associated with a project.

        This is a no-op for canonical story truth. Project associations live only
        in the visual_models.project_id column — FilmLevelMemory, FilmStructure,
        CreativeSpine and other canonical story truth are never mutated here.
        """
        logger.info(
            "VISUAL_MODEL_ASSOCIATION_RECORDED | model_id=%s | project_updates_keys=%s",
            model_id,
            list(project_updates.keys()),
        )


# Backwards-compatible alias used by routes and tests
visual_training_service = VisualTrainingService()