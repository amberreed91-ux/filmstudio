# Scene_001 blockers diagnostic — why edits don't save, why Maya isn't locked/trained, why Dre/Elena/Jay appear

**Date:** 2026-10-17 (evidence read 2026-10-18, read-only)
**Scope:** Project `project_5907c60cddbc`, `scene_001`, blueprint `sbp_project_5907c60cddbc_scene_001_ec41ca26`
**Method:** Read-only. `studio-backend/data/studio.db` opened `mode=ro`. No files edited, nothing restarted, no provider calls, no mutating requests. Zero changes applied.

**Headline state change since the mission was written:** the mission describes draft version `sbv_3cee32c0326a` with no persisting human edits. The database now shows `sbv_3cee32c0326a` as version 3, status **approved** (approved 2026-10-18T03:23:00Z), with **five human-origin, approved image-prompt rows** (approved 03:19–03:20Z). The owner's Maya hand-edits **did eventually land** — on the v3 shot IDs — and the board has since been approved. Everything below explains (a) the mechanisms that made saves *appear* to vanish, (b) why Dre/Elena/Jay are in every canonical prompt and Maya is not, (c) what "trained" actually means and why the panel is empty, and (d) what exactly clears each Generation Readiness blocker.

---

## 1. Why image-prompt saves do not persist

### 1.1 DB ground truth: human rows exist — but only on v3, and only recently

`storyboard_image_prompts` (PK = `storyboard_shot_id`, one row per board-shot, **not** per version):

| storyboard_shot_id | version | shot | status | origin | utf16 | created | updated/approved |
|---|---|---|---|---|---|---|---|
| `sbs_a90197d14135` | `sbv_b92243ea0008` (v2) | shot_001 | proposed | compactor | 969 | 2026-10-17T23:29:55Z | same |
| `sbs_253c0dbbe8f8` | v2 | shot_002 | proposed | compactor | 953 | 23:29:55Z | same |
| *(none)* | v2 | shot_003 | — | — | — | — | **no row at all** |
| *(none)* | v2 | shot_004 | — | — | — | — | **no row at all** |
| `sbs_956c53271150` | v2 | shot_005 | proposed | compactor | 987 | 23:29:55Z | same |
| `sbs_73c78e12319b` | `sbv_3cee32c0326a` (v3) | shot_001 | **approved** | **human** | 575 | 2026-10-18T01:20:33Z | 03:20:02Z |
| `sbs_0770de978d0c` | v3 | shot_002 | **approved** | **human** | 486 | 01:22:10Z | 03:19:50Z |
| `sbs_a9b90e31fc76` | v3 | shot_003 | **approved** | **human** | 552 | 03:17:54Z | 03:19:42Z |
| `sbs_cd2076ba3d14` | v3 | shot_004 | **approved** | **human** | 483 | 03:18:18Z | 03:19:30Z |
| `sbs_0a1a67de8405` | v3 | shot_005 | **approved** | **human** | 368 | 01:22:40Z | 03:19:12Z |

Board versions for the blueprint: v1 `sbv_ea20abec1338` (superseded), v2 `sbv_b92243ea0008` (draft, created 23:29:55Z), v3 `sbv_3cee32c0326a` (**approved**, created 00:49:15Z, approved 03:23:00Z). Blueprint row: `current_version_id = approved_version_id = sbv_3cee32c0326a`. **Nothing has created a board version since `sbv_3cee32c0326a`** (max `version_number` = 3). The mission's "draft version sbv_3cee32c0326a" is stale: v3 is now the current **and** approved version.

Source-hash check: every v3 row's `source_prompt_sha256` matches the live canonical `provider_neutral_prompt` sha256 (e.g. shot 1 `6dbc7841`, shot 2 `6eaf2889`, shot 3 `e3970469`, shot 4 `3fe7c177`, shot 5 `508027c5`). All five are **fresh**, not stale. The saved texts are the owner's Maya descriptions (verified: shot 3 reads "Medium close shot of Maya walking through downtown Chicago… lean Black woman in her late 20s… worn canvas jacket over layered olive, charcoal and rust…"; shot 1 includes "Maya is a small figure in frame, walking the Green Line…").

So: **human-origin rows exist under v3 for all five shot IDs, and the saves the owner reported missing have since persisted and been approved.** The failure modes below explain what the owner experienced at mission time.

