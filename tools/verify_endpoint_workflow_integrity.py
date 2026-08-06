#!/usr/bin/env python3
"""Independent HTTP reproduction for the canonical Studio production workflow.

The verifier creates an isolated backend and clean project through public APIs.
Paid provider calls are never enabled. Evidence is written as JSON/text artifacts,
and any required failure produces a non-zero process exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "studio-backend"
FRONTEND_ROOT = ROOT / "studio-app"
DEFAULT_EVIDENCE = ROOT / "reports/evidence/endpoint_workflow_integrity/checkpoint_7/after_fixes/reproduction_success"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


class VerificationFailure(RuntimeError):
    pass


@dataclass
class Recorder:
    evidence_dir: Path
    started_at: str = field(default_factory=utc_now)
    lines: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)
    pass_count: int = 0
    failure_count: int = 0
    skip_count: int = 0

    def emit(self, message: str) -> None:
        line = f"[{utc_now()}] {message}"
        self.lines.append(line)
        print(line, flush=True)

    def passed(self, name: str, details: dict[str, Any] | None = None) -> None:
        self.pass_count += 1
        row = {"name": name, "status": "passed", "timestamp": utc_now(), "details": details or {}}
        self.steps.append(row)
        self.emit(f"PASS {name}")

    def failed(self, name: str, message: str) -> None:
        self.failure_count += 1
        self.steps.append({"name": name, "status": "failed", "timestamp": utc_now(), "message": message})
        self.emit(f"FAIL {name}: {message}")

    def finalize(self, *, exit_code: int, command: list[str], environment: dict[str, Any]) -> None:
        finished_at = utc_now()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "reproduction_stdout.txt").write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        (self.evidence_dir / "reproduction_stderr.txt").write_text("", encoding="utf-8")
        write_json(self.evidence_dir / "runtime_http/requests.json", self.requests)
        write_json(self.evidence_dir / "test_logs/reproduction_steps.json", self.steps)
        write_json(
            self.evidence_dir / "test_logs/reproduction_command_record.json",
            {
                "working_directory": str(ROOT),
                "command": command,
                "exit_code": exit_code,
                "started_at": self.started_at,
                "finished_at": finished_at,
                "environment": environment,
                "pass_total": self.pass_count,
                "failure_total": self.failure_count,
                "skip_total": self.skip_count,
                "stdout": "reproduction_stdout.txt",
                "stderr": "reproduction_stderr.txt",
            },
        )


class ApiClient:
    def __init__(self, base_url: str, recorder: Recorder) -> None:
        self.base_url = base_url.rstrip("/")
        self.recorder = recorder

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
        step: str,
        timeout: float = 120.0,
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        started = time.monotonic()
        status = 0
        response_text = ""
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(response.status)
                response_text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            response_text = exc.read().decode("utf-8", errors="replace")
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000, 2)
            self.recorder.requests.append(
                {
                    "timestamp": utc_now(),
                    "step": step,
                    "method": method,
                    "url": url,
                    "request_payload": payload,
                    "status": status,
                    "duration_ms": elapsed_ms,
                    "transport_error": f"{type(exc).__name__}: {exc}",
                }
            )
            raise VerificationFailure(f"{step}: transport failure: {type(exc).__name__}: {exc}") from exc

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        parsed: Any = None
        if response_text:
            try:
                parsed = json.loads(response_text)
            except json.JSONDecodeError:
                parsed = response_text
        self.recorder.requests.append(
            {
                "timestamp": utc_now(),
                "step": step,
                "method": method,
                "url": url,
                "request_payload": payload,
                "status": status,
                "duration_ms": elapsed_ms,
                "response_payload": parsed,
            }
        )
        if status not in expected:
            raise VerificationFailure(f"{step}: expected HTTP {expected}, received {status}: {response_text[:800]}")
        self.recorder.passed(step, {"method": method, "path": path, "status": status, "duration_ms": elapsed_ms})
        return status, parsed


@dataclass
class ManagedBackend:
    python: Path
    port: int
    storage_dir: Path
    project_store_path: Path
    log_path: Path
    process: subprocess.Popen[str] | None = None
    _log_handle: Any = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("a", encoding="utf-8")
        self._log_handle.write(f"\n=== backend start {utc_now()} ===\n")
        self._log_handle.flush()
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "local",
                "RENDER_PROVIDER_TEST_MODE": "mock_success",
                "RENDER_VIDEO_PROVIDER": "simulated",
                "STUDIO_STORAGE_PATH": str(self.storage_dir),
                "STUDIO_PROJECT_STORE_PATH": str(self.project_store_path),
                "PRODUCTION_QUEUE_WORKER_ENABLED": "true",
                "PRODUCTION_QUEUE_WORKER_POLL_INTERVAL_SECONDS": "0.1",
                "BACKUP_ENABLED": "false",
                "PYTHONUNBUFFERED": "1",
            }
        )
        self.process = subprocess.Popen(
            [str(self.python), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=BACKEND_ROOT,
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.process = None
        if self._log_handle is not None:
            self._log_handle.flush()
            self._log_handle.close()
            self._log_handle = None


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_backend(backend: ManagedBackend, recorder: Recorder, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if backend.process is not None and backend.process.poll() is not None:
            raise VerificationFailure(f"backend exited during startup with code {backend.process.returncode}")
        try:
            with urllib.request.urlopen(f"{backend.base_url}/health", timeout=2) as response:
                if response.status == 200:
                    recorder.passed("managed backend became healthy", {"base_url": backend.base_url})
                    return
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    raise VerificationFailure(f"backend did not become healthy within {timeout}s: {last_error}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def run_external_command(
    recorder: Recorder,
    *,
    name: str,
    command: list[str],
    cwd: Path,
    timeout: int,
) -> None:
    started_at = utc_now()
    started = time.monotonic()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    safe_name = name.replace(" ", "_")
    log_dir = recorder.evidence_dir / "test_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{safe_name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (log_dir / f"{safe_name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
    combined_output = f"{result.stdout}\n{result.stderr}"
    passed_matches = [int(value) for value in re.findall(r"(\d+)\s+passed", combined_output)]
    failed_matches = [int(value) for value in re.findall(r"(\d+)\s+failed", combined_output)]
    skipped_matches = [int(value) for value in re.findall(r"(\d+)\s+skipped", combined_output)]
    pass_total = max(passed_matches, default=1 if result.returncode == 0 else 0)
    failure_total = max(failed_matches, default=0 if result.returncode == 0 else 1)
    skip_total = max(skipped_matches, default=0)
    write_json(
        log_dir / f"{safe_name}.command.json",
        {
            "working_directory": str(cwd),
            "command": command,
            "exit_code": result.returncode,
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_ms": duration_ms,
            "environment": {"paid_provider_calls": False},
            "pass_total": pass_total,
            "failure_total": failure_total,
            "skip_total": skip_total,
            "stdout": f"{safe_name}.stdout.txt",
            "stderr": f"{safe_name}.stderr.txt",
        },
    )
    if result.returncode != 0:
        raise VerificationFailure(f"{name} exited {result.returncode}")
    recorder.passed(name, {"exit_code": result.returncode, "duration_ms": duration_ms})


def extract_run(response: Any, step: str) -> dict[str, Any]:
    require(isinstance(response, dict), f"{step}: response is not an object")
    run = response.get("run")
    require(isinstance(run, dict), f"{step}: response has no run object")
    return run


def export_database(storage_dir: Path, run_id: str, evidence_dir: Path) -> dict[str, Any]:
    database = storage_dir / "studio.db"
    require(database.exists(), f"SQLite database was not created at {database}")
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        tables = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        counts: dict[str, int] = {}
        for table in tables:
            quoted = table.replace('"', '""')
            counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
        run_row = connection.execute(
            "SELECT run_id, project_id, script_id, scene_id, blueprint_id, blueprint_version_id, status, context_hash, created_at, updated_at FROM canonical_workflow_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        transitions = [
            dict(row)
            for row in connection.execute(
                "SELECT transition_id, run_id, idempotency_key, from_status, to_status, event_type, created_at FROM canonical_workflow_transitions WHERE run_id = ? ORDER BY created_at, transition_id",
                (run_id,),
            ).fetchall()
        ]
    export = {
        "database_path": str(database),
        "table_counts": counts,
        "canonical_run": dict(run_row) if run_row else None,
        "canonical_transitions": transitions,
    }
    write_json(evidence_dir / "database/persistence_export.json", export)
    return export


def exercise_workflow(client: ApiClient, recorder: Recorder, project_id: str) -> dict[str, Any]:
    suffix = project_id.rsplit("-", 1)[-1]
    script_id = f"script-{suffix}"
    scene_id = "scene_001"
    sequence_id = "sequence_001"
    beat_ids = ["beat_001", "beat_002"]

    client.request("GET", "/health", step="backend health")
    _, openapi = client.request("GET", "/openapi.json", step="runtime OpenAPI")
    require(isinstance(openapi, dict), "OpenAPI response is not JSON")
    write_json(recorder.evidence_dir / "openapi/runtime_openapi.json", openapi)
    required_paths = [
        "/api/f51/studio/projects/{project_id}",
        "/api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint",
        "/api/f51/studio/projects/{project_id}/scenes/{scene_id}/production-thread",
        "/api/f51/studio/production-threads/{run_id}",
    ]
    paths = openapi.get("paths", {}) if isinstance(openapi, dict) else {}
    for path in required_paths:
        require(path in paths, f"required runtime route missing from OpenAPI: {path}")
    route_inventory = {
        "required_paths": required_paths,
        "required_paths_present": True,
        "canonical_paths": sorted(path for path in paths if "production-thread" in path),
        "path_count": len(paths),
    }
    write_json(recorder.evidence_dir / "runtime_http/route_inventory.json", route_inventory)
    recorder.passed("required runtime routes are mounted", {"required_path_count": len(required_paths)})

    client.request(
        "POST",
        "/api/f51/studio/projects",
        payload={"title": "Checkpoint 7 Independent Verification", "project_id": project_id},
        step="create clean project through API",
    )
    project_payload = {
        "script_text": "INT. EDIT BAY - NIGHT\nMAYA holds one breath, then commits to the harder cut.",
        "execution_summary": {
            "script_id": script_id,
            "scenes": [
                {
                    "scene_id": scene_id,
                    "script_id": script_id,
                    "sequence_id": sequence_id,
                    "beats": [
                        {"beat_id": beat_ids[0], "objective": "Maya delays the answer."},
                        {"beat_id": beat_ids[1], "objective": "She commits to clarity."},
                    ],
                    "heading": "INT. EDIT BAY - NIGHT",
                    "description": "Maya holds one breath, then commits to the harder cut.",
                    "objective": "Make the irreversible choice.",
                    "emotional_objective": "Let dread settle before resolve arrives.",
                    "emotional_tone": "contained dread",
                    "character_intention": {"MAYA": "Protect truth without surrendering tenderness."},
                    "character_emotional_state": {"MAYA": "Afraid, precise, newly resolved."},
                    "theme": "Clarity has an emotional cost.",
                    "characters": ["MAYA"],
                }
            ],
        },
        "film_cut": {
            "cut_id": "default",
            "scene_order": [scene_id],
            "included_scenes": [scene_id],
            "excluded_scenes": [],
        },
    }
    client.request(
        "PUT",
        f"/api/f51/studio/projects/{project_id}",
        payload=project_payload,
        step="persist canonical script and scene through API",
    )
    _, scenes_response = client.request(
        "GET",
        f"/api/f51/studio/projects/{project_id}/scenes",
        step="load clean project scenes",
    )
    require(scenes_response["scenes"][0]["scene_id"] == scene_id, "created scene did not reload")

    _, blueprint = client.request(
        "POST",
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint",
        payload={"shot_count": 1, "regeneration_reason": "checkpoint_7_independent_verification"},
        step="create Storyboard blueprint",
    )
    blueprint_id = blueprint["blueprint"]["blueprint_id"]
    version_id = blueprint["version"]["version_id"]
    require(blueprint["shots"], "Storyboard blueprint has no shots")
    client.request(
        "POST",
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/continuity-review",
        payload={"reviewer": "checkpoint_7_verifier"},
        step="exercise Storyboard continuity review",
    )
    _, approved_blueprint = client.request(
        "POST",
        f"/api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/approve",
        payload={"approved_by": "checkpoint_7_verifier"},
        step="approve Storyboard version",
    )
    require(approved_blueprint["version"]["status"] == "approved", "Storyboard version was not approved")

    client.request(
        "POST",
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/production-thread",
        payload={"script_id": "wrong-script"},
        expected=(409,),
        step="reject invalid workflow ownership",
    )
    _, begun = client.request(
        "POST",
        f"/api/f51/studio/projects/{project_id}/scenes/{scene_id}/production-thread",
        payload={"script_id": script_id, "sequence_id": sequence_id, "beat_ids": beat_ids},
        step="begin canonical production thread",
    )
    run = extract_run(begun, "begin")
    run_id = run["run_id"]
    require(run["blueprint_version_id"] == version_id, "run did not bind to the approved Blueprint version")

    _, previs_response = client.request(
        "POST", f"/api/f51/studio/production-threads/{run_id}/previs/generate", step="generate Previs"
    )
    run = extract_run(previs_response, "generate Previs")
    previs_ids = [row["previs_image_id"] for row in run["data"]["artifacts"]["previs"]]
    require(previs_ids, "Previs generation returned no artifacts")
    first_previs_jobs = [row["job_id"] for row in run["data"]["artifacts"]["previs"]]
    _, duplicate_previs = client.request(
        "POST", f"/api/f51/studio/production-threads/{run_id}/previs/generate", step="repeat Previs generation idempotently"
    )
    require(
        [
            row["job_id"]
            for row in extract_run(duplicate_previs, "duplicate Previs")["data"]["artifacts"]["previs"]
        ] == first_previs_jobs,
        "duplicate Previs generation created a different job",
    )
    recorder.passed("Previs duplicate submission prevented", {"render_job_ids": first_previs_jobs})

    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/previs/approve",
        payload={"confirmed": False, "artifact_ids": previs_ids},
        expected=(422,),
        step="reject unconfirmed Previs approval",
    )
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/previs/approve",
        payload={"confirmed": True, "approved_by": "checkpoint_7_verifier", "artifact_ids": previs_ids},
        step="approve Previs",
    )
    _, package_response = client.request(
        "POST", f"/api/f51/studio/production-threads/{run_id}/production-package", step="create production package"
    )
    run = extract_run(package_response, "package")
    package_id = run["data"]["identifiers"]["production_package_id"]

    _, render_response = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/renders",
        payload={"provider": "simulated", "retry_confirmed": False},
        step="render production package with simulated provider",
    )
    run = extract_run(render_response, "render")
    queued_render_job_ids = [
        row["render_job_id"] for row in run["data"]["artifacts"].get("render_jobs", [])
    ]
    require(queued_render_job_ids, "production render returned no job IDs")
    for attempt in range(32):
        if run["status"] == "render_completed":
            break
        time.sleep(0.25)
        for job_id in queued_render_job_ids:
            client.request(
                "GET",
                f"/api/f51/studio/render/jobs/{job_id}/status",
                step=f"poll provider job {attempt + 1} ({job_id})",
            )
        _, render_response = client.request(
            "POST",
            f"/api/f51/studio/production-threads/{run_id}/renders",
            payload={"provider": "simulated", "retry_confirmed": False},
            step=f"poll canonical render {attempt + 1}",
        )
        run = extract_run(render_response, "render poll")
    require(run["status"] == "render_completed", f"render did not complete: {run['status']}")
    production_job_ids = list(run["data"]["identifiers"]["render_job_ids"])
    _, duplicate_render = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/renders",
        payload={"provider": "simulated", "retry_confirmed": False},
        step="repeat production render idempotently",
    )
    require(
        extract_run(duplicate_render, "duplicate render")["data"]["identifiers"]["render_job_ids"] == production_job_ids,
        "duplicate production render changed job identifiers",
    )
    recorder.passed("production render duplicate submission prevented", {"render_job_ids": production_job_ids})

    _, screening_response = client.request(
        "POST", f"/api/f51/studio/production-threads/{run_id}/screening/sync", step="sync Screening output"
    )
    run = extract_run(screening_response, "screening sync")
    screening_ids = list(run["data"]["identifiers"]["screening_output_ids"])
    require(screening_ids, "Screening sync returned no output IDs")
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/screening/approve",
        payload={"confirmed": False, "artifact_ids": screening_ids},
        expected=(422,),
        step="reject unconfirmed Screening approval",
    )
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/screening/approve",
        payload={"confirmed": True, "approved_by": "checkpoint_7_verifier", "artifact_ids": screening_ids},
        step="approve Screening output",
    )

    _, editorial_response = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/editorial/analyze",
        payload={"revision_emphasis": "emotional_residue"},
        step="exercise Editorial analysis",
    )
    run = extract_run(editorial_response, "editorial")
    analysis = run["data"]["artifacts"]["editorial_analysis"]
    analysis_id = analysis["analysis_id"]
    decision_id = analysis["edit_decisions"][0]["decision_id"]
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/editorial/decide",
        payload={"analysis_id": analysis_id, "decision_id": decision_id, "confirmed": False},
        expected=(422,),
        step="reject unconfirmed Editorial decision",
    )
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/editorial/decide",
        payload={"analysis_id": analysis_id, "decision_id": decision_id, "confirmed": True},
        step="apply Editorial decision",
    )
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/film-cut/update",
        payload={"confirmed": True},
        step="update Film Cut",
    )
    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/film-cut/approve",
        payload={"confirmed": False},
        expected=(422,),
        step="reject unconfirmed Film Cut approval",
    )
    _, cut_response = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/film-cut/approve",
        payload={"confirmed": True, "approved_by": "checkpoint_7_verifier"},
        step="approve Film Cut",
    )
    run = extract_run(cut_response, "film cut")

    original_job_id = run["data"]["identifiers"]["render_job_ids"][0]
    _, revision_response = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/revision",
        payload={
            "original_job_id": original_job_id,
            "revision_prompt": "Hold one additional breath before the cut.",
            "revision_reason": "Protect the emotional residue selected in Editorial.",
            "changed_fields": ["timing", "performance_guidance"],
            "confirmed": True,
        },
        step="create clip revision",
    )
    run = extract_run(revision_response, "revision")
    _, revision_render = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/revision/render",
        payload={"provider": "simulated"},
        step="submit revision render",
    )
    run = extract_run(revision_render, "revision render")
    submitted_revision_job_id = run["data"]["artifacts"]["revision"].get("new_job_id")
    for attempt in range(32):
        if run["status"] == "revision_completed":
            break
        time.sleep(0.25)
        _, revision_render = client.request(
            "POST",
            f"/api/f51/studio/production-threads/{run_id}/revision/render",
            payload={"provider": "simulated"},
            step=f"poll canonical revision render {attempt + 1}",
        )
        run = extract_run(revision_render, "revision render poll")
        require(
            run["data"]["artifacts"]["revision"].get("new_job_id") == submitted_revision_job_id,
            "revision polling created a duplicate job",
        )
    require(run["status"] == "revision_completed", f"revision did not complete: {run['status']}")
    recorder.passed("revision polling reused submitted job", {"revision_job_id": submitted_revision_job_id})

    client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/memory",
        payload={"confirmed": False, "summary": "Should not save"},
        expected=(422,),
        step="reject implicit memory save",
    )
    _, memory_response = client.request(
        "POST",
        f"/api/f51/studio/production-threads/{run_id}/memory",
        payload={
            "confirmed": True,
            "saved_by": "checkpoint_7_verifier",
            "summary": "Protect the held breath before the final cut.",
        },
        step="save approved memory explicitly",
    )
    run = extract_run(memory_response, "memory")
    require(run["data"]["memory_update_status"] == "explicitly_saved", "memory was not marked explicit")

    _, reloaded_response = client.request(
        "GET", f"/api/f51/studio/production-threads/{run_id}", step="reload durable canonical run"
    )
    reloaded = extract_run(reloaded_response, "reload")
    transitions = reloaded_response["transitions"]
    require(reloaded["status"] == "revision_completed", "terminal state did not survive reload")
    required_events = {
        "previs_records_persisted",
        "previs_approved",
        "production_package_ready",
        "render_requests_persisted",
        "render_outputs_completed",
        "screening_outputs_registered",
        "screening_outputs_approved",
        "editorial_analysis_persisted",
        "editorial_decision_confirmed",
        "film_cut_version_created",
        "film_cut_approved",
        "clip_revision_created",
        "revision_render_submitted",
        "revision_render_completed",
        "approved_memory_explicitly_saved",
    }
    observed_events = {row["event_type"] for row in transitions}
    missing_events = sorted(required_events - observed_events)
    require(not missing_events, f"required transitions missing: {missing_events}")
    _, listed = client.request(
        "GET",
        f"/api/f51/studio/projects/{project_id}/production-threads?scene_id={scene_id}",
        step="list canonical runs for exact scene",
    )
    require(listed["runs"][0]["run_id"] == run_id, "listed run does not match created run")
    require(listed["current_blueprint_version_id"] == version_id, "current Blueprint version did not reload")

    return {
        "project_id": project_id,
        "script_id": script_id,
        "scene_id": scene_id,
        "blueprint_id": blueprint_id,
        "blueprint_version_id": version_id,
        "run_id": run_id,
        "status": reloaded["status"],
        "transition_count": len(transitions),
        "production_package_id": package_id,
        "render_job_ids": production_job_ids,
        "screening_output_ids": screening_ids,
        "revision_job_id": submitted_revision_job_id,
        "final_run": reloaded,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="", help="Use an already-running backend instead of starting an isolated one")
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--project-id", default="")
    parser.add_argument("--keep-data", action="store_true", help="Keep the isolated backend data directory")
    parser.add_argument("--with-test-suite", action="store_true", help="Also run focused backend/frontend tests and the production build")
    parser.add_argument("--deliberate-failure", action="store_true", help="Inject a required assertion failure to prove non-zero exit behavior")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_dir = args.evidence_dir.resolve()
    recorder = Recorder(evidence_dir=evidence_dir)
    command = [sys.executable, *sys.argv]
    safe_environment = {
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "app_env": "local",
        "render_provider_test_mode": "mock_success",
        "provider_verification": "SIMULATED PROVIDER VERIFICATION",
        "paid_provider_calls": False,
        "external_backend": bool(args.base_url),
    }
    exit_code = 1
    backend: ManagedBackend | None = None
    temp_root: Path | None = None
    result: dict[str, Any] = {}

    try:
        recorder.emit("Checkpoint 7 independent verification started")
        require(sys.version_info >= (3, 11), "Python 3.11+ is required")
        require(BACKEND_ROOT.is_dir(), f"backend directory missing: {BACKEND_ROOT}")
        require(FRONTEND_ROOT.is_dir(), f"frontend directory missing: {FRONTEND_ROOT}")
        python = BACKEND_ROOT / ".venv/bin/python"
        require(python.is_file(), f"backend virtualenv Python missing: {python}")
        dependency_check = subprocess.run(
            [str(python), "-c", "import fastapi, uvicorn; print('dependencies-ok')"],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        require(dependency_check.returncode == 0, f"backend dependency check failed: {dependency_check.stderr}")
        recorder.passed("dependencies validated", {"python": str(python)})

        if args.base_url:
            base_url = args.base_url.rstrip("/")
            recorder.passed("connected to supplied backend", {"base_url": base_url})
        else:
            temp_root = Path(tempfile.mkdtemp(prefix="studio-checkpoint7-"))
            backend = ManagedBackend(
                python=python,
                port=available_port(),
                storage_dir=temp_root / "storage",
                project_store_path=temp_root / "project_state_store.json",
                log_path=evidence_dir / "runtime_http/backend_runtime.log",
            )
            backend.start()
            wait_for_backend(backend, recorder)
            base_url = backend.base_url

        if args.deliberate_failure:
            raise VerificationFailure("deliberate failure injection requested by --deliberate-failure")

        project_id = args.project_id.strip() or f"checkpoint7-{uuid4().hex[:10]}"
        client = ApiClient(base_url, recorder)
        result = exercise_workflow(client, recorder, project_id)

        if backend is not None:
            database_export = export_database(backend.storage_dir, result["run_id"], evidence_dir)
            require(database_export["canonical_run"] is not None, "canonical run missing from SQLite export")
            require(
                len(database_export["canonical_transitions"]) == result["transition_count"],
                "SQLite and API transition counts differ",
            )
            recorder.passed("SQLite persistence matches API state")

            backend.stop()
            backend.start()
            wait_for_backend(backend, recorder)
            restart_client = ApiClient(backend.base_url, recorder)
            _, after_restart_response = restart_client.request(
                "GET",
                f"/api/f51/studio/production-threads/{result['run_id']}",
                step="reload canonical run after backend restart",
            )
            after_restart = extract_run(after_restart_response, "restart reload")
            require(after_restart["status"] == "revision_completed", "terminal state did not survive backend restart")
            require(
                len(after_restart_response["transitions"]) == result["transition_count"],
                "transition count changed after backend restart",
            )
            recorder.passed("persistence survived backend restart", {"run_id": result["run_id"]})

        render_artifacts = result["final_run"]["data"]["artifacts"]["render_jobs"]
        revision = result["final_run"]["data"]["artifacts"]["revision"]
        provider_evidence = {
            "classification": "SIMULATED PROVIDER VERIFICATION",
            "paid_provider_calls": False,
            "provider": "simulated",
            "request": {
                "project_id": result["project_id"],
                "run_id": result["run_id"],
                "blueprint_version_id": result["blueprint_version_id"],
            },
            "provider_job_ids": result["final_run"]["data"]["identifiers"].get("provider_job_ids", []),
            "render_artifacts": render_artifacts,
            "revision": revision,
            "final_status": result["status"],
            "attached_application_record": result["run_id"],
            "timestamp": utc_now(),
        }
        write_json(evidence_dir / "provider/provider_evidence.json", provider_evidence)

        if args.with_test_suite:
            run_external_command(
                recorder,
                name="backend_focused_tests",
                command=[str(python), "-m", "pytest", "tests/test_checkpoint_5_canonical_workflow_thread.py", "tests/test_checkpoint_5_canonical_workflow_routes.py"],
                cwd=BACKEND_ROOT,
                timeout=180,
            )
            run_external_command(
                recorder,
                name="frontend_focused_tests",
                command=[
                    "npm", "test", "--", "--run",
                    "src/lib/canonicalWorkflowApi.test.ts",
                    "src/lib/canonicalWorkflowContext.test.ts",
                    "src/lib/optionalStudioApi.test.ts",
                    "src/lib/projectContext.test.ts",
                    "src/lib/studioMedia.test.ts",
                    "src/components/CanonicalWorkflowPanel.test.tsx",
                ],
                cwd=FRONTEND_ROOT,
                timeout=180,
            )
            run_external_command(
                recorder,
                name="frontend_production_build",
                command=["npm", "run", "build"],
                cwd=FRONTEND_ROOT,
                timeout=240,
            )

        summary = {
            "result": "VERIFIED",
            "classification": "SIMULATED PROVIDER VERIFICATION",
            "paid_provider_calls": False,
            "workflow": {key: value for key, value in result.items() if key != "final_run"},
            "pass_total": recorder.pass_count,
            "failure_total": recorder.failure_count,
            "skip_total": recorder.skip_count,
            "completed_at": utc_now(),
        }
        write_json(evidence_dir / "final_summary/reproduction_result.json", summary)
        recorder.emit(
            f"VERIFIED run={result['run_id']} status={result['status']} transitions={result['transition_count']} provider=SIMULATED"
        )
        exit_code = 0
    except VerificationFailure as exc:
        recorder.failed("independent reproduction", str(exc))
        write_json(
            evidence_dir / "final_summary/reproduction_result.json",
            {
                "result": "FAILED",
                "failure": str(exc),
                "classification": "SIMULATED PROVIDER VERIFICATION",
                "paid_provider_calls": False,
                "completed_at": utc_now(),
            },
        )
        exit_code = 1
    except Exception as exc:
        recorder.failed("independent reproduction", f"unexpected {type(exc).__name__}: {exc}")
        write_json(
            evidence_dir / "final_summary/reproduction_result.json",
            {
                "result": "FAILED",
                "failure": f"unexpected {type(exc).__name__}: {exc}",
                "classification": "SIMULATED PROVIDER VERIFICATION",
                "paid_provider_calls": False,
                "completed_at": utc_now(),
            },
        )
        exit_code = 1
    finally:
        if backend is not None:
            backend.stop()
        if temp_root is not None and temp_root.exists() and not args.keep_data:
            shutil.rmtree(temp_root)
        recorder.finalize(exit_code=exit_code, command=command, environment=safe_environment)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
