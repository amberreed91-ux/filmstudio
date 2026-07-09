"""
Tests for Render Retry Service - Automated prompt adherence retry loop.

Tests:
1. evaluate_and_retry with passing score (no retry)
2. evaluate_and_retry with correctable score (retry with diff)
3. evaluate_and_retry with manual_review score (no retry)
4. Stuck shot detection (score improves by < 5 points)
5. Max attempts reached (no retry even if correctable)
6. Attempt persistence to render_attempts table
7. Diff application and slot correction
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.render_retry_service import RenderRetryService, STUCK_SHOT_THRESHOLD
from app.services.adherence_service import AdherenceScore, CorrectiveDiff, CorrectionOp, DimensionScore


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage with render_attempts table."""
    import sqlite3
    
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create render_attempts table
    cursor.execute("""
        CREATE TABLE render_attempts (
            shot_id TEXT NOT NULL,
            attempt_n INTEGER NOT NULL,
            prompt_text TEXT NOT NULL,
            provider TEXT NOT NULL,
            adherence_score REAL,
            score_json TEXT,
            diff_json TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (shot_id, attempt_n)
        )
    """)
    conn.commit()
    conn.close()
    
    # Create mock storage object
    class MockStorage:
        def __init__(self, db_path):
            self.db_path = db_path
        
        def _get_connection(self):
            import sqlite3
            from contextlib import contextmanager
            
            @contextmanager
            def conn_ctx():
                conn = sqlite3.connect(str(self.db_path))
                try:
                    yield conn
                finally:
                    conn.close()
            
            return conn_ctx()
    
    return MockStorage(db_path)


@pytest.fixture
def mock_adherence_service():
    """Create mock adherence service."""
    service = MagicMock()
    service.score_render_attempt = AsyncMock()
    service.generate_corrective_diff = AsyncMock()
    service.apply_diff = MagicMock()
    return service


@pytest.fixture
def mock_keyframe_service():
    """Create mock keyframe service."""
    service = MagicMock()
    return service


@pytest.fixture
def retry_service(temp_storage, mock_adherence_service, mock_keyframe_service):
    """Create retry service with mocked dependencies."""
    return RenderRetryService(
        storage=temp_storage,
        adherence_service=mock_adherence_service,
        keyframe_service=mock_keyframe_service,
    )


@pytest.fixture
def passing_score():
    """Create a passing adherence score (score >= 80)."""
    return AdherenceScore(
        shot_id="shot_001",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=85.0,
                evidence="Character matches expected state",
                expected="Weathered man in tattered coat",
                observed="Weathered man in tattered coat",
            ),
            "action": DimensionScore(
                score=90.0,
                evidence="Action matches expected",
                expected="Walking slowly",
                observed="Walking slowly",
            ),
            "camera": DimensionScore(
                score=80.0,
                evidence="Camera matches expected",
                expected="Wide shot",
                observed="Wide shot",
            ),
            "lighting": DimensionScore(
                score=85.0,
                evidence="Lighting matches expected",
                expected="Golden hour",
                observed="Golden hour",
            ),
            "environment_persistence": DimensionScore(
                score=80.0,
                evidence="Environment consistent",
                expected="Desert landscape",
                observed="Desert landscape",
            ),
        },
        temporal_drift={"start_score": 85.0, "end_score": 80.0},
        adherence_score=84.0,
        verdict="pass",
        failed_slots=[],
    )


