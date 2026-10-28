# Visual regression suite

`npm run test:visual` renders the seven audited primary surfaces against
stubbed studio APIs and compares each frame with the committed baseline in
`__screenshots__/studioRooms.visual.ts/`.

No backend, provider call, or write is involved: `/api/f51/studio/auth/access-mode`
returns local access, the project endpoint returns a fixed empty project shell,
every other `/api/**` response is `{}`, and `/outputs/**` is a 404. The suite
fails if a room paints its error boundary or raises a page error, so a crash
cannot masquerade as a passing screenshot.

```bash
npm run test:visual          # compare
npm run test:visual:update   # intentionally accept a visual change
```

Run the suite twice when validating a pass: the second run proves the frames
hold still (the lobby, for example, has decorative motion).

## Reference set

The baselines cross-reference the 2026-10-28 UI audit in
`reports/ui-audit-2026-10-28/`:

| Room | Baseline | Audit reference |
|---|---|---|
| Lobby | `lobby.png` | `studio-lobby.png` |
| Overview | `overview.png` | `overview-type-fixed.png` |
| Dashboard | `dashboard.png` | `dashboard.png`, `dashboard-cta-repaired.png` |
| Board | `board.png` | `board-hierarchy-fixed.png`, `board-type-fixed.png` |
| Previs | `previs.png` | `previs.png`, `previs-type-fixed.png`, `previs-hierarchy-fixed.png` |
| Scenes | `scenes.png` | `production-board.png`, `production-board-after.png` |
| Watch | `watch.png` | `screening-hierarchy-fixed.png` |

The audit captures were taken against live project data; these baselines render
the same surfaces with an empty project shell. They are the visual intent to
cross-reference, not byte-identical inputs — the audit images are not used for
pixel comparison.

## Platform

Baselines were captured on macOS at 1440×900, `deviceScaleFactor: 1`, dark
scheme. Font rasterization differs by OS; regenerate on the platform that owns
the gate rather than expecting identical pixels on Linux. Do not wire this
suite into a Linux CI job without first recapturing baselines there.
