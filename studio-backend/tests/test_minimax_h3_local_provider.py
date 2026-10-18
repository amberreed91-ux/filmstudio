"""MiniMax H3 local provider scaffold tests.

Covers registration, discovery, capability metadata, configuration,
capability-based hardware detection, status states, explicit selection,
and no-silent-fallback guarantees. All hardware/service probes are
mocked — these tests require no NVIDIA GPU, no model files, and no
Pinokio installation.
"""

from __future__ import annotations

import pytest

from app.adapters import (
    ADAPTER_REGISTRY,
    GenericVideoProviderAdapter,
    RunwayAdapter,
    SimulatedProviderAdapter,
    get_adapter,
)
from app.adapters.minimax_h3_local import (
    PROVIDER_ID,
    MinimaxH3LocalAdapter,
    build_default_config,
    detect_h3_runtime_support,
)
from app.models import ProviderConfig, RenderJobInput, RenderJobModel


def _config(*, enabled: bool = False) -> ProviderConfig:
    return ProviderConfig(
        provider_id=PROVIDER_ID,
        name="MiniMax H3 Local",
        enabled=enabled,
        is_simulated=False,
        api_key=None,
        api_endpoint="http://127.0.0.1:8188",
        requires=[],
        capabilities=["video_generation"],
    )


def _job() -> RenderJobModel:
    return RenderJobModel(
        id="job-h3-1",
        project_id="project-h3",
        shot_id="scene_001_shot_001",
        provider=PROVIDER_ID,
        status="pending",
        input_payload=RenderJobInput(
            shot_id="scene_001_shot_001",
            prompt="A quiet interior at dawn, dust in a shaft of light.",
            parameters={},
        ),
    )


async def _false() -> bool:
    return False


async def _true() -> bool:
    return True


# ---------------------------------------------------------------------------
# Registration & discovery
# ---------------------------------------------------------------------------


def test_h3_provider_is_registered() -> None:
    assert ADAPTER_REGISTRY[PROVIDER_ID] is MinimaxH3LocalAdapter


def test_get_adapter_returns_h3_adapter() -> None:
    adapter = get_adapter(PROVIDER_ID, _config(enabled=True))
    assert isinstance(adapter, MinimaxH3LocalAdapter)
    assert adapter.provider_id == PROVIDER_ID


def test_unknown_provider_still_raises_without_fallback() -> None:
    with pytest.raises(ValueError, match="Unknown provider adapter"):
        get_adapter("minimax_h3_video_vae", _config())


def test_vae_is_not_a_registered_provider() -> None:
    assert "minimax_h3_video_vae" not in ADAPTER_REGISTRY


def test_render_service_discovers_h3_provider() -> None:
    from app.services.render import RenderService

    service = RenderService()
    config = service.get_provider_config(PROVIDER_ID)
    assert config is not None
    assert config.provider_id == PROVIDER_ID
    assert config.name == "MiniMax H3 Local"
    # Disabled by default: existing Studio behavior is unchanged.
    assert config.enabled is False


def test_list_providers_includes_h3_without_breaking_others() -> None:
    from app.services.render import RenderService

    statuses = {s.provider_id: s for s in RenderService().list_providers()}
    assert PROVIDER_ID in statuses
    h3 = statuses[PROVIDER_ID]
    assert h3.enabled is False
    assert h3.status == "disabled"
    assert "MiniMax H3 Local" in h3.display_label
    # Pre-existing providers keep their contracts.
    for known in ("runway", "happyhorse", "simulated", "generic", "local"):
        assert known in statuses


# ---------------------------------------------------------------------------
# Capability metadata
# ---------------------------------------------------------------------------


def test_h3_capability_metadata_is_local_video_only() -> None:
    config = build_default_config()
    assert config.is_simulated is False
    assert config.requires == []
    assert config.capabilities == ["video_generation"]
    for unverified in ("audio_generation", "image_to_video", "reference_to_video", "lipsync"):
        assert unverified not in config.capabilities


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_default_config_is_disabled_with_local_endpoint() -> None:
    config = build_default_config(enabled=False)
    assert config.enabled is False
    assert (config.api_endpoint or "").startswith("http")


def test_config_honors_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_H3_LOCAL_ENABLED", "true")
    monkeypatch.setenv("MINIMAX_H3_LOCAL_URL", "http://192.168.1.10:8188")
    config = build_default_config()
    assert config.enabled is True
    assert config.api_endpoint == "http://192.168.1.10:8188"


