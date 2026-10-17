# Runway Router + Meta Muse — Final Architecture Gate

**Audit date:** 2026-09-28  
**Verdict:** **FAIL — NOT READY for Portal configuration or production routing**  
**Scope:** Read-only source/docs audit plus mocked/offline tests. No source implementation, account configuration, creative data, approvals, references, scripts, or media were changed by this audit. No live generation or provider/account request was made; no credits were spent.

> **Meta Muse is the existing creative intelligence layer. Runway Model Router is the execution routing layer. The two are complementary and must not be merged.**

This gate distinguishes **code-path separation that is enforced** from **the complete generation contract and runtime wiring that are not yet proven/enforced**. Passing unit tests for the adapter does not prove the deployed generation path uses the Router or that every approved field reaches it unchanged.

## A. Meta Muse architecture

### Evidence and call path

The existing Co-Director call path is:

```text
app/routes/proactive.py:co_director_chat
  → app/routes/proactive.py:_get_llm_callable
  → app/routes/co_director_chat.py:_get_co_director_llm_callable
  → app/routes/co_director_chat.py:call_co_director_llm
  → app/services/providers/muse_chat_provider.py:call_muse
  → app/services/providers/muse_chat_provider.py:_post_chat_json
```

`CoDirectorChatService.chat` builds a read/context-grounded prompt, calls the injected `LLMCallable`, checks reply quality, and returns reply text plus prompt metadata. It has no approval, render-job, Router, or canonical-state write call. The route returns a chat response to the caller; there is no code path here that converts the reply into approval. `tests/test_muse_provider.py::test_muse_reply_never_mutates_canonical_truth` instruments the store and verifies no write calls.

The model registry identifies `meta/muse-glimmer-30b` as provider `muse`, modality `chat`, role `advisory_intelligence`, with empty generation modes and zero render credits (`app/services/model_registry.py:_MUSE_MODEL`). The provider asserts this registry shape (`muse_chat_provider.get_muse_model`) and declares `supports_render=False` and `supports_canonical_mutation=False` (`build_provider_registry_entries`). Tests verify Muse is excluded from Runway generation model allowlists and Muse’s registry shape.

`runway_router_provider.py` does not import/call Muse or read its credential; it constructs and submits Runway execution requests. Conversely, `muse_chat_provider.py` only sends chat-completions requests and has no generation submission call. `tests/test_runway_model_router.py::test_router_module_never_imports_or_invokes_muse` checks this separation. The existing `provider_router` Co-Director persona text is a chat persona, not execution-router code.

### Boundary result

**PASS, with one runtime identity caveat.** The implementation separates advisory chat from rendering, model selection, approvals, and canonical state. No Router integration introduced a second creative-intelligence provider or changed Meta Muse source. Other existing Studio intelligence services are outside this Router integration and are not a second Meta Muse.

The code labels the served model with NVIDIA’s namespaced model ID and comments that it is NVIDIA’s Muse model, but the default base URL in `muse_chat_provider.py` and `app/config.py` is `https://api.muse.example.com/v1`. Runtime may override it with `MUSE_API_BASE_URL`, but the source does not prove that deployed configuration points to NVIDIA. Thus **the advisory boundary and intended NVIDIA model identity are proven; the actual NVIDIA endpoint used in deployment is not proven by this checkout**. No environment secrets/config values were inspected and no connectivity probe was made.

## B. Creative contract boundary

`SceneProductionPipelineService.prepare_scene_batch` derives a per-shot preflight entry from ordered current shots, prompt, references, shot/storyboard versions, camera instructions/plan, duration, parameters, and generation-context IDs. It runs readiness/reference/cost checks before creating jobs. It then calls `build_shot_manifest` (`app/services/shot_manifest.py`), which records shot prompt, duration, references in list order, reference version, camera plan/instructions, and filtered parameters, and calculates a deterministic fingerprint.

`shot_manifest.py` excludes many known execution keys recursively (provider/model, routing mode/config, resolved model/settings/input, pipeline, costs, capacity fallback, task-related provider response metadata, etc.). Tests compare routed and direct manifests and check selected nested Router values do not change the fingerprint (`test_runway_model_router.py::test_router_manifest_stays_provider_agnostic_without_studio_model_or_cost`, `::test_manifest_strips_nested_router_resolution_and_fingerprint_is_provider_agnostic`; also `test_multishot_integrity_remediation.py::test_d7_manifest_fingerprint_ignores_execution_provider_and_model`).

### Boundary result

