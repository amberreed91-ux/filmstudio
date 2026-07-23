"""Render the four-shot scene_002 CosyVoice audio proof from saved Runway clips.

This harness is intentionally an audio-performance proof, not the authoritative
script-faithful scene assembly. It uses four already-rendered silent clips and
speaker-turn dialogue groups to test directed CosyVoice delivery, SSML timing,
pre_supplied reuse, and media stitching. It does not follow the stored previs
scene_002 shot count, and it does not create lip-synced picture.
"""
from __future__ import annotations

import asyncio
import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")
os.environ.setdefault("COSYVOICE_MODEL", "cosyvoice-v3-flash")
os.environ.setdefault(
    "COSYVOICE_VOICE_MAP_JSON",
    json.dumps(
        {
            "MAYA": "longwanjun_v3",
            "DRE": "longanyang",
            "default": "longwanjun_v3",
        }
    ),
)

from app.data.storage import get_storage
from app.services.audio_pipeline_service import (
    COSYVOICE_MODEL,
    AudioPipelineService,
    TrackStatus,
    _build_dialogue_instruction,
    _dialogue_instruction_sources,
    _dialogue_performance_direction,
    _dialogue_tts_text,
    _resolve_cosyvoice_voice_id,
)
from app.services.scene_assembly_service import SceneAssemblyService
from app.utils.helpers import derive_scene_id_from_shot_id


PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_002"
SOURCE_DIR = BACKEND_ROOT / "outputs" / "real_render_validation"
PRE_SUPPLIED_DIR = BACKEND_ROOT / "outputs" / "audio" / PROJECT_ID / SCENE_ID / "pre_supplied"
EXPECTED_SHOT_IDS = [
    "shot_scene_002_001",
    "shot_scene_002_002",
    "shot_scene_002_003",
    "shot_scene_002_004",
]
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")
SCENE_002_DIALOGUE_CONTEXT = {
    "audio_tension": "betrayal at gunpoint, intimate rather than operatic",
    "director_note": (
        "Keep every line psychologically specific: two former friends trying not "
        "to show the full damage until the scene makes that impossible."
    ),
}
SCENE_002_LINE_DIRECTIONS: dict[str, dict[str, str]] = {
    "I need you to understand something.": {
        "emotional_subtext": (
            "tense and controlled, trying to justify himself before he has said "
            "the unforgivable part"
        ),
        "pacing_tag": "low, careful, held in the throat",
    },
    "That's funny.": {
        "emotional_subtext": "bitter and flat, not actually amused",
        "pacing_tag": "short, dry, almost no lift on funny",
    },
    "What?": {
        "emotional_subtext": "caught off guard, defensive before he understands the accusation",
        "pacing_tag": "a small beat before the word, clipped",
        "ssml_text": '<speak><break time="250ms"/>What?</speak>',
    },
    "You always say that right before you do something you know is wrong.": {
        "emotional_subtext": (
            "quiet recognition, wounded by the pattern more than surprised by it"
        ),
        "pacing_tag": "measured, lets the accusation land without raising volume",
    },
    "Things changed.": {
        "emotional_subtext": "thin defensive cover, trying to make betrayal sound practical",
        "pacing_tag": "small, compressed, no flourish",
    },
    "No. People changed.": {
        "emotional_subtext": "controlled hurt hardening into moral clarity",
        "pacing_tag": "separate the correction from the verdict",
    },
    "There's not enough. You have to understand that. There is not enough for everyone.": {
        "emotional_subtext": (
            "strained rationalizing, almost pleading underneath the threat, as if "
            "he needs Maya to absolve him"
        ),
        "pacing_tag": "fractured, the second 'not enough' heavier and more exposed",
        "ssml_text": (
            '<speak>There&apos;s not enough.<break time="300ms"/> '
            "You have to understand that. "
            '<break time="250ms"/>There is not enough for everyone.</speak>'
        ),
    },
    "So you decided that for all of us.": {
        "emotional_subtext": (
            "low disbelief turning into indictment, carrying the betrayal without melodrama"
        ),
        "pacing_tag": "steady, with the pressure falling after 'you'",
        "ssml_text": (
            '<speak>So you<break time="180ms"/> decided that for all of us.</speak>'
        ),
    },
    "Someone had to.": {
        "emotional_subtext": (
            "ashamed but forcing himself to sound resolved, the justification already collapsing"
        ),
        "pacing_tag": "a real pause before the line, then quiet and final",
        "ssml_text": '<speak><break time="450ms"/>Someone had to.</speak>',
    },
    "I remember dying. So why am I here?": {
        "emotional_subtext": "quiet and disoriented, not performative, still inside the shock",
        "pacing_tag": "soft, searching, with air between memory and question",
    },
}


