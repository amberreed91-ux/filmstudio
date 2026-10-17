# Studio Workstream — Multi Shot Integrity Audit

Date: 2026-09-25 · Branch: `backend-expansion-dependency-slicing`
Scope: read-only audit of the Multi Shot workflow from canonical scene state to the final provider request boundary.
Constraints honored: **no production code modified, no Runway request submitted, no credits consumed, no fixes applied.** All evidence below was gathered by reading code and by read-only inspection of real project data (`data/studio.db`, `data/project_state_store.json`, project `project_5907c60cddbc`).

---

## Executive Summary

**Is Studio currently producing a true Multi Shot request?**
No — and yes. Studio does **not** call Runway's Multi-Shot workflow (the `/v1/recipes/multi_shot_video` recipe with `auto` or `custom` mode). It has its **own** multi-shot pipeline: independently addressable, versioned storyboard shots (`storyboard_shots` table) are rendered as **separate single-shot provider tasks**, then stitched with FFmpeg (`SceneProductionPipelineService` → `short_film_stitching_service`). This is a true shot-by-shot representation — arguably more faithful than Auto mode — but it is **not** the Runway Multi Shot feature the brief describes, and per-shot durations are fixed defaults (5 s) rather than per-shot authored timings.

**Is the shot list authoritative?**
Yes, in the storyboard blueprint layer. `scene_render_inputs()` refuses to render unless `approved_version_id == current_version_id` and every shot belongs to the approved version. Shot order is `sorted(shots, key=shot_number)` — deterministic, DB-ordering independent. A live trace on the real scene (`scene_002`, version `sbv_dbafa23cf4a1`) resolved exactly shots 001→005 in order.

**Is Custom or Auto mode being used?**
Neither. If Runway's recipe were ever adopted, **Custom mode is the only defensible choice** for Studio (Auto hands the approved shot list to Runway's "narrative planner" for re-decomposition — exactly the reinterpretation the brief prohibits). Studio's current per-shot pipeline achieves the same outcome without reinterpretation, at the cost of N separate generations and self-managed continuity.

**Are hallucinations potentially originating before Runway?**
Yes, in four concrete places (detailed in the risk map): (1) storyboard shot *framing/camera* values are heuristic template output (`ShotSequenceService._BASE_TYPES`), not scene-derived, yet carry `APPROVED` provenance once the version is approved; (2) edit-grammar strings ("match_cut", "bridge_action", "linger_on_micro_expression") are stored as **camera movement** and flow into camera provenance and `shot_planning.camera`; (3) the approved board's stored prompts contain 512-char truncation artifacts and severed sentences (e.g. shot 4 ends "She remembers everything. The."); (4) shots 2–5 all carry the same generic "Over-the-shoulder or two-shot framing" because a dialogue-tag heuristic dominates the framing choice.

**Are stale scenes or shots entering the request?**
Not into the primary path. The legacy `multi_shot_execution_ledger` inside `execution_summary.scenes[scene_002]` still contains **mock-era data** (picsum.photos placeholder URLs, synthetic shot intents) and remains a *fallback* shot source in `_resolve_ordered_shots` — it did not win in the live trace (storyboard shots resolved first), but it is a live hallucination vector whenever storyboard/scene shots are absent. Previs's own comment ("the frontend sends a stale editable copy of the Step-1 plan") documents a known stale-input path that is mitigated server-side.

**Render readiness (short answer):** **Not yet safe for the first Runway experiment on scene_002 via the scene pipeline.** The fail-closed reference gate would block it (no approved canonical setting reference; DRE has zero locked references) — which is correct behavior, but it means the experiment cannot run; and the batch path lacks the generation readiness gate that the Previs path has. Fixes required are listed in *Recommended Changes*. The single-shot Previs path is the safest first experiment.

---

## Current Architecture (complete pipeline)

```
The Page (script upload)
  └─ ScriptParser / FilmStructureService            app/services/script_parser.py (15,782 lines)
       ├─ FilmStructure / Act / Sequence / Beat     app/models/crew.py:737 (organizational, not generation state)
       ├─ CreativeSpine                             app/models/spine.py:207 (governance, referenced not copied)
       └─ execution_summary.scenes[]                project_state_store.json (scene_id, heading, text, characters,
                                                      multi_shot_execution_ledger ← LEGACY MOCK DATA)

Scene → Storyboard
  └─ StoryboardBlueprintService                     app/services/storyboard_blueprint_service.py
       ├─ ShotSequenceService.build_shot_sequence_plan   app/services/shot_sequence_service.py
       │    (5-step heuristic template: establishing/medium/close_up/transition/emotional_detail
       │     reordered by pacing/emotional_curve — NOT derived from scene content)
       ├─ _build_initial_shots → StoryboardShot[]   app/models/storyboard_blueprint.py
       ├─ create_version / approve_version          (requires completed Continuity Review)
       ├─ reorder_shots / lock_shot / delete_shot   (locked shots cannot move; reorder requires every shot exactly once)
       └─ _validate_shot_renderable                 (shot.version_id must equal approved AND current)

Storyboard → Generation inputs (the single translation point)
  └─ storyboard_render_inputs(shot)                 app/services/storyboard_render_inputs.py
       prompt = contract.provider_neutral_prompt (+ continuity handoff block)
       parameters = structured_parameters + duration + ratio + strict_render_settings + preserve_shot_prompt
                    + seed? + storyboard_frame_url? + continuity_handoff?
       reference_assets = [storyboard_frame?, *contract.reference_assets]

Two generation entry points:

  A. Previs (one shot at a time)                    app/services/previs_service.py generate_scene
       duplicate/active-job detection → fresh_render supersede
       → duration_options provider check
       → model selection (USER authoritative / registry auto)
       → generation_context_service.derive_camera_instructions   ← camera provenance
       → create_generation_context + validate_generation_context  ← READINESS GATE (blocks)
       → _enforce_cost_limit                                      ← cost gate
       → render_service.create_job → submit_job

  B. Scene pipeline ("Multi Shot", whole scene)     app/services/scene_production_pipeline_service.py generate_scene
       _resolve_ordered_shots (storyboard-first, then scene.shots, then shot_candidates,
        then LEGACY multi_shot_execution_ledger, then single-shot fallback)
       for each shot (ordered):
         prompt = _shot_prompt(scene, shot, index, total)      ← board prompt + "[SHOT POSITION]" block
         create_job(prompt, reference_assets=shot.reference_assets, parameters=shot.parameters)
         _link_storyboard_render_if_present
         submit_and_wait (needs_review honored)
         audio_pipeline per shot (dialogue bake)
       → short_film_stitching_service.stitch_scene (FFmpeg)

RenderService.create_job                          app/services/render.py (~4,400 lines)
  per-scene provider override → storyboard-frame provider restriction (runway/openrouter only)
  → _validate_model_override (registry-backed)
  → idempotency (_request_idempotency_key / _find_idempotent_job)  ← can return an existing pending job
  → generic-prompt rebuild path (slotted prompt, character staging, standing corrections,
    knowledge context, identity guidance, department context)
  → consistency payload (locked character refs) + environment refs appended
  → zero-touch debug metadata
  → _generation_context_metadata (observational only — records context, model selection, cost)

RenderService.submit_job
  validate_generation_payload                      app/services/reference_validation.py  ← FAIL-CLOSED reference gate
  → _missing_local_reference_assets check
  → budget_job (whole-fact allocation)             app/services/prompt_budget_service.py
  → prompt contradiction detection
  → adapter.submit_job                              app/adapters/__init__.py RunwayAdapter
       POST /v1/text_to_video  |  /v1/image_to_video
       payload = { model, promptText, duration, ratio, [promptImage], [seed] }
       validate_provider_text (512-char Runway policy) immediately before the wire
```

