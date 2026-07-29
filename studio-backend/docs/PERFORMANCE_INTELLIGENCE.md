# Performance Intelligence & Emotional Acting Engine

Sprint 12 adds the canonical acting-reasoning layer for AI Film Studio.

## Ownership

`PerformanceIntelligenceService` owns derived performance reasoning:

- character-scene objectives
- obstacles and tactics
- subtext and mask/reveal reads
- relationship pressure
- emotional carryover
- prompt, voice, audio, and screening context bundles
- explicit performance decision records

It does not own screenplay truth, visual character identity, provider execution, render state, audio generation, creative spine mutation, or automatic project memory writes.

## Canonical Boundaries

- Script structure and character arcs stay in `ScriptIntelligenceService`.
- Visual identity stays in `CharacterIdentityMemoryService`.
- Character memory stays in `MemoryService` and project memory.
- Creative Spine remains governance; Performance Intelligence reads spine evidence when available.
- Prompt, voice, and audio services consume provider-neutral performance context.
- Studio Brain receives Performance Intelligence as an advisory department signal.

## API

Project-scoped routes live under:

- `POST /api/projects/{project_id}/performance-intelligence/analyze`
- `GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}`
- `GET /api/projects/{project_id}/performance-intelligence/characters/{character_id}/history`
- `GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/prompt-context`
- `GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/voice-context/{character_id}`
- `GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/screening-context`
- `POST /api/projects/{project_id}/performance-intelligence/decisions`
- `PATCH /api/projects/{project_id}/performance-intelligence/decisions/{decision_id}`
- `DELETE /api/projects/{project_id}/performance-intelligence/decisions/{decision_id}`

## Memory Rule

Analysis never writes creative memory by default. A performance decision is projected into project memory only when `save_to_project_memory` is explicitly true.

## Public Language Guardrail

Filmmaker-facing performance output must not contain scores, ratings, percentages, or generic precision claims. Numeric internals are not part of the public Performance Intelligence contract.

## Verification

Targeted backend:

```bash
PYTHONPATH=. .venv/bin/python -m pytest app/services/test_performance_intelligence_service.py app/routes/test_performance_intelligence_routes.py app/services/test_studio_brain_service.py -q
```

Targeted frontend:

```bash
pnpm exec tsc --ignoreConfig --noEmit --target es2023 --module esnext --jsx react-jsx --moduleResolution bundler --allowImportingTsExtensions --verbatimModuleSyntax --types vite/client --skipLibCheck src/components/PerformanceIntelligencePanel.tsx src/components/ScriptIntelligencePanel.tsx src/lib/studioApi.ts
pnpm vitest run src/components/PerformanceIntelligencePanel.test.tsx
```
