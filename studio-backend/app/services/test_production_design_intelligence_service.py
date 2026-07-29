from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

from app.data.storage import DatabaseStorage
from app.models.crew import AgentRole
from app.models.production_design import (
    ProductionDesignAssessmentRequest,
    ProductionDesignDecisionRequest,
    ProductionDesignDecisionUpdateRequest,
    ProductionDesignObservationRequest,
    ProductionDesignPlanRequest,
    ProductionDesignRenderContextRequest,
)
from app.services.production_design_intelligence_service import ProductionDesignIntelligenceService
from app.services.stability import ValidationError


class _FakeReasoning:
    reasoning_id = "reasoning-production-design"


class _FakeCrewIntelligence:
    def __init__(self):
        self.created = []

    def build_role_context(self, *args, **kwargs):
        class _Context:
            memory_refs = []
            spine_refs = []
            context_notes = []

        return _Context()

    def create_reasoning_record(self, **kwargs):
        self.created.append(kwargs)
        return _FakeReasoning()


def _service(crew=None):
    tmp = TemporaryDirectory()
    storage = DatabaseStorage(tmp.name)
    service = ProductionDesignIntelligenceService(storage=storage, crew_intelligence_service=crew)
    return tmp, storage, service


def test_create_plan_persists_environment_props_costumes_and_slots():
    crew = _FakeCrewIntelligence()
    tmp, storage, service = _service(crew)
    try:
        response = service.create_plan(
            "project-pd",
            ProductionDesignPlanRequest(
                scene_id="scene_001",
                shot_id="shot_001",
                scene_context={
                    "location": "INT. SAFEHOUSE KITCHEN - NIGHT",
                    "description": "Mara waits by a broken lamp with a key and an old photo on the table.",
                    "characters": ["Mara"],
                    "wardrobe": ["gray coat", "muddy boots"],
                    "props": ["key", "old photo"],
                    "color_palette": ["gray", "sickly green"],
                    "motif_obligations": ["old photo"],
                    "continuity_constraints": ["The key stays in Mara's hand by the end of the scene."],
                },
            ),
        )

        plan = storage.get_production_design_plan(response.plan.plan_id)
        assert plan is not None
        assert plan.project_id == "project-pd"
        assert plan.environment_profile.location_name == "INT. SAFEHOUSE KITCHEN - NIGHT"
        assert {record.prop_name for record in plan.prop_records} >= {"key", "old photo"}
        assert plan.costume_records[0].character_name == "Mara"
        assert plan.symbolic_refs
        assert all(slot.budget_used <= slot.budget_limit for slot in plan.render_slot_suggestions)
        assert plan.advisory_only is True
        assert response.reasoning_record_id == "reasoning-production-design"
        assert crew.created[0]["agent_role"] == AgentRole.PRODUCTION_DESIGNER
    finally:
        tmp.cleanup()


def test_observation_assessment_and_render_context_are_durable_low_data_safe():
    tmp, storage, service = _service()
    try:
        plan = service.create_plan(
            "project-pd",
            ProductionDesignPlanRequest(
                scene_id="scene_001",
                scene_context={
                    "location": "warehouse",
                    "description": "A locked door and a key sit under a hanging lamp.",
                    "props": ["key"],
                },
            ),
        ).plan

        observation = service.create_observation(
            "project-pd",
            ProductionDesignObservationRequest(plan_id=plan.plan_id, asset_id="asset-missing", scene_id="scene_001"),
        )
        assessment = service.create_assessment(
            "project-pd",
            ProductionDesignAssessmentRequest(plan_id=plan.plan_id, observation_id=observation.observation_id, create_crew_reasoning=False),
        )
        render_context = service.build_render_context(
            "project-pd",
            ProductionDesignRenderContextRequest(plan_id=plan.plan_id, provider="runway"),
        )

        assert storage.get_production_design_observation(observation.observation_id) is not None
        assert "key" in assessment.missing_required_elements
        assert "score" not in assessment.alignment_summary.lower()
        assert render_context.environment_direction
        assert render_context.advisory_only is True
    finally:
        tmp.cleanup()


def test_decision_save_requires_explicit_creator_action():
    tmp, storage, service = _service()
    try:
        with pytest.raises(ValidationError):
            service.save_decision(
                "project-pd",
                ProductionDesignDecisionRequest(decision_text="Keep the key tarnished.", explicit_save=False),
            )

        decision = service.save_decision(
            "project-pd",
            ProductionDesignDecisionRequest(decision_text="Keep the key tarnished.", scene_id="scene_001"),
        )

        saved = storage.list_production_design_decision_memory_projections("project-pd")
        assert saved[0].decision_id == decision.decision_id
        assert saved[0].editable is True
        assert saved[0].forgotten_at is None

        updated = service.update_decision(
            "project-pd",
            decision.decision_id,
            ProductionDesignDecisionUpdateRequest(decision_text="Keep the key tarnished but visible.", forgotten_at="2026-01-01T00:00:00Z"),
        )

        assert updated.decision_text == "Keep the key tarnished but visible."
        assert updated.forgotten_at == "2026-01-01T00:00:00Z"
    finally:
        tmp.cleanup()
