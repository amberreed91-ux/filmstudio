"""Generate objective prosody proxies for scene_002 directed dialogue lines.

This does not replace a human listen-through. It gives a small signal-level
audit of whether the generated line WAVs show variation in timing, loudness, and
rough pitch contour — useful evidence when judging whether a TTS pass may still
be reading flat.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_002"
AUDIO_DIR = BACKEND_ROOT / "outputs" / "audio" / PROJECT_ID / SCENE_ID
DIRECTED_REPORT_PATH = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "scene_002_directed_dialogue_report.json"
)
OUTPUT_JSON = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "listen_review"
    / "scene_002_dialogue_prosody_proxy_report.json"
)
OUTPUT_MD = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "listen_review"
    / "scene_002_dialogue_prosody_proxy_report.md"
)


def _as_mono(samples: np.ndarray) -> np.ndarray:
    if samples.ndim == 1:
        return samples.astype(np.float64)
    return samples.mean(axis=1).astype(np.float64)


def _frame_rms_db(samples: np.ndarray, sample_rate: int) -> list[float]:
    frame = max(1, int(sample_rate * 0.05))
    hop = max(1, int(sample_rate * 0.025))
    values: list[float] = []
    for start in range(0, max(1, len(samples) - frame + 1), hop):
        chunk = samples[start : start + frame]
        if len(chunk) < frame:
            break
        rms = math.sqrt(float(np.mean(chunk * chunk)) + 1e-12)
        values.append(20.0 * math.log10(rms + 1e-12))
    return values


def _rough_f0_values(samples: np.ndarray, sample_rate: int) -> list[float]:
    """Estimate rough F0 via normalized autocorrelation.

    This is intentionally conservative: it is a proxy for contour variation,
    not a production-grade pitch tracker.
    """
    frame = max(1, int(sample_rate * 0.04))
    hop = max(1, int(sample_rate * 0.02))
    min_lag = max(1, int(sample_rate / 350.0))
    max_lag = max(min_lag + 1, int(sample_rate / 60.0))
    values: list[float] = []
    window = np.hanning(frame)
    for start in range(0, max(1, len(samples) - frame + 1), hop):
        chunk = samples[start : start + frame]
        if len(chunk) < frame:
            break
        chunk = (chunk - float(np.mean(chunk))) * window
        energy = float(np.dot(chunk, chunk))
        if energy < 1e-7:
            continue
        corr = np.correlate(chunk, chunk, mode="full")[frame - 1 :]
        search = corr[min_lag : min(max_lag, len(corr))]
        if search.size == 0:
            continue
        lag = int(np.argmax(search) + min_lag)
        confidence = float(corr[lag] / (corr[0] + 1e-12))
        if confidence < 0.3:
            continue
        values.append(float(sample_rate / lag))
    return values


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None,
            "iqr": None,
        }
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": round(float(np.min(arr)), 3),
        "max": round(float(np.max(arr)), 3),
        "mean": round(float(np.mean(arr)), 3),
        "median": round(float(np.median(arr)), 3),
        "std": round(float(np.std(arr)), 3),
        "iqr": round(float(np.percentile(arr, 75) - np.percentile(arr, 25)), 3),
    }


def _line_path(shot_id: str, line_index: int) -> Path:
    return AUDIO_DIR / f"{shot_id}_line_{line_index:03d}.wav"


def _flatness_flags(rms_stats: dict[str, Any], f0_stats: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    rms_std = rms_stats.get("std")
    f0_iqr = f0_stats.get("iqr")
    voiced = f0_stats.get("voiced_frame_count", 0)
    if isinstance(rms_std, float) and rms_std < 3.0:
        flags.append("low_loudness_variation")
    if isinstance(f0_iqr, float) and f0_iqr < 12.0 and voiced >= 8:
        flags.append("low_pitch_contour_variation")
    if voiced < 5:
        flags.append("pitch_proxy_low_confidence")
    return flags


def main() -> None:
    report = json.loads(DIRECTED_REPORT_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for shot in report.get("shots", []):
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("shot_id") or "")
        for line in shot.get("line_instructions") or []:
            if not isinstance(line, dict):
                continue
            line_index = int(line.get("line", line.get("line_index", len(rows))))
            path = _line_path(shot_id, line_index)
            if not path.is_file():
                rows.append(
                    {
                        "shot_id": shot_id,
                        "line_index": line_index,
                        "character": line.get("character"),
                        "text": line.get("text"),
                        "error": f"missing line wav: {path}",
                    }
                )
                continue
            samples, sample_rate = sf.read(path)
            mono = _as_mono(samples)
            duration = len(mono) / float(sample_rate)
            rms_values = _frame_rms_db(mono, sample_rate)
            f0_values = _rough_f0_values(mono, sample_rate)
            rms_stats = _stats(rms_values)
            f0_stats = _stats(f0_values)
            f0_stats["voiced_frame_count"] = len(f0_values)
            rows.append(
                {
                    "shot_id": shot_id,
                    "line_index": line_index,
                    "character": line.get("character"),
                    "text": line.get("text"),
                    "voice": line.get("voice"),
                    "instruction_mode": line.get("instruction_mode"),
                    "duration_seconds": round(duration, 3),
                    "rms_dbfs": rms_stats,
                    "rough_f0_hz": f0_stats,
                    "flatness_proxy_flags": _flatness_flags(rms_stats, f0_stats),
                    "interpretation_note": (
                        "Signal proxy only; human playback decides whether this reads as acted."
                    ),
                }
            )

    output = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "artifact_scope": "prosody_proxy_not_human_verdict",
        "method": {
            "loudness": "50ms RMS frames, reported in dBFS-like scale",
            "pitch": "rough autocorrelation F0 on 40ms frames, low-confidence frames dropped",
            "flatness_flags": "heuristic flags for low loudness/pitch variation",
        },
        "lines": rows,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")

    md_lines = [
        "# scene_002 dialogue prosody proxy report",
        "",
        "This is not a human acting verdict. It is a signal-level proxy for timing, loudness variation, and rough pitch contour.",
        "",
        "| Line | Character | Duration | RMS std | F0 IQR | Flags |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        rms_std = row.get("rms_dbfs", {}).get("std") if isinstance(row.get("rms_dbfs"), dict) else None
        f0_iqr = row.get("rough_f0_hz", {}).get("iqr") if isinstance(row.get("rough_f0_hz"), dict) else None
        md_lines.append(
            "| "
            + str(row.get("text", "")).replace("|", "\\|")
            + " | "
            + str(row.get("character") or "")
            + " | "
            + str(row.get("duration_seconds") or "")
            + " | "
            + str(rms_std or "")
            + " | "
            + str(f0_iqr or "")
            + " | "
            + ", ".join(row.get("flatness_proxy_flags") or [])
            + " |"
        )
    OUTPUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
