# Runway 1000-Char Prompt Limit — Decision Brief (2026-10-17)

Read-only mission. No code, DB, provider, process, or branch state was changed.
The only filesystem change in this mission is this file.

## 1. Summary (10 lines)

1. Root cause of length: one string, `render_contract.provider_neutral_prompt`, is both the
   approved canonical text and the exact `promptText` sent to Runway; board assembly
   (`_build_provider_neutral_prompt`) concatenates plan-head + full scene-text action +
   cast/character looks + mood + rationale + locked-appearance tail with no length target.
2. The 2286-char scene_001 shot-1 prompt therefore exceeds gen4_image's documented
   1000-char cap by 2.3x, and the adapter fails closed by design (zero credits spent).
3. Scale is systemic, not a scene_001 outlier: measured scene_002 board prompts run
   ~3000-3290 chars (3x over); live DB histogram could not run here (no shell — queries provided).
4. The guard is `build_runway_image_request` (`runway_image_provider.py:340-353`); the 1000
   cap is corroborated for gen4_image (repo-verified 2026-09-27 + independent web check).
5. The never-truncate rule is load-bearing: frozen-contract digests, storage gates, prompt-
   integrity gates, and approval semantics all assume byte-exact canonical prompts.
6. Recommendation, in order: (D) length validation at board creation/approval with a clear
   message first; then (A) a separate approved Runway-targeted image-prompt field, authored
   via (B) deterministic logged compaction linked by hash; (C) reference images opportunistically.
7. Option E (route storyboard through the Model Router, 32k image cap) is recorded but not
   recommended now: it changes the spend/authority surface (cf. D3, G3) to dodge a content problem.
8. Any auto-rewrite of the approved canonical string without a new version + re-approval is
   a silent alteration of user-approved text and is explicitly out (breaks digests, D2, approval).
9. scene_001 has prior gates anyway (draft board, no canonical env ref for loc-b543d669,
   empty camera fields); the length fix belongs BEFORE approval, since approval freezes text.
10. Open owner question: the board prompt is a Chicago L-train golden-hour establishing shot,
    not the pavilion prompt pasted earlier — confirm which is canonical for scene_001. (D4 below.)

## 2. Prompt segment breakdown (board row sbs_15ee23ce9296, board sbp_project_5907c60cddbc_scene_001_ec41ca26)

### 2.1 One string serves every purpose — no separate image prompt exists

- The stored canonical field is `StoryboardShotRenderContract.provider_neutral_prompt`
  (`studio-backend/app/models/storyboard_blueprint.py:117-129`).
- The failed render path forwards it verbatim:
  `routes/__init__.py:525` `generate_scene_storyboard`
  → `storyboard_blueprint_service.py:679` `generate_storyboard_image_for_scene_shot`
  → `:774-780` `_refresh_prompt_with_locked_characters` (appends locked block only if absent)
  → `:815-828` `storyboard_image_service.generate_runway_image`
  → `providers/runway_image_provider.py:submit_runway_image_render` → `:332-353`
  `build_runway_image_request` (guard).
- Byte-identity is asserted, not incidental: `scripts/live_runway_image_smoke_test3.py:277-312,395`
  compares sha256 of canonical prompt vs wire `promptText` vs stored `prompt_used`.
- No `image_prompt`, `runway_prompt`, or shortened variant field exists anywhere on the
  board models, storage rows, or DTOs (searched `image_prompt`, `runway_prompt` — no hits
  on the storyboard path). The casting path's inline `Avoid:` clause
  (`adapters/casting_image_adapter.py:138-146`) is NOT used by the storyboard path.

### 2.2 Assembly chain that produced the 2286 characters

Built once at board creation in `_build_initial_shots` via
`_build_provider_neutral_prompt` (`storyboard_blueprint_service.py:1204-1257`):

```
stored_prompt = plan_head + ". " + build_shot_aware_prompt(...) + ". " + rationale
                (+ locked-appearance tail re-ensured exactly once)
at render:      + locked block appended ONLY if "Locked appearance" absent (:774-780, :1835-1846)
                + "[CREATOR CAMERA PLAN ...]" ONLY if a camera_plan was passed (:741-772; not this call)
```

