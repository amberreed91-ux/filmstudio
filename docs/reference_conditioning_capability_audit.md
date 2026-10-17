# Multi-Reference Conditioning — Capability Audit (Local LTX / Phosphene)

**Date:** 2026-09-24 · **Branch:** `backend-expansion-dependency-slicing`
**Scope:** Can Studio's multi-reference selection actually reach and influence the installed
Phosphene/LTX renderer? This audit changes no behavior; it establishes the provider
capability boundary from installed code, live probes, and upstream sources.

---

## TL;DR

The provider contract accepts **exactly one** reference image per video generation
(`image` is a single path on the i2v form). The installed adapter already behaves
correctly against that contract: it uploads the strongest reference and the others
never reach Phosphene. The one provider-native multi-reference mode ("Ingredients",
2–8 images composed into a reference sheet) is **refused server-side on this install's
active generation (LTX-2.5)**, and this machine's LTX-2.3 pack is incomplete, so it
cannot be used today either. **No adapter change can deliver multi-reference video
conditioning on the current install.** Studio's selector is left intact; the adapter
now records an explicit reference trace so the boundary is visible per job.

Classification: **B (Phosphene API limitation)** as the primary boundary, compounded
by **D (installed local implementation)** for the one multi-reference mode that exists.
Not A (no existing supported capability to correct the adapter with), not C (the
engine layer itself accepts multi-image conditioning), not E alone (the adapter merely
mirrors the provider contract; the deliberate part lives in Phosphene's gate).

---

## The four channels, with evidence

### 1. Studio selected — what the intelligence layer chose

`app/services/reference_selection_service.py::select_character_references` selects
deterministically: approved rows only, registry + file dedup, tier assignment
(canonical anchor → identity tiers → scene-promoted context), stable sort, capped by
`CharacterVisualReferenceService.MAX_PROVIDER_REFERENCES = 9`
(`MAX_REFERENCES_PER_CHARACTER = 3`). Selected references ride the render job as
`input_payload.referenceAssets`, strongest first.
**Up to 9 URLs cross the Studio boundary. This is not a lie — it is the Studio-side
contract. It simply is not the provider contract.**

### 2. Adapter received — what crossed into `LocalLTXAdapter.submit_job`

`app/adapters/local_ltx.py::submit_job` passes the full list to
`translate_studio_request`, which uses only its truthiness
(`refs → mode = "i2v" if refs else "t2v"`), then iterates the list **in order** and
uploads each candidate until **one** upload succeeds:

```python
for reference in (getattr(payload, "referenceAssets", None) or []):
    candidate = _as_clean_str(reference)
    if not candidate:
        continue
    panel_path = await self._upload_reference(candidate)
    if panel_path:
        break
```

**Adapter received: all selected references. Adapter sent onward: one** (the first
that uploads successfully = the strongest, by the selector's ordering).

### 3. Provider received — what Phosphene actually accepts

Verified against the installed service (Pinokio: `~/pinokio/api/phosphene.git`,
**v4.15.2**, commit `59d733d`, 2026-09-22; live probe of `/status`, `/models`, `/version`
on 2026-09-24 answered and matches the checkout):

- `docs/API.md` (installed copy): `POST /queue/add` field `image` — *"I2V only.
  Absolute path to a reference PNG/JPG. **Required**"* — a single scalar path.
  `POST /upload` is one-file-per-request ("Send the images in a loop").
- `make_job` (mlx_ltx_panel.py:24569) reads `f("image", ...)` — a **scalar** form
  field. There is no array-shaped `image` input; extra fields would be silently
  ignored (the panel's documented "allowlist trap").
- The **video** i2v pipeline therefore receives **one image**. The `refs[]` JSON
  list that does exist in `make_job` belongs to `mode=image` — the *still-image*
  engine, not video.

**Provider received: one reference path.** Phosphene has exactly one multi-reference
video mode — **Ingredients** (`mode=ingredients`, 2–8 paths via
`ingredient_images_json`) — and it is out of reach here, see below.

### 4. Model consumed — what the installed LTX implementation conditions on

- The engine layer (`ltx-2-mlx`, vendored) genuinely supports multi-image
  conditioning: `generate_two_stage(..., images=None, image=None)` accepts an
  upstream-iso multi-anchor list (`ImageConditioningInput(path, frame_idx, strength)`;
  `ti2vid_two_stages.py:394–408`, `distilled.py:220–236`). **So this is not a model
  limitation at the conditioning-mechanics level.**
- But Phosphene never populates `images` for ordinary video jobs: the i2v branch
  sends a single `image` path, and the model builds its conditioning latent from
  that one anchor (anchor mode pins it; Inspire mode on 2.5 keeps it as a
  subject/style guide while recomposing).
- **Ingredients** consumes 2–8 images — server-side it composites them into one
  reference *sheet* PNG (`_compose_ingredient_sheet`), loops the sheet into an IC
  `video_conditioning` clip, and rides the Ingredients IC-LoRA. The multi-reference
  capability is real **only through that adapter**, which is generation-locked:
  `ltx_generation_serves_ingredients()` returns `(version or ACTIVE_MODEL_VERSION)
  != "ltx25"`, and the worker raises `RenderRefused("ingredients_generation", ...)`
  on 2.5 with the reason: the 2.3-trained adapter transfers nothing on 2.5 (reference
  sheet rides at strength 0.0 by design; at 1.0 the model copies the sheet verbatim —
  owner-reproduced 2026-08-15), so the render collapses to prompt-only at two-stage
  cost. **On this install (active generation = ltx25), Ingredients is refused at the
  door.**

**Model consumed: one anchor image** for every video job reachable from Studio today.

### 5. Output — do additional references measurably change the result?

No. Refs 2..N never leave Studio's adapter (no bytes uploaded, no form fields sent),
so they cannot influence the render. This matches the prior live A/B: with only the
first reference crossing the boundary, toggling the others leaves the output
unchanged. The installed `image` field is a scalar; there is nothing for the second
reference to occupy.

Live probe corroboration (2026-09-24):

| Probe | Result |
|---|---|
| `/version` | Phosphene **4.15.2**, commit `59d733d` (2026-09-22), clean, in sync with remote |
| `/models` active generation | **ltx25** (q4_25 + gemma4 complete; q8_25/hq_25 incomplete) |
| `/models` ltx23 q4 pack | **complete: false** — missing `transformer-distilled.safetensors`, `connector.safetensors` |
| `/models` IC adapters | `ic_ingredients` file present (the **2.3** adapter), `ic_union_control`/`ic_upscale_x2` incomplete |
| 50-job history | all `mode` ∈ {t2v, i2v}, no ingredients jobs, no multi-image fields |

---

## Classification (proven, not assumed)

| Claim | Verdict | Evidence |
|---|---|---|
| **A. Adapter limitation, correctable via an existing supported provider capability** | **No (on this install)** | The only supported multi-ref capability (Ingredients) is refused on the active generation, and the 2.3 pack that could run it is incomplete. Sending an array or extra `image` fields would be silently dropped by Phosphene's allowlist — a fake abstraction. |
| **B. Phosphene API limitation** | **Yes — primary boundary** | `image` is a single scalar path for all video i2v lanes (docs/API.md + `make_job`); no array input exists on the video path. |
| **C. LTX model limitation** | **No** | The vendored engine's pipelines accept a multi-anchor `images` list and multi-clip `video_conditioning`; the model mechanics exist. What was missing is a *trained* 2.5 multi-subject adapter — and Lightricks has since published one (see Forward path). |
| **D. Installed local implementation limitation** | **Yes — compounding** | Phosphene 4.15.2 hard-gates Ingredients to non-2.5 generations with a documented, owner-reproduced refusal; this machine's LTX-2.3 q4 pack is incomplete, so even pinning `LTX_MODEL_VERSION=ltx23` cannot run it today. |
| **E. Deliberate architectural choice** | **Yes, at the Phosphene layer** | The 2.5 refusal is explicit and reasoned ("reference-guided work on 2.5 → Image mode with Inspire, or install the 2.3 pack"), not an oversight. The Studio adapter's first-reference behavior simply mirrors the provider's one-image contract. |

---

## Forward path (when this boundary can move)

1. **Watch for Phosphene > 4.15.2 integrating the LTX-2.5 Ingredients adapter.**
   Upstream, Lightricks published `Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients`
   (Hugging Face, ~2026-09-10; IC-LoRA conditioning video generation on a reference
   sheet). Phosphene's own gate comment says: *"The day Lightricks publishes a 2.5
   adapter this returns True for ltx25 and the registry row is the only other
   change."* That day has arrived upstream but is **not yet integrated** in 4.15.2
   (released 2026-09-22 and still refusing). When a release ships it:
   `ltx_generation_serves_ingredients()` flips to True on ltx25, `mode=ingredients`
   becomes sendable, and the smallest supported path is: upload the 2–8 selected
   references via `POST /upload`, submit `mode=ingredients` with
   `ingredient_images_json` (+ `ingredient_action`), letting **Phosphene compose the
   sheet** — not Studio. No image stitching in Studio, ever.
2. **Or complete the LTX-2.3 q4 pack** (the two missing files) and pin
   `LTX_MODEL_VERSION=ltx23` for ingredients jobs. Then the existing 2.3 Ingredients
   path works as-is. This trades generation quality (2.3 vs 2.5) for the capability.
3. **In both cases** Studio's Reference Library, selector, and validation stay
   exactly as they are; only the adapter's submit branch for the (then-)supported
   mode changes, gated on the same capability predicate Phosphene exposes
   (`ingredients_available` via `/status` bootstrap flags).

## What was changed as a result of this audit (Studio side only)

- `app/adapters/local_ltx.py`: module docstring now states the single-image provider
  contract and the boundary precisely; `submit_job` records a
  `local_ltx_reference_trace` in job metadata (selected / uploaded / not consumed /
  provider capacity) so every job shows what crossed the boundary. **No behavioral
  change**: the strongest reference is still the one sent; no silent downgrades.
- Tests (`tests/test_local_ltx_provider.py`): pin the boundary — only the first
  uploadable reference is sent; the next candidate is used when the first fails;
  translation never pretends multiple references reach the provider.
- This report.

**Explicitly not done** (per the audit mandate): no multi-reference payload passthrough,
no image concatenation/stitching/embedding/CLIP-ranking workarounds in Studio, no
Reference Library rewrite, no validation weakening.
