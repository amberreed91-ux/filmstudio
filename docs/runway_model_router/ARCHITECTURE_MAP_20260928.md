# Runway Model Router — Architecture Map (2026-09-28)

Status: integration is implemented and covered by mocked tests; the live account remains blocked by missing Router configuration. No Meta Muse changes, canonical creative changes, or billable generations were made as part of the separation verification pass.

## Studio architecture placement (verified)

```text
Studio canonical truth / approved script, scene, shot, references, camera plan
        ↓ (read-only context assembly)
Existing Co-Director chat: co_director_chat_service
        ↓ injected LLMCallable via proactive route / co_director_chat seam
NVIDIA Meta Muse chat provider: muse_chat_provider.call_muse
        ↓ advisory text response (not a state mutation)
Creator / Studio workflow explicitly accepts or ignores advice
        ↓
Generation preflight: generation_context_service + reference/prompt validation
        ↓
Frozen creative generation contract (canonical creative inputs + creator-approved decisions)
        ↓
Runway Model Router (downstream execution selection)
        ↓
Resolved model/settings/cost → execution metadata → generation result

The implementation uses a deterministic manifest/fingerprint and does not claim
that the mutable Pydantic RenderJobInput itself is immutable.
```

Meta Muse's concrete implementation is `app/services/providers/muse_chat_provider.py`; the active Co-Director route is `app/routes/proactive.py` → `app/routes/co_director_chat.py` → `app/services/co_director_chat_service.py`. Muse Glimmer 30B is registered in `app/services/model_registry.py` as provider `muse`, modality `chat`, role `advisory_intelligence`, with no generation modes or render credits. The route assembles film context and returns a chat reply. It does not write canonical state, approve, create a render job, or invoke Runway. `provider_router` exists as a Co-Director persona but is prompt content only; model eligibility and execution remain outside Muse.

Runway Router is downstream of preflight, in `app/services/providers/runway_router_provider.py`, called by `RunwayRouterAdapter` (`app/adapters/__init__.py`) for video and the image-provider seam for images. It receives a validated request and returns routing/task metadata. The Studio-side `model_router` and `model_registry` apply only to direct `runway` selection; the `runway_router` path has no Studio model selection/scoring and rejects model overrides.

## Creative manifest and execution metadata boundary

`SceneProductionPipelineService.prepare_scene_batch` builds the preflight plan from canonical current scene/storyboard/shot/reference/camera state and generation-context IDs. The manifest is read-only, contains no provider/model/cost/readiness decision fields, and fingerprints only scene/storyboard/shot creative inputs and shot count/duration. Batch readiness blockers and provider-specific cost estimates remain adjacent preflight output, not part of the creative manifest. Each submitted render job persists its generation-context identity separately; post-routing resolved model, estimated/realized credits, resolved settings/input, config, pipeline/emptiedBy and routing mode are in `render_jobs.metadata.router_execution` and normalized provider-response metadata.

The video adapter validates references before any provider request. Explicit and consistency references retain canonical order; there is no blank filtering or weight sort. Only an explicitly designated storyboard frame receives the `first` role; all other required reference assets are sent as `reference` roles. Invalid/blank/unsupported/overlong references, malformed consistency payloads, and more than four required video references produce a failed job with `router_execution.reference_incompatibility` (stable code plus details), preserving the input contract. Image request builders likewise reject unsupported or over-limit references before HTTP. If Runway reports no eligible model for the required request, Studio surfaces that failure and stops. No ref is removed and no direct Runway/NVIDIA/other provider fallback is attempted. Studio does not independently infer model-specific compatibility omitted by the Router eligibility response.

Manifest construction also strips execution-only fields recursively from parameters (provider/model/router selection, pipeline, resolved model/settings/input, execution metadata/cost and related result fields). Provider/model resolution remains in `router_execution` / normalized result metadata, outside the creative manifest.

Existing generation job payloads remain mutable Pydantic records through Studio's established preprocessing. Therefore “frozen creative contract” means the deterministic creative manifest is separated from execution metadata and neither Router nor Muse may rewrite canonical Studio state; it does not claim a language-level immutable object implementation.

## Router management API finding

Runway's official configuration page says the same create, update, and delete actions are available through the Model Router API and SDKs, in addition to Developer Portal configuration. Thus configuration creation/modification is API-supported; no endpoint is invented and no management write was made. For this pass the creator's exact action remains to create `studio-production-router` in the Developer Portal, then report the generated management UUID. Generation continues to use the immutable slug.

## Account readiness

