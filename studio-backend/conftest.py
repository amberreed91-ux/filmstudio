"""
Pytest configuration and fixtures for proper async test isolation.

This file ensures:
- Fresh event loops per test
- Fresh service instances per test
- Proper cleanup after each test
"""

import asyncio
import pytest
from typing import Generator

from app.services.render import RenderService


@pytest.fixture(scope="function")
def render_service() -> Generator[RenderService, None, None]:
    """
    Create a fresh RenderService instance for each test.
    
    This ensures no state leaks between tests.
    """
    service = RenderService()
    yield service
    # Clean up any jobs or state after the test
    try:
        service._jobs.clear()
        service._batches.clear()
        service._submit_locks.clear()
    except Exception:
        pass


def run_async(coro):
    """
    Helper to run async code in tests with proper event loop handling.
    
    Uses a fresh event loop each time to prevent state leakage.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            # Clean up pending tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        finally:
            loop.close()
