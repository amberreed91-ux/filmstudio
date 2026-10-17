# SCENE_002 PRODUCTION RECOVERY REPORT — 2026-09-27

Companion to `SCENE002_RECOVERY_MERGE_MANIFEST_20260927.md` (the simulated, verified plan this
execution implements exactly). Authorization `EXECUTE_SCENE002_RECOVERY` was granted by the
creator on 2026-09-27 (approx. 19:30 EDT / 23:30 UTC) and executed the same session.

**Final verdict: RECOVERY VERIFIED** (see §18).

---

## 1. Authorization record

| Item | Value |
|---|---|
| Authorization | `EXECUTE_SCENE002_RECOVERY` (explicit, this session) |
| Scope | ONLY the verified scene_002 recovery defined by the merge manifest |
| Hard prohibitions honored | no scene_001 restoration; no creative modifications; no provider calls (Runway / FLUX.2 / other); no image or video generation; no `script_text` modification; no camera approvals; no canonical setting reference creation |
| Executing plan | `docs/forensics/SCENE002_RECOVERY_MERGE_MANIFEST_20260927.md` (45-row INSERT-only additive merge) |
| Implementation | `.validation/scene002_preflight_20260927/merge_lib.py` — byte-identical to the copy the preflight verified (`/tmp/sr927_prod/merge_lib.py` sha256-identical), merge loops verbatim-identical to the simulator `/tmp/sr927_manifest/merge_sim.py` |
| Source | September 26 verified composite: `.validation/scene002_approval_20260926/studio.db.pre-approval-backup` (sha256 `0899774f74f595ee…`) + byte-proven WAL continuation `data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` (sha256 `4dacc1c15fb5cd0d…`); standalone form `/tmp/sr927/composite/studio.db` sha256 `55895a004db965f9…` |

## 2. Pre-write verification (user gate 1 — all 7 checks revalidated immediately before the write)

Revalidation script: `/tmp/sr927_prod/revalidate.py`; evidence: `/tmp/sr927_prod/revalidation_results.json`.
All gates ran against FRESH byte copies and fresh digests, not cached preflight values.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Production database identity matches the verified preflight snapshot | **PASS** | live db sha256 `cb99f8c9bfbe0a52…` == preflight value; inode 271891263 unchanged; all 13 preserved-5907 tables byte-identical vs forensic-comparison copy; script sha16 `c66c7e8e573b00ec` len 16,285; `projects.updated_at` 2026-09-20T19:36:10.670388+00:00; owner `user-f8e8be9141fa8b64`; title "I was reborn" |
| 2 | Recovery composite digest matches | **PASS** | originals `0899774f…` / `4dacc1c1…` unchanged; standalone `55895a00…` == sim composite |
| 3 | WAL lineage matches | **PASS** | salts `8618c288`/`5836be1b`; 156→271 frames; 3→13 commit frames; byte-identical prefix |
| 4 | Manifest digest matches | **PASS** | both manifest files `c9703bfba7ae75c0…`; re-derived row set from composite + simulated PLAN == stored manifest (45 rows) |
| 5 | Rollback snapshot exists and verifies | **PASS** | 5 hash-pinned snapshot dirs under `data/recovery-snapshots/`, all re-hashed OK; latest `20260927T231537Z-pre-scene002-merge-recovery` (db `cb99f8c9…`, wal `839d44b6…`, shm `a1e77176…`, state store `3c7e716a…`) |
| 6 | Merge implementation unchanged from the simulated implementation | **PASS** | PLAN table set identical (11 tables); run-1/run-2 merge loop text verbatim-identical to `merge_sim.py`; forbidden-SQL AST scan (UPDATE/DELETE/DDL) clean |
| 7 | Production has not experienced unexpected creative state changes since preflight | **PASS** | row-level diff vs the simulation's pre-merge copy: added == exactly the 45 planned PKs, removed 0, content changes none; single known ts-only backend touch (`screening_outputs[screening_5fcae99919620474]`, field `updated_at` only) |

Additionally: a fresh dry-run merge on a new live copy produced 45 inserts / 0 updates / 0 deletes,
run-2 = 0 changes, 0 PK collisions, `foreign_key_check` empty, `integrity_check ok`, 92 statements all
within the BEGIN IMMEDIATE / INSERT OR IGNORE / COMMIT / SELECT / PRAGMA allowlist.

