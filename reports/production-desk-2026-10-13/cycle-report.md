# Production Desk cycle — 2026-10-13

Branch: `backend-expansion-dependency-slicing` @ `86c1b58e75d45fd77b4aa25176537a14000bb363`
No commits were made. No backend behavior was changed in this cycle.

---

## 1. Contract decisions (Priority 1) — resolved by existing code and tests

### Q1. Does the persisted film pointer represent only an accepted delivery?

**Answer: only an accepted delivery. A pending delivery never holds the pointer.**

Evidence:

- `ScreeningRoomService._clear_unaccepted_current_final()` (screening_room_service.py:162)
  clears `current_final_output_id` unless the pointed-to output is not outdated **and**
  `_is_current_accepted_final()` passes.
- `_is_current_accepted_final()` (line 336) requires `output_type == 'final'`,
  `source_type == 'final_package'`, an exact `original_url` match against the stored
  package, and `_is_package_currently_accepted()` (a current acceptance report plus
  `evaluate_package_approval_guard(..., desired_status='approved').allowed`).
- `sync_manifest()` only registers `final_package` outputs for
  `metadata.delivery_kind == 'canonical_film_cut'` when `_accepted_canonical_package()`
  passes (canonical cut match + current accepted report).

Tests that pin this:

- `tests/test_screening_film_delivery_acceptance.py::test_accepted_exact_package_output_can_be_selected`
  — accepted exact package sets the pointer.
- `tests/test_screening_film_delivery_acceptance.py::test_stale_report_does_not_replace_valid_current_final`
  — a changed output after acceptance is refused and the prior pointer survives.
- `tests/test_canonical_film_delivery_handoff.py::test_rejected_creator_review_preserves_previous_current_screening_final`
  — an unaccepted newer delivery registers no screening output and leaves the pointer unchanged.
- `tests/test_checkpoint_4c_screening_room_integrity.py::test_film_delivery_without_canonical_cut_package_and_manifest_cannot_be_approved`

**Decision: no behavior change. The contract is already established; documented here.**

### Q2. How is freshness evaluated for `final_package` Screening outputs (`cut_freshness: unverified`)?

**Answer: `unverified` is deliberate and correct for packages; it is not a defect.**

Evidence: `ScreeningRoomService._public_output()` (screening_room_service.py:604-630)

- `source_type == 'film_delivery'` → freshness compares the export URL and
  `FilmDeliveryService.status().film_outdated` → `current` / `outdated` / `unverified`.
- `output_type == 'final'` (canonical packages) → `unverified` with the reason
  "This package has no take and recording fingerprint. Review its contents before
  treating it as the current cut."

Why this is safe rather than a gap:

- Package validity is enforced elsewhere by construction:
  `_canonical_package_matches_current_cut()` compares `source_cut_id` against the
  current approved cut, requires the file inside the approved outputs root, and
  re-verifies `film_output_sha256`; acceptance staleness is enforced separately by
  `ProductionAcceptanceService.get_latest_report().stale`.
- `_clear_unaccepted_current_final()` only evicts on `status == 'outdated'`, so
  `unverified` never silently drops an accepted pointer, and it never *asserts*
  verification the backend has not established.
- The Screening UI already renders the freshness reason for any status other than
  `current` (ScreeningRoom.tsx:1259, 1405).

**Decision: no behavior change. Freshness for packages stays `unverified`, with
enforcement carried by canonical-cut match + package-scoped acceptance. The Production
Desk reflects this by never labelling a package "verified" on freshness alone.**

### Q3. Is the approved-cut → delivery → acceptance → Screening-selection path proven by current tests?

**Answer: yes.**

`tests/test_canonical_film_delivery_handoff.py::test_rejected_creator_review_preserves_previous_current_screening_final`
covers the whole positive path in one test:

1. `FilmDeliveryService.assemble()` with an explicitly approved cut (setup seeds
   `approve_film_cut`) → package + `acceptance_report_id`.
2. `ProductionAcceptanceService.run_acceptance()` → `ready_for_creator_approval`,
   and `evaluate_package_approval_guard(..., 'approved').allowed` is true.
3. `ScreeningRoomService.sync_manifest()` registers the accepted `final_package` output.
4. `approve_output(...)` → `current_final_output_id == that output`.

It then proves the negative path (rejected review → no registration, no pointer
change). The remaining safety rules (cross-project, non-owner, stale acceptance,
foreign output) are covered by
`tests/test_screening_film_delivery_acceptance.py`.

**Decision: no new test required for the happy path; it exists and passes.**

---

## 2. Test baseline revalidation (before changes)

