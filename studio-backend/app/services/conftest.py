"""
Pytest configuration for app/services tests.

This file provides fixtures and configuration specific to the services tests.
"""

import pytest


@pytest.fixture(scope="function", autouse=True)
def reset_continuity_intelligence_state():
    """
    Reset continuity intelligence service state before each test.
    
    This prevents state leakage from other tests that might populate
    memory graphs or environment context that affects render batch tests.
    """
    from app.services import continuity_intelligence_service
    
    # Clear any cached graphs or state
    if hasattr(continuity_intelligence_service.continuity_intelligence_service, '_graph_cache'):
        continuity_intelligence_service.continuity_intelligence_service._graph_cache.clear()
    
    yield
    
    # Cleanup after test
    if hasattr(continuity_intelligence_service.continuity_intelligence_service, '_graph_cache'):
        continuity_intelligence_service.continuity_intelligence_service._graph_cache.clear()
