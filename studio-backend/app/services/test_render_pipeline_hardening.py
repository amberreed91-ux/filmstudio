from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services import render as render_module
from app.services.render import RenderService, _run_render_quality_check, set_storage
from app.services.render_job_backfill import hydrate_render_service_from_storage


class _StorageStub:
    def __init__(self, jobs: Optional[list[RenderJobModel]] = None):
        self._jobs: dict[str, RenderJobModel] = {job.id: job for job in (jobs or [])}
        self._projects: dict[str, dict] = {}
        self._universe_nodes: list[dict] = []
        self._reference_assets: list[dict] = []
        self.last_list_jobs_limit: int | None = None

    def get_universe_nodes(self, project_id: str):
        return [row for row in self._universe_nodes if row.get("project_id") == project_id]

    def list_reference_assets(self, project_id: str = "", target_type: str = "", target_id: str = "", limit: int = 50):
        rows = [row for row in self._reference_assets if row.get("project_id") == project_id]
        if target_type:
            rows = [row for row in rows if row.get("target_type") == target_type]
        if target_id:
            rows = [row for row in rows if row.get("target_id") == target_id]
        return rows[:limit]

    def seed_project_scene(self, project_id: str, shot_id: str) -> None:
        """Seed a scene with a project-scoped canonical setting and approved anchor.

        Generation preflight intentionally rejects guessed setting IDs and
        unapproved/missing anchors, so test scenes must satisfy that same
        provenance contract before exercising unrelated submit behavior.
        """
        from app.services.project_store import project_store
        from app.utils.helpers import derive_scene_id_from_shot_id

        scene_id = derive_scene_id_from_shot_id(shot_id)
        setting_id = f"test-setting-{project_id}-{scene_id}"
        if project_store.get_project(project_id) is None:
            project_store.create_project(project_id=project_id)
        project = project_store.get_project(project_id)
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = [row for row in (summary.get("scenes") or []) if isinstance(row, dict)]
        if not any(row.get("scene_id") == scene_id for row in scenes):
            scenes.append({"scene_id": scene_id, "heading": f"INT. TEST - {scene_id}", "text": "Test scene.", "setting_id": setting_id, "location": "Test location"})
            summary["scenes"] = scenes
            project_store.update_project(project_id, {"execution_summary": summary})
        if not any(row.get("node_id") == setting_id and row.get("project_id") == project_id for row in self._universe_nodes):
            self._universe_nodes.append({
                "node_id": setting_id,
                "project_id": project_id,
                "node_type": "location",
                "name": "Test location",
                "first_scene": scene_id,
                "last_scene": scene_id,
            })
        if not any(row.get("target_id") == setting_id for row in self._reference_assets):
            self._reference_assets.append({
                "ref_id": f"test-environment-{project_id}-{scene_id}",
                "project_id": project_id,
                "target_type": "setting",
                "target_id": setting_id,
                "kind": "environment",
                "image_url": f"https://example.com/{setting_id}.png",
                "canonical": True,
                "approval_state": "approved",
                "source_kind": "confirmed",
            })
        return scene_id, setting_id

    def save_job(self, job: RenderJobModel):
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)

    def list_jobs(self, project_id: Optional[str] = None, status: Optional[str] = None, limit: int = 10000):
        self.last_list_jobs_limit = limit
        rows = list(self._jobs.values())
        if project_id:
            rows = [row for row in rows if row.project_id == project_id]
        if status:
            rows = [row for row in rows if row.status == status]
        return rows[:limit]

    def save_project(self, project):
        project_id = getattr(project, "project_id", None) or str((project or {}).get("project_id", ""))
        if project_id:
            self._projects[project_id] = {"project_id": project_id}
        return project


class _MissingFileReferenceStub(_StorageStub):
    """Storage stub that registers the nonexistent file as an approved,
    canonical setting reference so the reference-ownership gate passes and the
    file-existence check is what actually fails (the test's subject)."""

    def list_reference_assets(self, project_id: str = "", target_type: str = "", target_id: str = "", limit: int = 50):
        if target_type == "setting" and target_id == getattr(self, "missing_target_id", None):
            return [
                {
                    "ref_id": "missing-file",
                    "project_id": project_id,
                    "target_type": "setting",
                    "target_id": target_id,
                    "kind": "environment",
                    "image_url": "/tmp/studio-reference-that-does-not-exist.png",
                    "canonical": True,
                    "approval_state": "approved",
                    "source_kind": "confirmed",
                }
            ]
        return super().list_reference_assets(project_id, target_type, target_id, limit)


class _AdapterComplete:
    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        if job.status == "pending":
            job.status = "rendering"
            job.provider_job_id = job.provider_job_id or f"task-{job.id}"
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        job.status = "complete"
        job.progress = 100
        job.output_payload = RenderJobOutput(asset_url="https://example.com/out.mp4")
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        return True

    async def fetch_outputs(self, job: RenderJobModel):
        return []


