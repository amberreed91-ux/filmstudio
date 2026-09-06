# Prompt Adherence & Character Consistency — Gap Analysis

**Date:** August 15, 2026
**Scope:** `studio-backend/app/services` — adherence, retry, slot assembly, character reference locking
**Question:** what else can be done so the render matches the director's exact vision, and characters stay the same person

**Status (Aug 16, 2026):** Every item in this analysis is implemented and committed —
A1–A7 and B1–B6, plus the reporting surface and automatic reference upgrade.

**One thing remains:** `scripts/validate_adherence_stack.py` has not been run.
Nothing in this document has been proven against a real render — every check is
a unit test. Phase 0 is free and offline; the single most useful thing it reports
is whether this machine selects a face-identity embedder or only a general-visual
one, which determines how much of the identity work is currently doing anything.

The reporting surface is now mounted (`f319366c`), so the first real render will
also be the first real test of everything underneath it — the panel displays data
no render has yet produced.

Frontend verified locally: `tsc --noEmit` clean, 680 tests across 76 files pass,
`npm run build` succeeds.

Commits on `backend-expansion-dependency-slicing`:
- `7a0c1677` Fix prompt adherence and character identity consistency (Tiers 1 + 2)
- `5ef072d8` Add intent-fidelity check before render submission (B1)
- `cdf5527a` Put director intent into render-facing form (B2)
- `8da221f2` Surface shot signals to the director (reporting surface)
- `980048ad` Scope reference locks by look; upgrade them; improve corrections (A6, B3, B6, auto-upgrade)
- `4b27e588` Fix dropped-phrase lookup ordering and scoping (defect in `980048ad`)
- `f319366c` Mount Shot Signals in the Previs Bay

**All items from this analysis are now implemented and committed.** A6, B3, and
B6 closed in `980048ad`, along with automatic reference upgrade.

**One defect was introduced and fixed.** `_dropped_elements_for_shot` (B3) iterated
`storage.list_jobs` with `reversed()` — but that call returns newest-first, so it took the
*oldest* render of a shot and would have restored phrasing from a superseded prompt
assembly. It also queried across all projects unscoped, so on a busy install the shot's
jobs fall outside the 200-row window and restoration silently does nothing. Fixed in
`4b27e588` with four regression tests.

Worth recording *why* it got through: every test written for B3 passed `dropped_elements`
in as a parameter, so the lookup itself was never exercised against storage. The feature
was fully tested and completely broken at the same time. Any future storage-reading helper
should get a stubbed-storage test, not just a pure-function test.

**HEAD has been tested in isolation** (2737 passed, 1 failed — the Linux-only
`test_video_assets_routes`). Earlier runs, mine and Codex's, were all against the *working
tree*, which carries uncommitted in-progress work; none of them tested what was actually
committed until now.

**Correction:** `test_render_canon_integration.py` is NOT in the repo. It is an uncommitted
test belonging to the in-progress work in the tree, so its failure was never a repo-level
problem and should not be treated as a baseline failure.

**Verified on the real venv** (first local run of this work): 2743 passed,
3 failed, 26m33s. My sandbox run was 2744 passed / 2 failed — same 2746 total, so
no tests were missing on either side. The difference is environmental, not
behavioural: `test_video_assets_routes` failed in the Linux sandbox and passed on
macOS, and the flaky crew test failed locally and passed in the sandbox. No
failures appeared outside the two known areas.

`scripts/validate_adherence_stack.py` runs the checks below in cost order
(offline → provider probe → one gated paid render).

**Known flaky test — root cause found and fixed:**
`app/routes/test_crew_intelligence_routes.py` failed intermittently with SQLite
I/O errors (`unable to open database file`, locally `disk I/O error`).

My first diagnosis was wrong and is recorded here so it is not repeated. I
attributed it to disk pressure — the volume was 97% full — and to the same cause
as the Aug 6 incident where git died mid-write and left a partial
`.git/index.lock`. Space was freed. The test kept flaking. The disk was never
the problem, and I had evidence pointing elsewhere at the time that I
under-weighted.

