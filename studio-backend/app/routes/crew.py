"""
Crew Routes - API for the film production crew with Orchestrator/Director separation
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Any
from pydantic import BaseModel

from app.models.crew import (
    AgentRole, TaskType, TaskStatus, EscalationReason,
    ProjectOwnership, CreativeDecision
)
from app.models.crew_intelligence import (
    CrewDeliberationStatus,
    CrewHandoffStatus,
    CrewReasoningType,
)
from app.services.crew import crew_service
from app.services.crew_intelligence_service import (
    CrewIntelligenceStateError,
    CrewIntelligenceValidationError,
    crew_intelligence_service,
)
from app.services.conflicts import conflict_service, ConflictService
from app.services.guardrails import guardrails, TaskGuardrails
from app.services.adaptation import adaptation_engine
from app.services.deviation_engine import deviation_engine
from app.services.authority_hierarchy import authority_hierarchy, DecisionSource, SceneIntent
from app.services.scene_evolution import evolution_tracker

router = APIRouter(prefix="/api/f51/studio/crew", tags=["crew"])


def get_current_user_id() -> str:
    """Placeholder - would use real auth in production"""
    return "user-demo"


# ==================== PROJECT SETUP ====================

@router.post("/projects/{project_id}/init")
def init_project(
    project_id: str,
    creative_director_ids: Optional[List[str]] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Initialize project with ownership and Creative Director(s)"""
    if creative_director_ids is None:
        creative_director_ids = [user_id]
    
    return crew_service.create_project(project_id, user_id, creative_director_ids)


@router.get("/projects/{project_id}")
def get_project(project_id: str, user_id: str = Depends(get_current_user_id)):
    """Get project ownership and status"""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    ownership = crew_service.get_ownership(project_id)
    metrics = crew_service.get_task_metrics(project_id)
    
    return {
        "ownership": ownership,
        "metrics": metrics
    }


# ==================== TASK CREATION ====================

class CreateTaskRequest(BaseModel):
    agent_role: str
    task_type: str
    title: str
    description: str
    input_data: dict = {}
    depends_on: List[str] = []
    priority: int = 5
    requires_approval: bool = False


