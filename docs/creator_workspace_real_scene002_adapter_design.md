# Real authenticated Scene 002 Creator Workspace — pre-implementation design

**Status:** source-only design; no implementation or live-state verification performed.  
**Scope:** connect the existing Creator Decision Workspace to the real authenticated Scene 002 project while preserving explicit creator decisions and the existing versioned draft semantics.  
**Gate outcome:** a dedicated, narrowly scoped process is technically feasible in principle, but the current service graph is not safe to reuse unchanged. Several import-time/global dependencies must first be isolated or replaced. No claim is made that the current database, project, owner, session, or canonical reference is present or accessible.

## Evidence boundary and non-actions

This report is based on checked-out source, tests, documentation, and repository history only. The isolated fixture proves the UI workflow, not access to real Scene 002. No server was started; no request was sent; no process, port 8010, or PID 73674 was inspected; no live SQLite file was opened, read, hashed, or changed; and no provider, queue, render, training, preflight, or creator-decision action was performed. No tests were run for this report.

Paths and identifiers such as `project_5907c60cddbc`, `loc-c8f88b9c`, and the UI's active scene/version are source-level contract values, not confirmation of current database contents. The actual scene-to-setting mapping, current blueprint/version, reference rows, database schema/version, session validity, project owner, and database location remain unverified.

## A. Real Creator Workspace dependency graph

```text
PrevisRoom (active project + scene + storyboard version)
  └─ CreatorDecisionWorkspace
      ├─ SettingReferenceAuthorityPanel
      │   └─ settingReferenceApi
      │       ├─ GET  exact setting references (sync-free)
      │       ├─ POST create URI candidate (explicit)
      │       ├─ POST upload candidate (explicit + filesystem write)
      │       ├─ POST approve exact candidate (explicit)
      │       └─ POST designate exact candidate canonical (explicit)
      └─ SceneDirectionPanel
          └─ useSceneDirection
              └─ sceneDirectionApi
                  ├─ GET /api/f51/studio/projects/{project}/scenes/{scene}/direction
                  │   └─ Scene Direction route → SceneDirectionService.get
                  └─ PUT same path with expected_version_id + all explicit choices
                      └─ route → SceneDirectionService.save
                          ├─ StoryboardBlueprintService read/clone helpers
                          ├─ coverage contract + canonical dialogue extraction
                          ├─ canonical setting resolution + exact reference validation
                          └─ storage transaction: insert successor bundle and move current pointer
```

The frontend is intentionally a decision surface, not a readiness or generation surface. Setting authority, selecting a reference for Scene Direction, coverage choices, and per-shot handoffs are separate. The Scene Direction save is an explicit review/confirmation and writes a draft successor; it does not mutate the approved source version or mark the scene READY.

Source anchors: [CreatorDecisionWorkspace.tsx](../studio-app/src/components/CreatorDecisionWorkspace.tsx), [SceneDirectionPanel.tsx](../studio-app/src/components/SceneDirectionPanel.tsx), [useSceneDirection.ts](../studio-app/src/hooks/useSceneDirection.ts), [sceneDirectionApi.ts](../studio-app/src/lib/sceneDirectionApi.ts), [settingReferenceApi.ts](../studio-app/src/lib/settingReferenceApi.ts), [scene_direction.py](../studio-backend/app/routes/scene_direction.py), [scene_direction_service.py](../studio-backend/app/services/scene_direction_service.py).

## B. Exact read path for Scene 002

The active project, scene, and current storyboard version are selected by the host UI. GET accepts project and scene; the service loads the current blueprint/version and its shots, then builds a response. It does not take the UI's version as authority; the route returns the current stored version ID for optimistic save.

Required source reads and their purpose:

