"""
Orchestrator Service - Autonomous Agent Execution Layer

This service provides:
- Continuous execution loop for crew tasks
- Automatic workflow triggering after script ingestion
- Task persistence to database
- Event-driven handoffs between agents
- Failure handling with retry limits
- Director override and safety controls
- Full observability

Usage:
    # Start orchestration for a project
    orchestrator = StudioOrchestrator(storage)
    orchestrator.start(project_id="project-xxx")
    
    # Run single iteration (controlled mode)
    orchestrator.run_once(project_id="project-xxx")
    
    # Stop orchestration
    orchestrator.stop(project_id="project-xxx")
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4
import json

logger = logging.getLogger("studio-orchestrator")
logger.setLevel(logging.INFO)


class OrchestratorState(str, Enum):
    """Orchestrator lifecycle states"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class TaskExecutor:
    """
    Base class for agent task executors.
    Each agent role has its own executor that knows how to perform the work.
    """
    
    def __init__(self, agent_role: str):
        self.agent_role = agent_role
        self.name = f"{agent_role}_executor"
    
    def execute(self, task: Dict, context: Dict) -> Dict:
        """
        Execute a task and return output.
        
        Args:
            task: Task data dict with input, metadata
            context: Execution context (project_id, memory, etc.)
            
        Returns:
            Dict with output data, status, and any artifacts
        """
        raise NotImplementedError
    
    def can_execute(self, task: Dict) -> bool:
        """Check if this executor can handle the task"""
        return task.get("agent_role") == self.agent_role


@dataclass
class ExecutionResult:
    """Result of task execution"""
    success: bool
    output_data: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorConfig:
    """Configuration for orchestrator behavior"""
    # Execution
    poll_interval_seconds: float = 1.0
    max_concurrent_tasks: int = 3
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    
    # Safety
    max_tasks_per_project: int = 1000
    max_task_chain_depth: int = 50
    
    # Controlled mode
    controlled_mode: bool = True  # Process one project at a time
    log_every_step: bool = True