@pytest.fixture
def correctable_score():
    """Create a correctable adherence score (50 <= score < 80)."""
    return AdherenceScore(
        shot_id="shot_002",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=45.0,  # Failed
                evidence="Character appearance differs",
                expected="Weathered man in tattered coat",
                observed="Young man in clean jacket",
            ),
            "action": DimensionScore(
                score=70.0,
                evidence="Action partially matches",
                expected="Walking slowly",
                observed="Walking at moderate pace",
            ),
            "camera": DimensionScore(
                score=60.0,
                evidence="Camera angle slightly off",
                expected="Wide shot",
                observed="Medium-wide shot",
            ),
            "lighting": DimensionScore(
                score=75.0,
                evidence="Lighting close but not quite right",
                expected="Golden hour",
                observed="Late afternoon",
            ),
            "environment_persistence": DimensionScore(
                score=80.0,
                evidence="Environment consistent",
                expected="Desert landscape",
                observed="Desert landscape",
            ),
        },
        temporal_drift={"start_score": 65.0, "end_score": 60.0},
        adherence_score=62.5,
        verdict="correctable",
        failed_slots=["character_state"],
    )


@pytest.fixture
def manual_review_score():
    """Create a manual review score (score < 50)."""
    return AdherenceScore(
        shot_id="shot_003",
        attempt_n=1,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=30.0,
                evidence="Character completely wrong",
                expected="Weathered man in tattered coat",
                observed="Woman in modern dress",
            ),
            "action": DimensionScore(
                score=40.0,
                evidence="Action wrong",
                expected="Walking slowly",
                observed="Standing still",
            ),
            "camera": DimensionScore(
                score=50.0,
                evidence="Camera wrong",
                expected="Wide shot",
                observed="Close-up",
            ),
            "lighting": DimensionScore(
                score=45.0,
                evidence="Lighting wrong",
                expected="Golden hour",
                observed="Midday harsh",
            ),
            "environment_persistence": DimensionScore(
                score=60.0,
                evidence="Environment partially wrong",
                expected="Desert landscape",
                observed="Rocky terrain",
            ),
        },
        temporal_drift={"start_score": 45.0, "end_score": 40.0},
        adherence_score=43.75,
        verdict="manual_review",
        failed_slots=["character_state", "action", "camera", "lighting"],
    )


@pytest.mark.asyncio
async def test_evaluate_and_retry_passing_score(
    retry_service,
    mock_adherence_service,
    mock_keyframe_service,
    passing_score,
    temp_storage,
):
    """Test that passing score stops retry loop."""
    # Mock frame extraction - return list of keyframe objects
    mock_keyframes = [
        MagicMock(frame_path="/path/frame_0.jpg"),
        MagicMock(frame_path="/path/frame_1.jpg"),
        MagicMock(frame_path="/path/frame_2.jpg"),
    ]
    mock_keyframe_service.extract_keyframes_representative = MagicMock(
        return_value=mock_keyframes
    )
    
    # Mock adherence scoring
    mock_adherence_service.score_render_attempt.return_value = passing_score
    
    # Mock keyframe service on retry_service
    retry_service._keyframe_service = mock_keyframe_service
    
    # Evaluate
    result = await retry_service.evaluate_and_retry(
        shot_id="shot_001",
        attempt_n=1,
        video_url="https://example.com/video.mp4",
        video_path="/local/video.mp4",
        asset_id="asset_001",
        project_id="proj_001",
        provider="runway",
        current_prompt="A weathered man walks slowly through a desert at golden hour",
        prompt_slots={
            "character_state": "Weathered man in tattered coat",
            "action": "Walking slowly",
            "camera": "Wide shot",
            "lighting": "Golden hour",
            "environment_persistence": "Desert landscape",
        },
        locked_seed=12345,
    )
    
    # Assertions
    assert result["verdict"] == "pass"
    assert result["adherence_score"] == 84.0
    assert result["should_retry"] is False
    assert "score" in result
    
    # Verify attempt was persisted
    import sqlite3
    with temp_storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT shot_id, attempt_n, adherence_score FROM render_attempts"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "shot_001"
        assert row[1] == 1
        assert row[2] == 84.0


