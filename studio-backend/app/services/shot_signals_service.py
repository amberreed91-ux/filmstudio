"""
Shot signals — the director-facing view of what the pipeline noticed.

Three mechanisms added in Aug 2026 record their findings on the render job and
nowhere else: the intent-fidelity check (`input_payload.parameters`), identity
verification (`metadata`), and the reference set actually sent to the provider
(`input_payload.consistency_payload`). Useful signals with no reader are the
same as no signals, so this service assembles them into one payload a room can
render.

Two rules shape the output, both from AGENTS.md:

- **No scores, ratings, or percentages.** The underlying records carry cosine
  similarities and character counts because logs and debugging need them. None
  of that crosses this boundary. A director gets "reads as the same person" or
  "may not read as the same character", never 0.61.
- **Silence is often stronger than commentary.** A signal with nothing to say
  returns `status: "quiet"` and no note, so a room can render nothing rather
  than a reassuring row that trains the eye to skip the panel.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("shot_signals")


# Identity verification statuses → director-facing language. The underlying
# service also emits raw similarity values; those stop here.
IDENTITY_LANGUAGE = {
    "consistent": "Reads as the same person across the sampled frames.",
    "plausibly_consistent": (
        "Close enough to read as the same person, though not a clean match on every frame."
    ),
    "identity_drift": (
        "This may not read as the same character as the locked reference."
    ),
}

# Statuses that mean "we could not measure", which is not a finding about the
# shot and must not be presented as one.
IDENTITY_NON_FINDINGS = {"not_applicable", "unavailable", "unknown"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _quiet(kind: str, reason: str = "") -> dict[str, Any]:
    return {"kind": kind, "status": "quiet", "note": "", "reason": reason}


def build_intent_signal(job: Any) -> dict[str, Any]:
    """What the prompt lost to budget compression before it was sent."""
    parameters = _as_dict(getattr(getattr(job, "input_payload", None), "parameters", None))
    record = _as_dict(parameters.get("intent_fidelity"))
    if not record:
        return _quiet("intent_fidelity", "not_recorded")

    status = str(record.get("status") or "unknown")
    note = str(record.get("advisory_note") or "").strip()
    if status != "reduced" or not note:
        # "intact" is the common case and says nothing worth a row.
        return _quiet("intent_fidelity", status)

    # Surface the dropped phrases themselves — recognition is the point, and
    # they are the director's own words.
    dropped: list[str] = []
    for slot_report in _as_dict(record.get("slots")).values():
        if not isinstance(slot_report, dict):
            continue
        for element in slot_report.get("dropped_elements") or []:
            text = str(element).strip()
            if text and text not in dropped:
                dropped.append(text)

    return {
        "kind": "intent_fidelity",
        "status": "attention",
        "note": note,
        "dropped_phrases": dropped[:6],
    }


def build_identity_signal(job: Any) -> dict[str, Any]:
    """Whether the rendered characters still read as their locked references."""
    metadata = _as_dict(getattr(job, "metadata", None))
    record = _as_dict(metadata.get("character_identity_verification"))
    if not record:
        return _quiet("character_identity", "not_recorded")

    status = str(record.get("status") or "unknown")
    if status in IDENTITY_NON_FINDINGS:
        # Could not measure. Reporting this as a finding would turn an
        # unconfigured embedder into a permanent false alarm.
        return _quiet("character_identity", str(record.get("reason") or status))

    characters = [
        {
            "character_name": str(row.get("character_name") or "").strip()
            or str(row.get("character_id") or ""),
            "reading": IDENTITY_LANGUAGE.get(str(row.get("status") or ""), ""),
            "drifted": str(row.get("status") or "") == "identity_drift",
        }
        for row in record.get("characters") or []
        if isinstance(row, dict)
    ]

    # A general-visual embedding answers "does this look like the same picture",
    # not "is this the same face". Saying so keeps a continuity signal from being
    # read as a likeness verdict.
    measures_identity = bool(record.get("measures_identity"))
    qualifier = (
        ""
        if measures_identity
        else " Based on overall visual similarity rather than facial likeness."
    )

    if status == "identity_drift":
        drifted = [row["character_name"] for row in characters if row["drifted"]]
        subject = ", ".join(name for name in drifted if name) or "A character in this shot"
        return {
            "kind": "character_identity",
            "status": "attention",
            "note": f"{subject} may not read as the same character here.{qualifier}",
            "characters": characters,
            "measures_identity": measures_identity,
        }

    return {
        "kind": "character_identity",
        "status": "settled",
        "note": IDENTITY_LANGUAGE.get(status, "") + qualifier,
        "characters": characters,
        "measures_identity": measures_identity,
    }


def build_reference_signal(job: Any) -> dict[str, Any]:
    """Which locked character references conditioned this render."""
    payload = getattr(getattr(job, "input_payload", None), "consistency_payload", None)
    if payload is None:
        return _quiet("character_references", "none_attached")

    refs = getattr(payload, "refs", None) or []
    if not refs:
        return _quiet("character_references", "none_attached")

    references = []
    for ref in refs:
        ref_id = str(getattr(ref, "ref_id", "") or "")
        # ref_id is "charlock:<character_id>:<role>" for locked references.
        role = ref_id.rsplit(":", 1)[-1] if ref_id.count(":") >= 2 else "general"
        references.append(
            {
                "ref_id": ref_id,
                "role": role,
                "image_url": str(getattr(ref, "image_url", "") or ""),
                "source_shot_id": getattr(ref, "source_shot_id", None),
            }
        )

    return {
        "kind": "character_references",
        "status": "settled",
        "note": (
            f"{len(references)} locked reference"
            f"{'' if len(references) == 1 else 's'} conditioned this render."
        ),
        "references": references,
    }


def build_exclusion_signal(job: Any) -> dict[str, Any]:
    """What the render was told to keep out of frame."""
    negative = str(getattr(getattr(job, "input_payload", None), "negative_prompt", "") or "").strip()
    if not negative:
        return _quiet("exclusions", "none_sent")
    terms = [term.strip() for term in negative.split(",") if term.strip()]
    return {
        "kind": "exclusions",
        "status": "settled",
        "note": f"{len(terms)} exclusions were sent alongside the shot.",
        "terms": terms,
    }


def build_shot_signals(job: Any) -> dict[str, Any]:
    """Assemble every director-facing signal recorded on one render job."""
    signals = [
        build_intent_signal(job),
        build_identity_signal(job),
        build_reference_signal(job),
        build_exclusion_signal(job),
    ]
    visible = [signal for signal in signals if signal["status"] != "quiet"]
    needs_attention = [signal for signal in visible if signal["status"] == "attention"]

    return {
        "job_id": str(getattr(job, "id", "") or ""),
        "shot_id": str(getattr(job, "shot_id", "") or ""),
        "project_id": str(getattr(job, "project_id", "") or ""),
        "status": "attention" if needs_attention else ("settled" if visible else "quiet"),
        "signals": visible,
        # Kept so a room can distinguish "nothing to say" from "not measured",
        # without showing either to the director.
        "quiet_signals": [
            {"kind": signal["kind"], "reason": signal.get("reason", "")}
            for signal in signals
            if signal["status"] == "quiet"
        ],
    }
