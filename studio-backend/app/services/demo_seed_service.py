from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.data import get_storage
from app.models import (
    CinematicMemoryRecord,
    DirectorSignature,
    FinalShortFilmPackage,
    FrameAnalysisRecord,
    RenderJobInput,
    RenderJobModel,
    RenderJobOutput,
    ShortFilmReview,
    StudioProject,
    VideoKeyframe,
    VisualEmbedding,
)
from app.models.video_assets import VideoAsset
from app.services.project_store import project_store
from app.services.stability import ValidationError, elapsed_ms, log_stage_event, start_timer
from app.services.studio_decision_gate_service import studio_decision_gate_service
from app.services.video_asset_service import VideoAssetService


DEMO_PROJECT_ID = "demo_studio_cinematic_001"


class DemoSeedService:
    def __init__(self, storage=None, store=project_store, video_assets: VideoAssetService | None = None):
        self._storage = storage or get_storage("sqlite")
        self._store = store
        self._video_assets = video_assets or VideoAssetService(self._storage)
        if self._video_assets._storage is None:
            self._video_assets._storage = self._storage

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _demo_output_url() -> str:
        return "/outputs/final_films/route_keyframe_demo.mp4"

    def seed_demo_project(self, project_id: str = DEMO_PROJECT_ID) -> Dict[str, Any]:
        timer = start_timer()
        candidate = (project_id or "").strip()
        if candidate != DEMO_PROJECT_ID:
            log_stage_event(
                project_id=candidate or "",
                job_id=None,
                provider="demo_seed",
                stage="demo_seed_rejected",
                duration_ms=elapsed_ms(timer),
                extra={"code": "demo_seed_non_demo_project_rejected"},
            )
            raise ValidationError(
                f"Demo seeding is limited to the dedicated demo project '{DEMO_PROJECT_ID}'. "
                f"Your project '{candidate}' was left unchanged — open the demo project to run the demo seed.",
                stage="demo_seed",
                metadata={"code": "demo_seed_non_demo_project_rejected", "project_id": candidate},
            )
        now = self._now()
        output_url = self._demo_output_url()
        output_path = str((Path(__file__).resolve().parents[2] / output_url.removeprefix("/")).resolve())

        project = {
            "project_id": project_id,
            "title": "Demo Studio Cinematic 001",
            "created_at": now,
            "updated_at": now,
            "script_text": "Scene 1: Rainy alley confrontation\n\nScene 2: Quiet hallway reveal",
            "execution_summary": {
                "one_button_render_jobs": [
                    {
                        "scene_id": "scene_001",
                        "shot_id": "scene_001_shot_001",
                        "job_id": "demo-job-001",
                        "provider": "runway",
                        "status": "complete",
                        "task_id": "demo-task-001",
                        "output_url": output_url,
                        "preview_url": output_url,
                    },
                    {
                        "scene_id": "scene_002",
                        "shot_id": "scene_002_shot_001",
                        "job_id": "demo-job-002",
                        "provider": "runway",
                        "status": "complete",
                        "task_id": "demo-task-002",
                        "output_url": output_url,
                        "preview_url": output_url,
                    },
                ]
            },
        }
        self._store.save_project(project)
        self._storage.save_project(StudioProject(project_id=project_id, title=project["title"], updated_at=now))

        asset = VideoAsset(
            asset_id=f"{project_id}_asset_001",
            project_id=project_id,
            source_type="generated_output",
            source_url=output_url,
            title="Demo Reference Footage",
            description="Deterministic demo seed footage",
            status="available",
            created_at=now,
            updated_at=now,
            metadata={"seeded": True, "demo_project": project_id},
        )
        self._storage.save_video_asset(asset)

        keyframes = [
            VideoKeyframe(
                keyframe_id=f"{project_id}_kf_001",
                asset_id=asset.asset_id,
                project_id=project_id,
                source_type="generated_output",
                timestamp_seconds=0.5,
                image_path=output_path,
                image_url="https://picsum.photos/seed/demo_kf_001/800/450",
                frame_index=1,
                extraction_method="manual_seed",
                frame_path=output_path,
                frame_url="https://picsum.photos/seed/demo_kf_001/800/450",
                extraction_reason="demo_seed",
                created_at=now,
                metadata={"seeded": True},
            ),
            VideoKeyframe(
                keyframe_id=f"{project_id}_kf_002",
                asset_id=asset.asset_id,
                project_id=project_id,
                source_type="generated_output",
                timestamp_seconds=2.0,
                image_path=output_path,
                image_url="https://picsum.photos/seed/demo_kf_002/800/450",
                frame_index=2,
                extraction_method="manual_seed",
                frame_path=output_path,
                frame_url="https://picsum.photos/seed/demo_kf_002/800/450",
                extraction_reason="demo_seed",
                created_at=now,
                metadata={"seeded": True},
            ),
            VideoKeyframe(
                keyframe_id=f"{project_id}_kf_003",
                asset_id=asset.asset_id,
                project_id=project_id,
                source_type="generated_output",
                timestamp_seconds=3.8,
                image_path=output_path,
                image_url="https://picsum.photos/seed/demo_kf_003/800/450",
                frame_index=3,
                extraction_method="manual_seed",
                frame_path=output_path,
                frame_url="https://picsum.photos/seed/demo_kf_003/800/450",
                extraction_reason="demo_seed",
                created_at=now,
                metadata={"seeded": True},
            ),
        ]
        for kf in keyframes:
            self._storage.save_video_keyframe(kf)

        analyses = [
            FrameAnalysisRecord(
                analysis_id=f"{project_id}_analysis_001",
                keyframe_id=keyframes[0].keyframe_id,
                asset_id=asset.asset_id,
                project_id=project_id,
                caption="Rainy alley closeup",
                visual_summary="High-contrast rainy alley with neon reflections",
                mood_tags=["tense", "moody"],
                lighting_tags=["low-key", "neon"],
                composition_tags=["closeup", "centered subject"],
                color_palette=["teal", "amber", "charcoal"],
                detected_subjects=["lead actor", "alleyway"],
                camera_notes="Handheld drift",
                camera_tags=["handheld", "tight framing"],
                confidence=0.92,
                provider="demo_seed",
                model="seed-v1",
                status="available",
                created_at=now,
                metadata={"seeded": True},
            ),
            FrameAnalysisRecord(
                analysis_id=f"{project_id}_analysis_002",
                keyframe_id=keyframes[1].keyframe_id,
                asset_id=asset.asset_id,
                project_id=project_id,
                caption="Hallway reveal medium shot",
                visual_summary="Quiet corridor with motivated practicals",
                mood_tags=["suspenseful"],
                lighting_tags=["practical", "soft contrast"],
                composition_tags=["medium shot", "leading lines"],
                color_palette=["steel blue", "warm white"],
                detected_subjects=["lead actor", "hallway"],
                camera_notes="Locked shot",
                camera_tags=["locked", "stable"],
                confidence=0.89,
                provider="demo_seed",
                model="seed-v1",
                status="available",
                created_at=now,
                metadata={"seeded": True},
            ),
            FrameAnalysisRecord(
                analysis_id=f"{project_id}_analysis_003",
                keyframe_id=keyframes[2].keyframe_id,
                asset_id=asset.asset_id,
                project_id=project_id,
                caption="Final reaction beat",
                visual_summary="Intimate reaction framing with restrained movement",
                mood_tags=["emotional", "quiet"],
                lighting_tags=["soft key", "motivated"],
                composition_tags=["closeup", "rule of thirds"],
                color_palette=["warm gray", "soft cyan"],
                detected_subjects=["lead actor"],
                camera_notes="Minimal movement",
                camera_tags=["closeup", "subtle push"],
                confidence=0.9,
                provider="demo_seed",
                model="seed-v1",
                status="available",
                created_at=now,
                metadata={"seeded": True},
            ),
        ]
        for analysis in analyses:
            self._storage.save_video_frame_analysis(analysis)

        embeddings = [
            VisualEmbedding(
                embedding_id=f"{project_id}_embed_001",
                keyframe_id=keyframes[0].keyframe_id,
                asset_id=asset.asset_id,
                project_id=project_id,
                provider="demo_seed",
                model="embed-v1",
                vector_dimension=4,
                embedding_vector=[0.11, 0.22, 0.33, 0.44],
                status="available",
                created_at=now,
                metadata={"seeded": True},
            ),
            VisualEmbedding(
                embedding_id=f"{project_id}_embed_002",
                keyframe_id=keyframes[1].keyframe_id,
                asset_id=asset.asset_id,
                project_id=project_id,
                provider="demo_seed",
                model="embed-v1",
                vector_dimension=4,
                embedding_vector=[0.21, 0.31, 0.41, 0.51],
                status="available",
                created_at=now,
                metadata={"seeded": True},
            ),
            VisualEmbedding(
                embedding_id=f"{project_id}_embed_003",
                keyframe_id=keyframes[2].keyframe_id,
                asset_id=asset.asset_id,
                project_id=project_id,
                provider="demo_seed",
                model="embed-v1",
                vector_dimension=4,
                embedding_vector=[0.15, 0.25, 0.35, 0.45],
                status="available",
                created_at=now,
                metadata={"seeded": True},
            ),
        ]
        for embedding in embeddings:
            self._storage.save_visual_embedding(embedding)

        for idx in range(3):
            self._storage.save_cinematic_memory_record(
                CinematicMemoryRecord(
                    memory_id=f"{project_id}_memory_00{idx+1}",
                    project_id=project_id,
                    asset_id=asset.asset_id,
                    keyframe_id=keyframes[idx].keyframe_id,
                    analysis_id=analyses[idx].analysis_id,
                    embedding_id=embeddings[idx].embedding_id,
                    memory_type="keyframe_memory",
                    summary=analyses[idx].visual_summary,
                    visual_tags=analyses[idx].composition_tags,
                    emotional_tags=analyses[idx].mood_tags,
                    composition_tags=analyses[idx].composition_tags,
                    lighting_tags=analyses[idx].lighting_tags,
                    searchable_text=f"{analyses[idx].caption} {analyses[idx].visual_summary}",
                    created_at=now,
                    metadata={"seeded": True},
                )
            )

        self._storage.save_director_signature(
            DirectorSignature(
                signature_id=f"{project_id}_director_sig_001",
                project_id=project_id,
                dominant_mood_tags=["tense", "quiet"],
                dominant_lighting_tags=["low-key", "motivated"],
                dominant_composition_tags=["closeup", "leading lines"],
                dominant_palette=["teal", "amber", "steel blue"],
                pacing_notes="Restrained escalation with quiet emotional release",
                visual_language_summary="Naturalistic noir with restrained camera energy",
                confidence=0.86,
                evidence_keyframe_ids=[kf.keyframe_id for kf in keyframes],
                evidence_memory_ids=[f"{project_id}_memory_001", f"{project_id}_memory_002", f"{project_id}_memory_003"],
                created_at=now,
                metadata={"seeded": True},
            )
        )

        render_jobs = [
            RenderJobModel(
                id="demo-job-001",
                project_id=project_id,
                shot_id="scene_001_shot_001",
                provider="runway",
                provider_job_id="demo-task-001",
                status="complete",
                progress=100,
                input_payload=RenderJobInput(
                    shot_id="scene_001_shot_001",
                    prompt="Rainy alley confrontation cinematic pass",
                    referenceAssets=[],
                    parameters={"duration": 5, "ratio": "1280:720", "use_mock_success": True},
                ),
                output_payload=RenderJobOutput(
                    asset_url=output_url,
                    thumbnail_url=output_url,
                    metadata={"provider_response_normalized": {"provider": "runway", "status": "completed"}},
                ),
                created_at=now,
                updated_at=now,
                completed_at=now,
            ),
            RenderJobModel(
                id="demo-job-002",
                project_id=project_id,
                shot_id="scene_002_shot_001",
                provider="runway",
                provider_job_id="demo-task-002",
                status="complete",
                progress=100,
                input_payload=RenderJobInput(
                    shot_id="scene_002_shot_001",
                    prompt="Quiet hallway reveal cinematic pass",
                    referenceAssets=[],
                    parameters={"duration": 5, "ratio": "1280:720", "use_mock_success": True},
                ),
                output_payload=RenderJobOutput(
                    asset_url=output_url,
                    thumbnail_url=output_url,
                    metadata={"provider_response_normalized": {"provider": "runway", "status": "completed"}},
                ),
                created_at=now,
                updated_at=now,
                completed_at=now,
            ),
        ]
        for job in render_jobs:
            self._storage.save_job(job)

        review = ShortFilmReview(
            review_id=f"{project_id}_review_001",
            project_id=project_id,
            output_url=output_url,
            decision="approved",
            reviewer="demo_seed",
            notes="Seeded approved review for deterministic demo flow",
            created_at=now,
            updated_at=now,
            metadata={"seeded": True},
        )
        self._storage.save_review(review)

        package = FinalShortFilmPackage(
            package_id=f"{project_id}_package_001",
            project_id=project_id,
            film_title="Demo Studio Cinematic 001",
            final_output_url=output_url,
            final_output_path=output_path,
            review_id=review.review_id,
            review_decision=review.decision,
            runtime_seconds=10.0,
            scene_count=2,
            shot_count=2,
            render_job_ids=[job.id for job in render_jobs],
            revision_ids=[],
            has_title_card=True,
            has_end_card=True,
            has_soundtrack=False,
            package_status="approved",
            created_at=now,
            updated_at=now,
            metadata={"seeded": True},
        )
        self._storage.save_final_short_film_package(package)

        gate = studio_decision_gate_service.evaluate_project_gate(project_id)
        base = f"/studio"
        return {
            "project_id": project_id,
            "study_room_url": f"{base}/study-room?project_id={project_id}",
            "previs_url": f"{base}/previs?project_id={project_id}",
            "production_url": f"{base}/production-board?project_id={project_id}",
            "screening_url": f"{base}/screening-room?project_id={project_id}",
            "crew_ops_url": f"{base}/scheduler?project_id={project_id}",
            "gate_status": gate.gate_status,
            "recommended_next_action": gate.recommended_next_action,
            "seeded": {
                "asset_id": asset.asset_id,
                "keyframes": 3,
                "frame_analyses": 3,
                "embeddings": 3,
                "cinematic_memory_records": 3,
                "render_jobs": len(render_jobs),
                "review_id": review.review_id,
                "package_id": package.package_id,
            },
        }


demo_seed_service = DemoSeedService()
