# Checkpoint 3 hunk summary

The worktree baseline showed pre-existing modifications in both files touched by Checkpoint 3:

- `studio-backend/app/services/storyboard_blueprint_service.py`
- `studio-backend/tests/test_storyboard_blueprint_routes.py`

The full file diffs therefore include unrelated pre-existing hunks. The intentional Checkpoint 3 hunks are:

## `studio-backend/app/services/storyboard_blueprint_service.py`

Checkpoint 3 added lifecycle validation to `StoryboardBlueprintService.render_storyboard_shot()`:

- replaced the direct shot existence check with a call to `_validate_shot_renderable()`,
- added `_validate_shot_renderable()` immediately before `link_render_job()`.

The new guard rejects:

- missing storyboard shot, blueprint, or version,
- storyboard shots without an approved blueprint version,
- stale storyboard shot versions where `shot.version_id` does not match both `blueprint.current_version_id` and `blueprint.approved_version_id`,
- versions whose persisted status is not `approved`,
- shots whose persisted status is not approved/renderable,
- shots with render blockers.

Checkpoint 3 did not add the pre-existing continuity review methods shown elsewhere in the full file diff.

## `studio-backend/tests/test_storyboard_blueprint_routes.py`

Checkpoint 3 added route-level regression coverage:

- draft storyboard render returns `422`,
- draft storyboard render creates no render job,
- draft storyboard render creates no storyboard render link,
- approved storyboard render still succeeds,
- stale approved-version render returns `409`.

The continuity-review approval prerequisite assertions that were already present in the baseline diff were preserved and used by the new tests, but they are not claimed as new Checkpoint 3 work.
