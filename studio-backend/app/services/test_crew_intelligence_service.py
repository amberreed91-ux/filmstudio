from app.data.storage import DatabaseStorage
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewHandoffStatus, CrewReasoningType
from app.services.crew_intelligence_service import CrewIntelligenceService, CrewIntelligenceStateError


def make_service(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "studio-data"))
    return CrewIntelligenceService(storage=storage)


def test_create_and_list_crew_reasoning_record(tmp_path):
    service = make_service(tmp_path)

    record = service.create_reasoning_record(
        project_id="project-crew-1",
        agent_role=AgentRole.SCRIPT_ANALYST,
        reasoning_type=CrewReasoningType.ANALYSIS,
        scene_id="scene-001",
        observation="The scene establishes a withheld motive.",
        inference="The next department needs the emotional turn preserved.",
        recommendation_summary="Carry the withheld motive into the storyboard handoff.",
        creator_note="This beat should stay unresolved until the later callback.",
    )

    rows = service.list_reasoning_records("project-crew-1", filters={"agent_role": "script_analyst"})

    assert record.reasoning_id
    assert rows[0].reasoning_id == record.reasoning_id
    assert rows[0].advisory_only is True
    assert rows[0].requires_creator_decision is False


def test_creator_facing_score_language_is_flagged(tmp_path):
    service = make_service(tmp_path)

    record = service.create_reasoning_record(
        project_id="project-crew-1",
        agent_role=AgentRole.DIRECTOR,
        reasoning_type=CrewReasoningType.CREATIVE_SYNTHESIS,
        observation="Score: 8/10",
        recommendation_summary="Review the cut.",
    )

    assert record.metadata["creator_language_warnings"]
    assert record.advisory_only is True


def test_handoff_lifecycle_rejects_invalid_transition(tmp_path):
    service = make_service(tmp_path)

    handoff = service.create_handoff(
        project_id="project-crew-1",
        source_role=AgentRole.SCRIPT_ANALYST,
        target_role=AgentRole.STORYBOARD_ARTIST,
        context_summary="Scene intent is ready for visual planning.",
    )

    acknowledged = service.update_handoff_status(
        handoff.handoff_id,
        CrewHandoffStatus.ACKNOWLEDGED,
        actor_id="agent-storyboard_artist",
    )
    assert acknowledged is not None
    assert acknowledged.status == CrewHandoffStatus.ACKNOWLEDGED

    completed = service.update_handoff_status(handoff.handoff_id, CrewHandoffStatus.COMPLETED)
    assert completed is not None
    assert completed.status == CrewHandoffStatus.COMPLETED

    try:
        service.update_handoff_status(handoff.handoff_id, CrewHandoffStatus.IN_PROGRESS)
        assert False, "expected invalid transition to raise"
    except CrewIntelligenceStateError:
        pass


def test_deliberation_requiring_creator_appears_in_attention(tmp_path):
    service = make_service(tmp_path)

    deliberation = service.create_deliberation(
        project_id="project-crew-1",
        participating_roles=[AgentRole.EDITOR, AgentRole.MEMORY_ARCHIVIST],
        issue_summary="The shorter cut improves clarity but may weaken the callback.",
        points_of_agreement=["The pause carries story pressure."],
        points_of_tension=["Editor wants pace; Memory Archivist wants residue."],
        recommended_resolution="Ask creator which value should lead this revision.",
        requires_creator_decision=True,
        creator_question="Should this pass prioritize emotional residue or structural clarity?",
    )

    attention = service.get_creator_attention("project-crew-1")

    assert deliberation.deliberation_id
    assert attention
    assert attention[0].source_type == "deliberation"


def test_overview_snapshots_department_status_once_per_state(tmp_path):
    service = make_service(tmp_path)

    service.create_reasoning_record(
        project_id="project-crew-1",
        agent_role=AgentRole.MEMORY_ARCHIVIST,
        reasoning_type=CrewReasoningType.MEMORY_RECALL,
        observation="A callback is active.",
        recommendation_summary="Keep the callback visible to downstream departments.",
    )

    service.get_project_overview("project-crew-1")
    service.get_project_overview("project-crew-1")

    snapshots = service.storage.list_crew_department_status_snapshots(
        "project-crew-1",
        agent_role="memory_archivist",
    )
    assert len(snapshots) == 1
    assert snapshots[0]["last_reasoning_id"]
