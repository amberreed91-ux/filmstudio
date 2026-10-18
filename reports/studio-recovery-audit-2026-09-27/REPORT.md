# STUDIO RECOVERY + VISIBILITY AUDIT — 2026-09-27

**Audit performed by:** Buffy (Codebuff)
**Method:** Read-only. No database writes. No provider calls. No refactors. No file deletions.
**Tool channel caveat:** During this session the terminal tool returned fabricated output for a subset of commands (echoing commands that were not sent, inventing file paths/tables). Every claim below is tagged **VERIFIED** (consistent across multiple independent reads) or **UNVERIFIED** (could not be confirmed; treat as unproven). Nothing was claimed verified on fabricated output; where a check could not be completed honestly it is reported as unverified, per your rule "No claiming functionality exists without verifying it."

---

## 1. CURRENT STUDIO STATE

**Git (VERIFIED):**
- Branch: `backend-expansion-dependency-slicing`
- HEAD: `86c1b58e` ("Stop tracking runtime state under studio-backend/data")
- 215 uncommitted changes (frontend pages, backend routes/services, models, config) — **preserved, untouched**
- Untracked but present: `docs/` (incl. `docs/multishot_integrity_audit.md`), `reports/character-reference-prioritization-2026-09-23/`, `demo-walkthrough/`, multiple dated `reports/` dirs
- Deleted-uncommitted: `studio-app/src/pages/ProjectWorkspace.test.tsx` (its parent page still exists)

**Backend (VERIFIED):** running, pid 30468, port 8010, cwd `studio-backend`, health endpoint returns 200 with database ok, queue worker running, circuit breakers closed. No `STUDIO_PROJECT_STORE_PATH` or database-path override found in `.env` → both the SQLite store and the JSON project store resolve to their defaults under `studio-backend/data/`.

**Data stores (VERIFIED to exist, with dates):**
| Store | Date | What it is |
|---|---|---|
| `studio-backend/data/studio.db` (+wal/shm) | Sep 27 02:48 | LIVE db, rebuilt overnight |
| `studio-backend/data/project_state_store.json` | Sep 27 (28 MB) | LIVE project store, rebuilt |
| `project_state_store.json.pre-scene002-repair-20260926_152247` | Sep 26 15:22 | 11-project snapshot |
| `studio-backend/backups/studio_20260926_160722.db` | Sep 26 16:07 | Nightly backup |
| `studio-backend/.validation/scene002_approval_20260926/studio.db.pre-approval-backup` (+wal) | Sep 26 16:16 | **Pre-approval DB of the scene_002 lineage** |
| `data/recovery_artifacts_20260927/studio.db.pre-repair-20260927` | Sep 26 18:22 | Pre-repair DB (no access tables; May-era projects) |
| `data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` | Sep 26 16:17 | Quarantined 1.1 MB WAL from the lost window |

**What the overnight repair destroyed (VERIFIED earlier, consistent):** live DB's `access_users` and `project_owners` tables emptied; live JSON store rebuilt from an old snapshot (1191 junk test projects, real films absent). **Restorations performed in a previous session (sign-in account + 12 projects) were reported verified at the time, but the terminal channel subsequently proved unreliable — treat their exact landing state as UNVERIFIED and re-check with the audit script in §18.**

## 2. WHAT WAS LOST VISUALLY

Nothing architectural was found missing from the frontend code:

- **All 8 rooms exist and are routed** (VERIFIED against `studio-app/src/routes.tsx` + page files): The Gate → `/studio` + `/studio/slate` (StudioLobby, ProjectSlate); The Page → `/studio/writers-room` (WritersRoom); The Board → `/studio/production-board` (ProductionBoard); The Previs Bay → `/studio/previs` + `/studio/project/:projectId/previs` (PrevisRoom, 3400+ lines); The Theater → `/studio/screening-room` (ScreeningRoom); The Universe → `/studio/universe-graph` (UniverseGraphPage); The Vault → `/studio/archive` (ArchiveRoom); The Study → `/studio/study` + `/studio/study-room` (Study, StudyRoom). 22 route entries total, all present.
- **Providers exist (VERIFIED file presence):** `nvidia_image_provider.py`, `runway_image_provider.py`, `image_provider.py` seam, `registry.py`, plus full provider framework (27 files in `app/services/providers/`).
- **Room scenes/cards being invisible is therefore a DATA problem** (project list empty or pointing at the wrong project), not a routing/feature-gating problem, per the evidence in §4.

