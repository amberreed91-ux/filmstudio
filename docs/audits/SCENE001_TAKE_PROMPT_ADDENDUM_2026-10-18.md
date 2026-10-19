# ADDENDUM — Scene_001 take-prompt audit (2026-10-18)

Parent: `docs/audits/SCENE001_TAKE_PROMPT_2026-10-18.md`. Method: read-only
(`studio.db` opened `mode=ro`; no code edits, no DB writes, no provider calls,
no workflow steps performed). This file is the only change.

## 1. Lock recheck + per-shot character blocks under the lock-table rule

### 1a. Both audits are correct — they read different systems (re-verified today, read-only)

| Character | `appearance_approval.status` (`characters.continuity_state_json`) | `character_reference_locks` rows |
|---|---|---|
| DRE | **locked**, v3, approved 2026-10-09 | 1 row: `provisional` / `unreviewed` (scene_002_shot_001) |
| ELENA | **locked**, v1, approved 2026-09-06 | **no rows** |
| JAY | **locked**, v1, approved 2026-09-17 | **no rows** |
| MAYA | **locked**, v2, approved 2026-10-09 | `locked`+`approved` general (high) and alternate_angle (medium); 1 older `superseded` |
| MOM | **locked**, v1, approved 2026-09-06 | `locked`+`approved` general (high) and alternate_angle (medium); 1 older `superseded` |
| SIMONE | **locked**, v1, approved 2026-09-06 | **no rows** |

So "all six locked" (`SCENE001_BLOCKERS_2026-10-17.md` §2.3, via
`appearance_approval` in `character_appearance.py:24`) and "only MAYA and MOM
locked, DRE provisional" (take-prompt audit §5/appendix, via the
`character_reference_locks` table) describe two different lock systems. The old
prompt block used the first; the rebuild must use the second.

### 1b. New rule

`locked_appearance_characters` (`shot_prompt_builder.py:223`) is re-sourced from
`character_reference_locks` (`lock_status='locked'`) instead of
`appearance_approval.status`. Locked set becomes **{MAYA, MOM}**.
`build_locked_appearance_block` (`:298`, precedence shot focus → scene cast →
shot text → scene-union → empty, no alphabetical truncation) is otherwise
unchanged, as is `_appearance_only_text` (`:261`, appearance fields only —
the long staging sentences disappear regardless).

### 1c. Resulting blocks for scene_001 shots 1–5 (approved `sbv_1430cde84e4e`)

Shot inputs today: every shot has `character_focus=[]`, empty identity
constraints, empty handoff, and scene_001 declares no cast — so scopes 1–2
never fire. Name evidence in the built shot prose (word-boundary):

| Shot | Locked names in shot prose | Scope that fires | New block |
|---|---|---|---|
| 1 (wide establishing) | none (only baked DRE/ELENA/JAY, which the new rule drops) | 4 — scene_union (MAYA named in shots 3–4) | **MAYA only** |
| 2 (medium) | none | 4 — scene_union | **MAYA only** |
| 3 (close-up; "Maya walks…", "Only MAYA visible") | MAYA | 3 — shot_text | **MAYA only** |
| 4 (transition; "MAYA (V.O.). Only MAYA visible. Characters: MAYA…") | MAYA | 3 — shot_text | **MAYA only** |
| 5 (detail) | none | 4 — scene_union | **MAYA only** |

- **MOM appears in no shot** (no focus, cast, or prose mention anywhere in scene_001) and is correctly excluded everywhere — the rule must not leak other scenes' faces in.
- **DRE/ELENA/JAY are dropped from all five shots** (absent from the lock table).
- Shots 1/2/5 depend on the scope-4 union fallback (fires a `LOCKED_APPEARANCE_SCOPE`
stage log); the rebuild caller must pass `scene_shot_texts`, or those three
shots get an empty block plus warning instead of MAYA.
- New block text is short-form (`MAYA (Late 20s): <look>`, appearance fields
only) — the Pilsen-garden / auto-shop / post-collapse staging sentences go away.

### 1d. Rules kept as written (incl. §2 gates)

Only the locked-source + per-shot scoping change. Unchanged: frozen-contract
authority for video `promptText`; the submit-time byte-equality gate
(`runway_router_provider.py:1276-1313`); the 20,000-char fail-closed cap; the
frozen camera-plan projection (`:282-305`); continuity-handoff append; no
per-take text on any video path; take rendering still mints no board versions.

## 2. Design: make "Direct the action" honest (no behavior change)

Problem: the helper text "Your current direction is sent with this take"
(`PrevisRoom.tsx`, under `<label for="previs-render-prompt">`) is true only
for edited simulated-previs takes and false for every Runway video render.

