from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def resolve_runway_key() -> tuple[str, str]:
    for source in ("RUNWAYML_API_SECRET", "RUNWAY_API_KEY"):
        value = os.getenv(source, "").strip()
        if value:
            return source, value
    return "none", ""


def safe_key_info(value: str) -> dict:
    exists = bool(value)
    return {
        "exists": exists,
        "length": len(value) if exists else 0,
        "first4": value[:4] if exists else "",
        "last4": value[-4:] if exists else "",
    }


def curl_json(method: str, url: str, *, payload: dict | None = None, timeout: int = 20) -> dict:
    cmd = ["curl", "-sS", "-m", str(timeout), "-X", method]
    if payload is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(payload)])
    cmd.append(url)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "curl failed")
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else {}


def detect_backend_base() -> str:
    candidates = [
        os.getenv("STUDIO_BACKEND_BASE_URL", "").strip(),
        "http://127.0.0.1:8010",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8012",
    ]
    for base in [c for c in candidates if c]:
        try:
            _ = curl_json("GET", f"{base}/health", timeout=4)
            return base
        except Exception:
            continue
    raise RuntimeError("No healthy backend found on 8010/8000/8012")


def get_runway_provider_status(base: str) -> dict:
    rows = curl_json("GET", f"{base}/api/f51/studio/render/providers", timeout=10)
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected providers response shape")
    runway = next((row for row in rows if row.get("provider_id") == "runway"), None)
    if not runway:
        raise RuntimeError("Runway provider missing from provider status list")
    return runway


def assert_hosted_ready(runway_status: dict) -> None:
    if runway_status.get("provider_mode") != "hosted_api":
        raise RuntimeError(
            f"Runway not in hosted mode: provider_mode={runway_status.get('provider_mode')}"
        )
    if not runway_status.get("ready_for_hosted_generation"):
        raise RuntimeError(
            "Runway not ready for hosted generation; "
            f"missing_requirements={runway_status.get('missing_requirements') or []}"
        )


def create_render_job(base: str, prompt: str) -> dict:
    timestamp = int(time.time())
    project_id = f"hosted-verify-project-{timestamp}"
    shot_id = f"hosted-verify-{timestamp}"
    project = curl_json(
        "POST",
        f"{base}/api/f51/studio/projects",
        payload={
            "project_id": project_id,
            "title": "Hosted Runway Release Verification",
        },
        timeout=30,
    )
    if str(project.get("project_id") or project.get("id") or "") != project_id:
        raise RuntimeError(
            f"Temporary project creation failed for {project_id}: "
            f"{json.dumps(project, ensure_ascii=True)}"
        )
    query = urlencode(
        {
            "project_id": project_id,
            "shot_id": shot_id,
            "provider": "runway",
            "prompt": prompt,
        }
    )
    return curl_json(
        "POST",
        f"{base}/api/f51/studio/render/jobs?{query}",
        payload={},
        timeout=30,
    )


def _extract_output_fields(job_payload: dict) -> tuple[str | None, str | None, str | None, str | None]:
    output_payload = job_payload.get("output_payload") if isinstance(job_payload, dict) else {}
    output_payload = output_payload if isinstance(output_payload, dict) else {}
    metadata = output_payload.get("metadata") if isinstance(output_payload, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    normalized = metadata.get("provider_response_normalized") if isinstance(metadata, dict) else {}
    normalized = normalized if isinstance(normalized, dict) else {}
    normalized_output = normalized.get("output") if isinstance(normalized.get("output"), dict) else {}
    normalized_meta = normalized.get("metadata") if isinstance(normalized.get("metadata"), dict) else {}

    output_url = (
        output_payload.get("asset_url")
        or normalized_output.get("video_url")
        or job_payload.get("output_url")
    )
    preview_url = (
        output_payload.get("thumbnail_url")
        or normalized_output.get("preview_url")
        or job_payload.get("preview_url")
    )
    provider_job_id = job_payload.get("provider_job_id") or normalized_meta.get("task_id")
    provider_mode = normalized_meta.get("provider_mode")

    return output_url, preview_url, provider_job_id, provider_mode


def submit_and_poll_job(base: str, job_id: str, timeout_seconds: int) -> dict:
    _ = curl_json("POST", f"{base}/api/f51/studio/render/jobs/{job_id}/submit", payload={}, timeout=timeout_seconds)

    deadline = time.time() + timeout_seconds
    last_seen: dict = {}
    while time.time() < deadline:
        # Use status endpoint to keep polling upstream provider when backend
        # submit returns while task is still running.
        current = curl_json("GET", f"{base}/api/f51/studio/render/jobs/{job_id}/status", timeout=20)
        last_seen = current
        status = str(current.get("status", "")).lower()
        if status in {"complete", "failed", "cancelled"}:
            return current
        time.sleep(5)
    provider_job_id = last_seen.get("provider_job_id")
    last_status = str(last_seen.get("status", "unknown"))
    raise RuntimeError(
        f"Timed out waiting for render job completion; "
        f"provider_job_id={provider_job_id or 'unknown'} last_status={last_status}. "
        f"Try: curl -sS {base}/api/f51/studio/render/jobs/{job_id}/status"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify hosted Runway generation path")
    parser.add_argument(
        "--prompt",
        default="A cinematic rainy street at night, moody, 24fps, soft contrast",
        help="Prompt for hosted verification render",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("RUNWAY_TIMEOUT_SECONDS", "300") or "300"),
        help="Timeout for hosted render completion",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(ENV_PATH)

    key_source, runway_key = resolve_runway_key()
    print("RUNWAY_KEY_SOURCE:", key_source)
    print("RUNWAY_API_KEY:", json.dumps(safe_key_info(runway_key)))

    if not runway_key:
        print("status: failed")
        print("error:", json.dumps({"error_type": "missing_api_key", "message": "RUNWAY_API_KEY (or RUNWAYML_API_SECRET) is required"}))
        return 1

    test_mode = str(os.getenv("RENDER_PROVIDER_TEST_MODE", "")).strip().lower()
    if test_mode in {"mock_success", "true", "1"}:
        print("status: failed")
        print("error:", json.dumps({"error_type": "mock_mode_enabled", "message": "Disable RENDER_PROVIDER_TEST_MODE for hosted verification"}))
        return 1

    base = detect_backend_base()
    print("backend_base:", base)

    runway_status = get_runway_provider_status(base)
    print("provider_status:", json.dumps(runway_status, ensure_ascii=True))

    try:
        assert_hosted_ready(runway_status)
    except RuntimeError as exc:
        print("status: failed")
        print("error:", json.dumps({"error_type": "provider_not_ready", "message": str(exc)}))
        return 1

    created = create_render_job(base, args.prompt)
    job_id = created.get("id")
    if not job_id:
        print("status: failed")
        print("error:", json.dumps({"error_type": "job_create_failed", "raw_response": created}))
        return 1

    print("job_id:", job_id)

    try:
        final_job = submit_and_poll_job(base, job_id, max(args.timeout_seconds, 60))
    except RuntimeError as exc:
        print("status: failed")
        print("error:", json.dumps({"error_type": "timeout", "message": str(exc), "job_id": job_id}))
        return 1

    output_url, preview_url, provider_job_id, provider_mode = _extract_output_fields(final_job)
    status = final_job.get("status", "unknown")

    print("provider_job_id:", provider_job_id)
    print("status:", status)
    print("output_url:", output_url)
    print("preview_url:", preview_url)
    print("provider_mode:", provider_mode)

    if status != "complete":
        print("error:", json.dumps({"error_type": "job_not_complete", "job": final_job}, ensure_ascii=True))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
