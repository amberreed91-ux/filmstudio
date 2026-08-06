# Checkpoint 4B — Previs

## Result

Pass. Repository evidence confirms the canonical product name is **Previs**. No independent filmmaking feature, route family, model, or UI named “Precise” exists; incidental uses of the adjective “precise” are unrelated prose. This report does not claim cross-subsystem workflow integration.

## Audit findings

- The service called nonexistent storage methods for scenes, making the primary generation path nonfunctional.
- A provider job was submitted before its Previs record was saved, so submission failure could become invisible.
- Duplicate active jobs were not prevented.
- Provider polling errors were swallowed and active records could remain pending indefinitely.
- A provider-complete job without an asset could appear unfinished instead of failed.
- Approval, explicit revision, retry, cancellation, and production-package behavior were absent.
- Previs records did not retain exact Storyboard Blueprint/version/shot provenance.
- Frontend generation bypassed the Previs lifecycle and called generic render operations directly.

## Repairs

- Replaced nonexistent scene calls with canonical project-scene ownership lookup.
- Persisted a queued Previs record before provider submission.
- Persisted provider submission failures as terminal failed records and propagated a structured provider error.
- Added active-job idempotency across service restart/reload.
- Added terminal-state-aware polling, explicit missing-output failure, and provider-error propagation.
- Added project-scoped record loading, explicit approval, cancellation, and traceable retry attempts.
- Protected approved Previs; regeneration requires an explicit revision request and never overwrites the approved record.
- Recorded `blueprint_id`, `blueprint_version_id`, and `storyboard_shot_id` for approved Storyboard-driven Previs.
- Threaded Storyboard prompt, image references, staging, character/reference context, and continuity material into the provider request/package record.
- Added production-package creation gated on an approved Storyboard version and approved Previs for every shot.
- Wired Previs Room generation to the canonical Previs route.

## State model

Active states are queued/pending/submitted/generating/processing/rendering/retrying. Terminal states are complete/approved/failed/cancelled/superseded/rejected. Terminal records are not polled again.

## API surface verified

- Generate a rough scene Previs or an approved Storyboard-shot Previs.
- List scene Previs records and refresh active provider status.
- Load a project-owned record by ID.
- Approve, cancel, and retry a record.
- Create a provenance-bearing production package.

## Regression evidence

- Canonical scene lookup works and invalid project/scene/shot ownership fails.
- Duplicate active generation returns the existing job after restart.
- Submission failure remains visible after the exception.
- Complete-without-asset becomes failed and stops polling.
- Approved output cannot be overwritten.
- Retry creates a new attempt linked to its source record.
- Storyboard provenance and production packages survive reload.
- Focused Previs/backend route suite: 21 passing tests.
- Frontend API tests and production build pass.

## Exit status

Rough Previs, Previs Room calls, image creation/loading, status, approval, regeneration, retry, cancellation, polling, references, and production packaging pass independently.
