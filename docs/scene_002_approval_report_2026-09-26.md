# Scene 002 — Board Approval Stage Report

Project `project_5907c60cddbc` ("I was reborn") · Scene `scene_002` — "AFTER THE APOCALYPSE"
Date: 2026-09-26 · Branch: `backend-expansion-dependency-slicing`
Stage: **DRAFT v2 → APPROVED v2** (complete). Generation not attempted. Credits spent: **0**.

Preceding state (verified before acting, unchanged after): master `9a9c661823491a6a`,
scene_002 `ba873f18a7291bd8`, v1 `sbv_dbafa23cf4a1` approved, v2 `sbv_3b88a1e0ef95` draft.

---

## 1. What was executed (normal version approval path only)

1. **Continuity review** — `POST /api/f51/studio/storyboard-blueprints/{bp}/versions/sbv_3b88a1e0ef95/continuity-review`
   → `scr_c642613b209a`, status `completed`: 0 high / 5 medium (all five are the same benign
   advisory: "No emotional goal is recorded" per shot) / 0 low → `ready_for_creator_approval`.
2. **Approve** — `POST …/versions/sbv_3b88a1e0ef95/approve` (`approved_by: creator`) → HTTP 200.
   All 5 shots flipped `ready → approved`; version + blueprint now `approved`;
   `current_version_id == approved_version_id == sbv_3b88a1e0ef95`.
3. **Post-approval preflight** — via `scripts/dry_run_provider_boundary.py` (store copies +
   simulated provider, live stores never opened for writing) and the read-only live endpoint
   `GET …/scenes/scene_002/generation-preflight`. Both agree.

Audit evidence snapshots: `studio-backend/.validation/scene002_approval_20260926/`
(pre/post DB backups, shot/version/blueprint row snapshots).

## 2. Verification results (all PASS)

| Check | Result |
|---|---|
| `sbv_3b88a1e0ef95` is approved current version | ✅ blueprint `approved`, current == approved == v2 |
| `sbv_dbafa23cf4a1` untouched | ✅ all 5 shots byte-identical (payload digests + status + updated_at); version row status/approved_at/approved_by/metadata unchanged; still `approved` as historical lineage |
| Lineage | ✅ v2 `source_version_id = sbv_dbafa23cf4a1` (unchanged) |
| Approval reset behavior | ✅ draft state had blocked `scene_render_inputs` ("Approve the current storyboard version…"); after approval it resolves exactly 5 shots in order 1→5 |
| v2 prompts byte-stable through approval | ✅ all 5 `render_contract` payloads byte-identical pre/post approval (only shot status + updated_at moved) |
| Approved v2 prompts == regenerated prompts | ✅ per-shot sha16 match the review package exactly: `329b84e2f698f4ec` (3,200), `7118ac1afd66b685` (3,012), `5b98c2831a9da5d8` (2,994), `0e80c32afd7a576c` (3,003), `9bc47ad3336ac737` (3,074). Note: the prior doc's combined anchor `eb7fd32769644ab4` does not record its derivation recipe; the five per-shot hashes are the byte-exact proof (5/5 match) |
| No stale render manifest / fingerprint inherited | ✅ `delivery_manifests` has 0 rows; old pre-approval fingerprint `d28ad2a0104f1554` appears nowhere in the store; fingerprints are computed per preflight run from current state |
| Continuity review audit preserved | ✅ `scr_c642613b209a` stored on v2 + blueprint metadata; v1's own review (`scr_a1f08a0d1d9a`) untouched |
| Screenplay hashes unchanged | ✅ master `9a9c661823491a6a`, scene_002 `ba873f18a7291bd8` |
| Dialogue authority | ✅ exactly 10 canonical lines, script order DRE/MAYA alternating, 0 fabricated; 22 historical placeholder rows still quarantined from production consumers |
| No MOM contamination / truncation / scene leakage | ✅ zero `\bMOM\b` hits, no `...` truncation, no scene_003 content in any of the 5 approved prompts |
| No dialogue silently assigned | ✅ no `dialogue_lines` key in any shot contract; no scene_direction metadata on v2 |
| No provider calls / no credits | ✅ 0 render jobs before and after (28 → 28), no new audit rows, no provider endpoint contacted; cost figure is a local registry lookup |

## 3. Final generation preflight (current code, no provider calls)

**BLOCKED — by design.** Live endpoint and sandboxed dry run produce the identical verdict.

- Manifest fingerprint (deterministic, minted fresh from approved state):
  **`f797caebdf13ba37`** — identical across consecutive dry runs; live endpoint returns the
  same value. Nothing was inherited from v1's dead fingerprint.
