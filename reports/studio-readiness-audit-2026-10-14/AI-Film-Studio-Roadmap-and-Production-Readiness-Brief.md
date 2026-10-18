# AI Film Studio: Roadmap & Production Readiness Brief

Canonical project reference · Original baseline: October 14, 2026 · Status update: October 15, 2026 · Private project documentation

This document is the source of truth for future AI Film Studio work. Save it in the project's source files and update it whenever a phase is completed or a roadmap decision changes. It complements persistent memory; where the two disagree, this document and the underlying implementation reports control project decisions.

---

## Status update, Oct 15, 2026 (supersedes the Oct 14 status table where they differ)

Reports are in `reports/studio-readiness-audit-2026-10-14/`.

**Phase status**

- R4.1A (multi-shot batch preflight): **Implemented.** See `R4.1A-multi-shot-batch-preflight.md`.
- R4.2 (confirmation persistence and recovery): **Implemented.** See `R4.2-confirmation-persistence-recovery.md`.
- R4.3 (integrity and traceability): **Implemented.** See `R4.3-integrity-traceability.md`, R4.3A, R4.3D, R4.3F.
- R4.3F decisions: **A (approved)**, **B (reaffirmed)**, **C (deferred)**.
- R4.3K (Runway independence assessment): **complete, awaiting owner approval.** See `R4.3K-runway-independence.md`.
- R4.4 (final readiness verification): not started.

**Gaps closed since Oct 14**

- **G-5**, render-batch preflight bypass: closed at the route, per `R4.3G-render-batch-preflight-bypass.md`.
- **G-6**, demo seed project guard: closed at the service layer, per `R4.3H-demo-seed-project-guard.md`.

**Open**

