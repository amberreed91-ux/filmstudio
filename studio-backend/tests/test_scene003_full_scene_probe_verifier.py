from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_probe_module():
    path = Path("scripts/probe_scene003_full_scene_pipeline.py")
    spec = importlib.util.spec_from_file_location("probe_scene003_full_scene_pipeline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _complete_report() -> dict:
    return {
        "result": {
            "status": "complete",
            "score_ambient_provider": "manual_post_render",
            "soundtrack_status": "manual_post_render",
            "stitch": {"clip_count": 2},
            "shots": [
                {
                    "shot_id": "shot_scene_003_001",
                    "consistency": {
                        "attached": True,
                        "primary_reference_url": "/outputs/ref/dre.png",
                    },
                },
                {
                    "shot_id": "shot_scene_003_002",
                    "consistency": {
                        "attached": True,
                        "primary_reference_url": "/outputs/ref/dre.png",
                    },
                },
            ],
        },
        "saved_assembly_rows": [
            {
                "scene_id": "scene_003",
                "status": "complete",
                "score_ambient_provider": "manual_post_render",
            }
        ],
        "audio_calls": [
            {
                "score_ambient_provider": "none",
                "line_instructions": [
                    {
                        "instruction": "casual concern",
                        "instruction_sources": {
                            "emotional_subtext": {
                                "source": "line.emotional_subtext",
                                "value": "casual concern",
                            }
                        },
                    }
                ],
            },
            {
                "score_ambient_provider": "none",
                "line_instructions": [
                    {
                        "instruction": "controlled unease",
                        "instruction_sources": {
                            "emotional_subtext": {
                                "source": "line.emotional_subtext",
                                "value": "controlled unease",
                            }
                        },
                    }
                ],
            },
        ],
        "final_probe": {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        },
        "final_audio_frequency_evidence": {
            "detected": {
                "manual_score_196hz": True,
                "dialogue_line_1_440hz": True,
                "dialogue_line_2_520hz": True,
            }
        },
    }


def test_full_scene_probe_verifier_accepts_score_and_dialogue_evidence():
    module = _load_probe_module()

    module._assert_full_scene_probe_complete(_complete_report())


def test_full_scene_probe_verifier_rejects_missing_dialogue_frequency():
    module = _load_probe_module()
    report = _complete_report()
    report["final_audio_frequency_evidence"]["detected"]["dialogue_line_2_520hz"] = False

    with pytest.raises(RuntimeError, match="dialogue_line_2_520hz"):
        module._assert_full_scene_probe_complete(report)


def test_full_scene_probe_verifier_rejects_missing_instruction_sources():
    module = _load_probe_module()
    report = _complete_report()
    for call in report["audio_calls"]:
        for instruction in call["line_instructions"]:
            instruction["instruction_sources"] = {}

    with pytest.raises(RuntimeError, match="instruction source evidence missing"):
        module._assert_full_scene_probe_complete(report)


def test_full_scene_probe_verifier_rejects_single_shot_stitch():
    module = _load_probe_module()
    report = _complete_report()
    report["result"]["stitch"]["clip_count"] = 1

    with pytest.raises(RuntimeError, match="stitch multiple shots"):
        module._assert_full_scene_probe_complete(report)


def test_full_scene_probe_verifier_rejects_missing_visual_consistency():
    module = _load_probe_module()
    report = _complete_report()
    report["result"]["shots"][1]["consistency"] = {"attached": False}

    with pytest.raises(RuntimeError, match="visual consistency evidence"):
        module._assert_full_scene_probe_complete(report)


def test_full_scene_probe_verifier_rejects_missing_persisted_assembly_row():
    module = _load_probe_module()
    report = _complete_report()
    report["saved_assembly_rows"] = []

    with pytest.raises(RuntimeError, match="assembly persistence evidence"):
        module._assert_full_scene_probe_complete(report)
