"""Characterization: duplicate create_job against durable storage on a fresh service.

Pins the G-7 fix: when a fresh ``RenderService`` shares durable storage
containing a matching pending job but has an empty in-memory ``_jobs``
cache, the duplicate ``create_job`` reuses the persisted job (same id) via
``_find_idempotent_job`` AND hydrates it into the fresh service's ``_jobs``,
so the follow-up ``submit_job`` resolves the job (it may still fail closed
on domain gates, but never with "not found").

Synthetic data with an isolated tmp SQLite database.
"""

from __future__ import annotations

import asyncio

import pytest

from app.data.storage import DatabaseStorage


PROMPT = (
    "Maya pauses in a quiet hallway, medium shot, practical light, "
    "dust in the air, long enough to read as a deliberate beat."
)


@pytest.fixture()
def isolated_storage(tmp_path, monkeypatch):
    from app.services import render as render_module

    storage = DatabaseStorage(str(tmp_path / "storage-char"))
    previous = render_module._storage
    render_module.set_storage(storage)
    try:
        yield storage
    finally:
        render_module.set_storage(previous)


def test_duplicate_create_on_fresh_service_then_submit_characterization(isolated_storage):
    from app.services.render import RenderService

    kwargs = {
        "project_id": "proj-idempotent-char",
        "shot_id": "scene_001_shot_001",
        "provider": "simulated",
        "prompt": PROMPT,
        "parameters": {},
    }

    first_service = RenderService()
    first_job = first_service.create_job(**kwargs)
    assert first_job.status == "pending"
    assert isolated_storage.get_job(first_job.id) is not None

    # Fresh service: same durable storage, empty in-memory cache (no hydrate).
    second_service = RenderService()
    assert second_service._jobs == {}

    duplicate_job = second_service.create_job(**kwargs)

    # G-7 fixed behavior: reused AND hydrated into the fresh instance.
    assert duplicate_job.id == first_job.id  # persisted job is reused ...
    assert duplicate_job.id in second_service._jobs  # ... and cached ...

    try:
        asyncio.run(second_service.submit_job(duplicate_job.id))
    except Exception as exc:  # noqa: BLE001 - any fail-closed gate is fine
        assert "not found" not in str(exc)  # ... so submit resolves the job.