- `seed_demo_characters` (`storage.py` ~:13711): unguarded, no production callers.
- `/dev/` routes have no environment gate.
- Five direct `save_job` writers (D1: accepted as non-authorization writers, no change) and single-job digest revalidation (D2: accepted as by design) — decided Oct 15, see `R4.3I-owner-decisions.md`; Checkpoint 5 policy (D3: simulated-only previs, implemented per `R4.3J-checkpoint5-simulated-previs.md`).
- Non-hermetic tests: two tests in `test_real_project_rendering.py` quarantined 2026-10-16 per R4.4 step 2b (skipped by default, opt-in via `STUDIO_ALLOW_LIVE_NETWORK_TESTS`); 9 passed, 2 skipped under the network block.
- Scene 002 handler-level regression test: in progress.
- Historical failures unreconciled against `/tmp/r31-full.log`, now preserved at `reports/evidence/r4-raw/r31-full.log`.
- R4.3N (capability-declared preflight design, read-only, awaiting owner approval): see `R4.3N-capability-declared-preflight-design.md` — defer implementation until after R4.4 re-baselining.
- G-7 (unhydrated-duplicate `create_job` edge, pinned by characterization; startup hydration covers single-process) and G-8 (offline-delivery import fixed 2026-10-16 per R4.4 step 2b; both files collect and pass under the network block) — registered `R4.3K-runway-independence.md` §15 per R4.3M, resolution note appended per R4.4 step 2b; G1 reclassified as fixed-by-test-update (stale expectation), reconciliation failures confirmed fail-closed, helper proven opt-in (§14).
- Checkpoint G classified (a) STALE FIXTURE OR EXPECTATION with byte-identical evidence, fix proposed not applied — see `R4.4-step2a-checkpoint-G.md` (awaiting owner approval).
- Checkpoint G re-adjudicated 2026-10-16 (R4.4 step 2c): step 2a's premise is disproved — a pipeline-built multi-shot batch with ordinary face/environment references fails Router preflight (`unsupported_reference_role`), `create_job` manifest equality, and Router reconstruction `:783`/`:788` (setting row `project_id`), so it cannot dispatch through the router at all (0 jobs, fail-closed, Variant B withheld); brief §11 criterion 1 is not Met on the router path — owner decision required, see `R4.4-step2c-checkpoint-G-production-path.md`.
- R4.3L (2026-10-16): legacy previs Runway-family guard closed (R4.3K C-5); see `R4.3L-legacy-previs-runway-guard.md`.
- R4.4 step 2 (2026-10-16): bounded Runs 1–4 re-run network-blocked on the fingerprinted tree — Run 1 (83) green, Run 2 socket-only 1 failed/173 passed (Checkpoint G identical, G-9), Run 3 socket-only 102 passed + delivery 16 passed, Run 4 (72) green adjudicating the setting-gate fixes as holding; verdict remains NOT PRODUCTION READY — see `R4.4-step2-bounded-runs.md`.
- G-9 (generic pipeline-built contracts cannot dispatch through the Runway Model Router — four fail-closed gates, 0 jobs): root cause + smallest design, read-only, awaiting owner approval — see `R4.5-generic-router-dispatch-design.md`.
- R4.5 session A (2026-10-16): shared role/comparison/scope gates F1, F2, F3, F4, F6 implemented (F5 deliberately pending) — pipeline batch now passes preflight + creation/reconstruction comparisons and stops fail-closed (Checkpoint G now fails at the `:784` parameters gate; probe updated and green; 32 new gate/parity tests green; all baseline nodes unchanged) — see `R4.5-sessionA-shared-gates.md`.
- R4.5 session A2 downstream gate survey (2026-10-16, test-only probe, no production edits): ordered gate list from the missing generic declaration to mocked dispatch established by evidence — production entry stops at the seed-lock durable identity denial (new, F9: `render.submit_job` writes a seed into mutable inputs after the last durable write, adapter entry refuses `durable_render_job_identity_mismatch`; confirmed as the only pre-adapter blocker), then `mutable_render_input_mismatch` (F7 — now known to block *every* freshly created Router job, Scene 002 included: `create_job` persists only `frozen_parameters`), then `reference_projection_declaration_missing` (F5), then the declared-path record shape (pinned field by field, incl. the non-empty-list `rejected_environment_ref_ids` quirk); `:784` creative-parameters parity (F8) remains and is silently dropped on the declared path; both shots dispatched to the mocked Router (dry-run + submit + poll, 6 transport calls) with zero checks relaxed — revised F5 scope = F7 + F9 + F8 + F5, one F5 session + one acceptance session, high confidence on shape, see `R4.5-sessionA2-downstream-gates.md`.
- R4.5 gate census (2026-10-16, read-only review + throwaway census, deleted): session A verified scoped — zero assertion changes, F2 narrowing touches no real producer (`studio_role="reference"` only from role-less rows already refused downstream), Scene 002 byte-identical (41 v1 tests green), ceiling 4 intact; complete gate list pipeline→mocked-wire established (10 gates: session-A 3 closed, 1 NEW `mutable_render_input_mismatch` gate, declaration gate needs F5, declared-path shape constraints + parameters-parity gap found) — revised plan F5+F7(new)+F8(new)+T1/T2, 2 more sessions, medium-high confidence — see `R4.5-gate-census.md`.
- R4.4 step 3 (2026-10-16, read-only classification, no fixes): all seven remaining r31 nodes + the session-A pollution failure classified with evidence — isolation #1/#2/#17/#18 (+pollution, polluter `tests/test_generation_preflight_route.py` via `main.py` dotenv) and stale #19/#20/#22/#23; zero genuine defects; criterion 7 met in the reconciliation sense, verdict stays NOT PRODUCTION READY — see `R4.4-step3-remaining-failures.md`.
- R4.5 session A3 freeze-integrity classification (2026-10-16, read-only, fixes nothing): nine creative keys all class (2) selection/provenance metadata with verified carriers elsewhere (zero class (3); Scene 002 v1 pins `{}` so no production path silently drops anything — stop condition not triggered); seed lock mutates post-persist (recommend seed-before-freeze, fallback constrained re-persist); F7 store-more recommended (JSON blob, no migration); rejected-list non-empty rule is the only selection-ran evidence — do not relax without controls (options A/B); sequencing F7→F9→F8 before F5, record-shape with F5; 2 implementation sessions + 1 acceptance, medium overall — see `R4.5-sessionA3-freeze-integrity-classification.md`.
- R4.5 session B1 freeze integrity (2026-10-16/17): F7 (compared keys persisted at creation, router-only), F9 (seed decided before freeze, router-only), F8 (`{}` creative freeze + digest-linked selection evidence, router-only) implemented — no check relaxed, Scene 002 byte-identical, four-reference ceiling unchanged; pipeline batch now passes the mutable-input, durable-identity and creative-parity gates and stops fail-closed ONLY at the F5 declaration gate (A2 probe reaches mocked dispatch needing only the TEST-ONLY auth stand-in); 19 new tamper/positive tests green, all baseline nodes unchanged (356 passed), Checkpoint G still fails but at the stale F8 reconstruction pin (`test_r44_step2c_production_path_probe.py:463`, untouched — F5 session to update); remains: F5, record shape, role vocabulary, T1, T2; NOT PRODUCTION READY — see `R4.5-sessionB1-freeze-integrity.md`.
- R4.5 B1 independent review (2026-10-17, read-only, fixes nothing): B1's production changes verified scoped to Router jobs (guards cited), every tamper control shown to bite via 6 throwaway mutation tests (deleted), F8 carriers/readers and F9 fail-soft verified, non-router golden identical, Scene 002 suites 40 green — but two B1 claims corrected: the step-2c probe (passed at every baseline) now fails at `:463` by authorized F8 design while Checkpoint G still fails unchanged at multishot `:459` via provider `:784`, so "0 newly failing" is not supported as worded (report conflates the two files); no vacuous control, no Scene 002/non-router difference, no weakened assertion, no network reached; B2 safe to build on with the stale probe pin corrected in the F5 session — see `R4.5-B1-review.md`.