**FilmStructure and CreativeSpine** are present and consumed for governance/structure, but they are **not part of the generation payload path**; scene generation truth lives in `execution_summary.scenes[]` + storyboard blueprints. Nothing in the Multi Shot payload is sourced from FilmStructure/CreativeSpine directly (storyboard provenance *records* that spine constraints were available — advisory only).

---

## Shot Data Flow (Shot 1 … Shot N)

Where each shot attribute actually lives (verified against `app/models/storyboard_blueprint.py` and live rows):

| Brief asks for | Stored? | Where | Live evidence (scene_002, approved v1) |
|---|---|---|---|
| shot_id | ✅ | `StoryboardShot.shot_id` | `scene_002_shot_001` … `_005` |
| shot_order | ✅ | `shot_number` (+ storage order) | 1–5 |
| shot_version | ⚠️ partial | via `version_id` (board version, not per-shot) | all shots `sbv_dbafa23cf4a1`; **generation context's `shot_version` is always `"absent"`** (see H-1) |
| duration | ✅ | `render_contract.duration_seconds` | 5 for all (template default; never authored) |
| action | ✅ (indirect) | inside `provider_neutral_prompt` segment | per-shot text present |
| subject | ⚠️ | implicit in prompt cast lines | "Only DRE and MAYA visible" |
| camera | ⚠️ polluted | `visual_plan.framing` / `camera_movement` | framing = template shot type; movement = **edit grammar** ("match_cut", "bridge_action", "linger_on_micro_expression") |
| framing | ✅ | `visual_plan.framing` | "establishing_shot"/"medium_shot"/"close_up"/"transition_shot"/"emotional_detail_shot" (mapped strings) |
| movement | ⚠️ | `camera_movement` (misused, see above) | — |
| lens | ❌ | empty | `lens_language: ""` for all 5 |
| dialogue | ⚠️ | separate `dialogue_lines` (scene-level, only 2 generic rows) | not per-shot authored |
| visual requirements | ✅ | `intent`, `continuity_plan`, `department_notes` | present |
| character references | ✅ | `render_contract.reference_assets` (empty here) + locked refs resolved at create_job | contract refs `[]` for all 5 |
| setting references | ❌ for this scene | none approved → submit would block | — |
| style references | ❌ | not wired into shot contracts | — |
| continuity requirements | ✅ | `continuity_plan` (location/emotional filled; opening/action/ending empty) | — |
| generation status | ✅ | `shot.status` + `storyboard_render_links` (0 links) + previs_images | — |
| generation history | ✅ | render_jobs / previs_images ( Vault) | 6 historical jobs for scene_002 |

**Verdict:** Studio genuinely represents the scene as independently addressable shots — the `Scene ├ Shot 1…5` shape exists in SQLite with per-shot contracts — **not** a single scene prompt later divided by an AI. The weaknesses are *content quality* (template camera, fixed durations) and *context completeness* (stub shot_version), not representation.

Live trace `Storyboard Shot → Generation Shot` (scene pipeline orderer, actual run during audit):

```
Storyboard shot_number 1 (sbs_77d3ae4fe1e9, scene_002_shot_001) → generation position 1
Storyboard shot_number 2 (sbs_8b1c822fc206, scene_002_shot_002) → generation position 2
Storyboard shot_number 3 (sbs_1d23d6055c17, scene_002_shot_003) → generation position 3
Storyboard shot_number 4 (sbs_4d91b1c6bd3c, scene_002_shot_004) → generation position 4
Storyboard shot_number 5 (sbs_ee2d6576f016, scene_002_shot_005) → generation position 5
```

No mapping changes. `_resolve_ordered_shots` was verified to return these 5 in this order for the real project (storyboard branch won; ledger and shot_candidates fallbacks not exercised).

Ordering checks:
1. **Deterministic** — `sorted(..., key=shot_number)` / `(shot_number_from_id, id)` tuples. ✅
2. **Stable IDs** — `storyboard_shot_id` (`sbs_*`) immutable across a version; `shot_id` (`scene_002_shot_00N`) normalized at creation. ✅
3. **Order preserved** Storyboard → Previs → generation. ✅
4. **Previous-shot insertion** — `reorder_shots` requires the exact current set; `create_version` renumbers clones. ✅
5. **Foreign-scene shot** — filtered by `shot.scene_id` ownership; ledger fallback normalizes only same-scene ids. ✅ (primary), ⚠️ (ledger fallback can fabricate `shot_{scene_id}_{n}` from arbitrary raw ids)
6. **DB-ordering independence** — explicit sort everywhere; no reliance on row order. ✅
7. **Historical shots becoming current** — blocked by `_validate_shot_renderable` (shot.version_id must equal approved **and** current). ✅

---

## Storyboard Data Flow → generation input

```
storyboard_shots (approved version)
  → scene_render_inputs(project, scene)            [gates: approved==current; per-shot renderable; ≥1 shot]
    → storyboard_render_inputs(shot)               [prompt/params/refs/seed/frame]
      → parameters["storyboard"] = {blueprint_id, version_id, storyboard_shot_id, shot_number, …}
      → SceneProductionPipeline.create_job(..., parameters=inputs.parameters)
      → storyboard metadata rides into job.input_payload.parameters["storyboard"]
      → _link_storyboard_render_if_present writes StoryboardRenderLink after completion
```

Stale-data entry points checked (brief §5 list): cache ✅ n/a (no TTL caches on this path) · database queries ✅ version-gated · scene IDs ✅ ownership-checked · shot IDs ✅ version-gated · previous generation metadata ⚠️ idempotency reuse (below) · previous prompts ⚠️ stored board prompts carry 512-truncation artifacts (H-3) · frontend state ⚠️ previs stale `promptText` (documented, mitigated) · local/session storage ✅ not consulted server-side · API request reuse ⚠️ idempotency · background state ✅ · derived scene data ⚠️ legacy ledger (H-5).

Idempotency nuance: `_find_idempotent_job` returns an existing **pending/rendering** job on identical request hash. Board version lives in `parameters`, so any board change changes the hash → old job is *not* reused after a board edit. Same-parameters re-click during an active render intentionally reuses the job (documented behavior).

---

## Camera Data Flow (provenance)

Canonical model: `generation_context_service.derive_camera_instructions` — priority USER_SPECIFIED → APPROVED (creator-approved plan / board visual_plan) → UNSPECIFIED placeholders. AI suggestions are **only** attached when carried in an approved plan; the gate hard-blocks any `AI_SUGGESTED` value that reaches it with content. This satisfies the brief's invalid-transformation test at the *mechanism* level: nothing in the current pipeline can invent "35mm, slow dolly" for a shot that specified "medium shot" — there is no source for lens/movement invention (UNSPECIFIED placeholders remain empty).

