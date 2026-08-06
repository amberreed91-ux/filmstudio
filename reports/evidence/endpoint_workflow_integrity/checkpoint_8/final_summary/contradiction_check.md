# Checkpoint 8 contradiction check

| # | Required contradiction check | Evidence reviewed | Result |
| ---: | --- | --- | --- |
| 1 | Tests pass while runtime calls fail | 76-test backend XML, 100-test frontend XML, 102-request clean trace, final browser trace | CLEAR — canonical runtime calls pass; negative/optional failures are deliberate and classified. |
| 2 | OpenAPI routes return 404 | Runtime OpenAPI, canonical route inventory, final browser production-thread reads | CLEAR — all required paths present; valid canonical browser reads are 200. |
| 3 | Backend routes work while frontend calls another path | Frontend contract tests and browser request URLs | CLEAR — browser uses the same `/api/f51/studio` paths in OpenAPI. |
| 4 | Responses claim persistence while storage is empty | Persistence export, table counts, run row, 15 transitions, restart reload | CLEAR — API and SQLite match before and after restart. |
| 5 | Jobs say completed without assets | Provider evidence, render/Screening tests, complete-without-asset regression | CLEAR — terminal clean jobs have assets; missing output is demoted to failure. |
| 6 | Reports claim no failures while logs contain failures | Main command record, preserved browser attempt, browser summary, report risks | CLEAR — the main run has zero failures; the 429 attempt and external advisory calls are explicitly disclosed, retained, and excluded from success totals. |
| 7 | Current versions differ between services | Run, package, provider request, Editorial, Film Cut, and revision provenance | CLEAR — the approved Blueprint and exact Film Cut lineage agree across services. |
| 8 | Approval state differs between frontend and backend | Browser `revision_completed`/memory UI, exact run GET, SQLite transition list | CLEAR — visible state is restored from the same backend record. |
| 9 | Reported test totals differ from saved logs | JUnit XML and managed command JSON | CLEAR — backend 76, frontend 100, verifier 114, browser seed 111, final browser 6. Suites overlap and are not summed. |
| 10 | Files listed in reports differ from Git diff | Baseline, final isolated staged diff review | CLEAR — Checkpoint 8 stages only the final report, manifest, and `checkpoint_8/**`; pre-existing worktree changes remain unstaged. |

Result: no unresolved contradiction prevents **VERIFIED COMPLETE**.