| Read | Purpose | Classification |
|---|---|---|
| `get_project(project_id)` | Find the canonical scene in `execution_summary.scenes`; supply screenplay/source text, character names, and project context to coverage derivation. | SAFE READ, but only via injected storage/project reader; current fallback reaches global `project_store`. |
| `get_storyboard_blueprint(project_id, scene_id)` | Resolve blueprint and `current_version_id`. | SAFE READ. |
| `get_storyboard_blueprint_version(current_version_id)` | Load version status, metadata, saved decisions, setting selection, and source version identity. | SAFE READ. |
| `list_storyboard_shots(blueprint_id, current_version_id)` | Build shot identities, locks, continuity handoffs, frames, and the allowed targets for decisions. | SAFE READ. |
| `list_storyboard_blueprint_versions(blueprint_id)` | Determine successor version number on save. | SAFE READ. |
| `get_universe_nodes(...)` / the equivalent canonical universe read used by `resolve_canonical_setting_id` | Resolve the exact setting entity for the selected scene. | SAFE READ. Must not infer setting from scene ID, image, URI, or legacy reference. |
| `list_reference_assets(project_id, target_type='setting', target_id=<resolved setting>, limit=200)` | Produce offerable, exact-target approved/canonical environment options. The service filters project/target/type/kind/approval/canonical state and excludes the legacy ID. | SAFE READ. Do not call the generic reference-library GET. |
| Canonical source scene/project plus current shots and saved coverage metadata | Recompute canonical content/dialogue obligations and prior decisions; validate the submitted obligation set. | SAFE READ, with a hazardous import dependency described in F/G. |
| Session, user, and project-owner records | Authenticate the caller and prove ownership before returning project state. | AUTHENTICATION DEPENDENCY; use read-only checks in the dedicated path. |

The exact source-side storage method inventory identified for Scene Direction is `get_project`, `get_storyboard_blueprint`, `get_storyboard_blueprint_version`, `list_storyboard_shots`, `list_storyboard_blueprint_versions`, `get_universe_nodes`, and `list_reference_assets`. The actual rows and current values have not been checked.

The exact-setting authority panel's list call is separate from Scene Direction GET and uses the sync-free `GET /{project_id}/setting-references/{setting_id}`. **Exclude** `GET /reference-library/{target_type}/{target_id}` and the broad `/reference-assets` list: those route paths invoke `sync_creator_references` before listing.

## C. Exact explicit write paths

### Setting authority lifecycle

These are independent writes and do not automatically choose a Scene Direction reference:

1. **Candidate selection/registration:** explicit URI registration creates a fresh candidate against the exact project/setting scope (`project_5907c60cddbc` / `setting/loc-c8f88b9c` in the checked-in contract). It stores the URI string; source does not show a remote URI fetch on this path. Upload is a distinct explicit path that writes an uploaded file and registers its reference; exclude it from the smallest first bridge unless separately required and authorized.
2. **Approval:** explicit action updates only the matching exact-target reference's approval state; it does not designate canonical.
3. **Canonical designation:** separate explicit action validates an already-approved exact-target environment reference and applies canonical status through a transaction. Source indicates it does not clear other rows already marked canonical; exclusivity is therefore an open semantic question, not an assumption.
4. **Scene Direction reference choice:** explicit `setting_reference_decision` (`canonical_setting_id` + `reference_id`) is only persisted with a successful Scene Direction successor save. The save re-resolves the scene setting and revalidates that the chosen reference remains exact-target, approved, and canonical. Merely registering, approving, or designating a reference does not select it for the scene.

### Scene Direction decision capture

The PUT requires `expected_version_id`, the canonical dialogue rows exactly once with unchanged source wording, exactly one decision for each current canonical obligation, and exactly one handoff for every current shot. It verifies shot ownership, omission/silence constraints, and lock state. It clones the current shots, stores all coverage decision records and the explicit setting choice in version metadata, copies handoff fields to the clones, and creates a new `DRAFT` version with `source_version_id` pointing to the old version. `commit_storyboard_blueprint_version(... expected_version_id=...)` uses `BEGIN IMMEDIATE` and an expected-current-version check; transaction failure rolls back, and stale writes become a conflict instead of silently overwriting a newer version.