**PARTIAL / FAIL as a frozen-contract gate.** The manifest is a mutable dictionary plus fingerprint, not an immutable contract enforced at the provider boundary. `RenderService.create_job` subsequently performs prompt/context enrichment, persists a mutable `RenderJobInput`, and `RenderService.submit_job` can add a seed before adapter submission. The Router adapter receives that job input, not a manifest or a verified manifest hash. There is no final assertion that the exact frozen prompt/references/settings equal the payload that crosses the wire. The code’s own architecture map correctly disclaims object-level immutability.

The manifest retains some approved settings through `parameters`, but does not define a complete normalized contract for reference roles and all requested fields. In particular, the manifest builder has no explicit reference-role projection. Its recursive execution-field filter is a finite denylist and omits names such as `task_id`, `execution_task_id`, `runway_task_id`, `router_uuid`, and `realized_provider_cost`; if such execution fields appear nested in parameters, the code does not guarantee their exclusion. The exact excluded-field inventory in the request is therefore **not proven complete**. Provider/config/model/cost separation is demonstrated for the covered keys, not for all listed execution metadata.

## C. Router execution boundary

The Router implementation is an **additive explicit provider**, not a replacement for direct Runway:

```text
RenderService.submit_job(job.provider)
  → get_adapter(job.provider)
  → ADAPTER_REGISTRY["runway_router"] = RunwayRouterAdapter
  → submit_runway_router_video_render
  → POST /v1/generate/video
```

The image seam separately dispatches the explicit `runway_router` selection to `submit_runway_router_image_render` (`image_provider.submit_image_render`). Studio’s direct `runway` adapter remains distinct and continues to call direct-model endpoints. The Router builder creates `{configId, input, dryRun?}`, never sends a concrete `model`, and rejects model overrides in both `render._validate_model_override` and `RunwayRouterAdapter.submit_job`. Studio does not run its legacy `model_router` selection for the `runway_router` provider; that selector applies to direct `runway`.

Post-resolution values (resolved model, settings/input, estimated/realized credits, capacity fallback, task ID) are put in `job.metadata["router_execution"]` and/or normalized provider result metadata by `RunwayRouterAdapter.submit_job`. Tests assert model/cost do not enter the input payload and validate response metadata persistence.

### Boundary result

**PASS for the explicit Router adapter contract; FAIL for deployment-wide routing readiness.** The default config slug is `studio-production-router`, but `RUNWAY_ROUTER_CONFIG_ID` is an intentional environment override, so code alone does not prove the deployed request value. The explicit Router provider must be selected; the standard direct `runway` provider remains available and is still a separate direct path. No test or source evidence proves all Studio production generation entry points currently choose `runway_router`.

`RenderService._generation_context_metadata` stores routing mode/config in job `model_selection` metadata before execution, not in the shot manifest; resolved model/settings/cost are post-execution metadata. This remains outside the creative manifest, but the metadata naming does not itself prove a fully frozen handoff.

## D. Reference integrity

For video, `RunwayRouterAdapter._router_reference_assets` validates required URLs before HTTP, rejects missing/blank/invalid/unsupported/overlong references and more than four image references, and does not weight-sort consistency references. It collects explicit `referenceAssets` first, appends consistency references in their supplied order, and treats only a non-empty explicit `storyboard_frame_url` as the `first` role. The provider builder forwards valid references in order or raises; it does not slice an over-limit list. `no_eligible_model` returns a failed job and has no direct Runway, NVIDIA, FLUX, or other provider retry/fallback call. The image script-parser Router path skips ComfyUI and does not synthesize a preview after a Router failure.

Tests cover order, unsupported/missing references, over-limit failure before HTTP, explicit storyboard first role, and no direct Runway fallback.

### Boundary result

**PARTIAL / FAIL.** Fail-closed preservation is well-covered for the tested URI lists, but explicit role fidelity is not enforced end-to-end:

- `referenceAssets` is typed/consumed as URL strings; consistency-reference `kind` is not translated into Router roles. All non-storyboard video refs become `role="reference"`.
- There is no `last_frame_reference` path. An explicitly role-tagged reference cannot be proven to retain its role.
- The storyboard frame is projected ahead of all other refs, followed by `referenceAssets`, then consistency refs. That is a defined merge order, not proof it matches the canonical approved reference order across sources.
- `build_image_render_payload` deduplicates identical URIs gathered from the multiple image reference lists. That can remove a repeated canonical entry before the Router fail-closed validator sees it.

Therefore “never silently drop, reorder, substitute, or role-downgrade any canonical reference” is **not proven for all supported canonical inputs**. The existing five-reference test proves overflow fails closed, not all role/order source combinations.

## E. Prompt integrity