**Owner decisions D1–D3** (Oct 15): see `R4.3I-owner-decisions.md` — D1 accepted (no change), D2 accepted (by design), D3 simulated-only previs (implementation separate).

**Owner goal (Oct 15, 2026)**: Studio must not be dependent on Runway to work. Independence does not mean eliminating Runway today. It means Runway's limitations stop defining what Studio itself can do. Runway remains the only approved production provider until the owner explicitly authorizes another. Provider independence means a Studio-owned contract, not enabling a second provider.

**Live Runway acceptance: LIVE_VERIFIED (2026-10-17) — single-shot minimal probe completed with output delivered; trace `reports/evidence/live-acceptance/runway-live-trace-20261017T123204Z.json` (task ea6efb69-829c-46fa-ab81-f96a6bb39824, model seedance2_5, 1 dryRun + 1 live POST, 31 task polls). Verdict: NOT PRODUCTION READY (multi-shot + remaining gates still open).**

---

## 1. Executive summary

AI Film Studio has a substantial production architecture in place, including reference management, character casting, training safeguards, production authorization, single-shot reference binding, and a Runway adapter delivery path. However, the Studio is not yet verified as production-ready for multi-shot delivery.

The latest verification establishes that the single-shot reference-binding and authorization chain works through a mocked adapter boundary. It does not establish live Runway acceptance or successful end-to-end film delivery.

The immediate priority is an all-or-nothing multi-shot preflight. Every shot must pass validation before the system creates the first job or contacts a provider. If any shot fails, the batch is rejected with no partial job creation.

### Oct 14 baseline (historical)

| Phase or capability | Status | Evidence or limitation |
|---|---|---|
| R3.2: Generic Runway reference projection | Complete | Dedicated tests verify generic projection and fail-closed behavior. |
| R3.3: Single-shot end-to-end verification | Complete | 439 backend and 34 frontend tests reported green for the focused verification battery. Mocked adapter boundary verified. |
| R4.0: Consolidated readiness audit | Complete | Production readiness remains blocked; multi-shot delivery is not verified. |
| R4.0A: Projection capacity decision | Complete | Option C selected: retain the four-reference ceiling and reject over-capacity bindings. |
| R4.1A: Multi-shot batch preflight | Next implementation phase | Prompt prepared; implementation not yet confirmed. |
| R4.2: Confirmation persistence and recovery | Queued | Confirmation currently depends on transient UI and route state. |
| R4.3: Remaining integrity and traceability gaps | Queued | Must be based on evidence, not assumed fixes. |
| R4.4: Final readiness verification | Queued | Requires reconciliation of unresolved failures and a documented verdict. |
| Controlled live Runway acceptance | Not verified | Mocked success is not live-provider proof. Requires explicit authorization. |
| Room-level reconciliation and readiness audit | Pending | Complete after the agreed production-engine priorities. |

