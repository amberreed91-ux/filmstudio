#!/usr/bin/env python3
"""Local full-scene pipeline probe for scene 003.

This probe uses no external providers. It creates tiny local mock shot renders,
adds synthetic per-shot dialogue audio while recording the CosyVoice/Qwen
instruction payloads, then runs the real scene stitcher with a manual
post-render soundtrack source.
"""
from __future__ import annotations

import asyncio
import json
import math
import wave
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, SoundtrackConfig
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.routes.audio import (
    _get_scene_data,
    _resolve_scene_dialogue_context,
    _resolve_scene_dialogue_lines,
    _resolve_scene_text,
)
from app.services.audio_pipeline_service import (
    COSYVOICE_DEFAULT_VOICE,
    COSYVOICE_MODEL,
    _build_dialogue_instruction,
    _dialogue_instruction_sources,
)
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.short_film_stitching_service import ShortFilmStitchingService


PROJECT_ID = "project_3dba9330f43a_mock_full_scene"
SOURCE_PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_003"
OUT_DIR = BACKEND_ROOT / "outputs" / "full_stack_probe" / "scene_003_full_scene_pipeline"
REPORT_PATH = BACKEND_ROOT / "outputs" / "full_stack_probe" / "scene_003_full_scene_pipeline_probe.json"


def _require_media_tools() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"Missing required media tool(s): {', '.join(missing)}")


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip()[:1000])


def _ffprobe(path: Path | str | None) -> dict[str, Any] | None:
    if not path:
        return None
    media_path = Path(path)
    if not media_path.exists():
        return {"error": f"missing file: {media_path}"}
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,duration",
            "-of",
            "json",
            str(media_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"error": (proc.stderr or proc.stdout).strip()}
    return json.loads(proc.stdout)


def _probe_duration(path: Path) -> float:
    probe = _ffprobe(path) or {}
    try:
        return float((probe.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _generate_video(path: Path, *, duration: float, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=640x360:d={duration}:r=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(path),
        ]
    )


def _generate_wav(path: Path, *, duration: float, frequency: int = 196) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=44100:duration={duration}",
            "-ac",
            "1",
            str(path),
        ]
    )


def _extract_audio_wav(media_path: Path, wav_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "wav",
            str(wav_path),
        ]
    )


def _goertzel_magnitude(samples: list[float], sample_rate: int, target_frequency: float) -> float:
    if not samples:
        return 0.0
    normalized_frequency = target_frequency / sample_rate
    coeff = 2.0 * math.cos(2.0 * math.pi * normalized_frequency)
    prev = 0.0
    prev2 = 0.0
    for sample in samples:
        current = sample + (coeff * prev) - prev2
        prev2 = prev
        prev = current
    power = (prev2 * prev2) + (prev * prev) - (coeff * prev * prev2)
    return math.sqrt(max(power, 0.0)) / len(samples)


