from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


logger = logging.getLogger("studio-stability")


@dataclass
class StabilityError(Exception):
    error_type: str
    message: str
    stage: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "stage": self.stage,
            "metadata": self.metadata,
        }


class ValidationError(StabilityError):
    def __init__(self, message: str, stage: str = "", metadata: Optional[Dict[str, Any]] = None):
        super().__init__("validation_error", message, stage, metadata or {})


class ProviderError(StabilityError):
    def __init__(self, message: str, stage: str = "", metadata: Optional[Dict[str, Any]] = None):
        super().__init__("provider_error", message, stage, metadata or {})


class StateError(StabilityError):
    def __init__(self, message: str, stage: str = "", metadata: Optional[Dict[str, Any]] = None):
        super().__init__("state_error", message, stage, metadata or {})


class PersistenceError(StabilityError):
    def __init__(self, message: str, stage: str = "", metadata: Optional[Dict[str, Any]] = None):
        super().__init__("persistence_error", message, stage, metadata or {})


class PlaybackError(StabilityError):
    def __init__(self, message: str, stage: str = "", metadata: Optional[Dict[str, Any]] = None):
        super().__init__("playback_error", message, stage, metadata or {})


def log_stage_event(
    *,
    project_id: Optional[str],
    job_id: Optional[str],
    provider: Optional[str],
    stage: str,
    duration_ms: int,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "project_id": project_id or "",
        "job_id": job_id or "",
        "provider": provider or "",
        "stage": stage,
        "duration_ms": int(duration_ms),
    }
    if isinstance(extra, dict) and extra:
        payload.update(extra)
    logger.info("stability_event=%s", payload)


def start_timer() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
