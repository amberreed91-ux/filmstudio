# Provider Capability Layer — Audit & Implementation Report

**Date:** 2026-09-24 · **Branch:** `backend-expansion-dependency-slicing`
**Predecessor:** `docs/reference_conditioning_capability_audit.md` (Local LTX / Phosphene boundary)

---

## TL;DR

Studio's reference intelligence and provider conditioning were already correctly
separated by prior work: the Reference Library + deterministic selector select
strongest-first, and `local_ltx_reference_projection.py` projects that selection
into Local LTX's verified one-image i2v boundary with full trace and fail-closed
validation. What was missing was the **provider-wide** layer: a single
evidence-gated contract describing what every registered video provider can
actually consume, with UNKNOWN semantics. This workstream added that contract
(one new module + one additive hunk in `_reference_debug`) plus a deterministic
test matrix, and completed the ComfyUI Desktop evidence audit.

**Architecture decision: Outcome A + E.** Local LTX single-anchor conditioning is
correct and sufficient for the installed stack (Outcome A). ComfyUI Desktop on
this Mac has a **live-verified programmatic boundary** but **UNKNOWN generation
capability** — no models are installed on 16 GB hardware — so no integration is
justified today (Outcome E for ComfyUI). No Phase 17→19 live A/B was performed:
the existing context-aware anchor path was already live-verified in the prior
audit's capture, and no new untested scenario exists.

---

## Part 1 — Reference architecture metadata audit

Everything the selector and projection need already exists on
`reference_assets` rows / `ReferenceAsset` (`app/models/consistency.py`). No
fields had to be invented:

| Required metadata | Where it lives |
|---|---|
| Character identity / target ownership | `target_type`, `target_id` |
| Category (face, profile, full body, wardrobe, night, day, expression, other) | `category` (+ `reference_role`) |
| Canonical status | `canonical: bool` |
| Approval lifecycle | `approval_state: candidate\|approved\|rejected` |
| Candidate / stale handling | `approval_state`, `stale`/`is_stale`, `lock_status`, `source_status`, `review_status` |
| Scene provenance | `source_shot_id` (scene-scoped reuse enforced by projection) |
| Source type (uploaded vs URL vs generated) | `source_kind: confirmed\|uploaded\|generated` |
| Creation time | `created_at` / `reference_created_at` |
| Look lock info | `look_id`, `lock_status`, `reliability`, `capture_method` |
| Project isolation | `project_id` (+ `validate_consistency_isolation`) |
| Selection audit trail | `ConsistencyPayload.selection_audit` |
| Provider compatibility | now: `provider_capability_contract` (was implicit) |

Two services already implement the required behaviour and were preserved
untouched:

- **Stage 1 selection** — `reference_selection_service.py::select_character_references`
  (identity tiers → context tiers, deterministic, dedup, budget-bounded, audited)
  and `character_visual_reference_service.py::build_consistency_payload_for_shot`.
- **Fail-closed validation** — `reference_validation.py::validate_generation_payload`
  (approved-only, project/scene-owned, canonical-required, ≤9 refs, structured
  actionable `ValidationError` with recovery actions).

## Part 2 — Provider audit (installed code; live probes where possible)

