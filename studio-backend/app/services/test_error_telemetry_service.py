from app.services.error_telemetry_service import ErrorTelemetryService


class _Storage:
    def __init__(self):
        self.reports = []

    def save_error_report(self, report):
        self.reports.append(report)


def test_persist_reports_uses_storage_boundary():
    storage = _Storage()
    service = ErrorTelemetryService(storage=storage)
    reports = [{"error_id": "error-1", "timestamp": 1.0, "message": "Failed"}]

    assert service.persist_reports(reports) == 1
    assert storage.reports == reports


def test_persist_reports_accepts_batch_when_storage_write_fails():
    class FailingStorage:
        def save_error_report(self, report):
            raise RuntimeError("offline")

    service = ErrorTelemetryService(storage=FailingStorage())

    assert service.persist_reports([{"error_id": "error-1"}]) == 1
