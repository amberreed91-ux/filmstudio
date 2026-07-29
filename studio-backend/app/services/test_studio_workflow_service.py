from __future__ import annotations

import pytest

from app.data.storage import DatabaseStorage
from app.models.production_queue import (
    ProductionQueueDependencyCreate,
    ProductionQueueDependencyType,
    ProductionQueueItemCreate,
    ProductionQueueStatus,
    ProductionQueueWorkType,
)
from app.models.studio_workflow import (
    StudioApprovalDecisionCreate,
    StudioApprovalDecisionValue,
    StudioApprovalGateCreate,
    StudioApprovalGateStatus,
    StudioApprovalGateType,
    StudioArtifactType,
    StudioArtifactVersionCreate,
    StudioArtifactVersionStatus,
    StudioCollaboratorRole,
    StudioWorkflowCommentCreate,
)
from app.services.production_queue_service import ProductionQueueService
from app.services.project_store import ProjectStore
from app.services.stability import StateError, ValidationError
from app.services.studio_workflow_service import StudioWorkflowService


class _FakeGuard:
    def __init__(self, allowed: bool, reason: str = "guard reason"):
        self.allowed = allowed
        self.reason = reason
        self.evidence = []

    def model_dump(self, mode: str = "json"):
        return {"allowed": self.allowed, "reason": self.reason, "evidence": []}


class _FakeAcceptanceService:
    def __init__(self, allowed: bool):
        self.allowed = allowed
        self.calls = []

    def evaluate_package_approval_guard(self, package_id: str, desired_status: str = "approved"):
        self.calls.append((package_id, desired_status))
        return _FakeGuard(self.allowed, "ready" if self.allowed else "Run production acceptance before approving this package.")


@pytest.fixture()
def workflow_env(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "db"))
    project_store = ProjectStore(str(tmp_path / "project_state_store.json"))
    project_store.create_project("Sprint 9 Test", project_id="project_s9")
    service = StudioWorkflowService(storage=storage, project_store_service=project_store)
    return storage, project_store, service


def _create_scene_version_and_gate(service: StudioWorkflowService):
    version = service.create_artifact_version(
        "project_s9",
        StudioArtifactVersionCreate(
            artifact_type=StudioArtifactType.SCENE,
            artifact_id="scene_001",
            title="Scene 1 cut",
            created_by="owner",
        ),
    )
    gate = service.create_approval_gate(
        "project_s9",
        StudioApprovalGateCreate(
            gate_type=StudioApprovalGateType.SCENE_REVIEW,
            target_type="scene",
            target_id="scene_001",
            version_id=version.version_id,
            required_role=StudioCollaboratorRole.PRODUCER,
            opened_by="owner",
        ),
    )
    return version, gate


def test_scene_approval_persists_decision_version_projection_and_events(workflow_env):
    storage, project_store, service = workflow_env
    version, gate = _create_scene_version_and_gate(service)

    decision = service.record_approval_decision(
        "project_s9",
        gate.gate_id,
        StudioApprovalDecisionCreate(
            actor_id="owner",
            actor_role=StudioCollaboratorRole.OWNER,
            decision=StudioApprovalDecisionValue.APPROVE,
            rationale="The cut preserves the intended tension.",
        ),
    )

    updated_gate = storage.get_studio_approval_gate(gate.gate_id)
    updated_version = storage.get_studio_artifact_version(version.version_id)
    project = project_store.get_project("project_s9")
    events = storage.list_studio_workflow_events("project_s9", limit=20)

    assert decision.decision == StudioApprovalDecisionValue.APPROVE
    assert updated_gate.status == StudioApprovalGateStatus.APPROVED
    assert updated_version.status == StudioArtifactVersionStatus.APPROVED
    assert project["scene_review_status"]["scene_001"] == "approved"
    assert "scene_001" in project["approved_scenes"]
    assert any(event.event_type == "decision_recorded" for event in events)
    assert any(event.event_type == "projection_updated" for event in events)


def test_reviewer_cannot_approve_producer_gate(workflow_env):
    _, _, service = workflow_env
    _, gate = _create_scene_version_and_gate(service)

    with pytest.raises(ValidationError):
        service.record_approval_decision(
            "project_s9",
            gate.gate_id,
            StudioApprovalDecisionCreate(
                actor_id="reviewer",
                actor_role=StudioCollaboratorRole.REVIEWER,
                decision=StudioApprovalDecisionValue.APPROVE,
            ),
        )