- Blockers, exactly:
  - 5 × camera — `Camera 'framing' is an unapproved AI suggestion ('…'). Approve or remove it
    before rendering.` (one per shot)
  - 5 × reference — `reference gate: Generation blocked: Scene scene_002 for setting scene_002.
    no approved canonical environment reference is available` (one per shot)
- No prompt-integrity blockers, no cost-gate blockers, no readiness blockers beyond the above.

## 4. Five shot summary (approved v2)

| # | Shot ID | sbs | Prompt sha16 (len) | Purpose | Image | Camera | Dialogue |
|---|---|---|---|---|---|---|---|
| 1 | `scene_002_shot_001` | `sbs_a7648698ad00` | `329b84e2f698f4ec` (3,200) | establishing_shot | previs storyboard frame (I2V asset) | framing AI_SUGGESTED; movement UNSPECIFIED | unassigned |
| 2 | `scene_002_shot_002` | `sbs_a8481a439ea5` | `7118ac1afd66b685` (3,012) | medium_shot | none | framing AI_SUGGESTED; movement UNSPECIFIED | unassigned |
| 3 | `scene_002_shot_003` | `sbs_be2cce8fab93` | `5b98c2831a9da5d8` (2,994) | close_up | none | framing AI_SUGGESTED; movement UNSPECIFIED | unassigned |
| 4 | `scene_002_shot_004` | `sbs_51d1500d227c` | `0e80c32afd7a576c` (3,003) | transition_shot | none | framing AI_SUGGESTED; movement UNSPECIFIED | unassigned |
| 5 | `scene_002_shot_005` | `sbs_0046fb5192f0` | `9bc47ad3336ac737` (3,074) | emotional_detail_shot | none | framing AI_SUGGESTED; movement UNSPECIFIED | unassigned |

Durations: template 5 s each (creator may re-author). No seed locked on any shot.

## 5. Remaining blockers (exact, fail-closed — none auto-resolved)

1. **Camera approval per shot (5)** — every framing is AI_SUGGESTED and blocks until you
   approve (`AI_CAMERA_APPROVED_BY_USER` stamp via the camera-plan flow on the board shot) or
   replace/remove it. Movement is clean/UNSPECIFIED everywhere (no edit-grammar tokens).
2. **Approved canonical setting reference for scene_002 (5)** — `reference_assets` has **zero
   rows for this project**; the setting gate blocks all five shots until an environment
   reference is approved. Available starting point: shot 1's previs storyboard frame
   `/previs-assets/project_5907c60cddbc/scene_002_shot_001_storyboard_qwen.png` (previously
   used as the environment row in a historical run) — approval is your call, not performed.
3. **DRE character reference resolution** — DRE resolves **1 approved** appearance-snapshot
   URL (`…/f98ad9ab5d1c48b79ad948c514ff64ea.png`) but holds **no character_reference_lock**
   (only a `provisional`/`unreviewed` lock on the old storyboard frame). Confirm it as the
   locked reference or lock an alternative. MAYA has 2 locked+approved locks.
4. **Dialogue assignment** — 10 lines unassigned (see §7).
5. **Model selection** — AUTO currently resolves gen4.5 (see §8); accept or override.
6. Non-blocking, untouched: scene_003 heading glue (`— NIGHTMaya`) in the master script —
   deliberately not repaired without your approval.

## 6. Camera decisions required (exact proposals — approve or replace per shot)

| # | Shot | Proposed framing (AI_SUGGESTED) | Other dimensions |
|---|---|---|---|
| 1 | `scene_002_shot_001` | "Wide establishing shot. Camera far back. Full environment visible." | size/angle/movement/lens UNSPECIFIED |
| 2 | `scene_002_shot_002` | "Medium shot. Characters from waist up. Action and dialogue beginning." | size/angle/movement/lens UNSPECIFIED |
| 3 | `scene_002_shot_003` | "Medium close-up. Character faces and upper body. Emotional beats." | size/angle/movement/lens UNSPECIFIED |
| 4 | `scene_002_shot_004` | "Dynamic medium shot showing the story transition in motion." | size/angle/movement/lens UNSPECIFIED |
| 5 | `scene_002_shot_005` | "Close-up detail shot. Eyes, hands, specific objects. Intimate beat." | size/angle/movement/lens UNSPECIFIED |

Nothing was approved automatically. Approving a shot's framing, or authoring replacements
(and optionally real camera movement), is an explicit per-shot creator action.

## 7. Reference decisions required

