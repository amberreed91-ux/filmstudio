# Runway Model Router — Final Integration Report (2026-09-28)

Task: make Studio's execution layer route through the Runway Model Router
(configId `studio-production-router`) instead of naming concrete models — as an
additive provider, with zero billable calls, zero canonical mutation, and a
full fail-closed contract.

---

## Final report (requested fields)

> **Follow-up verification (2026-09-28):** Narrow changes in this pass strengthen the provider/model-independent manifest fingerprint and make video reference projection/order fail closed with structured incompatibility metadata. Mocked tests only; no live Runway calls were made in this pass. Meta Muse remains unchanged. See `ARCHITECTURE_MAP_20260928.md` for the boundary map.

| Requested item | Final result |
|---|---|
| **A. What changed** | Router references are validated before credentials/network use, preserved in input order, never filtered or weight-sorted, and incompatible/malformed/over-limit sets become failed jobs with `router_execution.reference_incompatibility` (`code` + details). Manifest projection now recursively excludes execution-only values, including nested Router resolution metadata. Regression tests cover fingerprints, structured failures/no POST, exact reference order, no direct-Runway fallback, and Muse isolation. |
| **B. Deliberately not changed** | No Scene 002 state, approvals, canonical references, or `script_text`; no Muse code; no generation or credit spend; no Router config/API write; no object-level Python immutability claim. Existing unrelated working-tree changes were left alone. |
| **C. Creative manifest boundary** | Canonical creative inputs and creator-approved generation decisions only. Provider/model/router selection, pipeline, execution cost, `resolved_model`, and estimates are excluded, including when nested in parameters. Same direct-vs-Router creative state produces the same fingerprint; post-resolution metadata stays adjacent and cannot be written into this returned manifest. |
| **D. Router execution boundary** | Studio freezes the creative generation contract before Router submission; Router then resolves model/settings/cost. These results are recorded under render-job execution/result metadata only. A Runway `no_eligible_model` or missing-config failure stops; no provider fallback. |
| **E. Reference behavior** | Explicit assets and consistency references preserve their order and are represented as Router `reference` roles; only an explicitly designated storyboard frame is role `first`. Blank, malformed, unsupported-scheme, too-long, invalid-payload, and over-limit image/video reference sets fail before HTTP with structured incompatibility. If Runway returns no eligible model for a request containing required refs, the job fails and the error is surfaced; no retry on another Studio provider. Studio does not independently infer model-specific inability omitted by Router. |
| **F. Meta Muse boundary** | Existing NVIDIA Muse Co-Director remains upstream advisory intelligence. It is not recreated, moved, called by Router, or used as a generation selector. Existing boundary and model-registry tests pass. |
| **G. Management API** | **Supported:** official configuration docs say create/update/delete are available through Model Router API and SDK as well as Portal. The API reference includes management operations; generation uses the immutable slug, while management uses the generated Router resource ID. No management write was invoked. |
| **H. Tests/results** | **232 passed** across focused Router, preflight, multi-shot, direct-Runway hardening/model-default, Runway image, and prompt-budget suites, with `IMAGE_PROVIDER_ENABLED=false LOCAL_LTX_ENABLED=false`. All provider HTTP in tests is mocked. No live provider/account calls or billable-generation endpoint calls in this pass. |
| **I. Account status** | Historical read-only account verification: organization auth succeeded; router list was empty; target UUID and `studio-production-router` dry runs returned 404 `router_config_not_found`. This turn made no live account calls. Config remains uncreated/unavailable on the last verified account state. No task/generation/credits were created in this pass. |
| **J. Exact next action** | In the same Runway Developer Portal organization as the Studio API key, open **Model Routers → New config**, create a saved Router whose immutable Config ID is exactly `studio-production-router`, and set its required name plus creator-approved eligibility/optimization/credit preferences. Save and report the Portal-generated Router UUID (it cannot be chosen at creation). Then allow only read-only GET/list verification and image/video `dryRun:true` with the intended payload; stop before live generation. |