**But two provenance defects exist in the current data:**

1. **"APPROVED" provenance is granted to heuristic content.** The framing values stored on scene_002's shots (`establishing_shot`, `medium_shot`, `close_up`, `transition_shot`, `emotional_detail_shot`) are the `_BASE_TYPES` template — a generic cinematic flow, not scene-derived — yet once the version was approved, `derive_camera_instructions(storyboard_shot=…)` stamps them `APPROVED` with the board version as `source_version`. Audit-trace output (real data):

```
Shot 1  camera[framing]=establishing_shot        source=APPROVED ver=sbv_dbafa23c…   camera[camera]=match_cut   source=APPROVED
Shot 2  camera[framing]=medium_shot              source=APPROVED …                   camera[camera]=match_cut   source=APPROVED
Shot 3  camera[framing]=close_up                 source=APPROVED …                   camera[camera]=match_cut   source=APPROVED
Shot 4  camera[framing]=transition_shot          source=APPROVED …                   camera[camera]=bridge_action source=APPROVED
Shot 5  camera[framing]=emotional_detail_shot    source=APPROVED …                   camera[camera]=linger_on_micro_expression APPROVED
shot_size/angle/movement/lens = UNSPECIFIED (empty) for all shots ✅
```

2. **Edit grammar stored as camera movement.** `transition_hint` values ("match_cut", "bridge_action", "linger_on_micro_expression") are cut/continuity grammar. `storyboard_blueprint_service._build_initial_shots` explicitly avoids sending them as camera *for image prompts* ("sending 'match_cut' as camera actively misdirects the provider") — but the same strings sit in `visual_plan.camera_movement` and `structured_parameters.shot_planning.camera`, and the generation-context service passes `camera_movement` through as the `camera` dimension. So the provenance system records a *camera* that is actually an *edit instruction*.

Also: **the scene pipeline path never calls `derive_camera_instructions` at all**; `_generation_context_metadata` (observational) derives camera only from `creator_shot_planning`/`camera_plan` request params — for pipeline renders the recorded camera is empty/UNSPECIFIED even though the board has approved values.

---

## Reference Data Flow (provenance)

Layers, separated per the brief:

| Kind | Source | Current state (scene_002) |
|---|---|---|
| locked character references | `character_reference_locks` (`lock_status='locked'`, `source_status='approved'`, adherence-reviewed promotion) | MAYA: 2 locked (general + alternate_angle, from scene_001 renders). **DRE: 0.** MOM: 2 (but MOM ∉ scene cast). |
| provisional / historical | `lock_status='superseded'`, `source_status='provisional'` | present (scene_001 storyboard-derived) — **excluded** from `_approved_character_urls` ✅ |
| setting references | `reference_assets` (`target_type='setting'`, canonical+approved) | **none approved for scene_002** → fail-closed |
| scene references | `environment_continuity_context.selected_references` (create_job) | resolved per scene |
| style references | not wired into shot contracts | n/a |
| storyboard references | `storyboard_frame_url` → provider `promptImage` (shot 1 only) | local `/previs-assets/…png` → base64 data-URL at the adapter ✅ |
| temporary references | n/a | — |

Integrity guarantees verified in code:
- locked ref cannot be replaced: supersede flow writes new lock rows; selection reads only `locked`+approved ✅
- current refs cannot be replaced by previous: `resolve_scene_reference_requirements` re-resolves from storage at submit time ✅
- Shot 1's ref cannot leak to Shot 3: per-shot consistency payload resolved by `shot_id`; `validate_generation_payload` enforces `target_id` ownership ✅
- other-scene refs: rejected via `allowed_urls` membership check (`stale_reference_payload`) ✅
- version matching: reference set content-hashed into `reference_version` in the generation context (previs path) ✅

**Live fail-closed result (read-only check, no submission):** `resolve_scene_reference_requirements(project_5907c60cddbc, scene_002)` raises
`Generation blocked: Scene scene_002 for setting scene_002. no approved canonical environment reference is available.`
→ A Runway submission of this scene would be **blocked at `submit_job`** today. Correct behavior; the experiment simply cannot run until references are approved.

---

## Versioning

| Stage | Protection | Status |
|---|---|---|
| Scene | `scene_version` = hash(scene_id, heading, text, updated_at); compared in the readiness gate | ✅ where the gate runs (previs) |
| Shot | `shot_version` | ❌ **stub** — `create_generation_context` passes `self.shot_version(None)` → always `"absent"` (H-1) |
| Storyboard | blueprint `approved_version_id == current_version_id`; per-shot `version_id` equality; continuity-review precondition | ✅ strongest gate in the system |
| References | `reference_version` content hash of the exact URLs crossing the boundary | ✅ previs; observational-only in pipeline |
| Camera | `camera_version` hash of provenance-tagged instructions | ✅ mechanism; ⚠️ content polluted (above) |
| Model | registry allowlist + USER/AUTO selection record | ✅ |
| Cost | estimate recorded in metadata; hard limit only in previs | ⚠️ gap in pipeline (H-6) |

---

## Prompt Construction (per shot, origins shown)

Board prompt composition (`_build_provider_neutral_prompt`, stored at version creation):

```
[plan_head]      framing template + camera + environment + lighting + "Shot N of M."   ← ShotSequenceService template
+ [shot prompt]  build_shot_aware_prompt(scene, N, total_shots=M)                      ← scene text segmented per shot,
                                                                                        cast guard "Only X and Y visible",
                                                                                        character visuals, mood
+ [rationale]    shot_rationale_service
+ [locked tail]  ensure_locked_appearance_in_prompt (non-truncatable)
```

At render time the pipeline appends:
```
[SHOT POSITION] Shot N of M in scene. Maintain character identity and visual continuity.
```

Then `create_job` may add: character staging/visuals, standing corrections, knowledge guidance, identity constraints, environment continuity block, director-intent tone line — then `budget_job` (whole-fact allocation) and finally `validate_provider_text` (Runway: 512 chars) at the adapter.

**Sources checked for injection of stale/unapproved content:** old prompt ❌ (each render re-reads the board) · old storyboard ❌ (version-gated) · old camera ⚠️ (approved-but-heuristic framing; edit-grammar movement — H-2) · old scene ❌ · old character ❌ (locked looks re-resolved) · generic cinematic instructions ⚠️ **YES, present**: shots 2–5 all open "Over-the-shoulder or two-shot framing for conversation" because `_determine_shot_type`'s dominant-DLG-tag fallback fired for every non-first shot; also the universal tail "Cinematic, film quality." · AI assumptions ⚠️ framing templates (H-2) · previous generation metadata ❌ · provider-generated instructions ❌.

**Concrete defects in the current approved data (real payload would carry these):**
- Shot 1 prompt ends mid-word: "…mismatched worn layers stands . e" — 512-char truncation artifact of the *previously used* builder; the fix exists in current code (no truncation) but the **approved version's stored prompts still carry it**.
- Shot 4's action segment is severed at the segmentation boundary: "Maya wakes up. Two months before the apocalypse. She remembers everything. The." — an incomplete sentence would be sent as action text.
- Shot 3 contains "Maya is killed. Darkness." (correct scene content) but shot 4 also contains the *preceding* beat's tail — `_segment_scene_text` splits on line counts, not sentence boundaries.

