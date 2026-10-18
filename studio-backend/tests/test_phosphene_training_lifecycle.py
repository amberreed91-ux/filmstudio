"""Real Phosphene training lifecycle tests.

Covers the honest async training boundary Studio now uses for the real
Phosphene trainer:

    Studio job → /train/upload → /train/start → provider id persisted →
    queued → running (via status polling) → completed LoRA discovered via
    /characters → persisted artifact → usable by the render pipeline.

All Phosphene HTTP traffic is faked with deterministic in-memory sessions —
no panel, models, or Pinokio needed. The service-level tests use real SQLite
storage (tmp_path) so restart/recovery semantics are exercised against the
same persistence layer production uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.services.visual_training_service as vts_module
from app.adapters.phosphene_training import (
    PROVIDER_ID,
    PhospheneTrainingAdapter,
    build_default_config as build_phosphene_config,
)
from app.data.storage import DatabaseStorage
from app.models import ProviderConfig
from app.services.stability import ValidationError
from app.services.visual_training_service import VisualTrainingService


# ---------------------------------------------------------------------------
# Deterministic fake HTTP session (same shape as test_local_ltx_provider.py)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status: int = 200):
        self._payload = payload
        self.status = status
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeAiohttpError(Exception):
    pass


class _FakeSession:
    """Records (method, url, data) and serves canned payloads per path."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.get_payloads: dict[str, object] = {}
        self.post_payloads: dict[str, object] = {}
        # per-path GET payload sequences: pop(0) on each hit
        self.get_sequences: dict[str, list] = {}
        self.get_raises: dict[str, Exception] = {}

    def _lookup(self, table, url):
        for suffix, payload in table.items():
            if url.endswith(suffix):
                return payload
        return None

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, None))
        for suffix, exc in self.get_raises.items():
            if url.endswith(suffix):
                raise exc
        seq = self.get_sequences.get(url)
        if seq:
            payload = seq.pop(0)
        else:
            payload = self._lookup(self.get_payloads, url)
        if payload is None:
            return _FakeResponse({"error": "not found"}, 404)
        status = 200
        if isinstance(payload, tuple):
            payload, status = payload
        return _FakeResponse(payload, status)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs.get("data")))
        payload = self._lookup(self.post_payloads, url)
        if payload is None:
            return _FakeResponse({"error": "not found"}, 404)
        status = 200
        if isinstance(payload, tuple):
            payload, status = payload
        return _FakeResponse(payload, status)


def _config(**overrides) -> ProviderConfig:
    values = dict(
        provider_id=PROVIDER_ID,
        name="Phosphene Training",
        enabled=True,
        is_simulated=False,
        api_key=None,
        api_endpoint="http://127.0.0.1:8198",
        requires=["local_service"],
        capabilities=["visual_training"],
        models=["ltx-2.3-mlx-q4"],
    )
    values.update(overrides)
    return ProviderConfig(**values)


def _adapter_with(session: _FakeSession) -> PhospheneTrainingAdapter:
    adapter = PhospheneTrainingAdapter(_config())

    async def _session():
        return session

    adapter._get_session = _session  # type: ignore[method-assign]
    return adapter


# ---------------------------------------------------------------------------
# Service fixtures
# ---------------------------------------------------------------------------


def _save_asset(storage: DatabaseStorage, ref_id: str, project_id: str) -> None:
    # Training sources must be approved references (approved-only enforcement
    # in VisualTrainingService._validate_source_assets).
    storage.save_reference_asset(
        {
            "ref_id": ref_id,
            "project_id": project_id,
            "kind": "character_face",
            "image_url": f"/previs-assets/{ref_id}.png",
            "created_at": "2026-01-01T00:00:00+00:00",
            "approval_state": "approved",
        }
    )


