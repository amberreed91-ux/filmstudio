# Generated character casting — September 5, 2026

Generated casting is integrated into The Page’s existing **Lock character looks** step, after saving profiles and before storyboarding. The creator can generate three portraits, compare them, select one, and explicitly approve its appearance snapshot. Uploading a portrait and optional body reference remain supported. Generation never chooses a portrait, locks a character, edits a physical description, or changes existing footage.

The production order remains: references and bibles → script → character profiles → cast and lock appearances → storyboard / Previs → render → Theatre review and finalization.

## Behavior and persistence

- One explicit request creates a three-option set from the saved appearance plus optional casting direction. Direction makes a new set of faces; this is not identity-preserving image editing. Change authoritative physical traits in Character profiles first.
- Generation uses the configured DashScope Qwen image provider. Three separate portrait requests respect the model’s one-image-per-request contract. Portraits use 1104 × 1472 output. Provider prompt rewriting is disabled. Oversized casting descriptions are rejected for revision rather than sliced locally.
- Typed API: `POST /api/f51/studio/projects/{project_id}/characters/{character_id}/look/casting`, returning HTTP 202 and `CharacterLook`. Requests require the current profile revision and a UUID. Routes invoke services; services own generation, provider access and persistence.
- Job metadata, original prompt, seeds, profile fingerprint, statuses and downloaded image URLs are saved on the scoped character. Unique local files survive the provider’s temporary URL expiration. Existing continuity metadata is preserved through atomic revision checks.
- Workers claim requests once. Duplicate submissions, competing workers, refreshes and uncertain browser responses cannot replay the same accepted request. No automatic paid retry is performed. Completed portraits survive a later failure; the creator can explicitly request another set.
- Polls ignore stale scope responses, preserve selected options and stop after repeated connection failures or their time limit. A process interruption cannot resume a paid request automatically: unfinished sets become failed or partial at their ten-minute deadline; saved portraits remain available.
- Generation from an earlier saved appearance is labeled for renewed review. Completion cannot overwrite a subsequently approved reference. Only explicit approval feeds the chosen reference into supported render-provider conditioning. The existing storyboard image generator still uses saved appearance text; reviewing likeness remains necessary.

## Validation and activation

- 52 isolated backend tests passed across casting, appearance approval and project-access boundaries. This includes 17 casting tests covering durable candidates, exact approval handoff, parallel worker idempotency, locked/stale/foreign guards, partial results, profile changes, invalid media, storage failures, interruption expiry, API contracts and provider requests. After the final error-message and cleanup adjustment, all 17 casting tests passed again.
- All 703 frontend tests passed; production TypeScript/Vite build passed.
- Targeted lint passed with no new errors. Existing WritersRoom dependency warnings remain.
- Thirteen browser checks passed on the real Vite application using fixture reads and intercepted writes: accepted-submit transport-error recovery, refresh, character switching while polling, incremental options, retained selection, explicit lock/reopen, partial/failed sets, prior-profile warning, upload, unsaved draft guard and missing-description guard. No browser page errors. Desktop and 390-pixel mobile screenshots show no horizontal overflow.
- Backend restarted after confirming there were no active render jobs. Live health is healthy, database is OK, the new typed 202 route appears in OpenAPI, and the existing project’s six characters return the casting status contract. No casting jobs were started in the real project.
- The image-provider key is configured. Provider requests and downloads were mocked for verification; no paid image generation was performed. Live provider acceptance, credit balance and output likeness have not been measured by this change.

Independent design review: **PASS** on the first review, with fresh desktop and mobile browser inspection. [Evaluation record](INDEPENDENT-EVALUATION.md). This was an independent same-provider review because no alternate-provider model was available.

Browser details: [browser-verification.json](browser-verification.json). UI implementation notes: [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Screenshots

- [Desktop casting options](casting-desktop-options.png)
- [Mobile casting options](casting-mobile-options.png)
- [Mobile selected portrait](casting-mobile-selected.png)
- [Partial set and earlier profile](casting-desktop-partial-stale.png)
- [Locked appearance](casting-mobile-locked.png)

These are verification fixtures using existing local character frames, not newly generated casting results.

## Provider contract sources

The provider’s current [Qwen-Image API reference](https://www.alibabacloud.com/help/en/model-studio/qwen-image-api) documents one image per Qwen Image Max call, supported portrait resolution, disabling prompt rewriting, and temporary image URLs. The [Base URL overview](https://www.alibabacloud.com/help/en/model-studio/base-url) confirms the existing shared DashScope domains remain available. No provider migration was needed for this feature.