def _audio_frequency_evidence(media_path: Path, *, working_dir: Path) -> dict[str, Any]:
    wav_path = working_dir / "final_audio_analysis.wav"
    try:
        _extract_audio_wav(media_path, wav_path)
        with wave.open(str(wav_path), "rb") as wav:
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            raw = wav.readframes(frame_count)
            sample_width = wav.getsampwidth()
        if sample_width != 2:
            return {"error": f"unsupported sample width: {sample_width}"}
        samples = [
            int.from_bytes(raw[index:index + 2], byteorder="little", signed=True) / 32768.0
            for index in range(0, len(raw), 2)
        ]
        targets = {
            "manual_score_196hz": _goertzel_magnitude(samples, sample_rate, 196.0),
            "dialogue_line_1_440hz": _goertzel_magnitude(samples, sample_rate, 440.0),
            "dialogue_line_2_520hz": _goertzel_magnitude(samples, sample_rate, 520.0),
        }
        strongest = max(targets.values()) if targets else 0.0
        threshold = strongest * 0.08
        return {
            "analysis_wav": str(wav_path),
            "sample_rate": sample_rate,
            "duration_seconds": frame_count / sample_rate if sample_rate else 0.0,
            "target_magnitudes": targets,
            "detected": {
                name: magnitude > threshold and magnitude > 0.0001
                for name, magnitude in targets.items()
            },
            "threshold": threshold,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _assert_full_scene_probe_complete(report: dict[str, Any]) -> None:
    result = report.get("result") if isinstance(report.get("result"), dict) else {}
    if result.get("status") != "complete":
        raise RuntimeError(f"scene pipeline did not complete: {result.get('status')}")
    stitch = result.get("stitch") if isinstance(result.get("stitch"), dict) else {}
    if stitch.get("clip_count", 0) < 2:
        raise RuntimeError("scene pipeline did not stitch multiple shots")
    if result.get("score_ambient_provider") != "manual_post_render":
        raise RuntimeError("scene pipeline did not use manual_post_render score/ambient")
    if result.get("soundtrack_status") != "manual_post_render":
        raise RuntimeError("scene pipeline did not report manual_post_render soundtrack status")
    shots = result.get("shots") if isinstance(result.get("shots"), list) else []
    if len(shots) < 2:
        raise RuntimeError("scene pipeline did not report multiple generated shots")
    for shot in shots:
        if not isinstance(shot, dict):
            raise RuntimeError("scene shot was not recorded as an object")
        consistency = shot.get("consistency") if isinstance(shot.get("consistency"), dict) else {}
        if consistency.get("attached") is not True or not consistency.get("primary_reference_url"):
            raise RuntimeError("scene shot is missing visual consistency evidence")
    saved_assembly_rows = (
        report.get("saved_assembly_rows")
        if isinstance(report.get("saved_assembly_rows"), list)
        else []
    )
    if not any(
        isinstance(row, dict)
        and row.get("scene_id") == SCENE_ID
        and row.get("status") == "complete"
        and row.get("score_ambient_provider") == "manual_post_render"
        for row in saved_assembly_rows
    ):
        raise RuntimeError("scene pipeline assembly persistence evidence missing")

    audio_calls = report.get("audio_calls") if isinstance(report.get("audio_calls"), list) else []
    if len(audio_calls) < 2:
        raise RuntimeError("probe expected at least two per-shot audio calls")
    for call in audio_calls:
        if not isinstance(call, dict):
            raise RuntimeError("audio call was not recorded as an object")
        if call.get("score_ambient_provider") != "none":
            raise RuntimeError("per-shot score/ambient generation was not skipped")
        instructions = call.get("line_instructions") if isinstance(call.get("line_instructions"), list) else []
        if not instructions or not any(item.get("instruction") for item in instructions if isinstance(item, dict)):
            raise RuntimeError("CosyVoice per-line instruction evidence missing")
        if not any(
            isinstance(item, dict)
            and isinstance(item.get("instruction_sources"), dict)
            and item["instruction_sources"].get("emotional_subtext", {}).get("source")
            in {"line.emotional_subtext", "line_text_inference"}
            for item in instructions
        ):
            raise RuntimeError("CosyVoice per-line instruction source evidence missing")

    final_probe = report.get("final_probe") if isinstance(report.get("final_probe"), dict) else {}
    streams = final_probe.get("streams") if isinstance(final_probe.get("streams"), list) else []
    if not any(isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams):
        raise RuntimeError("final scene artifact is missing an audio stream")

    frequency_evidence = (
        report.get("final_audio_frequency_evidence")
        if isinstance(report.get("final_audio_frequency_evidence"), dict)
        else {}
    )
    detected = frequency_evidence.get("detected") if isinstance(frequency_evidence.get("detected"), dict) else {}
    required = {"manual_score_196hz", "dialogue_line_1_440hz", "dialogue_line_2_520hz"}
    missing = sorted(name for name in required if detected.get(name) is not True)
    if missing:
        raise RuntimeError(f"final audio missing expected score/dialogue frequency evidence: {', '.join(missing)}")


def _merge_tone(video_path: Path, out_path: Path, *, frequency: int) -> None:
    duration = max(0.5, _probe_duration(video_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=44100:duration={duration}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
    )


class LocalRenderService:
    def __init__(self, renders_dir: Path) -> None:
        self.renders_dir = renders_dir
        self.created: list[dict[str, Any]] = []
        self.jobs: dict[str, RenderJobModel] = {}
        self.consistency_payload = ConsistencyPayload(
            project_id=PROJECT_ID,
            mode="identity_lock",
            refs=[
                ReferenceAsset(
                    ref_id="dre-full-probe",
                    kind="character_full",
                    image_url="/outputs/full_stack_probe/scene_003_full_scene_pipeline/reference/dre-full.png",
                    project_id=PROJECT_ID,
                ),
                ReferenceAsset(
                    ref_id="dre-face-probe",
                    kind="character_face",
                    image_url="/outputs/full_stack_probe/scene_003_full_scene_pipeline/reference/dre-face.png",
                    project_id=PROJECT_ID,
                ),
            ],
            weights={"dre-full-probe": 1.0, "dre-face-probe": 0.55},
        )

    def create_job(self, **kwargs: Any) -> RenderJobModel:
        index = len(self.created) + 1
        shot_id = str(kwargs["shot_id"])
        path = self.renders_dir / f"{shot_id}_mock_render.mp4"
        _generate_video(path, duration=2.0 + (index * 0.5), color="0x202838" if index == 1 else "0x382820")
        job = RenderJobModel(
            id=f"mock-render-{index}",
            project_id=str(kwargs["project_id"]),
            shot_id=shot_id,
            provider=kwargs.get("provider") or "mock_happyhorse",
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=str(kwargs.get("prompt") or ""),
                referenceAssets=kwargs.get("reference_assets") or [],
                parameters=kwargs.get("parameters") or {},
                consistency_payload=self.consistency_payload,
            ),
            output_payload=RenderJobOutput(asset_url=f"/outputs/full_stack_probe/scene_003_full_scene_pipeline/renders/{path.name}"),
        )
        self.created.append(kwargs)
        self.jobs[job.id] = job
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        self.jobs[job_id].status = "complete"
        return self.jobs[job_id]

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        return self.jobs[job_id]


class LocalCosyVoiceAudioService:
    def __init__(self, audio_dir: Path) -> None:
        self.audio_dir = audio_dir
        self.calls: list[dict[str, Any]] = []

    async def generate_full_pipeline(self, **kwargs: Any) -> dict[str, Any]:
        video_path = Path(kwargs["video_path"])
        shot_id = str(kwargs["scene_id"])
        lines = kwargs.get("dialogue_lines") if isinstance(kwargs.get("dialogue_lines"), list) else []
        scene_context = kwargs.get("scene_context") if isinstance(kwargs.get("scene_context"), dict) else {}
        line_instructions = []
        for idx, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            instruction, mode = _build_dialogue_instruction(
                line,
                model=COSYVOICE_MODEL,
                voice=COSYVOICE_DEFAULT_VOICE,
                scene_context=scene_context,
            )
            line_instructions.append(
                {
                    "line": idx,
                    "character": line.get("character"),
                    "text": line.get("text"),
                    "voice": COSYVOICE_DEFAULT_VOICE,
                    "model": COSYVOICE_MODEL,
                    "instruction_mode": mode,
                    "instruction": instruction,
                    "instruction_sources": _dialogue_instruction_sources(line, scene_context),
                }
            )

        final_path = self.audio_dir / f"{shot_id}_cosyvoice_mock_audio.mp4"
        _merge_tone(video_path, final_path, frequency=440 + (len(self.calls) * 80))
        call = {
            "shot_id": shot_id,
            "score_ambient_provider": kwargs.get("score_ambient_provider"),
            "line_instructions": line_instructions,
            "input_probe": _ffprobe(video_path),
            "final_probe": _ffprobe(final_path),
        }
        self.calls.append(call)
        return {
            "job_id": f"mock-audio-{shot_id}",
            "dialogue_provider": "cosyvoice",
            "score_ambient_provider": kwargs.get("score_ambient_provider") or "none",
            "steps": {
                "dialogue": {
                    "provider": "cosyvoice",
                    "line_instructions": line_instructions,
                }
            },
            "final_video_path": str(final_path),
            "final_video_url": f"/outputs/full_stack_probe/scene_003_full_scene_pipeline/audio/{final_path.name}",
        }


def _project() -> dict[str, Any]:
    scene = _get_scene_data(SOURCE_PROJECT_ID, SCENE_ID) or {}
    scene_text = _resolve_scene_text(SOURCE_PROJECT_ID, SCENE_ID)
    dialogue_lines = _resolve_scene_dialogue_lines(SOURCE_PROJECT_ID, SCENE_ID) or []
    normalized_lines: list[dict[str, str]] = []
    shot_ids = ["shot_scene_003_001", "shot_scene_003_002"]
    for index, line in enumerate(dialogue_lines[:2]):
        if not isinstance(line, dict):
            continue
        copied = {str(key): str(value) for key, value in line.items() if value is not None}
        copied["scene_id"] = SCENE_ID
        copied["shot_id"] = shot_ids[min(index, len(shot_ids) - 1)]
        normalized_lines.append(copied)

    if not normalized_lines:
        normalized_lines = [
            {
                "line_id": "scene_003_probe_dlg_01",
                "scene_id": SCENE_ID,
                "shot_id": "shot_scene_003_001",
                "character": "DRE",
                "text": "You heard that too, right?",
                "emotional_subtext": "casual concern",
            }
        ]
    if len(normalized_lines) < 2:
        normalized_lines.append(
            {
                "line_id": "scene_003_probe_dlg_02",
                "scene_id": SCENE_ID,
                "shot_id": "shot_scene_003_002",
                "character": normalized_lines[0].get("character", "DRE"),
                "text": "Keep your voice down.",
                "emotional_subtext": "controlled unease",
                "pacing_tag": "low and clipped",
            }
        )

    return {
        "project_id": PROJECT_ID,
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": SCENE_ID,
                    "description": scene_text or str(scene.get("description") or ""),
                    "emotional_tone": str(scene.get("emotional_tone") or scene.get("tone") or "restrained concern"),
                    "characters": scene.get("characters") if isinstance(scene.get("characters"), list) else ["DRE"],
                    "shots": [
                        {
                            "shot_id": "shot_scene_003_001",
                            "description": "Wide setup of the scene beat, holding the emotional pressure.",
                            "duration_seconds": 2.5,
                        },
                        {
                            "shot_id": "shot_scene_003_002",
                            "description": "Reverse angle that carries the response with controlled unease.",
                            "duration_seconds": 2.5,
                        },
                    ],
                }
            ],
            "dialogue_lines": normalized_lines,
        },
    }