| Provider | Backend / model | Ref capacity | Multi-ref conditioning | Character refs | Environment refs | Ordering | Weighting | Start frame | End frame | Ref video | I2V | T2V | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **local_ltx** | Phosphene 4.15.2 / LTX-2.5 q4 MLX | **1** | No | Yes (trained lane + anchor) | No | No | No | Yes | No | No | Yes | Yes | VERIFIED_LIVE (probe 2026-09-24: /version 4.15.2 `59d733d`, q4_25+gemma4_25 complete) + installed docs/API.md |
| **runway** | Runway hosted / gen4.5 | **1** | No | Yes (promptImage) | Yes (promptImage) | No | No | Yes | UNKNOWN | UNKNOWN | Yes | Yes | VERIFIED_CODE (`RunwayAdapter`: single `promptImage`; local/URL refs degrade to prompt text, recorded in metadata) |
| **happyhorse-r2v** | DashScope / happyhorse-1.1-r2v | **9** | Yes (vendor contract) | Yes | UNKNOWN | UNKNOWN | No | No | UNKNOWN | UNKNOWN | No | Yes | VERIFIED_CODE (media list of ≤9 reference images); consumption of all 9 is vendor-documented only → ordering/consumption UNKNOWN |
| **openrouter** (+ `-video`) | OpenRouter / happyhorse-1.1 | **9** | Yes (vendor contract) | Yes | UNKNOWN | UNKNOWN | No | Yes (`frame_images`) | No | No | Yes | Yes | VERIFIED_CODE (`input_references` ≤9 + `frame_images` first-frame; live probe of a data-URL submit is on record in adapter docs) |
| **minimax_h3_local** | ComfyUI graph / minimax_h3_video_vae | **1** | UNKNOWN (workflow-dependent) | Yes | UNKNOWN | UNKNOWN | No | Yes | UNKNOWN | No | Yes | Yes | VERIFIED_CODE (adapter uploads exactly one reference into graph image inputs; CUDA-gated host) |
| **wan** | DashScope / wan2.6-t2v | **0** | No | No | No | — | — | No | No | No | No | Yes | VERIFIED_CODE (payload carries prompt/parameters only) |
| **higgsfield / generic / amd / simulated** | placeholders | — | — | — | — | — | — | — | — | — | — | — | Not production paths (disabled/simulated); excluded from the contract |

Key truth distinction preserved: **happyhorse-r2v/openrouter accept 9 reference
fields at the API boundary; whether the model consumes all nine and preserves
order is vendor-documented, not verified on this machine — those stay UNKNOWN.**

## Part 3 — Capability contract (new, additive)

`app/services/provider_capability_contract.py` (504 lines, stdlib-only):

- Per-provider declarations: `maximum_reference_images`,
  `reference_conditioning.{multi_reference, character_references,
  environment_references, reference_ordering, reference_weighting, start_frame,
  end_frame, reference_video, i2v, t2v}` — each entry carries its **evidence
  level** (`verified_live`, `verified_code`, `unverified`).
- `UNKNOWN` is a distinct sentinel from `False`. Unverified capabilities are
  never reported as supported and never silently coerced.
- Unregistered providers fail closed: capacity UNKNOWN → projection sends **one
  anchor**, never "all references".
- `project_references_for_provider()` — deterministic, order-preserving,
  deduplicating projection; records `projected` vs `unconsumed` and the reason.
  Only providers with verified capacity ≥2 **and** verified `multi_reference`
  project the full set.
- `provider_reference_trace()` — the Part 9 trace (provider, backend, capacity,
  selected anchor, consumed/unconsumed, provider_job_id, evidence snapshot,
  `model_consumption_claim`), internal metadata only.

Deliberately **not** added (no implementation evidence): supported image formats
and dimensions per provider, upload requirements, provider-side reference
processing. Local LTX's format gate (PNG/JPEG ≤24 MP) lives where it is
enforced — `LocalLTXAdapter._upload_reference` — not as a declarative claim.

**Separation maintained:** the contract is read-only over the Reference Library;
the Reference Library has no knowledge of providers.

## Part 5/6/7 — Projection & context-aware anchor (verified, preserved)

Already landed by the prior workstream and re-verified by its tests this session
(35 tests passed unchanged):

- `local_ltx_reference_projection.py`: canonical-first anchor; the only
  non-canonical substitution is an **explicit full-body shot-plan framing** with
  a canonical face anchor and an approved, same-character, same-scene
  full-body reference; setting references never substitute for character
  identity; stale/candidate/rejected/foreign fail closed.
- `render.py` builds `local_ltx_scene_context` only from **structured shot
  plan** (`framing`, `lighting` from `get_shot_visual_plan`), never prompt
  keywords; scene-context categories (night/day) ride Stage 1 selection.
- Adapter boundary tests pin: exactly one `image` field sent, canonical
  available as recorded fallback, canonical payload never rewritten.

No changes were needed here; the hierarchy in Part 7 is validated by
`test_local_ltx_reference_projection.py` (face-only, full-body-only,
face+body+wardrobe+night, scene 1→2→3→1 leak checks, duplicates, foreign,
stale, candidate/rejected, no-valid-reference fail-closed).

## Part 8/9/10 — Identity protection, trace, fail-closed (verified)

