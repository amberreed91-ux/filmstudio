from __future__ import annotations

import importlib.util
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_audit_module():
    path = _BACKEND_ROOT / "scripts" / "audit_scene003_audio_goal.py"
    spec = importlib.util.spec_from_file_location("audit_scene003_audio_goal", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _full_scene_probe() -> dict:
    return {
        "artifact_path": "/tmp/final-scene.mp4",
        "result": {
            "status": "complete",
            "score_ambient_provider": "manual_post_render",
            "stitch": {"clip_count": 2},
            "shots": [
                {
                    "consistency": {
                        "attached": True,
                        "primary_reference_url": "/outputs/ref/dre.png",
                    }
                },
                {
                    "consistency": {
                        "attached": True,
                        "primary_reference_url": "/outputs/ref/dre.png",
                    }
                },
            ],
        },
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
        "final_probe": {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]},
        "final_audio_frequency_evidence": {
            "detected": {
                "manual_score_196hz": True,
                "dialogue_line_1_440hz": True,
                "dialogue_line_2_520hz": True,
            }
        },
    }


def _casting_plan() -> dict:
    return {
        "recommended_decision_now": {"casting_provider": "defer"},
        "live_comparison_readiness": {
            "can_run_after_consent": False,
            "missing": ["reference audio file", "explicit consent env"],
            "readiness_packet_command_template": (
                ".venv/bin/python scripts/plan_casting_voice_provider_comparison.py "
                "--reference-audio <local-reference.wav>"
            ),
        },
        "consent_gate": {
            "env": "LIVE_CASTING_VOICE_COMPARISON_APPROVED=I_APPROVE_EXTERNAL_VOICE_COMPARISON"
        },
    }


def _deferred_casting_decision() -> dict:
    return {
        "selected_path": "defer_pending_more_samples",
        "evidence_summary": {
            "has_deferral_notes": True,
        },
    }


def test_audio_goal_audit_reports_local_complete_with_casting_deferred(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        _deferred_casting_decision(),
    )

    assert audit["status"] == "local_complete_external_casting_deferred"
    assert audit["completion"]["local_scene_deliverable_complete"] is True
    assert audit["completion"]["overall_goal_complete"] is False
    assert "Casting provider decision" in audit["completion"]["why_not_complete"]
    assert "usable same-speaker reference audio" in audit["completion"]["why_not_complete"]
    assert "completed final provider-decision section" in audit["completion"]["why_not_complete"]
    assert "reference audio file" in audit["completion"]["why_not_complete"]
    assert audit["checks"]["casting_comparison_deferred_explicitly"] is True
    assert audit["checks"]["casting_decision_artifact_recorded"] is True
    assert audit["checks"]["casting_decision_or_deferral_supported"] is True
    assert audit["remaining_external_gate"]["recorded_decision_path"] == "defer_pending_more_samples"
    assert audit["remaining_external_gate"]["casting_provider_decision"].startswith("deferred")
    assert audit["next_actions"][0]["step"] == (
        "Provide a usable same-speaker reference audio clip for the Casting comparison."
    )
    assert audit["next_actions"][-2]["requires_network"] is True
    assert audit["next_actions"][-2]["command_template"].endswith("--live")
    assert audit["next_actions"][-1]["requires_network"] is False
    assert "use_cosyvoice_qwen_stack_for_casting" in audit["next_actions"][-1]["command_templates"]["choose_dashscope_stack"]
    assert "keep_fish_audio_for_casting" in audit["next_actions"][-1]["command_templates"]["keep_fish_audio"]
    assert audit["next_actions"][3]["consent_env"] == (
        "LIVE_CASTING_VOICE_COMPARISON_APPROVED=I_APPROVE_EXTERNAL_VOICE_COMPARISON"
    )


def test_audio_goal_audit_does_not_ask_to_expose_ready_public_reference(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)
    casting_plan = _casting_plan()
    casting_plan["public_reference_url"] = (
        "https://huggingface.co/datasets/flexthink/ljspeech/resolve/main/wavs/LJ001-0001.wav"
    )
    casting_plan["live_comparison_readiness"]["missing"] = [
        "FISH_AUDIO_API_KEY",
        "DASHSCOPE_API_KEY",
        "explicit consent env",
    ]

    audit = module._build_audit(
        _full_scene_probe(),
        casting_plan,
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        _deferred_casting_decision(),
    )

    assert audit["next_actions"][0]["public_url_ready"] is True
    assert "direct public URL" in audit["next_actions"][0]["step"]
    assert all("Expose the same reference clip" not in action["step"] for action in audit["next_actions"])


