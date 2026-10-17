# STUDIO PROJECT STATE RECONCILIATION

**Subject:** `project_5907c60cddbc` — "I was reborn"
**Mode:** strict read-only forensic comparison. No writes were made to any original file. No backend was restarted. No external provider was contacted.
**Method:** every SQL query was executed against SHA-256-verified copies under `/tmp/studio-audit/` (`live.db`, `preLineage.db`, `pre.db`, `pre-restore.db`, `state_store.json`), opened with read-only URIs. The pre-approval WAL was applied to a **copy** only. The state store was parsed in memory only.
**Originals re-verified unchanged after the audit (digests identical to capture):**

```
cb99f8c9bfbe0a52404064e703a3ee1ad0298aad18fd4e2e11e64ef7fd46067c  studio-backend/data/studio.db
f0c68cdaf22a20f6bde7294bea7e6221fcc3be74660a7f59aec61c7e33838f3b  studio-backend/data/studio.db-wal
3e23b6d525b1303eb5bb78610bc2ec079cb0988b2f38d4a961fe8eb401288475  studio-backend/data/studio.db-shm
3c7e716ad239988a918124bcb6e3c16a12d6e6c1deaba0e473d6b31cb74994f7  studio-backend/data/project_state_store.json
0899774f74f595eebf62fe2401c9277f0dae440472319ee289e2189980dad556  .validation/scene002_approval_20260926/studio.db.pre-approval-backup
2947761e100a2fa52b8cbc9c7f9c576b03b62c165eee32817bcf4b4234c8d696  .validation/scene002_approval_20260926/studio.db-wal.pre-approval-backup
```

---

## 0. FILE VERIFICATION (exact files present)

| Artifact | Size | mtime (local) | Notes |
|---|---|---|---|
| `data/studio.db` | 9,072,640 B | Sep 27 07:45 | live base; `page_size 4096`, `page_count 2233`, `freelist_count 0`, `journal_mode wal`, `auto_vacuum 0`, `schema_version 572` |
| `data/studio.db-wal` | 737,512 B | Sep 27 08:50 | live WAL; refreshed **after** the state store's last write |
| `data/studio.db-shm` | 32,768 B | Sep 27 02:48 | |
| `data/project_state_store.json` | 36,930,905 B | Sep 27 08:49 | 1,203 projects |
| `.validation/scene002_approval_20260926/studio.db.pre-approval-backup` | 12,750,848 B | Sep 26 16:16 | `page_count 3113`, `freelist_count 133`, `schema_version 572` |
| `.validation/scene002_approval_20260926/studio.db-wal.pre-approval-backup` | 642,752 B | Sep 26 16:16 | contains committed-but-uncheckpointed transactions |
| `.validation/.../studio.db-shm.pre-approval-backup` | 32,768 B | Sep 26 16:16 | |
| `.validation/.../studio.db.pre-approval-backup-shm` / `-wal` | 32,768 B / 0 B | Sep 26 16:24 | sidecars of an earlier inspection copy; WAL is empty |
| `data/studio.db.pre-user-restore-20260927_104500` | 3,403,776 B | Sep 27 06:31 | 23 projects, **0** storyboard rows, project_5907 absent, render_jobs 252 (max 2026-05-23) |
| `data/studio.db.bak_phase2_20260707_151547`, `studio.db.cleanup-backup-20260729073804`, `studio.db.pre-orphan-cleanup-20260817_122217` | — | Jul 7 / Jul 29 / Aug 17 | older snapshots, untouched |
| `.validation/.../test3_live_runway_image/` | — | Sep 27 06:29–06:30 | test report + two fingerprint DBs |
| `.validation/.../blueprint_rows_before.json`, `shot_rows_before.json`, `version_rows_before.json` | — | Sep 26 16:16 | row captures taken with the backup |

Both databases have `schema_version 572`, identical table sets (140 tables), and `auto_vacuum 0`. Therefore the live/backup differences are **data (DML), not schema (DDL)**.

