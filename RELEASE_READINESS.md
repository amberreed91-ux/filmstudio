# Release Readiness - Studio RC Hardening v1.0

## Snapshot
- Date: 2026-05-13
- Workspace: `/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project`
- Scope: backend stability, frontend build viability, recovery/debug path cleanup, release risk inventory.

## Commands Run
- Backend full suite:
  - `cd studio-backend && pytest -q`
- Frontend production build:
  - `cd studio-app && npm run build`

## Build/Test Outcome
- Frontend build: **PASS**
- Backend full suite: **PARTIAL FAIL**
  - Passed: `1617`
  - Failed: `30`
  - Warnings: `1437`

## Failures By Severity

### Critical
These directly impact demo/public core flows (generation/render/review/revision/package/recovery) or runtime correctness:
- `app/services/test_projects.py::test_generate_short_film_workflow_route_updates_project_and_returns_workflow`
- `app/services/test_projects.py::test_generate_short_film_scene_label_format_creates_scenes`
- `app/services/test_projects.py::test_generate_short_film_default_behavior_unchanged_without_render_chaining`
- `app/services/test_projects.py::test_generate_short_film_submit_renders_creates_jobs`
- `app/services/test_projects.py::test_generate_short_film_submit_renders_handles_provider_failure_gracefully`
- `app/services/test_projects.py::test_generate_short_film_assemble_final_reports_blockers_when_no_outputs`
- `app/services/test_projects.py::test_generate_short_film_submit_renders_mock_success_mode_outputs_urls`
- `app/services/test_projects.py::test_stitch_short_film_endpoint_schema`
- `app/services/test_render_pipeline_hardening.py::test_restart_recovery_completes_rendering_job`
- Root cause highlight: payload/model contract drift in `generate_short_film_workflow_service` (`GenerateShortFilmPayload` being treated as dict via `.get(...)`).

### Medium
Important correctness and persistence consistency; not always first-path blockers but risky for RC:
- `app/services/test_provider_request_service.py::test_minimal_package_request_is_empty`
- `app/services/test_provider_request_service.py::test_is_empty_true_for_minimal_package`
- `app/services/test_provider_request_service.py::test_scene_intent_known_label_appends_guidance`
- `app/services/test_provider_request_service.py::test_scene_intent_absent_leaves_prompt_unchanged`
- `app/services/test_provider_request_service.py::test_scene_intent_unknown_label_appends_only_scene_intent_line`
- `app/services/test_provider_request_service.py::test_scene_intent_append_preserves_original_prompt_prefix`
- `app/services/test_provider_request_service.py::test_sparse_canonical_scene_data_still_builds_runtime_request`
- `app/services/test_render_job_persistence.py::test_backfill_avoids_duplicates`
- `app/services/test_render_job_persistence.py::test_backfill_preserves_output_url`
- `app/services/test_render_job_persistence.py::test_backfill_handles_missing_state_store`
- `app/services/test_render_job_persistence.py::test_historical_job_backfill`
- `app/services/test_style_consistency_service.py::test_visual_continuity_scoring_and_prompt_envelope_integration`

### Low
Config determinism and environment-dependent assertions:
- `app/services/providers/test_providers.py::test_provider_config_deterministic`

