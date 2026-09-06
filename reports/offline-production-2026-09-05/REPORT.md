# Free production verification and repairs

No paid image, video, voice, or music generation was performed. Verification used disposable project stores, locally created video/audio fixtures, and the actual assembly, delivery, screening, and persistence services.

## Changes

- Film delivery explicitly disables new audio generation when it assembles missing/outdated scenes. Scene assembly also defaults to no new audio generation. It retains audio already present in a take and can mix a locally supplied per-shot dialogue file. It skips voice synthesis and score generation, even when those providers are configured. The separate audio-generation tools remain available; this is not a global spending lock on the entire application.
- Theatre states that assembly reuses existing footage/audio and does not generate new voices or music.
- Multi-shot scene generation no longer assigns every unscoped scene dialogue line to every shot. A shot receives its explicitly assigned lines; unassigned multi-shot dialogue remains unassigned. The one-shot scene fallback remains supported. Explicit empty dialogue lists now remain empty instead of triggering a range-based fallback that could restore unwanted lines.
- Scene assembly now normalizes all selected shots to the first shot's even-sized canvas at 24 fps, using letterboxing and consistent audio streams. This closes a gap where individual clips were normalized independently and then concatenated with differing dimensions/frame rates. It preserves the existing full-film delivery convention; configurable mastering formats are not added.

## Free end-to-end evidence

`tests/test_offline_production_delivery.py` uses actual FFmpeg media processing and SQLite:

1. Two one-second shots have different aspect ratios, resolutions, and frame rates.
2. One receives locally supplied audio; the other retains audio already in its video.
3. Film delivery assembles the scene, exports the film, and records the exact job IDs.
4. Decoded frames prove the picture order and consistent final canvas.
5. Audio-frequency measurements prove both sound sources survive in order; measured duration confirms the edit is not extended.
6. The exported file is registered in Screening and explicitly approved in the isolated fixture.
7. Reopening SQLite preserves the approved output, selected inputs, and current-delivery state.

Voice synthesis and music generation are wired to fail the test if invoked. The local tones are engineering fixtures, not a claim about generated voice performance or musical quality.

## Validation and activation

- 31 focused tests passed, covering the free end-to-end flow, take selection, scene assembly, scene pipeline, and supplied audio.
- 96 audio-provider/API regression tests passed. Total: 127 targeted checks.
- TypeScript/Vite production build passed.
- The first media run encountered the environment's shared-memory/OpenMP sandbox limitation; the identical isolated tests passed outside the sandbox. No failing product assertions were removed.
- The verified backend application copy matches the working tree byte for byte (`source-verification.json`).
- The idle local backend was restarted to activate these fixes; readiness and both existing projects' read-only contracts are recorded in `live-activation.json`. No real film was generated, reassembled, selected, or approved during activation.

## What remains unproven

A new provider render's facial fidelity, prop handoff, exact coverage, lighting transition, or emotional performance cannot be established from these software tests. These checks fix and verify the software and media pipeline without requiring a new paid production. Existing generated footage is not silently repaired or regenerated.