class _AdapterSlowSubmit(_AdapterComplete):
    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        await asyncio.sleep(0.05)
        return await super().submit_job(job)


class _AdapterCompleteWithoutUrl(_AdapterComplete):
    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        job.status = "complete"
        job.progress = 100
        job.output_payload = RenderJobOutput(asset_url="")
        return job


def test_restart_recovery_completes_rendering_job(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()

    now = datetime.now().isoformat()
    job = RenderJobModel(
        id="job-restart-1",
        project_id="p1",
        shot_id="shot_1",
        provider="runway",
        provider_job_id="task-123",
        status="rendering",
        progress=45,
        created_at=now,
        updated_at=now,
    )
    service._jobs[job.id] = job
    storage.save_job(job)

    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterComplete())

    result = asyncio.run(service.recover_jobs_after_restart())
    recovered = service.get_job(job.id)

    assert result["recovered_jobs"] == 1
    assert recovered is not None
    assert recovered.status == "complete"
    assert recovered.recovery_status in {"recovered_terminal", "orphan_reconciled"}
    assert recovered.output_payload is not None


def test_restart_recovery_hydration_uses_bounded_limit():
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()

    result = asyncio.run(service.recover_jobs_after_restart())

    assert result["hydrated_jobs"] == 0
    assert storage.last_list_jobs_limit == 1000


def test_stale_task_recovery_without_provider_task_id():
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()

    stale_time = (datetime.now() - timedelta(minutes=30)).isoformat()
    job = RenderJobModel(
        id="job-stale-1",
        project_id="p1",
        shot_id="shot_2",
        provider="simulated",
        status="rendering",
        progress=10,
        created_at=stale_time,
        updated_at=stale_time,
    )
    service._jobs[job.id] = job

    result = asyncio.run(service.recover_jobs_after_restart())
    recovered = service.get_job(job.id)

    assert result["stale_recovered_jobs"] == 1
    assert recovered is not None
    assert recovered.status == "failed"
    assert recovered.recovery_status == "stale_recovered"
    assert "Stale job" in (recovered.error_message or "")
    reliability = recovered.metadata["pipeline_reliability"]
    assert reliability["failure_location"]["phase"] == "render"
    assert reliability["failure_location"]["error_type"] == "abandoned_without_provider_job_id"


def test_restart_recovery_hydrates_persisted_jobs(monkeypatch):
    now = datetime.now().isoformat()
    persisted = RenderJobModel(
        id="job-hydrate-1",
        project_id="p1",
        shot_id="shot_2",
        provider="runway",
        provider_job_id="task-456",
        status="rendering",
        progress=20,
        created_at=now,
        updated_at=now,
    )
    storage = _StorageStub([persisted])
    set_storage(storage)
    service = RenderService()
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterComplete())

    result = asyncio.run(service.recover_jobs_after_restart())

    assert result["hydrated_jobs"] == 1
    assert result["recovered_jobs"] == 1
    assert service.get_job("job-hydrate-1").status == "complete"


def test_duplicate_submission_prevention(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()
    storage.seed_project_scene("p1", "shot_3")
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterComplete())

    job = service.create_job(project_id="p1", shot_id="shot_3", provider="simulated", prompt="test")
    first = asyncio.run(service.submit_job(job.id))
    second = asyncio.run(service.submit_job(job.id))

    assert first.status == "rendering"
    assert second.status == "rendering"
    assert second.provider_job_id == first.provider_job_id


def test_duplicate_generate_request_reuses_active_job():
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()

    first = service.create_job(project_id="p1", shot_id="shot_3", provider="simulated", prompt="same prompt with enough detail to avoid scene lookup")
    second = service.create_job(project_id="p1", shot_id="shot_3", provider="simulated", prompt="same prompt with enough detail to avoid scene lookup")

    assert second.id == first.id
    reliability = second.metadata["pipeline_reliability"]
    assert reliability["idempotency_key"]
    assert reliability["duplicate_request_reused_at"]


