"""Workflow Runner Service for executing reusable workflows."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from app.models import (
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStep,
    RenderJobModel,
)
from app.services import (
    render_service,
    project_store,
    generate_short_film_workflow_service,
    short_film_review_service,
    clip_revision_service,
    final_short_film_package_service,
)
from app.data.storage import get_storage


class WorkflowRunnerService:
    """Service for executing reusable workflows."""
    
    def __init__(self):
        self._executions: Dict[str, WorkflowExecution] = {}
        self._storage = get_storage("sqlite")
        self._step_handlers: Dict[str, Callable] = {
            "create_project": self._handle_create_project,
            "generate_scenes": self._handle_generate_scenes,
            "render_shots": self._handle_render_shots,
            "assemble_film": self._handle_assemble_film,
            "create_review": self._handle_create_review,
            "create_revision": self._handle_create_revision,
            "create_package": self._handle_create_package,
        }
    
    async def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        project_id: str,
        inputs: Dict[str, Any],
    ) -> WorkflowExecution:
        """Execute a workflow with given inputs."""
        execution_id = str(uuid.uuid4())
        
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=workflow.workflow_id,
            project_id=project_id,
            status="pending",
            inputs=inputs,
            started_at=datetime.now().isoformat(),
        )
        
        self._executions[execution_id] = execution
        
        # Save execution to storage
        if self._storage and hasattr(self._storage, "save_workflow_execution"):
            self._storage.save_workflow_execution(execution)
        
        try:
            # Validate required inputs
            self._validate_inputs(workflow, inputs)
            
            # Execute steps in dependency order
            step_order = workflow.get_dependency_order()
            
            for step_id in step_order:
                step = workflow.get_step_by_id(step_id)
                if not step:
                    raise ValueError(f"Step {step_id} not found in workflow")
                
                execution.current_step = step_id
                execution.status = "running"
                
                # Save execution state
                if self._storage and hasattr(self._storage, "save_workflow_execution"):
                    self._storage.save_workflow_execution(execution)
                
                # Execute step
                step_result = await self._execute_step(step, execution, inputs)
                execution.step_results[step_id] = step_result
                execution.completed_steps.append(step_id)
                
                # Update progress
                execution.progress_percentage = (len(execution.completed_steps) / len(step_order)) * 100.0
            
            execution.status = "completed"
            execution.completed_at = datetime.now().isoformat()
            execution.current_step = None
            
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = datetime.now().isoformat()
            execution.current_step = None
            raise
        
        finally:
            # Save final execution state
            if self._storage and hasattr(self._storage, "save_workflow_execution"):
                self._storage.save_workflow_execution(execution)
        
        return execution
    
    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get execution by ID."""
        # Check in-memory cache first
        execution = self._executions.get(execution_id)
        if execution:
            return execution
        
        # Check storage
        if self._storage and hasattr(self._storage, "get_workflow_execution"):
            execution = self._storage.get_workflow_execution(execution_id)
            if execution:
                self._executions[execution_id] = execution
                return execution
        
        return None
    
    def list_executions(self, project_id: Optional[str] = None) -> List[WorkflowExecution]:
        """List executions, optionally filtered by project."""
        if self._executions:
            executions = list(self._executions.values())
            if project_id:
                executions = [e for e in executions if e.project_id == project_id]
            return executions

        # Get from storage if available
        if self._storage and hasattr(self._storage, "list_workflow_executions"):
            executions = self._storage.list_workflow_executions(project_id)
            # Update cache
            for execution in executions:
                self._executions[execution.execution_id] = execution
            return executions
        
        # Fallback to in-memory cache
        executions = list(self._executions.values())
        if project_id:
            executions = [e for e in executions if e.project_id == project_id]
        return executions
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an execution."""
        execution = self.get_execution(execution_id)
        if not execution or execution.is_terminal():
            return False
        
        execution.status = "cancelled"
        execution.completed_at = datetime.now().isoformat()
        execution.current_step = None
        
        # Save to storage
        if self._storage and hasattr(self._storage, "save_workflow_execution"):
            self._storage.save_workflow_execution(execution)
        
        return True
    
    def _validate_inputs(self, workflow: WorkflowDefinition, inputs: Dict[str, Any]) -> None:
        """Validate required inputs for workflow."""
        missing_inputs = []
        for required_input in workflow.required_inputs:
            if required_input not in inputs:
                missing_inputs.append(required_input)
        
        if missing_inputs:
            raise ValueError(f"Missing required inputs: {', '.join(missing_inputs)}")
    
    async def _execute_step(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single workflow step."""
        handler = self._step_handlers.get(step.step_type)
        if not handler:
            raise ValueError(f"No handler for step type: {step.step_type}")
        
        # Prepare step inputs
        step_inputs = {}
        for input_name in step.required_inputs + step.optional_inputs:
            if input_name in inputs:
                step_inputs[input_name] = inputs[input_name]
            elif input_name in execution.step_results:
                step_inputs[input_name] = execution.step_results[input_name]
        
        # Execute step with timeout
        try:
            result = await asyncio.wait_for(
                handler(step, execution, step_inputs),
                timeout=step.timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            raise Exception(f"Step {step.step_id} timed out")
    
    async def _handle_create_project(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle project creation step."""
        title = inputs.get("title", "Workflow Project")
        project = project_store.create_project({"title": title})
        
        if not project:
            raise Exception("Failed to create project")
        
        return {"project_id": project.project_id, "project": project}
    
    async def _handle_generate_scenes(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle scene generation step."""
        project_id = execution.project_id
        project = project_store.get_project(project_id)
        
        if not project:
            raise Exception("Project not found")
        
        # Generate scenes using existing workflow service
        result = generate_short_film_workflow_service.handle_generate_short_film_request(
            project_id=project_id,
            payload={
                "concept": inputs.get("concept", ""),
                "manual_overrides": inputs.get("manual_overrides", {}),
                "submit_renders": False,  # Don't render in this step
                "assemble_final": False,
            },
        )
        if asyncio.iscoroutine(result):
            result = await result
        
        return {"scenes": result.get("project", {}).get("execution_summary", {})}
    
    async def _handle_render_shots(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle shot rendering step."""
        project_id = execution.project_id
        project = project_store.get_project(project_id)
        
        if not project:
            raise Exception("Project not found")
        
        # Render shots using existing workflow service
        result = generate_short_film_workflow_service.handle_generate_short_film_request(
            project_id=project_id,
            payload={
                "concept": inputs.get("concept", ""),
                "manual_overrides": inputs.get("manual_overrides", {}),
                "submit_renders": True,
                "assemble_final": False,
            },
        )
        if asyncio.iscoroutine(result):
            result = await result
        
        return {"render_jobs": result.get("render_jobs", [])}
    
    async def _handle_assemble_film(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle film assembly step."""
        project_id = execution.project_id
        project = project_store.get_project(project_id)
        
        if not project:
            raise Exception("Project not found")
        
        # Assemble film using existing workflow service
        result = generate_short_film_workflow_service.handle_generate_short_film_request(
            project_id=project_id,
            payload={
                "concept": inputs.get("concept", ""),
                "manual_overrides": inputs.get("manual_overrides", {}),
                "submit_renders": True,
                "assemble_final": True,
            },
        )
        if asyncio.iscoroutine(result):
            result = await result
        
        return {"assembly": result.get("assembly", {})}
    
    async def _handle_create_review(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle review creation step."""
        output_url = inputs.get("output_url")
        if not output_url:
            raise Exception("Output URL required for review")
        
        review = short_film_review_service.create_review(
            project_id=execution.project_id,
            output_url=output_url,
            reviewer=inputs.get("reviewer", "Workflow"),
            notes=inputs.get("notes", ""),
        )
        
        return {"review": review}
    
    async def _handle_create_revision(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle revision creation step."""
        review_id = inputs.get("review_id")
        original_job_id = inputs.get("original_job_id")
        
        if not review_id or not original_job_id:
            raise Exception("Review ID and original job ID required for revision")
        
        revision = clip_revision_service.create_revision(
            project_id=execution.project_id,
            review_id=review_id,
            original_job_id=original_job_id,
            provider=inputs.get("provider", "runway"),
            revision_prompt=inputs.get("revision_prompt", ""),
        )
        
        return {"revision": revision}
    
    async def _handle_create_package(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle package creation step."""
        final_output_url = inputs.get("final_output_url")
        if not final_output_url:
            raise Exception("Final output URL required for package")
        
        package = final_short_film_package_service.create_package_from_project(
            project_id=execution.project_id,
            film_title=inputs.get("film_title", "Workflow Film"),
            final_output_url=final_output_url,
            final_output_path=inputs.get("final_output_path"),
            has_title_card=inputs.get("has_title_card", True),
            has_end_card=inputs.get("has_end_card", True),
            has_soundtrack=inputs.get("has_soundtrack", True),
        )
        
        return {"package": package}


# Global service instance
workflow_runner_service = WorkflowRunnerService()
