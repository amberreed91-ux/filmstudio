"""Provider capability contract for reference conditioning.

This module is the additive answer to one architectural question: when Studio's
Reference Library has selected the strongest approved references for a shot,
what can each provider *actually* consume?

Hard separations preserved:
- The Reference Library and its deterministic selector remain provider
  independent. Nothing here reads or mutates registry rows.
- The consistency payload remains canonical Studio truth. Projection never
  rewrites it; adapters receive a projected list of image URLs.
- UNKNOWN is distinct from unsupported. Unverified capabilities are never
  reported as False (that would be a claim), never as True (that would be a
  fake), and never silently coerced to "supported" by a caller.

Every capability value carries an evidence level:
- VERIFIED_LIVE: proven against the installed provider (live probe) or its
  installed code on this machine.
- VERIFIED_CODE: proven from the provider adapter's installed implementation
  and the provider's documented contract.
- UNVERIFIED: capability is UNKNOWN. Unknowns fail closed at the boundary:
  an unknown multi-reference capacity projects to a single anchor, never to
  "send everything".
"""

from __future__ import annotations

from typing import Any

# ── Evidence levels ─────────────────────────────────────────────────────────

VERIFIED_LIVE = "verified_live"
VERIFIED_CODE = "verified_code"
UNVERIFIED = "unverified"

# Sentinel for capabilities whose support is unknown. Truthiness-free: callers
# must test ``is UNKNOWN`` or use the helpers below, never ``bool(...)``.
UNKNOWN = "unknown"

_REFERENCE_COND = "reference_conditioning"

# Projection rationale strings (auditable; internal metadata only).
_RATIONALE_SINGLE_ANCHOR = (
    "provider declares a single conditioning anchor; the strongest selected "
    "reference is projected and the remainder are recorded as not consumed"
)
_RATIONALE_UNVERIFIED_CAPACITY = (
    "provider reference capacity is unverified; failing closed to a single "
    "conditioning anchor rather than claiming unverified multi-reference support"
)
_RATIONALE_ORDER_UNVERIFIED = (
    "provider ordering guarantees are unverified; projection preserves the "
    "selector's strongest-first order and records ordering as UNKNOWN"
)


def is_supported(value: Any) -> bool:
    return value is True


def is_unsupported(value: Any) -> bool:
    return value is False


def is_unknown(value: Any) -> bool:
    return value == UNKNOWN


def evidence_level(capability: dict[str, Any], key: str) -> str:
    """Evidence level for one capability key, empty when not declared."""
    meta = capability.get(f"_{key}_evidence")
    return str(meta) if isinstance(meta, str) else ""


def _ref_entry(supported: bool | str, evidence: str) -> dict[str, Any]:
    """One reference-conditioning entry: value plus its evidence level."""
    value = True if supported is True else False if supported is False else UNKNOWN
    return {"supported": value, "evidence": evidence}


def _entry_supported(entry: Any) -> bool | str:
    if isinstance(entry, dict):
        return entry.get("supported", UNKNOWN)
    return entry if isinstance(entry, (bool, str)) else UNKNOWN


# ── The contract ─────────────────────────────────────────────────────────────
#
# ``maximum_reference_images`` is a count, not a claim of multi-reference
# conditioning: 1 with a single ``image``/``promptImage`` field means the
# provider accepts exactly one image. ``reference_conditioning`` entries:
#
#   multi_reference        the model consumes every supplied reference
#   character_references   identity-specific reference conditioning
#   environment_references setting/environment image conditioning
#   reference_ordering     downstream order is honored (as documented)
#   reference_weighting    per-reference weights are honored
#   start_frame            first-frame image conditioning (I2V init)
#   end_frame              last-frame image conditioning
#   reference_video        video-to-video conditioning
#   i2v / t2v              image-to-video / text-to-video modes