**Investigation note (transparency):** the first revalidation run failed Gates 1/7. Root cause was a
defect in the *revalidation harness itself*, not in production: (a) it copied the live `-shm` file;
a copied `-shm` carries a stale reader read-mark, so a second connection's checkpoint became a
no-op and the copied view reverted to the pre-Sept-27 base file; (b) a copy-loop bug wrote the
database bytes over the `-wal` name. Production was proven byte-identical to the preflight state
via three independent read paths (live-file SHA-256 identity, a correctly built db+wal copy, and a
fresh read-only connection on the live path). No repair of production was attempted — none was needed.

## 3. Snapshot identity and digest

| Artifact | SHA-256 (first 16) | Notes |
|---|---|---|
| `data/studio.db` pre-merge | `cb99f8c9bfbe0a52` | unchanged from manifest-session value; inode 271891263 |
| `data/studio.db-wal` pre-merge | `839d44b647d5aa67` | identical at preflight and immediately pre-merge |
| `data/studio.db-shm` pre-merge | `a1e77176221bf80f` | byte-identical to preflight copy |
| `data/project_state_store.json` | `3c7e716ad239988a` | untouched by recovery |
| Rollback snapshot | `data/recovery-snapshots/20260927T231537Z-pre-scene002-merge-recovery/` | manifest + independently re-hashed; read-only dir; **preserved intact after recovery** |
| Recovery composite | `55895a004db965f9` | verified unchanged after execution |
| Merge manifest | `c9703bfba7ae75c0` | both manifest files, unchanged after execution |

## 4. Exact rows inserted (45, all from the verified manifest)

| Table | Rows | Primary keys |
|---|---|---|
| `storyboard_blueprints` | 1 | `sbp_project_5907c60cddbc_scene_002_3400a20b` |
| `storyboard_blueprint_versions` | 2 | `sbv_dbafa23cf4a1` (v1), `sbv_3b88a1e0ef95` (v2) |
| `storyboard_shots` | 10 | v1: `sbs_77d3ae4fe1e9`, `sbs_8b1c822fc206`, `sbs_1d23d6055c17`, `sbs_4d91b1c6bd3c`, `sbs_ee2d6576f016` · v2: `sbs_a7648698ad00`, `sbs_a8481a439ea5`, `sbs_be2cce8fab93`, `sbs_51d1500d227c`, `sbs_0046fb5192f0` |
| `previs_images` | 2 | `previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1`, `previs_project_5907c60cddbc_scene_002_job-20260906034509-132bb802-scene_002_shot_001` |
| `scene_memories` | 1 | (`project_5907c60cddbc`, `scene_002`) |
| `characters` | 6 | `chr_f1425498cb68` DRE, `chr_3c9e91741ef3` MAYA, `chr_4c77bbd9be1e` MOM, `chr_d3b00f4d3460` ELENA, `chr_ce2b04d72a51` JAY, `chr_fe48553696be` SIMONE |
| `character_reference_locks` | 7 | `charlock_bfec79ba3679`, `charlock_c452e7d94c88` (MAYA), `charlock_344bea5a21b1`, `charlock_b1b80e46a21e` (MOM), `charlock_edfb077d045f` (MAYA, superseded history), `charlock_a4eb1ffa5ec9` (MOM, superseded history), `charlock_df3781262c1b` (DRE, preserved `provisional`) |
| `reference_assets` | 11 | `ref_look_005f852638f5d162`, `ref_look_cfe3f6ce97b0f870`, `ref_look_87b04afe81963373`, `ref_look_e46ec07463f33414`, `ref_look_5992ae85d7ebddc0`, `ref_look_e6326bc566c1e716`, `ref_vt_character_face`, `ref_vt_character_full`, `ref_vt_environment`, `ref_env_6b726885ed67ae4d`, `ref_upl_a73e6281957642c58940a942` |
| `render_jobs` | 3 | `job-20260826055419-f33b1af4-scene_002_shot_001`, `job-20260906034509-132bb802-scene_002_shot_001`, `job-20260922044825-220d49c7-scene_002_shot_001` |
| `canonical_workflow_runs` | 1 | `workflow-86d38f89c7c9` |
| `shots` | 1 | (`project_5907c60cddbc`, `scene_002_shot_001`) |

