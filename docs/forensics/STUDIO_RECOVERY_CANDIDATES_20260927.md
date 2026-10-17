# STUDIO RECOVERY CANDIDATES — 2026-09-27

**Project:** `project_5907c60cddbc` ("I was reborn")
**Audit type:** Read-only forensic comparison. No restoration, no merge, no checkpoint, no winner selection.
**Forensic workspace:** `/tmp/studio-recovery-20260927/` (all copies and all SQLite inspection happened there; originals untouched — re-verified 15/15 unchanged by SHA-256 after all analysis).
**Method notes:**
- Live DB + WAL inspected via copies with the original filename pair (`studio.db` / `studio.db-wal`), opened with `mode=ro` — **no checkpoint was performed on any original or copy**.
- Sept 26 lineage DB inspected from its pre-approval backup copy renamed to its source name for correct WAL pairing, `mode=ro`.
- Nightly backup DBs (no WAL sidecars) inspected with `immutable=1` (fully read-only).
- Two terminal outputs late in this session came back garbled and inconsistent with the commands issued; they were discarded in full. Every number in this report comes from earlier verified runs, cross-checked at least twice.

**Time convention:** filesystem mtimes are shown as local; database timestamps are UTC. Local 16:17 = UTC 20:17 (UTC−4).

---

## 1. Verified current state (LIVE lineage)

- Unit: `studio-backend/data/studio.db` (9,072,640 B) + `studio.db-wal` (737,512 B, warm — held open by backend pid 30468 at snapshot time) + `studio.db-shm` (32,768 B).
- Snapshot taken 2026-09-27 ~10:31 local; `integrity_check` = ok; 130 tables; WAL applied read-only for inspection.
- Project row present (1 of 35 projects).
- Storyboard/creative estate for this project: **all empty** — `storyboard_blueprints` 0, `storyboard_blueprint_versions` 0, `storyboard_shots` 0, `previs_images` 0, `scene_memories` 0, `reference_assets` 0, `characters` 0, `knowledge_atoms` 0, `universe_nodes` 0, `render_jobs` 0, `video_assets` 0.
- `projects.data` (JSON blob): 34 keys; `approved_scenes: []`, `storyboard_wall: []`, `shot_approval_gates: []`, `render_queue: []`.
- `script_text`: 16,285 chars, SHA-1 `3a3902a85ad9a472…` — contains the merged-dialogue artifact `I need you to understand something.MAYA`.
- `film_cut_state` / `film_cut_versions`: cut `film-cut-project_5907c60cddbc-v1`, updated 2026-09-27T12:49/12:50Z (same-day writes, later than Sept 26 lineage).
- Restore-forensic context: backups `studio.db.pre-user-restore-20260927_104500` (Sep 27 06:31 local, 23 projects, **project absent**) and `recovery_artifacts_20260927/studio.db.pre-repair-20260927` (Sep 26 18:22 local, 23 projects, project absent) bracket a same-day restore/repair sequence; live now has 35 projects including this one.
- Live has small *post*-Sept-26 artifacts of its own: `crew_department_status_snapshots` 1 (created 2026-09-27T12:50:09Z, "sound_designer / Performance Audio"), `dialogue_performance_cues` 9 vs 8, `soundscape_layer_plans` 4 vs 8, `screening_outputs` 1 vs 6, `character_voice_profiles` 3 (all three IDs shared with Sept 26).

## 2. Verified September 26 state (SEPTEMBER 26 LINEAGE)