The real cause was a process-wide singleton being rebound to per-test storage.
Four department services assigned `crew_intelligence_service._storage =
self.storage` at construction. A test using `tmp_path` storage rebound the
singleton to `/tmp/tmpXXXX/studio.db`; once pytest cleaned that directory up, any
later test reaching the singleton opened a path whose parent no longer existed.
Instrumenting `_create_connection` to print `db_path`, `parent_exists`, fd count
and thread showed exactly that: `parent_exists=False` on a path under a deleted
temp directory. Disk (28GB free at the time), fd exhaustion (peak 111 against a
20000 limit), per-PID path variation, and test ordering were each ruled out
individually.

Fixed by removing those four assignments. Verified with 8 consecutive clean runs
of a test that had been failing roughly one run in three.

**Nothing here has been validated against a real render.** Every change is unit-tested against
2673 passing tests; none has been proven on paid provider output. See "What is not yet proven".

---

## Summary

The correction machinery (5 loops, slot assembly, retry, two-stage reference locking) is built and
wired. The gaps that remain are not missing features so much as **three broken measurement points**
and **one missing input channel**:

1. Identity drift is scored but **cannot fail a shot** — its weight is `0.0`.
2. Identity similarity has **no real measurement** — the embedding adapter is a file-byte hash.
3. Adherence is measured **render-vs-prompt**, never **prompt-vs-vision** — so a shot can score 95
   while missing what you actually asked for, if compression dropped it.
4. There is **no negative-prompt channel** in the slot system.

Everything below is anchored to specific files and lines.

---

## A. Character consistency

### A1. `identity_continuity` is weighted zero — CRITICAL

`adherence_service.py:28`

```python
DIMENSION_WEIGHTS = {
    "character_state": 0.25,
    "identity_continuity": 0.0,     # <-- contributes nothing
    "action": 0.20,
    ...
}
```

The vision model is asked to score identity continuity (`adherence_service.py:990`), the score is
parsed, stored, and displayed — and then multiplied by zero. A shot where MAYA renders as a
completely different woman scores exactly the same as one where she doesn't.

Downstream consequence: `verdict` is derived from the weighted aggregate. If identity is the only
failing dimension, the aggregate stays above `VERDICT_PASS_THRESHOLD` (80), the verdict is `pass`,
`should_retry` is `False` (`render_retry_service.py:822`), and the shot is accepted. Identity drift
**can never trigger a retry today.**

**Fix**

- Give it real weight (~0.20), rebalancing `character_state` down since they overlap.
- Add a **hard gate independent of the aggregate**: any `identity_continuity` score below ~65 forces
  `verdict = "correctable"` regardless of the weighted total. Identity is not a thing that averages
  out against good lighting.
