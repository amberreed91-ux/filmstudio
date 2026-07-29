"""
Crew Service - Implements System Orchestrator / Creative Director separation

This service handles:
- System Orchestrator: Pure workflow management (logical)
- Agent execution: Technical task performance (no creative authority)
- Escalation: When agents must defer to Creative Director
- Creative Director handling: User decisions on escalated tasks
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4

from app.models.crew import (
    AgentRole, TaskType, TaskStatus, ApprovalState, EscalationReason,
    TaskInput, TaskOutput, CrewTask,
    SystemOrchestrator, OrchestratorAction, OrchestratorDecision, CreativeDecision,
    ProjectOwnership, AGENT_CONFIGS,
    validate_agent_can_decide, should_escalate, is_creative_decision
)
from app.models.memory import MemoryType
from app.services.guardrails import guardrails
from app.services.conflicts import conflict_service
from app.services.memory import memory_service
from app.services.crew_intelligence_service import crew_intelligence_service
from app.models.crew_intelligence import CrewEvidenceRef, CrewReasoningType, CrewRisk

logger = logging.getLogger("studio-crew")
logger.setLevel(logging.DEBUG)


class CrewService:
    """
    Crew Service - Manages the film production crew with clear separation:
    
    - SYSTEM ORCHESTRATOR: Handles workflow, scheduling, handoffs (logical)
    - AGENTS: Execute tasks within their technical domain (no creative authority)
    - CREATIVE DIRECTOR (User): Makes all creative decisions via escalation
    """
    
    def __init__(self, storage=None):
        self.storage = storage
        self._tasks: Dict[str, CrewTask] = {}
        self._ownership: Dict[str, ProjectOwnership] = {}
        self._orchestrator = SystemOrchestrator()
        self._active_agents: Dict[str, Dict] = {}
        
        # Guardrails
        self._max_tasks_per_project = 1000
        self._max_recursion_depth = 10
        
        self._initialize_orchestrator()
    
    def _initialize_orchestrator(self):
        """Initialize the System Orchestrator"""
        logger.info("System Orchestrator initialized")
    
    # ========================================================================
    # PROJECT OWNERSHIP
    # ========================================================================
    
    def create_project(
        self, 
        project_id: str, 
        owner_user_id: str,
        creative_director_ids: List[str] = None
    ) -> ProjectOwnership:
        """Create project with owner and Creative Director(s)"""
        now = datetime.now().isoformat()
        
        ownership = ProjectOwnership(
            project_id=project_id,
            owner_user_id=owner_user_id,
            creative_director_ids=creative_director_ids or [owner_user_id],
            orchestrator_active=True,
            active_agent_ids=list(AGENT_CONFIGS.keys()),
            created_at=now,
            updated_at=now
        )
        
        self._ownership[project_id] = ownership
        logger.info(f"Created project {project_id} with owner {owner_user_id}")
        
        return ownership
    
    def get_ownership(self, project_id: str) -> Optional[ProjectOwnership]:
        return self._ownership.get(project_id)
    
    def can_access_project(self, project_id: str, user_id: str) -> bool:
        """Check if user can access project"""
        ownership = self._ownership.get(project_id)
        if not ownership:
            # No ownership registered - allow access (project created via main API)
            return True
        
        return (user_id == ownership.owner_user_id or 
                user_id in ownership.creative_director_ids or
                user_id in ownership.collaborator_ids)
    
    def is_creative_director(self, project_id: str, user_id: str) -> bool:
        """Check if user has Creative Director authority"""
        ownership = self._ownership.get(project_id)
        if not ownership:
            # No ownership - treat user as creative director for demo
            return True
        return user_id in ownership.creative_director_ids
    
    # ========================================================================
    # TASK MANAGEMENT - SYSTEM ORCHESTRATOR LOGIC
    # ========================================================================
    
    def create_task(
        self,
        project_id: str,
        agent_role: AgentRole,
        task_type: TaskType,
        title: str,
        description: str,
        input_data: Dict = None,
        depends_on: List[str] = None,
        priority: int = 5,
        requires_approval: bool = False,
        created_by: str = "user"
    ) -> tuple[Optional[CrewTask], Optional[str]]:
        """
        Create a new task - System Orchestrator handles placement.
        Returns tuple of (task, error_message).
        If error_message is not None, task creation failed.
        """
        
        # Guardrail: Check task creation is allowed
        guardrail_check = guardrails.check_task_creation(
            project_id=project_id,
            parent_task_id=None,
            depends_on=depends_on,
            created_by=created_by
        )
        
        if not guardrail_check["allowed"]:
            error = f"Task creation blocked: {', '.join(guardrail_check['failed_checks'])}"
            logger.error(error)
            return None, error
        
        # Guardrail: Check project task limit
        project_tasks = [t for t in self._tasks.values() if t.project_id == project_id]
        if len(project_tasks) >= self._max_tasks_per_project:
            error = f"Project {project_id} has reached task limit of {self._max_tasks_per_project}"
            logger.error(error)
            return None, error
        
        # Guardrail: Check recursion
        if depends_on:
            if not self._validate_dependency_depth(depends_on, 0):
                error = f"Dependency depth would exceed limit for project {project_id}"
                logger.error(error)
                return None, error
        
        # Guardrail: Validate task type for agent role
        if not self._validate_task_for_role(agent_role, task_type):
            valid_types = [t.value for t in self._get_valid_task_types(agent_role)]
            error = f"Task type '{task_type.value}' not valid for role '{agent_role.value}'. Valid types: {', '.join(valid_types)}"
            logger.error(error)
            return None, error
        
        now = datetime.now().isoformat()
        task_id = f"task-{uuid4().hex[:12]}"
        
        # Determine approval requirement
        approval_state = ApprovalState.PENDING if requires_approval else ApprovalState.NOT_REQUIRED
        
        task = CrewTask(
            task_id=task_id,
            project_id=project_id,
            agent_role=agent_role,
            task_type=task_type,
            assigned_agent_id=None,
            input=TaskInput(
                data=input_data or {},
                constraints={},
                quality_requirements={}
            ),
            output=None,
            status=TaskStatus.CREATED,
            approval_state=approval_state,
            depends_on=depends_on or [],
            blocks=[],
            progress=0,
            created_at=now,
            priority=priority,
            tags=[]
        )
        
        self._tasks[task_id] = task
        logger.info(f"Created task {task_id}: {title} for role {agent_role.value}")
        
        # Record in guardrails
        guardrails.record_task_created(task_id, project_id, depends_on=depends_on)
        
        # System Orchestrator: Determine initial action
        self._orchestrator_decide(task)
        
        return task, None
    
    def _get_valid_task_types(self, role: AgentRole) -> List[TaskType]:
        """Get valid task types for a given role"""
        valid_combinations = {
            AgentRole.PRODUCER: [TaskType.COORDINATION],
            AgentRole.RENDER_COORDINATOR: [TaskType.EXECUTION],
            AgentRole.SCRIPT_ANALYST: [TaskType.ANALYSIS],
            AgentRole.STORYBOARD_ARTIST: [TaskType.PLANNING, TaskType.EXECUTION],
            AgentRole.CINEMATOGRAPHER: [TaskType.PLANNING],
            AgentRole.PROMPT_ENGINEER: [TaskType.EXECUTION],
            AgentRole.QUALITY_REVIEWER: [TaskType.VALIDATION],
            AgentRole.EDITOR: [TaskType.REVIEW, TaskType.EXECUTION],
            AgentRole.CONTINUITY_SUPERVISOR: [TaskType.VALIDATION],
        }
        return valid_combinations.get(role, [])
    
    def _validate_dependency_depth(self, depends_on: List[str], depth: int) -> bool:
        """Validate recursion depth limit"""
        if depth >= self._max_recursion_depth:
            return False
        
        for task_id in depends_on:
            task = self._tasks.get(task_id)
            if task and task.depends_on:
                if not self._validate_dependency_depth(task.depends_on, depth + 1):
                    return False
        
        return True
    
    def _validate_task_for_role(self, role: AgentRole, task_type: TaskType) -> bool:
        """Validate that task type is appropriate for agent role"""
        return task_type in self._get_valid_task_types(role)
    
    def _orchestrator_decide(self, task: CrewTask):
        """System Orchestrator makes logical decision about task"""
        decision = self._orchestrator.decide_next_action(task, {})
        
        if decision.action == OrchestratorAction.ASSIGN:
            # Auto-assign to appropriate agent
            agent_id = self._find_available_agent(task.agent_role)
            if agent_id:
                self.assign_task(task.task_id, agent_id)
        
        elif decision.action == OrchestratorAction.BLOCK:
            task.status = TaskStatus.BLOCKED
            task.escalation = {
                "reason": "dependency_not_met",
                "waiting_on": task.depends_on,
                "orchestrator_action": "block"
            }
        
        elif decision.action == OrchestratorAction.ESCALATE:
            self._escalate_task(task, decision.escalation_reason or EscalationReason.RESOURCE_DECISION)
    
    def _find_available_agent(self, role: AgentRole) -> Optional[str]:
        """Find available agent for role"""
        # Simplified: return agent ID based on role
        return f"agent-{role.value}"
    
    # ========================================================================
    # TASK EXECUTION - AGENT WORK
    # ========================================================================
    
    def assign_task(self, task_id: str, agent_id: str) -> Optional[CrewTask]:
        """Assign task to agent - purely logical operation"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        task.assigned_agent_id = agent_id
        task.status = TaskStatus.ASSIGNED
        task.updated_at = datetime.now().isoformat()
        
        logger.info(f"Assigned task {task_id} to agent {agent_id}")
        
        return task
    
    def start_task(self, task_id: str) -> Optional[CrewTask]:
        """Start task execution - agent begins work
        
        CRITICAL: Agent MUST read memory before acting to ensure continuity.
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        if task.status != TaskStatus.ASSIGNED:
            logger.warning(f"Cannot start task {task_id} - not assigned")
            return None
        
        # READ MEMORY BEFORE ACTING - Critical for continuity
        scene_id = task.input.data.get("scene_id")
        
        # Get agent role from task
        agent_role = task.agent_role.value
        
        # Read relevant memory for this task
        memory_context = memory_service.get_context_for_agent(
            project_id=task.project_id,
            agent_role=agent_role,
            scene_id=scene_id
        )
        
        # Store memory context in task for agent to use
        task.input.data["_memory_context"] = memory_context
        
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        
        logger.info(f"Task {task_id} started - memory context loaded for {agent_role}")
        
        return task
    
    def complete_task(
        self, 
        task_id: str, 
        output_data: Dict,
        quality_metrics: Dict = None,
        warnings: List[str] = None
    ) -> Optional[CrewTask]:
        """Complete task with output - agent finishes work
        
        CRITICAL: Agent MUST update memory after completing tasks.
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        now = datetime.now().isoformat()
        
        # Create output
        task.output = TaskOutput(
            data=output_data,
            artifacts=output_data.get("artifacts", []),
            quality_metrics=quality_metrics or {},
            warnings=warnings or [],
            metadata={}
        )
        
        # Check if should escalate to Creative Director
        escalation_reason = should_escalate(task, task.output)
        
        if escalation_reason:
            task.status = TaskStatus.BLOCKED
            self._escalate_task(task, escalation_reason)
            return task
        
        # Check for conflicts with other tasks
        conflict_check = conflict_service.check_and_resolve(
            task_outputs=[{
                "task_id": task.task_id,
                "agent_role": task.agent_role.value,
                "project_id": task.project_id,
                "output": task.output.model_dump()
            }],
            project_id=task.project_id
        )
        
        if conflict_check.get("has_conflicts") and conflict_check.get("escalated"):
            task.status = TaskStatus.BLOCKED
            task.escalation = {
                "reason": "conflict",
                "description": "Conflict detected between agent outputs",
                "conflicts": conflict_check["conflicts"],
                "escalated_to": "system_orchestrator"
            }
            return task
        
        # Complete task
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.completed_at = now
        
        # UPDATE MEMORY AFTER COMPLETING - Critical for continuity
        self._update_memory_from_task(task, output_data)
        self._record_crew_intelligence_from_task(task, output_data, warnings or [])
        
        logger.info(f"Task {task_id} completed - memory updated")
        
        # Record completion in guardrails
        guardrails.record_task_completed(task_id, task.project_id)
        
        # Trigger dependent tasks (System Orchestrator logic)
        self._trigger_dependents(task)
        
        return task

    def _record_crew_intelligence_from_task(self, task: CrewTask, output_data: Dict, warnings: List[str]):
        """Persist advisory crew reasoning without changing task lifecycle semantics."""
        try:
            scene_id = output_data.get("scene_id") or task.input.data.get("scene_id")
            shot_id = output_data.get("shot_id") or task.input.data.get("shot_id")
            asset_id = output_data.get("asset_id") or task.input.data.get("asset_id")
            role = task.agent_role
            reasoning_type = self._reasoning_type_for_role(role)
            observation = self._observation_for_task_output(task, output_data)
            recommendation = self._recommendation_for_task_output(task, output_data)
            evidence_refs = [
                CrewEvidenceRef(
                    ref_type="task",
                    ref_id=task.task_id,
                    label=f"{role.value} task",
                    summary=f"Completed {task.task_type.value} task for {role.value}.",
                    source_service="CrewService",
                )
            ]
            risks = [
                CrewRisk(
                    risk_id=f"risk-{task.task_id}-{idx}",
                    category="task_warning",
                    severity="needs_attention" if task.escalation else "advisory",
                    summary=warning,
                    evidence_refs=evidence_refs,
                    requires_creator_decision=bool(task.escalation),
                )
                for idx, warning in enumerate(warnings or [])
                if warning
            ]
            role_context = crew_intelligence_service.build_role_context(
                project_id=task.project_id,
                agent_role=role,
                film_id=task.input.data.get("film_id") or task.input.data.get("project_id"),
                scene_id=scene_id,
            )
            crew_intelligence_service.create_reasoning_record(
                project_id=task.project_id,
                task_id=task.task_id,
                agent_role=role,
                reasoning_type=reasoning_type,
                scene_id=scene_id,
                shot_id=shot_id,
                asset_id=asset_id,
                observation=observation,
                context_used=["crew_task", "task_output"] + list(role_context.canonical_sources.keys()),
                inference=output_data.get("inference", ""),
                recommendation_summary=recommendation,
                creator_note=output_data.get("creator_note", ""),
                evidence_refs=evidence_refs,
                memory_refs=role_context.memory_refs,
                spine_refs=role_context.spine_refs,
                risks=risks,
                downstream_departments=self._downstream_departments_for_role(role),
                requires_creator_decision=bool(task.escalation),
                escalation_reason=(task.escalation or {}).get("reason") if task.escalation else None,
                metadata={
                    "task_status": task.status.value,
                    "task_type": task.task_type.value,
                    "output_keys": sorted(output_data.keys()),
                    "context_notes": role_context.context_notes,
                },
            )
        except Exception as exc:
            logger.warning("Failed to record crew intelligence for task %s: %s", task.task_id, exc)

    def _reasoning_type_for_role(self, role: AgentRole) -> CrewReasoningType:
        mapping = {
            AgentRole.PRODUCER: CrewReasoningType.PRODUCTION_COORDINATION,
            AgentRole.RENDER_COORDINATOR: CrewReasoningType.PROVIDER_READINESS,
            AgentRole.DIRECTOR: CrewReasoningType.CREATIVE_SYNTHESIS,
            AgentRole.SCRIPT_ANALYST: CrewReasoningType.ANALYSIS,
            AgentRole.STORYBOARD_ARTIST: CrewReasoningType.PLAN,
            AgentRole.CINEMATOGRAPHER: CrewReasoningType.STYLE_CHECK,
            AgentRole.PROMPT_ENGINEER: CrewReasoningType.HANDOFF_PREPARATION,
            AgentRole.EDITOR: CrewReasoningType.EDITORIAL_READ,
            AgentRole.CONTINUITY_SUPERVISOR: CrewReasoningType.CONTINUITY_CHECK,
            AgentRole.MEMORY_ARCHIVIST: CrewReasoningType.MEMORY_RECALL,
            AgentRole.QUALITY_REVIEWER: CrewReasoningType.VALIDATION,
            AgentRole.SYSTEM_ORCHESTRATOR: CrewReasoningType.PRODUCTION_COORDINATION,
        }
        return mapping.get(role, CrewReasoningType.ANALYSIS)

    def _observation_for_task_output(self, task: CrewTask, output_data: Dict) -> str:
        if output_data.get("observation"):
            return output_data["observation"]
        if output_data.get("scene_data"):
            return "The department produced scene-level analysis for the current task."
        if output_data.get("shot_plan"):
            return "The department produced a shot planning handoff for the current scene."
        if output_data.get("style_data"):
            return "The department produced visual language guidance for downstream generation."
        if output_data.get("feedback"):
            return "The department produced review feedback for the completed output."
        return f"{task.agent_role.value.replace('_', ' ').title()} completed a {task.task_type.value} task."

    def _recommendation_for_task_output(self, task: CrewTask, output_data: Dict) -> str:
        for key in ["recommendation_summary", "pacing_notes", "camera_choice", "result"]:
            value = output_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if task.escalation:
            return "Review this department output before the next production handoff."
        return "Crew reasoning is available for inspection and downstream handoff."

    def _downstream_departments_for_role(self, role: AgentRole) -> List[AgentRole]:
        mapping = {
            AgentRole.SCRIPT_ANALYST: [AgentRole.STORYBOARD_ARTIST],
            AgentRole.STORYBOARD_ARTIST: [AgentRole.CINEMATOGRAPHER, AgentRole.PROMPT_ENGINEER],
            AgentRole.CINEMATOGRAPHER: [AgentRole.PROMPT_ENGINEER],
            AgentRole.PROMPT_ENGINEER: [AgentRole.RENDER_COORDINATOR],
            AgentRole.RENDER_COORDINATOR: [AgentRole.QUALITY_REVIEWER],
            AgentRole.QUALITY_REVIEWER: [AgentRole.CONTINUITY_SUPERVISOR, AgentRole.EDITOR],
            AgentRole.EDITOR: [AgentRole.MEMORY_ARCHIVIST, AgentRole.DIRECTOR],
            AgentRole.CONTINUITY_SUPERVISOR: [AgentRole.MEMORY_ARCHIVIST, AgentRole.PROMPT_ENGINEER],
            AgentRole.MEMORY_ARCHIVIST: [AgentRole.DIRECTOR],
            AgentRole.PRODUCER: [AgentRole.SYSTEM_ORCHESTRATOR],
        }
        return mapping.get(role, [])
    
    def _update_memory_from_task(self, task: CrewTask, output_data: Dict):
        """Update memory based on task output
        
        This is how agents UPDATE memory:
        - Script Analyst updates scene memory with story beats
        - Cinematographer updates style/camera choices
        - Prompt Engineer stores generated shots
        - Quality Reviewer stores feedback
        - Creative Director overrides update with highest priority
        """
        project_id = task.project_id
        agent_role = task.agent_role.value
        scene_id = output_data.get("scene_id")
        
        # Map agent roles to memory types
        memory_updates = []
        
        if agent_role in ["script_analyst"]:
            # Script Analyst updates scene memory with story decisions / analysis results
            if "scene_data" in output_data:
                memory_updates.append({
                    "type": MemoryType.SCENE,
                    "data": output_data.get("scene_data", {})
                })
            # Also capture analysis notes
            if "pacing_notes" in output_data and scene_id:
                memory_updates.append({
                    "type": MemoryType.SCENE,
                    "data": {
                        "scene_id": scene_id,
                        "lighting_note": output_data.get("pacing_notes")
                    }
                })
        
        elif agent_role in ["cinematographer"]:
            # Cinematographer updates style memory
            if "style_data" in output_data:
                memory_updates.append({
                    "type": MemoryType.STYLE,
                    "data": output_data.get("style_data", {})
                })
            if "camera_choice" in output_data and scene_id:
                memory_updates.append({
                    "type": MemoryType.SCENE,
                    "data": {
                        "scene_id": scene_id,
                        "camera_choice": output_data.get("camera_choice")
                    }
                })
        
        elif agent_role in ["prompt_engineer"]:
            # Prompt Engineer stores generated shots
            if "generated_shot" in output_data and scene_id:
                memory_updates.append({
                    "type": MemoryType.SCENE,
                    "data": {
                        "scene_id": scene_id,
                        "generated_shot": output_data.get("generated_shot")
                    }
                })
        
        elif agent_role in ["render_coordinator"]:
            # Render coordinator stores shot status
            if "shot_id" in output_data and scene_id:
                memory_updates.append({
                    "type": MemoryType.SCENE,
                    "data": {
                        "scene_id": scene_id,
                        "generated_shot": output_data.get("shot_id")
                    }
                })
        
        elif agent_role in ["quality_reviewer"]:
            # Quality Reviewer stores feedback
            if "feedback" in output_data:
                memory_updates.append({
                    "type": MemoryType.REVIEW,
                    "data": output_data.get("feedback", {})
                })
        
        elif agent_role in ["editor"]:
            # Editor updates pacing/decisions
            if "pacing_notes" in output_data:
                memory_updates.append({
                    "type": MemoryType.STYLE,
                    "data": {"pacing_notes": output_data.get("pacing_notes")}
                })
        
        # Creative Director always has highest priority
        if self.is_creative_director(project_id, agent_role):
            if "creative_decision" in output_data:
                memory_updates.append({
                    "type": MemoryType.PROJECT,
                    "data": output_data.get("creative_decision", {})
                })
        
        # Apply all memory updates
        logger.info(f"DEBUG complete_task: Found {len(memory_updates)} potential memory updates")
        logger.info(f"DEBUG complete_task: output_data keys = {list(output_data.keys())}")
        logger.info(f"DEBUG complete_task: scene_id = {scene_id}")
        
        for update in memory_updates:
            try:
                logger.info(f"DEBUG: Applying memory update: {update}")
                memory_service.update_memory(
                    project_id=project_id,
                    memory_type=update["type"],
                    data=update["data"],
                    agent_id=agent_role,
                    task_id=task.task_id
                )
            except Exception as e:
                logger.warning(f"Failed to update memory: {e}")
    
    def _escalate_task(self, task: CrewTask, reason: EscalationReason):
        """Escalate task to Creative Director - agent cannot decide"""
        now = datetime.now().isoformat()
        
        task.status = TaskStatus.BLOCKED
        task.escalation = {
            "reason": reason.value,
            "description": self._get_escalation_description(reason),
            "requires_creative_decision": is_creative_decision(reason.value),
            "escalated_at": now
        }
        task.escalated_at = now
        
        logger.info(f"Task {task.task_id} escalated to Creative Director: {reason.value}")
    
    def _get_escalation_description(self, reason: EscalationReason) -> str:
        """Get human-readable escalation description"""
        descriptions = {
            EscalationReason.CREATIVE_DECISION: "Subjective creative choice required",
            EscalationReason.QUALITY_CONCERN: "Output quality below threshold",
            EscalationReason.CONFLICT: "Multiple valid options, cannot decide",
            EscalationReason.RESOURCE_DECISION: "Budget or timeline impact requires decision",
            EscalationReason.POLICY_VIOLATION: "Request outside established parameters",
            EscalationReason.MANUAL_REVIEW_REQUESTED: "Agent requested human review",
        }
        return descriptions.get(reason, "Requires Creative Director review")
    
    def _trigger_dependents(self, completed_task: CrewTask):
        """Trigger tasks that depend on completed task"""
        for task_id in completed_task.blocks:
            dependent = self._tasks.get(task_id)
            if dependent and dependent.status == TaskStatus.PENDING_INPUT:
                # Check if all dependencies are met
                deps_met = all(
                    self._tasks.get(d_id) and 
                    self._tasks[d_id].status == TaskStatus.COMPLETED
                    for d_id in dependent.depends_on
                )
                if deps_met:
                    dependent.status = TaskStatus.CREATED
                    logger.info(f"Dependent task {task_id} now ready")
                    # Orchestrator decides what to do next
                    self._orchestrator_decide(dependent)
    
    # ========================================================================
    # CREATIVE DIRECTOR DECISIONS
    # ========================================================================
    
    def apply_creative_decision(
        self,
        task_id: str,
        user_id: str,
        decision: CreativeDecision
    ) -> Optional[CrewTask]:
        """Apply Creative Director's decision to a task"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        # Verify user has Creative Director authority
        if not self.is_creative_director(task.project_id, user_id):
            logger.warning(f"User {user_id} attempted Creative Director action without authority")
            return None
        
        now = datetime.now().isoformat()
        
        task.creative_decision = decision.model_dump()
        task.creative_decision["created_at"] = now
        
        # Apply decision
        if decision.decision == "APPROVE":
            task.approval_state = ApprovalState.APPROVED
            task.status = TaskStatus.COMPLETED
            task.completed_at = now
            task.escalation = None
            logger.info(f"Creative Director approved task {task_id}")
        
        elif decision.decision == "REJECT":
            task.approval_state = ApprovalState.REJECTED
            task.status = TaskStatus.FAILED
            logger.info(f"Creative Director rejected task {task_id}")
        
        elif decision.decision == "NEEDS_REVISION":
            task.approval_state = ApprovalState.NEEDS_REVISION
            task.status = TaskStatus.CREATED
            task.progress = 0
            task.output = None
            task.escalation = None
            # Task goes back to agent for rework
            self._orchestrator_decide(task)
            logger.info(f"Creative Director requested revision for task {task_id}")
        
        elif decision.decision == "REDIRECT":
            task.status = TaskStatus.CREATED
            if decision.redirect_to_role:
                task.agent_role = decision.redirect_to_role
            task.escalation = None
            self._orchestrator_decide(task)
            logger.info(f"Creative Director redirected task {task_id}")
        
        elif decision.decision == "TAKE_OVER":
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.completed_at = now
            task.approval_state = ApprovalState.APPROVED
            logger.info(f"Creative Director took over task {task_id}")
        
        # Trigger dependents if completed
        if task.status == TaskStatus.COMPLETED:
            self._trigger_dependents(task)
        
        return task
    
    # ========================================================================
    # QUERIES
    # ========================================================================
    
    def get_task(self, task_id: str) -> Optional[CrewTask]:
        return self._tasks.get(task_id)
    
    def get_project_tasks(
        self, 
        project_id: str, 
        status: Optional[TaskStatus] = None,
        escalated_only: bool = False
    ) -> List[CrewTask]:
        """Get tasks for project, optionally filtered"""
        tasks = [t for t in self._tasks.values() if t.project_id == project_id]
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        if escalated_only:
            tasks = [t for t in tasks if t.escalation is not None]
        
        return sorted(tasks, key=lambda t: t.priority, reverse=True)
    
    def get_creatives_need_attention(self, project_id: str) -> List[CrewTask]:
        """Get tasks that need Creative Director decision"""
        return self.get_project_tasks(project_id, escalated_only=True)
    
    def get_task_metrics(self, project_id: str) -> Dict:
        """Get project task metrics"""
        tasks = self.get_project_tasks(project_id)
        
        by_status = {}
        by_role = {}
        
        for task in tasks:
            by_status[task.status.value] = by_status.get(task.status.value, 0) + 1
            by_role[task.agent_role.value] = by_role.get(task.agent_role.value, 0) + 1
        
        escalated = len([t for t in tasks if t.escalation])
        
        return {
            "total": len(tasks),
            "by_status": by_status,
            "by_role": by_role,
            "escalated_to_creative_director": escalated,
            "completion_rate": len([t for t in tasks if t.status == TaskStatus.COMPLETED]) / max(len(tasks), 1)
        }


# Global service instance
crew_service = CrewService()
