# SCENE_002 RECOVERY MERGE MANIFEST — 2026-09-27

Companion to `SCENE002_READ_ONLY_COMPARISON_20260927.md`. This pass **constructs and proves** the merge; it does not execute it. Simulation workspace: `/tmp/sr927_manifest/` (`merge_sim.py` = manifest builder + idempotent merge simulator; `merge_manifest.json` / `merge_manifest_final.json` = machine manifest; `recognition.py` = application recognition pass; `final_run.log` = clean-run output; `clean_run.log` = first full run).

## SCENE_002 RECOVERY MERGE MANIFEST

**Operation:** explicit additive merge of scene_002 recovery rows from the verified September 26 composite into the current production database. Semantics, in order of binding force:

1. **Single transaction**, `BEGIN IMMEDIATE` … `COMMIT`; any failure → `ROLLBACK` (no half-merge can persist; SQLite guarantees atomicity).
2. **`INSERT OR IGNORE` only** — inserts rows whose primary keys are absent; every existing row is left byte-identical. **No `UPDATE`, no `DELETE`, no DDL, no checkpointing, no file replacement, no table drop/truncate, no whole-database restore.**
3. **Scope pinned per row** (not per database): only the rows enumerated below, selected by primary key from the verified composite. The `projects` table (script_text / execution_summary) is **not** in the plan — see Script Text Conflict.
4. **Pre-conditions (all hard gates):** verified manifest digest; source composite digest `55895a004db965f9…` (== fresh rebuild from originals `0899774f…` + WAL `4dacc1c1…`); immutable pre-merge snapshot taken via `recovery_lineage_guard.capture_recovery_snapshot`; backend stopped; `build_expected_counts` baseline captured.
5. **Post-conditions (all must pass before restart):** idempotency (re-run = 0 changes), `PRAGMA foreign_key_check` empty, `PRAGMA integrity_check ok`, `verify_restore_invariants` vs baseline, the recognition pass of §Application Recognition Result, and unchanged hashes for all non-manifest content (superset-only proof).

**Row classification key:** A = CANONICAL CREATIVE STATE · B = STRUCTURAL STATE REQUIRED FOR CANONICAL STATE · C = DERIVED OR REGENERABLE · D = HISTORICAL OPERATIONAL STATE · E = EXCLUDE.

**Completeness proof (item 14 of the brief):** every one of the 146 tables was swept for rows connected to `project_5907c60cddbc` — by `project_id` column, by `scene_id`/`shot_id` patterns, and by `asset_id` membership of the project's 8 video assets (covering the asset-keyed tables that lack a `project_id` column: `director_commentary_records`, `shot_boundaries`, `video_scene_memories`, `video_keyframes`). SQLite declared foreign keys exist on exactly 4 tables (`character_stagings`, `crew_task_log`, `project_owners`, `universe_relationships`); all are empty or satisfied for the planned rows. The sweep found **34 project-scoped row groups in the composite; 11 are in the restore plan (45 rows), 34 − 11 = 33 groups (plus `render_attempts`, discovered mid-scan, excluded with rationale) are excluded** with reasons below. This scan is how completeness is proven rather than assumed.

## Recovery Source

- **Database:** September 26 composite = `.validation/scene002_approval_20260926/studio.db.pre-approval-backup` (sha256 `0899774f74f595ee…`) + its byte-proven WAL continuation `data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` (sha256 `4dacc1c15fb5cd0d…`). Verified standalone form: `/tmp/sr927/composite/studio.db`, sha256 `55895a004db965f9…`, byte-identical to a fresh rebuild from the originals performed 2026-09-27.
- **WAL provenance (re-proven from fresh copies):** identical salts `8618c288 / 5836be1b`; all 156 frames of the pre-approval WAL are a byte-identical prefix of the 271-frame continuation; 3 commit frames in the prefix, 13 in the continuation. The v2 approval (`sbv_3b88a1e0ef95`, 2026-09-26T20:17:28.940362Z, by `creator`) lives in the continuation.
- **Excluded as sources:** Sept 18–23 nightlies (hold scene_001 v1 approval — out of scope), the JSON state store (structurally cannot carry storyboard artifacts; zero scene_002 markers verified), live WAL (different lineage, demo-era).

