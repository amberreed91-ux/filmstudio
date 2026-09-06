# Theatre implementation

Implemented in `studio-app/src/pages/ScreeningRoom.tsx`. The only owned change to `StudioShell.tsx` was adding `/screening-room` to the existing compact crew predicate; another agent owns shared navigation improvements.

## Presentation

A stable, film-first player beside four freely navigable stages: Watch, Review, Approve, Deliver. Stage panels stay mounted and are hidden using the native hidden attribute. The page scrolls naturally and responds at desktop, tablet, and mobile widths. Scene, shot/scene-edit, and take selectors appear only once. A real range input makes seeking keyboard-accessible; controls have accessible names, visible focus, and touch-sized targets.

Watch holds playback and the optional full-film assembly disclosure. Review holds rationale, co-director notes, the explicit Previs revision handoff, audience perspective, audio direction, specialist reviews, and storyboard provenance. Approve holds the exact media-output approval, acceptance checks, and a collapsed but mounted Canonical Production Thread. Deliver holds the current MP4 download, screening-link copy, final stitching/export manifest, and poster generation.

Removed simulated weak-scene markers, fabricated default emotion curve, hard-coded pacing and tension judgments, advisory percentage bars, and the hard-coded THE LAST TIDE end title. Local written audience reactions remain available on explicit request. External Qwen analysis stays explicit and cache reads remain provider-free; its numeric-only result is not displayed as a creative rating.

## Preserved controls map

- Watch: scene selection; previous/next scene; shot selection; new Scene edit choice; take selection; play/pause; seek; speed; volume; preview scenes in order / full film; return to individual preview; assemble film.
- Review: request note; carry note to Previs; save note to scene in The Page; explicit save this decision to project memory; audience segment; simulate locally; explicit Qwen active-scene analysis; request/apply audio brief; Editorial, Cinematographer, PerformanceAudio, Casting, ProductionDesign, and Colorist panels; storyboard source details.
- Approve: existing approval confirmation and API; existing acceptance panel; existing CanonicalWorkflowPanel with original props and independent gate semantics.
- Deliver: existing MP4 export; clipboard screening link; final stitch; export manifest JSON; poster display/generation.
- Removed controls were duplicate scene/take navigation and fabricated weak-scene jump, not production actions.

## Authorized correctness repairs

1. Full-film end handler finishes the saved film once rather than advancing through the same full-film URL once for every scene. Sequential previews still advance as before.
2. Output approval resolves by the exact displayed playback URL and available registry record. Full-film mode requires a matching final record instead of approving whichever final package happened to be loaded.
3. MP4 export validates the response and uses a film filename for full-film playback. The export-package callback remains JSON, now accurately labelled Export manifest (JSON).
4. Scene/shot route synchronization applies external route selections once; local selectors explicitly update the route. Deep-linked shot selection is not overwritten by unconditional scene-reset effects.
5. Added an optional Scene edit choice to the existing selector so an assembled scene remains accessible when individual shot renders also exist. This selects preview UI only and never alters the cut.
6. Removed current/adjacent scene automatic audience simulation POST effects. Simulate locally remains the explicit action; external cache-only reads remain.
7. Copy screening link identifies the studio-address scope, without claiming public publication.

## Verification

- First full frontend production build passed after the main refactor.
- Targeted `npx eslint src/pages/ScreeningRoom.tsx` passed.
- Later build blocked only by concurrent Previs unused constants; root reported those already removed and owns final build/test pass.
- `/tmp/playwright-test-theatre-design.js`: headed Chromium; all four stages at 1600, 900, and 390 pixels; no horizontal overflow or runtime errors; no navigation POSTs after the explicit-only advisory fix; initial scene_001 / shot 2; switch scene_002 and back; choose shot 2; revision handoff preserves project+scene+shot.
- `/tmp/playwright-test-theatre-actions.js`: intercepts all writes; scene-edit choice selects a distinct actual saved assembly; mocked final manifest approves the displayed final registry ID; film download gets `i-was-reborn-film.mp4`; ended event shows FIN once without advancing to another scene; exactly one video element; only POST is intercepted fixture approval.
- JSON evidence: `theatre-design-verification.json`, `theatre-actions-verification.json` in this directory.
- Screenshots: `theatre-{1600,900,390}-{watch,review,approve,deliver}.png`.

No real project data was written and no generation/provider operation was submitted. Browser verification uses read-only saved footage; final approval was a local route fixture.

8. Root-requested true-status fixes: co-director request now checks HTTP success before showing a received note; audio application shows queued only after the API succeeds and clears stale success first.

## Evaluation refinement

Added a presentation-only optional `compact` prop to `studio-app/src/components/CastingIntelligencePanel.tsx`. Theatre uses it to stack the header, role/talent areas, talent fields, and matching controls within its real sidebar width. Inputs/selects and grid children use min-width containment; no controls are clipped. All casting callbacks remain unchanged.

Deliver now directs an unassembled-film project to Watch → Prepare the full film, and only names Watch full film when that action exists. Local stage scope now reads Theatre · n of 4; the shared guide uses its separately coordinated Production label.

Expanded verification passed at 1440, 1600, 900, and 390 pixels with all nested specialist, acceptance, Canonical, packaging, and poster disclosures open. No document overflow, no controls outside the viewport, zero runtime errors, zero mutation requests. Evidence: `theatre-expanded-verification.json`, `expanded-{width}-{review,approve,deliver}.png`. Script: `/tmp/playwright-test-theatre-expanded.js`.

The requested error-path fixes also passed browser fixtures: co-director HTTP500 and audio-application HTTP500 show their real errors with no false success message. Evidence: `theatre-error-verification.json`. Script: `/tmp/playwright-test-theatre-errors.js`.
