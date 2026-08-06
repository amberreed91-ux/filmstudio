# Checkpoint 2 continuation test-integrity review

No tests were deleted, skipped, renamed, or weakened.

Strengthened backend assertions in `studio-backend/tests/test_checkpoint_2_route_registration.py`:

- all normalized HTTP method/path registrations must be unique;
- no earlier dynamic route may shadow a later static route for the same method;
- every schema-included runtime operation must match the generated OpenAPI operation set;
- final-export static routes must precede the generic artifact route;
- canonical Co-Director debate routes must be mounted exactly once.

Added frontend assertions:

- `buildStudioApiUrl()` cannot duplicate an `/api` suffix;
- the active Co-Director debate client uses the mounted canonical prefix and POST method;
- final export trigger/status/download URLs and methods match backend routes;
- film stitching trigger/status/download URLs and methods match backend routes.

Mocks are limited to `fetch` response isolation in frontend URL-construction tests. They do not replace backend runtime verification; separate live HTTP evidence is preserved under `runtime_http/`.