- Unit: `studio-backend/.validation/scene002_approval_20260926/` — pre-approval backup `studio.db.pre-approval-backup` (12,750,848 B) + its correctly paired `studio.db-wal.pre-approval-backup` (642,752 B) + shm; plus evidence JSONs (`blueprint_rows_before.json`, `shot_rows_before.json`, `version_rows_before.json`) and fingerprint copies.
- Two independent fingerprints (`store_copy_fingerprint_before.db` / `after.db`) are byte-identical to the pre-approval backup (same SHA-256) — backup provably unchanged since capture.
- Snapshot content (pre-approval capture, 2026-09-26 ~16:16 local / 20:16Z, after v2 draft creation at 19:30:21Z):
  - 12 storyboard blueprints (scenes 001–012), 13 blueprint versions, **65 storyboard shots** (5 per version × 13 versions).
  - `sbv_dbafa23cf4a1` (scene_002 v1) **approved**, `approved_at 2026-09-06T07:44:28.120443Z`, `approved_by: creator`; its 5 shots `approved`.
  - `sbv_3b88a1e0ef95` (scene_002 v2) **draft**, created 2026-09-26T19:30:21Z, `change_reason: create_or_update_draft`; its 5 shots `ready`.
  - scene_002 blueprint: `status=draft`, `current_version_id=sbv_3b88a1e0ef95`, `approved_version_id=sbv_dbafa23cf4a1`, unlocked.
  - Previs: 16 rows; `previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1` carries **seed 916483** (`previs_seed=916483`, `seed_locked=0`, `status=complete`, image `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`, job `storyboard_scene_002_shot_001_dashscope`, created 2026-07-27T16:15:29Z). A failed previs attempt for scene_002_shot_001 tied to `sbv_dbafa23cf4a1` exists (2026-09-06T03:45:09Z).
  - Seed 916483 also appears in the `render_contract_json` of approved shot `scene_002_shot_001` (sbv_dbafa23cf4a1) — `provider_neutral_prompt` begins "Wide establishing shot. Camera far back. Full environment visible. Characters small in frame…".
  - Full estate: 464 knowledge atoms, 175 bible sections, 9 bibles, 12 scene memories (newest 2026-09-26T15:30:21Z), 11 reference assets (newest 2026-09-26 09:27:23 local), 6 characters, 24 universe nodes + 24 relationships, 42 continuity graph versions, 6 color look bibles + 10 look bible rows, 9 production design plans, 9 camera grammar plans, 3 render jobs (scene_002_shot_001: openrouter-video failed 08-26, openrouter failed 09-06, local_ltx failed 09-22), 8 video assets (scene_001 shots 001–005, `available`, newest 2026-09-05T14:00:09Z), 6 `shots` rows (newest 2026-09-22T04:55:57Z).
  - `studio_workflow_project_states`: phase `intake`, `active` (updated 2026-09-05T19:07:56Z).
  - `projects.data`: same 34 keys as live; `script_text` 16,265 chars SHA-1 `d7179d25b48321c2…` (dialogue line properly split), `updated_at 2026-09-26T15:25:11Z`; `execution_summary` 294 keys; `scenes` subkey differs from live.
- **Crucially:** a *separate* quarantined WAL (see §5) extends this exact lineage 1 minute past capture and contains the v2 approval.

## 3. Verified project_state_store state (PROJECT STATE STORE)

- Unit: `studio-backend/data/project_state_store.json` (36,930,905 B, SHA-256 `3c7e716ad239988a…`).
- Single top key `projects`; this project present with the same 34 `projects.data` keys.
- `approved_scenes: []`, `storyboard_wall: []`, `shot_approval_gates: []`, `render_queue: []` (lengths 0) — **consistent with both DB lineages** on these fields.
- Zero occurrences of `sbv_dbafa23cf4a1`, `sbv_3b88a1e0ef95`, `916483` → the store holds **no storyboard artifacts at all**.
- Store `updated_at` = **2026-09-27T12:49:53.309236Z** — matches live's 12:49:52Z film-cut write to the second ⇒ the store is a **same-day re-projection of the live DB**, not an older independent snapshot.
- `script_text`/`execution_summary.scenes` byte-match live (store = live view); all other 31 keys identical across all three sources.

## 4. Complete artifact comparison (per artifact, three-way)

Legend: **L** = current live, **S** = September 26 lineage, **P** = project state store.

