from __future__ import annotations

import asyncio

import pytest

from app.services.background_task_registry import BackgroundTaskRegistry


@pytest.fixture
def registry():
    return BackgroundTaskRegistry()


class TestBackgroundTaskRegistry:
    async def test_register_adds_task(self, registry: BackgroundTaskRegistry):
        async def dummy():
            await asyncio.sleep(10)

        task = registry.register("test-task", dummy())
        assert "test-task" in registry.status()
        task.cancel()
        await asyncio.sleep(0)

    async def test_status_reports_running(self, registry: BackgroundTaskRegistry):
        async def dummy():
            await asyncio.sleep(10)

        task = registry.register("running-task", dummy())
        status = registry.status()
        assert status["running-task"] == "running"
        task.cancel()
        await asyncio.sleep(0)

    async def test_completed_task_removed_from_status(self, registry: BackgroundTaskRegistry):
        async def done():
            return 42

        registry.register("done-task", done())
        await asyncio.sleep(0.1)
        status = registry.status()
        assert "done-task" not in status

    async def test_failed_task_removed_from_status(self, registry: BackgroundTaskRegistry):
        async def fail():
            raise ValueError("boom")

        registry.register("fail-task", fail())
        await asyncio.sleep(0.1)
        status = registry.status()
        assert "fail-task" not in status

    async def test_cancel_all_cancels_tasks(self, registry: BackgroundTaskRegistry):
        async def long_running():
            await asyncio.sleep(100)

        registry.register("long", long_running())
        await asyncio.sleep(0.05)
        await registry.cancel_all(timeout=2.0)
        assert registry.status() == {}

    async def test_cancel_all_empty_registry(self, registry: BackgroundTaskRegistry):
        await registry.cancel_all(timeout=1.0)
        assert registry.status() == {}

    async def test_register_rejects_during_shutdown(self, registry: BackgroundTaskRegistry):
        await registry.cancel_all(timeout=1.0)
        with pytest.raises(RuntimeError, match="shutdown"):
            registry.register("post-shutdown", asyncio.sleep(0))