### Four comparison views
- **A. LIVE BASE** — `studio.db` alone.
- **B. PRE-APPROVAL BASE** — `studio.db.pre-approval-backup` alone (12 bbv / 60 shots).
- **C. PRE-APPROVAL LINEAGE** — pre-approval base **plus** its WAL (13 bbv / 65 shots). This is the material actually in the Sept 26 backup lineage.
- **D. STATE STORE** — `project_state_store.json`.

---

## 1. CURRENT PROJECT ROW (A vs C vs D)

| Column | A live | C pre-lineage | B pre-base |
|---|---|---|---|
| `updated_at` | `2026-09-20T19:36:10.670388+00:00` | `2026-09-26T15:25:11.781717` | `2026-09-05T14:54:42.370381` |
| `length(data)` | 473,929 | 473,851 | 473,873 |

The **live row is older than the lineage row** (Sep 20 vs Sep 26). The lineage row is the newest DB representation of the project that exists anywhere except the state store.

## 2. CURRENT PROJECT DATA JSON

Key sets are **identical** across all four sources (no keys added or removed anywhere). Differing keys:

- **B → C (the WAL transaction's rewrite of the project row):**
  - `script_text` (16,285 → 16,265 chars): two line-level parse corrections — `"I need you to understand something.\nMAYA"` (newline split restored) and the stray scene heading line `DRE — BEFORE THE FALL` removed. These are structural parse fixes, not narrative changes.
  - `execution_summary`: scene_002 `text`/`description` updated consistently with the same parse fix; all 14 scenes (`scene_001`–`scene_014`) present in both.
  - `updated_at`: Sep 5 → Sep 26.
- **C → A/D (live + store vs lineage):** live `script_text` (sha16 `7cb09678ff7c65fb`) and `execution_summary` (sha16 `a32b43fd8a50558e`) are **byte-identical to the state store's entry** and differ from lineage in the same two fields (live/store retain the merged `something.MAYA` line and the `DRE — BEFORE THE FALL` heading line that lineage removes). Store vs live differ **only** in `updated_at` (store `2026-09-27T12:49:53.309236+00:00`, live JSON `2026-09-20T19:36:10.670388+00:00`).

Conclusion: the live project row was hydrated from the state store (or from a common upstream), not evolved from the Sept 26 DB. The two script variants are sibling revisions on **different edit lines** — neither is a superset of the other (lineage has the parse fixes; live/store's text retains a heading the lineage text lacks).

## 3. CURRENT PROJECT STATE STORE ENTRY (D)

Top-level store: `{ "projects": { … } }` with **1,203 projects**. Entry `project_5907c60cddbc` present with keys: `project_id, title, created_at, updated_at, script_text, execution_summary, approved_scenes, reviewed_scenes, scene_review_status, film_cut, archive_snapshots, memory_context, collaboration, source_stats, render_provider, production_bible, render_provider_integrations, crew_agents, shot_approval_gates, storyboard_wall, render_queue, rights_safety_clearance_board, reference_study_library, interactive_modules, producer_dashboard, project_dashboard, agent_activity_timeline, continuity_register, risk_register, next_actions, co_director_workflow, co_director, director_intent, provider_overrides`.

Storyboard-relevant values: **`approved_scenes: []`**, `reviewed_scenes: []`, `scene_review_status: {}`, `storyboard_wall: []`, `shot_approval_gates: []`, `render_queue: []`.

The three disputed identifiers — `sbv_dbafa23cf4a1`, `sbs_77d3ae4fe1e9`, `916483` — appear **nowhere in the entire 36.9 MB file** (verified by whole-file scan and per-project scan; no other project references them either).

## 4. ALL STORYBOARD BLUEPRINT VERSIONS (C, 13 rows)

| version_id | scene | ver | status | approved_at | approved_by | source_version_id | created_at |
|---|---|---|---|---|---|---|---|
| sbv_beda30c49d3e | scene_001 | 1 | draft | — | — | — | 2026-09-21T09:03:48.927922+00:00 |
| **sbv_dbafa23cf4a1** | **scene_002** | **1** | **approved** | **2026-09-06T07:44:28.120443+00:00** | **creator** | — | 2026-07-27T20:15:08.855204+00:00 |
| **sbv_3b88a1e0ef95** | **scene_002** | **2** | **draft** | — | — | sbv_dbafa23cf4a1 | **2026-09-26T19:30:21.668456+00:00** (WAL-added) |
| sbv_665f0acb147e | scene_003 | 1 | draft | — | — | — | 2026-07-27T20:15:45.026296+00:00 |
| sbv_5c4dd2439b89 | scene_004 | 1 | draft | — | — | — | 2026-07-27T20:16:03.967562+00:00 |
| sbv_7a570a58a053 | scene_005 | 1 | draft | — | — | — | 2026-07-27T20:16:44.946539+00:00 |
| sbv_76ef95908019 | scene_006 | 1 | draft | — | — | — | 2026-07-27T20:17:26.288664+00:00 |
| sbv_1b6484095966 | scene_007 | 1 | draft | — | — | — | 2026-07-27T20:19:24.953207+00:00 |
| sbv_8aa9b9b5a6ee | scene_008 | 1 | draft | — | — | — | 2026-07-27T20:19:27.121227+00:00 |
| sbv_b04e1e535747 | scene_009 | 1 | draft | — | — | — | 2026-07-27T20:19:55.264224+00:00 |
| sbv_4603804d5ee4 | scene_010 | 1 | draft | — | — | — | 2026-07-27T20:19:56.728124+00:00 |
| sbv_72c944aee5fc | scene_011 | 1 | draft | — | — | — | 2026-07-27T20:20:45.026835+00:00 |
| sbv_2b962fb0a93a | scene_012 | 1 | draft | — | — | — | 2026-07-27T20:20:46.372138+00:00 |

Base (B) holds 12 of these; **sbv_3b88a1e0ef95 (scene_002 v2 draft) exists only in the WAL lineage.** The 12 shared rows are byte-identical between B and C (the WAL added a row; it did not mutate existing version rows). **Live (A) holds zero** blueprint versions — for any project.

Blueprints (`storyboard_blueprints`, 14 rows, all this project): scene_002 blueprint `sbp_project_5907c60cddbc_scene_002_3400a20b` has `approved_version_id = sbv_dbafa23cf4a1` in **both** B and C (the approval pointer is in the base backup; the WAL did not create it).

## 5. ALL STORYBOARD SHOTS (C, 65 rows: 13 versions × 5 shots)

- **v1 scene_002 (sbv_dbafa23cf4a1) — 5 shots, all `approved`, updated 2026-09-06T07:44:28.120443+00:00:**
  `sbs_77d3ae4fe1e9` (#1, seed 916483), `sbs_8b1c822fc206` (#2), `sbs_1d23d6055c17` (#3), `sbs_4d91b1c6bd3c` (#4), `sbs_ee2d6576f016` (#5).
- **v2 scene_002 (sbv_3b88a1e0ef95) — 5 shots, all `ready`, created/updated 2026-09-26T19:30:21.67…+00:00, WAL-only:**
  `sbs_a7648698ad00` (#1), `sbs_a8481a439ea5` (#2), `sbs_be2cce8fab93` (#3), `sbs_51d1500d227c` (#4), `sbs_0046fb5192f0` (#5).
- **Scenes 001, 003–012 — 60 shots, all `ready`** (5 per scene, Jul 27/Sep 21 generations).

Status totals: **approved 5, ready 60**. All 65 rows exist **only** in the Sept 26 lineage; live holds zero shots. No shot row differs between B and C except the 5 added v2 rows.

## 6. ALL RENDER_CONTRACT_JSON VALUES

- v2 scene_002 contracts: lengths **4194, 4006, 3977, 3981, 4074** bytes (shots 1–5), each with `provider_neutral_prompt` (wide establishing / medium / medium close-up / dynamic transition / close-up detail), `seed` absent, `seed_locked: 0`.
- v1 scene_002 shot 1 contract: **1409 bytes**, contains `"seed": "916483"`, `seed_locked: 0`, and the establishing-shot prompt.
- v1 shots 2–5 and all other scenes: same compact contract shape; no contract contains `916483` except v1 shot 1.
- Contract JSON is byte-identical between B and C for all shared rows. Live has none.

## 7. ALL STORYBOARD APPROVAL METADATA

- `storyboard_blueprint_versions` row `sbv_dbafa23cf4a1`: `status='approved'`, `approved_at='2026-09-06T07:44:28.120443+00:00'`, `approved_by='creator'`, `change_reason='create_or_update_draft'`, `inspection_json` 614 B (render_readiness `ready`, no blockers), `metadata` 3,669 B containing continuity review **`scr_a1f08a0d1d9a`** — `status completed`, `reviewed_at 2026-09-06T07:43:51.887733+00:00`, reviewer `continuity_intelligence`, 5 medium issues, readiness `ready_for_creator_approval`.
- `storyboard_blueprints.metadata` for scene_002: **B (base) = 3,700 B** — `{"preserve_locked_shots": true, "continuity_review": {…scr_a1f08a0d1d9a…}}`; **C (lineage) = 31 B** — `{"preserve_locked_shots": true}`. The WAL transaction **replaced** the review-bearing metadata with the stub; the identical review survives on the version row's own `metadata`, so no information is lost in C, but the placement differs between B and C.
- `studio_approval_decisions` / `studio_approval_gates`: **0 rows in every view** (the approval lives in the blueprint/version rows, not these tables).
- State store approval surface: `approved_scenes: []` (empty).
- Live: no approval metadata at all.

## 8. ALL PREVIS IMAGE REFERENCES

- Exactly **one** shot-level reference in the lineage: `sbs_a7648698ad00` (v2 shot 1, `ready`) → `previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1`. Present in C; **absent in B** (0 shot-level references).
- The referenced `previs_images` row exists in **both B and C** (it is old): `id = previs_…_b1d573f1`, `status complete`, **`previs_seed = 916483`**, `seed_locked 0`, `image_path = /previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`, `job_id = storyboard_scene_002_shot_001_dashscope`, created/updated `2026-07-27T16:15:29.931991`, its `blueprint_id`/`blueprint_version_id`/`storyboard_shot_id` columns empty, `approved 0`. Attempt 1, attempt metadata `{}`.
- A second, unrelated failed previs row for the v1 shot (`…_job-20260906034509-132bb802-scene_002_shot_001`, status `failed`, Sep 6, no seed) links v1 shot 1 to failed `render_jobs` row `job-20260906034509-132bb802-scene_002_shot_001` (provider `openrouter`).
- `916483` appears in exactly three lineage locations: `previs_images.previs_seed`, `render_jobs.input_payload`, and v1 shot 1's `render_contract_json.seed`. It is a **seed value, not an image id**.
- Live `previs_images`: **0 rows**.

## 9. ALL SEED VALUES (per version, shots 1–5; ∅ = none)

| version | seeds |
|---|---|
| sbv_dbafa23cf4a1 (scene_002 v1) | **916483**, ∅, ∅, ∅, ∅ |
| sbv_3b88a1e0ef95 (scene_002 v2) | ∅, ∅, ∅, ∅, ∅ |
| sbv_beda30c49d3e (scene_001) | ∅, ∅, ∅, ∅, ∅ |
| sbv_665f0acb147e (scene_003) | 415306, ∅, ∅, ∅, ∅ |
| sbv_5c4dd2439b89 (scene_004) | 535159, ∅, ∅, ∅, ∅ |
| sbv_7a570a58a053 (scene_005) | 819731, ∅, ∅, ∅, ∅ |
| sbv_76ef95908019 (scene_006) | 750214, ∅, ∅, ∅, ∅ |
| sbv_1b6484095966 (scene_007) | 625055, ∅, ∅, ∅, ∅ |
| sbv_8aa9b9b5a6ee (scene_008) | 254295, ∅, ∅, ∅, ∅ |
| sbv_b04e1e535747 (scene_009) | 977357, ∅, ∅, ∅, ∅ |
| sbv_4603804d5ee4 (scene_010) | 352983, ∅, ∅, ∅, ∅ |
| sbv_72c944aee5fc (scene_011) | 972530, ∅, ∅, ∅, ∅ |
| sbv_2b962fb0a93a (scene_012) | 463157, ∅, ∅, ∅, ∅ |

All `seed_locked` values are **0** (no seed is pinned anywhere). Only **one seed value in the entire project — 916483 — is tied to an existing generated image** (the Jul 27 qwen previs PNG).

## 10. ALL SCENE IDENTIFIERS

- `storyboard_blueprint_versions`: `scene_001` … `scene_012` (12 scenes).
- `storyboard_shots`: `scene_001` … `scene_012`.
- `scene_memories`: `scene_001` … `scene_012` (14 rows total for the project across the DB, one per scene).
- `projects.data.execution_summary.scenes`: **14** scenes, `scene_001` … `scene_014` (scenes 013/014 exist only in parsed script data, no storyboard coverage).

## 11. ALL PROJECT UPDATE TIMESTAMPS (chronological)

| When (UTC unless noted) | What |
|---|---|
| 2026-07-24T05:05:08.847568+00:00 | project created (store + live JSON `created_at`) |
| 2026-07-27T16:15:29.931991 | previs image (seed 916483) generated |
| 2026-07-27T20:15–20:20 | scenes 002–012 blueprint versions + shots created |
| 2026-09-05T14:54:42.370381 | pre-base project row `updated_at` |
| 2026-09-06T03:44/03:45 | scene_002 memory / failed previs render attempt |
| 2026-09-06T07:43:51 / 07:44:28 | continuity review completed / **v1 approved by creator** |
| 2026-09-20T19:36:10.670388+00:00 | live + store project JSON `updated_at` (the current live/store text variant) |
| **2026-09-26T15:25:11 → 19:30:21** | **WAL transaction(s): project row + scene_002 memory + blueprint metadata rewritten (≈15:25–15:30), scene_002 v2 draft + 5 shots inserted (19:30)** |
| 2026-09-26 16:16 **local** | `.validation` backup copied (consistent with the WAL contents above, given local-time mtimes) |
| 2026-09-27 06:31 local | `studio.db.pre-user-restore-20260927_104500` snapshot |
| 2026-09-27 07:45 local | current live `studio.db` mtime |
| 2026-09-27T12:49:53.309236+00:00 | state store entry `updated_at` (last store write for this project) |
| 2026-09-27 08:50 local | live WAL last refresh |

## 12. RECORDS PRESENT IN THE PRE-APPROVAL LINEAGE BUT ABSENT FROM LIVE (project scope)

Everything in the Sept 26 lineage is absent from live. Specifically for this project:

- **6 rows WAL-added on top of the base:** `sbv_dbafa23cf4a1`-scoped… precisely: `sbv_3b88a1e0ef95` (bbv), shots `sbs_a7648698ad00`, `sbs_a8481a439ea5`, `sbs_be2cce8fab93`, `sbs_51d1500d227c`, `sbs_0046fb5192f0`. The ID triple (`sbv_dbafa23cf4a1`, `sbs_77d3ae4fe1e9`, `916483`) is present in **base + lineage**, absent from live.
- **All 13 bbv + 65 shots + 14 blueprint rows + 20 previs_images rows** (project-scoped).
- **scene_memories for scene_001–012** including the scene_002 memory whose approved-shot list references the five v1 shots.
- **`studio_workflow_project_states`** row (`project_5907c60cddbc`, phase `intake`, state `active`, `legacy_collaboration_migrated: true`).
- `canonical_workflow_runs` (1, with `approvals.storyboard` = v1 approval record) + `canonical_workflow_transitions` (17).
- Entire project-derived layers: universe_nodes (219), universe_relationships (509), characters (103), knowledge_bibles/sections/atoms (9/175/464), continuity_graphs/versions (17/74), film_dna (4), color/casting/production-design/performance/crew tables, visual_models, `shots` (8), render_attempts (36), reference_assets, character_reference_locks, `final_short_film_packages` (1), `video_assets` (9, 8 live-absent), `sessions` (1), `access_users` (`user-a67ac2e5bf3ae313`, `user-e36ab1377b44be6d`), 4 `project_owners` mappings, `render_jobs` (26 live-absent of 28).

## 13. RECORDS PRESENT IN LIVE BUT ABSENT FROM THE PRE-APPROVAL LINEAGE (project scope + global)

- Project-scoped: **none of the disputed artifacts** — live contains **zero** traces of `sbv_dbafa23cf4a1`, `sbs_77d3ae4fe1e9`, or `916483` in **any** of its 140 tables (exhaustive per-table, per-column scan).
- Live-only registrations (global): 31 additional `projects` (35 total vs 4; max `updated_at` 2026-09-24), 250 additional `render_jobs` (252 vs 28; newest = seeded `demo-job-001/002`, 2026-05-23), 18 additional `final_short_film_packages`, 3 additional `video_assets`, 12 `project_owners` mappings (0 shared with backup), 1 `access_user` (`user-f8e8be9141fa8b64`; **user sets are disjoint**), plus small counts in `director_commentary_records`, `crew_reasoning_records`, `crew_department_status_snapshots`, `dialogue_performance_cues`, `character_voice_profiles`, `soundscape_layer_plans`, `video_frame_analyses`.
- For this project, the only live-side state is: the hydrated project row + `scene_013/014` in its execution_summary.

## 14. RECORDS THAT DIFFER BETWEEN THE TWO (all pairs)

- **B ↔ C (WAL delta):** 3 in-place updates — `projects` row (script_text/execution_summary/updated_at), `scene_memories` scene_002 (approved-shots JSON re-serialized, `updated_at` Sep 6 → Sep 26 15:30), `storyboard_blueprints` scene_002 metadata (3,700 B → 31 B); plus 6 inserted rows. No other table changed.
- **C ↔ A/D:** `projects.data` — `script_text` and `execution_summary` differ (the two sibling script variants described in §2); `updated_at` differs (Sep 26 lineage vs Sep 20 live vs Sep 27 store). Everything else about the project differs by **absence**, not content.
- **D ↔ A:** state store entry vs live project row are byte-identical except `updated_at`.
- Shared-but-divergent rows (global): `demo_studio_cinematic_001` (pre Sep 22 vs live May 23), `project_752ca3944869` (Sep 6 vs Sep 16), `project_ca31687b1ca7` (Aug 30 03:52 vs 08:09) — `updated_at` conflicts in both directions; and disjoint `access_users`.

## 15. DOES THE WAL CONTAIN TRANSACTIONS NOT REPRESENTED IN THE BASE DATABASE?

**Yes — for the pre-approval backup.** Its WAL carries committed-but-uncheckpointed transactions touching **5 tables**: `projects` (row rewrite), `scene_memories` (scene_002 update), `storyboard_blueprints` (metadata replacement), `storyboard_blueprint_versions` (+1 row: the scene_002 v2 draft, `source_version_id = sbv_dbafa23cf4a1`), `storyboard_shots` (+5 rows, scene_002 v2, `ready`, one with previs link). Write activity spans ≈15:25–19:30 UTC on Sep 26 — i.e. **at least three write operations**, including the v2-draft generation that followed the Sep 6 approval.

**No — for the live database.** The live WAL (737,512 B, refreshed as recently as Sep 27 08:50 local) adds **nothing** to the live base view: every table's full ordered row-dump is byte-identical with and without it (all 140 tables, both count- and content-level). Its frames are stale against the current base read snapshot.

## 16. DOES THE STATE STORE CONTAIN NEWER INFORMATION THAN THE SEPT 26 LINEAGE?

**Newer by wall clock, but strictly poorer for this project's storyboard domain.**

- The store entry was touched **2026-09-27T12:49:53Z** — newer than every lineage timestamp (newest lineage: 2026-09-26T19:30:21Z). Globally the store is the newest artifact (1,203 projects, including projects absent from both DBs).
- But for `project_5907c60cddbc`, the store's storyboard surface is **empty**: no blueprint versions, no shots, no approval records, no previs/seed references, `approved_scenes: []`. It contains **less** storyboard information than the Sept 26 lineage, not more. Its only genuinely newer content for this project is the timestamp itself and the script/execution-summary variant it shares with live.
- Conversely, the Sept 26 lineage is the **sole carrier** of the approved storyboard, the v2 draft, and seed 916483. The store cannot reconstruct any of it.

---

## INTERPRETATION (evidence-consistent timeline; labeled as inference)

Three coexisting state lineages are observable:

1. **The Sept 26 working database** (preserved only in `.validation/scene002_approval_20260926/`): 4 projects; full derived-content layers; the Jul–Sep storyboard history; the Sep 6 v1 approval; and — in its WAL — the Sep 26 v2-draft generation. This is the only place the disputed IDs exist.
2. **The current live `studio.db`**: a database whose own row population spans the April–May demo era (seeded demo projects, `demo-job-001/002`, render_jobs Apr 13–May 23) plus later registrations hydrated from the state store (including this project's row, `created_at` Jul 24, text = store variant). Zero derived content for any project, `freelist_count 0`, disjoint user records, and `schema_version` identical to the backup. These observations are consistent with live being a **different database file** (rebuilt/restored from a demo-era or seed-era lineage) that re-registered projects from the store — **not** with live being the Sept 26 file after a bulk delete. The morning snapshot `studio.db.pre-user-restore-20260927_104500` (23 projects, 0 storyboard rows, no project_5907) sits on this same lineage.
3. **The state store**: newest global state; for this project it holds the hydrated project shell and an **empty** storyboard state, byte-identical (except `updated_at`) to the live DB row.

Neither source "replaces" the other: the live pair and the store hold newer *registrations*, the Sept 26 lineage holds newer *creative artifacts*. Any merge decision must respect that these are disjoint record populations joined only by `project_id`.

---

# SAFE TO PRESERVE

- **`.validation/scene002_approval_20260926/` in its entirety** — the pre-approval base DB **and** its WAL **and** the `*_rows_before.json` captures and `test3_live_runway_image/` artifacts. This directory is the **only** home of: the approved v1 storyboard (`sbv_dbafa23cf4a1` + shots `sbs_77d3ae4fe1e9`, `sbs_8b1c822fc206`, `sbs_1d23d6055c17`, `sbs_4d91b1c6bd3c`, `sbs_ee2d6576f016`), the v2 draft (`sbv_3b88a1e0ef95` + 5 ready shots + the previs link), seed **916483** and its generated image record, the continuity review `scr_a1f08a0d1d9a`, and every derived-content row for this project. The WAL is not optional: without it the v2 draft and the shot-level previs reference vanish.
- **`project_state_store.json` exactly as it stands** — the newest global registry (1,203 projects), byte-verified; it is the source the live project row was hydrated from.
- **The live pair `studio.db` + `studio.db-wal` + `studio.db-shm` as a unit** — sole home of 31 registered projects, 252 render_jobs, 19 packages, 4 video assets, and user `user-f8e8be9141fa8b64`. The live WAL, though content-stale at audit time, was refreshed at 08:50 local and belongs to the live record.
- **All other snapshots:** `studio.db.pre-user-restore-20260927_104500`, `studio.db.pre-orphan-cleanup-20260817_122217`, `studio.db.cleanup-backup-20260729073804`, `studio.db.bak_phase2_20260707_151547`.
- **The audit copies and digests** in `/tmp/studio-audit/` and this report, which pin the exact byte state of every original at audit time.

# CONFLICTS REQUIRING DECISION

1. **Two sibling script variants.** Lineage text (Sep 26, parse-fixed, `updated_at` newest of any DB row) vs live/store text (Sep 20 content, Sep 27 store touch, retains the `DRE — BEFORE THE FALL` heading). Neither is a superset; a human must pick the canonical `script_text`/`execution_summary`.
2. **Approved v1 vs v2 draft for scene_002.** v1 is `approved` with seed 916483 and a generated previs image; v2 is `ready` (5 shots, no seeds), derives from v1, and references the v1-era previs image. Both belong to the same blueprint. Keep-both / supersede / regenerate are all open — the data supports no automatic resolution.
3. **Approval-state divergence.** Lineage says scene_002 is approved (bbv status, blueprint `approved_version_id`, scene_002 memory approved-shot list); the store says `approved_scenes: []` and live has nothing. If the store is treated as authoritative, the approval disappears from the UI; if the lineage is authoritative, the store must be updated — a semantic choice, not a mechanical one.
4. **Blueprint metadata placement.** The 3.7 KB continuity review moved from `storyboard_blueprints.metadata` (base) to `storyboard_blueprint_versions.metadata` (lineage). Any merge should decide where it lives; the lineage placement is loss-free.
5. **Identity/registry conflicts.** `access_users` sets are disjoint (live-only `user-f8e8be9141fa8b64` vs backup `user-a67ac2e5bf3ae313` / `user-e36ab1377b44be6d`), 1 live session vs 1 backup session, 16 distinct `project_owners` mappings with zero overlap, and three shared projects with bidirectionally conflicting `updated_at`. These must be reconciled before any database-level merge could even be contemplated.
6. **Provenance of live.db itself.** The evidence (demo-era rows, zero derived content, disjoint users, identical schema) strongly suggests the live file is not the Sept 26 file mutated, but a different lineage. Confirming this (and whether the true post-Sep-26 working DB still exists anywhere) is a decision-requiring unknown, not a settled fact.

# DATA THAT MUST NOT BE OVERWRITTEN

- **The six WAL-added rows** (`sbv_3b88a1e0ef95`; `sbs_a7648698ad00`, `sbs_a8481a439ea5`, `sbs_be2cce8fab93`, `sbs_51d1500d227c`, `sbs_0046fb5192f0`) and the **three WAL-rewritten rows** (`projects` Sep 26 text, `scene_memories` scene_002 Sep 26 version, blueprint metadata in either placement). They exist **only** inside the `.validation` lineage; any overwrite of that directory or of `studio.db.pre-approval-backup`'s WAL is unrecoverable destruction.
- **Seed 916483 and its image record** (`previs_…_b1d573f1`, `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`) — the only reproducibility anchor (seed + prompt + output path) for the approved shot 1. Note `seed_locked = 0` everywhere, so nothing else pins this seed.
- **The five approved v1 shots and their approval metadata** (approved_at/by, continuity review, `approved_version_id` pointer) — the only approval record that exists for this project anywhere.
- **The live store and live DB rows for the 31 live-only projects**, 250 live-only render_jobs, 18 live-only packages, and live-only users/ownership mappings — the Sept 26 lineage has no copy of these; restoring a DB wholesale would destroy them.
- **The current `script_text`/`execution_summary` variant in store + live** — even if the lineage text is chosen as canonical, the current variant must be preserved as history before any change, because it contains content the lineage text lacks.
- **The live WAL file** — must not be checkpointed, truncated, or deleted independently of the DB; it is part of the live unit and was modified as recently as Sep 27 08:50 local.

---

*End of report. Audit copies remain under `/tmp/studio-audit/` for re-verification; no original was modified at any point (digests re-verified post-audit, all identical).*