| # | Segment | Built by (file:line) | Size |
|---|---|---|---|
| 1 | Plan head: framing + camera_movement + environment + lighting + "Shot 1 of N.", joined ". " | `storyboard_blueprint_service.py:1229-1241` from `visual_plan` (`:1127-1142`); camera_movement forced "" unless transition_hint has a space and len>12 (`:1126`) | Variable (DB; framing template + location + time/tone + ~12 chars) |
| 2 | Shot-type template (shot 1 = wide establishing) | `shot_prompt_builder.py:52-56` (`SHOT_FRAMING_BY_POSITION[1]`), via `build_shot_aware_prompt` (`:360-368`) | **121 chars, exact** (counted from source) |
| 3 | Location + time of day | `shot_prompt_builder.py:370-375` from scene fields | Variable (DB; "DOWNTOWN CHICAGO … GOLDEN HOUR" family) |
| 4 | Action: first 2 ACT/DLG/None lines of this shot's scene-text segment | `shot_prompt_builder.py:377-386`, segmented by `_segment_scene_text` (`:106-148`), classified by `_classify_script_line_tag` (`:76-103`) | Variable, largest text share (scene_001 Chicago L-train action prose) |
| 5 | Cast guard "Only A and B visible. No extras." | `_format_visible_cast_constraint` (`:294-301`), names from `_extract_characters_from_segment` + `_merge_scene_characters` (`:150-216`) — note: scene-cast merge can ADD names beyond the shot segment | Variable (~30-80 chars) |
| 6 | Character looks "Characters: Name (age): visual…" (max 3) | `shot_prompt_builder.py:388-403`; locked looks use `appearance_description` | Variable, large (each approved look is a full physical description) |
| 7 | Mood ("Mood: …") | `shot_prompt_builder.py:407-411` from audio_brief or scene emotional_tone | Variable (tens of chars) |
| 8 | Performance visible lines (max 2) | `shot_prompt_builder.py:415-421` | Variable (often empty) |
| 9 | Style suffix "Cinematic, film quality, single continuous shot." | `shot_prompt_builder.py:424` | **48 chars, exact** (counted from source) |
| 10 | Locked-appearance tail "Locked appearance - maintain exact look, …: Name (age): …; …" | `build_locked_appearance_block` (`:228-275`) + `ensure_locked_appearance_in_prompt` (`:278-290`); re-ensured after join at `storyboard_blueprint_service.py:1245-1255` ("exactly once so it is never truncated away", `:1247`) | **88-char fixed prefix** (counted) + full per-character descriptions (duplicates seg. 6 content by design — non-truncatable) |
| 11 | Rationale (shot_rationale_service text) | `storyboard_blueprint_service.py:1139-1151` (prompt arg) joined at `:1243` | Variable (DB; present — this is the "reference notes"-like free text on this path) |
| 12 | Creator camera plan block | `:741-772` — **absent** in the failed call (no camera_plan passed; shot-1 camera fields are empty) | 0 chars here |

What is NOT in the 2286: negative/avoid text (no negative prompt exists on this path;
`negative_visual_constraints` is a model-only field — `models/storyboard_blueprint.py:93` —
with zero consumers in prompt assembly); reference images (travel as `referenceImages`,
max 3, never as text); continuity_plan object fields (enter only indirectly via scene
location/tone); seed/ratio (wire fields, not text).

Why it totals 2286: segments 4+6+10+11 are unbounded scene/character/rationale prose with
no budget anywhere upstream (§3.3), and the locked-look content is deliberately duplicated
(segments 6 and 10) as non-truncatable identity enforcement. Fixed templates contribute
only ~170-260 chars; the remaining ~2000+ are scene text + character descriptions +
rationale + locked tail.

## 3. Guard findings and integrity dependencies

### 3.1 The guard (file:line)

- `studio-backend/app/services/providers/runway_image_provider.py:97-98`:
  `_RUNWAY_MAX_PROMPT_LENGTH = 1000` ("Fail-closed request constraints (verified gen4_image schema, 2026-09-27)").
- Guard at `:340-353` (`build_runway_image_request`): empty prompt and `len(clean_prompt) > 1000`
  raise `ValueError("Runway image prompt exceeds the 1000-character limit (2286 characters);
  the canonical prompt is never truncated — fail closed instead.")`.
- Failure is pre-submit (10ms, no task created): `storyboard_image_service.py:104-125` maps it to
  `ProviderError(provider=runway, model=gen4_image, reason=runway_image_provider_failed)` →
  HTTP 502 via `routes/__init__.py:548-551`. Zero credits consumed.
- Sibling caps (NOT the failing one, for context): router image 32000 / router video 20000
  (`runway_router_provider.py:551-561,653-663`, same never-truncate wording);
  video-path provider budget 512 via `prompt_budget_service.prompt_policy` (conservative
  application ceiling, explicitly "model-specific maximum unverified").

### 3.2 Why the canonical prompt must never be truncated

- `shot_prompt_builder.py:405-413` (canonical-creative-integrity rule, Multi Shot audit Phase 1):
  `build_shot_aware_prompt` "MUST NOT cut the canonical prompt at this ceiling or any other";
  `max_length` param is accepted and deliberately ignored (`:340-358` docstring); over-budget
  prompts are "an explicit readiness concern handled by prompt_budget_service (fail-closed)".
- `prompt_integrity.py:1-51`: detection is "mechanical and read-only: it never rewrites, repairs,
  or summarizes"; corruption artifacts come from the historical 512-char truncation (H-3).
