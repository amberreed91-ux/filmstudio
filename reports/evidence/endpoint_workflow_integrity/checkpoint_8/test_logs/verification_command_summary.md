# Verification command summary

| Scope | Result | Machine evidence |
| --- | --- | --- |
| Independent reproduction plus its backend/frontend/build checks | 114 passed, 0 failed, 0 skipped, exit 0 | `../clean_state/reproduction/test_logs/reproduction_command_record.json` |
| Focused backend route/contract/persistence/workflow/state suite | 76 passed, 0 failed, 0 skipped | `backend_focused.xml` |
| Focused frontend workflow/API/route suite | 100 passed, 0 failed, 0 skipped | `frontend_focused.xml` |
| Standalone TypeScript project check | exit 0, no diagnostics | `npx tsc -b --pretty false` |
| Frontend production build | passed | `../clean_state/reproduction/test_logs/frontend_production_build.command.json` |
| Browser verification | 6 passed, exit 0 | `../browser/live_session/browser_evidence.json` |
| Browser seed reproduction | 111 passed, 0 failed, 0 skipped, exit 0 | `../browser/seed_reproduction/test_logs/reproduction_command_record.json` |

The backend selection explicitly includes Checkpoints 2–5, Storyboard route lifecycle, render persistence, provider truth, and render route contracts. The frontend selection covers canonical workflow client/context/panel, recovery polling, Previs resolution, Studio API contracts, Production Board, and route registration.