**STOP:** no live generation, credits, account writes, or canonical creative mutation were performed in this pass.

> Historical integration and account-probe details follow; test counts below in the historical section describe the earlier integration run, not this follow-up run.

<!-- HISTORICAL-INTEGRATION-DETAILS -->

## Historical integration report

**Follow-up note:**
<!-- old overview retained below for implementation provenance -->

> Existing NVIDIA Meta Muse remains the Studio Co-Director; no Muse code was changed. Runway Router remains a separate downstream execution layer. The generation-preflight creative manifest no longer includes provider/model/cost/readiness fields: execution routing and cost live in job metadata. The Runway adapter now fails closed rather than clipping excess canonical references. See `ARCHITECTURE_MAP_20260928.md` for the verified Studio map and exact boundaries.


| Item | Result |
|---|---|
| Router integration status | **IMPLEMENTED & TESTED (non-billable).** New provider `runway_router` wired into the adapter registry, render service, image seam, prompt policy, and persistence. Blocked from live generation solely by account configuration (see below). |
| configId used | `studio-production-router` (the slug, sent as `configId` in every request body; default constant + `RUNWAY_ROUTER_CONFIG_ID` env override). The Router ID `138f4c50-3411-4aee-88a9-91dd56b90987` is treated as the account/resource identity and is **never** sent — asserted by test. |
| Router dry run succeeded | **No — blocked upstream, fail-closed as designed.** `POST /v1/generate/image` and `POST /v1/generate/video` with `dryRun: true` returned HTTP 404 `router_config_not_found`: *"Router config 'studio-production-router' was not found or is not accessible."* Same result for video and image, and for `GET /v1/routers/138f4c50-3411-4aee-88a9-91dd56b90987` ("Router not found"). |
| Model dry run selected | None returned (dry run never reached routing — 404 before eligibility). **Not fabricated.** |
| Estimated cost | None returned. **Not fabricated.** |
| Resolved settings | None returned. **Not fabricated.** |
| Prompt compatibility | **COMPATIBLE (verified from official OpenAPI):** router input caps are 32,000 chars (image) / 20,000 chars (video); Studio's Scene 002 prompts are 3,084–3,290 chars — comfortably inside. Router-mode prompt policy set to 20,000 (fail-closed), replacing the old 512-char direct-model ceiling for this provider only. Prompts pass byte-identical (hash-proven test); the router's own `prompt_length` filter decides per-model eligibility. If all models are excluded → `no_eligible_model` with `pipeline` + `emptiedBy`, surfaced verbatim. |
| Reference compatibility | **Fail-closed:** router accepts ≤16 image refs / ≤4 role-tagged video image refs. Required references preserve order; only an explicit storyboard frame has role `first`, the rest role `reference`. Invalid or excess refs fail with structured incompatibility metadata before HTTP. Model-specific eligibility is determined by Runway. |
| Image readiness | **READY (code-complete).** Image seam dispatch branch, schema-shaped builder, dry-run passthrough. Live path awaits a valid config in the account. |
| Video readiness | **READY (code-complete).** `RunwayRouterAdapter` (submit→poll→parse, bounded, metadata recording) registered in `ADAPTER_REGISTRY` + `RenderService`. Same caveat. |
| Audio readiness | **NOT IMPLEMENTED (by design, minimal scope).** Endpoint constants documented (`/v1/generate/audio`); no builder/submit yet. No Studio audio pipeline change. |
| Multi-shot readiness | **READY.** Per-shot contracts preserved (test: two shots → two model-agnostic payloads, per-shot prompt/duration intact). No Scene-002 special case (source-scanned test). Works for arbitrary scenes/storyboard versions. |
| Meta Muse separation | **INTACT.** Existing NVIDIA Meta Muse / Co-Director remains a chat advisory subsystem (`proactive` → `co_director_chat` → `co_director_chat_service` → `muse_chat_provider.call_muse`). Muse has chat modality + `advisory_intelligence`, no render role, and returns advisory text only; the creator/Studio workflow remains responsible for accepting advice. The Router provider does not import/call Muse, and Muse does not call generation endpoints. |
| Creative manifest/provider agnosticism | **ENFORCED.** The preflight manifest carries creative shot inputs and context fingerprints only; model, provider, cost, readiness are outside its fingerprint/manifest. Router resolved information remains execution metadata. The Router path does not consult Studio's model scoring/eligibility; direct `runway` retains its separate existing selector. |
| Frozen-contract scope | The existing RenderJobInput is not an immutable type. The integration guarantees that Muse and Router do not write canonical Studio state, and Router resolution does not rewrite the manifest/contract; do not claim object-level immutability. Studio constructs the validated render-job payload before provider submission. |
| Reference overflow | **FAIL CLOSED.** Explicit and consistency references are combined; the adapter rejects video requests beyond Runway's documented four-image limit rather than slicing off remaining references. URI representation and eligibility failures still stop without fallback. |
| Tests passed | **731/731** across the full affected-suite combination (50 new router tests + 681 existing regression tests), with developer-`.env` leakage neutralized (`IMAGE_PROVIDER_ENABLED=false LOCAL_LTX_ENABLED=false`). New suite alone: 50 passed. Direct-Runway suites: 200 passed unchanged. |
| Tests failed | 0 real failures. 5 spurious failures in one specific test **combination order** were root-caused to a **pre-existing, unrelated** environment leak (see "Pre-existing issues" below); they pass in isolation and with `.env`-derived flags neutralized. |
| Files changed | **New:** `app/services/providers/runway_router_provider.py` (933 lines), `tests/test_runway_model_router.py` (50 tests), `docs/runway_model_router/ARCHITECTURE_MAP_20260928.md` (A–J pre-implementation map). **Modified:** `app/adapters/__init__.py` (+`RunwayRouterAdapter`, registry entry), `app/services/render.py` (+provider config, fail-closed model-override rejection, routing-mode metadata), `app/services/prompt_budget_service.py` (+router prompt policy), `app/services/providers/__init__.py` (+exports), `app/services/providers/image_provider.py` (+`runway_router` dispatch, `dry_run` status), `.env.example` (+router vars), `tests/test_local_ltx_provider.py` & `tests/test_minimax_h3_local_provider.py` (registry-count guard 12→14 with comment). |
| Database changes | **NONE.** No schema/migration changes; routing metadata persists in existing `render_jobs.metadata` JSON (`router_execution`, `provider_payload_metadata`, `provider_response_normalized`, `model_selection.routing_mode`/`router_config_id`). No project/scene/storyboard/reference/camera rows touched. |
| Runway API calls made | 8 total, **all non-billable**: 1× `GET /v1/organization` (auth probe → OK; tier/creditBalance/usage visible), 1× `GET /v1/routers` (list → `{"data": []}` — zero router configs in this account), 1× `GET /v1/routers/138f4c50-…` (→404), 4× `POST /v1/generate/{image,video}` with `dryRun:true` (→404 router_config_not_found), 1× `GET /v1/tasks` attempt (none — no task ever created). |
| Billable generations | **0** |
| Runway credits spent | **0** (confirmed: dry-run 404s create no task; account creditBalance unchanged; no task-id ever returned) |

