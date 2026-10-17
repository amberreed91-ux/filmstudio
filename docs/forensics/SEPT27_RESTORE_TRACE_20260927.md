# SEPT 27 RESTORE TRACE — how `project_5907c60cddbc`'s storyboard tables went empty in live

**Mode:** read-only forensic trace. No production file modified. All inspection on SHA-verified copies under `/tmp/studio-recovery-20260927/` (see `STUDIO_RECOVERY_CANDIDATES_20260927.md` Appendix A for the manifest).
**Companion to:** `docs/forensics/STUDIO_RECOVERY_CANDIDATES_20260927.md` (three-lineage comparison) and `docs/forensics/STUDIO_PROJECT_STATE_RECONCILIATION_20260927.md`.

**Channel caveat (repeated from `reports/studio-recovery-audit-2026-09-27/REPORT.md`):** the terminal channel again returned fabricated output for several commands during this session (echoing commands that were not sent, inventing paths, scrambling IDs). Every claim below is tagged **VERIFIED** (internally consistent and cross-checked across ≥2 independent commands) or **UNVERIFIED**. Fabricated outputs were discarded in full; nothing below rests on them.

---

## 1. VERIFIED timeline (local times = UTC−4)

| Local | Artifact | Size | VERIFIED content |
|---|---|---|---|
| Sep 26 15:22 | `data/project_state_store.json.pre-scene002-repair-20260926_152247` | 9,001,826 B | 11 projects; contains **9 of the 12 later-restored projects with byte-identical `updated_at`**, incl. `project_5907c60cddbc` (live script variant, sha1 `3a3902a85ad9…`) |
| Sep 26 16:16–16:17 | `.validation/scene002_approval_20260926/` db+wal; `quarantine_stale_wal_20260927/…T161728` | 12.75 MB + 642 KB / 1.12 MB | last verified sighting of the full estate in a live-path DB; stale WAL ends at the v2 approval (2026-09-26T20:17:28Z) |
| Sep 26 18:22 | `data/recovery_artifacts_20260927/studio.db.pre-repair-20260927` | 831,488 B | **31 tables, 11 schema migrations**, 23 demo-era projects, no 5907 — a legacy-shape DB was on the live path by this time |
| Sep 26 20:07 | `backups/studio_20260926_160722.db` | 3,559,424 B | 146 tables, **4 projects, no 5907, 0 storyboard rows globally**, 25 sessions |
| Sep 27 02:49 | `data/backend-restart-20260927.log` | — | restart attempt **failed, port 8010 busy**; "Loaded 252 jobs"; last nightly = 20260926 |
| Sep 27 02:58 | `data/project_state_store.json.pre-film-restore-20260927_105000` | 28,071,118 B | **1,191 projects; no 5907; zero storyboard markers** |
| Sep 27 06:31 | `data/studio.db.pre-user-restore-20260927_104500` | 3,403,776 B | 146 tables, 65 migrations; **23 projects (identical set to pre-repair), no 5907; every creative/global table 0 rows; `access_users` 0** |
| Sep 27 07:45 | `data/studio.db` (live, current) | 9,072,640 B | **35 projects incl. 5907; storyboard/previs/scene_memories/atoms = 0 rows for every project; `access_users` 1** |
| Sep 27 12:49 | `data/project_state_store.json` (live) | 36,930,905 B | **1,203 projects; 5907 present (live script variant); zero storyboard markers** |

## 2. VERIFIED set-kinship: what each restore actually did

- **DB kinship:** `pre-repair` (Sep 26 18:22) project set == `pre-user-restore` (Sep 27 06:31) project set — the same **23 demo-era projects** (252 render_jobs, May timestamps). The **user-restore added exactly 12 projects** to the live DB (35 = 23 + 12), **dropped none**, and re-added 1 `access_users` row.
- **The 12 restored projects** (live-only, with live `projects.data.updated_at`): `project_0d4d5287a448` (09-23), `project_193c13b84072` (09-24), `project_4cfd9b8714ed` (09-23), **`project_5907c60cddbc` (2026-09-20T19:36:10.670388+00:00)**, `project_5b1119ed5c91` (09-23), `project_6826f98cf54c` (09-23), `project_752ca3944869` (09-16), `project_97c57fa832cb` (09-23), `project_9dea2c3f51c0` (09-23), `project_c6ac027bdd6b` (09-23), `project_ca31687b1ca7` (08-30), `project_e0f23024b3e4` (09-23).
- **Store kinship:** the film-restore added **the identical 12 projects** to the JSON store (1,191 → 1,203), dropped none. The store entry for 5907 carries the live script variant (16,285 chars) and zero storyboard fields.
- **Restore source (best-evidence):** the `pre-scene002-repair` store snapshot (Sep 26 15:22) contains **9 of the 12** restored projects with **byte-identical `updated_at`** to the live DB rows — including 5907. The other 3 (`193c13b84072`, `5b1119ed5c91`, `6826f98cf54c`, all updated 09-23/09-24) are present in the pre-film-restore-era store state only. **UNVERIFIED:** the exact file the remaining 3 were read from.