def _directed_dialogue_lines(lines: Any) -> list[dict[str, str]]:
    directed: list[dict[str, str]] = []
    if not isinstance(lines, list):
        return directed
    for raw in lines:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        line = dict(raw)
        line["text"] = text
        direction = SCENE_002_LINE_DIRECTIONS.get(text)
        if direction:
            line.update(direction)
        directed.append(line)
    return directed


def _pre_supplied_path(shot_id: str) -> Path | None:
    for extension in SUPPORTED_AUDIO_EXTENSIONS:
        candidate = PRE_SUPPLIED_DIR / f"{shot_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _missing_pre_supplied_paths() -> list[str]:
    return [
        str(PRE_SUPPLIED_DIR / f"{shot_id}.wav")
        for shot_id in EXPECTED_SHOT_IDS
        if _pre_supplied_path(shot_id) is None
    ]


class LocalVerificationStorage:
    """Use canonical persisted job metadata with the saved real Runway files."""

    def __init__(self) -> None:
        self.delegate = get_storage("sqlite")

    def list_jobs(self, project_id: str, limit: int = 500):
        jobs = self.delegate.list_jobs(project_id=project_id, limit=limit)
        localized = []
        for job in jobs:
            if job.status != "complete":
                continue
            if derive_scene_id_from_shot_id(job.shot_id) != SCENE_ID:
                continue
            local_video = SOURCE_DIR / f"{job.shot_id}_raw.mp4"
            if not local_video.exists():
                continue
            copy = job.model_copy(deep=True)
            copy.output_payload.asset_url = str(local_video)
            params = dict(getattr(copy.input_payload, "parameters", None) or {})
            params["dialogue_lines"] = _directed_dialogue_lines(
                params.get("dialogue_lines")
            )
            copy.input_payload.parameters = params
            localized.append(copy)
        return localized

    def save_scene_composition(self, **kwargs):
        return self.delegate.save_scene_composition(**kwargs)


class PreSuppliedBypassAudioService(AudioPipelineService):
    """Generate fresh shot WAVs even when old pre_supplied files exist."""

    def _pre_supplied_shot_dialogue_path(
        self,
        project_id: str,
        scene_id: str,
        shot_id: str,
    ) -> Path | None:
        return None


