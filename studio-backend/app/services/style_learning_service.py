from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models import SceneMemoryRecord, StyleSignature
from app.services.semantic_memory_service import semantic_memory_service
from app.services.video_asset_service import video_asset_service


class StyleLearningService:
    """
    Advisory-only style learning based on analyzed scene memory artifacts.
    """

    def __init__(self, storage=None, semantic_memory=None, video_assets=None):
        self._storage = storage
        self._semantic_memory = semantic_memory or semantic_memory_service
        self._video_assets = video_assets or video_asset_service

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _signature_id(self) -> str:
        return f"style-{uuid.uuid4().hex[:12]}"

    def _extract_camera_movement_patterns(self, memories: List[SceneMemoryRecord]) -> List[str]:
        movement_tokens = (
            "static", "handheld", "dolly", "pan", "tilt", "tracking", "push-in", "pull-back", "crane", "gimbal"
        )
        counter: Counter[str] = Counter()
        for memory in memories:
            haystack = " ".join(
                (memory.composition_patterns or [])
                + [memory.cinematic_notes or "", memory.visual_style or ""]
            ).lower()
            for token in movement_tokens:
                if token in haystack:
                    counter[token] += 1
        return [token for token, _ in counter.most_common(6)]

    def _extract_color_motifs(self, memories: List[SceneMemoryRecord]) -> List[str]:
        color_tokens = (
            "warm", "cool", "neon", "saturated", "desaturated", "monochrome", "amber", "cyan", "teal", "magenta"
        )
        counter: Counter[str] = Counter()
        for memory in memories:
            haystack = f"{memory.visual_style} {memory.cinematic_notes}".lower()
            for token in color_tokens:
                if token in haystack:
                    counter[token] += 1
        return [token for token, _ in counter.most_common(6)]

    def _extract_framing_tendencies(self, memories: List[SceneMemoryRecord]) -> List[str]:
        counter: Counter[str] = Counter()
        for memory in memories:
            for pattern in memory.composition_patterns or []:
                token = str(pattern).strip().lower()
                if token:
                    counter[token] += 1
        return [token for token, _ in counter.most_common(8)]

    def _extract_pacing_patterns(self, memories: List[SceneMemoryRecord]) -> List[str]:
        counter: Counter[str] = Counter()
        for memory in memories:
            token = str(memory.pacing_profile or "").strip().lower()
            if token:
                counter[token] += 1
        return [token for token, _ in counter.most_common(6)]

    def build_project_signature(self, project_id: str) -> StyleSignature:
        if not self._storage:
            raise ValueError("Style signature storage is not configured")
        if not self._video_assets:
            raise ValueError("Video asset service is not configured")
        if not project_id:
            raise ValueError("project_id is required")

        assets = self._video_assets.list_assets_for_project(project_id)
        memories: List[SceneMemoryRecord] = []
        for asset in assets:
            memories.extend(self._semantic_memory.list_memories_for_asset(asset.asset_id))

        framing = self._extract_framing_tendencies(memories)
        pacing = self._extract_pacing_patterns(memories)
        colors = self._extract_color_motifs(memories)
        camera = self._extract_camera_movement_patterns(memories)
        signal_count = len(framing) + len(pacing) + len(colors) + len(camera)
        confidence = min(1.0, round((signal_count / 20.0), 4))

        signature = StyleSignature(
            signature_id=self._signature_id(),
            project_id=project_id,
            framing_tendencies=framing,
            pacing_patterns=pacing,
            color_motifs=colors,
            camera_movement_patterns=camera,
            confidence=confidence,
            advisory_only=True,
            metadata={"memory_count": len(memories), "asset_count": len(assets)},
            created_at=self._now_iso(),
        )
        return self._storage.save_style_signature(signature)

    def list_signatures_for_project(self, project_id: str) -> List[StyleSignature]:
        if not self._storage:
            return []
        return self._storage.list_style_signatures_for_project(project_id)

    def get_signature(self, signature_id: str) -> Optional[StyleSignature]:
        if not self._storage:
            return None
        return self._storage.get_style_signature(signature_id)

    def compare_signatures(self, left: StyleSignature, right: StyleSignature) -> Dict[str, object]:
        def overlap(a: List[str], b: List[str]) -> float:
            a_set = set(a or [])
            b_set = set(b or [])
            if not a_set and not b_set:
                return 1.0
            denom = max(1, len(a_set.union(b_set)))
            return round(len(a_set.intersection(b_set)) / denom, 4)

        breakdown = {
            "framing": overlap(left.framing_tendencies, right.framing_tendencies),
            "pacing": overlap(left.pacing_patterns, right.pacing_patterns),
            "color": overlap(left.color_motifs, right.color_motifs),
            "camera_movement": overlap(left.camera_movement_patterns, right.camera_movement_patterns),
        }
        overall = round(sum(breakdown.values()) / 4.0, 4)
        return {
            "overall_similarity": overall,
            "breakdown": breakdown,
            "advisory_only": True,
            "auto_regeneration_triggered": False,
        }

    def retrieve_style_patterns(self, project_id: str) -> Dict[str, object]:
        signatures = self.list_signatures_for_project(project_id)
        latest = signatures[0] if signatures else None
        return {
            "project_id": project_id,
            "signature_count": len(signatures),
            "latest_signature": latest.model_dump() if latest else None,
            "advisory_only": True,
            "auto_regeneration_triggered": False,
        }


style_learning_service = StyleLearningService()
