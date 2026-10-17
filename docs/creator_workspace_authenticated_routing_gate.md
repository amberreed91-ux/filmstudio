# Authenticated Creator Workspace Routing Gate

**Status:** source-only architecture report. **No adapter, proxy change, session bridge, server, database, or UI change was made.** Evidence is from checked-out source/configuration only. No HTTP requests, process inspection, provider calls, or live database access were performed.

## Decision in brief

Use the Studio's **existing same-origin reverse-proxy boundary**, not a browser-to-runtime connection. In development, a narrowly matched Vite proxy can send only Creator Workspace API paths to the dedicated runtime on an internal loopback port; in production, the existing Nginx reverse proxy is the durable same-origin boundary and can route those same paths to a private runtime service. Keep the browser URL and F51-shaped API contract unchanged. The proxy must preserve the incoming `Cookie` and `Origin`; for Vite, it must also preserve the browser `Host` (`changeOrigin: false`) so the current request-origin check can still compare the browser origin correctly.

The browser sends its cookie to the Studio origin, not to the runtime port. The proxy relays that request header internally. The dedicated runtime then validates the existing session against the same persisted session/user/owner records. Do not trust a project ID alone, mint another token, or bypass existing project-access checks.

This is a **routing recommendation, not authorization to implement it**. The current normal Vite proxy has `changeOrigin: true`, and the current fixture proxy is not authenticated. Neither should be reused unchanged for real Creator Workspace writes. No existing configuration currently routes real Creator Workspace requests to a real dedicated runtime.

## Current browser and API path

- The normal Studio dev server is `http://127.0.0.1:5001` (`host: '127.0.0.1'`, port 5001), with `localhost` also allowed. The actual browser hostname is whichever address the user opened: `localhost` and `127.0.0.1` are distinct cookie hosts. Production serves the frontend and API from the same public Studio host through Nginx on HTTP/HTTPS.
- Studio API helpers use relative paths by default. `fetchJson` calls `fetch(buildStudioApiUrl(path), ...)`; with an empty configured API base the URL stays relative, and Fetch's default credentials mode is `same-origin`. Session checks/sign-in explicitly request `credentials: 'same-origin'`.
- The normal Vite configuration proxies `/api`, `/health`, `/projects`, `/outputs`, and `/previs-assets` to `http://127.0.0.1:8010`. It sets `changeOrigin: true` and `xfwd: true` on those proxy entries. It imports `backendSupervisorPlugin()` as well.
- The production Nginx configuration serves the frontend and proxies `/api/` to the `api_backend` upstream. The current Compose file defines only the production API and Nginx services; there is no dedicated Creator Workspace service/upstream or path-specific Creator Workspace mapping.
- The isolated fixture configuration uses Vite on 5178 and proxies the broad prefix `/api/f51/studio/projects` to `127.0.0.1:8011`. It deliberately omits the backend supervisor and builds a fixture-only HTML entry. The fixture app/runtime is synthetic and has no real-session authentication. Its proxy is not suitable unchanged for real project requests.

Sources: [vite.config.ts](../studio-app/vite.config.ts), [backendSupervisor.ts](../studio-app/backendSupervisor.ts), [vite.creator-workspace-fixture.config.ts](../studio-app/vite.creator-workspace-fixture.config.ts), [studioApi.ts](../studio-app/src/lib/studioApi.ts), [useStudioSession.ts](../studio-app/src/hooks/useStudioSession.ts), [nginx.conf](../studio-backend/deployment/nginx.conf), [docker-compose.yml](../studio-backend/docker-compose.yml), [creator_workspace_fixture.py](../studio-backend/creator_workspace_fixture.py).

## Cookie and browser transport analysis

The login/register handlers call Starlette `Response.set_cookie` with `key='session_id'`, `httponly=True`, `samesite='lax'`, `max_age=86400`, and `secure` set from the request URL scheme. They do not pass a `domain` or `path`; Starlette's `set_cookie` default path is `/`.