- Note `adherence_service.py:243` already excludes *inferred* identity scores from `failed_slots`
  (correct — don't retry on a fabricated score). Keep that; the gate should only fire on scores the
  evaluator actually returned.

### A2. There is no real identity measurement anywhere

`visual_embedding_adapter.py:74`

```python
def build_visual_embedding_adapter() -> VisualEmbeddingAdapter:
    provider = (os.getenv("VISUAL_EMBEDDING_PROVIDER") or "").strip().lower()
    if provider in {"mock", "mock_local", "local"}:
        return MockLocalVisualEmbeddingAdapter()
    return UnavailableVisualEmbeddingAdapter()   # <-- the default
```

`MockLocalVisualEmbeddingAdapter` embeds `sha256(file_bytes)`. Two frames of the same actor,
one pixel apart, produce uncorrelated vectors. So the cosine similarity and the
`consistent / plausibly_consistent / identity_drift` thresholds in
`character_identity_continuity_verification_service.py:52` are measuring nothing. The default
adapter returns empty vectors, which `_cosine` turns into `0.0` — silent, permanent
`identity_drift`.

**Fix**

- Wire a real embedder. For *identity* specifically, a face-recognition embedding (ArcFace /
  InsightFace, ~10ms on CPU) beats a general CLIP/SigLIP embedding by a wide margin — CLIP encodes
  "young woman, dark hair, warm light" and will happily call two different actors a match.
- Practical approach: face embedding for `identity_continuity`, CLIP/SigLIP for wardrobe/style
  continuity. They answer different questions.
- Both run locally, no provider spend, no tenant-policy exposure — relevant given the DashScope
  screenplay restriction.

### A3. The identity verification service is orphaned

`character_identity_continuity_verification_service.py` — 254 lines, has its own test file, and is
imported by **nothing**:

```
$ grep -rn "character_identity_continuity_verification" --include=*.py .
./app/services/character_identity_continuity_verification_service.py:254   (self-instantiation)
./app/services/test_character_identity_continuity_verification_service.py:12
```

It's the natural consumer of A2 and the natural producer of the A1 gate. Wire it into the render
completion hook next to `lock_first_references_for_completed_job`.

### A4. One reference image per character, permanently

`storage.py:1163`

```sql
CREATE UNIQUE INDEX idx_character_reference_locks_active
    ON character_reference_locks(project_id, character_id)
    WHERE lock_status = 'locked';
```

and `character_visual_reference_service.py:388`

```python
existing_locked = storage.get_character_reference_lock(job.project_id, character_id, "locked")
if existing_locked:
    continue
```

The first render that passes adherence **permanently defines** that character for the whole film.
There is no re-lock path, no "use this frame instead," no override. If the locking frame is a
three-quarter-back angle or a motion-blurred one, every subsequent shot is conditioned on a bad
reference — and because the reference is bad, later shots are more likely to fail, which never
promotes a better one.

Meanwhile `happyhorse-1.1-r2v` accepts **1–9 reference images** and you send exactly one per
character (`character_visual_reference_service.py:115`, `characters[:9]`).

**Fix**

- **Multi-image reference sets per character.** The `reference_role` field already exists on
  `CharacterReferenceLock` and is hardcoded to `"general"` (line 420). Use it: `face_front`,
  `face_three_quarter`, `full_body`. Send 2–3 per character. This is the single largest available
  improvement in likeness stability and it needs no new provider.
- **Drop the unique index** in favour of unique-per-`(project, character, reference_role)`.
- **Add a re-lock action** — director-initiated "make this frame the canonical reference," plus
  automatic replacement when a later shot scores materially higher on identity.

### A5. Reference frames are chosen arbitrarily

`character_visual_reference_service.py:341` prefers the provider's `thumbnail_url` — typically
frame 0, which on a fade-up or a moving shot is the *worst* frame in the clip. Otherwise it
ffmpegs a hardcoded `-ss 00:00:01` (line 476). No check that a face is visible, in focus, or
facing camera.

**Fix** — candidate-frame scoring. Sample 6–8 frames, pick the best on:
`face bounding-box area × sharpness (variance of Laplacian) × frontality (yaw/pitch from landmarks)`.
Roughly 40 lines using the same face model as A2. This is cheap and it compounds — a good lock
improves every downstream shot.

### A6. No wardrobe / look scoping

The lock key is `(project_id, character_id)`. A character with a costume change, an injury, an age
jump, or a rain-soaked scene has one canonical look fighting the prompt for the rest of the film.
The fallback text tries to paper over this in prose (line 145: *"preserve changeable appearance …
unless this shot explicitly changes them"*), which is asking a video model to reason about an
exception it can't see.

**Fix** — add `look_id` to the lock key, with a scene-range or explicit assignment. "MAYA / hospital
look" and "MAYA / final act look" are different references, both canonical.

### A7. Reference weights are flat

`character_visual_reference_service.py:134` sets `weights[ref_id] = 1.0` for every character in the
shot. In a close-up on MAYA with DRE out of focus behind her, DRE's reference pulls just as hard.

**Fix** — weight by prominence: the shot's subject (derivable from the `character_state` slot order
and the camera slot) gets 1.0, background cast 0.3–0.5.

---

## B. Prompt adherence — "my exact vision"

### B1. Nothing measures prompt-vs-vision — only render-vs-prompt

This is the structural gap behind the question. `score_render_attempt(..., expected_slots)`
(`adherence_service.py:134`) scores the frames against **the already-compressed slots** — the output
of `_truncate_to_budget`, `_fit_character_state_to_budget`, and `_merge_slot_text`.

So the loop can only ever answer *"did the render match the prompt we sent?"* It structurally
cannot answer *"did the prompt we sent still contain what Amber asked for?"* If the 210-char
`character_state` budget dropped the detail that mattered, the render scores 95, passes, promotes a
reference lock, and the vision is quietly gone — with a green check next to it.

**Fix — an intent-fidelity check, pre-render.** Before spending a render:

1. Take the director's original shot description (unbudgeted, uncompressed).
2. Diff it against the assembled 512-char prompt.
3. Surface what was dropped, in the director's own words: *"dropped: 'her hands never stop moving',
   'the fluorescent buzzes'."*
4. Let the director promote a dropped element into the reserve, or accept the loss knowingly.

This costs one cheap text call, spends no render budget, and is the only thing in the system that
would catch a vision-to-prompt loss. Everything downstream is measuring against the lossy artifact.

### B2. Director intent is stored and never read

`director_intent_service.py` is a 31-line CRUD wrapper over `load_director_intent` /
`save_director_intent`, exposed at `routes/director_intent.py`, and consumed by **no service** —
not the prompt builders, not the enrichment layer, not the scorer.

The one place in the app where the director states what the film is supposed to feel like never
reaches a render prompt. Wiring it into `render_context_enrichment_service` (as another slot
guidance source alongside Bible/Spine) and into the adherence rubric is a small change with a
direct line to the stated goal.

### B3. Truncation is blind and unrecorded

`shot_prompt_builder.py:404`

```python
def _truncate_to_budget(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    return text[:budget - 3] + "..."
```

Cuts mid-word, mid-clause, silently. Per `POSITIONAL_WEIGHTING_FINDING.md` the tail matters least,
so the *choice* of what to drop is defensible — but nothing anywhere records what was dropped, so
neither the director nor the corrector can see it.

**Fix**

- Record dropped text in the attempt record. The corrector currently can't restore something it
  doesn't know was removed.
- Replace hard truncation with semantic compression for the `character_state` slot specifically
  (one cheap text call, cached per character) — "mid-40s, weathered hands, grey at the temples"
  survives compression far better than a mid-word cut.

### B4. `total_shots` is a guess

`shot_prompt_builder.py:280`

```python
# This is a heuristic — frontend should pass total_shots if available
total_shots = max(shot_number, 3)  # Assume at least 3 shots if not specified
```

`_segment_scene_text` then splits the scene into that many chunks. For a 6-shot scene, shot 2 gets
the segment computed as if there were 3 shots — so the action text attached to most shots describes
the wrong beat. The prompt is confidently, precisely wrong, and adherence scoring will happily
confirm the render matched it.

**Fix** — thread the real shot count through. The comment already identifies it; it's a small change
with an outsized effect on whether each shot is about the right moment.

### B5. No negative-prompt channel

`comfyui_provider.py:127`, `animation_prompt_builder.py:58`, and `script_parser.py:4846` all build
negative prompts. The slot system that actually feeds the render has no negative channel at all —
`_SLOT_ASSEMBLY_ORDER` is five positive slots plus an unused 32-char `reserve`.

For video models, negatives are among the cheapest adherence wins available: *no extra people, no
text overlay, no watermark, no morphing hands, no camera shake, no split screen, no subtitles.* The
cast guard (`"Only MAYA and DRE visible. No extras."`, line 210) is currently doing this job inside
the positive prompt, where it burns the most heavily-weighted budget in the whole prompt.

**Fix** — add negatives as a **separate provider field**, not a sixth slot. It shouldn't compete for
the 512 characters. Then remove the cast guard from `character_state` and reclaim ~35 characters of
the highest-value budget in the prompt.

### B6. The corrector never sees the image

`adherence_service.py:_call_groq_corrector` — *"Cheap call - only sees expected/observed text, not
video."*

The pipeline is: vision model looks at frames → writes a text summary → text model reads the summary
→ guesses a prompt fix. The only component that has seen both the intent and the actual pixels is
the vision model, and it's used purely as a scorer.

**Fix** — have the vision model propose corrected slot text in the same call it scores. Same token
cost roughly, strictly more information. Keep the text corrector as a fallback for when the vision
call fails.

---

## Suggested order

### Tier 1 — DONE (Aug 15, 2026)

| # | Item | Where |
|---|------|-------|
| 1 | Weight `identity_continuity` 0.0 → 0.20 + hard gate at 65 (A1) | `adherence_service.py`, `render_retry_service.py` |
| 2 | Negative-prompt channel as a separate provider field (B5) | `negative_prompt_builder.py` (new), `models/__init__.py`, `adapters/__init__.py`, `render.py` |
| 3 | Candidate-frame scoring for reference locks (A5) | `character_visual_reference_service.py` |
| 4 | Thread real `total_shots` (B4) | `shot_prompt_builder.py`, `storyboard_blueprint_service.py`, `previs_service.py` |

Three things surfaced during implementation that were not visible from the analysis alone:

- `identity_continuity` is a scoring dimension with no prompt slot of its own. The correction paths
  iterate the five real slots, so an identity-only failure would have carried every slot forward
  verbatim and retried a byte-identical prompt. Identity failures now also mark `character_state`
  failed, and slot reordering scores `character_state` by the weaker of the two so a drifted face
  moves to the front of the prompt.
- Back-filled identity scores (from evaluators that omit the dimension) must be excluded from the
  gate, or every such evaluator reads as identity drift.
- Cast exclusion in the negative prompt must never name the characters who should be present —
  "not MAYA" in a negative prompt is a reliable way to lose MAYA. It excludes the category instead.

**Verification:** 2584 passed, 2 failed across `app/services`. Both failures reproduce on unmodified
baseline code and are unrelated to this work:
`test_render_canon_integration::test_generic_render_uses_visible_character_and_saved_canon` and
`test_video_assets_routes::test_video_asset_status_update`. 48 new tests added across four new test
files; `test_adherence_service.py` updated for the rebalanced weights. No paid provider calls.

**Not yet done for Tier 1:** run the suite on the local machine (`.venv/bin/pytest app/services`) —
the repo venv is a macOS venv and could not execute in the Linux VM the file bridge uses, so the run
above was against a copy of the tree in a cloud container. Changes are also uncommitted to git.

### Tier 2 — DONE (Aug 15, 2026)

| # | Item | Where |
|---|------|-------|
| 5 | Real embedding adapters + kind-aware thresholds (A2) | `visual_embedding_adapter.py` |
| 6 | Identity verification wired into render completion (A3) | `character_visual_reference_service.py`, `render.py` |
| 7 | Multi-image reference sets per character (A4) | `storage.py` (migration 58), `models/consistency.py`, `character_visual_reference_service.py` |
| 8 | Re-lock / director override path (A4) | `character_visual_reference_service.relock_character_reference` |
| 9 | Prominence × role reference weighting (A7) | `character_visual_reference_service.prominence_by_character` |

Design decisions worth recording:

- **Embedding kinds are not interchangeable.** A CLIP-family embedding (DashScope
  `multimodal-embedding-v1`) encodes the whole picture — setting, palette, wardrobe — so two
  different actors in the same kitchen score high on it. A face embedding (ArcFace/InsightFace)
  encodes facial geometry and is the only thing that answers "same person". Thresholds are therefore
  defined per kind (`SIMILARITY_THRESHOLDS`), and every report carries `measures_identity` so a
  continuity signal is never read as a likeness verdict. The single hardcoded 0.97/0.82 pair that was
  there before was calibrated for neither.
- **Adapter selection auto-detects** instead of defaulting to `Unavailable`. The old default returned
  empty vectors, `_cosine` turned those into 0.0, and every comparison read as permanent identity
  drift that nothing consumed. Order: local face → hosted visual → unavailable.
- **InsightFace is optional and not in requirements.txt** (it pulls ~200MB of weights). Install
  `insightface onnxruntime` and identity verification upgrades from continuity evidence to a real
  likeness measure, locally, with no provider spend and no images leaving the machine.
- **Unavailable ≠ drift.** Every path that cannot produce a vector now reports `unavailable` with a
  reason rather than scoring 0.0.
- **Verification runs before locking**, or the job's own frames would be in the comparison set and
  the shot would be checked against itself. References sourced from the same job are also excluded.
- **Multi-view roles are labelled honestly.** Without a face detector, frames cannot be truthfully
  called `face` or `full_body` — that needs to know how much of the frame the subject occupies. They
  are labelled `general` (primary) and `alternate_angle`, and `_role_for_rank` is where a detector
  would upgrade them.

**Verification:** 2631 passed, 2 failed across `app/services` — the same two pre-existing baseline
failures as before, unrelated to this work. 47 new tests across two new files.

**Not yet done:** local test run, and git commit. See Tier 1 note above — same two caveats apply.

### Reporting surface (commit `8da221f2`)

`shot_signals_service` assembles intent fidelity, character identity, the
references that conditioned a render, and the exclusions sent with it into one
director-facing payload, exposed at `GET /render/jobs/{job_id}/signals`.
`POST /render/character-references/relock` is the first endpoint for the
reference override — before it, a lock set from a bad frame could not be
corrected through the API.

Two AGENTS.md rules are enforced at that boundary and asserted by tests on both
sides: no scores, ratings, or percentages reach the director, and a signal with
nothing to say returns `quiet` so a room renders nothing rather than a
reassuring row.

**Not mounted.** `ShotSignalsPanel` exists and is tested but is not rendered in
any room. Worth noting that `PrevisIntelligencePanel` — which predates this work
— is also mounted nowhere. This codebase has a standing pattern of panels being
built and never wired in, the same failure mode as the orphaned identity
verification service found at the start of this work.

### Still open in the consistency area

- **Look/wardrobe scoping (A6)** — see Tier 3. The lock key is now
  `(project, character, reference_role)`, not yet `look_id`, so a costume change still fights the
  reference.
- **Automatic reference upgrade** — `relock_character_reference` exists and is callable, but nothing
  calls it automatically yet. A rule like "replace the lock when a later shot verifies materially
  better" is a small addition on top of the verification report now recorded on every job.
- **A route for the director override** — the service method is there; no endpoint exposes it.

### Tier 3 — partially DONE

| # | Item | Status |
|---|------|--------|
| 10 | Intent-fidelity pre-render diff (B1) | DONE — `intent_fidelity_service.py`, commit `5ef072d8` |
| 11 | Director intent into the render prompt (B2) | DONE — commit `cdf5527a` |
| 12 | Look/wardrobe-scoped locks (A6) | OPEN |
| 13 | Vision-model-authored corrections (B6) | OPEN |
| 14 | Record dropped text at truncation (B3) | OPEN |

**Correction to the original B2 analysis.** This document originally said director intent "is stored
and never read". That was wrong. `director_intent_service` is unused, but `render.py` already called
`build_director_intent_prefix` and prepended its output to the render prompt. The real problem was
worse than the one described: that prefix is written for Claude system prompts, and on a video prompt
it inverted the slot priority the whole system is built around. Measured on a representative intent,
the prefix ran 299 characters against the slotted prompt's 191 — and because the provider weights
early tokens most heavily, it placed genre and "what success looks like" ahead of who is on screen.
`what_to_avoid` also sat in the positive prompt, where honouring it depends on the model processing a
negation. Fixed in `cdf5527a`: bounded renderable guidance placed after the shot, avoid-terms routed
to the negative channel, and 512-char enforcement added after all injections (nothing enforced it
once intent and the continuity block were appended).

### What is not yet proven

Everything above is verified by unit tests. None of it has been exercised against a real render.
Specifically unproven:

- Whether the identity hard gate fires correctly on genuine drift in real footage, and whether
  `IDENTITY_HARD_GATE_THRESHOLD = 65` is calibrated right — it was chosen from ArcFace verification
  norms, not from this pipeline's output.
- Whether the negative-prompt channel measurably improves adherence on HappyHorse. The field
  reaches the provider request body on both the t2v and r2v paths — verified by
  `scripts/validate_adherence_stack.py` Phase 0 — but whether HappyHorse honours
  `input.negative_prompt` or silently ignores it is still unknown, and only a paid render
  answers it.
- Whether multi-view references improve identity hold versus the previous single image.
- Whether candidate-frame scoring picks frames a human would also pick.
- Whether the DashScope multimodal embedding endpoint responds in the shape
  `DashScopeMultimodalEmbeddingAdapter._extract_vector` expects. A live probe returned HTTP 400,
  so the request itself is malformed and the response shape remains untested. This now degrades a
  fallback rather than the feature: with `insightface` installed,
  `build_visual_embedding_adapter()` selects `LocalFaceEmbeddingAdapter` and DashScope multimodal
  is second choice.

The no-spend verifiers (`scripts/verify_character_reference_locking_capture.py`,
`scripts/prove_new_render_pipeline_wiring.py`) can prove wiring. Only a paid render can prove effect.

B1 remains the largest single gap in the system. Everything built so far — including all of Tier 1 —
measures the render against the prompt. Nothing yet measures the prompt against what the director
actually asked for.

### Deferred deliberately

Removing the positive cast guard from `character_state` to reclaim ~35 characters of the
highest-weighted budget (discussed under B5). `test_render_canon_integration.py:276` asserts on its
presence, so it is a contract change rather than an additive one. The negative prompt now covers the
same ground from the other side, making this a cleanup rather than a fix.

Tier 2 and 3 items remain testable against the existing no-spend capture verifiers
(`scripts/verify_character_reference_locking_capture.py`,
`scripts/prove_new_render_pipeline_wiring.py`) — no paid provider calls needed to prove them.

---

## 2026-08-25 — B1 addressed: the director's shot now reaches the prompt (+ a budget defect surfaced)

This session tackled B1 — "nothing measures the prompt against what the director actually
asked for" — from the input side: the prompt was not describing the shot at all, so there
was nothing faithful to measure. Findings and changes, on project `project_5907c60cddbc`
("I was reborn").

### Root cause found: the shot's staging never reached the prompt

Every one of the 60 storyboard shots had 9 of 12 visual-plan fields empty
(`camera_angle`, `lens_language`, `blocking`, `composition`, `lighting`, `color_palette`,
`props`, `reference_asset_ids`, `negative_visual_constraints`), and the action slot was fed
raw screenplay prose (dialogue, V.O., transitions), then truncated to 110 chars. `render.py`
filled the empty slots from scene-level fallbacks (location, time-of-day) plus style-bible
text, so the provider received the same boilerplate for every shot in a scene — e.g. the
lighting slot literally read "Use light, color, and atmosphere to underline the beat", a note
to the director that a vision model cannot fail. Confirmed against a real prior scored render:
it PASSED at 85/100 with lighting scored 95 against that non-instruction.

New diagnostic: `scripts/diagnose_shot_inputs.py` reports empty-field counts, action-slot
overflow, dialogue-in-action, and identical-shot decomposition per project.

### Changes made (all committed to disk; NOT yet git-committed — foreign uncommitted work
was already present in the working tree, so these were delivered file-by-file)

