# Performance Audio Intelligence

Sprint 14 adds the canonical Performance Audio department for AI Film Studio. It plans and inspects voice direction, dialogue cues, character voice profiles, music, ambience, silence, sound design, and mix handoff.

## Ownership

`PerformanceAudioIntelligenceService` owns audio intelligence business logic. It creates durable, advisory records and delegates provider execution to existing audio generation services.

It does not:

- call TTS, music, or audio provider adapters directly during planning
- replace `PerformanceIntelligenceService`
- replace `DialogueVoiceService`
- replace `AmbientAudioService`
- replace voice casting or provider services
- write project memory unless the creator explicitly saves a decision

## Backend Files

- `app/models/performance_audio.py`
- `app/services/performance_audio_intelligence_service.py`
- `app/routes/performance_audio_intelligence.py`
- `app/data/storage.py` migration 46

## API

Base path:

`/api/f51/studio/projects/{project_id}/audio-intelligence`

Routes:

- `POST /plans`
- `GET /plans`
- `GET /plans/{plan_id}`
- `POST /plans/{plan_id}/execution-request`
- `POST /plans/{plan_id}/generate`
- `GET /voice-profiles`
- `GET /dialogue-cues`
- `GET /soundscape-layers`
- `POST /assessments`
- `GET /assessments`
- `POST /decisions`
- `PATCH /decisions/{decision_id}`
- `DELETE /decisions/{decision_id}`
- `GET /department-signal`

Legacy audio brief compatibility remains available through:

- `GET /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio-brief`

The legacy audio route and pipeline route are distinct:

- `POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/generate`
- `POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio/pipeline/generate`

## Persistence

Migration 46 adds:

- `performance_audio_plans`
- `character_voice_profiles`
- `dialogue_performance_cues`
- `soundscape_layer_plans`
- `audio_intelligence_assessments`
- `audio_decision_memory_projections`

Plans store nested DTOs for convenient retrieval. Cues, layers, and profiles are also stored as first-class rows so feature-length projects can query by plan, scene, track, and character.

## Memory Policy

Planning, assessment, and generation do not write memory automatically.

The only Sprint 14 memory-write path is explicit creator action through `POST /decisions` with `save_to_project_memory=true`. Decisions are editable through `PATCH /decisions/{decision_id}` and forgettable through `DELETE /decisions/{decision_id}`.

Raw voice samples, provider IDs, private notes, and transient UI toggles must not be auto-saved as memory.

## Provider Boundary

Canonical audio plans are provider-neutral. Provider IDs live only inside `VoiceProviderBinding`.

`generate_from_plan` delegates to `audio_pipeline_service.generate_full_pipeline()`. Routes must not call provider adapters directly.

Generation refuses:

- stale plans
- plans with readiness blockers

## Creative Spine And Crew Intelligence

Plans carry `AudioSpineRef` and `AudioMemoryRef` references when those systems are available. They do not copy Creative Spine or memory data as a new source of truth.

The department records Crew Intelligence under `AgentRole.SOUND_DESIGNER` with `department_name="Performance Audio"`.

## Frontend

Frontend additions:

- `studio-app/src/lib/performanceAudioApi.ts`
- `studio-app/src/components/PerformanceAudioPanel.tsx`

Mounted in:

- Previs Room
- Production Board
- Screening Room
- Crew Intelligence reasoning visibility

Frontend state must treat backend plans, assessments, and decisions as source of truth. Local state is allowed only for temporary interaction state.

## Verification

Targeted backend checks:

```bash
.venv/bin/python -m pytest \
  app/services/test_performance_audio_intelligence_service.py \
  app/routes/test_performance_audio_intelligence_routes.py \
  tests/test_audio_route_contracts.py \
  tests/test_voice_assignment_routes.py \
  tests/test_fish_audio_provider.py \
  app/services/test_ambient_audio_service.py \
  app/services/test_short_film_stitching_service.py
```

Targeted frontend checks:

```bash
pnpm test -- PerformanceAudioPanel.test.tsx CrewIntelligencePanel.test.tsx ProductionBoard.test.tsx
```

Production verification should exercise:

- build audio plan in Previs
- inspect voice profiles, dialogue cues, and soundscape layers
- inspect readiness in Production Board
- inspect assessment in Screening Room
- save, edit, and forget an explicit audio decision
- confirm legacy audio brief endpoint still works