@pytest.mark.asyncio
async def test_evaluate_and_retry_correctable_with_diff(
    retry_service,
    mock_adherence_service,
    mock_keyframe_service,
    correctable_score,
    temp_storage,
):
    """Test that correctable score generates diff and requests retry."""
    # Mock frame extraction - return list of keyframe objects
    mock_keyframes = [
        MagicMock(frame_path="/path/frame_0.jpg"),
        MagicMock(frame_path="/path/frame_1.jpg"),
        MagicMock(frame_path="/path/frame_2.jpg"),
    ]
    mock_keyframe_service.extract_keyframes_representative = MagicMock(
        return_value=mock_keyframes
    )
    
    # Mock adherence scoring
    mock_adherence_service.score_render_attempt.return_value = correctable_score
    
    # Mock diff generation
    diff = CorrectiveDiff(
        base_attempt=1,
        seed_locked=True,
        ops=[
            CorrectionOp(
                slot="character_state",
                op="strengthen",
                old_text="Weathered man in tattered coat",
                new_text="EMPHASIS: Elderly, deeply weathered man. Tattered, worn coat",
                reason="Character appearance was too young - strengthen age and wear details",
                char_delta=35,
            )
        ],
        chars_remaining=15,
    )
    mock_adherence_service.generate_corrective_diff.return_value = diff
    
    # Mock diff application
    corrected_slots = {
        "character_state": "EMPHASIS: Elderly, deeply weathered man. Tattered, worn coat. Weathered man in tattered coat",
        "action": "Walking slowly",
        "camera": "Wide shot",
        "lighting": "Golden hour",
        "environment_persistence": "Desert landscape",
    }
    mock_adherence_service.apply_diff.return_value = corrected_slots
    
    # Mock keyframe service on retry_service
    retry_service._keyframe_service = mock_keyframe_service
    
    # Evaluate
    result = await retry_service.evaluate_and_retry(
        shot_id="shot_002",
        attempt_n=1,
        video_url="https://example.com/video.mp4",
        video_path="/local/video.mp4",
        asset_id="asset_002",
        project_id="proj_001",
        provider="runway",
        current_prompt="A weathered man walks slowly through a desert at golden hour",
        prompt_slots={
            "character_state": "Weathered man in tattered coat",
            "action": "Walking slowly",
            "camera": "Wide shot",
            "lighting": "Golden hour",
            "environment_persistence": "Desert landscape",
        },
        locked_seed=12345,
    )
    
    # Assertions
    assert result["verdict"] == "correctable"
    assert result["adherence_score"] == 62.5
    assert result["should_retry"] is True
    assert result["corrected_slots"] == corrected_slots
    assert result["locked_seed"] == 12345
    assert "diff" in result
    
    # Verify diff was generated
    mock_adherence_service.generate_corrective_diff.assert_called_once()
    mock_adherence_service.apply_diff.assert_called_once()
    
    # Verify attempt was persisted with diff_json
    import sqlite3
    with temp_storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT shot_id, attempt_n, adherence_score, diff_json FROM render_attempts"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "shot_002"
        assert row[1] == 1
        assert row[2] == 62.5
        assert row[3] is not None  # diff_json should be present
        
        diff_data = json.loads(row[3])
        assert len(diff_data["ops"]) == 1
        assert diff_data["ops"][0]["slot"] == "character_state"