1. **Em-dash slugline parser fix** (`app/services/script_parser.py`) — `_parse_simple_heading`
   split only on `" - "` (ASCII hyphen). "I was reborn" uses em dashes, so `time_of_day` came
   back empty for all 12 scenes and `LOCATION — NIGHT` folded whole into the location. Now
   splits on em/en/hyphen. Test: `app/services/test_script_parser_headings.py`.

2. **Staging generator** (`scripts/generate_shot_staging.py`) — an AD pass that turns each
   screenplay beat into stageable per-shot fields via OpenRouter (Ox Alpha), written to a
   review file for director edit before `--apply` writes them to `storyboard_shots.visual_plan`.
   Instructed to leave a field blank rather than invent. Note: Ox Alpha is a reasoning model
   whose reasoning is billed as completion tokens; `max_tokens` must be generous (16000) or it
   returns empty content with `finish_reason=length`.

3. **The wire** (`app/services/render.py` + `app/data/storage.py`) — the live slot path
   (`if _full_content:`) now reads the shot's reviewed staging via a new
   `DatabaseStorage.get_shot_visual_plan(project_id, shot_id)` and overrides the scene-level
   fallbacks: action, lighting, camera (angle+lens+composition), and environment (+props).
   Absent staging leaves the old behavior untouched. NOTE: a second, structured-previs slot
   path in render.py is gated on `parameters["structured_prompt"]`, which nothing in the
   codebase ever sets — it is dead code and was not used.

