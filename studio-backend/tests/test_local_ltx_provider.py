"""Local LTX (Phosphene) provider tests.

All Phosphene HTTP traffic is faked — no panel, model, or Pinokio needed.
Covers registration, discovery, config, health states, request
translation, job lifecycle with exact-id association, i2v upload,
cancellation safety, capability gating, explicit selection, no-fallback,
and existing-provider isolation.
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
from app.adapters.local_ltx import (
    PROVIDER_ID,
    LocalLTXAdapter,
    build_default_config,
    translate_studio_request,
)
from app.models import ProviderConfig, RenderJobInput, RenderJobModel


# ---------------------------------------------------------------------------
# Fakes
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


class _FakeSession:
    """Records (method, url, data) and serves canned payloads."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.get_payloads: dict[str, object] = {}
        self.post_payloads: dict[str, object] = {}
        self.default_status = 200

    def _respond(self, table: dict, url: str):
        for prefix, payload in table.items():
            if url.endswith(prefix):
                status = self.default_status
                if isinstance(payload, tuple):
                    payload, status = payload
                return _FakeResponse(payload, status)
        return _FakeResponse({"error": "not found"}, 404)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, None))
        return self._respond(self.get_payloads, url)

    def post(self, url, **kwargs):
        data = kwargs.get("data")
        self.calls.append(("POST", url, data))
        return self._respond(self.post_payloads, url)


def _config(*, enabled: bool = False) -> ProviderConfig:
    return ProviderConfig(
        provider_id=PROVIDER_ID,
        name="Local LTX",
        enabled=enabled,
        is_simulated=False,
        api_key=None,
        api_endpoint="http://127.0.0.1:8198",
        requires=[],
        capabilities=["video_generation", "image_to_video"],
        models=["ltx-2.5-mlx-q4"],
    )


def _job(**overrides) -> RenderJobModel:
    payload = RenderJobInput(
        shot_id="scene_001_shot_001",
        prompt="A quiet interior at dawn, dust in a shaft of light.",
        negative_prompt="blurry",
        referenceAssets=[],
        parameters={},
    )
    for key, value in overrides.get("payload", {}).items():
        setattr(payload, key, value)
    return RenderJobModel(
        id="job-ltx-1",
        project_id="project-ltx",
        shot_id="scene_001_shot_001",
        provider=PROVIDER_ID,
        status="pending",
        input_payload=payload,
    )


def _adapter_with(session: _FakeSession, *, enabled: bool = True) -> LocalLTXAdapter:
    adapter = LocalLTXAdapter(_config(enabled=enabled))

    async def _session():
        return session

    adapter._get_session = _session  # type: ignore[method-assign]
    return adapter


def _status_state(*, current=None, queue=None, history=None) -> dict:
    return {
        "running": current is not None,
        "paused": False,
        "current": current,
        "queue": queue or [],
        "history": history or [],
    }


def _history_entry(job_id: str, status: str, **extra) -> dict:
    entry = {"id": job_id, "status": status, "elapsed_sec": 61.0, "error": None}
    entry.update(extra)
    return entry


# ---------------------------------------------------------------------------
# 1-3. Registration, discovery, configuration
# ---------------------------------------------------------------------------


def test_provider_is_registered() -> None:
    assert ADAPTER_REGISTRY[PROVIDER_ID] is LocalLTXAdapter


def test_get_adapter_returns_ltx_adapter() -> None:
    adapter = get_adapter(PROVIDER_ID, _config(enabled=True))
    assert isinstance(adapter, LocalLTXAdapter)
    assert adapter.provider_id == PROVIDER_ID


def test_render_service_discovers_ltx_disabled_by_default() -> None:
    from app.services.render import RenderService

    service = RenderService()
    config = service.get_provider_config(PROVIDER_ID)
    assert config is not None
    assert config.provider_id == PROVIDER_ID
    assert config.enabled is False
    assert config.models == ["ltx-2.5-mlx-q4"]


def test_list_providers_includes_ltx_as_disabled() -> None:
    from app.services.render import RenderService

    statuses = {s.provider_id: s for s in RenderService().list_providers()}
    ltx = statuses[PROVIDER_ID]
    assert ltx.enabled is False
    assert ltx.status == "disabled"
    assert "Local LTX" in ltx.display_label
    assert ltx.ready_for_hosted_generation is False


