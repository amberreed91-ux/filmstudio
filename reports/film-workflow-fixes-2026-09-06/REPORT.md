# Film workflow fixes — 2026-09-06

- Render deletion now resolves persisted jobs, propagates persistence failures, and removes the linked Previs take in the same storage transaction. Media files are retained for existing cut references. Active renders require cancellation before deletion.
- Failed/cancelled renders appear in history. Manage renders and retries is accessible in both Render and Review.
- The Page loads scenes independently of the health probe, identifies loading explicitly, and offers retry after a failed scene request. I was reborn has 14 saved scenes with nonempty script text; no screenplay data was replaced.
- Character listing is read-only and no longer seeds Last Tide characters into empty films.
- The Page has a project-scoped character profile import for TXT, Markdown, JSON, and DOCX (one named character, up to 2 MB). Existing profiles are protected from replacement. Imported profiles remain editable and require the existing explicit casting approval.

## Existing data cleanup

Four exact, unchanged Last Tide demo profiles were removed from SIX: MARA, ELI, CHILD, REPRESENTATIVE. None occurs in SIX's scene character lists; none had assigned voice IDs or character reference locks. Full rows were backed up in removed-demo-character-profiles.json before deletion. Last Tide's own cast remains intact.

## Verification

- 59 backend tests passed: render deletion, profile import, character appearance approval, casting, staging.
- 64 frontend tests passed: API requests, scene draft buffers, project context.
- Production build passed.
- ESLint: no errors; four pre-existing hook warnings in the two edited pages.
- Playwright verified scene-load retry after a simulated rate limit, selected scene persistence on reload, project-scoped profile file upload, mobile controls, and failed-render deletion remaining absent on reload. Browser mutations were intercepted; no user render was deleted and no paid provider analysis was triggered by verification.
- Restarted the local backend. Live reads verified all 14 reborn scenes, removal of the four SIX demo records, preservation of Last Tide's cast, and availability of the import endpoint.
