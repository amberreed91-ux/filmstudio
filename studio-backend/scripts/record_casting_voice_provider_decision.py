#!/usr/bin/env python3
"""Record the post-listening Casting voice-provider decision.

This script does not call providers. It turns a completed Fish-vs-DashScope
listening review into a durable JSON decision artifact that can be referenced
by the scene-003 audio goal audit/report.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND_ROOT / "outputs" / "full_stack_probe"
DEFAULT_EVIDENCE_PATH = OUT_DIR / "casting_voice_provider_comparison_live.json"
DECISION_PATH = OUT_DIR / "casting_voice_provider_decision.json"
VALID_DECISIONS = {
    "keep_fish_audio_for_casting",
    "use_cosyvoice_qwen_stack_for_casting",
    "defer_pending_more_samples",
}
VALID_LINE_PROVIDER_PREFERENCES = {
    "fish_audio_s2_pro_clone",
    "cosyvoice_voice_clone",
}
PROVIDER_DECISION_REASON_FIELDS = {
    "keep_fish_audio_for_casting": "reason_to_keep_fish_audio",
    "use_cosyvoice_qwen_stack_for_casting": "reason_to_use_single_dashscope_stack",
}


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluation_has_complete_listening_notes(evidence: dict[str, Any]) -> bool:
    template = (
        evidence.get("human_evaluation_template")
        if isinstance(evidence.get("human_evaluation_template"), dict)
        else {}
    )
    rows = template.get("sample_rows") if isinstance(template.get("sample_rows"), list) else []
    samples = evidence.get("samples") if isinstance(evidence.get("samples"), list) else []
    if not samples or len(rows) < len(samples):
        return False
    evidence_fields = {
        "likeness_evidence",
        "naturalness_evidence",
        "emotion_control_evidence",
        "artifact_or_distraction_notes",
        "decision_notes",
    }
    for index, row in enumerate(rows[:len(samples)]):
        if not isinstance(row, dict):
            return False
        sample = samples[index]
        if not isinstance(sample, dict):
            return False
        if row.get("index") != sample.get("index"):
            return False
        if str(row.get("text") or "").strip() != str(sample.get("text") or "").strip():
            return False
        if str(row.get("emotion_instruction") or "").strip() != str(sample.get("emotion_instruction") or "").strip():
            return False
        preferred_provider = str(row.get("preferred_provider_for_this_line") or "").strip()
        if preferred_provider not in VALID_LINE_PROVIDER_PREFERENCES:
            return False
        row_has_evidence = bool(str(row.get("decision_notes") or "").strip())
        if row_has_evidence:
            continue
        for key, value in row.items():
            if key in evidence_fields and str(value or "").strip():
                row_has_evidence = True
                break
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if nested_key in evidence_fields and str(nested_value or "").strip():
                        row_has_evidence = True
                        break
            if row_has_evidence:
                break
        if not row_has_evidence:
            return False
    return True


def _provider_decision_section_complete(evidence: dict[str, Any], selected_path: str) -> bool:
    reason_field = PROVIDER_DECISION_REASON_FIELDS.get(selected_path)
    if not reason_field:
        return False
    template = (
        evidence.get("human_evaluation_template")
        if isinstance(evidence.get("human_evaluation_template"), dict)
        else {}
    )
    provider_decision = (
        template.get("provider_decision")
        if isinstance(template.get("provider_decision"), dict)
        else {}
    )
    return bool(
        provider_decision.get("selected_path") == selected_path
        and str(provider_decision.get(reason_field) or "").strip()
    )


def _sample_path_exists(sample: dict[str, Any], provider_key: str) -> bool:
    provider = sample.get(provider_key) if isinstance(sample.get(provider_key), dict) else {}
    path_value = str(provider.get("path") or "").strip()
    if not path_value:
        return False
    path = Path(path_value)
    return path.exists() and path.stat().st_size > 0


def _has_complete_side_by_side_samples(samples: list[Any]) -> bool:
    if len(samples) < 2:
        return False
    for sample in samples:
        if not isinstance(sample, dict):
            return False
        if not str(sample.get("text") or "").strip():
            return False
        if not _sample_path_exists(sample, "fish_audio"):
            return False
        if not _sample_path_exists(sample, "cosyvoice"):
            return False
    return True


def _build_decision(
    *,
    selected_path: str,
    decision_notes: str,
    evidence_path: Path,
    reviewer: str,
    allow_owner_override_no_fish_audio: bool = False,
) -> dict[str, Any]:
    if selected_path not in VALID_DECISIONS:
        raise ValueError(f"selected_path must be one of {sorted(VALID_DECISIONS)}")
    if selected_path != "defer_pending_more_samples" and not decision_notes.strip():
        raise ValueError("decision_notes are required when selecting a provider path")

    evidence = _load_json_if_exists(evidence_path)
    samples = evidence.get("samples") if isinstance(evidence.get("samples"), list) else []
    has_side_by_side_samples = _has_complete_side_by_side_samples(samples)
    has_live_samples = bool(evidence.get("network_used") is True and has_side_by_side_samples)
    has_comparison_reference = bool(
        str(evidence.get("reference_audio") or "").strip()
        and str(evidence.get("reference_audio_sha256") or "").strip()
        and str(evidence.get("public_reference_url") or "").strip()
    )
    has_listening_notes = _evaluation_has_complete_listening_notes(evidence)
    has_provider_decision_notes = _provider_decision_section_complete(evidence, selected_path)
    has_deferral_notes = bool(
        selected_path == "defer_pending_more_samples"
        and decision_notes.strip()
    )
    has_owner_override_no_fish_audio = bool(
        allow_owner_override_no_fish_audio
        and selected_path == "use_cosyvoice_qwen_stack_for_casting"
        and decision_notes.strip()
    )
    if selected_path != "defer_pending_more_samples" and not (
        has_live_samples
        and has_comparison_reference
        and has_listening_notes
        and has_provider_decision_notes
    ) and not has_owner_override_no_fish_audio:
        if allow_owner_override_no_fish_audio and selected_path != "use_cosyvoice_qwen_stack_for_casting":
            raise ValueError("owner override without Fish Audio is only valid for the CosyVoice/Qwen stack")
        raise ValueError(
            "provider selection requires a live comparison artifact with at least two samples, "
            "concrete Fish/CosyVoice audio files, shared reference evidence, filled listening notes, "
            "and a completed final provider-decision section, unless the studio owner explicitly "
            "waives Fish Audio and selects the CosyVoice/Qwen stack"
        )

    return {
        "selected_path": selected_path,
        "decision_notes": decision_notes.strip(),
        "reviewer": reviewer.strip() or "studio-owner",
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "evidence_path": str(evidence_path),
        "evidence_summary": {
            "evidence_found": bool(evidence),
            "has_live_samples": has_live_samples,
            "has_side_by_side_samples": has_side_by_side_samples,
            "has_comparison_reference": has_comparison_reference,
            "has_listening_notes": has_listening_notes,
            "has_provider_decision_notes": has_provider_decision_notes,
            "has_deferral_notes": has_deferral_notes,
            "has_owner_override_no_fish_audio": has_owner_override_no_fish_audio,
            "sample_count": len(samples),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-path", required=True, choices=sorted(VALID_DECISIONS))
    parser.add_argument("--decision-notes", default="")
    parser.add_argument("--reviewer", default="studio-owner")
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--output-path", type=Path, default=DECISION_PATH)
    parser.add_argument(
        "--allow-owner-override-no-fish-audio",
        action="store_true",
        help="Allow the studio owner to choose the CosyVoice/Qwen stack when Fish Audio is unavailable.",
    )
    args = parser.parse_args()

    decision = _build_decision(
        selected_path=args.selected_path,
        decision_notes=args.decision_notes,
        evidence_path=args.evidence_path,
        reviewer=args.reviewer,
        allow_owner_override_no_fish_audio=args.allow_owner_override_no_fish_audio,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print(json.dumps({"decision_path": str(args.output_path), "selected_path": decision["selected_path"]}, indent=2))


if __name__ == "__main__":
    main()
