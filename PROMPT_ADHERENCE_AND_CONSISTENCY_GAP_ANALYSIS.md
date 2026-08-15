# Prompt Adherence & Character Consistency — Gap Analysis

**Date:** August 15, 2026
**Scope:** `studio-backend/app/services` — adherence, retry, slot assembly, character reference locking
**Question:** what else can be done so the render matches the director's exact vision, and characters stay the same person

**Status:** Tiers 1 and 2 implemented and tested (Aug 15, 2026) — items A1, A2, A3, A4, A5, A7, B4,
B5 below are DONE. Tier 3 is open. See "Suggested order" at the end for current state.

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

### Still open in the consistency area

- **Look/wardrobe scoping (A6)** — see Tier 3. The lock key is now
  `(project, character, reference_role)`, not yet `look_id`, so a costume change still fights the
  reference.
- **Automatic reference upgrade** — `relock_character_reference` exists and is callable, but nothing
  calls it automatically yet. A rule like "replace the lock when a later shot verifies materially
  better" is a small addition on top of the verification report now recorded on every job.
- **A route for the director override** — the service method is there; no endpoint exposes it.

### Tier 3 — the vision layer (OPEN)

10. Intent-fidelity pre-render diff (B1)
11. Wire director intent into prompt + rubric (B2)
12. Look/wardrobe-scoped locks (A6)
13. Vision-model-authored corrections (B6)
14. Record dropped text at truncation; semantic compression for `character_state` (B3)

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