## 5. Tables affected

Exactly the 11 manifest tables above. Full 146-table hash diff (pre-merge vs post-merge):
changed tables == the 11 plan tables; **unexpected table mutations: NONE.**

## 6. Updates

**0.** The merge is INSERT OR IGNORE only; the audited statement log for the production execution
(92 statements) contains only BEGIN IMMEDIATE / INSERT OR IGNORE / SELECT / COMMIT. Idempotent
re-run on production immediately after commit inserted 0 additional rows (run 2 = 0 changes),
matching the simulated idempotency proof.

## 7. Deletes

**0.** No DELETE statement exists anywhere in the implementation (AST-verified pre-write); the
superset proof shows every pre-merge row survived byte-identical in all 11 plan tables, and all
non-plan tables are hash-identical. No DDL, no file replacement, no WAL replacement, no checkpoint
of the production WAL, no JSON state store restoration, no `projects` modification.

## 8. Integrity verification (immediately after commit)

| Check | Result |
|---|---|
| Expected inserts 45 / actual 45 | **PASS** (per-table histogram exactly matches the manifest) |
| Updates 0 / Deletes 0 / Unexpected inserts 0 | **PASS** (45 == 45 == the 45 planned PKs; diff vs pre-merge shows nothing else added) |
| `PRAGMA foreign_key_check` | **PASS** — 0 violations (foreign_keys=ON during execution) |
| `PRAGMA integrity_check` | **PASS** — `ok` |
| Duplicate primary keys (8 core tables) | **PASS** — none |
| Duplicate canonical entities (one scene_002 blueprint / one approved chain / one scene memory) | **PASS** — none |
| Superset proof (every pre-merge row survives byte-identical) | **PASS** (dict-based row-multiset containment on all 11 plan tables) |
| 13 preserved Sept-27 5907 tables (`universe_nodes` 24, `universe_relationships` 24, `character_voice_profiles` 3, `dialogue_performance_cues` 9, `soundscape_layer_plans` 4, `crew_reasoning_records` 2, `crew_department_status_snapshots` 1, `film_cut_state` 1, `film_cut_versions` 1, `performance_audio_plans` 2, `screening_outputs` 1, `project_owners` 1, `projects` 1) | **PASS** — all counts unchanged |
| 35 project registrations and all 252 demo-era `render_jobs` | **PASS** — intact (render_jobs total 252 → 255 with the 3 PK-disjoint scene_002 history rows) |
| `verify_restore_invariants` (pre-merge baseline → live) | **PASS** — 0 failures across 22 projects |
| Post-commit stability | **PASS** — all 11 plan-table hashes identical at merge time and at the final verification pass (no drift) |

## 9. Scene_002 recognition

Live database content (all verified by direct query and by the application):

- Blueprint `sbp_project_5907c60cddbc_scene_002_3400a20b` — status `approved`,
  `current_version_id == approved_version_id == sbv_3b88a1e0ef95`.
- v1 `sbv_dbafa23cf4a1` — `approved` by `creator` at 2026-09-06T07:44:28.120443+00:00.
- v2 `sbv_3b88a1e0ef95` — `approved` by `creator` at **2026-09-26T20:17:28.940362Z** (exact, preserved).
- **Five v2 shots, all `approved`:** `sbs_a7648698ad00`, `sbs_a8481a439ea5`, `sbs_be2cce8fab93`,
  `sbs_51d1500d227c`, `sbs_0046fb5192f0` (render-contract lengths 4194 / 4006 / 3977 / 3981 / 4074).
- **Full recovered prompt contents** — v2 `provider_neutral_prompt` lengths 3200 / 3012 / 2994 / 3003 / 3074
  (shot-1 contract byte length 4,194 as in the manifest); v1 historical prompts intact (512-char era).
- **Seed 916483** present exactly once (previs `…_shot_001_b1d573f1`, status `complete`,
  image `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`); second previs row
  (failed historical job attempt) also present.