### 1.2 The Save path (frontend → backend)

- Panel: `studio-app/src/components/StoryboardImagePromptPanel.tsx`. `run('save')` (line 68) calls `editShotImagePrompt(blueprintId, shot.storyboard_shot_id, draft)` then `onChanged()` (refetch). Errors surface in `role="alert"` (line ~162) — they are **not** swallowed.
- API: `studio-app/src/lib/studioApi.ts:3907` — `PUT /api/f51/studio/storyboard-blueprints/{blueprintId}/shots/{storyboardShotId}/image-prompt`, body `{image_prompt}`. Limit constant `RUNWAY_IMAGE_PROMPT_LIMIT = 1000` (line 2445).
- Backend: `PUT` route `studio-backend/app/routes/storyboard_blueprints.py` (`edit_shot_image_prompt`) → `StoryboardImagePromptService.edit_for_shot` (`studio-backend/app/services/storyboard_image_prompt_service.py`). Rejects empty text and anything over 1000 UTF-16 units with 422 (`ValidationError`, stage `storyboard_image_prompt_edit`). A successful edit writes `origin='human'`, **`status='proposed'`** (back to unapproved), preserving `created_at`.

### 1.3 Every way a click can appear to succeed without persisting

1. **Save ≠ Approve (most likely core confusion).** A successful Save writes a *proposal* (`status='proposed'`, "awaiting approval"). The render path (`approved_prompt_for_shot`, fails closed via `StateError`) and the board-approval gate (`approve_version` → `gate_for_version`, `storyboard_blueprint_service.py:412+`) both require `approved`. Until the separate **Approve prompt** button (`StoryboardImagePromptPanel.tsx:154-159`, `studioApi.ts:3923`) is pressed, the panel keeps showing "awaiting approval" / not render-ready — easily read as "my save didn't take." Timeline evidence fits exactly: human saves 01:20–03:18Z sat as proposals; approvals 03:19–03:20Z; board approval 03:23Z (the D4 image gate blocks board approval while any shot is missing/stale/unapproved/over-limit).
2. **Save applies to a version that is later superseded — with new shot IDs.** Image prompts are keyed by `storyboard_shot_id`, and **every new board version mints brand-new shot IDs** (`_clone_shot_for_version`, `storyboard_blueprint_service.py:1973`: `clone.storyboard_shot_id = f"sbs_{uuid4…}"`). Nothing copies image-prompt rows to the clones. Three creators of new versions exist: explicit regenerate (`create_version`, line 197), **Scene Direction save** (`scene_direction_service.py:394-456` — saving direction in Build blueprint mints `sbv_…`, clones all shots, flips `current_version_id`), and **AI camera approval** (`previs_service.py:664` `approve_ai_camera` — "an approved board is immutable", so approval creates a new draft version). This demonstrably happened: v2's compactor rows (shots 1, 2, 5) were orphaned when v3 was created at 00:49Z; v2 shots 3/4 never had rows at all. Any edit saved against v2 shot IDs after 00:49Z would succeed on rows the UI (showing current v3) never displays.
3. **Refetch snaps the draft back.** The panel holds no optimistic state: `useEffect` resets `draft` to the fetched `current` whenever it changes (`StoryboardImagePromptPanel.tsx:57-61`). If the save went to a *different* shot ID than the one on screen (stale panel after a background regeneration), the refetch returns the old record and the pasted text visibly "vanishes."
4. **Disabled Save button gives zero feedback.** Save is disabled when `!dirty || !draft.trim() || draftOverLimit` (line 144) — a click does literally nothing, no error. The canonical prompts are 2203–2934 UTF-16 units (measured), so if the owner pasted a long prompt (or the full canonical text) exceeding 1000 units, the button was dead. Backend 422s (empty/over-limit) do show an error, but the disabled-button case is silent by construction.
5. **Re-derive destroys hand edits.** `derive_for_shot` unconditionally overwrites the row with the compactor proposal (`origin='compactor'`, `status='proposed'`). Pressing **Re-derive** after hand-editing — or any flow that re-derives — silently discards the human text.
6. **Canonical edits stale the prompt.** `status_for_shot` compares `source_prompt_sha256` to the live canonical hash; any board-text change (shot update, regeneration) flips saved prompts to `stale` ("Re-derive or re-approve"), which also reads as "my save is gone."