**Important:** A passing focused test suite does not establish that every production route works. A healthy dashboard does not establish that a scene is render-ready.

---

## 2. Canonical architecture and production rules

These rules apply across the project unless the owner explicitly changes them.

### Source of truth

Canonical production truth is owned by FilmLevelMemory, FilmStructure, CreativeSpine, and explicit scene input and approved creator decisions. Derived systems may validate, summarize, or propose changes. They must not silently overwrite canonical production truth.

### Authorization

- The Production Integrity Gate is the final production authorization boundary.
- The Production Integrity Engine is advisory. It must not independently authorize production work or create or submit jobs.
- Authorization must fail closed when required references, decisions, provenance, digests, or contracts are missing, stale, ambiguous, or invalid.
- Training eligibility is not production authorization.
- Creation-time, submit-time, and adapter-level checks remain in force.
- Legacy or direct Runway routes that are explicitly blocked must not be re-enabled through fallback behavior.

### Provider policy

- Runway is the only provider in the currently agreed production workflow.
- Do not invoke a provider, submit a render, or run a live acceptance test without explicit authorization.
- The model router must remain model-agnostic, with no hidden ranking or silent fallback.
- Mocked adapter success must never be reported as live-provider success.

### Reference integrity

- Approved canonical references must remain traceable from the reference library through the frozen shot binding and generation contract to the delivery outcome.
- Storyboard or composition references must remain separate from canonical identity and setting references.
- Required references must never be silently dropped, replaced, or substituted to fit provider capacity.
- Reference confirmation must be verified against the current binding, not trusted merely because the UI previously displayed a confirmation.

### Working-tree safety

The repository has a large pre-existing dirty tree. Treat unrelated changes as user-owned. Do not stage, commit, reset, clean, stash, revert, or discard changes unless explicitly instructed. Keep Studio UI work separate from unrelated design or Replit/Stitch work.

---

## 3. Agreed roadmap and order of work

Follow this sequence. Do not introduce new feature goals or expand scope without the owner's explicit decision.

1. **R4.1A: Multi-shot batch preflight (next).** Validate the entire batch before the first job is created. Any invalid shot rejects the batch with zero jobs created.
2. **R4.2: Confirmation persistence and recovery.** Address confirmation loss on reload, navigation, and recovery. Preserve fail-closed verification against current bindings.
3. **R4.3: Remaining integrity and traceability gaps.** Resolve the remaining verified issues, including evidence linking job creation, frozen contracts, provider outcomes, and delivery records.
4. **R4.4: Final readiness verification.** Re-run the required focused and broader checks, reconcile the outstanding failures, and issue a documented readiness verdict.
5. **Controlled live acceptance and room reconciliation.** Live Runway proof requires separate explicit authorization. Then reconcile the agreed Studio rooms and conduct the end-to-end readiness audit.

Do not automatically start R4.2 after R4.1A. Report the implementation evidence and unresolved decisions first.

---

## 4. R4.0A decision: provider reference capacity

The decision is to retain the current four-reference ceiling and reject bindings that exceed it.

The existing implementation enforces this limit at multiple layers. However, independent re-verification of the external provider documentation was inconclusive. Do not describe the limit as permanently proven or expand it based on assumption.

The implications are:

- A frozen binding containing more than four required references can be legitimate under the current reference requirements.
- The current projection policy does not have an authorized delivery strategy for those over-capacity bindings.
- The system must explicitly reject the affected shot or batch.
- The system must not silently omit, reorder, substitute, or remap required references to force a request through.
- The refusal must be surfaced during preflight, before any job is created.
- A future capacity change requires new evidence and an explicit policy decision. It is not part of R4.1A.

