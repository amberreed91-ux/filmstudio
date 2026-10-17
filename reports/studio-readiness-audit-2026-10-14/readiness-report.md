# Consolidated AI Film Studio Readiness Audit (2026-10-14)

Branch `backend-expansion-dependency-slicing` @ `86c1b58e`. Read-only audit: no source edits, no production mutations, no provider calls, nothing staged/committed. One temporary probe test was created for diagnosis and deleted immediately after (verified absent via `git status`).

## Baseline

- Repo root `/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project`; reports present for Desk, Integrity Engine, Reference Space, refinement.
- Rooms registered (`routes.tsx`): Gate `/`, Lobby `/studio`, Overview, Page, Universe, Board, **Desk `/studio/production-desk`, Engine `/studio/integrity`, Space `/studio/reference-space`**, Theater, Vault, DevTools + others. All three new rooms primary placement with breadcrumbs/contextual links.
- Massive pre-existing uncommitted backend modifications (e.g. `reference_asset_service.py` +805 lines, `storage.py`, adapters, render/validation); no backend file changed by any implementation phase.

## Re-verified claims (this audit, exit statuses preserved)

- `npx tsc -b` → 0. Full vitest → **111 files / 888 tests passed**. `npm run build` → 0. `eslint` on touched files → 0.
- Full backend suite: **4,777 tests collected** (not ~1,700 as prior reports assumed); full run needs ~1hr+ (timed out at 600s at ~22%, background run still in progress). Coverage claim corrected: full-suite pass is **unestablished**.

## Findings

**F1 — Confirmed working.** Engine and Desk are strictly read-only (zero `method: 'POST'` in either page). Space mutates only through 6 pre-existing authoritative endpoints (library upload/add/approve/remove, look approve/revise), all explicit user actions. No parallel approval system, no auto-promotion path in frontend code.

**F2 — Confirmed working.** Screening approval enforces the acceptance guard fail-closed (`screening_room_service.py:428-455`: unallowed guard → `StateError`). Routes call services, never storage/adapters directly (sampled acceptance, reference-assets, character-looks; zero `RunwayAdapter` references in routes). `get_character` is project-scoped (`WHERE id=? AND project_id=?`).

**F3 — Confirmed working.** Project context consistent (`useProjectRouteContext` + `?project_id=`) across all three rooms. Canonical changes remain server-side (route rejects `canonical:true`; look approve requires matching `expected_profile_revision`).

**F4 — CONFIRMED DEFECT (high). Reference write paths broken at DB layer.** `confirm()` (`reference_asset_service.py:356`) and `register_uploaded_reference()` build rows without `created_at`; both storage writers INSERT explicit NULL into `reference_assets.created_at NOT NULL` → `IntegrityError`/falsy write → user-facing 400 ("could not be created" / "could not be registered"). This breaks Reference Space's upload AND URL-add workflows and the propose→confirm flow in production, not just in tests. Evidence: 5 failing tests reproduced (`test_reference_asset_routes` ×3, `test_reference_assets_persistence` ×2); direct temp-DB repro raises `IntegrityError: NOT NULL constraint failed: reference_assets.created_at`; migrations run correctly (13 columns present) so schema is not the issue — the missing server-side default is. Smallest safe fix (not implemented per audit boundary): default `created_at` in the two service constructors.

**F5 — CONFIRMED DEFECT (medium). Render gating drift.** `submit_job` now fail-closes on unresolvable canonical setting (`reference_validation.py` → "Generation blocked … no resolvable canonical setting ID"), breaking 5 older `test_visual_training_service` render tests. Fail-closed is arguably correct policy from the Scene002-authority work, but tests and any UX depending on the old behavior were never updated. Needs a product decision: keep gate + update tests/UX, not silent revert. Evidence: failure traces + backend log line.

**F6 — Minor smell (low).** `reference_assets.py` add/approve/remove call the private `reference_asset_service._require_storage()` from route layer. Works, but violates the route→service boundary the codebase otherwise holds.

**F7 — Incomplete.** Full backend verdict unestablished (4,777 tests; bounded run timed out). Focused backend regressions relevant to Desk/Engine (delivery, acceptance, screening, take-selection, offline: 38 passed) and to Space (creator-sync, look-approval, binding-invariant: passed within the 91) stand.

**F8 — Unverified.** End-to-end Runway execution (correctly untouched per audit boundary); upload-against-production (state-changing, not attempted).

**F9 — Nonblocking UI.** Refinement-report items stand: Desk table density, Engine evidence grouping, Space comparison polish. Screenshots confirm coherent Theater/Lobby-derived identity; no workflow obstruction found.

## Remediation (smallest safe steps, in order)

1. Default `created_at` server-side in `confirm()` and `register_uploaded_reference()`; re-run the 5 reference tests. (Unblocks Reference Space core workflows.)
2. Decide the canonical-setting render gate (keep + update 5 render tests and affected UX copy, or scope it); re-run render tests.
3. Route the three `_require_storage()` route calls through public service methods.
4. Run the full 4,777-test backend suite in a long-window job and record the result.
5. Revisit F9 polish only after 1–4.

## Verdict: NOT READY

Reference Space's headline workflows (upload, URL-add, confirm) fail against the current schema from defects in pre-existing working-tree code (F4), and render gating has drifted from its tests (F5). Frontend claims re-verified green do not compensate. The defects are small and precisely located; a fix-then-re-audit of F4/F5 plus the full backend run is the path to READY.

---

## Reassessment 2026-10-14 — full-suite reconciliation (read-only; no source changes)

### Full-suite outcome (PID 82078/82079, fresh post-Phase-1 run, `-q -p no:cacheprovider`)

- **No trustworthy full-suite result exists.** Of 4,782 collected tests (4,777 pre-Phase-1 + 5 Phase-1 regression tests — count reconciles), **2,256 completed (2,245 passed, 11 failed)**, then the run **hung indefinitely at test #2257** and was terminated after proof of non-termination. Partial log preserved at `/tmp/remed-full.log`; collection index at `/tmp/collect-ids.txt`. Exit status: killed, no `FULL_EXIT` — a full-suite pass remains **unestablished** (F7 unchanged).
- The stale pre-change run (PID 81368, child of 81367) was found still competing and was terminated; only the fresh run was assessed. No duplicate suite was launched.
- Frontend result stands as reported: 111 files / 888 tests passed (`/tmp/remed-front.log`); no frontend files changed since.

### Phase-1 reconciliation — F4, F5, F6 resolution evidence stands

