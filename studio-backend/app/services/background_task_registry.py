import asyncio
import inspect
import logging
from typing import Dict

logger = logging.getLogger("studio-task-registry")


class BackgroundTaskRegistry:
    """Track all background asyncio tasks for graceful shutdown."""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._shutting_down = False

    def register(self, name: str, coro) -> asyncio.Task:
        if self._shutting_down:
            logger.warning("Task registry: rejecting '%s' during shutdown", name)
            if inspect.iscoroutine(coro):
                coro.close()
            raise RuntimeError("Cannot register tasks during shutdown")

        task = asyncio.create_task(coro, name=f"studio-bg-{name}")
        self._tasks[name] = task
        task.add_done_callback(lambda t, n=name: self._on_task_done(n, t))
        logger.info("Task registry: registered '%s'", name)
        return task

    def _on_task_done(self, name: str, task: asyncio.Task):
        self._tasks.pop(name, None)
        if task.cancelled():
            return
        error = task.exception()
        if error and not self._shutting_down:
            logger.error("Task registry: '%s' failed with %s", name, error)

    def status(self) -> Dict[str, str]:
        return {
            name: "running"
            if not task.done()
            else ("cancelled" if task.cancelled() else "failed" if task.exception() else "completed")
            for name, task in self._tasks.items()
        }

    async def cancel_all(self, timeout: float = 10.0):
        self._shutting_down = True
        if not self._tasks:
            logger.info("Task registry: no active tasks to cancel")
            return

        logger.info("Task registry: cancelling %d tasks", len(self._tasks))
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()

        results = await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        for (name, _task), result in zip(self._tasks.items(), results):
            if isinstance(result, asyncio.CancelledError):
                logger.info("Task registry: '%s' cancelled successfully", name)
            elif isinstance(result, Exception):
                logger.warning("Task registry: '%s' raised during shutdown: %s", name, result)

        self._tasks.clear()
