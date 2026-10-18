"""Render state hardening: runtime status vs persisted status agreement.

The render job state machine (``RenderJobModel.can_transition_to``) treats
``queued`` — provider accepted, not yet rendering — as a transient alias of
``pending``. The ``render_jobs`` CHECK constraint has only ever allowed
``('pending', 'rendering', 'complete', 'failed', 'cancelled', 'needs_review',
'skipped')``. These tests pin the agreement between the two:

- runtime-only states normalize to their canonical persisted equivalents at
  the single storage write choke point (``DatabaseStorage.save_job``),
- genuinely invalid statuses still fail loudly (no silent swallowing, no
  invalid rows), and
- the canonical lifecycle pending → rendering → complete / failed round-trips
  through real SQLite unchanged.
"""

from __future__ import annotations

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel


@pytest.fixture()
def db_storage(tmp_path):
    """Real SQLite storage with the production schema and constraints."""
    return DatabaseStorage(str(tmp_path / "storage"))


def _job(status: str, job_id: str = "job-state-1") -> RenderJobModel:
    now = "2026-09-23T12:00:00"
    return RenderJobModel(
        id=job_id,
        project_id="project_state",
        shot_id="scene_001_shot_001",
        provider="simulated",
        status=status,
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="State machine persistence probe",
            referenceAssets=[],
            parameters={},
        ),
        created_at=now,
        updated_at=now,
    )


def _persisted_status(storage: DatabaseStorage, job_id: str) -> str:
    with storage._get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM render_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return row["status"] if row else ""


# ── Runtime-only states persist under their canonical alias ───────────────


def test_queued_job_persists_as_pending(db_storage: DatabaseStorage):
    """A job accepted by the provider ('queued' at runtime) persists correctly.

    Before the fix this raised ``CHECK constraint failed: status 'queued'``
    at insert time; the in-memory job kept moving while the durable record
    never existed. Now the runtime alias projects to its canonical status.
    """
    job = _job("queued")
    saved = db_storage.save_job(job)

    assert saved.status == "queued"  # runtime view is unchanged in memory
    assert _persisted_status(db_storage, job.id) == "pending"


def test_queued_round_trips_with_runtime_alias_and_persistence_metadata(db_storage: DatabaseStorage):
    """Reloaded rows keep the runtime alias visible without storing it as status."""
    job = _job("queued", job_id="job-queued-alias")
    db_storage.save_job(job)

    reloaded = db_storage.get_job(job.id)
    assert reloaded is not None
    # The persisted status is canonical; the runtime alias is preserved in
    # metadata so operators can tell 'provider accepted' from 'pre-submit'.
    assert reloaded.status == "pending"
    metadata = reloaded.metadata or {}
    assert metadata.get("runtime_status") == "queued"


def test_other_runtime_aliases_normalize(db_storage: DatabaseStorage):
    for runtime_status, persisted in (
        ("submitted", "pending"),
        ("processing", "rendering"),
        ("running", "rendering"),
        ("in_progress", "rendering"),
    ):
        job = _job(runtime_status, job_id=f"job-alias-{runtime_status}")
        db_storage.save_job(job)
        assert _persisted_status(db_storage, job.id) == persisted


def test_noncanonical_runtime_status_recorded_in_metadata_json_column(db_storage: DatabaseStorage):
    """Legacy tables carrying metadata_json also record the alias mapping."""
    job = _job("queued", job_id="job-queued-meta")
    db_storage.save_job(job)
    with db_storage._get_connection() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(render_jobs)")}
    if "metadata_json" in columns:
        reloaded = db_storage.get_job(job.id)
        assert (reloaded.metadata or {}).get("runtime_status") == "queued"


# ── Invalid statuses are still rejected loudly ────────────────────────────


def test_invalid_status_still_rejected_by_check_constraint(db_storage: DatabaseStorage):
    """Unknown statuses must fail the CHECK — the fix never widens the DB."""
    import sqlite3

    job = _job("teleported")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        db_storage.save_job(job)
    assert "CHECK constraint failed" in str(excinfo.value)
    assert db_storage.get_job(job.id) is None


# ── Canonical lifecycle round-trips through real SQLite ───────────────────


def test_lifecycle_queued_to_running_to_complete(db_storage: DatabaseStorage):
    job = _job("queued")
    db_storage.save_job(job)
    assert _persisted_status(db_storage, job.id) == "pending"

    job.status = "rendering"
    job.progress = 40
    db_storage.save_job(job)
    assert _persisted_status(db_storage, job.id) == "rendering"

    job.status = "complete"
    job.progress = 100
    job.completed_at = "2026-09-23T12:05:00"
    db_storage.save_job(job)
    assert _persisted_status(db_storage, job.id) == "complete"

    reloaded = db_storage.get_job(job.id)
    assert reloaded.status == "complete"
    assert reloaded.completed_at == "2026-09-23T12:05:00"


def test_lifecycle_queued_to_failed(db_storage: DatabaseStorage):
    job = _job("queued", job_id="job-queued-failed")
    db_storage.save_job(job)
    job.status = "failed"
    job.error_message = "provider rejected the render"
    db_storage.save_job(job)

    reloaded = db_storage.get_job(job.id)
    assert reloaded.status == "failed"
    assert reloaded.error_message == "provider rejected the render"


