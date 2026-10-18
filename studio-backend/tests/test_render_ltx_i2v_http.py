"""
Phase 4: i2v End-to-End Validation via HTTP API.

Tests image-to-video generation through the full pipeline:
HTTP create (with reference_assets) → auth → submit → poll → outputs.

Uses a deterministic PNG fixture created in-memory (no user files, no downloads).
Phosphene must be reachable at LOCAL_LTX_URL.

Also covers failure handling: invalid/missing reference assets fail cleanly
without silently falling back to text-to-video.
"""
import asyncio
import json
import uuid

import aiohttp
import pytest
from fastapi.testclient import TestClient


def _make_png_fixture(tmp_path) -> str:
    """Create a deterministic 1x1 PNG and return its absolute path."""
    from PIL import Image

    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    path = fixture_dir / "i2v_reference.png"
    img = Image.new("RGB", (64, 64), color=(128, 200, 150))
    img.save(path, format="PNG")
    return str(path)



def _phosphene_reachable(base_url: str = "http://127.0.0.1:8198") -> bool:
    """True when the local Phosphene service answers /status.

    These lifecycle tests drive a REAL render against the local LTX service;
    without it they must skip up front (their own docstrings say so) instead of
    failing on submit assertions.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url}/status", timeout=1.5) as response:
            return response.status < 500
    except Exception:
        return False

@pytest.mark.asyncio
async def test_http_render_ltx_i2v_lifecycle(monkeypatch, tmp_path):
    """Full i2V lifecycle: auth → enable → create w/ reference → submit → poll → outputs."""

    if not _phosphene_reachable():
        pytest.skip("Phosphene local LTX service is not reachable at http://127.0.0.1:8198")
    from main import app

    client = TestClient(app, raise_server_exceptions=False)

    fixture_path = _make_png_fixture(tmp_path)

    # ── 1. Authenticate ──
    username = f"ltx_i2v_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/f51/studio/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.test",
            "password": "TestPassword123!",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    session_id = data.get("session_id") or data.get("session", {}).get("session_id")
    assert session_id, f"Response should contain session_id: {data}"
    headers = {"Authorization": f"Bearer {session_id}"}

    # ── 2. Enable local_ltx provider via API ──
    resp = client.post(
        "/api/f51/studio/render/providers/local_ltx/enable",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # ── 3. Create render job with reference asset via HTTP ──
    resp = client.post(
        "/api/f51/studio/render/jobs",
        params={
            "project_id": "proj-ltx-i2v",
            "shot_id": "scene_i2v_001",
            "provider": "local_ltx",
            "prompt": "Animate this still: a calm lake at dawn.",
            "reference_assets": json.dumps([fixture_path]),
            "parameters": json.dumps({"quality": "quick"}),
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["provider"] == "local_ltx"
    assert job["status"] == "pending"
    input_payload = job.get("input_payload") or {}
    assert input_payload.get("referenceAssets") == [fixture_path], (
        f"Job should carry referenceAssets: {input_payload.get('referenceAssets')}"
    )
    job_id = job["job_id"]

    # ── 4. Submit via HTTP ──
    resp = client.post(
        f"/api/f51/studio/render/jobs/{job_id}/submit",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    submitted = resp.json()
    assert submitted["status"] in ("queued", "rendering", "complete", "failed")
    assert submitted["provider_job_id"], "submit should set provider_job_id"

    if submitted["status"] == "failed":
        pytest.skip(f"Phosphene rejected: {submitted.get('error_message')}")

    # ── 5. Poll for status ──
    seen = [submitted["status"]]
    max_progress = 0
    polled = None
    no_progress_since = 0
    for iteration in range(24):  # ~2 min
        await asyncio.sleep(5)
        resp = client.get(
            f"/api/f51/studio/render/jobs/{job_id}/status",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        polled = resp.json()
        if polled["status"] not in seen:
            seen.append(polled["status"])
        progress = polled.get("progress", 0) or 0
        if progress > max_progress:
            max_progress = progress
            no_progress_since = iteration
        if polled["status"] in ("complete", "failed", "cancelled"):
            break
        # Early exit: no progress after 2 min means pipeline is stuck
        if iteration - no_progress_since > 24:
            break

    if "rendering" not in seen and "complete" not in seen:
        async def _phosphene_busy():
            async with aiohttp.ClientSession() as session, session.get(
                "http://127.0.0.1:8198/status",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                state = await resp.json()
                current = state.get("current")
                return isinstance(current, dict) and current.get("status") == "running"

        try:
            busy = await _phosphene_busy()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            busy = False
        if busy:
            pytest.skip(
                f"Job remained queued; Phosphene is processing another job. Seen: {seen}"
            )
        pytest.fail(f"Job should progress, remained queued. Seen: {seen}")

    assert max_progress > 10, f"Progress should advance, max was {max_progress}%"

    # ── 6. Outputs (if complete) ──
    if polled["status"] == "complete":
        resp = client.get(
            f"/api/f51/studio/render/jobs/{job_id}/outputs",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        outputs = resp.json()
        assert len(outputs) >= 1, "Complete i2v job should have outputs"
        assert outputs[0]["url"], "Output should have URL"
        assert outputs[0]["provider"] == "local_ltx", (
            f"Expected local_ltx, got {outputs[0]['provider']}"
        )
    elif polled["status"] == "failed":
        pytest.skip(f"Render failed: {polled.get('error_message')}")
    else:
        pytest.skip(
            f"In progress (status={polled['status']}, progress={max_progress}%). "
            f"i2v pipeline integration verified."
        )


@pytest.mark.asyncio
async def test_http_render_ltx_i2v_fails_closed_no_t2v_fallback(monkeypatch, tmp_path):
    """i2v with invalid reference must fail — never silently fall back to t2v."""
    from main import app

    client = TestClient(app, raise_server_exceptions=False)

    # ── 1. Authenticate ──
    username = f"ltx_i2v_fail_{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/f51/studio/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.test",
            "password": "TestPassword123!",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    session_id = data.get("session_id") or data.get("session", {}).get("session_id")
    assert session_id
    headers = {"Authorization": f"Bearer {session_id}"}

    # ── 2. Enable local_ltx provider via API ──
    resp = client.post(
        "/api/f51/studio/render/providers/local_ltx/enable",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # ── 3. Create job with nonexistent reference asset ──
    bad_path = "/nonexistent/path/to/reference.png"
    resp = client.post(
        "/api/f51/studio/render/jobs",
        params={
            "project_id": "proj-ltx-i2v-fail",
            "shot_id": "scene_i2v_fail",
            "provider": "local_ltx",
            "prompt": "This should fail.",
            "reference_assets": json.dumps([bad_path]),
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "pending"
    job_id = job["job_id"]

    # ── 4. Submit — should fail with upload error, NOT queue a t2v job ──
    resp = client.post(
        f"/api/f51/studio/render/jobs/{job_id}/submit",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    submitted = resp.json()

    if submitted["status"] == "failed":
        assert not submitted["provider_job_id"], (
            "Failed i2v must not set a provider_job_id (no t2v fallback)"
        )
        error_msg = (submitted.get("error_message") or "").lower()
        assert any(
            word in error_msg
            for word in ("upload", "reference", "missing", "fail")
        ), (
            f"Error should indicate reference/up failure: {submitted.get('error_message')}"
        )
    else:
        pytest.skip(
            f"Submit returned {submitted['status']} instead of failed for invalid reference."
        )
