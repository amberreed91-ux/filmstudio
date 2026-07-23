#!/usr/bin/env python3
"""Verify and emit canonical provenance/adherence capture for one scene run.

This script is intentionally no-spend: it only reads local evidence from a
completed provider render and checks the referenced local artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "prompt_adherence_happyhorse_completed_evidence.json"
)
DEFAULT_CAPTURE = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "canonical_scene003_pipeline_capture.json"
)
REQUIRED_PROMPT_SLOTS = {"character_state", "action", "environment_persistence", "camera"}
REQUIRED_ADHERENCE_DIMENSIONS = {
    "character_state",
    "action",
    "camera",
    "lighting",
    "environment_persistence",
}
CHARACTER_REFERENCE_KINDS = {"character", "character_face", "character_full", "identity"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _local_path_from_output_url(output_url: str) -> Path | None:
    if not output_url.startswith("/outputs/"):
        return None
    return BACKEND_ROOT / output_url.removeprefix("/")


def _assert_file_exists(path: Path | None, label: str) -> Path:
    if path is None or not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} local artifact is missing or empty")
    return path


def _non_empty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _reference_kinds(evidence: dict[str, Any]) -> list[str]:
    payload = evidence.get("consistency_payload")
    if not isinstance(payload, dict):
        return []
    refs = payload.get("refs") if isinstance(payload.get("refs"), list) else []
    return sorted(
        {
            str(ref.get("kind") or "").strip()
            for ref in refs
            if isinstance(ref, dict) and str(ref.get("kind") or "").strip()
        }
    )


def _derive_scene_id(evidence: dict[str, Any]) -> str:
    explicit = str(evidence.get("scene_id") or "").strip()
    if explicit:
        return explicit
    shot_id = str(evidence.get("shot_id") or "").strip()
    if "_shot_" in shot_id:
        return shot_id.split("_shot_", 1)[0]
    if shot_id.startswith("shot_scene_"):
        parts = shot_id.split("_")
        if len(parts) >= 3:
            return "_".join(parts[1:3])
    return ""


def build_canonical_capture(evidence: dict[str, Any], *, evidence_path: Path) -> dict[str, Any]:
    if evidence.get("mode") != "completed_real_render_visual_check":
        raise RuntimeError("evidence is not a completed real-render visual check")
    if evidence.get("status") != "complete":
        raise RuntimeError("evidence render did not complete")
    if not _non_empty(evidence.get("provider_job_id")):
        raise RuntimeError("provider_job_id is required for real provider provenance")
    if not _non_empty(evidence.get("job_id")):
        raise RuntimeError("job_id is required for pipeline provenance")
    if not _non_empty(evidence.get("output_url")):
        raise RuntimeError("output_url is required for artifact provenance")

    output_path = _assert_file_exists(
        _local_path_from_output_url(str(evidence.get("output_url") or "")),
        "render output",
    )

    prompt_slots = evidence.get("prompt_slots") if isinstance(evidence.get("prompt_slots"), dict) else {}
    missing_slots = sorted(slot for slot in REQUIRED_PROMPT_SLOTS if not _non_empty(prompt_slots.get(slot)))
    if missing_slots:
        raise RuntimeError(f"prompt slot provenance missing: {', '.join(missing_slots)}")

    attempt = evidence.get("attempt") if isinstance(evidence.get("attempt"), dict) else {}
    score_json = attempt.get("score_json") if isinstance(attempt.get("score_json"), dict) else {}
    adherence_summary = (
        evidence.get("adherence_summary")
        if isinstance(evidence.get("adherence_summary"), dict)
        else {}
    )
    if not attempt:
        raise RuntimeError("render attempt adherence row is missing")
    if score_json.get("verdict") != "pass":
        raise RuntimeError("adherence report does not have a pass verdict")
    dimensions = score_json.get("dimensions") if isinstance(score_json.get("dimensions"), dict) else {}
    missing_dimensions = sorted(REQUIRED_ADHERENCE_DIMENSIONS - set(dimensions))
    if missing_dimensions:
        raise RuntimeError(f"adherence dimensions missing: {', '.join(missing_dimensions)}")
    if not isinstance(adherence_summary.get("failed_slots"), list) or adherence_summary.get("failed_slots"):
        raise RuntimeError("adherence summary must contain an empty failed_slots list")

    keyframes = evidence.get("keyframes") if isinstance(evidence.get("keyframes"), list) else []
    if len(keyframes) < 3:
        raise RuntimeError("expected at least three keyframes for visual adherence evidence")
    verified_keyframes: list[dict[str, Any]] = []
    for keyframe in keyframes:
        if not isinstance(keyframe, dict):
            raise RuntimeError("keyframe evidence row is not an object")
        frame_path = _assert_file_exists(Path(str(keyframe.get("image_path") or "")), "keyframe")
        verified_keyframes.append(
            {
                "timestamp_seconds": keyframe.get("timestamp_seconds"),
                "frame_index": keyframe.get("frame_index"),
                "image_path": str(frame_path),
            }
        )

    visual_check = (
        evidence.get("human_visual_check")
        if isinstance(evidence.get("human_visual_check"), dict)
        else {}
    )
    if not _non_empty(visual_check.get("overall")):
        raise RuntimeError("human visual adherence check is missing")

    reference_kinds = _reference_kinds(evidence)
    if any(kind in CHARACTER_REFERENCE_KINDS for kind in reference_kinds):
        raise RuntimeError("character consistency references are present; this capture must not start that work")

    provider_prompt = str(evidence.get("prompt") or "")
    attempt_prompt = str(attempt.get("prompt_text") or "")
    scene_id = _derive_scene_id(evidence)
    if not scene_id:
        raise RuntimeError("scene_id could not be resolved for canonical capture")

    return {
        "schema_version": "scene_pipeline_capture.v1",
        "capture_type": "canonical_provenance_adherence_capture",
        "capture_status": "verified_no_spend",
        "network_used": False,
        "external_provider_run_required": False,
        "source_evidence_path": str(evidence_path),
        "run": {
            "project_id": evidence.get("project_id"),
            "scene_id": scene_id,
            "shot_id": evidence.get("shot_id"),
            "job_id": evidence.get("job_id"),
            "provider": evidence.get("provider"),
            "provider_model": evidence.get("provider_model"),
            "provider_job_id": evidence.get("provider_job_id"),
            "status": evidence.get("status"),
            "output_url": evidence.get("output_url"),
            "output_local_path": str(output_path),
            "output_artifact_verified": True,
        },
        "provenance": {
            "prompt_slots": prompt_slots,
            "provider_prompt_captured": bool(provider_prompt),
            "provider_prompt_matches_attempt_prompt": provider_prompt == attempt_prompt,
            "consistency_reference_kinds": reference_kinds,
            "standing_correction_id": (
                (evidence.get("standing_correction_after") or {}).get("correction_id")
                if isinstance(evidence.get("standing_correction_after"), dict)
                else None
            ),
            "keyframes": verified_keyframes,
        },
        "adherence": {
            "attempt_number": attempt.get("attempt_number") or attempt.get("attempt_n"),
            "render_provider": evidence.get("provider"),
            "attempt_row_provider": attempt.get("provider"),
            "verdict": score_json.get("verdict"),
            "failed_slots": adherence_summary.get("failed_slots"),
            "dimension_scores": adherence_summary.get("dimension_scores"),
            "frames_scored": score_json.get("frames_scored"),
            "visual_check_overall": visual_check.get("overall"),
        },
        "character_consistency": {
            "status": "not_started",
            "evidence_asserted": False,
            "reason": "This capture is limited to prompt provenance and render adherence.",
        },
    }


def verify_and_write_capture(evidence_path: Path, capture_path: Path) -> dict[str, Any]:
    evidence = _load_json(evidence_path)
    capture = build_canonical_capture(evidence, evidence_path=evidence_path)
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text(json.dumps(capture, indent=2), encoding="utf-8")
    return capture


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--out", default=str(DEFAULT_CAPTURE))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    capture = verify_and_write_capture(Path(args.evidence), Path(args.out))
    print(json.dumps({
        "status": capture["capture_status"],
        "capture": str(Path(args.out)),
        "provider": capture["run"]["provider"],
        "job_id": capture["run"]["job_id"],
        "character_consistency": capture["character_consistency"]["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