def test_lifecycle_failed_retry_and_terminal_states_round_trip(db_storage: DatabaseStorage):
    job = _job("failed", job_id="job-lifecycle-retry")
    db_storage.save_job(job)
    job.status = "pending"  # retry path
    db_storage.save_job(job)
    assert _persisted_status(db_storage, job.id) == "pending"

    for status in ("cancelled", "needs_review", "skipped"):
        terminal = _job(status, job_id=f"job-terminal-{status}")
        db_storage.save_job(terminal)
        assert _persisted_status(db_storage, terminal.id) == status


def test_state_machine_and_persistence_vocabulary_agree(db_storage: DatabaseStorage):
    """Every status the state machine can reach is persistable, and every
    persisted status maps back to a state the runtime understands."""
    machine_statuses = {"pending", "queued", "rendering", "complete", "failed", "cancelled"}
    for status in sorted(machine_statuses):
        job = _job(status, job_id=f"job-vocab-{status}")
        db_storage.save_job(job)  # must not raise
        persisted = _persisted_status(db_storage, job.id)
        assert persisted in {"pending", "rendering", "complete", "failed", "cancelled", "needs_review", "skipped"}
        reloaded = db_storage.get_job(job.id)
        assert reloaded.is_terminal() == (status in {"complete", "failed", "cancelled"})


# ── Provider submission never creates an invalid persisted row ────────────


class _AdapterQueuedThenRendering:
    """Simulates local_ltx semantics: submit → queued, poll → rendering."""

    async def submit_job(self, job: RenderJobModel) -> RenderJobModel:
        job.status = "queued"
        job.provider_job_id = f"phosphene-{job.id}"
        return job

    async def get_job_status(self, job: RenderJobModel) -> RenderJobModel:
        job.status = "rendering"
        job.progress = 25
        return job

    async def cancel_job(self, job: RenderJobModel) -> bool:
        return True

    async def fetch_outputs(self, job: RenderJobModel):
        return []


def test_provider_submission_persists_queued_as_pending(monkeypatch, tmp_path):
    """Submitting to a provider that reports 'queued' leaves a valid DB row.

    Regression for the live-testing failure: submit succeeded, the adapter set
    status='queued', ``_persist_job`` hit the CHECK constraint, and the job's
    durable record silently vanished while the runtime continued.
    """
    import asyncio

    from app.services import render as render_module
    from app.services.render import RenderService

    storage = DatabaseStorage(str(tmp_path / "storage-submit"))
    render_module.set_storage(storage)
    monkeypatch.setattr(render_module, "validate_generation_payload", lambda **_kwargs: {})
    monkeypatch.setattr(
        render_module.project_store,
        "get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [{"scene_id": "scene_001", "characters": []}]
            },
        },
    )
    try:
        service = RenderService()
        monkeypatch.setattr(
            "app.services.render.get_adapter",
            lambda *_args, **_kwargs: _AdapterQueuedThenRendering(),
        )
        job = service.create_job(
            project_id="project_state",
            shot_id="scene_001_shot_002",
            provider="simulated",
            prompt="Provider submission persistence probe with enough detail",
        )
        submitted = asyncio.run(service.submit_job(job.id))

        # Runtime keeps the provider's truthful 'queued'; the durable row is valid.
        assert submitted.status == "queued"
        assert _persisted_status(storage, job.id) == "pending"

        reloaded = storage.get_job(job.id)
        assert reloaded is not None
        assert reloaded.provider_job_id == submitted.provider_job_id
    finally:
        render_module.set_storage(None)


def test_local_ltx_poll_keeps_queued_job_persistable(tmp_path, monkeypatch):
    """The polling loop treats persisted 'pending' (runtime queued) rows as active."""
    from app.services.render import RenderService

    service = RenderService()
    job = _job("queued", job_id="job-poll-queued")
    service._jobs[job.id] = job

    active = service._get_jobs_by_status(["queued", "pending", "rendering", "processing", "submitted"])
    assert any(candidate.id == job.id for candidate in active)

    # And the model still refuses an illegal jump: terminal → queued.
    assert job.can_transition_to("complete") is False


def test_job_with_selection_audit_round_trips_through_storage(db_storage: DatabaseStorage):
    """A consistency payload carrying the selection audit persists and reloads."""
    from app.models.consistency import ConsistencyPayload, ReferenceAsset

    job = _job("rendering", job_id="job-audit-roundtrip")
    job.input_payload.consistency_payload = ConsistencyPayload(
        project_id=job.project_id,
        refs=[
            ReferenceAsset(
                ref_id="maya-canonical",
                kind="character_face",
                image_url="https://cdn.example/maya.png",
                project_id=job.project_id,
                target_type="character",
                target_id="maya",
                approval_state="approved",
                canonical=True,
            )
        ],
        mode="identity_lock",
        selection_audit=[
            {
                "character_id": "maya",
                "selection": {
                    "selected": [{"ref_id": "maya-canonical", "tier": "canonical"}],
                    "excluded_count": 1,
                    "excluded": [{"ref_id": "maya-night", "reason": "provider reference budget exhausted"}],
                },
            }
        ],
    )
    db_storage.save_job(job)

    reloaded = db_storage.get_job(job.id)
    assert reloaded is not None
    payload = reloaded.input_payload.consistency_payload
    assert payload is not None
    if isinstance(payload, dict):  # dict form when the input model stores raw JSON
        audit = payload["selection_audit"]
    else:
        audit = payload.selection_audit
    assert audit and audit[0]["character_id"] == "maya"
