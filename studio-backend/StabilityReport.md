# Stability Audit Pass v1.0

## Scope
- project creation
- scene generation and one-button short film generation
- render submission and polling
- stitching and soundtrack path
- review and revision creation/decision
- packaging

## Weak Spots Found
- Missing/empty payload fields could enter workflow (`title`, `output_url`, `final_output_url`).
- Render polling had no explicit timeout guard in the one-button path.
- Duplicate or stale polling risk (same job id reused in loop) was not explicitly guarded.
- Stage-level observability was inconsistent across project/render/stitch/package phases.
- Review decision transition accepted broad unvalidated input shape.
- Stitch soundtrack could be enabled without a concrete audio source.
- Hydration mismatch risk after project update (missing `execution_summary`) had no explicit guard.

## Fixes Applied
- Added structured stability error classes in `app/services/stability.py`:
  - `validation_error`
  - `provider_error`
  - `state_error`
  - `persistence_error`
  - `playback_error`
- Added consistent stage logging helper with:
  - `project_id`
  - `job_id`
  - `provider`
  - `stage`
  - `duration_ms`
- Hardened `app/routes/projects.py`:
  - Project creation default/validation and persistence payload sanity checks.
  - One-button render path:
    - duplicate polling/job-id guard
    - provider polling timeout guard
    - per-shot and full-flow stage logging
  - Stitch path:
    - soundtrack enabled requires `audio_url` or `local_audio_path`
    - invalid stitch payload guard
  - Review path:
    - required non-empty `output_url`
    - validated decision transitions (`approve`, `revise`, `reject`)
  - Revision path:
    - required `review_id` and `original_job_id`
  - Packaging path:
    - required `final_output_url`
    - structured persistence error mapping
  - Hydration integrity check after short-film project update.

## Additional Reliability Fixes
- Added missing semantic-search listing method used by status workflows:
  - `SemanticSearchService.list_analyses_for_asset(...)`

## Remaining Risks
- Some long-tail workflows in specialized route modules/services still rely on implicit payload assumptions and could benefit from the same stage/error wrapper pattern.
- Polling strategy in one-button path is still intentionally short and bounded; full production reconcile loops remain in dedicated render/reconcile flows.
- Frontend bundle size warning remains (non-blocking).

