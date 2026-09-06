> Activation follow-up: the Canonical panel provider wiring and legacy compatibility repairs are now active. See [the activation report](../canonical-production-activation-2026-09-05/REPORT.md). The activation caveats below describe the earlier audit state.

# Script → storyboard → Previs → render: adherence review

The pipeline needed repairs. Several visible controls were not reaching generation, and a saved storyboard reference was not necessarily being used as a starting frame. Better prompt wording alone would not correct those failures.

This review continues the earlier audit and prompt-budget work. Existing edits and the original six-shot visual benchmark remain intact. No new paid generation was submitted, and the running production backend and real project databases were not restarted or migrated.

## What was repaired

| Handoff | Before | Current behavior |
|---|---|---|
| Previs controls → request | The visible prompt was checked but not sent. Duration, resolution, seed, and manual shot directions were omitted. | A validated request body carries those choices. The approved contract supplies defaults; explicit edits apply to the requested take. |
| Request → Previs job | The backend rebuilt the prompt and requested three seconds. | It uses the supplied prompt and settings, preserves them in the Previs record, and carries explicit settings into retries. |
| Approved Previs → production package → render | Packaging reverted to the storyboard's original prompt and omitted the approved take's effective settings. Production rendering could use the approved MP4 URL as an image reference. | New packages freeze the approved take's prompt, timing, resolved seed, frame and references. Production forwards those parameters; the approved video stays a traceable artifact rather than an image input. |
| Storyboard → render | Duration/aspect fields were separate from provider parameters. The generated storyboard image could be absent from direct and scene render inputs. | A shared translation supplies contract timing, aspect ratio, seed, references, and an explicit storyboard first-frame field to all three paths. |
| Storyboard approval → scene production | Scene production could use a draft or silently fall back to script text after a storyboard lookup failed. Previs could use a stale approved version. | Existing blueprints must use the current approved version. Omitting a storyboard shot ID cannot bypass that version check. |
| Source text → prompt budget | Storyboard contracts and frontend prompt drafts still cut text at approximately 512 characters. Frontend action drafts took only two lines. | Those early cuts are removed. Previs and storyboard construction preserve source facts for the existing final provider budget. Oversized required context stops for review. |
| Creator prompt → render assembly | Prompts shorter than 50 characters could be treated as placeholders. Structured planning could replace the chosen action. | Explicit take prompts and approved storyboard prompts are protected from those replacement paths. Existing contextual enrichment still applies and must be inspected for contradictory source facts. |
| Storyboard → OpenRouter | Only character references from the consistency payload were sent; ordinary job references were ignored. | The storyboard is sent in `frame_images` as `first_frame`. Other references remain separate in `input_references`. Missing local frames fail instead of disappearing. |
| Storyboard → Runway | A character sheet could replace the shot image. Local storyboard paths degraded to text-only generation. | An explicit storyboard frame takes priority, supported local images become image data URLs, and Gen-4.5 uses its current output dimensions for the requested shape. |
| Selected provider → budget | `openrouter-video`, used by the dropdown, missed the OpenRouter/HappyHorse model budget policy. | Both OpenRouter names resolve the same model and prompt budget. |
| Seed → provider | A stored shot seed overwrote the seed entered for the take, including zero. | Explicit seeds survive submission. Empty means automatic/saved seed; the randomize button supplies a new explicit value. The storyboard-image seed lock is labeled separately. |
| Requested output → provider | Some adapters silently rounded duration or substituted resolution/shape. | Explicit settings are checked against normalization before submission. Unsupported requests fail instead of silently becoming different settings. Remote models still enforce their own capabilities. |
| Review stop → UI | `needs_review` became pending/processing and could leave polling stuck. | Previs persists the review stop and the UI ends its busy state. The browser's submission timeout also allows for existing adapters that await video completion. |

Take numbers are now included in job parameters so distinct takes are distinguishable in request identity. Duplicate-active responses report the existing take. This is still a one-take-per-click workflow; selecting a take number is not a request to generate that many alternate clips.

The FPS selector was removed from this render panel because these adapters do not use it. The panel now explains that the selected video model determines frame rate.

### Persistence issue discovered during runtime verification

An authenticated project update returned success, but the owner's next read returned 403. `INSERT OR REPLACE` deleted the project row before recreating it, cascading into the ownership table introduced by the earlier security repair. Project saves now update an existing row in place and insert only new rows.