async def _run_probe() -> dict[str, Any]:
    _require_media_tools()
    renders_dir = OUT_DIR / "renders"
    audio_dir = OUT_DIR / "audio"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    soundtrack_path = OUT_DIR / "manual_scene_score.wav"
    _generate_wav(soundtrack_path, duration=8.0, frequency=196)

    render = LocalRenderService(renders_dir)
    audio = LocalCosyVoiceAudioService(audio_dir)
    stitcher = ShortFilmStitchingService(outputs_root=BACKEND_ROOT / "outputs")
    service = SceneProductionPipelineService(
        render_svc=render,
        audio_svc=audio,
        stitching_svc=stitcher,
        backend_root=BACKEND_ROOT,
    )

    saved_projects: list[dict[str, Any]] = []
    result = await service.generate_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=_project(),
        overwrite=True,
        score_ambient_provider="manual_post_render",
        soundtrack_config=SoundtrackConfig(
            enabled=True,
            audio_source_type="local_file",
            local_audio_path=str(soundtrack_path),
            volume=0.18,
            fade_in_seconds=0.2,
            fade_out_seconds=0.4,
            loop_to_duration=True,
            style_label="manual_probe_score",
        ),
        save_project=lambda updated: saved_projects.append(updated) or updated,
    )

    output_path = Path(result.get("stitch", {}).get("output_path") or "")
    return {
        "mode": "local-mock",
        "network_used": False,
        "project_id": PROJECT_ID,
        "source_project_id": SOURCE_PROJECT_ID,
        "scene_id": SCENE_ID,
        "scene_003_source_planned_shot_count": 1,
        "probe_shot_count": 2,
        "result": result,
        "render_jobs_created": [
            {
                "shot_id": call.get("shot_id"),
                "provider": call.get("provider") or "mock_happyhorse",
                "reference_assets": call.get("reference_assets") or [],
            }
            for call in render.created
        ],
        "audio_calls": audio.calls,
        "saved_render_rows": (
            saved_projects[-1].get("execution_summary", {}).get("one_button_render_jobs", [])
            if saved_projects else []
        ),
        "saved_assembly_rows": (
            saved_projects[-1].get("execution_summary", {}).get("scene_pipeline_assemblies", [])
            if saved_projects else []
        ),
        "manual_soundtrack": {
            "path": str(soundtrack_path),
            "probe": _ffprobe(soundtrack_path),
        },
        "final_probe": _ffprobe(output_path),
        "final_audio_frequency_evidence": _audio_frequency_evidence(output_path, working_dir=OUT_DIR),
        "artifact_path": str(output_path),
    }


def main() -> None:
    report = asyncio.run(_run_probe())
    _assert_full_scene_probe_complete(report)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(REPORT_PATH), "artifact_path": report["artifact_path"]}, indent=2))


if __name__ == "__main__":
    main()