---

## Final Provider Payload (sanitized hypothetical — NOT submitted)

Mode: Studio's own per-shot pipeline (Runway Multi-Shot recipe **not** used). Provider as configured by the user's env: `RENDER_VIDEO_PROVIDER=open…` (OpenRouter); the Runway-shaped payload below is what Studio *would* send with provider=runway, per the brief.

Boundary facts (from `RunwayAdapter.submit_job`): endpoint `/v1/image_to_video` when a `promptImage` exists (shot 1: storyboard frame, base64 data-URL), else `/v1/text_to_video`; payload keys exactly `{model, promptText, duration, ratio, [seed]}`; one reference maximum (gen4.5); `validate_provider_text` (512 chars) immediately before the wire; cost metadata recorded, never spent.

```
provider:            runway                       (env default would otherwise be the user's openrouter setting)
model:               gen4.5                       (adapter env default RUNWAY_MODEL; pipeline params carry no model)
generation mode:     per-shot text_to_video ×4, image_to_video ×1 (storyboard frame as promptImage)
scene_id:            scene_002
shot_ids (ordered):  scene_002_shot_001 … scene_002_shot_005
durations:           5, 5, 5, 5, 5                (render_contract defaults; total 25 s; no per-shot authoring)
scene_version:       <hash of scene_002 heading/text/updated_at>
shot_versions:       "absent" for all (stub — H-1)
storyboard_version:  sbv_dbafa23cf4a1 (approved, pinned in parameters["storyboard"].version_id)
reference_versions:  shot 1 d519ba1892077636 (storyboard frame); shots 2–5 none
camera versions:     hash of [framing APPROVED, camera=match_cut/… APPROVED, shot_size/angle/movement/lens UNSPECIFIED]
references sent:     shot 1 → promptImage = base64(scene_002_shot_001_storyboard_qwen.png); shots 2–5 → none
prompts:             stored board prompt (512-char legacy artifacts included — see Prompt Construction)
                     + "\n\n[SHOT POSITION]\nShot N of 5 in scene. …"
generation_context:  recorded observationally per job (context id minted; NOT part of request hash)
estimated cost:      12 cr/s × 5 s × 5 shots = 300 credits (gen4.5); gen4_turbo 125; wan3 250
routing decision:    none performed on this path — adapter default model; USER/AUTO router not consulted
selection reason:    n/a (would be "USER_SELECTED/… " only via previs path)
```

**Outcome if submitted today:** shot 1 blocked by `validate_generation_payload` (referenceAssets non-empty → strict mode → missing canonical setting reference / DRE locked refs). Shots 2–5: blocked if a consistency payload resolves (DRE missing canonical refs), otherwise submitted without canonical validation. Either way **no credits would be spent on scene_002 in its current reference state** — the fail-closed gate does its job.

Runway Multi-Shot recipe comparison (if ever adopted): requires 3–5 ordered shots, per-shot prompt 3–512 chars, per-shot durations summing to a total of 5/10/15 s. Studio's 5 shots would fit Custom mode; the fixed 5-s-each durations (sum 25) would **not** fit without re-authoring; >5-shot scenes have no provider conflict under Studio's own pipeline (no limit), but would be rejected by the recipe.

---

## Hallucination Risk Map

| ID | Category | Source | File · Function | Input → Output | Why it can hallucinate | Severity | Recommended fix (do NOT implement yet) |
|---|---|---|---|---|---|---|---|
| H-1 | C. Shot construction / versioning | Shot version stub | `app/services/generation_context_service.py` · `create_generation_context` (line ~249: `shot_version=self.shot_version(None)`) | any shot → `shot_version="absent"` | The fingerprint claims to stamp shot state but never sees the shot; a shot edit cannot invalidate a prepared context on the shot axis | **High** | Pass the real shot dict (render contract + updated_at) into `create_generation_context` |
| H-2 | D. Camera generation | Heuristic framing + edit-grammar movement stamped APPROVED | `app/services/shot_sequence_service.py` · `build_shot_sequence_plan`; `storyboard_blueprint_service._build_initial_shots` (`_framing_map`, `_camera_move`); `generation_context_service.derive_camera_instructions` | template `shot_type`/`transition_hint` → `visual_plan.framing/camera_movement` → APPROVED camera instructions & `shot_planning.camera` | Values were never chosen by a human for camera; approval of the *board* is transmuted into approval of *camera data*; "match_cut" is not a camera move | **High** | Separate edit-grammar from camera provenance; require explicit creator camera approval before stamping APPROVED |
| H-3 | G. Prompt construction | Truncation/severance baked into approved prompts | `storyboard_blueprint_service._build_provider_neutral_prompt` (historical 512 cap) + `shot_prompt_builder._segment_scene_text` | scene text → per-shot segments → stored 512-char prompts | Approved v1 prompts end mid-word; segmentation severs sentences across shot boundaries; these strings are the exact `promptText` sent | **High** | Regenerate the board version with the current non-truncating builder + sentence-boundary segmentation (operator action) |
| H-4 | C. Shot construction | Generic framing fallback | `shot_prompt_builder._determine_shot_type` / `SHOT_FRAMING_BY_TAG` | dialogue-dominant segment → "Over-the-shoulder or two-shot framing for conversation" | Identical framing sentence on shots 2–5 regardless of content; a generic cinematic instruction injected into every prompt | Medium | Derive framing from approved per-shot visual plan only; drop tag-heuristic defaults from the render path |
| H-5 | I. Historical state | Legacy mock ledger | `project_state_store.json → execution_summary.scenes[].multi_shot_execution_ledger` (picsum.photos URLs, mock intents); consumed by `scene_production_pipeline_service._resolve_ordered_shots` fallback | stale ledger → shot list | If storyboard + scene shots are absent, mock-era shots with placeholder "renders" could be ordered and rendered as if canonical | Medium | Exclude the legacy ledger from generation fallbacks (read/report only) |
| H-6 | F. Multi Shot assembly / cost | Cost gate absent on batch path | `scene_production_pipeline_service.generate_scene` (no `_enforce_cost_limit` call) | N shots × duration × model rate | A 5-shot scene can be dispatched to a paid provider with no pre-spend estimate gate (previs path has one) | Medium-High | Invoke the existing `_enforce_cost_limit` (or an equivalent) per shot before create/submit |
| H-7 | L. Backend state | Observational-only context on batch path | `render.py · _generation_context_metadata` | pipeline params → context with UNSPECIFIED camera, absent shot version | Job metadata implies gate coverage that doesn't exist on this path; audit trails look richer than the actual guarantees | Medium | Either run the readiness gate on the batch path (see H-8) or clearly mark context as `ungated` |
| H-8 | B/C/F | Readiness gate not invoked on batch path | `previs_service.generate_scene` calls `validate_generation_context`; `scene_production_pipeline_service.generate_scene` does not | — | Scene/board staleness on the batch path is caught only indirectly (board version equality at input resolution, reference gate at submit) — camera provenance and scene-version mismatch are not | **High** | Route batch shots through the same gate before create_job |
| H-9 | E. Reference selection | Scene-level cast leakage into shot prompts | `render.py` character injection / `shot_prompt_builder._merge_scene_characters` | scene text mentions MOM → "Only DRE, MAYA, and MOM visible" on shots 3–5 | MOM is not in `scene.characters` but appears in the stored board prompts' cast guard; can summon a character the shot doesn't feature | Medium | Cast guard from per-shot plan (`character_focus`), not full-scene text |