| Artifact | LIVE | SEP 26 | STORE | Classification |
|---|---|---|---|---|
| `projects` row (34-key JSON blob) | ✔ | ✔ | ✔ | PRESENT IN ALL THREE; 31 keys PRESENT IN ALL THREE AND IDENTICAL |
| `script_text` | 16,285 ch | 16,265 ch (dialogue split) | = live | PRESENT IN ALL THREE BUT DIFFERENT (S vs L/P); Sept 26 is later-dated text |
| `execution_summary` (294 keys) | differs in `scenes` | differs in `scenes` | = live | PRESENT IN ALL THREE BUT DIFFERENT (`scenes` only) |
| `projects.data.updated_at` | 2026-09-20T19:36Z | 2026-09-26T15:25Z | 2026-09-27T12:49Z | PRESENT IN ALL THREE BUT DIFFERENT |
| `approved_scenes` / `storyboard_wall` / `shot_approval_gates` / `render_queue` | [] | [] | [] | PRESENT IN ALL THREE AND IDENTICAL (all empty everywhere) |
| Scene 002 blueprint `sbp_…scene_002_3400a20b` | — | ✔ (status draft, cur=sbv_3b88…, appr=sbv_dba…) | — | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| Blueprint set (12, scenes 001–012) | — | ✔ | — | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| Approved v1 `sbv_dbafa23cf4a1` (approved_at 2026-09-06, by creator) + 5 approved shots | — | ✔ | — | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| v2 draft `sbv_3b88a1e0ef95` + 5 ready shots | — | ✔ (draft) | — | PRESENT ONLY IN SEPTEMBER 26 LINEAGE (as draft); **approved in the stale-WAL composite, see §5** |
| 65 storyboard shots (13 versions × 5) | 0 | 65 | 0 | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| Seed 916483 | 0 occurrences | previs row + shot render_contract | 0 | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| Previs image `previs_…scene_002_shot_001_b1d573f1` + 15 others | 0 | 16 | 0 | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| Scene memories (12), reference assets (11), characters (6), universe (24+24), knowledge (464/175/9), continuity graphs (1+42), color/design/camera suites | 0 | ✔ | 0 | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| Render jobs (3, scene_002_shot_001, all failed) / video assets (8, scene_001, available) | 0 | ✔ | 0 | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| `shots` legacy rows (6) | 0 | 6 | 0 | PRESENT ONLY IN SEPTEMBER 26 LINEAGE |
| `film_cut_state` + `film_cut_versions` (v1 draft, same cut_id/timeline/scene_order) | updated 2026-09-27T12:49/50Z | updated 2026-09-05T12:34Z | — | PRESENT IN BOTH BUT DIFFERENT (timestamps only; content identical) |
| `character_voice_profiles` (3 IDs) | ✔ | ✔ (same 3 IDs) | — | PRESENT IN BOTH; IDs IDENTICAL (row content differs — see §6) |
| `project_owners` | ✔ | ✔ | — | PRESENT IN BOTH (1 row each) |
| `crew_department_status_snapshots` | 1 (2026-09-27T12:50Z, sound_designer) | 42 | — | PRESENT IN BOTH BUT DIFFERENT (no shared IDs; live row L-only, 42 S-only) |
| `dialogue_performance_cues` | 1 | 8 | — | PRESENT IN BOTH BUT DIFFERENT (no shared IDs) |
| `soundscape_layer_plans` | 4 | 8 | — | PRESENT IN BOTH BUT DIFFERENT (2 live-only, 8 S-only) |
| `screening_outputs` | 1 | 6 | — | PRESENT IN BOTH BUT DIFFERENT (1 shared, 5 S-only) |
| Global (non-project) tables | `render_attempts` 36, `canonical_workflow_transitions` 0, `character_stagings` 0, `director_commentary_records` 2, `access_users` 1, `sessions` 0 | `render_attempts` 0, transitions 17, stagings 3, commentary 0, users 2, sessions 1 | — | PRESENT IN BOTH BUT DIFFERENT (global scope) |
| Any storyboard/creative data at all in store | — | — | none | PRESENT ONLY IN LIVE/LINEAGE — i.e. **absent from store by design** |

Count summary: of 34 `projects.data` keys — 31 PRESENT IN ALL THREE AND IDENTICAL, 3 PRESENT IN ALL THREE BUT DIFFERENT (`script_text`, `execution_summary`, `updated_at`). Of 45 project-scoped DB tables with rows — 36 PRESENT ONLY IN SEPTEMBER 26 LINEAGE, 8 PRESENT IN BOTH BUT DIFFERENT, 1 (projects) three-way. Zero artifacts exist ONLY-STORE. Zero artifacts PRESENT ONLY IN LIVE at the creative level; live-only items are post-prune operational rows (§8).