These are **SAFE EXPLICIT WRITES** only behind authenticated project ownership, strict row scoping, the existing validations, and an atomic transaction. Scene Direction does not write a READY/approved status. Do not invoke unrelated storyboard create/backfill/approve, preflight, queue, render, training, or provider operations.

Relevant sources: [reference_assets.py](../studio-backend/app/routes/reference_assets.py), [reference_asset_service.py](../studio-backend/app/services/reference_asset_service.py), [scene_direction_service.py](../studio-backend/app/services/scene_direction_service.py), [storage.py](../studio-backend/app/data/storage.py).

## D. Authentication path

The existing browser session flow uses same-origin session cookies through `/api/f51/studio/auth/...` ([useStudioSession.ts](../studio-app/src/hooks/useStudioSession.ts), [StudioSessionGate.tsx](../studio-app/src/components/StudioSessionGate.tsx)). For non-local requests, `ProjectAccessMiddleware` extracts the session cookie (or accepted token header), validates a session/user, sets request identity context, obtains `access_owned_projects`, and authorizes the route's project scope. A project ID by itself is not authorization. Local loopback bypass must not be used for this real-project path.

The existing implementation is not safe to transplant unchanged: middleware's `ProjectAccessService` imports global `auth_service` and `project_store`; its session lookup may refresh activity; owned-listing uses the project-store global; and middleware invokes the main app's OpenAPI schema to map request paths. `main.py` also rebinds the auth service to production storage. A dedicated bridge must not rely on an unauthenticated mode, a fixture session, demo login, local bypass, caller-supplied owner ID, or project ID alone.

**Required future auth adapter:** accept the real existing session credential from the browser; validate token → unexpired persisted session → existing user → exact project ownership using read-only queries against the same auth/ownership store; fail closed for missing/expired session, missing owner row, unknown project, or query error. Do not create a session, update last-active, clean sessions, or change ownership. Bind verified `user_id` to request context and perform the owner check on every read and write. The project/session/owner state cannot be established in this source-only gate.

Sources: [auth.py](../studio-backend/app/auth.py), [project_access.py](../studio-backend/app/middleware/project_access.py), [project_access_service.py](../studio-backend/app/services/project_access_service.py), [access_context.py](../studio-backend/app/access_context.py).

## E. Database/storage requirements

`DatabaseStorage` is not a migration-free connection wrapper: its constructor creates the storage directory, opens `studio.db`, enables WAL/synchronous/cache/foreign-key pragmas, runs `_init_schema()`, and runs `_ensure_initial_data()` (demo seed behavior). `get_storage()` is therefore not suitable for this dedicated process. Do not construct `DatabaseStorage` or call `get_storage()` there.

A dedicated process can in principle connect to an already-existing SQLite database with a strictly scoped repository, but only after the correct file, schema/version, locking/journal mode, access permissions, and operational ownership are verified in a separately authorized gate. Use an explicit configured path and a non-creating open (`mode=rw`; fail if absent), issue no DDL/migrations/seeding or journal-mode PRAGMA, and expose only the required query/transaction methods. Read-only authentication queries must not refresh sessions. SQLite itself can create/use WAL shared-memory sidecars and may perform recovery depending on actual journal state; therefore “migration-free” does not mean “zero filesystem effects.” This behavior must be assessed before opening the real file, not inferred here.

**Preserving atomic semantics:** the existing storage method already establishes the required transaction boundary and optimistic version check. Reusing it requires avoiding the side-effectful `DatabaseStorage` constructor. Preferred design is a migration-free, allowlisted repository that implements the same expected-version check and writes the blueprint pointer, version, and cloned shot rows in one `BEGIN IMMEDIATE` transaction, with rollback on any failure. Reuse the current storage SQL/model serialization only after extracting it behind an explicitly supplied connection that does not initialize schema. Do not split the successor bundle into separate commits. Retain current `expected_version_id`, old-version preservation, explicit decision metadata, draft status, and lock checks.

The project/reference reads, setting lifecycle writes, auth/owner checks, and successor commit all target the same configured database file, but can have separate repository methods and transactions. They must remain exact-project/exact-setting scoped. DB path, actual schema compatibility, backup policy, WAL state, concurrency behavior, and write permissions are unresolved. No database was opened for this report.

