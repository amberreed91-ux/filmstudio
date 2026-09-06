# AI Film Studio: system audit and first repairs

Date: 2026-09-05. This is an evidence-backed initial investigation and repair iteration, not production certification or an exhaustive review of every function. The application has 516 Python files under `studio-backend/app` (including tests) and 178 TSX files under `studio-app/src`. Many substantial working-tree changes predated this session; they were preserved. `changes-this-session.patch` separates this session's changes from that work.

## Outcome

Implemented and tested:

1. Missing render-provider configuration now fails with recoverable job state and a structured HTTP 502 response instead of switching to simulated output. Unknown adapter identifiers also fail instead of selecting simulation. Explicit simulation remains available.
2. Polling snapshots status before invoking a mutating adapter. Completion now triggers continuity review, quality review, reference locking, and update notification exactly once in the tested sequential polling path.
3. Pytest config sets fresh SQLite and project JSON paths before application singleton imports. The grounding fixture can no longer inherit those developer store paths and delete a real project through them.
4. Provider initialization logs configuration presence without exposing credential prefixes or suffixes.
5. Generated-output registration rejects parent traversal and symlinks escaping the outputs directory. A related status test now creates its own asset instead of requiring a developer's sample video.

No schema migration, provider replacement, or production data mutation was performed. No paid generation was submitted. The existing backend process was not restarted.

## Baseline and verification

Tests ran in disposable copies of the actual working-tree backend, excluding credentials, project data, generated media, and local model weights. The existing virtualenv interpreter executed the copied code. This avoids legacy modules writing into live source-relative data paths. The first copy initially omitted `app/models` and `app/data` accidentally; that collection error was corrected before the reported baseline run.

| Verification | Evidence |
|---|---|
| Frontend tests | 76 files, 680 tests passed; `frontend-tests.log` |
| Frontend production build | TypeScript and Vite passed; Three.js chunk size warning remains; `frontend-build.log` |
| Initial backend broad run | 3,358 passed, 10 skipped, one failure and one fixture error. A concurrent focused process shared the copied JSON fixture path; rerunning with isolation removed that error. This run is not a clean product failure baseline. |
| Intermediate backend run | 3,365 passed, 10 skipped, one failure: missing `/outputs/mock-video/sample.mp4` in `test_video_asset_status_update`. The fixture dependency was then repaired. |
| Provider regression before | Five failed, one passed; `regression-before.log` |
| Render/canon/department regression after | 54 passed; `regression-after.log` |
| New provider, credential, screenplay, and store-isolation checks | Nine passed; `final-focused.log` |
| Output-boundary regression before | Two failed, one passed; `boundary-before.log` |
| Output-boundary/service/API regression after | 16 passed; `boundary-after.log` |
| Final broad run | **3,373 passed, 10 skipped, zero failures/errors**, 268.96 seconds; `backend-final.log`. |
| Runtime | Fresh isolated Uvicorn at `127.0.0.1:18010`: `/ready` returned 200 with schema v59. Existing backend at port 8010 timed out on the bounded readiness probe. |
| Browser | Existing Vite UI at port 5001 renders. Isolated-backend browser requests exercise overview/project/provider/queue APIs; details in `browser.log`. |

Repeat backend checks with `.venv/bin/python -m pytest` from `studio-backend`; frontend with `npm test` and `npm run build` from `studio-app`. For broad auditing, continue using a disposable backend copy because additional services have source-relative file stores beyond the two now isolated in conftest.

## Actual architecture and run paths

