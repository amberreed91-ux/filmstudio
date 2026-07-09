"""Workflow API endpoints for managing reusable workflows."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.models import WorkflowDefinition, WorkflowExecution
from app.services.workflow_runner_service import workflow_runner_service
from app.services.workflow_definitions import get_workflow, list_workflows, list_workflow_categories

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# Request/Response DTOs
class ExecuteWorkflowRequest(BaseModel):
    workflow_id: str
    project_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionResponse(BaseModel):
    execution_id: str
    workflow_id: str
    project_id: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    current_step: Optional[str] = None
    completed_steps: List[str] = Field(default_factory=list)
    failed_steps: List[str] = Field(default_factory=list)
    step_results: Dict[str, Any] = Field(default_factory=dict)
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    progress_percentage: float = 0.0


class WorkflowDefinitionResponse(BaseModel):
    workflow_id: str
    title: str
    description: str
    version: str
    category: str
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    required_inputs: Dict[str, Any] = Field(default_factory=dict)
    optional_inputs: Dict[str, Any] = Field(default_factory=dict)
    estimated_duration_minutes: int
    status: str
    tags: List[str] = Field(default_factory=list)


# Workflow Management Endpoints
@router.get("/definitions", response_model=List[WorkflowDefinitionResponse])
def list_workflow_definitions(category: Optional[str] = None):
    """List available workflow definitions, optionally filtered by category."""
    workflows = list_workflows(category)
    return [
        WorkflowDefinitionResponse(
            workflow_id=workflow.workflow_id,
            title=workflow.title,
            description=workflow.description,
            version=workflow.version,
            category=workflow.category,
            steps=[step.model_dump() for step in workflow.steps],
            required_inputs=workflow.required_inputs,
            optional_inputs=workflow.optional_inputs,
            estimated_duration_minutes=workflow.estimated_duration_minutes,
            status=workflow.status,
            tags=workflow.tags,
        )
        for workflow in workflows
    ]


@router.get("/definitions/{workflow_id}", response_model=WorkflowDefinitionResponse)
def get_workflow_definition(workflow_id: str):
    """Get a specific workflow definition by ID."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return WorkflowDefinitionResponse(
        workflow_id=workflow.workflow_id,
        title=workflow.title,
        description=workflow.description,
        version=workflow.version,
        category=workflow.category,
        steps=[step.model_dump() for step in workflow.steps],
        required_inputs=workflow.required_inputs,
        optional_inputs=workflow.optional_inputs,
        estimated_duration_minutes=workflow.estimated_duration_minutes,
        status=workflow.status,
        tags=workflow.tags,
    )


@router.get("/categories", response_model=List[str])
def list_workflow_categories_endpoint():
    """List all available workflow categories."""
    return list_workflow_categories()


# Workflow Execution Endpoints
@router.post("/execute", response_model=WorkflowExecutionResponse)
async def execute_workflow(request: ExecuteWorkflowRequest, background_tasks: BackgroundTasks):
    """Execute a workflow with given inputs."""
    # Get workflow definition
    workflow = get_workflow(request.workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    try:
        # Execute workflow
        execution = await workflow_runner_service.execute_workflow(
            workflow=workflow,
            project_id=request.project_id,
            inputs=request.inputs,
        )
        
        return WorkflowExecutionResponse(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            project_id=execution.project_id,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            current_step=execution.current_step,
            completed_steps=execution.completed_steps,
            failed_steps=execution.failed_steps,
            step_results=execution.step_results,
            inputs=execution.inputs,
            outputs=execution.outputs,
            error_message=execution.error_message,
            progress_percentage=execution.progress_percentage,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/executions", response_model=List[WorkflowExecutionResponse])
def list_workflow_executions(project_id: Optional[str] = None):
    """List workflow executions, optionally filtered by project."""
    executions = workflow_runner_service.list_executions(project_id)
    return [
        WorkflowExecutionResponse(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            project_id=execution.project_id,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            current_step=execution.current_step,
            completed_steps=execution.completed_steps,
            failed_steps=execution.failed_steps,
            step_results=execution.step_results,
            inputs=execution.inputs,
            outputs=execution.outputs,
            error_message=execution.error_message,
            progress_percentage=execution.progress_percentage,
        )
        for execution in executions
    ]


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionResponse)
def get_workflow_execution(execution_id: str):
    """Get a specific workflow execution by ID."""
    execution = workflow_runner_service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return WorkflowExecutionResponse(
        execution_id=execution.execution_id,
        workflow_id=execution.workflow_id,
        project_id=execution.project_id,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        current_step=execution.current_step,
        completed_steps=execution.completed_steps,
        failed_steps=execution.failed_steps,
        step_results=execution.step_results,
        inputs=execution.inputs,
        outputs=execution.outputs,
        error_message=execution.error_message,
        progress_percentage=execution.progress_percentage,
    )


@router.post("/executions/{execution_id}/cancel")
async def cancel_workflow_execution(execution_id: str):
    """Cancel a workflow execution."""
    success = await workflow_runner_service.cancel_execution(execution_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel execution")
    
    return {"message": "Execution cancelled successfully"}


@router.delete("/executions/{execution_id}")
def delete_workflow_execution(execution_id: str):
    """Delete a workflow execution."""
    storage = getattr(workflow_runner_service, "_storage", None)
    if not storage or not hasattr(storage, "delete_workflow_execution"):
        raise HTTPException(status_code=501, detail="Storage not available")
    
    success = storage.delete_workflow_execution(execution_id)
    if not success:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return {"message": "Execution deleted successfully"}