4. **Two missing functions implemented** (`app/services/shot_prompt_builder.py`) —
   `merge_identity_guidance_into_slots` and `merge_knowledge_guidance_into_slots`. render.py
   imported both from two call sites but neither was ever defined; `create_job` raised
   ImportError on any shot carrying identity guidance (the knowledge one was caught by a
   try/except and only warned). Reconstructed conservatively from the call sites: additive,
   dedup, budget-clamped. This means the identity-guidance path in `create_job` had never
   actually run before this session.

5. **Config regression fixed** (`app/config.py`) — `ADHERENCE_VISION_PROVIDER` /
   `ADHERENCE_VISION_MODEL` were added to `.env` earlier this session without being declared
   as `Settings` fields; pydantic-settings forbids unknown keys, so every `Settings()` — and
   thus backend startup — would have crashed. Now declared. (Self-inflicted; fixed same day.)

6. **Adherence scorer honesty** (`app/services/adherence_service.py`, earlier this session) —
   a dimension whose expected text is empty or is a director-instruction ("underline the beat")
   is now excluded from the weighted aggregate and reported in `unscored_dimensions`, rather
   than scored ~95 and inflating the verdict. Test: `test_unspecified_dimensions.py`.

### Proven end to end

`scripts/show_shot_prompt.py` runs the real `create_job` assembly (no provider call, no spend)
and prints the assembled prompt. For `scene_001_shot_001` the lighting, camera, environment,
and action slots now carry the director's staging ("Low western sun, warm backlight, long
shadows"; "Maya walks down a crowded sidewalk, slowing to watch a family laughing") instead of
boilerplate. B1's input side is closed for wired shots.