## 5. Newer recovery candidates (Phase 4, read-only search)

Full inventory probed (all opened read-only; backups via `immutable=1`; stale-WAL composite built only inside /tmp):

| Candidate (original path) | mtime | Integrity | Project 5907 content |
|---|---|---|---|
| `studio-backend/backups/studio_20260918_032327.db` | Sep 18 03:23 | ok | 12 bp / 13 ver / 65 shots; approved: **`sbv_33ba18db0a10` (scene_001 v1, approved 2026-07-28T10:59:04Z) AND `sbv_dbafa23cf4a1`**; seed 916483 ✔; 464 atoms; 12 scene memories; no v2 |
| `studio_20260919_032327.db` | Sep 19 | ok | identical profile to 09-18 (max shot upd 2026-09-17T04:56:19Z) |
| `studio_20260920_032327.db` | Sep 20 | ok | identical profile; projects.data.updated_at 2026-09-05T14:54:42Z |
| `studio_20260923_110809.db` | Sep 23 11:08 | ok | 12 bp / **12 ver / 60 shots**; approved: `sbv_dbafa23cf4a1` only; **no v2 version row**; seed ✔; 10 reference assets; max shot upd 2026-09-21T09:03:48Z |
| `studio_20260924_160721.db` | Sep 24 16:07 | ok | project **absent** (post-prune store shape) |
| `studio_20260925_160721.db` | Sep 25 | ok | project absent |
| `studio_20260926_160722.db` | Sep 26 16:07 | ok | project absent |
| `studio-backend/data/studio.db.pre-user-restore-20260927_104500` | Sep 27 06:31 | ok | 23 projects; project absent; 0 storyboard rows |
| `studio-backend/data/recovery_artifacts_20260927/studio.db.pre-repair-20260927` | Sep 26 18:22 | ok | 23 projects; project absent |
| `studio-backend/.validation/data/studio.db` (+wal/shm) | Sep 24 01:29 | ok | project absent; 0 storyboard rows |
| `data/studio.db` (repo root) | Aug 30 | ok | different/legacy DB (211 pages); project absent |
| `studio-backend/data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` | **Sep 26 16:17 local** | n/a (WAL) | see below — **the decisive find** |
| `backups/project_state_store_before_project_prune_20260830_035544.json` | Aug 30 | parse ok | 600 projects; project present but approved_scenes/wall/gates/queue all 0; no version/seed markers (updated_at 2026-08-27) |
| `studio-backend/.validation/project_state_store.json` | Sep 25 22:08 | parse ok | project absent |
| `studio-backend/reports/master_e2e_validation/project_state_store.json` | Sep 21 10:47 | parse ok | project absent |

**Stale WAL = continuation of the September 26 lineage (byte-proven):**
- Header salts identical to `studio.db-wal.pre-approval-backup` (salt1 2249769608, salt2 1479982619, page size 4096).
- All 156 leading frames byte-identical to the pre-approval WAL; the stale WAL carries 271 frames (115 more).
- Composite (built only at `/tmp/studio-recovery-20260927/phase4/pair_sept26_plus_stalewal/`, Sept 26 capture DB + stale WAL): `integrity_check` ok; `sbv_3b88a1e0ef95` **status `approved`, approved_at 2026-09-26T20:17:28.940362Z, approved_by `creator`, change_reason "scene_002 regeneration after creator-approved screenplay correction (2026-09-26)"**; its 5 shots `approved`; scene_002 blueprint flips to `status=approved`, `current_version_id = approved_version_id = sbv_3b88a1e0ef95`. All post-capture updates touch scene_002 only.
- Interpretation (factual): the quarantined WAL is a later segment of the same WAL; the v2 approval happened at 2026-09-26T20:17:28Z, i.e. ~1 minute after the pre-approval capture was taken, and **no store examined contains a later state of this lineage's creative data**. This composite is the newest known representation of the September 26 creative state — but it is a forensic composite, not a store that exists as a unit on disk.

