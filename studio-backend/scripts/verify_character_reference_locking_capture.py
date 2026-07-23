from __future__ import annotations

import asyncio
import json
import tempfile
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.storage import DatabaseStorage
from app.models import RenderJobOutput
from app.services import render as render_module
from app.services.character_visual_reference_service import project_store as reference_project_store
from app.services.render import RenderService


PROJECT_ID = "capture-character-locking"
CHARACTER_NAME = "Maya"
FIRST_SHOT_ID = "scene_001_shot_001"
SECOND_SHOT_ID = "scene_001_shot_002"
STORYBOARD_IMAGE_URL = "/previs-assets/capture-character-locking/maya-storyboard.png"
CANONICAL_IMAGE_URL = "https://cdn.example.test/capture/maya-post-render-reference.jpg"


def _project_state(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "title": "Character Reference Locking Capture",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "heading": "INT. HALLWAY - NIGHT",
                    "characters": [CHARACTER_NAME],
                    "text": "Maya crosses the hallway, carrying the emotional residue of the prior shot.",
                }
            ]
        },
    }


class CaptureAdapter:
    def __init__(self, captures: list[dict]):
        self.captures = captures

    async def submit_job(self, job):
        refs = []
        payload = job.input_payload.consistency_payload if job.input_payload else None
        if payload:
            refs = [ref.model_dump(mode="json") for ref in payload.refs]
        self.captures.append(
            {
                "job_id": job.id,
                "shot_id": job.shot_id,
                "provider": job.provider,
                "reference_images_seen_by_adapter": [ref["image_url"] for ref in refs],
                "reference_payload_refs": refs,
            }
        )
        job.provider_job_id = f"local-capture-{job.id}"
        job.status = "complete"
        job.progress = 100
        job.output_payload = RenderJobOutput(
            asset_url=f"https://cdn.example.test/capture/{job.shot_id}.mp4",
            thumbnail_url=CANONICAL_IMAGE_URL if job.shot_id == FIRST_SHOT_ID else None,
            metadata={"local_character_locking_capture": True},
        )
        job.completed_at = datetime.now().isoformat()
        return job


async def _no_op_completion_hook(job) -> None:
    return None


async def _passing_quality_hook(job) -> None:
    job.metadata = dict(job.metadata or {})
    job.metadata["adherence_review"] = {
        "verdict": "pass",
        "failed_slots": [],
        "outcome": "accepted",
    }


async def main() -> dict:
    storage_path = tempfile.mkdtemp(prefix="studio-character-locking-")
    storage = DatabaseStorage(storage_path)
    render_module.set_storage(storage)
    render_module.project_store.get_project = _project_state
    reference_project_store.get_project = _project_state
    render_module._run_continuity_review = _no_op_completion_hook
    render_module._run_render_quality_check = _passing_quality_hook

    storage.save_character(
        PROJECT_ID,
        CHARACTER_NAME,
        {"visual_prompt_summary": "short dark hair, blue jacket, tired watchful eyes"},
    )
    storage.save_previs_image(
        project_id=PROJECT_ID,
        scene_id="scene_001",
        shot_id=FIRST_SHOT_ID,
        image_path=STORYBOARD_IMAGE_URL,
        job_id="storyboard_scene_001_shot_001_dashscope",
        status="complete",
        prompt_used="Maya storyboard reference prompt",
        fallback=False,
    )

    adapter_captures: list[dict] = []
    render_module.get_adapter = lambda provider, config: CaptureAdapter(adapter_captures)

    service = RenderService()
    first = service.create_job(
        project_id=PROJECT_ID,
        shot_id=FIRST_SHOT_ID,
        provider="happyhorse",
        prompt="Maya turns toward the hallway window in a tense medium shot.",
    )
    character = storage.get_character_by_name(PROJECT_ID, CHARACTER_NAME)
    provisional_before_submit = storage.get_character_reference_lock(
        PROJECT_ID,
        character["id"],
        "provisional",
    )
    first_done = await service.submit_job(first.id)
    locked_after_first = storage.get_character_reference_lock(PROJECT_ID, character["id"], "locked")
    superseded_after_first = storage.list_character_reference_locks(
        PROJECT_ID,
        [character["id"]],
        "superseded",
    )

    second = service.create_job(
        project_id=PROJECT_ID,
        shot_id=SECOND_SHOT_ID,
        provider="happyhorse",
        prompt="Maya crosses the hallway with the same face, jacket, and guarded stillness.",
    )
    second_done = await service.submit_job(second.id)

    evidence = {
        "status": "pass",
        "storage_path": storage_path,
        "first_job": {
            "job_id": first_done.id,
            "shot_id": first_done.shot_id,
            "provider": first.provider,
            "submitted_provider": first_done.provider,
            "provider_job_id": first_done.provider_job_id,
            "provisional_reference_used": bool(provisional_before_submit),
        },
        "provisional_before_submit": provisional_before_submit,
        "locked_after_first_render": locked_after_first,
        "superseded_after_first_render": superseded_after_first,
        "second_job": {
            "job_id": second_done.id,
            "shot_id": second_done.shot_id,
            "provider": second.provider,
            "submitted_provider": second_done.provider,
            "provider_job_id": second_done.provider_job_id,
            "consistency_payload": (
                second.input_payload.consistency_payload.model_dump(mode="json")
                if second.input_payload.consistency_payload
                else None
            ),
        },
        "adapter_captures": adapter_captures,
        "proof": {
            "first_job_used_provisional_storyboard_reference": any(
                STORYBOARD_IMAGE_URL in capture.get("reference_images_seen_by_adapter", [])
                and capture.get("job_id") == first_done.id
                for capture in adapter_captures
            ),
            "provisional_promoted_to_locked": bool(
                locked_after_first
                and locked_after_first.get("image_url") == CANONICAL_IMAGE_URL
                and superseded_after_first
            ),
            "second_job_used_canonical_reference": any(
                CANONICAL_IMAGE_URL in capture.get("reference_images_seen_by_adapter", [])
                and capture.get("job_id") == second_done.id
                for capture in adapter_captures
            ),
            "paid_provider_call_made": False,
        },
    }
    if not (
        evidence["proof"]["first_job_used_provisional_storyboard_reference"]
        and evidence["proof"]["provisional_promoted_to_locked"]
        and evidence["proof"]["second_job_used_canonical_reference"]
    ):
        evidence["status"] = "fail"

    report_dir = Path(__file__).resolve().parents[1] / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "character_reference_locking_capture.json"
    report_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    evidence["report_path"] = str(report_path)
    return evidence


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main()), indent=2, sort_keys=True))
