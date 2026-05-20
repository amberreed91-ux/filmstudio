from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models import FrameAnalysisRecord
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService
from app.services.vision_model_adapter import VisionModelAdapter, build_vision_model_adapter


class FrameAnalysisService:
    def __init__(
        self,
        storage=None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
        video_asset_service: Optional[VideoAssetService] = None,
        vision_adapter: Optional[VisionModelAdapter] = None,
    ):
        self._storage = storage
        self._keyframe_service = keyframe_service
        self._video_asset_service = video_asset_service
        self._vision_adapter = vision_adapter or build_vision_model_adapter()
        self._fallback_analyses: Dict[str, FrameAnalysisRecord] = {}

    def _storage_supports(self, method_name: str) -> bool:
        return bool(self._storage) and hasattr(self._storage, method_name)

    def _save_analysis(self, record: FrameAnalysisRecord) -> FrameAnalysisRecord:
        if self._storage_supports("save_frame_analysis"):
            return self._storage.save_frame_analysis(record)
        if self._storage_supports("save_video_frame_analysis"):
            return self._storage.save_video_frame_analysis(record)
        self._fallback_analyses[record.analysis_id] = record
        return record

    def _resolve_adapter(self) -> VisionModelAdapter:
        if self._vision_adapter is not None:
            return self._vision_adapter
        self._vision_adapter = build_vision_model_adapter()
        return self._vision_adapter

    def _analysis_id(self) -> str:
        return f"analysis-{uuid.uuid4().hex[:12]}"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_analysis(self, analysis_id: str) -> Optional[FrameAnalysisRecord]:
        if self._storage_supports("get_frame_analysis"):
            return self._storage.get_frame_analysis(analysis_id)
        return self._fallback_analyses.get(analysis_id)

    def list_analyses_for_asset(self, asset_id: str) -> List[FrameAnalysisRecord]:
        if self._storage_supports("list_frame_analyses_for_asset"):
            return self._storage.list_frame_analyses_for_asset(asset_id)
        if self._storage_supports("list_video_frame_analyses_for_asset"):
            return self._storage.list_video_frame_analyses_for_asset(asset_id)
        return [row for row in self._fallback_analyses.values() if row.asset_id == asset_id]

    def list_analyses_for_project(self, project_id: str) -> List[FrameAnalysisRecord]:
        if self._storage_supports("list_frame_analyses_for_project"):
            return self._storage.list_frame_analyses_for_project(project_id)
        return [row for row in self._fallback_analyses.values() if row.project_id == project_id]

    def analyze_keyframe(self, keyframe_id: str) -> FrameAnalysisRecord:
        if not self._keyframe_service:
            raise ValueError("Keyframe service is not configured")

        keyframe = self._keyframe_service.get_keyframe(keyframe_id)
        if keyframe is None:
            raise ValueError("Video keyframe not found")

        image_path = (keyframe.image_path or keyframe.frame_path or "").strip()
        if not image_path:
            raise ValueError("Keyframe image path is missing")
        if not self._keyframe_service.validate_frame_exists(image_path):
            raise ValueError("Keyframe image file is not accessible")

        adapter = self._resolve_adapter()
        result = adapter.analyze_image(
            image_path,
            {
                "asset_id": keyframe.asset_id,
                "project_id": keyframe.project_id,
                "keyframe_id": keyframe.keyframe_id,
                "source_type": keyframe.source_type,
            },
        )

        record = FrameAnalysisRecord(
            analysis_id=self._analysis_id(),
            keyframe_id=keyframe.keyframe_id,
            asset_id=keyframe.asset_id,
            project_id=keyframe.project_id,
            caption=result.caption,
            visual_summary=result.visual_summary,
            mood_tags=result.mood_tags,
            lighting_tags=result.lighting_tags,
            composition_tags=result.composition_tags,
            color_palette=result.color_palette,
            detected_subjects=result.detected_subjects,
            camera_notes=result.camera_notes,
            confidence=result.confidence,
            provider=result.provider,
            model=result.model,
            status=result.status,
            created_at=self._now_iso(),
            metadata=result.metadata or {},
            # Backward compatibility fields
            camera_tags=result.composition_tags,
            embeddings=None,
        )
        return self._save_analysis(record)

    def analyze_asset_keyframes(self, asset_id: str) -> List[FrameAnalysisRecord]:
        if not self._keyframe_service:
            raise ValueError("Keyframe service is not configured")
        keyframes = self._keyframe_service.list_keyframes_for_asset(asset_id)
        if not keyframes:
            raise ValueError("No keyframes found for asset")
        rows: List[FrameAnalysisRecord] = []
        for frame in keyframes:
            rows.append(self.analyze_keyframe(frame.keyframe_id))
        return rows


frame_analysis_service = FrameAnalysisService()