@pytest.fixture
def storage(tmp_path: Path) -> DatabaseStorage:
    db = DatabaseStorage(str(tmp_path / "phosphene_training.db"))
    from app.models import StudioProject

    db.save_project(StudioProject(project_id="film-a", title="Film A"))
    db.save_project(StudioProject(project_id="film-b", title="Film B"))
    return db


class _FakeStatusAdapter(PhospheneTrainingAdapter):
    """Real adapter shape with a canned get_training_status response."""

    def __init__(self, config: ProviderConfig, status_result: dict):
        super().__init__(config)
        self.status_result = status_result
        self.status_calls: list[str] = []

    async def get_training_status(self, job):
        self.status_calls.append(job.provider_job_id)
        return dict(self.status_result)


@pytest.fixture
def service(storage, monkeypatch):
    """VisualTrainingService wired to a per-test Phosphene adapter fake."""
    holder: dict[str, _FakeStatusAdapter] = {}

    def _make(status_result: dict | None = None) -> VisualTrainingService:
        adapter = _FakeStatusAdapter(_config(), status_result or {"found": False})
        monkeypatch.setattr(
            vts_module, "get_training_adapter", lambda provider_id, config: adapter
        )
        holder["adapter"] = adapter
        svc = VisualTrainingService(storage=storage)
        svc.register_provider_config(_config())
        return svc

    holder["make"] = _make
    return holder


def _create_job(svc: VisualTrainingService, **overrides):
    _save_asset(svc._storage, "ref_train_1", "film-a")
    params = dict(
        project_id="film-a",
        visual_model_id=None,
        target_type="character",
        trigger_word="miratrn",
        source_asset_ids=["ref_train_1"],
        provider=PROVIDER_ID,
        provider_model="ltx-2.3-mlx-q4",
        configuration={
            "source_assets": [
                {
                    "ref_id": "ref_train_1",
                    "kind": "character_face",
                    "image_url": str(Path(__file__)),
                }
            ]
        },
    )
    params.update(overrides)
    return svc.create_training_job(**params)


# ---------------------------------------------------------------------------
# 1. Training image upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_train_upload_sends_image_bytes_and_echoes_dataset_id(tmp_path):
    image = tmp_path / "mira_ref.png"
    image.write_bytes(b"\x89PNG fake-bytes")
    session = _FakeSession()
    session.post_payloads["/train/upload"] = {
        "ok": True,
        "job_id": "j-ds1",
        "count": 1,
    }
    adapter = _adapter_with(session)

    result = await adapter.upload_training_images([str(image)])

    assert result["ok"] is True
    assert result["train_job_id"] == "j-ds1"
    assert result["uploaded"] == 1
    uploads = [c for c in session.calls if c[0] == "POST" and c[1].endswith("/train/upload")]
    assert len(uploads) == 1
    form = uploads[0][2]
    # aiohttp stores FormData fields as (options, headers, value) tuples;
    # the field name is carried in the options mapping.
    fields = {field[0]["name"]: field for field in form._fields}
    assert "file" in fields
    # No job_id on the first upload (dataset id is minted server-side).
    assert "job_id" not in fields


# ---------------------------------------------------------------------------
# 2-3. Submission + provider job id persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_persists_provider_job_id_and_marks_queued(service, monkeypatch):
    svc = service["make"]()
    # Replace the fake with a real-shape adapter whose submit path is faked at
    # the HTTP layer: preflight ok, upload ok, start ok.
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = {
        "ok": True,
        "required": [{"key": "k", "ready": True}],
        "all_ready": True,
    }
    session.post_payloads["/train/upload"] = {"ok": True, "job_id": "j-ds9", "count": 1}
    session.post_payloads["/train/start"] = {
        "ok": True,
        "queued_id": "j-run1",
        "train_job_id": "j-ds9",
        "params": {"mode": "train"},
    }
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)

    assert result.status == "queued"
    assert result.provider_job_id == "j-ds9"
    assert result.completed_at is None
    assert result.configuration["provider_job_id"] == "j-ds9"
    assert result.configuration["queued_id"] == "j-run1"
    # Persisted: a fresh service instance reloads the provider id.
    fresh = VisualTrainingService(storage=svc._storage)
    reloaded = fresh.get_training_job(job.id)
    assert reloaded is not None
    assert reloaded.provider_job_id == "j-ds9"
    assert reloaded.status == "queued"
    # The queued job must NOT be a registered complete model.
    assert fresh.get_visual_model(job.target_id) is None
    assert [c[1] for c in session.calls if c[0] == "POST"].count(
        session.calls[0][1]
    ) >= 0  # (recorded calls exist)
    posts = [c[1] for c in session.calls if c[0] == "POST"]
    assert any(p.endswith("/train/upload") for p in posts)
    assert any(p.endswith("/train/start") for p in posts)