## F. Startup and other effects that must remain excluded

Never import or launch production `main.py` for the isolated bridge. Its production storage construction and lifespan/startup assembly include or arrange database backup/snapshot/lineage work, output/static directory setup, render hydration/recovery, visual-training refresh, service rebinding, production-queue lease recovery and worker startup, Runway polling, task cleanup/registration, session cleanup writes, and resource-pool shutdown. Those are unrelated to displaying or explicitly capturing these creator decisions.

Also exclude:

- `DatabaseStorage`/`get_storage()` construction, schema initialization, migration, initial/demo seed, and WAL-setting pragmas.
- The route module's global `reference_asset_service` singleton where its constructor/storage resolution may initialize production storage; replace it with explicit scoped injection in a future implementation.
- `SceneDirectionService` paths that create/backfill a missing blueprint. The safe GET contract is to read an existing current blueprint; missing state should fail closed, not auto-create.
- Generic reference-library list/sync, reference synchronization, image download/fetch, upload/filesystem writes unless explicitly included, and any automatic candidate approval/canonicalization.
- All preflight, decision-gate, READY transition, generation-contract, render, audio-generation, provider, queue, worker, training, recovery, polling, backup, snapshot, lineage, and cleanup workflows.

## G. Global dependencies and import hazards

| Dependency | Why DI alone is insufficient today | Required replacement/isolation |
|---|---|---|
| `storyboard_blueprint_service.py` module-level `storyboard_blueprint_service = StoryboardBlueprintService()` | Importing the module eagerly constructs a service; its default constructor calls `get_storage('sqlite')`, which constructs `DatabaseStorage` and initializes schema/data. `SceneDirectionService` imports this module. | Remove import-time instantiation from the isolated import graph; use an explicit factory/provider in the focused app. Keep production composition separate. |
| Global `project_store` in `StoryboardBlueprintService` | Constructor assigns global store even when storage was injected. `_get_scene` checks that global first; some provenance/scene methods also read/write the global. | Inject a read-only project reader backed by the same scoped repository; never fall through to project_store. Audit `_inspect`, provenance, and helper call graph for additional global reads/writes before reuse. |
| Global `shot_rationale_service` and `shot_sequence_service` | Imported/assigned by the blueprint service; DI of storage does not replace them. Some blueprint helper paths may call them. | Do not invoke unrelated lifecycle methods; inject safe no-op/read-only collaborators only after call-graph proof, or isolate the minimal current-version read/clone helpers. |
| `scene_coverage_contract` → `audio_pipeline_service._extract_dialogue_lines` | Coverage only needs a pure parser, but importing the audio service pulls environment/library/media/provider capability setup and module singletons/directories. | Extract the pure dialogue parser into a side-effect-free module and point both callers to it, or otherwise establish a demonstrably safe isolated import. Never initialize or call audio generation. |
| `reference_validation.py` global `project_store` fallback | Setting resolver/validator imports the global store; source scene/project can avoid some fallbacks, but this must be verified for the exact call path. | Inject canonical project/scene data and repository explicitly; fail closed rather than fallback to global state. |
| `reference_asset_service` global singleton | Routes bind global service; injected storage support exists at service level, but route import/instance is not an adequate scoped dependency boundary. | Route through explicit request/app-scoped service wired to the migration-free repository. Do not import route module if it constructs the singleton before isolation. |
| `auth_service`, `ProjectAccessService`, `project_store`, `access_user_id` globals/context | Existing access path has process globals, session activity side effects, and project-store listing. | Add a dedicated read-only auth/ownership verifier; propagate verified identity explicitly/context-locally; do not reuse local bypass or fixture auth. |
| storage default/factory globals | Default storage selects the ordinary constructor that migrates/seeds. | Pass the dedicated repository explicitly to every service; audit import-time service instances transitively. |