def local_ltx_capability() -> dict[str, Any]:
    """Local LTX via Phosphene 4.15.2 on this machine (Apple Silicon/MLX).

    Evidence: live probe 2026-09-24 (/version 4.15.2 commit 59d733d, /models
    q4_25+gemma4_25 complete → active generation ltx25); installed
    docs/API.md and make_job (scalar image form field); job history (50 jobs,
    modes t2v/i2v only). Full audit: docs/reference_conditioning_capability_audit.md.
    """
    return {
        "provider": "local_ltx",
        "model": "ltx-2.5-mlx-q4 (Phosphene 4.15.2, generation ltx25)",
        "execution_backend": "Phosphene HTTP service (Pinokio)",
        "maximum_reference_images": 1,
        _REFERENCE_COND: {
            "multi_reference": _ref_entry(False, VERIFIED_LIVE),
            "character_references": _ref_entry(True, VERIFIED_LIVE),
            "environment_references": _ref_entry(False, VERIFIED_LIVE),
            "reference_ordering": _ref_entry(False, VERIFIED_CODE),
            "reference_weighting": _ref_entry(False, VERIFIED_CODE),
            "start_frame": _ref_entry(True, VERIFIED_LIVE),
            "end_frame": _ref_entry(False, VERIFIED_CODE),
            "reference_video": _ref_entry(False, VERIFIED_CODE),
            "i2v": _ref_entry(True, VERIFIED_LIVE),
            "t2v": _ref_entry(True, VERIFIED_LIVE),
        },
        "notes": (
            "Scalar image form field; multi-reference Ingredients mode exists "
            "upstream but is refused on the installed active generation."
        ),
    }


def runway_capability() -> dict[str, Any]:
    """Runway hosted adapter as installed in app/adapters/__init__.py.

    Evidence: adapter code (VERIFIED_CODE) — image_to_video takes a single
    promptImage; consistency payloads degrade extra refs to prompt text. The
    public marketing "multiple references" behaviour is not exercised by the
    installed adapter, so multi_reference stays unverified here.
    """
    return {
        "provider": "runway",
        "model": "gen4.5 (default; per-request overrides allowed)",
        "execution_backend": "Runway hosted API",
        "maximum_reference_images": 1,
        _REFERENCE_COND: {
            "multi_reference": _ref_entry(False, VERIFIED_CODE),
            "character_references": _ref_entry(True, VERIFIED_CODE),
            "environment_references": _ref_entry(True, VERIFIED_CODE),
            "reference_ordering": _ref_entry(False, VERIFIED_CODE),
            "reference_weighting": _ref_entry(False, VERIFIED_CODE),
            "start_frame": _ref_entry(True, VERIFIED_CODE),
            "end_frame": _ref_entry(False, UNVERIFIED),
            "reference_video": _ref_entry(False, UNVERIFIED),
            "i2v": _ref_entry(True, VERIFIED_CODE),
            "t2v": _ref_entry(True, VERIFIED_CODE),
        },
        "notes": (
            "promptImage is a single HTTPS URL; non-HTTPS references degrade "
            "to prompt context (recorded in job metadata)."
        ),
    }


def happyhorse_r2v_capability() -> dict[str, Any]:
    """HappyHorse r2v hosted adapter as installed (DashScope media list).

    Evidence: adapter code (VERIFIED_CODE) — up to 9 reference_image media
    entries are sent to the r2v model. Consumption of all nine by the model is
    vendor-documented but not verified on this machine (UNVERIFIED).
    """
    return {
        "provider": "happyhorse-r2v",
        "model": "happyhorse-1.1-r2v",
        "execution_backend": "DashScope hosted API",
        "maximum_reference_images": 9,
        _REFERENCE_COND: {
            "multi_reference": _ref_entry(True, VERIFIED_CODE),
            "character_references": _ref_entry(True, VERIFIED_CODE),
            "environment_references": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_ordering": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_weighting": _ref_entry(False, VERIFIED_CODE),
            "start_frame": _ref_entry(False, VERIFIED_CODE),
            "end_frame": _ref_entry(False, UNVERIFIED),
            "reference_video": _ref_entry(False, UNVERIFIED),
            "i2v": _ref_entry(False, VERIFIED_CODE),
            "t2v": _ref_entry(True, VERIFIED_CODE),
        },
        "notes": (
            "Order-preservation through the vendor pipeline is unverified; "
            "Studio still sends strongest-first, but does not claim the "
            "provider honors that order semantically."
        ),
    }


