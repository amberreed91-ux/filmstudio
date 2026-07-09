"""
Agent Service - Orchestrates the film production crew
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4

from app.models.agents import (
    Agent, AgentRole, CrewTask, TaskStatus, ApprovalState, HandoffState,
    ProjectOwnership, Handoff, DirectorOverride, AgentActivity
)

logger = logging.getLogger("studio-agents")


# Default agent configurations
DEFAULT_AGENTS = {
    AgentRole.DIRECTOR: {
        "name": "Director Agent",
        "description": "Orchestrates overall production, coordinates handoffs, escalates decisions",
        "capabilities": ["workflow_orchestration", "decision_making", "override", "escalate"]
    },
    AgentRole.SCRIPT_ANALYST: {
        "name": "Script Analyst",
        "description": "Parses and analyzes screenplay, identifies scenes and characters",
        "capabilities": ["script_parsing", "scene_extraction", "character_mapping", "structure_analysis"]
    },
    AgentRole.STUDY_CURATOR: {
        "name": "Study Curator",
        "description": "Processes reference materials and extracts production insights",
        "capabilities": ["material_analysis", "style_extraction", "study_card_creation", "reference_tagging"]
    },
    AgentRole.SCENE_BREAKDOWN: {
        "name": "Scene Breakdown Agent",
        "description": "Converts scenes into production tasks and shot requirements",
        "capabilities": ["scene_analysis", "shot_identification", "complexity_estimation", "resource_planning"]
    },
    AgentRole.SHOT_PLANNER: {
        "name": "Shot Planner",
        "description": "Plans shot composition, timing, and technical requirements",
        "capabilities": ["shot_composition", "camera_planning", "technical_specs", "prompt_templates"]
    },
    AgentRole.PROMPT_ENGINEER: {
        "name": "Prompt Engineer",
        "description": "Refines prompts for optimal render quality",
        "capabilities": ["prompt_optimization", "style_matching", "quality_tuning", "prompt_library"]
    },
    AgentRole.RENDER_COORDINATOR: {
        "name": "Render Coordinator",
        "description": "Manages render jobs and coordinates provider interactions",
        "capabilities": ["job_submission", "provider_coordination", "progress_monitoring", "output_collection"]
    },
    AgentRole.QUALITY_REVIEWER: {
        "name": "Quality Reviewer",
        "description": "Evaluates generated outputs against standards",
        "capabilities": ["quality_assessment", "automated_checks", "scoring", "annotation"]
    },
    AgentRole.POST_COORDINATOR: {
        "name": "Post Coordinator",
        "description": "Plans editorial workflow and final delivery",
        "capabilities": ["timeline_planning", "sequence_assembly", "delivery_prep", "pacing_analysis"]
    }
}


class AgentService:
    """Service for managing the film production crew"""
    
    def __init__(self, storage=None):
        self.storage = storage
        self._agents: Dict[str, Agent] = {}
        self._tasks: Dict[str, CrewTask] = {}
        self._ownership: Dict[str, ProjectOwnership] = {}
        self._handoffs: Dict[str, Handoff] = {}
        self._activities: List[AgentActivity] = []
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize the default agent crew"""
        now = datetime.now().isoformat()
        
        for role, config in DEFAULT_AGENTS.items():
            agent_id = f"agent-{role.value}"
            agent = Agent(
                agent_id=agent_id,
                role=role,
                name=config["name"],
                description=config["description"],
                capabilities=config["capabilities"],
                status="idle",
                created_at=now,
                updated_at=now
            )
            self._agents[agent_id] = agent
            logger.info(f"Initialized agent: {agent_id} ({role.value})")
    
    # ==================== OWNERSHIP ====================
    
    def create_project_ownership(self, project_id: str, user_id: str) -> ProjectOwnership:
        """Create project ownership with owner as director"""
        now = datetime.now().isoformat()
        
        ownership = ProjectOwnership(
            project_id=project_id,
            owner_user_id=user_id,
            director_user_ids=[user_id],  # Owner has director authority
            created_at=now,
            updated_at=now
        )
        
        self._ownership[project_id] = ownership
        
        # Assign all agents to project
        ownership.agent_ids = list(self._agents.keys())
        
        # Assign director agent to project
        director_agent = self._agents.get("agent-director")
        if director_agent:
            director_agent.project_id = project_id
        
        return ownership
    
    def get_ownership(self, project_id: str) -> Optional[ProjectOwnership]:
        return self._ownership.get(project_id)
    
    def can_access_project(self, project_id: str, user_id: str) -> bool:
        """Check if user can access project"""
        ownership = self._ownership.get(project_id)
        if not ownership:
            return False
        
        # Owner, collaborator, or director can access
        if user_id == ownership.owner_user_id:
            return True
        if user_id in ownership.collaborator_ids:
            return True
        if user_id in ownership.director_user_ids:
            return True
        
        return False
    
    def can_modify_task(self, task_id: str, user_id: str) -> bool:
        """Check if user can modify a task"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        # Check project access
        if not self.can_access_project(task.project_id, user_id):
            return False
        
        ownership = self._ownership.get(task.project_id)
        
        # Owner or director can modify
        if user_id == ownership.owner_user_id:
            return True
        if user_id in ownership.director_user_ids:
            return True
        
        return False
    
    # ==================== TASKS ====================
    
    def create_task(
        self,
        project_id: str,
        role: AgentRole,
        title: str,
        description: str,
        owner_user_id: str,
        creator_agent_id: str,
        priority: int = 0,
        input_from_task_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> CrewTask:
        """Create a new crew task"""
        now = datetime.now().isoformat()
        task_id = f"task-{uuid4().hex[:12]}"
        
        task = CrewTask(
            task_id=task_id,
            project_id=project_id,
            owner_user_id=owner_user_id,
            creator_agent_id=creator_agent_id,
            role=role,
            title=title,
            description=description,
            priority=priority,
            status=TaskStatus.CREATED,
            input_from_task_id=input_from_task_id,
            metadata=metadata or {},
            created_at=now,
            updated_at=now
        )
        
        self._tasks[task_id] = task
        self._log_activity(task_id, creator_agent_id, "created", f"Task created: {title}")
        
        # If there's an input dependency, link them
        if input_from_task_id:
            input_task = self._tasks.get(input_from_task_id)
            if input_task:
                input_task.output_to_task_ids.append(task_id)
        
        return task
    
    def assign_task(self, task_id: str, agent_id: str) -> Optional[CrewTask]:
        """Assign task to an agent"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        
        task.assignee_agent_id = agent_id
        task.status = TaskStatus.ASSIGNED
        task.updated_at = datetime.now().isoformat()
        
        # Update agent state
        agent.status = "working"
        agent.current_task_id = task_id
        agent.owned_tasks.append(task_id)
        
        self._log_activity(task_id, agent_id, "assigned", f"Assigned to {agent.name}")
        
        return task
    
    def start_task(self, task_id: str) -> Optional[CrewTask]:
        """Mark task as in progress"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.updated_at = datetime.now().isoformat()
        
        if task.assignee_agent_id:
            agent = self._agents.get(task.assignee_agent_id)
            if agent:
                self._log_activity(task_id, task.assignee_agent_id, "started", "Task started")
        
        return task
    
    def complete_task(self, task_id: str, output_data: Dict) -> Optional[CrewTask]:
        """Mark task as complete with output"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        task.status = TaskStatus.COMPLETE
        task.progress = 100
        task.output_data = output_data
        task.completed_at = datetime.now().isoformat()
        task.updated_at = datetime.now().isoformat()
        
        # Clear agent assignment
        if task.assignee_agent_id:
            agent = self._agents.get(task.assignee_agent_id)
            if agent:
                agent.status = "idle"
                agent.current_task_id = None
                self._log_activity(task_id, task.assignee_agent_id, "completed", "Task completed")
        
        # Trigger dependent tasks
        self._trigger_dependent_tasks(task)
        
        return task
    
    def _trigger_dependent_tasks(self, completed_task: CrewTask):
        """Trigger tasks that depend on completed task"""
        for dependent_id in completed_task.output_to_task_ids:
            dependent = self._tasks.get(dependent_id)
            if dependent and dependent.status == TaskStatus.CREATED:
                # Auto-assign to appropriate agent
                suitable_agent = self._find_available_agent(dependent.role)
                if suitable_agent:
                    self.assign_task(dependent_id, suitable_agent.agent_id)
    
    def _find_available_agent(self, role: AgentRole) -> Optional[Agent]:
        """Find available agent for a role"""
        for agent in self._agents.values():
            if agent.role == role and agent.status == "idle":
                return agent
        return None
    
    def get_task(self, task_id: str) -> Optional[CrewTask]:
        return self._tasks.get(task_id)
    
    def get_project_tasks(self, project_id: str, status: Optional[TaskStatus] = None) -> List[CrewTask]:
        """Get all tasks for a project"""
        tasks = [t for t in self._tasks.values() if t.project_id == project_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.priority, reverse=True)
    
    def get_user_tasks(self, user_id: str, project_id: str) -> List[CrewTask]:
        """Get tasks user can see in a project"""
        if not self.can_access_project(project_id, user_id):
            return []
        
        # User sees: owned tasks + all project tasks (as director)
        ownership = self._ownership.get(project_id)
        if not ownership:
            return []
        
        tasks = self.get_project_tasks(project_id)
        
        # If user is director, they see all
        if user_id in ownership.director_user_ids:
            return tasks
        
        # Otherwise show owned tasks
        return [t for t in tasks if t.owner_user_id == user_id]
    
    # ==================== DIRECTOR OVERRIDE ====================
    
    def apply_override(
        self,
        task_id: str,
        user_id: str,
        action: str,
        notes: str = "",
        redirect_to_role: Optional[AgentRole] = None
    ) -> Optional[CrewTask]:
        """Apply director override to a task"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        # Verify user has director authority
        ownership = self._ownership.get(task.project_id)
        if not ownership or user_id not in ownership.director_user_ids:
            logger.warning(f"User {user_id} attempted director override without authority")
            return None
        
        now = datetime.now().isoformat()
        
        override = {
            "action": action,
            "notes": notes,
            "timestamp": now
        }
        
        if action == "PAUSE":
            task.status = TaskStatus.PAUSED
            task.director_override = override
            task.override_by_user_id = user_id
        
        elif action == "REDIRECT":
            if redirect_to_role:
                # Find agent of that role
                for agent in self._agents.values():
                    if agent.role == redirect_to_role:
                        self.assign_task(task_id, agent.agent_id)
                        break
            task.director_override = override
            task.override_by_user_id = user_id
        
        elif action == "TAKE_OVER":
            task.status = TaskStatus.IN_PROGRESS
            task.director_override = override
            task.override_by_user_id = user_id
            task.approval_state = ApprovalState.NEEDS_REVISION
        
        elif action == "APPROVE":
            task.approval_state = ApprovalState.APPROVED
            task.status = TaskStatus.COMPLETE
            task.director_override = override
            task.override_by_user_id = user_id
            task.reviewed_by_user_id = user_id
            task.reviewed_at = now
        
        elif action == "REJECT":
            task.approval_state = ApprovalState.REJECTED
            task.status = TaskStatus.REJECTED
            task.review_notes = notes
            task.director_override = override
            task.override_by_user_id = user_id
            task.reviewed_by_user_id = user_id
            task.reviewed_at = now
            # Return to assignee for rework
            if task.assignee_agent_id:
                task.status = TaskStatus.IN_PROGRESS
                task.approval_state = ApprovalState.NEEDS_REVISION
        
        elif action == "ESCALATE":
            task.status = TaskStatus.ESCALATED
            task.director_override = override
            task.override_by_user_id = user_id
        
        task.updated_at = now
        self._log_activity(task_id, f"director-{user_id}", f"override_{action}", notes)
        
        return task
    
    # ==================== AGENT WORKFLOW ====================
    
    def run_script_analysis(self, project_id: str, script_content: str, user_id: str) -> List[CrewTask]:
        """Run script analysis workflow"""
        tasks = []
        
        # Create analysis task
        task = self.create_task(
            project_id=project_id,
            role=AgentRole.SCRIPT_ANALYST,
            title="Analyze Script",
            description=f"Analyze screenplay content: {script_content[:100]}...",
            owner_user_id=user_id,
            creator_agent_id="system",
            priority=10
        )
        tasks.append(task)
        
        # Auto-assign to script analyst
        self.assign_task(task.task_id, "agent-script_analyst")
        
        return tasks
    
    def run_scene_breakdown(self, project_id: str, script_analysis: Dict, user_id: str) -> List[CrewTask]:
        """Run scene breakdown workflow"""
        tasks = []
        
        # Create breakdown task
        task = self.create_task(
            project_id=project_id,
            role=AgentRole.SCENE_BREAKDOWN,
            title="Break Down Scenes",
            description="Convert script analysis into production tasks",
            owner_user_id=user_id,
            creator_agent_id="system",
            priority=8
        )
        tasks.append(task)
        
        self.assign_task(task.task_id, "agent-scene_breakdown")
        
        return tasks
    
    def create_render_request(self, project_id: str, shot_plan: Dict, user_id: str) -> CrewTask:
        """Create render request through coordinator"""
        task = self.create_task(
            project_id=project_id,
            role=AgentRole.RENDER_COORDINATOR,
            title=f"Render: {shot_plan.get('title', 'Shot')}",
            description=f"Execute render for shot plan",
            owner_user_id=user_id,
            creator_agent_id="system",
            priority=5,
            metadata={"shot_plan": shot_plan}
        )
        
        self.assign_task(task.task_id, "agent-render_coordinator")
        return task
    
    # ==================== ACTIVITY LOG ====================
    
    def _log_activity(self, task_id: str, agent_id: str, action: str, details: str = ""):
        """Log agent activity"""
        activity = AgentActivity(
            activity_id=f"act-{uuid4().hex[:12]}",
            task_id=task_id,
            agent_id=agent_id,
            action=action,
            details=details,
            created_at=datetime.now().isoformat()
        )
        self._activities.append(activity)
    
    def get_activities(self, project_id: str, limit: int = 50) -> List[AgentActivity]:
        """Get recent activities for a project"""
        task_ids = {t.task_id for t in self.get_project_tasks(project_id)}
        return [a for a in self._activities if a.task_id in task_ids][-limit:]


# Global service instance
agent_service = AgentService()