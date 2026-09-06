# Character look approval — September 5, 2026

Added the explicit character appearance approval stage in The Page: Script → Character profiles → Lock character looks. The shared production path still has four rooms; Prepare in Study → Write and lock looks in The Page → Storyboard and render in Previs → Review and deliver in Theatre. Previs links back to the look stage with project/scene/shot context preserved.

## Creator workflow

Save the physical description and age in Character profiles, choose or upload a face portrait, optionally add a full-body reference, and choose Approve and lock look. Uploading creates a candidate, not an approval. A protected look displays its version and can be deliberately reopened through Revise look. Personality and voice remain editable; appearance edits and descriptor imports require reopening. Existing approved boards and footage remain unchanged; regenerate affected work after revising and reapproving a look.

## Backend behavior

A single conditional database write persists the explicit approval snapshot, chosen references, timestamp, and version in the character continuity document. Revision history is preserved. Stale profile revisions cannot be approved or overwrite an approval. Reference uploads validate decoded JPEG/PNG/WebP content, size and dimensions; their scoped URLs are registered for media ownership checks. New async API routes use dependency-injected services and Pydantic contracts.

Render reference resolution and canonical identity context prioritize explicit approval over automatically captured frames. Reopening stops using the old approval until reapproved. Same-image explicit legacy reapproval now promotes automatic references to director protection. Scene costume/appearance staging retains approved physical identity text. Saved editable appearance text takes precedence over older migrated/structured appearance records when approving. Partial profile saves preserve omitted fields and character IDs.

## Validation

- Frontend: 695 tests across 78 files passed; production build passed; lint had zero errors (four existing hook warnings).
- Backend: 130 regression tests passed, four skipped, in a copied backend with temporary databases and outputs. Final affected tests after migrated-identity correction: 37 passed, four skipped. Final dedicated approval and profile-route suite: 18 passed. New approval tests include service persistence, partial profile edits, versioned revision, stale/foreign-reference rejection, upload validation, descriptor/approval races, storyboard text, render reference payload encoding, media ownership, and route contracts.
- Browser: 14 desktop/mobile workflow checks passed with all six test writes intercepted; age-only profile check also passed with zero writes. Live page confirmed six saved characters all in draft, no runtime errors and no mutations.
- Independent frontend evaluation: PASS, first round. Same-provider independent agent because no other model provider was callable.
- Local backend restarted to activate new endpoints; queue was idle. No paid generation, uploads, or look approvals were performed on real film data.

## Current limitation

New storyboard prompts use approved character text. The current storyboard image model accepts text only; the approved portrait is sent by supported reference-capable video providers. A saved lock improves guidance and protects creator decisions but cannot guarantee pixel-identical generative output. Existing approved boards and completed footage are never silently changed by a new look approval.

## Main source files

Frontend: `studio-app/src/components/CharacterLookApproval.tsx`, `hooks/useCharacterLooks.ts`, `lib/characterLookApi.ts`, `pages/WritersRoom.tsx`, `pages/PrevisRoom.tsx`, `components/ProductionJourneyGuide.tsx`.
Backend: `studio-backend/app/models/character_look.py`, `routes/character_looks.py`, `services/character_look_service.py`, `utils/character_appearance.py`; character profile, reference, identity, staging and shot prompt services; conditional character storage update; main router registration.

Screenshots and browser verification records are alongside this report. Fixture portraits illustrate the interface; the live project remains unapproved.