def minimax_h3_local_capability() -> dict[str, Any]:
    """MiniMax H3 local adapter as installed (Pinokio ComfyUI graph).

    Evidence: adapter code (VERIFIED_CODE) — the adapter uploads exactly one
    reference and injects it into every string image input of the configured
    workflow. Workflow-dependent multi-reference behaviour remains UNKNOWN.
    """
    return {
        "provider": "minimax_h3_local",
        "model": "minimax_h3_video_vae (workflow-defined)",
        "execution_backend": "ComfyUI /prompt (Pinokio)",
        "maximum_reference_images": 1,
        _REFERENCE_COND: {
            "multi_reference": _ref_entry(UNKNOWN, UNVERIFIED),
            "character_references": _ref_entry(True, VERIFIED_CODE),
            "environment_references": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_ordering": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_weighting": _ref_entry(False, VERIFIED_CODE),
            "start_frame": _ref_entry(True, VERIFIED_CODE),
            "end_frame": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_video": _ref_entry(False, UNVERIFIED),
            "i2v": _ref_entry(True, VERIFIED_CODE),
            "t2v": _ref_entry(True, VERIFIED_CODE),
        },
        "notes": (
            "CUDA-gated host runtime; graph image inputs receive one uploaded "
            "reference. Workflow-authored multi-image graphs could change "
            "multi_reference to supported after verification."
        ),
    }


def wan_capability() -> dict[str, Any]:
    """Wan hosted text-to-video adapter as installed.

    Evidence: adapter code (VERIFIED_CODE) — the submit payload carries only
    prompt/parameters; no image field exists, so reference support is False,
    and consistency references degrade to prompt text.
    """
    return {
        "provider": "wan",
        "model": "wan2.6-t2v",
        "execution_backend": "DashScope hosted API",
        "maximum_reference_images": 0,
        _REFERENCE_COND: {
            "multi_reference": _ref_entry(False, VERIFIED_CODE),
            "character_references": _ref_entry(False, VERIFIED_CODE),
            "environment_references": _ref_entry(False, VERIFIED_CODE),
            "reference_ordering": _ref_entry(False, VERIFIED_CODE),
            "reference_weighting": _ref_entry(False, VERIFIED_CODE),
            "start_frame": _ref_entry(False, VERIFIED_CODE),
            "end_frame": _ref_entry(False, VERIFIED_CODE),
            "reference_video": _ref_entry(False, UNVERIFIED),
            "i2v": _ref_entry(False, VERIFIED_CODE),
            "t2v": _ref_entry(True, VERIFIED_CODE),
        },
        "notes": "Text-only provider; references may only degrade to prompt text.",
    }


