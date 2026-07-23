#!/usr/bin/env python3
"""Audit the local scene-003 audio goal artifacts.

This audit intentionally does not call external providers. It verifies the
local proof artifacts for dialogue emotion instructions, manual post-render
score/ambient, final audio preservation, visual consistency evidence, and the
explicitly deferred Casting provider decision.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND_ROOT / "outputs" / "full_stack_probe"
FULL_SCENE_PROBE = OUT_DIR / "scene_003_full_scene_pipeline_probe.json"
CASTING_PLAN = OUT_DIR / "casting_voice_provider_comparison_plan.json"
CASTING_DECISION = OUT_DIR / "casting_voice_provider_decision.json"
LIVE_COMPARISON = OUT_DIR / "casting_voice_provider_comparison_live.json"
REPORT_PATH = OUT_DIR / "scene_003_audio_decision_report.md"
AUDIT_PATH = OUT_DIR / "scene_003_audio_goal_acceptance_audit.json"
PUBLIC_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_exists(path_value: str | None) -> bool:
    if not path_value:
        return False
    path = Path(path_value)
    return path.exists() and path.stat().st_size > 0


def _has_audio_stream(probe: dict[str, Any]) -> bool:
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    return any(isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams)


def _instruction_sources_present(audio_calls: list[Any]) -> bool:
    for call in audio_calls:
        if not isinstance(call, dict):
            return False
        instructions = call.get("line_instructions") if isinstance(call.get("line_instructions"), list) else []
        if not instructions:
            return False
        for item in instructions:
            if not isinstance(item, dict) or not item.get("instruction"):
                return False
            sources = item.get("instruction_sources") if isinstance(item.get("instruction_sources"), dict) else {}
            subtext = sources.get("emotional_subtext") if isinstance(sources.get("emotional_subtext"), dict) else {}
            if subtext.get("source") not in {"line.emotional_subtext", "line_text_inference"}:
                return False
    return True


def _all_consistency_attached(shots: list[Any]) -> bool:
    if not shots:
        return False
    for shot in shots:
        if not isinstance(shot, dict):
            return False
        consistency = shot.get("consistency") if isinstance(shot.get("consistency"), dict) else {}
        if consistency.get("attached") is not True:
            return False
        if not consistency.get("primary_reference_url"):
            return False
    return True


def _format_casting_incomplete_reason(missing: list[Any]) -> str:
    missing_text = ", ".join(str(item) for item in missing) if missing else "live comparison evidence"
    return (
        "Casting provider decision still requires an approved live Fish Audio vs "
        "DashScope/CosyVoice comparison with usable same-speaker reference audio, "
        "two side-by-side sample files, shared reference evidence, filled line-level "
        "listening notes, and a completed final provider-decision section. "
        f"Current missing live inputs: {missing_text}."
    )


def _live_failure_missing_items(live_report: dict[str, Any]) -> list[str]:
    failure = live_report.get("failure") if isinstance(live_report.get("failure"), dict) else {}
    stage = str(live_report.get("failure_stage") or "provider call")
    status_code = failure.get("status_code")
    if status_code:
        provider_failure = f"provider failure at {stage}: HTTP {status_code}"
    else:
        provider_failure = f"provider failure at {stage}"
    return [
        provider_failure,
        "complete side-by-side samples",
        "filled listening notes",
        "final provider-decision notes",
    ]


def _has_direct_public_audio_url(casting_plan: dict[str, Any]) -> bool:
    public_reference_url = str(casting_plan.get("public_reference_url") or "").strip()
    if not public_reference_url:
        return False
    parsed = urlparse(public_reference_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return any(parsed.path.lower().endswith(suffix) for suffix in PUBLIC_AUDIO_SUFFIXES)


def _reference_next_action(casting_plan: dict[str, Any], missing: list[Any]) -> dict[str, Any]:
    reference_audio = str(casting_plan.get("reference_audio") or "").strip()
    if _has_direct_public_audio_url(casting_plan):
        return {
            "step": "Use the prepared same-speaker reference audio and direct public URL for the live Casting comparison.",
            "requires_network": False,
            "public_url_ready": True,
        }
    if reference_audio and "reference audio file" not in missing and "usable reference audio clip" not in missing:
        return {
            "step": f"Expose the chosen reference clip at a public DashScope-compatible URL: {reference_audio}",
            "requires_network": True,
        }
    return {
        "step": "Provide a usable same-speaker reference audio clip for the Casting comparison.",
        "requires_network": False,
    }


def _build_audit(
    full_scene: dict[str, Any],
    casting_plan: dict[str, Any],
    report_text: str,
    casting_decision: dict[str, Any] | None = None,
    live_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = full_scene.get("result") if isinstance(full_scene.get("result"), dict) else {}
    frequency_evidence = (
        full_scene.get("final_audio_frequency_evidence")
        if isinstance(full_scene.get("final_audio_frequency_evidence"), dict)
        else {}
    )
    detected = frequency_evidence.get("detected") if isinstance(frequency_evidence.get("detected"), dict) else {}
    audio_calls = full_scene.get("audio_calls") if isinstance(full_scene.get("audio_calls"), list) else []
    shots = result.get("shots") if isinstance(result.get("shots"), list) else []
    live_readiness = (
        casting_plan.get("live_comparison_readiness")
        if isinstance(casting_plan.get("live_comparison_readiness"), dict)
        else {}
    )
    casting_decision = casting_decision if isinstance(casting_decision, dict) else {}
    live_report = live_report if isinstance(live_report, dict) else {}
    selected_casting_path = casting_decision.get("selected_path")
    provider_chosen_after_live_review = selected_casting_path in {
        "keep_fish_audio_for_casting",
        "use_cosyvoice_qwen_stack_for_casting",
    }
    evidence_summary = (
        casting_decision.get("evidence_summary")
        if isinstance(casting_decision.get("evidence_summary"), dict)
        else {}
    )
    owner_override_no_fish_audio = bool(
        selected_casting_path == "use_cosyvoice_qwen_stack_for_casting"
        and evidence_summary.get("has_owner_override_no_fish_audio") is True
        and str(casting_decision.get("decision_notes") or "").strip()
    )
    casting_provider_decided = bool(
        (
            provider_chosen_after_live_review
            and evidence_summary.get("has_live_samples") is True
            and evidence_summary.get("has_side_by_side_samples") is True
            and evidence_summary.get("has_comparison_reference") is True
            and evidence_summary.get("has_listening_notes") is True
            and evidence_summary.get("has_provider_decision_notes") is True
            and int(evidence_summary.get("sample_count") or 0) >= 2
        )
        or owner_override_no_fish_audio
    )
    live_comparison_failed = bool(
        live_report.get("mode") == "live_failed"
        and live_report.get("network_used") is True
        and live_report.get("side_by_side_complete") is False
    )
    casting_plan_ready_for_live = bool(
        live_readiness.get("can_run_after_consent") is True
        and not live_readiness.get("missing")
    )
    casting_deferred_with_plan = (
        selected_casting_path == "defer_pending_more_samples"
        and evidence_summary.get("has_deferral_notes") is True
        and casting_plan.get("recommended_decision_now", {}).get("casting_provider") == "defer"
        and (
            (
                live_readiness.get("can_run_after_consent") is False
                and bool(live_readiness.get("missing"))
            )
            or casting_plan_ready_for_live
            or live_comparison_failed
        )
    )
    readiness_command = str(live_readiness.get("readiness_packet_command_template") or "").strip()
    live_command = (
        f"{readiness_command} --live"
        if readiness_command
        else ".venv/bin/python scripts/plan_casting_voice_provider_comparison.py "
        "--reference-audio <local-reference.wav> "
        "--public-reference-url <https://.../reference.wav> --live"
    )
    raw_missing_live_inputs = live_readiness.get("missing") or []
    if casting_provider_decided:
        missing_live_inputs: list[Any] = []
    elif live_comparison_failed:
        missing_live_inputs = _live_failure_missing_items(live_report)
    elif raw_missing_live_inputs:
        missing_live_inputs = raw_missing_live_inputs
    else:
        missing_live_inputs = [
            "live side-by-side samples",
            "filled listening notes",
            "final provider-decision notes",
        ]

    checks = {
        "full_scene_completed": result.get("status") == "complete",
        "all_shots_stitched": result.get("stitch", {}).get("clip_count", 0) >= 2,
        "cosyvoice_dialogue_per_shot": all(
            isinstance(call, dict)
            and call.get("score_ambient_provider") == "none"
            for call in audio_calls
        ),
        "per_line_emotion_sources_present": _instruction_sources_present(audio_calls),
        "manual_post_render_score_selected": result.get("score_ambient_provider") == "manual_post_render",
        "manual_score_detected_in_final_audio": detected.get("manual_score_196hz") is True,
        "dialogue_detected_in_final_audio": (
            detected.get("dialogue_line_1_440hz") is True
            and detected.get("dialogue_line_2_520hz") is True
        ),
        "final_artifact_has_audio_stream": _has_audio_stream(
            full_scene.get("final_probe") if isinstance(full_scene.get("final_probe"), dict) else {}
        ),
        "final_artifact_exists": _artifact_exists(full_scene.get("artifact_path")),
        "visual_consistency_evidence_present": _all_consistency_attached(shots),
        "casting_live_comparison_failed": live_comparison_failed,
        "casting_live_comparison_ready": casting_plan_ready_for_live,
        "casting_provider_decision_owner_override": owner_override_no_fish_audio,
        "casting_comparison_deferred_explicitly": casting_deferred_with_plan,
        "casting_decision_artifact_recorded": selected_casting_path in {
            "keep_fish_audio_for_casting",
            "use_cosyvoice_qwen_stack_for_casting",
            "defer_pending_more_samples",
        },
        "casting_decision_or_deferral_supported": bool(
            casting_provider_decided or casting_deferred_with_plan
        ),
        "score_ambient_decision_documented": "Decision: use manual post-render" in report_text,
        "duration_decision_documented": "Decision: treat `5.04s`" in report_text,
    }
    local_required = [
        "full_scene_completed",
        "all_shots_stitched",
        "cosyvoice_dialogue_per_shot",
        "per_line_emotion_sources_present",
        "manual_post_render_score_selected",
        "manual_score_detected_in_final_audio",
        "dialogue_detected_in_final_audio",
        "final_artifact_has_audio_stream",
        "final_artifact_exists",
        "visual_consistency_evidence_present",
        "casting_decision_artifact_recorded",
        "casting_decision_or_deferral_supported",
        "score_ambient_decision_documented",
        "duration_decision_documented",
    ]
    local_complete = all(checks[name] for name in local_required)
    goal_complete = bool(local_complete and casting_provider_decided)
    if goal_complete:
        status = "complete"
    elif local_complete:
        status = "local_complete_external_casting_deferred"
    else:
        status = "local_incomplete"
    next_actions: list[dict[str, Any]] = []
    if not goal_complete:
        reference_action = _reference_next_action(casting_plan, missing_live_inputs)
        next_actions = [reference_action]
        if reference_action["requires_network"] is False and reference_action.get("public_url_ready") is not True:
            next_actions.append(
                {
                    "step": "Expose the same reference clip at a public URL accepted by DashScope voice cloning.",
                    "requires_network": True,
                }
            )
        next_actions.extend(
            [
                {
                    "step": "Export Fish Audio and DashScope credentials in the shell that runs the comparison.",
                    "requires_network": False,
                },
                {
                    "step": "Set the explicit consent env before sending reference audio and dialogue to providers.",
                    "requires_network": False,
                    "consent_env": casting_plan.get("consent_gate", {}).get("env"),
                },
                {
                    "step": "Run the live side-by-side comparison and listen using the qualitative evaluation template.",
                    "requires_network": True,
                    "command_template": live_command,
                },
                {
                    "step": "Record the final Casting provider decision after live listening notes are filled.",
                    "requires_network": False,
                    "command_templates": {
                        "choose_dashscope_stack": (
                            ".venv/bin/python scripts/record_casting_voice_provider_decision.py "
                            "--selected-path use_cosyvoice_qwen_stack_for_casting "
                            "--decision-notes '<why DashScope/CosyVoice won after listening>'"
                        ),
                        "keep_fish_audio": (
                            ".venv/bin/python scripts/record_casting_voice_provider_decision.py "
                            "--selected-path keep_fish_audio_for_casting "
                            "--decision-notes '<why Fish Audio won after listening>'"
                        ),
                        "defer_for_more_samples": (
                            ".venv/bin/python scripts/record_casting_voice_provider_decision.py "
                            "--selected-path defer_pending_more_samples "
                            "--decision-notes '<what extra samples or evidence are needed>'"
                        ),
                    },
                },
            ]
        )
    return {
        "status": status,
        "completion": {
            "local_scene_deliverable_complete": local_complete,
            "overall_goal_complete": goal_complete,
            "why_not_complete": (
                None
                if goal_complete
                else _format_casting_incomplete_reason(missing_live_inputs)
            ),
        },
        "network_used": False,
        "checks": checks,
        "remaining_external_gate": {
            "casting_provider_decision": (
                "complete"
                if goal_complete
                else "deferred_pending_live_fish_vs_dashscope_listening_comparison"
            ),
            "recorded_decision_path": casting_decision.get("selected_path"),
            "missing": missing_live_inputs,
            "consent_required": casting_plan.get("consent_gate", {}).get("env"),
        },
        "next_actions": next_actions,
        "artifacts": {
            "full_scene_probe": str(FULL_SCENE_PROBE),
            "casting_plan": str(CASTING_PLAN),
            "casting_decision": str(CASTING_DECISION) if CASTING_DECISION.exists() else None,
            "casting_live_comparison": str(LIVE_COMPARISON) if LIVE_COMPARISON.exists() else None,
            "decision_report": str(REPORT_PATH),
            "final_scene_artifact": full_scene.get("artifact_path"),
        },
    }


def main() -> None:
    full_scene = _load_json(FULL_SCENE_PROBE)
    casting_plan = _load_json(CASTING_PLAN)
    casting_decision = _load_json(CASTING_DECISION) if CASTING_DECISION.exists() else {}
    live_report = _load_json(LIVE_COMPARISON) if LIVE_COMPARISON.exists() else {}
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    audit = _build_audit(full_scene, casting_plan, report_text, casting_decision, live_report)
    AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps({"audit_path": str(AUDIT_PATH), "status": audit["status"]}, indent=2))


if __name__ == "__main__":
    main()
