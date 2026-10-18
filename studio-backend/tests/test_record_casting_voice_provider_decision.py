from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_decision_module():
    path = _BACKEND_ROOT / "scripts" / "record_casting_voice_provider_decision.py"
    spec = importlib.util.spec_from_file_location("record_casting_voice_provider_decision", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_sample_pair(tmp_path: Path, index: int) -> dict:
    fish_path = tmp_path / f"sample-{index}-fish.mp3"
    cosy_path = tmp_path / f"sample-{index}-cosy.mp3"
    fish_path.write_bytes(f"fish-{index}".encode())
    cosy_path.write_bytes(f"cosy-{index}".encode())
    return {
        "index": index,
        "text": f"Line {index}",
        "emotion_instruction": "controlled unease",
        "fish_audio": {"path": str(fish_path)},
        "cosyvoice": {"path": str(cosy_path)},
    }


def _listening_row(sample: dict, *, preferred_provider: str = "cosyvoice_voice_clone") -> dict:
    return {
        "index": sample["index"],
        "text": sample["text"],
        "emotion_instruction": sample["emotion_instruction"],
        "cosyvoice_voice_clone": {
            "likeness_evidence": "Close enough to keep character identity stable.",
        },
        "fish_audio_s2_pro_clone": {
            "naturalness_evidence": "Useful reference, but less controlled on this line.",
        },
        "preferred_provider_for_this_line": preferred_provider,
    }


def _provider_decision(selected_path: str = "use_cosyvoice_qwen_stack_for_casting") -> dict:
    return {
        "selected_path": selected_path,
        "reason_to_keep_fish_audio": (
            "Fish Audio held a stronger likeness on both lines."
            if selected_path == "keep_fish_audio_for_casting"
            else ""
        ),
        "reason_to_use_single_dashscope_stack": (
            "CosyVoice held likeness and emotional control while fitting the existing stack."
            if selected_path == "use_cosyvoice_qwen_stack_for_casting"
            else ""
        ),
        "reason_to_defer": "",
        "follow_up_needed": "",
    }


def test_records_defer_without_live_evidence(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "missing-live.json"

    decision = module._build_decision(
        selected_path="defer_pending_more_samples",
        decision_notes="Need a same-speaker reference clip before choosing.",
        evidence_path=evidence_path,
        reviewer="Amber",
    )

    assert decision["selected_path"] == "defer_pending_more_samples"
    assert decision["reviewer"] == "Amber"
    assert decision["evidence_summary"] == {
        "evidence_found": False,
        "has_live_samples": False,
        "has_side_by_side_samples": False,
        "has_comparison_reference": False,
        "has_listening_notes": False,
        "has_provider_decision_notes": False,
        "has_deferral_notes": True,
        "has_owner_override_no_fish_audio": False,
        "sample_count": 0,
    }


def test_rejects_provider_selection_without_live_listening_notes(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "samples": [_write_sample_pair(tmp_path, 0)],
                "human_evaluation_template": {"sample_rows": []},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filled listening notes"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice matched the reference well enough.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_with_partial_listening_notes(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    sample_1 = _write_sample_pair(tmp_path, 1)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [sample_0, sample_1],
                "human_evaluation_template": {
                    "sample_rows": [_listening_row(sample_0)],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filled listening notes"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness on one line.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_without_shared_reference_evidence(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    sample_1 = _write_sample_pair(tmp_path, 1)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "samples": [sample_0, sample_1],
                "human_evaluation_template": {
                    "sample_rows": [_listening_row(sample_0), _listening_row(sample_1)],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shared reference evidence"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness across both samples.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_with_only_one_live_sample(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [sample_0],
                "human_evaluation_template": {
                    "sample_rows": [_listening_row(sample_0)],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="at least two samples"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness on one sample.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_without_concrete_side_by_side_audio_files(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    missing_sample = {
        "index": 0,
        "text": "You good?",
        "emotion_instruction": "controlled unease",
    }
    sample_1 = _write_sample_pair(tmp_path, 1)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [
                    {
                        "index": 0,
                        "text": "You good?",
                        "fish_audio": {"path": str(tmp_path / "missing-fish.mp3")},
                        "cosyvoice": {"path": str(tmp_path / "missing-cosy.mp3")},
                    },
                    sample_1,
                ],
                "human_evaluation_template": {
                    "sample_rows": [_listening_row(missing_sample), _listening_row(sample_1)],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="concrete Fish/CosyVoice audio files"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness across both samples.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_with_mismatched_listening_row_sample_text(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    sample_1 = _write_sample_pair(tmp_path, 1)
    mismatched_row = _listening_row(sample_0)
    mismatched_row["text"] = "Notes for a different line."
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [sample_0, sample_1],
                "human_evaluation_template": {
                    "sample_rows": [mismatched_row, _listening_row(sample_1)],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filled listening notes"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness across both samples.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_with_ambiguous_line_preference(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    sample_1 = _write_sample_pair(tmp_path, 1)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [sample_0, sample_1],
                "human_evaluation_template": {
                    "sample_rows": [
                        _listening_row(sample_0, preferred_provider="cosyvoice"),
                        _listening_row(sample_1),
                    ],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="filled listening notes"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness across both samples.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_rejects_provider_selection_without_final_provider_decision_notes(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    sample_1 = _write_sample_pair(tmp_path, 1)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [sample_0, sample_1],
                "human_evaluation_template": {
                    "sample_rows": [_listening_row(sample_0), _listening_row(sample_1)],
                    "provider_decision": {
                        "selected_path": "use_cosyvoice_qwen_stack_for_casting",
                        "reason_to_keep_fish_audio": "",
                        "reason_to_use_single_dashscope_stack": "",
                        "reason_to_defer": "",
                        "follow_up_needed": "",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="completed final provider-decision section"):
        module._build_decision(
            selected_path="use_cosyvoice_qwen_stack_for_casting",
            decision_notes="CosyVoice held likeness across both samples.",
            evidence_path=evidence_path,
            reviewer="Amber",
        )


def test_accepts_provider_selection_with_live_samples_and_notes(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "live.json"
    sample_0 = _write_sample_pair(tmp_path, 0)
    sample_1 = _write_sample_pair(tmp_path, 1)
    evidence_path.write_text(
        json.dumps(
            {
                "network_used": True,
                "reference_audio": "/tmp/reference.wav",
                "reference_audio_sha256": "abc123",
                "public_reference_url": "https://example.com/reference.wav",
                "samples": [sample_0, sample_1],
                "human_evaluation_template": {
                    "sample_rows": [_listening_row(sample_0), _listening_row(sample_1)],
                    "provider_decision": _provider_decision(),
                },
            }
        ),
        encoding="utf-8",
    )

    decision = module._build_decision(
        selected_path="use_cosyvoice_qwen_stack_for_casting",
        decision_notes="CosyVoice held likeness and emotional control across the samples.",
        evidence_path=evidence_path,
        reviewer="Amber",
    )

    assert decision["selected_path"] == "use_cosyvoice_qwen_stack_for_casting"
    assert decision["evidence_summary"]["has_live_samples"] is True
    assert decision["evidence_summary"]["has_side_by_side_samples"] is True
    assert decision["evidence_summary"]["has_comparison_reference"] is True
    assert decision["evidence_summary"]["has_listening_notes"] is True
    assert decision["evidence_summary"]["has_provider_decision_notes"] is True
    assert decision["evidence_summary"]["has_deferral_notes"] is False
    assert decision["evidence_summary"]["has_owner_override_no_fish_audio"] is False
    assert decision["evidence_summary"]["sample_count"] == 2


def test_accepts_owner_override_to_use_cosyvoice_when_fish_audio_is_unavailable(tmp_path: Path):
    module = _load_decision_module()
    evidence_path = tmp_path / "missing-live.json"

    decision = module._build_decision(
        selected_path="use_cosyvoice_qwen_stack_for_casting",
        decision_notes=(
            "Studio owner waived Fish Audio after the provider was unavailable; "
            "proceed with the already integrated CosyVoice/Qwen stack."
        ),
        evidence_path=evidence_path,
        reviewer="Amber",
        allow_owner_override_no_fish_audio=True,
    )

    assert decision["selected_path"] == "use_cosyvoice_qwen_stack_for_casting"
    assert decision["evidence_summary"]["has_live_samples"] is False
    assert decision["evidence_summary"]["has_owner_override_no_fish_audio"] is True
    assert "waived Fish Audio" in decision["decision_notes"]


def test_rejects_owner_override_no_fish_audio_for_fish_selection(tmp_path: Path):
    module = _load_decision_module()

    with pytest.raises(ValueError, match="only valid for the CosyVoice/Qwen stack"):
        module._build_decision(
            selected_path="keep_fish_audio_for_casting",
            decision_notes="Keep Fish anyway.",
            evidence_path=tmp_path / "missing-live.json",
            reviewer="Amber",
            allow_owner_override_no_fish_audio=True,
        )
