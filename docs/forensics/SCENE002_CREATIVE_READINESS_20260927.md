# SCENE_002 CREATIVE READINESS — 2026-09-27

Read-only creative-readiness pass following the verified production recovery
(`docs/forensics/SCENE002_PRODUCTION_RECOVERY_20260927.md`, verdict **RECOVERY VERIFIED**).

**Generation readiness verdict: `NOT READY: CREATOR DECISIONS REQUIRED`**

**Purpose:** transition from forensic recovery back to the normal creative workflow —
prepare scene_002 for creator approval and return it to the image-generation workflow.
Nothing was modified, approved, or generated. This report stops at the decision surface.

## 1. Verification method (read-only)

- The live production database (`studio-backend/data/studio.db`, inode 271891263 — the same
  file identity the recovery report certified) was **never opened for write**. All SQL in this
  pass ran against a byte copy at `/tmp/scene002_readiness/` (SHA-256 `cb99f8c9bfbe0a52…`,
  verified byte-identical to the live base file before use; `PRAGMA integrity_check` = `ok`,
  WAL continuation `6c52f096a79283dc…` copied alongside).
- Post-pass integrity: live base file and WAL re-hashed **unchanged**
  (`cb99f8c9…` / `6c52f096…`); `data/project_state_store.json` unchanged (`3c7e716a…`).
  Only the volatile SQLite `-shm` reader file differed from the recovery-time hash — normal
  concurrent-reader housekeeping, no database content change.
