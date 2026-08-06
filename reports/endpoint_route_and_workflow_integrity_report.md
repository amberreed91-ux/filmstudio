# Endpoint, Route, and Production Workflow Integrity Report

Date: 2026-08-06

Verification base: `f41e1605`

Provider classification: **SIMULATED PROVIDER VERIFICATION** for render output

Final verdict: **VERIFIED COMPLETE**

## 1. Executive Summary

The endpoint, route, persistence, frontend-contract, and canonical production-workflow repair plan is verified complete for the applicable repository scope. The current runtime exposes 589 unique OpenAPI HTTP operations across 527 paths with no normalized method/path duplicate. The 14 canonical handoffs share durable server-owned records from approved Storyboard Blueprint through Previs, rendering, Screening, Editorial, Film Cut, revision, and explicit memory save.

Checkpoint 8 introduced no product feature or regression repair. A new isolated reproduction created project `checkpoint7-164ba1531c`, run `workflow-b9de9b744e6d`, and newly generated artifact identifiers. It completed at `revision_completed`, retained all 15 semantic transitions after backend restart, matched SQLite, and recorded 114 passed checks with no failures or skips. The render provider was explicitly simulated and `paid_provider_calls` is false for that verifier run.

An independent browser seed run created project `checkpoint7-226b67f779` and run `workflow-76e30cbfc425`. A freshly restarted frontend and backend restored that exact run, Blueprint version, state, and 15 transitions through live canonical APIs. Refresh and explicit refresh remained stable; a new unknown project produced a visible structured error.

## 2. Canonical Naming Findings

- **Previs** is canonical. “Precise” is not an implemented feature, route, model, service, table, or UI surface.
- **Screening Room** is the canonical review surface.
- **The Theater** is a presentation component/subtitle within Screening Room.
- **Theatre** is not a backend subsystem and no compatibility route was invented.
- **Storyboard Blueprint** and versioned Storyboard shots are canonical; Storyboard Wall is a compatibility projection.
- **Film Cut** and **Timeline** are versioned SQLite-backed artifacts.

## 3. Route Inventory

The clean runtime OpenAPI snapshot contains 589 unique HTTP operations across 527 paths. The focused route suite verifies that operations are mounted once, static routes are not shadowed by dynamic routes, runtime operations match OpenAPI, and the repaired final-export ordering remains stable.

The 16 canonical production-thread routes are mounted under `/api/f51/studio`. The live browser used the same relative `/api/f51/studio/...` paths as the frontend client, and all five valid production-thread reads observed in the final browser session returned 200. No duplicate API prefix, duplicate canonical operation, route-order collision, or canonical 404 was found.

Raw route evidence: `checkpoint_8/clean_state/reproduction/openapi/runtime_openapi.json` and `runtime_http/route_inventory.json`.

## 4. Defects Found

Across Checkpoints 2, 3, 4A–4D, and the live Checkpoint 6 frontend pass, 45 explicit defects/findings were documented and repaired:

- 6 route-registration, prefix, ordering, and client-base defects;
- 8 backend ownership, transaction, persistence, error, and contract defects;
- 7 Storyboard integrity findings;
- 8 Previs lifecycle findings;
- 6 Screening/media/approval findings;
- 6 Editorial/Film Cut/version findings;
- 4 live frontend polling, chart, optional-resource, and playback-path defects.

Checkpoint 5 added the missing canonical cross-stage orchestration and durable transition model. Checkpoint 7 added independent verification and evidence controls. Checkpoint 8 found no new product regression requiring repair.

## 5. Storyboard Verification

Storyboard create, load, update, versioning, shot lifecycle, continuity review, approval, render-contract handoff, stable identifiers, and persistence pass. Unknown scenes do not fabricate fallback records. Approved, historical, locked, superseded, and stale versions reject invalid mutation or rendering. The focused suite includes the live route contract and stale-version rejection tests.

## 6. Previs or Precise Verification

Previs generation, list/read, status refresh, approval, cancel, retry, idempotency, approved-output protection, production-package creation, Blueprint provenance, and restart persistence pass. Provider failure remains terminal and visible; provider-complete without media is demoted to failure. No real “Precise” feature exists, so that clause is not applicable.

## 7. Theatre, Theater, and Screening Room Verification

Screening Room manifest, synchronization, scoped playback, media availability, range responses, approval history, exact workflow selection, and persistence pass. Missing and unsafe media do not appear playable. The frontend restored the exact terminal canonical run in Screening after refresh. “The Theater” remains presentation-only; “Theatre” remains unimplemented by design.

## 8. Frontend Contract Verification

The frontend canonical client, shared workflow controller, Previs and Screening surfaces, Production Board, recovery polling, route registry, and API URL construction match backend contracts. The focused frontend run passed 100 tests; the verifier's narrower independent set passed 45 tests; standalone TypeScript checking and the production build passed.

Errors are visible, loading and polling terminate, terminal state is server-restored, mutations use single-flight guards, identifiers are rejected before malformed requests, and filesystem paths cannot become browser playback URLs.

