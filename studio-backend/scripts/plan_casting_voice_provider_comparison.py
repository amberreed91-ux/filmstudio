#!/usr/bin/env python3
"""Create a casting voice-provider comparison plan.

This script does not call external providers. It records the concrete inputs
needed before deciding whether Casting should use the single DashScope stack
or keep Fish Audio S2 Pro in the candidate set.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


OUT_DIR = Path("outputs/full_stack_probe")
LIVE_OUT_DIR = OUT_DIR / "casting_voice_provider_comparison"
DEFAULT_SAMPLE_TEXTS = [
    "You good? You're looking at me weird.",
    "Keep your voice down.",
]
DEFAULT_EMOTION_INSTRUCTIONS = [
    "casual concern, held back rather than melodramatic",
    "controlled unease, low and clipped",
]
CONSENT_ENV = "LIVE_CASTING_VOICE_COMPARISON_APPROVED"
CONSENT_VALUE = "I_APPROVE_EXTERNAL_VOICE_COMPARISON"
MIN_REFERENCE_AUDIO_SECONDS = 3.0
PUBLIC_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
NON_DIRECT_AUDIO_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "vimeo.com",
    "www.vimeo.com",
}


DOCS = {
    "fish_audio_tts": "https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech",
    "fish_audio_create_model": "https://docs.fish.audio/api-reference/endpoint/model/create-model",
    "alibaba_tts_models": "https://help.aliyun.com/en/model-studio/tts-model/",
    "alibaba_voice_cloning": "https://help.aliyun.com/en/model-studio/voice-clone-design-http-api",
    "alibaba_voice_design": "https://help.aliyun.com/en/model-studio/voice-design-user-guide",
}

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _ffprobe(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    if not path.exists():
        return {"error": f"missing file: {path}"}
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        return json.loads(subprocess.check_output(cmd, text=True))
    except Exception as exc:
        return {"error": str(exc)}


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _sha256(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_audio_usable(probe: dict[str, Any] | None) -> bool:
    if not isinstance(probe, dict) or probe.get("error"):
        return False
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    has_audio_stream = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )
    try:
        duration = float((probe.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return has_audio_stream and duration >= MIN_REFERENCE_AUDIO_SECONDS


def _public_reference_audio_url_usable(url: str) -> bool:
    value = str(url or "").strip()
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host in NON_DIRECT_AUDIO_HOSTS:
        return False
    suffix = Path(parsed.path).suffix.lower()
    return suffix in PUBLIC_AUDIO_EXTENSIONS


def _build_human_evaluation_template(
    sample_texts: list[str],
    emotion_instructions: list[str],
) -> dict[str, Any]:
    sample_rows: list[dict[str, Any]] = []
    for index, text in enumerate(sample_texts):
        sample_rows.append(
            {
                "index": index,
                "text": text,
                "emotion_instruction": _paired_emotion(emotion_instructions, index),
                "fish_audio_s2_pro_clone": {
                    "likeness_evidence": "",
                    "naturalness_evidence": "",
                    "emotion_control_evidence": "",
                    "artifact_or_distraction_notes": "",
                },
                "cosyvoice_voice_clone": {
                    "likeness_evidence": "",
                    "naturalness_evidence": "",
                    "emotion_control_evidence": "",
                    "artifact_or_distraction_notes": "",
                },
                "preferred_provider_for_this_line": "",
                "decision_notes": "",
            }
        )

    return {
        "purpose": (
            "Fill this after listening to the side-by-side samples; use concrete "
            "listening evidence instead of numeric scores."
        ),
        "sample_rows": sample_rows,
        "provider_decision": {
            "selected_path": "",
            "reason_to_keep_fish_audio": "",
            "reason_to_use_single_dashscope_stack": "",
            "reason_to_defer": "",
            "follow_up_needed": "",
        },
        "decision_options": [
            "keep_fish_audio_for_casting",
            "use_cosyvoice_qwen_stack_for_casting",
            "defer_pending_more_samples",
        ],
    }


def _shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _build_readiness_command_template(
    sample_texts: list[str],
    emotion_instructions: list[str],
    reference_audio: Path | None = None,
    public_reference_url: str = "",
) -> str:
    reference_audio_arg = (
        _shell_single_quote(str(reference_audio))
        if reference_audio
        else "<local-reference.wav>"
    )
    public_reference_url_arg = (
        _shell_single_quote(public_reference_url)
        if public_reference_url
        else "<https://.../reference.wav>"
    )
    parts = [
        ".venv/bin/python",
        "scripts/plan_casting_voice_provider_comparison.py",
        "--reference-audio",
        reference_audio_arg,
        "--public-reference-url",
        public_reference_url_arg,
    ]
    for text in sample_texts:
        parts.extend(["--sample-text", _shell_single_quote(text)])
    for instruction in emotion_instructions:
        parts.extend(["--emotion-instruction", _shell_single_quote(instruction)])
    return " ".join(parts)


def _recommended_decision_reason(
    *,
    shared_reference_ready: bool,
    all_live_ready: bool,
    consent_granted: bool,
) -> str:
    if all_live_ready and consent_granted:
        return (
            "The live side-by-side comparison is ready to run. Defer the "
            "Casting provider decision until Fish Audio and DashScope/CosyVoice "
            "samples are generated and reviewed with listening notes."
        )
    if shared_reference_ready:
        return (
            "A real side-by-side likeness/naturalness comparison cannot be run "
            "until provider credentials are exported and explicit approval is set "
            "for sending the prepared reference clip and test dialogue to Fish "
            "Audio and DashScope."
        )
    return (
        "A real side-by-side likeness/naturalness comparison cannot be run "
        "without a usable shared reference clip, provider credentials, and "
        "explicit approval to send that clip and test dialogue to Fish Audio "
        "and DashScope."
    )


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    reference_audio = args.reference_audio
    reference_probe = _ffprobe(reference_audio) if reference_audio else None
    reference_file_exists = bool(reference_audio and reference_audio.exists())
    reference_usable = _reference_audio_usable(reference_probe)
    reference_ready = bool(reference_file_exists and reference_usable)
    reference_usable_or_not_supplied = reference_usable or not reference_file_exists
    reference_sha256 = _sha256(reference_audio)

    fish_ready = reference_ready and _env_present("FISH_AUDIO_API_KEY")
    dashscope_ready = _env_present("DASHSCOPE_API_KEY")
    public_reference_url_usable = _public_reference_audio_url_usable(args.public_reference_url)
    public_reference_url_usable_or_not_supplied = public_reference_url_usable or not args.public_reference_url
    shared_reference_ready = bool(reference_ready and public_reference_url_usable)
    cosyvoice_clone_ready = dashscope_ready and public_reference_url_usable
    qwen_design_ready = dashscope_ready and bool(args.voice_prompt)
    sample_texts = args.sample_text or DEFAULT_SAMPLE_TEXTS
    emotion_instructions = args.emotion_instruction or DEFAULT_EMOTION_INSTRUCTIONS
    all_live_ready = fish_ready and cosyvoice_clone_ready
    consent_granted = os.environ.get(CONSENT_ENV) == CONSENT_VALUE

    return {
        "mode": "dry-run",
        "network_used": False,
        "sample_texts": sample_texts,
        "emotion_instructions": emotion_instructions,
        "reference_audio": str(reference_audio.resolve()) if reference_audio else None,
        "reference_audio_probe": reference_probe,
        "reference_audio_sha256": reference_sha256,
        "public_reference_url": args.public_reference_url or None,
        "reference_readiness": {
            "local_reference_file_exists": reference_file_exists,
            "local_reference_usable": reference_usable,
            "direct_public_audio_url_usable": public_reference_url_usable,
            "shared_reference_ready": shared_reference_ready,
        },
        "voice_prompt": args.voice_prompt or None,
        "consent_gate": {
            "env": f"{CONSENT_ENV}={CONSENT_VALUE}",
            "granted": consent_granted,
            "reason": (
                "A live comparison sends reference audio, test dialogue, and "
                "emotion instructions to Fish Audio and DashScope."
            ),
        },
        "providers": {
            "fish_audio_s2_pro_clone": {
                "can_run_live_comparison": fish_ready,
                "missing": [
                    item
                    for item, ok in (
                        ("reference audio file", reference_file_exists),
                        ("usable reference audio clip", reference_usable_or_not_supplied),
                        ("FISH_AUDIO_API_KEY", _env_present("FISH_AUDIO_API_KEY")),
                    )
                    if not ok
                ],
                "comparison_role": (
                    "Persistent clone or zero-shot reference baseline for likeness "
                    "and naturalness against the same reference audio."
                ),
                "current_pipeline_status": "Implemented as selectable dialogue provider, not default.",
                "emotion_control": "Inline/open-domain tags for S2-style requests.",
            },
            "cosyvoice_voice_clone": {
                "can_run_live_comparison": cosyvoice_clone_ready,
                "missing": [
                    item
                    for item, ok in (
                        ("DASHSCOPE_API_KEY", dashscope_ready),
                        ("public reference audio URL", bool(args.public_reference_url)),
                        ("direct public audio URL", public_reference_url_usable_or_not_supplied),
                    )
                    if not ok
                ],
                "comparison_role": (
                    "Likeness comparison against Fish Audio using the same reference "
                    "audio, once the sample is available as a public URL."
                ),
                "current_pipeline_status": "Dialogue stack already routes through CosyVoice/Qwen-TTS.",
                "emotion_control": "Free-form for cloned/designed voices on supported models; fixed format for some system voices.",
            },
            "qwen3_tts_vd_voice_design": {
                "can_run_live_comparison": qwen_design_ready,
                "missing": [
                    item
                    for item, ok in (
                        ("DASHSCOPE_API_KEY", dashscope_ready),
                        ("voice_prompt", bool(args.voice_prompt)),
                    )
                    if not ok
                ],
                "comparison_role": (
                    "Character voice design from description. Not a likeness test "
                    "against reference audio because voice design has no target speaker."
                ),
                "current_pipeline_status": "Not yet wired into Casting storage/UI.",
                "emotion_control": "Compatible with the Qwen/CosyVoice instruction pattern when synthesizing through supported TTS models.",
            },
        },
        "recommended_decision_now": {
            "casting_provider": "defer",
            "reason": _recommended_decision_reason(
                shared_reference_ready=shared_reference_ready,
                all_live_ready=all_live_ready,
                consent_granted=consent_granted,
            ),
            "default_direction_if_quality_ties": (
                "Prefer the single DashScope stack: CosyVoice/Qwen for dialogue, "
                "CosyVoice cloning for reference-based casting where viable, and "
                "Qwen3-TTS-VD for designed character voices."
            ),
            "keep_fish_audio_until_proven": (
                "Keep Fish Audio S2 Pro as a selectable Casting candidate until "
                "the comparison shows DashScope voices match or beat it on likeness, "
                "naturalness, emotional controllability, latency, and operational fit."
            ),
        },
        "live_comparison_readiness": {
            "can_run_after_consent": bool(all_live_ready and consent_granted),
            "missing": [
                item
                for item, ok in (
                    ("reference audio file", reference_file_exists),
                    ("usable reference audio clip", reference_usable_or_not_supplied),
                    ("FISH_AUDIO_API_KEY", _env_present("FISH_AUDIO_API_KEY")),
                    ("DASHSCOPE_API_KEY", dashscope_ready),
                    ("public reference audio URL for DashScope clone", bool(args.public_reference_url)),
                    ("direct public audio URL for DashScope clone", public_reference_url_usable_or_not_supplied),
                    ("explicit consent env", consent_granted),
                )
                if not ok
            ],
            "readiness_packet_command_template": _build_readiness_command_template(
                sample_texts,
                emotion_instructions,
                reference_audio,
                args.public_reference_url,
            ),
            "output_manifest": "outputs/full_stack_probe/casting_voice_provider_comparison_live.json",
        },
        "comparison_rubric": [
            "speaker likeness to the same reference sample",
            "naturalness and artifact level on scene-003 dialogue",
            "emotional range under per-line instruction",
            "latency and reliability",
            "voice lifecycle fit: clone/list/delete/reuse",
            "regional and credential complexity",
            "cost and quota exposure",
        ],
        "human_evaluation_template": _build_human_evaluation_template(sample_texts, emotion_instructions),
        "docs": DOCS,
    }


def _paired_emotion(instructions: list[str], index: int) -> str:
    if not instructions:
        return ""
    return instructions[min(index, len(instructions) - 1)]


def _safe_stem(text: str, index: int) -> str:
    keep = "".join(ch.lower() if ch.isalnum() else "_" for ch in text.strip())[:48].strip("_")
    return f"{index + 1:02d}_{keep or 'sample'}"


def _assert_live_ready(report: dict[str, Any]) -> None:
    readiness = report.get("live_comparison_readiness") if isinstance(report.get("live_comparison_readiness"), dict) else {}
    if not readiness.get("can_run_after_consent"):
        missing = readiness.get("missing") or []
        raise SystemExit(
            "Live comparison is not ready. Missing: "
            + (", ".join(str(item) for item in missing) if missing else "unknown readiness requirement")
        )


def _sample_file_exists(sample: dict[str, Any], provider_key: str) -> bool:
    provider = sample.get(provider_key) if isinstance(sample.get(provider_key), dict) else {}
    path_value = str(provider.get("path") or "").strip()
    if not path_value:
        return False
    path = Path(path_value)
    return path.exists() and path.stat().st_size > 0


def _assert_live_report_complete(live_report: dict[str, Any]) -> None:
    if live_report.get("mode") != "live" or live_report.get("network_used") is not True:
        raise RuntimeError("live comparison manifest was not recorded as a live network run")
    if not live_report.get("reference_audio_sha256") or not live_report.get("public_reference_url"):
        raise RuntimeError("live comparison manifest is missing shared reference evidence")
    sample_texts = live_report.get("sample_texts") if isinstance(live_report.get("sample_texts"), list) else []
    samples = live_report.get("samples") if isinstance(live_report.get("samples"), list) else []
    if len(samples) < 2 or len(samples) != len(sample_texts):
        raise RuntimeError("live comparison manifest does not contain the expected sample pair count")
    provider_voice_ids = (
        live_report.get("provider_voice_ids")
        if isinstance(live_report.get("provider_voice_ids"), dict)
        else {}
    )
    if not provider_voice_ids.get("fish_audio_s2_pro_clone") or not provider_voice_ids.get("cosyvoice_voice_clone"):
        raise RuntimeError("live comparison manifest is missing provider voice ids")
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise RuntimeError("live comparison sample was not recorded as an object")
        if sample.get("text") != sample_texts[index]:
            raise RuntimeError("live comparison sample text does not match the requested sample text")
        if not _sample_file_exists(sample, "fish_audio"):
            raise RuntimeError("live comparison sample is missing Fish Audio output")
        if not _sample_file_exists(sample, "cosyvoice"):
            raise RuntimeError("live comparison sample is missing CosyVoice output")


def _exception_summary(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    request = getattr(exc, "request", None)
    summary: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }
    if response is not None:
        summary["status_code"] = getattr(response, "status_code", None)
        summary["response_text"] = str(getattr(response, "text", "") or "")[:1000]
    if request is not None:
        summary["url"] = str(getattr(request, "url", "") or "")
        summary["method"] = str(getattr(request, "method", "") or "")
    return summary


def _write_live_failure_report(
    *,
    report: dict[str, Any],
    output_dir: Path,
    samples: list[dict[str, Any]],
    provider_voice_ids: dict[str, str | None],
    stage: str,
    exc: Exception,
) -> dict[str, Any]:
    failure_report = {
        **report,
        "mode": "live_failed",
        "network_used": True,
        "output_dir": str(output_dir.resolve()),
        "failure_stage": stage,
        "failure": _exception_summary(exc),
        "provider_voice_ids": provider_voice_ids,
        "sample_pair_count": len(samples),
        "side_by_side_complete": False,
        "samples": samples,
        "recommended_decision_now": {
            "casting_provider": "defer_pending_more_samples",
            "reason": (
                "The approved live comparison reached external providers but did "
                "not produce complete side-by-side samples. Resolve the provider "
                "failure, then rerun before choosing the Casting provider."
            ),
        },
    }
    live_path = OUT_DIR / "casting_voice_provider_comparison_live.json"
    live_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.write_text(json.dumps(failure_report, indent=2), encoding="utf-8")
    return failure_report


async def _run_live_comparison(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    """Run the approved Fish-vs-DashScope audio comparison and return a manifest."""
    _assert_live_ready(report)

    from fish_audio_provider import FishAudioProvider
    from app.services.audio.cosyvoice_tts_service import CosyVoiceTTSService

    sample_texts = report["sample_texts"]
    emotion_instructions = report["emotion_instructions"]
    output_dir = args.output_dir or LIVE_OUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    label = args.voice_label or "casting-comparison"
    fish = FishAudioProvider()
    cosy = CosyVoiceTTSService()
    fish_voice_id: str | None = None
    cosy_voice_id: str | None = None
    samples: list[dict[str, Any]] = []
    try:
        stage = "fish_audio_clone"
        fish_voice_id = args.fish_voice_id or await fish.clone_voice(str(args.reference_audio), label)
        stage = "cosyvoice_clone"
        cosy_voice = cosy.clone_voice_from_sample(
            audio_url=args.public_reference_url,
            preferred_name=label.replace(" ", "-")[:32] or "casting-comparison",
        )
        cosy_voice_id = cosy_voice.voice_id
        for index, text in enumerate(sample_texts):
            emotion = _paired_emotion(emotion_instructions, index)
            stem = _safe_stem(text, index)
            stage = f"fish_audio_synthesize_sample_{index + 1}"
            fish_result = await fish.synthesize(
                text=text,
                voice_id=fish_voice_id,
                emotion_tag=emotion or None,
                format="mp3",
            )
            fish_path = output_dir / f"{stem}_fish_audio_s2_pro.{fish_result.format}"
            fish_path.write_bytes(fish_result.audio_bytes)

            cosy_path = output_dir / f"{stem}_cosyvoice_qwen.mp3"
            stage = f"cosyvoice_synthesize_sample_{index + 1}"
            cosy.synthesize_dialogue(
                text=text,
                voice=cosy_voice.voice_id,
                output_path=cosy_path,
                instruction=emotion or None,
            )
            samples.append(
                {
                    "index": index,
                    "text": text,
                    "emotion_instruction": emotion,
                    "fish_audio": {
                        "voice_id": fish_voice_id,
                        "path": str(fish_path.resolve()),
                        "probe": _ffprobe(fish_path),
                    },
                    "cosyvoice": {
                        "voice_id": cosy_voice.voice_id,
                        "preferred_name": cosy_voice.preferred_name,
                        "path": str(cosy_path.resolve()),
                        "probe": _ffprobe(cosy_path),
                    },
                }
            )
    except Exception as exc:
        _write_live_failure_report(
            report=report,
            output_dir=output_dir,
            samples=samples,
            provider_voice_ids={
                "fish_audio_s2_pro_clone": fish_voice_id,
                "cosyvoice_voice_clone": cosy_voice_id,
            },
            stage=stage,
            exc=exc,
        )
        raise SystemExit(
            "Live comparison failed at "
            f"{stage}. A failure manifest was written to "
            f"{(OUT_DIR / 'casting_voice_provider_comparison_live.json').resolve()}. "
            f"Provider error: {exc}"
        ) from exc
    finally:
        await fish.close()

    live_report = {
        **report,
        "mode": "live",
        "network_used": True,
        "output_dir": str(output_dir.resolve()),
        "provider_voice_ids": {
            "fish_audio_s2_pro_clone": fish_voice_id,
            "cosyvoice_voice_clone": cosy_voice_id,
        },
        "sample_pair_count": len(samples),
        "side_by_side_complete": True,
        "samples": samples,
        "recommended_decision_now": {
            "casting_provider": "defer_pending_human_listening",
            "reason": (
                "Live side-by-side samples were generated. Pick the Casting "
                "provider after listening for likeness, naturalness, emotional "
                "range, artifacts, and operational fit."
            ),
        },
    }
    _assert_live_report_complete(live_report)
    live_path = OUT_DIR / "casting_voice_provider_comparison_live.json"
    live_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.write_text(json.dumps(live_report, indent=2), encoding="utf-8")
    return live_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-audio", type=Path)
    parser.add_argument("--public-reference-url", default="")
    parser.add_argument("--voice-prompt", default="")
    parser.add_argument("--sample-text", action="append")
    parser.add_argument("--emotion-instruction", action="append")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fish-voice-id", default="")
    parser.add_argument("--voice-label", default="casting-comparison")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = _build_report(args)
    out_path = OUT_DIR / "casting_voice_provider_comparison_plan.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    result = {"report_path": str(out_path.resolve())}
    if args.live:
        live_report = asyncio.run(_run_live_comparison(args, report))
        result["live_report_path"] = str((OUT_DIR / "casting_voice_provider_comparison_live.json").resolve())
        result["sample_count"] = len(live_report.get("samples", []))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
