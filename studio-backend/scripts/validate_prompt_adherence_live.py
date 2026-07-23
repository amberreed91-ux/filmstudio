#!/usr/bin/env python3
"""Validate staging + prompt-adherence wiring on an actual project shot.

Default mode is a no-network preflight: it temporarily seeds validation-only
staging/reference/standing-correction rows, creates an actual RenderJob payload,
records the evidence report, then removes those validation rows and the pending
job. Real provider submission requires --real-render and the explicit
--confirm-external-disclosure flag.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

from app.data.storage import get_storage
from app.models.standing_corrections import StandingCorrection
from app.services import render as render_module
from app.services.adherence_service import adherence_service
from app.services.keyframe_extraction_service import keyframe_extraction_service
from app.services.project_store import project_store
from app.services.render import render_service, set_storage
from app.services.render_retry_service import render_retry_service
from app.services.standing_corrections_service import standing_corrections_service
from app.services.video_asset_service import video_asset_service
from app.utils.helpers import derive_scene_id_from_shot_id


DEFAULT_PROJECT_ID = "project_3dba9330f43a"
DEFAULT_SHOT_ID = "scene_003_shot_001"
VALIDATION_SOURCE = "prompt_adherence_validation_20260723"
STYLE_REF_ID = "validation_style_scene003_20260723"
STANDING_CORRECTION_ID = "sc_validation_scene003_camera_20260723"


def _wire_runtime_services(storage) -> None:
    set_storage(storage)
    render_module._storage = storage
    render_retry_service.set_storage(storage)
    render_retry_service._adherence_service = adherence_service
    render_retry_service._keyframe_service = keyframe_extraction_service
    render_retry_service._video_asset_service = video_asset_service
    adherence_service._storage = storage
    keyframe_extraction_service._storage = storage
    keyframe_extraction_service._video_asset_service = video_asset_service
    video_asset_service._storage = storage
    standing_corrections_service._storage = storage


def _scene_for_shot(project: dict[str, Any], shot_id: str) -> dict[str, Any]:
    scene_id = derive_scene_id_from_shot_id(shot_id)
    summary = project.get("execution_summary") or {}
    for scene in summary.get("scenes") or []:
        if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
            return scene
    raise RuntimeError(f"Shot {shot_id} maps to missing scene {scene_id}")


def _resolve_validation_characters(scene: dict[str, Any]) -> list[str]:
    characters = [str(name).strip() for name in (scene.get("characters") or []) if str(name).strip()]
    if len(characters) < 2:
        raise RuntimeError(
            "Validation shot must be multi-character; "
            f"scene {scene.get('scene_id')} has {characters!r}"
        )
    return characters[:2]


def _staging_prompt_for(name: str, index: int) -> str:
    upper = name.upper()
    if upper == "MAYA":
        return "keeps her shoulders guarded, remembering the betrayal"
    if upper == "DRE":
        return "cannot quite meet Maya's eyes, guilt held in his jaw"
    return (
        "holds a distinct readable position in the two-character blocking"
        if index == 0
        else "keeps a clear eyeline toward the other character"
    )


@contextmanager
def _validation_rows(storage, *, project_id: str, shot_id: str, scene: dict[str, Any]):
    scene_id = str(scene.get("scene_id") or derive_scene_id_from_shot_id(shot_id))
    seeded: list[str] = []
    characters = _resolve_validation_characters(scene)

    try:
        for index, name in enumerate(characters):
            char = storage.get_character_by_name(project_id, name)
            if not char:
                raise RuntimeError(f"Missing character record for {name}")
            staging_prompt = _staging_prompt_for(name, index)
            storage.save_character_staging({
                "character_id": char["id"],
                "scene_id": scene_id,
                "shot_id": shot_id,
                "staging_prompt": staging_prompt,
                "source": VALIDATION_SOURCE,
            })
            seeded.append(f"staging:{name}")

        storage.save_reference_asset({
            "ref_id": STYLE_REF_ID,
            "project_id": project_id,
            "kind": "style",
            "image_url": "https://example.com/style-reference-placeholder.png",
            "source_shot_id": "scene_001_shot_001",
            "created_at": "2026-07-23T00:00:00",
        })
        seeded.append("style_reference")

        storage.save_standing_correction(StandingCorrection(
            correction_id=STANDING_CORRECTION_ID,
            project_id=project_id,
            slot="camera",
            trigger_json={"shot_id": shot_id},
            injection_text="Two-shot staging: both characters visible with readable eyelines",
            confidence=0.5,
            hits=0,
            misses=0,
            status="active",
        ).model_dump(mode="json"))
        seeded.append("standing_correction")

        yield seeded
    finally:
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM character_stagings WHERE source = ?",
                (VALIDATION_SOURCE,),
            )
            cursor.execute(
                "DELETE FROM reference_assets WHERE ref_id = ?",
                (STYLE_REF_ID,),
            )
            cursor.execute(
                "DELETE FROM standing_corrections WHERE correction_id = ?",
                (STANDING_CORRECTION_ID,),
            )
            conn.commit()


def _cleanup_job(storage, job_id: str) -> None:
    try:
        render_service.delete_job(job_id)
    except Exception:
        try:
            storage.delete_job(job_id)
        except Exception:
            pass


def _attempt_rows(storage, *, project_id: str, shot_id: str, job_id: str) -> list[dict[str, Any]]:
    attempts = storage.list_render_attempts(project_id=project_id, shot_id=shot_id)
    if attempts and "job_id" not in attempts[0]:
        return attempts
    return [row for row in attempts if row.get("job_id") == job_id]


def _keyframe_rows(storage, *, shot_id: str, job_id: str) -> list[dict[str, Any]]:
    asset_id = f"{shot_id}_{job_id}"
    if not hasattr(storage, "list_video_keyframes_for_asset"):
        return []
    rows = storage.list_video_keyframes_for_asset(asset_id)
    return [
        row.model_dump(mode="json") if hasattr(row, "model_dump") else dict(row)
        for row in rows
    ]


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.real_render and not args.confirm_external_disclosure:
        raise SystemExit(
            "--real-render sends project prompt/staging data to an external "
            "provider. Re-run with --confirm-external-disclosure only after "
            "the user has explicitly approved that disclosure."
        )

    storage = get_storage("sqlite")
    _wire_runtime_services(storage)

    project = project_store.get_project(args.project_id)
    if not isinstance(project, dict):
        raise RuntimeError(f"Project not found: {args.project_id}")
    scene = _scene_for_shot(project, args.shot_id)

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = BACKEND_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with _validation_rows(
        storage,
        project_id=args.project_id,
        shot_id=args.shot_id,
        scene=scene,
    ) as seeded:
        job = render_service.create_job(
            project_id=args.project_id,
            shot_id=args.shot_id,
            provider=args.provider,
            prompt=args.prompt,
            parameters={
                "structured_prompt": True,
                "duration": args.duration,
                "ratio": args.ratio,
            },
        )

        created_prompt = job.input_payload.prompt
        created_slots = dict(job.input_payload.parameters.get("prompt_slots") or {})
        consistency_payload = (
            job.input_payload.consistency_payload.model_dump(mode="json")
            if job.input_payload.consistency_payload
            else None
        )

        started = time.time()
        submitted = job
        submission_exception = None
        if args.real_render:
            try:
                submitted = await asyncio.wait_for(
                    render_service.submit_job(job.id),
                    timeout=args.submit_timeout_seconds,
                )
            except Exception as exc:
                submission_exception = exc
                refreshed = storage.get_job(job.id)
                submitted = refreshed or job
        elapsed = time.time() - started

        output_url = submitted.output_payload.asset_url if submitted.output_payload else ""
        report = {
            "validation_date": "2026-07-23",
            "mode": "real_render" if args.real_render else "preflight_no_network",
            "project_id": args.project_id,
            "scene_id": scene.get("scene_id"),
            "shot_id": args.shot_id,
            "scene_characters": scene.get("characters") or [],
            "seeded": seeded,
            "job_id": job.id,
            "provider": submitted.provider,
            "provider_job_id": submitted.provider_job_id,
            "status": submitted.status,
            "error_message": submitted.error_message,
            "submission_exception": str(submission_exception) if submission_exception else None,
            "elapsed_seconds": round(elapsed, 2),
            "output_url": output_url,
            "local_prompt_before_provider_merge": created_prompt,
            "provider_prompt_after_submit": submitted.input_payload.prompt if submitted.input_payload else "",
            "prompt_slots": created_slots,
            "consistency_payload": consistency_payload,
            "standing_correction_before_cleanup": storage.get_standing_correction(STANDING_CORRECTION_ID),
            "attempts_for_job": _attempt_rows(
                storage,
                project_id=args.project_id,
                shot_id=args.shot_id,
                job_id=job.id,
            ),
            "keyframes": _keyframe_rows(storage, shot_id=args.shot_id, job_id=job.id),
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        if not args.real_render:
            _cleanup_job(storage, job.id)

        return {
            "report": str(report_path),
            "mode": report["mode"],
            "job_id": job.id,
            "status": submitted.status,
            "output_url_present": bool(output_url),
            "attempts_for_job": len(report["attempts_for_job"]),
            "keyframes": len(report["keyframes"]),
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--shot-id", default=DEFAULT_SHOT_ID)
    parser.add_argument("--provider", default="runway")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--ratio", default="1280:720")
    parser.add_argument("--submit-timeout-seconds", type=float, default=420.0)
    parser.add_argument(
        "--report",
        default="outputs/real_render_validation/prompt_adherence_live_validation.json",
    )
    parser.add_argument("--real-render", action="store_true")
    parser.add_argument("--confirm-external-disclosure", action="store_true")
    return parser.parse_args()


def main() -> None:
    result = asyncio.run(_run(_parse_args()))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