- The running backend (uvicorn `main:app`, pid 30468, port 8010, **not restarted**, per the
  recovery report's determination) was exercised through exactly two read-only surfaces:
  the project GET and the generation-preflight endpoint. The preflight route is documented
  and implemented as never creating a job, never touching a provider, and never consuming
  credits (`app/routes/projects.py:713`, `get_generation_preflight`).

---

## Recovered State

Everything below was confirmed both from the DB copy and through the live HTTP API.

| Item | Value | Status |
|---|---|---|
| Project | `project_5907c60cddbc` — "I was reborn" (owner `user-f8e8be9141fa8b64`) | ✔ matches recovery report |
| Scene | `scene_002` ("EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE") | ✔ |
| Blueprint | `sbp_project_5907c60cddbc_scene_002_3400a20b` — `status=approved`, `current_version_id = approved_version_id = sbv_3b88a1e0ef95`, `locked=0` | ✔ |
| v1 | `sbv_dbafa23cf4a1` — `approved` by `creator` at 2026-09-06T07:44:28.120443+00:00 | ✔ preserved |
| **v2** | **`sbv_3b88a1e0ef95` — `approved` by `creator` at 2026-09-26T20:17:28.940362+00:00** | ✔ **exact timestamp preserved** |
| v2 shots | **Five, all `status=approved`, none `locked`:** `sbs_a7648698ad00` (1), `sbs_a8481a439ea5` (2), `sbs_be2cce8fab93` (3), `sbs_51d1500d227c` (4), `sbs_0046fb5192f0` (5) | ✔ |
| Prompts | `render_contract.provider_neutral_prompt` per shot: **3,200 / 3,012 / 2,994 / 3,003 / 3,074 chars** (v2 contract JSON byte lengths 4,194 / 4,006 / 3,977 / 3,981 / 4,074 — identical to the merge manifest) | ✔ unchanged |
| Seed 916483 | Exactly one occurrence: previs row `previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1` (status `complete`, job `storyboard_scene_002_shot_001_dashscope`), image `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png` (2,644,340 bytes, exists on disk). `previs_seed=916483`, `seed_locked=0`, `approved=0` | ✔ preserved |
| Second previs row | `…_job-20260906034509-132bb802-scene_002_shot_001` — `failed` historical v1 attempt (OpenRouter 16 s-duration error); its metadata pins v1 (`sbv_dbafa23cf4a1`) and v1 shot `sbs_77d3ae4fe1e9`; no image | ✔ |
| Scene memory | `approved_shots` = the five v2 shot ids in order, all `sbv_3b88a1e0ef95` | ✔ |
| Characters | 6 recovered (DRE, ELENA, JAY, MAYA, MOM, SIMONE) with locked appearance approvals in continuity documents | ✔ |
| Character locks | 7 recovered (MAYA ×2 locked, MOM ×2 locked, DRE 1 provisional + superseded history) | ✔ |
| script_text | SHA-256[:16] `c66c7e8e573b00ec`, length 16,285; `projects.updated_at` 2026-09-20T19:36:10.670388+00:00 | ✔ untouched |
| Live API | `GET /api/f51/studio/projects/project_5907c60cddbc/scenes/scene_002/storyboard-blueprint` serves v2 with 5 shots, approved, correct timestamps | ✔ |
| Live preflight | `GET …/scenes/scene_002/generation-preflight` → `ready: false` with exactly the two expected blocker families (camera ×5, canonical setting reference ×5) | ✔ blockers intact |

**Seeds on the generation paths (creator-relevant):** the v2 board contracts carry
`seed=None, seed_locked=false`. The only scene_002 seeds in the database are the previs row
(916483, unlocked, scoped to previs) and the legacy `shots` row `scene_002_shot_001` → seed
`1395559473`, `seed_locked=0`. See *Stale State Risk* — the legacy row is the one the video
render path will reuse.

---

## Five Camera Decisions

Live preflight wording, verbatim, per shot:
`Camera 'framing' is an unapproved AI suggestion ('…'). Approve or remove it before rendering.`

### Per-shot camera state (extracted from the live DB, v2 shots)

| # | Shot ID | Board shot | Purpose (`shot_planning.purpose`) | Existing framing (visual_plan) | Camera angle | Camera movement | Lens | Camera-plan provenance |
|---|---|---|---|---|---|---|---|---|
| 1 | `scene_002_shot_001` | `sbs_a7648698ad00` | `establishing_shot` | "Wide establishing shot. Camera far back. Full environment visible." | — (UNSPECIFIED) | — (empty; v1-era `match_cut` edit-grammar token is gone from v2) | — (UNSPECIFIED) | none |
| 2 | `scene_002_shot_002` | `sbs_a8481a439ea5` | `medium_shot` | "Medium shot. Characters from waist up. Action and dialogue beginning." | — | — | — | none |
| 3 | `scene_002_shot_003` | `sbs_be2cce8fab93` | `close_up` | "Medium close-up. Character faces and upper body. Emotional beats." | — | — | — | none |
| 4 | `scene_002_shot_004` | `sbs_51d1500d227c` | `transition_shot` | "Dynamic medium shot showing the story transition in motion." | — | — | — | none |
| 5 | `scene_002_shot_005` | `sbs_0046fb5192f0` | `emotional_detail_shot` | "Close-up detail shot. Eyes, hands, specific objects. Intimate beat." | — | — | — | none |

All five render contracts: `duration 5 s`, `aspect 16:9` (ratio `1280:720`), structured
parameters contain only `duration`, `ratio`, `shot_planning` — **no `camera_plan` key**;
shot `metadata` = `{}` on all five.

### Why the current state is AI_SUGGESTED

The provenance rules are explicit (`generation_context_service.py`, P0-2):

- Only a **creator camera plan** earns `APPROVED` — a plan written by an explicit creator
  action into `render_contract.structured_parameters["camera_plan"]` (the camera-preset flow)
  or `shot.metadata["camera_plan"]`. **None of the five v2 shots has either** (verified empty).
- The framings above are **template output** (`shot_prompt_builder.SHOT_FRAMING_BY_POSITION`
  + staging), and "heuristic board content is NOT creator camera approval." Template values
  without the approval record are held out of renderable camera entirely and surfaced as
  *pending AI suggestions* (`pending_ai_camera_suggestions`).
- The batch preflight deliberately evaluates pending suggestions through the gate as
  `AI_SUGGESTED` so they **block** — the recovery report confirms both blockers were
  preserved and required. Edit-grammar cut tokens are stripped from the camera dimension
  and can never be laundered into camera data.

### What creator approval would actually lock

`PrevisService.approve_ai_camera` (`previs_service.py:606`) — the ONLY `AI_SUGGESTED →
renderable` path — copies **only the non-empty pending AI suggestion values** (here: the
five framing strings) into `structured_parameters["camera_plan"]` on a **new draft board
version**, stamped `AI_CAMERA_APPROVED_BY_USER:<by>` via the change reason. Approval locks
exactly what exists today: framing only. It does **not** invent shot_size, angle, movement,
or lens — those stay UNSPECIFIED (empty) and the derived camera context is identical to
today's minus the framing blocker. An alternative creator path (the camera-preset flow,
§3) locks a fuller authored plan (camera movement, framing, lens, focal length, aperture)
and additionally appends a `[CREATOR CAMERA PLAN]` note to the stored prompt.