Interpreter note: the focused suites must run with the **repo-root** venv from
`studio-backend/` (`../.venv/bin/python -m pytest ...`). The backend venv
(`studio-backend/.venv`) ships a third-party `tests` package in site-packages that
shadows `studio-backend/tests`, so `from tests.test_canonical_film_delivery_handoff
import seed_cut` fails there.

| Suite | Result |
|---|---|
| tests/test_offline_production_delivery.py | 4 passed |
| tests/test_take_selection_delivery.py | 12 passed |
| tests/test_screening_film_delivery_acceptance.py | 6 passed |
| tests/test_canonical_film_delivery_handoff.py (untracked, preserved) | 8 passed |
| tests/test_checkpoint_4c_screening_room_integrity.py | 7 passed |
| **Focused delivery total** | **37 passed** |
| ProductionDesk.test.tsx (before changes) | 3 passed |

---

## 3. What was present vs. what changed

Present before this cycle: a 146-line `ProductionDesk.tsx` (untracked) showing
scene coverage, editorial readiness, render queue counts, delivery/acceptance state,
with 3 passing tests.

Changed files (both untracked, both extended — not replaced from HEAD):

- `studio-app/src/pages/ProductionDesk.tsx`
  - Four-stage rail (Scenes / Editorial / Delivery / Screening) derived only from loaded evidence.
  - `deriveNextActions()` — ordered blocker → next → info action list with real links into existing rooms.
  - Scene production table — per scene: storyboard plan (`listStoryboardBlueprints`),
    shot completion/failure/activity (render jobs), take selection (`getTakeChoices`,
    capped at `TAKE_LOOKUP_LIMIT = 24` scenes with an explicit on-screen note when capped),
    per-scene delivery state from `scenes_needing_assembly`, and a derived
    Draft / Rendering / Needs review / Blocked / Ready / Composed chip.
  - Render queue pulse from `getProductionQueueSummary` (status counts, blocked reasons,
    stale leases, oldest waiting item, recent failures).
  - Reference & media coverage from `listReferenceAssets`, storyboard coverage, planned/ready shots, saved media files.
  - Honest loading / unavailable / empty states everywhere; failed APIs stay unavailable.
- `studio-app/src/pages/ProductionDesk.test.tsx` — mocks extended for the four new
  read APIs; 3 new tests (scene table evidence, next-action derivation, unavailable APIs).

No backend file, route, model, or provider was modified. No existing tracked file was modified.

---

## 4. Verification evidence (after changes)

| Check | Result |
|---|---|
| `vitest run src/pages/ProductionDesk.test.tsx` | 6 passed |
| `vitest run` (full frontend suite) | 109 files, 873 passed |
| `tsc -b` | exit 0 |
| `eslint src/pages/ProductionDesk.tsx src/pages/ProductionDesk.test.tsx` | clean |
| `npm run build` (tsc -b && vite build) | exit 0 |
| Focused backend delivery/acceptance suites | 37 passed |
| Acceptance + 4C/4D regression add-on | 27 passed |
| `git diff --check` | exit 0 |
| Working-tree entry count | 338 (unchanged from before the cycle) |

Live verification (read-only): Vite dev server on `127.0.0.1:5173` against the
already-running backend on `127.0.0.1:8010`. The room loaded project
`project_193c13b84072` and every request returned HTTP 200 (scenes, assembly-status,
film-cut, render jobs, screening manifest, production-acceptance/latest, 5 ×
take-choices, production-queue summary, reference-assets, storyboard-blueprints).
No console errors. All displayed values (0/5 covered, Cut v1 · draft, 0/5 composed,
Acceptance · not_run, 0 reference assets) came from those responses.

Not run: full backend suite (~1,700 tests), backend syntax sweep (no backend files changed).

---

## 5. Remaining blockers

Essential (production safety): none found in this cycle. The three open contract
questions are answered by existing code and tests (section 1).

Optional improvements:

- Take-choice lookup is per scene; a project-scoped endpoint would remove N requests.
- `getAssemblyStatus` returns an HTTP error when no Film Cut is approved, so the desk
  shows "Delivery status unavailable: …" instead of a calmer "assembly blocked — no
  approved cut" state (the raw backend message is still shown, so nothing is falsified).
- Pre-existing lint failure in `studio-app/tests/creatorWorkspaceRouting.test.ts:181`
  (`no-useless-escape`) is unrelated to this cycle.

## 6. Deferred features

Trailer creation and the Fee Fee Anne Studios opening ident were **not** started.

## 7. Next bounded task

Priority 3: build the Production Integrity Engine experience — inspect the existing
integrity services and UI first, then expose real validation evidence (project/scene
validation, provenance, ownership, approved-cut consistency, acceptance freshness,
blockers with resolution evidence) as a technical verification console that never
competes with the backend gate.