class StudioOrchestrator:
    """
    Autonomous agent execution orchestrator.
    
    This service:
    1. Continuously scans for pending tasks
    2. Assigns tasks to correct agent roles
    3. Executes tasks with proper memory context
    4. Triggers next tasks on completion
    5. Handles failures with retry logic
    6. Persists all state to database
    """
    
    # Workflow definition: task_type -> next_task_type
    WORKFLOW_CHAIN = {
        "script_analysis": "scene_breakdown",
        "scene_breakdown": "shot_planning",
        "shot_planning": "prompt_generation",
        "prompt_generation": "render_coordination",
        "render_coordination": "quality_review",
        "quality_review": None,  # End of chain
    }
    
    # Agent role for each task type
    TASK_TYPE_TO_ROLE = {
        "script_analysis": "script_analyst",
        "scene_breakdown": "script_analyst",
        "shot_planning": "storyboard_artist",
        "prompt_generation": "prompt_engineer",
        "render_coordination": "render_coordinator",
        "quality_review": "quality_reviewer",
    }
    
    def __init__(
        self,
        storage,
        config: OrchestratorConfig = None,
        memory_service=None,
        render_service=None
    ):
        self.storage = storage
        self.config = config or OrchestratorConfig()
        
        # Service references
        self.memory_service = memory_service
        self.render_service = render_service
        
        # State management
        self._state: Dict[str, OrchestratorState] = {}  # project_id -> state
        self._threads: Dict[str, threading.Thread] = {}  # project_id -> thread
        self._stop_events: Dict[str, threading.Event] = {}  # project_id -> event
        
        # Task executors registry
        self._executors: Dict[str, TaskExecutor] = {}
        self._register_default_executors()
        
        # Event callbacks
        self._on_task_complete: Optional[Callable] = None
        self._on_task_fail: Optional[Callable] = None
        self._on_workflow_trigger: Optional[Callable] = None
        
        logger.info(f"StudioOrchestrator initialized (controlled_mode={self.config.controlled_mode})")
    
    def _register_default_executors(self):
        """Register default task executors"""
        from app.services.orchestrator_executors import (
            ScriptAnalysisExecutor,
            SceneBreakdownExecutor,
            ShotPlanningExecutor,
            PromptGenerationExecutor,
            RenderCoordinationExecutor,
QualityReviewExecutor,
        )
        
        executors = [
            ScriptAnalysisExecutor(),
            SceneBreakdownExecutor(),
            ShotPlanningExecutor(),
            PromptGenerationExecutor(),
            RenderCoordinationExecutor(),
            QualityReviewExecutor(),
        ]
        
        for executor in executors:
            self._executors[executor.agent_role] = executor
            logger.info(f"Registered executor: {executor.name}")
    
    # =========================================================================
    # LIFECYCLE MANAGEMENT
    # =========================================================================
    
    def start(self, project_id: str) -> bool:
        """
        Start orchestration for a project.
        
        Args:
            project_id: Project to orchestrate
            
        Returns:
            True if started successfully
        """
        if self._state.get(project_id) == OrchestratorState.RUNNING:
            logger.warning(f"Orchestrator already running for {project_id}")
            return False
        
        # Create stop event
        stop_event = threading.Event()
        self._stop_events[project_id] = stop_event
        
        # Create and start thread
        thread = threading.Thread(
            target=self._run_loop,
            args=(project_id, stop_event),
            name=f"orchestrator-{project_id}",
            daemon=True
        )
        self._threads[project_id] = thread
        self._state[project_id] = OrchestratorState.RUNNING
        
        thread.start()
        logger.info(f"Started orchestrator for project {project_id}")
        
        return True
    
    def stop(self, project_id: str) -> bool:
        """
        Stop orchestration for a project.
        
        Args:
            project_id: Project to stop
            
        Returns:
            True if stopped successfully
        """
        if project_id not in self._stop_events:
            logger.warning(f"No orchestrator running for {project_id}")
            return False
        
        # Signal stop
        self._stop_events[project_id].set()
        
        # Wait for thread
        if project_id in self._threads:
            self._threads[project_id].join(timeout=5.0)
            del self._threads[project_id]
        
        del self._stop_events[project_id]
        self._state[project_id] = OrchestratorState.STOPPED
        
        logger.info(f"Stopped orchestrator for project {project_id}")
        return True
    
    def pause(self, project_id: str) -> bool:
        """Pause orchestration without stopping"""
        if self._state.get(project_id) == OrchestratorState.RUNNING:
            self._state[project_id] = OrchestratorState.PAUSED
            logger.info(f"Paused orchestrator for project {project_id}")
            return True
        return False
    
    def resume(self, project_id: str) -> bool:
        """Resume paused orchestration"""
        if self._state.get(project_id) == OrchestratorState.PAUSED:
            self._state[project_id] = OrchestratorState.RUNNING
            logger.info(f"Resumed orchestrator for project {project_id}")
            return True
        return False
    
    def get_state(self, project_id: str) -> OrchestratorState:
        """Get orchestrator state for a project"""
        return self._state.get(project_id, OrchestratorState.STOPPED)
    
    # =========================================================================
    # CONTROLLED MODE - Single Iteration
    # =========================================================================
    
    def run_once(self, project_id: str) -> Dict[str, Any]:
        """
        Run a single orchestration iteration (controlled mode).
        
        This processes ONE batch of ready tasks and returns.
        Use this for testing or manual control.
        
        Args:
            project_id: Project to process
            
        Returns:
            Dict with execution results
        """
        results = {
            "project_id": project_id,
            "timestamp": datetime.now().isoformat(),
            "tasks_processed": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "tasks_created": 0,
            "details": []
        }
        
        if self.config.log_every_step:
            logger.info(f"[CONTROLLED] Processing project {project_id}")
        
        # Get pending tasks
        pending_tasks = self._get_pending_tasks(project_id)
        
        if self.config.log_every_step:
            logger.info(f"[CONTROLLED] Found {len(pending_tasks)} pending tasks")
        
        # Process up to max_concurrent_tasks
        for task in pending_tasks[:self.config.max_concurrent_tasks]:
            task_result = self._process_single_task(task)
            
            results["tasks_processed"] += 1
            results["details"].append(task_result)
            
            if task_result["success"]:
                results["tasks_succeeded"] += 1
            else:
                results["tasks_failed"] += 1
            
            # Check for new tasks created
            if task_result.get("next_task_created"):
                results["tasks_created"] += 1
        
        if self.config.log_every_step:
            logger.info(f"[CONTROLLED] Completed: {results['tasks_succeeded']} succeeded, "
                       f"{results['tasks_failed']} failed, {results['tasks_created']} created")
        
        return results
    
    # =========================================================================
    # INTERNAL EXECUTION LOOP
    # =========================================================================
    
    def _run_loop(self, project_id: str, stop_event: threading.Event):
        """Main execution loop - runs until stopped"""
        logger.info(f"[LOOP] Starting execution loop for {project_id}")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while not stop_event.is_set():
            try:
                # Check pause state
                if self._state.get(project_id) == OrchestratorState.PAUSED:
                    stop_event.wait(timeout=1.0)
                    continue
                
                # Run one iteration
                results = self.run_once(project_id)
                
                # Track errors
                if results["tasks_processed"] > 0:
                    consecutive_errors = 0
                elif results["tasks_failed"] > 0:
                    consecutive_errors += 1
                
                # Check for runaway condition
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"[LOOP] Too many consecutive errors for {project_id}, pausing")
                    self._state[project_id] = OrchestratorState.ERROR
                    break
                
                # Wait before next iteration
                stop_event.wait(timeout=self.config.poll_interval_seconds)
                
            except Exception as e:
                logger.exception(f"[LOOP] Error in execution loop for {project_id}: {e}")
                consecutive_errors += 1
                stop_event.wait(timeout=self.config.retry_delay_seconds)
        
        logger.info(f"[LOOP] Execution loop stopped for {project_id}")
    
    # =========================================================================
    # TASK PROCESSING
    # =========================================================================
    
    def _get_pending_tasks(self, project_id: str) -> List[Dict]:
        """Get tasks ready for execution"""
        tasks = self.storage.get_crew_tasks(project_id)
        
        pending = []
        for task in tasks:
            if self._is_task_ready(task):
                pending.append(task)
        
        # Sort by priority and creation time
        pending.sort(key=lambda t: (-t.get("priority", 5), t.get("created_at", "")))
        
        return pending
    
    def _is_task_ready(self, task: Dict) -> bool:
        """Check if task is ready for execution"""
        # Check status
        if task.get("status") not in ["created", "pending_input", "assigned"]:
            return False
        
        # Check dependencies
        depends_on = task.get("depends_on", [])
        if depends_on:
            all_tasks = self.storage.get_crew_tasks(task.get("project_id"))
            task_map = {t["task_id"]: t for t in all_tasks}
            
            for dep_id in depends_on:
                dep_task = task_map.get(dep_id)
                if not dep_task or dep_task.get("status") != "completed":
                    return False
        
        return True
    
    def _process_single_task(self, task: Dict) -> Dict[str, Any]:
        """
        Process a single task.
        
        Returns:
            Dict with execution results
        """
        task_id = task["task_id"]
        project_id = task["project_id"]
        agent_role = task["agent_role"]
        task_type = task.get("task_type", "")
        
        result = {
            "task_id": task_id,
            "agent_role": agent_role,
            "success": False,
            "next_task_created": False
        }
        
        if self.config.log_every_step:
            logger.info(f"[EXECUTE] Task {task_id}: {agent_role}/{task_type}")
        
        # Get executor
        executor = self._executors.get(agent_role)
        if not executor:
            result["error"] = f"No executor for role {agent_role}"
            logger.error(f"[EXECUTE] {result['error']}")
            return result
        
        # Build context
        context = {
            "project_id": project_id,
            "task_id": task_id,
            "storage": self.storage,
            "memory_service": self.memory_service,
            "render_service": self.render_service,
        }
        
        # Execute task
        try:
            # Mark as in_progress
            self.storage.update_crew_task_status(task_id, "in_progress")
            
            # Execute
            exec_result = executor.execute(task, context)
            
            if exec_result.success:
                # Mark as completed
                self.storage.update_crew_task_status(task_id, "completed", output_data=exec_result.output_data)
                
                result["success"] = True
                result["output_data"] = exec_result.output_data
                
                if self.config.log_every_step:
                    logger.info(f"[EXECUTE] Task {task_id} completed successfully")
                
                # Trigger next task
                next_task = self._trigger_next_task(task, exec_result.output_data)
                if next_task:
                    result["next_task_created"] = True
                    result["next_task_id"] = next_task["task_id"]
                
                # Call completion callback
                if self._on_task_complete:
                    self._on_task_complete(task, exec_result)
                    
            else:
                # Handle failure
                result["error"] = exec_result.error
                self._handle_task_failure(task, exec_result)
                
        except Exception as e:
            logger.exception(f"[EXECUTE] Exception executing task {task_id}: {e}")
            result["error"] = str(e)
            self.storage.update_crew_task_status(
                task_id, "failed", 
                error=str(e),
                retry_count=task.get("retry_count", 0) + 1
            )
        
        return result
    
    def _handle_task_failure(self, task: Dict, result: ExecutionResult):
        """Handle task failure with retry logic"""
        task_id = task["task_id"]
        retry_count = task.get("retry_count", 0) + 1
        
        if retry_count < self.config.max_retries:
            # Retry
            logger.warning(f"[RETRY] Task {task_id} failed, scheduling retry {retry_count}/{self.config.max_retries}")
            self.storage.update_crew_task_status(
                task_id, "pending_input",
                error=result.error,
                retry_count=retry_count
            )
        else:
            # Max retries exceeded
            logger.error(f"[FAILED] Task {task_id} exceeded max retries")
            self.storage.update_crew_task_status(
                task_id, "failed",
                error=f"Max retries exceeded: {result.error}",
                retry_count=retry_count
            )
            
            if self._on_task_fail:
                self._on_task_fail(task, result)
    
    def _trigger_next_task(self, completed_task: Dict, output_data: Dict) -> Optional[Dict]:
        """
        Trigger the next task in the workflow chain.
        
        This is where automation happens - completing one task automatically
        creates the next task in the pipeline.
        """
        task_type = completed_task.get("task_type", "")
        project_id = completed_task["project_id"]
        
        # Get next task type from workflow chain
        next_task_type = self.WORKFLOW_CHAIN.get(task_type)
        
        if not next_task_type:
            if self.config.log_every_step:
                logger.info(f"[CHAIN] No next task for {task_type}, workflow complete")
            return None
        
        # Get agent role for next task
        agent_role = self.TASK_TYPE_TO_ROLE.get(next_task_type)
        if not agent_role:
            logger.error(f"[CHAIN] No role mapping for {next_task_type}")
            return None
        
        # Create next task
        next_task = self.storage.create_crew_task({
            "project_id": project_id,
            "agent_role": agent_role,
            "task_type": next_task_type,
            "title": f"{next_task_type.replace('_', ' ').title()} - Auto-triggered",
            "description": f"Auto-generated from {task_type} completion",
            "depends_on": [completed_task["task_id"]],
            "priority": completed_task.get("priority", 5),
            "input_data": {
                "source_task_id": completed_task["task_id"],
                "source_output": output_data,
            }
        })
        
        if self.config.log_every_step:
            logger.info(f"[CHAIN] Created next task: {next_task['task_id']} ({next_task_type})")
        
        if self._on_workflow_trigger:
            self._on_workflow_trigger(completed_task, next_task)
        
        return next_task
    
    # =========================================================================
    # WORKFLOW INITIALIZATION
    # =========================================================================
    
    def initialize_workflow(self, project_id: str) -> List[Dict]:
        """
        Initialize the complete workflow for a project.
        
        Call this after script ingestion to start the automation.
        Creates all initial tasks in the workflow chain.
        
        Args:
            project_id: Project to initialize workflow for
            
        Returns:
            List of created tasks
        """
        if self.config.log_every_step:
            logger.info(f"[INIT] Initializing workflow for {project_id}")
        
        # Create first task: script analysis
        first_task = self.storage.create_crew_task({
            "project_id": project_id,
            "agent_role": "script_analyst",
            "task_type": "script_analysis",
            "title": "Script Analysis - Auto-triggered",
            "description": "Analyze screenplay and extract structure",
            "depends_on": [],
            "priority": 10,  # High priority for first task
            "input_data": {
                "source": "workflow_initialization"
            }
        })
        
        created_tasks = [first_task]
        
        if self.config.log_every_step:
            logger.info(f"[INIT] Created initial task: {first_task['task_id']}")
        
        return created_tasks
    
    # =========================================================================
    # DIRECTOR OVERRIDE
    # =========================================================================
    
    def director_override(
        self,
        project_id: str,
        task_id: str,
        action: str,
        params: Dict = None
    ) -> Dict[str, Any]:
        """
        Allow Creative Director to override task execution.
        
        Actions:
        - "cancel": Cancel a task
        - "redirect": Redirect to different role
        - "pause_workflow": Pause all tasks for project
        - "resume_workflow": Resume paused workflow
        - "force_complete": Mark task as complete with director's data
        """
        params = params or {}
        result = {"success": False, "message": ""}
        
        if action == "cancel":
            self.storage.update_crew_task_status(task_id, "cancelled")
            result["success"] = True
            result["message"] = f"Task {task_id} cancelled by director"
            logger.info(f"[DIRECTOR] {result['message']}")
            
        elif action == "redirect":
            new_role = params.get("new_role")
            if new_role:
                self.storage.update_crew_task(task_id, {"agent_role": new_role})
                result["success"] = True
                result["message"] = f"Task {task_id} redirected to {new_role}"
                logger.info(f"[DIRECTOR] {result['message']}")
                
        elif action == "pause_workflow":
            self.pause(project_id)
            result["success"] = True
            result["message"] = f"Workflow paused for {project_id}"
            
        elif action == "resume_workflow":
            self.resume(project_id)
            result["success"] = True
            result["message"] = f"Workflow resumed for {project_id}"
            
        elif action == "force_complete":
            output_data = params.get("output_data", {})
            self.storage.update_crew_task_status(task_id, "completed", output_data=output_data)
            result["success"] = True
            result["message"] = f"Task {task_id} force-completed by director"
            logger.info(f"[DIRECTOR] {result['message']}")
        
        else:
            result["message"] = f"Unknown action: {action}"
        
        return result
    
    # =========================================================================
    # OBSERVABILITY
    # =========================================================================
    
    def get_task_queue(self, project_id: str) -> Dict[str, Any]:
        """Get complete task queue status for a project"""
        tasks = self.storage.get_crew_tasks(project_id)
        
        status_counts = {}
        role_counts = {}
        type_counts = {}
        
        for task in tasks:
            status = task.get("status", "unknown")
            role = task.get("agent_role", "unknown")
            task_type = task.get("task_type", "unknown")
            
            status_counts[status] = status_counts.get(status, 0) + 1
            role_counts[role] = role_counts.get(role, 0) + 1
            type_counts[task_type] = type_counts.get(task_type, 0) + 1
        
        return {
            "project_id": project_id,
            "orchestrator_state": self.get_state(project_id).value,
            "total_tasks": len(tasks),
            "status_breakdown": status_counts,
            "role_breakdown": role_counts,
            "type_breakdown": type_counts,
            "tasks": tasks
        }
    
    def get_execution_log(self, project_id: str, limit: int = 100) -> List[Dict]:
        """Get execution log for a project"""
        return self.storage.get_crew_task_log(project_id, limit)


# Global orchestrator instance
_studio_orchestrator: Optional[StudioOrchestrator] = None


def get_orchestrator(
    storage=None,
    config: OrchestratorConfig = None,
    memory_service=None,
    render_service=None
) -> StudioOrchestrator:
    """Get or create the global orchestrator instance"""
    global _studio_orchestrator
    
    if _studio_orchestrator is None:
        if storage is None:
            from app.data.storage import get_storage
            storage = get_storage("sqlite")
        
        _studio_orchestrator = StudioOrchestrator(
            storage=storage,
            config=config,
            memory_service=memory_service,
            render_service=render_service
        )
    
    return _studio_orchestrator
