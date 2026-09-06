# Universe: realistic galaxy and story atlas

The Universe page now blends a generated astrophotographic galaxy backdrop with a usable story atlas. Dimensional nodes and delicate curved connections replace the large transparent bubbles and moving edge pulses. The atlas provides searchable names and filters; selecting a node opens its actual description, tags, appearances, and relationships beside the map. Following a relationship reveals the related entry on the map.

## Interface

- Factual character, location, and connection counts replace the fabricated consistency percentage and misleading story-arc count.
- All existing add, relationship, edit, delete, simulation, population, export, and absence-guidance capabilities remain available. Simulate mind is presented for characters.
- Zoom, reset and motion controls are visible. Reduced-motion preferences and background-tab visibility are respected.
- Stable graph positions survive filtering. The map uses a capped pixel ratio and a small foreground star layer over a local 349 KB JPEG.
- Desktop uses an allocated atlas/inspector sidebar. Phone and tablet views stack; selecting an entry brings its inspector into view.
- A usable atlas remains if WebGL is unavailable. Dialogs have keyboard focus management and show request errors inside the dialog.
- Universe now uses the same collapsed, in-flow crew presentation as Previs.

No character portraits or location photographs were fabricated. Entries display the project's existing names, descriptions, tags, and relationships. The generated galaxy is decorative interface imagery.

## Small editing correction

Editing a location, object, or lore entry now preserves its existing tags rather than adding a character role. The role control appears only for characters. Eight of nine existing handle callbacks remain byte-identical to the start of this change; this tag-preservation guard is the only callback change.

## Verification

- Production build passed; targeted ESLint passed.
- All 687 frontend tests across 76 test files passed.
- Independent design evaluation passed on the first review.
- Browser exploration passed at 1600, 900, and 390 px with no horizontal overflow, runtime page exceptions, server failures, or rate-limit responses.
- Search, entity filtering, keyboard entry selection, relationship details, zoom/reset, and motion pause were exercised.
- Empty graph and reduced-motion states were tested using fixtures. A separate browser with WebGL disabled verified that atlas selection/details still work.
- Five browser-intercepted mutation attempts verified character creation, relationship creation, character editing, deletion, and location editing. Errors appeared inside the dialogs, and location tags were preserved. All five requests were stopped before reaching the backend.
- No backend/API contract changes or real project mutations were made for this redesign or its verification.

[Browser results](browser-verification.json) · [Action checks](action-verification.json) · [Callback comparison](handler-comparison.json) · [Asset provenance](asset-generation.md)

## Views

[Desktop](desktop-overview.png) · [Selected entry](desktop-inspector.png) · [Phone](mobile-overview.png) · [Phone details](mobile-inspector.png) · [Tablet](tablet-overview.png) · [WebGL fallback](webgl-fallback.png)

## Source files

- `studio-app/src/pages/UniverseGraphPage.tsx`
- `studio-app/src/components/UniverseGraph3D.tsx`
- `studio-app/src/components/StudioShell.tsx` — scoped compact crew condition
- `studio-app/public/backgrounds/assets/universe-galaxy-atlas.jpg`

The running local app serves this view at http://localhost:5001/studio/universe-graph.
