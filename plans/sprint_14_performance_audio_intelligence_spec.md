# Sprint 14: Performance Audio Intelligence

Build a voice-directing system with emotional dialogue, character voice profiles, music, ambience, and sound design intelligence.

## 1. Executive Summary

This section exists to establish the implementation mandate before engineering begins. Sprint 14 introduces **Performance Audio Intelligence**, the canonical sound department layer for AI Film Studio. It transforms dialogue, voice direction, character voice profiles, music, ambience, silence, sound design, and final audio mix planning into inspectable, provider-neutral, evidence-backed studio artifacts.

The current repository already contains several audio foundations that must be extended rather than duplicated:

- `studio-backend/app/services/audio_director_service.py` generates a scene-level `SoundAdvisory`, but it currently uses module-level helpers, reaches directly into `project_store`, raises `HTTPException` inside service code, and returns only a small brief.
- `studio-backend/app/services/dialogue_voice_service.py` builds additive dialogue lines, voice style hints, timing metadata, voice provider plans, and audio timelines.
- `studio-backend/app/services/ambient_audio_service.py` builds layered ambient tracks, dialogue ducking windows, and final film audio render plans.
- `studio-backend/app/services/audio_generation_service.py` provides legacy dialogue, score, and ambient generation using local or mock tracks.
- `studio-backend/app/services/audio_pipeline_service.py` provides the newer audio pipeline using configurable dialogue providers such as `cosyvoice`, `elevenlabs`, `fish_audio`, `piper`, optional score/ambient providers, and FFmpeg mixing.
- `studio-backend/fish_audio_provider.py`, `studio-backend/app/services/audio/cosyvoice_tts_service.py`, and `studio-backend/casting_service.py` already represent provider-specific or casting-related behavior that must remain abstracted behind services.
- `studio-backend/app/models/voice_direction_command.py`, `studio-backend/app/models/dialogue_line.py`, and `studio-backend/app/models/ambient_audio_track.py` already provide small audio-related DTOs.
- `studio-backend/app/models/performance_intelligence.py` and `studio-backend/app/services/performance_intelligence_service.py` already produce acting briefs, performance beats, voice direction lines, audio lines, evidence refs, explicit-save decision memory, and advisory-only guardrails.
- `studio-backend/app/services/crew_intelligence_service.py` already persists department reasoning, evidence refs, memory refs, spine refs, risks, recommendations, handoffs, and creator-attention items.
- `studio-app/src/components/SoundIntelligencePanel.tsx`, `AudioGenerationPanel.tsx`, `PerformanceIntelligencePanel.tsx`, `VoicePicker.tsx`, and `studio-app/src/lib/audioApi.ts` already expose sound, generation, performance, and casting UI foundations.

Sprint 14 must consolidate these into one canonical service boundary:

- `PerformanceAudioIntelligenceService`

This service owns audio intelligence business logic. It must plan, inspect, explain, persist, and hand off audio direction. It must not become a provider adapter, a parallel memory engine, a render shortcut, or a creative authority. It must consume existing performance intelligence, memory, Creative Spine, script intelligence, cinematic language, continuity, render/job evidence, voice casting, ambient planning, dialogue timing, provider capabilities, and Crew Intelligence. It must produce durable records with clear source references and downstream contracts.

The sprint adds six durable concepts:

1. `PerformanceAudioPlan`: scene or shot-level sound plan covering dialogue delivery, emotional voice direction, music intent, ambience, silence, sound design events, mix priorities, and provider-neutral generation requirements.
2. `CharacterVoiceProfile`: project-scoped profile describing a character's vocal identity, casting source, emotional range, cadence, speech restraint, continuity rules, and provider binding references.
3. `DialoguePerformanceCue`: line or beat-level cue connecting text, subtext, performance beat, character voice profile, delivery intent, pacing, breath, silence, and mix priority.
4. `SoundscapeLayerPlan`: structured music, ambience, room tone, motif, drone, impact, transition, and silence layer plan with timing and rationale.
5. `AudioIntelligenceAssessment`: comparison between intended audio plan and generated or uploaded audio/video evidence, including dialogue presence, voice continuity, mix intelligibility, emotional alignment, ambience/score restraint, and missing-source blockers.
6. `AudioReasoningRecord`: a Crew Intelligence reasoning record or linked audio-specific record capturing why an audio decision was made, what evidence was consulted, and which departments should consume the result.

The sprint adds thin routes under `/api/f51/studio/projects/{project_id}/audio-intelligence` while preserving the existing `/audio/generate`, `/audio/status`, `/audio-brief`, and `/audio/pipeline` routes. Existing routes can internally delegate to the new service over time, but public behavior must remain backward compatible.

The frontend must replace scattered sound-read surfaces with a unified **Performance Audio** inspection experience in Previs, Production Board, Screening Room, and Crew Intelligence. It must remain source-of-truth aligned with backend DTOs and must not compute creative audio judgments locally.

All creator-facing audio language must obey the studio co-director rules: no scores, ratings, percentages, generic praise, humiliating criticism, absolute certainty from sparse evidence, or automatic creative-memory writes.

## 2. Vision

This section exists to define the long-term product direction. AI Film Studio should treat sound as a filmmaking department, not an afterthought attached to video generation. The system should understand that a whisper can carry refusal, a missing room tone can break emotional realism, a score entrance can release tension too early, a repeated sound motif can turn memory into structure, and silence can be the most decisive sound design choice in a scene.

The long-term vision is a feature-length-capable audio intelligence layer that can:

- Direct voice performance from subtext and acting continuity.
- Preserve character voice identity across scenes, revisions, takes, providers, and final assembly.
- Distinguish spoken dialogue, voice-over, offscreen dialogue, diegetic sound, non-diegetic score, ambience, room tone, silence, sound effects, transitions, and final mix intent.
- Carry sound motifs from Act 1 into later callbacks without inventing a second motif system.
- Explain why audio choices matter to story impact.
- Generate provider-neutral requirements that can be fulfilled by ElevenLabs, Fish Audio, CosyVoice/Qwen, Piper, Coqui, ACE Step, MusicGen, local placeholders, or future providers.
- Inspect produced audio/video assets for verifiable audio presence and high-level continuity evidence.
- Hand off useful constraints to render, previs, screening, editorial, packaging, and Crew Intelligence.

The architectural vision is not a new sound brain parallel to Studio Brain. Performance Audio Intelligence is a Studio Brain department. It reads existing canonical sources and writes durable operational records. Project memory, Creative Spine, character casting, provider configuration, render outputs, and final approvals remain separate sources of truth.

Potential failure modes include treating music prompts as the whole audio system, losing character voice continuity across rerenders, generating dialogue from placeholder text instead of screenplay lines, mixing score over dialogue, auto-saving private creative intent, and storing provider-specific IDs as if they were canonical character identity.

Validation requires proving every audio plan cites source evidence, every assessment distinguishes observed evidence from inference, every provider-specific detail is contained behind service/provider boundaries, and every frontend surface can explain where an audio note came from.

## 3. Mission

This section exists to define the sprint's concrete product mission. Sprint 14 must build the canonical engineering foundation for voice-directing and sound intelligence across the studio pipeline.

The mission is to answer these production questions:

- What should each character sound like in this project?
- Which voice casting or clone is currently assigned, and what is canonical versus provider-specific?
- What emotional delivery should each dialogue line carry?
- Which performance beats should be whispered, withheld, interrupted, overlapped, or left silent?
- Where should music enter, recede, or stay absent?
- What ambience or room tone grounds the scene?
- Which sound design events carry story meaning rather than decoration?
- How should dialogue, score, ambience, and effects be mixed?
- Was the generated output audibly aligned enough to proceed, revise, or inspect manually?
- What evidence supports the audio department's recommendation?

Implementation must integrate with:

- `PerformanceIntelligenceService` for acting briefs, performance beats, voice direction lines, and audio lines.
- `DialogueVoiceService` for dialogue extraction, voice style hints, timing metadata, and audio timeline construction.
- `AmbientAudioService` for layered ambient plans and dialogue ducking.
- `audio_pipeline_service` and `audio_generation_service` for execution, not planning authority.
- `casting_service`, voice assignment routes, and provider-specific services for provider bindings.
- `CrewIntelligenceService` for reasoning records, handoffs, risks, and creator attention.
- `SpineService` or `SpineConsumptionService` for role-filtered constraints.
- `SemanticMemoryService`, `memory_service`, `memory_archivist`, and existing creative decision memory for read-only context unless explicit save is requested.
- `short_film_stitching_service`, `ffmpeg_stitching_service`, and final package services for final mix verification and packaging integration.

Potential failure modes include implementing routes that call providers directly, adding a second voice casting table unrelated to existing casting, duplicating performance subtext logic, bypassing FFmpeg verification, or producing UI-only audio notes with no persisted backend trace.

Validation requires route tests, service tests, persistence tests, provider abstraction tests, frontend contract tests, and production verification using mock and real/local audio evidence.

## 4. Goals

This section exists to define implementation commitments.

Sprint 14 goals:

1. Create canonical Pydantic models for audio plans, voice profiles, dialogue cues, soundscape layers, assessments, evidence refs, memory refs, spine refs, provider requirements, mix requirements, and department signals.
2. Add SQLite persistence for audio plans, character voice profiles, dialogue cues, soundscape layer plans, assessments, and explicit creator audio decisions.
3. Implement `PerformanceAudioIntelligenceService` as the only owner of audio intelligence business logic.
4. Refactor or wrap `audio_director_service` so audio brief generation delegates to the new service without breaking existing routes.
5. Reuse `PerformanceIntelligenceService` for acting/subtext inputs instead of duplicating emotional performance analysis.
6. Reuse `DialogueVoiceService` and `AmbientAudioService` for dialogue/timing/ambience utilities.
7. Keep `audio_pipeline_service` and `audio_generation_service` as execution engines, not planning authorities.
8. Integrate voice casting with existing character voice assignment and `casting_service`.
9. Record major audio reasoning through `CrewIntelligenceService`.
10. Add provider-neutral audio plan APIs and backward-compatible adapters for existing audio APIs.
11. Add frontend API types matching backend DTOs.
12. Add a unified Performance Audio panel in Previs, Production Board, Screening Room, and Crew Intelligence.
13. Add inspection UI for evidence, memory refs, spine refs, provider requirements, and mix decisions.
14. Add tests for model contracts, storage, service logic, routes, provider abstraction, frontend API, and UI workflows.
15. Ensure all creator-facing language follows co-director rules.
16. Preserve explicit-save-only memory semantics.
17. Design records for feature-length projects with pagination, staleness tracking, and source signatures.

Architectural decisions:

- Audio intelligence records are operational planning and assessment artifacts, not canonical memory.
- Character voice identity is represented separately from provider voice IDs. Provider IDs are bindings, not the voice profile itself.
- Dialogue cues reference performance beats where available. They do not copy entire performance analyses.
- Music, ambience, and sound effects are modeled as layer plans because final film audio must support multiple simultaneous tracks.
- Assessments must support low-data outcomes because early demos may only have ffprobe stream evidence or generated placeholder tones.

Validation strategy:

- Contract tests confirm every DTO defaults to `advisory_only=True`.
- Storage tests confirm records round-trip and can be filtered by project, scene, character, plan status, and staleness.
- Service tests confirm no provider adapter is called during planning.
- Integration tests confirm audio execution consumes an approved plan but remains provider-abstract.

## 5. Non-Goals

This section exists to prevent scope creep and duplicate systems.

Sprint 14 does not:

- Replace `PerformanceIntelligenceService`.
- Replace `DialogueVoiceService`.
- Replace `AmbientAudioService`.
- Replace `audio_pipeline_service` or `audio_generation_service`.
- Replace `casting_service` or existing voice assignment routes.
- Replace `CrewIntelligenceService`.
- Replace Creative Spine, memory services, script intelligence, or render services.
- Create a new provider registry separate from existing provider configuration patterns.
- Build a full digital audio workstation.
- Implement professional waveform editing, spectral repair, ADR session recording, stem mastering, loudness normalization for every delivery platform, surround mixing, Dolby Atmos, or sample-accurate timeline editing in this sprint.
- Automatically clone voices without explicit source, provider readiness, and consent-aware user action.
- Store private voice samples in memory automatically.
- Auto-save Creative Decision Memory.
- Make audio recommendations block creator workflow.
- Use scores, ratings, percentages, or public quality grades.
- Couple canonical audio records to one provider such as ElevenLabs, Fish Audio, CosyVoice, ACE Step, or MusicGen.

Architectural decision:

Provider-specific execution belongs to provider-facing services. Performance Audio Intelligence produces requirements and evidence-backed recommendations. It may call an execution service only through a service boundary that already owns provider interaction.

Failure modes:

- Engineers add a second voice profile system only for the UI.
- The new service mutates scene JSON directly instead of using storage methods.
- Audio plan status becomes confused with render job status.
- Generated tracks are treated as approved final audio without assessment.

Validation strategy:

- Code review must verify no new direct route-to-provider or route-to-storage access.
- Tests must verify plan creation works with no configured external provider.
- Documentation must clearly separate planning, generation, assessment, approval, and memory save.

## 6. Existing Architecture Analysis

This section exists because implementation must start from current architecture.

Backend architecture:

- FastAPI routes live in `studio-backend/app/routes`.
- Services live in `studio-backend/app/services`.
- DTOs live in `studio-backend/app/models`.
- SQLite persistence is centralized in `studio-backend/app/data/storage.py`.
- The project follows thin routes, service-owned business logic, and storage-mediated persistence.

Existing audio and adjacent systems:

- `audio.py` route module exposes audio generation, status, capabilities, audio brief, brief apply, and newer audio pipeline routes.
- `audio.py` currently defines duplicate `POST /projects/{project_id}/scenes/{scene_id}/audio/generate` and duplicate `GET /projects/{project_id}/scenes/{scene_id}/audio/status` route functions in the same file. Sprint 14 must resolve this route ambiguity without removing existing public behavior. The safest path is to keep the public URLs but delegate to a single routing function that can choose legacy or pipeline execution based on request fields and configuration.
- `audio_director_service.py` has useful LLM prompt behavior but violates desired service boundaries by raising HTTP exceptions and reading `project_store` directly through local helper functions.
- `dialogue_voice_service.py` is a deterministic utility for building dialogue lines, timing, and audio timeline clips.
- `ambient_audio_service.py` is a deterministic utility for ambient layers and dialogue ducking.
- `audio_generation_service.py` is an execution service with in-memory job tracking and mock fallback.
- `audio_pipeline_service.py` is a richer execution service with provider selection, FFmpeg checks, dialogue provider abstractions, and optional score/ambient support.
- `casting_service.py` maps character casting to voice provider, voice ID, baseline emotion, and line-level audio requests.
- `fish_audio_provider.py` is currently top-level, not under `app/services/providers` or `app/services/audio`. It should be treated as an existing adapter to preserve, then optionally relocated later with compatibility imports.
- `performance_intelligence_service.py` already produces `PerformanceContextBundle.audio_lines` and `voice_lines`, plus explicit-save-only decisions.
- `crew_intelligence_service.py` already persists explainable department reasoning.
- `short_film_stitching_service.py` already validates audio source presence and preserves existing dialogue audio when mixing soundtrack.

Frontend architecture:

- Active frontend appears to be `studio-app`.
- `studio-app/src/lib/audioApi.ts` wraps legacy audio endpoints and defines current frontend audio types.
- `AudioGenerationPanel.tsx` displays dialogue, score, and ambient track status.
- `SoundIntelligencePanel.tsx` displays sound advisories from script analysis, but it currently fetches `/api/projects/{projectId}/script-analysis/sound`, which is outside the `/api/f51/studio` namespace used by most studio APIs.
- `PerformanceIntelligencePanel.tsx` displays acting briefs and saves explicit performance decisions.
- `PrevisRoom.tsx` has local audio config for voice, music, and SFX; this local state should become a view/edit surface for backend audio plans, not a second source of truth for production-critical audio intent.
- Screening and Previs showcase components already mention tension and audio signals, but those signals are not yet backed by a canonical audio intelligence DTO.

Repository overlap:

- Scene sound advisory exists in script intelligence and audio director brief.
- Dialogue line generation exists in `DialogueVoiceService` and route-local extraction.
- Voice casting exists in voice assignment routes and `casting_service`.
- Ambient tracks exist in `AmbientAudioService`.
- Generation status exists in both legacy and pipeline services.
- Performance voice direction exists in Performance Intelligence but is not yet tied to generated audio.

Architectural decision:

Sprint 14 must consolidate planning and reasoning in `PerformanceAudioIntelligenceService` while preserving existing execution services. It should not delete existing systems in the first pass. It should introduce compatibility adapters, then migrate route internals and UI consumers to the canonical plan APIs.

Potential failure modes:

- Route ambiguity remains and one route shadows another unpredictably.
- Existing tests assume legacy response shapes and fail if migration is abrupt.
- Audio generation continues to use placeholder lines when structured dialogue exists.
- Frontend local audio config diverges from backend audio plan.

Validation strategy:

- Add API regression tests for existing endpoints before migration.
- Add explicit tests for route uniqueness and expected handler behavior.
- Add frontend tests proving panels render backend plan data and do not require local-only audio config.

## 7. Repository Inspection Checklist

This section exists to make implementation evidence-driven.

Before coding, engineers must inspect:

- `studio-backend/app/routes/audio.py`
- `studio-backend/app/services/audio_director_service.py`
- `studio-backend/app/services/dialogue_voice_service.py`
- `studio-backend/app/services/ambient_audio_service.py`
- `studio-backend/app/services/audio_generation_service.py`
- `studio-backend/app/services/audio_pipeline_service.py`
- `studio-backend/app/services/audio/cosyvoice_tts_service.py`
- `studio-backend/fish_audio_provider.py`
- `studio-backend/casting_service.py`
- `studio-backend/app/models/dialogue_line.py`
- `studio-backend/app/models/ambient_audio_track.py`
- `studio-backend/app/models/voice_direction_command.py`
- `studio-backend/app/models/script_intelligence.py` for `SoundAdvisory`
- `studio-backend/app/models/performance_intelligence.py`
- `studio-backend/app/services/performance_intelligence_service.py`
- `studio-backend/app/services/crew_intelligence_service.py`
- `studio-backend/app/models/crew.py`
- `studio-backend/app/models/crew_intelligence.py`
- `studio-backend/app/services/spine_service.py`
- `studio-backend/app/services/semantic_memory_service.py`
- `studio-backend/app/services/memory.py`
- `studio-backend/app/services/memory_archivist.py`
- `studio-backend/app/services/short_film_stitching_service.py`
- `studio-backend/app/services/ffmpeg_stitching_service.py`
- `studio-backend/app/data/storage.py`
- `studio-backend/main.py`
- Audio tests under `studio-backend/tests/test_*audio*`, `test_voice_assignment_routes.py`, `test_fish_audio_provider.py`, and provider comparison tests.
- Service tests under `studio-backend/app/services/test_ambient_audio_service.py`, `test_voice_direction_interpreter_service.py`, and related performance tests.
- `studio-app/src/lib/audioApi.ts`
- `studio-app/src/lib/studioApi.ts`
- `studio-app/src/components/AudioGenerationPanel.tsx`
- `studio-app/src/components/SoundIntelligencePanel.tsx`
- `studio-app/src/components/PerformanceIntelligencePanel.tsx`
- `studio-app/src/components/VoicePicker.tsx`
- `studio-app/src/components/CrewIntelligencePanel.tsx`
- `studio-app/src/pages/PrevisRoom.tsx`
- `studio-app/src/pages/ProductionBoard.tsx`
- `studio-app/src/pages/ScreeningRoom.tsx`

Inspection must answer:

- Which existing endpoint shapes must remain stable?
- Which code currently owns generation execution?
- Which code currently owns character voice assignment?
- Which scene fields contain real dialogue versus placeholders?
- Which persistence tables already exist for audio-adjacent records?
- Which frontend panels are already mounted in target rooms?
- Which tests lock behavior?

Potential failure modes:

- Engineers implement against stale documentation rather than current code.
- Provider comparison scripts are mistaken for canonical product services.
- Top-level `casting_service.py` is ignored, leading to duplicate casting logic.

Validation strategy:

- Attach inspection notes to the implementation PR.
- Include a migration map from old audio concepts to new canonical concepts.
- Run targeted tests before and after route consolidation.

## 8. Gap Analysis

This section exists to make the sprint's necessity precise.

Current gaps:

- No canonical, durable audio plan exists.
- Character voice identity is not separated cleanly from provider voice IDs.
- Audio director briefs are scene-level only and not tied to performance beats.
- Dialogue timing exists but is not persisted as an inspectable plan.
- Music and ambience are generated from short notes rather than layered, reasoned soundscape plans.
- Sound design events are not modeled as first-class craft decisions.
- Silence is a boolean, not a timed, motivated plan element.
- Audio assessments are mostly script/test artifacts and ffprobe checks, not product records.
- Crew Intelligence does not yet represent a dedicated audio department role.
- Audio execution routes are ambiguous and partly duplicated.
- Existing services use different response shapes and job tracking strategies.
- Frontend audio controls rely on local state and legacy endpoints.
- Sound Intelligence panel uses a different API namespace from most studio APIs.
- Memory integration is read-only and implicit rather than traceable in audio outputs.
- Creative Spine constraints are not applied to audio planning.
- Studio Knowledge Engine traceability for audio choices is not yet modeled.

Canonical overlaps to eliminate:

- `SoundAdvisory` and audio brief should become a projection of `PerformanceAudioPlan`, not a separate planning source.
- Route-local dialogue extraction should delegate to a service method.
- Voice style hints should be sourced from `CharacterVoiceProfile` plus Performance Intelligence, not rebuilt independently per route.
- Ambient ducking should stay in `AmbientAudioService` and be called by the canonical service.
- Provider readiness should be read from execution services, not duplicated.

Potential failure modes:

- Audio plan becomes too broad and replaces generation execution.
- Character voice profiles become too provider-specific.
- Assessments overclaim from limited audio evidence.
- Frontend surfaces show stale plans after scene text changes.

Validation strategy:

- Each persisted plan and assessment must include `source_signature`, `model_version`, `stale`, and `stale_reason`.
- Every public note must contain either evidence refs or a low-data reason.
- Integration tests must prove scene edits mark old plans stale or create new source signatures.

## 9. Architectural Principles

This section exists to guide implementation decisions.

Principles:

1. Extend canonical systems. Reuse Performance Intelligence, Crew Intelligence, memory, Creative Spine, provider services, and audio execution services.
2. Keep planning separate from execution. Audio Intelligence creates requirements; generation services render assets.
3. Keep canonical voice identity provider-neutral. Provider voice IDs are bindings.
4. Make every major audio decision inspectable. Plans and assessments must show evidence, inference, rationale, and downstream impact.
5. Preserve creator authority. The system advises and prepares; the creator approves, revises, rejects, saves, or forgets.
6. Avoid hidden scoring. Use labels such as `insufficient_context`, `emerging`, `supported`, `conflicted`, `ready`, `blocked`, and `needs_review`.
7. Design for feature-length projects. Use pagination, source signatures, indexes, and lightweight references.
8. Support low-data operation. The system must still help when only script text exists, but it must label uncertainty honestly.
9. Keep provider implementations abstract. Canonical models must not assume one TTS, music, or audio analysis provider.
10. Preserve backward compatibility. Existing endpoints and UI behavior should continue while migrating internals.
11. No automatic memory writes. Audio plans may propose memory saves; only explicit creator action persists creative decisions.
12. Keep routes thin. Routes parse, validate, call services, and format HTTP errors.

Potential failure modes:

- Service accumulates provider-specific conditionals until it becomes an adapter.
- UI computes audio readiness locally.
- Audio decisions mutate project JSON without durable records.

Validation strategy:

- Code review checklist must enforce the principles.
- Tests must assert advisory flags, provider-neutral fields, source references, and route boundaries.

## 10. High-Level System Design

This section exists to define the system shape.

High-level flow:

1. User opens Previs, Production Board, Screening, or Crew Intelligence.
2. Frontend requests audio intelligence state for a project, scene, shot, character, or asset.
3. `PerformanceAudioIntelligenceService` loads project/scene data through existing project services/storage.
4. Service loads optional Performance Intelligence context.
5. Service loads role-filtered memory and Creative Spine context.
6. Service resolves character voice profiles and casting bindings.
7. Service builds or retrieves `PerformanceAudioPlan`.
8. Service derives dialogue cues through `DialogueVoiceService`.
9. Service derives soundscape layers through `AmbientAudioService` and new local layer planning logic.
10. Service creates Crew Intelligence reasoning.
11. If generation is requested, execution is delegated to `audio_pipeline_service` or legacy `audio_generation_service` through a service boundary.
12. Generated assets are assessed through available evidence such as file presence, ffprobe streams, known generated clip metadata, dialogue timeline, and future waveform/transcription adapters.
13. Screening and packaging consume assessments and final mix requirements.

New backend modules:

- `studio-backend/app/models/performance_audio.py`
- `studio-backend/app/services/performance_audio_intelligence_service.py`
- `studio-backend/app/routes/performance_audio_intelligence.py`

Potential supporting module:

- `studio-backend/app/services/audio_evidence_service.py` for ffprobe, waveform placeholder detection, generated asset metadata, and future transcript adapters. This should remain small and provider-neutral.

Existing modules to update:

- `main.py` include new route.
- `storage.py` add tables and methods.
- `audio.py` delegate brief and generation compatibility paths.
- `models/crew.py` add `SOUND_DESIGNER` or `AUDIO_DIRECTOR` role if compatible.
- `CrewIntelligenceService` department profiles should include audio department.
- Frontend API clients and panels.

Architectural decision:

The audio department should be named **Performance Audio** in product surfaces because Sprint 14 explicitly joins emotional dialogue, voice directing, music, ambience, and sound design. Internally, the service name should remain explicit: `PerformanceAudioIntelligenceService`.

Potential failure modes:

- Adding both `AUDIO_DIRECTOR` and `SOUND_DESIGNER` roles causes role fragmentation.
- Existing `StudioLanding` composer/sound designer labels imply separate departments; the sprint should either map both labels to the same backend role or add separate display labels backed by one canonical service.

Validation strategy:

- Confirm Crew Intelligence overview can show audio department status with one canonical role.
- Confirm all public audio APIs return consistent plan IDs and reasoning IDs where applicable.

## 11. Component Design

This section exists to define each component's responsibility.

### `PerformanceAudioIntelligenceService`

Responsibilities:

- Validate project, scene, shot, character, and asset inputs.
- Build source signatures from scene text, dialogue lines, character profiles, casting bindings, memory refs, Creative Spine refs, performance analysis IDs, and relevant render/asset IDs.
- Create `CharacterVoiceProfile` records.
- Create `PerformanceAudioPlan` records.
- Create `DialoguePerformanceCue` records.
- Create `SoundscapeLayerPlan` records.
- Create `AudioIntelligenceAssessment` records.
- Produce compatibility `SoundAdvisory` projections.
- Produce execution requests for `audio_pipeline_service`.
- Create Crew Intelligence reasoning records.
- Mark records stale when source signatures no longer match.