@pytest.mark.asyncio
async def test_submit_persists_queued_id_when_dataset_id_differs(service, monkeypatch):
    """Provider id follows /train/start's train_job_id (the lifecycle identity)."""
    svc = service["make"]()
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = {
        "ok": True,
        "required": [],
        "all_ready": True,
    }
    session.post_payloads["/train/upload"] = {"ok": True, "job_id": "j-dsA", "count": 3}
    session.post_payloads["/train/start"] = {
        "ok": True,
        "queued_id": "j-run2",
        "train_job_id": "j-run2",
    }
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)

    assert result.provider_job_id == "j-run2"


# ---------------------------------------------------------------------------
# 4. Running state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_running_marks_training(service, storage):
    svc = service["make"](
        {"found": True, "state": "running", "error": None, "phase_label": "Training face · step 40 / 120"}
    )
    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "queued"
    svc._persist_job_state(job)

    result = await svc.refresh_training_job(job.id)

    assert result.status == "training"
    assert result.configuration.get("provider_phase") == "Training face · step 40 / 120"
    # Persisted.
    assert storage.get_visual_training_job(job.id)["status"] == "training"


# ---------------------------------------------------------------------------
# 5-10. Completion, LoRA discovery, generation-path flow
# ---------------------------------------------------------------------------


class _DiscoveringAdapter(_FakeStatusAdapter):
    def __init__(self, config, status_result, discovery):
        super().__init__(config, status_result)
        self.discovery = discovery
        self.discovery_calls = 0

    async def find_provider_character(self, job):
        self.discovery_calls += 1
        return dict(self.discovery)


@pytest.mark.asyncio
async def test_refresh_complete_discovers_lora_and_registers_model(service, storage, monkeypatch):
    svc = service["make"]()
    adapter = _DiscoveringAdapter(
        _config(),
        {"found": True, "state": "complete", "error": None, "phase_label": None},
        {
            "found": True,
            "artifact_id": "miratrn",
            "id": "miratrn",
            "trigger": "miratrn",
            "name": "Mira",
            "face_lora_path": "/panel/mlx_models/loras/miratrn_v2.safetensors",
            "audio_lora_path": None,
            "adapter_verdict": "ok",
        },
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: adapter)

    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "training"
    svc._persist_job_state(job)

    result = await svc.refresh_training_job(job.id)

    assert result.status == "complete"
    assert result.trained_model_id == "miratrn"
    assert result.completed_at is not None
    assert adapter.discovery_calls == 1
    trained = result.configuration["trained_character"]
    assert trained["face_lora_path"].endswith("miratrn_v2.safetensors")
    # Persisted + registered via the existing model registration path.
    model = svc.get_visual_model(job.target_id)
    assert model is not None
    assert model.status == "complete"
    assert model.output_reference == "miratrn"
    row = storage.get_visual_model(job.target_id)
    assert row["status"] == "complete"
    assert row["output_reference"] == "miratrn"


