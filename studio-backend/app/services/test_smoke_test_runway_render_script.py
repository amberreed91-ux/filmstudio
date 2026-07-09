from __future__ import annotations

import types

import scripts.smoke_test_runway_render as smoke


def test_parse_args_supports_task_id(monkeypatch):
    monkeypatch.setattr("sys.argv", ["smoke", "--task-id", "abc-123"])
    args = smoke.parse_args()
    assert args.task_id == "abc-123"


def test_task_id_mode_does_not_create_new_job(monkeypatch):
    monkeypatch.setattr(smoke, "load_env", lambda _p: None)
    monkeypatch.setattr(smoke, "resolve_runway_key", lambda: ("RUNWAY_API_KEY", "key_test_1234"))
    monkeypatch.setenv("RUNWAY_TIMEOUT_SECONDS", "900")

    called = {"poll": 0, "run_new": 0}

    def _poll(task_id: str, timeout_seconds: int, runway_key: str) -> int:
        called["poll"] += 1
        assert task_id == "task-1"
        assert timeout_seconds >= 900
        assert runway_key == "key_test_1234"
        return 0

    def _run_new(timeout_seconds: int, runway_key: str) -> int:
        called["run_new"] += 1
        return 1

    monkeypatch.setattr(smoke, "poll_existing_task", _poll)
    monkeypatch.setattr(smoke, "run_new_job", _run_new)
    monkeypatch.setattr(smoke, "parse_args", lambda: types.SimpleNamespace(task_id="task-1"))

    rc = smoke.main()
    assert rc == 0
    assert called["poll"] == 1
    assert called["run_new"] == 0
