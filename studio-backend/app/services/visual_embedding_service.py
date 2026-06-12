from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models import VisualEmbedding
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.video_asset_service import VideoAssetService
from app.services.visual_embedding_adapter import VisualEmbeddingAdapter, build_visual_embedding_adapter

logger = logging.getLogger(__name__)


class VisualEmbeddingService:
    def __init__(
        self,
        storage=None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
        video_asset_service: Optional[VideoAssetService] = None,
        embedding_adapter: Optional[VisualEmbeddingAdapter] = None,
    ):
        self._storage = storage
        self._keyframe_service = keyframe_service
        self._video_asset_service = video_asset_service
        self._embedding_adapter = embedding_adapter

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _id(self) -> str:
        return f"embed-{uuid.uuid4().hex[:12]}"

    def _adapter(self) -> VisualEmbeddingAdapter:
        if self._embedding_adapter is None:
            self._embedding_adapter = build_visual_embedding_adapter()
        return self._embedding_adapter

    def get_embedding(self, embedding_id: str) -> Optional[VisualEmbedding]:
        if not self._storage:
            return None
        return self._storage.get_visual_embedding(embedding_id)

    def create_embedding_for_keyframe(self, keyframe_id: str) -> VisualEmbedding:
        if not self._keyframe_service:
            raise ValueError("Keyframe service is not configured")
        keyframe = self._keyframe_service.get_keyframe(keyframe_id)
        if keyframe is None:
            raise ValueError("Video keyframe not found")

        image_path = (keyframe.image_path or keyframe.frame_path or "").strip()
        result = self._adapter().embed_image(
            image_path,
            {
                "keyframe_id": keyframe.keyframe_id,
                "asset_id": keyframe.asset_id,
                "project_id": keyframe.project_id,
                "source_type": keyframe.source_type,
            },
        )
        row = VisualEmbedding(
            embedding_id=self._id(),
            keyframe_id=keyframe.keyframe_id,
            asset_id=keyframe.asset_id,
            project_id=keyframe.project_id,
            provider=result.provider,
            model=result.model,
            vector_dimension=result.dimension,
            embedding_vector=result.vector,
            status=result.status,
            created_at=self._now_iso(),
            metadata=result.metadata,
        )
        if self._storage:
            self._storage.save_visual_embedding(row)
        return row

    def create_embeddings_for_asset(self, asset_id: str) -> List[VisualEmbedding]:
        if not self._keyframe_service:
            raise ValueError("Keyframe service is not configured")
        keyframes = self._keyframe_service.list_keyframes_for_asset(asset_id)
        if not keyframes:
            raise ValueError("No keyframes found for asset")
        rows: List[VisualEmbedding] = []
        for keyframe in keyframes:
            rows.append(self.create_embedding_for_keyframe(keyframe.keyframe_id))
        return rows

    def list_embeddings_for_asset(self, asset_id: str) -> List[VisualEmbedding]:
        if not self._storage:
            return []
        return self._storage.list_visual_embeddings_for_asset(asset_id)

    def list_embeddings_for_project(self, project_id: str) -> List[VisualEmbedding]:
        if not self._storage:
            return []
        return self._storage.list_visual_embeddings_for_project(project_id)

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        a_norm = math.sqrt(sum(x * x for x in a)) or 1.0
        b_norm = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (a_norm * b_norm)

    def find_similar_keyframes(
        self,
        *,
        keyframe_id: str,
        top_k: int = 5,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        if not self._storage:
            return []
        anchor = self._storage.get_visual_embedding_for_keyframe(keyframe_id)
        if anchor is None or anchor.status != "complete":
            return []

        candidates = (
            self._storage.list_visual_embeddings_for_project(project_id)
            if project_id
            else self._storage.list_visual_embeddings(limit=5000)
        )

        results: List[Dict[str, object]] = []
        for candidate in candidates:
            if candidate.keyframe_id == keyframe_id:
                continue
            if candidate.status != "complete":
                continue
            score = self.cosine_similarity(anchor.embedding_vector, candidate.embedding_vector)
            kf = self._keyframe_service.get_keyframe(candidate.keyframe_id) if self._keyframe_service else None
            image_url = ""
            if kf:
                image_url = (kf.image_url or kf.frame_url or "").strip()
            results.append(
                {
                    "keyframe_id": candidate.keyframe_id,
                    "similarity_score": round(score, 6),
                    "image_url": image_url,
                    "asset_id": candidate.asset_id,
                    "project_id": candidate.project_id,
                }
            )

        results.sort(key=lambda r: float(r.get("similarity_score", 0.0)), reverse=True)
        return results[: max(1, top_k)]

    def try_auto_embed_keyframes(self, keyframe_ids: List[str], reason: str) -> None:
        for keyframe_id in keyframe_ids:
            try:
                row = self.create_embedding_for_keyframe(keyframe_id)
                logger.info("Auto-embedded keyframe=%s status=%s reason=%s", keyframe_id, row.status, reason)
            except Exception as exc:
                logger.warning("Auto-embedding failed keyframe=%s reason=%s error=%s", keyframe_id, reason, exc)


visual_embedding_service = VisualEmbeddingService()
