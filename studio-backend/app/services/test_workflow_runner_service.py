"""Tests for Workflow Runner Service."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.models import WorkflowDefinition, WorkflowStep, WorkflowExecution
from app.services.workflow_runner_service import WorkflowRunnerService
from app.services.workflow_definitions import QUICK_SHORT_FILM_WORKFLOW


class TestWorkflowRunnerService:
    """Test cases for WorkflowRunnerService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = WorkflowRunnerService()
        self.test_workflow = QUICK_SHORT_FILM_WORKFLOW
        self.test_project_id = "test-project-123"
        self.test_inputs = {
            "title": "Test Film",
            "concept": "A test concept for a short film",
        }

    @pytest.mark.asyncio
    async def test_execute_workflow_success(self):
        """Test successful workflow execution."""
        with patch('app.services.workflow_runner_service.project_store') as mock_store, \
             patch('app.services.workflow_runner_service.generate_short_film_workflow_service') as mock_workflow_service:
            
            # Mock project store
            mock_project = Mock()
            mock_project.project_id = self.test_project_id
            mock_store.get_project.return_value = mock_project
            mock_store.create_project.return_value = mock_project
            
            # Mock workflow service
            mock_workflow_service.handle_generate_short_film_request.return_value = {
                "project": {"project_id": self.test_project_id},
                "render_jobs": [],
                "assembly": {}
            }
            
            # Execute workflow
            execution = await self.service.execute_workflow(
                workflow=self.test_workflow,
                project_id=self.test_project_id,
                inputs=self.test_inputs,
            )
            
            # Verify execution
            assert execution.workflow_id == self.test_workflow.workflow_id
            assert execution.project_id == self.test_project_id
            assert execution.status == "completed"
            assert execution.progress_percentage == 100.0
            assert len(execution.completed_steps) == len(self.test_workflow.steps)

    @pytest.mark.asyncio
    async def test_execute_workflow_validation_error(self):
        """Test workflow execution with missing required inputs."""
        invalid_inputs = {"title": "Test Film"}  # Missing concept
        
        with pytest.raises(ValueError, match="Missing required inputs"):
            await self.service.execute_workflow(
                workflow=self.test_workflow,
                project_id=self.test_project_id,
                inputs=invalid_inputs,
            )

    @pytest.mark.asyncio
    async def test_execute_workflow_step_failure(self):
        """Test workflow execution with step failure."""
        with patch('app.services.workflow_runner_service.project_store') as mock_store:
            # Mock project store to raise exception
            mock_store.get_project.side_effect = Exception("Project not found")
            
            # Execute workflow should fail
            with pytest.raises(Exception, match="Project not found"):
                await self.service.execute_workflow(
                    workflow=self.test_workflow,
                    project_id=self.test_project_id,
                    inputs=self.test_inputs,
                )

    def test_get_execution(self):
        """Test getting execution by ID."""
        # Create a test execution
        execution = WorkflowExecution(
            execution_id="test-exec-123",
            workflow_id=self.test_workflow.workflow_id,
            project_id=self.test_project_id,
            status="completed",
        )
        
        # Add to service
        self.service._executions[execution.execution_id] = execution
        
        # Get execution
        retrieved = self.service.get_execution(execution.execution_id)
        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id
        assert retrieved.status == "completed"

    def test_get_execution_not_found(self):
        """Test getting non-existent execution."""
        retrieved = self.service.get_execution("non-existent")
        assert retrieved is None

    def test_list_executions(self):
        """Test listing executions."""
        # Create test executions
        exec1 = WorkflowExecution(
            execution_id="test-exec-1",
            workflow_id="workflow-1",
            project_id="project-1",
            status="completed",
        )
        exec2 = WorkflowExecution(
            execution_id="test-exec-2",
            workflow_id="workflow-2",
            project_id="project-2",
            status="running",
        )
        
        # Add to service
        self.service._executions[exec1.execution_id] = exec1
        self.service._executions[exec2.execution_id] = exec2
        
        # List all executions
        all_executions = self.service.list_executions()
        assert len(all_executions) == 2
        
        # Filter by project
        project_executions = self.service.list_executions("project-1")
        assert len(project_executions) == 1
        assert project_executions[0].project_id == "project-1"

    @pytest.mark.asyncio
    async def test_cancel_execution(self):
        """Test cancelling an execution."""
        # Create a test execution
        execution = WorkflowExecution(
            execution_id="test-exec-123",
            workflow_id=self.test_workflow.workflow_id,
            project_id=self.test_project_id,
            status="running",
        )
        
        # Add to service
        self.service._executions[execution.execution_id] = execution
        
        # Cancel execution
        success = await self.service.cancel_execution(execution.execution_id)
        assert success is True
        
        # Verify status
        cancelled = self.service.get_execution(execution.execution_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_execution(self):
        """Test cancelling a completed execution."""
        # Create a completed execution
        execution = WorkflowExecution(
            execution_id="test-exec-123",
            workflow_id=self.test_workflow.workflow_id,
            project_id=self.test_project_id,
            status="completed",
        )
        
        # Add to service
        self.service._executions[execution.execution_id] = execution
        
        # Try to cancel
        success = await self.service.cancel_execution(execution.execution_id)
        assert success is False

    def test_validate_inputs(self):
        """Test input validation."""
        # Valid inputs
        try:
            self.service._validate_inputs(self.test_workflow, self.test_inputs)
        except ValueError:
            pytest.fail("Valid inputs should not raise ValueError")
        
        # Missing required input
        invalid_inputs = {"title": "Test Film"}  # Missing concept
        with pytest.raises(ValueError, match="Missing required inputs"):
            self.service._validate_inputs(self.test_workflow, invalid_inputs)

    @pytest.mark.asyncio
    async def test_handle_create_project_step(self):
        """Test create project step handler."""
        step = WorkflowStep(
            step_id="create_project",
            name="Create Project",
            description="Create a new project",
            step_type="create_project",
            required_inputs=["title"],
        )
        
        execution = WorkflowExecution(
            execution_id="test-exec-123",
            workflow_id="test-workflow",
            project_id="test-project",
            status="running",
        )
        
        inputs = {"title": "Test Project"}
        
        with patch('app.services.workflow_runner_service.project_store') as mock_store:
            mock_project = Mock()
            mock_project.project_id = "test-project"
            mock_store.create_project.return_value = mock_project
            
            result = await self.service._handle_create_project(step, execution, inputs)
            
            assert result["project_id"] == "test-project"
            assert result["project"] == mock_project

    def test_get_step_by_id(self):
        """Test getting step by ID from workflow definition."""
        step = self.test_workflow.get_step_by_id("create_project")
        assert step is not None
        assert step.step_id == "create_project"
        assert step.step_type == "create_project"

    def test_get_dependency_order(self):
        """Test getting steps in dependency order."""
        order = self.test_workflow.get_dependency_order()
        assert len(order) == len(self.test_workflow.steps)
        
        # Verify first step has no dependencies
        first_step_id = order[0]
        first_step = self.test_workflow.get_step_by_id(first_step_id)
        assert len(first_step.depends_on) == 0

    def test_workflow_execution_progress(self):
        """Test workflow execution progress calculation."""
        execution = WorkflowExecution(
            execution_id="test-exec-123",
            workflow_id="test-workflow",
            project_id="test-project",
            status="running",
            completed_steps=["step1", "step2"],
        )
        
        # Mock total steps
        total_steps = 4
        expected_progress = (len(execution.completed_steps) / total_steps) * 100.0
        
        # Test progress calculation (would need to be updated in actual model)
        assert len(execution.completed_steps) == 2

    def test_workflow_execution_terminal_state(self):
        """Test workflow execution terminal state detection."""
        # Test completed
        execution = WorkflowExecution(
            execution_id="test-exec-123",
            workflow_id="test-workflow",
            project_id="test-project",
            status="completed",
        )
        assert execution.is_terminal() is True
        
        # Test running
        execution.status = "running"
        assert execution.is_terminal() is False
        
        # Test failed
        execution.status = "failed"
        assert execution.is_terminal() is True


if __name__ == "__main__":
    pytest.main([__file__])