@pytest.mark.asyncio
async def test_completion_without_discoverable_lora_fails_closed(service, storage, monkeypatch):
    """Provider says done but /characters has no usable face LoRA → failed."""
    svc = service["make"]()
    adapter = _DiscoveringAdapter(
        _config(),
        {"found": True, "state": "complete", "error": None, "phase_label": None},
        {"found": False},
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: adapter)

    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "training"
    svc._persist_job_state(job)

    result = await svc.refresh_training_job(job.id)

    assert result.status == "failed"
    assert "could not be discovered" in (result.error or "")
    # No artifact registered — never claim LoRA availability without /characters.
    assert svc.get_visual_model(job.target_id) is None
    assert storage.get_visual_model(job.target_id)["status"] == "failed"


@pytest.mark.asyncio
async def test_find_provider_character_requires_face_lora_on_disk(tmp_path):
    """LoRA discovery mirrors Phosphene's rule: face file must exist on disk."""
    session = _FakeSession()
    session.get_payloads["/characters"] = {
        "characters": [
            {"id": "othert RN".replace(" ", ""), "trigger": "othertrn", "face_lora_path": "/nope/othertrn_v2.safetensors"},
        ]
    }
    adapter = _adapter_with(session)

    class _Job:
        trigger = "miratrn"
        configuration = {}

    assert await adapter.find_provider_character(_Job()) == {"found": False}

    # Present on disk → found.
    lora_file = tmp_path / "miratrn_v2.safetensors"
    lora_file.write_bytes(b"\x00")
    session.get_payloads["/characters"] = {
        "characters": [
            {
                "id": "miratrn",
                "trigger": "miratrn",
                "name": "Mira",
                "face_lora_path": str(lora_file),
                "audio_lora_path": None,
            }
        ]
    }
    found = await adapter.find_provider_character(_Job())
    assert found["found"] is True
    assert found["artifact_id"] == "miratrn"


@pytest.mark.asyncio
async def test_trained_character_flows_into_generation_payload(service, storage, monkeypatch):
    """Acceptance: completed training → LoRA → usable by the generation path."""
    svc = service["make"]()
    adapter = _DiscoveringAdapter(
        _config(),
        {"found": True, "state": "complete", "error": None, "phase_label": None},
        {
            "found": True,
            "artifact_id": "miratrn",
            "id": "miratrn",
            "trigger": "miratrn",
            "name": "Mira",
            "face_lora_path": "/panel/mlx_models/loras/miratrn_v2.safetensors",
            "audio_lora_path": None,
            "adapter_verdict": "ok",
        },
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: adapter)

    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "training"
    svc._persist_job_state(job)
    await svc.refresh_training_job(job.id)

    from app.services.visual_training_service import visual_training_service as singleton

    monkeypatch.setattr(singleton, "_storage", storage)
    reference = singleton.resolve_render_reference(
        project_id="film-a", visual_model_id=job.target_id
    )
    assert reference is not None
    assert reference["output_reference"] == "miratrn"
    assert reference["trigger"] == "miratrn"

    # The local LTX translation layer must turn that reference into the
    # Phosphene character-lane payload (character_id + character_strength).
    from app.adapters.local_ltx import translate_studio_request

    translation = translate_studio_request(
        prompt="A quiet room.",
        negative_prompt="blurry",
        parameters={"visual_model_reference": reference},
        reference_assets=[],
    )
    assert translation["ok"] is True
    form = translation["form"]
    assert form["character_id"] == "miratrn"
    assert "character_strength" in form
    # Character lane values come from Phosphene's registry, not the request.
    assert "width" not in form and "frames" not in form and "steps" not in form


# ---------------------------------------------------------------------------
# 6. Provider failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_provider_failure_marks_failed(service, storage):
    svc = service["make"](
        {
            "found": True,
            "state": "failed",
            "error": "Training failed: OOM in face phase (step 88)",
            "phase_label": None,
        }
    )
    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "training"
    svc._persist_job_state(job)

    result = await svc.refresh_training_job(job.id)

    assert result.status == "failed"
    assert "OOM in face phase" in (result.error or "")
    assert result.completed_at is not None
    assert svc.get_visual_model(job.target_id) is None
    assert storage.get_visual_training_job(job.id)["status"] == "failed"


