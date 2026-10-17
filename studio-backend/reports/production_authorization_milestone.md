# Production authorization milestone — owner approval and Router last-mile gate

## Requirement verified

For non-contract-only Runway Router work, current persisted owner and exact approved storyboard provenance are re-evaluated at the Router adapter entry and immediately before each Router HTTP call (the cost estimate and the live submit are distinct calls). The adapter rejects a changed job payload, manifest, storyboard binding, owner, approval, or project scope before live submission. A durable diagnostic `production_authorization` annotation is excluded from the canonical job comparison because the adapter adds it after the initial check; every other metadata field remains identity-bound. The Scene 002 contract-only path retains its existing specialized proof checks.

Queue dispatch continues through `RenderService.submit_job` into the same Router adapter gate, not an alternate execution route. Queue attempt results now truthfully record a returned provider failure instead of labeling the attempt `complete`.

## Implementation evidence

- [production_authorization_service.py](app/services/production_authorization_service.py): owner, storyboard/version/shot, durable job identity, frozen contract and manifest validation.
- [adapters/__init__.py](app/adapters/__init__.py#L1846-L1925): Router adapter admission check; [last-mile recheck](app/adapters/__init__.py#L2298-L2345) reloads current durable authority immediately before each outbound Router request.
- [render.py](app/services/render.py#L2038-L2048): capture of authenticated request actor at Router job creation; direct Runway submission remains blocked.
- [storyboard_blueprints.py](app/routes/storyboard_blueprints.py#L157-L179) and [storyboard_blueprint_service.py](app/services/storyboard_blueprint_service.py#L361-L410): approval actor comes from request context when authenticated and is persisted as approval witness.
- [production_queue_service.py](app/services/production_queue_service.py#L744-L800): returned terminal failures are recorded as failed queue attempts and expose failure details.

## Tests executed

All executed from `studio-backend` using `.venv/bin/python -m pytest` and deterministic provider doubles only:

- Focused milestone/regression suite: **204 passed in 16.39s** across owner authorization, storyboard service/routes, frozen generation contract, Router projection, queue service, render provider safety, direct Runway bypass, Runway hardening/model registry, and adapter containment.
- The focused service suite additionally proves live SQLite authorization: current owner + authenticated approval + exact approved storyboard permits the policy; changed actor/owner/approval denies it.
- Adapter tests tamper with job prompt, manifest, storyboard version, and owner after the estimate callback; no live Router call occurs. Queue execution with an unauthorized actor records failure and never reaches the submission stub.
- Queue regression verifies disabled direct Runway is denied; the failed attempt carries the actual provider failure.
- `git diff --check` passed for the five files changed in this follow-up (adapter, authorization service, authorization tests, queue service, queue tests). The prior report's broad diff check had identified unrelated/pre-existing whitespace in `app/data/storage.py`; this follow-up does not edit storage.
- No production render, live generation, paid provider call, upload, or external production action was run.

## Continuation verification — 2026-10-10

- The generation/authorization/pipeline/persistence regression group passed: **108 passed** across `test_scene_production_pipeline_service.py`, `test_generation_contract_remediation.py`, `test_production_authorization_service.py`, and `test_render_job_persistence.py`.
- The authorization/provider/queue/stability integration group passed: **195 passed** across storyboard service/routes, queue service, render provider safety, Runway registry/state/retry/direct-provider/hardening, model routing, adapter containment, and project-access boundaries.
- Together these two focused runs verified **303 passing tests** with no live provider calls. They include SQLite owner-approved creation and metadata reload, refusal for missing/non-owner actors, stale storyboard approval rejection, frozen-dialogue and camera contract behavior, and queue/provider fail-closed regressions.
- A focused `git diff --check` over the affected test files and milestone evidence passed.

## Authorization gaps closure — 2026-10-10

Both outstanding gaps from the limits below are now closed at the provider execution boundary:

1. **Retry / recovery / lease / redispatch paths.** Traced every mutation path: `RenderService.retry_job` funnels into `RenderService.submit_job`; queue lease acquisition, `execute_leased_item`, and redispatch call `render_svc.submit_job`; `recover_jobs_after_restart` and `poll_active_runway_jobs` only call the read-only `reconcile_completed_runway_task` / `get_job_status` pollers, which never submit. The single provider-execution boundary is `RenderService.submit_job` → `RunwayRouterAdapter.submit_job`. A new regression test proves a retry whose storyboard approval went stale fails closed with zero Router HTTP calls.
2. **Direct `_submit_job_after_authorization` invocation.** The authority check now lives in a shared adapter helper invoked both at the `submit_job` entry gate and at the top of `_submit_job_after_authorization` itself, so a direct call resolves durable storage, re-evaluates owner-approved storyboard authority (request + durable row), fails closed with the same denial shape, and always enables the last-mile recheck before each Router request. New tests prove direct calls with missing storage or a revoked owner are denied with zero provider calls, and queue redispatch through the real inner method (not a stub) makes zero provider calls when approval is invalid.
- Direct-call white-box tests (`test_generation_contract_remediation.py`, `test_runway_router_projection_integration.py`) now provision owner-approved storyboard authority around their frozen jobs; intentionally corrupted contracts still fail closed with zero provider calls, denied at the authority integrity gate or the downstream frozen-contract check as appropriate.
- Combined focused run: **307 passed in 22.75s** (the prior 303 plus the 4 new boundary tests), deterministic provider doubles only, no live provider calls. Focused `git diff --check` over the changed adapter, authorization tests, contract/projection tests, and this report passed.

## Explicit limits — this is not production-engine completion

1. `production_approval.actor_authenticated` is application evidence derived from authenticated request context, not a cryptographic signature. Durable authority issuance, signing, revocation/invalidation, expiration, renewal, and stronger anti-forgery semantics remain open.
2. All located new `runway_router` durable render-job creation paths flow through `RenderService.create_job` (including route, pipeline/batch, retry/adherence, and queue helpers); creation validates owner and approved storyboard authority before persistence, and the provider adapter repeats authority checks. Legacy `runway` job hydration/backfill and explicitly seeded/demo historical rows are compatibility/data-import paths, not newly authorized production execution. Adapter tests still establish the final boundary; creator request identity relies on current authenticated request context.
3. Creator-selected Runway model capability fit is enforced at service creation/submission, but effective routed-model identity (`router_execution.resolved_model`) is recorded after execution; the concrete Router choice is not independently confirmed end to end before provider contact.
4. Queue execution is not certified for fencing at the irreversible provider call, exactly-once across process crashes/timeouts, retry idempotency across ambiguous provider responses, or cancellation racing the outbound request. Lease renewal now requires the current owner and a live lease, but there is no heartbeat renewal around long-running execution. Last-mile authority recheck cannot make Runway's remote call atomic with local revocation.
5. Protected Runway image generation/reference provenance, output/task identity, durable asset registration, assembly and final-delivery integrity, and the read-only Production Desk have not been accepted by this milestone.
6. Direct-to-adapter tests use mocked HTTP/provider calls. They establish branch behavior and pre-contact denial, not actual Runway capabilities, completed real runs, or delivery correctness.

## Next fixed-roadmap item

Implement queue lease fencing and heartbeat renewal through long provider execution, with stale-worker/provider-call race tests, while retaining the adapter's current authority and frozen-contract gates. Do not claim exactly-once semantics across remote timeouts until an idempotent remote request identity and ambiguous-response reconciliation are verified. Do not expand into unrelated product work.

## Execution-path, lease lifecycle, and pipeline failure follow-up — 2026-10-10

### Pipeline-hardening failures

- Re-ran the exact previously failing test file. Current result: **17 passed**; no `setting_id_missing` failures remain. The exact four assertions were in `test_duplicate_submission_prevention`, `test_missing_reference_file_stops_before_provider_submission`, `test_provider_call_timeout_records_render_failure`, and `test_ten_controlled_mocked_jobs_complete_without_state_corruption`; they exercise submit idempotency, missing local reference rejection, provider timeout recording, and concurrent batch completion respectively.
- Root cause was fixture provenance, not the reference validator: test scenes used a scene identifier as `setting_id` without a canonical location entity or approved canonical setting reference/anchor, so the validator correctly rejected payload assembly before the tests reached their unrelated assertions. `_StorageStub.seed_project_scene` now provisions the project-scoped canonical setting node plus approved anchor. The missing-file test swaps only that anchor for the intentionally nonexistent URI, so it still reaches and checks its actual file-existence condition. Validation remains fail-closed.

### Production creation-path matrix

- Searched route/service/job persistence entry points. The HTTP render create endpoint and discovered service callers (canonical workflow, clip revision, previs, scene pipeline/batch, queue render helper, retry/adherence, project workflow, agent executor, and storyboard render helper) construct jobs through `RenderService.create_job`. New Runway Router requests hit its pre-persistence owner/actor gate and shared `authorize_runway_submission(..., require_durable=False)` check over project owner, approved storyboard version/shot, frozen contract/manifest identity, and request actor. The durable row is persisted/reloaded and checked before return. No alternate in-scope Router RenderJobModel construction was found.
- `enqueue_existing_render_job` can attach any extant job but does not create or authorize it; execution still reaches `RenderService.submit_job` and the Router adapter gate. Recovery polls existing tasks and does not submit. Backfill and demo seeding are legacy/import/demo rows, not a new authenticated production create path; the adapter refuses unauthorized legacy Router rows.
- No new creation bypass was reproduced, so no duplicate policy implementation or extra creation check was added. Existing Router creation and adapter boundary tests remain the regression evidence.

### Queue lifecycle audit and bounded repair

- Lease acquisition is a conditional SQLite update with a single-row winner, attempt increment, and live/eligible status filter. Expiry atomically clears lease ownership and returns work to `queued` or marks it `dead_lettered` at max attempts. Added a demonstrated gap fix: lease renewal previously accepted any matching owner even after expiry/terminal transition and could write a past expiry. Renewal now requires a current leased/running row, matching owner, unexpired lease, and future requested expiry. Tests cover valid renewal, wrong owner, invalid expiry, and post-expiry denial.
- Queue exception handling previously marked every exception retryable, disregarding render's persisted permanent/transient classification. Added use of the existing render classifier/metadata to propagate permanent nonretryable errors to dead-letter, transient rate limits to retryable failed status, and cancellation to cancelled state. Tests cover permanent invalid-key vs transient rate-limit and cancelled render status.
- Retry remains explicit queue-item requeue and does not edit the render payload; every resumed Router execution re-enters the existing RenderService/adapter authority+frozen-contract gates. Render retry is also centralized at `submit_job`; ordinary retry retains existing Scene 002 proof checks. Queue idempotency has a project+key unique constraint in SQLite (the service pre-read alone is not relied on for uniqueness), though races can surface the storage constraint rather than return the concurrent winner.
- Queue cancellation atomically compares the observed status, owner, and generation, then cancels only that exact attempt. A render worker whose lease was cancelled cannot persist subsequent state or finalize the queue result. It still cannot retract an outbound provider request already accepted; cancellation during the provider call is therefore locally fenced, not remote cancellation.
- Heartbeats run during queue execution and renew only the matching owner/generation while the lease is live. A failed heartbeat marks the execution token lost; stale queue finalization, attempt writes, and fenced render-job persistence are rejected after recovery/reclaim. Atomic fencing protects local SQLite writes and dispatch result commits; it cannot make the external provider operation atomic with lease ownership.
- A storage failure during any queue-fenced render-job save now raises a persistence error and never falls through to legacy project/FK repair, preventing a second unfenced write. Runway's cost dry-run and live submit remain separate HTTP requests, and only the task ID returned by a successful submit response is persisted afterward.
- Remote timeout/retry behavior is **not exactly once**. A timeout or lost response on `POST /v1/generate/video` can happen after Runway accepted the task but before Studio received/persisted its task ID. The adapter reports failure, and queue retries may submit another POST; no verified provider idempotency key or request-to-task lookup is wired into this path. Poll timeouts after receiving a task ID also return failure metadata containing that ID, but current queue failure handling does not reconcile that ID before a retry. No live calls were made, and no exactly-once guarantee is claimed.
- Recovery atomically expires queue leases and terminalizes their running attempt before a new generation can claim the item. Render-job polling/recovery remains read-oriented; it does not itself resubmit provider work. A process death during an outbound request still leaves the remote outcome ambiguous if the task ID was not persisted.
- **Roadmap status for this addendum:** this closes the older queue lease-fencing/heartbeat roadmap item above; that earlier note is retained as historical evidence. Remaining queue limits are remote-submit ambiguity and provider-side cancellation/idempotency. The next fixed-roadmap item is the unaccepted production-output integrity slice: Runway image/reference provenance, task/output identity, durable asset registration, assembly/final-delivery integrity, and the read-only Production Desk.

### Lease-fencing and heartbeat continuation — 2026-10-10

- Added monotonic `lease_generation` fencing to queue item/attempt persistence. The worker token now follows queue execution through render service writes; `save_job` validates the exact, unexpired owner/generation in the same SQLite transaction as the render-job update. Queue attempt start/final updates and queue-item terminal/dispatch commits are conditional on the same token. Expiry marks the active attempt `lease_lost`; cancellation compares the exact observed status/owner/generation and terminalizes its active attempt.
- Heartbeat renewal runs concurrently with long queue execution, requires a live matching lease, cannot shorten an existing expiry, and marks heartbeat loss so post-recovery stale results are rejected. Render-side checks also run before and after provider submission and before persistence. Queue-fenced render persistence failures now fail explicitly and skip unfenced compatibility recovery.
- Regression coverage exercises successful renewal during long local execution; stale-owner renewal/attempt/finalization denial; competing claims; stale worker inability to overwrite authoritative render state after recovery/reclaim; cancellation during blocked work; and attempt terminalization/reclaim. Existing owner authorization/revoked approval queue tests now execute through a fenced queue-storage double because queue execution deliberately refuses unfenced storage.

### Verification (exact commands; deterministic doubles, no live Runway calls)

- `.venv/bin/python -m pytest app/services/test_production_authorization_service.py app/services/test_production_queue_service.py -q`: **44 passed in 8.63s**.
- `.venv/bin/python -m pytest app/services/test_production_queue_service.py -k 'heartbeat or stale_worker or cancellation or expired_lease or competing_workers or final_attempt' -q`: **9 passed, 15 deselected in 1.35s**.
- `.venv/bin/python -m pytest app/services/test_production_queue_service.py app/services/test_production_authorization_service.py app/services/test_render_pipeline_hardening.py app/services/test_render_job_backfill.py app/services/test_render_state_hardening.py app/services/test_render_job_persistence.py app/services/test_render_provider_safety.py app/services/test_runway_provider_hardening.py app/services/test_runway_direct_provider.py app/services/test_model_registry_and_router.py tests/test_runway_router_projection_integration.py tests/test_project_access_boundary.py -q`: **221 passed in 21.21s**.
- An earlier focused invocation failed 2 authorization queue tests because their storage double lacked lease acquisition/finalization/heartbeat behavior; tests were corrected to use a small fencing-capable in-memory storage double, without removing assertions. Re-run above passes. The separately observed broad storage diff also contains pre-existing trailing whitespace at `app/data/storage.py:7523` in the unrelated `access_resource_projects` hunk; do not attribute or clean it in this queue follow-up.
- Not run: live Runway submission, remote-timeout reconciliation, remote cancellation, or a real two-process crash test. Queue fencing is verified for the SQLite path and deterministic async races, not the remote provider boundary.

## Creator-selected Runway model capability enforcement — 2026-10-10

Closed the model-capability slice of limit 3 at the service boundary (no route, adapter, or UI logic changed; no live provider calls):

- **What was missing.** `_validate_model_override` checked only registry existence/availability for `runway`/`runway_direct` overrides, never capability fit; the full capability validator (`ModelRouter.select_model` with `user_model_id`) ran only inside observational `_generation_context_metadata`, which swallows failures and never blocks. A creator could therefore request e.g. `h3_max` for a 30s shot and pass creation with no fail-closed gate.
- **Implementation** (`app/services/render.py`): new `_model_requirements_for_user_selection` builds registry requirements solely from supplied shot inputs (mode from references, reference count, duration, resolution, audio/frame flags — absent dimensions are not validated); new `_validate_user_model_capabilities` validates a concrete creator `parameters["model"]` for `runway`/`runway_direct` through the bounded router as USER_SELECTED, raising the capability conflict (never silently swapping) and returning the selection for identity recording. Enforced at `create_job` (fails before persistence) and twice at `submit_job` — an early gate ahead of the generic direct-provider block so the specific capability reason surfaces and post-creation payload mutation fails closed, plus a recheck beside the existing override validation inside the submission flow. Compatible selections persist `metadata["creator_model_identity"]` as requested/validated/effective identity. The `runway_router` path is untouched: concrete overrides remain rejected at all three existing layers (service, adapter entry, router provider schema).
- **Tests** (`app/services/test_model_registry_and_router.py`, +4): incompatible creator model blocked at creation with the capability reason; compatible selection records requested/validated/effective identity; mutated persisted payload rechecked at submission (job marked failed, zero provider contact); router-path concrete override still rejected.
- **Verified.** 37 passed across the model registry/router + direct-provider suites; 227 passed across the wider authorization/contract/projection/queue/provider group (model, authorization, generation-contract remediation, router projection, provider safety, Runway registry/hardening, queue service), deterministic doubles only, no live provider calls. `git diff --check` clean over the touched files.
- **Superseded failure note.** The four named pipeline-hardening tests were reported failing in an earlier snapshot, but the current evidence shows this was a stale test fixture: they omitted required canonical setting provenance. The fixtures now seed that valid provenance and the unchanged reference-integrity requirement remains enforced; current focused result is 17/17 passing. This is not an unresolved pre-existing implementation failure.
- **Remaining model-identity limits.** Effective routed-model identity (`router_execution.resolved_model`) is still execution metadata recorded after Runway responds; pre-execution capability validation against the router's eligible-model set is not possible client-side (Runway owns eligibility); image-modality and advisory models remain excluded from video routing by registry modality scoping. Unsupported capabilities continue to fail closed everywhere a creator model is accepted.

## Lease-fencing continuation verification — 2026-10-10

- **Provider-dispatch race found and closed locally:** `RenderService.submit_job` checks the lease before invoking an adapter and after its await. Runway Router's live request runs inside `asyncio.to_thread`, so expiry/reclaim between the service check and the actual HTTP call could otherwise allow a stale worker to start a POST. `_runway_router_request` now checks the inherited queue fencing token immediately before `urlopen`; when stale, the request raises before any HTTP contact. This only closes the not-yet-started request race. A request already handed to `urlopen` cannot be retracted or made atomic with SQLite lease ownership.
- **Targeted deterministic test** pauses at that boundary, lets the checker observe lost ownership, and asserts `urlopen` was never reached; no provider/live calls are made. SQLite fencing also conditions render-job persistence, queue-item finalization, attempts, renewal, and cancellation on the lease owner/generation; recovery terminalizes the old attempt and a reclaimed generation rejects old state writes. Heartbeat renewal was exercised while a local async render was blocked.
- **Final verification after the dispatch-boundary addition:**
  - `.venv/bin/python -m pytest app/services/test_production_queue_service.py -k 'stale_worker_lost_before_router_http or heartbeat or stale_worker or cancellation or expired_lease or competing_workers or final_attempt' -q`: **10 passed, 15 deselected in 1.37s**.
  - `.venv/bin/python -m pytest app/services/test_production_queue_service.py app/services/test_production_authorization_service.py -q`: **45 passed in 8.17s**.
  - `.venv/bin/python -m pytest app/services/test_production_queue_service.py app/services/test_production_authorization_service.py app/services/test_render_pipeline_hardening.py app/services/test_render_job_backfill.py app/services/test_render_state_hardening.py app/services/test_render_job_persistence.py app/services/test_render_provider_safety.py app/services/test_runway_provider_hardening.py app/services/test_runway_direct_provider.py app/services/test_model_registry_and_router.py tests/test_runway_router_projection_integration.py tests/test_project_access_boundary.py -q`: **222 passed in 19.01s**.
- **Failure diagnosis:** the pre-edit pytest traceback logs from the previous interrupted session were not preserved in the current workspace. Rather than infer their cause from old notes, reran the current focused tests: the checkpoint screening test file collects and executes, and all 42 tests passed. Historical exception/traceback claims from the prior partial report are therefore not independently verified here and are not used to explain any current failure. No failed pytest command remains in this stabilization run.
- **Remote timeout remains ambiguous:** `_runway_router_request` performs a synchronous POST and maps `URLError`/timeout to a failure without a task ID. If Runway accepts the POST but its response is lost/times out, Studio cannot determine whether a task was created. The queue can retry and submit another POST because no verified provider idempotency token or task lookup keyed by Studio request identity is persisted. Once a task ID is received, polling timeouts include it in provider result metadata, but the Router adapter only stores `provider_job_id` on success; retry-time reconciliation of failed attempts is not established. Exactly-once remote execution is therefore **not guaranteed**. No live calls or changes to Runway retry policy were made.
- **Roadmap remains open for the next slice:** establish Runway image/reference provenance, task/output identity, durable asset registration, assembly/final-delivery integrity, and the read-only Production Desk. Queue lease fencing/heartbeats are verified for the tested SQLite + deterministic async paths, but provider in-flight cancellation, ambiguous remote submission outcomes, and real multi-process crash recovery remain unverified/unsupported.
- **Cache consistency hardening:** when a fenced render write fails because ownership was lost, the in-memory render cache is restored from the durable row (or evicted when the row is absent), preventing stale mutated state from being served after the queue worker rejects its result.
- **Whitespace check:** `git diff --check` on task-relevant tracked files reports one trailing-whitespace line at `app/data/storage.py:7524`, in the unrelated pre-existing `access_resource_projects` hunk. It is intentionally left unchanged. Other task-relevant tracked diff hunks and the newly appended provider boundary changes introduce no whitespace failure.
- **Final rerun after cache consistency hardening:** focused race selection **10 passed, 15 deselected in 1.26s**; queue + authorization **45 passed in 7.90s**; full focused regression command **222 passed in 18.89s**; Python compilation check passed.

## Production-output integrity continuation — 2026-10-10

### Gap and bounded change

- **Missing gate:** `FinalShortFilmPackageService.create_package_from_project` treated any non-empty remote URL as reachable; the completed-renders path could persist a `manifest://.../latest` placeholder on stitch failure or local-only clips. Package creation also swallowed generated-asset registration errors, while Production Acceptance checked for a URL/file but not an available durable asset belonging to the exact package/project/output. Consequently, approval could be based on a playable-looking URL without durable canonical registration, and reports could stay current after that registration changed.
- **Service-layer repair:** final-package creation now rejects empty/synthetic-manifest URLs, validates studio output root containment/nonempty local files, and accepts remote references only when they are syntactically HTTP(S) with a host. A creator review alone no longer marks a package `approved`. Generated asset registration failures propagate to the caller; any already persisted package remains non-approved and cannot pass acceptance without its asset record.
- **Assembly/deliverability repair:** `create_package_from_completed_renders` now rejects local/non-hosted single clips and manifests rather than presenting them as final film outputs. Failed hosted stitching raises before package persistence; successful hosted stitch and the established scene-pipeline/single hosted-preview path continue through package creation. Existing assembly metadata remains intact for successful outputs.
- **Canonical registration gate:** Production Acceptance now requires an `available` or `analyzed` `generated_output` record whose project, source URL, and `metadata.package_id` all match the package. That registration is included in the acceptance input fingerprint and current-snapshot approval-guard comparison, so removal, mutation, or failed status after the report blocks approval as stale. Existing final-output checks also reject empty local files, symlink escapes from `/outputs`, and non-HTTP remote references.
- **Focused tests** cover missing registration, cross-package/project/URL mismatches, failed registration status, successful matching registration and approval, stale registration between acceptance and approval, registration-write failure, empty/malformed/manifest outputs, local clip-to-manifest fallback, failed stitch, and preserved successful output registration/assembly paths.

### Verification

All commands were run from `studio-backend` with `.venv/bin/python`; no Runway/provider calls were made:

- `.venv/bin/python -m pytest app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py app/services/test_video_asset_service.py -q`: **42 passed in 4.86s**.
- `.venv/bin/python -m pytest tests/test_checkpoint_4c_screening_room_integrity.py app/services/test_scene_assembly_service.py tests/test_take_selection_delivery.py app/services/test_production_acceptance_identity.py app/routes/test_production_acceptance_routes.py -q`: **29 passed in 9.80s**.
- `.venv/bin/python -m py_compile app/services/final_short_film_package_service.py app/services/production_acceptance_service.py app/models/production_acceptance.py app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py`: passed.
- `git diff --check -- app/services/final_short_film_package_service.py app/services/production_acceptance_service.py app/models/production_acceptance.py app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py`: passed.
- A broader exploratory command also included `tests/test_offline_production_delivery.py`; two unrelated dialogue-handoff tests failed (`test_existing_media_mode_never_calls_voice_provider`, `test_explicit_empty_dialogue_does_not_restore_scene_dialogue`) because raw lines/no frozen handoff are rejected. These are outside the touched integrity code and were not changed. The focused final rerun excludes that unrelated file; targeted integrity and delivery/screening suites pass.

### Limits and next roadmap work

- Syntactic validation does **not** prove a remote HTTP output is live, playable, a valid video container, or controlled by the project; remote `HEAD`/fetch validation, media probing for arbitrary source URLs, signed content hashes, and provider task/output identity remain unverified. The local output fingerprint is existing name/size/mtime evidence, not a cryptographic content digest.
- The change establishes final package media registration/approval gates only. Runway image/reference provenance, task/output identity, full assembly/final-delivery integrity beyond this package path, and the read-only Production Desk remain the next unfinished fixed-roadmap work; no reconciliation phase or parallel registry was introduced.
- No real provider render, remote fetch, external upload, or production delivery was performed.

**Roadmap status:** queue lease fencing/heartbeat and the bounded final-package registration/deliverability slice above have local regression evidence. The next fixed-roadmap slice remains Runway image/reference provenance and task/output identity, then broader assembly/final-delivery integrity and the read-only Production Desk.

## Production-output integrity stabilization — 2026-10-11

Earlier evidence above is preserved. This section records only what was re-diagnosed and re-verified after the session edits to `production_acceptance_service.py`, `test_final_short_film_package_service.py`, and `test_checkpoint_4c_screening_room_integrity.py`.

### Failures found (actual pytest output, not guesses)

1. `tests/test_checkpoint_4c_screening_room_integrity.py` failed at collection with `SyntaxError` (`ast.parse`): line 196 merged two statements (`output_path = ...` and `output_path.write_bytes(...)`) and left the following `FinalShortFilmPackage(...)` block over-indented.
2. `app/services/test_final_short_film_package_service.py::test_final_status_can_only_be_set_after_acceptance_and_registration` failed with `UnboundLocalError: cannot access local variable 'VideoAssetService'`: the function used the top-level `VideoAssetService` import and then re-imported the same name locally, making all earlier uses local.
3. `tests/test_checkpoint_4c_screening_room_integrity.py::test_final_approval_selects_current_output_and_persists_project_completion` and the package guard test failed at approval with `StateError: Production acceptance guard failed: Production evidence changed after acceptance. Re-run acceptance for the current output and registration.` Root cause was fixture/service wiring, not the guard intent: the acceptance run used a tmp `outputs_root` (and, in screening, an empty-scene `ProjectStore`), while the guard evaluated through a service with the default backend `outputs_root` (and, in screening, the stored 2-scene project). The content fingerprint (`size:sha256`) and `scene_ids` therefore differed immediately after the run.

### Bounded fixes (no reset/stash/revert; unrelated work preserved)

- Fixed the checkpoint syntax break (newline + 12-space arg indent) and removed a duplicated `_project_store_service` assignment.
- Removed the redundant local `from app.services.video_asset_service import VideoAssetService` in the package guard test (top-level import retained).
- Production wiring: `FinalShortFilmPackageService.update_package_status` sets the guard's output root to the package service's configured root before evaluation; `ScreeningRoomService.__init__` wires both package and acceptance services to its `outputs_root`. The checkpoint helper propagates its temp root to acceptance, and the final-approval fixture runs acceptance against the same service/storage project scenes and outputs root.
- Contract correction: reverted the session's expansion of the approval guard to `archived`. Per `plans/sprint_7_production_acceptance_testing_spec.md` Step 9 ("If desired status is `draft`, `ready_for_review`, or `archived`, do not require acceptance"), the guard again applies only to `approved`/`packaged`. No test covered archived-gating; the change was unnecessary and inconsistent.
- Removed an unused local `from app.data.storage import DatabaseStorage` in `update_package_status`.
- Kept the necessary changes: manifest/`manifest://` rejection, `/outputs` containment + non-empty checks, HTTP(S)-only remote syntax, review-alone stays `ready_for_review`, registration-failure propagation, stitch-failure/local-clip raising instead of manifest persistence, `final_output_registered` blocker tied to exact project + package + URL, asset-fingerprint + sha256 content fingerprint in the acceptance hash and stale comparison. Acceptance also verifies the selected package belongs to the requested project; a regression now exercises the cross-project package-ID case.

### Verification (exact commands from `studio-backend`, deterministic doubles, no live Runway calls)

- `.venv/bin/python -m pytest app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py tests/test_checkpoint_4c_screening_room_integrity.py -q`: **42 passed in 10.10s**.
- `.venv/bin/python -m pytest app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py app/services/test_video_asset_service.py -q`: **44 passed in 5.07s**.
- `.venv/bin/python -m pytest tests/test_checkpoint_4c_screening_room_integrity.py app/services/test_scene_assembly_service.py tests/test_take_selection_delivery.py app/services/test_production_acceptance_identity.py app/routes/test_production_acceptance_routes.py app/services/test_full_film_assembly_service.py tests/test_assembly_routes.py -q`: **34 passed in 10.43s**.
- Combined final rerun after cross-project identity coverage and unused import cleanup: `.venv/bin/python -m pytest app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py app/services/test_video_asset_service.py tests/test_checkpoint_4c_screening_room_integrity.py app/services/test_scene_assembly_service.py app/services/test_full_film_assembly_service.py tests/test_take_selection_delivery.py tests/test_assembly_routes.py app/services/test_production_acceptance_identity.py app/routes/test_production_acceptance_routes.py -q`: **79 passed in 15.59s**.
- The earlier attempt to add an approval-guard test hit the wrong exact-string context and made no file change. The actual screening test was read and no blind replacement was retried. Two focused pytest runs and the combined final run all passed.
- `.venv/bin/python -m py_compile tests/test_checkpoint_4c_screening_room_integrity.py app/services/production_acceptance_service.py app/services/final_short_film_package_service.py app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py`: passed.
- Targeted `git diff --check` over the seven task integrity implementation/model/test files reported two whitespace-only added blank lines at `final_short_film_package_service.py:449,473` inherited from pre-existing whitespace in the touched package-status region. The stabilization edits removed those spaces, then the final diff check was rerun clean; no unrelated whitespace was changed.

### Verified behavior (separate from unverified claims)

- An accepted package is tied to exact requested project and package, final output URL, output bytes (sha256 for `/outputs` files), and a matching durable `generated_output` asset (`project_id` + `source_url` + `metadata.package_id`, status `available`/`analyzed`). Removal/status/identity changes and byte changes (including unchanged size/mtime) invalidate the acceptance fingerprint. Cross-package/project/output registrations block acceptance. Regression coverage includes a package-ID/project mismatch, wrong project, wrong package, wrong output URL, failed status, changed registration, and output byte replacement. Any stale report blocks `approved`/`packaged`.
- Synthetic `manifest://` outputs and empty/non-hosted assembly results never persist as deliverable packages; failed hosted stitch raises before persistence.
- No live Runway calls, production delivery, authorization/lease-fencing reopen, or reconciliation feature were added.

### Remaining limitations

- Remote HTTP(S) validation is syntactic only; liveness, playability, container validity, project control, signed hashes, and provider task/output identity remain unverified.
- The sha256 content fingerprint above corrects the older "name/size/mtime only" limit note for local `/outputs` files; non-`/outputs` local paths and remote URLs still use `package_id:URL` identity, not content hashes. Remote HTTP(S) registration is syntactic and does not establish ownership or playability.
- Broader assembly/final-delivery integrity beyond this package path, Runway image/reference provenance, and the read-only Production Desk remain open roadmap work.

### Reverification after the interrupted run — 2026-10-11

The earlier stabilization section is retained as historical evidence; the following results supersede its broad-test status for the current working tree.

- Final passing integrity command after the final compatibility adjustment: `.venv/bin/python -m pytest -q app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py tests/test_checkpoint_4c_screening_room_integrity.py app/services/test_video_asset_service.py app/services/test_generated_asset_boundary.py`: **56 passed in 10.91s**. This covers package creation and approval gating, acceptance identity/staleness/registration, screening integrity, asset registration, and generated-asset boundaries.
- A temporary intermediate run failed 13 tests when an attempt auto-registered absolute local `tmp_path` references as generated assets; the actual stack trace showed `VideoAssetService` does not accept arbitrary absolute local paths as `generated_output`. This was corrected by preserving the existing opt-in registration behavior: package creation auto-registers through an injected asset service, or creates the service for rooted `/outputs/` outputs only. The requested integrity contract is proved for durable matching registrations on `/outputs`; absolute local test/reference paths and remote URLs still require explicit usable registration through the asset service.
- Final passing assembly/delivery regression command: `.venv/bin/python -m pytest -q app/services/test_scene_assembly_service.py app/services/test_full_film_assembly_service.py tests/test_take_selection_delivery.py tests/test_assembly_routes.py app/services/test_production_acceptance_identity.py app/routes/test_production_acceptance_routes.py`: **27 passed in 8.25s**.
- The earlier broader assembly invocation that also included `tests/test_offline_production_delivery.py` remains **29 passed, 2 failed** and is diagnosed above; no newer passing rerun of that file is claimed.
- `.venv/bin/python -m pytest -q app/services/test_scene_assembly_service.py app/services/test_full_film_assembly_service.py tests/test_take_selection_delivery.py tests/test_offline_production_delivery.py tests/test_assembly_routes.py app/services/test_production_acceptance_identity.py app/routes/test_production_acceptance_routes.py`: **29 passed, 2 failed in 13.04s**. The failures are `test_existing_media_mode_never_calls_voice_provider` and `test_explicit_empty_dialogue_does_not_restore_scene_dialogue`; both raise `ValueError` from the current uncommitted `app/services/audio_pipeline_service.py` handoff validation for raw/empty dialogue without a frozen handoff. That file and the test file are outside this integrity change; the dialogue tests are not edited here.
- To identify whether those failures were already present at repository `HEAD`, archived the `HEAD` backend to a temporary directory, linked the same project virtualenv, and ran those exact two tests there: **2 passed in 4.49s**. Therefore they are not pre-existing at `HEAD`; they are attributable to the separate current working-tree audio-pipeline changes. No change was made to that code in this integrity stabilization.
- During the rerun, an overly strict temporary check of absolute local test outputs caused 13 package tests to fail; the actual output showed existing callers and fixtures use absolute `tmp_path` outputs. That check was removed, retaining the established absolute-local-path contract while keeping `/outputs` containment and non-empty checks. The final package/acceptance/screening/registration run above passes.
- `.venv/bin/python -m py_compile app/services/final_short_film_package_service.py app/services/production_acceptance_service.py app/models/production_acceptance.py app/services/screening_room_service.py app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py tests/test_checkpoint_4c_screening_room_integrity.py`: passed. This compile check and the clean targeted diff check were repeated after the final implementation/test adjustments.
- Targeted `git diff --check` for the integrity, screening, assembly, and related changed Python paths: passed. The milestone report is an untracked file in the shared checkout; it was appended in place to preserve its earlier evidence.

**Current disposition:** the scoped package/acceptance/registration/screening slice is verified by the passing tests above, including fail-closed behavior for an explicit nonexistent package ID, non-HTTP final references, invalid or missing asset registrations, changed registration identity/status, and local output-byte replacement. The complete relevant offline delivery suite is not green because its two failures are outside this slice and stem from separate current audio-pipeline changes; those failures were reproduced against the current tree and pass against `HEAD`. No task-related test failure remains; this roadmap item is ready to close narrowly, with independent audio failures and remote-output limits kept visible.

### Final re-verification from the resumed working tree — 2026-10-11

The commands below were run from `studio-backend`. These results supersede earlier test counts in this report where the commands differ.

- `.venv/bin/python -m pytest -q app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py tests/test_checkpoint_4c_screening_room_integrity.py`: **47 passed in 11.48s**.
- `.venv/bin/python -m pytest -q app/services/test_video_asset_service.py app/services/test_scene_assembly_service.py tests/test_offline_production_delivery.py tests/test_take_selection_delivery.py`: **24 passed, 2 failed in 13.03s**. Actual failures: `test_existing_media_mode_never_calls_voice_provider` raises `ValueError: Raw shot dialogue lines cannot bypass frozen handoff validation`; `test_explicit_empty_dialogue_does_not_restore_scene_dialogue` raises `ValueError: Narrative shot audio requires a frozen canonical dialogue handoff`. Both arise in the separate working-tree `app/services/audio_pipeline_service.py` handoff changes, not in the production-output integrity files. Neither failing assertion was weakened or edited.
- Re-ran those exact two tests against an archive of repository `HEAD` using the same virtualenv: **2 passed in 4.58s**. They are not pre-existing at `HEAD`; they are current-worktree failures in the unrelated audio-pipeline change. No edit was made to that file as part of this integrity task.
- `.venv/bin/python -m pytest -q app/services/test_video_asset_service.py app/services/test_scene_assembly_service.py tests/test_take_selection_delivery.py`: **22 passed in 9.50s**.
- `.venv/bin/python -m pytest -q app/services/test_full_film_assembly_service.py tests/test_assembly_routes.py tests/test_offline_production_delivery.py::test_local_audio_mixed_shot_sizes_export_approval_and_reopen`: **6 passed in 8.22s**.
- Combined integrity/regression command: `.venv/bin/python -m pytest -q app/services/test_final_short_film_package_service.py app/services/test_production_acceptance_service.py app/services/test_generated_asset_boundary.py app/services/test_video_asset_service.py tests/test_checkpoint_4c_screening_room_integrity.py app/services/test_scene_assembly_service.py app/services/test_full_film_assembly_service.py tests/test_take_selection_delivery.py tests/test_assembly_routes.py app/services/test_production_acceptance_identity.py app/routes/test_production_acceptance_routes.py`: **83 passed in 15.78s**.
- Python compilation of the changed package, acceptance, model, screening, and test files passed. Targeted `git diff --check` on `final_short_film_package_service.py`, `production_acceptance_service.py`, `test_final_short_film_package_service.py`, `test_production_acceptance_service.py`, and `test_checkpoint_4c_screening_room_integrity.py` passed. The checkpoint test's current structure was inspected directly; the earlier rejected replacement was not retried.

**Close decision:** production-output integrity is ready to close narrowly: the final combined task-focused run passes, exact package/project/output/available-registration matching is checked, and changed output identity or registration identity/status invalidates the acceptance gate. Do not describe the entire related offline-delivery set as green: the two named audio-handoff regressions remain open in the separate current working tree and must be resolved by that workstream. Remote HTTP(S) URL checks remain syntactic; remote liveness, byte identity, and playability are not verified.

**Verified behavior / remaining limits:** local `/outputs` file bytes are SHA-256 fingerprinted, and acceptance is stale if those bytes change even with preserved size/mtime. Matching asset identity/status and package, requested project, output URL, project scope, package fields, and lineage are included in acceptance identity; a valid asset must be durable and `available`/`analyzed`, with `source_type=generated_output`. Remote output contents and remote host availability are not fingerprinted or probed, and absolute local paths outside the canonical outputs root cannot pass the production acceptance reachability gate.

No live Runway calls, production delivery, authorization/lease-fencing changes, or reconciliation work were performed.

### Final repository review

- Reviewed the current implementation and test diffs for package creation, acceptance freshness/guarding, and screening approval against the working-tree versions; retained the task-related edits and preserved unrelated user work.
- Exact task-relevant tracked diff paths were checked with the targeted `git diff --check` above. The report is an existing untracked shared-worktree artifact, so Git does not include it in `git diff --check`; it was reviewed in place and earlier report content was preserved.
- Other unrelated working-tree files remain untouched and uncommitted.**Milestone status: production-output integrity is verified only for the bounded package/acceptance slice and the Runway Router image-registration slice documented here; the two separately owned offline audio regressions are explicitly not green.**


## Runway Router script-image reference authorization — 2026-10-11

### Gap closed

- The opt-in synchronous script-image path could forward shot reference URLs to Runway Router without proving that those exact references were selected for the current approved storyboard shot or remained eligible canonical references in the requested project.
- Added `authorize_runway_router_image_references` in `app/services/reference_validation.py`. It resolves the project and scene from durable storage, requires the current approved storyboard version and unique approved shot, compares the outbound URI sequence and reference IDs to that shot's persisted selection, then resolves every selected reference through the existing canonical project-scoped reference requirements. Stale approval, missing/duplicate context, candidate/rejected/cross-project references, altered URI/ID binding, and lookup errors fail closed.
- `build_image_render_assets` now authorizes the exact project/scene/shot and selected references before calling the image-provider seam, preventing provider dispatch on invalid context. The direct `submit_image_render` Runway Router branch repeats authorization at the provider boundary, so direct callers cannot bypass the workflow gate. Only the authorized reference records are sent to the Router and included in durable output provenance. Existing success registration checks remain in place.
- Regression coverage includes a valid current binding; rejected foreign, unapproved, missing, or changed reference bindings; direct provider bypass with zero Router submissions; no registration after workflow authorization failure; and persistence of the authorized references and generation context on successful generated-image registration.

### Verification

Commands run from `studio-backend`; all external provider calls were mocked:

- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py --tb=short`: **25 passed in 2.12s**.
- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py app/services/test_video_asset_service.py tests/test_runway_image_provider.py tests/test_runway_reference_projection.py tests/test_runway_router_projection_integration.py tests/test_generation_contract_remediation.py app/services/test_production_authorization_service.py app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py --tb=short`: **280 passed in 17.20s**.
- `.venv/bin/python -m py_compile app/services/reference_validation.py app/services/providers/image_provider.py app/services/script_parser.py tests/test_runway_router_image_script_parser.py app/services/video_asset_service.py`: passed.
- `git diff --check -- app/services/providers/image_provider.py app/services/script_parser.py app/services/video_asset_service.py`: passed. These implementation files already have substantial unrelated working-tree modifications; no broad diff normalization was attempted. Direct whitespace scans for the untracked reference-validation module, focused regression file, and this report found zero trailing-whitespace lines.
- An initial focused run before correcting the SQLite/project-state test fixture wiring was **20 passed, 5 failed**; failures were test setup resolving an empty persisted project scene, so the actual authorization gate correctly refused dispatch. The fixtures were corrected to seed both durable project and storyboard state. The rerun above passes all focused tests; no production behavior was weakened to make the suite pass.

### Limits

This verifies local authorization decisions against persisted Studio state and protects both the builder workflow and direct provider seam. It does not demonstrate live Runway behavior, remote URL availability/content, provider rendering success, or end-to-end readiness of the overall reference workflow or Production Integrity Gate. No live Runway calls, external upload, production render, or broader workflow changes were made. The separate roadmap items named above remain out of scope.

**Disposition:** the demonstrated input-authorization gap on the opt-in Runway Router script-image path is closed with mocked-provider regression evidence; broader reference assignment and final-video authorization remain separate work.

**Milestone status: production-output integrity is verified only for the bounded package/acceptance slice and the Runway Router image-registration/authorization slices documented here; the two separately owned offline audio regressions remain explicitly not green.**


## Runway Router image/reference provenance continuation — 2026-10-11

This section records the focused image-path continuation; it does not claim completion of durable image-asset registration or the full production-output roadmap.

- The opt-in `runway_router` image route now receives the canonical shot reference lists (preserving order and avoiding duplicate URIs), and a selected Router image provider does not fall through to ComfyUI or a synthetic preview when routed execution fails. Router success is accepted only when the reported task ID, output URL, and `runway_router_polled_task` association agree; otherwise the output is cleared and surfaced as failure. The image asset carries the Router execution identity for downstream inspection.
- Focused regressions cover reference order and task polling, missing/mismatched task/output identity, no ComfyUI or synthetic fallback, dry-run/failure handling, and reference-projection / frozen-contract behavior. All provider HTTP in these tests is mocked; no live Runway calls were made.

### Verification

Commands run from `studio-backend`:

- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py tests/test_runway_model_router.py tests/test_runway_router_projection_integration.py tests/test_runway_reference_projection.py tests/test_generation_contract_remediation.py app/services/test_model_registry_and_router.py`: **192 passed in 7.84s**.
- `.venv/bin/python -m pytest -q tests/test_runway_image_provider.py app/services/test_runway_direct_provider.py`: **49 passed in 4.92s**.
- `python -m py_compile app/services/providers/image_provider.py app/services/providers/runway_router_provider.py app/services/script_parser.py tests/test_runway_router_image_script_parser.py tests/test_runway_model_router.py tests/test_runway_router_projection_integration.py tests/test_runway_reference_projection.py tests/test_generation_contract_remediation.py app/services/test_model_registry_and_router.py`: passed.
- `git diff --check` passed for the task's tracked implementation changes (`image_provider.py`, `script_parser.py`); a whitespace scan found no trailing whitespace in the seven new task-scope provider/test files.

### Limits

This verifies Router image request/reference and polled-task/output association behavior, not durable canonical image-asset registration, remote output liveness/content, or a real provider render. Video Router output identity and projection tests remain separately covered by the focused suite; no production render, external upload, or delivery was performed.

**Disposition:** the task-scoped Router image/reference and task-output identity regressions pass. Keep durable image-asset registration and remote-output verification open; this continuation does not close the broader production-output integrity roadmap.

## Durable Runway Router image-asset registration continuation — 2026-10-11

### Confirmed gap and correction

- Before this continuation, a successful `runway_router` image response was projected into `image_render_assets` with `status=success` and a remote URL, but no call registered it in the durable `video_assets` table. The established `VideoAssetService.register_generated_output` contract already owns durable generated media; there was no need for another registry. Success also lacked a required project/execution boundary at the image builder, so the response could not truthfully establish exact association.
- The image-generation workflow passes its project and execution identifiers into `build_image_render_assets`. A selected Runway Router result now calls the existing generated-output service with that project, scene/shot/render identity, execution, exact polled task/output identity, reference list, and generation context. `VideoAssetService` verifies a real project, storage capability, exact output association, uniqueness of the Router task across existing generated assets, persisted reload, and matching metadata before returning a durable `available` asset.
- Missing project or execution provenance, conflicting provider-reported context, a missing/mismatched task/output association, a task already bound to another project/execution/shot/output, or storage/register/reload verification failure does not return a successful image record. The result is a failed image asset with cleared output URL/file path and a structured `durable_asset_registration_failed` error. Reference and generation-context provenance are immutable on idempotent re-registration.
- Creator authorization and storyboard approval rules were not changed or bypassed; Runway Router remains the only selected hosted provider on this route, and no fallback/reference substitution was added. The independent video-render-job/generated-asset flow is unchanged.

### Regression and verification evidence

All provider calls were mocked; no live Runway request, remote fetch, byte-integrity check, or media-playability probe was performed.

- `.venv/bin/python -m py_compile tests/test_runway_router_image_script_parser.py app/services/script_parser.py app/services/video_asset_service.py`: passed.
- Focused image path: `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py`: **15 passed in 1.03s** before the final idempotent-provenance tightening (includes success and SQLite persistence, missing project/execution, surfaced registration failure, mismatched provider context/task-output, and cross-project/execution task binding).
- Adjacent regression group after the first implementation: `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py app/services/test_video_asset_service.py tests/test_runway_image_provider.py tests/test_runway_reference_projection.py tests/test_runway_router_projection_integration.py tests/test_generation_contract_remediation.py app/services/test_production_authorization_service.py app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py`: **270 passed in 16.21s**. This verified image identity, canonical references, existing generated-asset behavior, video Runway projection, generation-contract remediation, authorization, and final-output registration/acceptance.
- Final focused/adjacent rerun and compilation after the last code/test edits are listed in the final verification subsection below; earlier counts do not cover later edits.
- `git diff --check` was clean for the implementation and focused test files at the first verification point; repeat after final changes is recorded below.

### Scope limits

- Durable registration establishes the Studio record and provenance only. It does **not** verify that the remote URL is still available, that downloaded bytes match the provider output, or that the image decodes/plays. No remote-output verification is claimed.
- This closes the durable-registration gap only for this opt-in synchronous Runway Router script-image path. It does not complete overall production-output integrity, assembly/final-delivery integrity, or the read-only Production Desk; no broad pipeline readiness claim is made.

### Final verification after provenance-idempotency tightening — 2026-10-11

- `.venv/bin/python -m py_compile tests/test_runway_router_image_script_parser.py app/services/script_parser.py app/services/video_asset_service.py`: **passed**.
- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py app/services/test_video_asset_service.py tests/test_runway_image_provider.py tests/test_runway_reference_projection.py tests/test_runway_router_projection_integration.py tests/test_generation_contract_remediation.py app/services/test_production_authorization_service.py app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py`: **271 passed in 15.65s** on the final rerun after all code edits.
- An initial compile attempt found an indentation error in the in-progress regression test, and the first new context-mismatch cases exposed that contradictory provider-reported project/execution values were not yet rejected. The test syntax was corrected and the builder gained an exact context comparison; both conditions are covered and pass in the final compile and test run. No unresolved task-specific failures remain.
- `git diff --check -- studio-backend/app/services/script_parser.py studio-backend/app/services/video_asset_service.py studio-backend/tests/test_runway_router_image_script_parser.py`: **passed**. The report is untracked in this checkout and thus is not included by Git's diff check; a direct trailing-whitespace scan of the report also passed.
- This final 271-test run includes the last context/ref provenance idempotency regression and was preceded in the same command by the successful `py_compile` check above. The task-relevant checks had no failures; the broader unrelated audio-handoff failures documented in the prior section are not covered by this image-specific run and are not claimed as passing.
- No live Runway calls, remote output validation, production delivery, UI work, new phase, or authorization/lease-fencing changes were performed.


### Final repository review

- Reviewed the current implementation and test diffs for package creation, acceptance freshness/guarding, and screening approval against the working-tree versions; retained the task-related edits and preserved unrelated user work.
- Exact task-relevant tracked diff paths were checked with the targeted `git diff --check` above. The report is an existing untracked shared-worktree artifact, so Git does not include it in `git diff --check`; it was reviewed in place and earlier report content was preserved.
- Other unrelated working-tree files remain untouched and uncommitted.**Milestone status: production-output integrity is verified only for the bounded package/acceptance slice and the Runway Router image-registration slice documented here; the two separately owned offline audio regressions are explicitly not green.**


## Runway Router script-image reference authorization — 2026-10-11

### Gap closed

- The opt-in synchronous script-image path could forward shot reference URLs to Runway Router without proving that those exact references were selected for the current approved storyboard shot or remained eligible canonical references in the requested project.
- Added `authorize_runway_router_image_references` in `app/services/reference_validation.py`. It resolves the project and scene from durable storage, requires the current approved storyboard version and unique approved shot, compares the outbound URI sequence and reference IDs to that shot's persisted selection, then resolves every selected reference through the existing canonical project-scoped reference requirements. Stale approval, missing/duplicate context, candidate/rejected/cross-project references, altered URI/ID binding, and lookup errors fail closed.
- `build_image_render_assets` now authorizes the exact project/scene/shot and selected references before calling the image-provider seam, preventing provider dispatch on invalid context. The direct `submit_image_render` Runway Router branch repeats authorization at the provider boundary, so direct callers cannot bypass the workflow gate. Only the authorized reference records are sent to the Router and included in durable output provenance. Existing success registration checks remain in place.
- Regression coverage includes a valid current binding; rejected foreign, unapproved, missing, or changed reference bindings; direct provider bypass with zero Router submissions; no registration after workflow authorization failure; and persistence of the authorized references and generation context on successful generated-image registration.

### Verification

Commands run from `studio-backend`; all external provider calls were mocked:

- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py --tb=short`: **25 passed in 2.12s**.
- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py app/services/test_video_asset_service.py tests/test_runway_image_provider.py tests/test_runway_reference_projection.py tests/test_runway_router_projection_integration.py tests/test_generation_contract_remediation.py app/services/test_production_authorization_service.py app/services/test_production_acceptance_service.py app/services/test_final_short_film_package_service.py app/services/test_generated_asset_boundary.py --tb=short`: **280 passed in 17.20s**.
- `.venv/bin/python -m py_compile app/services/reference_validation.py app/services/providers/image_provider.py app/services/script_parser.py tests/test_runway_router_image_script_parser.py app/services/video_asset_service.py`: passed.
- `git diff --check -- app/services/providers/image_provider.py app/services/script_parser.py app/services/video_asset_service.py`: passed. These implementation files already have substantial unrelated working-tree modifications; no broad diff normalization was attempted. Direct whitespace scans for the untracked reference-validation module, focused regression file, and this report found zero trailing-whitespace lines.
- An initial focused run before correcting the SQLite/project-state test fixture wiring was **20 passed, 5 failed**; failures were test setup resolving an empty persisted project scene, so the actual authorization gate correctly refused dispatch. The fixtures were corrected to seed both durable project and storyboard state. The rerun above passes all focused tests; no production behavior was weakened to make the suite pass.

### Limits

This verifies local authorization decisions against persisted Studio state and protects both the builder workflow and direct provider seam. It does not demonstrate live Runway behavior, remote URL availability/content, provider rendering success, or end-to-end readiness of the overall reference workflow or Production Integrity Gate. No live Runway calls, external upload, production render, or broader workflow changes were made. The separate roadmap items named above remain out of scope.

**Disposition:** the demonstrated input-authorization gap on the opt-in Runway Router script-image path is closed with mocked-provider regression evidence; broader reference assignment and final-video authorization remain separate work.

**Milestone status: production-output integrity is verified only for the bounded package/acceptance slice and the Runway Router image-registration/authorization slices documented here; the two separately owned offline audio regressions remain explicitly not green.**


## Runway Router final video-reference revalidation — 2026-10-12

### Gap closed and enforcement boundary

- Ordinary authorized frozen video references were previously checked for integrity against the prepared payload and replayed through the Runway projection, but were not universally resolved again against live Studio reference and creator-approval records at the last provider boundary.
- `validate_frozen_reference_binding_current` now uses the existing `resolve_scene_reference_requirements` canonical resolver immediately before Router submission. It compares the ordered current project/scene reference identities and mappings (reference ID, URI, project/target scope, role/category, kind, canonical/approval state, and source kind) with the frozen binding and generation contract. The selected setting must also still match the creator authorization record; for Scene 002, the current approved Scene Direction setting decision must still name the same explicit reference.
- In `RunwayRouterAdapter._submit_job_after_authorization`, the validation runs in `_run_sync` immediately before both the advisory dry-run and the live video request, after durable render/owner approval rechecks. The exact `referenceImages` in the prepared outbound body are compared to the authorized projected references before the request helper is called. Missing storage, missing current state, identity drift, revocation/deletion, mismatched authorization, or mismatched projected wire references fail before provider contact. `submit_job` accepts the already resolved reference storage from `RenderService` and passes it to this boundary; direct adapter use continues to resolve durable storage through the established authority service.
- The opt-in script-image authorization boundary was not changed. Scene 002's contract-only execution remains on its separately sealed execution and byte-verification path; the generic Scene Direction decision check preserves its existing specialized selection semantics and does not replace it with a generic registry choice.
- Task-scope files: `app/services/reference_validation.py` (canonical current-state validation); `app/adapters/__init__.py` and `app/services/render.py` (final-boundary integration and storage handoff); `app/services/test_reference_validation.py` and `tests/test_runway_router_projection_integration.py` (focused regressions); this milestone report. Existing unrelated working-tree edits in the adapter and render service were preserved.
- Focused regressions prove unchanged current binding and valid authorized Router video succeed; post-freeze revocation, deletion, URI/mapping changes, cross-project/role/target mismatches and stale projected selection fail with zero provider calls; current Scene 002 selected-setting authority still resolves; and revocation between advisory estimate and live submission prevents the live call.

### Verification

Commands run from `studio-backend`; Runway HTTP remained mocked:

- `.venv/bin/python -m pytest -q app/services/test_reference_validation.py tests/test_runway_router_projection_integration.py app/services/test_scene002_setting_reference_lifecycle.py tests/test_runway_reference_projection.py tests/test_generation_contract_remediation.py app/services/test_production_authorization_service.py --tb=short`: **222 passed in 13.03s**.
- `.venv/bin/python -m pytest -q tests/test_runway_router_image_script_parser.py --tb=short`: **25 passed in 2.23s** (opt-in script-image regression remains green).
- `.venv/bin/python -m py_compile app/services/reference_validation.py app/adapters/__init__.py app/services/render.py app/services/test_reference_validation.py tests/test_runway_router_projection_integration.py`: passed.
- `git diff --check -- app/adapters/__init__.py app/services/render.py`: passed. A direct trailing-whitespace scan of the new reference-validation module, focused regression files, and report is clean.

An earlier adjacent-suite run caught interface fixture incompatibilities after threading reference storage through `RunwayRouterAdapter.submit_job`; the adapter call now preserves the old no-keyword path when no reference storage is supplied, while `RenderService` passes it when available. The full adjacent suite above passes after that correction.

### Limits

This validates current local Studio records and the exact pre-request projected URI/role list under mocked provider transport. It does not demonstrate a live Runway request, remote image URL availability or content, provider rendering, or overall production readiness. No live Runway call, external upload, or production action was performed. The image authorization implementation and all other roadmap work remain separate.

**Disposition:** the identified last-boundary gap for ordinary frozen Runway video references is closed with local-state and mocked-provider regression evidence; no live provider behavior is claimed.

**Milestone status: bounded Runway video reference revalidation, image reference authorization, and previously documented delivery slices are locally tested; broader production readiness and the two separately owned offline audio regressions remain open.**
