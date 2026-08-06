# Browser verification summary

## Final bounded session

- Frontend: freshly started Vite server at `http://127.0.0.1:5001`.
- Backend: freshly restarted FastAPI server at `http://127.0.0.1:8010` using only the disposable seed database.
- Project: `checkpoint7-226b67f779`.
- Run: `workflow-76e30cbfc425`.
- Result: 6 checks passed, exit 0.
- Canonical request statuses: five valid production-thread reads, all HTTP 200.
- Refresh: restored `revision_completed`, the same run, the same Blueprint version, and 15 persisted transitions.
- Negative UI case: a newly generated unknown project returned a structured not-found response and rendered it visibly.
- Browser page errors during the valid-project and refresh checks: zero.
- Rate-limit responses in the final session: zero.

The session recorded 97 successful API responses, 26 deliberate/optional 404 responses, and two media redirects. The 404s consist of absent optional poster/final-package/composition resources and deliberate unknown-project reads. They are not canonical route misses. The exact valid production-thread list/run requests are 200 in `live_session/browser_evidence.json`.

The peripheral emotion-analysis request was intercepted with a deterministic local response during the final run so browser verification could not trigger an external LLM call. Canonical workflow, project, Screening, Film Cut, render-job, and persistence requests remained live and unmocked.

## Preserved first attempt

`attempt_1_rate_limited/browser_evidence.json` records an over-broad navigation sequence. Its required valid-project, refresh, explicit-refresh, and unknown-project visibility checks passed, but a fourth full page load crossed the in-memory request-rate threshold and produced 429 responses. The attempt exited 1 and was retained rather than hidden. Restarting the isolated backend cleared that transient in-memory window; the bounded final session passed without 429s. No application repair or weakened limit was used.

That first attempt also revealed that Screening's existing emotion-analysis effect automatically invoked the configured external Qwen LLM twice while the page was open. This was not a render request and did not affect canonical workflow state, but it was real external advisory-provider activity. The final run intercepted only that peripheral endpoint to prevent further external calls. This behavior is disclosed as a remaining cost/side-effect risk in the final report; no claim of “no provider calls” is made beyond the verifier's specific `paid_provider_calls: false` render classification.

## Cleanup

Both servers were stopped. The exact disposable directory reported by the seed verifier was deleted after the live checks. Repository user data and the pre-existing dirty worktree were not modified by the browser run.
