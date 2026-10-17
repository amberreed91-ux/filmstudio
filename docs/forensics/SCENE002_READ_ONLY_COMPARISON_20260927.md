# SCENE_002 READ-ONLY FORENSIC COMPARISON — 2026-09-27

**Scope:** scene_002 of `project_5907c60cddbc` only. Mode: read-only, isolated copies in `/tmp/scene002_audit_20260927/`.
**A (Recovery source):** verified September 26 composite = `.validation/scene002_approval_20260926/studio.db.pre-approval-backup` + its byte-proven WAL continuation `data/quarantine_stale_wal_20260927/studio.db-wal.stale-20260926T161728` (standalone verified copy: `/tmp/sr927/composite/studio.db`, SHA-256 `55895a00…` — byte-identical to a fresh rebuild from the originals performed this session).
**B (Current live):** `studio-backend/data/studio.db` + `-wal` + `-shm` (opened only as SHA-verified byte copies).
**C (Code/artifacts):** current on-disk application code (`backend-expansion-dependency-slicing`, 164 uncommitted files) and surviving asset files.

---

## SCENE_002 RECOVERY STATUS

| | Value |
|---|---|
| Recovery source verified | ✅ Fresh rebuild from originals == prior verified composite, byte-identical |
| WAL provenance re-proven | ✅ Same salt `8618c288/5836be1b`; all 156 frames of pre-approval WAL are a byte-identical prefix of the 271-frame continuation; 13 commit frames |
| Scene_002 identity | blueprint `sbp_project_5907c60cddbc_scene_002_3400a20b`; v1 `sbv_dbafa23cf4a1` (approved 2026-09-06T07:44:28Z); **v2 `sbv_3b88a1e0ef95` (created 2026-09-26T19:30:21Z, approved 2026-09-26T20:17:28.940362Z by creator)** |
| Live creative state | **Zero rows** in every storyboard/creative table (146-table schema present, all counts 0). Scene_002 exists live only as a project shell + advisory derived rows |
| Rehearsal claims re-verified | v2 approval ✓ · 5/5 v2 shots approved ✓ · correct v2 chain ✓ · full-length prompts (2,994–3,200 chars, no 512-cut) ✓ · seed 916483 in previs row ✓ · scene_002 recovery data in composite ✓ |
| Correction to prior report | The forensic report's "13 previs PNGs … under outputs/previs" covers the whole project: **only ONE scene_002 PNG survives on disk** (`scene_002_shot_001_storyboard_qwen.png`, 2,644,340 B, Jul 27, = the seed-916483 output). The other 12 are scenes 003–014. The one scene_002 previs row's URL resolves correctly. |

---

## RECOVERED V2 STATE (composite, exact)

**Blueprint** `sbp_…_scene_002_3400a20b`: status `approved`, current_version_id = approved_version_id = `sbv_3b88a1e0ef95`, locked=0, updated_at 2026-09-26T20:17:28.940362+00:00. Metadata carries the completed continuity review `scr_c642613b209a` (5 medium "missing emotional goal" advisories, readiness `ready_for_creator_approval`).

**Version v2** `sbv_3b88a1e0ef95`: version_number=2, status `approved`, change_reason "scene_002 regeneration after creator-approved screenplay correction (2026-09-26)", source_version_id=v1, approved_by `creator`. Full provenance/inspection JSON intact (inspection says render_readiness "ready").

**v2 shots — approved chain, in shot order (this is the exact restoration payload):**

| # | storyboard_shot_id | created_at | prompt len | prompt sha16 | framing (visual_plan) | purpose | camera fields | seed |
|---|---|---|---|---|---|---|---|---|
| 1 | `sbs_a7648698ad00` | 19:30:21.671648 | 3,200 | `329b84e2f698f4ec` | "Wide establishing shot. Camera far back. Full environment visible." | establishing_shot | camera_angle="" camera_movement="" | null |
| 2 | `sbs_a8481a439ea5` | 19:30:21.672168 | 3,012 | `7118ac1afd66b685` | "Medium shot. Characters from waist up…" | medium_shot | "" / "" | null |
| 3 | `sbs_be2cce8fab93` | 19:30:21.672649 | 2,994 | `5b98c2831a9da5d8` | "Medium close-up. Character faces and upper body. Emotional beats." | close_up | "" / "" | null |
| 4 | `sbs_51d1500d227c` | 19:30:21.673119 | 3,003 | `0e80c32afd7a576c` | "Dynamic medium shot showing the story transition in motion." | transition_shot | "" / "" | null |
| 5 | `sbs_0046fb5192f0` | 19:30:21.673626 | 3,074 | `9bc47ad3336ac737` | "Close-up detail shot. Eyes, hands, specific objects. Intimate…" | emotional_detail_shot | "" / "" | null |