---

## Verified architecture and boundary (addendum)

Meta Muse is already built. Its current Studio placement and runtime seam are documented in `ARCHITECTURE_MAP_20260928.md`: read-only context assembly, existing Co-Director chat service/route, NVIDIA Muse chat provider, advisory reply to the creator. Muse is not canonical truth, a model selector, an approval mechanism, or a generation trigger. The Co-Director persona named `provider_router` is just an existing chat persona; no generation routing logic is there.

The generation manifest is provider agnostic: scene/storyboard/shot/reference/camera facts and their versioned context only. The old manifest also carried model/cost/readiness fields; those were moved out of the manifest because those are execution/preflight observations, not creative truth. Router result values are recorded in `router_execution`; absent values stay absent/null and are never inferred. Runway decides eligibility and selected model per its saved config plus request. Studio does not score candidate models in Router mode.

The prepared `RenderJobInput` data class is not immutable in Python. This pass verifies separation by no mutation at the provider boundary and a distinct canonical creative manifest rather than misrepresenting the object itself as frozen. A separate explicit freeze/hash enforcement would be new behavior and was not added.

## What was built (target architecture, as specified)

```
Studio canonical creative state (no state mutation)
        ↓
Creator-approved decisions + generation preflight
        ↓
Frozen creative generation contract / fingerprint (creative inputs only)
        ↓
Runway Model Router (model-agnostic execution request)
        ↓
Resolved model, settings and cost
        ↓
Execution metadata → generation result (separate from the manifest)

Runway mode/config identifiers belong to dispatch/execution metadata, not
creative truth or the manifest.
```