- `docs/multishot_integrity_audit.md:423` (H-3 fix): "Existing canonical prompts are never
  rewritten by application logic"; `docs/runway_model_router/FINAL_REPORT_20260928.md:130`:
  "never truncated anywhere"; `docs/forensics/SCENE002_GENERATION_PREFLIGHT_20260928.md:245-256`.
- Guard tests pinning this: `tests/test_storyboard_prompt_no_truncation.py`
  (no-truncation + corruption-detection suites), `tests/test_runway_image_provider.py:785`
  (over-1000 raises), `tests/test_checkpoint_4b_previs_integrity.py:448` (long-text builder test).

### 3.3 Integrity-chain / digest / freeze dependents (all assume byte-exact prompts)

- `FrozenGenerationContract.prompt` (`services/generation_contract.py:241-242`) is covered by
  `creative_digest()` (`:312-316`, sha256 over canonical payload JSON); `from_record` (`:324-330`)
  rejects tampered payloads; adapter replay checks digest equality
  (`adapters/__init__.py:2277-2306`, `frozen_contract_digest_mismatch` fails closed).
- Storage choke-point: contract-less `runway_router` rows raise
  (`app/data/storage.py:6325-6334`) — the D1 backstop (`R4.3I-owner-decisions.md`).
- Approval/version pinning: `scene_render_inputs` requires approved==current
  (`storyboard_blueprint_service.py:936-938`); previs `_storyboard_context` requires approved
  version + non-empty prompt + corruption check (`previs_service.py:140-185`);
  `inspect_scene_direction_snapshot.py:358-384` pins per-shot prompt sha256 hashes.
- Contract-freeze: `freeze_generation_contract` (used across pipeline tests/services);
  `shot_manifest.py:89` manifest digests; `reference_binding_digest` frozen bindings
  (`scene_production_pipeline_service.py:2330-2333`).

### 3.4 Is 1000 Runway's documented gen4_image limit? Is it per-model?

- Repo claim: module docstring (`runway_image_provider.py:24-31`) cites the official Runway Dev
  API reference (`docs.dev.runwayml.com/api.md`, OpenAPI `openapi.json`, verified 2026-09-27):
  "`promptText`: non-empty, max 1000 characters (UTF-16 code units)".
- Independent check (this mission, web researcher agent): corroborates **1000 UTF-16 code units
  for gen4_image**, and confirms the cap is **per-model** (e.g. other text_to_image models carry
  4000 / 5500 / 32000 caps per Runway's API changelog). So changing models changes the limit.
- Confidence: **high** that 1000 is gen4_image's documented cap (two independent sources agree,
  plus the repo's dated verification); **medium** on first-hand schema re-read today (the API
  reference page was too large for the reader to extract and the Gen-4 help page returned 403;
  full URLs in appendix). Recommendation: re-verify against the live OpenAPI spec during
  implementation (5-minute task, in the draft scope below).

## 4. Scale histogram

### 4.1 Live counts: BLOCKED (no execution environment), queries provided

This mission had no working shell (see appendix), so no `sqlite3`/`python` could run and
`studio.db` was never opened (per §0 it must be `mode=ro` anyway). The exact histogram must be
produced with these read-only statements before implementation:

```sql
-- per-shot lengths for one board (scene_001 reproduces the 2286 figure)
SELECT shot_id, storyboard_shot_id, LENGTH(
  json_extract(render_contract_json, '$.provider_neutral_prompt')) AS prompt_len
FROM storyboard_shots WHERE blueprint_id LIKE 'sbp_project_5907c60cddbc_scene_001%';
-- histogram across all projects (adjust column access to the local schema:
-- storyboard_shots rows carry render_contract with provider_neutral_prompt)
SELECT CASE WHEN L<=1000 THEN '<=1000' WHEN L<=1500 THEN '1001-1500'
  WHEN L<=2000 THEN '1501-2000' WHEN L<=3000 THEN '2001-3000' ELSE '>3000' END AS bucket,
  COUNT(*) FROM (SELECT LENGTH(render_contract_provider_neutral_prompt) AS L
  FROM storyboard_shots) GROUP BY 1 ORDER BY 1;
```

(Python alternative, read-only: `sqlite3.connect('file:studio-backend/data/studio.db?mode=ro', uri=True)`
and SELECT only. Table/column shapes per `app/data/storage.py` storyboard-shots section and
`tests/test_scene002_creator_decision_capture.py:629-684`, which documents the live-digest
SELECT pattern.)

### 4.2 Proxy evidence (measured, on record — every sample exceeds 1000)

| Project / scene / shot | Prompt chars | Source |
|---|---|---|
| project_5907c60cddbc scene_001 shot 1 (sbs_15ee23ce9296) | **2286** (2.29x over) | Live 502 error + server log, AUDIT §9.6 |
| scene_002 v2 shots 1-5 | 3200 / 3012 / 2994 / 3003 / 3074 (3.0-3.2x over) | `docs/scene_002_final_creator_review_package.md:113-117` |
| scene_002 verified prompts | 3084-3290 | `docs/forensics/SCENE002_GENERATION_PREFLIGHT_20260928.md:252-256` |