@pytest.mark.asyncio
async def test_evaluate_and_retry_manual_review(
    retry_service,
    mock_adherence_service,
    mock_keyframe_service,
    manual_review_score,
    temp_storage,
):
    """Test that manual review score stops retry loop."""
    # Mock frame extraction - return list of keyframe objects
    mock_keyframes = [
        MagicMock(frame_path="/path/frame_0.jpg"),
        MagicMock(frame_path="/path/frame_1.jpg"),
        MagicMock(frame_path="/path/frame_2.jpg"),
    ]
    mock_keyframe_service.extract_keyframes_representative = MagicMock(
        return_value=mock_keyframes
    )
    
    # Mock adherence scoring
    mock_adherence_service.score_render_attempt.return_value = manual_review_score
    
    # Mock keyframe service on retry_service
    retry_service._keyframe_service = mock_keyframe_service
    
    # Evaluate
    result = await retry_service.evaluate_and_retry(
        shot_id="shot_003",
        attempt_n=1,
        video_url="https://example.com/video.mp4",
        video_path="/local/video.mp4",
        asset_id="asset_003",
        project_id="proj_001",
        provider="runway",
        current_prompt="A weathered man walks slowly through a desert at golden hour",
        prompt_slots={
            "character_state": "Weathered man in tattered coat",
            "action": "Walking slowly",
            "camera": "Wide shot",
            "lighting": "Golden hour",
            "environment_persistence": "Desert landscape",
        },
        locked_seed=12345,
    )
    
    # Assertions
    assert result["verdict"] == "manual_review"
    assert result["adherence_score"] == 43.75
    assert result["should_retry"] is False
    assert "reason" in result
    
    # Verify attempt was persisted
    import sqlite3
    with temp_storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT shot_id, attempt_n, adherence_score FROM render_attempts"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "shot_003"
        assert row[1] == 1
        assert row[2] == 43.75


@pytest.mark.asyncio
async def test_stuck_shot_detection(
    retry_service,
    mock_adherence_service,
    mock_keyframe_service,
    temp_storage,
):
    """Test that stuck shot detection stops retry loop."""
    # Insert first attempt with score 60.0
    import sqlite3
    with temp_storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO render_attempts 
            (shot_id, attempt_n, prompt_text, provider, adherence_score, 
             score_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "shot_stuck",
                1,
                "Prompt v1",
                "runway",
                60.0,
                json.dumps({"verdict": "correctable"}),
                "2024-01-01T00:00:00",
            ),
        )
        conn.commit()
    
    # Mock frame extraction - return list of keyframe objects
    mock_keyframes = [
        MagicMock(frame_path="/path/frame_0.jpg"),
        MagicMock(frame_path="/path/frame_1.jpg"),
        MagicMock(frame_path="/path/frame_2.jpg"),
    ]
    mock_keyframe_service.extract_keyframes_representative = MagicMock(
        return_value=mock_keyframes
    )
    
    # Mock adherence scoring for attempt 2 with score 63.0 (improvement < 5)
    score_attempt_2 = AdherenceScore(
        shot_id="shot_stuck",
        attempt_n=2,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions={
            "character_state": DimensionScore(
                score=50.0,
                evidence="Still wrong",
                expected="Expected",
                observed="Observed",
            ),
            "action": DimensionScore(70.0, "", "", ""),
            "camera": DimensionScore(65.0, "", "", ""),
            "lighting": DimensionScore(70.0, "", "", ""),
            "environment_persistence": DimensionScore(70.0, "", "", ""),
        },
        temporal_drift={"start_score": 65.0, "end_score": 60.0},
        adherence_score=63.0,  # Only 3-point improvement from 60.0
        verdict="correctable",
        failed_slots=["character_state"],
    )
    mock_adherence_service.score_render_attempt.return_value = score_attempt_2
    
    # Mock keyframe service on retry_service
    retry_service._keyframe_service = mock_keyframe_service
    
    # Evaluate attempt 2
    result = await retry_service.evaluate_and_retry(
        shot_id="shot_stuck",
        attempt_n=2,
        video_url="https://example.com/video.mp4",
        video_path="/local/video.mp4",
        asset_id="asset_stuck",
        project_id="proj_001",
        provider="runway",
        current_prompt="Prompt v2 (corrected)",
        prompt_slots={
            "character_state": "Corrected character state",
            "action": "Action",
            "camera": "Camera",
            "lighting": "Lighting",
            "environment_persistence": "Environment",
        },
        locked_seed=12345,
    )
    
    # Assertions
    assert result["verdict"] == "stuck"
    assert result["adherence_score"] == 63.0
    assert result["should_retry"] is False
    assert "reason" in result
    assert "unresponsive" in result["reason"].lower()


