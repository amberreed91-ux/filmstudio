# Checkpoint 6 — Frontend Workflow Integration

Status: **PASS**

Date: 2026-08-06

## Outcome

The real Previs and Screening interfaces now use the canonical production-thread records introduced in Checkpoint 5. The running application completed and restored this exact sequence:

`approved Blueprint → Previs → creator approval → production package → render → Screening → creator approval → Editorial → Film Cut → revision → explicit memory save`

The verified run was `workflow-037e4b501229` for project `project-thread`, scene `scene_001`, and approved Blueprint version `sbv_b152366b8476`. A refresh restored terminal state `revision_completed`, the explicit memory confirmation, stable artifact identifiers, and all 17 persisted transitions.

The successful render walkthrough was **SIMULATED PROVIDER VERIFICATION** using the explicit local setting `APP_ENV=local RENDER_PROVIDER_TEST_MODE=mock_success`; it did not submit a paid render. Before enabling that setting, the configured live provider returned 502 because the account had no credits. The UI displayed the failure, did not claim success, and recovered through the same durable run.

## Repairs made

### Canonical client and state

- Added a typed frontend client for every canonical production-thread route with exact payloads and identifier guards.
- Added project-and-scene run discovery so refresh can restore server state without a browser-only run ID.
- Added one shared workflow hook with request cancellation, single-flight mutations, cache refresh after mutations, and bounded canonical polling.
- Polling stops at terminal/error states or after ten minutes and resumes only submitted work. It never creates a replacement job while polling.
- Only a run sourced from the current approved Blueprint version is editable. Prior runs remain visible as retained history.

### Previs and Screening integration

- Added one shared canonical workflow panel to Previs and Screening.
- Made URL `project_id`, `scene`, and `shot` context authoritative over persisted selection.
- Preserved context in room-to-room links and fixed the Screening route to `/studio/screening-room`.
- Cleared project-, scene-, and shot-scoped UI state when their identifiers change.
- Restored completed render outputs in Screening through the canonical screening registry.
- Added visible loading, failure, pending, approved, stale/superseded, polling, and terminal states.
- Kept creator approval and explicit memory-save confirmation as non-blocking authority boundaries.
- Replaced open-ended room polling with bounded, status-aware polling.
- Rejected local filesystem paths before they can become browser playback URLs.

### Live defects found and repaired

1. A submitted revision render was being submitted again when the frontend polled it. The service now persists `revision_render_submitted`, polls the same provider job ID, and completes without duplicate creation.
2. A one-scene emotional curve divided by zero and emitted `NaN` SVG coordinates. The chart now uses a safe denominator.
3. Optional poster, final-package, and scene-composition reads were logged as hard errors and repeated across effects. Optional 404s now resolve quietly to empty UI states, and active composition is selected from one project cache.
4. A render could expose a host filesystem path to browser media elements. Browser playback now accepts only safe web-facing routes or URLs.

## Priority action trace

| User action | Frontend path | Canonical request | Persistence and visible result |
| --- | --- | --- | --- |
| Open Previs deep link | URL context → scene extraction → workflow hook | `GET /projects/{project}/production-threads?scene_id={scene}` | Correct project/scene/shot shown; no stale run injected |
| Start thread | Panel handler → `beginWorkflow` | `POST /projects/{project}/scenes/{scene}/production-thread` | Run ID stored by backend; run and approved source visible |
| Generate Previs | Confirmed panel action → mutation lock | `POST /production-threads/{run}/previs/generate` | First 502 remained visible; later 200 created the Previs artifact |
| Approve Previs | Creator confirmation → mutation | `POST /production-threads/{run}/previs/approve` | Approval persisted and next action unlocked |
| Package | Panel mutation | `POST /production-threads/{run}/production-package` | Stable package `previs_pkg_aeb907bf7371` persisted |
| Render | Confirmed simulated-provider action | `POST /production-threads/{run}/renders` | One job created; canonical GET polling reached complete |
| Enter Screening | Context-preserving link → Screening manifest | `POST /production-threads/{run}/screening/sync` | Completed render appeared as Scene 1 / rendered / takes |
| Approve Screening | Creator confirmation → mutation | `POST /production-threads/{run}/screening/approve` | Approval persisted; Editorial unlocked |
| Analyze/apply Editorial | Panel actions | `POST .../editorial/analyze`, then `/editorial/decide` | Two advisory decisions appeared; selected decision persisted |
| Update/approve Film Cut | Panel actions with confirmations | `POST .../film-cut/update`, then `/film-cut/approve` | Approved Film Cut v2 visible |
| Submit revision | Exact prompt/reason/changed fields/original job | `POST .../revision`, then `/revision/render` | Submitted state persisted; same job polled to complete |
| Save memory | Explicit creator confirmation only | `POST .../memory` | “Approved memory saved explicitly” persisted and restored |
| Refresh | Hook reload by project + scene | Canonical list and run GETs | Same run, terminal status, identifiers, and 17 transitions restored |

The response/status capture is in [browser_request_trace.md](../evidence/endpoint_workflow_integrity/checkpoint_6/browser_request_trace.md).

## Required verification matrix