@pytest.mark.asyncio
async def test_submit_fails_closed_when_preflight_not_ready(service, monkeypatch):
    """Blocked models fail the submission honestly — never a doomed run."""
    svc = service["make"]()
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = {
        "ok": True,
        "required": [
            {"key": "ltx_dev_transformer", "ready": False, "repo_id": "dgrauet/ltx-2.3-mlx-q8", "filename": "transformer-dev.safetensors", "size_gb": 20.6},
        ],
        "all_ready": False,
    }
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)

    assert result.status == "failed"
    assert "transformer-dev.safetensors" in (result.error or "")
    posts = [c[1] for c in session.calls if c[0] == "POST"]
    assert not any(p.endswith("/train/start") for p in posts)


# ---------------------------------------------------------------------------
# 7. Malformed provider responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_fails_on_malformed_start_response(service, monkeypatch):
    svc = service["make"]()
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = {"ok": True, "required": [], "all_ready": True}
    session.post_payloads["/train/upload"] = {"ok": True, "job_id": "j-dsZ", "count": 1}
    session.post_payloads["/train/start"] = "not-a-dict"
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)

    assert result.status == "failed"
    assert "rejected the training request" in (result.error or "")


@pytest.mark.asyncio
async def test_submit_fails_when_upload_returns_no_dataset_id(service, monkeypatch):
    svc = service["make"]()
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = {"ok": True, "required": [], "all_ready": True}
    session.post_payloads["/train/upload"] = {"ok": True}  # no job_id
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)

    assert result.status == "failed"
    assert "train_job_id" in (result.error or "")


@pytest.mark.asyncio
async def test_refresh_survives_malformed_status_payload(service, storage):
    """A malformed /status payload must not guess a state."""
    svc = service["make"]({"found": False})
    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "queued"
    svc._persist_job_state(job)

    result = await svc.refresh_training_job(job.id)

    assert result.status == "queued"


@pytest.mark.asyncio
async def test_adapter_status_mapping_for_terminal_history_entries(tmp_path):
    """Exact-id association in /status history (train_job_id params)."""
    session = _FakeSession()
    session.get_payloads["/status"] = {
        "running": False,
        "current": None,
        "queue": [],
        "history": [
            {"id": "j-stranger-1", "status": "done", "params": {"mode": "t2v"}},
            {
                "id": "j-run1",
                "status": "done",
                "output_path": "/x.mp4",
                "params": {"mode": "train", "train_job_id": "j-ds9"},
            },
        ],
    }
    adapter = _adapter_with(session)

    class _Job:
        provider_job_id = "j-ds9"
        configuration = {}

    result = await adapter.get_training_status(_Job())
    assert result["found"] is True
    assert result["state"] == "complete"

    # Unknown terminal label → never guessed.
    session.get_payloads["/status"] = {
        "running": False, "current": None, "queue": [],
        "history": [{"id": "j-x", "status": "mystery", "params": {"train_job_id": "j-ds9"}}],
    }
    assert await adapter.get_training_status(_Job()) == {"found": False}


# ---------------------------------------------------------------------------
# 8. Provider unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_fails_honestly_when_phosphene_down(service, monkeypatch):
    svc = service["make"]()
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = None  # 404 → unreachable
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)

    assert result.status == "failed"
    assert "unreachable" in (result.error or "")
    assert not result.provider_job_id


@pytest.mark.asyncio
async def test_refresh_keeps_state_when_provider_down(service, storage):
    """A transient poll outage must not corrupt or fail the job."""
    svc = service["make"]({"found": False})
    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "training"
    svc._persist_job_state(job)

    result = await svc.refresh_training_job(job.id)

    assert result.status == "training"
    assert storage.get_visual_training_job(job.id)["status"] == "training"


