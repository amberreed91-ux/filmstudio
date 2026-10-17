# AI Film Studio Roadmap & Production Readiness Brief

**Updated Oct 15, 2026 — supersedes the PDF where they differ.** Source: the Oct 14 consolidated brief (`readiness-report.md` in this directory, Phases 1–10) plus the R-series decision reports. No production code, test, or config change accompanies this brief. Standing verdict: **NOT READY.**

Evidence-level language is kept throughout: **CONFIRMED** (root-caused with direct evidence) / **PROBABLE** (best-supported interpretation, needs a product decision) / **UNRESOLVED** (observed but mechanism unclaimed) / observation. Testimony tiers: **Tested** (exit-status run) / **Code-inspected** (grep + read) / **Mocked** (no provider contact) / **Unverified**.

## 1. Milestone status (corrected)

| Milestone | Report | Status |
|---|---|---|
| R3.2 generic-scene Runway projection | R3.2 | Evidenced (prior) |
| R3.3 single-shot end-to-end verification | R3.3 | Evidenced (prior) |
| R4.0 consolidated readiness audit | R4.0 | Superseded by phases below, carried |
| R4.0A projection capacity decision (interim 4-ref policy) | R4.0A | Decided; `CAPACITY = 4` in force |
| **R4.1A multi-shot batch preflight** | R4.1A | **Implemented** — all-or-nothing `preflight_batch_authorization` before first `create_job`; zero-job rejection (Tested, Mocked) |
| **R4.2 confirmation persistence & recovery** | R4.2 | **Implemented** — migration 68 `shot_reference_confirmations`, project-scoped digests, `require_persisted_confirmation` on the submission entrypoint (Tested, Mocked) |
| **R4.3 integrity & traceability** | R4.3 | **Implemented** — creation/submit/adapter gates, Scene 002 `verify_submission_boundary` at all three boundaries (Tested, Mocked; provider leg Unverified per R4.3B) |
| R4.3A job-creation enforcement | R4.3A | Evidenced; confirmation scope beyond pipeline closed |
| R4.3B live-provider acceptance safety | R4.3B | Decision B stands: live acceptance blocked; provider-side truth Unverified |
| R4.3D provider-independent integrity (G-1…G-4) | R4.3D | Gaps registered; G-1 reconcile-before-retry recommended, owner approval required |
| R4.3E router submission reconciliation | R4.3E | Implemented per R4.3F parity review (Tested, Mocked) |
| R4.3F reconciliation parity & gap review (F-1…F-6; Decisions A/B/C) | R4.3F | A APPROVED, B REAFFIRMED, C DEFERRED (F-1 stays documented) |
| Legacy render-batch route (`POST …/render-batch` → `create_scene_batch`) | R4.3G (gap **G-5**) | **Closed at route Oct 15** — route retired (410 `render_batch_retired`, zero jobs); service method retained but unreachable via HTTP; dormant `SceneBatchRenderer` untouched per owner option (b) |

## 2. What stands from Oct 14 (unchanged)

- **F1–F3 CONFIRMED working** (read-only rooms, acceptance guard, project context).
- **F4/F5/F6 resolved with evidence** (server-side `created_at` defaults; fail-closed gate tests; boundary cleanup).
- **D1 repaired and proven** (polling `UnboundLocalError`; 4/4 tests, full suite completes: 4,690 passed / 79 failed / 13 skipped).
- **79 failures fully reconciled** (Phase 4): 47 path-assumption (A, test-only), 3 credential (B, env), 7 D2 with CONFIRMED code-level causes (C/D), 12 fail-closed-gate family (E, PROBABLE), 2 order-dependent (F, UNRESOLVED mechanism), 8 singletons (G, undiagnosed). Phase 7: C green; D blocked on version-resolution drift (STOP per scope). Phases 8–10: drift adjudicated as live-DB evolution, outcome A implemented and accepted (all focused suites green).
- **NOT READY** — remaining categories B/E/F/G, full-suite verdict post-repair, Runway end-to-end and production-upload paths (boundary-excluded).

## 3. Decisions carried (R4.3F §9, recorded Oct 15)

1. **A — APPROVED:** reconcile-adopted outputs pass the same integrity reviews; no check weakened.
2. **B — REAFFIRMED:** no automatic resubmission of unresolved ambiguous submissions.
3. **C — DEFERRED:** dry-run `submission_attempted` marker scoping not authorized; F-1 remains a documented fail-closed limitation.

## 4. Gap G-5 (R4.3G, closed at route Oct 15; was UNREGISTERED)

`RenderService.create_scene_batch` (`studio-backend/app/services/render.py:5915`), reachable via `POST /projects/{project_id}/scenes/{scene_id}/render-batch` (`studio-backend/app/routes/scene_continuity_intelligence.py:313`), creates N jobs in a loop with per-job `_persist_job` and **no** `preflight_batch_authorization` call, **no** `expected_reference_binding_digests` / `require_persisted_confirmation`, and **no** creation-time reference-capacity check (`create_job` has no count gate). An invalid shot mid-batch raises after earlier jobs are already persisted — partial batch, no rollback. Submit/adapter gates still apply per single job, but nothing enforces batch atomicity. Related single-job paths (`create_and_submit_job` via retry-render; `POST /jobs` via WritersRoom/Sandbox) likewise bypass preflight by design. Absent from R4.3D G-1…G-4 and R4.3F F-1…F-6 under any ID. Disposition per R4.3G: route retired (410 `render_batch_retired`, zero jobs; route-layer only, service untouched). Closure evidenced: POST route test asserts the 410 contract, status test seeds via the service (GET proven working), 33/33 across the three batch files green, exit 0 (Tested). Dormant frontend callers (`createRenderBatch`, unmounted `SceneBatchRenderer`) retained per owner option (b). Related single-job paths still bypass preflight by design — noted, out of scope.

## 5. Path to READY (unchanged, authorization required)

Repair sequence A→G per Phase 4 §remediation, register and adjudicate the §4 gap, fresh full-suite verdict, then R4.3B-gated live acceptance for the provider leg. Nothing staged, committed, or deployed with this brief; no provider calls.

- 2026-10-15: the two render-batch tests in `test_render_batch.py` were updated to the retired contract (POST asserts 410 `render_batch_retired` with zero jobs; status test seeds via the service and asserts GET 200).