def test_config_rejects_ambiguous_enable_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIMAX_H3_LOCAL_ENABLED", "yes-please")
    assert build_default_config().enabled is False


# ---------------------------------------------------------------------------
# Hardware / runtime detection (capability-based, mocked)
# ---------------------------------------------------------------------------


def test_detection_reports_shape() -> None:
    result = detect_h3_runtime_support()
    assert set(result) >= {"supported", "cuda_available", "reason"}
    assert isinstance(result["supported"], bool)
    assert isinstance(result["reason"], str) and result["reason"]


def test_detection_unsupported_without_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: False)
    result = detect_h3_runtime_support()
    assert result["supported"] is False
    assert result["cuda_available"] is False
    assert "CUDA" in result["reason"]


def test_detection_supported_with_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    result = detect_h3_runtime_support()
    assert result["supported"] is True
    assert result["cuda_available"] is True


def test_detection_is_capability_based_not_host_hardcoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same code path must be able to yield both states (no machine allowlist)."""
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: False)
    assert detect_h3_runtime_support()["supported"] is False
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    assert detect_h3_runtime_support()["supported"] is True


# ---------------------------------------------------------------------------
# Status states
# ---------------------------------------------------------------------------


async def test_status_disabled_by_default() -> None:
    status = await MinimaxH3LocalAdapter(_config(enabled=False)).get_status()
    assert status.provider_id == PROVIDER_ID
    assert status.status == "disabled"


async def test_status_unsupported_on_cuda_less_host(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: False)
    status = await MinimaxH3LocalAdapter(_config(enabled=True)).get_status()
    assert status.status == "unsupported"
    assert "cuda_runtime" in status.missing_requirements
    assert "CUDA" in (status.display_label or "")
    # No filesystem paths or secrets leak into UI-facing text.
    assert "/Users" not in (status.display_label or "")
    assert "safetensors" not in (status.display_label or "")


async def test_status_offline_when_service_down(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _false())
    status = await MinimaxH3LocalAdapter(_config(enabled=True)).get_status()
    assert status.status == "offline"
    assert "local_service" in status.missing_requirements


async def test_status_ready_when_service_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())
    status = await MinimaxH3LocalAdapter(_config(enabled=True)).get_status()
    assert status.status == "ready"


# ---------------------------------------------------------------------------
# Submission gating: fail closed, never pretend, never reroute
# ---------------------------------------------------------------------------


async def test_submit_fails_closed_when_disabled() -> None:
    job = await MinimaxH3LocalAdapter(_config(enabled=False)).submit_job(_job())
    assert job.status == "failed"
    assert job.provider == PROVIDER_ID
    assert "disabled" in (job.error_message or "").lower()
    assert not job.provider_job_id


async def test_submit_fails_closed_when_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: False)
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "failed"
    assert "CUDA" in (job.error_message or "")
    assert not job.provider_job_id


async def test_submit_requires_verified_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.delenv("MINIMAX_H3_WORKFLOW_PATH", raising=False)
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "failed"
    assert "MINIMAX_H3_WORKFLOW_PATH" in (job.error_message or "")


async def test_submit_fails_when_workflow_file_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured workflow path that does not exist fails closed."""
    import app.adapters.minimax_h3_local as h3_module

    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", "/tmp/does-not-exist-h3.json")
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "failed"
    assert "workflow" in (job.error_message or "").lower()
    assert not job.provider_job_id


async def test_cancel_without_prompt_id_is_safe_noop() -> None:
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    assert await adapter.cancel_job(_job()) is False
    assert await adapter.fetch_outputs(_job()) == []


async def test_fetch_outputs_preserves_asset_contract() -> None:
    from app.models import RenderJobOutput

    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.status = "complete"
    job.output_payload = RenderJobOutput(
        asset_url="http://127.0.0.1:8188/view?filename=h3_test.mp4",
        thumbnail_url=None,
        metadata={"workflow": "h3_t2v"},
    )
    job.completed_at = "2026-09-20T00:00:00Z"
    assets = await adapter.fetch_outputs(job)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.job_id == job.id
    assert asset.project_id == job.project_id
    assert asset.shot_id == job.shot_id
    assert asset.provider == PROVIDER_ID
    assert asset.asset_type == "video"


# ---------------------------------------------------------------------------
# Explicit selection & no silent substitution
# ---------------------------------------------------------------------------


