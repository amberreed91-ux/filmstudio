from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models import FrameAnalysisRecord, SceneMemoryRecord
from app.services.semantic_memory_service import SemanticMemoryService


class VectorIndex:
    """Simple vector-index abstraction for cosine similarity search."""

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        a_norm = math.sqrt(sum(x * x for x in a)) or 1.0
        b_norm = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (a_norm * b_norm)


class SemanticSearchService:
    def __init__(self, storage=None, semantic_memory_service: Optional[SemanticMemoryService] = None):
        self._storage = storage
        self._semantic_memory_service = semantic_memory_service
        self._vector_index = VectorIndex()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _analysis_id(self) -> str:
        return f"analysis-{uuid.uuid4().hex[:12]}"

    def _text_embedding(self, text: str) -> List[float]:
        vec = [0.0] * 8
        for idx, ch in enumerate(text.lower()):
            vec[idx % 8] += (ord(ch) % 97) / 97.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 6) for v in vec]

    def register_frame_analysis(
        self,
        *,
        asset_id: str,
        keyframe_id: Optional[str] = None,
        caption: str = "",
        mood_tags: Optional[List[str]] = None,
        lighting_tags: Optional[List[str]] = None,
        camera_tags: Optional[List[str]] = None,
        embeddings: Optional[List[float]] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> FrameAnalysisRecord:
        if not self._storage:
            raise ValueError("Semantic search storage is not configured")

        content = " | ".join([caption] + (mood_tags or []) + (lighting_tags or []) + (camera_tags or []))
        record = FrameAnalysisRecord(
            analysis_id=self._analysis_id(),
            keyframe_id=keyframe_id or "legacy_keyframe",
            asset_id=asset_id,
            project_id=str((metadata or {}).get("project_id") or "unassigned"),
            caption=caption,
            visual_summary=caption,
            mood_tags=mood_tags or [],
            lighting_tags=lighting_tags or [],
            composition_tags=camera_tags or [],
            color_palette=[],
            detected_subjects=[],
            camera_notes="",
            confidence=0.5,
            provider="semantic_search_legacy",
            model="semantic-search-embedding",
            status="complete",
            camera_tags=camera_tags or [],
            embeddings=embeddings if embeddings is not None else self._text_embedding(content),
            created_at=self._now_iso(),
            metadata=metadata or {},
        )
        return self._storage.save_video_frame_analysis(record)

    def search_similar_scenes(self, *, memory_id: str, limit: int = 10) -> List[Dict[str, object]]:
        if not self._storage:
            return []
        anchor = self._storage.get_video_scene_memory(memory_id)
        if anchor is None:
            raise ValueError("Scene memory not found")

        rows = self._storage.list_video_scene_memories(limit=1000)
        results: List[Dict[str, object]] = []
        for row in rows:
            if row.memory_id == anchor.memory_id:
                continue
            score = self._vector_index.cosine_similarity(anchor.embeddings or [], row.embeddings or [])
            if score <= 0:
                continue
            results.append({"memory": row, "score": round(score, 6), "source": "scene_memory"})

        frame_rows = self._storage.list_video_frame_analyses(limit=1000)
        for row in frame_rows:
            score = self._vector_index.cosine_similarity(anchor.embeddings or [], row.embeddings or [])
            if score <= 0:
                continue
            results.append({"frame_analysis": row, "score": round(score, 6), "source": "frame_analysis"})

        results.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return results[:limit]

    def search_by_mood(self, mood: str, limit: int = 20) -> List[SceneMemoryRecord]:
        if not self._storage:
            return []
        needle = (mood or "").strip().lower()
        rows = self._storage.list_video_scene_memories(limit=1000)
        matches = [row for row in rows if needle and needle in row.dominant_mood.lower()]
        return matches[:limit]

    def search_by_visual_style(self, style: str, limit: int = 20) -> List[SceneMemoryRecord]:
        if not self._storage:
            return []
        needle = (style or "").strip().lower()
        rows = self._storage.list_video_scene_memories(limit=1000)
        matches = [row for row in rows if needle and needle in row.visual_style.lower()]
        return matches[:limit]

    def list_analyses_for_asset(self, asset_id: str) -> List[FrameAnalysisRecord]:
        if not self._storage:
            return []
        return self._storage.list_video_frame_analyses_for_asset(asset_id)


semantic_search_service = SemanticSearchService()
