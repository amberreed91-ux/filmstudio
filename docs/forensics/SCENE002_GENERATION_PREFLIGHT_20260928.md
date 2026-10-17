# SCENE_002 GENERATION PREFLIGHT — 2026-09-28

**Verdict: GENERATION PREFLIGHT READY — `ready: true`, 0 blockers, 5 shots.
All provider calls withheld. Zero credits spent.**

This pass executed the first creator decision pass for scene_002
(`project_5907c60cddbc`) exactly as scoped in the pass instructions, following
`docs/forensics/SCENE002_CREATOR_WORKFLOW_20260927.md`. Every creative decision
below is an explicit creator choice made through the application's own
authenticated workflows; nothing was inferred from defaults, and nothing was
batched.

---

## 1. Recovered baseline (matches the creator workflow report exactly)

Live database `studio-backend/data/studio.db` hashes at pass start:

| File | SHA-256 |
|---|---|
| `studio.db` | `cb99f8c9bfbe0a52404064e703a3ee1ad0298aad18fd4e2e11e64ef7fd46067c` |
| `studio.db-wal` | `6c52f096a79283dc14503a727b16bdde1a405dac259078223cf873061db0c6d4` |

Verified against byte copies (`/tmp/scene002_preflight_verify/`,
`/tmp/scene002_post_actions/`):

| Check | Expected | Actual |
|---|---|---|
| Blueprint | `sbp_project_5907c60cddbc_scene_002_3400a20b`, locked=0 | ✔ |
| Approved version | `sbv_3b88a1e0ef95` = current = approved | ✔ |
| Version count | 2 (v1 + v2) | ✔ |
| Five approved v2 shots | approved, unlocked, no `camera_plan` | ✔ |
| Previs `…b1d573f1` | complete, approved=0, seed 916483 | ✔ |
| Canonical scene_002 setting rows | 0 | ✔ |
| Reference rows | 11 | ✔ |
| Live preflight | ready:false — 5 camera + 5 canonical-setting blockers | ✔ |
| Render jobs created 2026-09-27+ | 0 | ✔ |

**One deployment discrepancy was found and resolved at the start** (recorded in
the interim version of this report, restored below): the running production
backend (pid 30468, started 2026-09-27 02:48:44) predated the creator-workflow
implementation — `POST …/camera-approvals/{shot_id}` returned 404 and the route
was absent from the live OpenAPI schema while the code existed on disk (files
modified 2026-09-27 22:52; process started without `--reload`). The creator
authorized a restart; the backend was relaunched with the identical command,
venv, host/port, and environment (verified from the original process:
`STUDIO_ACCESS_MODE=local`, `LOCAL_LTX_ENABLED=true`, `IMAGE_PROVIDER_…`,
provider keys unchanged). After restart the route was live and the baseline
re-verified unchanged before any approval.

## 2. Five camera decisions — presented verbatim, approved individually

Suggestions were shown exactly as the application produces them
(`visual_plan.framing`); no rewrite, improvement, or substitution was offered.
For every shot the existing camera angle, movement, lens, and shot size are
**none** (empty/null), so approving locks **only** the framing sentence.

| # | Storyboard shot ID (v2) | Shot ID | Purpose | AI suggested framing (verbatim) |
|---|---|---|---|---|
| 1 | `sbs_a7648698ad00` | `scene_002_shot_001` | `establishing_shot` | "Wide establishing shot. Camera far back. Full environment visible." |
| 2 | `sbs_a8481a439ea5` | `scene_002_shot_002` | `medium_shot` | "Medium shot. Characters from waist up. Action and dialogue beginning." |
| 3 | `sbs_be2cce8fab93` | `scene_002_shot_003` | `close_up` | "Medium close-up. Character faces and upper body. Emotional beats." |
| 4 | `sbs_51d1500d227c` | `scene_002_shot_004` | `transition_shot` | "Dynamic medium shot showing the story transition in motion." |
| 5 | `sbs_0046fb5192f0` | `scene_002_shot_005` | `emotional_detail_shot` | "Close-up detail shot. Eyes, hands, specific objects. Intimate beat." |

