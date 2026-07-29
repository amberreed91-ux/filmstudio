from __future__ import annotations

import logging
from typing import Any, Iterable

from app.data.storage import StorageInterface, get_storage

logger = logging.getLogger("studio-error-telemetry")


class ErrorTelemetryService:
    def __init__(self, storage: StorageInterface | None = None):
        self._storage = storage

    def persist_reports(self, reports: Iterable[dict[str, Any]]) -> int:
        accepted = 0
        storage = self._storage or get_storage("sqlite")
        for report in reports:
            accepted += 1
            if storage is None:
                continue
            try:
                storage.save_error_report(report)
            except Exception as exc:
                logger.warning(
                    "Failed to persist error report %s: %s",
                    report.get("error_id", "unknown"),
                    exc,
                )
        return accepted


error_telemetry_service = ErrorTelemetryService()
