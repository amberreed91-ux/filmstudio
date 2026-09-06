# Pipeline UI implementation

Implemented in the shared working tree, preserving existing project data and backend actions.

- Added `ProductionJourneyGuide` with a quiet current-production-stage line, next-room link, expandable full four-stage path and supporting-room links. StudioShell room navigation and guide preserve project/scene/shot and await the Writer's `prepareRoomHandoff` when provided. StudioShell uses actual active project context ahead of fallback persisted IDs. Compact crew now stays in normal flow across studio rooms.
- Study now has three mounted steps: Bibles, References, Saved guidance. Project Bible form begins empty; saved Bibles and extracted guidance are available under a disclosure. Reference upload, title study, library, research and Studio Brain catalog remain accessible with optional tools disclosed. Reference reorganization is an explicit maintenance action, no longer a write on room entry. Removed the inert duplicate Ingest File button. Memory remains explicit-save and forgettable through the existing controls.
- Writer has Script and Character profiles stages. Script editor remains mounted, has an explicit Save script action, truthful loaded/saving/unsaved state and compact import/scene outline/creative support. Profiles retain appearance, energy, render text, descriptor upload, voice assignment and explicit save, with character-specific field labels. The handoff awaits script save and requires edited profiles be saved first. Root separately repaired writer persistence and imports/exports.
- Shared `useProjectRouteContext` makes explicit query/route film selection win over old context on Study, Universe and Board, and updates shared project context. Board-to-Write now uses canonical scene query parameter.
- Archive labels accurately identify Delete Film, Export JSON and Prepare export details. Removed fabricated runtime and unsupported archived filter; scene-approval status is labeled as such. “Rename” only showed details and is now labeled Details. No delete or publish action was executed.
- Workspace local checklist/notes now use Mark planned / Pin planning note and explain that real production approval lives in the workflow gates above. Responsive column and header fixes keep Workspace/Board/Archive within 390px.

## Validation

- `npm run build` passed after implementation; final root checks may include subsequent refinements.
- Targeted lint: zero errors. Existing Writer/Study hook dependency warnings retained; new route hook warning was resolved.
- Headed Playwright screenshots and checks at 1600 and 390 for Study (all three steps), Writer (script/profiles), Archive. No runtime errors; no writes attempted.
- Dedicated narrow-width DOM check after fixes: Archive, Production Board and ProjectWorkspace all have no elements extending past viewport.
- Root independently verified writer save/failure/scene handoffs and is running the full pipeline checks and independent evaluation.

Scripts: `/tmp/playwright-test-pipeline-design.js`, `/tmp/playwright-test-pipeline-overflow.js`. Screenshots and machine-readable observations are in this directory.

## Known coordination item

Reference uploads are categorized automatically by the existing backend. Removed the nonfunctional manual upload-focus selector and made this behavior explicit. Film-title study still offers its working focus selector. Bible form is keyed by the selected film so unsaved canon cannot transfer into another project.
