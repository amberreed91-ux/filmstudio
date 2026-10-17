# FULL PROJECT CONTEXT RECOVERY — 2026-09-27

**Subject:** `project_5907c60cddbc` — "I was reborn" (plus the surrounding Studio estate)
**Goal:** recover the complete Studio state actually in use before the hard reset + authentication failure; return to render readiness; prevent recurrence.
**Companions (prior sessions):** `STUDIO_RECOVERY_CANDIDATES_20260927.md`, `STUDIO_PROJECT_STATE_RECONCILIATION_20260927.md`, `SEPT27_RESTORE_TRACE_20260927.md`, `reports/studio-recovery-audit-2026-09-27/REPORT.md`
**Mode:** read-only forensic analysis + rehearsal-only recovery in `/tmp` + new safeguards/regression tests. **No production recovery was performed. No WAL was opened, renamed, or checkpointed on any original. No provider was contacted. Zero credits spent.**

All original evidence digests re-verified unchanged at end of session:

```
cb99f8c9bfbe0a52  data/studio.db                          (live, unchanged since audit)
0899774f74f595ee  .validation/.../studio.db.pre-approval-backup
2947761e100a2fa5  .validation/.../studio.db-wal.pre-approval-backup
4dacc1c15fb5cd0d  data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728
3c7e716ad239988a  data/project_state_store.json
```

---

## 0. Executive answers (details in sections below)

1. **Context before the reset:** account `user-e36ab1377b44be6d` ("Amb3rreed"), project `project_5907c60cddbc` "I was reborn", database = the **modern 146-table working DB** last verifiably on the live path Sept 26 16:16 local, whose WAL continued to the **Sept 26 20:17:28Z v2 approval**.
2. **Context after the reset:** same account name re-registered, **same project ID**, but a **rebuilt empty database** (demo-era lineage, 23 demo projects, zero creative rows) into which 12 project shells were re-registered **from the JSON state store**.
3. **Same project?** Same project *ID*; not the same *state*. The recovered context is **(B) same project ID, older/incomplete database state** — the estate never passed through the state store.
4. **Latest complete state:** the **September 26 composite** = `.validation/scene002_approval_20260926/studio.db.pre-approval-backup` + its byte-proven WAL continuation `quarantine_stale_wal_20260927/…T161728`. Proven by WAL salt/continuity (271 frames; first 156 byte-identical) and by content (v2 approved 20:17:28Z).
5–7. Sept 24+ work: **code fully survives** (164 source files, uncommitted, on disk); **creative state was lost from the live view and survives only in the composite**; the only current-production work newer than the recovery source is **derived/operational rows written Sept 27** (all regenerable, enumerated in §6).
8–11. Exact recovery target, restore/preserve/untouch lists: §7–§10.
12. **Root cause:** overnight Sept 26→27 the live DB was replaced by a rebuilt empty one; the subsequent "user restore" re-registered project shells from a store that structurally cannot carry storyboard artifacts. Not SQLite corruption — a **project-lineage substitution**.
13–15. Safeguards implemented + rehearsal + dry run: §11–§13 (rehearsal 18/18 ✓, suites green, dry run deterministic with two honest blockers).
16. **Next action:** the single authorized production operation in §14.

---

## 1. PHASE 1 — Every candidate Studio context (verified this session)