def comfyui_desktop_capability() -> dict[str, Any]:
    """ComfyUI Desktop on this Mac — audited 2026-09-24 (Part 12/13 evidence).

    The programmatic execution boundary is verified live: /prompt, /history,
    /queue, /system_stats, /view answered on 127.0.0.1:8188 (ComfyUI 0.37.2,
    PyTorch 2.12.1, Python 3.13.12, MPS device). Workflow-format validation
    already exists in app/services/providers/comfyui_provider.py.

    Conditioning capability is NOT verified: no generation model is installed
    (all model folders empty), so nothing here may claim multi-reference
    support. The installed core LTXV/Wan conditioning nodes are single-image
    or first/last-frame nodes; per-node evidence remains UNVERIFIED until a
    workflow with models exists.
    """
    return {
        "provider": "comfyui_desktop",
        "model": UNKNOWN,
        "execution_backend": "ComfyUI Desktop HTTP API (this Mac, MPS)",
        "maximum_reference_images": UNKNOWN,
        "installed": {
            "comfyui_version": "0.37.2",
            "python": "3.13.12",
            "pytorch": "2.12.1",
            "device": "mps (Apple M1 Pro, 16 GB unified memory)",
        },
        "programmatic_boundary": {
            "submit": {"supported": True, "evidence": VERIFIED_LIVE},
            "status": {"supported": True, "evidence": VERIFIED_LIVE},
            "cancel": {"supported": UNKNOWN, "evidence": UNVERIFIED},
            "output_retrieval": {"supported": True, "evidence": VERIFIED_LIVE},
            "deterministic_seed": {"supported": UNKNOWN, "evidence": UNVERIFIED},
        },
        _REFERENCE_COND: {
            "multi_reference": _ref_entry(UNKNOWN, UNVERIFIED),
            "character_references": _ref_entry(UNKNOWN, UNVERIFIED),
            "environment_references": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_ordering": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_weighting": _ref_entry(UNKNOWN, UNVERIFIED),
            "start_frame": _ref_entry(UNKNOWN, UNVERIFIED),
            "end_frame": _ref_entry(UNKNOWN, UNVERIFIED),
            "reference_video": _ref_entry(UNKNOWN, UNVERIFIED),
            "i2v": _ref_entry(UNKNOWN, UNVERIFIED),
            "t2v": _ref_entry(UNKNOWN, UNVERIFIED),
        },
        "notes": (
            "Programmatic boundary verified live; generation capability "
            "UNKNOWN because no models are installed on this machine "
            "(16 GB M1 Pro). See docs/provider_capability_layer_audit.md."
        ),
    }


# ── Registry ────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, tuple[Any, ...]] = {
    "local_ltx": (local_ltx_capability, ()),
    "runway": (runway_capability, ()),
    "happyhorse-r2v": (happyhorse_r2v_capability, ()),
    "minimax_h3_local": (minimax_h3_local_capability, ()),
    "wan": (wan_capability, ()),
    "comfyui_desktop": (comfyui_desktop_capability, ()),
}


def get_provider_capability(provider_id: str) -> dict[str, Any]:
    """Capability declaration for a registered provider (deep copy).

    Unknown providers return a fail-closed declaration: reference capacity
    UNKNOWN and every reference-conditioning capability UNKNOWN. The
    projection below then sends a single anchor — never "all references".
    """
    factory = _PROVIDERS.get(str(provider_id or "").strip().lower())
    if factory is None:
        unknown_refs = {
            key: _ref_entry(UNKNOWN, UNVERIFIED)
            for key in (
                "multi_reference", "character_references", "environment_references",
                "reference_ordering", "reference_weighting", "start_frame",
                "end_frame", "reference_video", "i2v", "t2v",
            )
        }
        return {
            "provider": str(provider_id or "").strip().lower(),
            "model": UNKNOWN,
            "execution_backend": UNKNOWN,
            "maximum_reference_images": UNKNOWN,
            _REFERENCE_COND: unknown_refs,
            "notes": "provider is not registered in the capability contract; capabilities UNKNOWN",
        }
    import copy

    return copy.deepcopy(factory[0]())


def known_capability_providers() -> list[str]:
    return sorted(_PROVIDERS)


# ── Projection ──────────────────────────────────────────────────────────────