- Canonical truth: projection works on a copy; the consistency payload is never
  rewritten (pinned by boundary tests: `refs[0].canonical is True` after
  submission). Canonical remains `available`/fallback in every trace.
- Part 9 trace fields all exist (adapter-level `local_ltx_reference_trace` with
  `upload_attempts`, `provider_image_path`, `phosphene_job_id`,
  `provider_received_image_count`), now complemented by the provider-generic
  `provider_reference_trace()` helper.
- Part 10: `validate_generation_payload` unchanged and untouched; projection
  never weakens it.

## Part 12/13 — ComfyUI Desktop evidence audit (live, this Mac, 2026-09-24)

**Hardware (verified):** MacBookPro18,3, Apple M1 Pro, 16 GB unified memory;
MPS device reported by PyTorch (`vram_total = 17179869184`, ~7.2 GB free at
probe time).

**Installed capability (verified live at 127.0.0.1:8188):**

| Check | Result |
|---|---|
| ComfyUI version | **0.37.2** (Desktop, embedded Python 3.13.12, PyTorch **2.12.1**) |
| Process | Running now (`~/ComfyUI-Installs/ComfyUI/...`), `--enable-manager` |
| `/system_stats`, `/queue`, `/object_info` | All answered (962 node classes) |
| Model folders (checkpoints, diffusion_models, loras, clip, text_encoders, vae, clip_vision, unet) | **All empty** (`/models/*` returned `[]`; shared dir `~/ComfyUI-Shared/models` empty) |
| Custom nodes | None (default Desktop install) |
| Saved workflows | None in user workflows dir |
| Pinokio neighbours | `wan.git` present but **0** `.safetensors` (not downloaded); H3 Pinokio drive model dirs contain only placeholder files |

**Conditioning nodes present (theoretical, no models):** `LTXVImgToVideo`
(single `image`), `LTXVAddGuide` (single guide image, `iclora_parameters` — the
mechanism behind Ingredients-style sheets), `WanImageToVideo`
(`start_image` only), `WanFirstLastFrameToVideo` (start+end), `WanFunControlToVideo`
(control video). No IPAdapter/InstantID nodes installed.

**Programmatic boundary:** `/prompt` submit, `/history/{id}` status, `/queue`,
`/view` output retrieval — all standard ComfyUI HTTP API, already exploited by
the existing `comfyui_provider.py` / `minimax_h3_local.py` (workflow format
validation included). Cancellation: `/interrupt` exists but is global-by-pid in
Desktop practice → treated UNKNOWN. Deterministic seed: KSampler is seedable,
but no workflow exists to verify → UNKNOWN.

**Layered verdict:**
- *Theoretical:* LTX-2.5 multi-guide conditioning via `LTXVAddGuide` chains exists in core ComfyUI.
- *Installed:* nothing — no models, no custom nodes, no workflows.
- *Hardware-feasible:* 16 GB unified memory is below LTX-2.5 22B-class video
  inference; the Phosphene MLX q4 pack (≈1.4 GB code + model pack on Pinokio)
  was built precisely for this memory class, and Phosphene already runs the
  2.5 engine natively. A duplicate LTX-2.5 path through ComfyUI would add a
  second conditioning implementation without adding capability.
- *Studio-integrable:* the boundary is programmable, but there is nothing
  verified to gain — **no capability ComfyUI can offer today that Phosphene
  cannot, and nothing verified at all.**

## Part 14/16 — ComfyUI decision gate (answered from evidence)

1. Studio selects the full approved multi-reference set (Stage 1). 2–3. Provider
   adapters receive it; verified per-provider capacities above. 4–5. Model
   consumption verified only for local_ltx (one anchor) and declared-by-contract
   for the r2v lanes. 6–7. Ordering/weighting: not guaranteed anywhere except
   Studio-side ordering. 8. No — ComfyUI offers nothing material over Phosphene
   for this use case today. 9–11. It runs on this hardware, is programmable
   without undocumented UI behaviour, but has no models to verify anything.
   12–14. Integration would not require changing canonical truth, but would
   require new adapter + workflow assets with zero verified payoff. **No
   integration step is justified beyond this audit.**

## Parts 18/19/20 — Live A/B