- **F4:** `save_reference_asset` and `create_reference_asset` (`storage.py:13979`, `~14027`) both default `created_at` server-side with `datetime.now(timezone.utc)`; re-run of `test_reference_asset_routes.py` → **11/11, exit 0**.
- **F5:** `test_visual_training_service.py` + `test_reference_library.py` re-run together → **52/52 (30+22), exit 0**, including the 2 new fail-closed contract tests.
- **F6:** zero `_require_storage` references remain under `studio-backend/app/routes` (grep exit 1 = no matches).
- The 2 `test_reference_library.py` failures seen in full-suite context (#2093, #2095) **pass standalone** — order-dependent, not a Phase-1 regression. Phase-1 report figures are accurate.

### New failures / genuine defects found (reported before any further remediation)

Failure positions in the partial log were mapped 1:1 to test IDs via collection order (no xfail markers in project tests; mapping verified against neighbors):

- **D1 — Suite-blocking hang (new, high).** Tests #2257–#2260 in `app/services/test_render_polling.py` (`calls_reconcile_for_each_job`, `never_raises_on_reconcile_error`, `never_raises_on_loop_error`, `reconciles_runway_jobs`) drive the infinite `poll_active_runway_jobs()` loop (`render.py:5888`, docstring: "Never raises") with **real** `asyncio.sleep(10)` and a `KeyboardInterrupt`-escape break the loop is designed to defeat. Proven: full run parked 15+ min at 0 CPU in kevent/select; the single test standalone produced zero output in 45 s and required SIGTERM. The suite **can never complete** past this file. (Sibling tests that patch `asyncio.sleep` terminate — the fix pattern already exists in-file.) Untouched by Phase-1; pre-existing.
- **D2 — Genuine standalone failures (pre-existing, untouched areas).** `test_final_short_film_package_service.py` ×3 (#1516, #1517, #1524) and `test_inspection_mode.py` ×4 (#1582–#1585) fail identically standalone (7 failed / 141 passed regroup, exit 1). Failure output references the production acceptance guard path — needs diagnosis, no cause claimed here.
- **D3 — Suite-order-dependent failures (observation, not yet defects).** `test_dialogue_provider_selection.py::test_auto_uses_piper_when_not_configured` (#697) and `test_model_registry_and_router.py::test_creator_selected_capability_rechecked_at_submission` (#1708) fail in full-suite context but pass in small groups — shared singleton/global-state leakage across files (consistent with the inspection-mode singleton theme). Same for the 2 reference-library cases above.

### Reassessed readiness

- F1–F3 confirmations stand (read-only evidence, untouched code). F4, F5, F6 show verified resolution evidence above.
- **Verdict remains NOT READY.** Reason changes shape: the Phase-1 blockers have resolution evidence, but D1 makes a full-suite verdict structurally unobtainable, D2 shows genuine failures in delivery/inspection paths, and D3 shows order-dependence in the suite itself. Unresolved limitations persist: end-to-end Runway execution and production-upload paths unverified (by boundary); authorization/production-workflow boundaries as previously reported.
- Nothing was staged, committed, pushed, or deployed. No provider calls, no production mutations (all test runs on isolated temp storage).

### Next smallest necessary action

Fix D1 first (test-only, smallest): give the 4 hanging polling tests the same `asyncio.sleep` patch their sibling tests already use (or an equivalent bounded-iteration break), then re-run the full 4,782-test suite in a long-window background job and record the result. Do not claim READY until the suite terminates with a verdict and D2 is diagnosed.

---

## Phase 2 reassessment 2026-10-14 — D1 root-caused to production code; scope STOP per directive

### D1 diagnosis verified against current code (direct evidence, not hypothesis)

Reproduced the hang in isolation with faulthandler + DEBUG log-cli (throwaway plugins in `/tmp`, no repo changes; bounded 25–40 s runs, all on isolated test storage). Findings:

- The polling loop iterates normally (`POLLING_CYCLE | checking=2 jobs` every 10 s) and parks at `render.py:5939` (`await asyncio.sleep(10)`).
- Live-object inspection after 25 s: both mock jobs visible to `_get_jobs_by_status`, yet `reconcile_calls == []` — reconcile is never invoked.
- The loop's own DEBUG log gives the exact cause, every cycle, for every job: `Polling error for job job-test-001: cannot access local variable 'is_contract_only' where it is not associated with a value`.
- Mechanism (`render.py`, `poll_active_runway_jobs`): the stale-job branch contains a function-local `from app.services.scene002_contract_only import is_contract_only`, which makes `is_contract_only` a LOCAL variable of the entire function under Python scoping rules; the provider-dispatch line references the bare name instead of the module-top alias `_is_contract_only` (line 16). Fresh (non-stale) jobs never execute the stale branch, so the local is unbound → `UnboundLocalError` (an `Exception` subclass) → swallowed by the loop's per-job `except Exception` → reconcile skipped → sleep forever. The tests' `KeyboardInterrupt` break can never fire because the mock is never called.
- Production impact (evidence, not speculation): the background polling loop cannot reconcile any non-stale runway job — i.e. every job for the first 15 min (`STALE_RENDER_THRESHOLD_SECONDS = 900`) of process life. It only begins working after some job goes stale and executes the local import (accidental healing). This is a production defect, not a test defect.
- Consequence for the prescribed test-only fix: patching `asyncio.sleep` alone would flip the 4 tests (#2257–#2260) from hang to assertion failure, since reconcile remains unreachable. No test-only change can fix D1.

### Scope decision (directive §2.3 / §5)

Production code is implicated with direct evidence, so **no fix was applied, no test file was modified, and the full suite was deliberately not re-launched** (it is proven to hang identically at test #2257 — two isolations plus the 15-minute full-run stall). Awaiting explicit authorization for the one-line production fix (use the existing `_is_contract_only` module alias at the dispatch line and/or hoist the stale-branch import), followed by bounded-sleep hardening of the 4 tests, then a fresh full run.

### Isolated verification / full suite

- Isolated proof: BLOCKED — cannot pass without the production fix (evidence above). One focused regression check was possible and green with exit 0: the sibling sleep-patched polling tests were not re-run because any file-level run still executes the hanging tests first; no partial-file claim is made.
- Fresh full suite: NOT LAUNCHED (would hang at #2257 by construction). Standing result remains 2,256/4,782 (2,245 passed, 11 failed) + hang; partial log `/tmp/remed-full.log`.
- Competing processes: zero backend pytest processes at phase start and end. No provider calls, no production mutations, nothing staged/committed.

### D2 / D3 reproduction status (no fresh-run data possible; no repairs per directive)

- D2 stands on prior exit-status evidence: `test_final_short_film_package_service` ×3 and `test_inspection_mode` ×4 fail identically standalone (7 failed / 141 passed regroup). Cause undiagnosed — explicitly not assumed pre-existing beyond the fact that Phase 1 did not touch those files.
- D3 stands as observation: dialogue ×1, model-registry ×1, reference-library ×2 fail in full-suite context but pass in small groups (F4 11/11, F5 52/52 re-verified). Leakage hypothesis unconfirmed — no evidence beyond the pass/fail contrast.

### Remaining unverified requirements

Full-suite verdict; D2 cause; D3 mechanism; Runway end-to-end and production uploads (boundary-excluded, unchanged).

### Readiness recommendation

**NOT READY.** F4/F5/F6 resolution evidence stands, but D1 is now a confirmed production defect in the render polling path (not a test-hygiene issue), D2 shows genuine delivery/inspection failures, and no full-suite verdict exists. Do not reassess until the authorized D1 production fix + test bounding + fresh full run + D2 diagnosis are all evidenced.

---

## Phase 3 reassessment 2026-10-14 — D1 repaired (authorized), full suite completes: 4690 passed / 79 failed

### Exact change (production, minimal, authorized)

`studio-backend/app/services/render.py`, `poll_active_runway_jobs` only (3 lines, one function; verified by AST that the sibling `recover_jobs_after_restart` binds the name correctly and was left untouched, as were all pre-existing working-tree edits):

1. Deleted the stale-branch function-local `from app.services.scene002_contract_only import is_contract_only` (the statement that made the bare name local to the whole function).
2. Stale branch now uses the existing module-top alias: `if not _is_contract_only(job):`.
3. Polling dispatch now uses the alias: `if job.provider == "runway" and not _is_contract_only(job):`.

Same function object, no routing/authorization/retry/interval/contract changes. `py_compile` clean; zero bare `is_contract_only` references remain in the function. No test file was modified (no sleep patches, no weakened assertions, no skips).

### Focused verification (exit statuses preserved)

- The 4 formerly-hanging polling tests: **4/4 passed, exit 0** (`calls_reconcile_for_each_job`, `never_raises_on_reconcile_error`, `never_raises_on_loop_error`, `reconciles_runway_jobs`). Two finish instantly (reconcile path reached, KI-escape fires); two take exactly 20.00 s each from the tests' own unpatched real sleeps — their design, unchanged per directive, assertions intact.
- Adjacent render tests (full polling file + pipeline/state hardening + runway reconcile): **52/52 passed, exit 0** — no regression in the changed function's neighborhood.

### Fresh full suite (one run, no duplicates, no competition)

- Command: `.venv/bin/python -m pytest studio-backend -q -p no:cacheprovider` (BACKGROUND task process; an initial shell-backgrounded launch died on tool cleanup with a 0-byte log and was replaced — never concurrently).
- Result: **FULL_EXIT=1 — 4,782 collected; 4,690 passed, 79 failed, 13 skipped in 1,660.74 s (27:40).** Log: `/tmp/phase3-full.log` (4,425 lines); failed IDs: 79 lines mapped 1:1.
- D1 proven fixed in-suite: zero `test_render_polling` failures; the run sailed past former hang point #2257 to completion.
- F4/F5/F6 areas green in-suite (reference routes, visual training, reference library, hardening all pass; the 2 previously order-dependent reference-library cases pass).

### Failure classification (evidence, not hypotheses; no repairs per directive)

- **Missing repo-root files, 47:** 13+12+11+6+3 `FileNotFoundError` for `scripts/{audit_scene003_audio_goal,record_casting_voice_provider_decision,plan_casting_voice_provider_comparison,probe_scene003_full_scene_pipeline,verify_scene_pipeline_capture}.py` (all verified absent) + 1 same cause in checkpoint_5 + 2 `fish_audio_provider.py` (tests address repo root; file exists only under `studio-backend/`). Environmental/path defects, unrelated to the Phase 3 edit.
- **Missing credential, 3:** `groq.AuthenticationError: 401 invalid_api_key` in corrector tests. Environmental.
- **D2 reproduced, 7:** all 3 `test_final_short_film_package_service` + all 4 `test_inspection_mode` fail identically standalone and in-suite → genuine defects, still unauthorized for repair.
- **D3 reproduced, 2:** dialogue + model-registry fail in-suite but pass in small groups → order-dependent; reference-library order-dependence cleared this run (both pass).
- **Fail-closed gate family, 9+:** 7 checkpoint_5 failures on the READY-frozen-contract gate + ≥2 setting-gate (`setting_id_missing`) failures in `test_render_reference_consistency` / `test_render_scene_reference_transition` — the same interpretation-A situation as Phase 1's F5 (fixtures predate the gates; gate code untouched by this phase). A standalone regroup of 9 related files reproduces its 13 failures deterministically (13 failed / 108 passed), proving order-independence for that set.
- **Remaining singletons (~8):** scene002-capture hash-scope, submit-hooks quality path, render-ltx-i2v project resolution, multishot e2e, preflight 409-vs-200, sbv hash mismatch, provider-registry expectations (ltx-disabled/minimax) — all fail identically standalone; signatures in `/tmp/phase3-full.log` FAILURES section; causes undiagnosed, no action taken.
- Blast-radius check for the Phase 3 edit: every failure signature traces to missing files, credentials, untouched gates, or untouched registry/contract paths — none flows through `poll_active_runway_jobs`, whose entire test file plus hardening/state/reconcile neighbors (52 tests) pass.

### Remaining unverified requirements

D2 cause and repair; D3 mechanism; singleton causes; Runway end-to-end execution and production uploads (boundary-excluded — a passing suite alone would not establish these).

### Readiness recommendation

**NOT READY.** D1 is repaired and proven (hang eliminated, polling dispatch resolves correctly, suite completes), and F4/F5/F6 stand — but 79 suite failures remain across environmental (47+3), genuine D2 (7), gate-family (9+), order-dependent D3 (2), and undiagnosed singleton defects. No READY reassessment until failures are triaged/repaired under separate authorization and Runway/production boundaries are evidenced. Nothing staged, committed, pushed, or deployed; no provider calls; no production mutations.

---

## Phase 4 triage 2026-10-14 — read-only failure reconciliation (no repairs, no re-runs)

### Baseline (verified this phase)

- Repo root `/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project`, branch `backend-expansion-dependency-slicing` @ `86c1b58e`; working tree carries large pre-existing uncommitted modifications (348 changed paths) plus untracked test/provider files. All preserved untouched.
- Prior sections of this report (baseline, F1–F9, Phase 1, Phase 2, Phase 3) re-read; F4/F5/F6 and D1 evidence stand as written. D1 not reopened: zero `test_render_polling` failures in the Phase 3 log.
- `/tmp/phase3-full.log` verified: 4,425 lines, `79 failed, 4690 passed, 13 skipped in 1660.74s`, `FULL_EXIT=1`; exactly 79 `^FAILED` lines, all mapped below.
- Pre-existing uncommitted diffs to `studio-backend/app/services/render.py` and `test_render_polling.py` preserved (not reset, staged, or committed). Zero backend pytest processes running at phase start and end.
- No full-suite re-run, no standalone test executions, no provider calls, no file restorations, nothing staged/committed. Only this report file was modified in this phase.

### Reconciled total: 79/79, each counted exactly once (primary classification)

| # | Primary category | Count | IDs accounted |
|---|---|---|---|
| A | Repo-root-relative path assumption (deliverable exists under `studio-backend/`, tests address repo root) | 47 | A1–A47 |
| B | Invalid Groq credential in run environment (HTTP 401) | 3 | B1–B3 |
| C | D2 final-package approval guard vs test expectation (uncommitted project-existence gate) | 3 | C1–C3 |
| D | D2 inspection-mode frozen call-path contract vs uncommitted service change | 4 | D1–D4 |
| E | Fail-closed gate family (fixtures predate the gates; same interpretation-A shape as F5) | 12 | E1–E12 |
| F | D3 order-dependent (fail in-suite, pass in small groups) | 2 | F1–F2 |
| G | Singleton defects, cause undiagnosed | 8 | G1–G8 |
| TOTAL | | **79** | |

Corrections to provisional Phase 3 counts: the gate family reconciles to **12**, not "9+" (8 READY-frozen-contract + 4 setting/project-gate failures). The provisional "1 same cause in checkpoint_5" (missing file) is **not supported**: all 8 `test_checkpoint_5_canonical_workflow_thread` failures raise the READY-frozen-contract `ValidationError`; zero raise `FileNotFoundError`. The missing-file family is exactly 47, all `FileNotFoundError` for repo-root-relative paths.

### A. Missing-file failures — 47, CONFIRMED root cause (test path assumption, not missing deliverables)

Every failure in this family raises `FileNotFoundError` for a repo-root-relative path while the suite runs from the repo root (`pytest studio-backend` from root). In each case the deliverable **exists and is git-tracked under `studio-backend/`**; the repo-root path was **never tracked** (`git log --all` for the root paths is empty).

| Group | Failed tests | Expected (absent) root path | Actual tracked path |
|---|---|---|---|
| A1–A11 (11) | `tests/test_casting_voice_provider_comparison_plan.py` (all 11) | `scripts/plan_casting_voice_provider_comparison.py` | `studio-backend/scripts/plan_casting_voice_provider_comparison.py` (tracked) |
| A12–A23 (12) | `tests/test_record_casting_voice_provider_decision.py` (all 12) | `scripts/record_casting_voice_provider_decision.py` (test line 11: bare `Path("scripts/...")`, CWD-relative) | `studio-backend/scripts/record_casting_voice_provider_decision.py` (tracked) |
| A24–A36 (13) | `tests/test_scene003_audio_goal_audit.py` (all 13) | `scripts/audit_scene003_audio_goal.py` | `studio-backend/scripts/audit_scene003_audio_goal.py` (tracked) |
| A37–A42 (6) | `tests/test_scene003_full_scene_probe_verifier.py` (all 6) | `scripts/probe_scene003_full_scene_pipeline.py` | `studio-backend/scripts/probe_scene003_full_scene_pipeline.py` (tracked) |
| A43–A45 (3) | `tests/test_scene_pipeline_capture_verifier.py` (all 3) | `scripts/verify_scene_pipeline_capture.py` | `studio-backend/scripts/verify_scene_pipeline_capture.py` (tracked) |
| A46–A47 (2) | `tests/test_fish_audio_provider.py::test_fish_audio_clone_voice_uses_current_model_endpoint`, `::test_fish_audio_synthesize_uses_v1_tts_endpoint` | `fish_audio_provider.py` (test line 9–10: bare `Path(...)` + `spec_from_file_location`) | `studio-backend/fish_audio_provider.py` (tracked) |

- Full suite: fail. Standalone: fail identically from repo-root CWD (deterministic path defect; would resolve only if CWD were `studio-backend/`). Classification: **confirmed**.
- Overlap: none (no other category shares these IDs).
- Not environmental and not a packaging defect: the files ship in the repo, but at `studio-backend/`-relative paths. The defect is the tests' CWD assumption (`Path("scripts/...")` with no `__file__` anchoring). A missing script required by a documented workflow would be a delivery defect — that does not apply here since the scripts exist.
- Smallest next diagnostic (authorized repair phase): none needed for diagnosis — cause is proven. Smallest repair is test-only: anchor resolution to the test file (`Path(__file__).resolve().parents[...] / "scripts" / ...`) or relocate the runner CWD; do NOT duplicate the scripts to root.

### B. Groq credential failures — 3, CONFIRMED environmental

- B1 `studio-backend/test_corrector_direct.py::test_corrector`, B2 `test_corrector_variations.py::test_minor_failure`, B3 `test_corrector_variations.py::test_moderate_failure` — all raise `groq.AuthenticationError: 401 invalid_api_key` (log lines 1531, 1762, 1970). The tests call the live Groq API; the run environment carries an invalid key (current shell has no `GROQ_API_KEY` at all).
- Full suite and standalone: fail identically whenever the key is invalid; unrelated to D1 or any code change. Classification: **confirmed** environmental. No overlap.
- Next action: supply a valid key in the repair-phase environment, or gate these tests on a working credential (repair-phase decision, not this phase).

### C. D2 final-package failures — 3, CONFIRMED root cause (uncommitted guard vs frozen test expectation)

- C1 `app/services/test_final_short_film_package_service.py::test_final_status_can_only_be_set_after_acceptance_and_registration`, C2 `::test_update_package_status`, C3 `::test_package_helper_methods`.
- Signature: `update_package_status` → `evaluate_package_approval_guard` raises `ValueError: The final package project no longer exists.` (log lines 212, 282, 386); C2/C3 then assert `'Run production acceptance' in str(e)` and fail on the mismatch (log lines 313–314, 419–420).
- Mechanism (code evidence): the guard checks project existence via `self._project_ref(project_id)` **before** the acceptance check (`production_acceptance_service.py:280-289`), and `update_package_status` builds its guard service against the **global `project_store` singleton**, not the test's injected fake store. The tests create packages under `project-1`/`project-guard` without seeding that project in the global store, so the project check fires first.
- Committed-vs-working-tree: `git show HEAD:...production_acceptance_service.py` contains **zero** occurrences of "no longer exists"; the string appears in the **uncommitted diff**. The committed test expectation (`assert "Run production acceptance"`, present at HEAD lines 589/729) predates the uncommitted project-existence gate. Both production and test files carry pre-existing uncommitted modifications.
- Full suite and standalone: fail identically (deterministic contract mismatch). Classification: **confirmed**; production defect vs stale expectation is a repair-phase product decision (F5 interpretation-A/B shape): either seed the project in fixtures and expect the acceptance message, or accept the new gate order and update expectations. No overlap with other categories.

### D. D2 inspection-mode failures — 4, CONFIRMED root cause (uncommitted service change vs frozen call-path contract)

- D1 `app/services/test_inspection_mode.py::test_inspection_import_skips_normal_lifecycle_singletons_and_creates_no_data`, D2 `::test_inspection_uses_immutable_readonly_copy_and_never_live_path`, D3 `::test_service_read_calls_are_bounded_and_no_write_or_job_methods_are_used`, D4 `::test_inspection_runtime_keeps_all_five_approved_prompts_camera_and_references_identical` — all die identically: the `inspect_scene` subprocess exits 1 (`CalledProcessError`, log lines 513, 610, 707, 802) before any parent-side assertion runs.
- Mechanism (code evidence): `inspect_scene` (`scripts/inspect_scene_direction_snapshot.py`, committed, unmodified) asserts the exact read path `storage.read_calls == ["get_storyboard_blueprint", "get_storyboard_blueprint_version", "list_storyboard_shots", "get_project"]` and raises `RuntimeError(f"Unexpected or mutating storage call path: {storage.read_calls}")` otherwise. The truncated subprocess stderr shows the actual list ending `..., 'get_project', 'get_project']` — i.e. **two** `get_project` calls. `scene_direction_service.py` (heavily modified, uncommitted: +398/−91) contains **two** `self.storage.get_project(...)` calls (lines 38, 140); `git show HEAD` contains exactly **one**. The uncommitted diff adds the second call (diff hunk +178).
- Full suite and standalone: fail identically (deterministic). Classification: **confirmed**; the frozen inspection contract did not move — the uncommitted service change added a read. Repair-phase decision: justify and extend the frozen path (updating both the script assertion and the test's `storage_calls` expectation) or remove the second read. No overlap.

### E. Fail-closed gate family — 12, PROBABLE (fixtures predate the gates; no repair authorized)

All 12 raise fail-closed `ValidationError` from gates the fixtures never satisfy — the same interpretation-A situation as Phase 1 F5. They fail identically in-suite and in the Phase 3 standalone regroup (which reproduced its 13 failures deterministically over 9 related files), so they are order-independent.

| Group | Tests | Gate signature (log) |
|---|---|---|
| E1–E8 (8) | `tests/test_checkpoint_5_canonical_workflow_thread.py`: `test_canonical_previs_passes_explicit_provider_to_render_job[runway]`, `test_complete_canonical_workflow_trace_survives_reload[runway]`, `[simulated]`, `test_package_render_keeps_frozen_settings_and_never_uses_video_as_image[None]`, `[runway]`, `test_package_render_review_stop_does_not_poll_forever`, `test_polling_does_not_change_queued_provider`, `test_render_failure_is_recoverable_without_erasing_upstream_or_creating_memory` | `Runway video generation requires the canonical scene pipeline's READY frozen contract; the standalone Previs path cannot authorize a mutable request.` (log lines 2366–2963) |
| E9 | `app/services/test_render_reference_consistency.py::test_first_completed_character_shot_locks_reference_and_second_routes_to_r2v` | `no resolvable canonical setting ID` for scene_001 (log line 989) |
| E10 | `app/services/test_render_scene_reference_transition.py::test_scene_1_to_2_to_3_to_1_payloads_never_retain_stale_references` | `setting identity provenance is missing` for setting-a (log line 1206) |
| E11 | `app/services/test_screenplay_provider_trace.py::test_screenplay_facts_reach_provider_and_completed_job_is_persisted` | `no resolvable canonical setting ID` (log line 1297) |
| E12 | `tests/test_render_submit_completion_hooks.py::test_submit_job_runs_quality_hooks_when_provider_returns_complete` | `the project could not be resolved` via `reference_validation` (log line 3759) |

- Note: the checkpoint_5 test file itself carries uncommitted modifications, and `render.py` is heavily modified in the working tree; whether each gate is committed or uncommitted behavior was not line-attributed in this read-only phase. Classification: **probable** (gate-intended vs fixture-obsolete needs the F5-style product decision per gate; E12's project-resolution failure may alternatively be a seeding gap — flagged as overlap-uncertain, next diagnostic below).
- Overlap: none assigned; E12 is the one ID whose gate-vs-seeding attribution is explicitly unresolved.
- Next diagnostic (repair phase, bounded): for one representative per gate (E1, E9, E12), seed the missing precondition (READY frozen contract / canonical setting / resolvable project) in isolation and confirm the test flips to green — proving interpretation-A before bulk fixture updates.

### F. D3 order-dependent failures — 2, mechanism UNRESOLVED (hypotheses separated from evidence)

- F1 `app/services/test_dialogue_provider_selection.py::TestDialogueProviderDispatch::test_auto_uses_piper_when_not_configured` — in-suite: `provider="auto"` with ElevenLabs unconfigured resolves to **cosyvoice** and raises `DashScopeConfigError: DASHSCOPE_API_KEY is not set` (log line 107); in small groups it resolves to piper and passes. The dispatch (`audio_pipeline_service.py:1740-1745`) routes auto→cosyvoice **iff** module-global `COSYVOICE_CONFIGURED` is true (import-time `bool(os.environ.get("DASHSCOPE_API_KEY"))`, line 180; run env has no such key). Read-only search of `app/`, `tests/`, `scripts/` found **no** non-`monkeypatch` writer of `COSYVOICE_CONFIGURED` (all in-file writes use auto-restoring `monkeypatch.setattr`; no `setattr(...)` string-form writer; no `reload()`; conftest sets only `STUDIO_*`). So the leaking writer is unidentified: hypotheses are (a) a cross-file module-global mutation under a name this search could not see, (b) module re-import under mutated env during collection, or (c) import-order artifact. All three are unproven.
- F2 `app/services/test_model_registry_and_router.py::test_creator_selected_capability_rechecked_at_submission` (file itself untracked) — in-suite: `submit_job` raises `ValueError: Job ... not found` (render.py:4336, in-memory `self._jobs` miss for a just-created job; expected regex `cannot satisfy`, log lines 849–875); in small groups it passes. Since create→submit is synchronous on one instance, the miss implies `create_job` registered the job somewhere other than the dict `submit_job` reads — i.e. polluted global/singleton registry state steering `create_job` down a different path. The polluting writer is unidentified: hypothesis only.
- Classification: **unresolved** (order-dependence itself is confirmed by the in-suite/small-group contrast; the mechanism is not). No overlap with other categories.
- Next diagnostic (each bounded, isolated temp storage, no external calls — for authorization): (F1) run the dialogue file alone (expect pass), then paired with each audio/casting neighbor file until the cosyvoice routing reproduces — the pairing that flips it names the polluter; (F2) run the registry file alone, then paired with provider-registry/render test files until `not found` reproduces.

### G. Singleton failures — 8, cause UNDIAGNOSED (evidence quoted, no cause claimed)

All fail identically standalone per Phase 3 regroup evidence (adopted, not re-run this phase). None shares a signature with another category.

| ID | Test | Signature (log) | Note / next diagnostic |
|---|---|---|---|
| G1 | `tests/test_generation_preflight_route.py::test_generation_preflight_route_reports_backend_blocked_verdict` (file untracked) | `assert payload["cost_estimate"]["estimated"] is True` → `assert False is True` (log line 3050) | Estimator returns `estimated=False` without pricing/credential config. Unresolved: behavior-vs-expectation. Diagnostic: inspect the cost estimator's `estimated` preconditions for this fixture. |
| G2–G4 | `tests/test_local_ltx_provider.py`: `test_render_service_discovers_ltx_disabled_by_default`, `test_list_providers_includes_ltx_as_disabled` (both `enabled True is False`, log lines 3063–3076); `test_existing_registry_entries_unchanged` (`13 == 14`, log line 3089). File untracked; `providers/` has uncommitted edits + untracked new providers (`muse_chat_provider`, `nvidia_image_provider`, `runway_image_provider`, `runway_router_provider`) | Registry drift: local_ltx enabled + one entry short of 14 | Probable direction (uncommitted registry change vs untracked expectation) but line-level attribution not done. Diagnostic: diff registry entries against the tests' expected set. |
| G5 | `tests/test_minimax_h3_local_provider.py::test_existing_registry_entries_unchanged` (untracked; `13 == 14`, log line 3103) | Same count drift as G4 | Same diagnostic as G2–G4 (shared root cause likely — one entry). |
| G6 | `tests/test_multishot_integrity_phase6_e2e.py::test_creator_decisions_reach_real_multishot_render_dispatch_and_durable_results` (untracked) | `ValueError: Frozen Router reconstruction manifest values contradict the contract` (log line 3315), raised after deep pipeline progress | Unresolved. Diagnostic: capture which manifest values contradict which contract fields in isolation. |
| G7 | `tests/test_scene002_creator_decision_capture.py::test_scene002_write_surface_is_version_scoped_and_hash_safe` | `assert 'sbv_9f8ccbbfd288' == 'sbv_a6096cb1fea5'` reading a LIVE_DB copy (log lines 3788–3792) | Version-resolution drift: service returns a different version than the frozen `sbv_a6096cb1fea5` (the version the inspection tests also pin). Plausibly the uncommitted `scene_direction_service` resolution change (cf. §D), unproven. Diagnostic: read-only query of `storyboard_blueprint_versions` on a **copy** of the LIVE DB for the live project. |
| G8 | `tests/test_render_ltx_i2v_http.py::test_http_render_ltx_i2v_fails_closed_no_t2v_fallback` (untracked) | Expects `200` with fail-closed body; gets `409 project_not_found` — `the project could not be resolved` between job creation and submit (log lines 3676–3679) | Project-resolution gap on the i2v submit path (distinct from E12: here the test expects to get *past* resolution). Unresolved: seeding gap vs resolution defect. Diagnostic: trace which store `reference_validation` reads for `scene_i2v` vs which store the route seeded. |

### Environmental vs repository/application defects

- Environmental (fix outside the repo): B (3, invalid Groq key). A (47) is **not** environmental — the files ship; only the tests' CWD assumption is wrong.
- Confirmed repository defects (code evidence in this phase): C (uncommitted guard/test mismatch), D (uncommitted service read vs frozen contract), A (test path assumption).
- Probable repository defects needing a product decision: E (fail-closed gates vs obsolete fixtures, F5-style).
- Unresolved (F1, F2, G1–G8 minus the probable direction on G2–G5): no defect location claimed.

### Smallest safe remediation sequence (ordered by evidence and dependency; authorization required — NOT started)

1. **A (47, test-only, zero production risk):** anchor the six test files' script/provider paths to `__file__` (or set runner CWD semantics once); re-run just those six files. Expected: 47 green, no other file touched.
2. **B (3, env-only):** provide a valid `GROQ_API_KEY` or gate the three corrector tests on a working credential; re-run the two corrector files.
3. **C (3, decision first):** decide guard order for `update_package_status` — keep the uncommitted project-existence-first order and update the three tests to seed the project + expect the acceptance message, or restore acceptance-first ordering. Then re-run the package file.
4. **D (4, decision first):** decide the second `get_project` read in `scene_direction_service.get` — keep it and extend the frozen inspection contract (script assertion + test expectation) or remove it. Then re-run the inspection file.
5. **E (12, decision per gate):** run the three one-case seeding diagnostics (E1/E9/E12); on green, apply the F5 interpretation-A fixture updates per gate group and re-run the gate files.
6. **F (2, diagnose before repair):** run the authorized bisection pairings; repair the leaking global/singleton once named.
7. **G (8, diagnose per row):** run the per-row diagnostics in the table; G2–G5 likely collapse to one registry reconciliation, G7 may collapse into D's resolution decision.
8. **Full suite** (long window, `-q -p no:cacheprovider`) only after 1–7, then reassess readiness.

### Explicitly unverified requirements

Runway end-to-end execution and production uploads (boundary-excluded — a passing suite alone would not establish these); D2 repair correctness; D3 mechanisms; all eight singleton causes; the E-gate product decisions; full-suite verdict post-repair.

### Readiness recommendation

**NOT READY.** D1 remains repaired and verified, and F4/F5/F6 stand — but 79 failures are now fully accounted for (47 path-assumption, 3 credential, 7 D2 with confirmed code-level causes, 12 fail-closed-gate, 2 order-dependent with unidentified polluters, 8 undiagnosed singletons), and several trace to uncommitted production/test drift that has not been adjudicated. No READY reassessment until the remediation sequence above is authorized, executed, and re-evidenced with a fresh full run. Nothing staged, committed, pushed, or deployed; no provider calls; no production mutations.

---

## Phase 7 triage 2026-10-14 — approved C/D repairs: C green, D blocked by out-of-scope version-resolution drift (STOP per directive, no improvisation)

### Preflight (verified this phase)

- Branch `backend-expansion-dependency-slicing` @ `86c1b58e`; changed paths **354** (Phase 4 baseline 348 + 6). The +6 delta reconciles exactly to Phase 5's six authorized category-A path fixes: all six test files (`test_casting_voice_provider_comparison_plan`, `test_record_casting_voice_provider_decision`, `test_scene003_audio_goal_audit`, `test_scene003_full_scene_probe_verifier`, `test_scene_pipeline_capture_verifier`, `test_fish_audio_provider`) are modified in the tree and now anchor script/provider paths to `__file__`. Untouched this phase.
- Zero pytest processes at phase start and end. No full-suite or frontend runs launched.
- No Phase 5/6 decision-report files exist anywhere in the tree (only Phase 1–4 content plus `remediation-phase1.md`); the C/D work items below were executed strictly from the Phase 7 inline specification, which matches Phase 4's confirmed C/D root causes exactly. This documentation gap is recorded, not repaired.
- Target-file baselines inspected before editing: `test_final_short_film_package_service.py` (tracked, pre-existing uncommitted diff reviewed hunk-by-hunk for the touched regions); `test_inspection_mode.py` and `scripts/inspect_scene_direction_snapshot.py` (untracked working-tree files, full current content read). Repo-wide grep confirmed exactly two frozen call-path locations. Guard order (`production_acceptance_service.py:280-289`, project-existence before acceptance), `_project_ref` fallback chain, the global-`project_store` wiring in `update_package_status` (`final_short_film_package_service.py:467-479`), the acceptance reason string (`production_acceptance_service.py:518`, "Run production acceptance before approving this package."), and the two `self.storage.get_project` reads in `scene_direction_service.py` (lines 38 and ~130) all confirmed against current code.
- Fixture conventions checked before selecting the C implementation: `studio-backend/conftest.py` isolates `STUDIO_PROJECT_STORE_PATH` to a per-process temp directory before singletons construct (so global-store seeding in tests cannot touch real project state); the autouse `real_project_fixture` uses `save_project`/`delete_project`; this file already uses `monkeypatch.setattr` on the global singleton.

### C. Project existence guard — test seeding only: COMPLETE, green

`studio-backend/app/services/test_final_short_film_package_service.py` only (guard behavior, execution order, DI, approval policy, and all other tests untouched):

- Added `_global_project_seed` context manager (snapshot via `get_project`, seed via `save_project` only when absent, restore-or-delete in `finally`) plus a `_with_global_project` decorator; applied as one line each to `test_final_status_can_only_be_set_after_acceptance_and_registration` ("project-guard"), `test_update_package_status` ("project-1"), and `test_package_helper_methods` ("project-1"). Test bodies, intent, and assertions are byte-identical, including the acceptance message for existing-but-unaccepted projects.
- Results: the three C tests **3/3 passed, pytest exit 0** (0.87 s); full package file **27/27 passed, exit 0** (3.85 s); `test_production_acceptance_service.py` **15/15 passed, exit 0** (1.84 s) — no regression.

### D. Inspection call path — frozen contract updated, then BLOCKED one layer deeper (out of scope, no fix applied)

`studio-backend/scripts/inspect_scene_direction_snapshot.py` and `studio-backend/app/services/test_inspection_mode.py` only (production service code, setting-identity feature, Scene 002 fixtures, and all other inspection tests untouched):

- Frozen expectation updated in both locations to the observed five-call sequence `get_storyboard_blueprint`, `get_storyboard_blueprint_version`, `list_storyboard_shots`, `get_project`, `get_project`, each with a concise comment attributing the second `get_project` to the scene setting identity read model (`SceneDirectionService._scene_setting_identity`). Verified live against the service: an in-process `service.get()` on a read-only DB copy emits exactly this sequence.
- The call-path gate now passes, but the subprocess still exits 1 on the *next* frozen gate: `Coverage contract mismatch: shot_content_dispositions 6 vs 5, shot_dialogue_dispositions 6 vs 5`. Root cause isolated with direct evidence: the uncommitted `get_blueprint_detail` (`storyboard_blueprint_service.py`, +324 uncommitted lines) resolves the **current draft v10 (`sbv_9f8ccbbfd288`)** instead of the pinned approved v3 (`sbv_a6096cb1fea5`) — returning 6 shots (001–006) plus saved ASSIGNED decisions from the draft's metadata, where the frozen contract pins v3 / 5 shots / all-UNASSIGNED. The v3 rows themselves are intact (5 shots, no `scene_direction` metadata).
- Repairing this requires changing production version-resolution code (or the frozen version/coverage contract and fixtures) — all explicitly forbidden in D scope ("Do not edit production service code ... or Scene 002 fixtures"). Per the stop-and-report rule, **no further D repair was attempted**: no weakened assertions, no skips, no production edits.
- Results: `test_inspection_mode.py` **1 passed / 4 failed, pytest exit 1** (1.79 s; full log `/tmp/phase7-inspection.log`). The Scene 002 lifecycle regression run was deliberately not launched (gated on all three suites passing) and no broad run was started.

### Diff accounting

- Before: 354 changed paths. After: **354** — delta is content-only inside the three intended files (one tracked test file's pre-existing diff extended; two untracked files edited in place). No new, renamed, or deleted paths; Phase 5's six path fixes and all preexisting unrelated changes intact.
- Nothing staged (`git diff --cached` empty), nothing committed, pushed, or deployed. No provider calls, no production mutations, no uploads, no renders (all runs on isolated temp storage; the inspection diagnostic used a disposable `/tmp` DB copy, since removed).

### Remaining work (unchanged in kind, D now precisely localized)

- B (3 Groq credential), E (12 fail-closed gates), F (2 order-dependent, polluters still unidentified), G (8 singletons) stand as in Phase 4.
- D's remaining failure is now localized to version resolution in `get_blueprint_detail` (current-draft vs pinned-approved) plus its downstream coverage/decision assertions — needs a product/authorization decision: restore approved-version resolution in production code, or re-pin the frozen contract and fixtures to the new resolution behavior.
- Unverified as ever: Runway end-to-end execution and production upload paths (boundary-excluded).

### Readiness recommendation

**NOT READY.** C is repaired and evidenced (3/3 C tests, 27/27 file, 15/15 acceptance, all exit 0), and the D five-call contract update is verified against the live read sequence — but the inspection suite still fails (exit 1) on version-resolution drift that Phase 7 scope forbids repairing, and categories B/E/F/G plus the Runway/production-upload boundaries remain open. No READY reassessment until the D version-resolution decision is authorized and executed, the remaining categories are remediated, and a fresh full run speaks. Nothing staged, committed, pushed, or deployed; no provider calls; no production mutations.

---

## Phase 8 adjudication 2026-10-14 — storyboard version resolution: no code regression; frozen v3 pins rotted as the live board evolved (read-only, nothing modified)

### Correction to Phase 7's reported cause

Phase 7 attributed v10 selection to "the uncommitted `get_blueprint_detail`". That attribution is **wrong** and is corrected here with direct evidence: `get_blueprint_detail` (`storyboard_blueprint_service.py:124-141`) resolves `blueprint.current_version_id` **identically at HEAD and in the working tree** (verified by `git show HEAD` byte comparison of the whole function). `approve_version` advancement semantics are likewise identical (approve sets `approved_version_id = current_version_id = version`; saves and `create_version` advance current — HEAD and worktree agree). No code change introduced current-version resolution; it was always the rule for this function. What changed is the **live database**: the board advanced v3 → … → v10 through normal approve/create/save flows, so `current_version_id` now points at draft v10 instead of v3.

### HEAD versus working tree (version selection only)

- `get_blueprint_detail`: HEAD == worktree (current-version rule). `SceneDirectionService.get` (HEAD line 67 / worktree line 209) and `.save` both delegate with no version pin — unchanged pattern.
- Uncommitted deltas that *do* touch this area: the second `get_project` read (setting identity — intended, Phase 7 D contract), coverage machinery, and a stricter save gate (worktree `scene_direction_service.py:304`: save requires source APPROVED **and** `approved_version_id == current_version_id == source`; HEAD required only version-match plus locks). None of these alters version *selection*.
- Live DB ground truth (read-only queries on a disposable `/tmp` copy, since removed): blueprint `current = sbv_9f8ccbbfd288` (v10, draft), `approved = sbv_5fb97c8f5fa3` (v8, approved); v3 has 5 shots and no `scene_direction` metadata; v10 has 6 shots (adds 006) with saved ASSIGNED decisions; **v8's five shot prompts and camera plans are hash-identical to v3's** (all five pairs match), but v8 metadata carries saved creator decisions.

### The two version-selection rules in this codebase (confirmed)

- **Working-draft rule → `current_version_id`**: `get_blueprint_detail`, the `GET .../storyboard-blueprint` detail route (`routes/storyboard_blueprints.py:122-127`, the creator editing view), `SceneDirectionService.get/save` (optimistic-concurrency `expected_version_id` flow targets current). Correct for editing surfaces.
- **Approved-frozen rule → `approved_version_id`**: `canonical_production_workflow_service.py:113-115`, `previs_service.py:803-805`, `storyboard_blueprint_service.py:907-909` (approved-gated shot read), version-contract checks requiring approved==current (`storyboard_blueprint_service.py:939-958`, `runway_reference_projection.py:718`, `scene_production_pipeline_service.py:1664`), `production_authorization_service.py:154`, `reference_validation.py:774-777,1136-1142`. Correct for anything stable/reproducible.
- Inspection's purpose (frozen approved prompts/camera/references, read-only and lifecycle-isolation guarantees) belongs to the **approved-frozen family**, but it currently travels the working-draft path (`service.get` → `get_blueprint_detail` → current).

### Why the frozen pins say v3

Point-in-time live state, not a code constant: `docs/forensics/SCENE002_GENERATION_PREFLIGHT_20260928.md:107` records "Final chain: `current = approved = sbv_a6096cb1fea5`" — when the inspection files and G7 were written, live current *was* v3, pristine (no decisions). The `APPROVED_VERSION_ID` name is now a double misnomer (v3 is neither current nor approved). G7 (`tests/test_scene002_creator_decision_capture.py:82,112`) pins the same v3 and fails the same way; notably it already contains the codebase's own answer to board evolution — `pytest.skip` when `data.saved` ("pre-input capture state no longer applies") — while the inspection script hard-fails instead.

### Required questions — explicit answers

1. **Introducing change?** None. Current-version resolution predates the working tree; the drift is live-DB evolution, not a code regression.
2. **HEAD vs worktree?** Identical selection behavior (current). Deltas are the intended second `get_project`, coverage machinery, and the stricter approved==current save gate.
3. **Why v10?** `current_version_id` advanced by designed save/create flows; inspection delegates to the current-resolving path.
4. **v3 pinned by input or fixture?** Both: hardcoded `APPROVED_VERSION_ID` drives direct version reads *and* stale fixture expectations (shots, hashes, 40/10/5/5, all-UNASSIGNED) written against the pristine v3 moment.
5. **What should inspection use?** The **approved** version — high confidence from the six-plus approved-frozen call sites and inspection's own stability purpose. It must not use current (a moving target no frozen contract can pin).
6. **Blast radius of restoring approved resolution?** Must NOT change `get_blueprint_detail`'s default: the detail route, `get`/`save` editing flow, and tests (`test_camera_presets`, `test_checkpoint_4a_storyboard_integrity`, `test_scene002_creator_decision_capture`) depend on current. An opt-in version selector defaults safely to current: zero default-path blast radius.
7. **Smallest safe production fix (regression framing adjusted: smallest safe repair)?** Add an optional version selector to `get_blueprint_detail` / `SceneDirectionService.get` (default current; inspection passes `approved_version_id`); re-pin version/hash expectations from v3 to v8 (prompts proven identical); adopt G7's saved-state skip (or updated decision assertions) since approved v8 legitimately carries creator decisions. No changes to approval, save-gate, editing, or render-authorization semantics.
8. **Evidence for preserving current + updating contract (B)?** Current-resolution is correct for the editing path, but a frozen contract on a moving current is inherently unstable — B requires de-pinning to structural assertions and weakens the Approved-content guarantees. Not recommended.
9. **Distinguishing tests (read-only guarantees kept)?** (a) Fixture-board unit test: approved≠current → `get_blueprint_detail` returns current (locks the editing rule). (b) Same fixture → opt-in selector returns approved. (c) Inspection subprocess against a fixture-pinned copy (approved==current, no decisions) → all frozen assertions pass (contract self-consistency, no live DB). (d) Live-DB inspection with G7-style saved-skip → read-only/lifecycle gates pass independent of board evolution. (e) v8-vs-v3 prompt-hash equivalence (already evidenced read-only) justifies the re-pin.

### Recommendation: outcome A — inspection resolves the approved version

Confidence: **high** on the resolution rule (approved-frozen family + inspection purpose); **medium** on decision-assertion handling (recommend the G7 skip pattern as smallest-safe). Minimum implementation scope and verification are items 7 and 9 above. The residual product decision is narrow: whether inspection asserts pristine-state (skip when decisions exist, as G7 does) or approved-state (updated decision expectations) — it does not affect the resolution rule. Outcome B rejected per item 8; outcome C not needed — version semantics are established.

### Read-only confirmation

No source, test, fixture, report (other than this appended section), configuration, or database state was modified in Phase 8: `git status` steady at 354 changed paths, nothing staged, no pytest processes started or left running, no provider calls, no renders/uploads/approvals. Read-only evidence came from `git show`/`git diff` comparisons, file reads, repo search, and SELECT-only queries against a disposable `/tmp` copy of the live DB (removed afterwards). The Studio verdict remains **NOT READY** until the authorized repair is implemented and its focused tests pass.

---

## Phase 9 implementation 2026-10-14 — approved version resolution for inspection (outcome A): all focused suites green

### Preflight (verified this phase)

- Phase 8 adjudication and Phase 7 report re-read; baseline **354** changed paths (Phase 5 six path fixes plus Phase 7 C/D changes all present); zero pytest processes at start and end.
- Target diffs inspected before editing; version-resolution code, inspection subprocess, fixture pins, v8 metadata, and saved-decision assertions all confirmed against current code.
- v8 identity re-established from scratch on a disposable DB copy (live DB never mutated, copy removed): blueprint `current=v10 draft / approved=v8`; v8 has 5 shots, carries `scene_direction` decisions (50 ASSIGNED / 9 UNASSIGNED / 1 EXPLICITLY_OMITTED) including a setting decision; **all five full prompt sha256 and all five full canonical camera-plan sha256 are identical between v3 and v8** using the script's exact extraction — so the re-pin preserves the frozen approved content.
- Smallest test set identified: `test_storyboard_blueprint_service.py` (temp-`DatabaseStorage` fixture boards) for selector behavior; `test_inspection_mode.py` (existing subprocess tests plus pure helper unit tests) for inspection; `test_scene002_setting_reference_lifecycle.py` (22 tests, the Phase 1 lifecycle target) for regression.

### Changes (4 files, no new paths: 354 → 354)

1. `studio-backend/app/services/storyboard_blueprint_service.py` — `get_blueprint_detail` gains `version_selection: Literal["current", "approved"] = "current"`. Default resolves `current_version_id` exactly as before (same error message preserved); `"approved"` resolves `approved_version_id` and fails closed (`No/Approved ... not found`) when absent; unknown modes raise instead of substituting. Return type, authorization, and unrelated fields untouched.
2. `studio-backend/app/services/scene_direction_service.py` — `get()` forwards the same opt-in (default current); `save()` and all other callers omit it. Repo-wide grep confirms only inspection passes `"approved"` in non-test code, so the route detail endpoint, editing flow, pipeline, and previs keep current-draft behavior.
3. `studio-backend/scripts/inspect_scene_direction_snapshot.py` — `service.get(..., version_selection="approved")` (same storage methods, so the Phase 7 five-call sequence is structurally unchanged); `APPROVED_VERSION_ID` re-pinned v3→v8 with a grounding comment (approved metadata, never version numbering); new `check_inspection_decision_state()` helper implementing the G7 skip precedent (returns skip=True only when `direction.saved`; raises on anomalous assigned rows without saved state; pure read); strict decision gates conditional on it with `saved_decisions_present` / `decision_assertions_skipped` report flags; character reference lists filtered to the schema's authoritative `canonical` rows exactly as production does (`reference_asset_service` canonical-primary convention), keeping the exactly-one-per-subject gate fail-closed — the live board now ships face+full-body look pairs (2026-10-09) so the unfiltered count had rotted 1→2 like the version pin.
4. `studio-backend/app/services/test_inspection_mode.py` + `test_storyboard_blueprint_service.py` — pins v3→v8; parent-side proof that inspection selects approved while a later draft is current; decision assertions conditional on the skip flags (content, isolation, and read-only assertions stay unconditional); 4 selector tests (default-current, approved, no-approval fail-closed, unknown-mode fail-closed); 3 helper tests (pristine pass, saved skip, anomalous raise) with real row models.

### How defaults are preserved

Every existing `get_blueprint_detail` / `SceneDirectionService.get` caller omits the selector (verified by grep) and therefore resolves `current_version_id` through byte-identical default logic; the 4 new selector tests lock both modes plus both fail-closed paths.

### Verification (bounded, true exit codes)

- `test_storyboard_blueprint_service.py`: **7 passed, exit 0** (~1.9 s) — default, approved, and consumer-omission behavior.
- `test_inspection_mode.py`: **8 passed, exit 0** (~2.7 s) — 4 subprocess tests (approved-v8 selection with v10 current, 5-call contract, prompts/camera/references/identity, read-only + lifecycle isolation) plus live-path rejection plus 3 decision-gate unit tests.
- `test_scene002_setting_reference_lifecycle.py`: **22 passed, exit 0** (~3.6 s) — final regression target from the readiness report.
- `test_final_short_film_package_service.py` / `test_production_acceptance_service.py` correctly **not run** per §7.3: grep confirms neither imports the storyboard/scene-direction dependency, and neither file was touched.
- No full backend/frontend suites, no unrelated categories, no provider calls, no renders/uploads/approvals; scratch DB copies removed; every test process exited (zero pytest processes at end).

### State and scope confirmation

- Diff is content-only inside the 4 intended files; Phase 5/7 changes and all unrelated edits intact; nothing staged, committed, pushed, or deployed; live database and project state unmutated.
- Categories B, E, F, G and the Runway end-to-end plus production-upload paths remain unresolved and unverified as in prior phases.
- Readiness verdict: **NOT READY** — Phase 9's authorized scope is fully evidenced green, but the separately required readiness criteria (remaining categories, full-suite verdict, Runway/production boundaries) are not satisfied by focused tests alone.

---

## Phase 10 audit 2026-10-14 — read-only audit of Phase 9: accepted as implemented (no defects; one latent observation)

### Preflight

Phase 8/9 sections re-read; tree steady at **354** changed paths, nothing staged, zero pytest processes. Phase 5 six-file `__file__` anchoring, Phase 7 C decorators (4 references) and D five-call contract (script line 643; test file multi-line list) all intact. Phase 9 `/tmp` logs corroborate the reported counts (8/8, 22/22, 7/7). No test was rerun: code inspection plus recorded true-exit-code logs were sufficient, and no focused rerun was justified.

### Audit A — version selection: PASS

`get_blueprint_detail` (`storyboard_blueprint_service.py:128-167`): default `"current"` resolves `current_version_id` through logic identical to HEAD's; `"approved"` resolves `blueprint.approved_version_id`; absent approval fails closed (`No approved storyboard version`); dangling IDs fail closed per-branch (`Approved/Current ... not found` — existing message preserved on the default path); unknown values raise (`Unknown version selection`) with no silent substitution. `SceneDirectionService.get` (`scene_direction_service.py:210-219`) forwards the selector, default current. Call-chain trace confirms only `inspect_scene_direction_snapshot.py:639` passes `"approved"` in non-test code; route detail, `save()`, pipeline, previs, and all existing tests omit it. No hidden fallback exists: every branch either resolves an explicit ID or raises.

### Audit B — approved v8 fixture: PASS

Independently re-grounded on a disposable read-only copy (removed): blueprint `approved_version_id = sbv_5fb97c8f5fa3`, v8 status approved, 5 shots. Snapshot extraction (`inspect_scene_direction_snapshot.py:346,358-359`: `ORDER BY shot_number`, `sha256(prompt)`, canonical-JSON `sha256(camera_plan)`) is identical to Phase 9's claimed verification method; all 5 shots covered with no LIMIT, reorder, or extra normalization; the `len != 5` gate (line 686) pins completeness. Zero `sbv_a6096cb1fea5` references remain in the four Phase 9 files; the remaining pins (`tests/test_scene002_creator_decision_capture.py` G7, forensics doc) are unrelated live-DB-coupled expectations outside Phase 9 scope, reported here without change.

### Audit C — saved decision handling: PASS

`check_inspection_decision_state()` (script lines 501-519) reads the authoritative `direction.saved` (version-persisted `scene_direction`, the same source G7 uses): saved → skip True; otherwise any non-UNASSIGNED decision/obligation row raises; else False. Pure read, no mutation path. Skip-controlled (script + tests 2/3/4 conditionals): exactly the two pristine gates and their `decision_status_counts`/`saved` report assertions. Unconditional and still enforced: version identity/status, coverage 40/10/5/5, prompt/camera/reference hashes and counts, five-call sequence, all storage/lifecycle/runtime/network/process guards, import isolation, `creator_decisions_recorded` (inspection records none — truthful as hardcoded). Missing/unreadable state cannot skip: `direction.saved` falsy plus anomalous rows raises; `None` rows would raise `TypeError`, never silently pass (fail-closed direction).

### Audit D — canonical reference filter: PASS with one latent observation

Filter (script lines 370-371) selects character rows with `bool(row.get("canonical"))`, matching the production convention (`reference_asset_service.py:575` canonical-primary split; coverage/projection bindings requiring canonical). Edge cases: (1) one valid canonical → selected, gate passes (live DRE/MAYA: exactly 1 of 2 each); (2) multiple legitimate canonicals → count gate raises — fail-closed, though production takes first-found (`next(...)`), a defensible strictness asymmetry; (3) missing canonical → 0 ≠ 1 raises; (4) duplicates → raises loudly, nothing silently concealed; (5) ambiguity → raises; (6) noncanonical face/full-body variants discarded by schema design, and the exactly-one gate guarantees the canonical identity is unambiguous; (7) **observation (latent, low)**: the filter does not check `approval_state`, so a canonical-but-unapproved row would be accepted, while production eligibility requires approved+canonical (`scene_coverage_contract.py:648`). No such rows exist today (all canonicals are approved), and the pre-Phase-9 snapshot never checked approval either, so this is not a Phase 9 regression — recorded as an unresolved contract question with smallest correction (assert `approval_state == "approved"` on selected canonicals) pending product confirmation that unapproved-canonical is a meaningful state.

### Audit E — test evidence: PASS

Selector tests build a real approved-then-draft board and lock default-current, approved resolution with shot-version scoping, no-approval fail-closed, and unknown-mode fail-closed (try/assert-False/except style is functionally equivalent to `pytest.raises` here — style note only). Helper tests use real row models and prove pristine-pass, saved-skip, and anomalous-raise. Updated subprocess tests prove approved-v8 selection under a live v10-current board (parent-side blueprint assertions, no call-contract impact), conditional decision gates, and unconditional content/isolation/contract assertions. Lifecycle 22/22 matches the Phase 1 target file exactly. `/tmp` logs corroborate all three reported results; no rerun was necessary.

### Audit F — scope and safety: PASS

No default-resolution change (only inspection opts in); authorization gates untouched — the single Phase-9-pattern match in auth/route diffs is pre-existing production code (`render.py` canonical projection inside its 2165-insertion pre-existing diff); live DB unmutated (read-only queries only, mtimes predate the audit, scratch copies removed); no provider/runway/render/upload/approval additions in any Phase 9 hunk (verified by hunk inspection); Phase 5/7 and unrelated edits intact; nothing staged, committed, or pushed.

### Verdicts and acceptance

A PASS, B PASS, C PASS, D PASS (one latent observation), E PASS, F PASS. **Zero confirmed defects.** Phase 9 is **accepted as implemented**; no corrective phase is required. Optional narrow follow-up (product-confirmed): assert `approval_state == "approved"` on inspection-selected canonical references. Delta accounting: 354 → 354, content-only in the 4 reported files. No source, test, fixture, configuration, database, or production state was modified during this audit. Remaining categories B, E, F, G and the unverified Runway end-to-end plus production-upload paths stand as in prior phases. Final Studio verdict remains **NOT READY**.