@pytest.mark.asyncio
async def test_max_attempts_reached(
    retry_service,
    mock_adherence_service,
    mock_keyframe_service,
    correctable_score,
    temp_storage,
):
    """Test that max attempts (3) stops retry loop even if correctable."""
    # Mock frame extraction - return list of keyframe objects
    mock_keyframes = [
        MagicMock(frame_path="/path/frame_0.jpg"),
        MagicMock(frame_path="/path/frame_1.jpg"),
        MagicMock(frame_path="/path/frame_2.jpg"),
    ]
    mock_keyframe_service.extract_keyframes_representative = MagicMock(
        return_value=mock_keyframes
    )
    
    # Create score for attempt 3 that's still correctable
    score_attempt_3 = AdherenceScore(
        shot_id="shot_max",
        attempt_n=3,
        frames_scored=[0.1, 0.5, 0.9],
        dimensions=correctable_score.dimensions,
        temporal_drift=correctable_score.temporal_drift,
        adherence_score=correctable_score.adherence_score,
        verdict="correctable",  # Still correctable
        failed_slots=correctable_score.failed_slots,
    )
    mock_adherence_service.score_render_attempt.return_value = score_attempt_3
    
    # Mock keyframe service on retry_service
    retry_service._keyframe_service = mock_keyframe_service
    
    # Evaluate attempt 3 (max)
    result = await retry_service.evaluate_and_retry(
        shot_id="shot_max",
        attempt_n=3,  # Max attempts
        video_url="https://example.com/video.mp4",
        video_path="/local/video.mp4",
        asset_id="asset_max",
        project_id="proj_001",
        provider="runway",
        current_prompt="Prompt v3",
        prompt_slots={
            "character_state": "Character",
            "action": "Action",
            "camera": "Camera",
            "lighting": "Lighting",
            "environment_persistence": "Environment",
        },
        locked_seed=12345,
    )
    
    # Assertions
    assert result["verdict"] == "manual_review"  # Should be manual_review, not correctable
    assert result["should_retry"] is False
    assert "reason" in result
    assert "Max attempts" in result["reason"]
    
    # Verify diff was NOT generated
    mock_adherence_service.generate_corrective_diff.assert_not_called()


def test_persist_attempt(retry_service, temp_storage):
    """Test that attempts are correctly persisted to database."""
    # Persist attempt
    score_json = {
        "shot_id": "shot_persist",
        "attempt_n": 1,
        "adherence_score": 75.0,
        "verdict": "correctable",
        "failed_slots": ["character_state"],
    }
    
    diff_json = {
        "base_attempt": 1,
        "ops": [
            {
                "slot": "character_state",
                "op": "strengthen",
                "old_text": "Old",
                "new_text": "New",
                "reason": "Reason",
                "char_delta": 10,
            }
        ],
    }
    
    retry_service._persist_attempt(
        shot_id="shot_persist",
        attempt_n=1,
        prompt_text="Full prompt text here",
        provider="runway",
        adherence_score=75.0,
        score_json=score_json,
        diff_json=diff_json,
    )
    
    # Verify persistence
    import sqlite3
    with temp_storage._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT shot_id, attempt_n, prompt_text, provider, adherence_score, 
                   score_json, diff_json 
            FROM render_attempts 
            WHERE shot_id = ? AND attempt_n = ?
            """,
            ("shot_persist", 1),
        )
        row = cursor.fetchone()
        
        assert row is not None
        assert row[0] == "shot_persist"
        assert row[1] == 1
        assert row[2] == "Full prompt text here"
        assert row[3] == "runway"
        assert row[4] == 75.0
        
        loaded_score = json.loads(row[5])
        assert loaded_score["verdict"] == "correctable"
        
        loaded_diff = json.loads(row[6])
        assert len(loaded_diff["ops"]) == 1
        assert loaded_diff["ops"][0]["slot"] == "character_state"
