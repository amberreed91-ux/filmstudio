"""
Co-Director Session Service - Phase 10.1

Manages Co-Director session lifecycle.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from app.models.co_director import (
    CoDirectorSession,
    SessionMode,
)


class CoDirectorSessionService:
    """
    Service for managing Co-Director sessions.
    
    In-memory only, no persistence.
    """
    
    def __init__(self) -> None:
        self._sessions: dict[UUID, CoDirectorSession] = {}
    
    def create_session(
        self,
        project_id: UUID,
        film_id: UUID,
        mode: SessionMode = SessionMode.PASSIVE,
    ) -> CoDirectorSession:
        """
        Create a new Co-Director session.
        
        Args:
            project_id: Project identifier
            film_id: Film identifier
            mode: Initial session mode (default: PASSIVE)
        
        Returns:
            New CoDirectorSession with auto-generated session_id
        """
        session = CoDirectorSession(
            session_id=uuid4(),
            project_id=project_id,
            film_id=film_id,
            current_mode=mode,
        )
        self._sessions[session.session_id] = session
        return session
    
    def get_session(self, session_id: UUID) -> Optional[CoDirectorSession]:
        """
        Retrieve an existing session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            CoDirectorSession if found, None otherwise
        """
        return self._sessions.get(session_id)
    
    def set_active_scene(self, session_id: UUID, scene_id: UUID) -> Optional[CoDirectorSession]:
        """
        Set the active scene for a session.
        
        Args:
            session_id: Session identifier
            scene_id: Scene identifier
        
        Returns:
            Updated session or None if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.set_active_scene(scene_id)
        return session
    
    def increment_revision(self, session_id: UUID) -> Optional[CoDirectorSession]:
        """
        Increment the revision counter for a session.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Updated session or None if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.increment_revision()
        return session
    
    def record_accepted_suggestion(self, session_id: UUID, suggestion_type: str) -> Optional[CoDirectorSession]:
        """
        Record an accepted suggestion for a session.
        
        Args:
            session_id: Session identifier
            suggestion_type: Type of suggestion accepted
        
        Returns:
            Updated session or None if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.record_accepted_suggestion(suggestion_type)
        return session
    
    def set_mode(self, session_id: UUID, mode: SessionMode) -> Optional[CoDirectorSession]:
        """
        Set the session mode.
        
        Args:
            session_id: Session identifier
            mode: New mode
        
        Returns:
            Updated session or None if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session.set_mode(mode)
        return session


# Singleton instance
co_director_session_service = CoDirectorSessionService()
