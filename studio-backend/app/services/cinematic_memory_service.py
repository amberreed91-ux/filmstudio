from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models import CinematicMemoryRecord
from app.services.frame_analysis_service import FrameAnalysisService
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService
from app.services.visual_embedding_service import VisualEmbeddingService


class CinematicMemoryService:
    def __init__(
        self,
        storage=None,
        frame_analysis_service: Optional[FrameAnalysisService] = None,
        visual_embedding_service: Optional[VisualEmbeddingService] = None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
        video_asset_service: Optional[VideoAssetService] = None,
    ):
        self._storage = storage
        self._frame_analysis_service = frame_analysis_service
        self._visual_embedding_service = visual_embedding_service
        self._keyframe_service = keyframe_service
        self._video_asset_service = video_asset_service

    def _id(self) -> str:
        return f"memory-{uuid.uuid4().hex[:12]}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_memory_record(self, record: CinematicMemoryRecord) -> CinematicMemoryRecord:
        if not self._storage:
            return record
        return self._storage.save_cinematic_memory_record(record)

    def build_memory_for_keyframe(self, keyframe_id: str) -> CinematicMemoryRecord:
        if not self._keyframe_service:
            raise ValueError("Keyframe service not configured")
        keyframe = self._keyframe_service.get_keyframe(keyframe_id)
        if keyframe is None:
            raise ValueError("Video keyframe not found")

        analyses = self._frame_analysis_service.list_analyses_for_asset(keyframe.asset_id) if self._frame_analysis_service else []
        analysis = next((a for a in analyses if a.keyframe_id == keyframe_id), None)

        embedding = self._visual_embedding_service._storage.get_visual_embedding_for_keyframe(keyframe_id) if self._visual_embedding_service and self._visual_embedding_service._storage else None

        visual_tags = []
        emotional_tags = []
        composition_tags = []
        lighting_tags = []
        summary = ""
        metadata: Dict[str, object] = {
            "source_type": keyframe.source_type,
            "asset_title": (self._video_asset_service.get_asset(keyframe.asset_id).title if self._video_asset_service and self._video_asset_service.get_asset(keyframe.asset_id) else ""),
        }
        if analysis is not None:
            summary = analysis.visual_summary or analysis.caption
            visual_tags = list(dict.fromkeys((analysis.mood_tags or []) + (analysis.composition_tags or [])))
            emotional_tags = analysis.mood_tags or []
            composition_tags = analysis.composition_tags or []
            lighting_tags = analysis.lighting_tags or []
            metadata["analysis_status"] = analysis.status

        searchable_text = " ".join(
            [summary] + visual_tags + emotional_tags + composition_tags + lighting_tags + [str(metadata.get("asset_title") or "")]
        ).strip()

        record = CinematicMemoryRecord(
            memory_id=self._id(),
            project_id=keyframe.project_id,
            asset_id=keyframe.asset_id,
            keyframe_id=keyframe.keyframe_id,
            analysis_id=analysis.analysis_id if analysis else "",
            embedding_id=embedding.embedding_id if embedding else "",
            memory_type="keyframe_memory",
            summary=summary,
            visual_tags=visual_tags,
            emotional_tags=emotional_tags,
            composition_tags=composition_tags,
            lighting_tags=lighting_tags,
            searchable_text=searchable_text,
            created_at=self._now(),
            metadata=metadata,
        )
        return self.create_memory_record(record)

    def build_memory_for_asset(self, asset_id: str) -> List[CinematicMemoryRecord]:
        if not self._keyframe_service:
            raise ValueError("Keyframe service not configured")
        keyframes = self._keyframe_service.list_keyframes_for_asset(asset_id)
        if not keyframes:
            raise ValueError("No keyframes found for asset")
        return [self.build_memory_for_keyframe(k.keyframe_id) for k in keyframes]

    def list_memory_for_project(self, project_id: str) -> List[CinematicMemoryRecord]:
        if not self._storage:
            return []
        return self._storage.list_cinematic_memory_for_project(project_id)

    def search_memory(self, project_id: str, query: str, limit: int = 20) -> List[CinematicMemoryRecord]:
        q = (query or "").strip().lower()
        rows = self.list_memory_for_project(project_id)
        if not q:
            return rows[: max(1, limit)]
        scored = []
        for row in rows:
            hay = " ".join([
                row.searchable_text,
                row.summary,
                " ".join(row.visual_tags),
                " ".join(row.emotional_tags),
                " ".join(row.composition_tags),
                " ".join(row.lighting_tags),
            ]).lower()
            overlap = sum(1 for token in q.split() if token and token in hay)
            if overlap <= 0:
                continue
            scored.append((overlap, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in scored[: max(1, limit)]]

    def find_related_memories(self, memory_id: str, limit: int = 10) -> List[CinematicMemoryRecord]:
        if not self._storage:
            return []
        all_rows = self._storage.list_cinematic_memory_records(limit=5000)
        anchor = next((r for r in all_rows if r.memory_id == memory_id), None)
        if not anchor:
            return []
        def score(row: CinematicMemoryRecord) -> int:
            if row.memory_id == anchor.memory_id:
                return -1
            s = 0
            if row.project_id == anchor.project_id:
                s += 2
            s += len(set(anchor.visual_tags) & set(row.visual_tags))
            s += len(set(anchor.emotional_tags) & set(row.emotional_tags))
            s += len(set(anchor.composition_tags) & set(row.composition_tags))
            s += len(set(anchor.lighting_tags) & set(row.lighting_tags))
            return s
        ranked = sorted((r for r in all_rows if r.project_id == anchor.project_id), key=score, reverse=True)
        return [r for r in ranked if r.memory_id != anchor.memory_id][: max(1, limit)]


cinematic_memory_service = CinematicMemoryService()
