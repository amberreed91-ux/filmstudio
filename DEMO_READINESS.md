# Cinematic Demo Readiness

## Demo Summary
This vertical slice demonstrates a guided cinematic workflow across five rooms:

1. **Studio Lobby** (one-click launch)
2. **Study Room** (evidence + co-director guidance)
3. **Previs Room** (shot intent + confidence bridge)
4. **Production Board** (execution command center)
5. **Screening Room** (cinematic review and package readiness)

Seeded demo project id:

- `demo_studio_cinematic_001`

## Run Commands

### Backend
```bash
cd /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-backend
APP_ENV=local RENDER_PROVIDER_TEST_MODE=mock_success python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

### Frontend
```bash
cd /Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/studio-app
npm run build
npm run preview -- --host 127.0.0.1 --port 5173
```

### Seed Endpoint
```bash
curl -X POST http://127.0.0.1:8010/api/f51/studio/dev/seed-demo-project
```

## Demo URLs

- Lobby: `http://127.0.0.1:5173/studio`
- Study: `http://127.0.0.1:5173/studio/study-room?project_id=demo_studio_cinematic_001`
- Previs: `http://127.0.0.1:5173/studio/previs?project_id=demo_studio_cinematic_001`
- Production: `http://127.0.0.1:5173/studio/production-board?project_id=demo_studio_cinematic_001`
- Screening: `http://127.0.0.1:5173/studio/screening-room?project_id=demo_studio_cinematic_001`

## Presenter Script (Short)

### What to click
1. Open `/studio`.
2. Click **Run Demo Flow**.
3. In Study Room, point out the mission checklist and co-director guidance.
4. Open Previs Room from navigation.
5. Open Production Board.
6. Open Screening Room.

### What each room proves
- **Study Room**: The system understands the project state and can guide next actions.
- **Previs Room**: Shot intent is translated into cinematic planning with confidence framing and an emotional advisory line.
- **Production Board**: Render execution is operationally visible (queue, status, readiness).
- **Screening Room**: Outputs are reviewable in a polished cinematic presentation layer with creative rationale.

### New emotional talking point
- The Studio does not just track assets, it explains why a shot matters emotionally.
- This appears in **Previs** and **Screening** as: `Why this shot matters: ...`
- It proves:
  - cinematic memory is being used in-context
  - emotional context survives into review
  - co-director guidance is actionable
  - intelligence is creative and non-generic, not just workflow bookkeeping

### Demo script line to call out live
- Notice this line: Why this shot matters. This is where the Studio shifts from workflow tracker into creative collaborator.

### Why this is not a generic AI video generator
- It is **workflow-native**, not just prompt-in/prompt-out.
- It preserves **project continuity** across rooms and stages.
- It includes **advisory intelligence** (co-director guidance, decision gate context, progression semantics).
- It now explains **creative significance** per shot/cut, not only operational status.
- It makes the user feel like they are operating a **film studio pipeline**, not a single render endpoint.

## Final Evidence

Screenshots captured in:

- `demo-evidence/final-pass/01-studio-lobby.png`
- `demo-evidence/final-pass/02-study-room.png`
- `demo-evidence/final-pass/03-previs.png`
- `demo-evidence/final-pass/04-production-board.png`
- `demo-evidence/final-pass/05-screening-room.png`

Browser smoke JSON:

- `demo-evidence/final-pass/browser-smoke.json`

## Validation Status

### Backend
- `python -m pytest -q` → **1719 passed, 0 failed**

### Frontend
- `npm test -- --no-coverage` → **266 passed, 0 failed**
- `npm run build` → **success**

### Browser smoke
- Study, Previs, Production, Screening cinematic elements verified.
- No captured console/network hard failures in final smoke checks.

## What Works
- Full seeded cinematic room flow is present and navigable.
- Production and Screening present completed seeded outputs clearly.
- Previs and Study demo guidance layers are visible for the seeded project.

## Still Rough (Known but acceptable for demo)
- Bundle size warning in frontend build (`>500kB` chunks).
- Some backend deprecation warnings (non-blocking for demo).

## Do Not Touch Before Demo
- Backend storage/schema and provider architecture.
- Demo seed route contract and seeded project id.
- Room-to-room query-based `project_id` propagation.
- Cinematic room copy/layout hierarchy already validated by smoke.
