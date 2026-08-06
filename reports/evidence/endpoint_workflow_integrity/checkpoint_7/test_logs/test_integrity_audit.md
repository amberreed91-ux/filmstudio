# Checkpoint 6 test integrity audit

Audited commit: `a2c85ea8 fix: align frontend with canonical production workflow`

## Quantitative review

- Test files changed: 8
- Assertion lines added: 45
- Assertion lines removed: 0
- Tests deleted: 0
- Tests skipped: 0
- Tests renamed: 0
- Broad exclusions added: 0
- Failure suppression added: 0

The two removed test-file lines were an import replacement in `studioMedia.test.ts` and the old one-line `get_job_status` body in the deterministic renderer. Neither was an assertion.

## File-by-file audit

| Test file | Assertions/coverage added | Mocks or fixtures changed | Integrity assessment |
| --- | --- | --- | --- |
| `CanonicalWorkflowPanel.test.tsx` | Exact project, scene, status, and explicit start action | Hook is isolated with a local Vitest mock | New UI contract coverage; no production behavior bypassed |
| `canonicalWorkflowApi.test.ts` | Exact URL encoding, no duplicate prefix, method/payload shape, missing-ID rejection, single render POST | Fetch mocked at HTTP boundary | Strengthened client contract and duplicate-call protection |
| `canonicalWorkflowContext.test.ts` | Selected-scene extraction, no cross-scene leakage, room-specific next action, bounded polling eligibility | Canonical run fixture added | Strengthened state-machine coverage |
| `optionalStudioApi.test.ts` | 404 becomes empty state, 200 parses, non-404 errors remain visible | Fetch mocked at HTTP boundary | Verifies narrow optional-resource behavior; does not swallow general failures |
| `projectContext.test.ts` | Project/scene/shot preservation and undefined-ID omission | None | Strengthened deep-link/history contract |
| `studioMedia.test.ts` | Rejects macOS, `file:`, and Windows local paths while retaining browser `/outputs` route | None | Strengthened browser boundary |
| `test_checkpoint_5_canonical_workflow_routes.py` | Project/scene run listing and current Blueprint version | Existing fake service extended only for the new route contract | Strengthened route/API coverage |
| `test_checkpoint_5_canonical_workflow_thread.py` | Submitted revision state, durable job ID, completion on later poll, create count unchanged | Deterministic renderer gains delayed-completion mode | Reproduces and prevents the live duplicate-revision defect |

## Assertions removed or loosened

None. No expected status, exception, count, or payload assertion was weakened.

## Mocks and fixtures

Mocks are limited to frontend HTTP/hook boundaries and the pre-existing deterministic backend renderer. The renderer enhancement makes completion asynchronous so the test can prove the same job is polled instead of recreated. It does not force the production service to succeed or bypass validation.

## Test data changes

Only new canonical fixture identifiers and deterministic delayed-render metadata were added. No existing fixture was rewritten to avoid a failure.

## Coverage conclusion

Coverage was strengthened. The independent reproduction separately exercises the real HTTP routes, SQLite persistence, backend restart, invalid requests, and simulated-provider polling without importing these unit-test fakes.