**Creator decision: approved all five framings individually, verbatim.**
Execution mode: strict one-by-one (each approval its own HTTP call with its own
`expected_version_id` binding), with a full state verification after each.

## 3. Camera approvals executed — one shot per call, never batched

Each approval used the authenticated route
`POST /projects/{project_id}/scenes/{scene_id}/camera-approvals/{shot_id}` with
`approved_by: "creator"` and the version binding current at the time of the
call. After each: decision persisted ✔, approved version hash unchanged ✔,
draft state as expected ✔, no other shot changed ✔.

| Shot | Called against | Persisted on | Response `approved_camera` |
|---|---|---|---|
| 1 | `sbv_3b88a1e0ef95` | v3 clone `sbs_9d42dbaf4a00` | framing 1 (verbatim) |
| 2 | `sbv_a6096cb1fea5` | v3 clone `sbs_637384209db0` | framing 2 (verbatim) |
| 3 | `sbv_a6096cb1fea5` | v3 clone `sbs_aaf9ddad55c3` | framing 3 (verbatim) |
| 4 | `sbv_a6096cb1fea5` | v3 clone `sbs_18b3baf5b2f3` | framing 4 (verbatim) |
| 5 | `sbv_a6096cb1fea5` | v3 clone `sbs_ee9d541dae68` | framing 5 (verbatim) |

Each shot's decision is stamped `AI_CAMERA_APPROVED_BY_USER:creator` in the
clone's change reason. Plans count on v3 progressed 1 → 2 → 3 → 4 → 5, one per
approval; nothing else on v3 changed between approvals. The v2 shot-set hash
(`ef7169ec1506a026ad2add36…`) never moved from first check to final check.

## 4. Version transitions (the application's actual chain, followed)

| Version | # | Status | Change reason | Notes |
|---|---|---|---|---|
| `sbv_dbafa23cf4a1` | 1 | approved (superseded) | create_or_update_draft | v1 history |
| `sbv_3b88a1e0ef95` | 2 | **approved — immutable** | scene_002 regeneration after creator-approved screenplay correction | Hash-verified unchanged through the entire pass; never a target of writes after approval |
| `sbv_a6096cb1fea5` | 3 | **approved** (final) | ai_camera_approval → creator approval | Created by approval 1 as the designed draft; approvals 2–5 mutated the same draft; continuity review then creator re-approval finalized it |

- After approval 1 the pass stopped and explained the transition to the creator,
  who explicitly authorized continuing against the new draft (per pass rule 3).
- Structural diff v3 vs v2: **only** the five approved `camera_plan` entries in
  `structured_parameters` plus the expected `provenance.version_id` bump. All
  other contract fields, prompts, visual plans, intents, durations, and seeds
  are byte-identical.
- The board re-approval (`POST /storyboard-blueprints/{bp}/versions/sbv_a6096cb1fea5/approve`,
  `approved_by: "creator"`) was an explicit creator decision after a completed
  continuity review (see §5). Final chain: `current = approved = sbv_a6096cb1fea5`,
  all five shots `approved`, 3 versions total.

## 5. Continuity review (mechanical precondition, creator-authorized)

`POST /storyboard-blueprints/{bp}/versions/sbv_a6096cb1fea5/continuity-review`
(reviewed_by creator). Result: `completed`, 5 shots, **0 high**, **5 medium**,
0 low — `ready_for_creator_approval`. The five medium issues are one pre-existing
advisory per shot ("An emotional goal for the shot" — empty `emotional_target`
in the intent carried over from v2); they are unchanged legacy content, not
introduced or resolvable by this pass, and do not block approval.

## 6. Canonical setting decision — explicit, via the supported workflow only

The creator was shown the actual candidate surface (image opened in the
browser): previs `previs_project_5907c60cddbc_scene_002_scene_002_shot_001_b1d573f1`,
seed **916483**, rendered 2026-07-27, 1664×928 PNG, prompt matching v2 Shot 1's
framing, `status=complete, approved=0` at decision time. The creator **chose it
as the canonical scene_002 environment**, and the supported workflow alone was
executed — no direct `canonical=1` manipulation at any point:

1. `POST …/previs/records/{image_id}/approve` → `approved=1, status='approved'`,
   `approved_by: creator`, 2026-09-28T01:33:04.
2. `GET …/reference-library/setting/scene_002` (the documented sync trigger)
   minted/healed the deterministic row.

**A second real gap was found and fixed during this step** (regression-pinned;
the interim report recorded the failure): the sync's idempotency check compared
only `image_url` + `kind`, so a legacy row from the pre-recovery pipeline —
`ref_env_6b726885ed67ae4d`, same deterministic ref_id, same image, but empty
`target_type`/`target_id` and `canonical=0` — was silently skipped, leaving the
creator's approval invisible to the reference gate. Fix: the skip condition now
also requires `target_type`, `target_id`, `canonical`, and `approval_state` to
match, so a stale row is healed in place while a converged row still
short-circuits (idempotency preserved). Test:
`test_legacy_row_with_matching_ref_id_is_upgraded_to_canonical`. The backend was
restarted (same faithful procedure) to load the fix before the sync was retried.

### Reference verification (final row state)

| Field | Required | Actual |
|---|---|---|
| ref_id | deterministic | `ref_env_6b726885ed67ae4d` |
| target_type | `setting` | ✔ `setting` |
| target_id | `scene_002` | ✔ `scene_002` |
| canonical | 1 | ✔ 1 |
| approval_state | `approved` | ✔ `approved` |
| kind | `environment` | ✔ `environment` |
| Count of canonical scene_002 setting rows | exactly 1 | ✔ 1 |
| Total project reference rows | 11 (healed in place, none added) | ✔ 11 |
| Scene binding | derived from the approved previs row's own `scene_id` | ✔ structurally scene_002 |

## 7. Generation preflight — real run, fail-closed stack

`GET /projects/project_5907c60cddbc/scenes/scene_002/generation-preflight`
(the exact `SceneProductionPipelineService.prepare_scene_batch` stack the batch
generation uses: readiness gate + prompt integrity + reference gate + cost gate):

- **ready: true**, 5 shots, **0 blockers** (was ready:false / 10 blockers at baseline).
- Mid-pass gate behavior (correct fail-closed): with v3 draft ≠ approved, the
  preflight refused with "Approve the current storyboard version before
  rendering this scene" — the version chain is enforced, not advisory.

## 8. Payload verification (per shot, pre-provider)

From the final preflight entries — prompts, hashes, camera provenance,
references, parameters. No scene_001 data anywhere; no stale camera plan; no
legacy shot seed silently overriding the scene (all seeds explicit None; the
previs seed 916483 lives only on the previs/reference asset and was never
injected into shot payloads).

| Shot | Prompt (first 60 chars) | Prompt sha256 | Camera plan (locked) | Camera provenance |
|---|---|---|---|---|
| 001 | "Wide establishing shot. Camera far back. Full env…" | `dd294ccc853e22d1ebd7c94d52a37d20aaafd566c6c73462ae8e577741b04221` | framing 1 verbatim | APPROVED @ sbv_a6096cb1fea5 |
| 002 | "Medium shot. Characters from waist up. Action and…" | `40a97b00b66851a3d1d3ba6b95f381d3d71640235f9967ddd5185b1a24da210d` | framing 2 verbatim | APPROVED @ sbv_a6096cb1fea5 |
| 003 | "Medium close-up. Character faces and upper body. …" | `0b17c9f5d9643d3bc1f6430b8fcc0624c9d7d99af64ec418c11184e8f1aa5852` | framing 3 verbatim | APPROVED @ sbv_a6096cb1fea5 |
| 004 | "Dynamic medium shot showing the story transition i…" | `0dfa7750244a11fe9a626c01d3fc6c00029386d47fdf0fa7a1a4dd8900e76771` | framing 4 verbatim | APPROVED @ sbv_a6096cb1fea5 |
| 005 | "Close-up detail shot. Eyes, hands, specific object…" | `b9d28ee7afb700553b295908823bd799be1e740d6fb06b40981b46f7fa324394` | framing 5 verbatim | APPROVED @ sbv_a6096cb1fea5 |