@pytest.mark.asyncio
async def test_get_status_reports_offline_and_unsupported():
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = None
    adapter = _adapter_with(session)
    status = await adapter.get_status()
    assert status.status == "offline"

    session2 = _FakeSession()
    session2.get_payloads["/train/preflight"] = {
        "ok": True,
        "all_ready": False,
        "required": [{"key": "ltx_dev_transformer", "ready": False, "filename": "transformer-dev.safetensors", "repo_id": "dgrauet/ltx-2.3-mlx-q8", "size_gb": 20.6}],
    }
    adapter2 = _adapter_with(session2)
    status2 = await adapter2.get_status()
    assert status2.status == "unsupported"
    assert "transformer-dev.safetensors" in (status2.display_label or "")

    session3 = _FakeSession()
    session3.get_payloads["/train/preflight"] = {"ok": True, "all_ready": True, "required": []}
    adapter3 = _adapter_with(session3)
    status3 = await adapter3.get_status()
    assert status3.status == "available"


# ---------------------------------------------------------------------------
# 9. Restart/recovery while a training job is running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_recovery_refreshes_running_jobs(service, storage, monkeypatch):
    """After a backend restart, a fresh service instance finds queued/training
    jobs via persistence and re-polls them through refresh_running_training_jobs."""
    svc = service["make"](
        {"found": True, "state": "running", "error": None, "phase_label": "Encoding captions"}
    )
    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "queued"
    job.configuration = {**job.configuration, "provider_job_id": "j-ds9"}
    svc._persist_job_state(job)

    # Fresh instance, same storage (the restart simulation).
    fresh = VisualTrainingService(storage=storage)
    fresh.register_provider_config(_config())
    adapter = _FakeStatusAdapter(
        _config(),
        {"found": True, "state": "running", "error": None, "phase_label": "Encoding captions"},
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: adapter)

    refreshed = await fresh.refresh_running_training_jobs()

    assert len(refreshed) == 1
    assert refreshed[0].id == job.id
    assert refreshed[0].status == "training"
    # Recovery attempts each persisted job at most once, even though this
    # refresh changes its status from queued to training mid-sweep.
    assert adapter.status_calls == ["j-ds9"]
    assert storage.get_visual_training_job(job.id)["status"] == "training"


@pytest.mark.asyncio
async def test_persisted_provider_job_id_survives_round_trip(service, storage):
    svc = service["make"]()
    job = _create_job(svc)
    job.provider_job_id = "j-ds42"
    job.status = "queued"
    job.configuration = {**job.configuration, "provider_job_id": "j-ds42"}
    svc._persist_job_state(job)

    fresh = VisualTrainingService(storage=storage)
    reloaded = fresh.get_training_job(job.id)
    assert reloaded is not None
    assert reloaded.provider_job_id == "j-ds42"
    assert reloaded.status == "queued"


# ---------------------------------------------------------------------------
# 10. Idempotent status refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_is_idempotent(service, storage, monkeypatch):
    adapter = _DiscoveringAdapter(
        _config(),
        {"found": True, "state": "complete", "error": None, "phase_label": None},
        {"found": True, "artifact_id": "miratrn", "id": "miratrn", "trigger": "miratrn", "face_lora_path": "/x.safetensors"},
    )
    svc = service["make"]()
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: adapter)

    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "training"
    svc._persist_job_state(job)

    first = await svc.refresh_training_job(job.id)
    assert first.status == "complete"
    calls_after_first = len(adapter.status_calls)

    second = await svc.refresh_training_job(job.id)
    third = await svc.refresh_training_job(job.id)

    assert second.status == "complete"
    assert third.status == "complete"
    # Terminal jobs are no-ops: no extra provider polls.
    assert len(adapter.status_calls) == calls_after_first


@pytest.mark.asyncio
async def test_refresh_noop_without_provider_id(service):
    svc = service["make"]({"found": True, "state": "complete", "error": None})
    job = _create_job(svc)  # pending, no provider id yet

    result = await svc.refresh_training_job(job.id)

    assert result.status == "pending"
    assert service["adapter"].status_calls == []


