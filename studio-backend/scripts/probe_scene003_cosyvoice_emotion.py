#!/usr/bin/env python3
"""Probe scene 003 CosyVoice/Qwen-TTS emotional instructions.

Dry-run mode is local only: it records the exact dialogue lines and delivery
instructions that would be sent to DashScope.

Live mode sends project dialogue text and instruction text to DashScope. It is
therefore deliberately double-gated:

    LIVE_DASHSCOPE_TTS_PROBE_APPROVED=I_APPROVE_EXTERNAL_TTS \
      .venv/bin/python scripts/probe_scene003_cosyvoice_emotion.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.routes.audio import (
    _get_scene_data,
    _resolve_scene_dialogue_context,
    _resolve_scene_dialogue_lines,
    _resolve_scene_text,
)
from app.services.audio_pipeline_service import (
    COSYVOICE_DEFAULT_VOICE,
    COSYVOICE_MODEL,
    AudioPipelineService,
    _build_dialogue_instruction,
    _extract_dialogue_lines,
    _select_dialogue_lines_for_video_duration,
)


PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_003"
SHOT_ID = "shot_scene_003_001"
DEFAULT_VIDEO = Path(
    "outputs/renders/project_3dba9330f43a/"
    "job-20260717214531-bcea91bb-shot_scene_003_001_happyhorse_silent.mp4"
)
OUT_DIR = Path("outputs/full_stack_probe")
CONSENT_ENV = "LIVE_DASHSCOPE_TTS_PROBE_APPROVED"
CONSENT_VALUE = "I_APPROVE_EXTERNAL_TTS"


def _ffprobe(path: Path | str | None) -> dict[str, Any] | None:
    if not path:
        return None
    media_path = Path(path)
    if not media_path.exists():
        return {"error": f"missing file: {media_path}"}
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,duration",
        "-of",
        "json",
        str(media_path),
    ]
    try:
        return json.loads(subprocess.check_output(cmd, text=True))
    except Exception as exc:
        return {"error": str(exc)}


def _resolve_scene_inputs(video_path: Path) -> dict[str, Any]:
    scene = _get_scene_data(PROJECT_ID, SCENE_ID) or {}
    scene_text = _resolve_scene_text(PROJECT_ID, SCENE_ID)
    dialogue_lines = _resolve_scene_dialogue_lines(PROJECT_ID, SCENE_ID)
    dialogue_source = "execution_summary.dialogue_lines"
    if dialogue_lines is None:
        dialogue_source = "screenplay_extraction_after_placeholder_filter"
        dialogue_lines = _extract_dialogue_lines(scene_text, characters=scene.get("characters"))

    video_probe = _ffprobe(video_path) or {}
    video_duration = None
    try:
        video_duration = float((video_probe.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        video_duration = None

    selected_lines, selection_reason = _select_dialogue_lines_for_video_duration(
        dialogue_lines,
        video_duration,
    )
    scene_context = _resolve_scene_dialogue_context(scene)

    return {
        "scene": scene,
        "scene_context": scene_context,
        "dialogue_source": dialogue_source,
        "dialogue_lines": dialogue_lines,
        "selected_lines": selected_lines,
        "selection_reason": selection_reason,
        "video_probe": video_probe,
        "video_duration": video_duration,
    }


def _instruction_report(lines: list[dict[str, str]], scene_context: dict[str, Any]) -> list[dict[str, Any]]:
    reports = []
    for idx, line in enumerate(lines):
        instruction, mode = _build_dialogue_instruction(
            line,
            model=COSYVOICE_MODEL,
            voice=COSYVOICE_DEFAULT_VOICE,
            scene_context=scene_context,
        )
        reports.append(
            {
                "line": idx,
                "character": line.get("character"),
                "text": line.get("text"),
                "voice": COSYVOICE_DEFAULT_VOICE,
                "model": COSYVOICE_MODEL,
                "instruction_mode": mode,
                "instruction": instruction,
            }
        )
    return reports


async def _run_live(video_path: Path, variation_count: int) -> dict[str, Any]:
    inputs = _resolve_scene_inputs(video_path)
    service = AudioPipelineService()

    pipeline = await service.generate_full_pipeline(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        video_path=video_path,
        dialogue_lines=inputs["dialogue_lines"],
        scene_context=inputs["scene_context"],
    )

    variation_lines = inputs["dialogue_lines"][:variation_count]
    variation = await service.generate_shot_dialogue(
        project_id=PROJECT_ID,
        scene_id=f"{SCENE_ID}_emotion_variation",
        shot_id=f"{SHOT_ID}_emotion_variation",
        dialogue_lines=variation_lines,
        provider="cosyvoice",
        scene_context=inputs["scene_context"],
    )

    return {
        "mode": "live",
        "network_used": True,
        "external_service": "DashScope Qwen-TTS/CosyVoice",
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "shot_id": SHOT_ID,
        "dialogue_source": inputs["dialogue_source"],
        "selected_instruction_report": _instruction_report(
            inputs["selected_lines"],
            inputs["scene_context"],
        ),
        "variation_instruction_report": _instruction_report(
            variation_lines,
            inputs["scene_context"],
        ),
        "pipeline": pipeline,
        "variation": variation,
        "input_video_probe": inputs["video_probe"],
        "final_probe": _ffprobe(pipeline.get("final_video_path")),
    }


def _run_dry(video_path: Path, variation_count: int) -> dict[str, Any]:
    inputs = _resolve_scene_inputs(video_path)
    variation_lines = inputs["dialogue_lines"][:variation_count]
    return {
        "mode": "dry-run",
        "network_used": False,
        "external_service": "DashScope Qwen-TTS/CosyVoice",
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "shot_id": SHOT_ID,
        "dialogue_source": inputs["dialogue_source"],
        "selected_instruction_report": _instruction_report(
            inputs["selected_lines"],
            inputs["scene_context"],
        ),
        "variation_instruction_report": _instruction_report(
            variation_lines,
            inputs["scene_context"],
        ),
        "selection_reason": inputs["selection_reason"],
        "input_video_probe": inputs["video_probe"],
        "consent_required_for_live": {
            "flag": "--live",
            "env": f"{CONSENT_ENV}={CONSENT_VALUE}",
            "reason": "Live mode sends scene dialogue and instruction text to DashScope.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--variation-count", type=int, default=4)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.live:
        import os

        if os.environ.get(CONSENT_ENV) != CONSENT_VALUE:
            raise SystemExit(
                "Refusing live DashScope probe without explicit consent. Set "
                f"{CONSENT_ENV}={CONSENT_VALUE} and pass --live."
            )
        report = asyncio.run(_run_live(args.video, max(1, args.variation_count)))
        out_path = OUT_DIR / "scene_003_live_cosyvoice_emotion_probe.json"
    else:
        report = _run_dry(args.video, max(1, args.variation_count))
        out_path = OUT_DIR / "scene_003_dry_cosyvoice_emotion_probe.json"

    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(out_path.resolve()), "mode": report["mode"]}, indent=2))


if __name__ == "__main__":
    main()
