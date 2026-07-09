from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.models import SceneMemoryRecord
from app.services.shot_detection_service import ShotDetectionService
from app.services.video_asset_service import VideoAssetService


class SemanticMemoryService:
    def __init__(self, storage=None, video_asset_service: Optional[VideoAssetService] = None, shot_detection_service: Optional[ShotDetectionService] = None):
        self._storage = storage
        self._video_asset_service = video_asset_service
        self._shot_detection_service = shot_detection_service

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_memory_id(self) -> str:
        return f"memory-{uuid.uuid4().hex[:12]}"

    def _text_embedding(self, text: str) -> List[float]:
        # Lightweight deterministic embedding placeholder (advisory-only memory index).
        chars = [0.0] * 8
        for idx, ch in enumerate(text.lower()):
            chars[idx % 8] += (ord(ch) % 97) / 97.0
        norm = math.sqrt(sum(v * v for v in chars)) or 1.0
        return [round(v / norm, 6) for v in chars]

    def ingest_asset_analysis(
        self,
        *,
        asset_id: str,
        dominant_mood: str = "neutral",
        visual_style: str = "observational",
        lighting_style: str = "naturalistic",
        pacing_profile: str = "moderate",
        character_presence: Optional[List[str]] = None,
        composition_patterns: Optional[List[str]] = None,
        cinematic_notes: str = "",
        embeddings: Optional[List[float]] = None,
    ) -> SceneMemoryRecord:
        if not self._storage:
            raise ValueError("Scene memory storage is not configured")
        if not self._video_asset_service:
            raise ValueError("Video asset service is not configured")

        asset = self._video_asset_service.get_asset(asset_id)
        if asset is None:
            raise ValueError("Video asset not found")

        shots = self._shot_detection_service.list_shots(asset_id) if self._shot_detection_service else []
        shot_count = len(shots)

        notes = cinematic_notes.strip() or f"Advisory memory generated from asset {asset_id}."
        if shot_count > 0 and "shot" not in notes.lower():
            notes = f"{notes} Detected shot count: {shot_count}."

        joined_for_embedding = " | ".join(
            [dominant_mood, visual_style, lighting_style, pacing_profile, notes] + (character_presence or []) + (composition_patterns or [])
        )

        memory = SceneMemoryRecord(
            memory_id=self._generate_memory_id(),
            asset_id=asset_id,
            dominant_mood=dominant_mood,
            visual_style=visual_style,
            lighting_style=lighting_style,
            pacing_profile=pacing_profile,
            character_presence=character_presence or [],
            composition_patterns=composition_patterns or [],
            cinematic_notes=notes,
            embeddings=embeddings if embeddings is not None else self._text_embedding(joined_for_embedding),
            created_at=self._now_iso(),
        )
        return self._storage.save_video_scene_memory(memory)

    def search_memories(self, query: str, limit: int = 20) -> List[SceneMemoryRecord]:
        if not self._storage:
            return []
        normalized_query = (query or "").strip().lower()
        if not normalized_query:
            return self._storage.list_video_scene_memories(limit=limit)

        tokens = [token for token in normalized_query.split() if token]
        rows = self._storage.list_video_scene_memories(limit=500)

        def score(memory: SceneMemoryRecord) -> int:
            haystack = " ".join([
                memory.dominant_mood,
                memory.visual_style,
                memory.lighting_style,
                memory.pacing_profile,
                memory.cinematic_notes,
                " ".join(memory.character_presence),
                " ".join(memory.composition_patterns),
            ]).lower()
            return sum(1 for token in tokens if token in haystack)

        ranked = sorted(rows, key=score, reverse=True)
        return [row for row in ranked if score(row) > 0][:limit]

    def list_memories_for_asset(self, asset_id: str) -> List[SceneMemoryRecord]:
        if not self._storage:
            return []
        return self._storage.list_video_scene_memories_for_asset(asset_id)

    def retrieve_related_memories(self, memory_id: str, limit: int = 5) -> List[SceneMemoryRecord]:
        if not self._storage:
            return []
        anchor = self._storage.get_video_scene_memory(memory_id)
        if anchor is None:
            raise ValueError("Scene memory not found")

        rows = self._storage.list_video_scene_memories(limit=500)
        candidates = [row for row in rows if row.memory_id != memory_id]

        def similarity(a: SceneMemoryRecord, b: SceneMemoryRecord) -> float:
            a_emb = a.embeddings or []
            b_emb = b.embeddings or []
            if not a_emb or not b_emb or len(a_emb) != len(b_emb):
                score = 0.0
                if a.dominant_mood == b.dominant_mood:
                    score += 0.35
                if a.visual_style == b.visual_style:
                    score += 0.25
                if a.lighting_style == b.lighting_style:
                    score += 0.2
                if a.pacing_profile == b.pacing_profile:
                    score += 0.2
                return score
            dot = sum(x * y for x, y in zip(a_emb, b_emb))
            a_norm = math.sqrt(sum(x * x for x in a_emb)) or 1.0
            b_norm = math.sqrt(sum(y * y for y in b_emb)) or 1.0
            return dot / (a_norm * b_norm)

        ranked = sorted(candidates, key=lambda row: similarity(anchor, row), reverse=True)
        return ranked[:limit]


semantic_memory_service = SemanticMemoryService()
