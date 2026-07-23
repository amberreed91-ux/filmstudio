from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_capture_module():
    path = Path("scripts/verify_scene_pipeline_capture.py")
    spec = importlib.util.spec_from_file_location("verify_scene_pipeline_capture", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _completed_evidence(tmp_path: Path) -> dict:
    output = tmp_path / "render.mp4"
    output.write_bytes(b"render-output")
    frames = []
    for index in range(3):
        frame = tmp_path / f"frame_{index:04d}.jpg"
        frame.write_bytes(b"frame")
        frames.append(
            {
                "timestamp_seconds": float(index),
                "frame_index": index,
                "image_path": str(frame),
            }
        )
    return {
        "mode": "completed_real_render_visual_check",
        "project_id": "project_3dba9330f43a",
        "scene_id": "scene_003",
        "shot_id": "scene_003_shot_001",
        "job_id": "job-20260723015712-b813ff2b-scene_003_shot_001",
        "provider": "happyhorse",
        "provider_job_id": "253315bc-11fa-4416-9d3c-1de31a0f3ad5",
        "status": "complete",
        "output_url": "/outputs/renders/project_3dba9330f43a/render.mp4",
        "prompt": "Dre cooks while Maya watches, two-shot staging.",
        "prompt_slots": {
            "character_state": "Dre avoids Maya's eyes; Maya stays guarded.",
            "action": "Dre cooks while Maya arrives.",
            "environment_persistence": "Dre's apartment",
            "camera": "Two-shot staging with readable eyelines.",
            "lighting": "",
        },
        "consistency_payload": {
            "refs": [
                {"ref_id": "style-ref", "kind": "style", "image_url": "https://example.test/style.png"}
            ],
            "mode": "identity_lock",
        },
        "standing_correction_after": {
            "correction_id": "sc_validation_scene003_camera_20260723",
        },
        "attempt": {
            "attempt_n": 1,
            "attempt_number": 1,
            "prompt_text": "Dre cooks while Maya watches, two-shot staging.",
            "provider": "runway",
            "score_json": {
                "verdict": "pass",
                "frames_scored": [0.1, 0.5, 0.9],
                "dimensions": {
                    "character_state": {},
                    "action": {},
                    "camera": {},
                    "lighting": {},
                    "environment_persistence": {},
                },
            },
        },
        "adherence_summary": {
            "failed_slots": [],
            "dimension_scores": {
                "character_state": 85.0,
                "action": 90.0,
                "camera": 95.0,
                "lighting": 90.0,
                "environment_persistence": 100.0,
            },
        },
        "keyframes": frames,
        "human_visual_check": {"overall": "The render adheres to the staged two-shot."},
    }


def test_canonical_capture_accepts_real_render_evidence_without_character_consistency(tmp_path, monkeypatch):
    module = _load_capture_module()
    monkeypatch.setattr(module, "BACKEND_ROOT", tmp_path)
    (tmp_path / "outputs" / "renders" / "project_3dba9330f43a").mkdir(parents=True)
    evidence = _completed_evidence(tmp_path)
    (tmp_path / "outputs" / "renders" / "project_3dba9330f43a" / "render.mp4").write_bytes(
        b"render-output"
    )

    capture = module.build_canonical_capture(
        evidence,
        evidence_path=tmp_path / "evidence.json",
    )

    assert capture["capture_status"] == "verified_no_spend"
    assert capture["network_used"] is False
    assert capture["run"]["provider_job_id"] == "253315bc-11fa-4416-9d3c-1de31a0f3ad5"
    assert capture["provenance"]["consistency_reference_kinds"] == ["style"]
    assert capture["adherence"]["verdict"] == "pass"
    assert capture["character_consistency"] == {
        "status": "not_started",
        "evidence_asserted": False,
        "reason": "This capture is limited to prompt provenance and render adherence.",
    }


def test_canonical_capture_rejects_character_consistency_references(tmp_path, monkeypatch):
    module = _load_capture_module()
    monkeypatch.setattr(module, "BACKEND_ROOT", tmp_path)
    (tmp_path / "outputs" / "renders" / "project_3dba9330f43a").mkdir(parents=True)
    evidence = _completed_evidence(tmp_path)
    (tmp_path / "outputs" / "renders" / "project_3dba9330f43a" / "render.mp4").write_bytes(
        b"render-output"
    )
    evidence["consistency_payload"]["refs"][0]["kind"] = "character_face"

    with pytest.raises(RuntimeError, match="character consistency references"):
        module.build_canonical_capture(evidence, evidence_path=tmp_path / "evidence.json")


def test_canonical_capture_rejects_missing_adherence_attempt(tmp_path, monkeypatch):
    module = _load_capture_module()
    monkeypatch.setattr(module, "BACKEND_ROOT", tmp_path)
    (tmp_path / "outputs" / "renders" / "project_3dba9330f43a").mkdir(parents=True)
    evidence = _completed_evidence(tmp_path)
    (tmp_path / "outputs" / "renders" / "project_3dba9330f43a" / "render.mp4").write_bytes(
        b"render-output"
    )
    evidence["attempt"] = {}

    with pytest.raises(RuntimeError, match="adherence row"):
        module.build_canonical_capture(evidence, evidence_path=tmp_path / "evidence.json")