| Question | Source-based answer |
|---|---|
| **A. What host receives the cookie?** | The hostname in the browser-visible Studio origin that receives the auth response: typically `127.0.0.1` or `localhost` in dev; the public Studio host in production. No `Domain` attribute means host-only. Port is not part of cookie host matching. |
| **B. What path applies?** | `/` (Starlette's default `path` argument), so `/api/f51/studio/projects/...` is in scope. |
| **C. Will the browser send it to the proposed request origin?** | Yes, when the request remains relative/same-origin on that same Studio hostname. The browser sends it to Vite/Nginx; it does not decide based on the proxy's internal target port. If the user switches between `localhost` and `127.0.0.1`, the other host's cookie will not be sent. |
| **D. Does `Secure` block local transmission?** | The current local Vite origin is plain HTTP, so the auth handler sees HTTP and sets `Secure=false`. On HTTPS, it sets `Secure=true`, and the browser sends it to the HTTPS Studio origin; an internal HTTP hop from the proxy to loopback does not change the browser's cookie decision. Any HTTPS-terminating dev proxy must correctly convey the original scheme to the auth handler; the present Vite config does not set `X-Forwarded-Proto`. No cookie-policy change is proposed. |
| **E. Does `SameSite=Lax` permit it?** | Yes for this same-origin request (which is also same-site). This does not justify cross-site use. |
| **F. Will the dedicated runtime receive the original `Cookie` header?** | Yes if the existing proxy passes request headers normally and no new middleware strips `Cookie`. Vite's proxy entries do not delete it; Nginx's current proxy locations do not blank it, so both forward it by default. The dedicated runtime can read the relayed `session_id` cookie without browser changes. |
| **G. Does proxy forwarding preserve auth semantics?** | It preserves the cookie value/header; changing the upstream target does not itself authenticate the request. Semantics are preserved only if the runtime validates that exact session against the same persisted session store and uses the same user and owner records. Preserve `Origin` too. Do not replace the cookie with a proxy-issued identity header. |
| **H. Is a new cookie/token needed?** | No. The current session cookie is sufficient. No cookie forwarder endpoint, second cookie, bearer token, or session bridge is needed. |

The login response model also contains `session_id`, but the frontend does not store or send that value in its shown session flow. This report proposes no use of that response field; the browser cookie remains the existing session mechanism.

## Authentication and authorization chain

### Current backend path

For an authenticated project request, the current production `ProjectAccessMiddleware` runs before the route. In non-local mode it:

1. The middleware explicitly passes `/api/f51/studio/auth/...` through without project authentication. `POST /login` and `POST /register` authenticate credentials and set the cookie; `GET /session` reads the cookie (or accepted token header), validates it with `AuthService.get_session()`, then resolves the user with `AuthService.get_user()`. `GET /access-mode` reports local mode. `POST /logout` and `DELETE /session` read the session credential and revoke it, then clear the cookie. For non-auth project requests, the middleware reads `session_id` from `request.cookies` (falling back to `X-Session-Token`; an `Authorization: Bearer ...` header overrides either value).
2. For cookie-authenticated mutation requests that include `Origin`, compares that origin against `request.base_url` and configured `settings.cors_origins`; mismatch is denied with 403. It does not inspect `Referer`, and source search found no CSRF-token mechanism in this path.
3. Calls `ProjectAccessService.authenticate()`. That calls `auth_service.get_session(token)`, then `auth_service.get_user(session['user_id'])`, rejecting missing/invalid session or user. The middleware sets `access_user_id` for downstream request context.
4. Gets the caller's project ownership set using `storage.access_owned_projects(user_id)`. For project routes, OpenAPI path matching extracts route parameters and `ProjectAccessService.authorize()` requires the path project ID to be in that owner set. It also validates IDs/project scopes in query/body and fails closed for unknown/global scopes.
5. Only after access validation invokes the route. The Scene Direction route passes to `SceneDirectionService.get/save`; the Creator Workspace browser contract uses `GET|PUT /api/f51/studio/projects/{project}/scenes/{scene}/direction`. Setting-reference endpoints are separately scoped under the same project path.

The chain is therefore **session → persisted user → project owner → route operation**, not project-ID-only authorization.

### Reuse from a dedicated runtime

- `AuthService` has a constructor-level `storage` injection point. Its persisted-storage path validates a session through `storage.get_session()` (the current storage implementation selects only unexpired rows) and resolves the user with `storage.access_get_user()`. Those storage reads do not refresh session activity. A dedicated runtime can instantiate the existing auth service with an explicitly injected, allowlisted repository implementing the required read methods; it need not import `main.py` or start the production lifespan.
- Project ownership is available from the existing storage method `access_owned_projects(user_id)`. The dedicated runtime must execute the same owner-membership check for the path project before every operation, and preserve any route/body resource checks required by that operation.
- The current `ProjectAccessService` is **not safely injectable unchanged**: it imports the global `auth_service` and `project_store`; its constructor only accepts storage. `main.py` binds the global auth service to production storage. A standalone runtime that imports no `main.py` would otherwise encounter the default in-memory global auth service. Reuse requires explicit auth-service injection/refactoring or a small focused verifier that calls the same injected `AuthService` and existing owner-storage policy. Do not import the project-store singleton as an ownership substitute.
- The ordinary `DatabaseStorage` constructor is not an acceptable runtime dependency: source shows it initializes schema and initial data, in addition to database connection setup. A separately injected, migration-free repository is needed for the dedicated process. Its live DB path/schema/journal behavior cannot be established in this report.
- `main.py` owns the normal production lifespan and attaches many unrelated jobs/services. It must not be imported or used as the focused runtime entry point. A focused FastAPI app with explicit dependencies and no production lifespan is feasible in principle.

### Origin, host, scheme, CSRF, and CORS

- Cookie validation itself keys on the session value and persisted session/user records; project access checks use the verified user ID and ownership records. Host and scheme are not the session identity.
- Host/scheme still matter to cookie delivery and origin protection. The local bypass in `ProjectAccessMiddleware` explicitly considers client, Host, Origin and forwarded address, but is not to be enabled for real project requests.
- For cookie-authenticated mutations, the existing middleware's Origin check relies on `request.base_url` plus `settings.cors_origins`. The normal Vite proxy currently has `changeOrigin: true`, which rewrites upstream Host to the target host, while the browser's Origin remains the Vite origin. That can make the existing origin comparison fail on writes unless a matching origin is separately configured. Do not solve that by relaxing the check or broadening allowed origins. A dedicated Vite route must preserve Host (`changeOrigin: false`) and Origin, or be proven to construct the same trusted request-origin context.
- Relative same-origin browser requests require **no CORS**. Proxy-to-runtime traffic is server-to-server, not browser cross-origin. If the browser must call the runtime's different port/origin or the design needs new CORS allowlists, that is unnecessary cross-origin coupling and a reason to reject that design. CORS is not a replacement for the Origin/CSRF check.

## Existing routing mechanisms and suitability

1. **Vite dev proxy — appropriate only as the development routing boundary.** It already receives relative Studio API requests and has a target mapping. Add a more-specific, narrow path matcher for the Creator Workspace API operations, before relying on the `/api` fallback. Do not route all `/api/f51/studio/projects` paths to the dedicated process: that prefix contains many unrelated APIs. Preserve Cookie and Origin, preserve browser Host, and leave auth/session endpoints on the existing auth-capable backend so a login cookie is still issued at the Studio origin. This does not change the frontend URL contract.
2. **Vite backend supervisor — not automatically invoked by proxying.** The plugin middleware only recognizes the exact `/__studio/backend/restart` path, requires POST plus local peer and admin token, and spawns `main:app` on port 8010. A Creator Workspace API request will not match that path and will not restart the backend. Nevertheless, the normal Vite configuration loads this unrelated plugin. It is safe from accidental restart if the API matcher remains narrow and the restart path is not rewritten, but an isolated real-dev config without that plugin provides cleaner separation. Do not use the fixture command as proof of authenticated behavior.
3. **Fixture Vite proxy — useful structural precedent, not a real auth boundary.** It proves a separate config can omit the supervisor and target a distinct backend port, but the current broad project-prefix match, target `8011`, fixture-only frontend entry, `changeOrigin: true`, and lack of real auth/session fallback make it unsuitable unchanged. It could be a starting point for a separate authenticated development config only after narrowing routing and preserving original request headers.
4. **Nginx production reverse proxy — safest existing production boundary.** Nginx already serves the Studio UI and forwards same-origin `/api/` traffic to the API upstream. A more-specific location for only the Creator Workspace route set can precede `/api/` and forward to a private runtime upstream. The browser continues to see the Studio host; the dedicated runtime need not be browser-visible or publish a host port. The current Nginx/Compose source has no such upstream/service yet, so this is an existing mechanism to extend, not an already-working route. A private service and proxy-config change would be separate from, and must not restart, the production API process.
5. **Other mechanisms.** Vite and Nginx are the only source-discovered request-proxy boundaries relevant here. The mobile preview server deliberately strips Cookie, Authorization, Origin, Referer and session-token headers, so it is not suitable. No other app middleware/dev server was found that routes this focused endpoint set to an internal runtime.

## Required report answers (A–T)

**A. Current browser origin.** Development: `http://127.0.0.1:5001` by default (or `http://localhost:5001` if opened under that allowed hostname). Production: the public Studio origin served by Nginx. The session cookie is host-only for the actual hostname used.

**B. Current API routing mechanism.** Relative paths go to the browser's Studio origin. Vite proxies `/api` to `127.0.0.1:8010` in dev; production Nginx proxies `/api/` to `api_backend`.

**C. Current session cookie configuration.** Name `session_id`; HttpOnly; SameSite=Lax; Max-Age 86400 seconds; Secure iff the auth handler sees HTTPS; no Domain attribute; Path `/` via Starlette's default.

**D. Exact authentication request path.** Browser `/api/f51/studio/auth/{access-mode|session|login|register|logout}` and `DELETE /api/f51/studio/auth/session` → current same-origin dev/production API proxy → auth route. Login/register authenticate credentials and issue the session cookie; GET session validates cookie (or an accepted token header) through `AuthService.get_session` then `AuthService.get_user`; logout and DELETE session revoke the supplied session and clear the cookie; access-mode reports the local-mode flag. For project requests, `ProjectAccessMiddleware` separately performs session → user resolution before ownership validation.

**E. Exact authorization request path.** For Creator Workspace `GET|PUT /api/f51/studio/projects/{project}/scenes/{scene}/direction` (and exact setting-reference paths): middleware authenticates first, fetches `access_owned_projects(user_id)`, resolves the matched path scope, requires the project to be owned, then calls the Creator Workspace route/service. Preserve all operation-specific validations and exact setting/reference checks.

**F. Existing proxies/routing discovered.** Normal Vite dev proxy; fixture Vite proxy; production Nginx reverse proxy; mobile-preview Node proxy (explicitly strips the existing session/auth headers and is unsuitable). No other relevant routing boundary was found.

**G. Can an existing proxy preserve the browser Cookie header?** Yes. Both Vite's proxy and Nginx pass request headers, including Cookie, unless explicitly filtered. The current configs do not filter it. The Vite `changeOrigin` Host rewrite is a separate concern; it does not strip Cookie.

**H. Can the dedicated runtime validate the existing session?** Yes in principle, without `main.py` or its lifespan: explicitly instantiate/inject `AuthService` with the same persisted session/user repository, then resolve ownership from the same project's owner records. The current global `ProjectAccessService` wiring is not safely reusable unchanged and needs explicit auth injection or a focused equivalent verifier. The database must not be opened until separately authorized.

**I. Can project ownership enforcement remain unchanged?** Yes semantically: verify the existing session and user, then require the requested project in `access_owned_projects(user_id)` on every request, retaining current route/resource checks. Do not use local bypass, fixture auth, project ID alone, or caller-supplied user identity.

**J. Can relative frontend paths remain unchanged?** Yes. Keep `/api/f51/studio/projects/{project}/...` at the browser and route internally by path. No client migration or UI change is necessary.

**K. Is CORS avoidable?** Yes. The browser continues to call the same Studio origin. No CORS changes are needed or recommended. CORS becoming necessary indicates the design has become cross-origin unnecessarily.

**L. Can Vite safely provide the development boundary?** Yes, with a narrowly matched route, Cookie/Origin preservation, Host preservation (not current `changeOrigin: true` semantics), and no local-auth bypass. The normal config's supervisor does not restart anything for ordinary API paths; an isolated dev config without that plugin is safer and easier to reason about. The fixture config is not ready unchanged.

**M. Is another existing mechanism safer than Vite?** For production, yes: extend the existing Nginx same-origin reverse proxy with a private, path-specific runtime upstream. It is already the deployed frontend/API boundary and avoids exposing the runtime to the browser. It is not currently configured for Creator Workspace and requires a later Nginx/Compose change. For local development, Vite is the natural boundary.

**N. Exact proposed request flow.** `Browser (Studio origin, relative F51 URL)` → browser attaches host-only `session_id` cookie to same-origin `/api/...` request → Vite in dev or Nginx in production matches only Creator Workspace paths and relays Cookie + Origin to the private dedicated runtime (preserving trusted Host/scheme context) → runtime extracts the existing session cookie → injected existing `AuthService` validates persisted session and resolves the user → injected ownership check verifies the path project against that user's existing owner records → scoped Creator Workspace operation runs with explicitly injected storage. Unmatched APIs remain on their existing backend route. Runtime has no direct browser exposure and no production `main.py` lifespan.

**O. Security properties preserved.** Existing session credential and expiry; host-only, Path `/`, HttpOnly, SameSite=Lax and HTTPS-dependent Secure behavior; same-origin browser transport; existing Origin mutation check (must preserve its request context); session-to-user resolution; per-project ownership checks; exact route/resource validation; F51 paths; no new authority, token, or browser-visible runtime; no local bypass; no production lifespan/startup.

**P. Security properties that would change, if any.** None are required to change. The transport gains an internal path-specific proxy hop only. Host/scheme/Origin forwarding must be configured to preserve the existing checks; any cookie-policy, CORS, auth, CSRF, owner-policy, or F51 change is outside this proposal and must stop for a separate security decision.

**Q. Files that would need modification for a later implementation.** For a development-only routing boundary: preferably a new isolated authenticated Vite config based on, but not identical to, [vite.creator-workspace-fixture.config.ts](../studio-app/vite.creator-workspace-fixture.config.ts), plus a package script if needed; or a narrowly scoped change to [vite.config.ts](../studio-app/vite.config.ts) if reusing the normal dev server is explicitly chosen. For production routing: [nginx.conf](../studio-backend/deployment/nginx.conf) and [docker-compose.yml](../studio-backend/docker-compose.yml) to define a private runtime upstream/service. For runtime authentication: a focused app/route, explicit auth/ownership dependency, and allowlisted repository modules/tests under `studio-backend/`. The global `ProjectAccessService` would need explicit auth injection if it is to be reused. No frontend files are required for routing.

**R. Files/systems that must remain untouched for this gate and must stay outside the routing change.** No Creator Workspace UI/API clients or relative URLs; no F51 route namespace or API paths; no cookie/auth/session/CSRF/Origin/CORS/ownership policy; no live DB/data/WAL/SHM; no `studio-backend/main.py` or production lifespan; no port 8010/PID 73674; no provider or production project data. The gate changed none of these.

**S. Is implementation now authorized by the evidence?** **No.** Source evidence selects a technically compatible routing pattern but does not authorize an adapter, runtime startup, proxy modification, database connection, or creator action. This gate explicitly stops at the report; obtain a separate implementation authorization.

**T. Exact next implementation step (only after separate authorization).** Add a **non-starting, testable routing-contract change** in an isolated authenticated-development Vite config: match only the Creator Workspace route set, preserve `Cookie`, `Origin`, and browser `Host`, leave `/api/f51/studio/auth/...` on the existing auth-capable backend, and omit the backend-supervisor plugin. Add config/contract tests using a disposable stub upstream to prove path isolation and header forwarding. Do not start either server. After that passes, implement the dedicated runtime's explicit session/user/owner dependencies and scoped storage; production Nginx/Compose wiring is a separate later deployment decision. No part of that next step is performed here.

## Stop record

Only this new source-only report was created. No implementation, server startup, HTTP request, process inspection, database access, auth/cookie change, F51 change, UI change, session bridge, provider contact, or creator decision occurred. Existing unrelated worktree modifications were left as found.