| Area | Implementation and interaction | Classification / limits |
|---|---|---|
| Frontend entry and routing | `src/main.tsx` → `App.tsx` → `routes.tsx`; lazy room pages, React Router, React Query, Studio/RenderActivity/AudioUX contexts; Zustand render status store | VERIFIED WORKING: tests/build and overview browser render. Full room-by-room behavior unverified. |
| Backend entry | `studio-backend/main.py`, FastAPI route registration, lifespan storage wiring, render hydration, backup/queue/poll tasks | VERIFIED WORKING: isolated startup and readiness. Run `.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8010`. |
| Development wiring | Vite port 5001 proxies API/media to 8010; `backendSupervisor.ts` can launch backend | PARTIALLY WORKING: frontend reachable, existing backend unresponsive to readiness probe. |
| Persistence | `app/data/storage.py`: SQLite WAL, foreign keys, pooled connections, migration list. `project_store.py`: JSON project snapshots, locking, atomic replacement | VERIFIED WORKING for new trace writes. Live database opened read-only: 141 tables, 59 migrations, 2 projects, 43 render jobs, 464 knowledge atoms, no production queue items. JSON and SQLite remain distinct stores. |
| API/domain boundaries | Render, projects, previs, knowledge, editorial, audio, queue routes call services; many route modules import service singletons directly | PARTIALLY WORKING: not consistently dependency-injected. `main.py` health routes query SQLite directly; one-button service raises HTTP exceptions. No boundary rewrite undertaken. |
| Auth/project isolation | `app/auth.py` uses process-global user/session dictionaries; `_load_users()` is a placeholder. Project/render route declarations lack user ownership dependencies | BROKEN for multi-user production. Isolated project listing returned 200 without any session. Password hashing exists, but this does not establish resource authorization. |
| Screenplay and scenes | `ScriptParser.build_script_breakdown_bundle`, project `script_text` and `execution_summary`, script-intelligence analysis routes | VERIFIED WORKING for the synthetic screenplay and existing tests; arbitrary screenplay formats not comprehensively evaluated. |
| Shots and storyboards | `storyboard_blueprint_service`, previs, scene production pipeline, `shot_staging_service` map scene beats to shot IDs/visual plans | PARTIALLY WORKING: extensive code/tests; shot choice includes deterministic position/tag defaults as well as story-informed staging. |
| Prompt construction | `RenderService.create_job` combines shot slots, identity, knowledge, department context, environment context, negative prompt, references, and provider metadata | VERIFIED WORKING for selected facts in trace/canon tests; BROKEN under saturated slot budgets (below). |
| Images/references | Previs service; image-provider abstraction/local/mock implementations; character visual references, face/body/wardrobe roles, representative-frame extraction | IMPLEMENTED BUT UNVERIFIED visually in this session. Reference locking hook regression is repaired. |
| Video | `app/adapters/__init__.py` registry plus RenderService; create → persisted job → submit → provider task → poll/download → output | VERIFIED WORKING with controlled provider response through real adapter request construction and SQLite. Hosted media quality unverified. |
| Character identity | `character_profile.py`, identity memory and visual reference services separate fixed traits from appearance versions; wardrobe, injuries, face/body/temporary-state references | PARTIALLY WORKING: richer than descriptions alone. Test proves selected identity text reaches a request, not facial consistency across scenes. |
| Environment/continuity | Scene continuity, continuity intelligence, reference memory, universe graph, semantic/cinematic memory; environment slots and context | PARTIALLY WORKING: tests validate selected retrieval/injection paths, not full chronology/object-placement/screen-direction preservation. |
| Director/story intelligence | Scene analyses, shot rationale, director intent, departmental context, staging purpose, emotional analysis, saved knowledge/Creative Spine | PARTIALLY WORKING: grounded context exists; no evidence that all shot selection is driven by dramatic turns rather than heuristics. |
| Audio/postproduction | `audio_pipeline_service`: dialogue providers, music/ambience, FFmpeg mixing/muxing; scene and film stitching/assembly services | IMPLEMENTED BUT UNVERIFIED with real voice/music generation. HappyHorse path explicitly strips generated audio for separate sound work. |
| Queue/retries | Persisted queue items/dependencies/leases/attempts/events; retry budgets, failure categories, provider-call timeouts, restart recovery | PARTIALLY WORKING: broad tests exercise these; live queue had no rows, so sustained worker recovery under load is unverified. |
| Assets/export | Video asset registration, output paths/static mounts, FFmpeg scene/film assembly, export packaging | PARTIALLY WORKING: registration/API tests pass after boundary fix. No finished film export verified this session. |
| Logging/deployment | Request IDs, structured logs, rate limits, circuit breakers, health/readiness, Docker Compose/nginx | PARTIALLY WORKING: container deployment/TLS/backup restore unverified. Compose defaults demo mode on; dev supervisor contains a hardcoded admin token. |
| Secondary/legacy paths | `services/providers` has separate mock/local/real-stub capability abstraction; `studio-dashscope-pivot`, old routers/scripts, multiple prompt builders | PLACEHOLDER OR MOCK applies to explicit stubs/simulation. No implementation was declared DEAD CODE or removed merely because an alternative exists. |