- **Recovered previs state**, **recovered characters** (6, all with locked appearance approvals in
  `continuity_state_json`), **recovered character locks** (7; DRE `charlock_df3781262c1b` preserved
  `provisional`, unresolved by design), **recovered reference assets** (11, approval states as restored),
  **recovered scene memory** (`approved_shots` == the five v2 shot ids in order, all `sbv_3b88a1e0ef95`).
- Legacy seed row `scene_002_shot_001` seed `1395559473` seed_locked 0; workflow run
  `workflow-86d38f89c7c9` status `blueprint_approved` with v1 approval payload.
- 14/14 recognition invariants PASS (§8 harness output in `/tmp/sr927_prod/recognition_live.log`).

## 10. Script isolation verification

- The `projects` table is not in the merge plan; no statement could touch it. Post-merge:
  `script_text` sha16 still `c66c7e8e573b00ec`, length 16,285 (live variant),
  `projects.updated_at` still `2026-09-20T19:36:10.670388+00:00` — unchanged by the recovery operation.
- The `script_text` conflict (live variant 16,285 chars vs composite variant 16,265 chars) is recorded
  as **BLOCKED_PENDING_CREATOR_AUTHORIZATION** and was NOT resolved; neither variant was selected.
- `execution_summary` and all other `projects.data` keys untouched.

## 11. Live state preservation

- All Sept-27 derived state intact (counts and table hashes, §8).
- The one previously observed timestamp touch — `screening_outputs[screening_5fcae99919620474]`
  (`updated_at` 2026-09-27T18:33:08.269530Z, content fields unchanged) — remains exactly as observed
  pre-merge: consistent with known backend activity (media-availability housekeeping), **not
  overwritten** by recovery (the recovery added no `screening_outputs` rows and modified none).
- JSON state store (`data/project_state_store.json`) untouched (sha `3c7e716a…`); the application did
  not fall back to JSON state — all recognition above resolves from the restored database through
  `DatabaseStorage` / `storyboard_blueprint_service` / `scene_production_pipeline_service`.

## 12. Lineage verification

Ran against the restored production database (`/tmp/sr927_prod/lineage_results.json`):

| Check | Result |
|---|---|
| Database identity valid | **PASS** — file identity (inode 271891263, schema_version 572) continuous through the merge; the live file was never replaced |
| Replacement detection valid | **PASS** — `write_lineage_registration` re-registered the SAME database identity (per manifest §Rollback step 8); `verify_render_lineage` now compares renders against inode 271891263 |
| Expected project identity valid | **PASS** — owner `user-f8e8be9141fa8b64`; project `project_5907c60cddbc` "I was reborn"; ownership mapping untouched |
| Expected creator identity valid | **PASS** — v1/v2 `approved_by = creator` with preserved timestamps; no approver mutation |
| Recovery state recognized | **PASS** — scene_002 v2 recognized (§9, §13) |
| No database replacement detected | **PASS** — `verify_render_lineage` ok with no warning post-registration (strict-mode capable; `STUDIO_LINEAGE_STRICT=1` available) |

## 13. Application behavior verification

- Same recognition harness as the successful simulation (`/tmp/sr927_manifest/recognition.py`),
  pointed at a materialization of the live post-merge database: **14/14 recognition invariants pass**;
  exit code 0 (its blocker-mutation tripwire did not fire).
- The running backend (`uvicorn main:app`, pid 30468, port 8010) — **before any restart** — serves the
  restored state over its HTTP API:
  - `GET /api/f51/studio/projects/project_5907c60cddbc` → "I was reborn";
  - `GET /api/f51/studio/projects/project_5907c60cddbc/scenes/scene_002/storyboard-blueprint` →
    blueprint `sbp_…_scene_002_3400a20b`, version `sbv_3b88a1e0ef95` (`approved`, approved_by
    `creator`, approved_at 2026-09-26T20:17:28.940362+00:00), **5 shots**.
- Real application recognition/generation preflight (`scene_production_pipeline_service.prepare_scene_batch`):
  **`ready: False`** with exactly the expected blockers —
  - Blocker 1: all five v2 shots report `Camera 'framing' is an unapproved AI suggestion (…)`;
  - Blocker 2: `Generation blocked: Scene scene_002 for setting scene_002. no approved canonical
    environment reference is available` (`canonical_setting_reference_missing`).
  Both blockers **remain in place** (required); neither disappeared without creator action.