---

## 5. R4.1A implementation requirements

### Required behavior

R4.1A must separate preflight from execution. Preflight must:

- Resolve every shot in the batch.
- Validate required canonical character and setting references.
- Verify approval, provenance, current authorization, and setting authority.
- Verify confirmation digests where required.
- Validate the correct projection policy for each shot.
- Reject v2 projections exceeding the current four-reference capacity.
- Preserve the existing Scene 002 v1 contract.
- Confirm that every shot has the required frozen binding and generation contract.
- Return a structured result for every rejected shot.

Execution must begin only after the entire batch passes preflight. If any shot fails, no jobs may be created and no provider may be contacted.

### Failure reporting

Each failure should identify:

- Shot ID.
- Stable error code.
- Failure category.
- Creator-facing explanation.
- Relevant non-sensitive diagnostic metadata.

An over-capacity error should explain that the current supported capacity has been exceeded. It must not imply that required references were dropped or that a reduced request was submitted.

### Required regression coverage

Tests must demonstrate:

- A fully valid batch passes preflight.
- Invalid shots at the beginning, middle, or end cause zero job creation.
- A valid first shot followed by an invalid later shot cannot create a partial batch.
- Over-capacity bindings are rejected.
- Stale digests and unauthorized or invalid references are rejected.
- Missing or ambiguous setting authority is rejected.
- Existing Scene 002 v1 behavior remains unchanged.
- Generic v2 projection behavior remains unchanged for valid bindings.
- Duplicate or malformed shot identifiers fail safely.
- Rejected preflight paths make no provider calls.
- Existing creation-time, submit-time, and adapter authorization checks remain active.

### Scope boundaries

Do not use R4.1A to:

- Increase the provider capacity limit.
- Implement confirmation persistence.
- Introduce unrelated schema changes.
- Repair unrelated historical failures.
- Bypass authorization to make a test pass.
- Claim production readiness based solely on unit tests.

If the all-or-nothing guarantee cannot be established without a broader persistence or schema redesign, stop and document the limitation rather than silently expanding scope.

Expected report: `reports/studio-readiness-audit-2026-10-14/R4.1A-multi-shot-batch-preflight.md`

---

## 6. Outstanding failures and known limitations

The R4.0 audit accounted for 23 failures. These must not be treated as resolved without new evidence. Known areas include:

- Deferred Previs layer-one gate checkpoint failures.
- R3.1B/F/G failure families and their historical diagnostic discrepancies.
- Historical test-order and event-loop issues, with R2.1's specific combined-test issue subsequently fixed and verified.
- Non-durable confirmation state.
- Partial outcome traceability.
- Live Runway acceptance: LIVE_VERIFIED 2026-10-17 for the single-shot minimal path — trace `reports/evidence/live-acceptance/runway-live-trace-20261017T123204Z.json` (1 primary ref, 16:9, 5s, output delivered). Multi-shot live delivery remains unverified.
- Over-capacity generic reference bindings that currently fail closed.
- Remaining route-propagation and job-row persistence claims that were code-inspected rather than fully proven through live execution.

Keep the two setting-gate failures distinct from the eight deferred Previs layer-one checkpoint failures. Do not reuse historical report counts or identifiers without checking the raw logs and the relevant report.

The full backend baseline previously contained a substantial number of failures. Do not rerun or reinterpret that baseline as part of a narrowly scoped phase unless the phase requires it. Record exactly which tests ran, what passed, what failed, and whether the result is comparable to the previous baseline.

---

## 7. Evidence and readiness language

Use these distinctions in all reports.

| Evidence level | What it establishes |
|---|---|
| Tested | The named automated test passed under the stated conditions. |
| Code-inspected | The implementation appears to contain the required path, but the full behavior was not exercised end to end. |
| Mocked | The path was exercised against a mock or simulated boundary, not the real provider. |
| Live-verified | The actual authorized provider interaction and resulting trace were observed and documented. |
| Unverified | Evidence is absent, incomplete, or insufficient to support the claim. |