### NEXT: the budget/duplication defect (the remaining real problem)

The assembled prompt is 590–608 chars against the 512 ceiling and trims the tail mid-word.
The identity description is duplicated: once in `character_state`, again in a separate
`identity_continuity` block (~600 chars alone, not part of the 5-slot assembly order). Result:
the prompt is ~70% Maya's appearance and ~30% the actual shot. This is the KNOWN DEFECT already
documented at the top of `shot_prompt_builder.py` (slots sum to 582 > 512; two prior fixes went
green-to-red and were reverted).

One test is currently red: `test_render_canon_integration.py::
test_generic_render_uses_visible_character_and_saved_canon` — asserts `"practical light"` (a
knowledge atom) is in the prompt; it is trimmed by the 512 cut (608→512). **Unverified whether
this test was already red before this session** — `merge_knowledge_guidance_into_slots` did not
exist, so knowledge guidance was never merged and the atom likely never reached the prompt.
Verify first next session with: `git stash && python -m pytest
app/services/test_render_canon_integration.py::test_generic_render_uses_visible_character_and_saved_canon -q`
then `git stash pop`.

Recommended next task, test-first, in the fragile budget area:
- De-duplicate identity: do not repeat the full appearance in `character_state` when
  `identity_continuity` already carries it.
- Trim `identity_continuity` to the fixed-identity essentials; drop emotional-state and
  review-note prose from the render prompt (keep it in the record, not the prompt).
- Make truncation cut on word/phrase boundaries, not raw character index.
- Separate concern, lower priority: department/knowledge guidance is injecting bible craft
  notes ("Never explain a motif…") into the action slot — the same non-instruction class as
  "underline the beat".

Render effect is still unproven: DashScope/HappyHorse is in billing arrears (all July renders
failed `Arrearage`), so a paid render can't run until billing is resolved or the render moves
to OpenRouter. Adherence scoring can be exercised now on the ~290 existing clips via
`scripts/score_rendered_shot.py`.