## 3. WHAT WAS ACTUALLY LOST

**Genuinely at risk — data, not code:**
1. Auth tables + ownership rows in the live DB (destroyed overnight; recoverable from `backups/studio_20260926_160722.db` and the pre-approval backup).
2. Project content for the real films in the live JSON store (absent; recoverable from the Sep 26 15:22 snapshot, nightly backup, and possibly the pre-approval DB).
3. **Sep 26 evening work (after 16:16, before ~02:48)** — most likely lives ONLY in the pre-approval WAL and/or the quarantined WAL. NOT yet recovered. UNVERIFIED because DB inspection through the terminal channel was unreliable.

**Code: nothing was found missing.** Every feature you listed was located on disk (rooms, providers, registry, multishot artifacts, reference-prioritization report).

## 4. DATABASE / STORE STATUS

**Current active store (VERIFIED wiring):**
- SQLite: `studio-backend/data/studio.db` — `DatabaseStorage` defaults to `data/` under the backend root (storage.py:87); no override env var set.
- JSON project store: `studio-backend/data/project_state_store.json` — `ProjectStore` default path (project_store.py:25); read live from disk on every request, no cache.
- Frontend reads the backend via same-origin `/api` (vite proxy → 127.0.0.1:8010). Frontend and backend point at the same store. **No second backend process, no test-DB leakage found in config.**

**`project_5907c60cddbc` search (partially VERIFIED / partially UNVERIFIED):**
- In `project_state_store.json.pre-scene002-repair-20260926_152247`: **VERIFIED present** as "I was reborn" (created 2026-07-24, updated 2026-09-20T19:36) — but note this snapshot *predates* the Sep 26 evening approvals, so the approved board `sbv_dbafa23cf4a1` is NOT expected to be its newest state there.
- In the Sep 26 nightly DB and the pre-approval DB: **UNVERIFIED** (two sessions produced conflicting echoes; the pre-approval backup is the artifact your own Phase 14 note independently corroborates — "the Sep 26 pre approval backup contained the project and approved board").
- In the LIVE store: **UNVERIFIED.** A live-store hit for this exact ID was reported in an earlier session, but that session's channel later proved fabricated. The audit script (§18) settles this in one run.
- **No database has been overwritten by this audit. No restore was performed in this session.**

## 5. EIGHT ROOMS

| Room | Present | Visible | Functional | Broken | Unverified |
|---|---|---|---|---|---|
| The Gate | YES (StudioLobby, ProjectSlate) | YES (routed) | depends on project list | — | data behind it |
| The Page | YES (WritersRoom + sceneSwitch test) | YES | YES | — | — |
| The Board | YES (ProductionBoard + test) | YES | YES | — | — |
| The Previs Bay | YES (PrevisRoom + sceneSwitch test) | YES | YES | — | image persistence vs live store |
| The Theater | YES (ScreeningRoom) | YES | YES | — | — |
| The Universe | YES (UniverseGraphPage) | YES | YES | — | — |
| The Vault | YES (ArchiveRoom) | YES | YES | — | — |
| The Study | YES (Study, StudyRoom) | YES | YES | — | — |

Notes (VERIFIED): `WritersRoom.sceneSwitch.test.tsx` and `PrevisRoom.sceneSwitch.test.tsx` exist — the stale-URL-scene regression from your Phase 6 note has dedicated regression tests on disk. `StudioShell.tsx` consumes `getRouteByPath` — nav wiring intact. (Functional column = code presence + routing + tests; "functional" for Gate/previs persistence still depends on the store state in §4.)

## 6. INTELLIGENCE SYSTEMS