## 9. End-to-End Workflow Thread Integrity

The 14 audited handoffs are:

`Approved Blueprint → workflow → Previs → approved Previs → production package → render jobs → Screening → approved Screening → Editorial analysis → confirmed application → Film Cut version → approved cut → revision/revised render → explicit memory save`

The clean trace preserves Project, Script, Scene, Sequence, Beat, Blueprint, Blueprint version, Storyboard shot, Previs image, package, render request/job/provider job, asset, clip, Screening output, approval, analysis, decision, application, Film Cut, timeline revision, original job, clip revision, revised job, continuity, and memory identifiers.

Creative intent and continuity are snapshotted from the approved source, included in the production package and initial provider request, and preserved in the revision request. Version and approval provenance remain explicit at every boundary. Frontend reconstruction is not a source of truth.

## 10. Persistence Verification

The verifier compares the terminal HTTP run with SQLite `canonical_workflow_runs` and 15 `canonical_workflow_transitions`. It then stops and restarts the backend and reloads the same run/status/transition count. The browser seed run independently repeated the same persistence sequence and then restored it through a freshly started frontend.

Film Cut state, Timeline revisions, Storyboard versions, Previs records/packages, render jobs, Screening outputs, Editorial analysis/application, revisions, continuity snapshot, and explicit cinematic memory are durable. The disposable browser database was deleted after verification; repository user data was preserved.

## 11. Error Handling Verification

All ten required negative cases pass; see `checkpoint_8/negative_tests/required_negative_matrix.md`.

- Unknown project and unknown shot return deliberate structured not-found errors.
- Cross-project scene and artifact references fail without mutation.
- Stale Storyboard and Film Cut versions return conflict errors.
- Invalid or unconfirmed approvals are rejected.
- Missing media remains unavailable and returns a playback error.
- Provider failure cannot appear as Screening or memory success.
- Duplicate render and repeated Editorial application replay idempotently with zero new jobs, applications, or transitions.

Storage failures are not converted into empty success, and provider failures are not presented as completion.

## 12. Security Findings

- No secrets, tokens, private keys, credentials, or filesystem media paths are introduced by the Checkpoint 8 evidence/report scope.
- Project-scoped media routes hide signed/original provider URLs and reject unsafe local paths.
- The active runtime rate limiter rejected an over-broad first browser attempt with 429 rather than being disabled. The failed attempt is retained.
- Many creative production endpoints remain unauthenticated in OpenAPI, as documented in Checkpoint 1. This is an existing deployment-hardening risk outside the endpoint/workflow integrity repair scope.
- Screening currently auto-invokes configured emotion analysis on page load. The first browser attempt made two real external Qwen advisory-LLM calls. This did not submit a render or mutate canonical workflow state, but it is a cost/side-effect risk. The final browser pass transparently intercepted only that peripheral endpoint; all canonical workflow requests remained live.

## 13. Test Results

| Verification | Result |
| --- | --- |
| Clean independent reproduction plus managed checks | 114 passed, 0 failed, 0 skipped, exit 0 |
| Expanded backend route/contract/persistence/workflow/state suite | 76 passed, 0 failed, 0 skipped |
| Expanded frontend workflow/API/route suite | 100 passed, 0 failed, 0 skipped |
| Standalone TypeScript project check | passed, no diagnostics |
| Frontend production build | passed |
| Final browser verification | 6 assertions passed, exit 0 |
| Browser seed reproduction | 111 passed, 0 failed, 0 skipped, exit 0 |

The totals above are intentionally not summed because the suites overlap. Machine-readable command/test records are under `checkpoint_8/test_logs` and the two reproduction directories.

## 14. Runtime Verification

The main clean trace recorded 102 live HTTP requests: 96 expected 200 responses, five deliberate 422 approval-boundary responses, and one deliberate 409 ownership response. It created all state through public APIs, used real SQLite persistence, restarted the backend, and reloaded the same terminal state.

The final browser session recorded 125 API responses: 97 successful reads/actions, 26 deliberate or optional 404s, and two media redirects. Valid canonical production-thread requests were all 200; there were no 429 responses or uncaught page errors during valid-project/refresh checks. Optional absent poster/final-package/composition records and the deliberate unknown project account for the 404s.

## 15. Files Changed

Checkpoint 8 changes only verification/report artifacts:

- `reports/endpoint_route_and_workflow_integrity_report.md`;
- `reports/evidence/endpoint_workflow_integrity/evidence_manifest.md`;
- `reports/evidence/endpoint_workflow_integrity/checkpoint_8/**`.

No backend or frontend product source, production data, test assertion, provider configuration, or runtime bypass was changed. The pre-existing dirty worktree remains unstaged and is recorded in `checkpoint_8/before_verification/worktree_baseline.md`.

## 16. Remaining Risks

