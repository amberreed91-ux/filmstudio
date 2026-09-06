# Guided Previs workflow

Previs now presents four freely navigable filmmaking steps: **Plan the shot → Approve the storyboard → Render a take → Review and assemble**. The selected scene, shot, preview, and active operation messages stay visible across steps. Detailed planning, generation settings, production handoff, and creative departments remain accessible through labeled disclosures.

The dark palette, warm amber selection, and wide preview match the existing studio. Natural page scrolling replaces the three independently scrolling columns. Smaller screens get a full-width workspace, a Rooms menu, and expandable Studio tools. The crew panel starts collapsed below the Previs content.

## Where the controls live

See [the full control map](control-map.md). Canonical Production Thread is in **Review and assemble → Production handoff**. Render provider, resolution, seed, and audio are in **Render a take → Advanced render settings**. The collapsed summary still shows the current provider, resolution, and seed.

Assembly copy reflects the existing backend behavior: it uses the latest completed take for each shot. Previewing an older take does not change the assembly. The separate whole-scene action clearly says it generates new footage.

## Validation

- Independent design evaluation passed after responsive and accessibility fixes.
- Production build passed.
- All 687 frontend tests across 76 files passed.
- All 18 existing production/action callbacks are byte-identical to the start of this redesign.
- Browser verification passed through all four steps at 1600 px and 390 px with no horizontal overflow, page exceptions, server errors, or rate-limit responses.
- Prompt, duration, resolution, provider, and seed survived navigation. The intercepted render request contained the exact entered prompt, 8 seconds, 1080p, OpenRouter, and seed 0.
- Navigation itself generated no mutation requests. Render submission was intercepted in the browser before reaching the server; this verification did not purchase or generate footage.
- Keyboard-operated disclosures exposed advanced settings and the Canonical panel. Duration/resolution presets expose selection state, and Continue/Next focus the new step heading.
- Backend services, API contracts, saved approvals, and render callbacks were not changed for this redesign.

[Browser results](browser-verification.json) · [Callback comparison](handler-comparison.json)

## Views

| Step | Desktop | Phone |
| --- | --- | --- |
| Plan | [View](desktop-plan.png) | [View](mobile-plan.png) |
| Storyboard | [View](desktop-storyboard.png) | [View](mobile-storyboard.png) |
| Render | [View](desktop-render.png) | [View](mobile-render.png) |
| Review | [View](desktop-review.png) | [View](mobile-review.png) |

## Files changed for this redesign

- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/components/StudioShell.tsx`
- `studio-app/src/components/ProjectContextBar.tsx`
- `studio-app/src/components/AICrewPresence.tsx`

The running local Vite app serves these changes at http://localhost:5001.
