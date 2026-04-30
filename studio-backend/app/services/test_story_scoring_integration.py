"""
Tests for Story Scoring Integration - Phase 4.4

Tests the integration of StoryLevelScoringService into agent_executor.py.
Verifies that story scoring runs non-blocking after director logic and
attaches structured StoryScore data to outputs.

Run with: python -m pytest app/services/test_story_scoring_integration.py -v
"""

import sys
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Test imports from agent_executor
from app.services.agent_executor import AgentExecutor


class TestStoryScoringIntegration:
    """Tests for Phase 4.4 story scoring integration."""

    def test_executor_has_story_scoring_methods(self):
        """Test that AgentExecutor has the story scoring helper methods."""
        executor = AgentExecutor()
        
        # Check helper methods exist
        assert hasattr(executor, '_build_story_scoring_context'), \
            "Missing _build_story_scoring_context method"
        assert hasattr(executor, '_run_story_scoring'), \
            "Missing _run_story_scoring method"

    def test_build_story_scoring_context_returns_context(self):
        """Test that _build_story_scoring_context builds valid context."""
        executor = AgentExecutor()
        
        context = executor._build_story_scoring_context(
            film_id="test_film",
            scene_id="scene_1",
            scene_data={"content": "test scene"},
            director_decision={"approved": True}
        )
        
        assert context is not None
        assert context.film_id == "test_film"
        assert context.scene_id == "scene_1"
        assert context.scene_data == {"content": "test scene"}

    def test_build_story_scoring_context_handles_missing_data(self):
        """Test that _build_story_scoring_context handles missing data gracefully."""
        executor = AgentExecutor()
        
        # Should not raise - returns context with None values
        context = executor._build_story_scoring_context(
            film_id="test_film"
        )
        
        assert context is not None
        assert context.film_id == "test_film"
        assert context.film_structure is None
        assert context.film_memory is None

    def test_run_story_scoring_returns_dict(self):
        """Test that _run_story_scoring returns structured dict."""
        executor = AgentExecutor()
        
        # Mock the story_scoring_service
        mock_score = Mock()
        mock_score.film_id = "test_film"
        mock_score.scope = "scene"
        mock_score.scope_id = "scene_1"
        mock_score.overall_health = 0.75
        mock_score.dimension_scores = {"thesis_alignment": 0.8}
        mock_score.warnings = []
        mock_score.recommendations = []
        mock_score.priority = Mock(value="medium")
        mock_score.timestamp = datetime.now().isoformat()
        mock_score.to_dict = Mock(return_value={
            "film_id": "test_film",
            "scope": "scene",
            "scope_id": "scene_1",
            "overall_health": 0.75,
            "dimension_scores": {"thesis_alignment": 0.8},
            "warnings": [],
            "recommendations": [],
            "priority": "medium",
            "timestamp": mock_score.timestamp
        })
        
        with patch('app.services.agent_executor.story_scoring_service') as mock_service:
            mock_service.score_scene.return_value = mock_score
            
            result = executor._run_story_scoring(
                film_id="test_film",
                scope="scene",
                scene_id="scene_1",
                scene_data={"content": "test"}
            )
        
        assert result is not None
        assert result["film_id"] == "test_film"
        assert result["scope"] == "scene"
        assert result["overall_health"] == 0.75

    def test_run_story_scoring_handles_missing_context(self):
        """Test that _run_story_scoring returns None on error."""
        executor = AgentExecutor()
        
        # Should return None when scoring fails
        with patch('app.services.agent_executor.story_scoring_service') as mock_service:
            mock_service.score_scene.side_effect = Exception("Service error")
            
            result = executor._run_story_scoring(
                film_id="test_film",
                scope="scene",
                scene_id="scene_1"
            )
        
        assert result is None

    def test_run_story_scoring_sequence_scope(self):
        """Test that _run_story_scoring handles sequence scope."""
        executor = AgentExecutor()
        
        mock_score = Mock()
        mock_score.to_dict = Mock(return_value={
            "film_id": "test_film",
            "scope": "sequence",
            "scope_id": "seq_1",
            "overall_health": 0.7
        })
        
        with patch('app.services.agent_executor.story_scoring_service') as mock_service:
            mock_service.score_sequence.return_value = mock_score
            
            result = executor._run_story_scoring(
                film_id="test_film",
                scope="sequence",
                sequence_id="seq_1"
            )
        
        assert result is not None
        assert result["scope"] == "sequence"
        mock_service.score_sequence.assert_called_once()

    def test_run_story_scoring_act_scope(self):
        """Test that _run_story_scoring handles act scope."""
        executor = AgentExecutor()
        
        mock_score = Mock()
        mock_score.to_dict = Mock(return_value={
            "film_id": "test_film",
            "scope": "act",
            "scope_id": "act_1",
            "overall_health": 0.7
        })
        
        with patch('app.services.agent_executor.story_scoring_service') as mock_service:
            mock_service.score_act.return_value = mock_score
            
            result = executor._run_story_scoring(
                film_id="test_film",
                scope="act",
                act_number=1
            )
        
        assert result is not None
        assert result["scope"] == "act"
        mock_service.score_act.assert_called_once()

    def test_run_story_scoring_film_scope(self):
        """Test that _run_story_scoring handles film scope."""
        executor = AgentExecutor()
        
        mock_score = Mock()
        mock_score.to_dict = Mock(return_value={
            "film_id": "test_film",
            "scope": "film",
            "overall_health": 0.8
        })
        
        with patch('app.services.agent_executor.story_scoring_service') as mock_service:
            mock_service.score_film.return_value = mock_score
            
            result = executor._run_story_scoring(
                film_id="test_film",
                scope="film"
            )
        
        assert result is not None
        assert result["scope"] == "film"
        mock_service.score_film.assert_called_once()

    def test_story_scoring_non_blocking(self):
        """Test that story scoring is non-blocking - errors don't propagate."""
        executor = AgentExecutor()
        
        # If story scoring raises, it should be caught and return None
        with patch('app.services.agent_executor.story_scoring_service') as mock_service:
            mock_service.score_scene.side_effect = Exception("Scoring error")
            
            # Should not raise
            result = executor._run_story_scoring(
                film_id="test_film",
                scope="scene",
                scene_id="scene_1"
            )
        
        assert result is None

    def test_story_scoring_import_exists(self):
        """Test that story_scoring_service is imported in agent_executor."""
        from app.services import agent_executor
        assert hasattr(agent_executor, 'story_scoring_service'), \
            "story_scoring_service not imported"
        assert hasattr(agent_executor, 'StoryScoringContext'), \
            "StoryScoringContext not imported"


def run_all_tests():
    """Run all tests."""
    tests = TestStoryScoringIntegration()
    
    test_methods = [m for m in dir(tests) if m.startswith('test_')]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            method = getattr(tests, method_name)
            method()
            print(f"✓ {method_name}")
            passed += 1
        except Exception as e:
            print(f"✗ {method_name}: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)