Working conclusion (to be replaced by the histogram above): the overage is systemic —
100% of measured board prompts exceed the cap by 2-3.3x, so the fix must handle the
common case, not scene_001 as an exception.

### 4.3 Board generator length target today: NONE effective

- `max_length=512` passed at `storyboard_blueprint_service.py:1222` is deprecated/ignored by
  the builder (`shot_prompt_builder.py:340-358`).
- `StoryboardShotContinuityPlan` sub-fields cap at 1500 (`models/storyboard_blueprint.py:104-106`)
  — Pydantic field validation, not a prompt target, and those fields do not enter prompt text directly.
- `intent.source_scene_text_excerpt = scene_text[:500]` (`:1149`) is provenance metadata, not prompt.
- `approve_version` (`storyboard_blueprint_service.py:381-421`) checks render blockers + completed
  continuity review — never length. No creation-time or approval-time length gate exists (the gap
  option D fills). `SLOT_BUDGETS` (`shot_prompt_builder.py:19-27`) bind only the standalone slotted
  preview, explicitly not the canonical board prompt.

## 5. Options table and recommendation

Legend — Integrity: effect on digests/approval semantics. D1/D2/D3: accepted owner decisions
(`reports/studio-readiness-audit-2026-10-14/R4.3I-owner-decisions.md`: D1 accept save_job writers,
D2 single-job digest by design, D3 simulated-only canonical previs).

