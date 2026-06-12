"""
Tests for Session Debrief Service.
"""
import pytest
from datetime import datetime, timedelta
from app.services.session_debrief_service import SessionDebriefService


@pytest.fixture
def debrief_service():
    """Create a session debrief service instance."""
    return SessionDebriefService()


@pytest.fixture
def sample_project_data():
    """Sample project data for testing."""
    return {
        "project_id": "test_project",
        "title": "Test Film",
        "render_queue": [
            {
                "id": "job_001",
                "shot_id": "shot_001",
                "status": "complete",
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": "job_002",
                "shot_id": "shot_002",
                "status": "failed",
                "updated_at": datetime.now().isoformat(),
                "error_message": "Render timeout",
            },
        ],
        "shot_approval_gates": [
            {
                "shot_id": "shot_001",
                "status": "passed",
            },
            {
                "shot_id": "shot_003",
                "status": "pending",
            },
        ],
        "storyboard_wall": [
            {
                "shot_id": "shot_001",
                "status": "approved",
            },
        ],
        "continuity_register": {
            "open_issues": 2,
            "last_checked": datetime.now().isoformat(),
        },
        "updated_at": datetime.now().isoformat(),
    }


@pytest.mark.asyncio
async def test_generate_debrief_basic(debrief_service, sample_project_data):
    """Test basic debrief generation."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    assert debrief["project_id"] == "test_project"
    assert debrief["session_start"] == session_start
    assert debrief["session_end"] == session_end
    assert "decisions_made" in debrief
    assert "what_changed" in debrief
    assert "unresolved_items" in debrief
    assert "continuity_state" in debrief
    assert "next_session_focus" in debrief
    assert "advisory" in debrief
    assert "generated_at" in debrief


@pytest.mark.asyncio
async def test_extract_decisions_includes_render_approvals(debrief_service, sample_project_data):
    """Test that decisions include render approvals."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    decisions = debrief["decisions_made"]
    assert len(decisions) > 0
    
    # Should include render approval
    render_decisions = [d for d in decisions if d["type"] == "render_approved"]
    assert len(render_decisions) > 0


@pytest.mark.asyncio
async def test_extract_decisions_includes_shot_approvals(debrief_service, sample_project_data):
    """Test that decisions include shot approvals."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    decisions = debrief["decisions_made"]
    
    # Should include shot approval
    shot_decisions = [d for d in decisions if d["type"] == "shot_approved"]
    assert len(shot_decisions) > 0


@pytest.mark.asyncio
async def test_extract_changes_includes_completed_renders(debrief_service, sample_project_data):
    """Test that changes include completed renders."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    changes = debrief["what_changed"]
    assert len(changes) > 0
    
    # Should mention completed renders
    render_changes = [c for c in changes if "render" in c.lower()]
    assert len(render_changes) > 0


@pytest.mark.asyncio
async def test_unresolved_items_includes_failed_renders(debrief_service, sample_project_data):
    """Test that unresolved items include failed renders."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    unresolved = debrief["unresolved_items"]
    assert len(unresolved) > 0
    
    # Should include failed render
    failed_renders = [u for u in unresolved if "failed render" in u["item"].lower()]
    assert len(failed_renders) > 0
    assert "shot_002" in failed_renders[0]["item"]


@pytest.mark.asyncio
async def test_unresolved_items_includes_pending_approvals(debrief_service, sample_project_data):
    """Test that unresolved items include pending approvals."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    unresolved = debrief["unresolved_items"]
    
    # Should include pending approval
    pending_approvals = [u for u in unresolved if "pending approval" in u["item"].lower()]
    assert len(pending_approvals) > 0


@pytest.mark.asyncio
async def test_unresolved_items_includes_continuity_issues(debrief_service, sample_project_data):
    """Test that unresolved items include continuity issues."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    unresolved = debrief["unresolved_items"]
    
    # Should include continuity issues
    continuity_issues = [u for u in unresolved if "continuity" in u["item"].lower()]
    assert len(continuity_issues) > 0


@pytest.mark.asyncio
async def test_continuity_state_clean(debrief_service):
    """Test continuity state when no issues."""
    project_data = {
        "continuity_register": {
            "open_issues": 0,
        },
    }
    
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=project_data,
    )
    
    assert "clean" in debrief["continuity_state"].lower()


@pytest.mark.asyncio
async def test_continuity_state_with_issues(debrief_service, sample_project_data):
    """Test continuity state when issues exist."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    assert "2" in debrief["continuity_state"]
    assert "issue" in debrief["continuity_state"].lower()


@pytest.mark.asyncio
async def test_next_session_focus_includes_unresolved(debrief_service, sample_project_data):
    """Test that next session focus includes unresolved items."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    focus = debrief["next_session_focus"]
    assert len(focus) > 0
    assert len(focus) <= 3  # Should limit to 3 items


@pytest.mark.asyncio
async def test_advisory_reflects_session_state(debrief_service, sample_project_data):
    """Test that advisory reflects the session state."""
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=sample_project_data,
    )
    
    advisory = debrief["advisory"]
    assert len(advisory) > 0
    # Should mention unresolved items
    assert "item" in advisory.lower() or "attention" in advisory.lower()


@pytest.mark.asyncio
async def test_empty_project_data(debrief_service):
    """Test debrief generation with minimal project data."""
    project_data = {}
    
    session_start = (datetime.now() - timedelta(hours=1)).isoformat()
    session_end = datetime.now().isoformat()
    
    debrief = await debrief_service.generate_debrief(
        project_id="test_project",
        session_start=session_start,
        session_end=session_end,
        project_data=project_data,
    )
    
    # Should still generate a valid debrief
    assert debrief["project_id"] == "test_project"
    assert len(debrief["decisions_made"]) > 0  # Should have placeholder
    assert len(debrief["what_changed"]) > 0
    assert len(debrief["next_session_focus"]) > 0
    assert len(debrief["advisory"]) > 0