## Representative end-to-end trace

`test_screenplay_provider_trace.py::test_screenplay_facts_reach_provider_and_completed_job_is_persisted` provides a repeatable trace:

1. Input screenplay: workshop at night; MAYA says to keep the door closed and holds a brass key.
2. Actual ScriptParser produces scenes and execution summary.
3. Project snapshot is saved to JSON; project and Maya's visual description are saved in temporary SQLite.
4. Actual `RenderService.create_job` resolves the scene/shot and builds the prompt with identity context.
5. Actual HappyHorse adapter builds its submit request; the test captures that payload at `_happyhorse_request`.
6. Assertions prove Maya, the key, the saved Black-woman descriptor, and a seed reach the provider request.
7. Controlled responses return a provider task and successful video URL; download/audio processing is explicitly stubbed.
8. SQLite readback proves the completed job, provider task ID, prompt, and output link survive persistence.

This trace contains no reference image and does not assemble a film. It verifies the software handoff through generated-asset state, not image adherence, downloaded media, final project assembly, or artistic coherence. Existing focused canon tests additionally verify Creative Spine/project Bible context and prevent a character name such as MOM being inferred from “moments.”

## Prompt forensics and filmmaking risks

The common video choke point is `RenderService.create_job`, but the system has several upstream authoring paths: slotted shot prompts, previs enhancement, script-intelligence scene prompts, animation prompts, and one-button/scene orchestration. Provider adapters can further transform the final text/references. Thus the slotted builder is shared but not the only source of prompt content.

**P1 — verified loss of final-slot instructions, unresolved.** `shot_prompt_builder.reassemble_prompt_from_slots()` caps output at 480 characters (512 minus 32 reserve), after joining character, action, environment, camera, lighting. Slot allocations total 550 characters before separators and suffix. The synthetic saturation probe supplies 528 characters including an explicit lighting sentinel; the actual HappyHorse payload contains 480 characters and no lighting sentinel. `prompt-baseline.json` records the exact result. Raw slicing also cuts words. This is a concrete context-to-provider loss, not a speculative prompt-quality criticism.

The existing source explicitly documents earlier failed attempts to shrink slots or change truncation in isolation: injected corrections can disappear. A safe next implementation should introduce an explicit provider budget at the assembly boundary and regression fixtures for every injected fact, then revise truncation. No new external provider limit is asserted here; current supported limits require official contract verification before changing them.

**Character coherence:** structured fixed identity, appearance versions, references, and seeds exist. HappyHorse T2V degrades references into text; R2V/OpenRouter paths construct reference arrays (up to nine in code). Merely storing a face reference or reusing a seed does not prove recognizability. The missed completion hook could prevent newly completed footage from establishing reference locks; repaired here. Cross-scene face/wardrobe/injury/light/angle evaluation remains unverified.

**Cinematography:** shot-position defaults prescribe wide → medium → medium close-up → detail; alternate takes include a 90-degree camera relocation. Staging also receives purpose, beat, characters and location. These coexist; inspect the resolved shot plan before asserting motivated coverage. Repetitiveness and screen-direction violations were not measured on a generated film.

**Story state:** scene/shot structures are clear, but preservation across a distinct sequence layer and chronological changes in props/injuries/relationships was not established. Do not introduce another memory store before proving existing state survives request construction.

## Provider inventory (repository contract, not current vendor certification)