Non-responsibilities:

- Calling provider APIs directly.
- Storing raw voice samples.
- Approving final creative decisions.
- Performing deep audio DSP beyond available evidence helpers.

### `AudioEvidenceService`

Responsibilities:

- Inspect local audio/video files using existing FFmpeg/ffprobe patterns.
- Report audio stream presence, duration, codec, container, and known generated clip metadata.
- Validate that expected dialogue clips exist when generation metadata is available.
- Provide low-data assessment inputs.

Non-responsibilities:

- Transcription, diarization, voice similarity, loudness mastering, or source separation in Sprint 14.

### Existing `DialogueVoiceService`

Use for:

- Dialogue lines.
- Timing metadata.
- Audio timeline clips.

Required change:

- Add optional methods to consume `CharacterVoiceProfile` and `PerformanceContextBundle` without changing existing method behavior.

### Existing `AmbientAudioService`

Use for:

- Layered ambience.
- Ducking windows.
- Final mix plan skeleton.

Required change:

- Accept richer `SoundscapeLayerPlan` inputs while preserving current `AmbientAudioTrack` outputs.

### Existing `audio_pipeline_service`

Use for:

- Actual dialogue, optional score/ambient, FFmpeg mixing, and merge-to-video execution.

Required change:

- Add an execution entry point that accepts a `PerformanceAudioPlan` or an execution DTO derived from it.
- Preserve current request shape.

### Existing `CrewIntelligenceService`

Use for:

- Durable audio department reasoning, risks, recommendations, handoffs, and creator attention.

Required change:

- Add department profile and role mapping for Performance Audio.

Potential failure modes:

- `PerformanceAudioIntelligenceService` grows large. Keep provider and evidence helpers separate.
- Existing services are modified destructively. Add optional parameters and adapters first.

Validation strategy:

- Unit tests per component.
- Integration tests proving service calls can be stubbed and no provider calls occur in planning.

## 12. Data Model Changes

This section exists to specify contracts and persistence.

Create `app/models/performance_audio.py`.

Core literals:

- `AudioPlanScope = Literal["project", "scene", "shot", "asset"]`
- `AudioPlanStatus = Literal["draft", "ready", "needs_creator_review", "superseded", "stale"]`
- `AudioTrackType = Literal["dialogue", "voiceover", "score", "ambience", "room_tone", "sfx", "silence", "transition", "final_mix"]`
- `AudioEvidenceSourceType = Literal["script_scene", "dialogue_line", "performance_brief", "character_profile", "voice_casting", "creative_memory", "director_memory", "film_memory", "continuity", "creative_spine", "render_job", "audio_asset", "video_asset", "ffprobe", "provider_metadata", "manual_note"]`
- `AudioUncertaintyLabel = Literal["insufficient_context", "emerging", "supported", "conflicted"]`
- `AudioReadinessLabel = Literal["ready", "needs_review", "blocked", "not_requested"]`

Models:

- `AudioEvidenceRef`
  - `evidence_id`
  - `source_type`
  - `source_id`
  - `field_path`
  - `scene_id`
  - `shot_id`
  - `character_id`
  - `asset_id`
  - `excerpt`
  - `relevance`
  - `reliability_label`

- `AudioMemoryRef`
  - `memory_id`
  - `memory_type`
  - `scope`
  - `scene_id`
  - `character_id`
  - `summary`
  - `source_service`

- `AudioSpineRef`
  - `constraint_id`
  - `field_name`
  - `summary`
  - `applied`
  - `risk_if_ignored`

- `VoiceProviderBinding`
  - `binding_id`
  - `provider`
  - `voice_id`
  - `voice_name`
  - `voice_source_type`
  - `voice_style_prompt`
  - `reference_asset_id`
  - `configured`
  - `requires_network`
  - `last_verified_at`
  - `metadata`

- `CharacterVoiceProfile`
  - `profile_id`
  - `project_id`
  - `character_id`
  - `character_name`
  - `vocal_identity`
  - `cadence`
  - `emotional_range`
  - `restraint_rules`
  - `speech_patterns`
  - `continuity_notes`
  - `provider_bindings`
  - `evidence_refs`
  - `memory_refs`
  - `source_signature`
  - `status`
  - `created_at`
  - `updated_at`
  - `stale`
  - `stale_reason`
  - `advisory_only`

- `DialoguePerformanceCue`
  - `cue_id`
  - `project_id`
  - `plan_id`
  - `scene_id`
  - `shot_id`
  - `line_id`
  - `character_id`
  - `character_name`
  - `text`
  - `spoken_intent`
  - `hidden_intent`
  - `delivery`
  - `pacing`
  - `breath`
  - `pause_before_seconds`
  - `pause_after_seconds`
  - `overlap_behavior`
  - `volume_intent`
  - `mix_priority`
  - `voice_profile_id`
  - `performance_brief_id`
  - `performance_beat_id`
  - `evidence_refs`
  - `uncertainty_label`
  - `advisory_only`

- `SoundscapeLayerPlan`
  - `layer_id`
  - `project_id`
  - `plan_id`
  - `scene_id`
  - `shot_id`
  - `track_type`
  - `label`
  - `intent`
  - `start_seconds`
  - `end_seconds`
  - `intensity_label`
  - `duck_under_dialogue`
  - `motif_refs`
  - `provider_requirement`
  - `evidence_refs`
  - `memory_refs`
  - `spine_refs`
  - `advisory_only`

- `AudioMixRequirement`
  - `dialogue_priority`
  - `score_position`
  - `ambience_position`
  - `sfx_position`
  - `ducking_strategy`
  - `silence_strategy`
  - `final_container`
  - `requires_audio_stream`
  - `preserve_existing_dialogue`
  - `notes`

- `PerformanceAudioPlan`
  - `plan_id`
  - `project_id`
  - `scope`
  - `scene_id`
  - `shot_id`
  - `asset_id`
  - `status`
  - `generated_at`
  - `updated_at`
  - `model_version`
  - `source_signature`
  - `summary`
  - `voice_profiles`
  - `dialogue_cues`
  - `soundscape_layers`
  - `mix_requirements`
  - `provider_requirements`
  - `reasoning_trace`
  - `evidence_refs`
  - `memory_refs`
  - `spine_refs`
  - `crew_reasoning_id`
  - `readiness_label`
  - `blockers`
  - `stale`
  - `stale_reason`
  - `advisory_only`

- `AudioIntelligenceAssessment`
  - `assessment_id`
  - `project_id`
  - `plan_id`
  - `scene_id`
  - `shot_id`
  - `asset_id`
  - `render_job_id`
  - `generated_at`
  - `source_signature`
  - `observed_audio_stream`
  - `observed_dialogue_presence`
  - `observed_music_presence`
  - `observed_ambience_presence`
  - `voice_continuity_read`
  - `emotional_alignment_read`
  - `mix_read`
  - `missing_evidence`
  - `risks`
  - `recommendations`
  - `evidence_refs`
  - `crew_reasoning_id`
  - `readiness_label`
  - `stale`
  - `stale_reason`
  - `advisory_only`

- `PerformanceAudioDepartmentSignal`
  - `role`
  - `status`
  - `signal`
  - `plan_count`
  - `assessment_count`
  - `blocked_count`
  - `evidence_count`
  - `advisory`
  - `advisory_only`

Persistence tables:

- `performance_audio_plans`
- `character_voice_profiles`
- `dialogue_performance_cues`
- `soundscape_layer_plans`
- `audio_intelligence_assessments`
- `audio_decision_memory_projections`

Indexes:

- `(project_id, scene_id)`
- `(project_id, character_id)`
- `(project_id, status)`
- `(project_id, stale)`
- `(project_id, created_at/generated_at)`
- `(plan_id)`
- `(asset_id)`
- `(render_job_id)`

Potential failure modes:

- JSON blobs become opaque and unqueryable. Store top-level filter fields as columns and nested content as JSON.
- Voice provider binding leaks sensitive data. Store provider IDs and metadata, not API keys or raw samples.

Validation strategy:

- Pydantic contract tests.
- SQLite migration idempotency tests.
- Round-trip tests with nested refs.

## 13. Memory Integration

This section exists because audio choices must be traceable without becoming unauthorized memory.

Read sources:

- `memory_service.read_memory(project_id)` for project and character memory.
- `memory_service.get_context_for_agent()` through Crew Intelligence role context.
- `SemanticMemoryService` where available for scene mood, motif, visual/audio tags, and cinematic notes.
- `memory_archivist` records for motifs, callbacks, and warnings.
- Existing Creative Decision Memory and Performance Decision Memory only when explicitly saved by the creator.

Write policy:

- Audio plans do not write memory automatically.
- Assessments do not write memory automatically.
- Voice profiles do not write creative memory automatically.
- A creator may explicitly save an audio decision to project memory through a dedicated endpoint.
- Saved decisions must be editable and forgettable.
- Raw reference audio, private notes, transient toggles, and provider samples must never be auto-saved.

Required endpoint:

- `POST /audio-intelligence/decisions`
  - Saves an explicit creator audio decision.
  - Optional `save_to_project_memory`.
  - Requires `decision_text`.
  - May reference `plan_id`, `cue_id`, `layer_id`, `profile_id`, or `assessment_id`.

Memory projection examples:

- "Keep Mara's voice lower and slower when she is protecting information."
- "The train-brake motif should return only when memory breaks into the present."
- "Do not score the apology; let room tone carry the discomfort."

Potential failure modes:

- The system infers permanent voice identity from one generated line.
- Provider clone metadata is treated as memory.
- Frontend save buttons bypass explicit confirmation.

Validation strategy:

- Tests confirm memory write only occurs through explicit save endpoint.
- Tests confirm forgetting marks records forgotten without deleting audit context needed for project integrity.
- UI tests confirm plan generation does not display "saved to memory."

## 14. Creative Spine Integration

This section exists because audio direction must preserve the film's governing creative identity.

Creative Spine inputs:

- Emotional contract.
- Restraint rules.
- Genre lane.
- Motif constraints.
- Pacing philosophy.
- Tone boundaries.
- Frozen fields.
- Character arc constraints.

Implementation:

- Use `SpineService` or `SpineConsumptionService.get_context_for_role()`.
- Add a role mapping for Performance Audio. If `AgentRole` is extended, prefer one role: `SOUND_DESIGNER = "sound_designer"` or `AUDIO_DIRECTOR = "audio_director"`. If minimizing enum churn is safer, map audio to `AgentRole.EDITOR` temporarily in Crew context but store `department_name="Performance Audio"`. The preferred implementation is to add `SOUND_DESIGNER` because existing UI copy already references Sound Designer and Composer, and sound design covers dialogue, music, ambience, and final mix.
- Store `AudioSpineRef` records on plans, layers, cues, and assessments.
- Include spine constraints in reasoning but do not copy Creative Spine fields into audio records as canonical truth.

Examples:

- Spine restraint rule says grief should stay implied. Audio plan delays score entrance and favors room tone.
- Motif rule says the memory tone returns only at callbacks. Soundscape layer references motif memory instead of generating generic drones.
- Pacing philosophy favors patience. Dialogue cue includes longer pause after the line and lower score density.

Potential failure modes:

- Audio plan contradicts Creative Spine because spine lookup fails silently.
- Spine fields are copied and drift from canonical spine.
- Audio department blocks workflow due to spine concerns.

Validation strategy:

- Tests with spine available and unavailable.
- Tests assert spine refs are references, not copied canonical fields.
- Crew reasoning should include risks rather than blocking actions.

## 15. Studio Knowledge Engine Integration

This section exists to make audio decisions traceable to studio knowledge.

In this codebase, the Studio Knowledge Engine is represented by overlapping canonical sources:

- Project store and execution summary.
- Script Intelligence.
- Performance Intelligence.
- Semantic Memory.
- Memory Archivist.
- Director Memory.
- Creative Decision Memory.
- Creative Spine.
- Continuity and style intelligence.
- Crew Intelligence reasoning ledger.
- Render and asset metadata.

Sprint 14 must not create a new knowledge graph. It must expose knowledge traceability through refs:

- `AudioEvidenceRef`
- `AudioMemoryRef`
- `AudioSpineRef`
- `crew_reasoning_id`
- `source_signature`
- `reasoning_trace`

Knowledge integration strategy:

- Every plan lists canonical sources consulted.
- Every cue lists the line, character, performance brief, and evidence refs.
- Every layer lists scene, motif, memory, spine, and rationale refs.
- Every assessment lists observed asset/render evidence and what remains unknown.
- Crew Intelligence stores the department-level reasoning summary.

Potential failure modes:

- Engineers create an `audio_knowledge` table duplicating memory.
- Evidence refs point to records that cannot be retrieved.
- Reasoning traces include private provider payloads.

Validation strategy:

- Tests assert evidence refs contain source type and source ID.
- API responses must include enough metadata for UI inspection.
- Documentation must define each source type and retrieval expectation.

## 16. AI Department Responsibilities

This section exists to define department boundaries.

Performance Audio department owns:

- Character voice profile planning.
- Dialogue delivery cues.
- Emotional voice direction.
- Score intent and restraint.
- Ambience and room tone planning.
- Sound design events and motifs.
- Silence strategy.
- Mix priority guidance.
- Audio generation readiness.
- Audio assessment and revision recommendations.
- Crew reasoning handoffs for audio.

Performance Audio consumes:

- Writer/script dialogue.
- Performance Intelligence subtext and beats.
- Creative Spine constraints.
- Memory motifs and character history.
- Continuity warnings.
- Cinematic language and pacing context.
- Render and asset metadata.
- Provider readiness from execution services.

Performance Audio does not own:

- Story truth.
- Character biography truth.
- Creative approvals.
- Provider adapter internals.
- Final render job lifecycle.
- Final packaging lifecycle.
- Memory writes without explicit save.

Collaboration partners:

- Director: creative intent and final decision.
- Writer: dialogue text and subtext.
- Performance Intelligence: acting and line delivery.
- Cinematographer: camera/audio relationship, offscreen sound, silence.
- Editor: transition sound, pacing, dialogue overlap, final cut timing.
- Continuity Supervisor: voice/motif/ambience continuity.
- Memory Archivist: motif callbacks and saved decisions.
- Render Coordinator: execution readiness and asset status.

Potential failure modes:

- Composer, sound designer, and dialogue director become three separate backend brains too early.
- Audio department rewrites dialogue text instead of cueing delivery.
- Audio department changes final mix without creator approval.

Validation strategy:

- Department profile tests.
- Crew overview tests.
- Handoff tests between Performance Audio and Editor/Render Coordinator.

## 17. Backend Implementation Plan

This section exists to give engineers an executable sequence.

Phase 1: Contracts and role setup

1. Add `app/models/performance_audio.py`.
2. Add `AgentRole.SOUND_DESIGNER = "sound_designer"` unless a lower-risk compatibility mapping is chosen.
3. Add department profile metadata for Performance Audio.
4. Add DTO contract tests.

Phase 2: Storage

1. Add idempotent table creation in `DatabaseStorage`.
2. Add methods:
   - `save_performance_audio_plan`
   - `get_performance_audio_plan`
   - `list_performance_audio_plans`
   - `save_character_voice_profile`
   - `get_character_voice_profile`
   - `list_character_voice_profiles`
   - `save_dialogue_performance_cue`
   - `list_dialogue_performance_cues`
   - `save_soundscape_layer_plan`
   - `list_soundscape_layer_plans`
   - `save_audio_intelligence_assessment`
   - `get_audio_intelligence_assessment`
   - `list_audio_intelligence_assessments`
   - `save_audio_decision_memory_projection`
   - `update_audio_decision_memory_projection`
3. Add storage tests.

Phase 3: Core service

1. Implement `PerformanceAudioIntelligenceService`.
2. Inject storage, project store, performance intelligence, dialogue voice, ambient audio, crew intelligence, memory, spine, and pipeline services.
3. Add deterministic plan generation first.
4. Add optional LLM enhancement later only behind the service.
5. Add guardrails for creator-facing language.
6. Add staleness/source signature logic.
7. Add Crew Intelligence reasoning.

Phase 4: Compatibility migration

1. Update `audio_director_service.generate_scene_audio_brief()` to call the new service and project a `SoundAdvisory`.
2. Consolidate duplicate audio routes in `audio.py`.
3. Preserve existing response models.
4. Add tests proving old clients still work.

Phase 5: Execution integration

1. Add `build_audio_execution_request(plan_id)` service method.
2. Add `generate_from_plan(plan_id, options)` service method that delegates to `audio_pipeline_service`.
3. Ensure no provider calls happen in routes.
4. Ensure generation output links back to plan ID.

Phase 6: Assessment

1. Add `AudioEvidenceService`.
2. Implement assessment from local file/render job evidence.
3. Add low-data labels and missing evidence.
4. Record assessment reasoning.

Phase 7: Frontend

1. Add `studio-app/src/lib/performanceAudioApi.ts`.
2. Add shared types or extend `studioApi.ts`.
3. Add `PerformanceAudioPanel.tsx`.
4. Add `CharacterVoiceProfilePanel.tsx` if panel complexity warrants separation.
5. Add `AudioPlanInspectionDrawer.tsx`.
6. Mount panels in Previs, Production Board, Screening Room, and Crew Intelligence.
7. Migrate `SoundIntelligencePanel` to consume new APIs or deprecate behind compatibility.

Phase 8: Tests and docs

1. Add backend unit, integration, and API tests.
2. Add frontend rendering and API tests.
3. Add production verification scripts or documented manual verification.
4. Update documentation.

Potential failure modes:

- Big-bang route migration breaks existing audio generation.
- Tests mock too much and miss provider boundary violations.
- Frontend panel ships before persistence is stable.

Validation strategy:

- Merge in small commits by phase.
- Keep old endpoints green through every phase.

## 18. API Design

This section exists to define backend contracts.

Base path:

- `/api/f51/studio/projects/{project_id}/audio-intelligence`

Endpoints:

- `POST /plans`
  - Request: `PerformanceAudioPlanRequest`
  - Creates or refreshes a plan for project/scene/shot.
  - Optional `persist=true`.
  - Returns `PerformanceAudioPlan`.

- `GET /plans`
  - Query: `scene_id`, `shot_id`, `status`, `stale`, `limit`, `offset`
  - Returns paginated plans.

- `GET /plans/{plan_id}`
  - Returns one plan.

- `POST /plans/{plan_id}/execution-request`
  - Builds provider-neutral execution request.
  - Does not generate audio.

- `POST /plans/{plan_id}/generate`
  - Delegates to audio pipeline execution.
  - Returns generation job/result with `plan_id`.

- `POST /voice-profiles`
  - Creates or refreshes character voice profiles.

- `GET /voice-profiles`
  - Query: `character_id`, `stale`, `limit`, `offset`

- `GET /voice-profiles/{profile_id}`

- `POST /assessments`
  - Request includes `plan_id`, optional `asset_id`, `render_job_id`, `audio_url`, or local asset reference.
  - Returns `AudioIntelligenceAssessment`.

- `GET /assessments`
  - Query: `scene_id`, `shot_id`, `asset_id`, `render_job_id`, `readiness_label`, `limit`, `offset`

- `GET /assessments/{assessment_id}`

- `POST /decisions`
  - Explicit creator save.
  - Can save to project memory when requested.

- `PATCH /decisions/{decision_id}`

- `POST /decisions/{decision_id}/forget`

- `GET /department-signal`
  - Returns `PerformanceAudioDepartmentSignal`.

Compatibility endpoints:

- Existing `GET /projects/{project_id}/scenes/{scene_id}/audio-brief` returns `SoundAdvisory` projected from the newest plan.
- Existing `POST /projects/{project_id}/scenes/{scene_id}/audio-brief/apply` creates a plan and delegates score generation behavior through compatibility.
- Existing `/audio/generate` and `/audio/status` endpoints continue to work, but internally should avoid duplicate route definitions.

Error design:

- Service raises structured stability errors such as `ValidationError`, `StateError`, `ProviderError`, or local domain errors.
- Routes convert to `HTTPException`.
- Use `validation_error`, `provider_error`, `state_error`, `persistence_error`, and `playback_error`.

Potential failure modes:

- API returns nested records too large for feature-length lists.
- Generate endpoint accepts stale plans without warning.
- Decision save endpoint writes memory by default.

Validation strategy:

- API tests for every route.
- Pagination tests.
- Stale plan generation warning tests.
- Explicit memory save tests.

## 19. Frontend Architecture

This section exists to keep frontend state aligned with backend truth.

New frontend modules:

- `studio-app/src/lib/performanceAudioApi.ts`
- `studio-app/src/components/PerformanceAudioPanel.tsx`
- `studio-app/src/components/AudioPlanInspectionDrawer.tsx`
- `studio-app/src/components/CharacterVoiceProfilePanel.tsx` if needed.

Integration surfaces:

- Previs Room: plan dialogue, voice, music, ambience, sound design, and silence before generation.
- Production Board: show audio readiness, blockers, voice casting gaps, generation status, and plan-to-render handoff.
- Screening Room: show assessment against generated assets, mix risks, missing dialogue evidence, and revision actions.
- Crew Intelligence Panel: show Performance Audio department reasoning, handoffs, and creator attention.

State rules:

- Backend is source of truth for audio plans, voice profiles, and assessments.
- Frontend local state may hold drafts before saving but cannot represent production readiness.
- Use React Query or existing async patterns for server state.
- Do not use `localStorage` for critical audio state. Existing demo-only `studio:audioGenerated` should not be expanded.
- API contracts must match backend Pydantic DTOs exactly.

UI conventions:

- Use icons from `lucide-react`.
- Use tabs for views: `Plan`, `Voices`, `Soundscape`, `Assessment`, `Evidence`.
- Use toggles for optional generation tracks.
- Use sliders or compact inputs for timing and mix intent only where backend supports editable values.
- Use inspection drawer for evidence, memory refs, spine refs, and reasoning.
- Avoid oversized marketing-style panels in operational rooms.

Potential failure modes:

- UI calculates readiness locally from partial fields.
- Existing `AudioGenerationPanel` diverges from new plan state.
- Users can click generate without seeing voice casting blockers.

Validation strategy:

- Component tests for empty, loading, error, low-data, ready, blocked, stale, and generated states.
- API mock tests to verify DTO fields are displayed correctly.
- Accessibility checks for controls.

## 20. UI/UX Workflows

This section exists to describe user-visible behavior.

Workflow 1: Plan scene audio in Previs

1. User selects a scene.
2. Performance Audio panel loads current plan or offers `Build Audio Plan`.
3. Panel displays dialogue delivery cues, character voice profiles, score intent, ambience, sound design, silence strategy, and mix requirements.
4. User can inspect evidence.
5. User can adjust plan fields that are creator-editable.
6. User can generate audio from the plan or proceed without generation.

Workflow 2: Resolve voice casting

1. Panel shows characters in selected scene.
2. Each character has profile status and provider binding status.
3. If missing, UI routes to existing `VoicePicker` or voice assignment flow.
4. Voice clone/upload actions must remain explicit.
5. Plan updates after casting changes.

Workflow 3: Generate audio

1. User selects track options.
2. Backend builds execution request from plan.
3. Execution service generates dialogue, score, ambience, and mix.
4. UI shows job status using canonical status normalization.
5. Generated output links back to plan ID.

Workflow 4: Assess generated audio in Screening

1. User opens Screening Room.
2. System loads latest plan and generated asset evidence.
3. Assessment checks audio stream, expected clip metadata, known dialogue tracks, score/ambient presence, and mix risk.
4. UI displays readiness label, concrete risks, and revision recommendations.
5. User can send revision emphasis back to Previs or Production Board.

Workflow 5: Save audio decision

1. User clicks save on a plan/cue/layer/profile decision.
2. UI shows an explicit confirmation/edit modal.
3. Backend saves projection and optionally writes project memory only when requested.
4. Saved decision is editable and forgettable.

Potential failure modes:

- UI presents plan suggestions as automated creative decisions.
- Generate button hides blockers.
- Assessment claims dialogue quality without transcription evidence.

Validation strategy:

- UX copy tests for prohibited language.
- Manual verification through Previs, Production Board, and Screening.

## 21. State Management

This section exists to prevent multiple sources of truth.

Backend states:

- Plan status: `draft`, `ready`, `needs_creator_review`, `superseded`, `stale`.
- Readiness: `ready`, `needs_review`, `blocked`, `not_requested`.
- Assessment readiness separate from generation status.
- Generation status remains owned by execution services.

Frontend states:

- `idle`
- `loading`
- `planning`
- `ready`
- `blocked`
- `generating`
- `assessing`
- `stale`
- `error`

Rules:

- Plan status is server-derived.
- Generation status is execution-service-derived.
- UI draft fields are temporary and unsaved until submitted.
- Stale plan warnings appear when `source_signature` mismatch is detected by backend.
- A generated asset can be complete while audio assessment is `needs_review`.

Potential failure modes:

- One "status" field is overloaded for plan, generation, and assessment.
- Local UI toggles persist across scene changes.

Validation strategy:

- Type tests and component tests for state transitions.
- API tests for stale source signatures.

## 22. Persistence Strategy

This section exists to define durable storage.

Use SQLite through `DatabaseStorage`. Do not write raw SQL in routes. Do not persist through project JSON except where existing compatibility requires reading legacy fields.

Storage design:

- Store top-level identifiers and status columns for queryability.
- Store nested DTO content as JSON text.
- Store `source_signature` for staleness.
- Store `created_at`, `updated_at`, and `generated_at`.
- Store `forgotten_at` for decision projections.
- Do not store API keys.
- Do not store raw uploaded voice files in these tables.
- Reference assets by `asset_id`, file URL, or existing asset table entries.

Migration approach:

- Idempotent `CREATE TABLE IF NOT EXISTS`.
- Idempotent indexes.
- Backfill optional. Sprint 14 does not require migrating all old audio briefs into plans, but compatibility endpoints should create plans on demand.

Potential failure modes:

- Existing project JSON sound advisories conflict with new plans.
- Large nested JSON slows list endpoints.
- Raw audio paths leak local filesystem details to frontend.

Validation strategy:

- Storage round-trip tests.
- Query/index tests with many fake scenes.
- Serialization tests with Pydantic JSON mode.

## 23. Error Handling

This section exists to keep failures actionable.

Domain errors:

- `ValidationError`: missing project, scene, required fields, unsupported status transition.
- `StateError`: stale plan execution, missing canonical source, invalid memory write attempt.
- `ProviderError`: execution service/provider failure.
- `PersistenceError`: storage write/read failure.
- `PlaybackError`: missing or invalid audio stream, final media unavailable.

Rules:

- Services raise domain errors.
- Routes convert to HTTP responses.
- Never swallow errors silently.
- Low-data assessment is not an exception; it is a valid assessment state with missing evidence.
- Provider unavailable is not a planning failure.

Logging must include:

- `project_id`
- `scene_id`
- `shot_id` when available
- `job_id` when available
- `provider` when execution is involved
- `stage`
- `duration_ms`
- `trace_id`

Potential failure modes:

- LLM parse failures produce generic 500s.
- Provider failures erase partial generation evidence.
- Audio plan generation fails when optional performance intelligence fails.

Validation strategy:

- Tests for each error class path.
- Tests for partial plans when optional dependencies are unavailable.
- Tests for route error formatting.

## 24. Logging & Observability

This section exists so production workflows are inspectable.

Required stages:

- `performance_audio_plan_start`
- `performance_audio_load_project`
- `performance_audio_load_performance_context`
- `performance_audio_load_memory_context`
- `performance_audio_load_spine_context`
- `performance_audio_voice_profile_build`
- `performance_audio_dialogue_cues_build`
- `performance_audio_soundscape_build`
- `performance_audio_plan_persist`
- `performance_audio_execution_request`
- `performance_audio_generate_delegate`
- `performance_audio_assessment_start`
- `performance_audio_evidence_probe`
- `performance_audio_assessment_persist`
- `performance_audio_crew_reasoning`
- `performance_audio_decision_save`

Observability outputs:

- Structured logs.
- Crew reasoning records.
- Department signal endpoint.
- Assessment missing evidence list.
- Provider readiness metadata.

Potential failure modes:

- Logs include private dialogue reference files or API payloads.
- Reasoning records become too verbose for overview pages.

Validation strategy:

- Logging tests with captured log fields where practical.
- Crew reasoning tests for concise creator notes and metadata boundaries.

## 25. Security Considerations

This section exists because audio systems can involve voice identity and uploaded samples.

Security rules:

- Never store API keys in audio plan/profile records.
- Never expose provider secrets through capabilities endpoints.
- Treat voice clone references as sensitive asset references.
- Do not auto-clone voices.
- Do not auto-save raw uploaded voice samples to memory.
- Validate local file paths before probing.
- Do not allow arbitrary filesystem paths from API requests unless they reference known project assets or generated outputs.
- Remote audio URLs must be validated before provider use.
- Provider errors should not leak credentials.

Consent-sensitive design:

- Voice cloning requires explicit user action and provider readiness.
- Profile records should distinguish `voice_source_type`: `stock`, `clone`, `uploaded_reference`, `manual`, `unknown`.
- UI must clearly show when a provider binding is a clone or uploaded reference.

Potential failure modes:

- SSRF via remote audio URL.
- Local path traversal in assessment request.
- Voice clone ID displayed as if it were creative identity.

Validation strategy:

- Security tests for path validation and URL rejection.
- Tests confirming no secrets in serialized DTOs.

## 26. Performance Considerations

This section exists to keep the system responsive.

Performance constraints:

- Plan creation should be fast with deterministic logic.
- Optional LLM enhancement must be bounded and timeout-protected.
- List endpoints must paginate.
- Avoid loading all scene plans for a feature-length project in one request.
- Avoid probing large media files repeatedly; cache assessment evidence by source signature.
- Use lazy dependency access for heavy services.
- Do not load TTS/music models during planning.

Potential failure modes:

- Audio pipeline imports heavy model libraries during API startup.
- Frontend loads every cue for every scene in a feature-length project.
- Assessment probes media on every page render.

Validation strategy:

- Unit tests for lazy planning with provider services stubbed.
- Load test list endpoints with hundreds of plans.
- Frontend tests for paginated rendering.

## 27. Scalability Considerations

This section exists because the platform targets feature-length filmmaking.

Scalability requirements:

- Support hundreds of scenes and thousands of dialogue cues.
- Store plans per scene/shot rather than one huge project blob.
- Use indexes for project/scene/character/status queries.
- Allow background generation and assessment later.
- Keep provider execution asynchronous where existing services support it.
- Use source signatures to avoid unnecessary recomputation.
- Support future distributed audio generation through provider-neutral execution requests.

Future scaling shape:

- Audio planning remains synchronous for small scene scopes.
- Project-level planning can become background task.
- Assessment of full cuts can run as production acceptance or packaging gate.
- Waveform/transcript/diarization providers can be added behind `AudioEvidenceService`.

Potential failure modes:

- Single project-level audio plan becomes too large.
- Provider-specific model loading blocks all requests.
- Crew reasoning records become too noisy.

Validation strategy:

- Pagination tests.
- Source signature cache tests.
- Department signal summarizes instead of listing all records.

## 28. Testing Strategy

This section exists to define end-to-end confidence.

Testing layers:

- Model contract tests.
- Storage tests.
- Service unit tests.
- Service integration tests.
- API route tests.
- Compatibility regression tests.
- Frontend API tests.
- Frontend component tests.
- Production verification tests.

Test principles:

- Do not test across architectural boundaries unnecessarily.
- Stub provider execution in planning tests.
- Use mock/local audio evidence for assessment tests.
- Include guardrail tests for creator-facing language.
- Include stale source tests.
- Include explicit memory save tests.

Potential failure modes:

- Tests only verify happy path.
- Mock provider tests miss route duplication.
- UI tests verify text but not state transitions.

Validation strategy:

- Required test checklist in PR.
- Run targeted backend and frontend tests before acceptance.

## 29. Unit Testing

This section exists to specify isolated test coverage.

Backend unit tests:

- `test_performance_audio_models.py`
  - Defaults.
  - Serialization.
  - Advisory flags.
  - Literal validation.

- `test_performance_audio_intelligence_service.py`
  - Plan from scene text only.
  - Plan with Performance Intelligence context.
  - Plan with memory refs.
  - Plan with Creative Spine refs.
  - Voice profile from casting binding.
  - Dialogue cues from structured dialogue lines.
  - Soundscape layers from scene mood and memory motif.
  - Stale signature detection.
  - Guardrail rejection for scores/percentages/generic praise.
  - No provider call during planning.

- `test_audio_evidence_service.py`
  - Audio stream present.
  - No audio stream.
  - Missing file.
  - Unsupported file reference.
  - Low-data evidence report.

- `test_audio_decision_memory.py`
  - Explicit save.
  - Update.
  - Forget.
  - No implicit memory write.

Frontend unit tests:

- `PerformanceAudioPanel.test.tsx`
- `AudioPlanInspectionDrawer.test.tsx`
- `performanceAudioApi.test.ts`

Potential failure modes:

- Unit tests rely on real provider credentials.
- Tests assert exact poetic copy, making iteration brittle.

Validation strategy:

- Use stubs and semantic assertions.
- Assert prohibited language is absent.

## 30. Integration Testing

This section exists to verify service collaboration.

Backend integration tests:

- Plan creation persists plan, profiles, cues, layers, and crew reasoning.
- Existing audio brief endpoint returns a `SoundAdvisory` projected from the new plan.
- Generate-from-plan delegates to audio pipeline service and returns plan-linked result.
- Assessment links render job, asset evidence, and plan.
- Crew Intelligence overview includes Performance Audio department signal.
- Explicit save can write project memory only when requested.

Frontend integration tests:

- Previs panel requests plan and displays cues.
- Production Board displays readiness and blockers.
- Screening displays assessment and revision recommendations.
- Voice missing state routes to existing voice picker flow.

Potential failure modes:

- Integration tests depend on order of existing duplicate route registration.
- Crew Intelligence role enum changes break existing serialized records.

Validation strategy:

- Add compatibility tests before modifying routes.
- If adding `AgentRole.SOUND_DESIGNER`, ensure storage can deserialize existing roles.

## 31. Regression Testing

This section exists to preserve existing product behavior.

Regression coverage:

- Existing `test_voice_assignment_routes.py`.
- Existing `test_fish_audio_provider.py`.
- Existing audio pipeline/generation tests.
- Existing ambient audio service tests.
- Existing scene003 audio goal audit tests.
- Existing full scene probe verifier tests.
- Existing short film stitching tests for soundtrack mixing and preserving dialogue audio.
- Existing Performance Intelligence tests.
- Existing Crew Intelligence tests.
- Frontend `AudioGenerationPanel` tests if present or newly added.
- Frontend room smoke tests for Previs, Production Board, and Screening.

Compatibility requirements:

- `/api/f51/studio/projects/{project_id}/scenes/{scene_id}/audio-brief` remains available.
- `/audio/generate` remains available.
- `/audio/status` remains available.
- Existing response fields remain present where clients expect them.

Potential failure modes:

- Route consolidation changes mock mode messages.
- Capabilities response shape changes.
- Legacy clients break because new endpoint requires plan ID.

Validation strategy:

- Snapshot old response shapes in tests.
- Add deprecation metadata only additively.

## 32. Production Verification

This section exists to prove the feature works beyond unit tests.

Verification scenarios:

1. Script-only plan
   - Create project with dialogue-heavy scene.
   - Build audio plan.
   - Confirm dialogue cues, voice profiles, score/ambience/silence plan, evidence refs, and crew reasoning.

2. Performance-informed plan
   - Run Performance Intelligence.
   - Build audio plan.
   - Confirm cues reference performance beats and voice lines.

3. Voice casting readiness
   - Assign provider voice to character.
   - Build profile.
   - Confirm provider binding appears without exposing secrets.

