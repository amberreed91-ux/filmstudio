"""
Tests for Co-Director Session Service - Phase 10.1

Verifies session lifecycle through the service.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.co_director import CoDirectorSession, SessionMode
from app.services.co_director_session_service import (
    CoDirectorSessionService,
)


class TestCoDirectorSessionService:
    """Tests for CoDirectorSessionService."""
    
    def setup_method(self):
        """Create fresh service for each test."""
        self.service = CoDirectorSessionService()
    
    def test_session_creation_through_service(self):
        """Test session creation returns a valid session."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        
        assert session is not None
        assert isinstance(session, CoDirectorSession)
        assert session.project_id == project_id
        assert session.film_id == film_id
        assert session.session_id is not None
    
    def test_default_passive_mode(self):
        """Test session defaults to PASSIVE mode."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        
        assert session.current_mode == SessionMode.PASSIVE
    
    def test_custom_mode_on_creation(self):
        """Test session can be created with custom mode."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(
            project_id, film_id, mode=SessionMode.ADVISORY
        )
        
        assert session.current_mode == SessionMode.ADVISORY

    def test_experimental_mode_on_creation(self):
        project_id = uuid4()
        film_id = uuid4()
        session = self.service.create_session(project_id, film_id, mode=SessionMode.EXPERIMENTAL)
        assert session.current_mode == SessionMode.EXPERIMENTAL
    
    def test_active_scene_update_through_service(self):
        """Test setting active scene through service."""
        project_id = uuid4()
        film_id = uuid4()
        scene_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        updated = self.service.set_active_scene(session.session_id, scene_id)
        
        assert updated is not None
        assert updated.active_scene_id == scene_id
    
    def test_revision_increment_through_service(self):
        """Test incrementing revision through service."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        assert session.revision_count == 0
        
        updated = self.service.increment_revision(session.session_id)
        
        assert updated is not None
        assert updated.revision_count == 1
    
    def test_accepted_suggestion_recording_through_service(self):
        """Test recording accepted suggestion through service."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        updated = self.service.record_accepted_suggestion(
            session.session_id, "visual_substitution"
        )
        
        assert updated is not None
        assert updated.last_accepted_suggestion == "visual_substitution"
    
    def test_mode_switching_through_service(self):
        """Test switching mode through service."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        assert session.current_mode == SessionMode.PASSIVE
        
        updated = self.service.set_mode(session.session_id, SessionMode.COLLABORATIVE)
        
        assert updated is not None
        assert updated.current_mode == SessionMode.COLLABORATIVE
    
    def test_missing_session_returns_none(self):
        """Test that operations on missing sessions return None."""
        nonexistent_id = uuid4()
        
        assert self.service.get_session(nonexistent_id) is None
        assert self.service.set_active_scene(nonexistent_id, uuid4()) is None
        assert self.service.increment_revision(nonexistent_id) is None
        assert self.service.record_accepted_suggestion(nonexistent_id, "test") is None
        assert self.service.set_mode(nonexistent_id, SessionMode.ADVISORY) is None
    
    def test_timestamps_are_timezone_aware(self):
        """Test that timestamps are timezone-aware UTC."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        
        assert session.created_at.tzinfo is not None
        assert isinstance(session.created_at.timestamp(), float)
        assert session.updated_at.tzinfo is not None
    
    def test_mutation_methods_update_updated_at(self):
        """Test that mutation methods update the updated_at timestamp."""
        project_id = uuid4()
        film_id = uuid4()
        
        session = self.service.create_session(project_id, film_id)
        original_updated = session.updated_at
        
        # Allow microsecond difference
        import time
        time.sleep(0.001)
        
        self.service.set_active_scene(session.session_id, uuid4())
        session = self.service.get_session(session.session_id)
        assert session is not None
        assert session.updated_at >= original_updated
        
        self.service.increment_revision(session.session_id)
        session = self.service.get_session(session.session_id)
        assert session is not None
        assert session.updated_at >= original_updated
        
        self.service.record_accepted_suggestion(session.session_id, "test")
        session = self.service.get_session(session.session_id)
        assert session is not None
        assert session.updated_at >= original_updated
        
        self.service.set_mode(session.session_id, SessionMode.COLLABORATIVE)
        session = self.service.get_session(session.session_id)
        assert session is not None
        assert session.updated_at >= original_updated