```
RunwayRouterAdapter  (ADAPTER_REGISTRY["runway_router"])
        ↓
Runway Model Router   POST /v1/generate/video | /image   (X-Runway-Version 2024-11-06)
    body: { configId: "studio-production-router", dryRun?: true,
            input: { promptText, aspectRatio "16:9"-form, duration, referenceImages[{uri,role}] } }
    (NO "model" key — enforced: builder raises; render service raises; adapter raises)
        ↓
Runway selects eligible model
        ↓
task id → bounded poll GET /v1/tasks/{id} → provider response
        ↓
Studio records (execution metadata ONLY, in render_jobs.metadata):
    router_execution = { routing_mode, router_config_id, resolved_model,
                         routing_provider, resolved_settings, resolved_input,
                         estimated_cost_credits, realized_cost_credits,
                         runway_task_id, references_forwarded,
                         references_unrepresentable, capacity_fallback,
                         no_eligible_model {pipeline, emptied_by} }
        ↓
asset validation → canonical/derived persistence (existing Studio rules unchanged)
```

Resolved model / cost / settings are recorded **only** as execution metadata;
they never overwrite the canonical model-agnostic contract and never flow back
into scene/storyboard/reference/camera state.

## Fail-closed guarantees implemented (each test-proven)

- Concrete model on routed path → rejected at three layers (builder,
  `_validate_model_override`, adapter) — never stripped silently.
- Unknown aspect ratio → raise (pixel-ratio forms translated at adapter only).
- Blank/malformed/unusable / over-limit references → structured
  `required_reference_incompatible` job failure before HTTP; never dropped.
- Prompt > router input cap → raise; never truncated anywhere.
- `no_eligible_model` → HTTP 400 parsed; `pipeline` + `emptiedBy` surfaced
  verbatim in job metadata; single call, no retry storm, no fallback provider.
- `router_config_not_found` → fail closed with code surfaced.
- Dry run → `dry_run` status; no task id accepted on a dry-run response;
  nothing billable, no output asset, no false-completed render job.
- Cost fields only ever populated from Runway responses; absent → `None`.
- Credentials env-first (`RUNWAY_API_KEY`/`RUNWAYML_API_SECRET`), adapter
  config-key fallback; never logged (redaction helper + test).

## Runway account verification findings (blocker)

- The account credential **is valid** (`GET /v1/organization` → 200 with tier,
  creditBalance, usage).
- The account's last verified read-only probe showed **zero saved router configs**: `GET /v1/routers` → `{"data": []}`.
- Official docs/OpenAPI verification (2026-09-28) confirms Router creation/modification/deletion are supported programmatically (configuration docs explicitly say API and SDK; the Model Router API reference lists the management group). No create/update/delete endpoint was called. Config slug is immutable on creation; management uses the Router UUID, generation uses the slug. For the requested creator action, use the Portal checklist below.
- Neither the slug `studio-production-router` nor the Router ID
  `138f4c50-3411-4aee-88a9-91dd56b90987` resolves on this account (404).
