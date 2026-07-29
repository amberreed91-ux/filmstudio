from __future__ import annotations

from types import SimpleNamespace
from tempfile import TemporaryDirectory

from app.data.storage import DatabaseStorage
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewReasoningType
from app.models.colorist import (
    ColorGradeObservationRequest,
    ColorLookBibleRequest,
    ColorMatchAssessmentRequest,
    ColoristDecisionSaveRequest,
    ColoristLookPlanRequest,
)
from app.services.colorist_intelligence_service import ColoristIntelligenceService


class _FakeCrewIntelligenceService:
    def __init__(self):
        self.reasoning_calls = []

    def build_role_context(self, *args, **kwargs):
        return SimpleNamespace(memory_refs=[], spine_refs=[], context_notes=[])

    def create_reasoning_record(self, **kwargs):
        self.reasoning_calls.append(kwargs)
        return SimpleNamespace(reasoning_id="crew-reason-colorist-001")


def test_colorist_plan_creates_palette_record_without_memory_write():
    with TemporaryDirectory() as tmp:
        storage = DatabaseStorage(tmp)
        service = ColoristIntelligenceService(storage=storage, crew_intelligence_service=None)

        look_bible = service.create_or_update_look_bible(
            "project-color",
            ColorLookBibleRequest(project_context={"color_palette": ["teal", "amber"]}),
        ).look_bible
        plan = service.create_look_plan(
            "project-color",
            ColoristLookPlanRequest(
                look_bible_id=look_bible.look_bible_id,
                scene_id="scene_001",
                scene_context={"description": "A cold room with amber practicals.", "color_palette": ["teal", "amber"]},
            ),
        ).plan

        palette_records = storage.list_color_palette_continuity_records("project-color", scene_id="scene_001")
        decisions = storage.list_colorist_decision_projections("project-color")

        assert plan.advisory_only is True
        assert palette_records
        assert palette_records[0].source_id == plan.plan_id
        assert decisions == []


def test_colorist_assessment_low_data_and_explicit_decision_projection():
    with TemporaryDirectory() as tmp:
        storage = DatabaseStorage(tmp)
        service = ColoristIntelligenceService(storage=storage, crew_intelligence_service=None)

        plan = service.create_look_plan(
            "project-color",
            ColoristLookPlanRequest(
                scene_id="scene_001",
                scene_context={"description": "A cold room with amber practicals.", "color_palette": ["teal", "amber"]},
            ),
        ).plan
        observation = service.create_observation(
            "project-color",
            ColorGradeObservationRequest(plan_id=plan.plan_id, asset_id="asset-color"),
        ).observation
        assessment = service.create_assessment(
            "project-color",
            ColorMatchAssessmentRequest(plan_id=plan.plan_id, observation_id=observation.observation_id),
        ).assessment
        decision = service.save_explicit_color_decision(
            "project-color",
            ColoristDecisionSaveRequest(
                decision_text="Keep amber practicals as the memory color.",
                plan_id=plan.plan_id,
                assessment_id=assessment.assessment_id,
            ),
        )

        assert observation.status == "low_data"
        assert assessment.status == "low_data"
        assert decision.metadata["explicit_creator_action"] is True
        assert storage.list_colorist_decision_projections("project-color")[0].decision_id == decision.decision_id


def test_colorist_records_crew_reasoning_when_available():
    with TemporaryDirectory() as tmp:
        storage = DatabaseStorage(tmp)
        crew = _FakeCrewIntelligenceService()
        service = ColoristIntelligenceService(storage=storage, crew_intelligence_service=crew)

        response = service.create_or_update_look_bible(
            "project-color",
            ColorLookBibleRequest(project_context={"color_palette": ["cyan", "vermillion"]}),
        )

        assert response.reasoning_record_id == "crew-reason-colorist-001"
        assert crew.reasoning_calls
        assert crew.reasoning_calls[0]["agent_role"] == AgentRole.COLORIST
        assert crew.reasoning_calls[0]["reasoning_type"] == CrewReasoningType.PLAN
