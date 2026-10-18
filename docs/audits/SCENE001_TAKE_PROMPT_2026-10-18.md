# Scene_001 Shot 1 — What exact text would a video take send to Runway?

Date: 2026-10-18 · Backend: release-hardening-2026-10-17 (d5e7fc90) · Project `project_5907c60cddbc`, `scene_001`
Method: read-only. `studio-backend/data/studio.db` opened `mode=ro`; no code edits, no DB writes, no provider calls, no submissions. This report file is the only change.

## TL;DR — "Runway would receive: …"

**Runway would receive: the board's frozen `provider_neutral_prompt` — byte-for-byte — with DRE, ELENA and JAY locked-appearance blocks in it, and zero words from the "Direct the action" box.**

The "Direct the action" box on the Render step **cannot reach any Runway video path**. The Render-step "Render take" button submits to the legacy previs (simulated, no cost) endpoint, which rejects Runway-family providers with 422. The actual Runway video path (canonical scene pipeline) accepts **no per-take text field at all** — its request payload (`GenerateScenePipelinePayload`) has no prompt/direction member, and every downstream layer derives the video `promptText` exclusively from the frozen board contract. Editing the box changes nothing about a video take; the frozen contract still carries the old text.

---

## 1. What happens when the owner clicks "Render take" (Render step, shot 1)

### 1a. Frontend handler — `studio-app/src/pages/PrevisRoom.tsx`

- Button: `PrevisRoom.tsx:3159-3172` (`data-testid="render-take-button"`, label "Render take"), wired to `handleInitializeRender` (defined ~`:1613`).
- Prefill: `useEffect` at `:1509-1519` copies the board text into the box on shot arrival:
  `setPromptText(activeBlueprintShot.render_contract.provider_neutral_prompt)` — this is why the box shows the DRE/ELENA/JAY entries and long staging sentences.
- On click, the handler builds (`:1616-1629`):
  - `storyboardPrompt` = board's `provider_neutral_prompt` (trimmed)
  - `renderPrompt` = `promptText.trim() || storyboardPrompt`
  - **Override gate:** `renderSettings.prompt` is sent **only if** the box was actually edited — `promptDirtyRef.current && promptText.trim() && promptText.trim() !== storyboardPrompt`. Untouched/prefilled-only text is deliberately **omitted** so the backend renders from the planned board prompt.
- The call is `generatePrevisScene(...)` (`studioApi.ts:3711`), i.e.:
  `POST /api/f51/studio/projects/{project_id}/previs/generate-scene/{scene_id}?shot_number=1&take_number=N&storyboard_shot_id=<sbs_id>&allow_approved_revision=true&provider=simulated`
  with JSON body `renderSettings`: `{prompt? (override only), duration_seconds, resolution, seed, shot_planning?, visual_model_id?, model?, fresh_render?}` (`PrevisRenderSettings`, `studio-backend/app/models/previs_render.py:13` — `prompt: str | None = None`).
- **Provider is forced to `simulated`.** `resolveLegacyPrevisProvider(renderProvider)` (`studio-app/src/lib/legacyPrevisProvider.ts:12`) maps any Runway-family picker value to `simulated`; the UI even notes "Simulated previs: instant, no cost". So this button is a **previs-image take**, never a Runway video take.

### 1b. API route + backend (previs take — NOT video)

- Route: `POST /projects/{project_id}/previs/generate-scene/{scene_id}` → `generate_scene_previs` (`studio-backend/app/routes/previs_routes.py:128`). Forwards `render_settings` body to `previs_service.generate_scene`.
- Runway is refused twice, before any job exists: route-level `_validate_legacy_previs_provider` (`previs_routes.py:110-119`, 422) and service-level (`previs_service.py:206-247`, 422 — "Runway video generation requires the canonical scene pipeline's READY frozen contract; the standalone Previs path cannot authorize a mutable request").
- Where the per-take text lands (previs only): `previs_service.py:324-331` — `if render_settings.prompt is not None: prompt = render_settings.prompt` (+ optional `[CREATOR SHOT DIRECTIONS]` append, `preserve_shot_prompt=True`). Then `:333-342` the server **re-attaches current locked looks** via `ensure_locked_appearance_in_prompt` regardless of what the box contains. Persisted per-take in `previs_images.prompt_used` + the render job's `input_payload` — **not** on the board, **no new board version**.