The regression reproduced loss of ownership. An additional approved-storyboard preservation test passed before and after; this review did **not** demonstrate deletion of approved storyboards by that save. This newly exposed security-change regression is not evidence for the user's historical visual mismatches.

## What the saved projects show

Read-only evidence is in `saved-project-evidence.json`:

- **THE LAST TIDE:** 11 saved scenes. No canonical storyboard blueprints were found for this project in the inspected SQLite database. The sampled saved render requests had no storyboard references.
- **I was reborn:** 14 saved scenes. Twelve blueprint records were present, all drafts with no approved version. The sampled saved render requests likewise had no attached storyboard references.

Both JSON project records had empty `approved_scenes` lists. These are observations of the saved stores inspected, not a claim that the creator never clicked a lock or that every live/session state is represented there. Scene approval, storyboard-version approval, storyboard-image seed locks, and video-take seeds are separate states. A lock in one place does not prove the provider received an approved shot image.

## How to get closer to the film you imagined

1. **Approve the image of each individual shot before animating it.** A close-up needs a close-up starting image; an insert needs an insert. A character sheet can help identity but should not substitute for the intended composition. OpenRouter distinguishes frame control from general reference guidance. [OpenRouter image-to-video guide](https://openrouter.ai/docs/cookbook/video-generation/image-to-video)
2. **Give each clip one clear dramatic action and a starting/ending state.** Specify who is visible, where the important prop is, who holds it, the movement direction, camera behavior, and what must still be true at the end. Use the image to establish appearance, lighting, and composition; use the text chiefly to describe movement and progression. [Runway image-to-video guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide)
3. **Budget scene time across selected shots.** For example, a 24-second scene might contain 8 + 6 + 10-second shots. Three takes of each shot creates nine candidates; the three selected takes still make the intended 24 seconds. A clip's duration control does not allocate the whole scene's dramatic beats.
4. **Test the hardest continuity transition before a batch.** A handoff, costume change, entrance, or time-of-day change is more revealing than an establishing shot. Correct the frame and action specification before buying more variations of the same mismatch.
5. **Carry the story state into the next shot's image.** If someone now holds the key, the next approved frame should already reflect that ownership. Reusing an earlier image can reset the story. For continuous coverage, a reviewed last frame can serve as the next starting image; a change of angle needs a deliberately composed new frame.
6. **Choose takes for the cut.** Compare the actual opening/ending composition, action, prop ownership, eyeline, wardrobe, and light. A prettier take that contradicts the adjacent shot is not the useful take for this sequence.

If an approved Previs video already contains the performance you want, retain that exact clip for the edit. A new generative production render can differ even with the same inputs. A distinct “use this approved clip” handoff is a higher-confidence path than regenerating a performance you already accepted.

Seed locking aids repeatability under the same model and inputs. It does not enforce exact performance, camera choreography, or prop behavior throughout a clip. Where exact motion is essential, allow for editorial, compositing, or controlled-animation work after generation.

## Provider boundaries and remaining work

- The current OpenRouter HappyHorse model list advertises first-frame conditioning, 3–15 second clips, 720p/1080p, and seeds. It does **not** advertise last-frame control. The read-only snapshot is in `openrouter-model-capabilities.json`. [Live model discovery](https://openrouter.ai/api/v1/videos/models)
- First-frame rendering is wired here for OpenRouter and Runway. The existing direct DashScope HappyHorse/Wan integrations cannot silently ignore an explicit storyboard frame: they stop with an integration-capability error. This does not claim the vendors lack image-to-video products; those specific integration paths still need separate implementation.
- Runway Gen-4.5 uses supported pixel dimensions rather than an independent 1080p selector in this adapter. Some aspect mappings use the model's pixel grid and can crop the input. Local data URLs must fit Runway's image-size limit. [Runway input requirements](https://docs.dev.runwayml.com/assets/inputs/)
- The automatic shot breakdown remains a suggestion: line segmentation and positional framing do not establish the filmmaker's coverage plan. The next useful product improvement is an explicit per-shot agreement covering image, action, start/end state, duration, and permitted variations.
- Existing context enrichment can still introduce stale or incorrectly classified facts. The earlier real benchmark contained internal identity-review prose and an environment incorrectly identified as a character. Preserving text does not make those source facts correct.
- Storyboard visual-plan fields and a manually maintained prompt can diverge. This repair forwards explicit Previs edits and preserves the chosen prompt; it does not perform semantic conflict resolution or regenerate approved images automatically after every plan edit.
- Scene audio remains separate from visual timing. Unassigned scene dialogue can be reused for each shot, and the scene pipeline's default audio-overrun policy can freeze the last frame. Review shot-level dialogue assignment and the final edit rather than relying on a scene duration alone.
- Existing approved Previs packages and the one-button scene generator are separate workflows. Do not assume generating a scene automatically assembles the exact takes you selected elsewhere.
- The Canonical Production Thread panel explicitly requests the **simulated** provider for its render and revision actions. Its rehearsal behavior was preserved; the paid Previs render-engine dropdown does not control that panel. The package handoff is now corrected, but unifying those provider controls and offering direct promotion of approved clips remain separate product changes. Do not treat a simulated workflow completion as a real final-film render.
- Older production packages do not acquire missing input snapshots retroactively. Build a fresh package from reviewed Previs after activating the repair; do not infer lost historical settings from labels alone.
- The existing real baseline still shows repeated wide compositions, a prop handoff reset, and missing dusk-to-night progression. It remains unmodified at `../phase-two-2026-09-05/real-run-05/`. No new paid visual comparison was executed, so this review proves repaired request behavior, not a measured improvement in generated filmmaking quality.

## Verification and activation

**Final verification: 3,454 backend tests passed, 10 skipped; 681 frontend tests passed; production build passed.** The final backend run took 260.59 seconds and adds 26 passing tests to the preserved 3,428 baseline. The package/service/route follow-up has 26 passing tests. Logs are `backend-final.log`, `frontend.log`, `production-build.log`, and `package-targeted.log`. The backend test copy matches the working tree application and test sources byte for byte. Before/after regression evidence is retained alongside them. The build retains the existing large Three.js bundle warning.

The real browser test registered a test user, created and updated an isolated project, opened Previs, entered a 2,149-character prompt, and selected eight seconds. The actual API received those choices and persisted an eight-second job. Required context exceeded the configured Runway budget, so the request returned `needs_review` without a provider task ID. The UI recovered from busy state, the owner could read the job, and no page errors occurred. See `browser-summary.json`, `browser.log`, and `previs-runtime.png`. Browser API traffic went to an isolated real backend; no render responses were mocked.

Provider-payload tests use controlled HTTP boundaries and fixtures. They prove first-frame placement, identity-reference separation, supported local-image encoding, explicit seed preservation, and rejection of settings that would be changed. They are not visual-quality evidence.

The repository contains the repairs. The original running backend has not been restarted. Activating it also needs the pending authentication/legacy-project ownership rollout from the earlier phase; no existing films were assigned to a new account by this review.

## Implementation files

- `studio-backend/app/models/previs_render.py`: validated take-setting contract.
- `studio-backend/app/services/previs_service.py`: setting/provenance forwarding, retries, review stops.
- `studio-backend/app/services/storyboard_render_inputs.py`: shared shot input translation.
- `studio-backend/app/services/storyboard_blueprint_service.py`: approved scene inputs and source-text preservation.
- `studio-backend/app/services/scene_production_pipeline_service.py`: approved-shot resolution and review stops.
- `studio-backend/app/services/canonical_production_workflow_service.py`: frozen package inputs, video/image separation, and terminal render-review handling.
- `studio-backend/app/services/render.py`: creator-prompt and seed preservation, provider alias, unsupported-frame guard.
- `studio-backend/app/services/prompt_budget_service.py`: OpenRouter alias budget parity.
- `studio-backend/app/adapters/__init__.py`: first-frame payloads, local-image handling, output-setting checks.
- `studio-backend/app/routes/previs_routes.py`: thin request forwarding.
- `studio-backend/app/data/storage.py`: updates that retain the project row and its ownership.
- `studio-app/src/lib/studioApi.ts`, `studio-app/src/lib/jobStatus.ts`, `studio-app/src/pages/PrevisRoom.tsx`: actual take requests and truthful controls/statuses.
- Regressions: `test_checkpoint_4b_previs_integrity.py`, `test_checkpoint_5_canonical_workflow_thread.py`, `test_storyboard_provider_conditioning.py`, `test_project_access_boundary.py`, `test_runway_provider_hardening.py`, `test_render_provider_safety.py`, and `studioApi.test.ts`.
