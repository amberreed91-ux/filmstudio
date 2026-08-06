# Required negative-test matrix

All ten required cases passed. HTTP cases returned deliberate structured errors or idempotent success without duplicate records; service-level failure cases were run in the 76-test focused backend suite recorded in `../test_logs/backend_focused.xml`.

| Required case | Evidence | Verified behavior |
| --- | --- | --- |
| Unknown project | `../browser/live_session/browser_evidence.json` | Browser received structured `Project not found`; the error was visible in `03_unknown_project_visible_error.png`. |
| Scene belonging to another project | `test_checkpoint_3_backend_integrity.py::test_scene_review_and_film_cut_reject_cross_project_scene_ids` | HTTP 422; canonical project state remains unchanged. |
| Unknown shot | `live_idempotency_and_unknown_shot.json` | Live render-contract request returned 404 `state_error`, `Storyboard shot not found`. |
| Stale Storyboard version | `test_storyboard_blueprint_routes.py::test_storyboard_render_rejects_stale_approved_version` | HTTP 409; stale approved version cannot render. |
| Invalid approval transition | `test_checkpoint_3_backend_integrity.py::test_workflow_rejects_cross_project_and_repeated_gate_decisions` plus clean reproduction unconfirmed approvals | Closed/repeated gate returns 409; unconfirmed canonical approval boundaries return 422. |
| Missing media | `test_checkpoint_4c_screening_room_integrity.py::test_media_route_supports_ranges_and_returns_useful_missing_error` | Missing playback returns a deliberate structured error; unsafe or missing media never appears playable. |
| Duplicate render submission | `live_idempotency_and_unknown_shot.json`; clean reproduction step `production render duplicate submission prevented` | Replay returned the durable terminal run and created zero render jobs or transitions. |
| Failed provider job | `test_checkpoint_5_canonical_workflow_thread.py::test_render_failure_is_recoverable_without_erasing_upstream_or_creating_memory` | Failure persists as `render_failed`; no Screening/memory success; confirmed retry reuses the existing render job. |
| Invalid Film Cut version | `test_checkpoint_4d_editorial_revision_integrity.py::test_film_cut_route_maps_stale_update_to_conflict` | HTTP 409 `stale_film_cut`; current version is not mutated. |
| Repeated editorial application | `live_idempotency_and_unknown_shot.json` | Replay returned the durable terminal run and created zero applications or transitions. |