async def _regenerate_pre_supplied_dialogue(
    storage: LocalVerificationStorage,
) -> dict[str, Any]:
    audio_service = PreSuppliedBypassAudioService()
    PRE_SUPPLIED_DIR.mkdir(parents=True, exist_ok=True)
    jobs = {
        job.shot_id: job
        for _, job in SceneAssemblyService(storage=storage).collect_scene_jobs(
            PROJECT_ID,
            SCENE_ID,
        )
    }
    calls = []
    for shot_id in EXPECTED_SHOT_IDS:
        job = jobs.get(shot_id)
        if job is None:
            raise SystemExit(f"Missing completed job for {shot_id}")
        params = getattr(job.input_payload, "parameters", None) or {}
        result = await audio_service.generate_shot_dialogue(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            shot_id=shot_id,
            dialogue_lines=params.get("dialogue_lines"),
            provider="cosyvoice",
            scene_context=SCENE_002_DIALOGUE_CONTEXT,
        )
        if result.get("status") != TrackStatus.COMPLETE:
            raise SystemExit(
                f"Directed CosyVoice generation failed for {shot_id}: "
                f"{json.dumps(result, indent=2, default=str)}"
            )
        source = Path(str(result.get("file_path") or ""))
        destination = PRE_SUPPLIED_DIR / f"{shot_id}.wav"
        shutil.copy2(source, destination)
        calls.append(
            {
                "shot_id": shot_id,
                "pre_supplied_path": str(destination),
                "status": result.get("status"),
                "provider": result.get("provider"),
                "source": result.get("source"),
                "lines_generated": result.get("lines_generated"),
                "line_instructions": result.get("line_instructions") or [],
            }
        )

    report = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "artifact_scope": "audio_performance_proof_not_script_faithful_scene",
        "visual_sync_warning": (
            "This four-shot harness overdubs directed dialogue onto silent "
            "Runway clips. It is not lip-synced and should not be treated as "
            "the final scene edit."
        ),
        "model": os.environ.get("COSYVOICE_MODEL")
        or os.environ.get("QWEN_TTS_MODEL")
        or "qwen3-tts-instruct-flash",
        "voices": {
            "MAYA": _resolve_cosyvoice_voice_id("MAYA", project_id=PROJECT_ID),
            "DRE": _resolve_cosyvoice_voice_id("DRE", project_id=PROJECT_ID),
        },
        "scene_context": SCENE_002_DIALOGUE_CONTEXT,
        "shots": calls,
    }
    report_path = (
        BACKEND_ROOT
        / "outputs"
        / "real_render_validation"
        / "scene_002_directed_dialogue_report.json"
    )
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def _write_directed_dialogue_preflight_report(
    storage: LocalVerificationStorage,
) -> dict[str, Any]:
    """Write the exact planned CosyVoice payloads without making provider calls."""
    jobs = {
        job.shot_id: job
        for _, job in SceneAssemblyService(storage=storage).collect_scene_jobs(
            PROJECT_ID,
            SCENE_ID,
        )
    }
    shots: list[dict[str, Any]] = []
    for shot_id in EXPECTED_SHOT_IDS:
        job = jobs.get(shot_id)
        if job is None:
            raise SystemExit(f"Missing completed job for {shot_id}")
        params = getattr(job.input_payload, "parameters", None) or {}
        line_payloads = []
        for index, line in enumerate(params.get("dialogue_lines") or []):
            if not isinstance(line, dict):
                continue
            character = str(line.get("character") or line.get("character_name") or "").strip()
            voice = _resolve_cosyvoice_voice_id(character, project_id=PROJECT_ID)
            instruction, instruction_mode = _build_dialogue_instruction(
                line,
                model=COSYVOICE_MODEL,
                voice=voice,
                scene_context=SCENE_002_DIALOGUE_CONTEXT,
            )
            line_payloads.append(
                {
                    "line_index": index,
                    "character": character,
                    "text": str(line.get("text") or "").strip(),
                    "tts_text": _dialogue_tts_text(line),
                    "performance_direction": _dialogue_performance_direction(
                        line,
                        SCENE_002_DIALOGUE_CONTEXT,
                    ),
                    "voice": voice,
                    "model": COSYVOICE_MODEL,
                    "instruction_mode": instruction_mode,
                    "instruction": instruction,
                    "instruction_sources": _dialogue_instruction_sources(
                        line,
                        SCENE_002_DIALOGUE_CONTEXT,
                    ),
                }
            )
        shots.append({"shot_id": shot_id, "line_instructions": line_payloads})

    report = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "artifact_scope": "audio_performance_preflight_not_script_faithful_scene",
        "network_used": False,
        "purpose": (
            "Preflight only: verifies directed performance payloads before "
            "spending live CosyVoice calls."
        ),
        "visual_sync_warning": (
            "Payload preflight covers directed dialogue only; it does not "
            "validate shot count, shot intent, visual continuity, or lip sync."
        ),
        "model": COSYVOICE_MODEL,
        "voices": {
            "MAYA": _resolve_cosyvoice_voice_id("MAYA", project_id=PROJECT_ID),
            "DRE": _resolve_cosyvoice_voice_id("DRE", project_id=PROJECT_ID),
        },
        "scene_context": SCENE_002_DIALOGUE_CONTEXT,
        "shots": shots,
    }
    report_path = (
        BACKEND_ROOT
        / "outputs"
        / "real_render_validation"
        / "scene_002_directed_dialogue_preflight.json"
    )
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote directed dialogue preflight report: {report_path}")
    return report


async def main(
    dialogue_provider: str,
    allow_live_provider: bool,
    regenerate_pre_supplied: bool,
    dry_run_directed_report: bool,
) -> None:
    storage = LocalVerificationStorage()
    if dry_run_directed_report:
        _write_directed_dialogue_preflight_report(storage)
        return
    if regenerate_pre_supplied:
        await _regenerate_pre_supplied_dialogue(storage)
    if dialogue_provider == "cosyvoice" and not allow_live_provider:
        missing = _missing_pre_supplied_paths()
        if missing:
            raise SystemExit(
                "Missing pre-supplied CosyVoice audio files. Expected one supported "
                "audio file per shot under "
                f"{PRE_SUPPLIED_DIR}. Missing canonical WAV paths:\n"
                + "\n".join(missing)
            )
    service = SceneAssemblyService(storage=storage)
    result = await service.assemble_completed_scene(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        dialogue_provider=dialogue_provider,
        score_ambient_provider="none",
        overwrite=True,
    )
    report_path = (
        BACKEND_ROOT
        / "outputs"
        / "real_render_validation"
        / f"scene_002_assembly_report_{dialogue_provider}.json"
    )
    report_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dialogue-provider",
        choices=("cosyvoice", "piper"),
        default="cosyvoice",
    )
    parser.add_argument(
        "--allow-live-provider",
        action="store_true",
        help="Allow live provider synthesis if pre_supplied files are missing.",
    )
    parser.add_argument(
        "--regenerate-pre-supplied",
        action="store_true",
        help="Regenerate the four pre_supplied shot WAVs with directed CosyVoice delivery first.",
    )
    parser.add_argument(
        "--dry-run-directed-report",
        action="store_true",
        help=(
            "Write the planned instruction/SSML payload report without making "
            "live CosyVoice calls."
        ),
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.dialogue_provider,
            args.allow_live_provider,
            args.regenerate_pre_supplied,
            args.dry_run_directed_report,
        )
    )