### 1.4 "Direct the action" is a different field

Yes. `PrevisRoom.tsx:2766` (`<label …>Direct the action</label>`, textarea `previs-render-prompt`, Step Render) is the **single-take render prompt** sent with a take-generation request — it writes neither the board's canonical text nor `storyboard_image_prompts`. Text pasted there and "saved"/sent never reaches the image-prompt panel. The shot-panel canonical-text editor is `CreatorDecisionWorkspace` → Scene Direction (`saveSceneDirection`, `sceneDirectionApi.ts:13-16`, with `expected_version_id` optimistic-concurrency), which — per §1.3(2) — mints a **new draft version** and orphans existing image-prompt rows. So both adjacent save buttons write somewhere other than where the owner was looking.

**Root cause (Q1):** No single persistence bug. Saves go to a per-shot-ID row as *unapproved proposals*; they become invisible when (a) never separately approved, (b) a new board version mints new shot IDs (v2→v3 did exactly this; Scene Direction saves and camera approvals do it again), or (c) the click hit a silently-disabled Save button (over-1000-unit paste). Current DB proves the mechanism and the recovery: the v3 human rows are present, fresh, and approved.

---

## 2. Why DRE/ELENA/JAY are in every shot and Maya is not

### 2.1 Where the block is built

`build_locked_appearance_block(all_characters, scene_data, max_characters=3)` (`studio-backend/app/services/shot_prompt_builder.py:237-270`):

1. `locked_appearance_characters` (line 223) keeps **every project character whose `appearance_approval.status == 'locked'`** — `appearance_approval` reads `continuity_state_json.appearance_approval` (`studio-backend/app/utils/character_appearance.py`). This is a **project-wide** list, not per-shot and not per-scene-cast.
2. Scene-scoping applies **only if the scene declares a cast** (`_scene_character_names` reads `scene.characters` / `scene.character_appearances`). **scene_001 declares `characters = []`** (verified in `studio-backend/data/project_state_store.json`: `characters = []`, text names Maya only in prose). Empty cast → **no scoping; falls back to all locked**.
3. The survivors are truncated to the **first `max_characters` (default 3)**. Callers (`ensure_locked_appearance_in_prompt`, `_locked_block_for_scene`, `_build_provider_neutral_prompt` path) all use the default 3.
4. Character order comes from `storage.get_characters` — **`ORDER BY name ASC`** (`studio-backend/app/data/storage.py:13691+`). All six characters are locked (DRE, ELENA, JAY, MAYA, MOM, SIMONE), so alphabetical order + cap 3 = **DRE, ELENA, JAY**. Maya is 4th alphabetically and is cut.

The block is appended identically to **every** shot (`ensure_locked_appearance_in_prompt`, line 292; invoked from `build_shot_aware_prompt` and re-ensured after plan-head assembly in `storyboard_blueprint_service.py:1308-1314`). There is no per-shot cast filtering — hence shots 3 and 4 carry DRE/ELENA/JAY despite reading "Only MAYA visible." (The per-shot `Characters: MAYA (Late 20s): …` line *is* shot-aware — `_extract_characters_from_segment` word-boundary-matches "Maya"/"MAYA" in the segment — but the Locked tail is scene/project-level.)

### 2.2 The long scene sentences

Yes: each block entry is `appearance_description(char)` = the locked approval's `description` field verbatim (`character_appearance.py: `approval["description"]` when locked), which is stored as **`age; look; visual_prompt_summary`** — i.e. the physical description **plus the full reference-image prompt** (Elena's Pilsen garden kneeling sentence, Jay's auto-shop sentence, Dre's post-collapse street sentence, Maya's rooftop sentence). Appending the whole `visual_prompt_summary` is **intended** (docstring at `shot_prompt_builder.py:243-252`: race/skin-tone/age/gender tokens must survive even when scene text is long; never truncated). The unintended parts are *which* characters are selected (alphabetical-first-3 of six) and that the block ignores the shot's visible cast.

### 2.3 Lock states (DB)

