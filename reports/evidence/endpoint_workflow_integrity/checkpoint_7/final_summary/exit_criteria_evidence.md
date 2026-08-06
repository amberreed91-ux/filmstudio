# Checkpoint 7 exit-criteria evidence

| # | Criterion | Evidence | Command | Result | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Reproduction script exists and exits nonzero on deliberate failure | `tools/verify_endpoint_workflow_integrity.py`; `after_fixes/deliberate_failure/test_logs/reproduction_command_record.json` | verifier with `--deliberate-failure` | Exit 1 | VERIFIED | Controlled failure recorded without suppression |
| 2 | Evidence directories populated | `checkpoint_7/` directory tree | final evidence inventory | Required areas present | VERIFIED | Includes before/after, tests, HTTP, OpenAPI, DB, browser, provider, diff, hashes, summary |
| 3 | Raw outputs and exit codes preserved | `after_fixes/reproduction_success/test_logs/` | verifier with `--with-test-suite` | Exit 0; stdout/stderr and command JSON | VERIFIED | Main run 114 pass, 0 fail, 0 skip |
| 4 | Test integrity audited | `test_logs/test_integrity_audit.md` | complete test diff audit of `a2c85ea8` | 45 assertion lines added, 0 removed | VERIFIED | No skips, deletions, renames, or loosened assertions |
| 5 | Complete Git diff audited | `diff_review/checkpoint_6_complete_diff_audit.md` | complete commit scan and manual review | No prohibited bypass found | VERIFIED | All 32 files reviewed |
| 6 | Provider results correctly labeled | `provider/summary.md`; structured provider record | isolated run with `RENDER_PROVIDER_TEST_MODE=mock_success` | Simulated, paid calls false | VERIFIED | No real-provider claim |
| 7 | SHA256 hashes recorded | `hashes/checkpoint_7_sha256.txt` | `shasum -a 256` over evidence and deliverables | Hash index created | VERIFIED | Includes report, script, manifest, runtime, DB, browser, and logs |
| 8 | Exit criteria mapped to evidence | This file and root `evidence_manifest.md` | evidence review | All criteria mapped | VERIFIED | No criterion relies only on narrative |
| 9 | No unsupported completion claim remains | Machine result, raw logs, audits, provider label, and hash index | cross-evidence consistency review | Every report claim has a cited artifact | VERIFIED | Real/simulated boundaries are explicit |
| 10 | Focused checkpoint commit created or prepared | Staged Checkpoint 7-only diff and worktree baseline | `git diff --cached --name-status` | Focused commit prepared | VERIFIED | Pre-existing dirty paths excluded |

## Reproduction result

- Project: `checkpoint7-80c335feb5`
- Run: `workflow-4970b9cfda8c`
- Final state: `revision_completed`
- Required transitions: 15/15 present
- Main verification: 114 passed, 0 failed, 0 skipped, exit 0
- Backend focused tests: 5 passed, exit 0
- Frontend focused tests: 45 passed, exit 0
- Production build: exit 0
- Deliberate failure: exit 1
