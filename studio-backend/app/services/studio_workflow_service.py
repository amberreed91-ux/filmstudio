from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.data import get_storage
from app.models.studio_workflow import (
    StudioApprovalDecision,
    StudioApprovalDecisionCreate,
    StudioApprovalDecisionValue,
    StudioApprovalGate,
    StudioApprovalGateCreate,
    StudioApprovalGateStatus,
    StudioApprovalGateType,
    StudioArtifactType,
    StudioArtifactVersion,
    StudioArtifactVersionCreate,
    StudioArtifactVersionStatus,
    StudioCollaborator,
    StudioCollaboratorRole,
    StudioCollaboratorUpsert,
    StudioVersionLineage,
    StudioVersionRelationshipType,
    StudioWorkflowComment,
    StudioWorkflowCommentCreate,
    StudioWorkflowCommentStatus,
    StudioWorkflowEvent,
    StudioWorkflowEvidenceRef,
    StudioWorkflowPhase,
    StudioWorkflowProjectState,
    StudioWorkflowStatus,
    StudioWorkflowSummary,
    StudioWorkflowTask,
    StudioWorkflowTaskStatus,
    utc_now_iso,
)
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer

logger = logging.getLogger("studio-workflow")


_ACTIVE_GATE_STATUSES = {
    StudioApprovalGateStatus.PENDING.value,
    StudioApprovalGateStatus.READY.value,
    StudioApprovalGateStatus.WAITING_EVIDENCE.value,
    StudioApprovalGateStatus.BLOCKED.value,
}

_ROLE_RANK: dict[str, int] = {
    StudioCollaboratorRole.AI_ADVISORY.value: -1,
    StudioCollaboratorRole.VIEWER.value: 0,
    StudioCollaboratorRole.REVIEWER.value: 1,
    StudioCollaboratorRole.EDITOR.value: 2,
    StudioCollaboratorRole.DIRECTOR.value: 3,
    StudioCollaboratorRole.PRODUCER.value: 4,
    StudioCollaboratorRole.OWNER.value: 5,
}


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:14]}"


def _now() -> str:
    return utc_now_iso()


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {}


