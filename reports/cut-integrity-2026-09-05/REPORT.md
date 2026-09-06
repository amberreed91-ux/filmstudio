# Theatre cut integrity — September 5, 2026

Implemented and activated three fixes without paid generation:

- Theatre recognizes both manual (`scene_002_shot_003`) and automatically split (`shot_scene_002_003`) shot IDs. It groups aliases as takes, retains exact job IDs for preview/selection, and passes the actual shot ID to review panels.
- Scene delivery records content hashes for the local pre-supplied recordings it consumes. Added, replaced, or removed recordings invalidate the scene and film. Replacing bytes under the same name, size, and modification time is detected. Changes during assembly/export abort publishing the new composition/film pointer.
- Assembled film outputs expose typed current/outdated/unverified freshness. Changing the cut leaves the saved file and its approval intact, but an outdated current final no longer reports the project complete. Rebuilding creates a separate output requiring its own approval. Theatre shows notices beside the player and in Approve, refreshing on take changes and window focus. Packages without recording/take provenance are explicitly marked unverified.

## Verification

- 30 focused backend tests passed in a disposable backend copy, including real FFmpeg media, audible frequency checks, picture ordering, audio replacement/removal, stale approval, rebuild/reapproval, and a recording changing during assembly.
- All 709 frontend tests passed; TypeScript and production build passed after final UI edits.
- Visible browser verification: auto-split exact take selection, preview without saving, reload persistence with intercepted writes, rejected/cleared choice behavior, stale approval notices in Watch and Approve, desktop/mobile layout, no page errors.
- Live project browser check read-only; test mutations were intercepted. Backend restarted only after confirming no unfinished render jobs. Readiness and both projects' choice/assembly endpoints passed; schema remains v62.

## Limits

Existing scene manifests without audio fingerprints may need one rebuild. Legacy composed scenes without a manifest remain reusable when no explicit take choices or supplied recordings require a traceable assembly. Package outputs outside the assembled-film pipeline are labeled unverified rather than claiming freshness. External recording changes are checked on status/manifest reads, window focus, and assembly; this is not continuous filesystem monitoring.

No new footage, voices, or music was generated for the user's projects. The fixes improve delivery reliability; they do not supply missing footage or establish that either existing project is a finished film.
