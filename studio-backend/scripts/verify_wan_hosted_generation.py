from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

from verify_runway_hosted_generation import (
    _extract_output_fields,
    curl_json,
    detect_backend_base,
    load_env,
    safe_key_info,
    submit_and_poll_job,
)

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def get_wan_provider_status(base: str) -> dict:
    rows = curl_json("GET", f"{base}/api/f51/studio/render/providers", timeout=10)
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected providers response shape")
    wan = next((row for row in rows if row.get("provider_id") == "wan"), None)
    if not wan:
        raise RuntimeError("Wan provider missing from provider status list")
    return wan


def assert_hosted_ready(provider_status: dict) -> None:
    if provider_status.get("provider_mode") != "hosted_api":
        raise RuntimeError(
            f"Wan not in hosted mode: provider_mode={provider_status.get('provider_mode')}"
        )
    if not provider_status.get("ready_for_hosted_generation"):
        raise RuntimeError(
            "Wan not ready for hosted generation; "
            f"missing_requirements={provider_status.get('missing_requirements') or []}"
        )


def create_render_job(base: str, prompt: str) -> dict:
    timestamp = int(time.time())
    project_id = f"wan-verify-project-{timestamp}"
    shot_id = f"wan-verify-{timestamp}"
    project = curl_json(
        "POST",
        f"{base}/api/f51/studio/projects",
        payload={
            "project_id": project_id,
            "title": "Hosted Wan Release Verification",
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
            "provider": "wan",
            "prompt": prompt,
            "parameters": json.dumps(
                {
                    "model": "wan2.6-t2v",
                    "duration_seconds": 5,
                    "resolution": "720P",
                    "ratio": "16:9",
                    "prompt_extend": True,
                    "shot_type": "multi",
                    "watermark": False,
                }
            ),
        }
    )
    return curl_json(
        "POST",
        f"{base}/api/f51/studio/render/jobs?{query}",
        payload={},
        timeout=30,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify hosted Wan generation path")
    parser.add_argument(
        "--prompt",
        default=(
            "A restrained cinematic night exterior. A woman waits alone beneath a failing "
            "station light as distant rain crosses the empty platform. Begin in a wide shot, "
            "then move gently closer. Natural ambience, no dialogue, soft contrast."
        ),
        help="Prompt for the 5-second hosted verification render",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("WAN_TIMEOUT_SECONDS", "900") or "900"),
        help="Timeout for hosted render completion",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(ENV_PATH)

    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    print("DASHSCOPE_API_KEY:", json.dumps(safe_key_info(dashscope_key)))
    print("estimated_max_cost_usd:", "0.50")

    if not dashscope_key:
        print("status: failed")
        print(
            "error:",
            json.dumps(
                {
                    "error_type": "missing_api_key",
                    "message": "DASHSCOPE_API_KEY is required",
                }
            ),
        )
        return 1

    base = detect_backend_base()
    print("backend_base:", base)

    provider_status = get_wan_provider_status(base)
    print("provider_status:", json.dumps(provider_status, ensure_ascii=True))
    try:
        assert_hosted_ready(provider_status)
    except RuntimeError as exc:
        print("status: failed")
        print(
            "error:",
            json.dumps({"error_type": "provider_not_ready", "message": str(exc)}),
        )
        return 1

    created = create_render_job(base, args.prompt)
    job_id = created.get("id")
    if not job_id:
        print("status: failed")
        print(
            "error:",
            json.dumps({"error_type": "job_create_failed", "raw_response": created}),
        )
        return 1
    print("job_id:", job_id)

    try:
        final_job = submit_and_poll_job(base, job_id, max(args.timeout_seconds, 60))
    except RuntimeError as exc:
        print("status: failed")
        print(
            "error:",
            json.dumps(
                {"error_type": "timeout", "message": str(exc), "job_id": job_id}
            ),
        )
        return 1

    output_url, preview_url, provider_job_id, provider_mode = _extract_output_fields(
        final_job
    )
    status = final_job.get("status", "unknown")
    print("provider_job_id:", provider_job_id)
    print("status:", status)
    print("output_url:", output_url)
    print("preview_url:", preview_url)
    print("provider_mode:", provider_mode)

    if status != "complete":
        print(
            "error:",
            json.dumps(
                {"error_type": "job_not_complete", "job": final_job},
                ensure_ascii=True,
            ),
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
