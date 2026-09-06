"""
Pytest configuration and fixtures for proper async test isolation.

This file ensures:
- Fresh event loops per test
- Fresh service instances per test
- Proper cleanup after each test
"""

import asyncio
import os
import tempfile
from pathlib import Path

# Set paths BEFORE application imports construct storage singletons. The autouse
# grounding fixture deletes a fixed project ID, so inheriting developer paths
# here can destroy real project state. Each pytest process gets its own stores.
_test_storage = tempfile.TemporaryDirectory(prefix="studio-pytest-")
os.environ["STUDIO_STORAGE_PATH"] = _test_storage.name
os.environ["STUDIO_PROJECT_STORE_PATH"] = str(Path(_test_storage.name) / "project_state_store.json")

os.environ["STUDIO_ACCESS_MODE"] = "local"

import pytest
from typing import Generator

from app.config import settings
from app.services.render import RenderService
from app.services.project_store import project_store
from app.data.storage import get_storage
from app.models import StudioProject


@pytest.fixture(scope="function", autouse=True)
def test_render_provider_default_isolation(monkeypatch) -> Generator[None, None, None]:
    """
    Keep local .env render-provider choices from changing test baselines.
    Individual tests can still override RENDER_VIDEO_PROVIDER with monkeypatch.
    """
    original_provider = settings.render_video_provider
    monkeypatch.delenv("RENDER_VIDEO_PROVIDER", raising=False)
    settings.render_video_provider = "happyhorse"
    try:
        yield
    finally:
        settings.render_video_provider = original_provider


@pytest.fixture(scope="function", autouse=True)
def real_project_fixture() -> Generator[None, None, None]:
    """
    Create a real project fixture for Co-Director grounding tests.
    This project contains the screenplay scenes that tests expect to find.

    Function scope ensures deterministic behavior for every test.
    Explicit cleanup before seeding prevents stale state leakage.
    """
    project_id = "project_3dba9330f43a"

    # Explicitly remove any existing fixture records before seeding
    # to prevent stale state from previous test runs
    try:
        project_store.delete_project(project_id)
    except Exception:
        pass  # Project may not exist, which is fine
    try:
        storage = get_storage()
        storage.delete_project(project_id)
    except Exception:
        pass  # Storage may not have the project, which is fine

    # Create the project with expected scene data
    project = {
        "project_id": project_id,
        "title": "I Was Reborn",
        "logline": "Maya survives the end of the world in Chicago.",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "heading": "DOWNTOWN CHICAGO",
                    "text": "DOWNTOWN CHICAGO - DAY\n\nPeople think the end of the world is fire. Maya walks through the golden hour, families passing her. Lake Michigan glimmers in the distance. She remembers MOM's voice.\n\nMAYA (V.O.)\nThey're wrong about the fire. It's the forgetting that kills you.",
                    "characters": ["Maya", "MOM"],
                    "emotional_tone": "exhausted grief",
                },
                {
                    "scene_id": "scene_002",
                    "heading": "CHICAGO RIVER",
                    "text": "CHICAGO RIVER - DAY\n\nThe same city. Different world. The L train is frozen. Buildings are cracked.\nMaya walks through the ruins. She reaches the Chicago River.\nDRE\nI need you to understand something.\nMAYA\nThat's funny.\nDRE\nWhat?\nMAYA\nYou always say that right before you do something you know is wrong.\nDRE\nThings changed.\nMAYA\nNo. People changed.\nDRE\n(raises the gun)\nThere's not enough. You have to understand that. There is not enough for everyone.\nMAYA\nSo you decided that for all of us.\nDRE\nSomeone had to.\nMAYA\nI remember dying. So why am I here?",
                    "characters": ["Maya", "Dre"],
                    "emotional_tone": "haunting",
                },
                {
                    "scene_id": "scene_003",
                    "heading": "DRE'S APARTMENT",
                    "text": "DRE'S APARTMENT - NIGHT\n\nDre cooks in warm kitchen practicals. Maya watches from the dark doorway before he notices her. The apartment has lived-in warmth.\n\nMedium two-shot as Dre continues cooking.",
                    "characters": ["Maya", "Dre"],
                    "emotional_tone": "intimate",
                },
                {
                    "scene_id": "scene_004",
                    "heading": "ROOFTOP",
                    "text": "ROOFTOP - NIGHT\n\nMaya stands at the edge. The city below is dark, the world ended. She holds a choice in her hands.\n\nMAYA\nSurvival isn't living. It's just not dying yet. The world ended but I'm still here.",
                    "characters": ["Maya"],
                    "emotional_tone": "dark resolve",
                },
            ]
        },
        "memory_context": {
            "director_memory": {
                "notes": [
                    {
                        "entry_id": "dm_notes_001",
                        "kind": "notes",
                        "note": "No more than one meaningful disagreement per surface.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_002",
                        "kind": "notes",
                        "note": "Studio pattern: emotional residue over structural clarity.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_003",
                        "kind": "notes",
                        "note": "Push scenes one degree darker in emotional implication.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_004",
                        "kind": "notes",
                        "note": "Hold stillness longer before payoff.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_005",
                        "kind": "notes",
                        "note": "Let ordinary beauty become emotional cost.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_006",
                        "kind": "notes",
                        "note": "Protect one beat of silence before major turns.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_007",
                        "kind": "notes",
                        "note": "Use visual callbacks to echo earlier emotional context.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_008",
                        "kind": "notes",
                        "note": "Explain why a shot matters to story impact.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_009",
                        "kind": "notes",
                        "note": "Visual Language: use consistent framing and lighting motifs.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "entry_id": "dm_notes_010",
                        "kind": "notes",
                        "note": "Punctuation pass: ensure prompt clarity without over-editing.",
                        "saved_at": "2024-01-01T00:00:00Z",
                    },
                ]
            }
        },
    }

    # Save to project_store (required for all consuming tests)
    project_store.save_project(project)

    # Save to database storage (required for tests that query it)
    # Fail clearly if database storage is unavailable
    storage = get_storage()
    storage.save_project(StudioProject(**project))

    # Verify dual storage consistency
    stored_project = project_store.get_project(project_id)
    assert stored_project is not None, "Project not found in project_store after save"
    db_project = storage.get_project(project_id)
    assert db_project is not None, "Project not found in database after save"
    assert stored_project["project_id"] == db_project.project_id, "Dual storage project_id mismatch"

    yield

    # Cleanup: delete the test project after each test
    project_store.delete_project(project_id)
    storage.delete_project(project_id)


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