- **Conclusion:** the router config was never created in THIS Runway account
  (or was created under a different account/key than `RUNWAYML_API_SECRET` in
  `studio-backend/.env`, or was deleted — deletion is permanent per docs).
- **Action required (creator):** create the config with slug exactly `studio-production-router`, configure the supported routing preferences in the Developer Portal checklist below, then re-run the dry-run probe to read `resolvedSettings`, `resolvedInput`, and `estimatedCost` before any live decision. I did not touch the account.

### Exact Developer Portal configuration checklist (do not guess capability)

1. In the same Runway Developer Portal organization/account used by `RUNWAYML_API_SECRET`, create a saved Model Router config with immutable slug **`studio-production-router`**. The UUID `138f4c50-3411-4aee-88a9-91dd56b90987` is the previously observed target, but the official API states that UUID is the management ID and it cannot be chosen in creation input. If the created config has another UUID, report it; do not change the config slug or code target without confirmation.
2. Set required human-readable name (e.g. `Studio Production Router`) and an optional description identifying Studio shot image/video routing.
3. Choose **eligible models** with either supported mode: allowlist-only or denylist/exclude-list with new models included. Ensure the chosen pool contains models Runway considers eligible for the request's actual capability inputs. Do not add a Studio-side hidden ranking list.
4. Choose one supported `optimizeFor`: `quality`, `cost`, or `latency`; this preference only ranks after Runway filters to eligible models.
5. Optionally set separate hard `maxCreditsPerGeneration` caps for video and image (and audio only if needed); unset means no configured price cap. Choose the creator-approved credit ceilings. They are per generated output, not Studio's estimated batch cost.
6. Leave `fallback.onCapacity` **off** unless the creator explicitly wants Runway's documented capacity-only next-eligible-model fallback. This is a Runway-internal capacity preference, not Studio provider fallback. Eligibility failures must still fail closed.
7. Save. Do not request audio for this Studio integration; Studio image/video routing is what is implemented. Do not assume Router configuration supports “long prompt” as a config switch: request prompt-length hard filter is Runway's eligibility behavior and is evaluated on the input.
8. Ensure the config admits models with the specific needed reference/capability shapes; never loosen Studio canonical reference requirements to make a model eligible. A dryRun with canonical reference URIs is the only validation of the actual request shape.