- A real hosted render was not purchased or submitted; provider output is simulated by design. Provider lifecycle/error contracts are verified, not third-party account capacity.
- Screening's automatic external emotion-analysis call can create advisory-provider cost/side effects on page load; it should be made explicit or cache-aware in a separately authorized product change.
- Optional poster, final-package, and scene-composition resources were absent in the disposable project and correctly rendered as empty states.
- Broad route authentication remains deployment-dependent and was not expanded in this repair plan.
- The repository retains substantial user-owned unstaged work/data changes unrelated to these checkpoints.

None of these risks contradicts the applicable canonical endpoint/workflow integrity result.

## 17. Exit-Criteria Evidence Table

| # | Criterion | Result | Primary evidence |
| ---: | --- | --- | --- |
| 1 | Every relevant canonical router mounted | PASS | Runtime OpenAPI; route-registration suite |
| 2 | Runtime routes match inventory | PASS | 589 unique operations; runtime/OpenAPI equality test |
| 3 | Frontend actions call valid routes | PASS | Frontend tests and browser network trace |
| 4 | HTTP methods correct | PASS | OpenAPI plus client contract tests |
| 5 | Request schemas match | PASS | Route/API tests and 102-request clean trace |
| 6 | Response schemas match | PASS | Pydantic route tests and frontend parsing tests |
| 7 | Storyboard CRUD/persistence | PASS | CP4A and focused backend suite |
| 8 | Previs lifecycle/persistence | PASS | CP4B and clean trace |
| 9 | Real Precise feature | N/A | Repository proves no such feature exists |
| 10 | Screening routes work | PASS | CP4C, browser, clean trace |
| 11 | Playback works | PASS | Range/missing-media route tests; Screening browser surface |
| 12 | Film Cut persists | PASS | CP4D; restart trace |
| 13 | Timeline persists | PASS | CP4D version/reload tests |
| 14 | Invalid identifiers deliberate | PASS | Required negative matrix |
| 15 | Missing records not found | PASS | Unknown project/shot and missing-media evidence |
| 16 | Provider failures not success | PASS | Canonical failure/recovery test |
| 17 | Storage failures not empty success | PASS | CP3 persistence-error tests |
| 18 | Frontend errors visible | PASS | Unknown-project browser screenshot; CP6 provider screenshot |
| 19 | No infinite polling | PASS | Bounded hook tests and terminal browser state |
| 20 | No duplicate route | PASS | Route uniqueness test |
| 21 | No route-order collision | PASS | Static/dynamic route test |
| 22 | No duplicate API prefix | PASS | URL builder/client tests and network trace |
| 23 | Regression tests pass | PASS | Backend 76; frontend 100 |
| 24 | Frontend build | PASS | Managed build command record |
| 25 | Focused backend tests | PASS | `backend_focused.xml` |
| 26 | Focused frontend tests | PASS | `frontend_focused.xml` |
| 27 | Runtime smoke tests | PASS | Health/OpenAPI/live HTTP |
| 28 | Seeded end-to-end workflow | PASS | Clean and browser-seed verifier results |
| 29 | Fixed defects have coverage | PASS | Checkpoint 2–7 reports/test audit |
| 30 | Stable identifiers across stages | PASS | Persistence export and result JSON |
| 31 | Creative intent survives handoffs | PASS | Clean run artifacts/provider evidence |
| 32 | Continuity survives handoffs | PASS | Package, render, and revision assertions |
| 33 | Version provenance preserved | PASS | Blueprint/package/Film Cut/revision IDs |
| 34 | State transitions validated | PASS | 15 ordered durable transitions; invalid-state tests |
| 35 | Approval boundaries enforced | PASS | Five deliberate 422s and focused tests |
| 36 | Retry behavior safe | PASS | Provider failure/retry test |
| 37 | Duplicate operations prevented | PASS | Live zero-delta idempotency evidence |
| 38 | Data survives refresh | PASS | Browser final session |
| 39 | Data survives restart | PASS | Both reproductions |
| 40 | Final output traceable upstream | PASS | Screening/Film Cut/revision provenance; final-package compatibility tests |
| 41 | Frontend/backend canonical records | PASS | Exact browser run/Blueprint/state restoration |
| 42 | Memory uses approved production state | PASS | Explicit memory record after approvals |
| 43 | Continuity uses approved production state | PASS | Approved Blueprint continuity snapshot |
| 44 | No frontend reconstruction dependency | PASS | Backend restart and browser cold reload |
| 45 | External blockers proven | PASS | Real hosted render capacity isolated from simulated verification |

## 18. Evidence Manifest Reference

Primary manifest: `reports/evidence/endpoint_workflow_integrity/evidence_manifest.md`

Checkpoint 8 evidence root: `reports/evidence/endpoint_workflow_integrity/checkpoint_8/`

Hash index: `reports/evidence/endpoint_workflow_integrity/checkpoint_8/hashes/checkpoint_8_sha256.txt`

## 19. Final Verdict

**VERIFIED COMPLETE**

Applicable canonical routes, contracts, persistence, frontend behavior, negative cases, state transitions, approvals, retries, idempotency, provenance, browser refresh, backend restart, tests, type checking, and build are evidence-backed. No contradiction remains unresolved, and no Checkpoint 8 product-code repair was required.