def test_audio_goal_audit_reports_incomplete_when_dialogue_not_detected(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)
    full_scene = _full_scene_probe()
    full_scene["final_audio_frequency_evidence"]["detected"]["dialogue_line_2_520hz"] = False

    audit = module._build_audit(
        full_scene,
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        _deferred_casting_decision(),
    )

    assert audit["status"] == "local_incomplete"
    assert audit["completion"]["local_scene_deliverable_complete"] is False
    assert audit["completion"]["overall_goal_complete"] is False
    assert audit["checks"]["dialogue_detected_in_final_audio"] is False


def test_audio_goal_audit_requires_recorded_casting_decision_or_deferral(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {},
    )

    assert audit["status"] == "local_incomplete"
    assert audit["completion"]["local_scene_deliverable_complete"] is False
    assert audit["completion"]["overall_goal_complete"] is False
    assert audit["checks"]["casting_decision_artifact_recorded"] is False
    assert audit["remaining_external_gate"]["recorded_decision_path"] is None


def test_audio_goal_audit_rejects_unsupported_casting_deferral(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)
    unsupported_plan = _casting_plan()
    unsupported_plan["live_comparison_readiness"]["missing"] = []

    audit = module._build_audit(
        _full_scene_probe(),
        unsupported_plan,
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        _deferred_casting_decision(),
    )

    assert audit["status"] == "local_incomplete"
    assert audit["completion"]["local_scene_deliverable_complete"] is False
    assert audit["checks"]["casting_decision_artifact_recorded"] is True
    assert audit["checks"]["casting_comparison_deferred_explicitly"] is False
    assert audit["checks"]["casting_decision_or_deferral_supported"] is False


def test_audio_goal_audit_accepts_ready_live_comparison_as_supported_deferral(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)
    ready_plan = _casting_plan()
    ready_plan["live_comparison_readiness"]["missing"] = []
    ready_plan["live_comparison_readiness"]["can_run_after_consent"] = True

    audit = module._build_audit(
        _full_scene_probe(),
        ready_plan,
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        _deferred_casting_decision(),
    )

    assert audit["status"] == "local_complete_external_casting_deferred"
    assert audit["completion"]["local_scene_deliverable_complete"] is True
    assert audit["checks"]["casting_live_comparison_ready"] is True
    assert audit["checks"]["casting_comparison_deferred_explicitly"] is True
    assert audit["checks"]["casting_decision_or_deferral_supported"] is True
    assert audit["remaining_external_gate"]["missing"] == [
        "live side-by-side samples",
        "filled listening notes",
        "final provider-decision notes",
    ]


def test_audio_goal_audit_accepts_live_failed_manifest_as_supported_deferral(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)
    ready_plan = _casting_plan()
    ready_plan["live_comparison_readiness"]["missing"] = []
    ready_plan["live_comparison_readiness"]["can_run_after_consent"] = True

    audit = module._build_audit(
        _full_scene_probe(),
        ready_plan,
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        _deferred_casting_decision(),
        {
            "mode": "live_failed",
            "network_used": True,
            "side_by_side_complete": False,
            "failure_stage": "fish_audio_synthesize_sample_1",
            "failure": {"status_code": 402},
        },
    )

    assert audit["status"] == "local_complete_external_casting_deferred"
    assert audit["completion"]["local_scene_deliverable_complete"] is True
    assert audit["checks"]["casting_live_comparison_failed"] is True
    assert audit["checks"]["casting_decision_or_deferral_supported"] is True
    assert audit["remaining_external_gate"]["missing"][0] == (
        "provider failure at fish_audio_synthesize_sample_1: HTTP 402"
    )


def test_audio_goal_audit_rejects_casting_deferral_without_notes(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {
            "selected_path": "defer_pending_more_samples",
            "evidence_summary": {
                "has_deferral_notes": False,
            },
        },
    )

    assert audit["status"] == "local_incomplete"
    assert audit["completion"]["local_scene_deliverable_complete"] is False
    assert audit["checks"]["casting_decision_artifact_recorded"] is True
    assert audit["checks"]["casting_comparison_deferred_explicitly"] is False
    assert audit["checks"]["casting_decision_or_deferral_supported"] is False