The Router request builders pass the prompt string without truncation and enforce the documented request input caps (image 32,000 chars; video 20,000 chars). `prompt_budget_service.budget_job` has a dedicated Router branch that retains the current prompt unchanged and marks it for review above its limit. Tests verify byte-identical prompt forwarding, longer than legacy prompt acceptance, and over-limit rejection without rewriting. `no_eligible_model` is parsed with Runway’s `pipeline` and `emptiedBy`; these are persisted in Router execution metadata.

**PARTIAL / FAIL.** The adapter preserves the prompt it receives, but Studio does not bind that prompt to the preflight manifest fingerprint. `RenderService.create_job` can append/prepend identity, director-intent, continuity, and other prompt context after the scene manifest was made; the generic `retry_with_continuity_context` path can create a changed prompt for a Router job if explicitly invoked. No test proves the precise surfaced UI/error text for a model-level prompt eligibility rejection: structured pipeline/emptiedBy metadata is recorded, while the job error string primarily includes a generic no-eligible message and `emptiedBy`. No automatic Muse rewrite or shortening is called by the Router error path; the broader prompt-mutation/retry path is not Router-excluded.

## F. Multi-shot isolation

`prepare_scene_batch` independently resolves each shot, current storyboard version/shot row, camera provenance, reference set/version, prompt, and generation context; a batch blocker prevents job creation. `generate_scene` maps the validated per-shot prompt by shot ID and submits individual jobs. `GenerationContextService` resolves current shots and rejects stale versions, cross-shot/scene IDs, changed references, and unapproved camera inputs. Each Router call receives the job’s own prompt/reference data; its response metadata is recorded per job.

Tests prove fresh contexts, shot-version isolation, deterministic shot order, per-shot Router prompt/duration in a two-shot adapter test, and provider-independent manifest identity.

**PARTIAL.** Existing safeguards support isolation, but the Router multi-shot test uses manually constructed jobs and does not exercise an end-to-end multi-scene batch with distinct per-shot references, explicit roles, camera plans, approved generation settings, and different Router resolutions. No test specifically proves stale Router execution metadata can never be read as creative truth in a later shot; the manifest filter covers some resolution keys, but is not a closed schema.

## G. Model agnosticism

**PASS for the routed adapter.** `build_runway_router_video_request` / `build_runway_router_image_request` never include a model field; concrete overrides fail closed. `RunwayRouterAdapter` delegates model selection to Runway and stores the returned `routing.model` as resolved execution metadata. The manifest fingerprint tests are independent of provider/model resolution. The direct `runway` provider remains explicitly model-specific and separate; this is not confused with Router mode.

## H. Provider and cost separation

### Provider separation

**PASS for explicit paths.** Meta Muse is chat-only advisory; `runway_router` is an explicit Runway execution provider; direct `runway` remains an explicit direct-model provider; NVIDIA image generation remains an explicit image-provider choice. Router errors do not cause automatic provider substitution. The image Router failure path disables ComfyUI fallback/synthetic preview for that selected routed request.

### Cost separation

Studio’s `GenerationCostGate` retains environment-configured per-generation and daily Studio limits and intentionally returns `estimated=False` for `runway_router` rather than inventing a local model cost. Router-reported estimate/realized credits are recorded separately. There is no Router credit ceiling in Portal code/config from this audit.

**FAIL — Studio budget enforcement is bypassable for routed requests.** `GenerationCostGate.enforce_shot_limit` returns without blocking when a Router estimate is unknown. The Router adapter’s live generation path always uses `dry_run=False`; no pre-generation Router estimate is compared to Studio’s configured limits. Consequently setting Studio’s existing limits does not enforce them for an unpriced Router shot, and a Router estimate cannot be checked against Studio policy before the live task. This is distinct from (and does not justify inventing) a Portal Router credit ceiling.

## I. Router configuration identity

The implementation default is `DEFAULT_ROUTER_CONFIG_ID = "studio-production-router"`; request bodies use this slug as `configId`. Tests assert the default slug and assert that UUID `138f4c50-3411-4aee-88a9-91dd56b90987` is not in the body. The UUID is documented as a resource/management identity, not the generation config ID. The code also supports `RUNWAY_ROUTER_CONFIG_ID` and a per-call `config_id`, so the exact deployed slug is not guaranteed by source constants alone.

No account/configuration API was called in this gate. Prior local integration documentation records an earlier read-only probe that found no accessible config and got `router_config_not_found`; that is historical evidence, not a fresh account-state assertion. The target Portal settings in the request (Quality, allowlist, unset credit ceilings/audio/capacity fallback unless explicitly decided) remain **design intent only**. This audit did not create, inspect, or modify Portal settings.

## J. Official contract and test results

