from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any

from app.data.storage import get_storage
from app.models.production_queue import (
    QueueFailureCategory,
    ProductionQueueAttempt,
    ProductionQueueDependency,
    ProductionQueueDependencyCreate,
    ProductionQueueDependencyType,
    ProductionQueueEvent,
    ProductionQueueItem,
    ProductionQueueItemCreate,
    ProductionQueuePage,
    ProductionQueueSchedulerDecision,
    ProductionQueueStatus,
    ProductionQueueSummary,
    ProductionQueueWorkerStatus,
    ProductionQueueWorkType,
)
from app.services.stability import StabilityError, log_stage_event

logger = logging.getLogger("production-queue")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _future_iso(seconds: int) -> str:
    return (datetime.now() + timedelta(seconds=max(1, seconds))).isoformat()


def _queue_id() -> str:
    return f"pqi_{uuid.uuid4().hex[:16]}"


def _event_id() -> str:
    return f"pqe_{uuid.uuid4().hex[:16]}"


def _attempt_id() -> str:
    return f"pqa_{uuid.uuid4().hex[:16]}"


class ProductionQueueService:
    """Durable production queue over canonical Studio execution services."""

    def __init__(
        self,
        *,
        storage: Any = None,
        render_svc: Any = None,
        worker_owner_id: str | None = None,
    ) -> None:
        self.storage = storage or get_storage("sqlite")
        self.render_service = render_svc
        self.worker_owner_id = worker_owner_id or f"studio-api-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._running = False
        self._last_heartbeat_at: str | None = None
        self._active_item_id: str | None = None
        self._worker_task: asyncio.Task | None = None

    @property
    def lease_seconds(self) -> int:
        try:
            from app.config import get_settings

            return int(getattr(get_settings(), "production_queue_lease_seconds", 300))
        except Exception:
            return 300

    @property
    def loop_interval_seconds(self) -> float:
        try:
            from app.config import get_settings

            return float(getattr(get_settings(), "production_queue_worker_poll_interval_seconds", 2.0))
        except Exception:
            return 2.0

    def set_storage(self, storage: Any) -> None:
        self.storage = storage

    def set_render_service(self, render_svc: Any) -> None:
        self.render_service = render_svc

    def _get_render_service(self) -> Any:
        if self.render_service is None:
            from app.services.render import render_service

            self.render_service = render_service
        return self.render_service

    def _settings_value(self, name: str, fallback: Any) -> Any:
        try:
            from app.config import get_settings

            return getattr(get_settings(), name, fallback)
        except Exception:
            return fallback

    def _provider_limits(self) -> dict[str, int]:
        raw = self._settings_value("production_queue_provider_concurrency_json", "{}")
        if isinstance(raw, dict):
            source = raw
        else:
            try:
                parsed = json.loads(str(raw or "{}"))
                source = parsed if isinstance(parsed, dict) else {}
            except Exception:
                source = {}
        limits: dict[str, int] = {}
        for key, value in source.items():
            try:
                limits[str(key).strip().lower()] = max(0, int(value))
            except Exception:
                continue
        return limits

    def _global_limit(self) -> int:
        return max(1, int(self._settings_value("production_queue_global_concurrency", 4) or 4))

    def _project_limit(self) -> int:
        return max(1, int(self._settings_value("production_queue_project_concurrency", 2) or 2))

    def _provider_limit(self, provider: str | None) -> int:
        if not provider:
            return self._global_limit()
        return self._provider_limits().get(str(provider).strip().lower(), self._global_limit())

    def _record_event(
        self,
        *,
        project_id: str,
        queue_item_id: str | None,
        event_type: str,
        stage: str,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> ProductionQueueEvent:
        event = ProductionQueueEvent(
            event_id=_event_id(),
            queue_item_id=queue_item_id,
            project_id=project_id,
            event_type=event_type,
            stage=stage,
            message=message,
            details=details or {},
            created_at=_now_iso(),
        )
        self.storage.save_queue_event(event)
        return event

    def enqueue_item(self, payload: ProductionQueueItemCreate) -> ProductionQueueItem:
        project_id = payload.project_id.strip()
        if not project_id:
            raise ValueError("project_id is required")
        canonical_type = payload.canonical_type.strip()
        if not canonical_type:
            raise ValueError("canonical_type is required")
        idempotency_key = (
            payload.idempotency_key
            or f"{payload.work_type.value}:{project_id}:{payload.scene_id or ''}:{payload.shot_id or ''}:{payload.canonical_id or ''}"
        )
        existing = self.storage.find_queue_item_by_idempotency_key(project_id, idempotency_key)
        if existing is not None:
            self._record_event(
                project_id=project_id,
                queue_item_id=existing.queue_item_id,
                event_type="idempotent_reuse",
                stage="enqueue",
                message="Existing queue item reused for idempotent request.",
            )
            return existing

        now = _now_iso()
        item = ProductionQueueItem(
            queue_item_id=_queue_id(),
            project_id=project_id,
            scene_id=payload.scene_id,
            shot_id=payload.shot_id,
            work_type=payload.work_type,
            canonical_type=canonical_type,
            canonical_id=payload.canonical_id,
            provider=payload.provider,
            status=ProductionQueueStatus.QUEUED,
            priority=payload.priority,
            idempotency_key=idempotency_key,
            dependency_policy=payload.dependency_policy,
            payload=payload.payload,
            max_attempts=payload.max_attempts,
            next_run_at=payload.next_run_at,
            created_at=now,
            updated_at=now,
        )
        created = self.storage.create_queue_item(item)
        for dep_create in payload.dependencies:
            self._save_dependency(created.queue_item_id, dep_create)
        self._record_event(
            project_id=created.project_id,
            queue_item_id=created.queue_item_id,
            event_type="queued",
            stage="enqueue",
            message="Production work queued.",
            details={
                "work_type": created.work_type.value,
                "canonical_type": created.canonical_type,
                "canonical_id": created.canonical_id or "",
            },
        )
        return created

    def _save_dependency(
        self,
        queue_item_id: str,
        dependency: ProductionQueueDependencyCreate,
    ) -> ProductionQueueDependency:
        now = _now_iso()
        dep = ProductionQueueDependency(
            dependency_id=f"pqd_{uuid.uuid4().hex[:16]}",
            queue_item_id=queue_item_id,
            depends_on_type=dependency.depends_on_type,
            depends_on_id=dependency.depends_on_id,
            required_status=dependency.required_status,
            status="pending",
            reason=dependency.reason,
            created_at=now,
            updated_at=now,
        )
        return self.storage.save_queue_dependency(dep)

    def enqueue_render_job(
        self,
        *,
        project_id: str,
        shot_id: str,
        provider: str | None = None,
        prompt: str = "",
        reference_assets: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        priority: int = 50,
        dependencies: list[ProductionQueueDependencyCreate] | None = None,
        idempotency_key: str | None = None,
    ) -> ProductionQueueItem:
        render_svc = self._get_render_service()
        job = render_svc.create_job(
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            prompt=prompt,
            reference_assets=reference_assets or [],
            parameters=parameters or {},
        )
        return self.enqueue_item(
            ProductionQueueItemCreate(
                project_id=project_id,
                scene_id=(parameters or {}).get("scene_id") if isinstance(parameters, dict) else None,
                shot_id=shot_id,
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id=job.id,
                provider=getattr(job, "provider", provider),
                priority=priority,
                idempotency_key=idempotency_key or f"render_job:{project_id}:{shot_id}:{job.id}",
                payload={
                    "prompt": prompt,
                    "reference_assets": reference_assets or [],
                    "parameters": parameters or {},
                },
                dependencies=dependencies or [],
            )
        )

    def enqueue_existing_render_job(
        self,
        *,
        job_id: str,
        priority: int = 50,
        dependencies: list[ProductionQueueDependencyCreate] | None = None,
        idempotency_key: str | None = None,
    ) -> ProductionQueueItem:
        render_svc = self._get_render_service()
        job = render_svc.get_job(job_id)
        if job is None:
            raise ValueError(f"Render job {job_id} not found")
        return self.enqueue_item(
            ProductionQueueItemCreate(
                project_id=job.project_id,
                scene_id=(job.input_payload.parameters or {}).get("scene_id") if job.input_payload else None,
                shot_id=job.shot_id,
                work_type=ProductionQueueWorkType.RENDER_JOB,
                canonical_type="render_job",
                canonical_id=job.id,
                provider=job.provider,
                priority=priority,
                idempotency_key=idempotency_key or f"render_job:{job.project_id}:{job.id}",
                payload={
                    "prompt": job.input_payload.prompt if job.input_payload else "",
                    "parameters": job.input_payload.parameters if job.input_payload else {},
                },
                dependencies=dependencies or [],
            )
        )

    def enqueue_scene_generation(
        self,
        *,
        project_id: str,
        scene_id: str,
        project: dict[str, Any],
        provider: str | None = None,
        priority: int = 50,
    ) -> dict[str, Any]:
        from app.services.scene_production_pipeline_service import SceneProductionPipelineService

        pipeline = SceneProductionPipelineService(render_svc=self._get_render_service())
        scene = pipeline._find_scene(project, scene_id)
        if scene is None:
            raise ValueError(f"Scene {scene_id} not found")
        shots = pipeline._resolve_ordered_shots(project, scene)
        if not shots:
            raise ValueError(f"Scene {scene_id} has no renderable shots")

        render_items: list[ProductionQueueItem] = []
        audio_items: list[ProductionQueueItem] = []
        for index, shot in enumerate(shots, start=1):
            shot_id = str(shot.get("shot_id") or f"{scene_id}_shot_{index:03d}").strip()
            prompt = pipeline._shot_prompt(scene, shot, index, len(shots))
            render_item = self.enqueue_render_job(
                project_id=project_id,
                shot_id=shot_id,
                provider=provider,
                prompt=prompt,
                reference_assets=shot.get("reference_assets") or shot.get("source_refs") or [],
                parameters={**(shot.get("parameters") or {}), "scene_id": scene_id, "queue_expanded": True},
                priority=priority,
                idempotency_key=f"scene_generation:{project_id}:{scene_id}:{shot_id}:render",
            )
            render_items.append(render_item)
            audio_item = self.enqueue_item(
                ProductionQueueItemCreate(
                    project_id=project_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    work_type=ProductionQueueWorkType.SHOT_AUDIO,
                    canonical_type="shot_audio",
                    canonical_id=f"{project_id}:{shot_id}:audio",
                    provider="audio_pipeline",
                    priority=max(0, priority - 5),
                    idempotency_key=f"scene_generation:{project_id}:{scene_id}:{shot_id}:audio",
                    payload={"render_queue_item_id": render_item.queue_item_id},
                    dependencies=[
                        ProductionQueueDependencyCreate(
                            depends_on_type=ProductionQueueDependencyType.QUEUE_ITEM,
                            depends_on_id=render_item.queue_item_id,
                            required_status="complete",
                            reason="Audio waits for rendered shot output.",
                        )
                    ],
                )
            )
            audio_items.append(audio_item)

        stitch_item = self.enqueue_item(
            ProductionQueueItemCreate(
                project_id=project_id,
                scene_id=scene_id,
                work_type=ProductionQueueWorkType.SCENE_STITCH,
                canonical_type="scene_stitch",
                canonical_id=f"{project_id}:{scene_id}:stitch",
                provider="ffmpeg",
                priority=max(0, priority - 10),
                idempotency_key=f"scene_generation:{project_id}:{scene_id}:stitch",
                payload={
                    "render_queue_item_ids": [item.queue_item_id for item in render_items],
                    "audio_queue_item_ids": [item.queue_item_id for item in audio_items],
                },
                dependencies=[
                    ProductionQueueDependencyCreate(
                        depends_on_type=ProductionQueueDependencyType.QUEUE_ITEM,
                        depends_on_id=item.queue_item_id,
                        required_status="complete",
                        reason="Scene stitch waits for shot audio work.",
                    )
                    for item in audio_items
                ],
            )
        )
        self._record_event(
            project_id=project_id,
            queue_item_id=stitch_item.queue_item_id,
            event_type="scene_queue_expanded",
            stage="scene_generation",
            message=f"Expanded scene {scene_id} into render, audio, and stitch queue items.",
            details={
                "scene_id": scene_id,
                "render_items": [item.queue_item_id for item in render_items],
                "audio_items": [item.queue_item_id for item in audio_items],
                "stitch_item": stitch_item.queue_item_id,
            },
        )
        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "render_items": render_items,
            "audio_items": audio_items,
            "stitch_item": stitch_item,
        }

    def list_items(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        work_type: str | None = None,
        provider: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ProductionQueuePage:
        return self.storage.list_queue_items(
            project_id=project_id,
            status=status,
            work_type=work_type,
            provider=provider,
            cursor=cursor,
            limit=limit,
        )

    def get_item(self, queue_item_id: str) -> ProductionQueueItem | None:
        return self.storage.get_queue_item(queue_item_id)

    def list_events(self, queue_item_id: str, limit: int = 100) -> list[ProductionQueueEvent]:
        return self.storage.list_queue_events(queue_item_id, limit=limit)

    def summarize(self, project_id: str | None = None) -> ProductionQueueSummary:
        summary = self.storage.get_queue_summary(project_id)
        provider_limits = self._provider_limits()
        global_limit = self._global_limit()
        for pressure in summary.provider_pressure:
            provider_key = pressure.provider.strip().lower()
            pressure.limit = provider_limits.get(provider_key, global_limit)
            pressure.status = "at_capacity" if pressure.limit <= pressure.active else "available"
        return summary

    def evaluate_dependencies(self, item: ProductionQueueItem) -> ProductionQueueSchedulerDecision:
        deps = self.storage.list_queue_dependencies(item.queue_item_id)
        blocked_by: list[str] = []
        failed_by: list[str] = []
        for dep in deps:
            status = self._dependency_status(dep)
            dep.status = status
            dep.updated_at = _now_iso()
            self.storage.save_queue_dependency(dep)
            if status == "failed":
                failed_by.append(f"{dep.depends_on_type.value}:{dep.depends_on_id}")
            elif status != "satisfied":
                blocked_by.append(f"{dep.depends_on_type.value}:{dep.depends_on_id}")

        if failed_by:
            return ProductionQueueSchedulerDecision(
                queue_item_id=item.queue_item_id,
                selected=False,
                reason="One or more dependencies failed.",
                provider=item.provider,
                project_id=item.project_id,
                blocked_by=failed_by,
            )
        if blocked_by:
            return ProductionQueueSchedulerDecision(
                queue_item_id=item.queue_item_id,
                selected=False,
                reason="Waiting for required dependencies.",
                provider=item.provider,
                project_id=item.project_id,
                blocked_by=blocked_by,
            )
        return ProductionQueueSchedulerDecision(
            queue_item_id=item.queue_item_id,
            selected=True,
            reason="All dependencies satisfied.",
            provider=item.provider,
            project_id=item.project_id,
        )

    def _dependency_status(self, dep: ProductionQueueDependency) -> str:
        required = (dep.required_status or "complete").strip()
        if dep.depends_on_type == ProductionQueueDependencyType.QUEUE_ITEM:
            other = self.storage.get_queue_item(dep.depends_on_id)
            if other is None:
                return "pending"
            if other.status.value in {"failed", "cancelled", "dead_lettered"}:
                return "failed"
            return "satisfied" if other.status.value == required else "pending"
        if dep.depends_on_type == ProductionQueueDependencyType.RENDER_JOB:
            job = self.storage.get_job(dep.depends_on_id)
            if job is None:
                return "pending"
            if job.status in {"failed", "cancelled"}:
                return "failed"
            return "satisfied" if job.status == required else "pending"
        if dep.depends_on_type == ProductionQueueDependencyType.MANUAL_GATE:
            return "satisfied" if str(dep.status or "").strip().lower() == "satisfied" else "pending"
        return "pending"

    def _mark_waiting_dependency(
        self,
        item: ProductionQueueItem,
        decision: ProductionQueueSchedulerDecision,
    ) -> ProductionQueueItem:
        item.status = ProductionQueueStatus.WAITING_DEPENDENCY
        item.reason = decision.reason
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        item.updated_at = _now_iso()
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="dependency_blocked",
            stage="schedule",
            message=decision.reason,
            details={"blocked_by": decision.blocked_by},
        )
        return item

    def refresh_waiting_dependencies(self, limit: int = 50) -> int:
        page = self.storage.list_queue_items(status=ProductionQueueStatus.WAITING_DEPENDENCY.value, limit=limit)
        updated = 0
        for item in page.items:
            decision = self.evaluate_dependencies(item)
            if decision.selected:
                item.status = ProductionQueueStatus.QUEUED
                item.reason = "Dependencies satisfied."
                item.updated_at = _now_iso()
                self.storage.update_queue_item(item)
                self._record_event(
                    project_id=item.project_id,
                    queue_item_id=item.queue_item_id,
                    event_type="dependency_satisfied",
                    stage="schedule",
                    message="Dependencies satisfied; item returned to queue.",
                )
                updated += 1
        return updated

    def cancel_item(self, queue_item_id: str, reason: str = "") -> ProductionQueueItem:
        item = self.storage.get_queue_item(queue_item_id)
        if item is None:
            raise ValueError("Queue item not found")
        item.status = ProductionQueueStatus.CANCELLED
        item.reason = reason or "Cancelled by user."
        item.failure = {"category": QueueFailureCategory.CANCELLED.value, "message": item.reason}
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        item.completed_at = _now_iso()
        item.updated_at = item.completed_at
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="cancelled",
            stage="cancel",
            message=item.reason,
        )
        if item.work_type == ProductionQueueWorkType.RENDER_JOB and item.canonical_id:
            try:
                render_svc = self._get_render_service()
                # Fire-and-forget cancellation is intentionally avoided; routes can call async separately later.
                job = render_svc.get_job(item.canonical_id)
                if job and job.status in {"pending", "rendering"}:
                    job.status = "cancelled"
                    job.updated_at = _now_iso()
                    render_svc._jobs[job.id] = job
                    if getattr(render_svc, "_storage", None):
                        render_svc._storage.save_job(job)
            except Exception as exc:
                logger.debug("Render cancellation sync skipped for queue item %s: %s", queue_item_id, exc)
        return item

    def retry_item(self, queue_item_id: str, reason: str = "") -> ProductionQueueItem:
        item = self.storage.get_queue_item(queue_item_id)
        if item is None:
            raise ValueError("Queue item not found")
        if item.status.value not in {"failed", "dead_lettered", "cancelled", "waiting_provider", "waiting_dependency"}:
            raise ValueError(f"Cannot retry queue item in status {item.status.value}")
        item.status = ProductionQueueStatus.QUEUED
        item.reason = reason or "Retry requested."
        item.failure = {}
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        item.completed_at = None
        item.next_run_at = _now_iso()
        item.updated_at = item.next_run_at
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="retry_scheduled",
            stage="retry",
            message=item.reason,
        )
        return item

    def recover_expired_leases(self) -> dict[str, Any]:
        now = _now_iso()
        count = self.storage.expire_stale_queue_leases(now)
        if count:
            self._record_event(
                project_id="system",
                queue_item_id=None,
                event_type="lease_expired",
                stage="recover",
                message=f"Recovered {count} expired queue lease(s).",
                details={"expired_leases": count},
            )
        return {"expired_leases": count, "recovered_at": now}

    def synchronize_render_items(self, limit: int = 100) -> int:
        page = self.storage.list_queue_items(status=ProductionQueueStatus.RUNNING.value, work_type=ProductionQueueWorkType.RENDER_JOB.value, limit=limit)
        updated = 0
        for item in page.items:
            if not item.canonical_id:
                continue
            job = self.storage.get_job(item.canonical_id)
            if job is None:
                continue
            if job.status == "complete":
                self._complete_item(item, {"render_job_id": job.id, "status": job.status})
                updated += 1
            elif job.status in {"failed", "cancelled"}:
                self._fail_item(
                    item,
                    category=QueueFailureCategory.PROVIDER_ERROR.value if job.status == "failed" else QueueFailureCategory.CANCELLED.value,
                    message=job.error_message or f"Render job {job.status}",
                    retryable=job.status == "failed",
                )
                updated += 1
        return updated

    def acquire_next_item(self) -> ProductionQueueItem | None:
        now = _now_iso()
        global_active = self.storage.count_active_queue_items()
        if global_active >= self._global_limit():
            return None
        for candidate in self.storage.list_queue_candidates(now=now, limit=50):
            if candidate.status.value not in {"queued", "waiting_provider"}:
                continue
            project_active = self.storage.count_active_queue_items(project_id=candidate.project_id)
            if project_active >= self._project_limit():
                self._defer_for_capacity(candidate, "Project queue capacity is full.")
                continue
            provider_active = self.storage.count_active_queue_items(provider=candidate.provider)
            provider_limit = self._provider_limit(candidate.provider)
            if provider_active >= provider_limit:
                self._defer_for_capacity(candidate, "Provider capacity is full.")
                continue
            decision = self.evaluate_dependencies(candidate)
            if not decision.selected:
                self._mark_waiting_dependency(candidate, decision)
                continue
            item = self.storage.acquire_queue_lease_for_item(
                queue_item_id=candidate.queue_item_id,
                owner_id=self.worker_owner_id,
                now=now,
                lease_expires_at=_future_iso(self.lease_seconds),
            )
            if item is None:
                continue
            self._record_event(
                project_id=item.project_id,
                queue_item_id=item.queue_item_id,
                event_type="lease_acquired",
                stage="schedule",
                message=decision.reason,
                details={
                    "lease_owner": self.worker_owner_id,
                    "global_active": global_active,
                    "project_active": project_active,
                    "provider_active": provider_active,
                    "provider_limit": provider_limit,
                },
            )
            return item
        return None

    def _defer_for_capacity(self, item: ProductionQueueItem, reason: str) -> None:
        if item.status == ProductionQueueStatus.WAITING_PROVIDER and item.reason == reason:
            return
        item.status = ProductionQueueStatus.WAITING_PROVIDER
        item.reason = reason
        item.updated_at = _now_iso()
        item.next_run_at = _future_iso(max(1, int(self.loop_interval_seconds)))
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="capacity_deferred",
            stage="schedule",
            message=reason,
            details={"provider": item.provider or "", "project_id": item.project_id},
        )

    async def run_once(self) -> dict[str, Any]:
        self._last_heartbeat_at = _now_iso()
        expired = self.storage.expire_stale_queue_leases(self._last_heartbeat_at)
        dependency_updates = self.refresh_waiting_dependencies(limit=50)
        render_sync_updates = self.synchronize_render_items(limit=100)
        item = self.acquire_next_item()
        if item is None:
            return {
                "status": "idle",
                "expired_leases": expired,
                "dependency_updates": dependency_updates,
                "render_sync_updates": render_sync_updates,
            }
        self._active_item_id = item.queue_item_id
        try:
            result = await self.execute_leased_item(item)
            return {
                "status": "executed",
                "queue_item_id": item.queue_item_id,
                "result": result,
                "expired_leases": expired,
                "dependency_updates": dependency_updates,
                "render_sync_updates": render_sync_updates,
            }
        finally:
            self._active_item_id = None

    async def execute_leased_item(self, item: ProductionQueueItem) -> dict[str, Any]:
        start = perf_counter()
        attempt = ProductionQueueAttempt(
            attempt_id=_attempt_id(),
            queue_item_id=item.queue_item_id,
            attempt_number=item.attempt_count,
            lease_owner=self.worker_owner_id,
            status="running",
            started_at=_now_iso(),
        )
        self.storage.save_queue_attempt(attempt)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="dispatch_started",
            stage=item.work_type.value,
            message="Queue item dispatch started.",
        )
        try:
            if item.work_type == ProductionQueueWorkType.RENDER_JOB:
                result = await self._execute_render_item(item)
            else:
                result = self._complete_inspection_only_item(item)
            attempt.status = "complete"
            attempt.completed_at = _now_iso()
            attempt.duration_ms = int((perf_counter() - start) * 1000)
            attempt.result = result
            self.storage.save_queue_attempt(attempt)
            log_stage_event(
                project_id=item.project_id,
                job_id=item.canonical_id,
                provider=item.provider,
                stage=f"production_queue.{item.work_type.value}",
                duration_ms=attempt.duration_ms,
                extra={"queue_item_id": item.queue_item_id, "status": result.get("status", "")},
            )
            return result
        except Exception as exc:
            duration_ms = int((perf_counter() - start) * 1000)
            category = self._failure_category(exc)
            attempt.status = "failed"
            attempt.completed_at = _now_iso()
            attempt.duration_ms = duration_ms
            attempt.error_type = category
            attempt.error_message = str(exc)
            self.storage.save_queue_attempt(attempt)
            self._fail_item(item, category=category, message=str(exc), retryable=True)
            log_stage_event(
                project_id=item.project_id,
                job_id=item.canonical_id,
                provider=item.provider,
                stage=f"production_queue.{item.work_type.value}",
                duration_ms=duration_ms,
                extra={"queue_item_id": item.queue_item_id, "status": "failed", "error_type": category},
            )
            return {"status": "failed", "error": str(exc), "error_type": category}

    async def _execute_render_item(self, item: ProductionQueueItem) -> dict[str, Any]:
        if not item.canonical_id:
            raise ValueError("Queued render item does not reference a render job")
        render_svc = self._get_render_service()
        job = render_svc.get_job(item.canonical_id)
        if job is None:
            raise ValueError(f"Render job {item.canonical_id} not found")
        if job.status == "complete":
            self._complete_item(item, {"render_job_id": job.id, "status": job.status})
            return {"status": "complete", "render_job_id": job.id}
        if job.status in {"failed", "cancelled"}:
            self._fail_item(
                item,
                category=QueueFailureCategory.PROVIDER_ERROR.value if job.status == "failed" else QueueFailureCategory.CANCELLED.value,
                message=job.error_message or f"Render job {job.status}",
                retryable=job.status == "failed",
            )
            return {"status": job.status, "render_job_id": job.id}
        submitted = await render_svc.submit_job(job.id)
        if submitted.status == "complete":
            self._complete_item(item, {"render_job_id": submitted.id, "status": submitted.status})
            return {"status": "complete", "render_job_id": submitted.id}
        if submitted.status in {"failed", "cancelled"}:
            self._fail_item(
                item,
                category=QueueFailureCategory.PROVIDER_ERROR.value if submitted.status == "failed" else QueueFailureCategory.CANCELLED.value,
                message=submitted.error_message or f"Render job {submitted.status}",
                retryable=submitted.status == "failed",
            )
            return {"status": submitted.status, "render_job_id": submitted.id}
        item.status = ProductionQueueStatus.RUNNING
        item.reason = "Render submitted to provider; waiting for canonical render completion."
        item.result = {"render_job_id": submitted.id, "render_status": submitted.status}
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        item.updated_at = _now_iso()
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="dispatch_completed",
            stage="render_job",
            message=item.reason,
            details=item.result,
        )
        return {"status": "running", "render_job_id": submitted.id, "render_status": submitted.status}

    def _complete_inspection_only_item(self, item: ProductionQueueItem) -> dict[str, Any]:
        result = {
            "status": "complete",
            "inspection_only": True,
            "message": f"{item.work_type.value} queue orchestration record completed without direct execution handler.",
        }
        self._complete_item(item, result)
        return result

    def _complete_item(self, item: ProductionQueueItem, result: dict[str, Any]) -> ProductionQueueItem:
        item.status = ProductionQueueStatus.COMPLETE
        item.result = result
        item.reason = "Queue item complete."
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        item.completed_at = _now_iso()
        item.updated_at = item.completed_at
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="dispatch_completed",
            stage=item.work_type.value,
            message=item.reason,
            details=result,
        )
        return item

    def _fail_item(
        self,
        item: ProductionQueueItem,
        *,
        category: str,
        message: str,
        retryable: bool,
    ) -> ProductionQueueItem:
        terminal = item.attempt_count >= item.max_attempts or not retryable
        item.status = ProductionQueueStatus.DEAD_LETTERED if terminal else ProductionQueueStatus.FAILED
        item.failure = {
            "category": category,
            "message": message,
            "retryable": bool(retryable and not terminal),
            "recorded_at": _now_iso(),
        }
        item.reason = message
        item.lease_owner = None
        item.lease_acquired_at = None
        item.lease_expires_at = None
        item.completed_at = _now_iso()
        item.updated_at = item.completed_at
        self.storage.update_queue_item(item)
        self._record_event(
            project_id=item.project_id,
            queue_item_id=item.queue_item_id,
            event_type="dispatch_failed",
            stage=item.work_type.value,
            message=message,
            details=item.failure,
        )
        return item

    def _failure_category(self, exc: Exception) -> str:
        if isinstance(exc, StabilityError):
            return exc.error_type
        name = exc.__class__.__name__.lower()
        if "timeout" in name:
            return QueueFailureCategory.TIMEOUT.value
        if "value" in name:
            return QueueFailureCategory.VALIDATION_ERROR.value
        return QueueFailureCategory.UNKNOWN.value

    def diagnostics(self, project_id: str | None = None) -> dict[str, Any]:
        summary = self.summarize(project_id)
        return {
            "captured_at": _now_iso(),
            "project_id": project_id or "",
            "worker": self.worker_status().model_dump(),
            "summary": summary.model_dump(),
            "recovery": {"stale_leases": summary.stale_leases},
        }

    def worker_status(self) -> ProductionQueueWorkerStatus:
        return ProductionQueueWorkerStatus(
            enabled=True,
            owner_id=self.worker_owner_id,
            running=self._running,
            last_heartbeat_at=self._last_heartbeat_at,
            active_item_id=self._active_item_id,
            loop_interval_seconds=self.loop_interval_seconds,
            lease_seconds=self.lease_seconds,
        )

    async def worker_loop(self) -> None:
        self._running = True
        logger.info("PRODUCTION_QUEUE_WORKER_STARTED | owner=%s", self.worker_owner_id)
        try:
            while self._running:
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Production queue worker loop error: %s", exc)
                await asyncio.sleep(self.loop_interval_seconds)
        finally:
            self._running = False
            logger.info("PRODUCTION_QUEUE_WORKER_STOPPED | owner=%s", self.worker_owner_id)

    def start_background_worker(self) -> asyncio.Task:
        if self._worker_task and not self._worker_task.done():
            return self._worker_task
        self._worker_task = asyncio.create_task(self.worker_loop())
        return self._worker_task

    async def stop_background_worker(self) -> None:
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass


production_queue_service = ProductionQueueService()
