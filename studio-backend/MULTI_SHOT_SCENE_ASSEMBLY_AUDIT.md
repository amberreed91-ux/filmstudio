# Multi-Shot Scene Assembly Audit

## Gating answer

Scene assembly existed before this work, but it was not reliable on the active
branch.

- The repository had an older FFmpeg scene composer that concatenated completed
  shot files with stream copy. It could carry an existing audio stream only when
  every input happened to have compatible streams.
- The active compose route did not run a dependable per-shot dialogue bake.
  Its optional audio path mixed scene-level tracks and did not place dialogue
  independently within each shot.
- The active parser recognized legacy IDs such as `scene_002_shot_001`, but not
  auto-split IDs such as `shot_scene_002_001`. As a result, a real auto-split
  multi-shot scene could be silently reduced to zero discovered shots.
- A stronger per-shot audio compositor and the auto-split parser fix existed in
  repository history (`fc08b85c` and `4bdbd8a6`), but the active branch was not
  descended from those changes and had regressed.

Therefore this session did not invent assembly from nothing. It repaired,
reinstated, and hardened an incomplete/regressed capability.

## Implemented delivery path

The canonical compose route now delegates to `SceneAssemblyService`, which:

1. Discovers every completed shot using shared legacy and auto-split ID parsers.
2. Deduplicates retries by shot ordinal and sorts shots numerically.
3. Generates dialogue per shot with CosyVoice using the shot's persisted
   dialogue-line metadata.
4. Bakes that dialogue into its shot, extending the final video frame when
   dialogue runs longer than the source picture.
5. Normalizes every shot to H.264/yuv420p video and AAC 48 kHz stereo audio.
6. Pads each audio stream to the exact shot duration so the assembled output has
   an audio packet timeline across every shot boundary.
7. Concatenates normalized video and audio together into one scene-level MP4.
8. Optionally mixes one scene-length score/ambient bed after concatenation.
   The current configured score/ambient provider is `none`, so the selected
   verification scene intentionally uses dialogue only.
9. Rejects delivery if video/audio streams are missing, audio and container
   durations diverge, audio packets gap or overlap at boundaries, or required
   per-shot dialogue was not successfully baked.

The same delivery path is used by the scene compose endpoint and by automatic
scene composition during full-film assembly.

## Real-scene verification target

- Project: *I Was Reborn* (`project_3dba9330f43a`)
- Scene: `scene_002`
- Characters: Maya and Dre
- Shots: `shot_scene_002_001` through `shot_scene_002_004`
- Persisted dialogue: ten lines distributed across all four shots
- Picture sources: four saved real Runway render outputs

The user explicitly authorized transmitting the ten dialogue lines to
DashScope. The managed execution environment nevertheless denied that export
under its tenant data policy, including after consent. The restriction cannot
be bypassed or worked around.

A policy-safe proof was therefore rendered with the bundled local Piper
provider through the same canonical assembly service:

- Output: `static/composed/project_3dba9330f43a/scene_002_audio.mp4`
- Duration: 22.445 seconds
- Video: H.264, 1280x720, yuv420p
- Audio: AAC, 48 kHz, stereo
- Dialogue: ten lines, distributed 3/3/1/3 across the four shots
- Score/ambient: skipped because the current provider is `none`
- Audio packet gap/overlap: at most one microsecond
- Incoming-shot acoustic onset after each boundary: 82 ms, 75 ms, and 21 ms

This is a valid complete multi-shot scene with local dialogue audio and no
material assembly-introduced boundary gap. It is not represented as a
CosyVoice render. The production path still defaults to CosyVoice and rejects
provider failures instead of accepting silence, but an actual CosyVoice render
cannot be demonstrated in this environment under the enforced export policy.

## Test status

- Assembly-focused tests: 11 passed.
- Backend full suite after final changes: 2,683 passed, 58 failed, 10 skipped.
- Frontend full suite: 550 passed, 14 failed.
- `git diff --check`: passed.

The full-suite failures are outside the assembly-focused test set. They include
pre-existing live-provider/network assumptions, script-intelligence expectation
regressions, co-director mock-target mismatches, FFmpeg/OpenMP shared-memory
aborts in unrelated video-analysis tests, and existing frontend contract or
copy expectations.

## Requirement-by-requirement completion audit

| Requirement | State | Authoritative evidence |
|---|---|---|
| Establish whether assembly pre-existed | Complete | Active source trace plus historical commits `4bdbd8a6`, `fc08b85c`, and `381469e1` |
| Determine video-only versus video/audio behavior | Complete | Legacy `compose_service` used FFmpeg stream-copy concatenation; the repaired service explicitly normalizes and maps both streams |
| Determine whether continuity was sophisticated or naïve | Complete | Legacy path had no per-shot normalization or boundary validation; repaired path records AAC packet timing and per-shot dialogue state |
| Confirm the shot-ID regression | Complete | Active branch parser accepted legacy IDs only; regression coverage now exercises `shot_scene_002_001` ordering and inclusion |
| Assemble all shots into one scene video | Complete | `scene_002_audio.mp4`, four persisted real Runway shots |
| Generate and bake dialogue independently per shot | Complete with local provider | Assembly report records complete 3/3/1/3 line distribution and `dialogue_baked=true` for every shot |
| Use CosyVoice for the real proof scene | Blocked by external policy | User consent was obtained; managed execution still denied transmission of the ten lines to DashScope |
| Apply current score/ambient decision | Complete | Provider is `none`; report records `score_ambient_status=skipped` |
| Verify no missing/overlapping audio packets | Complete | 1,057 packets; maximum gap and overlap are each one microsecond |
| Verify boundary acoustic behavior | Complete for local proof | Independent `-45 dB` silence analysis records incoming audio within 82 ms, 75 ms, and 21 ms of the three cuts |
| Verify dialogue timing per shot | Complete for local proof | Persisted ranges resolve to 3/3/1/3 lines; overruns on shots 2 and 4 use `freeze_last_frame` |
| Run complete test suites | Complete | Backend 2,683 passed / 58 failed / 10 skipped; frontend 550 passed / 14 failed |
| Link a complete real multi-shot output | Complete with local provider | `static/composed/project_3dba9330f43a/scene_002_audio.mp4` |

The goal cannot be marked fully complete while the explicitly required
CosyVoice proof remains unverified. The local artifact proves scene-level
assembly and audio continuity, but provider equivalence is not assumed.
