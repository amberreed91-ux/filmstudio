from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.models import CinematicMemoryRecord, VisualEmbedding
from app.services.cinematic_memory_service import CinematicMemoryService
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.visual_embedding_service import VisualEmbeddingService


class SemanticRetrievalService:
    def __init__(
        self,
        storage=None,
        cinematic_memory_service: Optional[CinematicMemoryService] = None,
        visual_embedding_service: Optional[VisualEmbeddingService] = None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
    ):
        self._storage = storage
        self._cinematic_memory_service = cinematic_memory_service
        self._visual_embedding_service = visual_embedding_service
        self._keyframe_service = keyframe_service

    @staticmethod
    def _token_overlap_score(query: str, row: CinematicMemoryRecord) -> float:
        q_tokens = {t for t in query.lower().split() if t}
        if not q_tokens:
            return 0.0
        hay = " ".join([
            row.searchable_text,
            row.summary,
            " ".join(row.visual_tags),
            " ".join(row.emotional_tags),
            " ".join(row.composition_tags),
            " ".join(row.lighting_tags),
        ]).lower()
        hits = sum(1 for t in q_tokens if t in hay)
        return hits / max(1, len(q_tokens))

    @staticmethod
    def _metadata_overlap_score(row: CinematicMemoryRecord, query: str) -> float:
        q = query.lower()
        score = 0.0
        if any(token in q for token in ["emotion", "mood", "isolation", "tense", "calm"]):
            score += 0.2 if row.emotional_tags else 0.0
        if any(token in q for token in ["composition", "framing", "wide", "close"]):
            score += 0.2 if row.composition_tags else 0.0
        if any(token in q for token in ["lighting", "neon", "soft", "natural", "low-key"]):
            score += 0.2 if row.lighting_tags else 0.0
        return min(score, 1.0)

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    def _embedding_by_keyframe(self, keyframe_id: str) -> Optional[VisualEmbedding]:
        if not self._storage:
            return None
        return self._storage.get_visual_embedding_for_keyframe(keyframe_id)

    def search_memory(self, *, project_id: str, query: str, top_k: int = 10) -> List[Dict[str, object]]:
        rows = self._cinematic_memory_service.list_memory_for_project(project_id) if self._cinematic_memory_service else []
        ranked: List[Dict[str, object]] = []
        for row in rows:
            semantic_score = self._token_overlap_score(query, row)
            metadata_score = self._metadata_overlap_score(row, query)
            total = (semantic_score * 0.7) + (metadata_score * 0.3)
            if total <= 0:
                continue
            keyframe = self._keyframe_service.get_keyframe(row.keyframe_id) if self._keyframe_service else None
            ranked.append(
                {
                    "memory": row,
                    "confidence": round(total, 6),
                    "why_match": {
                        "semantic_scoring": round(semantic_score, 6),
                        "metadata_overlap_scoring": round(metadata_score, 6),
                        "matched_tags": {
                            "visual": row.visual_tags,
                            "emotional": row.emotional_tags,
                            "composition": row.composition_tags,
                            "lighting": row.lighting_tags,
                        },
                    },
                    "related_frame_image_url": (keyframe.image_url or keyframe.frame_url or "") if keyframe else "",
                }
            )
        ranked.sort(key=lambda item: float(item["confidence"]), reverse=True)
        return ranked[: max(1, top_k)]

    def visual_to_memory_retrieval(self, *, keyframe_id: str, top_k: int = 8, project_id: Optional[str] = None) -> List[Dict[str, object]]:
        anchor = self._embedding_by_keyframe(keyframe_id)
        if anchor is None or anchor.status != "complete":
            return []
        candidates = self._storage.list_cinematic_memory_records(limit=5000) if self._storage else []
        rows = [r for r in candidates if (not project_id or r.project_id == project_id) and r.keyframe_id != keyframe_id]
        ranked: List[Dict[str, object]] = []
        for row in rows:
            emb = self._embedding_by_keyframe(row.keyframe_id)
            if emb is None or emb.status != "complete":
                continue
            score = self._cosine(anchor.embedding_vector, emb.embedding_vector)
            keyframe = self._keyframe_service.get_keyframe(row.keyframe_id) if self._keyframe_service else None
            ranked.append(
                {
                    "memory": row,
                    "confidence": round(score, 6),
                    "why_match": {
                        "embedding_similarity_scoring": round(score, 6),
                        "source": "visual_embedding",
                    },
                    "related_frame_image_url": (keyframe.image_url or keyframe.frame_url or "") if keyframe else "",
                }
            )
        ranked.sort(key=lambda item: float(item["confidence"]), reverse=True)
        return ranked[: max(1, top_k)]

    def get_related_memory_for_keyframe(self, keyframe_id: str) -> List[Dict[str, object]]:
        kf = self._keyframe_service.get_keyframe(keyframe_id) if self._keyframe_service else None
        if not kf:
            return []
        return self.visual_to_memory_retrieval(keyframe_id=keyframe_id, top_k=6, project_id=kf.project_id)


semantic_retrieval_service = SemanticRetrievalService()