Do not collapse these categories into one general statement such as "the pipeline works."

The R3.3 evidence supports single-shot verification through the mocked adapter boundary for generic v2 and Scene 002 v1. It does not prove live acceptance or multi-shot production readiness.

---

## 8. Studio room direction

The rooms should look like authentic professional filmmaking environments, not generic SaaS dashboards. They should have distinct visual identities while remaining part of a coherent Studio world.

Use the existing design system and room patterns rather than inventing a separate visual language for every page. The existing visual direction includes dark cinematic surfaces, amber accents, restrained typography, and reusable reference and training components.

Room reconciliation remains behind the agreed production priorities. Do not start a broad redesign or readiness audit early just because an individual room looks complete.

| Room | Direction |
|---|---|
| Production Desk | A real production control desk for managing production activity. |
| Production Integrity Engine | A technical verification and quality-control console. Advisory only; the Production Integrity Gate retains final enforcement. |
| Reference Space | A visual filmmaking workspace for creating, organizing, comparing, and approving character, outfit, angle, and environment references. |
| Universe | Preserve the existing room. Do not remove or replace it. |

---

## 9. Intelligence, training, and creative ownership

- Meta Muse already exists as the Studio Co-Director/intelligence layer. Do not introduce a duplicate intelligence feature.
- Runway Model Router and Studio intelligence are separate concerns.
- Training approval does not grant permission to use a model or reference in production.
- Character face identity, body identity, appearance, wardrobe, and scene-specific variations must remain distinguishable in the underlying contracts.
- Studio owns dialogue and character voice identity. The audio layer handles voice generation, performance, synchronization, and audio assets.
- Keep disabled scaffolding such as the H3 path disabled by default.
- Prefer reusable production capabilities over hard-coded Scene 002 fixes.
- The R1.2 training hardening requires approved source assets and aligns trigger-word validation with the backend's letters-only contract. R1.3 connects casting candidates to Reference Space without automatically promoting candidates to approved or canonical status.

---

## 10. Deferred work

These goals remain deferred and must not displace the current roadmap. Neither is part of R4.1A.

- **Trailer creation workflows.** Do not prioritize or implement until the agreed production-engine roadmap and readiness work are complete.
- **Reusable Studio opening ident.** The established requirements are:
  - New projects default to `include_studio_ident=True`.
  - Historical projects with the setting unset preserve legacy behavior.
  - The ident is inserted before the first film scene in the final export/re-encode path.
  - It must not be inserted into render or previs generation.
  - Locate and verify the actual Fee Fee Anne Studios opening asset before integration.

---

## 11. Definition of production readiness

Do not declare the Studio production-ready until the relevant evidence demonstrates all of the following:

- A representative multi-shot batch passes preflight and is executed without partial job creation.
- Invalid batches fail before any job creation or provider contact.
- Approved references and canonical setting authority survive the full handoff without silent substitution or loss.
- Confirmation is checked against current binding state and its recovery behavior is verified.
- Production authorization remains enforced at creation, submission, and adapter boundaries.
- Job, contract, request, and outcome evidence can be linked sufficiently to explain what was authorized and what was delivered.
- Historical failures are reconciled using reliable logs and explicit evidence.
- The required broader verification is complete, with remaining failures clearly classified.
- Live provider acceptance is reported separately and is only claimed when an authorized live test has actually occurred.
- Room-level work is reconciled against the agreed roadmap.

A conditional or blocked verdict is appropriate when evidence is missing. Do not change the verdict to READY merely because a new phase's tests pass.

---

## 12. Source reports

Keep these reports as supporting evidence for the canonical brief. Use them for detailed test commands, raw evidence, failure assertions, and implementation-specific findings. Update this brief when a phase changes the verified state.