def test_ai_advisory_cannot_close_gate(workflow_env):
    _, _, service = workflow_env
    _, gate = _create_scene_version_and_gate(service)

    with pytest.raises(ValidationError):
        service.record_approval_decision(
            "project_s9",
            gate.gate_id,
            StudioApprovalDecisionCreate(
                actor_id="co_director",
                actor_role=StudioCollaboratorRole.AI_ADVISORY,
                decision=StudioApprovalDecisionValue.APPROVE,
            ),
        )


def test_request_changes_marks_version_and_creates_revision_task(workflow_env):
    storage, project_store, service = workflow_env
    version, gate = _create_scene_version_and_gate(service)

    service.record_approval_decision(
        "project_s9",
        gate.gate_id,
        StudioApprovalDecisionCreate(
            actor_id="producer",
            actor_role=StudioCollaboratorRole.PRODUCER,
            decision=StudioApprovalDecisionValue.REQUEST_CHANGES,
            notes="Hold the silence longer before the reveal.",
            create_revision_task=True,
        ),
    )

    assert storage.get_studio_approval_gate(gate.gate_id).status == StudioApprovalGateStatus.CHANGES_REQUESTED
    assert storage.get_studio_artifact_version(version.version_id).status == StudioArtifactVersionStatus.CHANGES_REQUESTED
    assert storage.list_studio_workflow_tasks("project_s9", status="open")[0].task_type == "revision"
    assert project_store.get_project("project_s9")["scene_review_status"]["scene_001"] == "changes_requested"


def test_comments_are_scoped_and_resolvable(workflow_env):
    storage, _, service = workflow_env

    comment = service.post_comment(
        "project_s9",
        StudioWorkflowCommentCreate(
            target_type="scene",
            target_id="scene_001",
            actor_id="editor",
            actor_role=StudioCollaboratorRole.EDITOR,
            body="The handoff needs one more frame of visual breath.",
        ),
    )
    resolved = service.resolve_comment("project_s9", comment.comment_id, "producer")

    assert resolved.status == "resolved"
    comments = storage.list_studio_workflow_comments("project_s9", target_type="scene", target_id="scene_001")
    assert comments[0].comment_id == comment.comment_id
    assert comments[0].resolved_by == "producer"


def test_explicit_memory_save_gate_writes_creative_memory_but_comments_do_not(workflow_env):
    _, project_store, service = workflow_env
    service.post_comment(
        "project_s9",
        StudioWorkflowCommentCreate(
            target_type="scene",
            target_id="scene_001",
            actor_id="editor",
            actor_role=StudioCollaboratorRole.EDITOR,
            body="Remember this only if the director explicitly saves it.",
        ),
    )
    assert project_store.list_creative_memories("project_s9") == []

    gate = service.create_approval_gate(
        "project_s9",
        StudioApprovalGateCreate(
            gate_type=StudioApprovalGateType.MEMORY_DECISION_SAVE,
            target_type="scene",
            target_id="scene_001",
            required_role=StudioCollaboratorRole.PRODUCER,
            evidence_policy={
                "memory_data": {
                    "decision_type": "pacing_patience",
                    "user_note": "Hold silence longer before emotional reveals.",
                    "inferred_tradeoff": "emotional_residue_vs_structural_clarity",
                    "inferred_tradeoff_explanation": "The approved note favors lingering feeling over faster exposition.",
                    "source_context": {"scene_id": "scene_001"},
                }
            },
        ),
    )

    service.record_approval_decision(
        "project_s9",
        gate.gate_id,
        StudioApprovalDecisionCreate(
            actor_id="producer",
            actor_role=StudioCollaboratorRole.PRODUCER,
            decision=StudioApprovalDecisionValue.APPROVE,
        ),
    )

    memories = project_store.list_creative_memories("project_s9")
    assert len(memories) == 1
    assert memories[0]["decision_type"] == "pacing_patience"
    assert memories[0]["editable"] is True
    assert memories[0]["forgettable"] is True


