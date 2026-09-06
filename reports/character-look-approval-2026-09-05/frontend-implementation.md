Character look stage implemented in the existing application.

The Page now presents Script → Character profiles → Lock character looks. The third step focuses on one character at a time, with an uncropped identity image beside the saved physical description. It includes backend draft/locked state and version, portrait upload or existing reference selection, optional full-body reference, deliberate approval, and explicit revision with a cancel option. Empty, loading, error, selected, and locked states are implemented. No generated illustrations or new production images were created.

Appearance, age, descriptor upload, and visual prompt fields are protected while the backend reports a locked look. Energy and voice remain editable. Unsaved profile drafts prevent approval; saved profile updates refresh server revisions. Uploaded images remain unapproved candidates and fetch the new profile revision before approval. The route preserves project, scene, shot, selected character, and step context. Stale project responses are ignored. Previs offers one concise link to the look-approval step.

Shared journey remains four rooms. Its Write description now includes character approval, and the Previs description distinguishes storyboard approval. A collapsed explanation accurately distinguishes text-only storyboard generation from supported video-provider image conditioning and explains that existing footage is unchanged.

Modified frontend files:
- studio-app/src/components/CharacterLookApproval.tsx (new)
- studio-app/src/hooks/useCharacterLooks.ts (new)
- studio-app/src/lib/characterLookApi.ts (new)
- studio-app/src/lib/characterLookApi.test.ts (new)
- studio-app/src/pages/WritersRoom.tsx (existing, prior changes preserved)
- studio-app/src/pages/PrevisRoom.tsx (one handoff link)
- studio-app/src/components/ProductionJourneyGuide.tsx (purpose copy only)

Verification:
- 695 Vitest tests pass in 78 files, including five new API contract checks.
- Production build passes.
- Targeted ESLint: zero errors; four existing hook-dependency warnings in Writer/Previs remain.
- Browser workflow uses a fictional Nia record and reads an existing local frame as a candidate. All six POST/PUT writes were intercepted; no test approval, upload, profile mutation, or paid generation reached backend storage.
- Browser checks: deep link/no automatic approval; uploaded candidate refresh; visible stale approval rejection; explicit approval; reload persistence; locked fields; cancel revision; unsaved-draft guard; saved-description refresh; reapproval versioning; 390px overflow; provider disclosure; round-trip film/scene/shot context; visible read error.
- Script: /tmp/playwright-test-character-looks.js
- Machine report: browser-verification.json
- Screenshots: looks-desktop-draft.png, looks-desktop-selected.png, looks-desktop-locked.png, looks-mobile-locked.png, looks-mobile-error.png

No backend source or real film data changed by this implementation agent. Backend source of truth and render enforcement are being implemented by root. A character lock guides generation and cannot guarantee identical generative likeness; the current storyboard image path does not ingest portrait images. This limitation is exposed in the UI disclosure.
