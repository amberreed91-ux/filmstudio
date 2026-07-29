from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from app.data.storage import get_storage
from app.models.crew import AgentRole
from app.models.crew_intelligence import CrewReasoningType
from app.models.studio_brain import (
    StudioBrainConflictCase,
    StudioBrainConflictSeverity,
    StudioBrainConflictStatus,
    StudioBrainConflictType,
    StudioBrainDepartmentSignal,
    StudioBrainDirectiveStatus,
    StudioBrainDirectiveType,
    StudioBrainDispatchDirectiveRequest,
    StudioBrainExecutionDirective,
    StudioBrainExecutiveSession,
    StudioBrainOpenSessionRequest,
    StudioBrainPlanStatus,
    StudioBrainPlanStep,
    StudioBrainProductionPlan,
    StudioBrainReadinessSnapshot,
    StudioBrainReadinessStatus,
    StudioBrainReasoningTrace,
    StudioBrainResolutionDecision,
    StudioBrainResolutionMode,
    StudioBrainResolveConflictRequest,
    StudioBrainRisk,
    StudioBrainSessionPurpose,
    StudioBrainSessionResponse,
    StudioBrainSessionStatus,
    StudioBrainSourceRef,
    utc_now_iso,
)
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer
from app.services.studio_brain_service import studio_brain_service


logger = logging.getLogger("studio-brain-executive")