**Officially supported Router inputs/capabilities** (from Runway's current OpenAPI and model-router docs): video, image, audio endpoints; model allow/deny eligibility; capability/request-input filtering; optimize-for cost/latency/quality; separate modality credit ceilings; opt-in capacity fallback; `dryRun`; selected model/config/resolved settings/resolved input/estimated cost in routing results; explicit `no_eligible_model` with filter pipeline/emptiedBy. Image prompt up to 32,000 chars, up to 16 image refs; video prompt up to 20,000 chars, negative prompt up to 1,000, up to four role-tagged image refs plus up to two video refs, one audio ref, up to five keyframes, duration 2–30, model-agnostic aspect ratio/resolution/seed/audio fields. Model-level eligibility decides exact support for prompt length/capabilities. There is no special multi-shot/batch API: Studio submits independently model-agnostic per-shot calls. Studio relies on Router's eligibility response for model-specific compatibility; it does not weaken required references if the request returns `no_eligible_model`.

## Pre-existing issues discovered (not introduced, not modified)

1. **Test-order `.env` leak (explains all spurious failures):**
   `tests/test_scene002_creator_workflow.py:291` does `from main import app`,
   and `main.py:13` calls `load_dotenv(".env")`, importing the developer's
   real environment flags (`LOCAL_LTX_ENABLED=true`, `IMAGE_PROVIDER_ENABLED`,
   etc.) into `os.environ` for the remainder of the pytest process. Any suite
   asserting "disabled by default" then fails depending on suite order.
   Proven: probe test shows the values appear only after that suite runs; the
   5 spurious failures vanish with `IMAGE_PROVIDER_ENABLED=false
   LOCAL_LTX_ENABLED=false` or in isolation. Fix (suggested, not applied —
   out of scope): load dotenv once in `conftest.py` with explicit
   test-safe overrides, or delenv the provider flags in the autouse fixture.
2. **Uncommitted preflight gate in `render.py` (working tree, pre-dates this
   session):** `validate_generation_payload(..., require_setting_reference=True)`
   now fails closed on every submission whose project isn't resolvable in the
   store, breaking `tests/test_render_submit_completion_hooks.py::
   test_submit_job_runs_quality_hooks_when_provider_returns_complete` (passes
   at HEAD; the gate exists in no commit). Deliberately **left intact** per
   the reference-integrity rule.
3. Scene 002's 3,000+ character prompts remain **intact and untruncated**
   (canonical prompts untouched; only the policy ceiling changed for the
   routed provider).

## How to validate once the router config exists (non-billable)

```bash
cd studio-backend
.venv/bin/python - <<'PY'
from dotenv import load_dotenv; load_dotenv('.env')
from app.services.providers.runway_router_provider import (
    submit_runway_router_image_render, submit_runway_router_video_render)
print(submit_runway_router_image_render("probe frame", aspect_ratio="16:9", dry_run=True))
print(submit_runway_router_video_render("probe motion", duration=5, aspect_ratio="16:9", dry_run=True))
PY
```

Expected on success: `status == "dry_run"`, `meta.resolved_model`,
`meta.resolved_settings`, `meta.estimated_cost_credits` populated from Runway.
Stop condition unchanged: no live generation without explicit creator
authorization.

## Architectural invariants — final status

Verified: canonical state remains Studio-owned and the Router adapter does not mutate it; provider/model choice and resolved cost are execution metadata; Runway selects eligible models; no silent fallback, prompt truncation, or reference removal; no autonomous creative mutation; no provider call before preflight; zero billable generations and zero credits spent; Scene 002 state and approvals untouched. Preflight's creative manifest is provider agnostic. RenderJobInput is mutable by type, so no object-level immutability guarantee is claimed.

## Official references checked for Router API capabilities

- [Model Routers overview](https://docs.dev.runwayml.com/model-routers/)
- [Router configuration](https://docs.dev.runwayml.com/model-routers/configuration/)
- [Generate through a Router](https://docs.dev.runwayml.com/model-routers/generating/)
- [Current Runway OpenAPI API reference](https://docs.dev.runwayml.com/api/) — the Model Router group is documented; official configuration docs explicitly confirm create/update/delete via the API and SDK. Config slugs are immutable after creation; selected model eligibility is resolved by Runway.

## Tests changed in this verification pass

- `studio-backend/app/adapters/__init__.py`: ordered reference projection, strict reference validation, structured pre-submit incompatibility output.
- `studio-backend/app/services/providers/runway_router_provider.py`: typed structured reference incompatibility for unusable or over-limit image/video references; no request is made.
- `studio-backend/app/services/shot_manifest.py`: nested execution-only metadata filtering so resolution cannot enter the creative manifest fingerprint.
- `studio-backend/tests/test_runway_model_router.py` and `studio-backend/tests/test_multishot_integrity_remediation.py`: provider/resolution fingerprint regression; required refs ordered/forwarded or failed before HTTP; no direct provider fallback.
- `studio-backend/tests/test_runway_router_image_script_parser.py`: preserves the original Router failure code through the image seam.
- No Muse, creative-state, approval, reference-record, or script files were modified.

**Exact next action from creator:** In the Runway Developer Portal open **Model Routers → New config**, create a saved config with immutable Config ID `studio-production-router`, set its required name and creator-approved eligible-model/optimization/credit-cap preferences, and save. Report the UUID the Portal generates (it cannot be chosen at creation). The following pass may perform only read-only list/GET and image/video `dryRun:true` checks with the intended request shape; stop before any live generation.
