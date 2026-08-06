# Runtime HTTP evidence

The complete sanitized request/response sequence is stored at `after_fixes/reproduction_success/runtime_http/requests.json`. It contains method, URL, request payload, response status, response payload, duration, timestamp, and named verification step for every request.

The run created a clean project through HTTP, exercised Storyboard and every canonical production stage, rejected invalid ownership and unconfirmed approvals, polled provider and canonical status, reloaded state, and reloaded again after a backend restart.

Result: `workflow-4970b9cfda8c`, `revision_completed`, 15 required transitions.