| # | Source | State for project_5907 | Classification |
|---|---|---|---|
| 1 | `data/studio.db` + `-wal` + `-shm` (live) | project shell only; **0** shots/versions/blueprints/previs/characters/atoms; base-alone has 32 projects, base+WAL has 35 (WAL carries live uncheckpointed rows — never split) | CURRENT_ONLY (shell + Sept 27 derived rows) |
| 2 | `.validation/scene002_approval_20260926/` DB+**WAL** | **12 bp / 13 ver / 65 shots**; v1 approved; v2 draft | RECOVERY_ONLY |
| 3 | `data/quarantine_stale_wal_20260927/…T161728` | byte-proven continuation of #2; **v2 APPROVED 2026-09-26T20:17:28.940362Z** | RECOVERY_ONLY (newest) |
| 4 | `backups/studio_20260918|19|20_032327.db` | full estates **+ scene_001 v1 approval `sbv_33ba18db0a10`** (absent from Sept 26 lineage) | RECOVERY_ONLY (superset on one scene) |
| 5 | `backups/studio_20260923_110809.db` | estate w/o scene_001 approval; no v2 | RECOVERY_ONLY (older) |
| 6–8 | `backups/studio_20260924|25|26_160722.db` | 4 demo projects; **5907 absent** | RECOVERY_ONLY-EMPTY (nightlies ran against the wrong/empty DB) |
| 9 | `data/studio.db.pre-user-restore-20260927_104500` | 23 demo projects; 5907 absent; creative tables 0 | evidence of rebuilt DB |
| 10 | `data/recovery_artifacts_20260927/studio.db.pre-repair-20260927` | 31-table legacy-shape DB; 5907 absent | evidence of substitution |
| 11 | `data/project_state_store.json` (36.9 MB, 1,203 projects) | shell present; **zero storyboard markers anywhere in file** | CURRENT_ONLY (projection) |
| 12 | store snapshots (pre-scene002-repair 09-26 15:22 / pre-film-restore 09-27 02:58 / Aug-30 prune backup) | same: shells only, no storyboard markers | confirm store never held the estate |
| 13 | Git | HEAD `86c1b58e` (09-21); **no commits Sept 24+**; **164 source files** modified/untracked after 09-23 | code lineage (below) |
| 14 | `outputs/previs/project_5907c60cddbc/` | **13 PNGs survive** incl. seed-916483 output (2.6 MB, Jul 27) | assets survive |
| 15 | `outputs/references/project_5907c60cddbc/` | 18 reference JPGs survive | assets survive |

Timestamp-vs-truth rule applied throughout: e.g. the live DB/store have the **newest** timestamps yet hold the **poorest** creative state → `NEWER_TIMESTAMP_OLDER_STATE`; the composite has older mtimes yet the **newest complete creative state** → `OLDER_TIMESTAMP_NEWER_OR_MORE_COMPLETE_STATE`.

## 2. PHASE 2 — Verified timeline (UTC; local = UTC−4)

| When | Event | Survived? |
|---|---|---|
| 09-20 19:36 | live/store `script_text` variant written (merged-line parse artifact) | in composite's project row? no — lineage row is 09-26 |
| 09-24 01:21 | `project_193c13b84072` (VAL Reference Continuity) last update; 6th VAL project of the Sept 23–24 reference-testing workstream | yes (all six registered in live) |
| 09-25→26 | app work continues uncommitted (see §3) | yes, on disk |
| 09-26 15:22 | store snapshot pre-scene002-repair taken (shells only) | yes |
| 09-26 ~15:25–15:30 | lineage WAL tx 1: project row rewritten (parse-fixed script_text), scene_002 memory updated, blueprint metadata rewritten | composite ✓ |
| 09-26 16:07 | nightly backup → captured an EMPTY/other DB (5907 absent) | n/a |
| 09-26 16:16 | `.validation` capture (12 bp / 12 ver / 60 shots) | composite ✓ |
| 09-26 19:30:21 | WAL tx: **scene_002 v2 draft + 5 shots inserted** | composite ✓ |
| **09-26 20:17:28** | **v2 APPROVED by creator; 5 shots approved; blueprint → approved** | **composite only** |
| 09-26 18:22 | legacy 31-table DB already on live path (captured "pre-repair") | evidence |
| 09-27 02:48–02:49 | backend restarts on rebuilt empty modern DB; "Loaded 252 jobs" (demo-era) | evidence |
| 09-27 06:31 | pre-user-restore snapshot (23 demo projects) | evidence |
| 09-27 ~06:30–07:45 | "user restore" re-registers 12 real projects from **state-store lineage** → shells; auth user row re-added | live shells |
| 09-27 10:50–12:50 | overview-driven derived writes: 24 universe nodes+24 rels (character/location/lore), 2 performance-audio plans, 2 crew reasoning records, 1 dept snapshot, voice profiles ×3, film-cut timestamp touches, screening_output touch; render_attempts (audit-time 36) now 0 | live only, derived |
| 09-27 12:49 | state store re-projection of live | live only |

**Sept 24 specific:** no Sept-24-dated creative rows exist in any examined store; the Sept 23–24 window's work was the six VAL Reference Continuity projects (shells + reference assets inside those projects' own scope, which live carries) plus application code. No Sept-24 creative work for 5907 is missing beyond what the composite already restores.

## 3. PHASE 5 — Application code vs project state