def test_default_config_env_conventions(monkeypatch: pytest.MonkeyPatch) -> None:
    config = build_default_config(enabled=False)
    assert config.enabled is False
    assert config.api_endpoint == "http://127.0.0.1:8198"
    assert config.requires == []
    assert config.capabilities == ["video_generation", "image_to_video"]

    monkeypatch.setenv("LOCAL_LTX_ENABLED", "true")
    monkeypatch.setenv("LOCAL_LTX_URL", "http://127.0.0.1:8199")
    monkeypatch.setenv("LOCAL_LTX_MODEL", "ltx-2.5-mlx-q4-test")
    config = build_default_config()
    assert config.enabled is True
    assert config.api_endpoint == "http://127.0.0.1:8199"
    assert config.models == ["ltx-2.5-mlx-q4-test"]


def test_only_verified_capabilities_advertised() -> None:
    config = build_default_config()
    for unverified in ("audio_generation", "keyframe", "extend", "high_quality", "q8"):
        assert unverified not in config.capabilities


# ---------------------------------------------------------------------------
# 4-6. Health states
# ---------------------------------------------------------------------------


async def test_status_disabled() -> None:
    session = _FakeSession()
    status = await _adapter_with(session, enabled=False).get_status()
    assert status.provider_id == PROVIDER_ID
    assert status.status == "disabled"
    assert session.calls == []


async def test_status_offline_when_unreachable() -> None:
    session = _FakeSession()  # no canned payloads → 404 → unreachable
    status = await _adapter_with(session).get_status()
    assert status.status == "offline"
    assert "local_service" in status.missing_requirements


async def test_status_unsupported_when_model_incomplete() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.get_payloads["/models"] = {
        "repos": [{"key": "q4_25", "complete": False, "missing_files": ["a"]}]
    }
    status = await _adapter_with(session).get_status()
    assert status.status == "unsupported"
    assert "ltx_model" in status.missing_requirements
    label = status.display_label or ""
    assert "/Users" not in label and "safetensors" not in label


async def test_status_ready_when_pack_complete() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.get_payloads["/models"] = {
        "repos": [{"key": "q4_25", "complete": True, "missing_files": []}]
    }
    status = await _adapter_with(session).get_status()
    assert status.status == "ready"


# ---------------------------------------------------------------------------
# 7-8. Request translation + form encoding
# ---------------------------------------------------------------------------


def test_translation_defaults_match_verified_envelope() -> None:
    result = translate_studio_request("A lighthouse at dusk.")
    assert result["ok"] is True
    form = result["form"]
    assert form == {
        "mode": "t2v",
        "prompt": "A lighthouse at dusk.",
        "negative_prompt": "",
        "width": "768",
        "height": "448",
        "frames": "121",
        "quality": "balanced",
        "steps": "8",
        "seed": "-1",
        "enhance": "false",
        "engine": "ltx",
    }
    assert result["wants_i2v"] is False


def test_translation_never_sends_h3_engine() -> None:
    result = translate_studio_request(
        "A lighthouse.", parameters={"engine": "h3", "quality": "high", "frames": 999}
    )
    # h3 engine is dropped; invalid quality still fails (not coerced).
    assert result["ok"] is False


def test_translation_accepts_explicit_valid_fields() -> None:
    result = translate_studio_request(
        "A market.",
        negative_prompt="watermark",
        parameters={
            "quality": "standard",
            "width": 704,
            "height": 448,
            "frames": 169,
            "steps": 10,
            "seed": 42,
        },
    )
    assert result["ok"] is True
    assert result["form"]["quality"] == "standard"
    assert result["form"]["frames"] == "169"
    assert result["form"]["seed"] == "42"
    assert result["form"]["negative_prompt"] == "watermark"


def test_translation_maps_verified_durations() -> None:
    assert translate_studio_request("x", parameters={"duration_seconds": 7})["form"]["frames"] == "169"


# ---------------------------------------------------------------------------
# 9-11. Job creation, phosphene id, polling
# ---------------------------------------------------------------------------


async def test_submit_t2v_posts_form_and_tracks_id() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.post_payloads["/queue/add"] = {"ok": True, "id": "j-abc123"}
    job = await _adapter_with(session).submit_job(_job())
    assert job.status == "queued"
    assert job.provider_job_id == "j-abc123"
    assert job.provider == PROVIDER_ID
    assert job.error_message is None
    posts = [c for c in session.calls if c[0] == "POST"]
    assert len(posts) == 1
    method, url, data = posts[0]
    assert url == "http://127.0.0.1:8198/queue/add"
    assert isinstance(data, dict)  # form-encoded (not JSON)
    assert data["mode"] == "t2v" and data["engine"] == "ltx"


async def test_submit_fails_when_disabled() -> None:
    session = _FakeSession()
    job = await _adapter_with(session, enabled=False).submit_job(_job())
    assert job.status == "failed"
    assert "disabled" in (job.error_message or "").lower()
    assert not job.provider_job_id
    assert session.calls == []


