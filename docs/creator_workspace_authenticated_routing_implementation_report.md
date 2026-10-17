# Creator Workspace Authenticated Routing Implementation Report

**Scope:** Development routing boundary only, as authorized by `creator_workspace_authenticated_routing_gate.md`. No runtime process was started by the implementation or tests; a dedicated runtime target is reserved but remains a stub/unavailable. No real storage adapter is implemented.

## A. Files changed

- `studio-app/creatorWorkspaceRouting.ts` — exact route matchers, proxy options, and runtime-target safety validation.
- `studio-app/vite.creator-workspace-authenticated.config.ts` — isolated Vite config on port 5179; omits Studio backend supervisor and broad proxy routes.
- `studio-app/tests/creatorWorkspaceRouting.test.ts` — disposable proxy/upstream integration tests.
- `studio-app/package.json` — adds `dev:creator-workspace-authenticated` script. The file already had other concurrent modifications when this task began; those unrelated edits were preserved.
- `studio-app/package-lock.json` already had unrelated concurrent dependency/test-library edits at task start; I did not modify or stage it. It remains dirty and is intentionally not part of this implementation.

## B. Files intentionally untouched

The normal Vite config and fixture Vite config, fixture runtime, all browser API clients/relative paths, F51 route definitions and API schemas, auth/session/middleware and cookie configuration, project ownership enforcement, `main.py`, production lifespan, backend storage and DB, Nginx/Compose, production configuration, and all unrelated dirty files. In particular, port 8010/PID 73674, live data, and services were not inspected, contacted, stopped, signaled, or restarted.

## C. Exact proxy/routing mechanism

A separate Vite 8 development configuration uses its built-in reverse proxy via `server.proxy`. The proxy uses anchored route regexes, method gates, no request rewrite, `changeOrigin: false`, `xfwd: false`, and no injected headers/auth options. The isolated dev config does not import `backendSupervisorPlugin` and does not define a catch-all. `CREATOR_WORKSPACE_AUTH_TARGET` is required and validated as a credential-free loopback HTTP(S) origin; the runtime target defaults to loopback port 8012 and must remain distinct from auth, fixture, 8010, and 8011. This is just a routing destination; it does not start or implement that runtime.

## D. Exact routes intercepted

Sent to the dedicated runtime:

- `GET|PUT /api/f51/studio/projects/{project}/scenes/{scene}/direction`
- `GET|POST /api/f51/studio/projects/{project}/setting-references/{setting}`
- `POST /api/f51/studio/projects/{project}/setting-references/{setting}/upload`
- `POST /api/f51/studio/projects/{project}/setting-references/{setting}/{reference}/approve`
- `POST /api/f51/studio/projects/{project}/setting-references/{setting}/{reference}/canonical`

Path segments are matched as individual non-empty segments; only an optional query string is allowed after the complete endpoint. Unsupported methods do not go to the runtime.

The existing auth endpoints use a separately configured auth-capable loopback target. The config serves Vite's ordinary `index.html` entry (the existing Studio UI); it adds no fixture-specific entry or frontend API-path changes. This keeps the login/session flow routable while leaving unrelated APIs unproxied:

- `GET /api/f51/studio/auth/access-mode`
- `GET|DELETE /api/f51/studio/auth/session`
- `POST /api/f51/studio/auth/login`
- `POST /api/f51/studio/auth/register`
- `POST /api/f51/studio/auth/logout`

## E. Exact routes excluded

Everything else: unrelated `/api` routes; other `/api/f51/studio/projects/...` endpoints (including broad project APIs); other F51 namespaces; auth endpoints not listed above; unsupported methods; prefix/suffix lookalikes and extra path segments; and non-API paths. These are not intercepted by this config and are left to normal Vite handling, not forwarded to the Creator Workspace runtime or auth target.

## F. Host behavior

`changeOrigin: false` preserves the incoming browser Host. A disposable-upstream test sent `Host: studio.example.test:5179` and confirmed that exact Host reached the runtime. The tests also verify that the proxy target remains the dedicated runtime, not a browser-visible URL.

## G. Origin behavior

Origin is relayed unchanged. The integration test confirmed the supplied `Origin: http://studio.example.test:5179` reached the upstream verbatim. No Origin validation or CSRF policy was weakened or changed. The Vite proxy implementation rewrites WebSocket Origin only when its opt-in `rewriteWsOrigin` is true; these HTTP-only routes do not enable WebSockets or that option.

