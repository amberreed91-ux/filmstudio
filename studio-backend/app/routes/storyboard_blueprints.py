from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.services.stability import StabilityError
from app.services.storyboard_blueprint_service import storyboard_blueprint_service


router = APIRouter(prefix="/api/f51/studio", tags=["storyboard-blueprints"])


class CreateStoryboardBlueprintRequest(BaseModel):
    mode: str = "create_or_update_draft"
    shot_count: int | None = Field(default=None, ge=1, le=20)
    source: str = "scene"
    preserve_locked_shots: bool = True
    regeneration_reason: str = "initial_storyboard"
    create_new_version: bool = False


class ApproveStoryboardVersionRequest(BaseModel):
    approved_by: str = "creator"
    acknowledged_warnings: list[str] = Field(default_factory=list)


class RenderStoryboardShotRequest(BaseModel):
    provider: str | None = None
    submit: bool = False


class UpdateStoryboardShotRequest(BaseModel):
    intent: dict[str, Any] | None = None
    visual_plan: dict[str, Any] | None = None
    continuity_plan: dict[str, Any] | None = None
    render_contract: dict[str, Any] | None = None
    change_reason: str = "creator_storyboard_update"


class LockStoryboardShotRequest(BaseModel):
    locked: bool = True


class BackfillStoryboardBlueprintsRequest(BaseModel):
    shot_count: int | None = Field(default=None, ge=1, le=20)
    preserve_locked_shots: bool = True


class CreateStoryboardVersionRequest(BaseModel):
    shot_count: int | None = Field(default=None, ge=1, le=20)
    preserve_locked_shots: bool = True
    change_reason: str = "creator_storyboard_regeneration"


class CreateStoryboardShotRequest(BaseModel):
    shot_id: str | None = None
    intent: dict[str, Any] = Field(default_factory=dict)
    visual_plan: dict[str, Any] = Field(default_factory=dict)
    continuity_plan: dict[str, Any] = Field(default_factory=dict)
    render_contract: dict[str, Any] = Field(default_factory=dict)
    change_reason: str = "creator_shot_create"


class ReorderStoryboardShotsRequest(BaseModel):
    ordered_storyboard_shot_ids: list[str]


def _serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _handle_stability(exc: StabilityError) -> HTTPException:
    if exc.error_type == "validation_error":
        return HTTPException(status_code=422, detail=exc.to_dict())
    if exc.error_type == "state_error":
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.to_dict())
    if exc.error_type == "provider_error":
        return HTTPException(status_code=502, detail=exc.to_dict())
    if exc.error_type == "persistence_error":
        return HTTPException(status_code=503, detail=exc.to_dict())
    return HTTPException(status_code=500, detail=exc.to_dict())


