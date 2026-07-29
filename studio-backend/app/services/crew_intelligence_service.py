from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.data.storage import get_storage
from app.models.crew import AGENT_CONFIGS, AgentRole
from app.models.crew_intelligence import (
    CrewCreatorAttentionItem,
    CrewDeliberationRecord,
    CrewDeliberationStatus,
    CrewDepartmentProfile,
    CrewDepartmentStatus,
    CrewEvidenceRef,
    CrewHandoffPacket,
    CrewHandoffStatus,
    CrewIntelligenceOverview,
    CrewMemoryRef,
    CrewReasoningRecord,
    CrewReasoningType,
    CrewRisk,
    CrewRoleContext,
    CrewSpineRef,
)

logger = logging.getLogger("studio-crew-intelligence")


class CrewIntelligenceError(Exception):
    pass


class CrewIntelligenceValidationError(CrewIntelligenceError):
    pass


class CrewIntelligenceStateError(CrewIntelligenceError):
    pass


class CrewIntelligenceService:
    """Durable, advisory intelligence layer for AI Film Studio departments."""

    _DISALLOWED_CREATOR_TEXT_PATTERNS = [
        re.compile(r"\bscore\s*:", re.IGNORECASE),
        re.compile(r"\brating\s*:", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bgreat job\b", re.IGNORECASE),
        re.compile(r"\blooks good overall\b", re.IGNORECASE),
        re.compile(r"\bobjectively worse\b", re.IGNORECASE),
    ]

    _VALID_HANDOFF_TRANSITIONS = {
        CrewHandoffStatus.CREATED: {
            CrewHandoffStatus.AWAITING_ACKNOWLEDGEMENT,
            CrewHandoffStatus.ACKNOWLEDGED,
            CrewHandoffStatus.CANCELLED,
            CrewHandoffStatus.REDIRECTED,
        },
        CrewHandoffStatus.AWAITING_ACKNOWLEDGEMENT: {
            CrewHandoffStatus.ACKNOWLEDGED,
            CrewHandoffStatus.FAILED,
            CrewHandoffStatus.CANCELLED,
            CrewHandoffStatus.REDIRECTED,
        },
        CrewHandoffStatus.ACKNOWLEDGED: {
            CrewHandoffStatus.IN_PROGRESS,
            CrewHandoffStatus.COMPLETED,
            CrewHandoffStatus.FAILED,
            CrewHandoffStatus.REDIRECTED,
        },
        CrewHandoffStatus.IN_PROGRESS: {
            CrewHandoffStatus.COMPLETED,
            CrewHandoffStatus.FAILED,
            CrewHandoffStatus.REDIRECTED,
        },
        CrewHandoffStatus.COMPLETED: set(),
        CrewHandoffStatus.FAILED: {CrewHandoffStatus.REDIRECTED, CrewHandoffStatus.CANCELLED},
        CrewHandoffStatus.REDIRECTED: {CrewHandoffStatus.AWAITING_ACKNOWLEDGEMENT, CrewHandoffStatus.CANCELLED},
        CrewHandoffStatus.CANCELLED: set(),
    }

    def __init__(
        self,
        storage=None,
        memory_service=None,
        spine_consumption_service=None,
    ):
        self._storage = storage
        self._memory_service = memory_service
        self._spine_consumption_service = spine_consumption_service

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    @property
    def memory_service(self):
        if self._memory_service is None:
            from app.services.memory import memory_service

            self._memory_service = memory_service
        return self._memory_service

    @property
    def spine_consumption_service(self):
        if self._spine_consumption_service is None:
            from app.services.spine_consumption_service import spine_consumption_service

            self._spine_consumption_service = spine_consumption_service
        return self._spine_consumption_service

    def _now_iso(self) -> str:
        return datetime.utcnow().isoformat()

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

    def _value(self, item: Any) -> Any:
        return getattr(item, "value", item)

    def _model_dict(self, item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        return dict(item)

    def _language_warnings(self, *texts: str) -> list[str]:
        warnings: list[str] = []
        for text in texts:
            if not text:
                continue
            for pattern in self._DISALLOWED_CREATOR_TEXT_PATTERNS:
                if pattern.search(text):
                    warnings.append(f"Creator-facing text contains prohibited pattern: {pattern.pattern}")
        return warnings

    def build_role_context(
        self,
        project_id: str,
        agent_role: AgentRole,
        film_id: str | None = None,
        scene_id: str | None = None,
    ) -> CrewRoleContext:
        memory_refs: list[CrewMemoryRef] = []
        spine_refs: list[CrewSpineRef] = []
        notes: list[str] = []
        canonical_sources = {
            "project_memory": False,
            "creative_spine": False,
        }

        try:
            memory_context = self.memory_service.get_context_for_agent(
                project_id=project_id,
                agent_role=agent_role.value,
                scene_id=scene_id,
            )
            canonical_sources["project_memory"] = bool(memory_context)
            if memory_context:
                memory_refs.append(
                    CrewMemoryRef(
                        memory_id=f"{project_id}:{scene_id or 'project'}:{agent_role.value}",
                        memory_type="role_context",
                        scope="project",
                        source_service="MemoryService",
                        scene_id=scene_id,
                        summary="Role-filtered project memory context was consulted.",
                    )
                )
        except Exception as exc:
            notes.append(f"Memory context unavailable: {exc}")

        if film_id:
            try:
                spine_context = self.spine_consumption_service.get_context_for_role(
                    film_id=film_id,
                    role=agent_role,
                    scene_id=scene_id,
                )
                constraints = spine_context.get("constraints") or []
                canonical_sources["creative_spine"] = True
                for constraint in constraints[:8]:
                    if hasattr(constraint, "to_dict"):
                        constraint_data = constraint.to_dict()
                    elif hasattr(constraint, "model_dump"):
                        constraint_data = constraint.model_dump(mode="json")
                    else:
                        constraint_data = dict(constraint)
                    spine_refs.append(
                        CrewSpineRef(
                            constraint_id=constraint_data.get("constraint_id", ""),
                            field_name=constraint_data.get("field_name", ""),
                            severity=constraint_data.get("severity", ""),
                            summary=constraint_data.get("description", ""),
                            applied=True,
                        )
                    )
            except Exception as exc:
                notes.append(f"Creative Spine context unavailable: {exc}")
        else:
            notes.append("Creative Spine lookup requires a film_id; project-level crew reasoning continues without it.")

        return CrewRoleContext(
            project_id=project_id,
            film_id=film_id,
            agent_role=agent_role,
            scene_id=scene_id,
            memory_available=canonical_sources["project_memory"],
            memory_refs=memory_refs,
            memory_summary="Role-filtered project memory context consulted." if memory_refs else "",
            spine_available=canonical_sources["creative_spine"],
            spine_refs=spine_refs,
            context_notes=notes,
            canonical_sources=canonical_sources,
        )

    def create_reasoning_record(
        self,
        *,
        project_id: str,
        agent_role: AgentRole,
        reasoning_type: CrewReasoningType,
        department_name: str | None = None,
        task_id: str | None = None,
        workflow_execution_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        package_id: str | None = None,
        observation: str = "",
        context_used: list[str] | None = None,
        inference: str = "",
        recommendation_summary: str = "",
        creator_note: str = "",
        evidence_refs: list[CrewEvidenceRef | dict[str, Any]] | None = None,
        memory_refs: list[CrewMemoryRef | dict[str, Any]] | None = None,
        spine_refs: list[CrewSpineRef | dict[str, Any]] | None = None,
        risks: list[CrewRisk | dict[str, Any]] | None = None,
        recommendations: list[Any] | None = None,
        downstream_departments: list[AgentRole] | None = None,
        requires_creator_decision: bool = False,
        escalation_reason: str | None = None,
        confidence_label: str = "emerging",
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CrewReasoningRecord:
        started = time.time()
        if not project_id:
            raise CrewIntelligenceValidationError("project_id is required")

        data = metadata.copy() if metadata else {}
        language_warnings = self._language_warnings(observation, inference, recommendation_summary, creator_note)
        if language_warnings:
            data["creator_language_warnings"] = language_warnings

        record = CrewReasoningRecord(
            reasoning_id=self._new_id("reasoning"),
            project_id=project_id,
            task_id=task_id,
            workflow_execution_id=workflow_execution_id,
            agent_role=agent_role,
            department_name=department_name or self._department_name(agent_role),
            reasoning_type=reasoning_type,
            scene_id=scene_id,
            shot_id=shot_id,
            asset_id=asset_id,
            render_job_id=render_job_id,
            package_id=package_id,
            observation=observation,
            context_used=context_used or [],
            inference=inference,
            recommendation_summary=recommendation_summary,
            creator_note=creator_note,
            evidence_refs=[ref if isinstance(ref, CrewEvidenceRef) else CrewEvidenceRef(**ref) for ref in (evidence_refs or [])],
            memory_refs=[ref if isinstance(ref, CrewMemoryRef) else CrewMemoryRef(**ref) for ref in (memory_refs or [])],
            spine_refs=[ref if isinstance(ref, CrewSpineRef) else CrewSpineRef(**ref) for ref in (spine_refs or [])],
            risks=[risk if isinstance(risk, CrewRisk) else CrewRisk(**risk) for risk in (risks or [])],
            recommendations=recommendations or [],
            downstream_departments=downstream_departments or [],
            requires_creator_decision=requires_creator_decision,
            escalation_reason=escalation_reason,
            confidence_label=confidence_label,
            advisory_only=True,
            trace_id=trace_id or self._new_id("trace"),
            created_at=self._now_iso(),
            metadata=data,
        )
        saved = self.storage.save_crew_reasoning_record(self._model_dict(record))
        logger.info(
            "crew_reasoning_created project_id=%s task_id=%s agent_role=%s reasoning_id=%s stage=crew_reasoning_create duration_ms=%s trace_id=%s",
            project_id,
            task_id,
            agent_role.value,
            record.reasoning_id,
            int((time.time() - started) * 1000),
            record.trace_id,
        )
        return CrewReasoningRecord(**saved)

    def list_reasoning_records(
        self,
        project_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrewReasoningRecord]:
        rows = self.storage.list_crew_reasoning_records(project_id, filters or {}, limit=limit, offset=offset)
        return [CrewReasoningRecord(**row) for row in rows]

    def get_reasoning_record(self, reasoning_id: str) -> CrewReasoningRecord | None:
        row = self.storage.get_crew_reasoning_record(reasoning_id)
        return CrewReasoningRecord(**row) if row else None

    def create_handoff(
        self,
        *,
        project_id: str,
        source_role: AgentRole,
        target_role: AgentRole,
        context_summary: str,
        source_task_id: str | None = None,
        target_task_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        asset_id: str | None = None,
        requirements: list[str] | None = None,
        open_questions: list[str] | None = None,
        evidence_refs: list[CrewEvidenceRef | dict[str, Any]] | None = None,
        risks: list[CrewRisk | dict[str, Any]] | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CrewHandoffPacket:
        if source_role == target_role:
            raise CrewIntelligenceValidationError("source_role and target_role must be different")
        now = self._now_iso()
        handoff = CrewHandoffPacket(
            handoff_id=self._new_id("handoff"),
            project_id=project_id,
            source_role=source_role,
            target_role=target_role,
            source_task_id=source_task_id,
            target_task_id=target_task_id,
            scene_id=scene_id,
            shot_id=shot_id,
            asset_id=asset_id,
            context_summary=context_summary,
            requirements=requirements or [],
            open_questions=open_questions or [],
            evidence_refs=[ref if isinstance(ref, CrewEvidenceRef) else CrewEvidenceRef(**ref) for ref in (evidence_refs or [])],
            risks=[risk if isinstance(risk, CrewRisk) else CrewRisk(**risk) for risk in (risks or [])],
            status=CrewHandoffStatus.AWAITING_ACKNOWLEDGEMENT,
            trace_id=trace_id or self._new_id("trace"),
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        return CrewHandoffPacket(**self.storage.save_crew_handoff_packet(self._model_dict(handoff)))

    def list_handoffs(
        self,
        project_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrewHandoffPacket]:
        rows = self.storage.list_crew_handoff_packets(project_id, filters or {}, limit=limit, offset=offset)
        return [CrewHandoffPacket(**row) for row in rows]

    def get_handoff(self, handoff_id: str) -> CrewHandoffPacket | None:
        row = self.storage.get_crew_handoff_packet(handoff_id)
        return CrewHandoffPacket(**row) if row else None

    def update_handoff_status(
        self,
        handoff_id: str,
        status: CrewHandoffStatus,
        actor_id: str | None = None,
        failed_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CrewHandoffPacket | None:
        current = self.get_handoff(handoff_id)
        if not current:
            return None
        if status not in self._VALID_HANDOFF_TRANSITIONS[current.status]:
            raise CrewIntelligenceStateError(f"Invalid handoff transition: {current.status.value} -> {status.value}")
        updates: dict[str, Any] = {
            "status": status.value,
            "updated_at": self._now_iso(),
            "metadata": {**current.metadata, **(metadata or {})},
        }
        if status == CrewHandoffStatus.ACKNOWLEDGED:
            updates["acknowledged_by"] = actor_id
            updates["acknowledged_at"] = self._now_iso()
        if status == CrewHandoffStatus.COMPLETED:
            updates["completed_at"] = self._now_iso()
        if status == CrewHandoffStatus.FAILED:
            updates["failed_reason"] = failed_reason or "Handoff failed without a detailed reason."
        saved = self.storage.update_crew_handoff_status(handoff_id, updates)
        return CrewHandoffPacket(**saved) if saved else None

    def create_deliberation(
        self,
        *,
        project_id: str,
        participating_roles: list[AgentRole],
        issue_summary: str,
        triggering_reasoning_ids: list[str] | None = None,
        triggering_task_ids: list[str] | None = None,
        points_of_agreement: list[str] | None = None,
        points_of_tension: list[str] | None = None,
        recommended_resolution: str = "",
        requires_creator_decision: bool = False,
        creator_question: str | None = None,
        scene_id: str | None = None,
        evidence_refs: list[CrewEvidenceRef | dict[str, Any]] | None = None,
        risks: list[CrewRisk | dict[str, Any]] | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CrewDeliberationRecord:
        if requires_creator_decision and not creator_question:
            raise CrewIntelligenceValidationError("creator_question is required when deliberation needs creator decision")
        now = self._now_iso()
        record = CrewDeliberationRecord(
            deliberation_id=self._new_id("deliberation"),
            project_id=project_id,
            scene_id=scene_id,
            participating_roles=participating_roles,
            triggering_reasoning_ids=triggering_reasoning_ids or [],
            triggering_task_ids=triggering_task_ids or [],
            issue_summary=issue_summary,
            points_of_agreement=points_of_agreement or [],
            points_of_tension=points_of_tension or [],
            evidence_refs=[ref if isinstance(ref, CrewEvidenceRef) else CrewEvidenceRef(**ref) for ref in (evidence_refs or [])],
            risks=[risk if isinstance(risk, CrewRisk) else CrewRisk(**risk) for risk in (risks or [])],
            recommended_resolution=recommended_resolution,
            requires_creator_decision=requires_creator_decision,
            creator_question=creator_question,
            status=CrewDeliberationStatus.NEEDS_CREATOR if requires_creator_decision else CrewDeliberationStatus.OPEN,
            trace_id=trace_id or self._new_id("trace"),
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        return CrewDeliberationRecord(**self.storage.save_crew_deliberation_record(self._model_dict(record)))

    def list_deliberations(
        self,
        project_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CrewDeliberationRecord]:
        rows = self.storage.list_crew_deliberation_records(project_id, filters or {}, limit=limit, offset=offset)
        return [CrewDeliberationRecord(**row) for row in rows]

    def get_deliberation(self, deliberation_id: str) -> CrewDeliberationRecord | None:
        row = self.storage.get_crew_deliberation_record(deliberation_id)
        return CrewDeliberationRecord(**row) if row else None

    def resolve_deliberation(
        self,
        deliberation_id: str,
        resolved_by: str,
        resolution_summary: str,
    ) -> CrewDeliberationRecord | None:
        current = self.get_deliberation(deliberation_id)
        if not current:
            return None
        data = self._model_dict(current)
        data.update(
            {
                "status": CrewDeliberationStatus.RESOLVED.value,
                "resolution_summary": resolution_summary,
                "resolved_by": resolved_by,
                "resolved_at": self._now_iso(),
                "updated_at": self._now_iso(),
            }
        )
        return CrewDeliberationRecord(**self.storage.save_crew_deliberation_record(data))

    def get_department_profiles(self, project_id: str | None = None) -> list[CrewDepartmentProfile]:
        return [self._profile_for_role(role) for role in AgentRole]

    def get_creator_attention(self, project_id: str) -> list[CrewCreatorAttentionItem]:
        items: list[CrewCreatorAttentionItem] = []
        reasoning = self.list_reasoning_records(
            project_id,
            filters={"requires_creator_decision": True, "status": "active"},
            limit=25,
        )
        for record in reasoning:
            items.append(
                CrewCreatorAttentionItem(
                    attention_id=f"attention:{record.reasoning_id}",
                    project_id=project_id,
                    source_type="reasoning",
                    source_id=record.reasoning_id,
                    agent_role=record.agent_role,
                    title=f"{record.department_name} needs your read",
                    summary=record.creator_note or record.recommendation_summary or record.observation,
                    recommended_action=record.escalation_reason or "Review the department recommendation.",
                    severity="needs_attention",
                    created_at=record.created_at,
                )
            )
        deliberations = self.list_deliberations(
            project_id,
            filters={"requires_creator_decision": True},
            limit=25,
        )
        for deliberation in deliberations:
            if deliberation.status not in {CrewDeliberationStatus.NEEDS_CREATOR, CrewDeliberationStatus.OPEN}:
                continue
            items.append(
                CrewCreatorAttentionItem(
                    attention_id=f"attention:{deliberation.deliberation_id}",
                    project_id=project_id,
                    source_type="deliberation",
                    source_id=deliberation.deliberation_id,
                    title="Crew deliberation needs your decision",
                    summary=deliberation.creator_question or deliberation.issue_summary,
                    recommended_action=deliberation.recommended_resolution,
                    severity="needs_attention",
                    created_at=deliberation.created_at,
                )
            )
        return items

    def get_project_overview(
        self,
        project_id: str,
        recent_limit: int = 10,
        handoff_limit: int = 10,
        deliberation_limit: int = 10,
    ) -> CrewIntelligenceOverview:
        recent_reasoning = self.list_reasoning_records(project_id, limit=recent_limit)
        active_handoffs = self.list_handoffs(
            project_id,
            filters={},
            limit=handoff_limit,
        )
        active_handoffs = [
            handoff
            for handoff in active_handoffs
            if handoff.status
            not in {CrewHandoffStatus.COMPLETED, CrewHandoffStatus.CANCELLED}
        ]
        open_deliberations = self.list_deliberations(project_id, limit=deliberation_limit)
        open_deliberations = [
            item
            for item in open_deliberations
            if item.status
            in {CrewDeliberationStatus.OPEN, CrewDeliberationStatus.NEEDS_CREATOR}
        ]
        attention = self.get_creator_attention(project_id)
        departments = self._department_statuses(
            project_id=project_id,
            recent_reasoning=recent_reasoning,
            active_handoffs=active_handoffs,
            attention=attention,
        )
        self._snapshot_department_statuses(project_id, departments)
        summary = self._overview_summary(recent_reasoning, active_handoffs, open_deliberations, attention)
        return CrewIntelligenceOverview(
            project_id=project_id,
            generated_at=self._now_iso(),
            departments=departments,
            recent_reasoning=recent_reasoning,
            active_handoffs=active_handoffs[:handoff_limit],
            open_deliberations=open_deliberations[:deliberation_limit],
            creator_attention=attention,
            summary=summary,
            canonical_sources={
                "crew_tasks": True,
                "crew_reasoning_records": True,
                "crew_handoffs": True,
                "crew_deliberations": True,
            },
        )

    def _snapshot_department_statuses(self, project_id: str, departments: list[CrewDepartmentStatus]) -> None:
        for department in departments:
            if department.state == "idle" and not department.last_reasoning_id:
                continue
            try:
                latest = self.storage.list_crew_department_status_snapshots(
                    project_id,
                    agent_role=department.agent_role.value,
                    limit=1,
                )
                if latest:
                    last = latest[0]
                    if (
                        last.get("state") == department.state
                        and last.get("current_task_id") == department.current_task_id
                        and last.get("last_reasoning_id") == department.last_reasoning_id
                        and int(last.get("active_handoff_count") or 0) == department.active_handoff_count
                        and bool(last.get("needs_creator_attention")) == department.needs_creator_attention
                    ):
                        continue
                self.storage.save_crew_department_status_snapshot(
                    {
                        "snapshot_id": self._new_id("crew-status"),
                        "project_id": project_id,
                        "agent_role": department.agent_role.value,
                        "department_name": department.department_name,
                        "state": department.state,
                        "current_task_id": department.current_task_id,
                        "current_activity": department.current_activity,
                        "last_reasoning_id": department.last_reasoning_id,
                        "active_handoff_count": department.active_handoff_count,
                        "unresolved_risk_count": department.unresolved_risk_count,
                        "needs_creator_attention": department.needs_creator_attention,
                        "created_at": self._now_iso(),
                        "metadata": {"source": "overview_derivation"},
                    }
                )
            except Exception as exc:
                logger.warning("crew_department_snapshot_failed project_id=%s agent_role=%s error=%s", project_id, department.agent_role.value, exc)

    def _department_statuses(
        self,
        project_id: str,
        recent_reasoning: list[CrewReasoningRecord],
        active_handoffs: list[CrewHandoffPacket],
        attention: list[CrewCreatorAttentionItem],
    ) -> list[CrewDepartmentStatus]:
        now = self._now_iso()
        statuses: list[CrewDepartmentStatus] = []
        for profile in self.get_department_profiles(project_id):
            latest = next((record for record in recent_reasoning if record.agent_role == profile.agent_role), None)
            handoff_count = sum(
                1
                for handoff in active_handoffs
                if handoff.source_role == profile.agent_role or handoff.target_role == profile.agent_role
            )
            attention_count = sum(1 for item in attention if item.agent_role == profile.agent_role)
            if attention_count:
                state = "needs_creator"
            elif handoff_count:
                state = "waiting"
            elif latest:
                state = "working" if latest.status == "active" else "idle"
            else:
                state = "idle"
            statuses.append(
                CrewDepartmentStatus(
                    agent_role=profile.agent_role,
                    department_name=profile.department_name,
                    state=state,
                    current_task_id=latest.task_id if latest else None,
                    current_activity=self._activity_for(profile.agent_role, latest),
                    last_reasoning_id=latest.reasoning_id if latest else None,
                    active_handoff_count=handoff_count,
                    unresolved_risk_count=sum(1 for risk in (latest.risks if latest else []) if risk.severity in {"needs_attention", "blocking"}),
                    needs_creator_attention=attention_count > 0,
                    last_updated_at=latest.created_at if latest else now,
                )
            )
        return statuses

    def _overview_summary(
        self,
        recent_reasoning: list[CrewReasoningRecord],
        active_handoffs: list[CrewHandoffPacket],
        open_deliberations: list[CrewDeliberationRecord],
        attention: list[CrewCreatorAttentionItem],
    ) -> str:
        if attention:
            return "The crew has surfaced decisions that need the creator's read before the next clean handoff."
        if open_deliberations:
            return "The crew is holding an open department deliberation with evidence ready for inspection."
        if active_handoffs:
            return "Department handoffs are active and carrying production context forward."
        if recent_reasoning:
            return "Crew intelligence is active with recent department reasoning available for inspection."
        return "Crew intelligence is ready; no department has produced new reasoning yet."

    def _department_name(self, role: AgentRole) -> str:
        return AGENT_CONFIGS.get(role, {}).get("name", role.value.replace("_", " ").title())

    def _activity_for(self, role: AgentRole, latest: CrewReasoningRecord | None) -> str:
        if latest and latest.recommendation_summary:
            return latest.recommendation_summary
        defaults = {
            AgentRole.PRODUCER: "Coordinating production attention.",
            AgentRole.RENDER_COORDINATOR: "Watching render readiness.",
            AgentRole.DIRECTOR: "Synthesizing crew signals.",
            AgentRole.SCRIPT_ANALYST: "Reading scene intent.",
            AgentRole.STORYBOARD_ARTIST: "Preparing visual handoff.",
            AgentRole.CINEMATOGRAPHER: "Checking visual language.",
            AgentRole.PRODUCTION_DESIGNER: "Checking environment, prop, and costume continuity.",
            AgentRole.COLORIST: "Checking look, palette, and grading continuity.",
            AgentRole.PROMPT_ENGINEER: "Preserving constraints for generation.",
            AgentRole.EDITOR: "Reading rhythm and transition pressure.",
            AgentRole.CONTINUITY_SUPERVISOR: "Checking continuity pressure.",
            AgentRole.MEMORY_ARCHIVIST: "Checking long-form memory.",
            AgentRole.QUALITY_REVIEWER: "Validating production output.",
            AgentRole.SYSTEM_ORCHESTRATOR: "Managing workflow handoffs.",
        }
        return defaults.get(role, "Standing by.")

    def _profile_for_role(self, role: AgentRole) -> CrewDepartmentProfile:
        config = AGENT_CONFIGS.get(role, {})
        partners = {
            AgentRole.SCRIPT_ANALYST: [AgentRole.STORYBOARD_ARTIST, AgentRole.MEMORY_ARCHIVIST],
            AgentRole.STORYBOARD_ARTIST: [AgentRole.CINEMATOGRAPHER, AgentRole.PRODUCTION_DESIGNER, AgentRole.PROMPT_ENGINEER],
            AgentRole.CINEMATOGRAPHER: [AgentRole.PRODUCTION_DESIGNER, AgentRole.COLORIST, AgentRole.PROMPT_ENGINEER, AgentRole.CONTINUITY_SUPERVISOR],
            AgentRole.PRODUCTION_DESIGNER: [AgentRole.CINEMATOGRAPHER, AgentRole.COLORIST, AgentRole.CONTINUITY_SUPERVISOR, AgentRole.PROMPT_ENGINEER],
            AgentRole.COLORIST: [AgentRole.CINEMATOGRAPHER, AgentRole.PRODUCTION_DESIGNER, AgentRole.EDITOR, AgentRole.CONTINUITY_SUPERVISOR],
            AgentRole.PROMPT_ENGINEER: [AgentRole.RENDER_COORDINATOR, AgentRole.CONTINUITY_SUPERVISOR],
            AgentRole.RENDER_COORDINATOR: [AgentRole.QUALITY_REVIEWER, AgentRole.PRODUCER],
            AgentRole.QUALITY_REVIEWER: [AgentRole.CONTINUITY_SUPERVISOR, AgentRole.EDITOR],
            AgentRole.EDITOR: [AgentRole.MEMORY_ARCHIVIST, AgentRole.DIRECTOR],
            AgentRole.CONTINUITY_SUPERVISOR: [AgentRole.MEMORY_ARCHIVIST, AgentRole.PROMPT_ENGINEER],
            AgentRole.MEMORY_ARCHIVIST: [AgentRole.DIRECTOR, AgentRole.EDITOR],
            AgentRole.PRODUCER: [AgentRole.SYSTEM_ORCHESTRATOR, AgentRole.RENDER_COORDINATOR],
            AgentRole.DIRECTOR: [AgentRole.MEMORY_ARCHIVIST, AgentRole.EDITOR, AgentRole.PRODUCER],
            AgentRole.SYSTEM_ORCHESTRATOR: [AgentRole.PRODUCER],
        }
        return CrewDepartmentProfile(
            agent_role=role,
            department_name=config.get("name", self._department_name(role)),
            description=config.get("description", ""),
            responsibilities=[cap.capability for cap in config.get("capabilities", [])],
            inputs_consumed=["crew_task", "role_context", "memory_refs", "spine_refs"],
            outputs_produced=["crew_reasoning", "handoff_packet", "risk", "recommendation"],
            memory_read_policy=["role_filtered_project_memory", "scene_context_when_available"],
            memory_write_policy="propose_only",
            spine_access_policy="role_filtered",
            collaboration_partners=partners.get(role, []),
            escalation_triggers=[item.value for item in config.get("escalates_on", [])],
            inspection_fields=["observation", "inference", "recommendation", "evidence", "memory", "spine", "risks"],
            creator_authority_boundary="Advisory and operational only; creator retains final creative authority.",
        )


crew_intelligence_service = CrewIntelligenceService()