**Recommended (label, not hide):** the box belongs to the Render step, whose
only button is the previs take; hiding it would remove previs functionality.
Change the helper copy (UI-only, handler logic untouched):

- From: "Describe what moves, what happens, and how the camera follows. Your current direction is sent with this take."
- To: "Describe what moves, what happens, and how the camera follows. Edited direction is sent with this previs take only — Runway video renders always use the approved board prompt."
- Add `data-testid="render-prompt-scope-note"` to the `<p>` for the test below.

Frontend test (repo pattern: `renderToStaticMarkup`, cf.
`CanonicalWorkflowPanel.test.tsx`): render the Render-step prompt block (or a
small extracted `RenderPromptScopeNote` component if the team prefers) and
assert the markup contains both "previs take" and "approved board prompt" and
no bare "sent with this take" claim. Disabled-state matrix unchanged; no
handler, route, or service code touched — zero behavior delta by construction.

## 3. Owner click path: one real canonical Runway video render (research only — nothing performed)

Surface: PrevisRoom → Review step (`previs-step-review`) → "Production
handoff · Canonical Production Thread" `<details>` →
`CanonicalWorkflowPanel` (`studio-app/src/components/CanonicalWorkflowPanel.tsx`,
`data-testid="canonical-workflow-panel"`). Gated sequence
(`nextCanonicalWorkflowAction`; each button appears only in its state):

1. **"Start approved production thread"** — `POST …/production-threads/begin`
   (project+scene+script context). Local/durable only. No spend.
2. **"Generate approved Previs"** — simulated previs (panel labels it
   "Simulated previs: instant, no cost"). No spend.
3. **"Approve exact Previs set"** — `window.confirm` + approval over the exact
   artifact IDs. No spend.
4. **"Build production package"** — `POST …/production-threads/{run_id}/production-package`
   (`canonical_workflow.py:148`; service `:360`). Freezes the exact package
   from the approved blueprint. No spend. Safe to verify first via read-only
   `GET generation-preflight` before proceeding.
5. **"Queue approved render"** — `window.confirm("Queue the exact approved
   package with {provider}?")` → `POST …/production-threads/{run_id}/renders`
   with `provider=runway_router` (panel shows "New renders: {providerLabel}").
   Backend `render_production_package` (`canonical_production_workflow_service.py:399`)
   first **creates** the jobs (`render_queued`, free), then calls
   `_reconcile_renders(…, submit=True)` (`:488`), which calls
   `renderer.submit_job(job.id)` (`:1024`) — the network POST to Runway.

**First credit spend = step 5's confirm ("Queue approved render").** Steps 1–4
(incl. job-row creation inside step 5 before submit) cost nothing. Notes:
step 5 queues the whole package's shots, not a single shot (there is no
one-shot canonical video button; single-shot video exists only via the
board-shot render route, a different path); retries keep the original provider
(`:161-163`, `retry_render` reuses jobs without duplicates).

### Correction (2026-10-19, pre–Phase B verification — supersedes step 5 above)

Step 5 as written is wrong on two counts, verified by reading the submit path
end to end (no render performed):

1. **The dialog does not send `runway_router`.** The panel sends the Previs
   room's render-provider picker value straight through
   (`renderCanonicalShots(run.run_id, { provider: renderProvider, … })`,
   `studio-app/src/lib/canonicalWorkflowApi.ts`). The picker offers `runway`
   (`PrevisRoom.tsx:398-403`, `buildRenderProviderOptions`), so the owner
   path submits with **provider `runway`** — never `runway_router`.
2. **Provider `runway` submits nothing.** `RenderService.submit_job`
   (`studio-backend/app/services/render.py:4383-4408`) marks any
   `runway`/`runway_direct` job **failed** with
   `direct_runway_submission_disabled` ("rebuild through the Runway Model
   Router with a frozen contract") before any adapter is reached, and
   `RunwayAdapter.submit_job` (`studio-backend/app/adapters/__init__.py:799`)
   independently refuses the legacy direct video boundary fail-closed. No
   video model is selected, no endpoint is contacted, no POST is sent, no
   credits move. The workflow run ends `render_failed`; the failure is the
   guard working, not a render.

Corrected click-path outcome: steps 1–4 are durable and free; confirming the
one-shot dialog with provider `runway` creates exactly one job row, then fails
it closed at submit — **the owner gets no video and spends nothing**.
`runway_router` cannot be driven from this dialog either: creation raises
without a `generation_contract` (`render.py:2161`), which this workflow never
passes. A working owner render requires Phase B to route this dialog through
the frozen-contract Router path; until then, no Gate-1/Phase-A claim about
"the `runway` path that actually submits" should be relied on — real
submission was proven only under the fake renderer in tests.