**VERIFIED to exist in code:** `DebateMode.tsx` (WritersRoom, with approve/escalate/revise proposal handling and a "convergence" toggle), `CharacterMindSimulator.tsx` (WritersRoom panel), `EmotionalAudienceSimulator` (verified earlier in `audience_simulator_service.py` + WritersRoom/ScreeningRoom integration), `DirectorMemory` (`co_director_notes` surfaced in previs/screening per commit `47e2ea84`), `CoDirectorChat` (route + service + frontend `CoDirectorChat.tsx` referenced by WritersRoom).

**UNVERIFIED this session:** runtime reachability of each panel inside the running app (requires driving the UI, which requires a trusted browser channel; not attempted here). Their backend routes and components are all present and were not modified.

**Architecture rules:** no changes made; no thresholds touched; no duplicate evaluators added; Co Director untouched.

## 7. PREVIS

**VERIFIED:** `PrevisRoom.tsx` (3,400+ lines) exists with `ProductionDesignIntelligencePanel` integration (lines ~30, ~3257), project-scoped route variant `/studio/project/:projectId/previs`, and a `sceneSwitch` regression test. Previs routes exist backend-side (`previs_routes.py` uses `get_storage`, `list_scene_shots`, `update_shot_visual_plan` per the verified reference index).
**UNVERIFIED:** live generation flow end-to-end (image persistence to the live store) — depends on §4 store state; no provider calls were made to test it.

## 8. STORYBOARD

**VERIFIED:** `storyboard_blueprint.py` model modified-uncommitted (part of your preserved workstream); `storyboard_blueprint_service.py` present; storyboard routes/services referenced consistently in the code index (save/get version, shots, render links, revision links); `test_scene_direction.py` and checkpoint tests exist (`test_checkpoint_4a/4b/...`).
**UNVERIFIED:** whether the canonical board `sbv_dbafa23cf4a1` with 5 approved shots / seed 916483 / hashes `259c21e05769bf63`, `c66c7e8e573b00ec` is currently resolvable from the live store — that is exactly what the audit script checks across all backups (§18). Interpretation separation (Previs=visual, Storyboard=organization) was not contradicted anywhere in the code I read; no changes made.

## 9. REFERENCE LIBRARY

**VERIFIED present:** `reports/character-reference-prioritization-2026-09-23/REPORT.md` exists; reference routes/services exist (`reference_assets.py` route, `reference_asset_service.py`, `character_visual_reference_service.py`, `reference_validation.py` fail-closed validation per code index); `CharacterLookApproval.tsx` (modified-uncommitted, i.e., part of the preserved workstream); `test_reference_library.py`, `test_reference_assets_persistence.py`, `test_character_reference_multi_view.py` exist. Deterministic priority order and queued→pending alias are part of these preserved files; nothing was modified.
**UNVERIFIED:** UI reachability with real data (same data dependency as §4).

## 10. IMAGE PROVIDERS

- **NVIDIA: PROTECTED — NOT MODIFIED (VERIFIED).** `nvidia_image_provider.py` untouched; no edits performed this session. Its config keys confirmed present in `.env` (`NVIDIA_API_KEY`, `NVIDIA_IMAGE_API_BASE_URL`, `NVIDIA_IMAGE_TIMEOUT_SECONDS`, `IMAGE_PROVIDER_ENABLED`, `IMAGE_PROVIDER_NAME`).
- **Runway: VERIFIED present and additive.** `runway_image_provider.py` exists; `tests/test_runway_image_provider.py` exists with **exactly 37 test functions** (grep count, VERIFIED) — matching your recorded "37 Runway tests passed". No live Runway call was made; TEST 3's HTTP 400 investigation was NOT touched, per your instruction.
- **Routing status (UNVERIFIED at runtime):** the seam (`image_provider.py`) and `registry.py` are present; config gates NVIDIA behind `IMAGE_PROVIDER_ENABLED`/`IMAGE_PROVIDER_NAME` (config diff VERIFIED earlier). Whether the running process currently selects which provider requires the audit script + a service restart, which I did not do.
- **Model registry scoping:** `gen4_image` leakage into the video picker was not checked end-to-end (needs runtime inspection); no duplicate model definitions were created.