def test_explicit_h3_selection_is_accepted() -> None:
    from app.services.render import RenderService

    job = RenderService().create_job(
        project_id="project-h3",
        shot_id="scene_001_shot_001",
        provider="minimax_h3_local",
        prompt="A quiet interior at dawn.",
    )
    assert job.provider == "minimax_h3_local"


def test_unknown_provider_still_rejected() -> None:
    from app.services.render import RenderService

    with pytest.raises(ValueError, match="Unknown provider"):
        RenderService().create_job(
            project_id="project-h3",
            shot_id="scene_001_shot_001",
            provider="minimax_h3_video_vae",
        )


# ---------------------------------------------------------------------------
# Existing behavior unaffected
# ---------------------------------------------------------------------------


def test_existing_registry_entries_unchanged() -> None:
    assert ADAPTER_REGISTRY["runway"] is RunwayAdapter
    assert ADAPTER_REGISTRY["simulated"] is SimulatedProviderAdapter
    assert ADAPTER_REGISTRY["generic"] is GenericVideoProviderAdapter
    # Presence-based guard (R4.5-Phase2 #20): every non-H3 entry is pinned by
    # name, so registry drift fails loudly instead of hiding behind a magic
    # count. 14 total keys → 13 besides minimax_h3_local itself.
    assert {k for k in ADAPTER_REGISTRY if k != PROVIDER_ID} == {
        "generic",
        "happyhorse",
        "happyhorse-r2v",
        "higgsfield",
        "local",
        "local_ltx",
        "local_training",
        "phosphene_training",
        "runway",
        "runway_direct",
        "runway_router",
        "simulated",
        "wan",
    }


def test_existing_comfyui_provider_untouched() -> None:
    from app.services.providers import comfyui_provider

    # Pure-function behavior only: _LAST_RENDER_ERROR is module-global state
    # that other tests legitimately mutate, so it is not asserted here.
    assert comfyui_provider.derive_deterministic_seed("scene_001", "shot_001", "a prompt") == (
        comfyui_provider.derive_deterministic_seed("scene_001", "shot_001", "a prompt")
    )
    assert comfyui_provider.detect_workflow_format({"nodes": [], "links": []}) == "ui"
    assert comfyui_provider.validate_comfyui_api_workflow({})["valid"] is False


# ---------------------------------------------------------------------------
# H3 dispatch: workflow validation, /prompt submission, /history polling
# ---------------------------------------------------------------------------


def _write_api_workflow(path, *, with_image_input: bool = True, fmt: str = "api") -> str:
    """Write a minimal API-format ComfyUI graph and return its path."""
    import json

    graph = {
        "30": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "authored placeholder", "clip": ["31", 0]},
        },
        "31": {"class_type": "CLIPLoader", "inputs": {"clip_name": "h3.safetensors"}},
        "32": {
            "class_type": "MiniMaxH3VideoSampler",
            "inputs": {"positive": ["30", 0], "negative": ["33", 0], "seed": 1},
        },
        "33": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "low quality, blurry", "clip": ["31", 0]},
        },
    }
    if with_image_input:
        graph["34"] = {
            "class_type": "LoadImage",
            "inputs": {"image": "authored_reference.png"},
        }
        graph["32"]["inputs"]["image"] = ["34", 0]
    graph["35"] = {
        "class_type": "SaveVideo",
        "inputs": {"video": ["32", 0], "filename_prefix": "h3"},
    }
    if fmt == "api":
        path.write_text(json.dumps(graph))
    else:
        path.write_text(json.dumps({"nodes": [], "links": [], "last_node_id": 1}))
    return str(path)