| # | Requirement | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Correct project remains selected | PASS | URL-first resolution and live `project-thread` walkthrough |
| 2 | Correct scene remains selected | PASS | Exact `scene_001` in both rooms and restored run |
| 3 | Correct shot remains selected | PASS | `shot=1` survived navigation and refresh |
| 4 | Navigation preserves context | PASS | Previs-to-Screening deep link retained all identifiers |
| 5 | Deep links restore context | PASS | Screenshot 01 and live direct navigation |
| 6 | Refresh reloads canonical server state | PASS | Screenshots 07/08; same run and 17 transitions |
| 7 | Returning to a prior room shows downstream changes | PASS | Screening showed approved Film Cut, revision, and memory state |
| 8 | Project switching clears old state | PASS | Live switch to `I was reborn` showed no prior canonical run |
| 9 | Scene switching clears old state | PASS | Effects reset run, media, selection, and local scene state by ID |
| 10 | Shot switching clears old state | PASS | Screening resets playback/take state and updates URL shot context |
| 11 | Loading states start and stop | PASS | Mutation, loading, and polling indicators terminate in UI/tests |
| 12 | Errors are visible | PASS | Screenshot 03 captures provider failure |
| 13 | Failed requests do not display success | PASS | 502 left durable failure and no success state |
| 14 | Polling uses canonical endpoints | PASS | Run GET and revision-render requests captured |
| 15 | Polling stops at terminal states | PASS | Final refresh remained stable at `revision_completed` |
| 16 | Polling does not duplicate jobs | PASS | Backend test and live same revision job ID |
| 17 | Completed renders appear in Screening | PASS | Screenshots 04/05 and live Scene 1 rendered state |
| 18 | Revisions return to correct review stage | PASS | UI states “Revision complete and returned to Screening review” |
| 19 | Approved and stale versions distinguishable | PASS | Approved-source/superseded-source visual labels and component test |
| 20 | Superseded versions cannot be edited | PASS | Hook selects only the current approved version; retained runs are read-only |
| 21 | Caches invalidate after mutations | PASS | Every mutation reloads the canonical run before releasing its lock |
| 22 | Browser history avoids stale project state | PASS | Live switch then Back restored URL-matching `project-thread` run |
| 23 | No duplicate API prefixes | PASS | URL builder tests and captured `/api/f51/studio/...` requests |
| 24 | No undefined identifiers | PASS | Client rejects blank/undefined/null IDs before fetch |
| 25 | No filesystem playback paths | PASS | `browserPlaybackUrl` guards and 14 media tests |

## Browser and network verification

- Pages exercised: Previs and Screening Room.
- Actions exercised: all canonical mutations from run creation through explicit memory save.
- Request methods, URLs, statuses, and durable IDs: captured in `browser_request_trace.md`.
- Visible results: captured across screenshots 01–08.
- Refresh: restored the same run and terminal state.
- Project/history check: navigating to `project_5907c60cddbc` cleared the former workflow; Browser Back restored only the URL-matching `project-thread` run.
- Fresh console after repair: no React errors, unhandled rejections, parsing failures, CORS errors, blank failure screens, or hard API error logs.
- Expected optional 404s: poster, final package, and scene composition had not been generated. They render deliberate empty states and no longer create console errors.
- No unexpected 405, 422, or 500 responses were observed on the canonical path.
- The 502 was an intentional real failure-path observation from the uncredited provider and is retained as failure evidence, not counted as a successful provider verification.

## Automated verification

All commands exited 0.

| Scope | Command | Result |
| --- | --- | --- |
| Frontend full suite | `npm test -- --run` | 73 files, 664 tests passed |
| Frontend production build | `npm run build` | Passed; one existing large Three.js chunk warning |
| Canonical backend focus | `.venv/bin/python -m pytest tests/test_checkpoint_5_canonical_workflow_thread.py tests/test_checkpoint_5_canonical_workflow_routes.py` | 5 passed |

Focused frontend coverage includes exact endpoint/payload construction, missing-ID rejection, URL context preservation, canonical scene extraction, status-to-action mapping, safe playback URLs, optional-resource reads, and shared panel rendering.

## Evidence inventory

- `reports/evidence/endpoint_workflow_integrity/checkpoint_6/worktree_baseline.txt` — dirty-worktree boundary captured before Checkpoint 6.
- `reports/evidence/endpoint_workflow_integrity/checkpoint_6/browser_request_trace.md` — canonical request/status and refresh/history trace.
- `screenshots/01_previs_deep_link_ready.png` — exact Previs context before thread creation.
- `screenshots/02_thread_started.png` — canonical run started.
- `screenshots/03_provider_error_visible.png` — visible provider failure and no false success.
- `screenshots/04_render_completed.png` — bounded polling reached render completion.
- `screenshots/05_screening_context_restored.png` — Screening received the exact context and render.
- `screenshots/06_revision_complete_memory_saved.png` — revision completion and explicit memory save.
- `screenshots/07_refresh_restored_durable_state.png` — state restored after refresh.
- `08_clean_refresh_restored.png` — final clean-console reload after optional-resource and chart repairs.

## Exit criteria

1. Priority workflows verified in the running frontend — **PASS**.
2. Frontend and backend use the same canonical records — **PASS**.
3. Refresh preserves state — **PASS**.
4. Project, scene, and shot switching do not leak state — **PASS**.
5. Polling terminates correctly — **PASS**.
6. Errors are visible — **PASS**.
7. Network evidence exists — **PASS**.
8. Browser console evidence exists — **PASS**.
9. Focused frontend tests and production build pass — **PASS**.
10. Focused checkpoint commit — **prepared as part of this checkpoint**.

Checkpoint 7 was not started.