class StudioWorkflowService:
    """Canonical professional workflow layer for approvals, versions, and collaboration."""

    def __init__(
        self,
        *,
        storage: Any = None,
        project_store_service: Any = None,
        queue_service: Any = None,
        decision_gate_service: Any = None,
        acceptance_service: Any = None,
    ) -> None:
        self._storage = storage
        self._project_store_service = project_store_service
        self._queue_service = queue_service
        self._decision_gate_service = decision_gate_service
        self._acceptance_service = acceptance_service

    def _storage_ref(self):
        return self._storage or get_storage("sqlite")

    def set_storage(self, storage: Any) -> None:
        self._storage = storage

    def _project_store_ref(self):
        if self._project_store_service is not None:
            return self._project_store_service
        from app.services.project_store import project_store

        self._project_store_service = project_store
        return project_store

    def _queue_ref(self):
        if self._queue_service is not None:
            return self._queue_service
        from app.services.production_queue_service import production_queue_service

        production_queue_service.set_storage(self._storage_ref())
        self._queue_service = production_queue_service
        return production_queue_service

    def _decision_gate_ref(self):
        if self._decision_gate_service is not None:
            return self._decision_gate_service
        from app.services.studio_decision_gate_service import StudioDecisionGateService

        self._decision_gate_service = StudioDecisionGateService(storage=self._storage_ref())
        return self._decision_gate_service

    def _acceptance_ref(self):
        if self._acceptance_service is not None:
            return self._acceptance_service
        from app.services.production_acceptance_service import production_acceptance_service

        production_acceptance_service._storage = self._storage_ref()
        self._acceptance_service = production_acceptance_service
        return production_acceptance_service

    def _project_exists(self, project_id: str) -> bool:
        if not project_id.strip():
            return False
        try:
            project = self._project_store_ref().get_project(project_id)
            if project is not None:
                return True
        except Exception:
            pass
        try:
            return self._storage_ref().get_project(project_id) is not None
        except Exception:
            return False

    def _require_project(self, project_id: str) -> None:
        if not self._project_exists(project_id):
            raise ValidationError(f"Project {project_id} not found")

    def _event(
        self,
        *,
        project_id: str,
        event_type: str,
        actor_id: str = "",
        target_type: str = "",
        target_id: str = "",
        version_id: str | None = None,
        gate_id: str | None = None,
        decision_id: str | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> StudioWorkflowEvent:
        event = StudioWorkflowEvent(
            event_id=_id("sw_evt"),
            project_id=project_id,
            event_type=event_type,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            version_id=version_id,
            gate_id=gate_id,
            decision_id=decision_id,
            message=message,
            details=details or {},
            created_at=_now(),
        )
        self._storage_ref().save_studio_workflow_event(event)
        return event

    def get_or_create_project_workflow(self, project_id: str) -> StudioWorkflowProjectState:
        self._require_project(project_id)
        existing = self._storage_ref().get_studio_workflow_project_state(project_id)
        if existing is not None:
            self._migrate_legacy_collaboration_once(existing)
            return self._storage_ref().get_studio_workflow_project_state(project_id) or existing

        now = _now()
        state = StudioWorkflowProjectState(
            project_id=project_id,
            current_phase=StudioWorkflowPhase.INTAKE,
            workflow_status=StudioWorkflowStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self._storage_ref().save_studio_workflow_project_state(state)
        self._event(
            project_id=project_id,
            event_type="workflow_initialized",
            message="Professional studio workflow initialized.",
        )
        self.upsert_collaborator(
            project_id,
            StudioCollaboratorUpsert(
                actor_id="owner",
                display_name="Project Owner",
                role=StudioCollaboratorRole.OWNER,
                metadata={"source": "workflow_default"},
            ),
        )
        self._migrate_legacy_collaboration_once(state)
        return self._storage_ref().get_studio_workflow_project_state(project_id) or state

    def update_project_phase(
        self,
        project_id: str,
        *,
        phase: StudioWorkflowPhase,
        actor_id: str = "",
        status: StudioWorkflowStatus | None = None,
    ) -> StudioWorkflowProjectState:
        state = self.get_or_create_project_workflow(project_id)
        state.current_phase = phase
        if status is not None:
            state.workflow_status = status
        state.updated_at = _now()
        self._storage_ref().save_studio_workflow_project_state(state)
        self._event(
            project_id=project_id,
            event_type="phase_updated",
            actor_id=actor_id,
            target_type="workflow_phase",
            target_id=phase.value,
            message=f"Workflow phase updated to {phase.value}.",
            details={"workflow_status": state.workflow_status.value},
        )
        return state

    def _migrate_legacy_collaboration_once(self, state: StudioWorkflowProjectState) -> None:
        if state.metadata.get("legacy_collaboration_migrated"):
            return
        try:
            project = self._project_store_ref().get_project(state.project_id)
        except Exception:
            project = None
        if not isinstance(project, dict):
            state.metadata["legacy_collaboration_migrated"] = True
            state.updated_at = _now()
            self._storage_ref().save_studio_workflow_project_state(state)
            return

        collaboration = project.get("collaboration") if isinstance(project.get("collaboration"), dict) else {}
        for member in collaboration.get("members") or []:
            if not isinstance(member, dict):
                continue
            actor_id = str(member.get("user_id") or "").strip()
            if not actor_id:
                continue
            self.upsert_collaborator(
                state.project_id,
                StudioCollaboratorUpsert(
                    actor_id=actor_id,
                    display_name=str(member.get("display_name") or actor_id),
                    role=self._normalize_role(member.get("role")),
                    metadata={"source": "legacy_collaboration"},
                ),
                emit_event=False,
            )

        for comment in collaboration.get("live_comments") or []:
            if not isinstance(comment, dict):
                continue
            text = str(comment.get("comment") or "").strip()
            actor_id = str(comment.get("user_id") or "legacy").strip() or "legacy"
            if not text:
                continue
            self._storage_ref().save_studio_workflow_comment(
                StudioWorkflowComment(
                    comment_id=_id("swc_legacy"),
                    project_id=state.project_id,
                    target_type="room",
                    target_id=str(comment.get("room") or collaboration.get("shared_room") or "lobby"),
                    actor_id=actor_id,
                    actor_role=self._normalize_role(comment.get("role")),
                    display_name=str(comment.get("display_name") or actor_id),
                    body=text,
                    metadata={"source": "legacy_collaboration", "legacy_created_at": comment.get("created_at")},
                    created_at=str(comment.get("created_at") or _now()),
                    updated_at=str(comment.get("created_at") or _now()),
                )
            )

        for vote in collaboration.get("approval_votes") or []:
            if not isinstance(vote, dict):
                continue
            actor_id = str(vote.get("user_id") or "legacy").strip() or "legacy"
            scene_id = str(vote.get("scene_id") or "").strip() or "unknown_scene"
            vote_value = str(vote.get("vote") or "").strip()
            if not vote_value:
                continue
            self._storage_ref().save_studio_workflow_comment(
                StudioWorkflowComment(
                    comment_id=_id("swc_vote"),
                    project_id=state.project_id,
                    target_type="scene",
                    target_id=scene_id,
                    actor_id=actor_id,
                    actor_role=self._normalize_role(vote.get("role")),
                    display_name=str(vote.get("display_name") or actor_id),
                    body=f"Legacy approval vote: {vote_value}",
                    metadata={"source": "legacy_approval_vote", "vote": vote_value},
                    created_at=str(vote.get("updated_at") or _now()),
                    updated_at=str(vote.get("updated_at") or _now()),
                )
            )

        state.metadata["legacy_collaboration_migrated"] = True
        state.updated_at = _now()
        self._storage_ref().save_studio_workflow_project_state(state)
        self._event(
            project_id=state.project_id,
            event_type="legacy_collaboration_migrated",
            message="Legacy collaboration projection migrated into canonical workflow records.",
        )

    def _normalize_role(self, role: Any) -> StudioCollaboratorRole:
        raw = str(role or "").strip().lower()
        aliases = {"producer": "producer", "director": "director", "editor": "editor", "reviewer": "reviewer"}
        raw = aliases.get(raw, raw)
        try:
            return StudioCollaboratorRole(raw)
        except ValueError:
            return StudioCollaboratorRole.REVIEWER

    def upsert_collaborator(
        self,
        project_id: str,
        payload: StudioCollaboratorUpsert,
        *,
        emit_event: bool = True,
    ) -> StudioCollaborator:
        self._require_project(project_id)
        actor_id = payload.actor_id.strip()
        if not actor_id:
            raise ValidationError("actor_id is required")
        now = _now()
        existing = self._storage_ref().get_studio_collaborator(project_id, actor_id)
        collaborator = StudioCollaborator(
            collaborator_id=existing.collaborator_id if existing else _id("sw_col"),
            project_id=project_id,
            actor_id=actor_id,
            display_name=payload.display_name.strip() or actor_id,
            role=payload.role,
            permission_scope=payload.permission_scope or "project",
            status=payload.status or "active",
            last_seen_at=now,
            metadata=payload.metadata or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._storage_ref().upsert_studio_collaborator(collaborator)
        if emit_event:
            self._event(
                project_id=project_id,
                event_type="collaborator_joined",
                actor_id=actor_id,
                target_type="collaborator",
                target_id=actor_id,
                message=f"{collaborator.display_name} joined the professional workflow.",
                details={"role": collaborator.role.value},
            )
        return collaborator

    def list_collaborators(self, project_id: str, limit: int = 200) -> list[StudioCollaborator]:
        self.get_or_create_project_workflow(project_id)
        return self._storage_ref().list_studio_collaborators(project_id, limit=limit)

    def create_artifact_version(
        self,
        project_id: str,
        payload: StudioArtifactVersionCreate,
    ) -> StudioArtifactVersion:
        timer = start_timer()
        self._require_project(project_id)
        artifact_id = payload.artifact_id.strip()
        if not artifact_id:
            raise ValidationError("artifact_id is required")
        version_number = self._storage_ref().next_studio_artifact_version_number(
            project_id,
            payload.artifact_type.value,
            artifact_id,
        )
        now = _now()
        version = StudioArtifactVersion(
            version_id=_id("sw_ver"),
            project_id=project_id,
            artifact_type=payload.artifact_type,
            artifact_id=artifact_id,
            version_number=version_number,
            status=payload.status,
            title=payload.title,
            summary=payload.summary,
            source_version_id=payload.source_version_id,
            canonical_ref_type=payload.canonical_ref_type,
            canonical_ref_id=payload.canonical_ref_id,
            snapshot=payload.snapshot,
            evidence=payload.evidence,
            created_by=payload.created_by,
            created_at=now,
            updated_at=now,
        )
        self._storage_ref().save_studio_artifact_version(version)
        if payload.source_version_id:
            self._storage_ref().save_studio_version_lineage(
                StudioVersionLineage(
                    lineage_id=_id("sw_lin"),
                    project_id=project_id,
                    parent_version_id=payload.source_version_id,
                    child_version_id=version.version_id,
                    relationship_type=StudioVersionRelationshipType.REVISION,
                    change_summary=payload.summary or "Version created from prior version.",
                )
            )
        state = self.get_or_create_project_workflow(project_id)
        state.active_version_id = version.version_id
        state.updated_at = now
        self._storage_ref().save_studio_workflow_project_state(state)
        self._event(
            project_id=project_id,
            event_type="version_created",
            actor_id=payload.created_by,
            target_type=version.artifact_type.value,
            target_id=version.artifact_id,
            version_id=version.version_id,
            message=f"Created {version.artifact_type.value} version {version.version_number}.",
        )
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="internal",
            stage="create_artifact_version",
            duration_ms=elapsed_ms(timer),
            extra={"version_id": version.version_id},
        )
        return version

    def list_artifact_versions(
        self,
        project_id: str,
        *,
        artifact_type: str | None = None,
        artifact_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[StudioArtifactVersion]:
        self.get_or_create_project_workflow(project_id)
        return self._storage_ref().list_studio_artifact_versions(
            project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            status=status,
            limit=limit,
        )

    def get_artifact_version_with_lineage(self, project_id: str, version_id: str) -> dict[str, Any]:
        self.get_or_create_project_workflow(project_id)
        version = self._storage_ref().get_studio_artifact_version(version_id)
        if version is None or version.project_id != project_id:
            raise ValidationError("Version not found")
        lineage = self._storage_ref().list_studio_version_lineage(version_id)
        return {
            "version": version.model_dump(mode="json"),
            "lineage": [row.model_dump(mode="json") for row in lineage],
        }

    def create_approval_gate(self, project_id: str, payload: StudioApprovalGateCreate) -> StudioApprovalGate:
        self._require_project(project_id)
        if not payload.target_type.strip() or not payload.target_id.strip():
            raise ValidationError("target_type and target_id are required")
        if payload.version_id and self._storage_ref().get_studio_artifact_version(payload.version_id) is None:
            raise ValidationError("version_id not found")
        existing = self._storage_ref().list_studio_approval_gates(
            project_id=project_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            gate_type=payload.gate_type.value,
            limit=20,
        )
        for gate in existing:
            if gate.status.value in _ACTIVE_GATE_STATUSES:
                return gate
        now = _now()
        gate = StudioApprovalGate(
            gate_id=_id("sw_gate"),
            project_id=project_id,
            gate_type=payload.gate_type,
            target_type=payload.target_type.strip(),
            target_id=payload.target_id.strip(),
            version_id=payload.version_id,
            status=StudioApprovalGateStatus.PENDING,
            required_role=payload.required_role,
            required_decision=payload.required_decision,
            queue_item_id=payload.queue_item_id,
            manual_dependency_id=payload.manual_dependency_id or payload.gate_type.value + ":" + payload.target_id.strip(),
            evidence_policy=payload.evidence_policy,
            opened_by=payload.opened_by,
            created_at=now,
            updated_at=now,
        )
        gate = self.evaluate_gate(project_id, gate, persist=False)
        self._storage_ref().save_studio_approval_gate(gate)
        state = self.get_or_create_project_workflow(project_id)
        state.active_gate_id = gate.gate_id
        state.workflow_status = StudioWorkflowStatus.WAITING_CREATOR
        state.updated_at = now
        self._storage_ref().save_studio_workflow_project_state(state)
        self._event(
            project_id=project_id,
            event_type="gate_created",
            actor_id=payload.opened_by,
            target_type=gate.target_type,
            target_id=gate.target_id,
            version_id=gate.version_id,
            gate_id=gate.gate_id,
            message=f"Opened {gate.gate_type.value} gate.",
        )
        return gate

    def list_approval_gates(
        self,
        project_id: str,
        *,
        status: str | None = None,
        gate_type: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
    ) -> list[StudioApprovalGate]:
        self.get_or_create_project_workflow(project_id)
        return self._storage_ref().list_studio_approval_gates(
            project_id,
            status=status,
            gate_type=gate_type,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
        )

    def get_approval_gate_with_decisions(self, project_id: str, gate_id: str) -> dict[str, Any]:
        self.get_or_create_project_workflow(project_id)
        gate = self._storage_ref().get_studio_approval_gate(gate_id)
        if gate is None or gate.project_id != project_id:
            raise ValidationError("Approval gate not found")
        decisions = self._storage_ref().list_studio_approval_decisions(project_id, gate_id=gate_id)
        return {
            "gate": gate.model_dump(mode="json"),
            "decisions": [decision.model_dump(mode="json") for decision in decisions],
        }

    def evaluate_gate(
        self,
        project_id: str,
        gate_or_id: StudioApprovalGate | str,
        *,
        persist: bool = True,
    ) -> StudioApprovalGate:
        self._require_project(project_id)
        gate = gate_or_id if isinstance(gate_or_id, StudioApprovalGate) else self._storage_ref().get_studio_approval_gate(gate_or_id)
        if gate is None:
            raise ValidationError("Approval gate not found")
        evidence: list[StudioWorkflowEvidenceRef] = []
        blockers: list[str] = []
        warnings: list[str] = []

        try:
            decision_gate = self._decision_gate_ref().evaluate_project_gate(project_id)
            evidence.append(
                StudioWorkflowEvidenceRef(
                    source_type="studio_decision_gate",
                    source_id=project_id,
                    source_label="Studio Decision Gate",
                    field_path="gate_status",
                    observed_value=getattr(decision_gate, "gate_status", "unknown"),
                    metadata=_as_dict(decision_gate),
                )
            )
            for blocker in getattr(decision_gate, "blockers", []) or []:
                warnings.append(str(blocker))
        except Exception as exc:
            warnings.append(f"Studio decision gate unavailable: {exc}")

        if gate.version_id:
            version = self._storage_ref().get_studio_artifact_version(gate.version_id)
            if version is None:
                blockers.append("Target version no longer exists.")
            else:
                evidence.append(
                    StudioWorkflowEvidenceRef(
                        source_type="studio_artifact_version",
                        source_id=version.version_id,
                        source_label=f"{version.artifact_type.value} v{version.version_number}",
                        field_path="status",
                        observed_value=version.status.value,
                    )
                )

        if gate.queue_item_id:
            try:
                queue_item = self._storage_ref().get_queue_item(gate.queue_item_id)
            except Exception:
                queue_item = None
            if queue_item is None:
                warnings.append("Linked queue item is unavailable.")
            else:
                evidence.append(
                    StudioWorkflowEvidenceRef(
                        source_type="production_queue_item",
                        source_id=queue_item.queue_item_id,
                        source_label="Production Queue Item",
                        field_path="status",
                        observed_value=queue_item.status.value,
                        metadata=queue_item.model_dump(mode="json"),
                    )
                )

        if gate.gate_type in {StudioApprovalGateType.PACKAGE_ACCEPTANCE, StudioApprovalGateType.DELIVERY_APPROVAL}:
            guard = self._package_guard(gate)
            evidence.extend(guard.get("evidence", []))
            if not guard.get("allowed"):
                blockers.append(str(guard.get("reason") or "Production acceptance is not ready."))

        status = StudioApprovalGateStatus.READY if not blockers else StudioApprovalGateStatus.BLOCKED
        if gate.status in {
            StudioApprovalGateStatus.APPROVED,
            StudioApprovalGateStatus.CHANGES_REQUESTED,
            StudioApprovalGateStatus.REJECTED,
            StudioApprovalGateStatus.CANCELLED,
            StudioApprovalGateStatus.SUPERSEDED,
        }:
            status = gate.status
        gate.status = status
        gate.latest_evaluation = {
            "evaluated_at": _now(),
            "blockers": blockers,
            "warnings": warnings[:10],
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "advisory_only": True,
        }
        gate.updated_at = _now()
        if persist:
            self._storage_ref().save_studio_approval_gate(gate)
            self._event(
                project_id=project_id,
                event_type="gate_evaluated",
                target_type=gate.target_type,
                target_id=gate.target_id,
                version_id=gate.version_id,
                gate_id=gate.gate_id,
                message=f"Gate evaluated as {gate.status.value}.",
                details=gate.latest_evaluation,
            )
        return gate

    def _package_guard(self, gate: StudioApprovalGate) -> dict[str, Any]:
        package_id = gate.target_id if gate.target_type in {"final_package", "package"} else ""
        if not package_id and gate.version_id:
            version = self._storage_ref().get_studio_artifact_version(gate.version_id)
            if version:
                package_id = version.canonical_ref_id or version.artifact_id
        if not package_id:
            return {"allowed": False, "reason": "Package target is missing.", "evidence": []}
        guard = self._acceptance_ref().evaluate_package_approval_guard(package_id, desired_status="approved")
        refs = []
        for ref in getattr(guard, "evidence", []) or []:
            refs.append(StudioWorkflowEvidenceRef(**_as_dict(ref)))
        refs.append(
            StudioWorkflowEvidenceRef(
                source_type="production_acceptance_guard",
                source_id=package_id,
                source_label="Production Acceptance Guard",
                field_path="allowed",
                observed_value=bool(getattr(guard, "allowed", False)),
                metadata=_as_dict(guard),
            )
        )
        return {"allowed": bool(getattr(guard, "allowed", False)), "reason": getattr(guard, "reason", ""), "evidence": refs}

    def _role_allowed(self, actor_role: StudioCollaboratorRole, required_role: StudioCollaboratorRole) -> bool:
        if actor_role == StudioCollaboratorRole.AI_ADVISORY:
            return False
        return _ROLE_RANK.get(actor_role.value, 0) >= _ROLE_RANK.get(required_role.value, 999)

    def record_approval_decision(
        self,
        project_id: str,
        gate_id: str,
        payload: StudioApprovalDecisionCreate,
    ) -> StudioApprovalDecision:
        timer = start_timer()
        self._require_project(project_id)
        gate = self._storage_ref().get_studio_approval_gate(gate_id)
        if gate is None:
            raise ValidationError("Approval gate not found")
        actor_id = payload.actor_id.strip()
        if not actor_id:
            raise ValidationError("actor_id is required")
        if payload.actor_role == StudioCollaboratorRole.AI_ADVISORY and payload.decision != StudioApprovalDecisionValue.ABSTAIN:
            raise ValidationError("AI advisory participants cannot close approval gates")
        if payload.decision in {
            StudioApprovalDecisionValue.APPROVE,
            StudioApprovalDecisionValue.REQUEST_CHANGES,
            StudioApprovalDecisionValue.REJECT,
            StudioApprovalDecisionValue.OVERRIDE,
            StudioApprovalDecisionValue.CANCEL,
        } and not self._role_allowed(payload.actor_role, gate.required_role):
            raise ValidationError(f"{payload.actor_role.value} cannot decide a gate requiring {gate.required_role.value}")

        gate = self.evaluate_gate(project_id, gate.gate_id)
        if payload.decision == StudioApprovalDecisionValue.APPROVE and gate.status == StudioApprovalGateStatus.BLOCKED:
            raise StateError((gate.latest_evaluation.get("blockers") or ["Gate is blocked."])[0])

        evidence = list(payload.evidence)
        for item in gate.latest_evaluation.get("evidence") or []:
            if isinstance(item, dict):
                evidence.append(StudioWorkflowEvidenceRef(**item))

        decision = StudioApprovalDecision(
            decision_id=_id("sw_dec"),
            project_id=project_id,
            gate_id=gate.gate_id,
            version_id=gate.version_id,
            actor_id=actor_id,
            actor_role=payload.actor_role,
            decision=payload.decision,
            rationale=payload.rationale,
            notes=payload.notes,
            evidence=evidence,
            created_at=_now(),
        )
        self._storage_ref().save_studio_approval_decision(decision)

        if payload.decision == StudioApprovalDecisionValue.APPROVE:
            self._approve_gate(gate, decision, release_queue=payload.release_queue)
        elif payload.decision == StudioApprovalDecisionValue.REQUEST_CHANGES:
            self._request_changes(gate, decision, create_revision_task=payload.create_revision_task)
        elif payload.decision == StudioApprovalDecisionValue.REJECT:
            self._close_gate(gate, decision, StudioApprovalGateStatus.REJECTED)
        elif payload.decision == StudioApprovalDecisionValue.CANCEL:
            self._close_gate(gate, decision, StudioApprovalGateStatus.CANCELLED)

        self._event(
            project_id=project_id,
            event_type="decision_recorded",
            actor_id=actor_id,
            target_type=gate.target_type,
            target_id=gate.target_id,
            version_id=gate.version_id,
            gate_id=gate.gate_id,
            decision_id=decision.decision_id,
            message=f"{payload.actor_role.value} recorded {payload.decision.value}.",
            details={"rationale": payload.rationale, "notes": payload.notes},
        )
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="internal",
            stage="record_approval_decision",
            duration_ms=elapsed_ms(timer),
            extra={"gate_id": gate.gate_id, "decision": payload.decision.value},
        )
        return decision

    def _approve_gate(self, gate: StudioApprovalGate, decision: StudioApprovalDecision, *, release_queue: bool) -> None:
        now = _now()
        gate.status = StudioApprovalGateStatus.APPROVED
        gate.closed_by = decision.actor_id
        gate.closed_at = now
        gate.updated_at = now
        self._storage_ref().save_studio_approval_gate(gate)
        if gate.version_id:
            version = self._storage_ref().get_studio_artifact_version(gate.version_id)
            if version:
                version.status = StudioArtifactVersionStatus.APPROVED
                version.approved_by = decision.actor_id
                version.approved_at = now
                version.updated_at = now
                self._storage_ref().save_studio_artifact_version(version)
        if release_queue:
            released = self._storage_ref().satisfy_manual_queue_dependencies(
                gate.manual_dependency_id or gate.gate_id,
                reason=f"Released by workflow decision {decision.decision_id}",
            )
            try:
                released += self._storage_ref().satisfy_manual_queue_dependencies(
                    gate.gate_id,
                    reason=f"Released by workflow decision {decision.decision_id}",
                )
            except Exception:
                pass
            if released:
                try:
                    self._queue_ref().refresh_waiting_dependencies(limit=100)
                except Exception as exc:
                    logger.warning("Queue dependency refresh failed after gate approval: %s", exc)
                self._event(
                    project_id=gate.project_id,
                    event_type="queue_dependency_released",
                    actor_id=decision.actor_id,
                    target_type=gate.target_type,
                    target_id=gate.target_id,
                    version_id=gate.version_id,
                    gate_id=gate.gate_id,
                    decision_id=decision.decision_id,
                    message=f"Released {released} manual queue dependency record(s).",
                )
        if gate.gate_type == StudioApprovalGateType.MEMORY_DECISION_SAVE:
            self._save_explicit_creative_memory(gate, decision)
        self._project_gate_projection(gate, decision)

    def _save_explicit_creative_memory(self, gate: StudioApprovalGate, decision: StudioApprovalDecision) -> None:
        memory_data = gate.evidence_policy.get("memory_data") if isinstance(gate.evidence_policy, dict) else None
        if not isinstance(memory_data, dict):
            version = self._storage_ref().get_studio_artifact_version(gate.version_id) if gate.version_id else None
            snapshot = version.snapshot if version is not None and isinstance(version.snapshot, dict) else {}
            memory_data = snapshot.get("memory_data") if isinstance(snapshot.get("memory_data"), dict) else {}
        if not memory_data:
            self._event(
                project_id=gate.project_id,
                event_type="memory_save_skipped",
                actor_id=decision.actor_id,
                target_type=gate.target_type,
                target_id=gate.target_id,
                version_id=gate.version_id,
                gate_id=gate.gate_id,
                decision_id=decision.decision_id,
                message="Memory decision gate approved without memory payload.",
            )
            return
        memory = self._project_store_ref().save_creative_memory(gate.project_id, memory_data)
        self._event(
            project_id=gate.project_id,
            event_type="creative_memory_saved",
            actor_id=decision.actor_id,
            target_type=gate.target_type,
            target_id=gate.target_id,
            version_id=gate.version_id,
            gate_id=gate.gate_id,
            decision_id=decision.decision_id,
            message="Explicit creative decision saved to project memory.",
            details={"memory_id": memory.get("memory_id", ""), "decision_type": memory.get("decision_type", "")},
        )

    def _request_changes(
        self,
        gate: StudioApprovalGate,
        decision: StudioApprovalDecision,
        *,
        create_revision_task: bool,
    ) -> None:
        now = _now()
        gate.status = StudioApprovalGateStatus.CHANGES_REQUESTED
        gate.closed_by = decision.actor_id
        gate.closed_at = now
        gate.updated_at = now
        self._storage_ref().save_studio_approval_gate(gate)
        if gate.version_id:
            version = self._storage_ref().get_studio_artifact_version(gate.version_id)
            if version:
                version.status = StudioArtifactVersionStatus.CHANGES_REQUESTED
                version.updated_at = now
                self._storage_ref().save_studio_artifact_version(version)
        if create_revision_task:
            task = StudioWorkflowTask(
                workflow_task_id=_id("sw_task"),
                project_id=gate.project_id,
                title=f"Revise {gate.target_type} {gate.target_id}",
                task_type="revision",
                target_type=gate.target_type,
                target_id=gate.target_id,
                version_id=gate.version_id,
                assignee_actor_id="",
                status=StudioWorkflowTaskStatus.OPEN,
                priority="normal",
                metadata={"decision_id": decision.decision_id, "notes": decision.notes},
            )
            self._storage_ref().save_studio_workflow_task(task)
        self._project_gate_projection(gate, decision)

    def _close_gate(
        self,
        gate: StudioApprovalGate,
        decision: StudioApprovalDecision,
        status: StudioApprovalGateStatus,
    ) -> None:
        gate.status = status
        gate.closed_by = decision.actor_id
        gate.closed_at = _now()
        gate.updated_at = gate.closed_at
        self._storage_ref().save_studio_approval_gate(gate)
        self._project_gate_projection(gate, decision)

    def _project_gate_projection(self, gate: StudioApprovalGate, decision: StudioApprovalDecision) -> None:
        try:
            project_store = self._project_store_ref()
            project = project_store.get_project(gate.project_id)
            if not isinstance(project, dict):
                return
            updates: dict[str, Any] = {}
            if gate.target_type == "scene" or gate.gate_type in {
                StudioApprovalGateType.SCENE_REVIEW,
                StudioApprovalGateType.SCENE_CUT_APPROVAL,
            }:
                scene_id = gate.target_id
                reviewed = [str(v) for v in project.get("reviewed_scenes", []) if str(v).strip()]
                approved = [str(v) for v in project.get("approved_scenes", []) if str(v).strip()]
                status_map = project.get("scene_review_status") if isinstance(project.get("scene_review_status"), dict) else {}
                if scene_id not in reviewed:
                    reviewed.append(scene_id)
                if decision.decision == StudioApprovalDecisionValue.APPROVE:
                    if scene_id not in approved:
                        approved.append(scene_id)
                    status_map[scene_id] = "approved"
                elif decision.decision == StudioApprovalDecisionValue.REQUEST_CHANGES:
                    status_map[scene_id] = "changes_requested"
                elif decision.decision == StudioApprovalDecisionValue.REJECT:
                    status_map[scene_id] = "rejected"
                updates.update(
                    {
                        "reviewed_scenes": reviewed,
                        "approved_scenes": approved,
                        "scene_review_status": status_map,
                    }
                )
            if gate.gate_type == StudioApprovalGateType.FILM_CUT_APPROVAL and decision.decision == StudioApprovalDecisionValue.APPROVE:
                film_cut = project.get("film_cut") if isinstance(project.get("film_cut"), dict) else {}
                film_cut["approved_version_id"] = gate.version_id or ""
                film_cut["approved_at"] = decision.created_at
                film_cut["approved_by"] = decision.actor_id
                updates["film_cut"] = film_cut
            if updates:
                project_store.update_project(gate.project_id, updates)
                self._event(
                    project_id=gate.project_id,
                    event_type="projection_updated",
                    actor_id=decision.actor_id,
                    target_type=gate.target_type,
                    target_id=gate.target_id,
                    version_id=gate.version_id,
                    gate_id=gate.gate_id,
                    decision_id=decision.decision_id,
                    message="Updated legacy project workflow projection.",
                    details={"fields": sorted(updates.keys())},
                )
        except Exception as exc:
            logger.warning("Workflow projection failed for %s: %s", gate.project_id, exc)
            self._event(
                project_id=gate.project_id,
                event_type="projection_failed",
                target_type=gate.target_type,
                target_id=gate.target_id,
                version_id=gate.version_id,
                gate_id=gate.gate_id,
                decision_id=decision.decision_id,
                message="Legacy project projection failed.",
                details={"error": str(exc)},
            )

    def post_comment(self, project_id: str, payload: StudioWorkflowCommentCreate) -> StudioWorkflowComment:
        self._require_project(project_id)
        body = payload.body.strip()
        if not body:
            raise ValidationError("Comment body is required")
        comment = StudioWorkflowComment(
            comment_id=_id("swc"),
            project_id=project_id,
            target_type=payload.target_type.strip(),
            target_id=payload.target_id.strip(),
            version_id=payload.version_id,
            parent_comment_id=payload.parent_comment_id,
            actor_id=payload.actor_id.strip() or "unknown",
            actor_role=payload.actor_role,
            display_name=payload.display_name.strip() or payload.actor_id.strip() or "Collaborator",
            body=body,
            metadata=payload.metadata,
            created_at=_now(),
            updated_at=_now(),
        )
        if not comment.target_type or not comment.target_id:
            raise ValidationError("target_type and target_id are required")
        self._storage_ref().save_studio_workflow_comment(comment)
        self._event(
            project_id=project_id,
            event_type="comment_posted",
            actor_id=comment.actor_id,
            target_type=comment.target_type,
            target_id=comment.target_id,
            version_id=comment.version_id,
            message="Workflow comment posted.",
        )
        return comment

    def list_comments(
        self,
        project_id: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        version_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[StudioWorkflowComment]:
        self.get_or_create_project_workflow(project_id)
        return self._storage_ref().list_studio_workflow_comments(
            project_id,
            target_type=target_type,
            target_id=target_id,
            version_id=version_id,
            status=status,
            limit=limit,
        )

    def resolve_comment(self, project_id: str, comment_id: str, actor_id: str) -> StudioWorkflowComment:
        self._require_project(project_id)
        matches = self._storage_ref().list_studio_workflow_comments(project_id, limit=200)
        comment = next((row for row in matches if row.comment_id == comment_id), None)
        if comment is None:
            raise ValidationError("Comment not found")
        comment.status = StudioWorkflowCommentStatus.RESOLVED
        comment.resolved_by = actor_id.strip() or "unknown"
        comment.resolved_at = _now()
        comment.updated_at = comment.resolved_at
        self._storage_ref().save_studio_workflow_comment(comment)
        self._event(
            project_id=project_id,
            event_type="comment_resolved",
            actor_id=comment.resolved_by,
            target_type=comment.target_type,
            target_id=comment.target_id,
            version_id=comment.version_id,
            message="Workflow comment resolved.",
        )
        return comment

    def workflow_summary(self, project_id: str) -> StudioWorkflowSummary:
        state = self.get_or_create_project_workflow(project_id)
        storage = self._storage_ref()
        active_gates = [
            gate
            for gate in storage.list_studio_approval_gates(project_id, limit=50)
            if gate.status.value in _ACTIVE_GATE_STATUSES
        ]
        active_versions = storage.list_studio_artifact_versions(project_id, limit=50)
        open_tasks = storage.list_studio_workflow_tasks(project_id, status=StudioWorkflowTaskStatus.OPEN.value, limit=50)
        recent_events = storage.list_studio_workflow_events(project_id, limit=50)
        return StudioWorkflowSummary(
            project_state=state,
            collaborators=storage.list_studio_collaborators(project_id, limit=200),
            active_gates=active_gates,
            active_versions=active_versions,
            open_tasks=open_tasks,
            recent_events=recent_events,
            legacy_projection=self._legacy_projection(project_id),
        )

    def list_events(
        self,
        project_id: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        gate_id: str | None = None,
        version_id: str | None = None,
        limit: int = 50,
    ) -> list[StudioWorkflowEvent]:
        self.get_or_create_project_workflow(project_id)
        return self._storage_ref().list_studio_workflow_events(
            project_id,
            target_type=target_type,
            target_id=target_id,
            gate_id=gate_id,
            version_id=version_id,
            limit=limit,
        )

    def list_tasks(self, project_id: str, *, status: str | None = None, limit: int = 50) -> list[StudioWorkflowTask]:
        self.get_or_create_project_workflow(project_id)
        return self._storage_ref().list_studio_workflow_tasks(project_id, status=status, limit=limit)

    def compatibility_projection(self, project_id: str) -> dict[str, Any]:
        self.get_or_create_project_workflow(project_id)
        return self._legacy_projection(project_id)

    def _legacy_projection(self, project_id: str) -> dict[str, Any]:
        try:
            project = self._project_store_ref().get_project(project_id)
        except Exception:
            project = None
        if not isinstance(project, dict):
            return {}
        return {
            "approved_scenes": project.get("approved_scenes", []),
            "reviewed_scenes": project.get("reviewed_scenes", []),
            "scene_review_status": project.get("scene_review_status", {}),
            "film_cut": project.get("film_cut", {}),
            "collaboration": project.get("collaboration", {}),
        }


studio_workflow_service = StudioWorkflowService()