async def test_submit_dispatches_verified_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Verified workflow + reachable service → /prompt POST, queued, prompt_id set."""
    import app.adapters.minimax_h3_local as h3_module

    workflow_path = _write_api_workflow(tmp_path / "h3-api.json")
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", workflow_path)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())

    submitted: list[tuple[str, dict]] = []

    async def fake_post(self, path, payload):
        submitted.append((path, payload))
        return True, {"prompt_id": "h3-prompt-123"}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_post_json", fake_post)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = await adapter.submit_job(_job())

    assert job.status == "queued"
    assert job.provider_job_id == "h3-prompt-123"
    assert not job.error_message
    path, payload = submitted[0]
    assert path == "/prompt"
    graph = payload["prompt"]
    # The shot prompt replaces the graph author's text in the positive node.
    assert graph["30"]["inputs"]["text"] == "A quiet interior at dawn, dust in a shaft of light."
    # The negative node keeps its authored negative text.
    assert graph["33"]["inputs"]["text"] == "low quality, blurry"
    assert job.metadata["minimax_h3_local"]["prompt_id"] == "h3-prompt-123"


async def test_submit_rejects_ui_format_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """UI-format graphs (the bundled Pinokio exports) fail closed."""
    import app.adapters.minimax_h3_local as h3_module

    workflow_path = _write_api_workflow(tmp_path / "h3-ui.json", fmt="ui")
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", workflow_path)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())

    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "failed"
    assert "API-format" in (job.error_message or "")
    assert not job.provider_job_id


async def test_submit_wraps_full_api_export(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Full API exports (graph nested under 'prompt') submit the inner graph."""
    import json

    import app.adapters.minimax_h3_local as h3_module

    workflow_file = tmp_path / "h3-export.json"
    bare = tmp_path / "bare.json"
    _write_api_workflow(bare, with_image_input=False)
    graph = json.loads(bare.read_text())
    workflow_file.write_text(json.dumps({"prompt": graph}))
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", str(workflow_file))
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())

    captured: dict = {}

    async def fake_post(self, path, payload):
        captured.update(payload)
        return True, {"prompt_id": "h3-prompt-456"}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_post_json", fake_post)
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "queued"
    assert "30" in captured["prompt"]