def test_audio_goal_audit_reports_complete_after_live_casting_decision(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {
            "selected_path": "use_cosyvoice_qwen_stack_for_casting",
            "evidence_summary": {
                "has_live_samples": True,
                "has_side_by_side_samples": True,
                "has_comparison_reference": True,
                "has_listening_notes": True,
                "has_provider_decision_notes": True,
                "sample_count": 2,
            },
        },
    )

    assert audit["status"] == "complete"
    assert audit["completion"]["local_scene_deliverable_complete"] is True
    assert audit["completion"]["overall_goal_complete"] is True
    assert audit["completion"]["why_not_complete"] is None
    assert audit["remaining_external_gate"]["casting_provider_decision"] == "complete"
    assert audit["next_actions"] == []


def test_audio_goal_audit_reports_complete_after_owner_waives_fish_audio(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {
            "selected_path": "use_cosyvoice_qwen_stack_for_casting",
            "decision_notes": "Studio owner waived Fish Audio; proceed with CosyVoice/Qwen.",
            "evidence_summary": {
                "has_live_samples": False,
                "has_side_by_side_samples": False,
                "has_comparison_reference": False,
                "has_listening_notes": False,
                "has_provider_decision_notes": False,
                "has_owner_override_no_fish_audio": True,
                "sample_count": 0,
            },
        },
    )

    assert audit["status"] == "complete"
    assert audit["completion"]["local_scene_deliverable_complete"] is True
    assert audit["completion"]["overall_goal_complete"] is True
    assert audit["completion"]["why_not_complete"] is None
    assert audit["checks"]["casting_provider_decision_owner_override"] is True
    assert audit["checks"]["casting_decision_or_deferral_supported"] is True
    assert audit["remaining_external_gate"]["casting_provider_decision"] == "complete"
    assert audit["next_actions"] == []


def test_audio_goal_audit_does_not_complete_without_reference_backed_casting_evidence(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {
            "selected_path": "use_cosyvoice_qwen_stack_for_casting",
            "evidence_summary": {
                "has_live_samples": True,
                "has_side_by_side_samples": True,
                "has_comparison_reference": False,
                "has_listening_notes": True,
                "has_provider_decision_notes": True,
                "sample_count": 2,
            },
        },
    )

    assert audit["status"] == "local_incomplete"
    assert audit["completion"]["overall_goal_complete"] is False
    assert audit["checks"]["casting_decision_or_deferral_supported"] is False


def test_audio_goal_audit_does_not_complete_without_final_provider_decision_notes(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)

    audit = module._build_audit(
        _full_scene_probe(),
        _casting_plan(),
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {
            "selected_path": "use_cosyvoice_qwen_stack_for_casting",
            "evidence_summary": {
                "has_live_samples": True,
                "has_side_by_side_samples": True,
                "has_comparison_reference": True,
                "has_listening_notes": True,
                "has_provider_decision_notes": False,
                "sample_count": 2,
            },
        },
    )

    assert audit["status"] == "local_incomplete"
    assert audit["completion"]["overall_goal_complete"] is False
    assert audit["checks"]["casting_decision_or_deferral_supported"] is False


def test_audio_goal_audit_accepts_live_casting_decision_without_deferral_plan(monkeypatch):
    module = _load_audit_module()
    monkeypatch.setattr(module, "_artifact_exists", lambda _path: True)
    non_deferred_plan = _casting_plan()
    non_deferred_plan["recommended_decision_now"]["casting_provider"] = "cosyvoice_qwen_stack"
    non_deferred_plan["live_comparison_readiness"]["missing"] = []
    non_deferred_plan["live_comparison_readiness"]["can_run_after_consent"] = True

    audit = module._build_audit(
        _full_scene_probe(),
        non_deferred_plan,
        "Decision: use manual post-render\nDecision: treat `5.04s`",
        {
            "selected_path": "use_cosyvoice_qwen_stack_for_casting",
            "evidence_summary": {
                "has_live_samples": True,
                "has_side_by_side_samples": True,
                "has_comparison_reference": True,
                "has_listening_notes": True,
                "has_provider_decision_notes": True,
                "sample_count": 2,
            },
        },
    )

    assert audit["status"] == "complete"
    assert audit["checks"]["casting_comparison_deferred_explicitly"] is False
    assert audit["checks"]["casting_decision_or_deferral_supported"] is True
