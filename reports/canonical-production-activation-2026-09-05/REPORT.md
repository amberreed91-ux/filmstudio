# Canonical Production Thread — repaired and active

The repaired frontend is running at http://localhost:5001 and the backend at http://127.0.0.1:8010. Both listeners are restricted to loopback. The existing Mac launcher starts this configuration. Local desktop access remains available; the default authenticated mode and nonlocal access checks are preserved.

## Rendering behavior

- The Previs Render Engine selector now controls both Canonical Previs generation and new production-package renders. The panel displays the selected provider and queues an approved render instead of silently requesting the simulator.
- With no override, new Previs uses the server default (currently OpenRouter). Package rendering inherits the provider saved with approved Previs, falling back to the server default for older packages without that field. Explicit simulator requests remain supported for deliberate test runs.
- Retries and polling retain the existing jobs. Revisions inherit their original job's provider; changing the Previs selector does not move an existing job to another provider.
- The earlier adherence repairs are active: approved image conditioning, complete prompt handling, duration/resolution/seed forwarding, frozen package inputs, review stops, and project-ownership preservation during saves.
- Video-generation requests have a ten-minute client timeout instead of the generic thirty-second limit.

## Compatibility problems found during activation

1. Older films lacked Script IDs. The service now resolves a stable project-scoped script version from saved script text or saved scene text. Explicit IDs are retained. The panel uses this server context; it no longer asks you to regenerate the writing merely to create an ID. Existing approval requirements remain enforced.
2. Some saved storyboard props were comma-separated text rather than a list. They now load through a compatibility validator. All 60 saved shot records deserialize; their stored content was not rewritten.
3. Two films shared the legacy Film Cut ID `default`. Bootstrapping the second cut caused an insertion failure. New bootstrap IDs are scoped to the project, concurrent requests reuse the committed cut, and existing scene order is retained.
4. Failed or unfinished database transactions could return to the connection pool while holding a writer lock. Pool return now rolls them back. Independent-connection tests verify that subsequent writes succeed immediately.
5. Rapid desktop room loads hit the generic request limit. The local desktop launch paths now allow 600 requests per minute. The backend configuration default remains 120; ownership and origin checks remain active.

## Verification

- Backend: **3,481 passed, 10 skipped**, using a disposable source copy. Its application Python files match the activated source.
- Focused workflow, compatibility, transaction, and concurrency tests: **34 passed**.
- Frontend: **687 passed** across 76 test files.
- Production build: passed; the existing large Three.js bundle warning remains.
- Live browser: both films load, legacy script context resolves, the panel starts normally, and provider controls send the expected requests. Package, Previs, retry, and revision button tests used explicit workflow fixtures and intercepted generation POSTs before they reached the backend. No browser exceptions, HTTP 500 responses, or rate-limit responses occurred in the final run.
- Live compatibility check: four concurrent Film Cut reads and two storyboard reads all returned HTTP 200. Readiness stayed responsive after the browser workflow.
- Live validation: an empty provider is rejected with 422; a forwarded nonlocal anonymous project request is rejected with 401.
- No paid generation or new visual-quality benchmark was run. This verifies activation, request behavior, data compatibility, and persistence; it does not promise an exact generative recreation of a film.

## Data preservation

Before restarting, the active project stores were backed up with SQLite's backup API and JSON copies at:

`/Users/amberreed/Library/Application Support/AI Film Studio/backups/studio-canonical-activation-x1r5qt2x`

Migrations 60 and 61 were rehearsed on a copy, preserving existing content across 140 tables, then activated. Database integrity passes with no foreign-key violations. The two original project rows, 43 render jobs, 12 storyboard blueprints, and 60 storyboard shots remain intact. The missing Film Cut version was bootstrapped separately from existing scene order. No script, take, or storyboard was regenerated or approved during verification.

## Using the repair

Open Previs, choose the Render Engine, and continue from the approved storyboard and Previs set. Build a fresh production package to capture the repaired input snapshot; old packages cannot recover settings that were never saved. Auto keeps the approved provider for packages, while retries and revisions retain their original job provider.

Evidence is saved alongside this report, including the live screenshot, browser request captures, migration checks, test logs, source hashes, and scoped code diff.
