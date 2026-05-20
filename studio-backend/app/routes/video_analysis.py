from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.project_store import project_store
from app.services.video_asset_service import video_asset_service
from app.services.keyframe_extraction_service import keyframe_extraction_service
from app.services.frame_analysis_service import frame_analysis_service

router = APIRouter(prefix="/api/f51/studio", tags=["video-analysis"])


class ExtractKeyframesPayload(BaseModel):
    interval_seconds: int = 5
    max_frames: int = 20
    overwrite: bool = False
    extraction_reason: str = "interval"


class RegisterFrameAnalysisPayload(BaseModel):
    keyframe_id: Optional[str] = None
    caption: str = ""
    mood_tags: List[str] = Field(default_factory=list)
    lighting_tags: List[str] = Field(default_factory=list)
    camera_tags: List[str] = Field(default_factory=list)
    embeddings: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalyzeAssetKeyframesPayload(BaseModel):
    pass


@router.post("/video-assets/{asset_id}/extract-keyframes")
def extract_video_asset_keyframes(asset_id: str, payload: ExtractKeyframesPayload):
    try:
        extraction_method = payload.extraction_reason or "representative"
        keyframes = keyframe_extraction_service.extract_keyframes_for_asset(
            asset_id=asset_id,
            interval_seconds=payload.interval_seconds,
            max_frames=payload.max_frames,
            overwrite=payload.overwrite,
            extraction_method=extraction_method,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"keyframes": [keyframe.model_dump() for keyframe in keyframes]}


@router.get("/video-assets/{asset_id}/keyframes")
def list_video_asset_keyframes(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    keyframes = keyframe_extraction_service.list_keyframes_for_asset(asset_id)
    return {"keyframes": [keyframe.model_dump() for keyframe in keyframes]}


@router.get("/projects/{project_id}/keyframes")
def list_project_keyframes(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    keyframes = keyframe_extraction_service.list_keyframes_for_project(project_id)
    return {"keyframes": [keyframe.model_dump() for keyframe in keyframes]}


@router.get("/video-keyframes/{keyframe_id}")
def get_video_keyframe(keyframe_id: str):
    keyframe = keyframe_extraction_service.get_keyframe(keyframe_id)
    if keyframe is None:
        raise HTTPException(status_code=404, detail="Video keyframe not found")
    return {"keyframe": keyframe.model_dump()}


@router.post("/video-keyframes/{keyframe_id}/analyze")
def analyze_video_keyframe(keyframe_id: str):
    try:
        row = frame_analysis_service.analyze_keyframe(keyframe_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"analysis": row.model_dump(), "advisory_only": True}


@router.post("/video-assets/{asset_id}/analyze-keyframes")
def analyze_video_asset_keyframes(asset_id: str, payload: AnalyzeAssetKeyframesPayload):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    try:
        rows = frame_analysis_service.analyze_asset_keyframes(asset_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"analyses": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/video-assets/{asset_id}/frame-analyses")
def list_video_asset_frame_analyses(asset_id: str):
    asset = video_asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Video asset not found")
    rows = frame_analysis_service.list_analyses_for_asset(asset_id)
    return {"analyses": [row.model_dump() for row in rows], "advisory_only": True}


@router.get("/projects/{project_id}/frame-analyses")
def list_project_frame_analyses(project_id: str):
    current = project_store.get_project(project_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = frame_analysis_service.list_analyses_for_project(project_id)
    return {"analyses": [row.model_dump() for row in rows], "advisory_only": True}