| Path | Inputs/behavior in code | Verification limits |
|---|---|---|
| Simulated | Explicit sample MP4 progression; no real generation | PLACEHOLDER OR MOCK; implicit fallback removed. |
| Runway | Text/image paths, key-based configuration, task polling, reference context | Existing request/timeout tests; no hosted call this session. |
| HappyHorse | DashScope text-to-video, prompt/negative prompt, duration/resolution/ratio/seed, synchronous submit-and-poll, audio stripping | Real request builder exercised with transport/media doubles. |
| HappyHorse R2V | Extends HappyHorse with reference media | Existing adapter tests; appearance continuity unverified. |
| Wan | Separate model/request adaptation on DashScope adapter foundation | Existing adapter tests; no new live call. |
| OpenRouter video | Configurable model default `alibaba/happyhorse-1.1`, `/videos`, polling/content retrieval, image references; negative channel omitted and recorded | Source implementation and older in-repo probe comments only; no current external availability or cost claim. |
| Higgsfield / generic | Configured endpoints and adapter classes | IMPLEMENTED BUT UNVERIFIED live. |
| Qwen / OpenRouter LLM | Shared LLM client/config and fallback models for analysis/staging | Configuration/implementation inspected; no current model availability certification. |
| Vision | Qwen/Gemini/OpenRouter paths for visual analysis/adherence | IMPLEMENTED BUT UNVERIFIED on newly generated footage. |
| Audio | ElevenLabs, Fish Audio, CosyVoice/Qwen TTS, local Piper/ACE-Step/MusicGen paths | Model settings and orchestration exist; local weights/voices and paid services excluded from isolated test runtime. |

BLOCKED BY ENVIRONMENT: no credentials, local model weights, or real reference/media library were loaded into the isolated verification runtime. Existing live credentials were neither printed nor used. Cross-shot visual identity, real audio synchronization, provider billing/rate-limit behavior, and final-film quality remain unknown.

## Prioritized remaining work

- **P0 — authorization and project ownership.** Anonymous isolated GET returned full project details. Auth dictionaries are process-local; resource ownership enforcement is absent on inspected project/render APIs. Add and test a coherent session/ownership boundary before shared deployment, preserving an explicitly configured local mode rather than silently breaking the desktop workflow.
- **P1 — prompt fact loss.** Reproduced above. Preserve canonical facts and user corrections through final provider-specific assembly, with saturated-budget fixtures.
- **P1 — unresponsive existing backend.** Port 8010 process existed but bounded readiness timed out; fresh isolated instance succeeded. Root cause not established. Inspect running task/thread stacks and logs without resubmitting jobs or resetting project state.
- **P1 — persistence failure during paid submission.** `_persist_job` can return false after recording metadata, and callers often continue. Code risk, not fault-injection verified in this session. Verify crash/retry behavior before claiming no orphaned paid jobs.
- **P1 — broader file/URL trust boundaries.** Generated-output escape fixed; local-file registration intentionally accepts arbitrary absolute paths, and external URLs are accepted syntactically. Downstream SSRF/file-read exposure needs separate service-boundary tracing. No private files or internal services were exploited.
- **P2 — deployment defaults and supervisor.** Dev Vite binds broadly/allows hosts; restart token is hardcoded, and Compose defaults demo mode on. These are unsuitable assumptions for shared hosting. Container/TLS deployment not verified.
- **P2 — misleading seed data.** Fresh DB auto-seeds Neon Dreams with illustrative production/clearance/render data. Runtime proves that exists; it is demo content, not real production evidence.
- **P2 — auth logout.** Route clears the cookie but does not call existing session revocation. Code finding; session replay not exercised.
- **P2 — duplication/health truth.** Separate JSON/SQLite project representations and provider capability registries require consistency tests. Health status is not proof of configured provider readiness or film quality.

## Coverage limits

Test counts are execution evidence, not statement/branch coverage percentages. No coverage report or full dependency CVE scan was generated. No visual identity scoring, full screenplay corpus evaluation, multi-user penetration test, load test, production backup restore, or complete sound-and-picture export was completed. Browser evidence covers overview and rendered Crew Ops / Production Pipeline against an isolated backend, with successful read-only API responses and no page errors. No broad aesthetic redesign was made.


## Final validation record

- Final source snapshot: 3,373 backend tests passed, 10 skipped. No backend failures or errors remain in this isolated run.
- Frontend: 680 tests passed; production build passed.
- Browser: overview → View Queue → Crew Ops rendered successfully; all recorded API responses were HTTP 200; no page errors. Saved screenshot and script accompany the log. This does not verify every action in Crew Ops.
- `git diff --check` passed for the modified tracked code files.
- The isolated server was stopped after verification. Existing development servers and project data were preserved.
- The implementation is in the working tree; the already-running original backend still needs a normal restart to load these Python changes. It was not restarted during this audit.
