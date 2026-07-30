# Checkpoint 3 test integrity review

Changed test file:

- `studio-backend/tests/test_storyboard_blueprint_routes.py`

## Why the test changed

The Storyboard Blueprint render handoff route could create render jobs from draft and stale storyboard versions. The route-level regression tests were strengthened to prove the backend service guard through the same HTTP surface used by callers.

## Assertions added

- Draft storyboard render returns HTTP `422`.
- Draft storyboard render error text includes `Approve storyboard version`.
- Draft storyboard render leaves `render_service.list_jobs(project_id=project_id)` empty.
- Draft storyboard render leaves `storyboard_render_links` empty for the project shot.
- Approved current-version storyboard render still returns HTTP `200`.
- Approved render job persists storyboard metadata and render link version id.
- Stale storyboard render returns HTTP `409`.
- Stale storyboard render error text includes `stale storyboard version`.

## Assertions removed

None.

## Assertions loosened

None.

## Mocks added

None.

## Fixtures changed

None.

## Test data changed

Fresh UUID-based project identifiers remain in use. A stale-version regression mutates only the persisted `current_version_id` for its isolated test project to simulate a newer current version while preserving the approved shot's original version.

## Tests skipped, deleted, or renamed

- Skipped: none.
- Deleted: none.
- Renamed: none.

## Coverage assessment

Coverage became stronger. No test was weakened, no failing test was hidden, no mock replaced the actual guard behavior, and no fixture was changed to avoid the broken path. Exact route status codes and rejected-request job/link behavior are asserted.
