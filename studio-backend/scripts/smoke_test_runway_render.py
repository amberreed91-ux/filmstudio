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


def safe_key_info(value: str) -> dict:
    exists = bool(value)
    return {
        "exists": exists,
        "length": len(value) if exists else 0,
        "first4": value[:4] if exists else "",
        "last4": value[-4:] if exists else "",
    }


def resolve_runway_key() -> tuple[str, str]:
    for source in ("RUNWAYML_API_SECRET", "RUNWAY_API_KEY"):
        value = os.getenv(source, "")
        if value:
            return source, value
    return "none", ""


def curl_json(method: str, url: str, *, payload: dict | None = None, timeout: int = 10, headers: dict | None = None) -> dict:
    cmd = ["curl", "-sS", "-m", str(timeout), "-X", method]
    for k, v in (headers or {}).items():
        cmd.extend(["-H", f"{k}: {v}"])
    if payload is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(payload)])
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "curl failed")
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else {}


def detect_backend_base() -> str:
    for base in ["http://127.0.0.1:8000", "http://127.0.0.1:8012"]:
        try:
            _ = curl_json("GET", f"{base}/health", timeout=4)
            return base
        except Exception:
            continue
    raise RuntimeError("No healthy backend found on 8000 or 8012")


def _extract_output(status_response: dict) -> tuple[str | None, str | None, dict | None]:
    output_payload = status_response.get("output_payload") or {}
    metadata = output_payload.get("metadata") or {}
    normalized = metadata.get("provider_response_normalized") or {}
    output_url = output_payload.get("asset_url") or (normalized.get("output") or {}).get("video_url")
    preview_url = output_payload.get("thumbnail_url")
    structured_error = (normalized.get("metadata") or {}).get("error")
    return output_url, preview_url, structured_error


def poll_existing_task(task_id: str, timeout_seconds: int, runway_key: str) -> int:
    deadline = time.time() + timeout_seconds
    url = f"https://api.dev.runwayml.com/v1/tasks/{task_id}"
    headers = {
        "Authorization": f"Bearer {runway_key}",
        "X-Runway-Version": "2024-11-06",
    }
    print("task_id:", task_id)
    while time.time() < deadline:
        response = curl_json("GET", url, timeout=30, headers=headers)
        status = str(response.get("status", "")).strip().lower()
        print("status:", status or "unknown")
        if status in {"succeeded", "completed"}:
            output = response.get("output") or []
            output_url = output[0] if isinstance(output, list) and output else None
            print("output_url:", output_url)
            print("preview_url:", None)
            return 0
        if status in {"failed", "canceled", "cancelled"}:
            print("error:", json.dumps(response.get("error") or response, ensure_ascii=True))
            return 1
        print("polling: waiting 10s...")
        time.sleep(10)
    print("error:", json.dumps({"error_type": "timeout", "message": f"task still running after {timeout_seconds}s"}))
    return 1


def run_new_job(timeout_seconds: int, runway_key: str) -> int:
    base = detect_backend_base()
    print("backend_base:", base)

    shot_id = f"smoke-{int(time.time())}"
    query = urlencode(
        {
            "project_id": "smoke-project",
            "shot_id": shot_id,
            "provider": "runway",
            "prompt": "A lone woman walking through neon rain at night, cinematic, moody",
        }
    )

    created = curl_json("POST", f"{base}/api/f51/studio/render/jobs?{query}", payload={}, timeout=30)
    job_id = created.get("id")
    if not job_id:
        print("status: failed")
        print("error:", json.dumps({"error_type": "job_create_failed", "message": "No job id returned", "raw_response": created}))
        return 1
    print("job_id:", job_id)

    submit_cmd = [
        "curl", "-sS", "-m", str(max(timeout_seconds, 900)), "-X", "POST", "-H", "Content-Type: application/json", "-d", "{}",
        f"{base}/api/f51/studio/render/jobs/{job_id}/submit",
    ]
    submit_proc = subprocess.Popen(submit_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    deadline = time.time() + timeout_seconds
    seen_task_id: str | None = None
    last_status = "unknown"

    while time.time() < deadline:
        if submit_proc.poll() is not None:
            break
        try:
            current = curl_json("GET", f"{base}/api/f51/studio/render/jobs/{job_id}", timeout=20)
            last_status = str(current.get("status", "unknown"))
            current_task_id = current.get("provider_job_id")
            if current_task_id and not seen_task_id:
                seen_task_id = current_task_id
                print("task_id:", seen_task_id)
            print("polling_status:", last_status)
        except Exception as exc:
            print("polling_status_error:", str(exc))
        print("polling: waiting 10s...")
        time.sleep(10)

    if submit_proc.poll() is None:
        submit_proc.kill()
        print("status: failed")
        print("error:", json.dumps({"error_type": "timeout", "message": f"submit exceeded {timeout_seconds}s"}))
        return 1

    stdout, stderr = submit_proc.communicate()
    if submit_proc.returncode != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "submit curl failed")

    submitted = json.loads((stdout or "{}").strip() or "{}")
    status = submitted.get("status")
    task_id = submitted.get("provider_job_id") or seen_task_id
    output_url, preview_url, structured_error = _extract_output(submitted)

    print("final_job_status:", status)
    print("task_id:", task_id)
    print("output_url:", output_url)
    print("preview_url:", preview_url)
    if status in {"failed", "cancelled"}:
        print("error:", json.dumps(structured_error or {"message": submitted.get("error_message", "unknown error")}, ensure_ascii=True))

    return 0 if status == "complete" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runway smoke test")
    parser.add_argument("--task-id", dest="task_id", default=None, help="Existing Runway task ID to poll")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(ENV_PATH)

    key_source, runway_key = resolve_runway_key()
    print("RUNWAY_KEY_SOURCE:", key_source)
    print("RUNWAY_API_KEY:", json.dumps(safe_key_info(runway_key)))
    print("RUNWAY_MODEL:", os.getenv("RUNWAY_MODEL", ""))
    timeout_seconds = int(os.getenv("RUNWAY_TIMEOUT_SECONDS", "900") or "900")
    timeout_seconds = max(timeout_seconds, 900)
    print("RUNWAY_TIMEOUT_SECONDS:", timeout_seconds)

    if not runway_key:
        print("status: failed")
        print("error:", json.dumps({"error_type": "missing_api_key", "message": "RUNWAY key is not set"}))
        return 1

    if args.task_id:
        return poll_existing_task(args.task_id, timeout_seconds, runway_key)

    return run_new_job(timeout_seconds, runway_key)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    _backend_root = str(Path(__file__).resolve().parents[1])
    if _backend_root not in sys.path:
        sys.path.insert(0, _backend_root)
    from app.script_guard import require_live_spend_gate

    require_live_spend_gate(
        __file__,
        what="poll an existing Runway task OR submit one new Runway render job",
        exposure="poll is read-only; without --task-id submits 1 Runway render + polls",
        provider="runway",
    )
    raise SystemExit(main())
