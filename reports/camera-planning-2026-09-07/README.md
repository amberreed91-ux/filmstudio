# Camera planning — September 7, 2026

Previs → Plan the shot → Camera plan → Browse camera presets.

48 provider-neutral presets cover supplied camera moves, lens/focus effects, aerial movement, and additional dialogue/detail setups. Separate view and framing choices and editable text are available. Browsing does not change the shot; Apply sets a session draft. Generate storyboard frame persists camera/framing on that shot and includes them in its canonical render prompt and structured parameters for future takes. Approved versions remain intact; locked shots reject changes.

Drafts are scoped to project, scene and shot. Generated camera plans hydrate from the saved visual plan. Provider failure leaves the saved shot plan intact. Existing storyboard revision behavior may leave an ungenerated new draft after provider failure.

Validation: 26 focused backend tests passed, including route validation, generation persistence, render handoff, replacement, failure, approval and locking. Production frontend build passed. 23 UI/API/planning focused tests passed. New component, hook and API helper lint passed. Browser evaluation could not run: Vite startup hit sandbox listen EPERM, and the escalated retry did not receive approval before it was stopped. No screenshots or browser interaction checks were completed.

Limitations: text catalog, not photographic or animated preset previews. Start/end frame and drawn path editor are not included. Camera direction expresses the requested shot; generation fidelity depends on the provider. Backend must load the updated routes before the catalog endpoint is available.