def test_missing_reference_file_stops_before_provider_submission():
    storage = _MissingFileReferenceStub()
    set_storage(storage)
    service = RenderService()
    scene_id, setting_id = storage.seed_project_scene("p1", "shot_missing_ref")
    storage.missing_target_id = setting_id
    # Replace the valid fixture anchor with the approved-but-missing URI so
    # preflight reaches the local file-existence check that this test covers.
    storage._reference_assets = [
        row for row in storage._reference_assets if row.get("target_id") != setting_id
    ]
    from app.models.consistency import ConsistencyPayload, ReferenceAsset
    from app.services.project_store import project_store

    _project = project_store.get_project("p1")
    _summary = _project["execution_summary"]
    for row in _summary["scenes"]:
        if row.get("scene_id") == scene_id:
            row["location"] = "Test location"

    job = service.create_job(
        project_id="p1",
        shot_id="shot_missing_ref",
        provider="simulated",
        prompt="A corridor holds a quiet practical light and a slow push in.",
        reference_assets=["/tmp/studio-reference-that-does-not-exist.png"],
    )
    # The reference-ownership gate requires the payload to carry its selected
    # reference set; give it the (missing-file) environment anchor so the
    # file-existence check is the failure under test.
    job.input_payload.consistency_payload = ConsistencyPayload(
        project_id="p1",
        mode="environment_lock",
        refs=[
            ReferenceAsset(
                ref_id="missing-file",
                kind="environment",
                image_url="/tmp/studio-reference-that-does-not-exist.png",
                project_id="p1",
                target_type="setting",
                target_id=setting_id,
                approval_state="approved",
            )
        ],
    )
    submitted = asyncio.run(service.submit_job(job.id))

    assert submitted.status == "failed"
    assert submitted.provider_job_id is None
    reliability = submitted.metadata["pipeline_reliability"]
    assert reliability["failure_location"]["phase"] == "resolve_references"
    assert reliability["failure_location"]["error_type"] == "reference_file_missing"


def test_app_served_storyboard_reference_does_not_fail_local_preflight():
    missing = render_module._missing_local_reference_assets(
        [
            "/previs-assets/project_1/scene_001_shot_001.png",
            "previs-assets/project_1/scene_001_shot_002.png",
            "/outputs/references/project_1/locked.jpg",
            "/static/style/reference.png",
            "/tmp/studio-reference-that-does-not-exist.png",
        ]
    )

    assert missing == ["/tmp/studio-reference-that-does-not-exist.png"]


def test_invalid_scene_input_is_rejected_before_job_creation():
    service = RenderService()

    try:
        service.create_job(project_id="p1", shot_id="", provider="simulated", prompt="valid prompt")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "shot_id cannot be empty" in str(exc)


def test_persistence_failure_records_failure_location_in_memory():
    class _BrokenStorage(_StorageStub):
        def save_job(self, job: RenderJobModel):
            raise RuntimeError("database is locked")

    storage = _BrokenStorage()
    set_storage(storage)
    service = RenderService()

    job = service.create_job(
        project_id="p1",
        shot_id="shot_persist_fail",
        provider="simulated",
        prompt="Mara waits in a hallway under practical light.",
    )

    assert job.metadata["persistence_failure"]["error_type"] == "persistence_error"
    assert job.metadata["pipeline_reliability"]["failure_location"]["phase"] == "persist"


