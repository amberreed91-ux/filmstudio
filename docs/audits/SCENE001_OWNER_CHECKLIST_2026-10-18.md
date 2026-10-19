# scene_001 Owner Checklist (2026-10-18)

Plain-language click order for each scene_001 blocker, traced from the code.
Paths are `studio-app/src/...` unless noted. Anything I could not verify in
the code is marked **[NOT VERIFIED]** — do not treat those steps as confirmed.

**Does this click create a new board version?** Answered per step. Rule of
thumb (backend: `studio-backend/app/routes/storyboard_blueprints.py`):
- `POST .../versions` creates a new board version.
- Rebuild on an **approved** version clones exactly one new draft; the
  approved version is untouched. Rebuilding a **draft** updates it in place
  (route docstring, `rebuild_version_shot_prompts`).
- Approving a version, editing/approving image prompts, and re-approving
  after a rebuild all act **in place** — no new version.

## 0. Open the scene

Previs Bay (`pages/PrevisRoom.tsx`): pick the project, then scene_001. Every
step below lives here except Maya's look and the Desk confirmation.

## 1. Maya's look (reference gate)

The look text the prompt builder sends (age + look drift-guard tokens) is
the character record's `look` field
(`studio-backend/app/services/shot_prompt_builder.py`, `_appearance_only_text`).
Edit it here — not in the Page, which shows character truth read-only
(`pages/PageRoom.tsx`, `page-characters`):

1. Open the Writers Room (`pages/WritersRoom.tsx`), Characters step, Maya's
   card. Edit the **Maya appearance** box — this is the `look` field,
   including the paper and the rooftop sentences — and optionally **Maya
   render description** (`visual_prompt_summary`).
2. Click the card's Save (`handleSaveCharacter` → `updateCharacter`, then
   looks refresh). If the boxes are disabled with "Physical look locked",
   revise the look first (step 4) — locked looks block profile edits.
3. Open Reference Space (`pages/ReferenceSpace.tsx`), Maya's look card.
   The saved profile change makes the locked approval stale: click
   **Revise look**, then **Approve and lock look** with her face image
   (approval is refused without one). This stamps the new
   `profile_revision` the reference gate checks.

No new board version. Rebuild the board prompts (step 2) after
re-approval so the video carries the new look words.

**[NOT VERIFIED]** — the literal "paper" / "rooftop" strings appear
nowhere in code; they are data inside Maya's `look` text. The field, the
save path, and the revise/re-approve path above are all verified.

## 2. Rebuild the board prompts

In Previs Bay, open the Prompt Rebuild panel
(`components/PromptRebuildPanel.tsx`, mounted in PrevisRoom):

1. Review the per-shot before/after diff. Shots without a stored builder
   hash are never overwritten silently — tick the per-shot confirm for each
   shot you accept. Hand-edited shots are skipped automatically.
2. Click Rebuild.

**New board version only if you rebuild an approved version** (mints exactly
one new draft). Rebuilding a draft updates it in place.

## 3. Re-approve the image prompts

In Previs Bay, each board shot has an image-prompt card
(`components/StoryboardImagePromptPanel.tsx`, mounted in PrevisRoom):

1. For each rebuilt shot: Derive (proposal only, never auto-approves), edit
   the text if needed, Save, then Approve.
2. For shots already approved against older text: tick the re-approve
   confirm and Re-approve — this re-anchors the approval to the rebuilt
   canonical text (`reapproved_at`).

No new board version (record-level updates). The Generation Readiness panel
(`components/GenerationReadinessPanel.tsx`) shows the D4 image-prompt gate:
all shots must read render-ready before submit.

## 4. Camera plans for shots 3 and 4

In Previs Bay, select board shot 3, then 4. Each has an AI camera card
(`components/AiCameraApproval.tsx`, mounted in PrevisRoom):

1. Replace every "AI suggestion awaiting approval" dimension with a creator
   decision (or explicitly approve the suggestion as creator).
2. Click the approve action (a deliberate click — nothing approves on load).

No new board version. Unapproved AI suggestions and empty camera blocks fail
the camera gate at preflight, so both shots must read clean.

## 5. Shot 5 coverage

In Previs Bay, open the Creator Decision workspace
(`components/CreatorDecisionWorkspace.tsx`, mounted in PrevisRoom) with the
Scene Direction panel (`components/SceneDirectionPanel.tsx`):

1. Assign shot 5 its canonical content (and dialogue, if it carries any).
   Every content unit needs exactly one shot — shared claims are duplicate-
   coverage blockers, and an empty shot 5 is an unresolved-coverage blocker
   unless it is an explicit establishing shot with a recorded reason.
2. Nothing resolves on display alone — each assignment needs its explicit
   decision click.

No new board version.

## 6. Board approval

In Previs Bay (`handleApproveStoryboardBlueprint`, `pages/PrevisRoom.tsx`):

1. Run Continuity Review first — approval is refused without it.
2. Click Approve for the current board version
   (`approveStoryboardVersion`, `lib/studioApi.ts`).

No new board version (approves in place). Approval re-stamps the same
version; a package built before this approval still carries older text, so
rebuild (step 2) after any late board text change.

## 7. Desk confirmation (kept, still mandatory)

Production Desk (`pages/ProductionDesk.tsx`):

1. Resolve each reference-bound shot — review the server-resolved
   authorized references in canonical order.
2. Click **Confirm this binding** per shot. This saves a durable
   project-scoped record (survives reload) and creates no jobs.
3. Back in Previs Bay, the single-take dialog and the whole-scene button
   both re-verify confirmations at submit; a stale or missing confirmation
   fails closed with zero jobs.

No new board version. If references changed since you confirmed, resolve
and confirm again — the submit will tell you, and nothing will have spent.

## 8. Submit (after every blocker clears)

- **One take:** Generation Readiness → Render a single take → pick exactly
  one shot (nothing preselected) → read the first 600 characters of the
  exact prompt, characters, duration, and submission counts → Check cost
  (estimate) → tick the spend checkbox → Confirm. The backend keeps every
  whole-scene gate and creates only that take; no scene assembly is written
  for a subset.
- **Whole scene:** Generate new scene footage (unchanged). Over
  `RUNWAY_RENDER_MAX_CREDITS` (default 300) or unknown cost without the
  acknowledgement checkbox fails closed with zero jobs.

The Canonical Production Thread panel no longer submits renders — its
render controls were replaced with a notice pointing here.
