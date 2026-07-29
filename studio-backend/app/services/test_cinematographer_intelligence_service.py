from __future__ import annotations

from tempfile import TemporaryDirectory

from app.data.storage import DatabaseStorage
from app.models import FrameAnalysisRecord, VideoAsset, VideoKeyframe
from app.models.cinematography import (
    CameraGrammarAssessmentRequest,
    CameraGrammarObservationRequest,
    CameraGrammarPlanRequest,
    CameraGrammarRenderContextRequest,
)
from app.services.cinematographer_intelligence_service import CinematographerIntelligenceService
from app.services.shot_prompt_builder import SLOT_BUDGETS


class _FakeReasoning:
    reasoning_id = "reasoning-cam"


class _FakeCrewIntelligence:
    def __init__(self):
        self.created = []

    def create_reasoning_record(self, **kwargs):
        self.created.append(kwargs)
        return _FakeReasoning()


def _service():
    tmp = TemporaryDirectory()
    storage = DatabaseStorage(tmp.name)
    return tmp, storage, CinematographerIntelligenceService(storage=storage, crew_intelligence_service=None)


def test_create_plan_persists_structured_camera_grammar():
    tmp, storage, service = _service()
    try:
        response = service.create_plan(
            "project-cam",
            CameraGrammarPlanRequest(
                scene_id="scene_001",
                shot_id="shot_001",
                plan_scope="shot",
                scene_context={
                    "visual_description": "Mara stands alone in the corner.",
                    "camera_work": "static close-up",
                    "lighting": "night practical lamp",
                    "emotional_tone": "tense",
                },
            ),
        )

        plan = storage.get_camera_grammar_plan(response.plan.plan_id)
        assert plan is not None
        assert plan.project_id == "project-cam"
        assert plan.framing_intent == "close_up"
        assert plan.advisory_only is True
        assert plan.evidence_refs[0].source_service == "CinematicLanguageAnalyzer"
        assert all(slot.budget_used <= slot.budget_limit for slot in plan.render_slot_suggestions)
    finally:
        tmp.cleanup()


def test_observation_without_frame_analysis_is_low_data():
    tmp, _storage, service = _service()
    try:
        plan = service.create_plan(
            "project-cam",
            CameraGrammarPlanRequest(scene_id="scene_001", scene_context={"description": "A quiet room."}),
        ).plan
        observation = service.create_observation(
            "project-cam",
            CameraGrammarObservationRequest(plan_id=plan.plan_id, asset_id="asset-missing", scene_id="scene_001"),
        )

        assert observation.status == "low_data"
        assert observation.confidence_label == "low_data"
        assert "No keyframes" in observation.limitations[0]
    finally:
        tmp.cleanup()


def test_observation_and_assessment_use_existing_frame_analysis():
    tmp, storage, service = _service()
    try:
        asset = VideoAsset(
            asset_id="asset-1",
            project_id="project-cam",
            source_type="generated_output",
            title="Rendered shot",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        keyframe = VideoKeyframe(
            keyframe_id="key-1",
            asset_id="asset-1",
            project_id="project-cam",
            timestamp_seconds=0,
            frame_index=0,
            image_path="/tmp/key.jpg",
            created_at="2026-01-01T00:00:00Z",
        )
        analysis = FrameAnalysisRecord(
            analysis_id="analysis-1",
            keyframe_id="key-1",
            asset_id="asset-1",
            project_id="project-cam",
            visual_summary="A close-up under practical light.",
            lighting_tags=["practical", "low-key"],
            composition_tags=["close-up", "center-weighted"],
            camera_notes="Still-frame evidence with stable close framing.",
            confidence=0.7,
            provider="mock",
            model="mock",
            status="complete",
            created_at="2026-01-01T00:00:00Z",
        )
        storage.save_video_asset(asset)
        storage.save_video_keyframe(keyframe)
        storage.save_frame_analysis(analysis)

        plan = service.create_plan(
            "project-cam",
            CameraGrammarPlanRequest(
                scene_id="scene_001",
                scene_context={"visual_description": "A close-up by a practical lamp.", "camera_work": "close-up"},
            ),
        ).plan
        observation = service.create_observation(
            "project-cam",
            CameraGrammarObservationRequest(plan_id=plan.plan_id, asset_id="asset-1", scene_id="scene_001"),
        )
        assessment = service.create_assessment(
            "project-cam",
            CameraGrammarAssessmentRequest(
                plan_id=plan.plan_id,
                observation_id=observation.observation_id,
                create_crew_reasoning=False,
            ),
        )

        assert observation.status == "active"
        assert observation.analysis_ids == ["analysis-1"]
        assert "close-up" in observation.observed_framing_tags
        assert "lighting" in assessment.matched_axes
        assert "score" not in assessment.alignment_summary.lower()
    finally:
        tmp.cleanup()


def test_render_context_uses_existing_slot_budgets():
    tmp, _storage, service = _service()
    try:
        plan = service.create_plan(
            "project-cam",
            CameraGrammarPlanRequest(scene_id="scene_001", scene_context={"camera_work": "wide establishing"}),
        ).plan
        context = service.build_render_context(
            "project-cam",
            CameraGrammarRenderContextRequest(plan_id=plan.plan_id, provider="runway"),
        )

        assert len(context.camera_direction) <= SLOT_BUDGETS["camera"]
        assert len(context.lighting_direction) <= SLOT_BUDGETS["lighting"]
        assert context.advisory_only is True
    finally:
        tmp.cleanup()


def test_plan_records_cinematographer_crew_reasoning_when_available():
    tmp = TemporaryDirectory()
    storage = DatabaseStorage(tmp.name)
    crew = _FakeCrewIntelligence()
    service = CinematographerIntelligenceService(storage=storage, crew_intelligence_service=crew)
    try:
        response = service.create_plan(
            "project-cam",
            CameraGrammarPlanRequest(scene_id="scene_001", scene_context={"visual_description": "A held frame."}),
        )

        assert response.reasoning_record_id == "reasoning-cam"
        assert crew.created
        assert crew.created[0]["agent_role"].value == "cinematographer"
        assert crew.created[0]["evidence_refs"]
    finally:
        tmp.cleanup()