## 3. Mechanism (inference — labeled as such; each step rests on the verified rows above)

1. The **modern working DB** (146 tables, full creative estates for 4+ projects incl. all of 5907's storyboard rows) was last verifiably on the live path at the **Sep 26 16:16** `.validation` capture; its WAL continued to the **16:17 v2 approval** (quarantined). It does not exist under `data/` in any later artifact.
2. Between Sep 26 evening and **Sep 27 ~02:48**, the live path came to hold something else — first a legacy-shape 31-table DB (captured at 18:22 as "pre-repair"), then a rebuilt **empty** modern DB (captured at 06:31 as "pre-user-restore": right schema, zero rows, 23 demo-era projects). The 02:49 restart log ("Loaded 252 jobs", demo-era render_jobs) shows the backend was already on that rebuilt DB.
3. The **Sep 27 morning restores** (documented in `reports/studio-recovery-audit-2026-09-27/REPORT.md` as a prior session's "user restore" of account + 12 projects, and "film restore" on the store) re-registered the 12 real-film projects **from the state-store lineage** (best evidence: the pre-scene002-repair snapshot) into both the rebuilt DB and the store.
4. **The state store never carried storyboard artifacts** — zero occurrences of `sbv_dbafa23cf4a1` / `sbv_3b88a1e0ef95` / `916483` in **every** store snapshot examined (pre-film-restore 28 MB, live 36.9 MB, plus the Aug 30 600-project backup). So the restore could only bring back **project shells**: the 34-key `projects.data` blob with `approved_scenes/storyboard_wall/shot_approval_gates/render_queue` all empty.
5. Therefore: **project_5907c60cddbc's storyboard tables are empty in live because the estate never passed through the state store, and the DB that held it was replaced on the live path overnight Sep 26→27.** Nothing deleted the rows from the modern DB — the modern DB itself is what went missing; what lives at `data/studio.db` today is a different, rebuilt lineage that re-registered projects from the store.

## 4. Where the estate actually survives (unchanged, verified)

- `.validation/scene002_approval_20260926/` — pre-approval DB + WAL (13 versions / 65 shots / v1 approved)
- `data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` — WAL continuation carrying the **v2 approval** (newest known state)
- `backups/studio_20260918|19|20_032327.db` — full estates **plus** `sbv_33ba18db0a10` (scene_001 v1 approved, absent from the Sept 26 lineage); `studio_20260923_110809.db` — estate without scene_001's approval
- Forensic workspace `/tmp/studio-recovery-20260927/` (manifest + inspection copies)

## 5. Open items

- The exact command(s)/session that replaced the live-path DB overnight Sep 26→27 are **not in the repo** (grep found only the read-only audit script); the prior session's report confirms restores happened but flags its own channel as unreliable at the time.
- Source of the 3 late-updated restored projects (`193c13b84072`, `5b1119ed5c91`, `6826f98cf54c`): present in pre-film-restore-era store state, absent from the Sep 26 15:22 snapshot — **UNVERIFIED** which artifact supplied them.
- Whether any WAL frames from the lost modern DB exist outside the two quarantined/backup artifacts: no evidence found; treated as **UNVERIFIED-negative**.

## 6. Implications for recovery

Any recovery of the storyboard estate must come from the **DB artifacts** (Sept 26 lineage + stale WAL, or Sept 18–23 nightlies) — the state store is structurally incapable of providing it. Conversely, the 35 live project shells and 252 demo-era jobs exist only in the live/restored lineage; a wholesale DB replacement would destroy them. This matches §12 of `STUDIO_RECOVERY_CANDIDATES_20260927.md` (options A–F, none selected, none executed).

---

```
RESTORE TRACE COMPLETE
NO PRODUCTION DATA MODIFIED
NO WAL MODIFIED
NO DATABASE MODIFIED
NO STATE STORE MODIFIED
```