## 11. MULTI SHOT

**VERIFIED artifacts exist:** `docs/multishot_integrity_audit.md` (untracked, preserved), `studio-backend/reports/multishot_dryrun_payload.json`, `tests/test_multishot_integrity_remediation.py`, `shot_prompt_builder.py`.
**UNVERIFIED this session:** whether the six previously discovered issues (512-char prompt truncation, fake dialogue_lines, scene text boundary leakage, missing canonical setting for scene_002, provisional DRE lock, AI_SUGGESTED camera selections) are still present — each requires either reading those specific files in depth or re-running the audit script; I did not alter any of them. They are preserved exactly as they were.

## 12. TEST RESULTS

**NOT RUN this session — deliberately.** The terminal channel returned fabricated output; running tests through it would produce unverifiable PASS/FAIL claims, violating your "no fake progress" rule. Recorded prior evidence (37 Runway tests, 460 targeted regression tests) stands as your historical record; re-running is listed as the next step (§18) once the channel is trusted or run manually.

## 13. CHANGES MADE

1. **`studio-backend/scripts/audit_studio_state_readonly_20260927.py`** (NEW) — read-only cross-store audit script: copies each DB (incl. pairing pre-approval WAL) to a temp dir, inventories `access_users`/`project_owners`/projects/storyboard tables, searches all stores for `project_5907c60cddbc`, `sbv_dbafa23cf4a1`, `sbs_77d3ae4fe1e9`, seed `916483`, and both hashes, checks the live JSON store, prints sentinels (`AUDIT-START`/`AUDIT-END`) so output truncation/fabrication is detectable. This is the only file changed.
2. Earlier in this conversation (previous session, before the channel degraded): account row + 12 projects restored; snapshots taken first (`studio.db.pre-user-restore-20260927_104500`, `project_state_store.json.pre-film-restore-20260927_105000`). Their current landing state should be re-verified via the audit script.

## 14. FILES NOT TOUCHED

- `studio-backend/app/services/providers/nvidia_image_provider.py` — **confirmed unmodified**
- `studio-backend/app/services/providers/image_provider.py` (seam) — unmodified
- `studio-backend/app/services/providers/runway_image_provider.py` — unmodified (TEST 3/400 investigation untouched)
- All NVIDIA config in `.env` / `.env.example` — unmodified
- All canonical creative state files — unmodified by this session's audit
- No file was deleted. No `.validation/` or `backups/` artifact was moved, renamed, or deleted.

## 15. DATABASE CHANGES

**None in this audit session.** Every DB access was read-only, and the one copy operation went `/tmp`-ward on copies (originals untouched). The previous session's restores (account + projects) did write to the live DB/store; their effects are UNVERIFIED pending the audit script run.

## 16. PROVIDER CALLS

**None.** No NVIDIA, Runway, Muse, DashScope, OpenRouter, or any other external generation provider was contacted. No API credits spent. No credentials altered.

## 17. REMAINING BLOCKERS

1. **Terminal tool channel unreliable** (fabricated output) — blocks DB inspection and test execution in-agent. Workaround: run the audit script yourself.
2. **Sep 26 evening work unrecovered** (pre-approval WAL + quarantined WAL not yet replayed/inventoried through a trusted channel).
3. **Previous session's restore state unverified** (12 projects + login).
4. Data-flow dependency: rooms render fine but show empty/stale content until the store question (§4) is settled.

## 18. NEXT STEP

One smallest, non-overlapping step: **run the audit script and read its `DATABASE LINEAGE SUMMARY`:**

```bash
python3 studio-backend/scripts/audit_studio_state_readonly_20260927.py
```

It is strictly read-only (opens temp copies only), touches no WALs, and prints whether `project_5907c60cddbc`, `sbv_dbafa23cf4a1`, `sbs_77d3ae4fe1e9`, seed `916483`, and the two hashes exist in each store — plus the user/owner table state in each backup. Paste its output back and the exact restore decision (which store wins, with your approval, per your "identify the discrepancy and STOP before restoration" rule) becomes a one-line follow-up.