The local integration record says it was checked against Runway’s official Model Router overview/configuration/generation docs and OpenAPI schemas. This audit compared source with that already-reviewed contract and did not infer undocumented Router behavior. Relevant references recorded in `docs/runway_model_router/FINAL_REPORT_20260928.md` and `ARCHITECTURE_MAP_20260928.md` are:

- `https://docs.dev.runwayml.com/model-routers/`
- `https://docs.dev.runwayml.com/model-routers/configuration/`
- `https://docs.dev.runwayml.com/model-routers/generating/`
- `https://docs.dev.runwayml.com/api/` and the OpenAPI `RoutedImageRequest`, `RoutedVideoRequest`, and response/error schemas

The code/tests cover image/video request builders, model-agnostic bodies, the config slug, reference limits and roles, prompt limits, `dryRun` response parsing, resolved settings/model and estimated/realized cost metadata, and `no_eligible_model` details. The video adapter’s normal submit is live (`dry_run=False`); dry-run coverage is at the provider-function/seam level. Audio routing is not implemented by the Studio adapter and is not treated as supported.

**Focused offline test run:**

```text
IMAGE_PROVIDER_ENABLED=false LOCAL_LTX_ENABLED=false .venv/bin/python -m pytest -q --no-header -p no:cacheprovider \
  tests/test_runway_model_router.py \
  tests/test_muse_provider.py \
  tests/test_runway_router_image_script_parser.py \
  tests/test_multishot_integrity_remediation.py \
  tests/test_storyboard_provider_conditioning.py \
  tests/test_storyboard_prompt_no_truncation.py \
  tests/test_prompt_budget_adversarial.py \
  app/services/test_runway_provider_hardening.py \
  app/services/test_render_runway_registry.py \
  app/services/test_render_pipeline_hardening.py \
  app/services/test_render_scene_reference_transition.py \
  app/services/test_generation_context_service.py \
  app/services/test_model_registry_and_router.py

304 passed in 14.24s
```

A narrower subset also passed (178 passed in 11.01s). The 304-test run used mocked provider HTTP; no tests made live generation/account calls. Two exploratory test invocations initially used incorrect file paths and stopped at collection with “file or directory not found”; the corrected combined run above collected and passed. No test was weakened or edited. No build/typecheck was applicable to this Python-focused audit.

## K. Remaining implementation/readiness gaps

1. **No enforced immutable/handoff contract:** manifest is a mutable preflight projection, not the exact immutable payload verified at Router submission; later prompt/context and seed preparation can diverge from it.
2. **Manifest exclusion is not a closed contract:** the recursive denylist misses possible task IDs, UUIDs, and provider cost/routing aliases. Roles and all approved settings are not normalized as required fields.
3. **Reference fidelity incomplete:** role downgrade/absence (`last` and other explicit roles), source-order merge, and image URI deduplication are not proven lossless.
4. **Studio budget bypass for Router:** configured Studio cost gates skip unpriced Router jobs; there is no integrated dry-run estimate-before-live check.
5. **Production selection not proven:** Router is opt-in/additive; direct `runway` remains distinct. No deployment evidence shows the intended Studio flows select `runway_router`.
6. **Config identity is overridable:** deployed `RUNWAY_ROUTER_CONFIG_ID`/per-call config was not verified; no fresh account state was queried.
7. **Image settings handoff incomplete:** image payload construction does not demonstrate that all approved image resolution/aspect/seed settings survive into the Router seam; the image builder receives only the fields explicitly forwarded there.
8. **Prompt rejection visibility and retry fencing:** structured Router eligibility details are stored, but exact user-facing constraint presentation is unproven; explicit continuity retry can alter a Router prompt and is not fenced off for `no_eligible_model` recovery.
9. **Multi-shot coverage is not end-to-end for the full contract:** current Router multi-shot test is adapter-level and does not vary every independent canonical input.
10. **NVIDIA runtime endpoint not demonstrated:** Muse’s configured default is an example-domain URL; the deployment override that would prove the NVIDIA endpoint was not inspected.
11. **Portal state/preferences remain unknown:** there is no current read-only verification of Router existence, allowlist/Quality settings, or ceilings. Official dry-run behavior cannot be assumed successful from mocks.

## L. Exact next authorized action

**Do not create or modify the Portal Router configuration now. Do not run a dry run or generation from this gate.** The architecture gate fails on the code-level gaps above, and the present request authorizes only this read-only audit/report.

The next action is for the creator to authorize a separate **code-remediation and re-audit** task addressing the listed contract, reference, budget, settings, prompt-error, and end-to-end isolation gaps. After every architecture gate passes, obtain separate explicit authorization before any Portal read/write or provider request. Portal creation is not recommended or authorized by this report.

**STOP.**