- The application did not create a new scene, did not duplicate a version, and did not substitute
  JSON state for the restored database state.

## 14. Backend restart status

**No restart was required; the backend was left running (pid 30468) and was NOT restarted.**

Determination: (a) code — `main.py` opens SQLite connections per request/operation; no database
file handle or prepared state pins the pre-merge view, and `render.py:3416` lineage verification
runs per request; (b) process evidence — the pre-existing backend process serves the restored
scene_002 over HTTP (§13) without a restart; (c) the only startup-time lineage step
(`write_lineage_registration`) was performed out-of-band with the same-identity registration, so a
future restart (if any) will snapshot nothing and re-register the same identity. The startup
auto-snapshot-on-change logic stays silent: file identity never changed across the merge.

## 15. Remaining creator decisions

1. **script_text conflict (CONFLICT ①)** — still pending explicit creator authorization; no variant selected.
2. **Camera approvals** — the five v2 shots still carry AI_SUGGESTED camera framing; approval must be
   given by the creator via the camera approval surface (expected to create a new draft version per
   approved-board immutability).
3. **Canonical approved setting reference for scene_002** — still missing; requires the creator to
   upload/bind and approve a real image through the Scene 002 reference library.

No other decisions were made or permitted in this recovery; none of the three above was executed.

## 16. Provider activity

**None.** No network egress, no provider module execution, no image or video generation, no provider
configuration changes. All verification ran through deterministic local surfaces (SQLite reads and
the application's own dry-run recognition path).

## 17. Rollback status

**Not needed; not executed.** All post-merge verification passed. The verified rollback snapshot
`20260927T231537Z-pre-scene002-merge-recovery` (trio + state store, hash-pinned, independently
re-verified, read-only) is **preserved intact** together with the four earlier pre-merge snapshots.

## 18. Final recovery verdict

Every item of the final checklist holds:

45 rows restored · 0 updates · 0 deletes · foreign keys clean · database integrity clean ·
scene_002 recognized · v2 recognized · five v2 shots recognized · approval state preserved ·
prompt contents preserved · seed 916483 preserved · previs preserved · character approvals preserved ·
reference assets preserved · scene memory preserved · script_text unchanged · scene_001 NOT restored ·
live Sept-27 derived state preserved · lineage verification passes · expected camera blocker remains ·
expected setting blocker remains · no provider called · Runway credits spent 0.

## **RECOVERY VERIFIED**

---

## Final safety record

| Item | Value |
|---|---|
| Production DB modified | **YES — authorized recovery only** (45-row INSERT-only additive merge, exactly as manifested) |
| Recovery rows inserted | **45** |
| Updates | **0** |
| Deletes | **0** |
| Recovery composite modified | **NO** (`0899774f…`, `4dacc1c1…`, `55895a00…` re-verified unchanged post-execution) |
| Validation source modified | **NO** (`.validation/scene002_approval_20260926/` and `.validation/scene002_preflight_20260927/` untouched) |
| script_text modified | **NO** (conflict remains BLOCKED_PENDING_CREATOR_AUTHORIZATION) |
| Scene_001 creative state restored | **NO** (0 scene_001 creative rows; the only scene_001-scoped row is the manifest group-8 registry candidate `ref_upl_…`, approval_state `candidate`, canonical 0 — not an approval) |
| Camera approvals created | **NO** |
| Canonical setting reference created | **NO** |
| Provider called | **NO** |
| Runway credits spent | **0** |
| Rollback snapshot preserved | **YES** |
| Lineage verification | **PASS** |
| Application recognition | **PASS** (14/14 invariants; blockers preserved; HTTP API serves restored state) |
| Expected scene_002 blockers preserved | **YES** |

*Recovery incident formally closed and verified. STOP: no Runway, no FLUX.2, no further creative
changes. Execution evidence retained under `/tmp/sr927_prod/`
(`revalidate.py`, `execute_merge.py`, `revalidation_results.json`, `execute_merge_results.json`,
`lineage_results.json`, `recognition_live.log`) and the project rollback snapshots.*
