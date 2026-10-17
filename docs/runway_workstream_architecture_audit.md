# Runway Workstream — Mandatory Architecture Audit (pre-implementation)

Date: 2026-09-25 · Branch: `backend-expansion-dependency-slicing`
Scope: everything the workstream brief lists, inspected before any code change.

---

## 1. What already exists (do not duplicate)

### Provider execution spine (works, stays)
- **`RenderService` (`app/services/render.py`, ~4,300 lines)** — owns job lifecycle:
  `create_job` (line 1700), `submit_job` (3179), provider registry
  (`_initialize_providers`), default provider (`get_default_provider`, env
  `RENDER_VIDEO_PROVIDER`), idempotency (`_request_idempotency_key` /
  `_find_idempotent_job`), model override validation (`_validate_model_override`,
  line 776), model resolution (`_provider_model_for_job`, line 757).
- **`RunwayAdapter` (`app/adapters/__init__.py`, line 515)** — already the hosted
  Runway boundary: `_runway_request` (auth, version header `2024-11-06`, SSL
  hardening, error classification `_classify_runway_error`), text-to-video and
  image-to-video endpoints, single `promptImage` conditioning, seed injection,
  poll loop with timeout, honest failures (`missing_api_key`, `task_failed`,
  `timeout`, `missing_video_url`), `mock_success` gated to local/test envs only.
  Registered via `ADAPTER_REGISTRY` + `get_adapter()`.
- **`ProviderRequestService` (`app/services/provider_request_service.py`)** —
  read-only translation from canonical `SceneProductionPackage` →
  `ProviderRenderRequest` + execution records. Explicitly non-authoritative.
  Untouched by this workstream.
- **Secondary provider layer (`app/services/providers/*`)** — `RenderProvider`
  ABC, `ProviderRegistry`, execution layer with audit, manual-only selection
  contract. Image path + tests. Left alone.

### Truth / gating systems (protected, reused)
- **Canonical reference validation (fail-closed)** — `reference_validation.py`
  `resolve_scene_reference_requirements` + `validate_generation_payload`:
  blocks unapproved references, wrong character/setting ownership, stale
  reference payloads (>9 refs), missing canonical anchors. Called in
  `submit_job` **before** the provider boundary. This *is* the reference-integrity
  gate the brief asks for — it exists.
- **Character/setting reference locks** — `character_visual_reference_service.py`
  (`build_consistency_payload_for_shot`, `lock_first_references_for_completed_job`,
  look-scoped locks), `reference_selection_service.py` (deterministic identity-
  first selection: canonical → face → profile → full-body → context), Reference
  Library (`reference_asset_service.py`).
- **Capability contract** — `provider_capability_contract.py`: evidence-leveled
  (VERIFIED_LIVE / VERIFIED_CODE / UNVERIFIED / UNKNOWN) capability declarations
  per provider + `project_references_for_provider` (fail-closed single-anchor
  projection when capacity is unknown) + audit traces. This is the existing
  capability machinery the model registry must extend, not replace.
- **Storyboard integrity** — `storyboard_blueprint_service.py` versioned
  blueprints (DRAFT/APPROVED/SUPERSEDED), `_validate_shot_renderable` refuses
  rendering from a non-approved or stale version; `scene_render_inputs` requires
  approved == current. This is the storyboard staleness gate — it exists.
- **Camera plan provenance** — `camera_presets.py` (`StoryboardCameraPlan`),
  advisory `CameraShotRecommendation` ("never auto-applied"), creator plans
  stored as `[CREATOR CAMERA PLAN]` in the shot contract. AI camera suggestions
  exist via `scene_direction` / camera recommendation routes and are explicitly
  advisory-only already.
- **Visual Training** — `visual_training_service.py` with fail-closed
  `resolve_render_reference` and `_apply_visual_model_reference` in render.py.
- **Co Director** — proposal/critique/session/collaboration services, advisory
  only, no-score rules in AGENTS.md.
- **Prompt budget** — `prompt_budget_service.py` (512-char Runway policy,
  allocation before paid call).
- **Fresh-ish state** — idempotency keys, `pipeline_reliability` metadata,
  retry limits, poll reconciliation, previs duplicate/active-job detection.

## 2. Where stale state actually enters (verified gaps)

1. **No generation-context versioning.** Jobs carry `shot_id` + prompt but no
   scene/shot/storyboard/reference/camera version fingerprints, so nothing can
   prove a job was built from *current* state, and nothing invalidates old jobs
   when state changes. `project_store` exposes only project-level `updated_at`.
2. **Idempotency can return an old job for identical-looking input.**
   `_find_idempotent_job` reuses a pending/rendering job matching a
   content-hash key; if the scene/board changed upstream while the *sent*
   prompt stayed equal, the old job is silently reused.