async def test_submit_fails_when_offline() -> None:
    session = _FakeSession()
    job = await _adapter_with(session).submit_job(_job())
    assert job.status == "failed"
    assert "unreachable" in (job.error_message or "").lower()
    assert not job.provider_job_id


async def test_submit_fails_on_rejection_without_id() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.post_payloads["/queue/add"] = ({"error": "bad prompt"}, 400)
    job = await _adapter_with(session).submit_job(_job())
    assert job.status == "failed"
    assert not job.provider_job_id


async def test_polling_queued_then_rendering() -> None:
    session = _FakeSession()
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-1"
    session.get_payloads["/status"] = _status_state(
        queue=[{"id": "j-1", "status": "queued", "params": {}}]
    )
    job = await adapter.get_job_status(job)
    assert job.status == "queued"
    session.get_payloads["/status"] = _status_state(
        current={"id": "j-1", "status": "running", "progress": {"pct": 41}}
    )
    job = await adapter.get_job_status(job)
    assert job.status == "rendering"
    assert job.progress == 41


# ---------------------------------------------------------------------------
# 12. Exact-id association (never map a stranger job)
# ---------------------------------------------------------------------------


async def test_status_ignores_unrelated_jobs() -> None:
    session = _FakeSession()
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-mine"
    job.status = "queued"
    session.get_payloads["/status"] = _status_state(
        current={"id": "j-stranger", "status": "running", "progress": {"pct": 90}},
        history=[_history_entry("j-other", "done", output_path="/x/out.mp4")],
    )
    job = await adapter.get_job_status(job)
    assert job.status == "queued"  # untouched
    assert job.provider_job_id == "j-mine"
    assert job.output_payload is None


# ---------------------------------------------------------------------------
# 13-18. Terminal states + retrieval + RenderAsset
# ---------------------------------------------------------------------------


async def test_completed_output_builds_file_url() -> None:
    session = _FakeSession()
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-9"
    session.get_payloads["/status"] = _status_state(
        history=[_history_entry("j-9", "done", output_path="/o/clip.mp4", elapsed_sec=120.0)]
    )
    job = await adapter.get_job_status(job)
    assert job.status == "complete"
    assert job.output_payload is not None
    assert job.output_payload.asset_url == (
        "http://127.0.0.1:8198/file?path=%2Fo%2Fclip.mp4"
    )
    assert job.output_payload.metadata["phosphene_job_id"] == "j-9"


async def test_done_without_output_fails() -> None:
    session = _FakeSession()
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-9"
    session.get_payloads["/status"] = _status_state(
        history=[_history_entry("j-9", "done", output_path="")]
    )
    job = await adapter.get_job_status(job)
    assert job.status == "failed"


async def test_failed_error_cancelled_stopped_mapping() -> None:
    session = _FakeSession()
    adapter = _adapter_with(session)
    cases = [
        ("failed", "failed", "boom"),
        ("error", "failed", "kaput"),
        ("cancelled", "cancelled", None),
        ("stopped", "cancelled", None),
    ]
    for remote, local, err in cases:
        job = _job()
        job.provider_job_id = "j-x"
        session.get_payloads["/status"] = _status_state(
            history=[_history_entry("j-x", remote, error=err)]
        )
        job = await adapter.get_job_status(job)
        assert job.status == local, remote


async def test_fetch_outputs_preserves_associations() -> None:
    from app.models import RenderJobOutput

    adapter = _adapter_with(_FakeSession())
    job = _job()
    job.status = "complete"
    job.completed_at = "2026-09-20T00:00:00Z"
    job.output_payload = RenderJobOutput(
        asset_url="http://127.0.0.1:8198/file?path=%2Fo%2Fclip.mp4",
        metadata={"phosphene_job_id": "j-9"},
    )
    assets = await adapter.fetch_outputs(job)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.job_id == job.id
    assert asset.project_id == "project-ltx"
    assert asset.shot_id == "scene_001_shot_001"
    assert asset.provider == PROVIDER_ID
    assert asset.asset_type == "video"


async def test_fetch_outputs_empty_unless_complete() -> None:
    adapter = _adapter_with(_FakeSession())
    assert await adapter.fetch_outputs(_job()) == []


# ---------------------------------------------------------------------------
# 22-24. I2V upload workflow
# ---------------------------------------------------------------------------


