"""Tests for the director-facing shot signals payload.

Two rules from AGENTS.md govern this boundary and are asserted here: no scores,
ratings, or percentages reach the director, and a signal with nothing to say
stays quiet rather than rendering a reassuring row.
"""

from app.models import RenderJobInput, RenderJobModel
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services.shot_signals_service import (
    build_exclusion_signal,
    build_identity_signal,
    build_intent_signal,
    build_reference_signal,
    build_shot_signals,
)


def _job(**kwargs) -> RenderJobModel:
    input_payload = kwargs.pop("input_payload", None) or RenderJobInput(
        shot_id="scene_001_shot_002", prompt="MAYA turns."
    )
    return RenderJobModel(
        id="job-signals-1",
        project_id="proj-signals",
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        status="complete",
        input_payload=input_payload,
        created_at="2026-08-16T00:00:00",
        updated_at="2026-08-16T00:00:00",
        **kwargs,
    )


# ── intent fidelity ──────────────────────────────────────────────────────────


def test_intact_intent_stays_quiet():
    job = _job(input_payload=RenderJobInput(parameters={"intent_fidelity": {"status": "intact"}}))
    assert build_intent_signal(job)["status"] == "quiet"


def test_reduced_intent_surfaces_the_note_and_phrases():
    job = _job(
        input_payload=RenderJobInput(
            parameters={
                "intent_fidelity": {
                    "status": "reduced",
                    "advisory_note": 'The prompt no longer carries "never stops moving".',
                    "slots": {
                        "character_state": {"dropped_elements": ["never stops moving", "dry mud"]}
                    },
                }
            }
        )
    )
    signal = build_intent_signal(job)
    assert signal["status"] == "attention"
    assert "never stops moving" in signal["dropped_phrases"]
    assert "dry mud" in signal["dropped_phrases"]


def test_missing_intent_record_stays_quiet():
    assert build_intent_signal(_job())["status"] == "quiet"


# ── identity ─────────────────────────────────────────────────────────────────


def _identity_job(record: dict) -> RenderJobModel:
    return _job(metadata={"character_identity_verification": record})


def test_identity_drift_is_reported_in_plain_language():
    signal = build_identity_signal(
        _identity_job(
            {
                "status": "identity_drift",
                "measures_identity": True,
                "characters": [
                    {"character_name": "MAYA", "status": "identity_drift", "similarity": 0.11}
                ],
            }
        )
    )
    assert signal["status"] == "attention"
    assert "MAYA" in signal["note"]
    assert "same character" in signal["note"]


def test_identity_similarity_numbers_never_reach_the_director():
    signal = build_identity_signal(
        _identity_job(
            {
                "status": "identity_drift",
                "measures_identity": True,
                "characters": [
                    {"character_name": "MAYA", "status": "identity_drift", "similarity": 0.6142}
                ],
            }
        )
    )
    serialised = str(signal)
    assert "0.6142" not in serialised
    assert "similarity" not in serialised
    assert "%" not in serialised


def test_unmeasurable_identity_stays_quiet_rather_than_alarming():
    """An unconfigured embedder must not look like a finding about the shot."""
    for status in ("unavailable", "not_applicable", "unknown"):
        signal = build_identity_signal(_identity_job({"status": status, "reason": "embedding_unavailable"}))
        assert signal["status"] == "quiet", status


def test_general_visual_embedding_is_qualified_not_presented_as_likeness():
    signal = build_identity_signal(
        _identity_job(
            {
                "status": "consistent",
                "measures_identity": False,
                "characters": [{"character_name": "MAYA", "status": "consistent"}],
            }
        )
    )
    assert "visual similarity rather than facial likeness" in signal["note"]


def test_face_embedding_carries_no_qualifier():
    signal = build_identity_signal(
        _identity_job(
            {
                "status": "consistent",
                "measures_identity": True,
                "characters": [{"character_name": "MAYA", "status": "consistent"}],
            }
        )
    )
    assert "rather than facial likeness" not in signal["note"]


# ── references ───────────────────────────────────────────────────────────────


def test_reference_signal_reports_roles():
    payload = ConsistencyPayload(
        project_id="proj-signals",
        mode="identity_lock",
        refs=[
            ReferenceAsset(
                ref_id="charlock:c1:general",
                kind="character_full",
                image_url="/outputs/references/p/a.jpg",
                project_id="proj-signals",
            ),
            ReferenceAsset(
                ref_id="charlock:c1:alternate_angle",
                kind="character_full",
                image_url="/outputs/references/p/b.jpg",
                project_id="proj-signals",
            ),
        ],
    )
    job = _job(input_payload=RenderJobInput(consistency_payload=payload))
    signal = build_reference_signal(job)
    assert signal["status"] == "settled"
    assert {ref["role"] for ref in signal["references"]} == {"general", "alternate_angle"}


def test_no_references_stays_quiet():
    assert build_reference_signal(_job())["status"] == "quiet"


# ── exclusions ───────────────────────────────────────────────────────────────


def test_exclusions_are_listed():
    job = _job(input_payload=RenderJobInput(negative_prompt="extra people, watermark, blurry"))
    signal = build_exclusion_signal(job)
    assert signal["terms"] == ["extra people", "watermark", "blurry"]


def test_no_exclusions_stays_quiet():
    assert build_exclusion_signal(_job())["status"] == "quiet"


# ── assembly ─────────────────────────────────────────────────────────────────


def test_job_with_nothing_recorded_is_entirely_quiet():
    result = build_shot_signals(_job())
    assert result["status"] == "quiet"
    assert result["signals"] == []
    # The reasons are kept for diagnosis but are not director-facing content.
    assert len(result["quiet_signals"]) == 4


def test_any_attention_signal_raises_the_overall_status():
    job = _job(
        input_payload=RenderJobInput(negative_prompt="watermark"),
        metadata={
            "character_identity_verification": {
                "status": "identity_drift",
                "measures_identity": True,
                "characters": [{"character_name": "MAYA", "status": "identity_drift"}],
            }
        },
    )
    result = build_shot_signals(job)
    assert result["status"] == "attention"


def test_settled_signals_alone_do_not_raise_attention():
    job = _job(input_payload=RenderJobInput(negative_prompt="watermark"))
    assert build_shot_signals(job)["status"] == "settled"


def test_assembled_payload_carries_no_digits_in_director_facing_notes():
    """Counts of things are fine; scores and percentages are not."""
    job = _job(
        metadata={
            "character_identity_verification": {
                "status": "identity_drift",
                "measures_identity": True,
                "characters": [
                    {"character_name": "MAYA", "status": "identity_drift", "similarity": 0.42}
                ],
            }
        }
    )
    result = build_shot_signals(job)
    identity_note = next(s["note"] for s in result["signals"] if s["kind"] == "character_identity")
    assert "%" not in identity_note
    assert "0.42" not in identity_note
