from __future__ import annotations

import pytest

from app.adapters.local_ltx import LocalLTXAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services.local_ltx_reference_projection import LOCAL_LTX_REFERENCE_CAPABILITY

PROJECT = "film-anchor"


class _Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, None))
        return _Response({"current": None, "queue": [], "history": []})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs.get("data")))
        if url.endswith("/queue/add"):
            return _Response({"ok": True, "id": "phosphene-job-1"})
        return _Response({"ok": True})


def _ref(ref_id: str, category: str, *, canonical: bool, target_type="character", target_id="maya") -> dict:
    return {
        "ref_id": ref_id,
        "kind": "environment" if target_type == "setting" else "character_face" if category == "face" else "character_full",
        "image_url": f"/outputs/{ref_id}.png",
        "source_shot_id": "scene_001_shot_001",
        "project_id": PROJECT,
        "target_type": target_type,
        "target_id": target_id,
        "category": category,
        "approval_state": "approved",
        "canonical": canonical,
        "source_kind": "uploaded",
        "reference_role": category,
        "look_id": "default",
        "lock_status": "locked" if canonical else None,
        "source_status": "approved",
        "review_status": "approved",
        "capture_method": "director_override",
        "reliability": "high",
        "reference_created_at": "2026-09-01T00:00:00Z",
    }


def _job(refs: list[dict], *, framing="full") -> RenderJobModel:
    params = {
        "local_ltx_scene_context": {
            "scene_id": "scene_001",
            "shot_id": "scene_001_shot_001",
            "setting_id": "loft",
            "character_ids": ["maya"],
            "framing": framing,
        },
        "width": 768,
        "height": 448,
        "frames": 121,
        "steps": 8,
        "seed": 1234,
        "quality": "balanced",
    }
    # A real consistency schema is used to ensure the adapter sees IDs/categories,
    # while the separate image URL list models the existing request field.
    from app.models.consistency import ConsistencyPayload, ReferenceAsset
    consistency_refs = [ReferenceAsset(**row) for row in refs]
    payload = RenderJobInput(
        shot_id="scene_001_shot_001",
        prompt="Maya is seen in a full body shot in the loft.",
        referenceAssets=[row.image_url for row in consistency_refs],
        parameters=params,
        consistency_payload=ConsistencyPayload(
            project_id=PROJECT,
            refs=consistency_refs,
            mode="identity_lock",
            selection_audit=[{
                "character_id": "maya",
                "selection": {"selected": [{"ref_id": row.ref_id, "reason": f"selected {row.category}"} for row in consistency_refs]},
            }],
        ),
    )
    return RenderJobModel(
        id="job-anchor-test",
        project_id=PROJECT,
        shot_id="scene_001_shot_001",
        provider="local_ltx",
        status="pending",
        input_payload=payload,
        metadata={},
    )


def _adapter(session: _Session) -> LocalLTXAdapter:
    adapter = LocalLTXAdapter(ProviderConfig(
        provider_id="local_ltx",
        name="Local LTX",
        enabled=True,
        is_simulated=False,
        api_endpoint="http://127.0.0.1:8198",
        capabilities=["video_generation", "image_to_video"],
    ))

    async def get_session():
        return session

    adapter._get_session = get_session  # type: ignore[method-assign]
    return adapter