def test_package_acceptance_gate_blocks_when_acceptance_guard_blocks(workflow_env):
    storage, project_store, _ = workflow_env
    service = StudioWorkflowService(
        storage=storage,
        project_store_service=project_store,
        acceptance_service=_FakeAcceptanceService(allowed=False),
    )
    gate = service.create_approval_gate(
        "project_s9",
        StudioApprovalGateCreate(
            gate_type=StudioApprovalGateType.PACKAGE_ACCEPTANCE,
            target_type="final_package",
            target_id="package_001",
            required_role=StudioCollaboratorRole.PRODUCER,
        ),
    )

    with pytest.raises(StateError):
        service.record_approval_decision(
            "project_s9",
            gate.gate_id,
            StudioApprovalDecisionCreate(
                actor_id="producer",
                actor_role=StudioCollaboratorRole.PRODUCER,
                decision=StudioApprovalDecisionValue.APPROVE,
            ),
        )

    assert storage.get_studio_approval_gate(gate.gate_id).status == StudioApprovalGateStatus.BLOCKED


def test_approval_releases_manual_queue_dependency(workflow_env):
    storage, project_store, service = workflow_env
    queue = ProductionQueueService(storage=storage, worker_owner_id="test-owner")
    service._queue_service = queue
    queue_item = queue.enqueue_item(
        ProductionQueueItemCreate(
            project_id="project_s9",
            work_type=ProductionQueueWorkType.CUSTOM_WORKFLOW,
            canonical_type="custom_workflow",
            canonical_id="workflow_waiting_for_scene_001",
            idempotency_key="workflow_waiting_for_scene_001",
            dependencies=[
                ProductionQueueDependencyCreate(
                    depends_on_type=ProductionQueueDependencyType.MANUAL_GATE,
                    depends_on_id="scene_001_manual_gate",
                    required_status="satisfied",
                    reason="Wait for scene approval.",
                )
            ],
        )
    )
    decision = queue.evaluate_dependencies(queue_item)
    queue._mark_waiting_dependency(queue_item, decision)
    version = service.create_artifact_version(
        "project_s9",
        StudioArtifactVersionCreate(
            artifact_type=StudioArtifactType.SCENE,
            artifact_id="scene_001",
            created_by="owner",
        ),
    )
    gate = service.create_approval_gate(
        "project_s9",
        StudioApprovalGateCreate(
            gate_type=StudioApprovalGateType.SCENE_REVIEW,
            target_type="scene",
            target_id="scene_001",
            version_id=version.version_id,
            manual_dependency_id="scene_001_manual_gate",
            required_role=StudioCollaboratorRole.PRODUCER,
        ),
    )

    service.record_approval_decision(
        "project_s9",
        gate.gate_id,
        StudioApprovalDecisionCreate(
            actor_id="producer",
            actor_role=StudioCollaboratorRole.PRODUCER,
            decision=StudioApprovalDecisionValue.APPROVE,
        ),
    )

    updated_item = storage.get_queue_item(queue_item.queue_item_id)
    deps = storage.list_queue_dependencies(queue_item.queue_item_id)

    assert deps[0].status == "satisfied"
    assert updated_item.status == ProductionQueueStatus.QUEUED


def test_legacy_collaboration_migrates_once(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "db"))
    project_store = ProjectStore(str(tmp_path / "project_state_store.json"))
    project_store.create_project("Legacy Collab", project_id="project_s9")
    project_store.update_project(
        "project_s9",
        {
            "collaboration": {
                "owner_user_id": "owner",
                "members": [{"user_id": "editor_1", "display_name": "Editor One", "role": "editor"}],
                "live_comments": [
                    {
                        "user_id": "editor_1",
                        "display_name": "Editor One",
                        "role": "editor",
                        "room": "screening",
                        "comment": "This cut releases tension too early.",
                        "created_at": "2026-07-27T00:00:00Z",
                    }
                ],
                "approval_votes": [
                    {
                        "user_id": "producer_1",
                        "display_name": "Producer One",
                        "role": "producer",
                        "scene_id": "scene_001",
                        "vote": "approve",
                        "updated_at": "2026-07-27T00:01:00Z",
                    }
                ],
            }
        },
    )
    service = StudioWorkflowService(storage=storage, project_store_service=project_store)

    first = service.workflow_summary("project_s9")
    second = service.workflow_summary("project_s9")

    assert any(c.actor_id == "editor_1" for c in first.collaborators)
    assert len(storage.list_studio_workflow_comments("project_s9", limit=20)) == 2
    assert len(storage.list_studio_workflow_comments("project_s9", limit=20)) == 2
    assert second.project_state.metadata["legacy_collaboration_migrated"] is True