def test_provider_call_timeout_records_render_failure(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()
    storage.seed_project_scene("p1", "shot_provider_timeout")  # derives scene 'shot_provider'
    monkeypatch.setattr(render_module, "PROVIDER_CALL_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterSlowSubmit())

    job = service.create_job(
        project_id="p1",
        shot_id="shot_provider_timeout",
        provider="simulated",
        prompt="A static frame watches a doorway in low practical light.",
    )

    try:
        asyncio.run(service.submit_job(job.id))
        assert False, "expected timeout"
    except TimeoutError:
        pass

    failed = service.get_job(job.id)
    assert failed.status == "failed"
    assert failed.metadata["pipeline_reliability"]["failure_location"]["phase"] == "render"
    assert failed.metadata["provider_failure"]["error_type"] == "timeout"


def test_rate_limit_is_classified_temporary():
    now = datetime.now().isoformat()
    job = RenderJobModel(
        id="job-rate-limit",
        project_id="p1",
        shot_id="shot_rate_limit",
        provider="runway",
        status="failed",
        error_message="Runway API error 429",
        output_payload=RenderJobOutput(
            asset_url="",
            metadata={
                "provider_response_normalized": {
                    "metadata": {
                        "error": {
                            "error_type": "rate_limit",
                            "message": "Provider rate limit reached",
                            "status_code": "429",
                        }
                    }
                }
            },
        ),
        created_at=now,
        updated_at=now,
    )

    render_module._record_provider_failure_policy(job)

    assert job.metadata["provider_failure"]["category"] == "temporary"
    assert job.metadata["provider_failure"]["retryable"] is True


def test_complete_without_preview_or_output_url_records_download_failure(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterCompleteWithoutUrl())
    now = datetime.now().isoformat()
    job = RenderJobModel(
        id="job-no-preview",
        project_id="p1",
        shot_id="shot_no_preview",
        provider="simulated",
        status="rendering",
        created_at=now,
        updated_at=now,
    )
    service._jobs[job.id] = job

    updated = asyncio.run(service.get_job_status(job.id))

    assert updated.status == "failed"
    assert updated.metadata["pipeline_reliability"]["failure_location"]["error_type"] == "missing_video_url"


def test_retry_limit_reached_records_failure_location():
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()
    now = datetime.now().isoformat()
    job = RenderJobModel(
        id="job-retry-cap",
        project_id="p1",
        shot_id="shot_retry_cap",
        provider="simulated",
        status="failed",
        retry_count=render_module.MAX_RETRIES,
        created_at=now,
        updated_at=now,
    )
    service._jobs[job.id] = job

    try:
        asyncio.run(service.submit_job(job.id))
        assert False, "expected retry cap ValueError"
    except ValueError as exc:
        assert "exceeded max retries" in str(exc)

    assert job.metadata["pipeline_reliability"]["failure_location"]["error_type"] == "retry_limit_reached"


def test_persistence_restoration_hydrates_jobs():
    now = datetime.now().isoformat()
    existing = RenderJobModel(
        id="job-persist-1",
        project_id="p2",
        shot_id="shot_4",
        provider="simulated",
        status="complete",
        progress=100,
        recovery_status="recovered_terminal",
        last_polled_at=now,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    storage = _StorageStub([existing])
    service = RenderService()

    loaded = hydrate_render_service_from_storage(service, storage)
    restored = service.get_job(existing.id)

    assert loaded == 1
    assert restored is not None
    assert restored.recovery_status == "recovered_terminal"
    assert restored.last_polled_at == now


def test_quality_check_records_evaluation_failure_without_raising(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    now = datetime.now().isoformat()
    job = RenderJobModel(
        id="job-eval-failure-1",
        project_id="p3",
        shot_id="shot_5",
        provider="simulated",
        status="complete",
        progress=100,
        input_payload=RenderJobInput(
            shot_id="shot_5",
            prompt="Mara waits in the hallway.",
            parameters={"prompt_slots": {"character": "Mara"}},
        ),
        output_payload=RenderJobOutput(asset_url="https://example.com/eval-fails.mp4"),
        metadata={
            "zero_touch_pipeline": {
                "phases": [
                    {"phase": "evaluate", "status": "pending"},
                    {"phase": "retry", "status": "pending"},
                ]
            }
        },
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    storage.save_job(job)

    async def _raise_record_attempt(**_kwargs):
        raise RuntimeError("adherence evaluator unavailable")

    monkeypatch.setattr(
        "app.services.render_retry_service.render_retry_service.record_render_attempt",
        _raise_record_attempt,
    )

    asyncio.run(_run_render_quality_check(job))

    persisted = storage.get_job(job.id)
    phases = {
        row["phase"]: row
        for row in persisted.metadata["zero_touch_pipeline"]["phases"]
    }
    assert phases["evaluate"]["status"] == "failed"
    assert "adherence evaluator unavailable" in phases["evaluate"]["error"]
    assert phases["evaluate"]["duration_ms"] >= 0
    assert phases["retry"]["status"] == "pending"
    assert persisted.metadata.get("adherence_retry_cascade") is None


def test_ten_controlled_mocked_jobs_complete_without_state_corruption(monkeypatch):
    storage = _StorageStub()
    set_storage(storage)
    service = RenderService()
    # create_scene_batch uses film_id as the job's project_id.
    for index in range(1, 11):
        storage.seed_project_scene("project-controlled-batch", f"scene_batch_001_shot_{index:03d}")
    monkeypatch.setattr("app.services.render.get_adapter", lambda *_args, **_kwargs: _AdapterComplete())

    shots = [
        {
            "shot_id": f"scene_batch_001_shot_{index:03d}",
            "prompt": f"Controlled reliability shot {index}, static camera, practical light, clear subject.",
        }
        for index in range(1, 11)
    ]

    batch = asyncio.run(
        service.create_scene_batch(
            film_id="project-controlled-batch",
            scene_id="scene_batch_001",
            scene_data={},
            shots=shots,
            provider="simulated",
        )
    )
    for job_id in batch["job_ids"]:
        asyncio.run(service.get_job_status(job_id))

    status = service.get_batch_status(batch["batch_id"])
    stored_jobs = storage.list_jobs(project_id="project-controlled-batch", limit=20)
    job_ids = [job.id for job in stored_jobs]
    correlations = [
        job.metadata["pipeline_reliability"]["correlation_id"]
        for job in stored_jobs
    ]

    assert status["total"] == 10
    assert status["complete"] == 10
    assert status["failed"] == 0
    assert len(batch["job_ids"]) == 10
    assert len(set(batch["job_ids"])) == 10
    assert len(stored_jobs) == 10
    assert len(set(job_ids)) == 10
    assert len(set(correlations)) == 10
    assert all(job.batch_id == batch["batch_id"] for job in stored_jobs)
    assert all(job.status == "complete" and job.output_payload for job in stored_jobs)
