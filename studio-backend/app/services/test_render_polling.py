"""
Tests for background Runway job polling functionality.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.render import RenderService
from app.models import RenderJobModel, RenderJobInput, RenderJobOutput, ProviderConfig


@pytest.fixture
def render_service():
    """Create a RenderService instance for testing"""
    service = RenderService()
    return service


@pytest.fixture
def mock_rendering_job():
    """Create a mock job in rendering state"""
    return RenderJobModel(
        id="job-test-001",
        project_id="project-001",
        shot_id="scene_001_shot_001",
        provider="runway",
        provider_job_id="runway-task-123",
        status="rendering",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="Test prompt",
            referenceAssets=[],
            parameters={}
        ),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )


@pytest.fixture
def mock_processing_job():
    """Create a mock job in processing state"""
    return RenderJobModel(
        id="job-test-002",
        project_id="project-001",
        shot_id="scene_001_shot_002",
        provider="runway",
        provider_job_id="runway-task-456",
        status="processing",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Test prompt 2",
            referenceAssets=[],
            parameters={}
        ),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )


@pytest.fixture
def mock_complete_job():
    """Create a mock job in complete state"""
    return RenderJobModel(
        id="job-test-003",
        project_id="project-001",
        shot_id="scene_001_shot_003",
        provider="runway",
        provider_job_id="runway-task-789",
        status="complete",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_003",
            prompt="Test prompt 3",
            referenceAssets=[],
            parameters={}
        ),
        output_payload=RenderJobOutput(
            asset_url="https://example.com/video.mp4",
            thumbnail_url="https://example.com/thumb.jpg",
            metadata={}
        ),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat()
    )


def test_get_jobs_by_status_returns_matching_jobs(render_service, mock_rendering_job, mock_processing_job, mock_complete_job):
    """Test that _get_jobs_by_status correctly filters jobs by status"""
    # Add jobs to service
    render_service._jobs[mock_rendering_job.id] = mock_rendering_job
    render_service._jobs[mock_processing_job.id] = mock_processing_job
    render_service._jobs[mock_complete_job.id] = mock_complete_job
    
    # Get jobs in rendering or processing state
    active_jobs = render_service._get_jobs_by_status(["rendering", "processing"])
    
    assert len(active_jobs) == 2
    assert mock_rendering_job in active_jobs
    assert mock_processing_job in active_jobs
    assert mock_complete_job not in active_jobs


def test_get_jobs_by_status_returns_empty_when_no_matches(render_service, mock_complete_job):
    """Test that _get_jobs_by_status returns empty list when no jobs match"""
    render_service._jobs[mock_complete_job.id] = mock_complete_job
    
    active_jobs = render_service._get_jobs_by_status(["rendering", "processing"])
    
    assert len(active_jobs) == 0


def test_get_jobs_by_status_handles_empty_jobs(render_service):
    """Test that _get_jobs_by_status handles empty job dict"""
    active_jobs = render_service._get_jobs_by_status(["rendering", "processing"])
    
    assert len(active_jobs) == 0
    assert active_jobs == []


@pytest.mark.asyncio
async def test_poll_active_runway_jobs_calls_reconcile_for_each_job(render_service, mock_rendering_job, mock_processing_job):
    """Test that poll_active_runway_jobs calls reconcile_completed_runway_task for each active job"""
    # Add jobs to service
    render_service._jobs[mock_rendering_job.id] = mock_rendering_job
    render_service._jobs[mock_processing_job.id] = mock_processing_job
    
    # Mock reconcile_completed_runway_task
    reconcile_calls = []
    
    async def mock_reconcile(job_id):
        reconcile_calls.append(job_id)
        # Stop the loop after processing both jobs
        if len(reconcile_calls) >= 2:
            raise KeyboardInterrupt("Test complete")
        return render_service._jobs[job_id]
    
    render_service.reconcile_completed_runway_task = mock_reconcile
    
    # Run polling loop (will be interrupted after processing jobs)
    try:
        await render_service.poll_active_runway_jobs()
    except KeyboardInterrupt:
        pass
    
    # Verify reconcile was called for both jobs
    assert mock_rendering_job.id in reconcile_calls
    assert mock_processing_job.id in reconcile_calls


@pytest.mark.asyncio
async def test_poll_active_runway_jobs_never_raises_on_reconcile_error(render_service, mock_rendering_job):
    """Test that poll_active_runway_jobs continues even when reconcile throws"""
    render_service._jobs[mock_rendering_job.id] = mock_rendering_job
    
    call_count = [0]
    
    async def mock_reconcile_that_fails(job_id):
        call_count[0] += 1
        if call_count[0] >= 3:
            raise KeyboardInterrupt("Test complete")
        raise Exception("Reconcile failed")
    
    render_service.reconcile_completed_runway_task = mock_reconcile_that_fails
    
    # Run polling loop - should not raise despite reconcile errors
    try:
        await render_service.poll_active_runway_jobs()
    except KeyboardInterrupt:
        pass
    
    # Verify it tried multiple times despite errors
    assert call_count[0] >= 3


@pytest.mark.asyncio
async def test_poll_active_runway_jobs_never_raises_on_loop_error(render_service):
    """Test that poll_active_runway_jobs continues even when the loop itself throws"""
    iteration_count = [0]
    
    original_get_jobs = render_service._get_jobs_by_status
    
    def mock_get_jobs_that_fails(statuses):
        iteration_count[0] += 1
        if iteration_count[0] >= 3:
            raise KeyboardInterrupt("Test complete")
        raise Exception("Loop error")
    
    render_service._get_jobs_by_status = mock_get_jobs_that_fails
    
    # Run polling loop - should not raise despite loop errors
    try:
        await render_service.poll_active_runway_jobs()
    except KeyboardInterrupt:
        pass
    
    # Verify it tried multiple times despite errors
    assert iteration_count[0] >= 3


@pytest.mark.asyncio
async def test_poll_active_runway_jobs_only_processes_runway_jobs(render_service):
    """Test that poll_active_runway_jobs only processes jobs with provider='runway'"""
    # Create jobs with different providers
    runway_job = RenderJobModel(
        id="job-runway",
        project_id="project-001",
        shot_id="scene_001_shot_001",
        provider="runway",
        provider_job_id="runway-task-123",
        status="rendering",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="Test",
            referenceAssets=[],
            parameters={}
        ),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    simulated_job = RenderJobModel(
        id="job-simulated",
        project_id="project-001",
        shot_id="scene_001_shot_002",
        provider="simulated",
        provider_job_id="sim-task-456",
        status="rendering",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_002",
            prompt="Test",
            referenceAssets=[],
            parameters={}
        ),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    render_service._jobs[runway_job.id] = runway_job
    render_service._jobs[simulated_job.id] = simulated_job
    
    reconcile_calls = []
    
    async def mock_reconcile(job_id):
        reconcile_calls.append(job_id)
        raise KeyboardInterrupt("Test complete")
    
    render_service.reconcile_completed_runway_task = mock_reconcile
    
    try:
        await render_service.poll_active_runway_jobs()
    except KeyboardInterrupt:
        pass
    
    # Only runway job should be reconciled
    assert runway_job.id in reconcile_calls
    assert simulated_job.id not in reconcile_calls


@pytest.mark.asyncio
async def test_poll_active_runway_jobs_sleeps_between_iterations(render_service):
    """Test that poll_active_runway_jobs sleeps 10 seconds between iterations"""
    iteration_count = [0]
    sleep_calls = []
    
    original_sleep = asyncio.sleep
    
    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        iteration_count[0] += 1
        if iteration_count[0] >= 2:
            raise KeyboardInterrupt("Test complete")
    
    with patch('asyncio.sleep', mock_sleep):
        try:
            await render_service.poll_active_runway_jobs()
        except KeyboardInterrupt:
            pass
    
    # Verify it slept for 10 seconds between iterations
    assert len(sleep_calls) >= 2
    assert all(s == 10 for s in sleep_calls)


def test_timeout_metadata_structure():
    """Test that timeout metadata has the correct structure"""
    job = RenderJobModel(
        id="job-timeout-test",
        project_id="project-001",
        shot_id="scene_001_shot_001",
        provider="runway",
        status="rendering",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="Test",
            referenceAssets=[],
            parameters={}
        ),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Simulate timeout metadata being set
    job.metadata = {}
    job.metadata["timeout_at"] = datetime.now().isoformat()
    job.metadata["timeout_note"] = (
        "Runway submission timed out after 5 minutes. "
        "Background polling will continue checking for completion."
    )
    
    # Verify metadata structure
    assert "timeout_at" in job.metadata
    assert "timeout_note" in job.metadata
    assert isinstance(job.metadata["timeout_at"], str)
    assert "5 minutes" in job.metadata["timeout_note"]
    assert "Background polling" in job.metadata["timeout_note"]


@pytest.mark.asyncio
async def test_poll_active_runway_jobs_handles_no_active_jobs(render_service, mock_complete_job):
    """Test that poll_active_runway_jobs handles case with no active jobs gracefully"""
    # Only add completed job
    render_service._jobs[mock_complete_job.id] = mock_complete_job
    
    iteration_count = [0]
    
    original_sleep = asyncio.sleep
    
    async def mock_sleep(seconds):
        iteration_count[0] += 1
        if iteration_count[0] >= 2:
            raise KeyboardInterrupt("Test complete")
    
    with patch('asyncio.sleep', mock_sleep):
        try:
            await render_service.poll_active_runway_jobs()
        except KeyboardInterrupt:
            pass
    
    # Should still loop and sleep even with no active jobs
    assert iteration_count[0] >= 2
