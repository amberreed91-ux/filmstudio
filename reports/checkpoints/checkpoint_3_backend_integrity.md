# Checkpoint 3 — Backend Contracts, Versioning, Approval, and Persistence Integrity

Verdict: **CHECKPOINT 3 PARTIALLY COMPLETE**

This checkpoint repaired one runtime-confirmed backend integrity defect in the canonical Storyboard Blueprint to render handoff.

The larger Checkpoint 3 audit surface remains broader than this repair. No claim is made that every listed priority system has been exhaustively repaired.

## Baseline Safety

Required baseline was captured before editing:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/worktree_baseline.txt`

The baseline showed substantial unrelated pre-existing worktree changes across frontend files, backend routes/services/tests, backend data files, scripts, and Studio Brain library files.

Checkpoint 3 intentional code changes were limited to new hunks in:

- `studio-backend/app/services/storyboard_blueprint_service.py`
- `studio-backend/tests/test_storyboard_blueprint_routes.py`

Both files already contained pre-existing modifications at baseline. Exact Checkpoint 3 hunk ownership is documented in:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/diff_review/checkpoint_3_hunk_summary.md`

Checkpoint 3 evidence artifacts were added under:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/`

## Authoritative Inputs Used

- `reports/checkpoints/checkpoint_1_repository_mapping.md`
- `reports/checkpoints/checkpoint_2_route_repair.md`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_1/feature_endpoint_summary.md`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_1/sqlite_table_inventory.txt`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_2/after_fixes/route_registration_defects.txt`

Canonical ownership used:

- `StoryboardBlueprint` is canonical.
- `storyboard_wall` is a legacy projection.
- `Previs` is canonical.
- `ScreeningRoom` is canonical.
- No `Precise`, `Theatre`, or backend `Theater` implementation was introduced.

## Baseline Test Evidence

Before editing, the focused backend checkpoint suite passed:

- Command: `./.venv/bin/python -m pytest tests/test_checkpoint_2_route_registration.py app/routes/test_recommended_duration_route.py app/routes/test_studio_workflow_routes.py app/routes/test_studio_knowledge_routes.py app/services/test_render_create_route.py tests/test_storyboard_blueprint_routes.py -q`
- Result: `22 passed`
- Evidence: `reports/evidence/endpoint_workflow_integrity/checkpoint_3/backend_focused_tests_before.txt`

## CP3-BI-001 — Draft storyboard shots could create render jobs

Status: **Repaired and verified**

Systems:

- Storyboard Blueprint
- Storyboard Blueprint versions
- Storyboard shots
- Render requests
- Render jobs
- Project ownership
- Scene ownership
- Shot ownership
- Version validation
- Stale-version rejection
- Approval enforcement
- Provenance persistence

### Finding

`POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render` could create a render job for a draft storyboard version before creator approval.

The route correctly went through `StoryboardBlueprintService`, but `render_storyboard_shot()` only checked that the shot existed and belonged to the blueprint. It did not validate:

- the blueprint had an approved version,
- the shot belonged to the current approved version,
- the persisted version status was approved,
- the shot status was approved or otherwise renderable,
- the shot had no render blockers.

### Reproduction

The failure was reproduced through the real HTTP route using `TestClient`.

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/storyboard_unapproved_render_repro_before.txt`

Before the repair:

- Create draft storyboard blueprint: `200`
- Draft blueprint status: `draft`
- Draft shot status: `ready`
- Render draft shot: `200`
- Render job created with storyboard metadata from an unapproved version

### Root Cause

The render handoff path lacked service-layer lifecycle validation. The route had no project or scene path parameters, so backend ownership and version integrity had to be enforced by the canonical service before render job creation.

### Repair

Added `StoryboardBlueprintService._validate_shot_renderable()`.

The render handoff now rejects:

- missing shot/blueprint/version,
- storyboard shots without an approved blueprint version,
- shots belonging to stale non-current versions,
- versions not marked `approved`,
- shots not in an approved/renderable lifecycle state,
- shots with render blockers.

The route remains thin and continues to delegate to the canonical service.

### Regression Tests

Strengthened `studio-backend/tests/test_storyboard_blueprint_routes.py`:

- draft storyboard render is rejected with `422`,
- approved storyboard render still succeeds,
- stale-version render is rejected with `409`,
- render links preserve the approved storyboard version id.

Focused storyboard test result:

- Command: `./.venv/bin/python -m pytest tests/test_storyboard_blueprint_routes.py -q`
- Result: `3 passed`
- Evidence: `reports/evidence/endpoint_workflow_integrity/checkpoint_3/storyboard_blueprint_tests_after.txt`
- Final rerun evidence: `reports/evidence/endpoint_workflow_integrity/checkpoint_3/test_logs/focused_storyboard_render_handoff.txt`

Focused backend checkpoint suite after repair:

- Command: `./.venv/bin/python -m pytest tests/test_checkpoint_2_route_registration.py app/routes/test_recommended_duration_route.py app/routes/test_studio_workflow_routes.py app/routes/test_studio_knowledge_routes.py app/services/test_render_create_route.py tests/test_storyboard_blueprint_routes.py -q`
- Result: `23 passed`
- Evidence: `reports/evidence/endpoint_workflow_integrity/checkpoint_3/backend_focused_tests_after.txt`
- Final rerun evidence: `reports/evidence/endpoint_workflow_integrity/checkpoint_3/test_logs/focused_checkpoint_3_backend_suite.txt`

Test integrity review:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/test_logs/test_integrity_review.md`

### HTTP and Persistence Verification

After the repair:

- Draft render route returns `422` with structured `validation_error`.
- Draft render creates no `storyboard_render_links` record.
- Continuity review route returns `200`.
- Approval route returns `200`.
- Approved render route returns `200`.
- Created render job includes storyboard metadata:
  - `blueprint_id`
  - `version_id`
  - `storyboard_shot_id`
  - `project_id`
  - `scene_id`
  - `shot_id`
  - `shot_number`
- Stored `storyboard_render_links` record preserves the approved `version_id`.
- A fresh `StoryboardBlueprintService` instance reads back the same current version, approved version, shot version, and approved shot status.

Evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/storyboard_render_approval_after_http_persistence.txt`
- Final rerun evidence: `reports/evidence/endpoint_workflow_integrity/checkpoint_3/runtime_http/final_storyboard_render_handoff_http.txt`

## Deferred / Not Repaired In This Pass

The full Checkpoint 3 priority list includes many backend systems beyond the repaired Storyboard Blueprint render handoff. Those systems were not broadly redesigned or exhaustively repaired in this pass.

Deferred broader Checkpoint 3 areas include:

- full request and response contract matrix,
- exhaustive project, scene, and shot ownership testing,
- complete dual-storage audit,
- full restart-persistence matrix,
- complete provider-failure matrix,
- complete idempotency matrix,
- complete approval and state-transition matrix,
- exhaustive live HTTP coverage across all priority backend systems.

No new `Precise`, `Theatre`, or backend `Theater` implementation was created.

No broad frontend workflow repair was performed.

## Diff Evidence

Final diff evidence:

- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/diff_review/storyboard_blueprint_service.diff`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/diff_review/test_storyboard_blueprint_routes.diff`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/diff_review/checkpoint_3_hunk_summary.md`
- `reports/evidence/endpoint_workflow_integrity/checkpoint_3/diff_review/status_after_fixes.txt`

Unrelated pre-existing worktree changes remain unstaged and outside this Checkpoint 3 repair scope.