4. Generate from plan in mock/local mode
   - Trigger generation.
   - Confirm execution result links to plan.
   - Confirm no route calls provider directly.

5. Assessment
   - Assess generated local video/audio.
   - Confirm audio stream evidence and low-data labels.

6. Screening workflow
   - Open Screening Room.
   - Confirm assessment visible and actionable.

7. Explicit memory save
   - Save one audio decision to project memory.
   - Edit and forget it.

Verification commands:

- Backend targeted tests with `.venv/bin/python -m pytest`.
- Frontend targeted tests with existing package scripts.
- Manual browser verification for Previs, Production Board, and Screening.

Potential failure modes:

- Mock audio passes as final quality.
- Manual verification skips stale plan behavior.

Validation strategy:

- Production verification report must state provider mode.
- Assessment must distinguish `mock`, `local`, and external provider evidence.

## 33. Documentation Requirements

This section exists to ensure implementation can be maintained.

Required docs:

- Update API documentation for Performance Audio Intelligence endpoints.
- Add model field documentation to code or docs.
- Update audio pipeline docs to explain plan-based generation.
- Update frontend docs or component notes for new panels.
- Add migration notes for legacy `SoundAdvisory` and audio routes.
- Add provider abstraction notes.
- Add memory policy notes.
- Add Creative Spine integration notes.
- Add verification checklist.

Documentation must include:

- Canonical ownership boundaries.
- How to build a plan.
- How to generate from a plan.
- How to assess output.
- How to save an audio decision.
- How to add a future provider.
- How to avoid prohibited creator-facing language.

Potential failure modes:

- Documentation teaches engineers to call provider services from routes.
- Legacy endpoints are undocumented and accidentally removed later.

Validation strategy:

- Docs reviewed against implemented routes and tests.
- Include examples using provider-neutral DTOs.

## 34. Deployment Considerations

This section exists to avoid breaking demo and production environments.

Deployment requirements:

- SQLite migrations must be idempotent.
- New route inclusion in `main.py` must not shadow existing routes.
- No new required external credentials for planning.
- Provider-backed generation remains optional.
- Mock/local generation remains supported.
- Heavy audio dependencies must not be imported during startup unless already imported by existing execution service behavior.
- Existing environment variables remain valid:
  - `AUDIO_DIALOGUE_PROVIDER`
  - `DIALOGUE_TTS_PROVIDER`
  - `AUDIO_SCORE_PROVIDER`
  - `AUDIO_SCORE_AMBIENT_PROVIDER`
  - `ELEVENLABS_API_KEY`
  - `FISH_AUDIO_API_KEY`
  - `DASHSCOPE_API_KEY`
  - related provider variables.

Rollout:

1. Deploy models/storage/service behind routes.
2. Keep frontend fallback to old audio generation panel.
3. Enable Performance Audio panel.
4. Consolidate route internals.
5. Monitor logs and Crew Intelligence records.

Potential failure modes:

- Startup fails on missing optional provider libraries.
- Existing audio endpoints resolve to the wrong duplicate handler.
- Frontend deployed before backend route exists.

Validation strategy:

- Health check after migration.
- Capabilities endpoint checked in mock and configured modes.
- Smoke test old and new endpoints.

## 35. Risks & Mitigation

This section exists to make implementation risks explicit.

Risk: Duplicate audio systems persist.

- Mitigation: Make `PerformanceAudioIntelligenceService` the canonical planner and project old briefs from plans.

Risk: Voice profile becomes provider-specific.

- Mitigation: Store provider bindings as nested refs, not as profile identity.

Risk: Audio assessment overclaims quality.

- Mitigation: Use low-data labels and missing evidence. Do not claim transcription/voice similarity unless implemented.

Risk: Memory policy violation.

- Mitigation: Only explicit decision endpoint writes memory. Add tests.

Risk: Route consolidation breaks clients.

- Mitigation: Preserve response shapes and add regression tests.

Risk: Crew role enum migration causes deserialization issues.

- Mitigation: Add role carefully and test existing crew records. If risky, use department name with existing role temporarily.

Risk: Heavy provider imports slow startup.

- Mitigation: Keep planning imports light and execution lazy.

Risk: UI becomes cluttered.

- Mitigation: Use compact tabs and inspection drawer.

Risk: Feature-length performance degrades.

- Mitigation: Pagination, source signatures, indexes, and scene-scoped records.

## 36. Future Extensibility

This section exists to ensure Sprint 14 supports later growth.

Future capabilities:

- Transcription-backed dialogue presence.
- Diarization and speaker continuity checks.
- Voice similarity and character voice drift analysis.
- Loudness and intelligibility analysis.
- Sound motif graph integration using existing memory systems.
- ADR workflow and take comparison.
- Music motif composer department with the same canonical plan model.
- Sound effects library and asset search.
- Full-cut mix timeline.
- Production acceptance gate for final audio.
- Multi-provider generation comparison.
- Scene-to-scene ambience continuity.
- Export stems for dialogue, music, ambience, and SFX.
- Collaboration handoffs between editor, sound designer, composer, and director.

Extension rules:

- Add new providers behind execution services or provider adapters.
- Add new evidence sources behind `AudioEvidenceService`.
- Add new memory links through refs, not copied memory stores.
- Add new UI tabs only when backed by backend DTOs.

Potential failure modes:

- Future provider features bypass canonical plan.
- New analysis creates separate assessment model.

Validation strategy:

- Architectural review for every future audio sprint must check against Sprint 14 ownership boundaries.

## 37. Definition of Done

This section exists to define completion.

Sprint 14 is done when:

1. `performance_audio.py` models exist with complete DTOs and tests.
2. SQLite tables and storage methods exist with idempotent migrations and round-trip tests.
3. `PerformanceAudioIntelligenceService` owns audio planning, voice profiles, dialogue cues, soundscape layers, assessments, staleness, compatibility projections, and Crew Intelligence reasoning.
4. Existing audio brief and generation endpoints remain backward compatible.
5. Duplicate route behavior in `audio.py` is resolved or explicitly tested and controlled.
6. Audio planning does not call provider adapters directly.
7. Generation-from-plan delegates through existing execution services.
8. Character voice profiles integrate with existing casting/voice assignment.
9. Performance Intelligence context is consumed when available.
10. Memory and Creative Spine refs are included when available.
11. No automatic memory writes occur.
12. Explicit audio decision save/edit/forget flow exists.
13. Frontend Performance Audio panel exists and is mounted in target rooms.
14. Inspection UI exposes evidence, memory refs, spine refs, reasoning, blockers, and readiness.
15. Assessment exists for generated/uploaded assets with honest low-data handling.
16. Crew Intelligence includes Performance Audio reasoning and department signal.
17. Unit, integration, regression, frontend, and production verification tests are complete.
18. Documentation is updated.
19. Creator-facing language contains no scores, ratings, percentages, generic praise, humiliating language, or unsupported certainty.
20. Final architectural review confirms no duplicate systems, no provider leakage, no route boundary violations, no unauthorized memory writes, and no scalability blockers.

Potential failure modes:

- The sprint is declared done after UI only.
- Plans exist but are not persisted.
- Generation works but is not traceable.
- Assessment exists but cannot cite evidence.

Validation strategy:

- Completion audit must map each item above to a test, file, route, or manual verification artifact.

## Final Architectural Review

This section exists to verify the specification itself is internally consistent and implementation-ready.

Consistency review:

- The spec extends existing audio systems rather than replacing them. `DialogueVoiceService`, `AmbientAudioService`, `audio_pipeline_service`, `audio_generation_service`, `casting_service`, and provider adapters remain in place.
- The spec introduces one canonical planning service: `PerformanceAudioIntelligenceService`.
- The spec separates planning, execution, assessment, approval, and memory save.
- The spec keeps provider-specific IDs in `VoiceProviderBinding`, not in canonical character voice identity.
- The spec uses `CrewIntelligenceService` for durable reasoning instead of inventing a new reasoning ledger.
- The spec uses memory and Creative Spine through references instead of copying source-of-truth fields.
- The spec preserves old routes and response shapes while adding new canonical APIs.
- The spec acknowledges and addresses current duplicate audio routes.
- The spec respects service boundaries by keeping routes thin and provider calls service-mediated.
- The spec preserves explicit-save-only memory policy.
- The spec avoids scores, ratings, percentages, and public quality grades.

Scalability review:

- Plans are scoped by project, scene, shot, and asset.
- Lists are paginated.
- Storage has indexes for project, scene, character, status, staleness, asset, render job, and time.
- Source signatures support cache and stale detection.
- Provider execution remains lazy and optional.
- Assessment can start with low-data evidence and later support transcription, diarization, and audio analysis without changing core ownership.

Implementation readiness review:

- Required backend files, models, services, routes, storage methods, and tests are named.
- Required frontend files, panels, API clients, and workflows are named.
- API endpoints and DTOs are specified.
- Error handling, logging, security, performance, deployment, and documentation requirements are specified.
- Completion criteria are concrete and testable.

The Sprint 14 specification is ready for implementation by senior engineers or Codex/OpenCode, provided implementers first perform the repository inspection checklist and keep backward compatibility tests green throughout migration.