**Reuse verdict:** `SceneDirectionService(storage=...)` and `ReferenceAssetService(storage=...)` show partial DI, but that is not enough. Service and route imports cross eager global construction, global project lookup, and hazardous coverage imports. Existing logic can be selectively retained after dependency extraction, or the minimal GET/PUT contract can be implemented in a new adapter; neither is safe unchanged.

## H. Smallest viable real-project adapter architecture

A focused app/process (not `main:app`) with only these elements:

1. **App factory and two route groups:** exact setting-reference list/lifecycle and Scene Direction GET/PUT. Preserve the existing JSON schemas and endpoint contract for now; no F51 namespace/client-path decision is part of this gate. The focused app has no production lifespan handlers or background tasks.
2. **Read-only auth/ownership adapter:** validates the browser's real persisted session and exact project owner on each request, with no login/session creation, local bypass, session activity write, or owner mutation.
3. **Migration-free `CreatorWorkspaceRepository`:** explicit existing SQLite path, non-creating open, scoped allowlist for the reads above, exact setting operations, auth/ownership queries, and one atomic successor commit. No general-purpose `DatabaseStorage`, schema init, seed, project-store facade, filesystem path access, or unrelated storage methods.
4. **Pure domain layer:** reuse the Scene Direction Pydantic models and validation/coverage semantics only after making their import graph side-effect-free. Inject canonical project/scene/setting data and reference validation; no global fallback. If extraction makes the existing service's helper graph too broad, put only the needed response shaping, validation, cloning, and repository calls in a narrow adapter service rather than importing `StoryboardBlueprintService` wholesale.
5. **Explicit dependency composition:** inject repository, auth verifier, and scoped reference lifecycle into every route/service. No module-level production singletons. GET of missing blueprint returns not-found; it must not create one.
6. **No automatic behavior:** writes occur only as a direct result of the corresponding authenticated user action. URI candidate creation, approval, canonical designation, Scene Direction save, and upload are separate explicit actions. First bridge should omit upload unless a separate requirement is accepted.

This preserves the existing UI contract and atomic successor semantics while avoiding main/lifespan/global initialization. It is a design proposal, not an implemented app or verified connection.

## I. F51 dependency inventory and removal evidence

**Finding:** F51 is not merely the old folder name. In the checked-out source it is an active route namespace and frontend contract: router prefixes include `/api/f51/studio`; `sceneDirectionApi`, `settingReferenceApi`, and session clients call it; project-access middleware has an auth-prefix exception and route-scope logic keyed to it; fixture endpoints, mocks, tests, docs, telemetry, and other frontend API clients use it. Repository history shows it persists from its introduction in the earlier project state through the available September 2026 history. It should not be treated as a directory-only rename.

**Source inventory observed:** `studio-app/src` has dozens of distinct files containing F51 paths (the source search found well over 30, including API modules, session/auth, mocks, tests, health/admin controls, telemetry, and feature pages); backend routes and middleware contain F51 prefixes/allowlists; backend tests and fixture runtime use F51; docs and generated OpenAPI/evidence snapshots contain it. Counts from source inventory are approximate and exclude archived/temp/generated copies; the repository-wide text search also finds reports and snapshots. There is no checked-out `F51/` source directory corresponding to the namespace.

**External consumers:** cannot be identified from this repository. No claim is made that the checked-out search is a complete consumer inventory.

**Safely replaceable later:** likely through a controlled, side-by-side route/client migration, not global replacement. First enumerate checked-in route definitions, direct URL literals, shared URL builders, middleware auth exceptions and path-scope rules, CORS/reverse-proxy configuration, generated OpenAPI, fixture app/proxy, tests/mocks, docs/examples, and any external consumers. Add and test the new route/client contract in parallel; preserve auth and ownership behavior; migrate each client deliberately; record telemetry/compatibility evidence; only remove old paths after consumer/deployment verification and a deprecation window. Do not rename the namespace or change frontend paths in this gate. The evidence does not decide what namespace should replace it.