| Opt | Sketch | Files / areas touched | Integrity + digests | D1/D2/D3 | Test impact | Effort | Risks |
|---|---|---|---|---|---|---|---|
| A | Board generator authors a separate Runway-targeted `image_prompt` (≤1000) beside the full `provider_neutral_prompt`; separately approved field | `models/storyboard_blueprint.py` (new contract field), `_build_provider_neutral_prompt` + `_build_initial_shots`, storage serialization, storyboard routes/DTOs, `generate_storyboard_image_for_scene_shot` (send image_prompt, keep canonical as `prompt_used`), frontend display | Clean IF the new field is versioned + approved alongside canonical and digests cover both (extend `creative_digest` payload or pin image-prompt sha in manifest). Canonical bytes untouched | Neutral (no new writers of authority; approval semantics preserved) | New contract/round-trip tests; update sha-assertion helpers (smoke test); frontend tests for new field | M | Two texts can drift (which is "the" prompt?); review burden per shot; stale image_prompt after canonical edits needs invalidation rule |
| B | Deterministic logged compaction producing a derived prompt, canonical untouched, derived record links by hash | New `prompt_compaction_service` (or extend `prompt_budget_service`), derivation record (input sha256, rules version, output), wire into storyboard image path after approval | Safe IFF derived output is stored separately with input-hash link + rules version and re-derived deterministically (same input → same output); verifiers recompute. Canonical never edited | Neutral if derived record cannot authorize anything alone (D1 tripwire: it must not become a writer that mints success state) | Adversarial tests (`test_prompt_budget_adversarial.py` pattern): determinism, no silent drop of required facts, over-limit still fails closed | M | Any nondeterminism (LLM summarizer) destroys verifiability — must be rule-based; "compaction" that drops required facts silently = integrity violation by another name |
| C | Move setting/character/continuity detail into reference images, shrink text | Mostly editorial + existing machinery: `referenceImages` max 3 already forwarded (`runway_image_provider.py`, `_locked_reference_images_for_scene`); approval/designation flow (`routes/reference_assets.py:264,337,377,403`); board text trims | Positive (less text under digest, same bytes rule); references already have their own approval/canonical + fingerprint checks (`scene_production_pipeline_service.py:2295-2320`) | Neutral | Reference-forwarding tests exist; needs per-shot reference-sufficiency tests | S (infra) + ongoing editorial | Max 3 refs; env/wardrobe nuance that only text carries may be lost; does not fix character-description bloat alone; needs canonical env refs to exist (scene_001's loc-b543d669 has none) |
| D | Length validation at board creation AND approval: overlong prompts blocked at the gate with a clear message | `_build_initial_shots`/`create_version` (warn/collect), `approve_version` (hard gate or blocking warning), `_inspect` blockers, frontend board UI messaging | Positive (pure gate, zero canonical mutation; blockers already flow through `render_blockers` → approval refuses) | Neutral; consistent with D2's fail-closed posture | Gate unit tests (boundary 1000/1001), approval-blocked tests, UI message tests | S | Alone it converts a render-time 502 into a board-time blocker — necessary but not sufficient; without A/B the creator has no in-app path forward (must hand-edit scene/characters) |
| E1 | Route storyboard images through the Model Router (image input cap 32000) instead of direct gen4_image | `storyboard_image_service` (seam call), provider selection, router config/eligibility, cost accounting, `prompt_budget_service` router branch already exists | Neutral-to-negative: prompt stays exact, BUT moves storyboard onto the router authority surface (frozen-contract storage gate, manifest digests, `authorize_runway_submission`) | **Touches D2/D3**: single-job router work outside the pipeline is intentionally impossible today; storyboard is outside the D3 simulated-only guard (audit G3) — E1 widens live-spend surface | Router + authorization + reconciliation suites | M | Dodges a content problem with a provider change; per-model `prompt_length` filter may still refuse gen4_image routing for 2286 chars (filter owns eligibility); cost/observability changes |
| E2 | Creator trims scene text / defers locked looks, then regenerates (manual, today's only path) | No code (operator action) | Clean (new version + re-approval) | Neutral | None | S (per shot, manual) | Unscalable given §4.2 (every shot 2-3x over); pressures creators to cut identity enforcement (locked tail) — the worst segment to cut |

### Recommendation (ordered combination)

1. **D first (immediate, S).** Fail fast with a clear, actionable message at creation/approval
   instead of a 502 at render time. Include per-segment lengths in the message (reuse the §2
   accounting) so the creator sees WHAT is long.
2. **A, authored via B (structural, M+M, one project).** The separate approved `image_prompt`
   is the durable fix; B is its authoring mechanism (deterministic, rule-based, hash-linked,
   separately approved — never an overwrite of canonical). A without B means hand-writing every
   image prompt; B without A has nowhere to store its output. Ship together.
3. **C opportunistically.** Approve the loc-b543d669 environment reference and character face
   refs anyway (scene_001 needs them regardless, §6); every approved reference is text that can
   leave the prompt later.
4. **Not now: E1.** Revisit only if A proves editorially unworkable; E1 trades a content fix for
   authority-surface expansion and may still be refused by the router's per-model filter.

### Explicit silent-alteration flags

- 🔴 **Would silently alter user-approved text:** any truncation, summarization, or "compaction"
  applied to `provider_neutral_prompt` in place (including "just cut the rationale" or "drop the
  locked tail to fit") without a new board version + re-approval. This breaks `creative_digest`,
  snapshot prompt hashes, D2's pipeline guarantee, and approval semantics. Includes E2 variants
  that auto-trim.
- 🟢 **Does NOT silently alter:** D (gate only, no mutation); A (new field, both approved);
  B as specified (derived record, hash-linked, deterministic, separately approved); C (references
  are explicit creator approvals); E2 manual (creator edits + regenerate + re-approve).

## 6. Remaining scene_001 blockers — correct gate order (no fixes applied)

Recorded preflight state (mission brief; code refs confirm the gates exist): board in draft
(`approved_version_id=None`), no canonical approved environment reference for setting
loc-b543d669, empty camera fields on shot 1. Plus content-authority question: the board prompt
is a Chicago L-train golden-hour establishing shot ("EXT. DOWNTOWN CHICAGO — GOLDEN HOUR"
scene family; cf. `test_scene_segmentation_boundaries.py:9`, benchmarks prompts), not the
pavilion prompt the owner pasted earlier.

Correct unblock order (each gate's code ref):

1. **Settle scene_001 content authority (owner).** Which is canonical: Chicago L-train board
   text or the pavilion prompt? If pavilion, scene text must be updated and the board
   regenerated — everything below re-runs. Do this first; it invalidates all downstream artifacts.
2. **Designate + approve the canonical environment reference for loc-b543d669**
   (`routes/reference_assets.py:337` register → `:403/:264` approve → `:377` designate canonical;
   pipeline enforces approved+canonical at `scene_production_pipeline_service.py:2278,2301`).
   Needed for video; also feeds option C. (Mission's earlier walk-through confirmed the
   authority endpoints exist and the setting gate is enforced.)
3. **Camera: decide/approve shot-1 framing.** Empty fields are NOT a storyboard-image blocker
   (that route never checks camera), but ARE a downstream video blocker: heuristic/template
   values stay AI_SUGGESTED/UNSPECIFIED until explicit approval (`generation_context_service.py`
   provenance rules; ONLY `PrevisService.approve_ai_camera` promotes, `previs_service.py:674`).
   Approve or author before expecting video.
4. **Prompt-length fix lands HERE — before approval.** (Re)generate the board so prompts are
   length-validated (D) and carry the approved image-prompt field (A/B); run continuity review
   (required by `approve_version`, `:409-415`); then approve (sets `approved_version_id`, `:427`).
   Approval freezes bytes — any length work after approval forces a new version + re-approval.
5. **Storyboard image render** (the previously failing call): passes the 1000-char guard with the
   image prompt; `prompt_used` records the canonical for provenance (keep the sha comparison).
6. **Video pipeline gates** (frozen contract + reference authority + camera provenance + cost),
   then screening.

## 7. Owner Decision D4

**Decision required (D4): how Studio handles board prompts longer than Runway's 1000-char
gen4_image limit. Recommendation: D now + A authored via B, C opportunistically (see §5).**

| Option | One-line | Commits the project to |
|---|---|---|
| A | Separate approved Runway image prompt (≤1000) beside full canonical | A new versioned+approved prompt field; digest coverage for two texts; drift/invalidation rules; per-shot review of image prompts |
| B | Deterministic logged compaction, hash-linked, canonical untouched | A rule-based (never LLM-free-text) derivation service with stored provenance; "same input → same output" as a tested invariant |
| C | Detail into reference images | Approving/canonicalizing env + face refs as a standing practice; accepting 3-ref ceiling and text loss where refs can't carry nuance |
| D | Length validation at creation/approval with clear message | Gate wording + thresholds owned by Studio (re-verify 1000 against live spec); board-time blockers instead of render-time 502s |
| E1 | Router path (32k cap) for storyboard | Router authority/cost surface for storyboard; D2/D3 re-examination; possible per-model filter refusal anyway |
| E2 | Manual trim + regenerate (status quo fallback) | Nothing in code; per-shot editorial labor forever; pressure to cut identity text |

**My recommendation: approve D + A(via B) + C-in-passing.** D is uncontroversial and immediate.
A+B is the only option that preserves byte-exact canonical approval AND gives every shot a
renderable image prompt without per-shot heroics. C work (env/face refs) is needed for
scene_001 regardless. Reject silent in-place rewrites (§5 flags) and defer E1.

**What each choice commits to** (irreversible-ish parts): A commits to dual-text governance
forever; B commits to maintaining derivation rules + provenance store; E1 commits to router
authority expansion (hardest to unwind — touches D2/D3). D and C are cheap to unwind.

## 8. Draft title and scope for the implementation prompt

**Title:** "Board prompt-length gates + approved Runway image prompt (D4: D now, A via B)"

**Scope (for the follow-up implementer, not this mission):**
1. Re-verify 1000 UTF-16 units against the live Runway OpenAPI spec (`docs.dev.runwayml.com/openapi.json`); record outcome + date in code comment.
2. Run the §4.1 histogram (read-only) and paste results into the implementation plan.
3. D: length check in `_build_initial_shots`/`create_version` (advisory w/ per-segment lengths) + hard gate in `approve_version` via `render_blockers`; UI message; tests at 1000/1001 boundary.
4. A+B: new approved `image_prompt` field (model → storage → DTO → route → `generate_storyboard_image_for_scene_shot` sends it, canonical stays `prompt_used`); deterministic rule-based derivation service with hash-linked record; digest/manifest coverage for both texts; determinism + adversarial tests.
5. C support: surface "approving this reference removes ~N chars" hint where measurable (optional).
6. Layered tests (unit + integration + API), tsc + vitest + pytest green; no D1/D2/D3 semantic changes; no canonical mutation paths.
7. Out of scope: router rerouting (E1), auto-rewriting canonical text, frontend Runway-label cleanup (G7), provider unification (G5/G6).

## 9. Appendix

- **HEAD:** `04b3fb6c71ba7a5dfafaefeb7f41a39e4cff498e` (branch `backend-expansion-dependency-slicing`;
  matches AUDIT_2026-10-17 §8; confirmed by direct `git rev-parse HEAD` at mission start).
- **Starting status:** dirty tree (pre-existing uncommitted changes, not mine) — first `git status
  --short` showed the same modified set as the audit (reports, studio-app, studio-backend, .env, etc.).
- **Shell limitation (stop-condition adjacent, reported not continued-through):** after one successful
  command, the execution shell became unavailable (`posix_spawn 'bash'` ENOENT on every subsequent
  attempt, 3 tries). Consequently: no live `SELECT`s (§4.1 queries provided instead), no test runs,
  no reusability check of `git status` at mission end. No writes, restarts, commits, or provider calls
  were attempted or needed. DB files were never opened.
- **Only change:** this file. All investigation was read-only (`read_files`/`code_search`); one
  `researcher-web` subagent performed read-only web verification (no credentials, no posting).
- **Commands run:** `git rev-parse HEAD` ✓; `git status --short | head -50` ✓ (dirty, pre-existing);
  `git status --short | wc -l` + sqlite/python attempts ✗ (shell unavailable).
- **Files read (primary):** `docs/audits/AUDIT_2026-10-17.md` (full §1-9);
  `studio-backend/app/services/providers/runway_image_provider.py` (full);
  `studio-backend/app/services/providers/runway_router_provider.py` (`:530-679`);
  `studio-backend/app/services/storyboard_image_service.py` (`:1-260`);
  `studio-backend/app/services/storyboard_blueprint_service.py` (`:679-938`, `:1120-1319`, `:1594-1873`, `approve_version :381-421`);
  `studio-backend/app/services/shot_prompt_builder.py` (builder core + budgets);
  `studio-backend/app/services/prompt_budget_service.py` (`:1-120`);
  `studio-backend/app/services/prompt_integrity.py` (full);
  `studio-backend/app/services/generation_contract.py` (`creative_digest` region);
  `studio-backend/app/models/storyboard_blueprint.py` (`:60-159`);
  `studio-backend/app/services/previs_service.py` (`_storyboard_context :130-185`, `generate_scene` guards);
  `studio-backend/app/services/scene_production_pipeline_service.py` (`:2255-2354`);
  `studio-backend/app/routes/__init__.py` (`:520-563`); `studio-backend/app/adapters/casting_image_adapter.py` (`:120-156`);
  `reports/studio-readiness-audit-2026-10-14/R4.3I-owner-decisions.md` (D1-D3);
  `docs/forensics/SCENE002_GENERATION_PREFLIGHT_20260928.md` (`:230-289`);
  `docs/scene_002_final_creator_review_package.md` (`:105-117`).
- **Searches:** guard strings (`1000-character limit`, `never truncated`, `gen4_image` — 57 hits);
  board-row IDs (0 code hits — DB-only, as expected); `GOLDEN HOUR` (scene_001 family);
  `approved_version_id` (106 hits, gate map); digest/sha256 consumers (151 hits);
  `AI_SUGGESTED` (82 hits); `NEGATIVE_PROMPT`/`Avoid:` on storyboard path (0 hits);
  `image_prompt` field (0 hits — confirms no separate field).
- **Secrets:** none printed (env var names only, per §0).
- **Status confirmation:** shell unavailable for end-of-mission `git status`; by construction the
  only write performed was this file via the file tool (all other tool calls were reads).
  Recommend the owner run `git status --short` to confirm only
  `docs/audits/PROMPT_LENGTH_DECISION_2026-10-17.md` is added.

## 10. D4 Implementation Log

Implementation date: 2026-10-17. Owner decision D4 built as specified; C and E1
stayed out of scope; Runway remains the only production provider (no providers added).

### Files changed (backend)
- NEW `studio-backend/app/services/runway_prompt_length.py` — single source of
  truth: `RUNWAY_IMAGE_MAX_PROMPT_UTF16 = 1000`, `utf16_length()` (counts UTF-16
  code units, not Python chars), `canonical_sha256()`. Unit-tested with emoji /
  non-BMP characters. The existing provider guard now measures with this helper;
  strictness unchanged (still fails closed).
- NEW `studio-backend/app/services/runway_image_prompt_compactor.py` —
  deterministic compactor (`COMPACTOR_VERSION`), no LLM, no randomness. Segments
  the canonical prompt by the assembler's own structure (plan-head, action,
  cast looks, mood, rationale, locked-appearance tail), keeps subject/action +
  setting first, then camera/lens/lighting, then essential looks, then mood;
  drops rationale and exact duplicates first, whole clauses only, recording each
  dropped segment and chars removed per rule. Returns ok=false with a clear
  message when it cannot fit 1000 units. Every output is a PROPOSAL.
- NEW `studio-backend/app/services/storyboard_image_prompt_service.py` —
  service layer (route → service → storage; routes never touch storage):
  `derive_for_shot`, `edit_for_shot` (limit-enforced, origin=human, back to
  proposed), `approve_for_shot` (only from unapproved/ready; never approves the
  board), `status_for_shot` (missing | stale | over_limit | unapproved | ready),
  `gate_for_version`, `approved_digest_for_shot`, `approved_prompt_for_shot`
  (render-path accessor, fails closed). Canonical changes flip the record STALE
  via `source_prompt_sha256` mismatch; the gate treats stale as missing.
- `studio-backend/app/data/storage.py` (+160) — ADDITIVE ONLY: new nullable
  table `storyboard_image_prompts` (per-shot image prompt + source_prompt_sha256,
  origin, compactor_version, rules_applied_json, dropped_segments_json,
  canonical_utf16, utf16_length, chars_removed, status, approved_by/at,
  timestamps) plus `get/save_storyboard_image_prompt`. No columns altered.
- `studio-backend/app/services/storyboard_blueprint_service.py` (+502/-~40) —
  proposals auto-derived (best-effort, warn-only) on create/regenerate;
  `get_blueprint_detail` returns non-blocking `image_prompt_gate` +
  per-shot `image_prompts` (render_ready/state/gate_message/canonical_utf16)
  and appends gate warnings to inspection warnings; `approve_version` BLOCKS on
  missing/stale/unapproved/over-limit image prompts (canonical length never
  blocks); approved image digest pinned into the contract-freeze chain;
  `render_storyboard_shot` + Runway storyboard generation use ONLY the approved
  image prompt for promptText and fail closed BEFORE any provider call;
  pre-existing check order preserved (render blockers → continuity review →
  image gate) so the "Continuity Review" error still fires first. New
  `derive_and_approve_image_prompts_for_version` bulk helper (explicit human
  gesture, never automatic).
- `studio-backend/app/services/providers/runway_image_provider.py` — guard
  measures with `utf16_length()`; same fail-closed strictness.
- `studio-backend/app/routes/storyboard_blueprints.py` (+106) — thin routes:
  GET/POST-derive/PUT-edit/POST-approve per-shot image prompt; detail routes
  serialize the new gate fields.
- `studio-backend/app/routes/projects.py` (+15) — generation-preflight exposes
  per-shot render-readiness so the UI can show what is not render-ready and why.
- Pollinations/legacy paths behave exactly as before (no gate, canonical text).

### Files changed (frontend)
- `studio-app/src/lib/studioApi.ts` — `RUNWAY_IMAGE_PROMPT_LIMIT`,
  `utf16Length()` (JS `length` IS UTF-16 units), `StoryboardImagePromptEntry` /
  `Gate` types, `StoryboardBlueprintDetail.image_prompt_gate/image_prompts`,
  four client functions (get/derive/edit/approve).
- NEW `studio-app/src/components/StoryboardImagePromptPanel.tsx` — per-shot
  panel (Command HUD styling, no redesign): canonical UTF-16 length, image
  prompt text, red counter over 1000, compactor "removed" summary, edit box,
  Re-derive / Save edit / Approve prompt buttons, stale/missing/over-limit
  states with the gate's message. Never auto-approves.
- `studio-app/src/pages/PrevisRoom.tsx` (+39) — panel mounted in the blueprint
  step for the active shot (disabled once the board is approved).
- Scoping note: ProductionBoard is scene-level (no per-shot data; its copy
  already defers shot review to Previs via "Review storyboard"), so the panel
  lives on the Previs review surface where shot data exists.
- NEW `studio-app/src/components/StoryboardImagePromptPanel.test.tsx` — 8
  tests (UTF-16 counting incl. emoji, removed summary, states, explicit
  approve, edit error surfacing, no auto-approve on render).

### Files changed (tests, backend)
- NEW `studio-backend/tests/test_d4_image_prompt.py` — 16 tests, temp DBs only:
  length util, compactor determinism/fit/failure, derive→edit→approve flow,
  stale-on-canonical-change, approval BLOCKS on missing/stale/unapproved/
  over-limit, canonical length never blocks, render uses approved text and
  fails closed pre-provider, digest pinning, additive migration on temp DBs.
- Updated to the D4 workflow (derive+approve before board approval, via routes
  or the bulk helper; no production behavior weakened): `test_storyboard_`
  `blueprint_service.py`, `test_checkpoint_4a/4b`, `test_checkpoint_5_thread`,
  `test_multishot_integrity_phase6_e2e`, `test_camera_presets` (provider-failure
  test now saves the camera plan via the legacy path, re-derives+approves, then
  exercises the Runway failure), `test_generation_preflight_route`,
  `test_storyboard_blueprint_routes`, `test_storyboard_qwen_route` (gate
  accessor stubbed — route-defaulting is its subject; gating is D4-tested).

### Brief-vs-code differences (code trusted, per §1)
- Deprecated `max_length=512` confirmed display-only/ignored for canonical text.
- Camera-plan-in-generate and locked-look refresh mutate canonical in place, so
  a same-call camera edit correctly stales the image prompt (re-derive +
  approve is the designed next step).
- `storyboard_image_prompts` is a new table (not nullable columns), the most
  additive option; existing digests untouched for existing data.

### Test outcomes
- Backend (`R43K_SOCKET_ONLY=1`, temp DBs, no provider calls): final full run
  **5067 passed, 15 skipped, 0 failed**. Mid-work full run showed 3 failures,
  all pre-existing tests hitting the new gate; fixed by adopting the D4
  workflow (above), not by weakening the gate. No "before" full-suite count
  was taken (tree carries many pre-existing uncommitted changes; stash/reset
  forbidden), so no before/after delta is claimed.
- Frontend: `tsc --noEmit` clean; full vitest **132 files / 1057 tests passed**
  (includes the 8 new panel tests).
- Migration verified on temp DBs only (D4 suite). Live `studio.db` untouched,
  backend not restarted, no board regenerated, nothing approved, nothing
  rendered — per §8 STOP.

### Live-run proposal (awaiting explicit approval; DO NOT RUN YET)
1. `cp studio.db studio.db.pre-d4-<timestamp>.bak` (timestamped backup).
2. Apply the additive migration (creates `storyboard_image_prompts` only).
3. `PRAGMA integrity_check` — proceed only on `ok`.
4. Restart via the launchd submitted job `com.aifilmstudio.backend` with
   `DASHSCOPE_*` unset and `DEFAULT_IMAGE_PROVIDER=runway`,
   `RUNWAY_API_ENABLED=true`, `R43K_SOCKET_ONLY=1`.
5. Verify `/health` + provider resolution (no provider call).
- Board regeneration (scene_001 Chicago golden-hour L-train establishing shot,
  same authoring path; no cliffside pavilion) makes NO paid/external calls —
  it is fully internal (prompt assembly + deterministic compaction). The only
  paid step would be a Runway render submit, which is explicitly NOT proposed:
  no approval, no render until owner review.