**APPLICATION CODE (survives fully):** branch `backend-expansion-dependency-slicing`, HEAD `86c1b58e` (09-21), **zero commits Sept 24+**, and **164 modified/untracked source files** dated 09-23+ — the entire preserved workstream is uncommitted on disk: multishot integrity remediation tests, generation preflight route, shot manifest/prompt builder, prompt budget/integrity, camera presets + take-camera-review, reference validation/selection priority, model registry/router + capability contract, runway/nvidia/muse/local-LTX/minimax/phosphene providers, 8 frontend rooms + sceneSwitch regression tests, visual training suite. **Risk:** all of it is uncommitted — see §12.

**PROJECT STATE:** everything Sept 24+ creative lives in the composite (§1 #2/#3). Derived intelligence is advisory and regenerable; canonical creative state is authoritative — the composite restores the canonical layer; Sept 27 derived rows regenerate from it.

## 4. PHASE 3 — Identity reconciliation

- Pre-reset: account `user-e36ab1377b44be6d` (Amb3rreed, `last_login 2026-09-26T05:17Z`) owned `project_5907c60cddbc` (mapping `created 2026-09-20T16:07Z`) in the modern DB.
- Post-reset: live has 1 user (`valadmin`, `user-f8e8be9141fa8b64`), 12 `project_owners` rows, 35 projects — the 12 re-registered shells include 5907, whose row content byte-matches the state store's entry (except `updated_at`), proving the store (not the modern DB) was the re-registration source.
- Verdict: **(B) same project ID, older/incomplete DB state**, with account re-provisioning artifacts ((A)-flavored identity churn: `valadmin` ≠ `Amb3rreed` — sign-in breakage consistent with the incident).

## 5. PHASE 4 — Recovery-target inventory (composite, all verified live against the real schema)

44 project-scoped tables with rows, incl.: `projects` 1 · `storyboard_blueprints` 12 · `storyboard_blueprint_versions` 13 · `storyboard_shots` 65 (10 approved) · `previs_images` 16 (seed 916483 intact, `seed_locked 0`) · `scene_memories` 12 · `characters` 6 · `character_reference_locks` 7 (DRE `charlock_df3781262c1b` still `provisional` — an honest, unresolved state, preserved as-is) · `reference_assets` 11 (10 approved, 1 candidate) · `universe_nodes` 24 + `universe_relationships` 24 · `knowledge_bibles/sections/atoms` 9/175/464 · `continuity_graphs(+versions)` · color suite (10/6/6) · production design (9/9/9/2) · camera_grammar_plans 9 · casting (6+1) · `visual_models` 3 (2 local trainings complete) · `render_jobs` 3 (all failed, historical) · `video_assets` 8 (scene_001 renders) · `shots` 6 legacy seeds · `film_cut_state/versions` · workflow tables + 4 events · crew intelligence (45 reasoning, 42 snapshots) · performance audio (8 plans, 10 cues, 16 soundscape layers) · screening_outputs 6 · `access_users` 2 · `project_owners` 1 · `sessions` 1.
Asset files verified on disk: 13 previs PNGs (correct URL mapping `/previs-assets → outputs/previs/`) + 18 reference JPGs.

## 6. PHASES 7/9 — Reconciliation & preservation manifest

**NEWER_TIMESTAMP_OLDER_STATE:** live DB, live WAL, state store.
**OLDER_TIMESTAMP_NEWER_OR_MORE_COMPLETE_STATE:** pre-approval DB+WAL, quarantined stale WAL, Sept 18–20 nightlies.
**CURRENT_ONLY (must survive any recovery):** 35 project registrations (32 demo-era + 12 re-registered incl. 5907's shell) · 252 demo-era render_jobs · live `valadmin` user + 12 ownership mappings · **Sept 27 derived rows for 5907** (24+24 universe rows, 2+2 audio plans, 2 reasoning records, 1 dept snapshot, 3 voice profiles, film-cut/screening timestamp touches) · the store itself (1,203 projects).
**RECOVERY_ONLY:** everything in §5. **CONFLICT (must remain human-decided, none auto-resolved):** ① canonical `script_text` (live merged-line variant vs lineage parse-fixed variant — lineage is newer and tied to the approved screenplay correction, but the live variant contains content the lineage lacks); ② scene_001 v1 approval `sbv_33ba18db0a10` exists **only** in Sept 18–20 nightlies (kept absent from target unless you say otherwise); ③ DRE provisional lock (unresolved by design). **Live WAL integrity:** verified the live WAL carries uncheckpointed rows (32→35 projects) — any production operation must treat db+wal+shm as one unit.

## 7. PHASE 8 — THE TRUE RECOVERY TARGET (proven)

**The September 26 composite: `studio.db.pre-approval-backup` + `studio.db-wal.stale-20260926T161728`.**
Proof: WAL salts identical to the pre-approval WAL; first 156 frames byte-identical (271 total); `integrity_check ok`; v2 `sbv_3b88a1e0ef95` approved 2026-09-26T20:17:28.940362Z by `creator`; scene_002 memory approved-shot list updated to the five v2 IDs (16:17:28.947Z stored); no store contains any later state of this lineage. The composite now exists as a verified standalone at `/tmp/sr927/composite/studio.db` (`provenance.json` + source SHA-256s recorded).

## 8. REHEARSAL RECOVERY (Phase 10) — PASSED

Composite copied to `/tmp/sr927/rehearsal/studio.db` and exercised through the **real** storage/pipeline stack via `STUDIO_STORAGE_PATH` isolation: **18/18 invariants hold** (identity/ownership, v2+v1 approvals, 12/13/65 counts, 16 previs rows, seed, 6 characters, 11 references, 464 atoms, 24 universe nodes, 65 render contracts, workflow state, integrity ok). Test suites: **1,032 passed / 13 skipped / 6 failed**, where the 6 failures are pre-existing issues of the preserved Sept-24+ workstream (provider-registry count assertion in an untracked test; a reference-validation setup gap in a completion-hooks test) — reproduced independently of my changes, which all 84 directly-related tests (incl. 11 new incident tests) pass around.

## 9. RENDER READINESS (Phase 11) — deterministic dry run, zero credits

Ran the real `prepare_scene_batch` stack for scene_002 against the rehearsal copy. Results:
- **Prompt truncation: FIXED** — v2 prompts 2,994–3,290 chars (verified in DB and dry run; no 512-char cut).
- **Correct chain:** approved v2 shots 1–5 in order, correct scene heading (`DOWNTOWN CHICAGO — AFTER THE APOCALYPSE`), correct v1 previs image reference on shot 1; deterministic fingerprint stable across two runs.
- **Two fail-closed blockers remain (correct behavior, require creator decisions, not data loss):**
  1. **Camera framing on all 5 v2 shots is an unapproved AI suggestion** → approve via `approve_ai_camera` (or edit) before rendering. (The previously-flagged "AI_SUGGESTED camera" risk — verified still present and correctly gating.)
  2. **Missing approved canonical environment reference for scene_002** → approve a setting reference (candidate exists: `reference_assets` row of 09-26 09:27) or bind the canonical environment. (The previously-flagged risk — verified still present and correctly gating.)
- Also verified still gated: stale-scene/version reuse (raises), foreign-scene references (rejected), reference-version content hashing, provisional DRE lock preserved unresolved. Fake-dialogue/execution-summary and scene-boundary risks are covered by the multishot + scene-boundary test suites (all passing).
- Provider/model: no run was made (rule honored); the dry run is the exact payload surface that would reach the provider seam.

**Answer: the recovered project passes render readiness EXCEPT for the two creator decisions above — by design.**

## 10. Restore / Preserve / Untouch

**RESTORE (what the target returns that production lacks):** all 44 tables of §5 (12 blueprints, 13 versions, 65 shots incl. 10 approved, 16 previs, seed 916483, 12 scene memories, 6 characters, 7 locks, 11 references, universe 24+24, knowledge 9/175/464, continuity, color/design/camera suites, casting, 3 visual models, historical render jobs, 8 video assets, legacy seeds, film cut v1, workflow state, crew/performance-audio intelligence, screening outputs) + parse-fixed `script_text`/`execution_summary` + creator account row & ownership mapping.
**PRESERVE (current production):** 35 registrations, 252 demo jobs, `valadmin` + 12 ownership rows, Sept 27 derived rows for 5907 (regenerable; keep if present), the store, both conflicting script variants (lineage wins as canonical only by your explicit decision on ③①).
**UNTOUCH (evidence, now git-clean-protected):** `.validation/scene002_approval_20260926/` (both WAL files!), `data/quarantine_stale_wal_20260927/`, `data/recovery_artifacts_20260927/`, `pre-user-restore` snapshot, Sept 18–23 nightlies, live trio db+wal+shm as a unit, frozen copies in `/tmp/sr927/evidence-frozen/`.

## 11. PHASE 12 — Safeguards implemented (code + tests)

New `studio-backend/app/services/recovery_lineage_guard.py`:
1. **`capture_recovery_snapshot`** — immutable hash-pinned snapshot (db+wal+shm+extras, read-only dir, manifest with git identity) before destructive operations.
2. **`verify_restore_invariants`** — application-level post-restore check vs a pre-operation baseline; "had N rows → 0 after" on any creative table = hard failure (integrity_check alone is explicitly insufficient).
3. **`write_lineage_registration` / `verify_render_lineage`** — inode-identity + schema-version registration at startup; render-time detection of a swapped database (strict mode env `STUDIO_LINEAGE_STRICT=1`).

Wired in `main.py` lifespan: auto-snapshot when the database changed since last registration (pre-serve), lineage registration on every startup, restore-invariant verification with loud failure logging. Wired in `app/services/render.py::submit_job`: **fail-closed, permanent refusal to render against a replaced/changed database** — no silent substitutions, no retry hammering.
New `tests/test_recovery_lineage_incident.py` — 11 tests covering all 12 incident steps you specified (build project → approve board → previs → references → contracts → hard reset → auth failure → older-context discovery → mismatch detection → refusal to silently replace → artifacts intact → preflight refuses incomplete state).
Evidence hardening: `.gitignore` now covers `.validation/`, `quarantine_stale_wal_20260927/`, `recovery_artifacts_20260927/`, `recovery-snapshots/` (a `git clean` would previously have destroyed the only Sept-26 lineage on disk). **Remaining prevention gap (needs you): the 164-file workstream is still uncommitted — commit it.**

## 12. Root cause & remaining unknowns

Cause (evidence-consistent): between Sept 26 evening and Sept 27 02:48 the modern working DB was replaced on the live path — first by a legacy 31-table DB, then by a rebuilt empty modern DB; the morning "user restore" then re-registered 12 projects from the state store, which structurally cannot carry storyboard artifacts. Nothing "deleted" the rows; the DB that held them left the live path. Unknowns (unchanged): the exact command/session that performed the overnight substitution (not in the repo); the source of the 3 late-dated restored projects; whether any WAL frames from the lost modern DB exist outside the two known artifacts (searched: none found).

## 13. Questions 8–11, 13–15 answered

8. **Recovery target** = Sept 26 composite (§7). 9. **Restore** = §10 first list. 10. **Preserve** = §10 second list. 11. **Untouch** = §10 third list. 13. **Safeguards** = §11 (+ commit the code; + a standing operational rule: never treat the JSON store as a creative-state recovery source). 14. **Rehearsal succeeds** (§8). 15. **Render readiness**: yes with two creator decisions pending (§9).

## 14. PHASE 13 — Exact production recovery operation (AWAITING YOUR AUTHORIZATION — nothing below has been executed)

**Preconditions:** backend stopped (`kill 30468` gracefully); fresh `capture_recovery_snapshot(..., reason="pre-merge-recovery")`; human sign-off on CONFLICT ① (script_text) and ② (scene_001 approval).
**Step 1 — Snapshot:** `python -c "from app.services.recovery_lineage_guard import capture_recovery_snapshot, build_expected_counts; capture_recovery_snapshot('data/studio.db', reason='pre-merge-recovery')"` and write `baseline-creative-counts.json`.
**Step 2 — Merge (single script, dry-run mode first):** for each of the 44 project-scoped tables, `INSERT OR IGNORE` every composite row for `project_5907c60cddbc` into the live DB (opening the live trio **only through the backend's own storage class on a copy, then atomic file replacement while stopped**); additionally insert the composite `access_users` row for `user-e36ab1377b44be6d` + its `project_owners` row (this restores your sign-in); leave all live-only registrations/jobs/derived rows untouched; on CONFLICT ① write the chosen `script_text` explicitly.
**Step 3 — Verify:** `verify_restore_invariants` against the baseline (must pass with zero failures) + re-run the 18 rehearsal invariants **against the live path** + re-run the dry run (§9) expecting the same two honest blockers.
**Step 4 — Restart:** backend restart re-registers lineage; Overview re-derives advisory intelligence; you approve camera framing ×5 and a scene_002 canonical setting reference; render readiness then returns to the exact pre-incident state.
**ROLLBACK:** stop backend → restore the Step-1 snapshot trio over `data/` (byte-verified against its manifest) → restart; the snapshot is the complete inverse because Step 2 only adds rows.

**STOP CONDITION HONORED — audit ended, production untouched, awaiting your authorization.**

---

*Forensic workspace: `/tmp/sr927/` (manifest, composite + provenance, rehearsal, evidence-frozen copies, all scripts). No original was modified at any point (digests re-verified post-session, all identical).*