class StudioBrainExecutiveService:
    """Executive coordination layer for Studio Brain 2.0.

    The service coordinates existing departments and canonical services. It does
    not own task execution, memory truth, Creative Spine mutation, render
    provider execution, or creator authority.
    """

    _DISALLOWED_CREATOR_TEXT_PATTERNS = [
        re.compile(r"\bscore\s*:", re.IGNORECASE),
        re.compile(r"\brating\s*:", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*/\s*10\b", re.IGNORECASE),
        re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bgreat job\b", re.IGNORECASE),
        re.compile(r"\blooks good overall\b", re.IGNORECASE),
        re.compile(r"\bobjectively\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        *,
        storage: Any | None = None,
        crew_intelligence_service: Any | None = None,
        workflow_service: Any | None = None,
        knowledge_service: Any | None = None,
        department_adapters: dict[AgentRole, Callable[[StudioBrainExecutiveSession], StudioBrainDepartmentSignal]] | None = None,
    ) -> None:
        self._storage = storage
        self._crew_intelligence_service = crew_intelligence_service
        self._workflow_service = workflow_service
        self._knowledge_service = knowledge_service
        self._department_adapters = department_adapters or {}

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    @property
    def crew_intelligence_service(self):
        if self._crew_intelligence_service is None:
            from app.services.crew_intelligence_service import crew_intelligence_service

            self._crew_intelligence_service = crew_intelligence_service
        return self._crew_intelligence_service

    @property
    def workflow_service(self):
        if self._workflow_service is None:
            from app.services.studio_workflow_service import studio_workflow_service

            self._workflow_service = studio_workflow_service
        return self._workflow_service

    @property
    def knowledge_service(self):
        if self._knowledge_service is not None:
            return self._knowledge_service
        try:
            from app.services.studio_knowledge_service import studio_knowledge_service
        except Exception:
            return None
        self._knowledge_service = studio_knowledge_service
        return self._knowledge_service

    def _id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:14]}"

    def _stable_id(self, prefix: str, *parts: Any) -> str:
        raw = "|".join(str(part or "") for part in parts)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}"

    def _model_dict(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return value
        return {}

    def _duration(self, started: float) -> int:
        return int((perf_counter() - started) * 1000)

    def _language_warnings(self, *texts: str) -> list[str]:
        warnings: list[str] = []
        for text in texts:
            if not text:
                continue
            for pattern in self._DISALLOWED_CREATOR_TEXT_PATTERNS:
                if pattern.search(text):
                    warnings.append(f"Creator-facing text contains prohibited pattern: {pattern.pattern}")
        return warnings

    def _require_session(self, session_id: str) -> StudioBrainExecutiveSession:
        session = self.storage.get_studio_brain_session(session_id)
        if session is None:
            raise ValidationError("Studio Brain session not found", stage="studio_brain_session")
        return session

    def _save_session(self, session: StudioBrainExecutiveSession) -> StudioBrainExecutiveSession:
        session.updated_at = utc_now_iso()
        self.storage.save_studio_brain_session(session)
        return session

    def open_session(
        self,
        project_id: str,
        request: StudioBrainOpenSessionRequest | None = None,
    ) -> StudioBrainExecutiveSession:
        timer = start_timer()
        request = request or StudioBrainOpenSessionRequest()
        if not project_id.strip():
            raise ValidationError("project_id is required", stage="studio_brain_open_session")
        try:
            project = self.storage.get_project(project_id)
        except Exception:
            project = None
        if project is None:
            raise ValidationError("Project not found", stage="studio_brain_open_session")

        session = StudioBrainExecutiveSession(
            session_id=self._id("brain_session"),
            project_id=project_id,
            purpose=request.purpose,
            status=StudioBrainSessionStatus.OPEN,
            scope=request.scope or {},
            created_by=request.created_by,
            metadata={
                "source": "StudioBrainExecutiveService",
                "project_title": getattr(project, "title", "") if project is not None else "",
            },
        )
        session.legacy_orchestration_bundle = studio_brain_service.build_orchestration_bundle_from_executive_session(session)
        self.storage.save_studio_brain_session(session)
        self._record_trace(
            session,
            trace_type="session",
            operation="open_session",
            output_ids=[session.session_id],
            duration_ms=elapsed_ms(timer),
        )
        log_stage_event(
            project_id=project_id,
            job_id=session.session_id,
            provider="local",
            stage="studio_brain_open_session",
            duration_ms=elapsed_ms(timer),
        )
        return session

    def list_sessions(self, project_id: str, limit: int = 20) -> list[StudioBrainExecutiveSession]:
        return list(self.storage.list_studio_brain_sessions(project_id, limit=limit))

    def get_session_response(self, session_id: str) -> StudioBrainSessionResponse:
        session = self._require_session(session_id)
        signals = self.storage.list_studio_brain_department_signals(session_id)
        plan = self.storage.get_studio_brain_production_plan(session.active_plan_id) if session.active_plan_id else None
        conflicts = self.storage.list_studio_brain_conflicts(session_id)
        directives = self.storage.list_studio_brain_execution_directives(session_id)
        readiness = (
            self.storage.get_studio_brain_readiness_snapshot(session.latest_readiness_snapshot_id)
            if session.latest_readiness_snapshot_id
            else None
        )
        traces = self.storage.list_studio_brain_reasoning_traces(session_id)
        return StudioBrainSessionResponse(
            session=session,
            signals=signals,
            plan=plan,
            conflicts=conflicts,
            directives=directives,
            readiness=readiness,
            traces=traces,
            legacy_orchestration_bundle=session.legacy_orchestration_bundle,
        )

    def latest_session_response(self, project_id: str) -> StudioBrainSessionResponse | None:
        sessions = self.list_sessions(project_id, limit=1)
        if not sessions:
            return None
        return self.get_session_response(sessions[0].session_id)

    def gather_department_signals(self, session_id: str, refresh: bool = False) -> list[StudioBrainDepartmentSignal]:
        timer = start_timer()
        session = self._require_session(session_id)
        if not refresh:
            existing = self.storage.list_studio_brain_department_signals(session_id)
            if existing:
                return existing

        signals: list[StudioBrainDepartmentSignal] = []
        adapters = self._default_department_adapters()
        adapters.update(self._department_adapters)
        for role, adapter in adapters.items():
            try:
                signal = adapter(session)
            except Exception as exc:
                signal = self._failed_signal(session, role, str(exc))
            signal.metadata.setdefault("language_warnings", self._language_warnings(signal.summary, *signal.recommended_actions))
            self.storage.save_studio_brain_department_signal(signal)
            signals.append(signal)

        session.department_signal_ids = [signal.signal_id for signal in signals]
        session.status = StudioBrainSessionStatus.PLANNING
        session.legacy_orchestration_bundle = studio_brain_service.build_orchestration_bundle_from_executive_session(
            session,
            signals=signals,
        )
        self._save_session(session)
        self._record_trace(
            session,
            trace_type="signals",
            operation="gather_department_signals",
            included_signal_ids=[signal.signal_id for signal in signals],
            output_ids=[signal.signal_id for signal in signals],
            duration_ms=elapsed_ms(timer),
        )
        return signals

    def generate_production_plan(self, session_id: str) -> StudioBrainProductionPlan:
        timer = start_timer()
        session = self._require_session(session_id)
        signals = self.gather_department_signals(session_id)
        readiness = self.create_readiness_snapshot(session_id)
        phase = str(session.scope.get("phase") or self._workflow_phase(session.project_id) or "")
        steps: list[StudioBrainPlanStep] = []
        risks: list[StudioBrainRisk] = []
        for idx, signal in enumerate(signals, start=1):
            risks.extend(signal.risks)
            action = signal.recommended_actions[0] if signal.recommended_actions else "Review department signal before the next production move."
            steps.append(
                StudioBrainPlanStep(
                    step_id=self._stable_id("brain_step", session.session_id, signal.signal_id, idx),
                    order_index=idx,
                    title=action,
                    target_department=signal.agent_role,
                    target_service=signal.metadata.get("source_service", ""),
                    target_phase=phase,
                    action_type="department_review" if signal.requires_creator_decision else "department_coordination",
                    input_requirements=["source_refs", "memory_refs", "spine_refs"],
                    expected_output="Inspectable department update or creator decision.",
                    risk_ids=[risk.risk_id for risk in signal.risks],
                    status="waiting_creator" if signal.requires_creator_decision else "proposed",
                    source_refs=signal.source_refs,
                    requires_creator_decision=signal.requires_creator_decision,
                    validation_requirements=["Preserve advisory-only boundary.", "Route side effects through canonical services."],
                )
            )

        status = StudioBrainPlanStatus.READY
        if readiness.status == StudioBrainReadinessStatus.WAITING_CREATOR:
            status = StudioBrainPlanStatus.WAITING_CREATOR
        elif readiness.status in {StudioBrainReadinessStatus.BLOCKED, StudioBrainReadinessStatus.PARTIALLY_READY}:
            status = StudioBrainPlanStatus.PARTIALLY_BLOCKED

        trace = self._record_trace(
            session,
            trace_type="plan",
            operation="generate_production_plan",
            included_signal_ids=[signal.signal_id for signal in signals],
            rule_evaluations=[
                {"rule": "creator_authority_preserved", "passed": True},
                {"rule": "canonical_mutation_forbidden", "passed": True},
                {"rule": "readiness_status", "value": readiness.status.value},
            ],
            duration_ms=elapsed_ms(timer),
        )
        plan = StudioBrainProductionPlan(
            plan_id=self._id("brain_plan"),
            session_id=session.session_id,
            project_id=session.project_id,
            purpose=session.purpose,
            status=status,
            phase=phase,
            title="Studio Brain executive production plan",
            summary=self._plan_summary(signals, readiness),
            steps=steps,
            risks=risks,
            creator_attention=[signal.summary for signal in signals if signal.requires_creator_decision],
            readiness_snapshot_id=readiness.snapshot_id,
            source_refs=[ref for signal in signals for ref in signal.source_refs[:2]],
            reasoning_trace_id=trace.trace_id,
        )
        self.storage.save_studio_brain_production_plan(plan)
        session.active_plan_id = plan.plan_id
        session.latest_readiness_snapshot_id = readiness.snapshot_id
        session.status = StudioBrainSessionStatus.WAITING_CREATOR if status == StudioBrainPlanStatus.WAITING_CREATOR else StudioBrainSessionStatus.READY_TO_DISPATCH
        session.legacy_orchestration_bundle = studio_brain_service.build_orchestration_bundle_from_executive_session(
            session,
            signals=signals,
            plan=plan,
            readiness=readiness,
        )
        self._save_session(session)
        self._record_crew_reasoning(session, "Studio Brain generated an executive production plan.", plan.summary)
        return plan

    def detect_conflicts(self, session_id: str) -> list[StudioBrainConflictCase]:
        timer = start_timer()
        session = self._require_session(session_id)
        signals = self.gather_department_signals(session_id)
        conflicts: list[StudioBrainConflictCase] = []
        for signal in signals:
            if signal.requires_creator_decision:
                conflicts.append(
                    self._signal_conflict(
                        session,
                        signal,
                        StudioBrainConflictType.CREATIVE_AUTHORITY,
                        StudioBrainConflictSeverity.REQUIRES_DECISION,
                        "Creator decision needed",
                        signal.open_questions[0] if signal.open_questions else "Which direction should the studio preserve?",
                    )
                )
            if signal.status in {"failed", "blocked", "unavailable"}:
                conflicts.append(
                    self._signal_conflict(
                        session,
                        signal,
                        StudioBrainConflictType.MISSING_EVIDENCE,
                        StudioBrainConflictSeverity.NEEDS_ATTENTION,
                        "Department evidence missing",
                        "Review missing evidence or rerun the department analysis.",
                    )
                )
        if not signals:
            conflicts.append(
                StudioBrainConflictCase(
                    conflict_id=self._stable_id("brain_conflict", session.session_id, "no_signals"),
                    session_id=session.session_id,
                    project_id=session.project_id,
                    conflict_type=StudioBrainConflictType.MISSING_EVIDENCE,
                    severity=StudioBrainConflictSeverity.NEEDS_ATTENTION,
                    title="No department signals available",
                    summary="Studio Brain could not gather department signals for this session.",
                    recommended_resolution_mode=StudioBrainResolutionMode.DEFER_MISSING_EVIDENCE,
                )
            )

        deduped: dict[str, StudioBrainConflictCase] = {conflict.conflict_id: conflict for conflict in conflicts}
        for conflict in deduped.values():
            self.storage.save_studio_brain_conflict(conflict)
        session.conflict_ids = list(deduped)
        if any(conflict.requires_creator_decision for conflict in deduped.values()):
            session.status = StudioBrainSessionStatus.WAITING_CREATOR
        self._save_session(session)
        self._record_trace(
            session,
            trace_type="conflict",
            operation="detect_conflicts",
            included_signal_ids=[signal.signal_id for signal in signals],
            output_ids=list(deduped),
            duration_ms=elapsed_ms(timer),
        )
        return list(deduped.values())

    def resolve_conflict(
        self,
        session_id: str,
        conflict_id: str,
        request: StudioBrainResolveConflictRequest | None = None,
    ) -> StudioBrainResolutionDecision:
        request = request or StudioBrainResolveConflictRequest()
        session = self._require_session(session_id)
        conflict = self.storage.get_studio_brain_conflict(conflict_id)
        if conflict is None or conflict.session_id != session_id:
            raise ValidationError("Studio Brain conflict not found", stage="studio_brain_resolve_conflict")
        if conflict.status != StudioBrainConflictStatus.OPEN:
            raise StateError("Studio Brain conflict is already closed", stage="studio_brain_resolve_conflict")

        mode = request.resolution_mode or conflict.recommended_resolution_mode
        created_directive_ids: list[str] = []
        created_gate_id = ""
        created_attention_id = ""
        if conflict.requires_creator_decision or mode == StudioBrainResolutionMode.ESCALATE_CREATOR:
            mode = StudioBrainResolutionMode.ESCALATE_CREATOR
            directive = self._creator_gate_directive(session, conflict)
            self.storage.save_studio_brain_execution_directive(directive)
            created_directive_ids.append(directive.directive_id)
            conflict.status = StudioBrainConflictStatus.ESCALATED
            decision_text = "Escalated to creator through a proposed workflow gate."
        elif mode == StudioBrainResolutionMode.DEFER_MISSING_EVIDENCE:
            conflict.status = StudioBrainConflictStatus.RESOLVED
            decision_text = "Deferred until missing evidence is available."
        else:
            conflict.status = StudioBrainConflictStatus.RESOLVED
            decision_text = "Resolved through deterministic operational policy; canonical truth was not mutated."

        conflict.resolved_at = utc_now_iso()
        self.storage.save_studio_brain_conflict(conflict)
        resolution = StudioBrainResolutionDecision(
            resolution_id=self._id("brain_resolution"),
            conflict_id=conflict.conflict_id,
            session_id=session.session_id,
            project_id=session.project_id,
            mode=mode,
            decision=decision_text,
            rationale=conflict.summary,
            selected_source_refs=conflict.conflicting_source_refs[:3],
            created_directive_ids=created_directive_ids,
            created_gate_id=created_gate_id,
            created_attention_id=created_attention_id,
            resolved_by=request.actor_id,
        )
        self.storage.save_studio_brain_resolution_decision(resolution)
        session.directive_ids = sorted(set(session.directive_ids + created_directive_ids))
        self._save_session(session)
        return resolution

    def create_readiness_snapshot(self, session_id: str) -> StudioBrainReadinessSnapshot:
        session = self._require_session(session_id)
        signals = self.storage.list_studio_brain_department_signals(session_id) or self.gather_department_signals(session_id)
        conflicts = self.storage.list_studio_brain_conflicts(session_id)
        ready_departments = [signal.department_name for signal in signals if signal.status in {"active", "ready", "standby"}]
        blocked_departments = [signal.department_name for signal in signals if signal.status in {"failed", "blocked", "unavailable"}]
        missing_evidence: list[str] = []
        if not signals:
            missing_evidence.append("No department signals have been gathered.")
        if not self.knowledge_service:
            missing_evidence.append("Studio Knowledge context is unavailable; memory and workflow fallbacks are being used.")
        open_conflicts = [conflict.conflict_id for conflict in conflicts if conflict.status == StudioBrainConflictStatus.OPEN]
        waiting_creator = any(signal.requires_creator_decision for signal in signals) or any(
            conflict.requires_creator_decision for conflict in conflicts
        )
        if waiting_creator:
            status = StudioBrainReadinessStatus.WAITING_CREATOR
        elif blocked_departments:
            status = StudioBrainReadinessStatus.PARTIALLY_READY
        elif missing_evidence:
            status = StudioBrainReadinessStatus.INSUFFICIENT_EVIDENCE
        else:
            status = StudioBrainReadinessStatus.READY
        snapshot = StudioBrainReadinessSnapshot(
            snapshot_id=self._id("brain_ready"),
            session_id=session.session_id,
            project_id=session.project_id,
            phase=str(session.scope.get("phase") or self._workflow_phase(session.project_id) or ""),
            status=status,
            summary=self._readiness_summary(status, ready_departments, blocked_departments, missing_evidence),
            ready_departments=ready_departments,
            blocked_departments=blocked_departments,
            missing_evidence=missing_evidence,
            open_conflict_ids=open_conflicts,
            memory_readiness={"available": True, "source": "MemoryService/CrewIntelligenceService"},
            spine_readiness={"available": True, "source": "SpineConsumptionService", "role_filtered": True},
            knowledge_readiness={"available": bool(self.knowledge_service), "source": "StudioKnowledgeService"},
        )
        self.storage.save_studio_brain_readiness_snapshot(snapshot)
        session.latest_readiness_snapshot_id = snapshot.snapshot_id
        self._save_session(session)
        return snapshot

    def propose_directives(self, session_id: str) -> list[StudioBrainExecutionDirective]:
        session = self._require_session(session_id)
        plan = self.storage.get_studio_brain_production_plan(session.active_plan_id) if session.active_plan_id else self.generate_production_plan(session_id)
        conflicts = self.storage.list_studio_brain_conflicts(session_id, status=StudioBrainConflictStatus.OPEN.value)
        directives: list[StudioBrainExecutionDirective] = []
        for conflict in conflicts:
            if conflict.requires_creator_decision:
                directives.append(self._creator_gate_directive(session, conflict, plan_id=plan.plan_id if plan else ""))
        if not directives and plan:
            directives.append(
                StudioBrainExecutionDirective(
                    directive_id=self._stable_id("brain_directive", session.session_id, plan.plan_id, "record_attention"),
                    session_id=session.session_id,
                    project_id=session.project_id,
                    directive_type=StudioBrainDirectiveType.RECORD_ATTENTION,
                    target_service="CrewIntelligenceService",
                    target_method="create_reasoning_record",
                    payload={
                        "title": "Studio Brain plan is ready",
                        "summary": plan.summary,
                        "recommended_action": "Review proposed plan steps before dispatching production work.",
                    },
                    idempotency_key=self._stable_id("brain_key", session.session_id, plan.plan_id, "record_attention"),
                    source_plan_id=plan.plan_id,
                )
            )
        saved: list[StudioBrainExecutionDirective] = []
        for directive in directives:
            existing = self.storage.get_studio_brain_execution_directive_by_key(directive.project_id, directive.idempotency_key)
            if existing:
                saved.append(existing)
                continue
            self.storage.save_studio_brain_execution_directive(directive)
            saved.append(directive)
        session.directive_ids = sorted(set(session.directive_ids + [directive.directive_id for directive in saved]))
        self._save_session(session)
        return saved

    def dispatch_directive(
        self,
        session_id: str,
        directive_id: str,
        request: StudioBrainDispatchDirectiveRequest | None = None,
    ) -> StudioBrainExecutionDirective:
        request = request or StudioBrainDispatchDirectiveRequest()
        session = self._require_session(session_id)
        directive = self.storage.get_studio_brain_execution_directive(directive_id)
        if directive is None or directive.session_id != session_id:
            raise ValidationError("Studio Brain directive not found", stage="studio_brain_dispatch_directive")
        if directive.status in {StudioBrainDirectiveStatus.DISPATCHED, StudioBrainDirectiveStatus.COMPLETED}:
            return directive
        if directive.requires_creator_approval and not request.approve:
            raise StateError("Directive requires creator approval before dispatch", stage="studio_brain_dispatch_directive")

        try:
            if directive.directive_type == StudioBrainDirectiveType.CREATE_WORKFLOW_GATE:
                gate = self._dispatch_workflow_gate(session, directive, request.actor_id)
                directive.approval_gate_id = getattr(gate, "gate_id", "") or directive.approval_gate_id
                directive.dispatch_result = {"gate_id": directive.approval_gate_id, "status": getattr(getattr(gate, "status", None), "value", "")}
            elif directive.directive_type == StudioBrainDirectiveType.RECORD_ATTENTION:
                reasoning = self._record_crew_reasoning(
                    session,
                    directive.payload.get("title") or "Studio Brain attention",
                    directive.payload.get("summary") or "Studio Brain requested creator attention.",
                    requires_creator_decision=True,
                )
                directive.dispatch_result = {"reasoning_id": getattr(reasoning, "reasoning_id", "")}
            else:
                directive.dispatch_result = {"status": "recorded", "note": "Directive recorded for canonical service dispatch."}
            directive.status = StudioBrainDirectiveStatus.DISPATCHED
            directive.dispatched_at = utc_now_iso()
        except Exception as exc:
            directive.status = StudioBrainDirectiveStatus.FAILED
            directive.error_message = str(exc)
        directive.updated_at = utc_now_iso()
        self.storage.save_studio_brain_execution_directive(directive)
        session.status = StudioBrainSessionStatus.DISPATCHING if directive.status == StudioBrainDirectiveStatus.DISPATCHED else StudioBrainSessionStatus.FAILED
        self._save_session(session)
        return directive

    def _default_department_adapters(self) -> dict[AgentRole, Callable[[StudioBrainExecutiveSession], StudioBrainDepartmentSignal]]:
        return {
            AgentRole.SYSTEM_ORCHESTRATOR: self._system_signal,
            AgentRole.PRODUCER: self._producer_signal,
            AgentRole.MEMORY_ARCHIVIST: self._memory_signal,
            AgentRole.CONTINUITY_SUPERVISOR: self._continuity_signal,
            AgentRole.RENDER_COORDINATOR: self._render_signal,
            AgentRole.EDITOR: self._editor_signal,
            AgentRole.QUALITY_REVIEWER: self._quality_signal,
            AgentRole.CINEMATOGRAPHER: self._service_signal_adapter(
                AgentRole.CINEMATOGRAPHER,
                "Cinematographer",
                "app.services.cinematographer_intelligence_service",
                "cinematographer_intelligence_service",
                "department_signal",
            ),
            AgentRole.PRODUCTION_DESIGNER: self._service_signal_adapter(
                AgentRole.PRODUCTION_DESIGNER,
                "Production Design",
                "app.services.production_design_intelligence_service",
                "production_design_intelligence_service",
                "department_signal",
            ),
            AgentRole.COLORIST: self._service_signal_adapter(
                AgentRole.COLORIST,
                "Colorist",
                "app.services.colorist_intelligence_service",
                "colorist_intelligence_service",
                "department_signal",
            ),
            AgentRole.SOUND_DESIGNER: self._service_signal_adapter(
                AgentRole.SOUND_DESIGNER,
                "Performance Audio",
                "app.services.performance_audio_intelligence_service",
                "performance_audio_intelligence_service",
                "department_signal",
            ),
        }

    def _service_signal_adapter(
        self,
        role: AgentRole,
        department_name: str,
        module_name: str,
        service_name: str,
        method_name: str,
    ) -> Callable[[StudioBrainExecutiveSession], StudioBrainDepartmentSignal]:
        def adapter(session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
            try:
                module = __import__(module_name, fromlist=[service_name])
                service = getattr(module, service_name)
                method = getattr(service, method_name)
                try:
                    raw = method(session.project_id, scene_id=session.scope.get("scene_id"))
                except TypeError:
                    raw = method(session.project_id)
                data = self._model_dict(raw)
                status = str(data.get("status") or data.get("state") or "active")
                summary = str(data.get("summary") or data.get("signal") or f"{department_name} signal is available.")
                return StudioBrainDepartmentSignal(
                    signal_id=self._stable_id("brain_signal", session.session_id, role.value, data.get("signal_id") or summary),
                    session_id=session.session_id,
                    project_id=session.project_id,
                    agent_role=role,
                    department_name=department_name,
                    status=status,
                    purpose=session.purpose,
                    summary=summary,
                    recommended_actions=self._list_strings(data.get("recommended_actions") or data.get("recommendations")),
                    risks=self._risks_from_signal(session, role, data),
                    open_questions=self._list_strings(data.get("open_questions")),
                    source_refs=[self._source_ref(session, "department_signal", service_name, data.get("signal_id") or role.value, summary)],
                    memory_refs=self._list_dicts(data.get("memory_refs")),
                    spine_refs=self._list_dicts(data.get("spine_refs")),
                    crew_reasoning_ids=[str(data.get("crew_reasoning_id"))] if data.get("crew_reasoning_id") else [],
                    confidence_label=str(data.get("confidence_label") or "emerging"),
                    requires_creator_decision=bool(data.get("requires_creator_decision") or data.get("needs_creator_attention")),
                    metadata={"source_service": service_name, "raw_signal": data},
                )
            except Exception as exc:
                return self._failed_signal(session, role, f"{department_name} signal unavailable: {exc}", department_name=department_name)

        return adapter

    def _system_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, "system"),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=AgentRole.SYSTEM_ORCHESTRATOR,
            department_name="System Orchestrator",
            status="active",
            purpose=session.purpose,
            summary="Workflow coordination is available through existing orchestrator and workflow services.",
            recommended_actions=["Coordinate next steps through existing workflow, queue, and department services."],
            source_refs=[self._source_ref(session, "service", "StudioOrchestrator", "system_orchestrator", "Existing task orchestrator remains execution owner.")],
            confidence_label="consistent",
            metadata={"source_service": "StudioBrainExecutiveService"},
        )

    def _producer_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        source_refs = [self._source_ref(session, "workflow", "StudioWorkflowService", session.project_id, "Professional workflow state consulted.")]
        summary = "Workflow state is available for executive production planning."
        try:
            workflow = self.workflow_service.workflow_summary(session.project_id)
            data = self._model_dict(workflow)
            phase = data.get("project_state", {}).get("current_phase") if isinstance(data.get("project_state"), dict) else ""
            if phase:
                summary = f"Current workflow phase is {phase}."
        except Exception as exc:
            return self._failed_signal(session, AgentRole.PRODUCER, f"Workflow summary unavailable: {exc}", department_name="Producer")
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, "producer", summary),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=AgentRole.PRODUCER,
            department_name="Producer",
            status="active",
            purpose=session.purpose,
            summary=summary,
            recommended_actions=["Use workflow gates and queue state to protect the next production move."],
            source_refs=source_refs,
            confidence_label="consistent",
            metadata={"source_service": "StudioWorkflowService"},
        )

    def _memory_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        try:
            overview = self.crew_intelligence_service.get_project_overview(session.project_id)
            data = self._model_dict(overview)
            attention_count = len(data.get("creator_attention") or [])
            summary = data.get("summary") or "Crew reasoning and memory-aware department context are available."
            return StudioBrainDepartmentSignal(
                signal_id=self._stable_id("brain_signal", session.session_id, "memory", summary),
                session_id=session.session_id,
                project_id=session.project_id,
                agent_role=AgentRole.MEMORY_ARCHIVIST,
                department_name="Memory Archivist",
                status="active",
                purpose=session.purpose,
                summary=summary,
                recommended_actions=["Preserve callback and continuity context in the next department handoff."],
                open_questions=["Review creator attention before dispatch."] if attention_count else [],
                source_refs=[self._source_ref(session, "crew_intelligence", "CrewIntelligenceService", session.project_id, "Crew reasoning overview consulted.")],
                requires_creator_decision=attention_count > 0,
                confidence_label="consistent",
                metadata={"source_service": "CrewIntelligenceService", "creator_attention_count": attention_count},
            )
        except Exception as exc:
            return self._failed_signal(session, AgentRole.MEMORY_ARCHIVIST, f"Crew intelligence unavailable: {exc}", department_name="Memory Archivist")

    def _continuity_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        knowledge = self._knowledge_signal_context(session, "continuity")
        summary = "Continuity context is available through memory, crew reasoning, and knowledge sources."
        if knowledge:
            summary = f"Continuity context cites {len(knowledge.get('atoms', []))} knowledge items."
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, "continuity", summary),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=AgentRole.CONTINUITY_SUPERVISOR,
            department_name="Continuity",
            status="active" if knowledge is not None else "standby",
            purpose=session.purpose,
            summary=summary,
            recommended_actions=["Check memory, spine, and knowledge conflicts before approving phase movement."],
            source_refs=[self._source_ref(session, "knowledge_context", "StudioKnowledgeService", knowledge.get("pack_id", "fallback") if knowledge else "fallback", summary)],
            confidence_label="consistent" if knowledge else "emerging",
            metadata={"source_service": "StudioKnowledgeService", "knowledge_context": knowledge or {}},
        )

    def _render_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        try:
            jobs = self.storage.list_jobs(project_id=session.project_id, limit=50)
        except Exception:
            jobs = []
        active = [job for job in jobs if str(getattr(job, "status", "")).lower() in {"queued", "running", "processing", "rendering"}]
        failed = [job for job in jobs if str(getattr(job, "status", "")).lower() in {"failed", "error"}]
        summary = f"Render coordinator sees {len(jobs)} recent jobs, with {len(active)} active and {len(failed)} needing attention."
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, "render", len(jobs), len(failed)),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=AgentRole.RENDER_COORDINATOR,
            department_name="Render Coordinator",
            status="blocked" if failed else "active",
            purpose=session.purpose,
            summary=summary,
            recommended_actions=["Route render work through queue and render services; keep provider execution outside Studio Brain."],
            source_refs=[self._source_ref(session, "render_jobs", "RenderService", session.project_id, summary)],
            risks=[
                StudioBrainRisk(
                    risk_id=self._stable_id("brain_risk", session.session_id, "render_failed", len(failed)),
                    category="render",
                    severity=StudioBrainConflictSeverity.NEEDS_ATTENTION,
                    summary="Recent render jobs need inspection before dispatch.",
                )
            ]
            if failed
            else [],
            confidence_label="consistent" if jobs else "emerging",
            metadata={"source_service": "RenderService", "job_count": len(jobs), "active_count": len(active), "failed_count": len(failed)},
        )

    def _editor_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, "editor"),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=AgentRole.EDITOR,
            department_name="Editor",
            status="standby",
            purpose=session.purpose,
            summary="Editorial coordination is available through the existing editorial intelligence and screening surfaces.",
            recommended_actions=["Use editorial and screening evidence before locking cuts or revision plans."],
            source_refs=[self._source_ref(session, "department_signal", "EditorialIntelligenceService", "editorial", "Editorial readiness is represented as advisory context.")],
            confidence_label="emerging",
            metadata={"source_service": "EditorialIntelligenceService"},
        )

    def _quality_signal(self, session: StudioBrainExecutiveSession) -> StudioBrainDepartmentSignal:
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, "quality"),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=AgentRole.QUALITY_REVIEWER,
            department_name="Production Acceptance",
            status="standby",
            purpose=session.purpose,
            summary="Production acceptance should verify package and delivery evidence before final approval.",
            recommended_actions=["Create or inspect acceptance evidence before package and delivery approvals."],
            source_refs=[self._source_ref(session, "department_signal", "ProductionAcceptanceService", "acceptance", "Production acceptance remains the verification owner.")],
            confidence_label="emerging",
            metadata={"source_service": "ProductionAcceptanceService"},
        )

    def _knowledge_signal_context(self, session: StudioBrainExecutiveSession, department: str) -> dict[str, Any] | None:
        service = self.knowledge_service
        if service is None:
            return None
        try:
            from app.models.studio_knowledge import KnowledgeContextRequest

            pack = service.get_context_pack(
                session.project_id,
                KnowledgeContextRequest(
                    department=department,
                    purpose=session.purpose.value,
                    scene_id=session.scope.get("scene_id"),
                    shot_id=session.scope.get("shot_id"),
                    asset_id=session.scope.get("asset_id"),
                    max_atoms=12,
                    consumer_id=session.session_id,
                ),
            )
            return pack.model_dump(mode="json")
        except Exception as exc:
            logger.info("Studio knowledge context unavailable for %s/%s: %s", session.project_id, department, exc)
            return None

    def _failed_signal(
        self,
        session: StudioBrainExecutiveSession,
        role: AgentRole,
        message: str,
        *,
        department_name: str | None = None,
    ) -> StudioBrainDepartmentSignal:
        return StudioBrainDepartmentSignal(
            signal_id=self._stable_id("brain_signal", session.session_id, role.value, "failed"),
            session_id=session.session_id,
            project_id=session.project_id,
            agent_role=role,
            department_name=department_name or role.value.replace("_", " ").title(),
            status="failed",
            purpose=session.purpose,
            summary=message,
            recommended_actions=["Rerun or inspect this department before relying on its output."],
            source_refs=[self._source_ref(session, "service_error", "StudioBrainExecutiveService", role.value, message)],
            confidence_label="insufficient_context",
            metadata={"source_service": "StudioBrainExecutiveService", "error": message},
        )

    def _source_ref(
        self,
        session: StudioBrainExecutiveSession,
        source_type: str,
        source_service: str,
        source_id: str,
        summary: str,
    ) -> StudioBrainSourceRef:
        return StudioBrainSourceRef(
            source_ref_id=self._stable_id("brain_src", session.session_id, source_type, source_service, source_id, summary),
            source_type=source_type,
            source_service=source_service,
            source_id=str(source_id or ""),
            project_id=session.project_id,
            scene_id=session.scope.get("scene_id"),
            shot_id=session.scope.get("shot_id"),
            asset_id=session.scope.get("asset_id"),
            summary=summary,
        )

    def _risks_from_signal(self, session: StudioBrainExecutiveSession, role: AgentRole, data: dict[str, Any]) -> list[StudioBrainRisk]:
        risks: list[StudioBrainRisk] = []
        raw_risks = data.get("risks") or data.get("blockers") or []
        for idx, item in enumerate(raw_risks[:6] if isinstance(raw_risks, list) else []):
            summary = item.get("summary") if isinstance(item, dict) else str(item)
            if not summary:
                continue
            risks.append(
                StudioBrainRisk(
                    risk_id=self._stable_id("brain_risk", session.session_id, role.value, idx, summary),
                    category=role.value,
                    severity=StudioBrainConflictSeverity.NEEDS_ATTENTION,
                    summary=summary,
                    requires_creator_decision=bool(isinstance(item, dict) and item.get("requires_creator_decision")),
                )
            )
        return risks

    def _signal_conflict(
        self,
        session: StudioBrainExecutiveSession,
        signal: StudioBrainDepartmentSignal,
        conflict_type: StudioBrainConflictType,
        severity: StudioBrainConflictSeverity,
        title: str,
        creator_question: str,
    ) -> StudioBrainConflictCase:
        requires_creator = severity in {StudioBrainConflictSeverity.REQUIRES_DECISION, StudioBrainConflictSeverity.BLOCKS_DISPATCH}
        return StudioBrainConflictCase(
            conflict_id=self._stable_id("brain_conflict", session.session_id, signal.signal_id, conflict_type.value),
            session_id=session.session_id,
            project_id=session.project_id,
            conflict_type=conflict_type,
            severity=severity,
            title=title,
            summary=signal.summary,
            conflicting_signal_ids=[signal.signal_id],
            conflicting_roles=[signal.agent_role],
            conflicting_source_refs=signal.source_refs,
            evidence_summary=signal.summary,
            recommended_resolution_mode=StudioBrainResolutionMode.ESCALATE_CREATOR if requires_creator else StudioBrainResolutionMode.DEFER_MISSING_EVIDENCE,
            requires_creator_decision=requires_creator,
            creator_question=creator_question if requires_creator else None,
        )

    def _creator_gate_directive(
        self,
        session: StudioBrainExecutiveSession,
        conflict: StudioBrainConflictCase,
        *,
        plan_id: str = "",
    ) -> StudioBrainExecutionDirective:
        return StudioBrainExecutionDirective(
            directive_id=self._stable_id("brain_directive", session.session_id, conflict.conflict_id, "gate"),
            session_id=session.session_id,
            project_id=session.project_id,
            directive_type=StudioBrainDirectiveType.CREATE_WORKFLOW_GATE,
            target_service="StudioWorkflowService",
            target_method="create_approval_gate",
            payload={
                "gate_type": "manual_gate",
                "target_type": "studio_brain_conflict",
                "target_id": conflict.conflict_id,
                "opened_by": "studio_brain",
                "evidence_policy": {
                    "summary": conflict.summary,
                    "creator_question": conflict.creator_question,
                    "source_refs": [ref.model_dump(mode="json") for ref in conflict.conflicting_source_refs],
                },
            },
            requires_creator_approval=True,
            idempotency_key=self._stable_id("brain_key", session.session_id, conflict.conflict_id, "gate"),
            source_plan_id=plan_id,
            source_conflict_id=conflict.conflict_id,
        )

    def _dispatch_workflow_gate(
        self,
        session: StudioBrainExecutiveSession,
        directive: StudioBrainExecutionDirective,
        actor_id: str,
    ) -> Any:
        from app.models.studio_workflow import StudioApprovalGateCreate, StudioApprovalGateType

        payload = dict(directive.payload or {})
        gate_payload = StudioApprovalGateCreate(
            gate_type=StudioApprovalGateType(payload.get("gate_type") or "manual_gate"),
            target_type=payload.get("target_type") or "studio_brain_directive",
            target_id=payload.get("target_id") or directive.directive_id,
            evidence_policy=payload.get("evidence_policy") or {},
            opened_by=actor_id,
        )
        return self.workflow_service.create_approval_gate(session.project_id, gate_payload)

    def _record_trace(
        self,
        session: StudioBrainExecutiveSession,
        *,
        trace_type: str,
        operation: str,
        input_source_refs: list[StudioBrainSourceRef] | None = None,
        included_signal_ids: list[str] | None = None,
        excluded_signal_ids: list[str] | None = None,
        rule_evaluations: list[dict[str, Any]] | None = None,
        decision_points: list[dict[str, Any]] | None = None,
        output_ids: list[str] | None = None,
        warnings: list[str] | None = None,
        duration_ms: int = 0,
    ) -> StudioBrainReasoningTrace:
        trace = StudioBrainReasoningTrace(
            trace_id=self._id("brain_trace"),
            session_id=session.session_id,
            project_id=session.project_id,
            trace_type=trace_type,
            operation=operation,
            input_source_refs=input_source_refs or [],
            included_signal_ids=included_signal_ids or [],
            excluded_signal_ids=excluded_signal_ids or [],
            rule_evaluations=rule_evaluations or [],
            decision_points=decision_points or [],
            output_ids=output_ids or [],
            warnings=warnings or [],
            duration_ms=duration_ms,
        )
        self.storage.save_studio_brain_reasoning_trace(trace)
        session.reasoning_trace_ids = sorted(set(session.reasoning_trace_ids + [trace.trace_id]))
        self._save_session(session)
        return trace

    def _record_crew_reasoning(
        self,
        session: StudioBrainExecutiveSession,
        observation: str,
        recommendation: str,
        *,
        requires_creator_decision: bool = False,
    ) -> Any:
        try:
            return self.crew_intelligence_service.create_reasoning_record(
                project_id=session.project_id,
                agent_role=AgentRole.SYSTEM_ORCHESTRATOR,
                reasoning_type=CrewReasoningType.PRODUCTION_COORDINATION,
                observation=observation,
                context_used=["studio_brain_executive_session", "department_signals", "workflow_state"],
                recommendation_summary=recommendation,
                creator_note=recommendation if requires_creator_decision else "",
                requires_creator_decision=requires_creator_decision,
                escalation_reason="Studio Brain executive attention" if requires_creator_decision else None,
                metadata={"studio_brain_session_id": session.session_id},
            )
        except Exception as exc:
            logger.info("Could not record Studio Brain crew reasoning: %s", exc)
            return None

    def _workflow_phase(self, project_id: str) -> str:
        try:
            summary = self.workflow_service.workflow_summary(project_id)
            data = self._model_dict(summary)
            state = data.get("project_state") if isinstance(data.get("project_state"), dict) else {}
            return str(state.get("current_phase") or "")
        except Exception:
            return ""

    def _plan_summary(self, signals: list[StudioBrainDepartmentSignal], readiness: StudioBrainReadinessSnapshot) -> str:
        active_count = len([signal for signal in signals if signal.status in {"active", "ready", "standby"}])
        if readiness.status == StudioBrainReadinessStatus.WAITING_CREATOR:
            return "Studio Brain has a production plan, but at least one creator decision should be reviewed before dispatch."
        if active_count:
            return f"Studio Brain coordinated {active_count} department signals into the next production move."
        return "Studio Brain created a provisional plan with limited department evidence."

    def _readiness_summary(
        self,
        status: StudioBrainReadinessStatus,
        ready: list[str],
        blocked: list[str],
        missing: list[str],
    ) -> str:
        if status == StudioBrainReadinessStatus.READY:
            return "Departments are ready for the next executive production move."
        if status == StudioBrainReadinessStatus.WAITING_CREATOR:
            return "A creator decision is needed before Studio Brain should dispatch production work."
        if blocked:
            return f"{', '.join(blocked[:3])} needs attention before full readiness."
        if missing:
            return "Studio Brain is operating with partial evidence; inspect missing context before relying on the plan."
        return "Readiness is emerging from available department context."

    def _list_strings(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item or "").strip()]

    def _list_dicts(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [self._model_dict(item) for item in value if self._model_dict(item)]


studio_brain_executive_service = StudioBrainExecutiveService()
