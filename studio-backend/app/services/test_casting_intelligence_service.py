from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

from app.data.storage import DatabaseStorage
from app.models.casting_intelligence import (
    AuditionPackageRequest,
    AuditionSubmissionRequest,
    CastingDecisionRequest,
    CastingRecommendationRequest,
    CastingReadinessRequest,
    RoleBreakdownBuildRequest,
    TalentConsentRecord,
    TalentProfileRequest,
)
from app.services.casting_intelligence_service import CastingIntelligenceService
from app.services.project_store import ProjectStore
from app.services.stability import StateError


def _service():
    tmp = TemporaryDirectory()
    storage = DatabaseStorage(tmp.name)
    store = ProjectStore(f"{tmp.name}/projects.json")
    store.save_project(
        {
            "project_id": "project-casting",
            "title": "Casting Fixture",
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "description": "Mara hides grief while asking Jonah to keep quiet.",
                    "characters": ["Mara", "Jonah"],
                    "dialogue_lines": [{"character_name": "Mara", "text": "Keep your voice down."}],
                },
                {
                    "scene_id": "scene_002",
                    "description": "Mara returns with anger under control.",
                    "characters": ["Mara"],
                },
            ],
        }
    )
    service = CastingIntelligenceService(storage=storage, project_store_service=store)
    return tmp, storage, service


def test_casting_flow_builds_roles_recommends_approves_and_projects():
    tmp, _storage, service = _service()
    try:
        roles = service.build_role_breakdowns(
            "project-casting",
            RoleBreakdownBuildRequest(persist=True),
        ).roles

        mara_role = next(role for role in roles if role.character_name == "Mara")
        assert mara_role.role_size == "supporting"
        assert mara_role.evidence_refs

        talent = service.create_talent_profile(
            "project-casting",
            TalentProfileRequest(
                display_name="Lena Vale",
                modality="human",
                performance_strengths=["restrained grief under pressure"],
                vocal_characteristics=["low, held-back delivery"],
                consent_records=[
                    TalentConsentRecord(
                        consent_id="consent-lena-voice",
                        project_id="project-casting",
                        talent_id="placeholder",
                        modality="voice",
                        status="granted",
                    )
                ],
            ),
        )
        # Normalize the embedded fixture consent to the generated talent id.
        talent.consent_records[0].talent_id = talent.talent_id
        service.storage.save_talent_profile(talent)

        package = service.create_audition_package(
            "project-casting",
            mara_role.role_id,
            AuditionPackageRequest(),
        )
        audition = service.submit_audition(
            "project-casting",
            package.package_id,
            AuditionSubmissionRequest(
                talent_id=talent.talent_id,
                submitted_text="A contained reading that lets grief arrive as a pause.",
            ),
        )
        evaluation = service.evaluate_audition("project-casting", audition.audition_id)
        assert evaluation.uncertainty_label == "supported"

        recommendations = service.recommend_casting(
            "project-casting",
            mara_role.role_id,
            CastingRecommendationRequest(candidate_talent_ids=[talent.talent_id]),
        )
        assert recommendations[0].evidence_refs
        assert recommendations[0].readiness_label == "ready"

        decision = service.approve_casting_decision(
            "project-casting",
            CastingDecisionRequest(
                role_id=mara_role.role_id,
                talent_id=talent.talent_id,
                recommendation_id=recommendations[0].recommendation_id,
                audition_id=audition.audition_id,
                evaluation_id=evaluation.evaluation_id,
                decision_rationale="Cast Lena for the role's held-back grief.",
            ),
        )
        assert decision.active is True
        assert decision.readiness_label == "ready"

        projection = service.get_active_casting_projection("project-casting", role_id=mara_role.role_id)
        assert projection.active_decisions[0].decision_id == decision.decision_id
        assert projection.talent_profiles[0].talent_id == talent.talent_id

        report = service.create_readiness_report("project-casting", CastingReadinessRequest())
        assert report.total_roles == 2
        assert report.covered_roles == 1
        assert report.readiness_label == "needs_review"

        signal = service.department_signal("project-casting")
        assert signal.total_roles == 2
        assert signal.covered_roles == 1
    finally:
        tmp.cleanup()


def test_revoked_consent_blocks_approval_without_override():
    tmp, _storage, service = _service()
    try:
        role = service.build_role_breakdowns("project-casting").roles[0]
        talent = service.create_talent_profile(
            "project-casting",
            TalentProfileRequest(
                display_name="Blocked Performer",
                modality="human",
                consent_records=[
                    TalentConsentRecord(
                        consent_id="consent-blocked",
                        project_id="project-casting",
                        talent_id="blocked",
                        modality="voice",
                        status="revoked",
                    )
                ],
            ),
        )
        talent.consent_records[0].talent_id = talent.talent_id
        service.storage.save_talent_profile(talent)

        with pytest.raises(StateError):
            service.approve_casting_decision(
                "project-casting",
                CastingDecisionRequest(role_id=role.role_id, talent_id=talent.talent_id),
            )
    finally:
        tmp.cleanup()


def test_memory_save_is_explicit():
    tmp, _storage, service = _service()
    try:
        role = service.build_role_breakdowns("project-casting").roles[0]
        talent = service.create_talent_profile(
            "project-casting",
            TalentProfileRequest(display_name="AI Placeholder", modality="placeholder"),
        )
        decision = service.approve_casting_decision(
            "project-casting",
            CastingDecisionRequest(role_id=role.role_id, talent_id=talent.talent_id),
        )
        assert decision.decision_id

        project = service.project_store.get_project("project-casting")
        memories = project.get("memory_context", {}).get("creative_memories", [])
        assert memories == []

        saved = service.approve_casting_decision(
            "project-casting",
            CastingDecisionRequest(
                role_id=role.role_id,
                talent_id=talent.talent_id,
                decision_rationale="Use the placeholder while auditions are pending.",
                save_to_project_memory=True,
            ),
        )
        assert saved.decision_id
        project = service.project_store.get_project("project-casting")
        assert project.get("memory_context", {}).get("creative_memories")
    finally:
        tmp.cleanup()


def test_recasting_supersedes_prior_active_decision():
    tmp, _storage, service = _service()
    try:
        role = service.build_role_breakdowns("project-casting").roles[0]
        first = service.create_talent_profile(
            "project-casting",
            TalentProfileRequest(display_name="First Stand-In", modality="placeholder"),
        )
        second = service.create_talent_profile(
            "project-casting",
            TalentProfileRequest(display_name="Second Stand-In", modality="placeholder"),
        )

        first_decision = service.approve_casting_decision(
            "project-casting",
            CastingDecisionRequest(role_id=role.role_id, talent_id=first.talent_id),
        )
        second_decision = service.approve_casting_decision(
            "project-casting",
            CastingDecisionRequest(role_id=role.role_id, talent_id=second.talent_id),
        )

        active = service.storage.list_casting_decisions("project-casting", role_id=role.role_id, active=True)
        history = service.storage.list_casting_decisions("project-casting", role_id=role.role_id, active=False)
        assert [decision.decision_id for decision in active] == [second_decision.decision_id]
        assert history[0].decision_id == first_decision.decision_id
        assert history[0].status == "superseded"
    finally:
        tmp.cleanup()