## H. Cookie behavior

The existing browser Cookie header is forwarded by Vite without adding, translating, filtering, or replacing credentials. Test verified the exact existing `session_id=existing-session-value` header at the runtime and auth upstream. No cookie attributes or issuance behavior changed.

## I. Referer behavior

When supplied, Referer is forwarded unchanged; the integration test confirmed the value at the runtime upstream. Referer is not used as a replacement for Origin validation or authentication.

## J. Authentication behavior

No token, auth header, proxy identity, user identity, or synthetic credential is created. Tests verify no Authorization, `X-Session-Token`, or user header is introduced. Existing login/session/logout endpoints route to the explicitly configured auth-capable upstream. Project API requests carry the browser's existing Cookie to the dedicated runtime. **The runtime is not implemented or started in this gate, so this report does not claim live session validation has been exercised.**

## K. Project ownership behavior

The routing boundary does not set user/project identity or change ownership policy; it forwards the unchanged request and path. The required dedicated runtime must still validate the existing session, resolve the user, and enforce existing per-project ownership before an operation. That runtime verifier is a remaining blocker, not implemented here. Tests assert no auth/ownership bypass headers, hardcoded project scope, or global project proxy are present.

## L. Production impact

None. No Nginx or Compose file, production API service, or production route was modified. Production path-specific configuration remains a later separate decision.

## M. Tests added and results

`studio-app/tests/creatorWorkspaceRouting.test.ts`: **8 passed**. With disposable loopback-only stub upstreams it verifies relative F51 routing, exact route/method scope, excluded routes, unchanged Host/Origin/Cookie/Referer, auth endpoint routing, no injected auth or ownership context, isolated-runtime separation, and rejection of ports 8010 and 8011 as runtime destinations.

TypeScript check for the changed config/module/test: passed using `tsc --ignoreConfig` with explicit node/bundler compiler options. Existing fixture regression: `studio-backend/tests/test_creator_workspace_fixture_runtime.py`, **6 passed**. No full Studio suite was run.

One standalone CLI invocation was initially rejected by TypeScript 6 because it detected a tsconfig while files were specified; reran correctly using `--ignoreConfig`. The focused Vite command was also intentionally tried with auth target set to port 8012 (same as the default runtime) and correctly refused to load due to target-separation validation. No server started in that attempt.

## N. Proof port 8010 was not contacted

- No HTTP request, process/listener inspection, or backend startup command to 8010 was made.
- The new isolated dev config contains no route targeting 8010 and omits the normal backend supervisor. Runtime-target validation rejects port 8010 before config load.
- Tests used dynamically allocated disposable loopback ports for both stubs and asserted that 8010 is forbidden. The only textual inspection was source/test inspection of current configuration; no reachability check was made.
- No PID inspection or signaling was performed, including PID 73674.

## O. Proof no live database was accessed

No database files were opened/read, no DB adapter or normal backend module was imported by these changes, no DB connection code was run, and no live API process was contacted. All integration tests used ephemeral in-memory Node HTTP stub servers. The pre-existing synthetic fixture test suite passed independently.

## P. Proof no providers/jobs/workers were contacted or started

No production backend, runtime, provider, job queue, render/training recovery, or worker was started or contacted. The Vite config excludes the backend supervisor and production runtime imports; only the frontend test runner and disposable local Node stub servers ran. No preflight or recovery action was run.

## Q. F51 status

Unchanged. Browser relative `/api/f51/...` URLs, F51 route names and API contract remain intact; the proxy preserves the exact request path and query string.

## R. Remaining blocker

The dedicated authenticated Creator Workspace runtime is still absent/unavailable. It must be separately implemented with explicit dependencies that validate the existing session, resolve the same user, enforce project ownership, and inject scoped storage, without importing `main.py`, production lifespan, global store, recovery, workers, or provider adapters. No authenticated real request can be completed safely until that runtime exists and its access boundary is independently verified.

## S. Exact next step

Stop at this gate. After separate authorization, implement and test the dedicated runtime’s explicit session → user → project-owner dependency and injected read/write storage adapter in a way that does not open the live database until that later storage gate explicitly authorizes it. Production Nginx/Compose wiring remains separate. Do not start the runtime, open the live database, or proceed with real Scene 002 storage under this gate.
