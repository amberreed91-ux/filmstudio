# Checkpoint 7 — Evidence and Integrity

Status: **VERIFIED COMPLETE**

Provider classification: **SIMULATED PROVIDER VERIFICATION**

Paid provider calls: **false**

## Independent result

`tools/verify_endpoint_workflow_integrity.py` created a fresh temporary SQLite/JSON backend, created project `checkpoint7-80c335feb5` through public HTTP APIs, built and approved its Storyboard Blueprint, and exercised the entire canonical production thread.

Run `workflow-4970b9cfda8c` reached `revision_completed`. All 15 required semantic transitions were present. API state matched SQLite, and the same run/status/transition count reloaded after a full backend restart.

The main verifier recorded 114 passed checks, 0 failures, 0 skips, and exit 0. Its deliberate-failure mode recorded exit 1.

## What the verifier proves

- Python/runtime dependencies and backend health are checked before state creation.
- Runtime OpenAPI must contain the required project, Storyboard, and canonical workflow routes.
- The project, script, scene, Blueprint, and workflow are created without manually seeding hidden database state.
- Invalid script ownership and every unconfirmed approval/memory boundary are rejected.
- Previs and production-render duplicate submissions preserve their original job IDs.
- Simulated provider status is polled to terminal state through real HTTP routes.
- Completed renders register in Screening.
- Editorial analysis and creator-selected application persist.
- Film Cut update/approval and revision submission/polling persist.
- Revision polling reuses the submitted revision job.
- Explicit memory save is required and marked `explicitly_saved`.
- SQLite rows match the HTTP transition count.
- Terminal state survives backend restart.
- Paid provider calls remain disabled.

## Raw command results

| Command | Exit | Pass | Fail | Skip | Raw record |
| --- | ---: | ---: | ---: | ---: | --- |
| Independent reproduction with test suite | 0 | 114 | 0 | 0 | `after_fixes/reproduction_success/test_logs/reproduction_command_record.json` |
| Backend focused tests | 0 | 5 | 0 | 0 | `backend_focused_tests.command.json` |
| Frontend focused tests | 0 | 45 | 0 | 0 | `frontend_focused_tests.command.json` |
| Frontend production build | 0 | 1 | 0 | 0 | `frontend_production_build.command.json` |
| Deliberate failure injection | 1 | 2 | 1 | 0 | `after_fixes/deliberate_failure/test_logs/reproduction_command_record.json` |

Each record includes working directory, exact command, exit code, timestamps, safe environment classification, stdout path, stderr path, and totals. No command uses forced success or broad test exclusion.

## Integrity audits

The Checkpoint 6 commit was reviewed in full: 32 files, 1,886 insertions, and 128 deletions. No hardcoded success, production fake, disabled validation/auth, removed assertion, test skip, lint/type ignore, disabled route, commented failure, or temporary bypass was found.

Eight changed test files were audited. They added 45 assertion lines and removed none. No test was deleted, skipped, renamed, or loosened. The deterministic delayed-render fixture specifically proves that revision polling does not create a second job.

## Evidence map

- Manifest: `reports/evidence/endpoint_workflow_integrity/evidence_manifest.md`
- Exit criteria: `checkpoint_7/final_summary/exit_criteria_evidence.md`
- HTTP: `after_fixes/reproduction_success/runtime_http/requests.json`
- OpenAPI: `after_fixes/reproduction_success/openapi/runtime_openapi.json`
- Persistence: `after_fixes/reproduction_success/database/persistence_export.json`
- Provider: `after_fixes/reproduction_success/provider/provider_evidence.json`
- Diff audit: `checkpoint_7/diff_review/checkpoint_6_complete_diff_audit.md`
- Test audit: `checkpoint_7/test_logs/test_integrity_audit.md`
- Browser/network: Checkpoint 6 browser evidence, referenced by Checkpoint 7 summaries
- Hashes: `checkpoint_7/hashes/checkpoint_7_sha256.txt`

## Exit criteria

All ten Checkpoint 7 exit criteria are mapped to raw evidence and verified. The focused Checkpoint 7 commit was prepared without staging any pre-existing worktree changes. Checkpoint 8 was not started.
