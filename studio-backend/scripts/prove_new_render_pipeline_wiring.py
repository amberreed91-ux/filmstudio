#!/usr/bin/env python3
"""Run one fresh hosted render and storyboard capture for pipeline wiring proof."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
CAPTURE_ROOT = BACKEND_ROOT / "outputs" / "real_render_validation"
PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_002"
SHOT_ID = f"{SCENE_ID}_shot_001"
PROOF_CORRECTION_ID = "sc_proof_20260723_fresh_scene002_camera"
PROOF_STAGING_ID = "cstg_proof_20260723_fresh_maya_scene002"


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_env() -> None:
    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _local_output_path(output_url: str) -> str | None:
    if output_url.startswith("/outputs/"):
        return str(BACKEND_ROOT / output_url.removeprefix("/"))
    if output_url.startswith("/previs-assets/"):
        return str(BACKEND_ROOT / "outputs" / "previs" / output_url.removeprefix("/previs-assets/"))
    return None


def _read_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _seed_proof_rows(storage: Any) -> dict[str, Any]:
    from app.models import StudioProject

    storage.save_project(StudioProject(project_id=PROJECT_ID, title="Fresh pipeline proof"))

    maya = storage.get_character_by_name(PROJECT_ID, "MAYA")
    if not maya:
        raise RuntimeError("MAYA character row is required for character staging proof")

    staging = storage.save_character_staging(
        {
            "id": PROOF_STAGING_ID,
            "character_id": maya["id"],
            "scene_id": SCENE_ID,
            "shot_id": SHOT_ID,
            "staging_prompt": (
                "proof-run staging: Maya holds near the broken curb, shoulders still, "
                "watching Dre before either of them moves"
            ),
            "appearance_override": None,
            "source": "fresh_pipeline_proof",
        }
    )

    correction = {
        "correction_id": PROOF_CORRECTION_ID,
        "project_id": PROJECT_ID,
        "slot": "camera",
        "trigger_json": {"shot_id": SHOT_ID},
        "injection_text": "Proof correction: hold the camera low and patient before movement.",
        "confidence": 0.91,
        "hits": 0,
        "misses": 0,
        "last_applied": None,
        "status": "active",
        "superseded_by": None,
    }
    if not storage.save_standing_correction(correction):
        raise RuntimeError("Failed to save proof standing correction")

    return {
        "character_id": maya["id"],
        "character_name": "MAYA",
        "character_staging": staging,
        "standing_correction": correction,
    }


async def _run_render(provider: str, duration: int) -> tuple[Any, dict[str, Any]]:
    import app.services.character_staging_service as character_staging_module
    import app.services.standing_corrections_service as standing_module
    from app.services.render import render_service

    trace: dict[str, Any] = {
        "character_staging_calls": [],
        "standing_corrections_calls": [],
    }

    original_resolve = character_staging_module.resolve_character_prompt
    original_inject = standing_module.standing_corrections_service.inject_into_slots

    def traced_resolve(character: dict[str, Any], scene_id: str, shot_id: str | None, storage: Any = None) -> str:
        result = original_resolve(character, scene_id, shot_id, storage)
        trace["character_staging_calls"].append(
            {
                "character_id": character.get("id"),
                "character_name": character.get("name"),
                "scene_id": scene_id,
                "shot_id": shot_id,
                "used_staging_text": "In this shot:" in result,
                "resolved_prompt": result,
            }
        )
        return result

    def traced_inject(project_id: str, slots: dict[str, str], shot_context: dict[str, Any], job_id: str | None = None) -> dict[str, list[str]]:
        before = dict(slots)
        applied = original_inject(project_id, slots, shot_context, job_id)
        trace["standing_corrections_calls"].append(
            {
                "project_id": project_id,
                "shot_context": dict(shot_context or {}),
                "job_id": job_id,
                "applied": applied,
                "before_slots": before,
                "after_slots": dict(slots),
            }
        )
        return applied

    character_staging_module.resolve_character_prompt = traced_resolve
    standing_module.standing_corrections_service.inject_into_slots = traced_inject
    try:
        job = render_service.create_job(
            project_id=PROJECT_ID,
            shot_id=SHOT_ID,
            provider=provider,
            prompt="",
            reference_assets=[],
            parameters={
                "duration": duration,
                "ratio": "16:9" if provider == "happyhorse" else "1280:720",
                "resolution": "720P",
                "structured_prompt": True,
            },
        )
        submitted = await render_service.submit_job(job.id)
        return submitted, trace
    finally:
        character_staging_module.resolve_character_prompt = original_resolve
        standing_module.standing_corrections_service.inject_into_slots = original_inject


def _run_storyboard() -> dict[str, Any]:
    from main import app

    client = TestClient(app)
    response = client.post(
        f"/api/f51/studio/projects/{PROJECT_ID}/scenes/{SCENE_ID}/storyboard",
        params={"provider": "qwen-image-max", "shot_number": 1},
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Storyboard generation failed: {response.status_code} {response.text}")
    return response.json()


def _fetch_attempt(storage: Any, job_id: str) -> dict[str, Any] | None:
    try:
        attempts = storage.list_render_attempts(project_id=PROJECT_ID, shot_id=SHOT_ID)
    except Exception:
        return None
    for attempt in attempts:
        if str(attempt.get("job_id") or "") == job_id:
            return {key: _read_jsonish(value) for key, value in attempt.items()}
    return None


def _write_capture(
    *,
    capture_path: Path,
    log_path: Path,
    provider: str,
    duration: int,
    seeded: dict[str, Any],
    job: Any,
    render_trace: dict[str, Any],
    storyboard: dict[str, Any],
    storage: Any,
) -> dict[str, Any]:
    output_url = ""
    output_payload = None
    if job.output_payload:
        output_payload = job.output_payload.model_dump()
        output_url = str(job.output_payload.asset_url or "")

    storyboard_output = str(storyboard.get("image_url") or "")
    render_local_path = _local_output_path(output_url)
    storyboard_local_path = _local_output_path(storyboard_output)

    capture = {
        "schema_version": "fresh_pipeline_capture.v1",
        "capture_type": "fresh_real_render_and_previs_storyboard",
        "capture_status": "complete" if job.status == "complete" else "render_failed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "network_used": True,
        "old_scene003_capture_reused": False,
        "proof_seed_rows": seeded,
        "render": {
            "project_id": PROJECT_ID,
            "scene_id": SCENE_ID,
            "shot_id": SHOT_ID,
            "job_id": job.id,
            "provider": job.provider,
            "requested_provider": provider,
            "duration_seconds": duration,
            "status": job.status,
            "provider_job_id": job.provider_job_id,
            "output_url": output_url,
            "output_local_path": render_local_path,
            "output_local_exists": bool(render_local_path and Path(render_local_path).exists()),
            "error_message": job.error_message,
            "input_prompt": job.input_payload.prompt if job.input_payload else "",
            "input_parameters": job.input_payload.parameters if job.input_payload else {},
            "output_payload": output_payload,
        },
        "code_path_trace": render_trace,
        "standing_correction_after": storage.get_standing_correction(PROOF_CORRECTION_ID),
        "render_attempt": _fetch_attempt(storage, job.id),
        "storyboard": {
            **storyboard,
            "output_local_path": storyboard_local_path,
            "output_local_exists": bool(storyboard_local_path and Path(storyboard_local_path).exists()),
        },
        "artifacts": {
            "capture_path": str(capture_path),
            "log_path": str(log_path),
            "render_local_path": render_local_path,
            "storyboard_local_path": storyboard_local_path,
        },
    }
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text(json.dumps(capture, indent=2, ensure_ascii=True), encoding="utf-8")
    return capture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="happyhorse", choices=["happyhorse", "runway"])
    parser.add_argument("--duration", type=int, default=3)
    args = parser.parse_args()

    _load_env()
    os.environ.setdefault("ADHERENCE_AUTO_RETRY_MAX", "0")

    run_slug = _now_slug()
    log_path = CAPTURE_ROOT / f"fresh_pipeline_{run_slug}.log"
    capture_path = CAPTURE_ROOT / f"fresh_pipeline_capture_{run_slug}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )

    from main import storage

    seeded = _seed_proof_rows(storage)
    logging.info("FRESH_PIPELINE_PROOF_SEEDED project=%s scene=%s shot=%s", PROJECT_ID, SCENE_ID, SHOT_ID)

    job, render_trace = asyncio.run(_run_render(args.provider, args.duration))
    storyboard = _run_storyboard()
    capture = _write_capture(
        capture_path=capture_path,
        log_path=log_path,
        provider=args.provider,
        duration=args.duration,
        seeded=seeded,
        job=job,
        render_trace=render_trace,
        storyboard=storyboard,
        storage=storage,
    )

    print(json.dumps({
        "capture_status": capture["capture_status"],
        "capture_path": str(capture_path),
        "log_path": str(log_path),
        "render_job_id": job.id,
        "provider": job.provider,
        "provider_job_id": job.provider_job_id,
        "render_output_local_path": capture["artifacts"]["render_local_path"],
        "storyboard_output_local_path": capture["artifacts"]["storyboard_local_path"],
        "character_staging_calls": len(render_trace["character_staging_calls"]),
        "standing_corrections_calls": len(render_trace["standing_corrections_calls"]),
    }, indent=2))
    return 0 if job.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