## Exact Rows To Restore

**45 rows total.** Columns: PK · relationship · class · source timestamp · in live? · insert? · conflict? · exclude?

**Group 1 — `storyboard_blueprints` (1 row)**

| PK | Relationship | Class | Source ts | Live? | Insert? | Conflict? | Exclude? |
|---|---|---|---|---|---|---|---|
| `sbp_project_5907c60cddbc_scene_002_3400a20b` | project 5907 / scene_002; current_version_id = approved_version_id = v2 | B (parent pointer; its `approved` status reflects creator's act) | updated 2026-09-26T20:17:28.940362Z | no | yes | no | no |

**Group 2 — `storyboard_blueprint_versions` (2 rows)**

| PK | Relationship | Class | Source ts | Live? | Insert? | Conflict? | Exclude? |
|---|---|---|---|---|---|---|---|
| `sbv_dbafa23cf4a1` | v1 of the scene_002 blueprint; approved by creator 2026-09-06 | A+B (creator approval + chain parent of v2) | approved 2026-09-06T07:44:28Z | no | yes | no | no |
| `sbv_3b88a1e0ef95` | v2; `source_version_id` = v1; change_reason = screenplay-correction regeneration | A+B | created 2026-09-26T19:30:21.668456Z; approved 2026-09-26T20:17:28.940362Z | no | yes | no | no |

**Group 3 — `storyboard_shots` (10 rows)**

| PK (storyboard_shot_id) | Relationship | Class | Source ts | Live? | Insert? | Conflict? | Exclude? |
|---|---|---|---|---|---|---|---|
| `sbs_77d3ae4fe1e9` | v1 shot 1 (`scene_002_shot_001`); 512-char historical prompt; image URL | A (v1 creator-approved) | approved 2026-09-06T07:44:28Z | no | yes | no | no |
| `sbs_8b1c822fc206` | v1 shot 2 | A | approved 2026-09-06 | no | yes | no | no |
| `sbs_1d23d6055c17` | v1 shot 3 | A | approved 2026-09-06 | no | yes | no | no |
| `sbs_4d91b1c6bd3c` | v1 shot 4 | A | approved 2026-09-06 | no | yes | no | no |
| `sbs_ee2d6576f016` | v1 shot 5 | A | approved 2026-09-06 | no | yes | no | no |
| `sbs_a7648698ad00` | v2 shot 1; previs_image_id → group 4 row; storyboard_image_url | A | created 2026-09-26T19:30:21.671648Z; approved 20:17:28.940362Z | no | yes | no | no |
| `sbs_a8481a439ea5` | v2 shot 2 | A | created 19:30:21.672168Z; approved 20:17:28Z | no | yes | no | no |
| `sbs_be2cce8fab93` | v2 shot 3 | A | created 19:30:21.672649Z; approved 20:17:28Z | no | yes | no | no |
| `sbs_51d1500d227c` | v2 shot 4 | A | created 19:30:21.673119Z; approved 20:17:28Z | no | yes | no | no |
| `sbs_0046fb5192f0` | v2 shot 5 | A | created 19:30:21.673626Z; approved 20:17:28Z | no | yes | no | no |

**Group 4 — `previs_images` (2 rows)**

| PK | Relationship | Class | Source ts | Live? | Insert? | Conflict? | Exclude? |
|---|---|---|---|---|---|---|---|
| `previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1` | scene_002 shot 1; status complete; **previs_seed 916483**; URL → surviving PNG | A+B (creator-visible output; seed = creative determinism anchor) | 2026-07-27T16:15:29Z | no | yes | no | no |
| `previs_project_5907c60cddbc_scene_002_job-20260906034509-132bb802-scene_002_shot_001` | failed attempt row | D (historical) | 2026-09-06T03:45:09Z | no | yes | no | no |

**Group 5 — `scene_memories` (1 row)**

| PK (project_id + scene_id) | Relationship | Class | Source ts | Live? | Insert? | Conflict? | Exclude? |
|---|---|---|---|---|---|---|---|
| project_5907c60cddbc / scene_002 | `approved_shots` = the five v2 shot entries in order | B (projection of the creator's v2 approval; required for board/room views) | updated 2026-09-26T16:17:28.947565Z | no | yes | no | no |

**Group 6 — `characters` (6 rows, project-scoped: the recovery set's scene_002 cast DRE/MAYA/MOM plus ELENA/JAY/SIMONE of the same shared character bible)**

| PK | Class | Source ts | Live? | Insert? | Conflict? | Exclude? |
|---|---|---|---|---|---|---|
| `chr_3c9e91741ef3` MAYA | A (locked appearance approval inside `continuity_state_json`) | 2026-09-06T04:39:11Z | no | yes | no | no |
| `chr_f1425498cb68` DRE | A (locked appearance approval) | 2026-09-06T02:20:43Z | no | yes | no | no |
| `chr_4c77bbd9be1e` MOM | A (locked appearance approval) | 2026-09-06T04:45:25Z | no | yes | no | no |
| ELENA, JAY, SIMONE (3 rows) | A (project character bible; referenced by the same scenes' knowledge estate) | 2026-07-27–09-06 | no | yes | no | no |

*Why included:* the reference-validation gate resolves scene characters by name/id and requires their locked approvals; a scene_002 restore without its cast is not recognized by the application. No live rows exist to conflict with.

**Group 7 — `character_reference_locks` (7 rows)**

| PK | Class | Note | Live? | Insert? |
|---|---|---|---|---|
| `charlock_bfec79ba3679`, `charlock_c452e7d94c88` (MAYA), `charlock_344bea5a21b1`, `charlock_b1b80e46a21e` (MOM), | A (locked, approved) | promoted after adherence-passed renders | no | yes |
| `charlock_edfb077d045f` (MAYA), `charlock_a4eb1ffa5ec9` (MOM) | D (superseded history) | audit trail | no | yes |
| `charlock_df3781262c1b` (DRE, scene_002 shot 1) | A-adjacent, **preserved `provisional`, unresolved by design** | must NOT be auto-promoted | no | yes |

**Group 8 — `reference_assets` (11 rows)** — 6 `ref_look_*` (approved character-face looks backing the locked approvals — A), 3 `ref_vt_*` (approved visual-training fixtures — A; 3 image files missing on disk, flagged in comparison report), `ref_env_6b726885ed67ae4d` (approved environment row, legacy shape: target_type NULL, canonical 0 — B, does NOT satisfy the setting gate), `ref_upl_a73e6281957642c58940a942` (scene_001 candidate upload — D/kept-as-is; restored only because it is part of the project's verified reference registry and inserts harmlessly as a candidate; **it cannot and must not satisfy scene_002's gate**). All: live? no · insert? yes · conflict? no.

**Group 9 — `render_jobs` (3 rows)** — `job-20260826055419-f33b1af4…` (openrouter-video), `job-20260906034509-132bb802…` (openrouter), `job-20260922044825-220d49c7…` (local_ltx) — all `scene_002_shot_001`, all `failed`. Class D (historical operational). Included because job lineage/history is expected by production tooling and their absence would make the estate incomplete; they are inert. Live has 252 unrelated demo rows in this table; the 3 new PKs are absent → clean inserts, no conflicts.

**Group 10 — `canonical_workflow_runs` (1 row)** — `workflow-86d38f89c7c9` (scene_002, v1, status `blueprint_approved`, approvals.storyboard = v1/creator). Class B (approval bookkeeping for the v1 chain). No `canonical_workflow_transitions` rows exist for this run (verified) → nothing else required. Live? no · insert? yes.

**Group 11 — `shots` (1 row, legacy seed table)** — `scene_002_shot_001`, seed `1395559473`, seed_locked 0. Class D (legacy seed registry consumed by render paths). Live? no · insert? yes.

**Group 12 — lineage/dependency rows required:** none beyond the above. Proof: FK sweep (§SCENE_002 RECOVERY MERGE MANIFEST completeness paragraph) found zero additional rows in any `*_links`, `*_dependencies`, `transitions`, `stagings`, or asset-keyed table tied to the 45 restored rows. The one extra FK-discovered row, `render_attempts` (scene_002_shot_001 attempt 1, provider runway, outcome `matched`, 2026-07-23), is **excluded** (class C/D — provider-score telemetry, regenerable, and referencing shot-id only, so nothing dangles if absent).

**Conflict column across all 45 rows:** `no` — verified: every planned PK is absent from live, and live rows sharing any table (e.g. 252 demo `render_jobs`) have disjoint PKs.

## Rows Explicitly Excluded

| Source group (composite) | Rows | Class | Why excluded |
|---|---|---|---|
| `render_attempts` scene_002 row | 1 | C/D | Provider adherence telemetry; regenerable; excluded from this scoped set (can be added later without breaking anything). |
| `knowledge_bibles/sections/atoms` | 9 / 175 / 464 | C | Derived intelligence from script; rebuilt from canonical state by existing pipelines. |
| `universe_nodes` + `universe_relationships` (lineage) | 24 + 24 | C | Live already holds its own Sept-27 24+24 for the same project — restoring lineage versions would duplicate entities. |
| color suite (look bibles/plans/palettes/verifications) | 10/6/6/3 | C | Advisory, regenerable. |
| production design suite | 9/9/9/2 | C | Advisory, regenerable. |
| `camera_grammar_plans` | 9 | C | Advisory, regenerable. |
| casting (role breakdowns/audition package) | 6 + 1 | C | Advisory, regenerable. |
| crew intelligence (reasoning/snapshots) | 45 + 42 | C | Advisory, regenerable. |
| performance audio (plans/cues/layers) | 8/10/16 | C | Live holds its own Sept-27 versions. |
| `video_assets` + `video_keyframes` | 8 + 24 | C/D | scene_001 renders (out of scope); nothing scene_002 depends on them. |
| `visual_models` | 3 | C | Training lineage, advisory. |
| film cut state/versions, workflow state/events/collaborator | 1+1, 1+4+1 | C | Editorial/workflow projections. |
| `screening_outputs` | 6 | C/D | Live holds 1 Sept-27 row; composites are older screenings. |
| `projects` row (script_text/execution_summary JSON) | 1 | **E — BLOCKED_PENDING_CREATOR_AUTHORIZATION** | See Script Text Conflict. |
| `project_owners` (composite Amb3rreed mapping) | 1 | E | Live already owns a mapping for 5907 (to `valadmin`); replacing ownership is an identity decision outside scene_002 scope. |
| `access_users` Amb3rreed + ltx_test, `sessions` | 2 + 1 | E | Account provisioning / expired session — outside scene_002 recovery scope. |

*Why the included groups are required (brief item 2):* Groups 1–3 are the canonical board the application renders from (B carries A's creator approvals). Group 4 carries the seed anchor and shot-1 previs binding. Group 5 is how the rooms display the approved chain. Groups 6–8 make the reference gates evaluate exactly as they did on Sept 26 (characters + locked approvals + registry), while deliberately leaving both render blockers in place. Groups 9–11 are inert historical lineage that completes the estate without creative effect. Nothing derived is restored.

## Live State Preserved

**Design guarantee:** the merge issues zero `UPDATE`/`DELETE`/DDL statements; it can only add rows whose PKs are absent. Therefore destruction of live state is impossible by construction, and the simulation verified it empirically (byte-level superset check + per-table hashes below).

**Live 5907 rows preserved (the Sept-27 derived estate), identified pre-merge:** `universe_nodes` 24, `universe_relationships` 24, `performance_audio_plans` 2, `soundscape_layer_plans` 4, `dialogue_performance_cues` 9, `character_voice_profiles` 3, `crew_reasoning_records` 2, `crew_department_status_snapshots` 1, `film_cut_state` 1, `film_cut_versions` 1, `screening_outputs` 1, `project_owners` 1, `projects` 1 (shell). Every one of these tables either is not in the plan, or (for `render_jobs`) received only PK-disjoint additions.

**Estate-wide preserved (verified by table-hash comparison, pre vs post):** all 35 project registrations, all 252 demo-era `render_jobs` (table total 252 → 255 with the 3 inert scene_002 history rows), the `valadmin` user + 12 ownership rows, `access_users`, `sessions`, `provider_configs`, and every non-plan table — the simulator reported `unexpected changed tables: NONE` and `pre-merge rows survived byte-identical: True` (row-multiset containment proven for every plan table; full-table SHA over every row for all 146 tables).

**Explicitly non-destructive by prohibition:** no `DROP TABLE`, no `TRUNCATE`/`DELETE FROM`, no database-file replacement, no whole-composite restore, no checkpoint of any WAL.

## Script Text Conflict

Status: **BLOCKED_PENDING_CREATOR_AUTHORIZATION.**

- **Where the conflict would occur:** the `projects` table, single row `project_5907c60cddbc`, JSON column `data` — keys `script_text` and `execution_summary`. Composite (parse-fixed) variant: 16,265 chars, sha16 `9a9c661823491a6a`, `updated_at` 2026-09-26T15:25:11Z. Live (merged-line) variant: 16,285 chars, sha16 `c66c7e8e573b00ec`, `updated_at` 2026-09-20T19:36:10Z. The variants differ in exactly 3 tiny blocks (two newline differences and the live-only `DRE — BEFORE THE FALL` heading fragment; both share the unresolved `NIGHTMaya` merged-heading artifact).
- **How the merge leaves it untouched:** the `projects` table is not in the merge plan at all — no statement in the plan can touch it. Simulated proof: post-merge `script_text` sha16 still `c66c7e8e573b00ec`, row `updated_at` still `2026-09-20T19:36:10.670388+00:00`, `execution_summary` unchanged; table hash of `projects` identical pre/post.
- **Consequence (accepted):** until the creator resolves CONFLICT ①, the restored scene_002 board coexists with the live script variant. Nothing in the application requires the projects row to change for scene_002 state to be recognized — proven by the recognition pass, which ran against the untouched live variant.

## Idempotency Result

Protocol: fresh byte copy of the live trio → merge run 1 → merge run 2 (identical logic) → compare. All operations single-transaction `INSERT OR IGNORE`.

| Metric | Run 1 | Run 2 |
|---|---|---|
| inserts | **45** (== 45 planned, 0 skipped) | **0** |
| updates | **0** | **0** |
| deletes | **0** | **0** |

`expected == run1: True`, `run2 zero: True`. No update was required at any point, so the STOP-on-update condition never triggered. Second execution also left every table hash unchanged (delta `{}`).

## Referential Integrity Result

All checks **PASS** on the simulated merged database (28/28 in the simulator; highlights):

1. Scene_002 FKs resolve — blueprint ↔ v1 ↔ v2 chain: `current_version_id == approved_version_id == sbv_3b88a1e0ef95`; `v2.source_version_id == sbv_dbafa23cf4a1`; both version rows present and approved.
2. Shot version relationships — all 10 scene_002 shots resolve to existing version rows; 5 v2 shots `approved`.
3. Character relationships — all 7 locks resolve to existing `characters` rows; 6 characters present; DRE lock still `provisional`; 3 locked appearance approvals present.
4. Reference relationships — 11 reference assets present; **no** scene_002 setting/canonical row created.
5. Previs relationships — shot 1's `previs_image_id` resolves to a `previs_images` row; seed 916483 present exactly once.
6. Lock relationships — as (3); provisional state preserved unresolved.
7. Approval relationships — v2 approval timestamp/author intact; scene memory `approved_shots` == the five v2 entries in order; workflow run present with v1 approval payload; `canonical_workflow_transitions` empty for the run (nothing dangles).
8. No duplicate PKs — verified on `storyboard_shots`, `storyboard_blueprint_versions`, `previs_images`, `reference_assets`, `characters`, `character_reference_locks`, `render_jobs` (GROUP BY … HAVING COUNT>1 = 0).
9. No duplicate canonical entities — one scene_002 blueprint, one approved chain, one scene memory; no second approval surface created.
10. No unrelated project state changes — `PRAGMA foreign_key_check` = empty; `integrity_check` = ok; every non-plan table hash identical; 35 projects and 252 demo jobs intact post-merge.

## Application Recognition Result

Executed through the **real** application stack (`DatabaseStorage` via `STUDIO_STORAGE_PATH`, `project_store`, `scene_production_pipeline_service`) against the simulated merged DB in `/tmp/sr927_manifest/recog/`:

- **14/14 recognition invariants hold:** scene_002 blueprint (approved) · v1 recognized · v2 recognized with exact approval timestamp · all five v2 shots approved · v2 prompt contents intact (shot-1 render contract byte length 4,194) · seed 916483 · both previs rows · 3 locked character appearance approvals · 11 reference assets · scene memory approved chain · no canonical setting row · no camera_plan · Sept-27 derived rows preserved · script_text untouched. Project title resolves: "I was reborn".
- **Preflight dry run on the merged copy:** `ready: False` with **exactly** the expected blockers — five shots each reporting `Camera 'framing' is an unapproved AI suggestion (…)`, and `Generation blocked: Scene scene_002 for setting scene_002. no approved canonical environment reference is available`.
- **Blocker-mutation tripwire:** the recognition script hard-fails (exit 2) if either blocker disappears without creator action. It did not trigger: both blockers survived, proving the merge restored state without inventing or clearing creative decisions.

## Rollback Procedure

Because the merge is additive-only, the snapshot is a complete inverse. Production sequence (only after independent review and authorization):

1. **Snapshot:** stop backend → `capture_recovery_snapshot('data/studio.db', reason='pre-scene002-merge-recovery', extra_files=[state_store])` → record manifest digests.
2. **Verify snapshot:** re-hash every file in the snapshot dir against its `snapshot_manifest.json`; refuse to proceed on any mismatch.
3. **Verify source composite:** `55895a004db965f9…` for the standalone verified composite (and/or rebuild-from-originals equality), WAL salt/frame continuity re-checked.
4. **Verify manifest:** hash `merge_manifest.json`; re-run the simulator's dry-run mode against a fresh /tmp copy of the live trio; require 45 planned inserts, 0 conflicts.
5. **Execute merge:** the same single-transaction script against production (backend stopped); log `total_changes`.
6. **Verify post-merge invariants:** `foreign_key_check` empty · `integrity_check ok` · `verify_restore_invariants` vs pre-merge baseline · idempotency re-run = 0 changes · table-hash diff == exactly the 11 plan tables with exactly +45 rows.
7. **Verify application recognition:** run the recognition pass against the live path (or a fresh snapshot copy) — 14/14 invariants + both blockers present.
8. **Verify lineage:** `write_lineage_registration` re-registers the (same) database identity; startup snapshot-on-change logic stays silent (no change event).
9. **Restart** only after 1–8 are green.

**If any post-merge verification fails: STOP. No improvised repair.** Restore the snapshot trio byte-verified against its manifest over `data/studio.db` + `-wal` + `-shm` (as one unit), re-run `verify_restore_invariants` against the pre-merge baseline to prove zero regression, then re-register lineage and restart.

## Prevention Safeguard Verification

Mechanisms verified in code this pass: `capture_recovery_snapshot` (hash-pinned, read-only-dir, fail-closed on capture failure), `verify_restore_invariants` (per-project creative-count regression = hard failure; `integrity_check` explicitly insufficient), `write_lineage_registration`/`verify_render_lineage` (inode+schema identity; wired into `main.py` lifespan with auto-snapshot on change, and into `render.py:3416` pre-render), merge atomicity (single transaction), and the manifest's own gates (PK-absence checks, superset proof, blocker tripwire).

| Scenario | Verdict | Mechanism / gap |
|---|---|---|
| A. Database file replaced | **BLOCKED/DETECTED** | `verify_render_lineage` inode mismatch → pre-render refusal; startup auto-snapshots the outgoing file; inode change is detectable even off-runtime. |
| B. Database rebuilt from JSON state | **BLOCKED/DETECTED** | Rebuild ⇒ new inode ⇒ lineage mismatch (A) ⇒ render refusal; plus `verify_restore_invariants` (creative counts had rows → 0 = hard failure). |
| C. DB exists but creative tables empty | **DETECTED** | Exactly `verify_restore_invariants`' purpose; also the comparison report's zero-count inventory; render readiness would fail closed (no shots). |
| D. Recovery source stale | **DETECTED (procedural)** | Composite provenance (WAL salts, frame continuity, approval timestamp) + required pre-merge verification step 3; not a runtime guard — procedural. |
| E. Source belongs to another project | **BLOCKED** | Manifest pins `project_id=project_5907c60cddbc` per row; FK/scan assertions fail on foreign rows; insertion of foreign PKs impossible without manifest change (hash-pinned). |
| F. Source belongs to another creator | **DETECTED (procedural)** | Creator identity lives in approval fields (`approved_by='creator'`) + ownership rows; manifest records them; no hard runtime check that approver == current owner — **residual gap (procedural check suffices here)**. |
| G. WAL missing (live) | **DETECTED (procedural)** | Live trio treated as a unit in snapshot/rollback; a missing live WAL with a checkpointed db is legitimate; an *unexpectedly* missing WAL alongside a non-empty db would surface as row-count changes in invariant verification. **Residual gap: no dedicated WAL-presence assertion.** |
| H. WAL lineage mismatch | **BLOCKED** | Salt + frame-prefix continuity is a hard verification gate before any merge authorization (fails closed). |
| I. Evidence files changed | **BLOCKED** | SHA-256 digest gates on every original; digests re-verified unchanged after every pass; any change aborts steps 2–3. |
| J. Merge interrupted halfway | **BLOCKED** | Single SQLite transaction — interrupt ⇒ rollback ⇒ database untouched; no partial state can persist. |
| K. Merge run twice | **ALLOWED (safe)** | Idempotent by proof: second run = 0 inserts/updates/deletes, zero state change. |
| L. Render attempted after DB replacement | **BLOCKED** | `render.py:3416` calls `verify_render_lineage` pre-render; strict mode env `STUDIO_LINEAGE_STRICT=1` available; failure is permanent refusal, no retry hammering. |

**Missing-safeguard notes (not implemented this pass, per brief):** (1) scenario F has no runtime approver↔owner equality check — the manifest's recorded identity plus review covers it here; (2) scenario G lacks a dedicated WAL-presence/consistency assertion outside the general invariant checks; (3) the manifest is hash-pinned procedurally (documented digests) rather than enforced by a runtime manifest-verification tool. None of these blocks the scene_002 merge as specified; all three are candidates for the next hardening pass.

## Remaining Creator Decisions

1. Which `script_text` variant becomes canonical (CONFLICT ①) — required only to lift the `projects`-row block; not required for the scene_002 merge itself.
2. Camera approval for the five v2 shots (via the camera approval surface after restoration; expect a new draft version per approved-board immutability).
3. Canonical approved setting reference for scene_002 (upload/bind and approve through the Scene 002 reference library; requires a real image file).

No other decision is required or permitted by this pass; none is made here.

## Safety Verification

- **Production DB modified: NO** — every operation ran on `/tmp` byte copies; live `data/studio.db` sha256 identical before and after (`cb99f8c9bfbe0a52…`).
- **Production WAL modified: NO** — live `-wal` identical (`0f5b8c18dea5d1a5…`); never opened, renamed, or checkpointed; `-shm` untouched (`7cad67acb7bd591e…`).
- **Recovery composite modified: NO** — originals identical (`0899774f74f595ee…`, `2947761e100a2fa5…`, `4dacc1c15fb5cd0d…`); verified standalone composite identical (`55895a004db965f9…`).
- **Validation artifacts modified: NO** — `.validation/scene002_approval_20260926/` untouched.
- **Backend restarted: NO** — no process started, stopped, or signaled.
- **Provider called: NO** — no network egress, no provider module execution; the dry run is the deterministic payload surface only.
- **Runway credits spent: 0**

*State store read via byte copy only (`3c7e716ad239988a…` unchanged). Simulation artifacts: `/tmp/sr927_manifest/`. STOP as instructed: no production merge executed, scene_001 untouched, cameras not approved, no setting reference created.*
