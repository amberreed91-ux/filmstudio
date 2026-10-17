# Creator Workspace fixture runtime

## Purpose and boundary

This is a disposable UI/runtime verification environment for the existing Creator Decision Workspace. It uses synthetic screenplay/dialogue text, five invented shot records, and 60 invented unresolved coverage rows. Its project/scene/version/setting identifiers intentionally match the requested scope so the existing UI contracts can be exercised, but those identifiers do **not** cause any live project lookup. Nothing in the fixture runtime connects to the normal Studio process, the live database, a provider, or a render/queue system.

The service is `studio-backend/creator_workspace_fixture.py`, a standalone FastAPI app with only an in-process `FixtureStore`. It does not import `main.py`, production route modules, production service modules, global storage, or `project_store`. It defines no startup/shutdown work beyond FastAPI's no-op default lifespan. A successful fixture save changes only that process's memory, creates a synthetic DRAFT successor, and preserves a detached approved-source snapshot. Restarting the fixture discards every saved decision and reference.

The separate UI entrypoint at `studio-app/creator-workspace-fixture.html` mounts the existing `CreatorDecisionWorkspace`, `SettingReferenceAuthorityPanel`, and `SceneDirectionPanel`. Its dedicated Vite config at `studio-app/vite.creator-workspace-fixture.config.ts` does not load the normal `backendSupervisorPlugin`, does not proxy to port 8010, and proxies only the Creator Workspace API prefix to loopback port 8011. It is served on loopback port 5178.

## Run locally

From the repository root, start the disposable API in one terminal:

```bash
cd studio-backend
python -m uvicorn creator_workspace_fixture:app --app-dir . --host 127.0.0.1 --port 8011
```

In another terminal, start the separate fixture preview:

```bash
cd studio-app
npm run dev:creator-workspace-fixture
```

Open `http://127.0.0.1:5178/creator-workspace-fixture.html`. Stop each process with Ctrl-C. The commands above do not start or restart the normal backend or frontend. Do not substitute the normal Vite config or `main:app` for these fixture commands.

## Fixture behavior

- GET direction and setting references are detached, read-only responses. Initial coverage is exactly 40 content, 10 dialogue, 5 shot-content, and 5 shot-dialogue obligations, all unresolved. The Scene Direction reference starts null, with no candidate references.
- Decision saves require the existing UI's explicit review/confirm flow, validate the expected version, preserve every obligation exactly once, and return a distinct synthetic draft successor. Only the explicitly submitted decision payload changes.
- Setting Authority actions are each separate: register a `fixture://...` identifier (no fetch or media persistence), approve, and designate canonical. The Scene Direction reference remains unselected until the creator explicitly selects the canonical reference and confirms a save.
- Uploads are disabled. External image URLs are rejected in fixture mode.
- There is no sign-in form or invented session. This preview is conspicuously marked synthetic and unauthenticated; it does not attest to authentication or access to the real project.

## Real-project access boundary

Real Scene 002 access has **not** been attempted, and no real data is represented by this fixture. The normal `SceneDirectionService` dependency graph reaches storyboard/global project-store and reference validation/service code; the reference asset routes also construct/reference a global service and generic library reads can perform creator sync. The production application lifespan and `DatabaseStorage` startup are excluded because they may initialize persistent schema/data and start recovery, polling, backup, queue, or other background work. Until those dependencies have a separately reviewed, explicitly injected read/write storage path and a safe authenticated launch lifecycle, there is no supported route from this fixture to the real project.

`useStudioSession` and its retry/auth behavior are untouched. The fixture does not call the auth routes, bypass the normal gate while claiming authentication, or manufacture a session. Real authenticated Creator Workspace use is a separate follow-up; the fixture's success is not evidence that it is accessible.

## Out of scope

This runtime does not change F51, startup behavior, live storage, canonical creative truth, production readiness, rendering, generation, providers, preflight, queue work, training refresh, recovery, backups, or lineage. It does not make or infer creator decisions.