**Missing information per shot (creator decision space):** shot_size, camera angle,
camera movement, lens/focal length/aperture — all UNSPECIFIED. Approving as-is leaves them
decided-by-omission (acceptable to the gate, but worth an explicit creator choice, e.g. via
a camera preset which would also author a movement value).

**No approval was executed; no AI suggestion was converted into a canonical camera plan.**

---

## Available Setting References

**Gate requirement (verified in code, `reference_validation.py:180–186`):** the scene's
setting reference must be a `reference_assets` row with
`target_type='setting'`, `target_id='scene_002'`, `canonical=1`,
`approval_state='approved'`, `kind='environment'`, non-empty `image_url`.
**Current rows matching: 0** → blocker `canonical_setting_reference_missing` (live preflight:
"Generation blocked: Scene scene_002 for setting scene_002. no approved canonical environment
reference is available"). The setting id resolves to `scene_002` itself (scene has no
explicit `setting_id`; fallback per `_setting_id`).

Candidate inventory (all 11 `reference_assets` rows for the project; file existence checked
against the backend's actual mount roots):

| Reference | File / path | Target | Kind | Approval | Canonical | File exists | Visually usable | Provenance | Can enter canonical setting workflow? |
|---|---|---|---|---|---|---|---|---|---|
| `ref_env_6b726885ed67ae4d` | `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png` (2.6 MB, serves via `/previs-assets` mount) | None / None | environment | approved | 0 | **YES** | **YES** | synced creator-approved visual (legacy registry row; `source_kind=confirmed`) | **Closest candidate — see below** |
| `ref_vt_environment` | `/media/vt_environment.png` | None / None | environment | approved | 0 | **NO** (no `/media` mount exists; file not found anywhere) | no | visual-training stub | no — dead URL; would fail fail-closed reference checks |
| `ref_vt_character_face` | `/media/vt_character_face.png` | None / None | character_face | approved | 0 | **NO** | no | visual-training stub | no (character-scope anyway) |
| `ref_vt_character_full` | `/media/vt_character_full.png` | None / None | character_full | approved | 0 | **NO** | no | visual-training stub | no (character-scope anyway) |
| `ref_look_005f…` … `ref_look_e632…` (6 rows) | `/outputs/references/character-looks/54f20532…/…` (directories exist; hashed leaf filenames truncated in registry URLs — content match unverified) | None / None | character_face | approved | 0 | partial (dirs exist; exact files unverified) | unknown | character look approvals (demo-era sync) | no — character-scope, not setting |
| `ref_upl_a73e6281957642c58940a942` | `/outputs/reference-assets/uploads/518740b9…/44081ca4…3.jpg` (35,904 bytes, exists) | **setting / scene_001** | environment | **candidate** | 0 | **YES** | yes (file serves) | creator upload, Sept 26 | **no — wrong scene (scene_001) and candidate**; out of scope by instruction |

Key structural fact: **the reference-library approval route can only flip
`approval_state → approved` on non-canonical rows** (`approve_supporting` returns canonical
rows untouched), and the upload route only creates **candidates** (`canonical=False`).
There is **no implemented endpoint or service that sets `canonical=1`** — the only writer
of canonical rows is `sync_creator_references`, which derives them from *other* explicit
creator approvals (locked character looks; approved previs/blueprint stills). This is a
deliberate fail-closed design: a canonical setting anchor for scene_002 must come from one
of the §"Scene 002 Previs Material" pathways below — a creator decision, then a
deterministic sync — not from a manual DB flag.

**No reference was approved, no `canonical=1` was set, and no reference was created.**

---

## Scene 002 Previs Material

The recovered estate contains exactly one real visual asset for scene_002: the seed-916483
previs image (`…scene_002_shot_001_storyboard_qwen.png`, July 27 render by the DashScope
storyboard provider, prompt_used = the 512-char v1-era establishing prompt — pre-dates v2).
Assessment of what it **can** serve as, per the current code:

- **A. Scene reference only — YES (its current, legitimate role).** It is already wired as
  shot 1's `reference_assets` and surfaces in the preflight entry (`references: [/previs-assets/…]`,
  `reference_version d519ba1892077636`). No action needed; it rides along as shot-level context.
