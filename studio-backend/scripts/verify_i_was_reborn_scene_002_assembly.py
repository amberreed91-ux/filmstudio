"""Independently verify the rendered I Was Reborn scene_002 media artifact."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_002"
EXPECTED_SHOT_IDS = [
    "shot_scene_002_001",
    "shot_scene_002_002",
    "shot_scene_002_003",
    "shot_scene_002_004",
]
EXPECTED_LINES = [3, 3, 1, 3]
EXPECTED_VOICES = {
    "MAYA": "longwanjun_v3",
    "DRE": "longanyang",
}
EXPECTED_DIRECTED_LINE_COUNT = 10
EXPECTED_SSML_MARKERS = {
    "What?": ['<break time="250ms"/>'],
    "So you decided that for all of us.": [
        '<break time="180ms"/>',
    ],
    "Someone had to.": ['<break time="450ms"/>'],
}
VALID_COSYVOICE_V3_FIXED_INSTRUCTIONS = {
    "你说话的情感是neutral。",
    "你说话的情感是fearful。",
    "你说话的情感是angry。",
    "你说话的情感是sad。",
    "你说话的情感是surprised。",
    "你说话的情感是happy。",
    "你说话的情感是disgusted。",
}
EXPECTED_INSTRUCTION_MODE_BY_VOICE = {
    "longanyang": "cosyvoice_fixed",
    "longwanjun_v3": "none",
}
SUPPORTED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")
MEDIA_PATH = (
    BACKEND_ROOT
    / "static"
    / "composed"
    / PROJECT_ID
    / f"{SCENE_ID}_audio.mp4"
)
PRE_SUPPLIED_DIR = BACKEND_ROOT / "outputs" / "audio" / PROJECT_ID / SCENE_ID / "pre_supplied"
DIRECTED_REPORT_PATH = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "scene_002_directed_dialogue_report.json"
)

SILENCE_RE = re.compile(
    r"silence_(?P<kind>start|end): (?P<time>[0-9.]+)"
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _probe() -> dict:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration,size,bit_rate:"
                "stream=index,codec_type,codec_name,width,height,pix_fmt,"
                "sample_rate,channels,duration"
            ),
            "-of",
            "json",
            str(MEDIA_PATH),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "ffprobe failed")
    return json.loads(result.stdout)


def _probe_duration(path: Path) -> float | None:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _silence_intervals(duration: float) -> list[tuple[float, float]]:
    result = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(MEDIA_PATH),
            "-af",
            "silencedetect=noise=-45dB:d=0.08",
            "-f",
            "null",
            "-",
        ]
    )
    events = [
        (match.group("kind"), float(match.group("time")))
        for match in SILENCE_RE.finditer(result.stderr)
    ]
    intervals: list[tuple[float, float]] = []
    start: float | None = None
    for kind, timestamp in events:
        if kind == "start":
            start = timestamp
        elif start is not None:
            intervals.append((start, timestamp))
            start = None
    if start is not None:
        intervals.append((start, duration))
    return intervals


def _expected_pre_supplied_path(shot_id: str) -> Path | None:
    for extension in SUPPORTED_AUDIO_EXTENSIONS:
        candidate = PRE_SUPPLIED_DIR / f"{shot_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _directed_performance_check() -> dict:
    if not DIRECTED_REPORT_PATH.is_file():
        return {
            "report_path": str(DIRECTED_REPORT_PATH),
            "report_exists": False,
            "valid": False,
            "failures": ["directed dialogue report missing"],
        }

    report = json.loads(DIRECTED_REPORT_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    shots = report.get("shots") if isinstance(report, dict) else None
    if not isinstance(shots, list):
        return {
            "report_path": str(DIRECTED_REPORT_PATH),
            "report_exists": True,
            "valid": False,
            "failures": ["directed dialogue report has no shots list"],
        }

    if [str(shot.get("shot_id") or "") for shot in shots] != EXPECTED_SHOT_IDS:
        failures.append("shot order does not match expected scene_002 four-shot order")

    line_rows = []
    for shot in shots:
        shot_id = str(shot.get("shot_id") or "")
        if shot.get("status") != "complete":
            failures.append(f"{shot_id} generation status is not complete")
        if shot.get("provider") != "cosyvoice":
            failures.append(f"{shot_id} provider is not cosyvoice")
        if shot.get("source") != "live_provider":
            failures.append(f"{shot_id} was not generated from live provider in report")
        pre_supplied_path = Path(str(shot.get("pre_supplied_path") or ""))
        if not pre_supplied_path.is_file():
            failures.append(f"{shot_id} pre_supplied_path does not exist")
        instructions = shot.get("line_instructions")
        if not isinstance(instructions, list):
            failures.append(f"{shot_id} has no line_instructions list")
            continue
        line_rows.extend(instructions)

    if len(line_rows) != EXPECTED_DIRECTED_LINE_COUNT:
        failures.append(
            f"expected {EXPECTED_DIRECTED_LINE_COUNT} directed lines, found {len(line_rows)}"
        )

    ssml_seen = {text: False for text in EXPECTED_SSML_MARKERS}
    for index, line in enumerate(line_rows):
        character = str(line.get("character") or "").strip().upper()
        text = str(line.get("text") or "").strip()
        tts_text = str(line.get("tts_text") or "").strip()
        performance_direction = str(line.get("performance_direction") or "").strip()
        voice = str(line.get("voice") or "").strip()
        model = str(line.get("model") or "").strip()
        instruction = str(line.get("instruction") or "").strip()
        mode = str(line.get("instruction_mode") or "").strip()
        sources = line.get("instruction_sources")
        sources = sources if isinstance(sources, dict) else {}
        emotional_source = (
            sources.get("emotional_subtext")
            if isinstance(sources.get("emotional_subtext"), dict)
            else {}
        )

        expected_voice = EXPECTED_VOICES.get(character)
        if expected_voice and voice != expected_voice:
            failures.append(
                f"line {index} {character} voice {voice!r} != expected {expected_voice!r}"
            )
        if model != "cosyvoice-v3-flash":
            failures.append(
                f"line {index} {character} model {model!r} != 'cosyvoice-v3-flash'"
            )
        expected_mode_voice = expected_voice or voice
        expected_mode = EXPECTED_INSTRUCTION_MODE_BY_VOICE.get(expected_mode_voice, "none")
        if mode != expected_mode:
            failures.append(
                f"line {index} {character} instruction_mode {mode!r} != {expected_mode!r}"
            )
        if expected_mode == "cosyvoice_fixed" and instruction not in VALID_COSYVOICE_V3_FIXED_INSTRUCTIONS:
            failures.append(
                f"line {index} {character} instruction {instruction!r} is not a valid cosyvoice-v3 fixed instruction"
            )
        if expected_mode == "none" and instruction:
            failures.append(
                f"line {index} {character} voice {voice!r} should not send unsupported instruction {instruction!r}"
            )
        if not performance_direction:
            failures.append(f"line {index} {character} has no rich performance_direction")
        if emotional_source.get("source") != "line.emotional_subtext":
            failures.append(
                f"line {index} {character} emotional_subtext was not explicit line metadata"
            )
        if text in EXPECTED_SSML_MARKERS:
            missing = [
                marker
                for marker in EXPECTED_SSML_MARKERS[text]
                if marker not in tts_text
            ]
            if missing:
                failures.append(f"line {index} {text!r} missing SSML marker(s): {missing}")
            else:
                ssml_seen[text] = True

    for text, seen in ssml_seen.items():
        if not seen:
            failures.append(f"required SSML line not found: {text}")

    return {
        "report_path": str(DIRECTED_REPORT_PATH),
        "report_exists": True,
        "expected_voices": EXPECTED_VOICES,
        "expected_model": "cosyvoice-v3-flash",
        "expected_directed_line_count": EXPECTED_DIRECTED_LINE_COUNT,
        "actual_directed_line_count": len(line_rows),
        "required_ssml_lines": sorted(EXPECTED_SSML_MARKERS),
        "valid": not failures,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dialogue-provider",
        choices=("cosyvoice", "piper"),
        default="cosyvoice",
    )
    parser.add_argument(
        "--allow-live-provider",
        action="store_true",
        help="Do not require every shot dialogue source to be pre_supplied.",
    )
    parser.add_argument(
        "--require-directed-performance",
        action="store_true",
        help=(
            "Require scene_002_directed_dialogue_report.json to prove the "
            "expected CosyVoice voices, per-line instructions, and SSML beats."
        ),
    )
    args = parser.parse_args()

    assembly_report_path = (
        BACKEND_ROOT
        / "outputs"
        / "real_render_validation"
        / f"scene_002_assembly_report_{args.dialogue_provider}.json"
    )
    verification_report_path = (
        BACKEND_ROOT
        / "outputs"
        / "real_render_validation"
        / (
            f"scene_002_media_verification_{args.dialogue_provider}"
            f"{'' if args.allow_live_provider else '_pre_supplied'}.json"
        )
    )
    assembly = json.loads(assembly_report_path.read_text(encoding="utf-8"))
    probe = _probe()
    duration = float(probe["format"]["duration"])
    streams = probe.get("streams") or []
    video = next(row for row in streams if row.get("codec_type") == "video")
    audio = next(row for row in streams if row.get("codec_type") == "audio")
    intervals = _silence_intervals(duration)

    boundary_checks = []
    for boundary in assembly["audio_continuity"]["shot_boundaries_seconds"]:
        crossing = next(
            (
                (start, end)
                for start, end in intervals
                if start <= float(boundary) <= end
            ),
            None,
        )
        post_boundary_silence = (
            max(0.0, crossing[1] - float(boundary))
            if crossing is not None
            else 0.0
        )
        boundary_checks.append(
            {
                "boundary_seconds": boundary,
                "crossing_silence_interval_seconds": (
                    [round(crossing[0], 6), round(crossing[1], 6)]
                    if crossing is not None
                    else None
                ),
                "post_boundary_silence_seconds": round(post_boundary_silence, 6),
                "no_material_inserted_gap": post_boundary_silence <= 0.1,
            }
        )

    actual_lines = [int(shot["dialogue_lines"]) for shot in assembly["shots"]]
    dialogue_check = {
        "expected_lines_per_shot": EXPECTED_LINES,
        "actual_lines_per_shot": actual_lines,
        "all_shots_complete": all(
            shot.get("dialogue_status") == "complete"
            and shot.get("dialogue_baked") is True
            for shot in assembly["shots"]
        ),
        "line_distribution_matches": actual_lines == EXPECTED_LINES,
        "overrun_policy": "freeze_last_frame",
    }
    pre_supplied_checks = []
    for shot in assembly["shots"]:
        shot_id = str(shot.get("shot_id") or "")
        expected_path = _expected_pre_supplied_path(shot_id)
        source_path = Path(str(shot.get("dialogue_source_path") or ""))
        pre_supplied_duration = _probe_duration(source_path) if source_path.is_file() else None
        assembled_duration = float(shot.get("duration_seconds") or 0.0)
        duration_preserved = (
            pre_supplied_duration is not None
            and assembled_duration >= pre_supplied_duration - 0.75
        )
        pre_supplied_checks.append(
            {
                "shot_id": shot_id,
                "dialogue_source": shot.get("dialogue_source"),
                "dialogue_source_path": str(source_path) if str(source_path) else None,
                "expected_pre_supplied_path": (
                    str(expected_path) if expected_path is not None else None
                ),
                "source_is_pre_supplied": shot.get("dialogue_source") == "pre_supplied",
                "source_path_exists": source_path.is_file(),
                "source_path_matches_expected": (
                    expected_path is not None and source_path == expected_path
                ),
                "pre_supplied_duration_seconds": (
                    round(pre_supplied_duration, 3)
                    if pre_supplied_duration is not None
                    else None
                ),
                "assembled_shot_duration_seconds": round(assembled_duration, 3),
                "duration_preserved": duration_preserved,
            }
        )
    pre_supplied_required = not args.allow_live_provider
    pre_supplied_valid = (
        len(pre_supplied_checks) == len(EXPECTED_SHOT_IDS)
        and [row["shot_id"] for row in pre_supplied_checks] == EXPECTED_SHOT_IDS
        and all(
            row["source_is_pre_supplied"]
            and row["source_path_exists"]
            and row["source_path_matches_expected"]
            and row["duration_preserved"]
            for row in pre_supplied_checks
        )
    )

    packet_timeline = assembly["audio_continuity"]["audio_packet_timeline"]
    result = {
        "media_path": str(MEDIA_PATH),
        "assembly_report_path": str(assembly_report_path),
        "assembly_status": assembly["status"],
        "dialogue_provider": assembly["dialogue_provider_requested"],
        "score_ambient_provider": assembly["score_ambient_provider"],
        "shot_count": assembly["shot_count"],
        "shot_ids": assembly["shot_ids"],
        "container_duration_seconds": duration,
        "video": video,
        "audio": audio,
        "packet_timeline": packet_timeline,
        "boundary_checks": boundary_checks,
        "dialogue_timing": dialogue_check,
        "pre_supplied_required": pre_supplied_required,
        "pre_supplied_directory": str(PRE_SUPPLIED_DIR),
        "pre_supplied_checks": pre_supplied_checks,
    }
    directed_performance = (
        _directed_performance_check()
        if args.require_directed_performance
        else {
            "required": False,
            "valid": True,
            "advisory": "Directed performance report was not required for this verification run.",
        }
    )
    result["directed_performance"] = directed_performance
    result["valid"] = bool(
        assembly["audio_continuity"]["valid"]
        and assembly["dialogue_provider_requested"] == args.dialogue_provider
        and video.get("codec_name") == "h264"
        and video.get("pix_fmt") == "yuv420p"
        and audio.get("codec_name") == "aac"
        and audio.get("sample_rate") == "48000"
        and audio.get("channels") == 2
        and packet_timeline["max_gap_seconds"] <= 0.05
        and packet_timeline["max_overlap_seconds"] <= 0.05
        and all(check["no_material_inserted_gap"] for check in boundary_checks)
        and dialogue_check["all_shots_complete"]
        and dialogue_check["line_distribution_matches"]
        and (pre_supplied_valid or not pre_supplied_required)
        and directed_performance["valid"]
    )
    verification_report_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
