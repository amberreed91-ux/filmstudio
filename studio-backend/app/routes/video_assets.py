from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.project_store import project_store
from app.services.video_asset_service import video_asset_service
from app.services.video_metadata_matching_service import video_metadata_matching_service

router = APIRouter(prefix="/api/f51/studio", tags=["video-assets"])
logger = logging.getLogger(__name__)


class RegisterVideoAssetPayload(BaseModel):
    source_type: str
    title: str
    description: Optional[str] = None
    source_url: Optional[str] = None
    local_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateVideoAssetStatusPayload(BaseModel):
    status: str
    metadata_patch: Dict[str, Any] = Field(default_factory=dict)


class AttachVideoAssetProjectPayload(BaseModel):
    project_id: str


@router.post("/projects/{project_id}/video-assets")
def register_video_asset(project_id: str, payload: RegisterVideoAssetPayload):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        if payload.source_type == "generated_output":
            asset = video_asset_service.register_generated_output(
                project_id=project_id,
                source_url=payload.source_url or "",
                title=payload.title,
                description=payload.description,
                duration_seconds=payload.duration_seconds,
                metadata=payload.metadata,
            )
        elif payload.source_type == "local_file":
            asset = video_asset_service.register_local_file(
                project_id=project_id,
                local_path=payload.local_path or "",
                title=payload.title,
                description=payload.description,
                duration_seconds=payload.duration_seconds,
                metadata=payload.metadata,
            )
        elif payload.source_type == "external_url":
            asset = video_asset_service.register_external_url(
                project_id=project_id,
                source_url=payload.source_url or "",
                title=payload.title,
                description=payload.description,
                duration_seconds=payload.duration_seconds,
                metadata=payload.metadata,
            )
        elif payload.source_type == "uploaded_file":
            asset = video_asset_service.register_uploaded_file(
                project_id=project_id,
                local_path=payload.local_path,
                title=payload.title,
                description=payload.description,
                duration_seconds=payload.duration_seconds,
                metadata=payload.metadata,
            )
        else:
            raise ValueError("Invalid source_type")
        return {"asset": asset.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/video-assets")
def list_video_assets_for_project(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    assets = video_asset_service.list_assets_for_project(project_id)
    return {"assets": [asset.model_dump() for asset in assets]}


@router.get("/video-assets")
def list_video_assets(source_type: Optional[str] = None):
    assets = video_asset_service.list_assets(source_type=source_type)
    return {"assets": [asset.model_dump() for asset in assets]}


@router.post("/video-assets/upload")
@router.post("/video-assets/upload/")
async def upload_video_asset(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    metadata_json: Optional[str] = Form(None),
):
    logger.info(
        "[StudyRoomUpload] route_hit path=/video-assets/upload filename=%s content_type=%s project_id=%s",
        file.filename,
        file.content_type,
        project_id,
    )
    normalized_project_id = (project_id or "").strip()
    if normalized_project_id:
        current = project_store.get_project(normalized_project_id)
        if current is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {normalized_project_id}")
    else:
        normalized_project_id = "unassigned"

    raw_name = (file.filename or "uploaded_video").strip()
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw_name) or "uploaded_video"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output_root = Path(__file__).resolve().parents[2] / "outputs" / "uploads" / "video-assets" / normalized_project_id
    output_root.mkdir(parents=True, exist_ok=True)
    saved_path = output_root / f"{stamp}_{uuid4().hex[:8]}_{safe_name}"
    content = await file.read()
    saved_path.write_bytes(content)

    metadata: Dict[str, Any] = {
        "original_filename": raw_name,
        "content_type": file.content_type or "application/octet-stream",
    }
    if tags:
        metadata["tags"] = [part.strip() for part in tags.split(",") if part.strip()]
    if notes:
        metadata["notes"] = notes
    if metadata_json:
        try:
            extra = json.loads(metadata_json)
            if isinstance(extra, dict):
                metadata.update(extra)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata_json must be a valid JSON object")

    try:
        asset = video_asset_service.register_uploaded_file(
            project_id=normalized_project_id,
            local_path=str(saved_path),
            title=(title or Path(raw_name).stem or "Uploaded Video").strip(),
            description=description,
            metadata=metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        video_metadata_matching_service.auto_match_uploaded_asset(asset.asset_id)
    except Exception:
        pass
    return {"asset": asset.model_dump()}


@router.get("/video-assets/unmatched")
def list_unmatched_assets():
    assets = video_metadata_matching_service.list_unmatched_assets()
    return {"assets": [a.model_dump() for a in assets]}


@router.get("/video-assets/{asset_id}")
def get_video_asset(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return {"asset": asset.model_dump()}


@router.post("/video-assets/{asset_id}/status")
def update_video_asset_status(asset_id: str, payload: UpdateVideoAssetStatusPayload):
    try:
        asset = video_asset_service.update_asset_status(
            asset_id=asset_id,
            status=payload.status,
            metadata_patch=payload.metadata_patch,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return {"asset": asset.model_dump()}


@router.post("/video-assets/{asset_id}/attach-project")
def attach_video_asset_to_project(asset_id: str, payload: AttachVideoAssetProjectPayload):
    target_project_id = payload.project_id.strip()
    current = project_store.get_project(target_project_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Project not found: {target_project_id}")
    asset = video_asset_service.attach_asset_to_project(asset_id=asset_id, project_id=target_project_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    return {"asset": asset.model_dump()}


@router.post("/video-assets/{asset_id}/auto-match-metadata")
def auto_match_metadata(asset_id: str):
    result = video_metadata_matching_service.auto_match_uploaded_asset(asset_id)
    if not result:
        raise HTTPException(status_code=404, detail="Asset not found or no metadata match found")
    match_dict = result["match"].model_dump()
    return {
        "match": match_dict,
        "confidence": result["confidence"],
        "match_status": result["match_status"],
        "metadata_record": result["metadata_record"],
    }


@router.get("/video-assets/{asset_id}/metadata-matches")
def list_metadata_matches(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    matches = video_metadata_matching_service.list_matches_for_asset(asset_id)
    return {"matches": [m.model_dump() for m in matches]}


@router.post("/video-assets/{asset_id}/metadata-matches/{match_id}/confirm")
def confirm_metadata_match(asset_id: str, match_id: str):
    match = video_metadata_matching_service.confirm_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.asset_id != asset_id:
        raise HTTPException(status_code=400, detail="Match does not belong to this asset")
    return {"match": match.model_dump()}


@router.post("/video-assets/{asset_id}/metadata-matches/{match_id}/reject")
def reject_metadata_match(asset_id: str, match_id: str):
    match = video_metadata_matching_service.reject_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.asset_id != asset_id:
        raise HTTPException(status_code=400, detail="Match does not belong to this asset")
    return {"match": match.model_dump()}