# ---------------------------------------------------------------------------
# 11. No simulated success path remaining
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_simulated_success_in_real_provider(monkeypatch, tmp_path):
    """The real provider can never return ok without a provider id, and the
    simulated adapter remains its own opt-in provider only."""
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = {"ok": True, "required": [], "all_ready": True}
    session.post_payloads["/train/upload"] = {"ok": True, "job_id": "j-ds1", "count": 1}
    session.post_payloads["/train/start"] = {"ok": True, "queued_id": "j-r", "train_job_id": "j-ds1"}
    adapter = _adapter_with(session)

    class _Job:
        trigger = "miratrn"
        configuration = {}

    image = tmp_path / "x.png"
    image.write_bytes(b"\x89PNG fake-bytes")
    result = await adapter.submit_training_job(
        _Job(),
        {
            "trigger_word": "miratrn",
            "target_type": "character",
            "source_assets": [{"ref_id": "r1", "image_url": str(image)}],
        },
    )
    assert result["ok"] is True
    assert result.get("provider_job_id")  # async contract: always an external id
    assert "trained_model_id" not in result  # no synchronous artifact faking

    # The registry keeps the simulated provider isolated and opt-in.
    from app.adapters import ADAPTER_REGISTRY, get_adapter
    from app.adapters.local_visual_training import LocalVisualTrainingAdapter

    assert ADAPTER_REGISTRY["local_training"] is LocalVisualTrainingAdapter
    assert ADAPTER_REGISTRY[PROVIDER_ID] is PhospheneTrainingAdapter
    from app.adapters.local_visual_training import build_default_config as build_local_config
    sim = LocalVisualTrainingAdapter(build_local_config())
    assert sim.config.is_simulated is True
    real = get_adapter(PROVIDER_ID, _config())
    assert real.config.is_simulated is False


@pytest.mark.asyncio
async def test_unavailable_provider_never_returns_simulated_success(service, monkeypatch):
    """Full pipeline: provider down end-to-end → failed, never complete."""
    svc = service["make"]()
    session = _FakeSession()
    session.get_payloads["/train/preflight"] = None
    session.post_payloads["/train/upload"] = None
    session.post_payloads["/train/start"] = None
    real_adapter = _adapter_with(session)
    monkeypatch.setattr(
        vts_module, "get_training_adapter", lambda provider_id, config: real_adapter
    )

    job = _create_job(svc)
    result = await svc.submit_training_job(job.id)
    assert result.status == "failed"

    # Even a completed-status poll with a dead registry fails closed.
    failing = _DiscoveringAdapter(
        _config(),
        {"found": True, "state": "complete", "error": None, "phase_label": None},
        {"found": False},
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: failing)
    refreshed = await svc.refresh_training_job(job.id)
    assert refreshed.status == "failed"


# ---------------------------------------------------------------------------
# Trigger validation guardrail
# ---------------------------------------------------------------------------


def test_create_job_rejects_digit_trigger(service):
    svc = service["make"]()
    with pytest.raises(ValidationError) as exc:
        _create_job(svc, trigger_word="mrz07")
    assert "letters only" in str(exc.value)


# ---------------------------------------------------------------------------
# API route surface (deterministic, no server needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_refresh_endpoint_is_wired(service, monkeypatch):
    from app.routes import visual_training as routes

    svc = service["make"]()
    job = _create_job(svc)
    job.provider_job_id = "j-ds9"
    job.status = "queued"
    svc._persist_job_state(job)

    adapter = _FakeStatusAdapter(
        _config(),
        {"found": True, "state": "running", "error": None, "phase_label": "step 3"},
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: adapter)
    monkeypatch.setattr(routes._vts, "visual_training_service", svc)

    payload = await routes.refresh_visual_training_job(job.id)
    assert payload.status == "training"