async def test_i2v_uploads_bytes_and_uses_panel_path(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.post_payloads["/queue/add"] = {"ok": True, "id": "j-i2v"}

    seen: dict = {}

    async def fake_upload(self, reference: str):
        seen["reference"] = reference
        return "/panel/mlx_outputs/uploads/1_still.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    adapter = _adapter_with(session)
    job = _job(payload={"referenceAssets": ["https://example.com/still.png"]})
    job = await adapter.submit_job(job)
    assert job.status == "queued"
    assert job.provider_job_id == "j-i2v"
    assert seen["reference"] == "https://example.com/still.png"
    posts = [c for c in session.calls if c[0] == "POST"]
    assert posts[0][2]["mode"] == "i2v"
    # Studio path never sent: only the panel-side opaque path.
    assert posts[0][2]["image"] == "/panel/mlx_outputs/uploads/1_still.png"
    assert "example.com" not in posts[0][2]["image"]


async def test_i2v_sends_only_first_uploadable_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider capacity boundary: Phosphene i2v takes exactly ONE image.

    Studio may select many references; only the first uploadable one may be
    uploaded and sent. The extras are never transmitted and the job metadata
    records that honestly (local_ltx_reference_trace) instead of implying the
    provider consumed them.
    """
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.post_payloads["/queue/add"] = {"ok": True, "id": "j-i2v-multi"}

    uploaded: list[str] = []

    async def fake_upload(self, reference: str):
        uploaded.append(reference)
        return f"/panel/uploads/{len(uploaded)}.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    adapter = _adapter_with(session)
    refs = [
        "https://example.com/face.png",
        "https://example.com/wardrobe.png",
        "https://example.com/location.png",
    ]
    job = await adapter.submit_job(_job(payload={"referenceAssets": refs}))
    assert job.status == "queued"
    # Exactly one upload: the strongest (first) reference. Refs 2..N never
    # cross the Studio→Phosphene boundary.
    assert uploaded == [refs[0]]
    posts = [c for c in session.calls if c[0] == "POST"]
    form = posts[0][2]
    assert form["mode"] == "i2v"
    assert form["image"] == "/panel/uploads/1.png"
    assert all(r not in form["image"] for r in refs[1:])
    trace = (job.metadata or {}).get("local_ltx_reference_trace")
    assert trace["selected_count"] == 3
    assert trace["uploaded"] == refs[0]
    assert trace["not_consumed_count"] == 2
    assert trace["provider_capacity"] == 1
    assert trace["uploaded_reference_id"] is None  # legacy URL-only caller has no ID carrier
    assert trace["provider_image_path"] == "/panel/uploads/1.png"


async def test_i2v_next_candidate_used_when_first_upload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ordered fallback WITHIN the upload loop: a dead first reference does
    not fail the job — the next selected candidate is tried, still ending at
    exactly one image on the wire."""
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.post_payloads["/queue/add"] = {"ok": True, "id": "j-i2v-skip"}

    async def fake_upload(self, reference: str):
        return None if reference.endswith("dead.png") else "/panel/uploads/ok.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    job = await _adapter_with(session).submit_job(
        _job(
            payload={
                "referenceAssets": [
                    "https://example.com/dead.png",
                    "https://example.com/live.png",
                ]
            }
        )
    )
    assert job.status == "queued"
    posts = [c for c in session.calls if c[0] == "POST"]
    assert posts[0][2]["image"] == "/panel/uploads/ok.png"
    trace = (job.metadata or {}).get("local_ltx_reference_trace")
    assert trace["uploaded"] == "https://example.com/live.png"
    assert trace["selected_count"] == 2
    assert trace["not_consumed_count"] == 1


async def test_i2v_upload_failure_fails_without_t2v_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()

    async def fake_upload(self, reference: str):
        return None

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    job = await _adapter_with(session).submit_job(
        _job(payload={"referenceAssets": ["https://example.com/still.png"]})
    )
    assert job.status == "failed"
    assert "upload" in (job.error_message or "").lower()
    assert not job.provider_job_id
    assert not [c for c in session.calls if c[0] == "POST"]


# ---------------------------------------------------------------------------
# 25-26. Cancellation safety
# ---------------------------------------------------------------------------


async def test_cancel_queued_job_removes_by_id() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state(
        queue=[{"id": "j-q", "status": "queued"}]
    )
    session.post_payloads["/queue/remove"] = {"ok": True}
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-q"
    assert await adapter.cancel_job(job) is True
    posts = [c for c in session.calls if c[0] == "POST"]
    assert posts[0][1].endswith("/queue/remove")
    assert posts[0][2] == {"id": "j-q"}


async def test_cancel_running_own_job_stops() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state(
        current={"id": "j-r", "status": "running"}
    )
    session.post_payloads["/stop"] = {"ok": True}
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-r"
    assert await adapter.cancel_job(job) is True