- **B. Setting reference candidate — POSSIBLE, requires creator action + upload flow.** The
  registry upload route accepts only file uploads (`register_upload` → candidate row). To
  make the previs frame a *candidate* setting reference the creator would re-upload that
  PNG through the Scene 002 reference library UI. There is no implemented
  "promote existing URL to candidate" endpoint. It is visually on-target (the recovered
  establishing frame of the frozen-L-train Chicago street) but was rendered from the **v1-era
  512-char prompt**, so the creator should judge whether it still represents the v2 look.
- **C. Canonical setting reference — POSSIBLE via the intended pathway, NOT directly.** No
  endpoint sets canonical on an arbitrary row. The supported pathway: creator **approves the
  previs image in the Previs UI** (`POST /previs/records/{id}/approve`) — approval is
  per-shot-keyed and would supersede nothing today (no other approved scene_002 previs) —
  and the next `sync_creator_references` pass (triggered on any reference-library listing)
  upserts the deterministic row `ref_env_project_5907c60cddbc_scene_002` as
  `target_type=setting / target_id=scene_002 / kind=environment / canonical=1 /
  source_kind=confirmed`. The previs row's `storyboard_shot_id` is NULL but its
  `shot_id=scene_002_shot_001` satisfies the fallback key; status is `complete` with a real
  image, so it is eligible. Alternatively, regenerating the shot-1 storyboard frame through
  the v2 board (with creator camera plan) produces a v2-prompt frame whose approval lands
  canonically the same way.
- **D. Neither — not chosen.** Not applicable: A is already true today.

Constraint inherited from the recovery report: **the previs image is recovered state and was
not modified by this pass.** All pathways above are creator actions to be taken in the
decision pass; none was executed. **Nothing was promoted.**

---

## Runway Image Path

- **Provider selection:** config-gated through the provider-agnostic seam
  `submit_image_render` (`app/services/providers/image_provider.py`); registry
  `{local_image, nvidia, runway}`; used **only** when the operator sets
  `image_provider_name="runway"` (with `image_provider_enabled=true` and key env
  `RUNWAY_API_KEY` / `RUNWAYML_API_SECRET`; `runway_image_api_base_url` default
  `https://api.dev.runwayml.com`, gen4_image family).
- **Wired surface:** the **ScriptParser image-asset pipeline**
  (`script_parser.build_image_render_assets`, ~9300) — a bulk per-scene asset builder that
  consumes the *legacy* `multi_shot_execution_ledger` prompt packs, runs ComfyUI first
  (only when `comfyui_enabled=true`), then submits to the hosted provider. **Not** the
  storyboard/scene pipeline: `storyboard_blueprint_service` image generation is
  Qwen/Pollinations only; the scene batch / previs path is the *video* provider path
  (`render_service` → runway gen4.5/gen4_turbo, which the cost gate prices at 60 credits × 5 s).
- **Reference support:** runway accepts reference images through the capability-contracted
  reference-conditioning path (multi-reference or single start-frame anchor;
  `_reference_debug` reports support). The image seam itself passes `base_prompt` +
  `meta` (aspect, seed) only — references ride the *video* payload contracts, not the
  `build_image_render_payload` image payload.