3. **Previs stale-copy handoff (mitigated but structurally fragile).**
   `previs_service.generate_scene` explicitly re-attaches locked looks because
   "the frontend sends a stale editable copy" — a documented stale-input path.
   It also raises/uses prompts from the *approved board version* — correct —
   but nothing records which storyboard version a non-board render used.
4. **Prompt override path** (`promptDirtyRef` in PrevisRoom) correctly refuses
   to send stale synced text, but nothing server-side stamps the prompt with
   its source (user-edited vs board-derived) or version.
5. **Camera instructions**: creator camera/shot planning is merged into
   prompts and `structured_parameters` with no `instruction_source` /
   approval-state stamp, so a previously AI-suggested value that a user once
   sent cannot be distinguished from an approved one on the next render.
6. **Model allowlist rot.** `ALLOWED_RUNWAY_MODELS = {gen4.5, gemini_omni_flash,
   gen6, gen3}` — verified against https://docs.dev.runwayml.com (models +
   changelog + pricing, Sept 2026): `gen6` and `gen3` do not exist; Gen-3 Alpha
   Turbo and Gen-4 Aleph are *retired* identifiers that now fail. `gen4.5` and
   `gemini_omni_flash` are real. Several genuinely available models
   (`gen4_turbo`, `veo3.1`, `veo3.1_fast`, `wan3`, `seedance2_5`, `h3_max`,
   `hailuo3`, `aleph2`, `grok_imagine_1_5`, `seedance2*`, `happyhorse_1_0`,
   `act_two`) are absent. Model truth lives in a hardcoded frozenset + env
   default, duplicated in render.py's `_provider_model_for_job` /
   `_validate_model_override` — exactly the hard-coding the brief prohibits.
7. **No cost estimation / budget limits** anywhere (`grep estimated_cost` → 0).
8. **No selection metadata**: nothing persists *why* a model/provider was
   chosen or whether it was user- vs auto-selected (provider override exists;
   model "Auto" does not).

## 3. Architectural conflicts found

- **Two provider layers** exist by history (adapters registry for video +
  `app/services/providers` for images/audit). The brief's
  "ProviderRequestService → adapter" flow maps onto the *adapters* registry
  (`get_adapter`), which is what `RenderService.submit_job` actually calls.
  Workstream additions go there; no third layer is created.
- **`PrevisService.duration_options`** hardcodes per-provider duration tables —
  a second place where model capability data would leak; registry-driven
  durations must feed it, not parallel it.
- **Co Director hard rule**: "NO scores, ratings, or percentages" (AGENTS.md).
  Any router "quality score" output is forbidden; recommendations must be
  capability-based sentences. This aligns with the brief.

## 4. Decisions (what is created vs modified)

| Concern | Decision |
|---|---|
| Model registry | **Create** `app/services/model_registry.py` — single source of truth for Runway video models with verified capability metadata + relative cost; feeds `ALLOWED_RUNWAY_MODELS` via re-export so adapter/render validation stop hardcoding. |
| Model router | **Create** `app/services/model_router.py` — bounded, capability-match router (AUTO vs USER), human-readable reasons, cost estimate, no mutation of canonical data, no invented scores. |
| Fresh render / readiness | **Create** `app/services/generation_context_service.py` — version fingerprinting (scene/shot/board/references/camera), readiness gate blocking stale AI-suggested camera values and version mismatch, fresh-render context creation. |
| Adapter changes | **Modify** `RunwayAdapter` to consult the registry (allowed models, duration/ratio support) and persist selection metadata; keep all transport/honest-failure code. |
| Render service | **Modify** `create_job`/`submit_job` minimally: accept/record `model_selection`, generation context, enforce budget gate. |
| Previs route/service | **Modify** to thread `model` / `fresh_render` / camera source stamps through existing `render_settings` DTO. |
| UI | **Modify** PrevisRoom advanced settings: Model select (Auto + registry models), estimated cost line, selection reason display, Fresh Render toggle. |
| Tests | **Add** `test_model_registry.py`, `test_model_router.py`, `test_generation_context_service.py` + fix stale `gen6`/`gen3` tests. |

## 5. Explicitly NOT created (per brief)

- No duplicate reference selection (reuses Reference Library + selection service).
- No duplicate readiness/staleness gates (extends `validate_generation_payload`
  and `_validate_shot_renderable` usage rather than re-implementing).
- No second intelligence layer; Co Director stays advisory.
- No new provider abstraction (adapters registry remains THE boundary).
- No simulated success in production paths (mock path stays env-gated).
- No broad refactor of `render.py` / `provider_request_service.py`.
