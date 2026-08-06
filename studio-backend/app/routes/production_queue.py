from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from app.models.production_queue import (
    ProductionQueueItem,
    ProductionQueueItemCreate,
    ProductionQueuePage,
    ProductionQueueSummary,
)
from app.services.production_queue_service import production_queue_service


router = APIRouter(prefix="/api/f51/studio/production-queue", tags=["production-queue"])


class QueueCancelRequest(BaseModel):
    reason: str = ""


class QueueRetryRequest(BaseModel):
    reason: str = ""


class QueueSceneRequest(BaseModel):
    provider: str | None = None
    priority: int = 50


@router.post("/items", response_model=ProductionQueueItem)
def create_queue_item(payload: ProductionQueueItemCreate):
    try:
        return production_queue_service.enqueue_item(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/scenes/{scene_id}/queue")
def queue_scene_generation(
    project_id: str,
    scene_id: str,
    payload: QueueSceneRequest = Body(default_factory=QueueSceneRequest),
):
    try:
        from app.services.project_store import project_store

        project = project_store.get_project(project_id)
        if not isinstance(project, dict):
            raise ValueError(f"Project {project_id} not found")
        result = production_queue_service.enqueue_scene_generation(
            project_id=project_id,
            scene_id=scene_id,
            project=project,
            provider=payload.provider,
            priority=max(0, min(int(payload.priority), 100)),
        )
        return {
            "project_id": result["project_id"],
            "scene_id": result["scene_id"],
            "render_items": [item.model_dump() for item in result["render_items"]],
            "audio_items": [item.model_dump() for item in result["audio_items"]],
            "stitch_item": result["stitch_item"].model_dump(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/items/{queue_item_id}", response_model=ProductionQueueItem)
def get_queue_item(queue_item_id: str):
    item = production_queue_service.get_item(queue_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return item


@router.get("/projects/{project_id}/items", response_model=ProductionQueuePage)
def list_project_queue_items(
    project_id: str,
    status: str | None = None,
    work_type: str | None = None,
    provider: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return production_queue_service.list_items(
        project_id=project_id,
        status=status,
        work_type=work_type,
        provider=provider,
        cursor=cursor,
        limit=limit,
    )


@router.get("/summary", response_model=ProductionQueueSummary)
def get_global_queue_summary():
    return production_queue_service.summarize()


@router.get("/projects/{project_id}/summary", response_model=ProductionQueueSummary)
def get_project_queue_summary(project_id: str):
    return production_queue_service.summarize(project_id)


@router.post("/items/{queue_item_id}/cancel", response_model=ProductionQueueItem)
def cancel_queue_item(
    queue_item_id: str,
    payload: QueueCancelRequest = Body(default_factory=QueueCancelRequest),
):
    try:
        return production_queue_service.cancel_item(queue_item_id, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/items/{queue_item_id}/retry", response_model=ProductionQueueItem)
def retry_queue_item(
    queue_item_id: str,
    payload: QueueRetryRequest = Body(default_factory=QueueRetryRequest),
):
    try:
        return production_queue_service.retry_item(queue_item_id, reason=payload.reason)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 409
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.get("/items/{queue_item_id}/events")
def list_queue_events(
    queue_item_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    if production_queue_service.get_item(queue_item_id) is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return [event.model_dump() for event in production_queue_service.list_events(queue_item_id, limit=limit)]


@router.get("/diagnostics")
def get_queue_diagnostics(project_id: str | None = None):
    return production_queue_service.diagnostics(project_id)


@router.post("/recover")
def recover_queue_leases():
    return production_queue_service.recover_expired_leases()


@router.post("/worker/run-once")
async def run_queue_worker_once():
    return await production_queue_service.run_once()