**Not performed, deliberately.** The prior audit's live capture already proved
the one-image consumption and the deterministic anchor behaviour; the
deterministic selector identifies no new anchor scenario beyond the
full-body-framing exception that is already implemented and tested. Per Part 20,
if a non-canonical anchor were found to cause identity drift, the design
already retains canonical anchoring and records the provider's one-image
limitation as the cause. No outputs were scored or ranked.

## Part 22 — Regression results

**Passed this session (362 tests):** provider capability contract (28),
local LTX projection + adapter boundary (35), reference library/validation/
selection/consistency isolation (70), render reference consistency & scene
transition, render state hardening, provider truth contract, create route,
path A/B staging wiring, render polling/retry, adherence, character visual
reference/multi-view/look locks, scene production pipeline, visual training,
H3/ComfyUI provider suites, provider status routes, dialogue provider
selection, phase11 containment (165 in that batch), frontend ReferenceLibrary +
renderProviderCatalog vitest (15), `tsc --noEmit` clean, `git diff --check`
clean, `py_compile` clean.

**Remaining failures — all pre-existing, proven not introduced here.** Isolation
procedure: with my single hunk in `_reference_debug` neutralized (and again with
the whole file stashed to HEAD), the identical failures reproduce; the failure
signature is
`Generation blocked: Scene … the project could not be resolved` from
`reference_validation.py:49`, raised from an **uncommitted dirty-tree hunk** in
`render.py`'s submit path that calls `validate_generation_payload` on every
submit (at HEAD, that call does not exist; `reference_validation.py` itself is
untracked). Affected: 5 tests in `test_render_pipeline_hardening.py` /
`test_render_job_persistence.py` (stub storages that define no project),
2 seed-injection tests in `test_render_provider_safety.py` (fixture mounts no
project), `test_render_ltx_http/_i2v/_pipeline` HTTP suites (expect projects
they never create), and 1 registry-count assertion
(`test_existing_registry_entries_unchanged`: expects 12 adapter keys, the dirty
tree has 13 because `phosphene_training` was added by the visual-training
workstream). **Classification: pre-existing / test-fixture dependent / absorbed
from another workstream — none introduced by this workstream, none hidden.**

## Part 23 — Final architecture decision

**Outcome A + E.**

- **A:** Local LTX single-reference conditioning is the verified capability;
  the deterministic single-anchor projection with the explicit full-body
  framing exception is retained. No change to Local LTX behaviour was needed.
- **E:** ComfyUI Desktop is left UNKNOWN at the generation-capability layer and
  receives no adapter, no dependencies, and no workflow migration. The only
  verified ComfyUI fact is its programmatic boundary, which is already
  abstracted in `providers/comfyui_provider.py` should the model landscape
  change.
- **B is partially pre-existing:** the already-integrated happyhorse-r2v /
  openrouter lanes are genuine multi-reference (≤9) provider paths; the new
  contract makes their verified capacity explicit and projects the full ordered
  set to them — no new integration was required for that.

## Part 24 — Trace summary (per render, verifiable in job metadata)

Studio selected (Stage 1, `selection_audit`) → provider projection (capability
contract + `local_ltx_reference_projection`, `local_ltx_scene_context`) →
adapter received (`provider_payload_metadata` / `upload_attempts`) → execution
backend received (`provider_image_path`, `phosphene_image_field=image`,
`provider_received_image_count=1`) → model consumed (`model_consumption_contract`:
one scalar conditioning image; `model_consumption_claim` in the generic trace).
These four statements are never collapsed.

**Files changed by this workstream:**
- `app/services/provider_capability_contract.py` (new, 504 lines)
- `app/services/test_provider_capability_contract.py` (new, 363 lines)
- `app/services/render.py` (one additive hunk: `_reference_debug` now sources
  reference support from the capability contract; adds
  `provider_support_unknown`; no behavioural change to generation)
- `docs/provider_capability_layer_audit.md` (this report)

**Remaining UNKNOWN:** happyhorse-r2v/openrouter per-reference consumption and
ordering; all ComfyUI generation capabilities; minimax_h3_local
workflow-dependent multi-reference; Runway end-frame/reference-video; Phosphene
Ingredients on LTX-2.5 (upstream IC-LoRA exists; not yet integrated in 4.15.2).