| Character | `appearance_approval.status` (continuity_state_json) | `character_reference_locks` | Scenes assigned |
|---|---|---|---|
| MAYA (`chr_3c9e91741ef3`) | **locked**, v2, approved 2026-10-09T03:10:48Z | locked+approved (general, alternate_angle, 2026-09-05); one superseded | scene_001 declares **no cast** (`characters=[]`); shots 3–4 name her in prose ("Only MAYA visible") |
| DRE (`chr_f1425498cb68`) | locked, v3, approved 2026-10-09T03:09:30Z | provisional/unreviewed only | same (no scene cast anywhere) |
| ELENA (`chr_d3b00f4d3460`) | locked, v1, approved 2026-09-06 | **no rows** | same |
| JAY (`chr_ce2b04d72a51`) | locked, v1, approved 2026-09-17 | **no rows** | same |
| MOM, SIMONE | locked | (not enumerated; irrelevant — also cut by cap) | same |

Note the two lock systems disagree: the prompt block uses `appearance_approval` (all six locked), while `character_reference_locks` has Maya fully locked/approved and Dre only provisional — yet Dre appears and Maya doesn't. The block never consults `character_reference_locks` or scene assignment.

**Root cause (Q2):** The block lists *all project-locked characters*, scene_001 declares an empty cast so no scoping kicks in, and the hard cap of 3 with alphabetical storage order deterministically selects DRE/ELENA/JAY and amputates MAYA (4th). It is per-scene-identical by design, so "Only MAYA visible" shots still get the wrong three faces. Nothing about Maya's lock is broken — she is locked; she is simply 4th of 6.

---

## 3. Maya's trained identity

### 3.1 Maya's records

- Character `chr_3c9e91741ef3` (MAYA): `appearance_approval` locked v2 (2026-10-09), face + body `face_image_url`/`body_image_url` set; both files **exist on disk** (`studio-backend/outputs/references/character-looks/54f20532b4dd2ea190563995/950cd32fcf2d8247bdc26818/a3967016f7794dabac8ccb433153b1f6.jpg`, `…/c9ca9cbaed944217abad4e8b41a7410a.jpg`).
- `reference_assets` for Maya: 3 casting candidates + approved canonical face `ref_look_e46ec07463f33414` (`canonical=1`, `approved`) + approved full-body `ref_look_cfe64ecb1f1ba2ad`. Reference side is complete.
- `visual_models` for the project: **0 rows**.
- `character_reference_locks` for Maya: locked + approved (general and alternate_angle).

### 3.2 What "train" means here

"Train" is **not** lock + approved reference. It is a **provider-side visual-model training job** (LoRA-style reusable identity): `POST …/visual-training/jobs` with `{project_id, target_type:'character', trigger_word, source_asset_ids, provider, provider_model}` (`studio-backend/app/routes/visual_training.py: create_visual_training_job`), submitted to the provider as a background task, lifecycle pending → complete/failed. The picker reads **only** `GET …/visual-training/models?status=complete`, and the route additionally filters `status == 'complete'` (`visual_training.py:310`). UI: `CharacterLookTraining` → `VisualTrainingPanel` ("Train This Look" → configure provider/model/trigger word + confirmed reference assets → **Begin Training**, `VisualTrainingPanel.tsx:199,414`; API `createVisualTrainingJob`, `visualTrainingApi.ts:141-142`). The picker itself (`TrainedIdentityPicker.tsx`, fed by `useAvailableIdentities`, which queries `listVisualModels({target_type:'character'|'scene', status:'complete'})`) is opt-in per take and never auto-attaches.

### 3.3 Why "No trained identities yet"

`TrainedIdentityPicker.tsx` renders that string when both identity lists are empty. Both are empty because **no visual-training job has ever been created for this project** (`visual_models` = 0 rows) — for Maya or anyone. The exact empty text is at `TrainedIdentityPicker.tsx` ("No trained identities yet. Train a character look or this setting to reuse a consistent visual identity here.").

**Root cause (Q3):** Nothing is broken. Maya has a locked look, approved canonical references, files on disk, and approved reference locks — but "trained identity" names a different object (a completed provider training row in `visual_models`) that nobody has created. What populates the panel: Character Look → Train This Look → Begin Training → job reaches `complete` (then `useAvailableIdentities` picks it up; per-scene setting identities additionally filter by `configuration.canonical_target_id === sceneId`).

---

## 4. Generation Readiness blockers

