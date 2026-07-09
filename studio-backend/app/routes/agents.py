"""
Agent Routes - API for crew orchestration
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.models.agents import (
    AgentRole, TaskStatus, CrewTask, ProjectOwnership, DirectorOverride
)
from app.services import agent_service, AgentRole as AgentRoleEnum, TaskStatus as TaskStatusEnum

router = APIRouter(prefix="/api/f51/studio/agents", tags=["agents"])


def get_current_user_id() -> str:
    """Placeholder - would use real auth in production"""
    return "user-demo"


# ==================== PROJECT OWNERSHIP ====================

@router.post("/projects/{project_id}/ownership")
def create_project_ownership(project_id: str, user_id: str = Depends(get_current_user_id)):
    """Create project ownership for a user"""
    return agent_service.create_project_ownership(project_id, user_id)


@router.get("/projects/{project_id}/ownership")
def get_project_ownership(project_id: str, user_id: str = Depends(get_current_user_id)):
    """Get project ownership"""
    if not agent_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return agent_service.get_ownership(project_id)


# ==================== TASKS ====================

class CreateTaskRequest(BaseModel):
    role: str
    title: str
    description: str
    priority: int = 0
    input_from_task_id: Optional[str] = None
    metadata: dict = {}


@router.post("/projects/{project_id}/tasks")
def create_task(
    project_id: str,
    request: CreateTaskRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Create a new crew task"""
    if not agent_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    role = AgentRoleEnum(request.role)
    return agent_service.create_task(
        project_id=project_id,
        role=role,
        title=request.title,
        description=request.description,
        owner_user_id=user_id,
        creator_agent_id="user",
        priority=request.priority,
        input_from_task_id=request.input_from_task_id,
        metadata=request.metadata
    )


@router.get("/projects/{project_id}/tasks")
def get_project_tasks(
    project_id: str,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """Get all tasks for a project"""
    if not agent_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    task_status = TaskStatusEnum(status) if status else None
    return agent_service.get_project_tasks(project_id, task_status)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user_id: str = Depends(get_current_user_id)):
    """Get a specific task"""
    task = agent_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not agent_service.can_modify_task(task_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return task


@router.post("/tasks/{task_id}/assign/{agent_id}")
def assign_task(task_id: str, agent_id: str, user_id: str = Depends(get_current_user_id)):
    """Assign task to an agent"""
    if not agent_service.can_modify_task(task_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = agent_service.assign_task(task_id, agent_id)
    if not result:
        raise HTTPException(status_code=400, detail="Could not assign task")
    return result


@router.post("/tasks/{task_id}/start")
def start_task(task_id: str, user_id: str = Depends(get_current_user_id)):
    """Start a task"""
    if not agent_service.can_modify_task(task_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = agent_service.start_task(task_id)
    if not result:
        raise HTTPException(status_code=400, detail="Could not start task")
    return result


class CompleteTaskRequest(BaseModel):
    output_data: dict


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Complete a task with output"""
    if not agent_service.can_modify_task(task_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = agent_service.complete_task(task_id, request.output_data)
    if not result:
        raise HTTPException(status_code=400, detail="Could not complete task")
    return result


# ==================== DIRECTOR OVERRIDE ====================

class OverrideRequest(BaseModel):
    action: str  # PAUSE, REDIRECT, TAKE_OVER, APPROVE, REJECT, ESCALATE
    notes: str = ""
    redirect_to_role: Optional[str] = None


@router.post("/tasks/{task_id}/override")
def apply_override(
    task_id: str,
    request: OverrideRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Apply director override to a task"""
    if not agent_service.can_modify_task(task_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    redirect_role = AgentRoleEnum(request.redirect_to_role) if request.redirect_to_role else None
    result = agent_service.apply_override(
        task_id=task_id,
        user_id=user_id,
        action=request.action,
        notes=request.notes,
        redirect_to_role=redirect_role
    )
    if not result:
        raise HTTPException(status_code=400, detail="Could not apply override")
    return result


# ==================== WORKFLOWS ====================

class ScriptAnalysisRequest(BaseModel):
    script_content: str


@router.post("/projects/{project_id}/workflow/script-analysis")
def run_script_analysis(
    project_id: str,
    request: ScriptAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Run script analysis workflow"""
    if not agent_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return agent_service.run_script_analysis(
        project_id=project_id,
        script_content=request.script_content,
        user_id=user_id
    )


class RenderRequest(BaseModel):
    shot_plan: dict


@router.post("/projects/{project_id}/workflow/render")
def create_render_request(
    project_id: str,
    request: RenderRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Create render request through agent workflow"""
    if not agent_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return agent_service.create_render_request(
        project_id=project_id,
        shot_plan=request.shot_plan,
        user_id=user_id
    )


# ==================== ACTIVITIES ====================

@router.get("/projects/{project_id}/activities")
def get_activities(
    project_id: str,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id)
):
    """Get recent activities for a project"""
    if not agent_service.can_access_project(project_id, user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return agent_service.get_activities(project_id, limit)


# ==================== AGENTS ====================

@router.get("/agents")
def list_agents():
    """List all available agents"""
    from app.services.agents import DEFAULT_AGENTS
    return [
        {
            "agent_id": f"agent-{role.value}",
            "role": role.value,
            "name": config["name"],
            "description": config["description"],
            "capabilities": config["capabilities"]
        }
        for role, config in DEFAULT_AGENTS.items()
    ]