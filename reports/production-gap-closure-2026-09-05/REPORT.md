# Production gap repairs — 5 September 2026

The repaired local backend is active on loopback port 8010 with schema 62; the existing frontend at port 5001 exposes the new Theatre controls. Existing films were preserved. No real take choices, approvals, uploads, or paid provider generations were made during verification.

## Creator workflow

In Theatre, preview a shot and take, then explicitly choose **Use this take for the cut**. Previewing alone performs no save. The selected job persists in SQLite across reloads and backend restarts; later renders cannot replace it. **Clear take choice** restores the existing latest-completed-take behavior for that shot. Shots without an explicit choice still use their latest completed take.

Under **Prepare the full film**, assemble or rebuild the film to apply changed choices. Existing exported files remain available under distinct URLs. A rebuilt film is registered for screening and explicit approval, and the player prefers the new delivery over an older approved final. Shot preview uses the exact selected render instead of falling back to an unrelated scene edit.

## Repairs

- Added typed, service-mediated take-choice APIs, durable project/scene/shot choices, ownership validation, and stage logging. Missing, failed, foreign-project, or wrong-shot chosen jobs cannot silently fall back to another take. Delivery examines the complete stored project job history; a known shot with no completed take prevents partial scene assembly.
- Scene assembly and the older composition path resolve explicit choices. Scene delivery records the actual job IDs, supports a one-shot scene, and writes a distinct output file for each assembly. Cached reuse requires matching inputs and an existing file.
- Moved full-film assembly out of the route into FilmDeliveryService. It follows the saved screenplay scene order, assembles missing/outdated scenes, aborts on missing media, normalizes scene streams to the first scene's canvas at 24 fps with letterboxing, and verifies duration and full-file decoding before recording delivery. Frame-rate conversion is part of this delivery path; it is not a configurable mastering/export profile.
- Delivery status reads durable manifests instead of an unbounded process cache. Changed take inputs, scene files, or scene order mark the film outdated. Legacy exports without provenance need rebuilding before they are described as current.
- Full-film media contains a normalized audio stream, including silence padding where a scene has no audio. `has_audio` means an audio stream exists, not that dialogue/music quality was evaluated.
- Dialogue that exceeds the selected take's duration stops scene assembly with a recoverable timing error instead of freezing the last frame. Existing per-shot dialogue assignment and prerecorded-audio support remain; this does not add an audio timeline editor.
- Environment continuity no longer infers a persistent location from arbitrary prompt prepositions such as “looks at Jules” or “in blue clothes.” Structured scene/environment fields establish location identity.
- Character provider context keeps human-review status in metadata instead of sending “not yet verified” / “human review needed” as visual instructions. Actual stored identity and appearance facts remain.
- Theatre provides a concrete continuity review cue for prop ownership, eyeline, costume, light, action, and dialogue placement. It does not automatically claim visual continuity or block creator choices with creative advice.

## Verification

- Broad isolated backend run: **3,535 passed, 10 skipped** (`backend-tests.log`).
- Final affected suite after the last completeness/cached-reuse refinements: **29 passed** (`final-focused-rerun.log`). This includes an additional missing-shot regression. The first focused rerun hit an OS shared-memory/OpenMP restriction; the identical isolated checks passed outside the sandbox. No product assertion was weakened.
- Frontend: **705 passed across 81 files** (`frontend-tests.log`). TypeScript/Vite production build passed (`build.log`).
- Actual FFmpeg media checks verify the chosen older take by decoding its exported frame, verify scene order using distinct picture colors, verify both scene soundtracks using their measured tone frequencies, check final duration and decoding, reopen SQLite, and confirm rebuilding preserves the prior file.
- Browser: exact older-job selection; no preview write; reload persistence; failed-clear recovery; explicit clearing; desktop/mobile inspection; no horizontal overflow or page errors. Writes used intercepted fixtures. A second read-only check against the activated backend confirmed the live choice control is ready (`browser.json`, `live-browser.json`).
- Migration 62 rehearsed against an SQLite backup: integrity OK, no foreign-key errors, no existing table row counts changed. Backup and rehearsal locations are recorded in `activation-backup.json`.
- Activation occurred with no active or queued provider work. Both saved projects return the new contracts; live readiness reports schema 62 (`live-activation.json`). Verified backend application files match the activated source (`source-verification.json`).

## Remaining acceptance work

A new real cinematic sequence with generated dialogue and music still needs review through this complete workflow. This pass verifies software selection, media assembly, sound preservation, persistence, and delivery; it does not prove that generative video now follows every prop handoff, close-up, lighting change, or performance direction. Approved first frames and human review remain necessary.

The existing canonical production approval gates remain separate from Theatre output approval. This pass does not turn a Theatre take choice into canonical package approval, and it does not silently regenerate existing storyboards or footage.

The live delivery status reports one composed scene out of fourteen for “I was reborn,” and no composed scenes out of eleven for “THE LAST TIDE.” These are project completion states, not software failures; the remaining scenes need footage and assembly before a full-film delivery can succeed.