async def test_cancel_never_stops_stranger_job() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state(
        current={"id": "j-stranger", "status": "running"},
        queue=[{"id": "j-other", "status": "queued"}],
    )
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-mine"  # in history/nowhere relevant
    assert await adapter.cancel_job(job) is False
    assert not [c for c in session.calls if c[0] == "POST"]


async def test_cancel_without_id_is_false() -> None:
    assert await _adapter_with(_FakeSession()).cancel_job(_job()) is False


# ---------------------------------------------------------------------------
# 27-28. Timeout + invalid API responses
# ---------------------------------------------------------------------------


async def test_status_poll_survives_malformed_responses() -> None:
    session = _FakeSession()
    adapter = _adapter_with(session)
    job = _job()
    job.provider_job_id = "j-1"
    job.status = "rendering"
    session.get_payloads["/status"] = ["not", "a", "dict"]
    job = await adapter.get_job_status(job)
    assert job.status == "rendering"  # unchanged, no crash


async def test_submit_survives_non_json_rejection() -> None:
    session = _FakeSession()
    session.get_payloads["/status"] = _status_state()
    session.post_payloads["/queue/add"] = ValueError("no json")
    job = await _adapter_with(session).submit_job(_job())
    assert job.status == "failed"


# ---------------------------------------------------------------------------
# 29-30. Hardware capability gating (fail, never downgrade)
# ---------------------------------------------------------------------------


def test_unsupported_resolution_fails() -> None:
    result = translate_studio_request("x", parameters={"width": 1280, "height": 704})
    assert result["ok"] is False
    assert "768" in result["error"]


def test_unaligned_dimensions_fail() -> None:
    result = translate_studio_request("x", parameters={"width": 700, "height": 400})
    assert result["ok"] is False
    assert "divisible by 32" in result["error"]


def test_unsupported_quality_fails_without_substitution() -> None:
    result = translate_studio_request("x", parameters={"quality": "high"})
    assert result["ok"] is False
    assert "high" in result["error"]


def test_unsupported_frames_fail() -> None:
    result = translate_studio_request("x", parameters={"frames": 120})
    assert result["ok"] is False
    assert "% 8 == 1" in result["error"]


def test_unsupported_duration_fails() -> None:
    result = translate_studio_request("x", parameters={"duration_seconds": 3})
    assert result["ok"] is False
    assert "frames explicitly" in result["error"]


def test_empty_prompt_fails() -> None:
    assert translate_studio_request("   ")["ok"] is False


# ---------------------------------------------------------------------------
# 31-34. Explicit selection, no fallback, isolation
# ---------------------------------------------------------------------------


def test_explicit_ltx_selection_accepted() -> None:
    from app.services.render import RenderService

    job = RenderService().create_job(
        project_id="project-ltx",
        shot_id="scene_001_shot_001",
        provider="local_ltx",
        prompt="A quiet interior at dawn.",
    )
    assert job.provider == "local_ltx"


def test_unknown_provider_still_rejected() -> None:
    from app.services.render import RenderService

    with pytest.raises(ValueError, match="Unknown provider"):
        RenderService().create_job(
            project_id="project-ltx",
            shot_id="scene_001_shot_001",
            provider="pinokio_video",
        )


def test_existing_registry_entries_unchanged() -> None:
    assert ADAPTER_REGISTRY["runway"] is RunwayAdapter
    assert ADAPTER_REGISTRY["simulated"] is SimulatedProviderAdapter
    assert ADAPTER_REGISTRY["generic"] is GenericVideoProviderAdapter
    # Presence-based guard (R4.5-Phase2 #19): every non-local_ltx entry is
    # pinned by name, so registry drift fails loudly instead of hiding behind
    # a magic count. 14 total keys → 13 besides local_ltx itself.
    assert {k for k in ADAPTER_REGISTRY if k != PROVIDER_ID} == {
        "generic",
        "happyhorse",
        "happyhorse-r2v",
        "higgsfield",
        "local",
        "local_training",
        "minimax_h3_local",
        "phosphene_training",
        "runway",
        "runway_direct",
        "runway_router",
        "simulated",
        "wan",
    }


def test_minimax_h3_provider_untouched() -> None:
    from app.adapters.minimax_h3_local import (
        MinimaxH3LocalAdapter,
        build_default_config as h3_config,
    )

    assert ADAPTER_REGISTRY["minimax_h3_local"] is MinimaxH3LocalAdapter
    assert h3_config(enabled=False).enabled is False

    from app.services.render import RenderService

    h3 = RenderService().get_provider_config("minimax_h3_local")
    assert h3 is not None and h3.enabled is False
