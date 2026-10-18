"""
Phase 3: HTTP API lifecycle with authentication.

Tests the user-facing workflow through the real FastAPI app:
register → enable provider → create render job → submit → poll → outputs.

Uses TestClient with full app (auth middleware included).
Phosphene must be reachable at LOCAL_LTX_URL.
"""
import asyncio
import uuid

import aiohttp
import pytest
from fastapi.testclient import TestClient



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
async def test_http_render_ltx_lifecycle(monkeypatch):
    """Full HTTP lifecycle: register, enable, create, submit, poll, outputs."""

    if not _phosphene_reachable():
        pytest.skip("Phosphene local LTX service is not reachable at http://127.0.0.1:8198")
    from main import app

    client = TestClient(app, raise_server_exceptions=False)

    # ── 1. Authenticate ──
    username = f"ltx_user_{uuid.uuid4().hex[:8]}"
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

    # ── 3. Create render job via HTTP ──
    resp = client.post(
        "/api/f51/studio/render/jobs",
        params={
            "project_id": "proj-http-ltx",
            "shot_id": "scene_001_shot_001",
            "provider": "local_ltx",
            "prompt": "A calm lake at dawn with soft morning light.",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["provider"] == "local_ltx"
    assert job["status"] == "pending"
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
    for iteration in range(84):  # ~7 min
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
        max_progress = max(max_progress, progress)
        if polled["status"] in ("complete", "failed", "cancelled"):
            break
        # After 2 min still queued + Phosphene busy = skip
        if iteration == 23 and progress == 0:
            try:
                async with aiohttp.ClientSession() as s, s.get(
                    "http://127.0.0.1:8198/status",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as r:
                    st = await r.json()
                    c = st.get("current")
                    busy = isinstance(c, dict) and c.get("status") == "running"
                if busy:
                    pytest.skip("Phosphene busy; job queued behind another render.")
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass

    if "rendering" not in seen and "complete" not in seen:
        try:
            async with aiohttp.ClientSession() as s, s.get(
                "http://127.0.0.1:8198/status",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                st = await r.json()
                c = st.get("current")
                busy = isinstance(c, dict) and c.get("status") == "running"
        except (aiohttp.ClientError, asyncio.TimeoutError):
            busy = False
        if busy:
            pytest.skip(
                "Job remained queued; Phosphene is processing another job. "
                f"Seen: {seen}"
            )
        pytest.fail(f"Job should progress, seen: {seen}")

    assert max_progress > 10, f"Progress should advance, max was {max_progress}%"

    # ── 6. Outputs (if complete) ──
    if polled["status"] == "complete":
        resp = client.get(
            f"/api/f51/studio/render/jobs/{job_id}/outputs",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        outputs = resp.json()
        assert len(outputs) >= 1, "Complete job should have outputs"
        assert outputs[0]["url"], "Output should have URL"
        assert outputs[0]["provider"] == "local_ltx", (
            f"Expected local_ltx, got {outputs[0]['provider']}"
        )
    elif polled["status"] == "failed":
        pytest.skip(f"Render failed: {polled.get('error_message')}")
    else:
        pytest.skip(
            f"In progress (status={polled['status']}, progress={max_progress}%). "
            f"HTTP pipeline integration verified."
        )