- **Credits:** any Runway image generation costs credits; none were spent (nothing called).

## FLUX.2 Image Path

- **Provider selection:** same seam, `image_provider_name="nvidia"` — FLUX.2 Klein 4B
  (`flux.2-klein-4b`) via NVIDIA's OpenAI-compatible image endpoint
  (`NVIDIA_IMAGE_API_BASE_URL`, default `https://ai.api.nvidia.com`, path
  `/v1/genai/black-forest-labs/flux.2-klein-4b`; key `NVIDIA_API_KEY`).
- **Wired surface:** identical seam and identical caller (ScriptParser image assets) as
  runway-image — the seam is model-agnostic by construction: `submit_image_render` dispatches
  on the configured name, each provider module owns its request/response, and storyboard/
  reference/scene services never see a provider-specific field. The dispatcher takes the
  canonical `base_prompt` from the payload top level (nested `prompt_pack.base_prompt` kept
  only as a legacy fallback; no prompt is ever fabricated), plus `aspect_ratio` and `seed`
  from `meta`.
- **Reference support:** the FLUX.2/NVIDIA image module consumes prompt/aspect/seed only —
  **no uploaded reference images** on this image path (reference conditioning exists on the
  video contracts and in the Runway video models' `promptImage`).

### Which accepts what (summary answers)

1. **Runway image surface:** ScriptParser `build_image_render_assets` → `submit_image_render(provider="runway")` (gen4_image).
2. **FLUX.2 surface:** same seam with `image_provider_name="nvidia"` (`flux.2-klein-4b`).
3. **Accepts scene_002 references:** the *scene pipeline* (video path) validates and carries
   scene_002's resolved canonical references (character + setting). The hosted *image* seam
   currently carries **no reference set at all** — neither provider's image path accepts
   scene_002 references today.
4. **Uploaded reference assets:** consumed by the scene/video generation path via
   `ConsistencyPayload` / `validate_generation_payload` (approved-only, target-ownership
   enforced, ≤9 images). The FLUX.2 image module: no. Runway gen4_image: prompt/aspect/seed only.
5. **Canonical character references:** resolved by `resolve_scene_reference_requirements`
   from canonical+approved `character_face/character_full` rows **and** locked appearance
   approvals (face/body URLs) **and** approved character reference locks — then enforced
   payload-side (ownership mismatch / unapproved / missing canonical all fail closed).
   MAYA and MOM currently resolve this way (locked looks + approved locks); DRE is
   `provisional` and contributes nothing.
6. **Setting references:** the same resolver requires the §Setting gate row; the payload
   validator additionally requires the final provider payload to actually contain the
   approved canonical environment URL (or an `environment_continuity_context` selection) —
   a stale/foreign setting URL fails `payload_canonical_reference_missing` or
   `stale_reference_payload`.
7. **Prompts constructed:** batch path = the **board's stored `provider_neutral_prompt`**
   (creator-approved v2 content, 2,994–3,200 chars) + a `[SHOT POSITION]` suffix
   (`_shot_prompt`); storyboards regenerate prompts via `build_shot_aware_prompt` (no
   truncation of canonical content); `prompt_budget_service` applies the provider ceiling
   fail-closed at job creation (512 default; 4,400 for the LTX-2 Gemma encoder) — it never
   edits canonical text.
8. **Recovered scene_002 prompt used directly:** **YES** on the batch path — the live
   preflight prompt for each shot begins with the recovered v2 board prompt content and the
   gate pins it via `prompt_source="BOARD"` + scene/shot/board/reference/camera version
   fingerprints. **NO** on the hosted image seam — `build_image_render_assets` uses the
   legacy ledger `prompt_pack` (402-char summarized prompt), not the recovered board prompt.
9. **Stale-state leakage:** see below.

## Reference Handoff

- **Scene/Video path (the wired, gated path):** creator approvals → `reference_assets` /
  appearance approvals / character locks → `resolve_scene_reference_requirements` →
  `ConsistencyPayload.refs` → `validate_generation_payload` immediately before provider
  submission (approval state, target ownership, ≤9, canonical-presence, staleness — all
  fail closed). Local file existence for referenced URLs is checked before submission
  (`_missing_local_reference_assets`).
- **Hosted image seam:** no reference handoff exists (see #3/#4). If the creator's intent is
  "Runway/FLUX.2 images guided by approved references," that is a **gap**, not a silent risk.

## Prompt Handoff

- Board prompt (canonical, approved, versioned) → preflight entry prompt → batch job prompt
  (`prompts_by_shot` — the validated string is reused verbatim, "never re-derived ad hoc")
  → provider payload. Version fingerprints invalidate the whole chain on any change.
- Hosted image seam: ledger prompt pack only — a **different, older prompt source**.

## Stale State Risk

**Multishot integrity (previously fixed, verified still enforced):** the batch is
all-or-nothing; one blocked shot blocks the batch; every shot's context carries real
scene/shot/board/reference/camera version fingerprints and the same canonical record
resolves at submit time — a change between check and generate re-blocks. Mock-era ledger
data is explicitly excluded as a generation source (H-5) and only warns.

Silent-reuse audit against the five legacy categories:

| Legacy artifact | Can it silently reach a scene_002 generation request? | Mechanism |
|---|---|---|
| **Old scene prompts** (v1 512-char era, mock ledger packs) | **No** on the batch path | Board prompt is read from the pinned v2 shots; `_validate_shot_renderable` + `scene_render_inputs` reject non-approved/mismatched versions; ledger is warn-only. **Yes** on the hosted *image* seam (#8) — that surface reads legacy prompt packs by design; do not treat its output as scene_002 board output. |
| **Old camera selections** (v1 `match_cut` edit grammar, template framings) | **No** | v2 visual plans carry no edit-grammar movement; edit-grammar tokens are stripped/rejected anywhere they surface; only a creator camera plan earns APPROVED; unapproved suggestions block. |
| **Old scene references** | **No** | Reference version fingerprint + `stale_reference_payload` ownership check fail closed; previs-row references ride shot 1's context but the *generation-blocking* reference set is the resolved canonical one. |
| **Old provider settings** | **No** | Provider selection is config-gated and read at submit time (`get_render_provider_config`); model overrides are validated against the registry per provider (e.g. runway allows only registered ids); unknown providers fail. Nothing persisted in the recovered rows selects a provider. |
| **Old seeds** | **Partial — one specific path** | The v2 contracts carry no seeds, so nothing stale is *embedded*. But `RenderService.submit_job` reuses the **legacy `shots` row seed 1395559473** (`seed_locked=0`) for any scene_002 shot that submits without an explicit seed (log line `SEED_REUSED`). That row predates v2. This is deterministic reuse, not silent corruption — and the previs seed 916483 cannot leak (different table, previs-scoped) — but the creator should explicitly decide seeds for the new renders. |

No stale state can silently pass the gates today; the two residual couplings are the image
seam's legacy prompt source and the legacy seed row — both enumerated as creator decisions.

---

## Creator Decisions Required

1. **Camera, per shot (5 decisions).** Where: Previs Room board — the camera-preset picker
   (`CameraPresetPicker` in `PrevisRoom.tsx`, which reaches `updateShotPlanningDetail`) plus
   **Generate Storyboard Frame** (`POST /api/f51/studio/projects/{p}/scenes/{s}/storyboard`
   with a `camera_plan` body → persists the creator camera plan + new draft version), or the
   gate-sanctioned `PrevisService.approve_ai_camera` action (approve the framing as-is; no
   HTTP route exists for it yet — see UI note). Each decision creates a **new draft version**
   (approved boards are immutable); **the creator must then re-approve the board version**
   (continuity review + `POST /storyboard-blueprints/{id}/versions/{vid}/approve`) to return
   the pipeline to the approved chain. `scene_render_inputs` hard-fails while
   `current_version_id != approved_version_id` — nothing can render from a draft.
2. **Canonical setting reference for scene_002 (1 decision).** Where: Previs Room reference
   panel — either (a) approve the recovered seed-916483 previs frame in the Previs UI and
   let the next sync mint the canonical environment row, or (b) upload a fresh environment
   still via the reference-library upload (candidate) — but note (b) alone cannot reach
   `canonical=1` with today's endpoints; pathway (a), or a future explicit
   canonical-selection action, is the supported route. The creator should also confirm the
   previs frame (v1-prompt era) still represents the intended v2 look.
3. **Seeds (per shot, optional but recommended).** Explicitly set or lock seeds for the new
   renders; otherwise the legacy seed 1395559473 (unlocked) is reused per shot on the video path.
4. **script_text conflict (CONFLICT ①).** Still `BLOCKED_PENDING_CREATOR_AUTHORIZATION`
   from the recovery — unchanged by this pass, listed for completeness.

**Minimum UI note (no change implemented):** the existing Previs Room already presents the
five camera decisions (per-shot picker + GenerationReadinessPanel showing each AI_SUGGESTED
framing as "AI suggestion awaiting approval — not renderable", disabled Generate until the
fresh preflight passes) and the reference surface for settings exists for
upload/approve-as-supporting. Two gaps are **not** exposed in the UI today: (a) a one-click
"approve AI framing" action — `approve_ai_camera` is service-level only (no HTTP route), so
the strictly necessary surface for the as-is-approval variant would be a small route + one
button; the camera-preset path is already fully wired and sufficient if the creator authors
plans instead of approving suggestions; (b) an explicit "make canonical" control for setting
references (the supported path runs through previs approval + sync, which is UI-reachable).
No UI change was made in this pass.

---

## Generation Readiness

Live aggregate preflight (`generation-preflight`, fresh, this session):
`ready: false` — 5 shots, 10 blockers (5 × unapproved AI-suggested camera framing,
5 × `canonical_setting_reference_missing`). Cost gate prices the batch at
60 credits/shot (runway gen4.5, 5 s × 5) once unblocked.

**`NOT READY: CREATOR DECISIONS REQUIRED`**

Blocking decisions, exactly as the recovery report prescribed:
1. Five camera approvals (or authored camera plans) on v2 shots 1–5 — *then* board re-approval.
2. One approved canonical setting reference (`setting/scene_002`, environment, canonical) —
   the recovered previs frame is the ready-made candidate pending the creator's choice.
3. (Recommended) explicit seed decisions; (out of scope) script_text conflict CONFLICT ①.

The pipeline is otherwise fully wired: the moment those creator decisions land, the same
gated path that reports the blockers today will pass the batch through to the provider
boundary, with the recovered prompts, current references, and chosen seeds intact.

---

## Final Safety Record

| Item | Value |
|---|---|
| Database modified | **NO** — live DB opened read-only via byte copy; base file + WAL re-hashed unchanged after the pass (`cb99f8c9…`, `6c52f096…`); state store unchanged (`3c7e716a…`) |
| Canonical scene state modified | **NO** |
| Camera approvals created | **NO** — no version created, no `camera_plan` written |
| Setting reference approved | **NO** — no `approval_state` change, no `canonical=1` anywhere |
| script_text modified | **NO** — sha16 `c66c7e8e573b00ec`, len 16,285, `projects.updated_at` 2026-09-20T19:36:10.670388+00:00 |
| Runway called | **NO** |
| FLUX.2 called | **NO** (no NVIDIA/FLUX endpoint touched) |
| Credits spent | **0** |
| Images or video generated | **NO** |
| Backend restarted | **NO** (pid 30468 untouched; only read-only GET endpoints exercised) |
| scene_001 investigated | **NO** (its single reference row is shown only as part of the complete project reference inventory, for exclusion) |

**STOP.** The next step is the actual creator decision pass (five camera decisions, one
canonical setting reference), followed by Runway and FLUX.2 image generation. Nothing here
generates, approves, or promotes anything.