- `reports/studio-readiness-audit-2026-10-14/R3.2-generic-scene-runway-projection.md`
- `reports/studio-readiness-audit-2026-10-14/R3.3-single-shot-end-to-end-verification.md`
- `reports/studio-readiness-audit-2026-10-14/R4.0-consolidated-readiness-audit.md`
- `reports/studio-readiness-audit-2026-10-14/R4.0A-projection-capacity-decision.md`
- `reports/studio-readiness-audit-2026-10-14/R4.1A-multi-shot-batch-preflight.md` (planned output, not yet confirmed created — Oct 14 wording; exists as of Oct 15, see status update)
- Added since Oct 14: R4.2, R4.3, R4.3A, R4.3D, R4.3F, R4.3G, R4.3H reports in the same folder.

---

## 13. Operating instructions for future sessions

At the start of a Studio work session:

1. Read this brief and the relevant latest phase report.
2. Verify the actual repository branch, commit, working-tree state, and current implementation before assuming prior status still holds.
3. Identify the single next agreed roadmap step.
4. Keep the task scoped to that step and its necessary tests.
5. Preserve existing user changes and production state.
6. Report verified evidence, unverified claims, blockers, open decisions, and the next non-overlapping step.
7. Do not advance to a queued phase automatically.

### Immediate next action (Oct 14 wording; historical — R4.1A, R4.2 and R4.3 are now implemented, see status update)

Run the prepared R4.1A multi-shot batch preflight implementation against the actual current repository. Treat the prompt as an implementation request, not proof that the code already exists. After implementation, inspect the diff and test evidence, verify that rejected batches create zero jobs, and produce the required report. Stop if the guarantee requires broader architectural changes.

Document status: Canonical roadmap brief, baseline October 14, 2026. It records the current decisions and evidence summarized here; it does not replace verification of the repository or the underlying reports.

---

## Appendix: Repo-side notes carried from the earlier reconstruction

The sections below are carried unmodified from the earlier repo-side reconstruction (`AI-Film-Studio-Roadmap-and-Production-Readiness-Brief.pre-merge.md`): its Sections 3–5 and its dated render-batch test line.

## 3. Decisions carried (R4.3F §9, recorded Oct 15)

1. **A — APPROVED:** reconcile-adopted outputs pass the same integrity reviews; no check weakened.
2. **B — REAFFIRMED:** no automatic resubmission of unresolved ambiguous submissions.
3. **C — DEFERRED:** dry-run `submission_attempted` marker scoping not authorized; F-1 remains a documented fail-closed limitation.

## 4. Gap G-5 (R4.3G, closed at route Oct 15; was UNREGISTERED)

`RenderService.create_scene_batch` (`studio-backend/app/services/render.py:5915`), reachable via `POST /projects/{project_id}/scenes/{scene_id}/render-batch` (`studio-backend/app/routes/scene_continuity_intelligence.py:313`), creates N jobs in a loop with per-job `_persist_job` and **no** `preflight_batch_authorization` call, **no** `expected_reference_binding_digests` / `require_persisted_confirmation`, and **no** creation-time reference-capacity check (`create_job` has no count gate). An invalid shot mid-batch raises after earlier jobs are already persisted — partial batch, no rollback. Submit/adapter gates still apply per single job, but nothing enforces batch atomicity. Related single-job paths (`create_and_submit_job` via retry-render; `POST /jobs` via WritersRoom/Sandbox) likewise bypass preflight by design. Absent from R4.3D G-1…G-4 and R4.3F F-1…F-6 under any ID. Disposition per R4.3G: route retired (410 `render_batch_retired`, zero jobs; route-layer only, service untouched). Closure evidenced: POST route test asserts the 410 contract, status test seeds via the service (GET proven working), 33/33 across the three batch files green, exit 0 (Tested). Dormant frontend callers (`createRenderBatch`, unmounted `SceneBatchRenderer`) retained per owner option (b). Related single-job paths still bypass preflight by design — noted, out of scope.

## 5. Path to READY (unchanged, authorization required)

Repair sequence A→G per Phase 4 §remediation, register and adjudicate the §4 gap, fresh full-suite verdict, then R4.3B-gated live acceptance for the provider leg. Nothing staged, committed, or deployed with this brief; no provider calls.

- 2026-10-15: the two render-batch tests in `test_render_batch.py` were updated to the retired contract (POST asserts 410 `render_batch_retired` with zero jobs; status test seeds via the service and asserts GET 200).