Representative references: [scene_direction.py](../studio-backend/app/routes/scene_direction.py), [project_access.py](../studio-backend/app/middleware/project_access.py), [sceneDirectionApi.ts](../studio-app/src/lib/sceneDirectionApi.ts), [settingReferenceApi.ts](../studio-app/src/lib/settingReferenceApi.ts), [creator_workspace_fixture.py](../studio-backend/creator_workspace_fixture.py), [creator_workspace_fixture_runtime.md](creator_workspace_fixture_runtime.md).

## J. Risks and unresolved questions

1. **No live truth:** database path/schema/version, exact Scene 002 ID mapping, blueprint/version/lock state, references/canonical state, user session, and project ownership are unknown. Must not present fixture evidence as proof of access.
2. **Migration-free open is not zero-effect:** even correct SQLite URI/open flags can interact with WAL/SHM/recovery and filesystem permissions. Need an approved operational plan before opening the file.
3. **Schema compatibility:** safe repository SQL and the current atomic commit depend on the live schema matching source assumptions. No schema inspection was permitted.
4. **Auth durability and transport:** determine how the real session cookie reaches a dedicated process without exposing tokens, weakening SameSite/origin/CSRF protections, adding a local bypass, or creating a second auth authority. Verify session expiry and owner mapping read-only.
5. **Import graph:** additional imports below the apparent service boundary may initialize storage, media libraries, directories, project state, or singleton services. Must prove the isolated import graph with import-safety tests before any live launch.
6. **Project scene/settings:** canonical setting resolution may depend on universe rows or fallback logic; exact project/scene linkage needs source-only coverage tests and then a separately authorized read verification.
7. **Canonical uniqueness:** designation code's exact-target validation does not establish that it clears prior canonical rows. Determine whether multiple canonical references are valid, and define conflict handling without silently modifying unrelated rows.
8. **Reference URI semantics:** URI candidate creation does not itself prove asset availability or safety; local `/outputs/` image serving may have additional project authorization/path behavior. Exclude arbitrary remote fetching and upload in the minimal bridge.
9. **Concurrency/locks:** confirm the existing expected-version transaction, blueprint lock checks, shot locks, and concurrent canonical-reference changes remain enforced by the isolated repository and response path.
10. **Creator intent integrity:** retain exact obligation coverage, unchanged canonical dialogue, omission/silence reasons, exact setting reference IDs, and draft-only successor semantics. Never auto-resolve, preselect, approve, or mark READY.
11. **F51 consumers:** repository inventory is not an external consumer inventory. Preserve current paths for initial integration; migration requires a later evidence-based gate.
12. **Operational ownership:** dedicated process location, bind address, reverse proxy, TLS/cookie origin, secrets/config source, file permissions, lifecycle/supervision, and monitoring are not specified or authorized in this gate.

## K. Proposed implementation sequence (future gate only)

1. Obtain explicit authorization for the real database path, read-only verification, process/network topology, and any eventual writes; confirm no other agent is changing the relevant files.
2. Perform a static transitive-import/call-graph audit; add import-safety tests that assert no storage creation, filesystem setup, global project-store use, or background/provider import occurs in the focused app.
3. Extract pure dialogue parsing and make exact setting/project resolution injectable, with fail-closed behavior and regression tests preserving current contract.
4. Build a migration-free repository against a temporary test database/schema fixture first; implement scoped reads, auth/ownership checks, exact setting writes, and the atomic expected-version successor transaction. Test rollback, stale-version conflict, lock checks, old-version preservation, draft status, and zero schema/init calls.
5. Create the focused app with explicit dependencies and no lifespan workers; test unauthenticated, expired session, wrong owner/project, wrong setting/ref, stale version, malformed/partial obligations, and successful explicit actions against disposable storage only.
6. Audit the exact F51 route/client/middleware/proxy contract and confirm how the existing browser cookie will reach the focused process without changing F51 paths in this step.
7. Only after separate authorization, validate configured DB identity/schema read-only; then verify session/ownership and read Scene 002 state. Do not create a decision during access validation.
8. Obtain a separate explicit go-ahead before any real candidate/approval/canonical/Scene Direction write. Start the focused process only under that later authorization, verify each action and rollback boundary, and stop if any scope/state differs.
9. Address F51 migration as an independent, side-by-side compatibility project after external consumer inventory; do not bundle it into initial real-project access.