@router.post("/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint")
def create_storyboard_blueprint(
    project_id: str,
    scene_id: str,
    payload: CreateStoryboardBlueprintRequest = Body(default_factory=CreateStoryboardBlueprintRequest),
) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.get_or_create_blueprint(
                project_id=project_id,
                scene_id=scene_id,
                shot_count=payload.shot_count,
                change_reason=payload.regeneration_reason or payload.mode,
                preserve_locked_shots=payload.preserve_locked_shots,
                create_new_version=payload.create_new_version,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.get("/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint")
def get_storyboard_blueprint(project_id: str, scene_id: str) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.get_blueprint_detail(
                project_id=project_id,
                scene_id=scene_id,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.get("/projects/{project_id}/storyboard-blueprints")
def list_storyboard_blueprints(project_id: str) -> list[dict[str, Any]]:
    try:
        return storyboard_blueprint_service.list_project_blueprints(project_id)
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.post("/projects/{project_id}/storyboard-blueprints/backfill")
def backfill_storyboard_blueprints(
    project_id: str,
    payload: BackfillStoryboardBlueprintsRequest = Body(default_factory=BackfillStoryboardBlueprintsRequest),
) -> dict[str, Any]:
    try:
        return storyboard_blueprint_service.backfill_project_blueprints(
            project_id=project_id,
            shot_count=payload.shot_count,
            preserve_locked_shots=payload.preserve_locked_shots,
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.post("/storyboard-blueprints/{blueprint_id}/versions/{version_id}/approve")
def approve_storyboard_version(
    blueprint_id: str,
    version_id: str,
    payload: ApproveStoryboardVersionRequest = Body(default_factory=ApproveStoryboardVersionRequest),
) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.approve_version(
                blueprint_id=blueprint_id,
                version_id=version_id,
                approved_by=payload.approved_by,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.get("/storyboard-blueprints/{blueprint_id}/versions")
def list_storyboard_versions(blueprint_id: str) -> list[dict[str, Any]]:
    try:
        return _serialize(storyboard_blueprint_service.list_versions(blueprint_id))
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.post("/storyboard-blueprints/{blueprint_id}/versions")
def create_storyboard_version(
    blueprint_id: str,
    payload: CreateStoryboardVersionRequest = Body(default_factory=CreateStoryboardVersionRequest),
) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.create_version(
                blueprint_id=blueprint_id,
                shot_count=payload.shot_count,
                change_reason=payload.change_reason,
                preserve_locked_shots=payload.preserve_locked_shots,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.post("/storyboard-blueprints/{blueprint_id}/shots")
def create_storyboard_shot(
    blueprint_id: str,
    payload: CreateStoryboardShotRequest,
) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.create_shot(
                blueprint_id=blueprint_id,
                shot_id=payload.shot_id,
                intent=payload.intent,
                visual_plan=payload.visual_plan,
                continuity_plan=payload.continuity_plan,
                render_contract=payload.render_contract,
                change_reason=payload.change_reason,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.put("/storyboard-blueprints/{blueprint_id}/shots/reorder")
def reorder_storyboard_shots(
    blueprint_id: str,
    payload: ReorderStoryboardShotsRequest,
) -> list[dict[str, Any]]:
    try:
        return _serialize(
            storyboard_blueprint_service.reorder_shots(
                blueprint_id=blueprint_id,
                ordered_storyboard_shot_ids=payload.ordered_storyboard_shot_ids,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.patch("/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}")
def update_storyboard_shot(
    blueprint_id: str,
    storyboard_shot_id: str,
    payload: UpdateStoryboardShotRequest,
) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.update_shot(
                blueprint_id=blueprint_id,
                storyboard_shot_id=storyboard_shot_id,
                intent=payload.intent,
                visual_plan=payload.visual_plan,
                continuity_plan=payload.continuity_plan,
                render_contract=payload.render_contract,
                change_reason=payload.change_reason,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.delete("/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}")
def delete_storyboard_shot(
    blueprint_id: str,
    storyboard_shot_id: str,
) -> list[dict[str, Any]]:
    try:
        return _serialize(
            storyboard_blueprint_service.delete_shot(
                blueprint_id=blueprint_id,
                storyboard_shot_id=storyboard_shot_id,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.patch("/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/lock")
def lock_storyboard_shot(
    blueprint_id: str,
    storyboard_shot_id: str,
    payload: LockStoryboardShotRequest,
) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.lock_shot(
                blueprint_id=blueprint_id,
                storyboard_shot_id=storyboard_shot_id,
                locked=payload.locked,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.post("/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render-contract")
def build_storyboard_render_contract(blueprint_id: str, storyboard_shot_id: str) -> dict[str, Any]:
    try:
        return _serialize(
            storyboard_blueprint_service.build_render_contract(
                blueprint_id=blueprint_id,
                storyboard_shot_id=storyboard_shot_id,
            )
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc


@router.post("/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render")
async def render_storyboard_shot(
    blueprint_id: str,
    storyboard_shot_id: str,
    payload: RenderStoryboardShotRequest = Body(default_factory=RenderStoryboardShotRequest),
) -> dict[str, Any]:
    try:
        job = storyboard_blueprint_service.render_storyboard_shot(
            blueprint_id=blueprint_id,
            storyboard_shot_id=storyboard_shot_id,
            provider=payload.provider,
        )
        if payload.submit:
            from app.services.render import render_service

            job = await render_service.submit_job(job.id)
        return _serialize(job)
    except StabilityError as exc:
        raise _handle_stability(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/image")
def generate_storyboard_shot_image(
    blueprint_id: str,
    storyboard_shot_id: str,
    provider: str = "qwen-image-max",
) -> dict[str, Any]:
    try:
        shot = storyboard_blueprint_service.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.blueprint_id != blueprint_id:
            raise HTTPException(status_code=404, detail="Storyboard shot not found")
        return storyboard_blueprint_service.generate_storyboard_image_for_scene_shot(
            project_id=shot.project_id,
            scene_id=shot.scene_id,
            provider=provider,
            shot_number=shot.shot_number,
            storyboard_shot_id=shot.storyboard_shot_id,
        )
    except StabilityError as exc:
        raise _handle_stability(exc) from exc