---

## Stale State Risk Map

| Location | Entry vector | Guard today | Residual risk |
|---|---|---|---|
| Storyboard versions | stale version rows | `_validate_shot_renderable`, `approved==current` | none material |
| Scene rows | edited after job prepared | readiness gate (previs only) | batch path: none (H-8) |
| Shot rows | edited after job prepared | shot_version stub → **none** (H-1) | High until fixed |
| References | superseded/provisional locks | lock_status + approval filters + submit-time re-resolution | none material |
| Legacy ledger | mock-era data in project state | fallback only (4th priority) | H-5 |
| Idempotency cache | identical request hash during active render | hash includes board version + prompt + params | same-params retry intentionally reuses; acceptable |
| Frontend previs prompt | stale `promptText` copy | server re-attaches locked looks; `preserve_shot_prompt` flag | documented, mitigated |
| Render history | old takes | previs duplicate detection + Fresh Render supersede | pipeline path has no fresh-render concept (re-run = new jobs; overwrite applies to stitch only) |

**Fresh Render (brief §15):** implemented in the Previs path — `render_settings.fresh_render` supersedes the active job for that shot, mints a new generation context, keeps all history (Vault). ✅ for previs. The batch scene pipeline has no per-shot fresh-render semantics (it always creates new jobs, which is effectively fresh, but has no explicit context separation). Old payloads are never reused across runs because inputs are re-derived from the board each run.

---

## Multi Shot Compatibility (Studio ↔ Runway)

| Runway Multi-Shot (recipe, verified 2026-09-25) | Studio today |
|---|---|
| `mode: auto` — story prompt decomposed by Runway | **Not used.** Would cede shot decomposition to Runway's planner — incompatible with an approved Studio shot list |
| `mode: custom` — ordered 3–5 shots, per-shot prompt 3–512 chars | Studio has ordered, versioned shots with 512-char prompts — shape-compatible; count fixed at 3–5 by the recipe |
| per-shot durations summing to `duration` (5/10/15) | Studio stores fixed 5 s per shot (sum 25) — would be rejected; no sum validation exists |
| single task, single bill | Studio runs N separate tasks + local stitch — N× generations, no recipe support |
| `firstFrame` optional | Studio conditions shot 1 on the storyboard frame; shots 2–5 have no frame → t2v |
| reference media guidelines | gen4.5 accepts one promptImage; consistency payload selects one — aligned |

**Behavior with >5 shots:** Studio's own pipeline renders any shot count (no constraint); the recipe would refuse. Studio currently has **no code handling the 3–5 constraint** because it doesn't use the recipe — documented, not invented-fixable here.

---

## Duration Handling

1. Individual durations: `render_contract.duration_seconds` (5 for every shot — template default; `PrevisRenderSettings` can override per previs render but the board contract was never re-authored).
2. Total: not computed anywhere on the batch path; stitch concatenates actual outputs.
3/4. Provider min/max: previs path validates against `duration_options`; **batch path does not** (gen4.5 supports 2–10 s per registry — 5 s is fine today, but nothing checks).
5. Rounding: none — integer seconds; `_validate_requested_video_settings` refuses unsupported durations instead of rounding ✅.
6. Validation: adapter `supports_duration` fail-closed ✅ (gen4.5 path).
7. Inheritance from old shots: durations come from the board contract of the approved version — not from previous generations ✅.
8. Shot edit invalidates duration metadata: only via a new board version (durations are cloned/renumbered) ✅ — but note H-1 means the *generation context* won't see the shot change.

Exact durations Studio would send: **5, 5, 5, 5, 5 seconds** (total 25 s).

---

## Model Routing for Multi Shot