All shots: `duration_seconds=5`, `aspect_ratio 16:9` (contract) / `ratio 1280:720`
(parameters), `seed=None` everywhere, `shot_version` per-shot, `generation_context_id`
per-shot, storyboard metadata bound to `sbv_a6096cb1fea5` / the v3 clone IDs /
`link_type=scene_pipeline_render`, per-shot `blockers=[]`.

Reference identity, per shot: `reference_requirements.setting_id = scene_002`,
`setting_urls = ['/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png']`
(the canonical reference image), `character_ids = ['chr_f1425498cb68' (DRE),
'chr_3c9e91741ef3' (MAYA)]`. Shot 1 additionally carries the frame in its own
shot-level references; shots 2–5 carry it through the canonical setting
requirement — the gate-validated source for every shot.

Manifest: `manifest_version 1`, `scene_version a7c14e2b1bb2c7c0`,
`storyboard_version sbv_a6096cb1fea5`, batch model `gen4.5` (provider default,
AUTO), total 25s / estimated 300 credits (Runway pricing), readiness `ready`,
fingerprint `04d869c32363d03f`.

### Provider-invariance proof

Preflight was run with `provider=runway` and `provider=flux2` and every creative
field compared: prompts, camera plans, camera instructions, references, setting
URLs, parameters, durations, manifest shots (except per-call generation-context
ids), scene and storyboard versions — **identical**. The only provider-dependent
fields are cost metadata (model selection / credit estimate), and the manifest
fingerprint excludes generation-context ids by design. Switching providers
cannot silently change prompt, camera, references, scene, shot, seed, or any
creative decision; only the price/model row changes.

## 9. Stale-state checks (final sweep, all clean)

- scene_001: previs rows, blueprint, and shots all **byte-identical** to baseline.
- `scene_memories` table: identical to baseline (no script/scene-text mutation).
- `project_state_store.json` untouched (mtime predates the pass).
- v2 approved version shots: hash `ef7169ec1506a026ad2add36…` unchanged.
- No stale-version shots on the current chain; no unapproved scene_002 setting
  candidates left behind.
- `render_jobs` created 2026-09-27+ for the project: **0**.
- No prompt substitution or hidden fallback: prompts are the board's
  provider-neutral prompts plus the deterministic `[SHOT POSITION]` block, hashed
  and reported verbatim above.

## 10. Regression tests (code change made by this pass)

Only one production file changed (`app/services/reference_asset_service.py` —
the sync-heal fix in §6) plus two tests:

- `app/services/test_reference_asset_creator_sync.py` — 16 passed (incl. the new
  legacy-heal regression pin).
- `tests/test_scene002_creator_workflow.py` — 23 passed (one test hardened to
  enumerate routes via the OpenAPI schema because this FastAPI version wraps
  included routers in `_IncludedRouter` objects with no `.path`; behavior
  unchanged — the no-batch-endpoint guarantee still asserts exactly one
  camera-approval path).
- `app/services/test_reference_library.py`, `test_reference_validation.py`,
  `test_render_reference_consistency.py`, `test_render_scene_reference_transition.py`,
  `test_render_canon_integration.py` — all passed (70 + 26 green total).

## 11. Provider readiness gate (configuration checked; zero calls made)

**Runway image generation (gen4_image): NOT READY — one blocker.**
- Credential present (`RUNWAYML_API_SECRET` in the running env), provider
  registry `available`, hosted mode, ready-for-hosted-generation.
- Aspect ratio supported (`1280:720` is in gen4_image's supported ratios; the
  image seam translates it deterministically).
- References supported: `referenceImages` (max 3) with fail-closed normalization
  — unrepresentable entries are reported in meta, never silently discarded.
- **Blocker:** the provider fails closed on prompt length
  (`promptText` max 1000 UTF-16 units, `_RUNWAY_MAX_PROMPT_LENGTH = 1000`), and
  every verified shot prompt is 3,084–3,290 characters. A submit today would
  correctly raise, not truncate — so generation is blocked until the creator
  decides how to handle prompt length (condense, restructure prompt budget, or
  an explicitly approved per-provider prompt policy). No automatic truncation
  was performed or will be.