- **Setting (scene_002, blocking all 5 shots):** approve/upload a canonical environment
  reference. Nothing is currently approved; no reference was created or approved on your behalf.
- **DRE:** explicitly resolve — lock the existing approved appearance snapshot or supply a new
  reference. MOM must NOT be introduced into the scene: MOM (`chr_4c77bbd9be1e`) is not part
  of the canonical scene cast and appears in none of the five approved prompts (verified).

## 8. Dialogue assignment decisions required (all 10 canonical lines, script order)

Preserved exactly from the screenplay; **none assigned to any shot**. Assign via the existing
version-scoped Scene Direction interface
(`PUT /api/f51/studio/projects/project_5907c60cddbc/scenes/scene_002/direction` with
`expected_version_id`), leaving any line unassigned (`shot_id: null`) as you see fit. Saving
creates a NEW draft version (approval then resets — dialogue edits are themselves versioned).

| # | Character | Line (exact) | Suggested candidate (non-binding) |
|---|---|---|---|
| 1 | DRE | I need you to understand something. | shot 2 (scene opens two-shot) |
| 2 | MAYA | That's funny. | shot 2 |
| 3 | DRE | What? | shot 2 |
| 4 | MAYA | You always say that right before you do something you know is wrong. | shot 2 |
| 5 | DRE | Things changed. | shot 3 (close-up) |
| 6 | MAYA | No. People changed. | shot 3 |
| 7 | DRE | There's not enough. You have to understand that. There is not enough for everyone. | shot 3 |
| 8 | MAYA | So you decided that for all of us. | shot 4 (transition) |
| 9 | DRE | Someone had to. | shot 4 |
| 10 | MAYA | I remember dying. So why am I here? | shot 5 (emotional detail) |

These candidates are the board's segment-design reading of where each line falls — they are
**not assignments** and were not saved anywhere. Every line may also stay scene-level/unassigned.

## 9. Model resolution & cost estimate (informational — NOT generation authorization)

| Item | Value |
|---|---|
| AUTO resolution | `gen4.5` — "AUTO: registry-compatible default for the provider" |
| Durations | 5 × 5 s = 25 s · rate 12 credits/s |
| Per shot | 60 credits (estimated) |
| **Batch total** | **300 credits (estimated: true — local registry lookup, no provider contact)** |
| Cheaper first step | single-shot experiment: shot 1, I2V with its storyboard frame — 60 credits estimated |

Model selection is a preference record, never a generation authorization; nothing generates
until you explicitly trigger it after the gates are green.

## 10. Test results

- **Targeted integrity suite (this stage):** 165 passed — dialogue authority, prompt
  non-truncation, multishot integrity remediation, advisory camera/dialogue boundaries,
  scene segmentation boundaries, Scene Direction, generation-preflight route, storyboard
  blueprint service, scene production pipeline, generation context, reference validation,
  render state hardening, render scene-reference transition, model registry/router.
- **Full sweep:** **4060 passed, 10 failed, 13 skipped** (6m07s, isolated run).
  - The 10 failures reproduce deterministically standalone and are confined to the render
    persistence / provider-registry domain (render_job_persistence ×2, render_provider_safety
    seed-injection ×2, local LTX provider registry-count ×3, minimax registry-count ×1,
    LTX i2v fails-closed ×1, submit completion hooks ×1). They track the uncommitted
    local-provider expansion work on this branch (e.g. `assert 13 == 12` adapter count) and
    one cross-test isolation failure — **none touch scene_002, the dialogue authority, the
    board versioning, the preflight gates, or prompt integrity.**
  - The prior workstream's baseline suite (849 tests) is a subset of this sweep and passed
    within it; no integrity regression was introduced by this stage.

## 11. Ledger

- **Provider calls: 0** — no adapter that can reach a provider was invoked; the only
  persistence-path calls were the version approval API and the read-only preflight.
- **Credits consumed: 0** (Runway balance unchanged; nothing was estimated into spend).
- **Canonical mutations this stage:** storyboard version 2 status DRAFT → APPROVED (the one
  creator-directed action), plus its continuity-review metadata record. Nothing else — no
  screenplay bytes, no prompts, no camera values, no references, no dialogue, no model pin.

## 12. Next required creator action

Review §5–§9 and decide, in any order:
1. Camera per shot (approve or replace),
2. Setting reference for scene_002 (+ DRE lock; keep MOM out),
3. Dialogue assignment (or explicit dialogue-free),
4. Model (accept AUTO gen4.5 or pick explicitly).

Then re-run preflight; when it reads READY, generation remains your explicit, separate,
credit-spending decision. **This workstream stops here and waits for creator review.**
