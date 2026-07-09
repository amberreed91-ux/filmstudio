# Demo Green Snapshot

## Frozen State
- Tag: `cinematic-demo-green-v1`
- Backup branch: `demo-stable-backup`
- Active branch at freeze: `backend-expansion-dependency-slicing`

## Validation Snapshot
- Backend tests: passing (`python -m pytest -q`)
- Frontend tests: passing (`npm test -- --no-coverage`)
- Frontend build: passing (`npm run build`)
- Browser smoke: passing (Lobby -> Study -> Previs -> Production -> Screening)
- Demo seed flow: operational (`POST /api/f51/studio/dev/seed-demo-project`)
- Seeded project id: `demo_studio_cinematic_001`

## Verified Journey
- Study Room -> Previs Room -> Production Board -> Screening Room
- Cinematic overlays and guidance visible across room handoffs
- No critical console/API failures in final smoke capture

## Evidence
- Screenshot references:
  - `demo-evidence/final-pass/01-studio-lobby.png`
  - `demo-evidence/final-pass/02-study-room.png`
  - `demo-evidence/final-pass/03-previs.png`
  - `demo-evidence/final-pass/04-production-board.png`
  - `demo-evidence/final-pass/05-screening-room.png`
- Browser smoke report:
  - `demo-evidence/final-pass/browser-smoke.json`