The credential's most recently verified state is in `FINAL_REPORT_20260928.md`: `GET /v1/routers` returned no saved Router configs; target UUID retrieval and dryRun by slug failed with `router_config_not_found`. This pass made no account/API calls and no create/update/delete operation. The creator should create the saved router in the Developer Portal using the exact slug, then provide the generated management UUID; only after that, perform read-only GET verification and image/video dry-run probes.


Authoritative Runway contract used for this map (read, not guessed):
- https://dev.runwayml.com/quickstart.txt
- https://docs.dev.runwayml.com/llms.txt
- https://docs.dev.runwayml.com/_llms-txt/model-routers.txt
- https://docs.dev.runwayml.com/model-routers/ + /model-routers/generating/ (+ configuration page)
- https://docs.dev.runwayml.com/api.md and the generated-from-OpenAPI schemas for
  POST /v1/generate/image, /v1/generate/video, /v1/generate/audio (fetched from
  https://docs.dev.runwayml.com/openapi.json)

Authoritative target: configId `studio-production-router` (slug), Router ID
`138f4c50-3411-4aee-88a9-91dd56b90987` (account/resource identity of the router
configuration — NOT sent as configId; the API takes the slug only).

## A. Current architecture map

Two parallel "provider" layers exist; both are real, both are used:

1. **Video render path (production path for shots):**
   `RenderService.create_job` (app/services/render.py) → preflight/idempotency →
   `RenderService.submit_job` → `get_adapter(job.provider, config)`
   (app/adapters/__init__.py `ADAPTER_REGISTRY`) → `RunwayAdapter.submit_job`
   → POST /v1/text_to_video or /v1/image_to_video with `model` ALWAYS present
   (default `RUNWAY_MODEL` env, default "gen4.5") → poll GET /v1/tasks/{id}.
   Persistence: RenderJobModel (`provider_job_id`, `metadata`
   `provider_payload_metadata` (endpoint/model/prompt_length/reference_count),
   `provider_response_normalized` (task_id/model/status/error)), `generation_context`
   and `model_selection` metadata via `_generation_context_metadata`,
   prompt budget via `prompt_budget_service.budget_job` (fail-closed), seed
   locking, cost gate (`generation_cost_gate.estimate_shot`).

2. **Provider-agnostic seams (smaller, newer, cleanly abstracted):**
   - Image: `providers/image_provider.submit_image_render(payload, config)`
     → config-gated dispatch table `_IMAGE_PROVIDER_REGISTRY`
     = {local_image, nvidia, runway}; `runway_image_provider.py` (gen4_image,
     POST /v1/text_to_image, fail-closed prompt ≤1000, references ≤3).
   - Video: `providers/video_provider.submit_video_render` — a stub (pending/failed
     by config gate; no real network calls).
   - Base abstraction: `providers/base.RenderProvider` (render/execute) +
     `providers/registry.ProviderRegistry` (mock, real_stub) — used by
     `providers/execution_layer.py` and the provider config/readiness surface.

3. **Model routing today (Studio-side, pre-Runway-Router):**
   `app/services/model_registry.py` (verified per-model capability/pricing table)
   + `app/services/model_router.py` (`ModelRouter.select_model` AUTO/USER,
   capability match, fail-closed on user-selection conflict, fallback to
   `RUNWAY_MODEL` default when AUTO has no compatible model). Consumed by
   render.py `_resolve_model_selection` (metadata only) and
   `_validate_model_override` (allowlist gate). This is a recommendation/registry
   layer — it names a model; it is not Runway's router.

4. **Generation preflight:** RenderService.create_job is the preflight gate
   (provider validation, model override validation, idempotency, storyboard-frame
   provider restriction, prompt budgeting fail-closed, reference resolution via
   consistency payload + environment continuity context, cost gate at
   previs/batch entry points). No provider call occurs before submit_job.

5. **Multi-shot:** scene_production_pipeline_service + render batches
   (`create_scene_batch`), scene assembly, prompt slots per shot. Per-shot
   routing (docs/multishot_integrity_audit.md): sufficient today; no Scene-002
   special case exists in code (Scene 002 state lives in project data only).

6. **Meta Muse:** `providers/muse_chat_provider.py` (Muse Glimmer 30B) is wired
   ONLY as advisory chat behind the existing `LLMCallable` seam
   (co_director_chat_service/routes). Registry role `advisory_intelligence`,
   chat modality, no generation role → render routing/cost gates can never
   select it. Fully separate from render execution today.

## B. Exact current Runway integration seam

- **Video (the seam that matters):** `ADAPTER_REGISTRY["runway"] = RunwayAdapter`
  (app/adapters/__init__.py). Contract: submit_job/get_job_status/cancel_job/
  fetch_outputs/get_status over RenderJobModel. It hardcodes the model on EVERY
  request (`self._runway_model(job)` → params.model (registry-validated) or
  `RUNWAY_MODEL` env default "gen4.5"), calls direct-model endpoints only
  (/v1/text_to_video, /v1/image_to_video), and sends Studio's model-specific
  `ratio` values (e.g. "1280:720"). There is no router mode.
- **Image:** `submit_image_render` seam → `runway_image_provider.py`
  (POST /v1/text_to_image, model gen4_image hardcoded, ratio translation at the
  adapter boundary, fail-closed prompt/reference handling).
- **Config:** RenderService._initialize_providers builds the "runway"
  ProviderConfig (key from RUNWAYML_API_SECRET | RUNWAY_API_KEY |
  VIDEO_PROVIDER_API_KEY; endpoint https://api.dev.runwayml.com).
  `providers/config.py` mirrors video/image provider envs.
- **Prompt policy:** `prompt_budget_service.prompt_policy(provider, model)` —
  conservative 512-char application ceiling for runway; Scene 002 prompts are
  3,084–3,290 chars, so runway currently fails closed at budget time
  (needs_review) — see docs/forensics/SCENE002_GENERATION_PREFLIGHT_20260928.md.

## C. Exact changes required to introduce the Model Router

1. New module `app/services/providers/runway_router_provider.py` — the ONLY
   place that knows the router contract:
   - constants: RUNWAY_ROUTER_PROVIDER_NAME="runway", ROUTING_MODE_MODEL_ROUTER,
     DEFAULT configId "studio-production-router" (env override
     RUNWAY_ROUTER_CONFIG_ID), endpoints /v1/generate/{image,video,audio}.
   - `build_runway_router_video_request(...)` / `..._image_request(...)`: model-
     agnostic bodies `{configId, dryRun?, input:{promptText, aspectRatio(16:9
     form), duration, referenceImages:[{uri,role}] ...}}` — NEVER a `model` key.
     Fail-closed on: unknown aspect ratio, >16 image refs, empty prompt,
     router-schema prompt caps (image 32000 / video 20000 chars — both above
     Studio's prompts), invalid role mix (≤1 first, ≤1 last).
   - `parse_runway_router_response`: task-created branch (dryRun=false → id) vs
     dry-run branch (dryRun=true → routing metadata only); extracts
     routing.model / provider / configId / resolvedSettings.optimizeFor /
     priceCeiling / resolvedInput / estimatedCost.credits.
   - `RunwayRouterAPIError` with `no_eligible_model` + `pipeline` + `emptiedBy`
     parsed and carried verbatim (fail closed, no fallback, no reference drop).
   - `submit_runway_router_video_render(dry_run=...)`: request → (dry run?
     return decision) → task id → bounded poll (reuses Runway task lifecycle,
     statuses PENDING/THROTTLED/RUNNING/SUCCEEDED/FAILED/CANCELLED) →
     provider-neutral result carrying execution metadata
     (router_config_id, resolved_model, routing, task id).
2. **Adapter layer:** add `RunwayRouterAdapter(RenderProviderAdapter)` in
   app/adapters/__init__.py registered as `ADAPTER_REGISTRY["runway_router"]`,
   same RenderJobModel contract as RunwayAdapter, delegating payload/response
   work to the router provider module; job.metadata["router_execution"] records
   routing mode, configId, resolved model, estimated cost; real cost captured
   from polled task (`estimatedCost`/`cost.credits`) when Runway returns it.
3. **Render service:** register provider config "runway_router"
   (endpoint/api key identical to runway); `_validate_model_override` must
   REJECT any parameters.model on this provider (fail closed — no concrete
   model may reach the router endpoint); `_provider_model_for_job` returns the
   routing-mode label (never a concrete model) for metadata; generation context
   records `routing_mode="model_router"`, `router_config_id`, and (after
   execution) `resolved_model` as execution metadata only.
4. **Image seam:** add "runway_router" to `_IMAGE_PROVIDER_REGISTRY` with a
   dispatch branch mirroring the runway branch (configId + aspectRatio + refs).
5. **Prompt policy:** add router-mode policy entry — the router's own
   prompt_length filter decides per-model eligibility (max 32k image/20k video
   at the router input; individual models may exclude themselves). Studio does
   not truncate; over-length → fail closed (existing behavior).
6. **Cost gate:** router mode has no Studio-side model to price; estimate
   returns estimated:False unless a resolved model is known from a dry run;
   dry-run estimatedCost.credits is recorded as execution metadata.
7. **Env/docs:** RUNWAY_ROUTER_CONFIG_ID (+ RUNWAY_ROUTER_API_BASE_URL) in
   .env.example; doc note that Router ID 138f4c50-... is the account resource
   id and configId is the slug actually sent.

## D. Conflicts between the existing provider abstraction and the Router API

1. **Model-vs-configId discrimination:** every Runway request today carries
   `model`; the router forbids it (input has NO model field). → router mode
   must refuse `parameters.model` instead of silently ignoring it.
2. **Ratio vocabulary:** direct endpoints use pixel ratios ("1280:720"); router
   endpoints use model-agnostic `aspectRatio` ("16:9"). The router response's
   resolvedInput.ratio returns the model-specific mapping. → translation at the
   adapter boundary only; canonical aspect_ratio unchanged.
3. **Reference semantics:** direct gen4.5 has one promptImage; router input has
   referenceImages[{uri, role: first|last|reference}] (≤4 video / ≤16 image).
   The existing ConsistencyPayload → promptImage selection still applies; role
   mapping happens in the router adapter (first-frame → role "first"), other
   approved refs → role "reference". The router itself excludes models that
   cannot honor the inputs (fail-closed upstream — exactly what Studio wants).
4. **Prompt budget:** Studio's 512-char conservative ceiling vs router input
   caps (32k/20k) — Studio must NOT keep enforcing 512 for router mode or it
   would force a truncation policy the user forbids; policy keyed on routing
   mode instead, still fail-closed (raise, never shorten).
5. **Duration/seed vocabulary:** router video duration 2–30 (models excluded if
   unsupported), seed integer 0..2^32-1 — compatible; no conflict.
6. **Cost:** today Studio prices via registry credits_per_second; router mode
   has no canonical model → estimated:False until dry-run/real-cost metadata
   exists (must not fabricate credits).
7. **Status/task lifecycle:** unchanged (same GET /v1/tasks/{id}) — no conflict.
8. **ProviderRegistry (providers/base) vs ADAPTER_REGISTRY:** two registries
   already coexist; the router provider plugs into ADAPTER_REGISTRY (video path)
   and the image seam registry (image path) without touching the mock/real-stub
   registry.

## E. Prompt / reference / aspect-ratio constraints (verified from docs/OpenAPI)

- Router input promptText caps: image 32,000 chars; video 20,000 chars (min 1).
  Studio's Scene 002 prompts (3,084–3,290 chars) fit the router input cap; the
  router's per-model `prompt_length` hard filter may still exclude some models
  (e.g. gen4.5's 1000-char limit) — that is Runway's fail-closed decision, not
  Studio truncation. If EVERY model is excluded → `no_eligible_model` with
  `emptiedBy` naming the filter(s); Studio must surface it and stop.
- referenceImages: image input ≤16 (uri only); video input ≤4 with required
  `role` (≤1 first, ≤1 last; multiple `reference`). uri: https (≤2048 chars) or
  runway:// or data:image (≤5MB). Studio must pass approved refs as-is and fail
  closed if unrepresentable — never drop to become eligible.
- aspectRatio enums: image {16:9,9:16,1:1,4:3,3:4,21:9,2:3,3:2,4:5,5:4}; video
  {16:9,9:16,1:1,4:3,3:4,21:9}. Studio canonical 16:9/9:16/1:1 map 1:1; 3:2/2:3
  are image-only.
- dryRun: same endpoint, `"dryRun": true` in the BODY → same routing decision +
  ESTIMATED cost, no task, no billing. Response shape: {dryRun, routing{model,
  provider, configId, resolvedSettings{optimizeFor,priceCeiling}, resolvedInput,
  estimatedCost{credits}}}. Never invent fields Runway does not return.
- Errors: 400 no_eligible_model (pipeline + emptiedBy), router_config_not_found
  (404), rate limit 429; version header X-Runway-Version: 2024-11-06 required.

## F. Required persistence changes

No schema change needed — render_jobs.metadata (JSON) already persists
arbitrary dicts and is the established home for provider metadata:
- `metadata["generation_context"]` — unchanged (canonical context).
- `metadata["model_selection"]` — for router mode: routing_mode=model_router,
  router_config_id, no concrete model; keep estimated_cost_credits=None unless
  a dry run supplied it.
- NEW `metadata["router_execution"]` — execution metadata only:
  {routing_mode, router_config_id, resolved_model, routing_provider,
  resolved_settings, resolved_input, estimated_cost_credits (dry run),
  realized_cost_credits (from task when Runway returns it), runway_task_id,
  dry_run:boolean, no_eligible_model:{pipeline,emptiedBy} on failure}.
- NEW `metadata["router_dry_run"]` — persisted result of a dry run request
  (never creates a render job, never sets output_payload).
- Asset/model metadata: RenderAsset.metadata and
  output_payload.metadata["provider_response_normalized"] gain
  router_config_id/resolved_model alongside the existing task_id/model keys.

## G. Required UI changes (minimum for this task)

None required for correctness; the Production Board renders provider/model from
existing metadata keys. Minimal honest display (follow-up work, not this task):
surface `router_execution.resolved_model` as execution info and distinguish
"dry run — routing validated" states; the provider picker lists
`runway_router` as a provider (backend list_providers already derives from
_provider_configs, so registration exposes it automatically).

## H. Test plan (new: studio-backend/tests/test_runway_model_router.py + additions)

1. Existing provider tests remain green (run the suite).
2. Router request construction (video/image) — schema-shaped, model-agnostic.
3. configId tests — body.configId == "studio-production-router" (and env
   override path), never the router UUID.
4. No `model` key anywhere in the router payload (deep assert).
5. dryRun=true path: routing-only response parsed; no task id fabricated;
   metadata persisted; nothing billable.
6. Routing metadata persistence (routing/resolved settings/estimated cost).
7. Resolved-model persistence (task-created + dry-run branches).
8. Cost metadata (estimated from dry run; realized from task when present;
   never fabricated).
9. no_eligible_model fail-closed: pipeline/emptiedBy surfaced, job failed, no
   fallback provider invoked, no reference dropped, no retry loop.
10. Reference preservation: approved refs → referenceImages with roles; a
    ref that cannot be represented → hard failure, never silent removal.
11. Prompt preservation: full prompt passes through byte-identical
    (hash-proven); no truncation at any layer.
12. Provider switching: runway ↔ runway_router ↔ simulated do not interfere;
    switching cannot mutate canonical state.
13. Multi-shot: two shots through the router path keep per-shot contracts and
    remain model agnostic (no Scene-002 special case).
14. Idempotency: same request → same idempotency key → one job (existing
    behavior proven for the new provider).
15. Retry behavior: failed router job can retry; retry does not double-submit.
16. Task polling: status mapping incl. THROTTLED; bounded polling; timeout
    fails closed.
17. Failure persistence: router failures recorded (error_message +
    provider_response_normalized + router_execution.no_eligible_model).
18. Regression: routing never mutates canonical creative state (storyboard/
    reference/camera fields unchanged after create+submit through router path).
19. Meta Muse separation: router provider never touches muse modules and vice
    versa; registry roles still make advisory models unselectable for render.
20. Run relevant existing regression suites (runway hardening, image provider,
    model registry/router, prompt budget, render pipeline hardening).

## I. Runway account/config items to verify (not changeable by this task)

1. The config slug `studio-production-router` exists in the Developer Portal
   and is accessible to the account whose key is in RUNWAYML_API_SECRET
   (a 404 router_config_not_found on dry run would prove otherwise).
2. Its per-modality eligible models / allow-deny list / optimization
   preference / price ceilings — unknowable from here; the dry run response
   (resolvedSettings + resolvedInput + estimatedCost) is the read-only probe.
3. Router ID 138f4c50-3411-4aee-88a9-91dd56b90987 corresponds to that config
   (the API cannot verify the UUID↔slug pairing; the Portal shows it).
4. Account credit balance / concurrency limits (capacityFallback metadata
   would reveal capacity effects).

## J. Minimal implementation sequence

1. `providers/runway_router_provider.py` (pure builders/parsers + submit with
   dry-run flag; no Studio state touched).
2. `RunwayRouterAdapter` + ADAPTER_REGISTRY + RenderService provider config.
3. Fail-closed model-override rejection + metadata plumbing (routing mode,
   configId, resolved model) in render service.
4. Image seam "runway_router" branch.
5. Prompt-policy entry for router mode (no silent truncation; fail closed).
6. Tests (the 20 items above).
7. Optional, explicitly non-billable: dryRun=true probe against
   /v1/generate/image (and video) with the approved Scene 002 payload shape —
   records routing decision metadata only.
STOP before any live generation; a live call stays blocked behind the existing
preflight + explicit creator action.
