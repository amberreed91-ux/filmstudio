# Checkpoint 5 — Canonical Workflow Threading

## Result

Pass. The repaired Storyboard, Previs, Screening, Editorial, Film Cut, and Revision subsystems now share one durable, service-owned production thread. The thread begins from one approved Storyboard Blueprint version and carries exact identifiers, immutable creative context, continuity, approvals, version lineage, provider provenance, failures, and explicit memory saves through reload.

Checkpoint 6 frontend workflow integration has not been started.

## Canonical sequence

`Project → Script → Scene → Creative/Continuity Context → Approved Storyboard Blueprint Version → Previs → Approved Previs → Production Package → Render Requests/Jobs → Generated Clips → Screening → Screening Approval → Editorial Analysis → Confirmed Editorial Decision → New Film Cut Version → Film Cut Approval → Clip Revision → Revised Render → Explicit Memory Save`

`CanonicalProductionWorkflowService` owns cross-subsystem handoffs. Existing domain services remain authoritative for their own artifacts; the orchestration service does not bypass them or move business logic into routes.

## Repairs

- Added durable `canonical_workflow_runs` and `canonical_workflow_transitions` tables.
- Enforced one run per project, scene, and approved Blueprint version.
- Added an atomic compare-and-set transition operation that persists run state and its event in one transaction.
- Added typed workflow request/response contracts and 15 thin workflow endpoints.
- Captured exact Project, Script, Scene, Sequence, Beat, Blueprint, version, and Storyboard-shot ownership before the first handoff.
- Snapshotted creative intent, shot render contracts, continuity plans, and same-project memory/continuity references into a hashed immutable context.
- Made the approved production package the owner of render-request construction.
- Embedded workflow, package, Blueprint-version, Storyboard-shot, Previs, creative-intent, continuity, camera/staging, and approved-reference provenance in every render request.
- Limited Screening synchronization to the exact workflow render-job IDs; no latest-record discovery is used.
- Required explicit confirmation for Previs approval, Screening approval, Editorial application, Film Cut creation/approval, Revision creation, render retry, and memory save.
- Made Editorial resolve the exact Previs production package and reject missing or cross-project packages instead of falling back to a latest package.
- Preserved analysis/application IDs at the top level of new Film Cut versions and in their metadata.
- Preserved the original render, changed fields, approved cut, Editorial lineage, and unchanged continuity in revisions.
- Added terminal failure persistence and confirmed retry using the same paid render jobs.
- Reused a matching already-persisted production package after interruption instead of duplicating it.
- Kept creative memory explicit-save-only; failed, rejected, or merely generated output cannot enter memory automatically.

## State and approval model

The canonical thread accepts only these forward states: `blueprint_approved`, `previs_generated`, `previs_approved`, `package_ready`, `render_queued`, `render_completed`, `screening_ready`, `screening_approved`, `editorial_analyzed`, `editorial_decided`, `cut_updated`, `cut_approved`, `revision_pending`, and `revision_completed`. Render and revision failure states are durable recovery branches.

Each transition checks its expected prior state. Repeat calls after completion return the canonical persisted run. Every transition has a run-scoped unique idempotency key. Provider polling stops at complete, failed, or cancelled states, and incomplete output is never exposed to Screening as finished.

The thread does not mark the project complete or fabricate a final package. Final-output packaging remains owned by `FinalShortFilmPackageService`; project completion remains gated by an approved final Screening output in the existing Screening state service. This Checkpoint's required trace ends at Revision and persistence reload.

## Integration evidence

The automated trace exercises the complete required workflow with a deterministic local renderer and fresh SQLite/project-store reload. It asserts:

- all 24 required identifier classes;
- exact project/script/scene ownership;
- Blueprint and Film Cut versions;
- emotional objective and provider-request creative intent;
- continuity in the package, initial render, and revision render;
- explicit approval rejection and acceptance;
- exact Editorial package/cut provenance and stale-context protection;
- render idempotency and retry without another render-job creation;
- upstream preservation after downstream failure;
- absence of automatic memory updates;
- explicit memory provenance tied to approved artifacts;
- durable workflow state and unique transition events after process-style reload.

Focused regression result: **113 passed in 57.02s** across route registration, Checkpoints 4A–4D, the new Checkpoint 5 route and trace tests, Storyboard, Previs, Screening, Editorial, Revision, and final-package compatibility tests.

## Exit status

The canonical sequence is implemented and documented; stable IDs, creative intent, continuity, versions, provenance, approvals, failure states, idempotent replay, and persistence are enforced. Invalid ownership and state transitions fail deliberately. The focused checkpoint commit is ready with the requested message.
