"""Audit whether the scene_002 CosyVoice proof matches the stored shot plan.

This is intentionally separate from media verification. The directed CosyVoice
proof can be technically valid while still being the wrong scene cut: wrong shot
count, wrong visual beat coverage, and no lip-sync strategy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "project_3dba9330f43a"
SCENE_ID = "scene_002"
PROJECT_STATE_PATH = BACKEND_ROOT / "data" / "project_state_store.json"
ASSEMBLY_REPORT_PATH = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "scene_002_assembly_report_cosyvoice.json"
)
DIRECTED_REPORT_PATH = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "scene_002_directed_dialogue_report.json"
)
MEDIA_VERIFICATION_PATH = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "scene_002_media_verification_cosyvoice_pre_supplied.json"
)
REPORT_PATH = (
    BACKEND_ROOT
    / "outputs"
    / "real_render_validation"
    / "listen_review"
    / "scene_002_structure_alignment_report.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _scene_board(summary: dict[str, Any]) -> dict[str, Any]:
    boards = summary.get("previs_scene_board")
    if not isinstance(boards, list):
        return {}
    for row in boards:
        if isinstance(row, dict) and row.get("scene_id") == SCENE_ID:
            return row
    return {}


def _scene_sequence(summary: dict[str, Any]) -> list[str]:
    sequences = summary.get("scene_sequence")
    if not isinstance(sequences, list):
        return []
    for row in sequences:
        if isinstance(row, dict) and row.get("scene_id") == SCENE_ID:
            shots = row.get("shots")
            return [str(shot) for shot in shots] if isinstance(shots, list) else []
    return []


def _previs_beat_shots(summary: dict[str, Any]) -> list[str]:
    beat_map = summary.get("previs_beat_shot_map")
    if not isinstance(beat_map, dict):
        return []
    rows = beat_map.get(SCENE_ID)
    if not isinstance(rows, list):
        return []
    shots: list[str] = []
    for row in rows:
        if isinstance(row, dict) and row.get("shot_id"):
            shots.append(str(row["shot_id"]))
    return shots


def _shot_coverage(summary: dict[str, Any]) -> int | None:
    coverage = summary.get("shot_coverage")
    if not isinstance(coverage, dict):
        return None
    scene_coverage = coverage.get(SCENE_ID)
    if not isinstance(scene_coverage, dict):
        return None
    value = scene_coverage.get("candidate_count")
    return int(value) if isinstance(value, int | float) else None


def _scene_text(summary: dict[str, Any]) -> str:
    scene_index = summary.get("scene_index")
    if isinstance(scene_index, dict):
        scene = scene_index.get(SCENE_ID)
        if isinstance(scene, dict):
            return str(scene.get("text") or scene.get("description") or "")
    return ""


def _count_script_dialogue_lines(scene_text: str) -> int:
    """Count only the known scene_002 spoken lines used by this proof."""
    known_lines = [
        "I need you to understand something.",
        "That's funny.",
        "What?",
        "You always say that right before you do something",
        "Things changed.",
        "No. People changed.",
        "There's not enough. You have to understand that.",
        "There is not enough for everyone.",
        "So you decided that for all of us.",
        "Someone had to.",
        "I remember dying. So why am I here?",
    ]
    return sum(1 for line in known_lines if line in scene_text)


def main() -> None:
    state = _read_json(PROJECT_STATE_PATH)
    project = (
        state.get("projects", {})
        .get(PROJECT_ID, {})
        if isinstance(state.get("projects"), dict)
        else {}
    )
    summary = project.get("execution_summary", {})
    if not isinstance(summary, dict):
        summary = {}

    assembly = _read_json(ASSEMBLY_REPORT_PATH)
    directed = _read_json(DIRECTED_REPORT_PATH)
    verification = _read_json(MEDIA_VERIFICATION_PATH)

    board = _scene_board(summary)
    board_shot_count = board.get("shot_count")
    if not isinstance(board_shot_count, int):
        board_shot_count = None

    scene_sequence = _scene_sequence(summary)
    previs_beat_shots = _previs_beat_shots(summary)
    shot_coverage = _shot_coverage(summary)
    assembly_shots = [
        str(shot)
        for shot in assembly.get("shot_ids", [])
        if isinstance(shot, str)
    ]
    assembly_shot_count = (
        int(assembly.get("shot_count"))
        if isinstance(assembly.get("shot_count"), int)
        else len(assembly_shots)
    )
    directed_line_count = sum(
        len(shot.get("line_instructions") or [])
        for shot in directed.get("shots", [])
        if isinstance(shot, dict)
    )
    scene_text = _scene_text(summary)

    expected_counts = {
        "previs_scene_board_shot_count": board_shot_count,
        "previs_beat_shot_count": len(previs_beat_shots),
        "scene_sequence_shot_count": len(scene_sequence),
        "shot_coverage_candidate_count": shot_coverage,
    }
    non_null_expected = [
        value for value in expected_counts.values() if isinstance(value, int)
    ]
    expected_consensus = (
        non_null_expected[0]
        if non_null_expected and all(value == non_null_expected[0] for value in non_null_expected)
        else None
    )

    shot_count_matches_stored_plan = (
        expected_consensus is not None
        and assembly_shot_count == expected_consensus
    )
    final_scene_valid = False
    reasons = []
    if not shot_count_matches_stored_plan:
        reasons.append(
            "assembled shot count does not match stored previs/scene-sequence shot count"
        )
    reasons.append(
        "current visual clips are silent Runway outputs with generated dialogue overlaid; no lip-sync stage is present"
    )
    reasons.append(
        "four-shot grouping follows speaker-turn audio convenience, not full script beat coverage"
    )

    report = {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "artifact_scope": "structure_alignment_audit",
        "stored_plan": {
            **expected_counts,
            "expected_consensus_shot_count": expected_consensus,
            "previs_beat_shots": previs_beat_shots,
            "scene_sequence": scene_sequence,
        },
        "current_audio_proof": {
            "assembly_report": str(ASSEMBLY_REPORT_PATH),
            "media_verification_report": str(MEDIA_VERIFICATION_PATH),
            "media_verification_valid": verification.get("valid"),
            "assembly_shot_count": assembly_shot_count,
            "assembly_shots": assembly_shots,
            "directed_line_count": directed_line_count,
            "script_dialogue_line_fragments_found": _count_script_dialogue_lines(
                scene_text
            ),
        },
        "assessment": {
            "shot_count_matches_stored_plan": shot_count_matches_stored_plan,
            "lip_sync_stage_present": False,
            "valid_as_directed_audio_proof": bool(verification.get("valid")),
            "valid_as_final_script_scene": final_scene_valid,
            "reasons": reasons,
        },
        "recommended_next_step": (
            "Use scene_002_script_aligned_rebuild_plan.json to render a "
            "beat-covered visual rebuild with offscreen/profile/reaction "
            "dialogue strategy, then reuse the directed CosyVoice metadata."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