### Legacy / Technical Debt
Workflow test surface currently mismatched with runtime storage interfaces and async test plugin assumptions:
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_execute_workflow_success`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_execute_workflow_validation_error`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_execute_workflow_step_failure`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_get_execution_not_found`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_list_executions`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_cancel_execution`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_cancel_completed_execution`
- `app/services/test_workflow_runner_service.py::TestWorkflowRunnerService::test_handle_create_project_step`

## Cleanup Applied (This Pass)

### Dead/Abandoned Debug Paths Removed
- Removed temporary route/tab console debug traces from:
  - `studio-app/src/components/StudioShell.tsx`
  - `studio-app/src/pages/ProductionBoard.tsx`
- Removed request-level debug logging noise from:
  - `studio-app/src/lib/studioApi.ts`

### Import/Startup Blockers Fixed
- Fixed `IndentationError` in:
  - `studio-backend/app/services/generate_short_film_workflow_service.py`
- Replaced invalid `_storage` import usage in:
  - `studio-backend/app/services/workflow_runner_service.py`
  - `studio-backend/app/routes/workflows.py`
  - `studio-backend/app/services/production_recovery_service.py`

### TODO/FIXME Audit
- Searched touched app/backend sources for `TODO` / `FIXME` markers.
- No stale TODO/FIXME markers were removed in this pass because none were surfaced in touched files.

## Known Limitations
- Core short-film workflow payload/model mismatch still breaks multiple project flow tests.
- Workflow runner layer remains partially coupled to storage methods that may not exist on all storage implementations.
- Provider config tests are sensitive to local env values (API key/base URL/timeout).
- Very high warning volume (mostly `datetime.utcnow()` deprecation) still present.

## Recovery Procedures

### Render Recovery
1. Use `POST /api/f51/studio/render/jobs/{job_id}/reconcile` for stalled/failed historical runway tasks.
2. Use `GET /api/f51/studio/render/diagnostics` to inspect queue state, hydration, persistence health, and FFmpeg availability.
3. On backend restart, confirm recovery summary in API logs and verify job statuses in diagnostics.

### Production Board Recovery
1. Trigger safe refresh from Production Board UI.
2. Validate no ghost rows via queue counts in diagnostics.
3. Verify reviews/revisions/packages repopulate from storage.

## Provider Setup
- Expected provider envs:
  - `RUNWAYML_API_SECRET` or `RUNWAY_API_KEY`
  - optional: `RUNWAY_API_BASE_URL`
- Validate provider readiness in DevTools diagnostics:
  - provider status
  - provider availability map
- FFmpeg/FFprobe should be present for keyframe/shot workflows.

## Troubleshooting
- If backend suite fails during collection/import:
  - check for missing or invalid `_storage` imports.
  - check syntax/indentation in service modules loaded by `main.py`.
- If workflow generation fails:
  - verify request payload type compatibility (`pydantic model` vs `dict` assumptions).
- If provider tests fail locally:
  - sanitize env-dependent expectations or isolate env in test setup.

## Architecture Summary
- Routes: thin HTTP translation + validation/response shaping.
- Services: own business logic, orchestration, recovery, and persistence workflows.
- Providers: adapter boundary for external generation systems.
- Storage: SQLite-backed canonical persistence (projects, jobs, reviews, revisions, packages, media intelligence).
- Frontend orchestration: room-level state + DevTools diagnostics overlay (hidden in production mode unless dev mode enabled).

## Manual QA Status
Requested checklist:
- project creation
- rendering
- stitching
- soundtrack
- review
- revision
- packaging
- reload recovery
- backend restart recovery

Status in this pass:
- **Partially covered via automated backend tests and route/service checks.**
- **Full browser-driven manual QA was not fully completed in this pass** due outstanding critical backend failures in short-film generation/stitching workflow tests.

## Release Readiness Score
- **68 / 100**

Rationale:
- Strong baseline: frontend production build passes; backend pass count is high (1617).
- Blocking risks: 30 backend failures concentrated in workflow-critical paths and persistence/recovery coupling.

## Remaining Blockers
1. Fix `GenerateShortFilmPayload` handling in `generate_short_film_workflow_service` (model vs dict access).
2. Stabilize workflow runner/storage interface expectations and related tests.
3. Resolve render job persistence/backfill regressions.
4. Resolve provider request service prompt-shaping regressions.

## Stabilization Recommendations (Next)
1. Introduce strict typed DTO adapter inside `handle_generate_short_film_request` and update tests to one canonical payload path.
2. Add storage capability guards + protocol interface for workflow runner to avoid implicit method assumptions.
3. Resolve backfill contract mismatches with focused fixtures; re-run `test_render_job_persistence.py` suite.
4. Add a CI pre-merge gate for collection errors (`pytest --collect-only`) before full run.
5. Schedule a dedicated deprecation cleanup for `datetime.utcnow()` warnings to reduce future runtime drift risk.
