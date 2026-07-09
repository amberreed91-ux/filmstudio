from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.models import DirectorCommentary
from app.services.keyframe_extraction_service import KeyframeExtractionService
from app.services.semantic_memory_service import SemanticMemoryService
from app.services.shot_detection_service import ShotDetectionService
from app.services.video_asset_service import VideoAssetService


class DirectorCommentaryService:
    def __init__(
        self,
        storage=None,
        video_asset_service: Optional[VideoAssetService] = None,
        keyframe_service: Optional[KeyframeExtractionService] = None,
        shot_detection_service: Optional[ShotDetectionService] = None,
        semantic_memory_service: Optional[SemanticMemoryService] = None,
    ):
        self._storage = storage
        self._video_asset_service = video_asset_service
        self._keyframe_service = keyframe_service
        self._shot_detection_service = shot_detection_service
        self._semantic_memory_service = semantic_memory_service

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _id(self) -> str:
        return f"commentary-{uuid.uuid4().hex[:12]}"

    def list_for_asset(self, asset_id: str) -> List[DirectorCommentary]:
        if not self._storage:
            return []
        return self._storage.list_director_commentary_for_asset(asset_id)

    def generate_commentary(self, *, asset_id: str, overwrite: bool = True) -> List[DirectorCommentary]:
        if not self._storage:
            raise ValueError("Director commentary storage is not configured")
        if not self._video_asset_service:
            raise ValueError("Video asset service is not configured")

        asset = self._video_asset_service.get_asset(asset_id)
        if asset is None:
            raise ValueError("Video asset not found")

        shots = self._shot_detection_service.list_shots(asset_id) if self._shot_detection_service else []
        keyframes = self._keyframe_service.list_keyframes_for_asset(asset_id) if self._keyframe_service else []
        memories = self._semantic_memory_service.list_memories_for_asset(asset_id) if self._semantic_memory_service else []

        if overwrite:
            self._storage.delete_director_commentary_for_asset(asset_id)

        if not shots:
            shots = []
        if not keyframes:
            keyframes = []

        commentary_rows: List[DirectorCommentary] = []

        # Generate one commentary record per detected shot where possible.
        for idx, shot in enumerate(shots):
            shot_memory = memories[min(idx, len(memories) - 1)] if memories else None
            beat = f"Scene beat {idx + 1} ({shot.start_time:.2f}s-{shot.end_time:.2f}s)"
            interpretation = (
                f"{beat} frames a controlled transition through {shot.transition_type.replace('_', ' ')} editing, "
                f"inviting the audience to register visual intent before narrative acceleration."
            )
            emotional_read = (
                shot_memory.dominant_mood if shot_memory else (
                    "heightened tension" if shot.transition_type in {"hard_cut", "dissolve"} else "reflective suspension"
                )
            )
            visual_language_notes = (
                f"Coverage cadence is grounded in {len(keyframes)} extracted keyframes and {len(shots)} shot boundaries; "
                f"composition signal leans toward {', '.join(shot_memory.composition_patterns[:2]) if shot_memory else 'transition-led framing'}."
            )
            pacing_notes = (
                shot_memory.pacing_profile if shot_memory else (
                    "Measured hold preceding transition." if (shot.end_time - shot.start_time) > 2 else "Compressed beat with brisk editorial handoff."
                )
            )
            commentary = DirectorCommentary(
                commentary_id=self._id(),
                asset_id=asset_id,
                scene_reference=beat,
                interpretation=interpretation,
                emotional_read=emotional_read,
                visual_language_notes=visual_language_notes,
                pacing_notes=pacing_notes,
                created_at=self._now_iso(),
                metadata={
                    "grounding": {
                        "shot_boundary_id": shot.boundary_id,
                        "keyframe_count": len(keyframes),
                        "memory_id": shot_memory.memory_id if shot_memory else None,
                    }
                },
            )
            self._storage.save_director_commentary(commentary)
            commentary_rows.append(commentary)

        # Fallback commentary when there are no detected shots yet.
        if not commentary_rows:
            memory = memories[0] if memories else None
            commentary = DirectorCommentary(
                commentary_id=self._id(),
                asset_id=asset_id,
                scene_reference="Scene-wide overview",
                interpretation="The scene currently reads as a study in tonal setup, with image rhythm still consolidating around emergent shot logic.",
                emotional_read=memory.dominant_mood if memory else "undetermined mood",
                visual_language_notes=(
                    f"Grounded in {len(keyframes)} extracted keyframes"
                    + (f" and memory signature {memory.memory_id}." if memory else ".")
                ),
                pacing_notes=memory.pacing_profile if memory else "Pacing profile pending shot-level segmentation.",
                created_at=self._now_iso(),
                metadata={
                    "grounding": {
                        "shot_boundary_id": None,
                        "keyframe_count": len(keyframes),
                        "memory_id": memory.memory_id if memory else None,
                    }
                },
            )
            self._storage.save_director_commentary(commentary)
            commentary_rows.append(commentary)

        return commentary_rows


director_commentary_service = DirectorCommentaryService()