All per-shot evidence below is from v3's persisted `render_contract_json` (`structured_parameters` + `render_blockers`) and the preflight/freeze code. Note the two readiness layers: **board-level** (`_inspect`: `render_blockers` — empty = "Ready") vs **generation-time** (preflight coverage/camera/contract gates). They disagree by design.

### 4.1 Shots 3 and 4: "authoritative camera plan" for the Runway Router

- Gate: `scene_production_pipeline_service.py:1428` — `if provider == "runway_router" and not camera_plan: shot_blockers.append("camera plan: Runway Router requires an authoritative camera plan")`.
- Authority (`camera_provenance.py: `authoritative_camera_source``): only (a) a non-empty `camera_plan` persisted on the **exact current board shot's** `structured_parameters` (provenance STORYBOARD/APPROVED), or (b) `creator_shot_planning` (provenance CREATOR/USER_SPECIFIED). AI suggestions are explicitly non-authoritative (`AI_SUGGESTED` "awaiting approval — not renderable"; `GenerationReadinessPanel.tsx: CameraProvenanceLine`).
- DB: shots 1/2/5 carry `camera_plan.framing`; **shots 3 and 4 carry `camera_plan: None` and no `creator_shot_planning`** — hence the blocker, and only for them.
- Exact UI steps: per shot, the **AiCameraApproval** control ("Approve this camera decision", `AiCameraApproval.tsx`) — `POST …/projects/{projectId}/scenes/{sceneId}/camera-approvals/{storyboardShotId}` with `{approved_by, expected_version_id}` (`studioApi.ts:3778`; service `previs_service.py:664`). This locks the visual-plan framing as the creator camera plan. **Yes, camera approvals attach to a board version:** the request binds `expected_version_id` to the on-screen version and is refused on stale versions; because an approved board is immutable, approval **creates a new draft board version** — after which continuity review + board re-approval are required before rendering (stated in the component). Shots 1/2/5 show the "Camera decision approved" state; 3/4 still show the pending AI_SUGGESTED control (all five have `visual_plan.framing`, so the button is available on 3/4).
- Side effect (fix-order critical): approving camera on v3 orphans v3's five approved image-prompt rows (new shot IDs → `missing`), requiring re-save/re-approve of image prompts on the new version.

### 4.2 Shot 5: "canonical content coverage unresolved" while listed Ready

- "Ready" is board-level: shot 5's `render_blockers == []` (true for all five v3 shots), so `_inspect` reports ready.
- Coverage is a generation-time gate: `scene_coverage_contract.py:660,748` — a shot with **empty `covered_content_ids`** that is not an establishing/transition shot with reasoned `INTENTIONAL_SILENCE` gets `content_coverage_state = UNRESOLVED` + blocker. Shot 5's `covered_content_ids == []` (shots 1–4 carry 1/1/1/4 IDs respectively) — hence unresolved.
- Why it matters beyond shot 5: `prepare_scene_batch` sets `coverage_resolved = not coverage_blockers` and, when False, mints **no** frozen contract for **any** entry (`entry["generation_contract"] = None`, lines 2010–2015). One uncovered shot poisons the whole batch's contracts (see §4.3).
- Exact UI steps: assign shot 5's content in **Scene Direction** (CreatorDecisionWorkspace → coverage decisions: assign the leftover canonical content unit(s) to `scene_001_shot_005`, or record a reasoned editorial disposition), then save — which mints a new draft board version → continuity review → board re-approval. (Same version-orphaning side effect on image prompts as §4.1.)

### 4.3 Shots 1, 2 (and 5): "no parsable frozen generation contract"

- Gate: batch authorization parses each prepared entry's `generation_contract` (`scene_production_pipeline_service.py:1038-1046`); unparsable/missing → "produced no parsable frozen generation contract." The Runway adapter additionally requires a persisted contract and its `camera_plan` field (`app/adapters/__init__.py:2175,2181`).
- **Yes — absent-before-approval is expected.** Frozen contracts are minted **during batch preparation/freeze** (`freeze_generation_contract`, lines 2008–2088), never at board approval (`approve_version` checks render blockers + continuity + image gate only) and never persisted onto storyboard shots — all five v3 `render_contract_json` rows show `generation_contract: ABSENT`. They exist only inside prepared-batch entries, and only when coverage resolved (§4.2: currently they would be `None` for every shot because shot 5 breaks coverage).
- So this blocker is downstream fallout, not an independent defect: fix coverage (§4.2) and camera (§4.1), run a fresh preflight/prepare, and contracts get minted; the authorization-time parse then succeeds. (Shots 3/4 will additionally show it until their camera plans exist, since the freeze carries `camera_plan`/`camera_provenance` into the contract.)

