# Storyboard simplification and co-director presence

September 5, 2026. Activated in the local app at localhost:5001; backend restarted with the queue idle and confirmed healthy.

## Storyboard workflow

The Board now starts with the scene wall. Scene options remain accessible without hover; Production and Creative advice have their own views. Department panels load when opened. Images have honest loading/failure states, missing scene data is separated from an empty film, and read failures offer retry. Removed fabricated runtime/progress and duplicate queue presentation. The Board links to the existing Previs editing and approval workflow instead of creating a competing editor.

Previs storyboard preparation now presents four focused stages: Create frame → Build blueprint (shot plan) → Check continuity → Approve scene. The frame stays visible, detailed image settings and continuity comparisons remain accessible, and the existing callbacks, draft state, current-version checks, and explicit approval behavior are preserved. Scene and shot changes select the appropriate preparation stage. Page character look approvals and all render controls remain available.

Fixed the Board cancel control: it now calls the cancellation endpoint exactly once rather than retrying a render and claiming cancellation. It refreshes authoritative job state and guards late responses after a project switch. Corrected video URLs being treated as image thumbnails. Seed locks are labelled as image seed preferences, separate from storyboard and character look approval.

## Co-director

A single co-director launcher is visible in the shared shell on desktop and mobile; Cmd+D/Ctrl+D also opens it. The drawer fits the mobile viewport. Availability was verified in Study, The Page (including character looks), The Board, Previs, Theatre, and Universe.

The co-director reads the selected film/scene, reference library, and relevant explicitly saved project memory. Advice remains advisory; it does not silently approve or apply changes. The shared crew indicator now uses backend department states rather than rotating fictional work messages. Idle, working, waiting, and unavailable states are distinguished.

Moved conversation requests and context reads into a hook; replies cannot appear under another film, scene, or specialist after navigation. Explicit scene IDs survive pending scene-list loads. The backend now reports an unavailable requested scene instead of silently substituting the opening. Shared API cancellation now preserves request deadlines even when a caller provides its own abort signal.

The co-director is an available collaborator, not a claim that every frame is continuously being watched or that all creative decisions are automatic. Chat requests do not automatically save creative memory.

## Verification

- Full frontend suite: 702 tests passed across 80 files. Final production build passed after loading/error copy refinements.
- Backend: 23 co-director scope, grounding, and API tests passed in an isolated copy of the backend using temporary storage and mocked LLM calls.
- Board/Previs browser fixtures: nine scenarios passed, including frame/blueprint/continuity/approval, preserved model selection, empty/error states, and cancellation routing.
- Responsive checks: 390, 900, and 1600px; no horizontal page overflow.
- Co-director browser checks: six pipeline/support rooms on mobile, correct project+scene payloads, late reply ignored after specialist switch, clean second-film context. Nine explicit chat writes were intercepted; no runtime errors.
- Touched UI lint: no errors; existing Previs effect dependency warning remains. Drawer retains its input-reset effect warning in the broader root lint check.
- No real render generation, cancellation, approvals, uploads, or memory writes were performed during verification. All browser writes intercepted.

Independent visual evaluation: PASS on the first round, with fresh desktop/tablet/mobile inspection. No additional model provider was callable; evaluation uses an independent agent on the available provider.

## Files

Frontend pages/components: ProductionBoard.tsx, PrevisRoom.tsx, StudioShell.tsx, AICrewPresence.tsx, CoDirectorDrawer.tsx. Data hooks: useCrewPresence.ts, useCoDirectorConversation.ts. Helpers/tests: crewPresence.ts, coDirectorDrawerContext.ts, studioApi.ts deadline handling and targeted tests. Backend: co_director_chat_service.py and test_co_director_scene_scope.py.

Screenshots and verification JSON/logs are alongside this report. Populated storyboard screenshots use intercepted fixture states with existing film images; live film data was not changed.