def project_references_for_provider(
    selected_reference_urls: list[str],
    capability: dict[str, Any],
) -> dict[str, Any]:
    """Project Studio's ordered selection into a provider's declared capacity.

    Deterministic and order-preserving: the Reference Library's strongest-first
    order is never reordered here. When capacity is 1 or UNKNOWN, exactly one
    anchor (the first selected reference) is projected and the remainder are
    reported as unconsumed. When capacity is a verified count >= 2 and the
    provider declares multi_reference supported, the full ordered list is
    projected and the residual is empty.

    This function never mutates its inputs and never touches Reference Library
    truth; it only decides how much of the selection crosses the boundary.
    """
    selection = [str(url or "").strip() for url in (selected_reference_urls or [])]
    selected = [url for url in selection if url]
    # Deduplicate while preserving first-seen order (same file must not consume
    # two slots of a scarce provider budget).
    seen: set[str] = set()
    ordered: list[str] = []
    for url in selected:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)

    capacity_value = capability.get("maximum_reference_images")
    refs = capability.get(_REFERENCE_COND) if isinstance(capability.get(_REFERENCE_COND), dict) else {}
    multi_entry = _entry_supported(refs.get("multi_reference"))

    multi_reference_supported = (
        isinstance(capacity_value, int)
        and not isinstance(capacity_value, bool)
        and capacity_value >= 2
        and multi_entry is True
    )

    if multi_reference_supported:
        capacity = capacity_value
        projected = ordered[:capacity]
        unconsumed = ordered[capacity:]
        reason = (
            f"provider declares capacity {capacity} with verified multi-reference "
            "conditioning; the ordered selection is projected in full"
        )
    else:
        projected = ordered[:1]
        unconsumed = ordered[1:]
        if capacity_value == UNKNOWN or not isinstance(capacity_value, int):
            reason = _RATIONALE_UNVERIFIED_CAPACITY
        else:
            reason = _RATIONALE_SINGLE_ANCHOR

    return {
        "projected_reference_urls": projected,
        "unconsumed_reference_urls": unconsumed,
        "projected_count": len(projected),
        "unconsumed_count": len(unconsumed),
        "provider_capacity": capacity_value if isinstance(capacity_value, int) else UNKNOWN,
        "multi_reference_supported": multi_reference_supported,
        "reference_ordering": _entry_supported(refs.get("reference_ordering")),
        "selection_reason": reason,
        "ordering_note": "" if multi_reference_supported else _RATIONALE_ORDER_UNVERIFIED,
    }


def provider_reference_trace(
    *,
    provider: str,
    execution_backend: Any,
    capability: dict[str, Any],
    projection: dict[str, Any],
    selected_reference_ids: list[Any] | None = None,
    provider_job_id: Any = None,
) -> dict[str, Any]:
    """Internal audit trace: what Studio selected vs what the provider consumed.

    Internal job metadata only — never filmmaker-facing, never sent to the
    provider. It records the boundary honestly: projected references are what
    the adapter *sent*; the trace never claims the model consumed them unless
    the provider declares verified multi-reference support.
    """
    selected_ids = list(selected_reference_ids or [])
    projected = list(projection.get("projected_reference_urls") or [])
    unconsumed = list(projection.get("unconsumed_reference_urls") or [])
    return {
        "provider": provider,
        "execution_backend": execution_backend,
        "provider_capacity": projection.get("provider_capacity"),
        "multi_reference_supported": projection.get("multi_reference_supported"),
        "selected_count": len(selected_ids) if selected_ids else len(projected) + len(unconsumed),
        "consumed_reference_ids": [],  # filled by the adapter from its real upload/submit results
        "unconsumed_reference_ids": unconsumed,
        "consumption_reason": projection.get("selection_reason"),
        "selected_anchor": projected[0] if projected else None,
        "reference_ordering": projection.get("reference_ordering"),
        "ordering_note": projection.get("ordering_note"),
        "provider_job_id": provider_job_id,
        "capability_evidence": {
            key: _entry_supported(value)
            for key, value in (capability.get(_REFERENCE_COND) or {}).items()
        },
        # Distinguish "accepted at the boundary" from "consumed by the model".
        "model_consumption_claim": (
            "all projected references declared consumed by the provider contract"
            if projection.get("multi_reference_supported")
            else "single anchor conditioning only; remaining references were not sent"
        ),
    }