All 5: status `approved` (updated_at 20:17:28.940362), locked=0, `camera_plan` **absent** from render_contract.structured_parameters and from metadata, `reference_assets` empty, environment "DOWNTOWN CHICAGO — AFTER THE APOCALYPSE", intent character_focus [DRE, MAYA], emotional_target "". Full render contracts intact (prompt_components, structured_parameters duration=5 ratio 1280:720, AR 16:9). Shot 1 carries `previs_image_id=previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1` and `storyboard_image_url=/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png`.

**v1 shots** (`sbv_dbafa23cf4a1`, `sbs_77d3ae4fe1e9`/`8b1c822fc206`/`1d23d6055c17`/`4d91b1c6bd3c`/`ee2d6576f016`): approved 2026-09-06, prompts all **exactly 512 chars** (the historical truncation — evidence, not target).

**Previs rows (scene_002):** 2 — (a) `…_shot_001_b1d573f1`: complete, seed **916483**, seed_locked=0, 512-char prompt, URL resolves on disk; (b) `job-20260906034509-132bb802…`: failed, empty path (historical failure).

**Scene memory:** `approved_shots` = the five v2 entries in order (sbs IDs + v2 version_id), updated_at 2026-09-26T16:17:28.947565 (stored; report §7 records the same write), camera_choices [].

**References:** 6 characters (MAYA, DRE, MOM, ELENA, JAY, SIMONE). MAYA/MOM/DRE carry **locked appearance approvals** (`continuity_state_json.appearance_approval`, status locked, version 1, approved 2026-09-06) — this is how the character reference gate passes. DRE additionally has provisional charlock `charlock_df3781262c1b` (unresolved by design, preserved as-is). 11 reference_assets rows; **none** is a scene_002 setting row; the only setting-typed row is `ref_upl_a73e6281957642c58940a942` = scene_001, `candidate`, canonical=0, and **its upload file does not exist on disk**.

**Assets on disk:** scene_002 seed PNG ✓ (2,644,340 B). All 8 `character-looks` URLs referenced by the locked approvals exist. 16/21 relevant URLs resolve; 5 missing = 3 `/media/vt_*.png` visual-training fixtures + 2 scene_001-scoped lock images (both out of scene_002 scope).

**Live-only derived rows touching scene_002:** 1 `performance_audio_plans` row (scene-scope, `needs_creator_review`, generated 2026-09-27T12:50:02Z) + 9 `dialogue_performance_cues` (advisory_only=1). Both regenerate from scene text.

---

## CURRENT LIVE STATE (all scene_002-relevant tables)

Zero rows for: `storyboard_blueprints`, `storyboard_blueprint_versions`, `storyboard_shots`, `previs_images`, `scene_memories`, `characters`, `reference_assets`, `character_reference_locks`, `render_jobs`, `video_assets`, `storyboard_render_links`, `storyboard_revision_links`, `canonical_workflow_runs`, `previs_production_packages`, `production_queue_items`, legacy `shots`, `knowledge_*`, casting, color, production-design, camera-grammar, visual_models, workflow tables.

Live-only for 5907 (13 tables, all derived/regenerable): universe_nodes 24 + universe_relationships 24, performance_audio_plans 2, soundscape_layer_plans 4, dialogue_performance_cues 9, character_voice_profiles 3, crew_reasoning_records 2, crew_department_status_snapshots 1, film_cut_state/versions 1+1, screening_outputs 1, project_owners 1, projects 1.