@pytest.mark.asyncio
async def test_full_body_projection_uploads_supporting_body_and_sends_exactly_one_image(monkeypatch):
    face = _ref("maya-face-lock", "face", canonical=True)
    body = _ref("maya-full-body", "full_body", canonical=False)
    session = _Session()
    uploaded = []

    async def fake_upload(self, reference: str):
        uploaded.append(reference)
        return "/panel/uploads/maya-full-body.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    job = await _adapter(session).submit_job(_job([face, body]))

    queue_call = next(call for call in session.calls if call[0] == "POST" and call[1].endswith("/queue/add"))
    trace = job.metadata["local_ltx_reference_trace"]
    assert uploaded == [body["image_url"]]
    assert queue_call[2]["mode"] == "i2v"
    assert queue_call[2]["image"] == "/panel/uploads/maya-full-body.png"
    assert sum(key == "image" for key in queue_call[2]) == 1
    assert trace["selected"]["ref_id"] == "maya-full-body"
    assert trace["canonical_reference_id"] == "maya-face-lock"
    assert trace["canonical_available"] is True
    assert trace["uploaded_reference_id"] == "maya-full-body"
    assert trace["uploaded_category"] == "full_body"
    assert trace["provider_received_image_count"] == 1
    assert trace["provider_capacity"] == 1
    assert trace["phosphene_job_id"] == "phosphene-job-1"
    assert trace["phosphene_image_field"] == "image"
    assert trace["model_consumption_contract"].endswith("one scalar conditioning image")
    assert trace["scene_context"]["framing"] == "full"
    assert trace["studio_selected_references"][0]["ref_id"] == "maya-face-lock"
    assert trace["studio_selected_references"][0]["canonical"] is True
    assert trace["studio_selected_references"][1]["stage1_selection_reason"] == "selected full_body"
    assert trace["upload_attempts"] == [{
        "reference_id": "maya-full-body",
        "reference_category": "full_body",
        "available_to_provider": True,
    }]
    assert trace["selected"]["selection_reason"].startswith("explicit full-body framing")
    assert LOCAL_LTX_REFERENCE_CAPABILITY == {"maximum_reference_images": 1, "conditioning_mode": "i2v"}
    # The original multi-reference consistency set is not rewritten or demoted.
    assert [ref.ref_id for ref in job.input_payload.consistency_payload.refs] == ["maya-face-lock", "maya-full-body"]
    assert job.input_payload.consistency_payload.refs[0].canonical is True


@pytest.mark.asyncio
async def test_unavailable_context_asset_falls_back_to_canonical_and_records_actual_url(monkeypatch):
    face = _ref("maya-face-lock", "face", canonical=True)
    body = _ref("maya-full-body", "full_body", canonical=False)
    session = _Session()
    attempts = []

    async def fake_upload(self, reference: str):
        attempts.append(reference)
        return None if reference == body["image_url"] else "/panel/uploads/maya-face.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    job = await _adapter(session).submit_job(_job([face, body]))

    queue_call = next(call for call in session.calls if call[0] == "POST" and call[1].endswith("/queue/add"))
    trace = job.metadata["local_ltx_reference_trace"]
    assert attempts == [body["image_url"], face["image_url"]]
    assert queue_call[2]["image"] == "/panel/uploads/maya-face.png"
    assert trace["selected"]["ref_id"] == "maya-full-body"
    assert trace["uploaded_reference_id"] == "maya-face-lock"
    assert trace["uploaded_category"] == "face"
    assert trace["provider_image_path"] == "/panel/uploads/maya-face.png"
    assert trace["canonical_reference_id"] == "maya-face-lock"
    assert trace["upload_attempts"] == [
        {"reference_id": "maya-full-body", "reference_category": "full_body", "available_to_provider": False},
        {"reference_id": "maya-face-lock", "reference_category": "face", "available_to_provider": True},
    ]


@pytest.mark.asyncio
async def test_no_canonical_character_reference_fails_before_phosphene(monkeypatch):
    support = _ref("maya-body-support", "full_body", canonical=False)
    session = _Session()
    uploads = []

    async def fake_upload(self, reference: str):
        uploads.append(reference)
        return "/panel/uploads/should-not-upload.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    job = await _adapter(session).submit_job(_job([support]))
    assert job.status == "failed"
    assert "no approved" in (job.error_message or "")
    assert uploads == []
    assert not [call for call in session.calls if call[0] == "POST"]


@pytest.mark.asyncio
async def test_contextual_anchor_not_selected_when_shot_plan_is_not_explicit(monkeypatch):
    face = _ref("maya-face-lock", "face", canonical=True)
    body = _ref("maya-full-body", "full_body", canonical=False)
    session = _Session()
    uploaded = []

    async def fake_upload(self, reference: str):
        uploaded.append(reference)
        return "/panel/uploads/canonical-face.png"

    monkeypatch.setattr(LocalLTXAdapter, "_upload_reference", fake_upload)
    job = await _adapter(session).submit_job(_job([face, body], framing="wide"))
    trace = job.metadata["local_ltx_reference_trace"]
    assert uploaded == [face["image_url"]]
    assert trace["selected"]["ref_id"] == "maya-face-lock"
    assert trace["canonical_available"] is True
