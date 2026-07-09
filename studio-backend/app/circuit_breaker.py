import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("studio-circuit-breaker")


@dataclass
class CircuitState:
    """Circuit breaker state"""
    failures: int = 0
    last_failure: Optional[float] = None
    state: str = "closed"  # closed, open, half-open
    next_attempt: float = 0


class CircuitBreaker:
    """Circuit breaker for provider calls"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._states: Dict[str, CircuitState] = {}
        self._half_open_calls: Dict[str, int] = {}
    
    def _get_state(self, provider: str) -> CircuitState:
        if provider not in self._states:
            self._states[provider] = CircuitState()
        return self._states[provider]
    
    def can_execute(self, provider: str) -> bool:
        """Check if call can be executed"""
        state = self._get_state(provider)
        now = time.time()
        
        if state.state == "closed":
            return True
        
        if state.state == "open":
            if now >= state.next_attempt:
                # Transition to half-open
                state.state = "half-open"
                self._half_open_calls[provider] = 0
                logger.info(f"Circuit breaker for {provider} transitioning to half-open")
                return True
            return False
        
        # Half-open: allow limited calls
        if state.state == "half-open":
            calls = self._half_open_calls.get(provider, 0)
            return calls < self.half_open_max_calls
        
        return False
    
    def record_success(self, provider: str):
        """Record successful call"""
        state = self._get_state(provider)
        state.failures = 0
        state.state = "closed"
        self._half_open_calls[provider] = 0
        logger.debug(f"Circuit breaker for {provider} reset to closed")
    
    def record_failure(self, provider: str):
        """Record failed call"""
        state = self._get_state(provider)
        state.failures += 1
        state.last_failure = time.time()
        
        if state.state == "half-open":
            # Failed in half-open, go back to open
            state.state = "open"
            state.next_attempt = time.time() + self.recovery_timeout
            logger.warning(f"Circuit breaker for {provider} opened after half-open failure")
        
        elif state.failures >= self.failure_threshold:
            # Failed threshold reached, open circuit
            state.state = "open"
            state.next_attempt = time.time() + self.recovery_timeout
            logger.warning(f"Circuit breaker for {provider} opened after {state.failures} failures")
    
    def get_status(self, provider: str) -> dict:
        """Get circuit breaker status"""
        state = self._get_state(provider)
        return {
            "provider": provider,
            "state": state.state,
            "failures": state.failures,
            "last_failure": state.last_failure,
            "next_attempt": state.next_attempt if state.state == "open" else None
        }


# Global circuit breaker instance
circuit_breaker = CircuitBreaker()


async def with_circuit_breaker(provider: str, func, *args, **kwargs):
    """Execute function with circuit breaker protection"""
    if not circuit_breaker.can_execute(provider):
        raise Exception(f"Circuit breaker open for provider {provider}")
    
    try:
        result = await func(*args, **kwargs)
        circuit_breaker.record_success(provider)
        return result
    except Exception as e:
        circuit_breaker.record_failure(provider)
        raise


class GracefulShutdown:
    """Graceful shutdown handler for background tasks"""
    
    def __init__(self):
        self._shutdown_event = asyncio.Event()
        self._active_tasks: Dict[str, asyncio.Task] = {}
    
    def request_shutdown(self):
        """Request graceful shutdown"""
        logger.info("Graceful shutdown requested")
        self._shutdown_event.set()
    
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()
    
    def register_task(self, name: str, task: asyncio.Task):
        """Register active task for tracking"""
        self._active_tasks[name] = task
    
    def unregister_task(self, name: str):
        """Unregister task"""
        if name in self._active_tasks:
            del self._active_tasks[name]
    
    async def wait_for_tasks(self, timeout: float = 30.0):
        """Wait for all registered tasks to complete"""
        if not self._active_tasks:
            return
        
        logger.info(f"Waiting for {len(self._active_tasks)} tasks to complete...")
        
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._active_tasks.values(), return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Shutdown timeout - {len(self._active_tasks)} tasks still running")
            # Cancel remaining tasks
            for name, task in self._active_tasks.items():
                if not task.done():
                    task.cancel()
                    logger.warning(f"Cancelled task: {name}")
        
        logger.info("All tasks completed or cancelled")


# Global shutdown handler
shutdown_handler = GracefulShutdown()