async def test_submit_fails_when_comfyui_rejects_graph(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """/prompt validation errors surface as failures with the node detail."""
    import app.adapters.minimax_h3_local as h3_module

    workflow_path = _write_api_workflow(tmp_path / "h3-api.json")
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", workflow_path)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())

    async def fake_post(self, path, payload):
        return False, {"node_errors": {"32": {"errors": ["missing weight"]}}}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_post_json", fake_post)
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "failed"
    assert "/prompt" in (job.error_message or "")
    assert not job.provider_job_id


async def test_submit_requires_reachable_service_before_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """No dispatch (no /prompt POST) when the service is unreachable."""
    import app.adapters.minimax_h3_local as h3_module

    workflow_path = _write_api_workflow(tmp_path / "h3-api.json")
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", workflow_path)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _false())

    posted = []

    async def fake_post(self, path, payload):
        posted.append(path)
        return True, {"prompt_id": "x"}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_post_json", fake_post)
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(_job())
    assert job.status == "failed"
    assert posted == []


async def test_submit_fails_closed_on_reference_upload_failure(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A reference the local service cannot accept fails the job — never a
    silent text-only substitution."""
    import app.adapters.minimax_h3_local as h3_module

    workflow_path = _write_api_workflow(tmp_path / "h3-api.json")
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", workflow_path)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_upload_reference", lambda self, ref: _none())

    job = _job()
    job.input_payload.referenceAssets = ["/outputs/references/maya-face.png"]
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(job)
    assert job.status == "failed"
    assert "reference upload" in (job.error_message or "")


async def _none():
    return None


async def test_submit_with_reference_patches_image_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Uploaded reference name lands in every string image input."""
    import app.adapters.minimax_h3_local as h3_module

    workflow_path = _write_api_workflow(tmp_path / "h3-api.json")
    monkeypatch.setattr(h3_module, "_cuda_available", lambda: True)
    monkeypatch.setenv("MINIMAX_H3_WORKFLOW_PATH", workflow_path)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_probe_service", lambda self: _true())

    async def fake_upload(self, reference):
        return "studio/maya-face.png"

    captured: dict = {}

    async def fake_post(self, path, payload):
        captured.update(payload)
        return True, {"prompt_id": "h3-prompt-789"}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_upload_reference", fake_upload)
    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_post_json", fake_post)

    job = _job()
    job.input_payload.referenceAssets = ["/outputs/references/maya-face.png"]
    job = await MinimaxH3LocalAdapter(_config(enabled=True)).submit_job(job)
    assert job.status == "queued"
    assert captured["prompt"]["34"]["inputs"]["image"] == "studio/maya-face.png"
    assert job.metadata["minimax_h3_local"]["with_reference"] is True


async def test_poll_maps_running_and_pending_queue_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    async def fake_get(self, path, *, timeout):
        if path == "/queue":
            return {
                "queue_running": [{"prompt_id": "other-run"}],
                "queue_pending": [{"prompt_id": "h3-prompt-1"}],
            }
        return {}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_get_json", fake_get)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.provider_job_id = "h3-prompt-1"
    job.status = "queued"
    job = await adapter.get_job_status(job)
    assert job.status == "queued"

    job2 = _job()
    job2.provider_job_id = "h3-prompt-2"
    job2.input_payload.prompt = "p2"

    async def fake_get_running(self, path, *, timeout):
        if path == "/queue":
            return {"queue_running": [{"prompt_id": "h3-prompt-2"}], "queue_pending": []}
        return {}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_get_json", fake_get_running)
    job2 = await adapter.get_job_status(job2)
    assert job2.status == "rendering"


async def test_poll_maps_history_outputs_to_view_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    async def fake_get(self, path, *, timeout):
        if path.startswith("/history/"):
            return {
                "h3-prompt-9": {
                    "status": {"status_str": "success"},
                    "outputs": {
                        "35": {
                            "videos": [
                                {"filename": "h3_00001.mp4", "subfolder": "", "type": "output"}
                            ]
                        }
                    },
                }
            }
        return {}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_get_json", fake_get)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.provider_job_id = "h3-prompt-9"
    job.status = "rendering"
    job = await adapter.get_job_status(job)
    assert job.status == "complete"
    assert job.output_payload.asset_url == "http://127.0.0.1:8188/view?filename=h3_00001.mp4&subfolder=&type=output"
    assert job.output_payload.metadata["comfyui_prompt_id"] == "h3-prompt-9"


async def test_poll_marks_failed_on_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    async def fake_get(self, path, *, timeout):
        if path.startswith("/history/"):
            return {
                "h3-prompt-err": {
                    "status": {"status_str": "error", "messages": [["execution_error", {"node_type": "MiniMaxH3VideoSampler"}]]},
                    "outputs": {},
                }
            }
        return {}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_get_json", fake_get)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.provider_job_id = "h3-prompt-err"
    job.status = "rendering"
    job = await adapter.get_job_status(job)
    assert job.status == "failed"
    assert "execution error" in (job.error_message or "")


async def test_poll_never_touches_stranger_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """History/queue entries for other prompt_ids leave the job untouched."""
    import app.adapters.minimax_h3_local as h3_module

    async def fake_get(self, path, *, timeout):
        if path == "/queue":
            return {"queue_running": [{"prompt_id": "someone-else"}], "queue_pending": []}
        if path.startswith("/history/"):
            return {"someone-else": {"status": {"status_str": "success"}, "outputs": {}}}
        return {}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_get_json", fake_get)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.provider_job_id = "h3-prompt-mine"
    job.status = "rendering"
    job = await adapter.get_job_status(job)
    assert job.status == "rendering"
    assert not job.output_payload


async def test_poll_unreachable_service_leaves_job_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    async def fake_get(self, path, *, timeout):
        return None

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_get_json", fake_get)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.provider_job_id = "h3-prompt-1"
    job.status = "rendering"
    job = await adapter.get_job_status(job)
    assert job.status == "rendering"


async def test_cancel_interrupts_own_prompt_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.adapters.minimax_h3_local as h3_module

    calls: list[tuple[str, dict]] = []

    async def fake_post(self, path, payload):
        calls.append((path, payload))
        return True, {}

    monkeypatch.setattr(MinimaxH3LocalAdapter, "_api_post_json", fake_post)
    adapter = MinimaxH3LocalAdapter(_config(enabled=True))
    job = _job()
    job.provider_job_id = "h3-prompt-1"
    assert await adapter.cancel_job(job) is True
    assert calls == [("/interrupt", {"prompt_id": "h3-prompt-1"})]
    # No prompt_id → no interrupt call at all.
    assert await adapter.cancel_job(_job()) is False
    assert len(calls) == 1


def test_load_h3_workflow_rejects_garbage(tmp_path) -> None:
    from app.adapters.minimax_h3_local import load_h3_workflow

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json")
    missing = tmp_path / "missing.json"
    ui = tmp_path / "ui.json"
    ui.write_text('{"nodes": [], "links": []}')
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    invalid_api = tmp_path / "invalid.json"
    invalid_api.write_text('{"1": "not-a-node"}')

    assert load_h3_workflow("") is None
    assert load_h3_workflow(str(missing)) is None
    assert load_h3_workflow(str(bad_json)) is None
    assert load_h3_workflow(str(ui)) is None
    assert load_h3_workflow(str(empty)) is None
    assert load_h3_workflow(str(invalid_api)) is None
    good = tmp_path / "good.json"
    _write_api_workflow(good)
    assert load_h3_workflow(str(good)) is not None
