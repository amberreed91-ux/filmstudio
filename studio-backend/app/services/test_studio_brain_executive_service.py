from __future__ import annotations

from app.data.storage import get_storage
from app.models.studio_brain import (
    StudioBrainDepartmentSignal,
    StudioBrainDispatchDirectiveRequest,
    StudioBrainOpenSessionRequest,
    StudioBrainResolveConflictRequest,
    StudioBrainResolutionMode,
    StudioBrainSessionPurpose,
)
from app.models.crew import AgentRole
from app.services.studio_brain_executive_service import StudioBrainExecutiveService


def _creator_signal(session):
    return StudioBrainDepartmentSignal(
        signal_id=f"signal-director-{session.session_id}",
        session_id=session.session_id,
        project_id=session.project_id,
        agent_role=AgentRole.DIRECTOR,
        department_name="Director",
        status="active",
        purpose=session.purpose,
        summary="Two plausible production paths need a creator read before dispatch.",
        recommended_actions=["Ask the creator which emotional direction should lead the revision."],
        open_questions=["Should this revision preserve emotional residue or structural clarity?"],
        requires_creator_decision=True,
    )


def _service(tmp_path, *, creator_adapter: bool = False):
    storage = get_storage("sqlite", storage_path=str(tmp_path))
    adapters = {AgentRole.DIRECTOR: _creator_signal} if creator_adapter else None
    return StudioBrainExecutiveService(storage=storage, knowledge_service=None, department_adapters=adapters), storage


def test_studio_brain_executive_session_plan_and_readiness_round_trip(tmp_path):
    service, storage = _service(tmp_path)

    session = service.open_session(
        "proj-001",
        StudioBrainOpenSessionRequest(
            purpose=StudioBrainSessionPurpose.PRODUCTION_PLANNING,
            scope={"phase": "production"},
            created_by="owner",
        ),
    )
    signals = service.gather_department_signals(session.session_id)
    plan = service.generate_production_plan(session.session_id)
    readiness = service.create_readiness_snapshot(session.session_id)

    assert session.session_id
    assert len(signals) >= 3
    assert plan.steps
    assert plan.reasoning_trace_id
    assert readiness.snapshot_id == storage.get_studio_brain_session(session.session_id).latest_readiness_snapshot_id
    assert storage.get_studio_brain_production_plan(plan.plan_id).summary == plan.summary


def test_studio_brain_detects_and_escalates_creator_conflict(tmp_path):
    service, storage = _service(tmp_path, creator_adapter=True)
    session = service.open_session("proj-001", StudioBrainOpenSessionRequest())

    service.gather_department_signals(session.session_id)
    conflicts = service.detect_conflicts(session.session_id)
    assert conflicts

    creator_conflict = next(conflict for conflict in conflicts if conflict.requires_creator_decision)
    resolution = service.resolve_conflict(
        session.session_id,
        creator_conflict.conflict_id,
        StudioBrainResolveConflictRequest(
            actor_id="owner",
            resolution_mode=StudioBrainResolutionMode.ESCALATE_CREATOR,
        ),
    )

    assert resolution.created_directive_ids
    directive = storage.get_studio_brain_execution_directive(resolution.created_directive_ids[0])
    assert directive.requires_creator_approval is True


def test_studio_brain_directive_dispatch_requires_approval(tmp_path):
    service, _ = _service(tmp_path, creator_adapter=True)
    session = service.open_session("proj-001", StudioBrainOpenSessionRequest())
    service.gather_department_signals(session.session_id)
    service.detect_conflicts(session.session_id)
    directives = service.propose_directives(session.session_id)

    approval_directive = next(directive for directive in directives if directive.requires_creator_approval)
    try:
        service.dispatch_directive(session.session_id, approval_directive.directive_id, StudioBrainDispatchDirectiveRequest(approve=False))
    except Exception as exc:
        assert "requires creator approval" in str(getattr(exc, "message", exc)).lower()
    else:
        raise AssertionError("dispatch should require creator approval")


def test_studio_brain_legacy_projection_preserves_advisory_boundaries(tmp_path):
    service, _ = _service(tmp_path)
    session = service.open_session("proj-001", StudioBrainOpenSessionRequest())
    signals = service.gather_department_signals(session.session_id)
    plan = service.generate_production_plan(session.session_id)
    response = service.get_session_response(session.session_id)

    bundle = response.legacy_orchestration_bundle
    assert bundle["deterministic_audit"]["deterministic"] is True
    assert bundle["deterministic_audit"]["advisory_only"] is True
    assert bundle["canonical_truth_boundaries"]["authority"]["canonical_mutation"] == "forbidden"
    assert signals
    assert plan.plan_id == response.plan.plan_id