## 6. Data conflicts

1. **script_text:** live/store (16,285 ch, merged line `…something.MAYA`, updated 2026-09-20) vs Sept 26 (16,265 ch, dialogue split, updated 2026-09-26, change_reason references "creator-approved screenplay correction"). Conflict class: PRESENT IN ALL THREE BUT DIFFERENT.
2. **v2 approval status:** Sept 26 pre-approval capture says v2 = draft; stale-WAL composite says v2 = approved (2026-09-26T20:17:28Z). Same lineage, two points in time — resolved by WAL ordering, but any recovery choice must pick which representation to honor.
3. **scene_001 approved version:** Sept 26 lineage has **no** approved version for scene_001; Sept 18–20 backups contain `sbv_33ba18db0a10` (approved 2026-07-28) whose 5 shots are `approved`. Sept 23 backup also lacks it (12 versions only). Provenance of its removal is not recorded in any examined store.
4. **Scene-coverage divergence:** Sept 26 lineage has 12 scene blueprints; Sept 23 backup has 12 blueprints but 60 shots (one scene's v1 shots absent: scene_001 v1 shots). Backups are internally consistent; they simply differ from the Sept 26 lineage.
5. **Estate-table timestamp skew:** e.g. `characters` newest update 2026-09-17 (backups) vs 2026-09-17 (Sept 26 lineage identical); `reference_assets` 10 (Sept 23) vs 11 (Sept 26); `screening_outputs` 1 shared + 5 S-only; `soundscape_layer_plans` disjoint sets (2 live-only vs 8 S-only). Conflicts are additive rather than contradictory, but row-level merges would be non-trivial.
6. **Store vs DB clock:** store `updated_at` (2026-09-27T12:49:53Z) post-dates every creative table it mirrors; store carries no divergent creative data (all markers 0). No conflict — store is a projection.

## 7. Data that exists only in the September 26 lineage

12 blueprints; 13 versions (incl. v1 approved `sbv_dbafa23cf4a1` + v2 draft `sbv_3b88a1e0ef95`); 65 storyboard shots (5 approved v1); seed 916483 + previs row `…b1d573f1` (16 previs rows); scene memories (12); reference assets (11); characters (6); universe nodes/relationships (24/24); knowledge bibles/sections/atoms (9/175/464); continuity graphs + 42 versions; color look bibles (10 rows/6), colorist look plans (6), color palette continuity records (6); production design plans/env/prop/costume (9/9/9/2); camera grammar plans (9); casting role breakdowns (6); character reference locks (7); audition package (1); canonical workflow run (1); 3 render jobs; 8 video assets; 6 legacy `shots`; crew reasoning records (45); department snapshots (42); dialogue performance cues (8); soundscape plans (8); screening outputs (5 extra); studio workflow project state; Sept-26-dated `script_text` and `execution_summary.scenes`.

## 8. Data that exists only in the current live lineage

- `crew_department_status_snapshots` row `crew-status-cf860e5eb8b2` (2026-09-27T12:50:09Z, sound_designer, derived from overview) — live-only.
- 1 live-only `dialogue_performance_cue` and 2 live-only `soundscape_layer_plans` (IDs disjoint from Sept 26).
- `film_cut_state`/`film_cut_versions` timestamp advances (2026-09-27T12:49/50Z) — content otherwise identical.
- 2 global `director_commentary_records` (0 in Sept 26); 36 global `render_attempts` (0 in Sept 26) — from other activity.
- 1 `access_users` row fewer (2→1) and 0 `sessions` (1 in Sept 26) — global.
- The live unit itself (35 projects incl. this one) after the 09-27 restore/repair sequence.

## 9. Data that exists only in the state store

None. The store holds zero artifacts (version IDs, seed, shot IDs: 0 occurrences) and all 34 project keys match live byte-for-byte except none — its only unique aspect is its own `updated_at` (2026-09-27T12:49:53Z), which post-dates the live DB's 12:49:52Z film-cut write by ~1s. Historical store backups (`before_project_prune` Aug 30, 600 projects) likewise contain no storyboard artifacts for this project.

## 10. Items that must not be overwritten

- The live DB unit (`studio.db` + `-wal` + `-shm`) and the live backend's ability to keep its WAL — any recovery must not checkpoint, truncate, or replace these files in place.
- `project_state_store.json` (current) — it is today's projection and the only store reflecting the 2026-09-27 state.
- `studio-backend/.validation/scene002_approval_20260926/` — the pre-approval capture and its paired WAL are the anchor of the September 26 lineage; both WAL files must remain unpaired-to-originals, untruncated, untouched.
- `studio-backend/data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` — the newest segment of that lineage (contains the v2 approval); quarantined but evidentiary.
- `studio-backend/backups/studio_20260918|19|20_*.db` — sole carriers of `sbv_33ba18db0a10` (scene_001 v1 approved).
- `recovery_artifacts_20260927/studio.db.pre-repair-20260927` and `studio.db.pre-user-restore-20260927_104500` — restore-sequence evidence.
- The forensic workspace `/tmp/studio-recovery-20260927/` (manifest + inspection DBs) until any human decision is executed.

## 11. Items requiring human editorial decisions

1. Which `script_text` is canonical: live/store (merged line, older mtime) vs Sept 26 (split line, newer, tied to a "creator-approved screenplay correction").
2. Whether the v2 approval recorded at 2026-09-26T20:17:28Z (stale-WAL composite) stands as creator intent, or whether the pre-approval capture (v2 = draft) is the intended stopping point.
3. Whether scene_001's approved v1 `sbv_33ba18db0a10` (only in Sept 18–20 backups) should be treated as superseded/withdrawn (it is absent from the Sept 23–26 lineage) or still desired.
4. Whether the 42 Sept-26 department snapshots / 45 reasoning records / 8 soundscape plans etc. (operational history) are worth re-attaching, or whether only the creative estate (blueprints/versions/shots/previs/knowledge/characters) matters.
5. Whether live-only operational rows (09-27 sound_designer snapshot, live cues/plans) must survive any recovery (they would constrain any table-level restore).
6. Which store is canonical going forward (DB vs JSON projection) before any merge-of-record is even considered.

## 12. Proposed recovery options (no recommendation, no selection)

All options below are *proposals only*. Nothing has been executed; none touches production paths.

- **Option A — Composite reattachment (newest known state).** Build, in a scratch DB from /tmp copies, the Sept 26 lineage with the stale-WAL composite applied (v2 approved). Would restore the largest, newest creative state (65 shots incl. 10 approved across two scenes… specifically: v1 5 approved + v2 5 approved, 12 blueprints, full estate, seed 916483). Requires resolving conflict #2 in favor of the composite and conflict #3 (scene_001 approval stays absent).
- **Option B — September 26 pre-approval capture as-is.** Reattach rows from the pre-approval capture DB only (v2 = draft). Restores the estate but at 2026-09-26 ~20:16Z; discards the 1-minute-later v2 approval unless re-approved manually in-app.
- **Option C — Hybrid selective restore.** Import only the creative-estate tables (blueprints/versions/shots/previs/knowledge/characters/universe/reference) from the composite, leaving live operational tables untouched; requires manual reconciliation for the 8 "both but different" tables and the 3 differing `projects.data` keys.
- **Option D — Approval-only patch.** Keep live as-is; surface the Sept 26 blueprint/shot *content* to the creator via export/diff (e.g. regenerate scene_002 from seed 916483 evidence) and let the in-app approval flow re-create state forward — no historical rows reattached.
- **Option E — No restore; archive-only.** Freeze the forensic workspace and all candidate stores as evidence, change nothing, re-decide after the live backend's provenance for the 09-27 restore/repair sequence is fully understood.
- **Option F — Full state-machine replay (most invasive).** Restore Sept 26 composite DB as a *parallel* database and migrate all 35 live projects into it — explicitly flagged as highest-risk and not advisable without a separate migration design and human sign-off.

Every option requires: a cold backend, fresh SHA-256 manifests, a new pre-change backup, and a written human approval. None has been requested or performed here.

---

## Appendix A — Forensic copy manifest (Phase 1)

Workspace: `/tmp/studio-recovery-20260927/` — copies made 2026-09-27 ~10:31 local; full ISO timestamps + full SHA-256 in `manifest/copy_manifest.json`. Re-verified after analysis: 15/15 copies match recorded SHA-256, and 15/15 originals still match their snapshot hashes (unchanged during the audit).

| # | Original path (repo-relative) | Copy path (workspace-relative) | Bytes | SHA-256 (first 16) |
|---|---|---|---|---|
| 1 | `studio-backend/data/studio.db` | `copy-live/studio.db` | 9,072,640 | `cb99f8c9bfbe0a52…` |
| 2 | `studio-backend/data/studio.db-wal` | `copy-live/studio.db-wal` | 737,512 | `f0c68cdaf22a20f6…` |
| 3 | `studio-backend/data/studio.db-shm` | `copy-live/studio.db-shm` | 32,768 | `3e23b6d525b1303e…` |
| 4 | `studio-backend/.validation/scene002_approval_20260926/blueprint_rows_before.json` | `copy-sept26/blueprint_rows_before.json` | 440 | `b8f268dfcdf39794…` |
| 5 | `…/shot_rows_before.json` | `copy-sept26/shot_rows_before.json` | 2,727 | `e4eddc26bc740311…` |
| 6 | `…/studio.db-shm.pre-approval-backup` | `copy-sept26/studio.db-shm.pre-approval-backup` | 32,768 | `687226341ec9610c…` |
| 7 | `…/studio.db-wal.pre-approval-backup` | `copy-sept26/studio.db-wal.pre-approval-backup` | 642,752 | `2947761e100a2fa5…` |
| 8 | `…/studio.db.pre-approval-backup` | `copy-sept26/studio.db.pre-approval-backup` | 12,750,848 | `0899774f74f595ee…` |
| 9 | `…/studio.db.pre-approval-backup-shm` | `copy-sept26/studio.db.pre-approval-backup-shm` | 32,768 | `fd4c9fda9cd3f9ae…` |
| 10 | `…/studio.db.pre-approval-backup-wal` | `copy-sept26/studio.db.pre-approval-backup-wal` | 0 | `e3b0c44298fc1c14…` (empty) |
| 11 | `…/version_rows_before.json` | `copy-sept26/version_rows_before.json` | 7,165 | `78d4893556613704…` |
| 12 | `…/test3_live_runway_image/store_copy_fingerprint_after.db` | `copy-sept26/test3_live_runway_image/store_copy_fingerprint_after.db` | 12,750,848 | `0899774f74f595ee…` |
| 13 | `…/test3_live_runway_image/store_copy_fingerprint_before.db` | `copy-sept26/test3_live_runway_image/store_copy_fingerprint_before.db` | 12,750,848 | `0899774f74f595ee…` |
| 14 | `…/test3_live_runway_image/test3_report.json` | `copy-sept26/test3_live_runway_image/test3_report.json` | 2,582 | `8acb6f73f08e5374…` |
| 15 | `studio-backend/data/project_state_store.json` | `copy-state-store/project_state_store.json` | 36,930,905 | `3c7e716ad239988a…` |

Note: rows 8, 12, 13 share one SHA-256 — the fingerprints independently prove the pre-approval backup was byte-identical before and after capture.

## Appendix B — Phase 2/3 inspection set (inside workspace only)

- `inspect-live/studio.db{,-wal,-shm}` — live pair, `mode=ro`, no checkpoint.
- `inspect-sept26/studio.db{,-wal}` — pre-approval backup renamed to source name for pairing, `mode=ro`.
- `phase4/pair_sept26_plus_stalewal/studio.db{,-wal}` — Sept 26 capture DB + quarantined WAL (the v2-approval composite). Composite only; originals never touched.

```
RECOVERY AUDIT COMPLETE
NO PRODUCTION DATA MODIFIED
NO WAL MODIFIED
NO DATABASE MODIFIED
NO STATE STORE MODIFIED
NO CANONICAL CREATIVE STATE MODIFIED
```
