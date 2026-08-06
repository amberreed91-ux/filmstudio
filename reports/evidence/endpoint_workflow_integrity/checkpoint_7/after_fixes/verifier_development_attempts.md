# Verifier development attempts

The independent verifier was developed against fresh isolated projects. These were verifier-assertion failures, not product failures, and each run exited nonzero:

1. Assumed Previs job IDs were already in the production render identifier list. Corrected to inspect Previs artifacts at that stage.
2. Disabled the production queue worker, leaving the simulated render queued. Corrected the isolated backend configuration.
3. Allowed only three seconds for a simulated adapter whose documented completion threshold is six seconds. Replaced with bounded eight-second polling.
4. Added provider-status polling so the canonical workflow observes the provider's terminal state.
5. Expected `saved_explicitly`; the API contract returns `explicitly_saved`. Corrected to the actual durable value.
6. Assumed every successful run has 17 transitions because the prior browser run included failure/recovery events. Replaced the count assumption with an exact set of 15 required semantic events.

The final success evidence was generated only after these verifier defects were corrected. The separate `deliberate_failure` record remains the controlled proof that the final verifier exits nonzero on demand.
