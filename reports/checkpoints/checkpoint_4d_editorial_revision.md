# Checkpoint 4D — Editorial / Film Cut / Timeline / Revision

## Result

Pass. Film Cut and Timeline are now versioned canonical artifacts rather than a single mutable project field. This report does not claim cross-subsystem workflow integration.

## Audit findings

- The canonical cut existed only as mutable `project.film_cut` JSON.
- Timeline changes had no independent durable version history.
- Applying a decision checked only an optional caller-provided context hash and did not verify that the analysis still referenced the current cut.
- Cut mutation and editorial-application persistence were separate writes.
- Revision comparison lacked canonical Film Cut provenance.
- Final Film Cut approval was not a persisted version-selection operation.

## Repairs

- Added durable `film_cut_versions` and `film_cut_state` persistence.
- Bootstrapped legacy Film Cut state once, preserving its scene order and timeline.
- Added current/version loading, explicit timeline update, version comparison, and final approval APIs.
- Every timeline update creates a distinct version with `source_cut_id`; approved source versions remain protected.
- Editorial analysis now resolves and records the exact canonical `source_cut_id`.
- Applying decisions requires creator confirmation and a non-empty exact context hash.
- Application rejects when the analysis cut is no longer current or when current evidence changes the context hash.
- Reorder decisions create a new Film Cut version linked to the originating analysis and application.
- Film Cut version creation and editorial application persistence are one SQLite transaction.
- Revision comparison reports moved/added/removed scenes, timeline change, and source cut/analysis/application provenance.
- Final approval only applies to the current cut and persists the approved-cut selection.
- Legacy project JSON remains a compatibility mirror; SQLite is canonical.
- Frontend Editorial Intelligence exposes the current version, explicit cut revision, and explicit cut approval.

## Regression evidence

- Film Cut and timeline bootstrap survive service reload.
- Timeline edits create distinct versions and preserve an approved prior cut.
- Unconfirmed and stale timeline updates fail deliberately.
- Analysis references the exact cut version.
- An older analysis cannot modify a newer current cut.
- Applied decisions retain analysis/source/result version provenance.
- Revision comparison identifies moved scenes and lineage.
- Only the current cut can be finally approved, and approval survives reload.
- Dedicated Editorial/Revision integrity suite: 7 passing tests.
- Focused canonical plus legacy Editorial suite passes after compatibility verification.
- Frontend Editorial/API tests and production build pass.

## Exit status

Film Cut loading/persistence, Timeline loading/persistence, exact-version analysis, confirmed decision application, stale rejection, version creation, comparison, provenance, and final approval pass independently.
