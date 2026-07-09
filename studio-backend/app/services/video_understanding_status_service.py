from __future__ import annotations

from typing import Dict, List, Optional

from app.models import VideoUnderstandingStatus
from app.services.keyframe_extraction_service import keyframe_extraction_service
from app.services.semantic_memory_service import semantic_memory_service
from app.services.semantic_search_service import semantic_search_service
from app.services.video_asset_service import video_asset_service


class VideoUnderstandingStatusService:
    """Computes true video understanding readiness from existing artifacts."""

    def __init__(self, video_assets=None, keyframes=None, semantic_memory=None, semantic_search=None):
        self._video_assets = video_assets or video_asset_service
        self._keyframes = keyframes or keyframe_extraction_service
        self._semantic_memory = semantic_memory or semantic_memory_service
        self._semantic_search = semantic_search or semantic_search_service

    def get_asset_status(self, asset_id: str) -> VideoUnderstandingStatus:
        asset = self._video_assets.get_asset(asset_id)
        if asset is None:
            raise ValueError("Video asset not found")

        ingestion_complete = False
        try:
            ingestion_complete = bool(self._video_assets.validate_asset_accessible(asset))
        except Exception:
            ingestion_complete = False

        keyframes = self._keyframes.list_keyframes_for_asset(asset_id)
        keyframes_complete = len(keyframes) > 0

        analyses = self._semantic_search.list_analyses_for_asset(asset_id)
        memory_records = self._semantic_memory.list_memories_for_asset(asset_id)
        memory_complete = len(memory_records) > 0

        analysis_complete = False
        if keyframes_complete:
            keyframe_ids = {row.keyframe_id for row in keyframes}
            analyzed_ids = {row.keyframe_id for row in analyses if row.keyframe_id}
            # Count as complete when every extracted keyframe has at least one analysis,
            # or when analysis rows exist for asset-level without keyframe ids.
            analysis_complete = keyframe_ids.issubset(analyzed_ids) or (
                len(analyses) >= len(keyframes) and any(not row.keyframe_id for row in analyses)
            )

        understanding_enabled = bool(keyframes_complete and analysis_complete and memory_complete)
        return VideoUnderstandingStatus(
            asset_id=asset_id,
            ingestion_complete=ingestion_complete,
            keyframes_complete=keyframes_complete,
            analysis_complete=analysis_complete,
            memory_complete=memory_complete,
            understanding_enabled=understanding_enabled,
        )

    def list_project_statuses(self, project_id: str) -> Dict[str, object]:
        assets = self._video_assets.list_assets_for_project(project_id)
        statuses: List[VideoUnderstandingStatus] = []
        for asset in assets:
            statuses.append(self.get_asset_status(asset.asset_id))
        enabled_count = sum(1 for row in statuses if row.understanding_enabled)
        return {
            "project_id": project_id,
            "statuses": statuses,
            "understanding_enabled": enabled_count > 0,
            "enabled_asset_count": enabled_count,
            "asset_count": len(statuses),
        }


video_understanding_status_service = VideoUnderstandingStatusService()