**Projects blob (fallback JSON):** live `script_text` 16,285 chars sha16 `c66c7e8e573b00ec` vs composite 16,265 sha16 `9a9c661823491a6a`; execution_summary differs by the same 2 insertions + 2 deletions. `storyboard_wall` empty in both; `scene_review_status` {} in both. The JSON state store (36.9 MB, 1,203 projects) contains **zero** scene_002/storyboard markers.

---

## EXACT DIFFERENCES (classification A–E)

A = RECOVERABLE SCENE_002 CREATIVE STATE · B = RECOVERABLE SCENE_002 STRUCTURAL STATE · C = DERIVED/REGENERABLE · D = CURRENT CREATOR DECISION REQUIRED · E = UNRELATED TO SCENE_002

| # | Item | Composite (source) | Live | Class |
|---|---|---|---|---|
| 1 | Blueprint row | approved, v2 current+approved | absent | B |
| 2 | Blueprint versions | v1 approved + **v2 approved** | absent | B (chain) + A (approval = creator act) |
| 3 | v2 shots ×5 | approved, full contracts | absent | B (rows) + A (creator approval recorded in status) |
| 4 | v1 shots ×5 | approved, 512-char historical prompts | absent | B |
| 5 | Previs rows ×2 | complete(seed 916483) + failed | absent | B |
| 6 | Scene memory | approved_shots = 5× v2 | absent | B |
| 7 | Characters ×6 + locked appearance approvals | present | absent | A |
| 8 | DRE provisional charlock | provisional | absent | A (preserved unresolved) |
| 9 | reference_assets ×11 | present | absent | B |
| 10 | knowledge 9/175/464, universe 24+24 (lineage versions), color/design/camera suites, casting, visual_models, film cut, workflow state, crew intelligence (45+42) | present | absent | C (derived) |
| 11 | render_jobs ×3 (all failed, incl. 1 scene_002 local_ltx) | present | absent | B (history) |
| 12 | canonical_workflow_runs ×1 (v1 approval) | present | absent | B (history) |
| 13 | legacy `shots` seed row `scene_002_shot_001` seed 1395559473 | present | absent | B (legacy) |
| 14 | **script_text** | parse-fixed 16,265 (newer, tied to approved correction) | merged-line variant 16,285 (+20 chars) | **D — CONFLICT ①** |
| 15 | execution_summary | lineage variant | live variant (+48 chars) | D (follows #14) |
| 16 | Camera approval for 5 v2 framings | **missing in composite too** (camera_plan absent) | — | **D — BLOCKER 1** |
| 17 | Approved canonical scene_002 setting reference | **missing in composite too** | — | **D — BLOCKER 2** |
| 18 | Sept 27 derived rows for 5907 (24+24, 2+2, 2, 1, 3, touches) | absent | live only | C (preserve live) |
| 19 | Live WAL uncheckpointed demo rows | absent | live only | E |
| 20 | scene_001 v1 approval `sbv_33ba18db0a10` (Sept 18–20 nightlies only) | absent from composite | absent | E (scene_001 — out of scope) |
| 21 | vt_*.png media fixtures + scene_001 lock images | referenced, files missing | files missing | E |

Rows that exist **only in the composite**: items 1–13 (every creative row). Rows that exist **only in live**: items 18–19 (derived/operational only). Nothing in either store contradicts the v2 approval chain; the only content conflicts are #14–#15 (already flagged CONFLICT ①) and they are creator decisions, not silent-restore material.

---

## REQUIRED RESTORATION SET (exact rows the live DB must contain; NOT executed)

All `INSERT OR IGNORE`-able, project-scoped to `project_5907c60cddbc`, sourced byte-for-byte from the verified composite:

1. `storyboard_blueprints` — 1 row: `sbp_project_5907c60cddbc_scene_002_3400a20b` (approved, current/approved = sbv_3b88a1e0ef95, full metadata JSON incl. continuity review).
2. `storyboard_blueprint_versions` — 2 rows: `sbv_dbafa23cf4a1` (v1 approved), `sbv_3b88a1e0ef95` (v2 approved, change_reason, provenance/inspection JSON).
3. `storyboard_shots` — 10 rows: v1 five (`sbs_77d3ae4fe1e9, 8b1c822fc206, 1d23d6055c17, 4d91b1c6bd3c, ee2d6576f016`) + v2 five (`sbs_a7648698ad00, a8481a439ea5, be2cce8fab93, 51d1500d227c, 0046fb5192f0`), all approved, full intent/visual_plan/continuity_plan/render_contract JSON — **no truncation, no rewriting**.
4. `previs_images` — 2 rows (incl. seed 916483 row bound to shot 1 via `previs_image_id`).
5. `scene_memories` — 1 row: scene_002 approved_shots JSON (5× v2 entries).
6. `characters` — 6 rows incl. `continuity_state_json` appearance approvals (locked) for DRE/MAYA/MOM.
7. `character_reference_locks` — 7 rows incl. DRE provisional `charlock_df3781262c1b` (kept provisional).
8. `reference_assets` — 11 rows (incl. scene_001 candidate — restored as-is, remains candidate; it is not a scene_002 gate asset).
9. `render_jobs` — 3 failed historical rows; `canonical_workflow_runs` — 1 row; legacy `shots` — 1 row.
10. Project-scoped derived estate of the same lineage (for 5907 scene_002 relevance, these are advisory but part of the verified composite): knowledge_bibles/sections/atoms 9/175/464, universe 24+24 (lineage version), color 10/6/6/3/6, production design 9/9/9/2, camera_grammar_plans 9, casting 6+1+1, performance_audio_plans 8, dialogue cues 10, soundscape layers 16, visual_models 3, video_assets 8 + keyframes 24, film_cut 1+1, workflow state 1 + events 4 + collaborator 1, crew 45+42.
11. `projects` row — the composite (parse-fixed) variant **only upon explicit creator sign-off on CONFLICT ①**; otherwise leave live variant and restore items 1–10 (they do not depend on it).
12. NOT restored: live-only derived rows (item 18) and live WAL demo rows (item 19) — preserved untouched.

Nothing in this set pre-decides either blocker; items 16–17 remain missing after restoration by design until the creator decides.

---

## CURRENT RENDER BLOCKERS (re-verified against current code)

**BLOCKER 1 — five v2 cameras remain AI_SUGGESTED.**
- Responsible field: **absence of `render_contract.structured_parameters["camera_plan"]`** (or `metadata["camera_plan"]`) on all five v2 shots. The v2 board generation template wrote `visual_plan_json.framing` (+ empty `camera_angle`/`camera_movement`) but no creator camera plan.
- Responsible table: `storyboard_shots` (columns `visual_plan_json`, `render_contract_json`, `metadata`).
- Responsible pipeline decision chain (current code):
  1. `generation_context_service._camera_plan_provenance()` (app/services/generation_context_service.py:212) returns `creator_defined=False` because no camera_plan dict exists in either candidate location.
  2. `pending_ai_camera_suggestions()` (:185) therefore exposes the non-empty `visual_plan.framing` values as pending AI suggestions.
  3. `derive_camera_instructions()` (:427) attaches only AI_SUGGESTED provenance — per its P0-2 rule "heuristic board content is NOT creator camera approval."
  4. `validate_generation_context()` (:665) appends `Camera 'framing' is an unapproved AI suggestion …` as a **hard blocker**.
  5. Wired identically in `scene_production_pipeline_service.prepare_scene_batch` (:283–332, notes at :292 "it blocks this shot until the user explicitly approves it (approve_ai_camera)") and `render.py::submit_job` (:880).
- The only sanctioned path out: creator action via `approve_ai_camera` (previs_service.py:606) or an explicit camera plan — which (per that method) will create a **new draft version** because approved boards are immutable, recording `creator_shot_planning`/camera_plan provenance and re-stamping instructions to APPROVED. This is a new creator act on top of restored state; the composite does not and must not contain it.

**BLOCKER 2 — no approved canonical setting reference for scene_002.**
- Responsible gate: `reference_validation.resolve_scene_reference_requirements()` (app/services/reference_validation.py:197–255): `_approved_setting_urls()` requires a `reference_assets` row with `target_type='setting'`, `target_id=<setting_id>`, `canonical=1`, `approval_state='approved'`, `kind='environment'`; otherwise raises `canonical_setting_reference_missing` with recovery action "Open Scene scene_002 setting references and approve a canonical environment reference."
- Exact missing record: **no `reference_assets` row with `target_type='setting'`/`target_id='scene_002'` exists anywhere in the composite** (11 rows total; the only setting row is `ref_upl_a73e6281957642c58940a942` = scene_001, candidate, canonical=0, upload file also absent on disk). `setting_id` resolves from the scene record (`_setting_id()`), and scene_002's scene row (in execution_summary) carries no explicit setting/location id, so the missing row is the scene_002-scoped environment reference itself.
- Contributing structural fact (code): there is **no code path that sets `canonical=1`** for a setting reference. `update_reference_asset_state()` (app/data/storage.py:13578) explicitly "changes review state without changing canonical ownership," and the upload route rejects `payload.canonical` with "Canonical references are changed only through the existing lock workflow." Canonical setting binding is a creator act through the reference-library/lock surface.
- Secondary gap for full awareness (not a new blocker): the composite's `ref_env_6b726885ed67ae4d` (kind=environment, approved, source scene_002_shot_001, pointing at the surviving seed PNG) has `target_type=NULL`/`canonical=0` — legacy-shaped, it does not satisfy the gate and is not being "promoted" here. Promotion/dedup/creation is the creator's decision.

---

## CREATOR DECISIONS REQUIRED (fail-closed; nothing auto-approved)

1. **CONFLICT ① — canonical `script_text`** for project_5907: composite parse-fixed variant (16,265 chars; newer, tied to the creator-approved screenplay correction that motivated v2) vs live variant (16,285 chars; contains the `DRE — BEFORE THE FALL` heading fragment the lineage lacks). Decide which is canonical before the projects row is touched. (Both share the unresolved `NIGHTMaya` merged-heading artifact — noted, not fixed here.)
2. **BLOCKER 1** — approve (or edit, or reject and re-plan) the five AI-suggested camera framings after restoration, via the camera approval surface. Expected mechanical effect: new draft version of the approved board (immutability preserved), five shots stamped APPROVED, framing blockers clear.
3. **BLOCKER 2** — approve/bind a canonical scene_002 setting reference (e.g., approve an uploaded environment reference through the Scene 002 reference library, which requires a real file, then bind canonical). No row in the composite can be silently promoted.
4. (Context, scene_001 — explicitly out of scope here): v1 approval `sbv_33ba18db0a10` exists only in Sept 18–20 nightlies; kept out of this target.

---

## SAFETY VERIFICATION

- **Production DB modified: NO** — all reads via `file:…?mode=ro` on SHA-verified copies; live `data/studio.db` digest identical before and after (`cb99f8c9bfbe0a52…`).
- **Production WAL modified: NO** — live `-wal` digest identical before and after (`0f5b8c18dea5d1a5…`); never opened, never checkpointed; `-shm` untouched.
- **Recovery composite modified: NO** — source digests identical before/after (DB `0899774f74f595ee…`, WAL `2947761e100a2fa5…`, continuation `4dacc1c15fb5cd0d…`); `/tmp/sr927/composite/studio.db` digest unchanged (`55895a004db965f9…`). (During analysis a *copy* of the pre-approval WAL under `/tmp` was auto-checkpointed by a sqlite CLI read; copies only — the original and its digest are unaffected, and provenance was re-proven from fresh copies.)
- **Validation artifacts modified: NO** — `.validation/scene002_approval_20260926/` contents untouched (digests above; only `mtimes` of the directory listing were observed).
- **Backend restarted: NO** — no processes touched.
- **Provider called: NO** — no Runway/openrouter/local generation endpoints or provider modules executed; only static code reading and local SQL/JSON inspection.
- **Runway credits spent: 0**
- State store read via byte copy only: digest identical (`3c7e716ad239988a…`).
- Isolated working area: `/tmp/scene002_audit_20260927/` (copies, probes, JSON inventories `inventory_composite.json` / `inventory_live.json`).

---

*End of report. Stopped as instructed: no restoration executed, no merge prepared or run, scene_001 not investigated, no creative decisions made.*