The router (`model_router.py`) is capability-based, human-overridable, fail-closed on incompatible USER selections (verified: `gen6` rejected; `gen4.5/gen4_turbo/wan3` accepted for a 5-shot 5-s profile during the audit). **But it has no Multi Shot concept**: requirements cover mode/references/duration/resolution/audio — there is no shot-count or multi-shot capability dimension; `ModelDefinition.capabilities` exists but is unused in routing; `providers/capabilities.py` reports `supports_multi_shot: False` for every provider (and `wan`'s config claims a `multi_shot` capability string that nothing consumes). Because Studio doesn't use the recipe, per-shot routing is *sufficient today*; a recipe adoption would require adding shot-count/duration-sum constraints to `check_requirements`. USER-selected incompatible model → blocked with explanation, never substituted ✅ (verified in code and tests).

---

## Cost Before Rendering

Verified read-only estimates (registry rates, 2026-09-25):

| Model | Rate | Per shot (5 s) | Scene (5 shots) |
|---|---|---|---|
| gen4.5 (default) | 12 cr/s | 60 | **300 credits** |
| gen4_turbo | 5 cr/s | 25 | 125 |
| wan3 | 10 cr/s (720p) | 50 | 250 |

Monetary conversion: not available in-repo (registry is credits-only) — recorded as unknown, honestly. No spend occurred; nothing was submitted; the only Runway-adjacent actions were registry/router lookups and a read-only reference-resolution call.

---

## What Should Remain Unchanged

- `storyboard_blueprint_service` versioning + `scene_render_inputs` + `_validate_shot_renderable` (the strongest integrity gates in the system).
- `reference_validation.resolve_scene_reference_requirements` / `validate_generation_payload` (fail-closed, ownership-checked).
- `generation_context_service` provenance/gate mechanisms (they need the H-1 input fix, not replacement).
- `RunwayAdapter` transport/hardening, registry-backed model allowlist, `validate_provider_text` before the wire.
- `model_registry` / `model_router` (bounded, no invented scores).
- Previs path ordering: duplicate check → fresh render supersede → duration options → model → **gate** → cost → create/submit.
- Mock/test-mode gating (`mock_success` local/test only).
- Historical renders/storyboards/generation records — untouched; nothing deleted.

---

## Render Readiness — Final Answer

**Is Studio safe to begin the first Runway experiment?**

**Not via the batch scene pipeline, not on scene_002 in its current state.** Exactly what must be fixed first, in order:

1. **Operator prerequisites (no code):** approve a canonical environment reference for scene_002 and a locked reference for DRE (MOM if she appears). Until then the fail-closed gate will — correctly — block every submission.
2. **P0 (code):** run the generation readiness gate + camera provenance + cost estimate on `SceneProductionPipelineService.generate_scene` (H-6, H-7, H-8).
3. **P0:** fix the `shot_version` stub so shot edits actually invalidate prepared contexts (H-1).
4. **P1:** regenerate the scene_002 board version to replace truncated/severed stored prompts (H-3) — operator action enabled by existing code.
5. **P1:** separate edit-grammar from camera provenance before any camera data is stamped APPROVED (H-2).
6. **P1:** exclude the legacy mock `multi_shot_execution_ledger` from generation fallbacks (H-5).

**Safest first experiment:** a single-shot Previs render (the path that already has the full gate stack) on a shot whose references are approved — after items 1 and 3. The batch Multi Shot experiment should wait for 2 and 4.

The one question the brief poses — *what exactly would Studio send to Runway, shot by shot?* — now has a verified answer: five ordered per-shot requests (1 I2V with the storyboard frame, 4 T2V), gen4.5, 5 s each, ratio 1280:720, the prompts documented above (with their stored defects), no references beyond shot 1's frame, 300 credits estimated — and the submission would be blocked today by the reference gate before any credit is spent.

---
---

# REMEDIATION REPORT — P0 Workstream (2026-09-26)

Same branch, on top of the audit. **Runway credits consumed: 0.** No provider request was submitted, attempted, or possible through any code path exercised by this workstream.

## Fixed

| # | Finding | Remediation | Where |
|---|---------|-------------|-------|
| **H-1** | `create_generation_context` passed `None`, so `shot_version` was always `"absent"` — shot edits could not invalidate prepared contexts. | The context now fingerprints the **real canonical shot record** (prompt, duration, visual plan, camera plan, status, locked, `updated_at`). `resolve_current_shot()` resolves the shot from canonical storage and refuses historical rows (version must equal the blueprint's current version); `require_shot_version=True` fails closed when a shot axis is required but unresolvable; the gate blocks contexts whose shot version cannot be re-verified against current state. Context metadata records `shot_version_source` (`canonical_shot_record`; `no_storyboard_context` for the legacy no-board previs path). | `generation_context_service.py`; wired into `previs_service.py`, `scene_production_pipeline_service.prepare_scene_batch`, and observational metadata in `render.py` |
| **H-2** | Heuristic template camera (framing) and edit-grammar tokens (`match_cut`, `bridge_action`) were stamped `APPROVED` once the board was approved; edit grammar entered the camera dimension. | Provenance now requires **explicit creator provenance**: only `render_contract.structured_parameters["camera_plan"]` (written solely by the camera-preset flow) or `shot_metadata["camera_plan"]` earns `APPROVED`. Without it, template values are **held out of renderable camera entirely** (dimension stays `UNSPECIFIED`) and preserved as *pending AI suggestions* (`pending_ai_camera_suggestions`) for the approval flow — nothing is destroyed. Edit-grammar tokens are stripped from camera; an explicit plan carrying one raises. A single explicit action (`PrevisService.approve_ai_camera`) is the **only** AI_SUGGESTED→APPROVED path: it writes the creator camera plan on a NEW board version (approved boards immutable, history preserved) and stamps `AI_CAMERA_APPROVED_BY_USER:<by>`. The batch path evaluates pending suggestions through the gate so unapproved values **block**; the single-shot previs path keeps them unspecified-and-held. Board-written `shot_planning` is no longer treated as creator-entered camera (that transmutation was the H-2 mechanism). | `generation_context_service.py`, `previs_service.py`, `scene_production_pipeline_service.py`, `render.py` |
| **H-3** | Approved board prompts carried 512-char truncation artifacts ("… stands . e") and severed sentences. | Root cause was the historical silent truncation in canonical board assembly. Canonical assembly now never truncates (verified: prompts over 512 chars are stored byte-accurate; the provider-side 512 budget is applied later, losslessly, at the wire by `validate_provider_text`). Corruption is **detected, not repaired**: `prompt_integrity.detect_prompt_corruption` flags legacy ellipsis artifacts and severed terminal fragments in BOARD prompts; a flagged prompt **fails the generation gate closed** (previs `_storyboard_context` and the batch pre-flight) with regeneration/re-approval named as the only path. Existing canonical prompts are never rewritten by application logic; USER_EDITED prompts are never second-guessed. | `prompt_integrity.py` (new), both gates; assembly contract test updated |
| **H-5** | The mock-era `multi_shot_execution_ledger` (picsum placeholders, synthetic intents) remained a generation fallback. | Excluded from generation: read only to WARN (`LEGACY_MULTI_SHOT_LEDGER_EXCLUDED`); the pipeline falls through to the explicit single-shot fallback. The test that encoded the ledger as a source was rewritten to assert exclusion. | `scene_production_pipeline_service._resolve_ordered_shots` |
| **H-6** | Cost gate absent on the batch path. | The **shared** `GenerationCostGate` (one implementation, both paths — previs `_enforce_cost_limit` now delegates to it) enforces per-generation and daily-budget limits before any provider call, computes the whole-batch estimate (model, per-shot durations, total duration, estimated credits) before anything is dispatched, and never downgrades/shortens/reduces to fit. Daily budget computed from real render history. | `generation_cost_gate.py` (new, shared), both paths |
| **H-7** | Batch-path context was observational-only with UNSPECIFIED camera and absent shot version. | Batch contexts are minted **before** `create_job` with real shot versions and full provenance; the context id and shot version ride into render rows while staying **out of request parameters** (idempotency hashes stay stable). | `scene_production_pipeline_service` |
| **H-8** | The batch path bypassed the readiness gate. | `prepare_scene_batch` runs the **full stack for every shot before any job is created**: canonical scene → approved board (`scene_render_inputs` gates) → current shot list → generation context (real shot version) → readiness gate (scene/shot/storyboard/reference/camera-provenance validation) → prompt integrity → reference requirements (same `resolve_scene_reference_requirements` as submit, with the batch's canonical scene injected) → cost gate → all-or-nothing verdict. One blocked shot blocks the whole batch; no partial generation mode exists. | `scene_production_pipeline_service.py` |

Integrity-relevant fixes beyond the numbered findings: batch render rows now carry per-shot `generation_context_id` + `shot_version`; generation context ids never enter request parameters (verified by test). The audit's "What Should Remain Unchanged" list was honored — storyboard versioning gates, `_validate_shot_renderable`, `validate_generation_payload` semantics, adapter transport, registry/router, and mock-mode gating were not weakened.

## Not Fixed (intentionally deferred)

- **H-4** (generic "Over-the-shoulder…" framing fallback) — content-quality P1, not an integrity gate.
- **H-9** (scene-cast leakage into shot prompts) — P1.
- **P1 regeneration of scene_002's approved board** — an **operator action** enabled by existing code (new version via the current non-truncating builder + explicit re-approval). Application logic must not silently rewrite approved creative data.
- Runway **native** Multi Shot recipe support — explicitly out of scope per the brief.
- The heuristic shot-sequencing template itself (provenance fixed; template content is a separate workstream).

## Architecture Changes

1. **New shared modules** (no duplicates of existing services): `generation_cost_gate.py` (the ONE cost gate), `prompt_integrity.py` (read-only corruption detector), `shot_manifest.py` (deterministic canonical shot manifest builder).
2. **Extended, not replaced:** `generation_context_service` (canonical shot resolution, real shot versioning, provenance rules, explicit approval path); `scene_production_pipeline_service` (`prepare_scene_batch` — the gated pre-flight / dry-run surface); `previs_service` (`approve_ai_camera` — explicit approval action).
3. **One signature extension:** `resolve_scene_reference_requirements(..., scene=None)` — optional injection of the already-resolved canonical scene; omitted = identical behavior to before.
4. **Fallback removal:** the legacy ledger is no longer a shot source (H-5).
5. No canonical-truth architecture modified; no service duplicated; no gate weakened; no historical records deleted.

## Test Evidence

New focused suite: **`studio-backend/tests/test_multishot_integrity_remediation.py` — 42 passed** (Generation context ×5, Camera provenance ×8, Prompt integrity ×8, Batch readiness ×6, Fresh Render ×4, Cost protection ×4, Payload determinism ×3, Reference integrity ×4).

| Suite | Result |
|---|---|
| `tests/test_multishot_integrity_remediation.py` (new) | 42 passed |
| `app/services/test_generation_context_service.py` | 19 passed (1 rewritten for P0-2 creator-plan provenance; 1 new template-provenance test added) |
| `app/services/test_scene_production_pipeline_service.py` | 9 passed (ledger test rewritten to assert H-5 exclusion; plumbing tests use a documented gate-bypass helper — the gates themselves have dedicated coverage) |
| `tests/test_checkpoint_4b_previs_integrity.py` | 22 passed (1 assertion updated: canonical prompts now exceed 512 chars without silent truncation) |
| `tests/test_checkpoint_4a_storyboard_integrity.py` | 12 passed |
| `tests/test_camera_presets.py` | 10 passed |
| `tests/test_scene_direction.py` | 5 passed (1 plumbing test switched to the gate-bypass helper) |
| `app/services/test_reference_validation.py` | 9 passed |
| `app/services/test_reference_library.py` | 14 passed |
| `app/services/test_model_registry_and_router.py` | 12 passed |
| `app/services/test_render_runway_registry.py` + `test_runway_provider_hardening.py` | 12 passed |
| `tests/test_reference_assets_persistence.py` | 4 passed |
| **Frontend typecheck** (`tsc -b`) | **exit 0, no errors** |

Broader sweep (`pytest tests/`): **892 passed, 13 skipped, 6 failed — all 6 pre-existing**, none caused by this workstream:
- 5 failures in `test_local_ltx_provider.py` / `test_minimax_h3_local_provider.py` / `test_render_ltx_i2v_http.py` — untracked local test files from the parallel ComfyUI/local-adapter work in this branch's working tree (they do not exist at HEAD) plus an adapter-count assertion (`13 == 12`) from that same parallel work in `app/adapters/__init__.py` (untouched by this workstream).
- 1 failure in `test_render_submit_completion_hooks.py` — a synthetic job with a nonexistent project id hits the submit-time reference gate's project resolution. Proven not caused by this workstream: HEAD's `render.py` + the new gate modules → pass; the failing frame (`reference_validation` project resolution) is untouched code. This test file does not exist at HEAD either (untracked).

Full focused-run totals: **117 passed** across the remediation + generation-context + batch + previs + storyboard + camera + scene-direction suites; **123 passed** across the reference + registry/router + Runway suites. Skipped tests are pre-existing; no new skips or warnings introduced. Full-repo regression was NOT fully green (6 pre-existing failures above) — reported honestly rather than claimed.

## Dry Run Evidence

`studio-backend/scripts/dry_run_provider_boundary.py` — read-only. It grounds all storage env vars at **copies** of the real data stores (`studio-backend/data/studio.db` + `project_state_store.json`) in a temp dir and runs **only** `prepare_scene_batch`, which never creates a job, never imports a submission adapter, and performs no network I/O. Two full runs, then a fingerprint comparison.

Project `project_5907c60cddbc`, scene `scene_002` (real data; shot list resolved 1→5 from approved version `sbv_dbafa23cf4a1`):

- **Determinism:** run 1 fingerprint `d28ad2a0104f1554` == run 2 fingerprint `d28ad2a0104f1554` — identical request content excluding generation context ids (fresh per run: `genctx_5398bfddcf9b49f0…` vs `genctx_33e9baf539e846bd…`).
- **Readiness: `ready: False` — fail-closed**, with blockers naming exactly the audit's findings:
  - Every shot: `reference gate: Generation blocked: Scene scene_002 for setting scene_002. no approved canonical environment reference is available` (no approved setting reference; DRE has zero locked references — correct per §10).
  - Every shot: `Camera 'framing' is an unapproved AI suggestion ('establishing_shot' / 'medium_shot' / 'close_up' / 'transition_shot' / 'emotional_detail_shot')` — template camera no longer passes as approved (H-2 verified on real data).
- **Batch cost picture (before any provider call):** gen4.5 × 12 cr/s × 5 shots × 5 s = **300 credits estimated**; `selected_model: gen4.5`; `total_duration_seconds: 25`; `model_selection_reason: AUTO: registry-compatible default for the provider`.
- **Per-shot payload** (sanitized; full trace in `studio-backend/reports/multishot_dryrun_payload.json`): 5 ordered shots, each with a real `shot_version` hash (e.g. shot 1 `270336a9063ccf2e`), duration 5 s, reference set (shot 1: storyboard frame `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png` with `reference_version d519ba1892077636`; shots 2–5: none), camera provenance (`framing` AI_SUGGESTED pending approval; `shot_size`/`angle`/`movement`/`lens` UNSPECIFIED), `generation_context_id`, board metadata pinning `sbv_dbafa23cf4a1` / `sbs_77d3ae4fe1e9` … `sbs_ee2d6576f016`, and seed where locked (shot 1: 916483).
- **Runway credits consumed by the dry run: 0** (no provider call exists on this path).

## Remaining Risks

1. **Corrupted stored prompts on scene_002** remain in the approved version; they now **block generation** until the operator regenerates the board version or explicitly repairs and re-approves. Severed-but-punctuated sentences (e.g. "… The.") cannot be proven corrupt mechanically — covered by the operator regeneration path.
2. **Shots 2–5 generic framing** (H-4) still enters prompts via the dialogue-tag heuristic — content-quality P1.
3. **Cast leakage** (H-9) — scene-level cast guard can summon a character a shot doesn't feature — P1.
4. **The template camera values themselves** are unchanged (provenance fixed; heuristic content is a separate matter).
5. **Reference prerequisites are operator actions**: until scene_002 has an approved canonical setting reference and DRE a locked reference, every submission is blocked by the reference gate (correct behavior).
6. **Pre-existing uncommitted parallel work** in the working tree (ComfyUI/local adapters, adapter-registry count, submit-gate behavior on synthetic jobs) accounts for the 6 pre-existing test failures — outside this workstream.
7. The daily budget is an estimate over render history (registry rates × durations); a job with an unpriced model contributes 0 — honest but conservative.

## Render Readiness

**NOT READY FOR RUNWAY EXPERIMENT**

Ready-when conditions (all must hold): (1) operator approves a canonical setting reference for scene_002 and locks DRE (MOM if she appears); (2) operator regenerates the scene_002 board version (replacing corrupted prompts) and re-approves; (3) operator approves the camera framing values they want renderable via the explicit approval action — until then every shot blocks with the AI-suggestion blocker; (4) a fresh dry run then shows `ready: true` with a deterministic fingerprint. Only then consider a controlled first experiment.

---

# GENERATION PREFLIGHT UI (2026-09-26)

Next workstream, built directly on the P0 remediation. **Runway credits consumed: 0.** No provider request was made, attempted, or made possible by any code path in this workstream. No readiness logic was added to React: the UI is an inspection and safety surface over the backend's existing pre-flight.

## Backend (single source of truth)

No gate, service, evaluator, or generation architecture was modified. One **read-only HTTP surface** was added for the already-existing batch pre-flight (`SceneProductionPipelineService.prepare_scene_batch`), which had no API exposure (verified: only the mutating `POST .../pipeline/generate` existed).

- **Endpoint:** `GET /api/f51/studio/projects/{project_id}/scenes/{scene_id}/generation-preflight?provider=` in `app/routes/projects.py`. Loads the project, runs `prepare_scene_batch`, and returns `{project_id, scene_id, ready, blockers, shot_count, entries[], manifest, cost_estimate}` — the backend's own verdict, per-shot validated entries (prompt, duration, camera provenance, references, shot/reference versions, blockers), deterministic shot manifest, and batch cost estimate. No job creation, no provider contact, no credit consumption, no mutation of canonical creative state (covered by tests). Unknown project/scene → honest 404. `backend files changed: app/routes/projects.py` only (additive).

## UI files changed

- `src/lib/studioApi.ts` — `getGenerationPreflight()` + typed response interfaces (additive).
- `src/components/GenerationReadinessPanel.tsx` — the "Generation Readiness" panel: explicit `READY` / `BLOCKED` / `CHECKING` status (no scores/percentages), the backend's actual aggregate blockers shown verbatim and categorized (references / camera / prompt integrity / cost / state currency), per-shot blocker rows, multi-shot summary ("N shots · X ready · Y blocked — the scene cannot render until all required shots pass preflight"), the no-credits notice while blocked, "Ready to Generate" plan from backend data (model + backend's selection reason verbatim, shot count, total footage, estimated credits, generation mode **Studio Multi Shot**, per-shot provider execution + Studio local assembly), and the expandable "Review Generation Plan" manifest (per shot: full prompt — never truncated in expanded view, "Prompt unavailable" when absent; camera with provenance where `AI_SUGGESTED` renders as "AI suggestion awaiting approval — not renderable"; duration; references + reference version; shot version; storyboard shot). The Generate button is disabled unless the backend's latest result is `ready`; clicking it runs a **fresh backend preflight** and only proceeds from that fresh verdict — a scene change between check and generate refreshes the blockers and generates nothing.
- `src/components/useGenerationPreflightGuard.ts` — single-shot hook over the same endpoint: fetches the backend preflight, reports the active shot's blockers, invalidates the verdict when scene/project/provider changes (with re-check), and `authorizeFinal()` performs the final preflight immediately before the render call, refusing with the backend's blockers when not authorized.
- `src/pages/PrevisRoom.tsx` — panel mounted at both spend surfaces: whole-scene pipeline card (panel's gated Generate button replaces the old ungated one; audio-mode validation ANDed as a non-readiness gate) and the single-shot "Render take" card (panel in inspection mode; Render take disabled while the backend reports blocked/error/stale, and `handleInitializeRender` runs the guard's final preflight before spending; a blocked final check shows the backend's reasons and generates nothing). Existing **Fresh Render** toggle preserved; storyboard/scene mutations bump a revision that invalidates and re-runs the preflight (stale-state protection). No new intelligence, scoring, auto-correction, or reference management — references display the backend's actual categories.

## Preflight data displayed

Verdict (`ready`), aggregate blockers, per-shot blockers/entries, manifest (`selected_model`, `model_selection_reason`, per-shot durations, `total_duration_seconds`, `estimated_total_credits`, `readiness_status`, `manifest_fingerprint`, scene/storyboard/shot versions, camera provenance, references, prompts), batch cost estimate, mode labels. Every value rendered comes from this response; the UI invents nothing and repairs nothing.

## Tests

- **Backend (new):** `tests/test_generation_preflight_route.py` — 5 passed (blocked verdict passthrough with real gates on a fresh approved board; whole-project read-only equality; no render jobs created; unknown project 404; unknown scene 404; ready-passthrough via stubbed `prepare_scene_batch`).
- **Frontend (new):** `src/components/GenerationReadinessPanel.test.tsx` — 21 passed, covering the 18 required behaviors: blocked display, ready display, shot-specific blockers, missing references, camera approval blocker, prompt-integrity blocker, cost blocker, model selection display, estimated cost display, manifest expansion, generate disabled while blocked, generate enabled when ready, final preflight before generation (fresh check blocked → no generation, blockers refreshed), stale preflight invalidation (old verdict cannot authorize new scene), loading state ("Checking generation readiness..."), backend error state (generation stays disabled), multi-shot shot count summary, individual shot details — plus Studio-Multi-Shot labeling, AI-suggested camera badge, and verbatim/unavailable prompt display.
- No existing test weakened. Full sweeps below.

## Verification

| Check | Result |
|---|---|
| Frontend typecheck (`tsc -b`) | exit 0, no errors |
| Frontend full suite (`vitest run`) | **804 passed** (100 files), 0 failed, 0 skipped |
| Backend focused suites (new route + remediation + generation context + batch + previs + storyboard + references + camera + scene-direction + registry/router) | **178 passed** |
| Backend broader sweep (`pytest tests/`) | **897 passed, 13 skipped, 6 failed — all 6 pre-existing** (same untracked local LTX/MiniMax provider tests, adapter-count assertion, and submit-hook synthetic-job test documented in the remediation report; none caused by this workstream) |
| Live endpoint on real data | `HTTP 200`; manifest fingerprint `d28ad2a0104f1554` — **byte-identical to the audit dry run across processes/environments** |

## Manual UI verification (real scene_002, project `project_5907c60cddbc` — NOT rendered)

The development stack was brought up (`vite` on 127.0.0.1:5001 proxying to `uvicorn` on 8010, restarted via the project's own supervisor endpoint after confirming no active render jobs existed), the Previs Room opened for scene_002, and both panels inspected in the live DOM:

- Whole-scene panel: **BLOCKED**; "5 shots · 0 ready · 5 blocked — the scene cannot render until all required shots pass preflight"; every shot listed with its actual backend reasons — `Camera 'framing' is an unapproved AI suggestion ('establishing_shot'/'medium_shot'/'close_up'/'transition_shot'/'emotional_detail_shot')` and `reference gate: … no approved canonical environment reference is available` — exactly matching the P0 dry-run blockers; "No provider credits can be spent while generation is blocked." shown; **Generate disabled**.
- Single-shot panel: same backend blockers for the active shot; **Render take disabled** while blocked.
- Manifest expanded: shot 1 shows the full 602-character prompt **verbatim including the known legacy truncation artifact** ("… stands . e") — displayed honestly, not repaired; framing `establishing shot` with the **"AI suggestion awaiting approval — not renderable"** badge; shot version `270336a9063ccf2e`; storyboard version pinned.
- Read-only evidence: render jobs for the project unchanged before/after verification (3 historical failed rows, 0 created); canonical project state untouched.
- Screenshot capture was not available in this environment (preview compositor produced no frames); the verification evidence above is direct DOM state read from the running UI backed by the live endpoint payload.

**Runway credits consumed by this workstream: 0.** No provider request exists on the preflight path (it never imports or calls a submission adapter), and no Generate/Render action was triggered during verification.