**Root causes (Q4):** (camera) shots 3/4 have no persisted board/creator camera plan while the Router demands one — cleared by per-shot AiCameraApproval (version-bound, spawns a new draft); (coverage) shot 5 covers zero canonical content units while board-"Ready" only means zero render blockers — cleared by a Scene Direction coverage assignment (also spawns a new draft); (contract) frozen contracts are freeze-time artifacts deliberately withheld while coverage is unresolved and never stored on the board — expected-absent, clears automatically once the first two are fixed and a fresh prepare runs.

---

## 5. Proposed fix order (no fixes applied)

1. **Decide the Locked-appearance selection rule first** (code, not data): scope the block to the shot's visible cast / scene assignment and/or raise `max_characters`, because every downstream prompt regenerates it. Amputating Maya textually while her approved image prompt says "Maya" is the highest generation-quality risk. (`shot_prompt_builder.py:237-270`; scene_001's empty `characters` is the data half.)
2. **Camera approvals for shots 3 + 4** (AiCameraApproval → new draft version). Do this before touching image prompts.
3. **Coverage assignment for shot 5** (Scene Direction → new draft version). Combines with step 2's version churn: aim for **one** new draft covering both, then continuity review + board re-approval.
4. **Re-save + Approve the five Runway image prompts on the final version's new shot IDs** (Save edit, then Approve prompt per shot; all ≤1000 UTF-16). Do this **last** — any earlier board edit orphans them again. Consider carrying image-prompt rows across `_clone_shot_for_version` when the canonical hash is unchanged (the hash check already makes this safe).
5. **Run a fresh Generation preflight** (GenerationReadinessPanel Re-check): coverage resolved → frozen contracts minted at prepare → camera/contract blockers clear. Expect this panel, not the board, to be the source of truth for generation.
6. **Only then, optionally, train Maya** (Character Look → Train This Look → Begin Training → `complete`) if a reusable provider-side identity is actually wanted. It is independent of all blockers above — the picker is opt-in per take and nothing in generation requires it. Do not conflate it with locking/approval, which Maya already has.

## 6. State notes for the record

- `sbv_3cee32c0326a` is now **approved** (not draft); it is both `current_version_id` and `approved_version_id`. No version supersedes it.
- Canonical lengths (UTF-16): 2286 / 2203 / 2934 / 2892 / 2236 — all over the 1000-unit Runway image-prompt limit, which is exactly why the separate (already-approved, 368–575-unit, hash-fresh) human image prompts exist.
- Pre-existing working-tree modifications were observed (`git status --porcelain` shows many `M`/`D` entries unrelated to this task, e.g. under `reports/` and `studio-backend/reports/`); this audit adds only `docs/audits/SCENE001_BLOCKERS_2026-10-17.md`. No other file was touched (verified: DB opened `mode=ro`; no writes, no restarts, no provider calls).

---

## Owner click path

Read-only research — none of these steps were performed. All locations are in Previs → Step 2 (Build blueprint) unless noted. Assumes the board is currently at approved v3 (`sbv_3cee32c0326a`); every new draft below requires its own continuity review + board approval before the next step sees it.

### 1. Approving camera for shots 3 and 4

- Control: the per-shot **AiCameraApproval** card (`studio-app/src/components/AiCameraApproval.tsx`, rendered at `PrevisRoom.tsx:2641`). Shots 3 and 4 show the amber "Camera decision · AI suggestion" card with the `AI_SUGGESTED` framing verbatim; shots 1/2/5 show the green "Camera decision approved" state instead.
- Button: **"Approve this camera decision"** (`data-testid="approve-ai-camera-3"` / `approve-ai-camera-4`). It calls `POST …/projects/{projectId}/scenes/{sceneId}/camera-approvals/{storyboardShotId}` with `{approved_by, expected_version_id}` (`studioApi.ts:3778`). It locks only the shown framing as the creator camera plan — no values invented.
- Do shot 3 and shot 4 (one click each). Each approval is version-bound: a stale `expected_version_id` is refused rather than applied elsewhere.

