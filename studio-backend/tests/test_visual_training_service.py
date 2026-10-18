"""Visual training service tests.

Covers the character/scene visual training lifecycle through the provider
boundary: job creation and validation, fail-closed provider handling, trained
artifact registration, persistence, project isolation, and the render-facing
visual model reference resolution.

These tests never touch a real provider. A fake VisualTrainingAdapter is
injected via monkeypatch so the tests exercise service + storage + boundary
without any network calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import app.services.visual_training_service as vts_module
from app.adapters import VisualTrainingAdapter
from app.adapters.local_visual_training import LocalVisualTrainingAdapter, build_default_config
from app.data.storage import DatabaseStorage, get_storage
from app.models import ProviderConfig
from app.services.stability import ValidationError
from app.services.visual_training_service import VisualTrainingService

# ── Fake training adapter ────────────────────────────────────────────────────

class FakeTrainingAdapter(VisualTrainingAdapter):
    """Records training calls and returns a configurable normalized result."""

    def __init__(self, config: ProviderConfig, result=None, raises: Exception | None = None):
        super().__init__(config)
        self.calls: list[dict] = []
        self.result = result if result is not None else {
            "ok": True,
            "configuration": {"trained": True},
            "trained_model_id": "artifact-abc123",
        }
        self.raises = raises
        self.cancelled = False

    async def submit_training_job(self, job, training_config):
        self.calls.append({"job": job, "training_config": training_config})
        if self.raises is not None:
            raise self.raises
        return dict(self.result)

    async def cancel_training_job(self, job):
        self.cancelled = True
        return True

    async def submit_job(self, job):
        return job

    async def get_job_status(self, job):
        return job

    async def cancel_job(self, job):
        return True

    async def fetch_outputs(self, job):
        return []

    async def get_status(self):
        from app.models import ProviderStatus

        return ProviderStatus(provider_id=self.provider_id, name="fake", status="available")


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _provider_config(provider_id: str = "fake-trainer") -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        name="Fake Trainer",
        enabled=True,
        is_simulated=False,
        api_key=None,
        api_endpoint="http://127.0.0.1:9/",
        requires=[],
        capabilities=["video_generation"],
        models=["fake-model-1"],
    )


def _save_asset(storage: DatabaseStorage, ref_id: str, project_id: str, kind: str = "character_face", approval_state: str | None = "approved") -> None:
    asset = {
        "ref_id": ref_id,
        "project_id": project_id,
        "kind": kind,
        "image_url": f"https://cdn.example.com/{ref_id}.png",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    if approval_state is not None:
        asset["approval_state"] = approval_state
    storage.save_reference_asset(asset)


@pytest.fixture
def storage(tmp_path: Path) -> DatabaseStorage:
    db = DatabaseStorage(str(tmp_path / "visual_training.db"))
    from app.models import StudioProject

    db.save_project(StudioProject(project_id="film-a", title="Film A"))
    db.save_project(StudioProject(project_id="film-b", title="Film B"))
    return db


@pytest.fixture
def adapter(monkeypatch) -> FakeTrainingAdapter:
    fake = FakeTrainingAdapter(_provider_config())
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: fake)
    return fake


@pytest.fixture
def service(storage, adapter) -> VisualTrainingService:
    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    return svc


def _create(service: VisualTrainingService, *, project_id: str = "film-a", target_type: str = "character", source_asset_ids=None, provider: str = "fake-trainer", provider_model: str = "fake-model-1", trigger_word: str = "mirastyle"):
    source_asset_ids = source_asset_ids or []
    source_assets = [
        {
            "ref_id": asset_id,
            "kind": "character_face" if target_type == "character" else "environment",
            "image_url": f"https://cdn.example.com/{asset_id}.png",
        }
        for asset_id in source_asset_ids
    ]
    return service.create_training_job(
        project_id=project_id,
        visual_model_id=None,
        target_type=target_type,
        trigger_word=trigger_word,
        source_asset_ids=source_asset_ids,
        provider=provider,
        provider_model=provider_model,
        configuration={"source_assets": source_assets},
    )


def _local_training_config() -> ProviderConfig:
    return build_default_config()


# ── Provider listing ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_training_providers_includes_local_training(service, storage, monkeypatch):
    from app.routes.visual_training import list_training_providers

    monkeypatch.setattr(vts_module, "visual_training_service", service)
    service.register_provider_config(_local_training_config())
    result = await list_training_providers()

    providers = result["providers"]
    local = [p for p in providers if p.provider_id == "local_training"]
    assert len(local) == 1
    assert local[0].name == "Local Visual Training"
    assert local[0].is_simulated is True
    assert "visual_training" in local[0].capabilities
    assert "local-visual-v1" in local[0].models


# ── Job creation and validation ──────────────────────────────────────────────

def test_create_character_training_job(service, storage):
    _save_asset(storage, "ref_char_1", "film-a")
    job = _create(service, target_type="character", source_asset_ids=["ref_char_1"])

    assert job.status == "pending"
    assert job.target_type == "character"
    assert job.provider_train_type == "character"
    assert job.target_id.startswith("vm_")
    assert job.source_asset_ids == ["ref_char_1"]

    model = storage.get_visual_model(job.target_id)
    assert model is not None
    assert model["status"] == "pending"
    assert model["training_id"] == job.id


def test_create_scene_training_job(service, storage):
    _save_asset(storage, "ref_scene_1", "film-a", kind="environment")
    job = _create(service, target_type="scene", source_asset_ids=["ref_scene_1"])

    assert job.target_type == "scene"
    assert job.provider_train_type == "style"
    assert job.target_id.startswith("vm_")


def test_create_training_job_rejects_unknown_source_asset(service, storage):
    _save_asset(storage, "ref_known", "film-a")

    with pytest.raises(ValidationError) as exc:
        _create(service, source_asset_ids=["ref_not_known"])

    assert "not a confirmed reference" in str(exc.value)


def test_create_training_job_rejects_candidate_source_asset(service, storage):
    _save_asset(storage, "ref_candidate", "film-a", approval_state="candidate")

    with pytest.raises(ValidationError) as exc:
        _create(service, source_asset_ids=["ref_candidate"])

    assert "not approved for training" in str(exc.value)


def test_create_training_job_rejects_rejected_source_asset(service, storage):
    _save_asset(storage, "ref_rejected", "film-a", approval_state="rejected")

    with pytest.raises(ValidationError) as exc:
        _create(service, source_asset_ids=["ref_rejected"])

    assert "not approved for training" in str(exc.value)


def test_create_training_job_rejects_source_asset_with_unknown_approval_state(service, storage):
    # Storage defaults an omitted approval_state to 'approved', so an
    # unrecognized explicit state plus a legacy NULL row cover 'unknown'.
    _save_asset(storage, "ref_pending", "film-a", approval_state="pending")
    with pytest.raises(ValidationError) as exc:
        _create(service, source_asset_ids=["ref_pending"])
    assert "not approved for training" in str(exc.value)


def test_create_training_job_rejects_foreign_project_source_asset(service, storage):
    _save_asset(storage, "ref_other_film", "film-b")

    with pytest.raises(ValidationError) as exc:
        _create(service, project_id="film-a", source_asset_ids=["ref_other_film"])

    assert "not a confirmed reference" in str(exc.value)


def test_create_scene_training_job_rejects_candidate_source_asset(service, storage):
    _save_asset(storage, "ref_env_candidate", "film-a", kind="environment", approval_state="candidate")

    with pytest.raises(ValidationError) as exc:
        _create(service, target_type="scene", source_asset_ids=["ref_env_candidate"])

    assert "not approved for training" in str(exc.value)


def test_create_training_job_rejects_invalid_target_type(service):
    with pytest.raises(ValidationError) as exc:
        _create(service, target_type="prop")

    assert "Invalid target_type" in str(exc.value)


def test_create_training_job_requires_configured_provider(service):
    with pytest.raises(ValidationError) as exc:
        _create(service, provider="unconfigured-provider")

    assert "not configured" in str(exc.value)


def test_create_training_job_requires_trigger_word(service):
    with pytest.raises(ValidationError) as exc:
        _create(service, trigger_word="   ")

    assert "trigger_word" in str(exc.value)


def test_create_training_job_unknown_project_fails(storage, service):
    with pytest.raises(ValidationError) as exc:
        _create(service, project_id="film-does-not-exist")

    assert "not found" in str(exc.value)


# ── Submission: success and fail-closed behavior ─────────────────────────────

@pytest.mark.asyncio
async def test_submit_training_job_local_adapter_registers_model(storage, monkeypatch):
    from app.adapters.local_visual_training import LocalVisualTrainingAdapter

    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: LocalVisualTrainingAdapter(config))
    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_local_training_config())
    _save_asset(storage, "ref_local", "film-a")
    job = _create(svc, provider="local_training", provider_model="local-visual-v1", source_asset_ids=["ref_local"])

    result = await svc.submit_training_job(job.id)

    assert result is not None
    assert result.status == "complete"
    assert result.trained_model_id == "local-vm-" + job.target_id
    assert result.configuration["simulated"] is True
    assert result.configuration["reference_count"] == 1

    model = svc.get_visual_model(job.target_id)
    assert model is not None
    assert model.status == "complete"
    assert model.output_reference == "local-vm-" + job.target_id
    assert model.configuration["simulated"] is True


@pytest.mark.asyncio
async def test_submit_training_job_success_registers_model(service, storage, adapter):
    _save_asset(storage, "ref_char_1", "film-a")
    job = _create(service, source_asset_ids=["ref_char_1"])

    result = await service.submit_training_job(job.id)

    assert result is not None
    assert result.status == "complete"
    # trained_model_id mirrors the artifact id returned by the provider adapter
    # (the FakeTrainingAdapter default result), exactly as the local adapter
    # test above asserts its own "local-vm-" convention.
    assert result.trained_model_id == "artifact-abc123"
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["training_config"]["target_type"] == "character"

    model = service.get_visual_model(job.target_id)
    assert model is not None
    assert model.status == "complete"
    assert model.output_reference == "artifact-abc123"
    assert model.provider == "fake-trainer"


@pytest.mark.asyncio
async def test_submit_training_job_provider_failure_fails_closed(storage, monkeypatch):
    fake = FakeTrainingAdapter(
        _provider_config(),
        result={"ok": False, "error": "provider rejected dataset"},
    )
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: fake)

    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    _save_asset(storage, "ref_char_1", "film-a")
    job = _create(svc, source_asset_ids=["ref_char_1"])

    result = await svc.submit_training_job(job.id)

    assert result is not None
    assert result.status == "failed"
    assert "provider rejected dataset" in (result.error or "")
    # No model may be registered on failure.
    assert svc.get_visual_model(job.target_id) is None
    assert storage.get_visual_model(job.target_id)["status"] == "failed"


@pytest.mark.asyncio
async def test_submit_training_job_exception_fails_closed(storage, monkeypatch):
    fake = FakeTrainingAdapter(_provider_config(), raises=RuntimeError("network down"))
    monkeypatch.setattr(vts_module, "get_training_adapter", lambda provider_id, config: fake)

    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    job = _create(svc)

    result = await svc.submit_training_job(job.id)

    assert result is not None
    assert result.status == "failed"
    assert "network down" in (result.error or "")
    assert svc.get_visual_model(job.target_id) is None


@pytest.mark.asyncio
async def test_submit_training_job_without_provider_config_fails_closed(storage):
    svc = VisualTrainingService(storage=storage)
    # Register the provider so creation passes, then drop the config before submit.
    svc.register_provider_config(_provider_config())
    job = _create(svc)
    svc._provider_configs.clear()

    result = await svc.submit_training_job(job.id)

    assert result is not None
    assert result.status == "failed"
    assert "not configured" in (result.error or "")


# ── Persistence, isolation, canonical truth ──────────────────────────────────

@pytest.mark.asyncio
async def test_job_state_round_trips_across_service_instances(storage, adapter):
    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    _save_asset(storage, "ref_char_1", "film-a")
    job = _create(svc, source_asset_ids=["ref_char_1"])
    await svc.submit_training_job(job.id)

    fresh = VisualTrainingService(storage=storage)
    loaded = fresh.get_training_job(job.id)

    assert loaded is not None
    assert loaded.id == job.id
    assert loaded.status == "complete"
    assert loaded.target_id == job.target_id
    assert loaded.source_asset_ids == ["ref_char_1"]


@pytest.mark.asyncio
async def test_visual_models_are_project_isolated(service, storage, adapter):
    _save_asset(storage, "ref_a", "film-a")
    job = _create(service, project_id="film-a", source_asset_ids=["ref_a"])
    await service.submit_training_job(job.id)

    assert service.list_visual_models(project_id="film-a", status="complete")
    assert service.list_visual_models(project_id="film-b", status="complete") == []

    with pytest.raises(ValidationError) as exc:
        service.resolve_render_reference(project_id="film-b", visual_model_id=job.target_id)
    assert "does not belong to project" in str(exc.value)


@pytest.mark.asyncio
async def test_training_does_not_mutate_canonical_story_memory(service, storage):
    from app.models import StudioProject

    storage.save_project(
        StudioProject(
            project_id="film-a",
            title="Film A",
            script_text="INT. KITCHEN - DAY\nMIRA waits.",
        )
    )
    before = storage.get_project("film-a")
    before_data = before.model_dump() if hasattr(before, "model_dump") else dict(before)

    _save_asset(storage, "ref_a", "film-a")
    job = _create(service, project_id="film-a", source_asset_ids=["ref_a"])
    await service.submit_training_job(job.id)

    after = storage.get_project("film-a")
    after_data = after.model_dump() if hasattr(after, "model_dump") else dict(after)

    assert after_data == before_data


# ── Cancellation ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_training_job_marks_cancelled(service, adapter):
    job = _create(service)

    ok = await service.cancel_training_job(job.id)

    assert ok is True
    assert adapter.cancelled is True
    reloaded = service.get_training_job(job.id)
    assert reloaded is not None
    assert reloaded.status == "cancelled"


# ── Render-facing reference resolution ───────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_render_reference_none_when_not_requested(service, adapter):
    assert service.resolve_render_reference(project_id="film-a") is None


@pytest.mark.asyncio
async def test_resolve_render_reference_returns_registered_model(service, storage, adapter):
    _save_asset(storage, "ref_a", "film-a")
    job = _create(service, source_asset_ids=["ref_a"])
    await service.submit_training_job(job.id)

    ref = service.resolve_render_reference(project_id="film-a", visual_model_id=job.target_id)

    assert ref is not None
    assert ref["model_id"] == job.target_id
    assert ref["output_reference"] == "artifact-abc123"
    assert ref["provider"] == "fake-trainer"
    assert ref["target_type"] == "character"


@pytest.mark.asyncio
async def test_resolve_render_reference_fails_closed_for_missing_model(service):
    with pytest.raises(ValidationError) as exc:
        service.resolve_render_reference(project_id="film-a", visual_model_id="vm_missing")

    assert "not registered or not complete" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_render_reference_fails_closed_for_pending_model(service):
    job = _create(service)

    with pytest.raises(ValidationError):
        service.resolve_render_reference(project_id="film-a", visual_model_id=job.target_id)


@pytest.mark.asyncio
async def test_resolve_render_reference_by_target(service, storage, adapter):
    _save_asset(storage, "ref_a", "film-a")
    job = _create(service, source_asset_ids=["ref_a"])
    await service.submit_training_job(job.id)

    ref = service.resolve_render_reference(
        project_id="film-a",
        target_type="character",
        target_id=job.target_id,
    )

    assert ref is not None
    assert ref["model_id"] == job.target_id


# ── RenderService integration: unchanged without a model, wired with one ─────

class _RecordingRenderAdapter:
    """Minimal render adapter that records the submitted job and completes."""

    def __init__(self, config):
        self.config = config
        self.provider_id = config.provider_id
        self.submitted = []

    async def submit_job(self, job):
        self.submitted.append(job)
        job.status = "queued"
        job.provider_job_id = "fake-provider-job"
        return job

    async def get_job_status(self, job):
        return job

    async def cancel_job(self, job):
        return True

    async def fetch_outputs(self, job):
        return []

    async def get_status(self):
        from app.models import ProviderStatus

        return ProviderStatus(provider_id=self.provider_id, name="fake", status="available")

    async def close(self):
        return None


def _render_env(monkeypatch):
    from app.services import render as render_module
    from app.services.render import RenderService

    service = RenderService()
    service._provider_configs["simulated"] = _provider_config("simulated")

    recorder = _RecordingRenderAdapter(service._provider_configs["simulated"])
    monkeypatch.setattr(render_module, "get_adapter", lambda provider_id, config: recorder)
    monkeypatch.setattr(render_module, "_storage", None)
    # The render boundary validates scene identity AND canonical setting
    # resolution before provider submission (fail-closed). These trigger/
    # reference tests therefore declare a valid setting context: the scene
    # carries a canonical setting_id and exactly one matching universe
    # location node exists in isolated test storage.
    setting_id = "test-setting-film-a-scene_001"
    monkeypatch.setattr(
        render_module.project_store,
        "get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_001", "setting_id": setting_id}]},
        },
    )
    storage = get_storage("sqlite")
    storage.save_universe_node({
        "node_id": setting_id,
        "project_id": "film-a",
        "node_type": "location",
        "name": "Test location",
        "first_scene": "scene_001",
        "last_scene": "scene_001",
    })
    storage.save_reference_asset({
        "ref_id": "test-env-anchor-film-a-scene_001",
        "project_id": "film-a",
        "target_type": "setting",
        "target_id": setting_id,
        "kind": "environment",
        "image_url": "https://example.com/test-setting-film-a-scene_001.png",
        "canonical": True,
        "approval_state": "approved",
        "source_kind": "confirmed",
    })
    monkeypatch.setattr(render_module, "_persist_job", lambda job: None)
    monkeypatch.setattr(render_module, "_log_audit", lambda *a, **k: None)
    monkeypatch.setattr(render_module, "_notify_update", AsyncMock())
    monkeypatch.setattr(render_module, "_run_render_quality_check", AsyncMock())
    monkeypatch.setattr(render_module, "_run_continuity_review", AsyncMock())
    monkeypatch.setattr(render_module, "_run_character_reference_lock", AsyncMock())
    monkeypatch.setattr(render_module, "_record_provider_failure_policy", lambda *a, **k: None)
    monkeypatch.setattr(render_module, "_record_failure_location", lambda *a, **k: None)
    monkeypatch.setattr(render_module, "_set_zero_touch_phase", lambda *a, **k: None)
    return service, recorder


@pytest.mark.asyncio
async def test_render_without_visual_model_is_unchanged(monkeypatch):
    service, recorder = _render_env(monkeypatch)
    job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
    )

    await service.submit_job(job.id)

    assert len(recorder.submitted) == 1
    assert "visual_model_reference" not in (recorder.submitted[0].input_payload.parameters or {})


@pytest.mark.asyncio
async def test_render_with_visual_model_passes_reference_to_provider(monkeypatch, storage, adapter):
    from app.services.visual_training_service import visual_training_service

    _save_asset(storage, "ref_a", "film-a")
    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    job = _create(svc, source_asset_ids=["ref_a"])
    await svc.submit_training_job(job.id)

    monkeypatch.setattr(visual_training_service, "_storage", storage)
    service, recorder = _render_env(monkeypatch)
    render_job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
        parameters={"visual_model_id": job.target_id},
    )

    await service.submit_job(render_job.id)

    submitted_params = recorder.submitted[0].input_payload.parameters
    reference = submitted_params.get("visual_model_reference")
    assert reference is not None
    assert reference["model_id"] == job.target_id
    assert reference["output_reference"] == "artifact-abc123"


@pytest.mark.asyncio
async def test_render_without_visual_model_leaves_prompt_unchanged(monkeypatch):
    service, recorder = _render_env(monkeypatch)
    job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
    )

    await service.submit_job(job.id)

    assert recorder.submitted[0].input_payload.prompt == "A quiet room."


@pytest.mark.asyncio
async def test_render_with_visual_model_folds_trigger_into_prompt(monkeypatch, storage, adapter):
    from app.services.visual_training_service import visual_training_service

    _save_asset(storage, "ref_a", "film-a")
    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    job = _create(svc, source_asset_ids=["ref_a"], trigger_word="mirastyle")
    await svc.submit_training_job(job.id)

    monkeypatch.setattr(visual_training_service, "_storage", storage)
    service, recorder = _render_env(monkeypatch)
    render_job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
        parameters={"visual_model_id": job.target_id},
    )

    await service.submit_job(render_job.id)

    prompt = recorder.submitted[0].input_payload.prompt
    # The trained identity is invoked by its trigger word, folded into the
    # prompt the provider renders from, while the creator's prompt is preserved.
    assert "mirastyle" in prompt
    assert "A quiet room." in prompt


@pytest.mark.asyncio
async def test_render_with_visual_model_does_not_duplicate_trigger_on_retry(monkeypatch, storage, adapter):
    from app.services.visual_training_service import visual_training_service

    _save_asset(storage, "ref_a", "film-a")
    svc = VisualTrainingService(storage=storage)
    svc.register_provider_config(_provider_config())
    job = _create(svc, source_asset_ids=["ref_a"], trigger_word="mirastyle")
    await svc.submit_training_job(job.id)

    monkeypatch.setattr(visual_training_service, "_storage", storage)
    service, recorder = _render_env(monkeypatch)
    render_job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
        parameters={"visual_model_id": job.target_id},
    )

    # First submission injects the trigger; a re-run of the resolution step on
    # the same job must not stack a second copy.
    await service.submit_job(render_job.id)
    submitted = recorder.submitted[0]
    from app.services.render import _apply_visual_model_reference

    _apply_visual_model_reference(submitted)

    assert submitted.input_payload.prompt.count("mirastyle") == 1


@pytest.mark.asyncio
async def test_render_fails_closed_when_requested_model_missing(monkeypatch, storage):
    from app.services.stability import ProviderError
    from app.services.visual_training_service import visual_training_service

    monkeypatch.setattr(visual_training_service, "_storage", storage)
    service, recorder = _render_env(monkeypatch)
    render_job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
        parameters={"visual_model_id": "vm_does_not_exist"},
    )

    with pytest.raises(ProviderError):
        await service.submit_job(render_job.id)

    # Fail closed: never submitted to the provider with an untrained model.
    assert recorder.submitted == []
    assert service._jobs[render_job.id].status == "failed"


# ── F5 regression: canonical-setting enforcement contract ────────────────
# The render boundary requires a resolvable canonical setting (scene
# setting_id + exactly one matching universe location node + approved
# canonical environment anchor) and fails closed otherwise. These tests pin
# both sides of that contract using isolated test storage.

@pytest.mark.asyncio
async def test_render_reaches_provider_with_valid_setting_context(monkeypatch):
    """A scene with full setting context passes the setting gate."""
    service, recorder = _render_env(monkeypatch)
    job = service.create_job(
        project_id="film-a",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="A quiet room.",
    )

    await service.submit_job(job.id)

    assert len(recorder.submitted) == 1
    assert service._jobs[job.id].status != "failed"


@pytest.mark.asyncio
async def test_render_fails_closed_when_setting_unresolvable(monkeypatch):
    """A scene with no setting context is blocked before provider submission."""
    from app.services import render as render_module
    from app.services.render import RenderService
    from app.services.stability import ValidationError

    service = RenderService()
    service._provider_configs["simulated"] = _provider_config("simulated")
    recorder = _RecordingRenderAdapter(service._provider_configs["simulated"])
    monkeypatch.setattr(render_module, "get_adapter", lambda provider_id, config: recorder)
    monkeypatch.setattr(render_module, "_storage", None)
    monkeypatch.setattr(
        render_module.project_store,
        "get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_009"}]},
        },
    )
    monkeypatch.setattr(render_module, "_persist_job", lambda job: None)
    job = service.create_job(
        project_id="film-a",
        shot_id="scene_009_shot_001",
        provider="simulated",
        prompt="A room with no setting.",
    )

    with pytest.raises(ValidationError, match="no resolvable canonical setting ID"):
        await service.submit_job(job.id)

    assert recorder.submitted == []