## L. Exact files that a future implementation is expected to touch

No files were changed for this report. Subject to review after the future gate, the smallest likely code delta is:

- **New:** `studio-backend/creator_workspace_app.py` — focused app factory/entry point, no production lifespan.
- **New:** `studio-backend/app/services/creator_workspace_repository.py` — migration-free allowlisted DB repository and atomic version-bundle transaction.
- **New:** `studio-backend/app/services/creator_workspace_auth.py` — read-only session/user/owner validation.
- **New:** `studio-backend/app/routes/creator_workspace.py` — focused contract routes, or equivalent route modules if keeping existing imports safe proves smaller.
- **Modify if retaining existing domain logic:** `studio-backend/app/services/scene_direction_service.py` — explicit project/setting/coverage dependency injection and no global fallback.
- **Modify if reusing blueprint helpers:** `studio-backend/app/services/storyboard_blueprint_service.py` — remove eager singleton/import hazards and inject project reader/collaborators; otherwise avoid wholesale reuse and keep a narrow adapter.
- **Modify:** `studio-backend/app/services/scene_coverage_contract.py` plus a new pure dialogue extraction module, and `studio-backend/app/services/audio_pipeline_service.py` only if needed to re-export the extracted helper without changing its behavior.
- **Modify if exact lifecycle code is reused:** `studio-backend/app/services/reference_asset_service.py` and route dependency wiring in `studio-backend/app/routes/reference_assets.py`, so no global storage singleton is imported by the focused app.
- **Modify only if necessary for isolated injection:** `studio-backend/app/services/reference_validation.py` to accept all required source entities/repository explicitly and remove fallback for this path.
- **Tests to add/adjust:** focused backend tests for import safety, adapter contract, auth/ownership, exact lifecycle, transaction rollback/concurrency, and current Scene Direction semantics. Existing production tests remain intact.

This list is conditional: if route/service imports cannot be made safe with a small refactor, implement the narrow contract in the new adapter instead of importing or modifying broad production services. No frontend path change is included; the current contract must be served compatibly for initial integration.

## M. Files and systems not to modify for this design gate / first bridge

**This design gate changed only this new report.** The following remain untouched. For the first adapter, keep them out of scope as well:

- `studio-backend/main.py`, production lifespan/startup assembly, production app wiring, and existing production startup configuration.
- Existing frontend components/hooks/API clients, especially [sceneDirectionApi.ts](../studio-app/src/lib/sceneDirectionApi.ts), [settingReferenceApi.ts](../studio-app/src/lib/settingReferenceApi.ts), [useStudioSession.ts](../studio-app/src/hooks/useStudioSession.ts); do not change F51 routes or client paths yet.
- Existing route prefixes or auth exceptions for F51 as part of this gate; do not globally replace `f51` strings, rename the API namespace, or alter external compatibility assumptions.
- `DatabaseStorage` schema/migration/seed code and the live SQLite database, including any live database, WAL, SHM, backup, snapshot, or lineage artifact. Do not open, query, hash, inspect, migrate, write, copy, or delete them under this authorization.
- `project_store` data/files or project JSON snapshots as a substitute for authenticated database access; no fixture/demo/session/user/owner data may be promoted into real state.
- Render, audio/provider, training, production queue, preflight/decision-gate, recovery, polling, backup, lineage, cleanup, output generation, and any worker configuration or routes.
- Any candidate/approval/canonical/Scene Direction creator action against the real project before a separate explicit write authorization.
- Port 8010 and PID 73674: do not inspect, contact, stop, or otherwise interact with them.
- External providers or services; no HTTP requests or outbound calls in this gate.

**Stop condition:** this report is the complete deliverable for the current gate. Do not proceed to implementation, process startup, database access, HTTP, or creator decisions without a new authorization.
