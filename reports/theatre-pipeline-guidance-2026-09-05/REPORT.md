# Theatre and production handoffs — 5 September 2026

Theatre and the surrounding production pages now present an ordered workflow. This pass updates the existing React application and repairs editor persistence, navigation, playback/approval targeting, and misleading action labels. Earlier backend production/adherence repairs are preserved; this pass introduces no backend route or service changes.

## The production path

| Stage | Room | Responsibility |
|---|---|---|
| 1 Prepare | Study | Project Bibles, creative references, explicitly saved guidance |
| 2 Write | The Page | Screenplay scenes and saved production character profiles/voices |
| 3 Storyboard and render | Previs | Plan, approve storyboard, direct/render takes, review and assemble scene |
| 4 Review and deliver | Theatre | Watch, review/revise, approve the displayed output, assemble/download |

A shared guide shows the current production stage, the next room, and an expandable complete path. Universe is the supporting story atlas; Production Board monitors scene/jobs; Archive is the film library. Ordinary room links preserve project, scene, and shot context. Explicit film links now take priority over the previously active film.

## What changed

- **Theatre:** Four freely accessible stages: Watch, Review, Approve, Deliver. One stable player with scene/shot-or-scene-edit/take selection. Specialist tools and canonical handoff remain available in disclosures. Fabricated weak-scene markers, preset pacing/tension claims, and advisory percentage charts were removed. Local audience simulation is explicit instead of running when navigating. Full film ends once; approval targets the registry entry for the displayed file; MP4 downloads validate HTTP success and use the correct filename. JSON manifests and local screening links are named accurately. Note/audio failures no longer show success. Expanded casting controls fit the actual sidebar.
- **Study:** Bibles, References, Saved guidance. New Bible content starts empty and is scoped to the selected film. Reference reorganization is explicit maintenance instead of a write on entry. The duplicate inert file-ingest button was removed. Uploaded files are categorized automatically by the existing backend; only title-based study exposes its working focus selector.
- **The Page:** Script and Character profiles stages; explicit Save script plus visible loading/saving/failure status. Scene and legacy scene_id links open the correct scene. Saves are serialized per film/scene so older requests cannot overwrite newer edits. Failed script drafts remain recoverable in the current tab. Room handoffs await saving; unsaved character profiles require explicit save and retain their drafts. Empty profile libraries can create the characters found in the script. Save failures stay visible and newer form edits survive an older save response.
- **Imports/exports:** The Page now truthfully accepts plain-text TXT/Fountain screenplays instead of sending binary PDFs/FDX as plain text. Text-draft download and clipboard export work; unsupported PDF/FDX export choices are removed. Markdown Bible uploads remain separate from screenplay import and analyzed reference upload.
- **Previs:** Accept Duration now changes duration alone. It preserves the chosen provider, resolution, seed and prompt instead of silently changing model/frame-rate/resolution.
- **Supporting rooms:** Crew tools stay in normal flow. Board, Archive, and Workspace narrow layouts fit the viewport. Archive names deletion and JSON export honestly, no longer claims publication from fetching an export manifest, and removes invented runtime. Workspace's local planning checklist/notes no longer masquerade as backend production approvals.

## Verification

- Production build passed (TypeScript and Vite).
- **690 frontend tests passed across 77 files**, including three meaningful tests for save ordering, failed-draft recovery, and project isolation.
- Targeted ESLint checks for new navigation/draft helpers and Theatre/Casting passed. Existing hook-dependency warnings in legacy room code remain; no new lint errors were introduced.
- Browser checks covered all Theatre stages and expanded specialist/acceptance/canonical/packaging controls at 390, 900, 1440 and 1600px. No tested controls escaped the viewport.
- The full Study → Write → Previs → Theatre path retained project_5907c60cddbc, scene_001 and shot 2. Study/Write stages and Board/Universe/Archive layouts passed desktop/tablet/mobile checks with zero runtime errors and zero navigation writes.
- Cross-film deep links were checked on Study, Write, Board, Universe and Theatre with an older film initially active. The explicit target won and guide links retained it.
- Intercepted fixtures verified correct-scene saving on handoff, failed-save prevention/recovery/retry, explicit profile-save guarding, failed character-save retention, exact displayed-final approval, once-only film ending, honest API errors, and duration-only application.
- Independent design evaluation passed: Theatre after one revision round; broader pipeline on its first evaluation.

All browser writes were intercepted before reaching the backend. No real script/profile edits, approvals, deletions, uploads, provider generations, or paid renders were submitted. Existing saved footage was used for playback checks. This is UI/contract verification, not a newly rendered film or a paid end-to-end production run.

## Remaining distinctions

- Universe graph entities and production character profiles are separate records; appearance/voice used for production belong in The Page. The guide states this explicitly.
- Screening-output approval and Canonical Production Thread gates remain distinct backend operations. Moving them into Approve does not pretend that one approves the other.
- Selecting a take in the preview does not select the final edit. Existing scene assembly uses the latest completed take per shot; the player explains this.
- Studio Brain guidance remains advisory. Duration suggestions still use the existing recommendation service; this pass does not claim it is aware of every selected provider's constraints or automatically applies every note.
- Unsaved recovery buffers are temporary in-tab form state, not persistent project memory. Save before closing the tab. Creative memories remain explicit-save.
- No interface can guarantee pixel-exact generative renders; the existing storyboard/prompt/reference approval and render-conditioning pipeline remains responsible for adherence.

## Preview

[Open the updated Theatre](http://localhost:5001/studio/screening-room?project_id=project_5907c60cddbc&scene=scene_001&shot=2)

![Desktop Theatre](/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/reports/theatre-pipeline-guidance-2026-09-05/theatre-desktop-final.png)

![Mobile Theatre](/Users/amberreed/Enhanced_adaptive_strategy_python/studio-project/reports/theatre-pipeline-guidance-2026-09-05/theatre-mobile-final.png)

## Source files

Frontend changes are in `studio-app/src/pages/ScreeningRoom.tsx`, `StudyRoom.tsx`, `WritersRoom.tsx`, `PrevisRoom.tsx`, `ProductionBoard.tsx`, `UniverseGraphPage.tsx`, `ArchiveRoom.tsx`, `ProjectWorkspace.tsx`; `components/StudioShell.tsx`, `ProductionJourneyGuide.tsx`, `CastingIntelligencePanel.tsx`, `KnowledgeLibraryPanel.tsx` and its label test; `hooks/useProjectRouteContext.ts`; and `lib/sceneDrafts.ts` with its unit tests. No changes were committed or deployed externally.
