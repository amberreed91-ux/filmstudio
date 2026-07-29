# Editorial Intelligence

Editorial Intelligence is the Studio's advisory AI editor. It reads existing project evidence and produces explainable guidance about pacing, rhythm, transitions, and emotional flow.

## Canonical Ownership

Editorial Intelligence owns editorial reasoning only. It does not render media, submit provider jobs, or silently change creator-approved cuts.

The canonical implementation entry points are:

- `app/models/editorial_intelligence.py`
- `app/services/editorial_timeline_context_service.py`
- `app/services/editorial_intelligence_service.py`
- `app/routes/editorial_intelligence.py`
- `app/data/storage.py` tables `editorial_analysis_records` and `editorial_decision_applications`

The canonical route family is:

- `POST /api/f51/studio/projects/{project_id}/editorial-intelligence/analyze`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence/latest`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence/{analysis_id}`
- `POST /api/f51/studio/projects/{project_id}/editorial-intelligence/{analysis_id}/apply`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence/applications`

## Evidence Sources

The context service reads existing Studio systems:

- Project `film_cut`
- Completed render jobs
- Scene compositions
- Final short film packages
- Registered project video assets
- Extracted project keyframes
- Detected shot boundaries for known project assets
- Continuity issues
- Style drift issues
- Cinematic memory records
- Frame analyses when available
- Studio decision gate status

Every analysis has a `context_hash` derived from the source cut, source package, clip IDs, and evidence counts, including keyframe and shot-boundary counts. Apply requests can pass this hash to reject stale analysis.

## Advisory Behavior

All analysis records, transition advisories, and edit decisions are advisory by default. Applying decisions requires `creator_confirmation: true`.

Supported apply modes:

- `metadata_only`: records selected decisions as audit metadata.
- `next_stitch`: prepares approved transition advisories and executable timing adjustments for the next stitch.
- `update_cut`: applies explicit `reorder_scene` decisions only when the decision metadata includes a valid `proposed_scene_order` containing the same scenes as the current canonical `film_cut`. Invalid reorder proposals are skipped and recorded in the application result.

Unsupported physical media edits remain advisory metadata until an execution service implements them honestly.

Generated editorial decision types include:

- Executable for `next_stitch`: `replace_transition`, `hold`, `compress_escalation`, and `trim`.
- Applicable through validated `update_cut`: `reorder_scene` when it carries a valid `proposed_scene_order`.
- Advisory-only story decisions: `extend_reaction`, `protect_silence`, `delay_reveal`, and `restore_motif_callback`.

## Stitching Integration

`FFmpegStitchingService` reads the latest `next_stitch` editorial application and overlays supported transition advisories onto the existing scene transition mechanism.

Supported editorial transition mapping:

- `cut`
- `cross_dissolve`
- `dissolve`
- `fade_to_black`
- `hold_then_cut`, mapped conservatively to `cut` for current FFmpeg execution

Supported editorial timing adjustments:

- `hold` decisions become `tail_hold` adjustments. The stitcher extends the target scene by cloning the final frame and padding the audio bed.
- `compress_escalation` decisions become `compress_duration` adjustments. The stitcher shortens the target scene duration before segment construction while preserving a minimum viable duration.
- `trim` decisions become `tail_trim` adjustments. The stitcher removes a bounded amount from the target scene tail before segment construction while preserving a minimum viable duration.

The stitching service remains the execution owner.

## Frontend Integration

`studio-app/src/components/EditorialIntelligencePanel.tsx` is mounted in Screening Room near stitch/final package controls. The panel can:

- Load the latest editorial analysis.
- Trigger a fresh cut read.
- Display overall read, pacing, emotional flow, transition advisories, decisions, and evidence counts.
- Select supported transition and timing decisions.
- Apply selected executable decisions to the next stitch.

Frontend components must not compute editorial recommendations. They display backend DTOs and collect explicit user intent.

## Legacy Compatibility

`CinematicTimelineIntelligenceService.analyze_project_timeline()` now attempts to derive its legacy response shape from canonical editorial analysis first. This preserves older callers of `/api/f51/studio/projects/{project_id}/timeline-intelligence` while preventing timeline guidance from drifting into a separate reasoning system.

`EditingIntelligenceService` remains a standalone helper for non-project payloads, but its creative language must follow the same no-score and no-percentage guidance rules as canonical Editorial Intelligence.

## Guardrails

Editorial Intelligence must not emit scores, ratings, or percentages in creative guidance. It must preserve uncertainty for low-data projects and avoid blocking creator workflow.

The service guardrail scan rejects common score/rating patterns before persisting analysis.

## Verification

Focused verification commands:

```bash
.venv/bin/python -m pytest app/services/test_editorial_intelligence_service.py app/services/test_editorial_intelligence_routes.py app/services/test_editorial_legacy_compatibility.py app/services/test_editorial_revision_intelligence_service.py app/services/test_editorial_ffmpeg_stitch_plan.py -q
npx vitest run src/components/EditorialIntelligencePanel.test.tsx src/components/ScreeningEditorialComparisonPanel.test.tsx
npm run build
```

`test_editorial_ffmpeg_stitch_plan.py` includes media-level FFmpeg checks for editorial `tail_hold` and bounded trim segment timing. It also verifies that an approved canonical Editorial Intelligence `next_stitch` application is consumed by the real stitch core, producing an output file and recording `editorial_transition_source`, `editorial_timing_source`, and `editorial_timing_adjustments` on the stitch job. The media tests generate short local clips and skip only when FFmpeg/ffprobe are unavailable.

Manual verification:

1. Open Screening Room for a project.
2. Use "Read Cut" in the Editorial Intelligence panel.
3. Confirm the panel displays advisory reasoning.
4. Select a transition decision if available.
5. Select a supported timing decision if available.
6. Apply it to the next stitch.
7. Trigger stitch and confirm the stitch job records `editorial_transition_source` or `editorial_timing_source` when approved editorial metadata is available.