@router.post("/projects/{project_id}/tasks")
def create_task(
    project_id: str,
    request: CreateTaskRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Create a new crew task - handled by System Orchestrator"""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    role = AgentRole(request.agent_role)
    task_type = TaskType(request.task_type)
    
    created_by = "user" if not request.agent_role.startswith("agent-") else request.agent_role
    
    task, error = crew_service.create_task(
        project_id=project_id,
        agent_role=role,
        task_type=task_type,
        title=request.title,
        description=request.description,
        input_data=request.input_data,
        depends_on=request.depends_on,
        priority=request.priority,
        requires_approval=request.requires_approval,
        created_by=created_by
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return task


# ==================== TASK QUERIES ====================

@router.get("/projects/{project_id}/tasks")
def get_project_tasks(
    project_id: str,
    status: Optional[str] = None,
    escalated_only: bool = False,
    user_id: str = Depends(get_current_user_id)
):
    """Get tasks for a project"""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    task_status = TaskStatus(status) if status else None
    return crew_service.get_project_tasks(project_id, task_status, escalated_only)


@router.get("/projects/{project_id}/needs-attention")
def get_creative_attention(
    project_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Get tasks that need Creative Director decision"""
    if not crew_service.is_creative_director(project_id, user_id):
        raise HTTPException(status_code=403, detail="Only Creative Director can view escalation queue")
    
    return crew_service.get_creatives_need_attention(project_id)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user_id: str = Depends(get_current_user_id)):
    """Get specific task"""
    task = crew_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not crew_service.can_access_project(task.project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return task


# ==================== TASK EXECUTION ====================

@router.post("/tasks/{task_id}/start")
def start_task(task_id: str, user_id: str = Depends(get_current_user_id)):
    """Start task execution - agent begins work"""
    task = crew_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not crew_service.can_access_project(task.project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return crew_service.start_task(task_id)


class CompleteTaskRequest(BaseModel):
    output_data: dict
    quality_metrics: dict = {}
    warnings: List[str] = []


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Complete task with output - may trigger escalation to Creative Director"""
    task = crew_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not crew_service.can_access_project(task.project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return crew_service.complete_task(
        task_id, 
        request.output_data,
        request.quality_metrics,
        request.warnings
    )


# ==================== CREATIVE DIRECTOR DECISIONS ====================

class CreativeDecisionRequest(BaseModel):
    decision: str  # APPROVE, REJECT, NEEDS_REVISION, REDIRECT, TAKE_OVER
    feedback: Optional[str] = None
    redirect_to_role: Optional[str] = None
    notes: Optional[str] = None


@router.post("/tasks/{task_id}/decision")
def apply_creative_decision(
    task_id: str,
    request: CreativeDecisionRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Apply Creative Director's decision to an escalated task"""
    task = crew_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Verify creative director authority
    if not crew_service.is_creative_director(task.project_id, user_id):
        raise HTTPException(
            status_code=403, 
            detail="Only Creative Director can make decisions on escalated tasks"
        )
    
    decision = CreativeDecision(
        task_id=task_id,
        decision=request.decision,
        feedback=request.feedback,
        redirect_to_role=AgentRole(request.redirect_to_role) if request.redirect_to_role else None,
        notes=request.notes,
        user_id=user_id
    )
    
    return crew_service.apply_creative_decision(task_id, user_id, decision)


# ==================== AGENT INFO ====================

@router.get("/agents")
def list_agents():
    """List all available agents with their capabilities"""
    from app.models.crew import AGENT_CONFIGS
    
    return [
        {
            "agent_id": f"agent-{role.value}",
            "role": role.value,
            "name": config["name"],
            "description": config["description"],
            "capabilities": [c.model_dump() for c in config["capabilities"]],
            "is_creative": config["is_creative"],
            "escalates_on": [e.value for e in config.get("escalates_on", [])]
        }
        for role, config in AGENT_CONFIGS.items()
    ]


@router.get("/orchestrator/status")
def get_orchestrator_status():
    """Get System Orchestrator status"""
    return {
        "status": "active",
        "description": "System Orchestrator manages workflow, scheduling, and handoffs",
        "separation": {
            "orchestrator_responsibility": "Pure logical workflow management - no creative authority",
            "creative_director_responsibility": "All creative decisions, approvals, overrides",
            "agent_responsibility": "Technical execution within defined parameters"
        }
    }


# ==================== ADVANCED CREW INTELLIGENCE ====================

class CreateCrewHandoffRequest(BaseModel):
    source_role: str
    target_role: str
    context_summary: str
    source_task_id: Optional[str] = None
    target_task_id: Optional[str] = None
    scene_id: Optional[str] = None
    shot_id: Optional[str] = None
    asset_id: Optional[str] = None
    requirements: List[str] = []
    open_questions: List[str] = []
    evidence_refs: List[dict] = []
    risks: List[dict] = []
    metadata: dict = {}


class UpdateCrewHandoffRequest(BaseModel):
    status: str
    failed_reason: Optional[str] = None
    metadata: dict = {}


class CreateCrewDeliberationRequest(BaseModel):
    participating_roles: List[str]
    issue_summary: str
    triggering_reasoning_ids: List[str] = []
    triggering_task_ids: List[str] = []
    points_of_agreement: List[str] = []
    points_of_tension: List[str] = []
    recommended_resolution: str = ""
    requires_creator_decision: bool = False
    creator_question: Optional[str] = None
    scene_id: Optional[str] = None
    evidence_refs: List[dict] = []
    risks: List[dict] = []
    metadata: dict = {}


class ResolveCrewDeliberationRequest(BaseModel):
    resolution_summary: str


@router.get("/projects/{project_id}/intelligence")
def get_crew_intelligence_overview(
    project_id: str,
    recent_limit: int = 10,
    handoff_limit: int = 10,
    deliberation_limit: int = 10,
    user_id: str = Depends(get_current_user_id),
):
    """Get bounded project-level crew intelligence overview."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return crew_intelligence_service.get_project_overview(
        project_id=project_id,
        recent_limit=recent_limit,
        handoff_limit=handoff_limit,
        deliberation_limit=deliberation_limit,
    )


@router.get("/projects/{project_id}/intelligence/departments")
def get_crew_department_profiles(project_id: str, user_id: str = Depends(get_current_user_id)):
    """List all crew department profiles and authority boundaries."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return crew_intelligence_service.get_department_profiles(project_id)


@router.get("/projects/{project_id}/intelligence/reasoning")
def list_crew_reasoning(
    project_id: str,
    agent_role: Optional[str] = None,
    reasoning_type: Optional[str] = None,
    scene_id: Optional[str] = None,
    task_id: Optional[str] = None,
    requires_creator_decision: Optional[bool] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List persisted crew reasoning records."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    filters: dict[str, Any] = {}
    if agent_role:
        filters["agent_role"] = AgentRole(agent_role).value
    if reasoning_type:
        filters["reasoning_type"] = CrewReasoningType(reasoning_type).value
    if scene_id:
        filters["scene_id"] = scene_id
    if task_id:
        filters["task_id"] = task_id
    if requires_creator_decision is not None:
        filters["requires_creator_decision"] = requires_creator_decision
    if status:
        filters["status"] = status
    items = crew_intelligence_service.list_reasoning_records(project_id, filters=filters, limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset, "has_more": len(items) == limit}


@router.get("/projects/{project_id}/intelligence/reasoning/{reasoning_id}")
def get_crew_reasoning(project_id: str, reasoning_id: str, user_id: str = Depends(get_current_user_id)):
    """Get one crew reasoning record."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    record = crew_intelligence_service.get_reasoning_record(reasoning_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Crew reasoning record not found")
    return record


@router.get("/projects/{project_id}/intelligence/handoffs")
def list_crew_handoffs(
    project_id: str,
    source_role: Optional[str] = None,
    target_role: Optional[str] = None,
    scene_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List crew handoff packets."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    filters: dict[str, Any] = {}
    if source_role:
        filters["source_role"] = AgentRole(source_role).value
    if target_role:
        filters["target_role"] = AgentRole(target_role).value
    if scene_id:
        filters["scene_id"] = scene_id
    if status:
        filters["status"] = CrewHandoffStatus(status).value
    items = crew_intelligence_service.list_handoffs(project_id, filters=filters, limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset, "has_more": len(items) == limit}


@router.post("/projects/{project_id}/intelligence/handoffs")
def create_crew_handoff(
    project_id: str,
    request: CreateCrewHandoffRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a cross-department crew handoff."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        return crew_intelligence_service.create_handoff(
            project_id=project_id,
            source_role=AgentRole(request.source_role),
            target_role=AgentRole(request.target_role),
            context_summary=request.context_summary,
            source_task_id=request.source_task_id,
            target_task_id=request.target_task_id,
            scene_id=request.scene_id,
            shot_id=request.shot_id,
            asset_id=request.asset_id,
            requirements=request.requirements,
            open_questions=request.open_questions,
            evidence_refs=request.evidence_refs,
            risks=request.risks,
            metadata={**request.metadata, "created_by": user_id},
        )
    except CrewIntelligenceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/projects/{project_id}/intelligence/handoffs/{handoff_id}")
def update_crew_handoff(
    project_id: str,
    handoff_id: str,
    request: UpdateCrewHandoffRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update crew handoff lifecycle status."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    handoff = crew_intelligence_service.get_handoff(handoff_id)
    if not handoff or handoff.project_id != project_id:
        raise HTTPException(status_code=404, detail="Crew handoff not found")
    try:
        updated = crew_intelligence_service.update_handoff_status(
            handoff_id=handoff_id,
            status=CrewHandoffStatus(request.status),
            actor_id=user_id,
            failed_reason=request.failed_reason,
            metadata=request.metadata,
        )
    except CrewIntelligenceStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return updated


@router.get("/projects/{project_id}/intelligence/deliberations")
def list_crew_deliberations(
    project_id: str,
    status: Optional[str] = None,
    scene_id: Optional[str] = None,
    requires_creator_decision: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List crew deliberations."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = CrewDeliberationStatus(status).value
    if scene_id:
        filters["scene_id"] = scene_id
    if requires_creator_decision is not None:
        filters["requires_creator_decision"] = requires_creator_decision
    items = crew_intelligence_service.list_deliberations(project_id, filters=filters, limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset, "has_more": len(items) == limit}


@router.get("/projects/{project_id}/intelligence/deliberations/{deliberation_id}")
def get_crew_deliberation(project_id: str, deliberation_id: str, user_id: str = Depends(get_current_user_id)):
    """Get one crew deliberation."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    record = crew_intelligence_service.get_deliberation(deliberation_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Crew deliberation not found")
    return record


@router.post("/projects/{project_id}/intelligence/deliberations")
def create_crew_deliberation(
    project_id: str,
    request: CreateCrewDeliberationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a structured crew deliberation."""
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        return crew_intelligence_service.create_deliberation(
            project_id=project_id,
            participating_roles=[AgentRole(role) for role in request.participating_roles],
            issue_summary=request.issue_summary,
            triggering_reasoning_ids=request.triggering_reasoning_ids,
            triggering_task_ids=request.triggering_task_ids,
            points_of_agreement=request.points_of_agreement,
            points_of_tension=request.points_of_tension,
            recommended_resolution=request.recommended_resolution,
            requires_creator_decision=request.requires_creator_decision,
            creator_question=request.creator_question,
            scene_id=request.scene_id,
            evidence_refs=request.evidence_refs,
            risks=request.risks,
            metadata={**request.metadata, "created_by": user_id},
        )
    except CrewIntelligenceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/projects/{project_id}/intelligence/deliberations/{deliberation_id}")
def resolve_crew_deliberation(
    project_id: str,
    deliberation_id: str,
    request: ResolveCrewDeliberationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Resolve a crew deliberation. Creator-required deliberations need Creative Director authority."""
    record = crew_intelligence_service.get_deliberation(deliberation_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="Crew deliberation not found")
    if record.requires_creator_decision and not crew_service.is_creative_director(project_id, user_id):
        raise HTTPException(status_code=403, detail="Only Creative Director can resolve this deliberation")
    updated = crew_intelligence_service.resolve_deliberation(deliberation_id, user_id, request.resolution_summary)
    return updated


@router.get("/projects/{project_id}/intelligence/attention")
def get_crew_creator_attention(project_id: str, user_id: str = Depends(get_current_user_id)):
    """Get crew intelligence items needing creator attention."""
    if not crew_service.is_creative_director(project_id, user_id):
        raise HTTPException(status_code=403, detail="Only Creative Director can view crew attention")
    return crew_intelligence_service.get_creator_attention(project_id)


# ==================== CONFLICT RESOLUTION ====================

@router.get("/conflicts")
def get_conflicts(project_id: Optional[str] = None):
    """Get conflict history"""
    return conflict_service.get_conflicts(project_id)


@router.get("/conflicts/audit")
def get_audit_trail(field: Optional[str] = None):
    """Get decision audit trail"""
    return conflict_service.get_audit_trail(field)


# ==================== GUARDRAILS ====================

@router.get("/guardrails/status")
def get_guardrails_status():
    """Get guardrails system status"""
    return {
        "metrics": guardrails.get_metrics(),
        "config": {
            "max_recursion_depth": guardrails.config.MAX_RECURSION_DEPTH,
            "max_tasks_per_project": guardrails.config.MAX_TASKS_PER_PROJECT,
            "max_child_tasks": guardrails.config.MAX_CHILD_TASKS,
            "rate_limits": guardrails.config.RATE_LIMITS
        }
    }


@router.get("/guardrails/project/{project_id}")
def get_project_guardrails_status(project_id: str):
    """Get guardrails status for specific project"""
    return {
        "project_id": project_id,
        "is_stopped": guardrails.is_project_stopped(project_id),
        "metrics": guardrails.get_metrics()
    }


@router.post("/guardrails/project/{project_id}/reset")
def reset_project_guardrails(project_id: str):
    """Reset guardrails for a project after resolving issues"""
    guardrails.reset_project(project_id)
    return {"success": True, "project_id": project_id}


@router.post("/guardrails/project/{project_id}/emergency-stop")
def emergency_stop_project(project_id: str, reason: str = "Manual emergency stop"):
    """Emergency stop a project's task generation"""
    return guardrails.emergency_stop(project_id, reason)


# ==================== AGENT EXECUTION LOOP ====================

from app.services.agent_executor import (
    agent_executor,
    start_project_agent_loop,
    stop_project_agent_loop,
    get_agent_loop_status
)


@router.post("/projects/{project_id}/agent-loop/start")
def start_agent_loop(project_id: str, user_id: str = Depends(get_current_user_id)):
    """
    Start the autonomous agent execution loop for a project.
    
    This activates the agent-driven workflow where crew agents will:
    1. Continuously poll for pending tasks
    2. Execute tasks based on their role
    3. Update memories with results
    4. Automatically hand off to next agent
    
    The loop runs asynchronously and can be monitored via /agent-loop/status.
    """
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if loop is already running
    status = get_agent_loop_status(project_id)
    if status.get("loop_active"):
        return {
            "message": f"Agent loop already running for project {project_id}",
            "project_id": project_id,
            "state": status.get("state"),
            "agent_loop_active": True,
            "already_running": True
        }
    
    result = start_project_agent_loop(project_id)
    
    # Handle gracefully if loop couldn't start (e.g., already exists)
    if not result.get("success"):
        error = result.get("error", "")
        if "already" in error.lower() or "exist" in error.lower():
            return {
                "message": f"Agent loop already running for project {project_id}",
                "project_id": project_id,
                "state": status.get("state", "running"),
                "agent_loop_active": True,
                "already_running": True
            }
        raise HTTPException(status_code=500, detail=error)
    
    return {
        "message": f"Agent loop started for project {project_id}",
        "project_id": project_id,
        "state": result.get("state"),
        "agent_loop_active": True
    }


@router.post("/projects/{project_id}/agent-loop/stop")
def stop_agent_loop(project_id: str, user_id: str = Depends(get_current_user_id)):
    """
    Stop the autonomous agent execution loop for a project.
    
    This halts all agent activity for the project. In-flight tasks
    will be completed or marked as interrupted.
    """
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = stop_project_agent_loop(project_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to stop loop"))
    
    return {
        "message": f"Agent loop stopped for project {project_id}",
        "project_id": project_id,
        "agent_loop_active": False
    }


@router.get("/projects/{project_id}/agent-loop/status")
def get_agent_loop_status_endpoint(
    project_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get the status of the agent execution loop for a project.
    
    Returns:
    - Whether the loop is active
    - Number of tasks processed
    - Current state of the executor
    """
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return get_agent_loop_status(project_id)


@router.get("/agent-loop/global-status")
def get_global_agent_status():
    """
    Get the global status of all agent loops.
    
    Returns information about all active project loops.
    """
    return get_agent_loop_status()


@router.post("/projects/{project_id}/agent-loop/trigger")
def trigger_agent_execution(
    project_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Trigger a single iteration of agent execution.
    
    This allows manual triggering of agent work without starting
    the full autonomous loop. Useful for testing or step-by-step workflows.
    """
    if not crew_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.services.agent_executor import agent_executor
    
    # Get pending tasks
    pending = crew_service.get_project_tasks(
        project_id, 
        status=TaskStatus.CREATED
    )
    
    results = []
    for task in pending[:5]:  # Process up to 5 tasks
        # Execute synchronously for manual trigger
        try:
            from app.services.agent_executor import AgentExecutor
            executor = AgentExecutor()
            
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            output = loop.run_until_complete(executor._execute_task(task))
            loop.close()
            
            results.append({
                "task_id": task.task_id,
                "status": "executed",
                "output": output
            })
        except Exception as e:
            results.append({
                "task_id": task.task_id,
                "status": "error",
                "error": str(e)
            })
    
    return {
        "project_id": project_id,
        "tasks_triggered": len(results),
        "results": results
    }


# ========================================================================
# ADAPTATION & LEARNING
# ========================================================================

class FeedbackRequest(BaseModel):
    pattern_type: str
    pattern_value: str
    approved: bool
    scene_id: Optional[str] = None
    render_job_id: Optional[str] = None
    notes: Optional[str] = None


class UserOverrideRequest(BaseModel):
    key: str
    value: str


class StyleBoundaryRequest(BaseModel):
    boundaries: dict


@router.get("/projects/{project_id}/adaptation/patterns")
def get_established_patterns(project_id: str):
    """
    Get all established patterns for a project.
    
    Returns patterns that have been reinforced through feedback.
    """
    patterns = adaptation_engine.get_project_established_patterns(project_id)
    return {
        "project_id": project_id,
        "patterns": patterns
    }


@router.get("/projects/{project_id}/adaptation/decisions")
def get_adaptation_decisions(
    project_id: str,
    agent_role: Optional[str] = None,
    limit: int = 50
):
    """
    Get adaptive decision log for traceability.
    
    Shows what decisions were made, why, and what memory was used.
    """
    decisions = adaptation_engine.get_decision_log(project_id, agent_role, limit)
    return {
        "project_id": project_id,
        "decisions": decisions,
        "count": len(decisions)
    }


@router.get("/projects/{project_id}/adaptation/evolution")
def get_evolution_metrics(project_id: str):
    """
    Get metrics showing how behavior has evolved over time.
    
    Returns feedback counts, success rates, and evolution phase.
    """
    metrics = adaptation_engine.get_evolution_metrics(project_id)
    return {
        "project_id": project_id,
        "metrics": metrics
    }


@router.post("/projects/{project_id}/adaptation/feedback")
def record_feedback(project_id: str, request: FeedbackRequest):
    """
    Record feedback for pattern learning.
    
    When a render is approved or rejected, record what patterns
    (camera angle, lighting, etc.) contributed to the outcome.
    """
    feedback_id = adaptation_engine.record_feedback(
        project_id=project_id,
        feedback_type="user_feedback",
        pattern_type=request.pattern_type,
        pattern_value=request.pattern_value,
        approved=request.approved,
        scene_id=request.scene_id,
        render_job_id=request.render_job_id,
        notes=request.notes
    )
    
    return {
        "feedback_id": feedback_id,
        "approved": request.approved,
        "pattern": f"{request.pattern_type}:{request.pattern_value}"
    }


@router.post("/projects/{project_id}/adaptation/user-override")
def set_user_override(project_id: str, request: UserOverrideRequest):
    """
    Set a user override - always takes priority over adaptive decisions.
    
    Use this to enforce specific styles or prevent drift.
    """
    adaptation_engine.set_user_override(project_id, request.key, request.value)
    
    return {
        "key": request.key,
        "value": request.value,
        "message": "User override set - will take priority over adaptive behavior"
    }


@router.post("/projects/{project_id}/adaptation/style-boundaries")
def set_style_boundaries(project_id: str, request: StyleBoundaryRequest):
    """
    Set style boundaries for a project.
    
    Defines acceptable ranges for patterns to prevent drift.
    """
    adaptation_engine.set_style_boundaries(project_id, request.boundaries)
    
    return {
        "boundaries": request.boundaries,
        "message": "Style boundaries set - adaptation will stay within these limits"
    }


@router.get("/projects/{project_id}/adaptation/suggestions")
def get_pattern_suggestions(
    project_id: str,
    pattern_type: str,
    limit: int = 5
):
    """
    Get ranked pattern suggestions with confidence scores.
    
    Useful for understanding what patterns are working well.
    """
    suggestions = adaptation_engine.get_pattern_suggestions(
        project_id, pattern_type, limit
    )
    
    return {
        "project_id": project_id,
        "pattern_type": pattern_type,
        "suggestions": [
            {"value": value, "confidence": score}
            for value, score in suggestions
        ]
    }


@router.post("/projects/{project_id}/adaptation/consistency-check")
def check_consistency(
    project_id: str,
    pattern_type: str,
    proposed_value: str,
    scene_id: Optional[str] = None
):
    """
    Check if a proposed value is consistent with established patterns.
    
    Returns whether the value is acceptable or if it contradicts prior work.
    """
    is_consistent, warning = adaptation_engine.check_consistency(
        project_id, pattern_type, proposed_value, scene_id
    )
    
    return {
        "project_id": project_id,
        "pattern_type": pattern_type,
        "proposed_value": proposed_value,
        "consistent": is_consistent,
        "warning": warning
    }


# ========================================================================
# PATTERN DEVIATION ENGINE
# ========================================================================

class DeviationCheckRequest(BaseModel):
    scene_context: dict
    scene_intensity: float = 0.5


@router.post("/projects/{project_id}/deviation/check")
def check_deviation_opportunity(
    project_id: str,
    request: DeviationCheckRequest
):
    """
    Check if current scene presents a deviation opportunity.
    
    Analyzes intensity, turning points, and pattern saturation
    to determine if deviation should be applied.
    """
    opportunity = deviation_engine.analyze_deviation_opportunity(
        project_id,
        request.scene_context,
        request.scene_intensity
    )
    
    return {
        "project_id": project_id,
        "should_deviate": opportunity.should_deviate,
        "trigger": opportunity.trigger.value if opportunity.trigger else None,
        "deviation_type": opportunity.deviation_type.value if opportunity.deviation_type else None,
        "proposed_value": opportunity.proposed_value,
        "reason": opportunity.reason,
        "safety_check_passed": opportunity.safety_check_passed,
        "intensity_score": opportunity.intensity_score,
        "saturation_level": opportunity.saturation_level
    }


@router.post("/projects/{project_id}/deviation/apply")
def apply_deviation(
    project_id: str,
    request: DeviationCheckRequest
):
    """
    Apply deviation if appropriate - returns DeviationResult.
    
    Main entry point for deviation application with full result.
    """
    result = deviation_engine.should_apply_deviation(
        project_id,
        request.scene_context,
        request.scene_intensity
    )
    
    return {
        "deviation_applied": result.deviation_applied,
        "deviation_reason": result.deviation_reason,
        "original_pattern": result.original_pattern,
        "deviated_pattern": result.deviated_pattern,
        "deviation_type": result.deviation_type.value if result.deviation_type else None,
        "trigger": result.trigger.value if result.trigger else None,
        "safety_respected": result.safety_respected,
        "within_boundaries": result.within_boundaries,
        "emotional_impact_expected": result.emotional_impact_expected
    }


@router.get("/projects/{project_id}/deviation/history")
def get_deviation_history(
    project_id: str,
    limit: int = 50
):
    """Get deviation history for the project."""
    history = deviation_engine.get_deviation_history(project_id, limit)
    return {
        "project_id": project_id,
        "deviations": history,
        "count": len(history)
    }


@router.get("/projects/{project_id}/deviation/stats")
def get_deviation_stats(project_id: str):
    """Get deviation statistics."""
    stats = deviation_engine.get_deviation_stats(project_id)
    return {
        "project_id": project_id,
        "stats": stats
    }


class CustomInversionRequest(BaseModel):
    pattern_type: str
    inversions: dict


@router.post("/projects/{project_id}/deviation/custom-inversions")
def set_custom_inversions(
    project_id: str,
    request: CustomInversionRequest
):
    """Set custom inversion map for a pattern type."""
    deviation_engine.set_custom_inversions(
        project_id,
        request.pattern_type,
        request.inversions
    )
    
    return {
        "project_id": project_id,
        "pattern_type": request.pattern_type,
        "inversions": request.inversions,
        "message": "Custom inversions set"
    }


@router.post("/projects/{project_id}/deviation/thresholds")
def set_deviation_thresholds(
    project_id: str,
    high_intensity: float = 0.7,
    saturation: float = 0.8
):
    """Configure deviation thresholds for the project."""
    deviation_engine.set_thresholds(high_intensity, saturation)
    
    return {
        "project_id": project_id,
        "high_intensity_threshold": high_intensity,
        "saturation_threshold": saturation,
        "message": "Thresholds configured"
    }


# ========================================================================
# CREATIVE AUTHORITY HIERARCHY
# ========================================================================

class UserOverrideRequest(BaseModel):
    decision_type: str
    value: Any
    reason: Optional[str] = ""


class SceneIntentRequest(BaseModel):
    scene_id: str
    scene_type: Optional[str] = ""
    emotion: Optional[str] = ""
    genre: Optional[str] = ""
    visual_goal: Optional[str] = ""
    emotional_goal: Optional[str] = ""
    pacing: Optional[str] = "medium"
    intensity: Optional[float] = 0.5
    is_turning_point: Optional[bool] = False
    narrative_beat: Optional[str] = ""


class DecisionConflictRequest(BaseModel):
    decision_type: str
    scene_id: Optional[str] = None
    inputs: Optional[List[dict]] = None
    default_value: Optional[Any] = None
    check_deviation: Optional[bool] = False
    scene_intensity: Optional[float] = 0.5


@router.post("/projects/{project_id}/hierarchy/override")
def set_user_override(project_id: str, request: UserOverrideRequest):
    """
    Set a user override for a decision type.
    
    User overrides always take highest priority in the hierarchy.
    """
    authority_hierarchy.set_user_override(
        project_id,
        request.decision_type,
        request.value,
        request.reason or ""
    )
    
    return {
        "project_id": project_id,
        "decision_type": request.decision_type,
        "value": request.value,
        "message": f"User override set for {request.decision_type}"
    }


@router.delete("/projects/{project_id}/hierarchy/override/{decision_type}")
def clear_user_override(project_id: str, decision_type: str):
    """Clear a user override."""
    authority_hierarchy.clear_user_override(project_id, decision_type)
    
    return {
        "project_id": project_id,
        "decision_type": decision_type,
        "message": f"User override cleared for {decision_type}"
    }


@router.post("/projects/{project_id}/hierarchy/scene-intent")
def set_scene_intent(project_id: str, request: SceneIntentRequest):
    """
    Set scene intent for a scene.
    
    Scene intent represents story-driven requirements and takes
    Priority 2 in the authority hierarchy.
    """
    intent = SceneIntent(
        scene_id=request.scene_id,
        scene_type=request.scene_type,
        emotion=request.emotion,
        genre=request.genre,
        visual_goal=request.visual_goal,
        emotional_goal=request.emotional_goal,
        pacing=request.pacing,
        intensity=request.intensity,
        is_turning_point=request.is_turning_point,
        narrative_beat=request.narrative_beat
    )
    
    authority_hierarchy.set_scene_intent(project_id, request.scene_id, intent)
    
    return {
        "project_id": project_id,
        "scene_id": request.scene_id,
        "intent": intent.to_dict(),
        "message": "Scene intent set"
    }


@router.post("/projects/{project_id}/hierarchy/resolve")
def resolve_decision_conflict(project_id: str, request: DecisionConflictRequest):
    """
    Resolve a decision conflict using authority hierarchy.
    
    Returns:
    - final_value: The resolved decision
    - decision_source: "intent", "pattern", "override", etc.
    - conflict_resolved: True if multiple sources were considered
    - overridden_sources: List of sources that were overruled
    """
    inputs = []
    if request.inputs:
        for inp in request.inputs:
            inputs.append(DecisionInput(
                value=inp.get("value"),
                source=DecisionSource(inp.get("source", "adaptive")),
                confidence=inp.get("confidence", 1.0),
                reason=inp.get("reason", "")
            ))
    
    result = authority_hierarchy.resolve_decision_conflict(
        project_id=project_id,
        decision_type=request.decision_type,
        scene_id=request.scene_id,
        inputs=inputs,
        default_value=request.default_value,
        check_deviation=request.check_deviation,
        scene_intensity=request.scene_intensity
    )
    
    return {
        "project_id": project_id,
        "decision_type": request.decision_type,
        "final_value": result.final_value,
        "decision_source": result.decision_source,
        "conflict_resolved": result.conflict_resolved,
        "overridden_sources": result.overridden_sources,
        "authority_used": result.authority_used,
        "all_inputs": result.all_inputs
    }


@router.get("/projects/{project_id}/hierarchy/debug")
def get_hierarchy_debug(
    project_id: str,
    decision_type: str,
    scene_id: Optional[str] = None
):
    """
    Get full hierarchy debug info for a decision.
    
    Shows all active sources and their priority order.
    """
    debug = authority_hierarchy.get_hierarchy_debug(
        project_id, decision_type, scene_id
    )
    return debug


@router.get("/projects/{project_id}/hierarchy/decisions")
def get_hierarchy_decisions(
    project_id: str,
    decision_type: Optional[str] = None,
    limit: int = 50
):
    """Get decision log entries for the project."""
    decisions = authority_hierarchy.get_decision_log(
        project_id, decision_type, limit
    )
    
    return {
        "project_id": project_id,
        "decisions": decisions,
        "count": len(decisions)
    }


@router.get("/projects/{project_id}/hierarchy/status")
def get_hierarchy_status(project_id: str):
    """Get current hierarchy status for a project."""
    overrides = authority_hierarchy._user_overrides.get(project_id, {})
    
    return {
        "project_id": project_id,
        "active_overrides": overrides,
        "priority_order": [
            "1. USER_OVERRIDE (highest)",
            "2. SCENE_INTENT",
            "3. ESTABLISHED_PATTERNS",
            "4. ADAPTIVE_SUGGESTIONS (lowest)"
        ]
    }


# ========================================================================
# SCENE EVOLUTION TRACKER
# ========================================================================

class RecordIterationRequest(BaseModel):
    scene_id: str
    intent_alignment: float = 0.0
    quality_score: float = 0.0
    patterns_used: Optional[List[dict]] = []
    deviations_used: Optional[List[dict]] = []
    scene_intent: Optional[dict] = None
    render_job_id: Optional[str] = None
    notes: str = ""
    decision_sources: Optional[dict] = None
    conflicts_resolved: int = 0


class RecordApprovalRequest(BaseModel):
    scene_id: str
    render_job_id: Optional[str] = None
    notes: str = ""


@router.post("/projects/{project_id}/adaptation/iteration")
def record_iteration(project_id: str, request: RecordIterationRequest):
    """
    Record a new iteration for a scene.
    
    Tracks how a scene evolves over multiple attempts.
    """
    iteration = evolution_tracker.record_iteration(
        project_id=project_id,
        scene_id=request.scene_id,
        intent_alignment=request.intent_alignment,
        quality_score=request.quality_score,
        patterns_used=request.patterns_used,
        deviations_used=request.deviations_used,
        scene_intent=request.scene_intent,
        render_job_id=request.render_job_id,
        notes=request.notes,
        decision_sources=request.decision_sources,
        conflicts_resolved=request.conflicts_resolved
    )
    
    return {
        "project_id": project_id,
        "scene_id": request.scene_id,
        "iteration_number": iteration.iteration_number,
        "timestamp": iteration.timestamp,
        "quality_score": iteration.quality_score,
        "intent_alignment_score": iteration.intent_alignment_score
    }


@router.post("/projects/{project_id}/adaptation/approval")
def record_approval(project_id: str, request: RecordApprovalRequest):
    """Record approval for a scene iteration."""
    iteration = evolution_tracker.record_approval(
        project_id=project_id,
        scene_id=request.scene_id,
        render_job_id=request.render_job_id,
        notes=request.notes
    )
    
    return {
        "project_id": project_id,
        "scene_id": request.scene_id,
        "iteration_number": iteration.iteration_number,
        "approved": iteration.approved
    }


@router.get("/projects/{project_id}/adaptation/scene-evolution/{scene_id}")
def get_scene_evolution(project_id: str, scene_id: str):
    """
    Get full evolution history for a scene.
    
    Returns all iterations with metrics showing improvement.
    """
    evolution = evolution_tracker.get_scene_evolution(project_id, scene_id)
    
    if not evolution:
        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "evolution": None,
            "message": "No evolution data found for this scene"
        }
    
    return {
        "project_id": project_id,
        "scene_id": scene_id,
        "evolution": evolution
    }


@router.get("/projects/{project_id}/adaptation/iteration/{scene_id}/{iteration_number}")
def get_iteration(project_id: str, scene_id: str, iteration_number: int):
    """Get specific iteration of a scene."""
    iteration = evolution_tracker.get_iteration(project_id, scene_id, iteration_number)
    
    if not iteration:
        raise HTTPException(status_code=404, detail="Iteration not found")
    
    return {
        "project_id": project_id,
        "scene_id": scene_id,
        "iteration": iteration.to_dict()
    }


@router.get("/projects/{project_id}/adaptation/metrics")
def get_evolution_metrics(project_id: str):
    """
    Get project-level evolution metrics.
    
    Returns improvement_rate, consistency_score, diversity_score.
    """
    metrics = evolution_tracker.get_metrics(project_id)
    
    return {
        "project_id": project_id,
        "metrics": metrics
    }


@router.get("/projects/{project_id}/adaptation/project-evolution")
def get_project_evolution(project_id: str):
    """Get full project evolution summary."""
    evolution = evolution_tracker.get_project_evolution(project_id)
    
    return {
        "project_id": project_id,
        "evolution": evolution
    }


@router.get("/projects/{project_id}/adaptation/trajectory/{scene_id}")
def get_improvement_trajectory(project_id: str, scene_id: str):
    """Get improvement trajectory for a scene."""
    trajectory = evolution_tracker.get_improvement_trajectory(project_id, scene_id)
    
    if "error" in trajectory:
        raise HTTPException(status_code=404, detail=trajectory["error"])
    
    return {
        "project_id": project_id,
        "scene_id": scene_id,
        "trajectory": trajectory
    }


@router.get("/projects/{project_id}/adaptation/compare/{scene_id}")
def compare_iterations(
    project_id: str,
    scene_id: str,
    iteration_a: int,
    iteration_b: int
):
    """Compare two iterations of a scene."""
    comparison = evolution_tracker.compare_iterations(
        project_id, scene_id, iteration_a, iteration_b
    )
    
    if "error" in comparison:
        raise HTTPException(status_code=404, detail=comparison["error"])
    
    return {
        "project_id": project_id,
        "scene_id": scene_id,
        "comparison": comparison
    }


# ========================================================================
# SCENE-ID FIRST ROUTES (direct access to repaired methods)
# ========================================================================

class PatternItem(BaseModel):
    """Validated pattern item with required pattern_type and pattern_value."""
    pattern_type: str
    pattern_value: str

class RecordEvolutionRequest(BaseModel):
    """Request body for recording evolution with scene_id as primary key."""
    iteration_number: int
    intent_alignment_score: float
    quality_score: float
    patterns_used: Optional[List[PatternItem]] = None
    deviations_used: Optional[List[PatternItem]] = None


@router.post("/scenes/{scene_id}/evolution")
def record_evolution_endpoint(scene_id: str, request: RecordEvolutionRequest):
    """
    Record a new evolution iteration using scene_id as primary key.
    
    This is the scene_id-first variant of the evolution tracking methods.
    The iteration_number should be provided by the caller.
    
    Repaired method: scene_evolution.record_evolution()
    """
    iteration = evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=request.iteration_number,
        intent_alignment_score=request.intent_alignment_score,
        quality_score=request.quality_score,
        patterns_used=request.patterns_used,
        deviations_used=request.deviations_used
    )
    
    return {
        "scene_id": scene_id,
        "iteration_number": iteration.iteration_number,
        "timestamp": iteration.timestamp,
        "intent_alignment_score": iteration.intent_alignment_score,
        "quality_score": iteration.quality_score,
        "patterns_used": iteration.patterns_used,
        "deviations_used": iteration.deviations_used
    }


@router.get("/scenes/{scene_id}/evolution")
def get_evolution_data_endpoint(scene_id: str, limit: Optional[int] = None):
    """
    Get evolution data for a scene using scene_id as primary key.
    
    Optional limit parameter restricts to the most recent N iterations.
    
    Repaired method: scene_evolution.get_evolution_data()
    """
    data = evolution_tracker.get_evolution_data(scene_id, limit=limit)
    
    if not data:
        return {
            "scene_id": scene_id,
            "iterations": [],
            "count": 0,
            "message": "No evolution data found for this scene"
        }
    
    return {
        "scene_id": scene_id,
        "iterations": data,
        "count": len(data)
    }


@router.get("/scenes/{scene_id}/evolution/metrics")
def compute_improvement_metrics_endpoint(scene_id: str):
    """
    Compute improvement metrics for a scene using scene_id as primary key.
    
    Returns improvement trajectory, alignment trends, and quality trends.
    
    Repaired method: scene_evolution.compute_improvement_metrics()
    """
    metrics = evolution_tracker.compute_improvement_metrics(scene_id)
    
    return {
        "scene_id": scene_id,
        "metrics": metrics
    }