### 2. Resolving shot 5's "canonical content coverage unresolved"

- A content unit is one canonical screenplay-derived obligation (a beat/action/dialogue the scene must account for). "Covering" it means assigning it to exactly one approved shot, or explicitly omitting it with a reason.
- Control: **CreatorDecisionWorkspace → "Scene Direction & coverage decisions"** (`SceneDirectionPanel.tsx:114`, `data-testid="coverage-workspace"`) → **Content coverage** section (`data-testid="coverage-section-content"`). For each unassigned content row: set **"Content decision N"** to **"Assigned to one approved shot"** and pick **Shot 5** in **"Owning shot"** (or "Explicitly omitted" + required reason). Shot 5 currently has `covered_content_ids == []` while shots 1–4 carry 1/1/1/4 — the leftover unit(s) belong to shot 5.
- Button: the workspace **Save** (`useSceneDirection.save` → `saveSceneDirection`, `sceneDirectionApi.ts:13-16`). Note the panel's own copy: "Save commits your explicit decisions as a new draft." If the save reports "The storyboard changed. Reload before saving," reload and re-apply (optimistic concurrency on `expected_version_id`).
- Constraint: new or changed Scene Direction decisions require the **current approved** version (`scene_direction_service.py` Option B draft carry); an unchanged decision carries forward across current drafts and is re-validated live on every save (422 if the referenced row is no longer approved and canonical). Coverage edits that change the decision still need the camera-approval draft (step 1) to pass continuity review and board approval first.

### 3. Order that creates the fewest new board versions

Minimum is **two** new drafts, then image prompts, then preflight:

1. **Camera approvals (shots 3 + 4)** → creates **draft v4**. Run continuity review → **approve v4** (board approval gate requires the image-prompt gate too — v4's cloned shots start with *missing* prompts, so either re-save/approve image prompts on v4 first, or accept approving v4's board only after a throwaway prompt pass; cheapest is to do the throwaway via derive+approve per shot, knowing v5 will orphan them again — better: approve v4's board, then immediately do step 2 before investing in hand-written prompts).
2. **Coverage assignment (shot 5)** on approved v4 → creates **draft v5**. Continuity review → **approve v5**.
3. **Re-save + Approve the five Runway image prompts on v5's new shot IDs** (per-shot "Save edit", then "Approve prompt"; all ≤1000 UTF-16). Do this last — any earlier board edit orphans them.
4. **Fresh preflight**: Generation Readiness → **Re-check**. Coverage resolved → frozen contracts minted at prepare → camera/contract blockers clear.

Do not interleave: image-prompt work done before step 3 completes is discarded by the next version mint.

### 4. Which steps create a new draft version and orphan image prompts

- **Creates a new draft (orphans image-prompt rows — new `sbs_` IDs, prompts start `missing`):** AiCameraApproval (`previs_service.py:664`, "an approved board is immutable"); Scene Direction save (`scene_direction_service.py:394-456`); explicit storyboard regenerate (`create_version`).
- **Does NOT create a version (prompts safe):** continuity review; board approval (`approve_version` mutates status in place); image-prompt Save/Approve; Generation preflight Re-check (read-only); "Direct the action" take rendering (writes takes, not the board).

---

## Locked-appearance fix (2026-10-18) — length guard, scope note

- **Video-path prompt-length guard (`runway_router`):** `prompt_budget_service.prompt_policy` sets the Router ceiling at **20,000 characters** (video input cap; 32,000 image). Studio forwards the canonical prompt verbatim; over-limit fails closed to `needs_review` and is refused at submit — never truncated (`budget_job`, `validate_provider_text`, enforced in `render.py` and the Router adapter). Scene_001's canonical prompts are 2,203–2,934 characters, ~7–9x below the cap, and the scoping fix shortens them further. The video path does **not** fail on these lengths.
- **Existing boards keep their stored canonical text.** Scene_001's approved v3 still contains the Dre/Elena/Jay block in every shot's `provider_neutral_prompt` — the fix changes only newly built boards. A **board rebuild** (new version + continuity review + re-approval, then re-save/re-approve image prompts on the new shot IDs) is needed to pick the fix up.