### 1c. The actual Runway video paths (both ignore the box)

1. **Canonical scene pipeline** (the production video path): `POST /projects/{id}/generate-scenes`-family → `generate_scene_pipeline` (`studio-backend/app/routes/projects.py:649`). Payload `GenerateScenePipelinePayload` (`projects.py:244-251`) = `{provider, on_audio_overrun, score_ambient_provider, prepared_snapshot_id, execution_mode, source_authority_id, expected_reference_binding_digests, …soundtrack}` — **there is no prompt, direction, or free-text field.** A per-take direction is untransmittable here by construction.
2. **Board shot render**: `POST /storyboard-blueprints/{bid}/shots/{sid}/render` (`storyboard_blueprints.py:338`). The handler reads `provider`/`submit` from the payload and calls `render_storyboard_shot`, which builds the job with `prompt=shot.render_contract.provider_neutral_prompt` (`storyboard_blueprint_service.py:981`) — again the board text, no take-text input.

## 2. Which text becomes the Runway video `promptText` — file:line

**The frozen contract's `provider_neutral_prompt`.** The per-take direction is not prepended, appended, or substituted — it is never read on this path. Chain:

| Step | Location | What happens |
|---|---|---|
| Board → prepared entry | `scene_production_pipeline_service.py:1291-1295` (standard) / `:1231-1235` (protected: "Only the approved storyboard prompt is creative authority") | `prompt` comes from the board shot; `_shot_prompt` (`:3158`) falls back through board-stored text only |
| Prepared entry → job | `scene_production_pipeline_service.py:536-542` (`prompt = prepared_entry["prompt"]`) → `render.py:~2579` (`input_payload.prompt = approved["prompt"]`, persisted from the **frozen** contract) | Job input = frozen prompt |
| Job → wire body | `runway_router_provider.py:1313` via `build_runway_router_video_request` (`:623`); `video_input["promptText"] = clean_prompt` (~`:660`) | `promptText` = frozen prompt, byte-for-byte; the builder **raises instead of truncating** over 20,000 chars |
| Submit-time gate | `runway_router_provider.py:1276-1313` (`submit_runway_router_video_render` with `request_payload`) | A prepared body is accepted only if it **byte-matches** a fresh rebuild from the frozen contract (`request_payload.promptText != prompt` → `ValueError`) — a mutated prompt fails closed |
| Offline rebuild | `reconstruct_runway_router_video_request` (`:809-934`) | Rebuilds the identical body from frozen contract + manifest only; "neither mutable RenderJob input nor current project text is consulted" |
| Camera-plan projection | `project_frozen_camera_plan_prompt` (`:282-305`), applied at `:917` | **Appends** any frozen camera-plan instructions missing from the prompt as a trailing block — the one sanctioned addition, from frozen state, not from the box |
| Shared board translation | `storyboard_render_inputs.py:26` (`prompt = contract.provider_neutral_prompt`; handoff append `:27-28`) | Feeds previs storyboard context (`previs_service.py:176`) and `render_storyboard_shot` (`storyboard_blueprint_service.py:972`) |

## 3. Does editing "Direct the action" change / persist / version anything?

- **Video prompt: no.** No video code path reads it (see §1c, §2).
- **Previs take: only if actually edited** (dirty + different from board text, `PrevisRoom.tsx:1622-1629`); then it overrides that one take's prompt, is stored in `previs_images.prompt_used` / job `input_payload`, and the server additionally re-injects current locked appearances (`previs_service.py:333-342`). Merely prefilling, or typing-then-reverting, sends nothing.
- **Board version: never.** Take rendering writes takes/jobs, not the board (consistent with `SCENE001_BLOCKERS_2026-10-17.md` §1.4). The adjacent board editor (`CreatorDecisionWorkspace` → `saveSceneDirection`) is what mints versions.
- **Helper-text accuracy:** "Your current direction is sent with this take" is true **only** for simulated previs takes (when edited). For a Runway video take it is false — nothing typed there reaches Runway.

## 4. Dry-run / preview / "show request" without submitting?

**No HTTP route returns the final Runway video request body without submitting.** What exists:

- `GET /projects/{project_id}/scenes/{scene_id}/generation-preflight` (`projects.py:745-808`) — **verifiably read-only** ("NEVER creates a render job, never touches a provider, never consumes credits"). Runs the real `prepare_scene_batch` gates and returns verdict + per-shot blockers + cost estimate + deterministic shot manifest (which carries each shot's frozen prompt). This is the safe way to inspect *what would be frozen*, but it does **not** return the wire body (`configId`/`input.promptText`/refs envelope).
- `reconstruct_runway_router_video_request(contract, manifest, dry_run=True)` (`runway_router_provider.py:809`) — pure/offline; rebuilds the exact body from already-frozen artifacts. This is how to construct the payload **in a test using temp data**: copy the frozen contract record + manifest to temp fixtures, call with `dry_run=True` (no network, no DB write). Do **not** call the live `submit_*` with `dry_run=True` against production — that still performs network I/O to Runway.
- `scripts/dry_run_provider_boundary.py` — manifest-fingerprint comparison only; does not build the wire body (per `R4.3B-live-provider-acceptance-safety-decision.md`).
- `POST …/shots/{sid}/render` **without** `submit:true` creates a DB job row (a write) — not read-only; not recommended as a "preview".

## 5. Exact `promptText` for scene_001 shot 1 as it stands today

Source: approved board row `sbs_1dd5df1d0955` (`version_id=sbv_1430cde84e4e` = blueprint `sbp_project_5907c60cddbc_scene_001_ec41ca26` current = approved; status `approved`). No render jobs, previs images, canonical runs, or delivery manifests exist yet for this project — **no take of any kind has ever been submitted** — so the frozen board text below *is* the entire prompt story. Length 2,286 chars (well under the 20,000 cap). Continuity handoff fields are all empty, `storyboard_image_url` is empty, `reference_assets` is `[]`, seed is `None`, duration 5s, aspect `16:9` — so `storyboard_render_inputs` adds nothing and the reference/seed wire fields carry only what the freeze step resolves (currently: no frame ref, refs TBD from binding; camera-plan projection appended at freeze if the frozen plan adds instructions — `structured_parameters.shot_planning.camera` is currently `""`).

First 600 characters (exact, verbatim from `render_contract_json.provider_neutral_prompt`):

> `Wide establishing shot. Camera far back. Full environment visible. DOWNTOWN CHICAGO — GOLDEN HOUR. Shot 1 of 5. Wide establishing shot. Camera far back. Full environment visible. Characters small in frame. Sets the location and mood.. DOWNTOWN CHICAGO — GOLDEN HOUR. Chicago is alive. The L train moves through the skyline. People fill the streets. Music,. Cinematic, film quality, single continuous shot. Locked appearance - maintain exact look, do not change race, skin tone, age, or gender: DRE (Early 30s): Early 30s; Broad-shouldered and physically imposing Black man with medium brown textured skin and expressive br…`

### Characters in that `promptText`

| Name | Occurrences | Form |
|---|---|---|
| DRE | 1 | `Locked appearance …: DRE (Early 30s): …` + full look + staging sentence |
| ELENA | 1 | `ELENA (Early 60s): …` + full look + staging sentence |
| JAY | 1 | `JAY (Early 30s): …` + full look + staging sentence |
| MAYA / Maya | **0** | absent — despite the shot's own intent narrative being Maya-centric ("Maya walks through the city…", `intent_json`) |
| MOM | **0** | absent |

Striking mismatch: the only `locked`-status reference locks in the DB today are **MAYA** (general + alternate_angle, approved) and **MOM** (general + alternate_angle, approved); **DRE's sole lock row is `provisional`/`unreviewed`** (`character_reference_locks`). The DRE/ELENA/JAY prose is stale baked-in text from an older prompt builder, while the shot's `intent.character_focus` is `[]` and its story is Maya's. (`prompt_components` is clean — 3 short strings: framing / location / rationale — and is *not* what is sent; only `provider_neutral_prompt` is.)

### If the per-take text were what Runway received…

It is not — so **no**: deleting the DRE/ELENA/JAY entries in the box is **not sufficient** for a video take; it changes zero bytes of any video request. And yes, the frozen contract still carries the old text elsewhere-or-rather-everywhere-downstream: the same string lives in `storyboard_shots.render_contract_json.provider_neutral_prompt` on all four version rows of `scene_001_shot_001` (`sbv_ea20abec1338`, `sbv_b92243ea0008`, `sbv_3cee32c0326a`, `sbv_1430cde84e4e`), and once a freeze happens it propagates immutably into the generation contract (`payload["prompt"]`), the manifest `shot_prompt`, the job `input_payload.prompt`, and the byte-checked wire body — all of which must match exactly or submission fails closed.

## 6. Safest way to get a Maya-only video prompt for ONE take today

There is **no per-take video override mechanism** — by design (frozen-contract authority). The only safe path today goes through the board:

1. Edit Scene Direction for scene_001 shot 1 via `CreatorDecisionWorkspace` (the shot-panel canonical-text editor, *not* the "Direct the action" box) — remove the DRE/ELENA/JAY locked-appearance blocks, keep the Maya beat. This mints a **new draft version** (expected; orphaned image-prompt rows are a known side effect — re-derive/approve them).
2. Run continuity review → approve the new version (board must be `approved`, current = approved).
3. Optionally hit `GET generation-preflight` (read-only) and confirm the shot-1 manifest prompt is Maya-only.
4. Render via the canonical scene pipeline (`generate_scene_pipeline` with `provider=runway_router`), which freezes the new prompt and sends it.

Do **not** try to "fix it in the box": on the video path it is silently ignored, and on the previs path an edit only affects a simulated take (while the server re-attaches MAYA/MOM locked looks anyway).

## 7. Longer-term fix (not applied)

1. **Stop baking stale appearances into the frozen prompt**: reconcile `_build_provider_neutral_prompt` (`storyboard_blueprint_service.py:1263`) with the live lock table at version-creation time (DRE is provisional; MAYA/MOM are locked; ELENA/JAY have no locks at all) — or drop baked-in appearance prose in favor of reference bindings, which is what the router path actually enforces.
2. **Fix the misleading helper text** under "Direct the action" ("Your current direction is sent with this take"): qualify it — e.g. "Sent with this previs take when edited. Runway video renders always use the approved board prompt." — or hide/disable the box's implication whenever a video provider is selected.
3. **If per-take video steering is ever wanted**, add it as a first-class, re-frozen input (e.g. an explicit override field on the pipeline payload that flows through `prepare_scene_batch` → new manifest fingerprint → contract), never as a silent mutation — the byte-equality submit gate (`runway_router_provider.py:1276-1313`) must keep holding.
4. Consider a read-only `show-request` route wrapping `reconstruct_runway_router_video_request(..., dry_run=True)` over the *current approved* board state, so owners can see the exact `promptText` before spending anything.

## Appendix — provenance of each claim

- Prefill + override gate: `studio-app/src/pages/PrevisRoom.tsx:1509-1519`, `:1616-1629`; button `:3159-3172`.
- Forced simulated provider: `studio-app/src/lib/legacyPrevisProvider.ts:12`; API client `studio-app/src/lib/studioApi.ts:3711-3755`.
- Previs route/service Runway refusals: `studio-backend/app/routes/previs_routes.py:104-122,128-170`; `studio-backend/app/services/previs_service.py:206-247`.
- Per-take prompt handling (previs): `studio-backend/app/services/previs_service.py:324-342`; model `studio-backend/app/models/previs_render.py:13-46`.
- Pipeline payload has no text field: `studio-backend/app/routes/projects.py:244-251,649-748`; read-only preflight `:745-808`.
- Frozen prompt chain: `scene_production_pipeline_service.py:1231-1235,1291-1295,536-542`; `render.py:~2579` (job `input_payload.prompt=approved["prompt"]`); `runway_router_provider.py:282-305,623-,809-934,1276-1313`; `storyboard_render_inputs.py:11-30`; `storyboard_blueprint_service.py:972-985` (`render_storyboard_shot`).
- DB facts (read-only): blueprint `sbp_project_5907c60cddbc_scene_001_ec41ca26` (current=approved=`sbv_1430cde84e4e`); shot `sbs_1dd5df1d0955`; prompt 2,286 chars; handoff empty; no frame URL; refs `[]`; locks: MAYA/MOM `locked`, DRE `provisional`; zero rows in `render_jobs`/`previs_images`/`canonical_workflow_runs`/`delivery_manifests` for this project.