**FLUX.2 image generation (flux.2-klein-4b via NVIDIA): NOT READY — three blockers.**
- Credential present (`NVIDIA_API_KEY` in the running env), seam enabled
  (`IMAGE_PROVIDER_ENABLED=true`, `IMAGE_PROVIDER_NAME=nvidia`).
- **Blocker 1 — prompt length:** fails closed at 800 chars
  (`_MAX_PROMPT_LENGTH`); verified prompts are 3,084–3,290 chars. Same creator
  decision required as Runway.
- **Blocker 2 — references:** the integration is text-to-image only
  (`reference_types=()`, `maximum_reference_count=0`; the NVIDIA seam's submit
  signature takes no references). The scene now requires a canonical setting
  reference and resolves two character references per shot; sending to NVIDIA's
  hosted FLUX.2 endpoint would silently drop the reference identity binding the
  creator just established. Nothing in the pipeline masks this today — the
  honest readiness answer is that reference-conditioned generation is out of
  contract for this integration, not merely unpriced.
- **Blocker 3 — cost model:** unpriced in the registry (`credits_per_second=0`,
  estimated 0 credits); the batch manifest reports no model for it. Not a
  generation blocker, but the cost gate cannot estimate FLUX.2 spend today.

**Provider switching remains model-agnostic:** the image seam
(`providers/image_provider.py`) and the model registry are the only
provider-aware layers; storyboard/reference/scene services are provider-blind.
The provider-invariance proof in §8 is the structural guarantee that switching
Runway ↔ FLUX.2 cannot silently change prompt, camera, references, scene, shot,
seed, or creative decisions.

## 12. Remaining blockers (nothing hidden)

1. **Prompt-length policy (creative, blocks both providers' image path):** the
   verified prompts exceed both providers' fail-closed limits. Requires an
   explicit creator decision — the application will not truncate silently.
2. **FLUX.2 reference conditioning (product gap):** the hosted FLUX.2 Klein
   integration cannot consume the canonical setting / character references the
   scene now requires. Until the seam supports references (or the creator
   accepts reference-less generation as an explicit decision), FLUX.2 stays
   NOT READY for scene_002.
3. Pre-existing, outside this pass (unchanged): script_text CONFLICT ①, the five
   medium continuity advisories (empty per-shot `emotional_goal`), and the
   explicit-seed decision recommendation from the readiness audit.

## 13. Creator approvals ledger

| Decision | Choice | Authorization |
|---|---|---|
| Camera shot 1–5 (each asked individually) | Approve verbatim framing | Explicit, per shot |
| Execution mode | (left unanswered → strict one-by-one applied) | Default per pass rules |
| Version transition after approval 1 | Continue approvals 2–5 against draft v3 | Explicit |
| Backend restart (deployment discrepancy) | Restart now and resume | Explicit |
| Canonical setting (seed 916483 previs) | Promote via approved workflow | Explicit |
| Board re-approval | Continuity review + approve v3 | Explicit |

## 14. Safety record

| Item | Value |
|---|---|
| Database modifications | ONLY the explicit creator decisions above (5 camera plans on v3, continuity review metadata, v3 approval stamps, previs approve flag, canonical reference heal) + the one code fix with its regression test |
| Script text modified | NO |
| Scene_001 modified | NO (byte-identical previs, blueprint, shots) |
| Unexpected creative mutations | 0 (v2 immutable throughout, hash-verified; v3 diff = approved decisions only) |
| Runway calls | 0 |
| FLUX.2 / NVIDIA calls | 0 |
| Any provider calls | 0 |
| Credits spent | 0 |
| Render jobs created | 0 |
| Generation payload verified | YES (§8) |
| Generation preflight | READY — ready:true, 0 blockers, fail-closed gates green |

---

**STOP — HARD GATE.** The verified generation payload (§8) and readiness status
are delivered; no provider has been contacted. The next authorization must
explicitly determine (a) which image provider to use and (b) the prompt-length
policy for it — and for FLUX.2, whether reference-less generation is acceptable
at all. No credits will be spent and no provider will be called until that
explicit instruction.
