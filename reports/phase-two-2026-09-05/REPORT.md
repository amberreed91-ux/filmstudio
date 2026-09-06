# Phase Two: access security, prompt budgets, and film coherence

This continues the completed audit without repeating it. Prior worktree edits and all five previous repairs remain. Tests and generation run in disposable backend copies to keep source-relative legacy stores away from the user's real projects. No production database migration or backend restart was performed.

## Project access repair

The root problem was that project IDs selected data without establishing an authenticated owner. Authentication existed separately, used process-local user/session state, and was not a mandatory boundary for project routes or mounted generated media. A frontend gate alone could not fix this.

The new ASGI access boundary authenticates before dispatch and delegates ownership decisions to ProjectAccessService. Migration 60 adds durable users and immutable project-owner records. Migration 61 makes needs_review durable and preserves job metadata; it rebuilds the render job table transactionally, retaining its rows and standard indexes. Project creation derives the owner from authenticated request context; a payload cannot claim an existing ID or change ownership. Sessions survive restart and logout revokes them. Lists and overview return only owned projects. Scene, shot, character, project metadata, asset, and nested generation selectors are checked against project ownership. Globally addressed IDs must resolve to owned resources. Mounted media requires exact registered URL ownership; a filename is not an ownership credential. Unknown/global scopes fail closed. Administrative operations remain denied in authenticated mode.

The secure default is `STUDIO_ACCESS_MODE=authenticated`. Explicit local mode requires a loopback peer, host, origin, and forwarded client chain and is disabled under production APP_ENV. Development launchers bind loopback and opt into local mode. Vite forwards the original peer address; its backend supervisor also requires a loopback connection. The new frontend session gate provides registration/sign-in through secure session cookies, with no token persistence in localStorage.

### Compatibility and rollout limits

- Existing projects have no inferred owner. They remain available in explicit local mode; authenticated deployment requires deliberate administrator assignment of existing projects to registered users. The migration intentionally does not let the first registrant claim them.
- Legacy WebSockets broadcast all projects. Authenticated mode closes them until both subscriptions and broadcasts are scoped. HTTP polling remains available.
- Unscoped/global APIs are denied even if a caller adds an owned project ID. This is deliberate protection, but those global workflows need project-scoped contracts before becoming available to authenticated users. Full multi-user product parity is not claimed.
- This validates the identified ownership boundary, not a certification of every possible application security issue.

## Prompt truncation findings

| Stage | Before | After on video generation path |
|---|---|---|
| Slotted builder | Character/action/environment/camera/lighting budgets 210/110/100/70/60, plus reserve 32: 582 before glue, exceeding inherited 512 ceiling | Lossless collection during create_job; final allocator owns provider budget |
| Per-slot helpers | Raw character slices and ellipses could sever appearance, wardrobe, actor bindings, or negation | Complete fact text collected |
| Reassembly/final render | Late slots and later injected continuity lost to trailing cut | Required facts admitted together or job enters needs_review before submission |
| Department/knowledge context | Independent 92/180/220-character compaction could remove source meaning upstream | Collection mode retains text for final budgeting |
| Intent/continuity prepend | Context could displace tail of creator text | Source facts retained and omission report persisted |
| Negative channel | Default artifact exclusions came first; explicit creator terms could fall outside 500 characters | Explicit exclusions first, whole terms; unsupported/oversized explicit constraints block submission |
| Adapter reference transformation | Could add text after application budgeting | Final payload validation before paid POST; exact outgoing prompt recorded |

The 512-character ceiling was an application inheritance, not a verified universal provider maximum. The policy distinguishes verified Alibaba limits from conservative application ceilings:

- HappyHorse: 5,000 weighted character units (Chinese characters count twice), following [text-to-video](https://help.aliyun.com/en/model-studio/happyhorse-text-to-video-api-reference) and [reference-to-video](https://help.aliyun.com/en/model-studio/happyhorse-reference-to-video-api-reference) documentation.
- Wan 2.5/2.6: 1,500 characters; Wan 2.1/2.2: 800, with separate negative-channel budgeting. [Alibaba documentation](https://help.aliyun.com/en/model-studio/text-to-video-api-reference).
- Runway and unknown OpenRouter models retain a conservative application ceiling of 512 where the selected model maximum is unverified. The explicit OpenRouter model `alibaba/happyhorse-1.1` uses the upstream HappyHorse 5,000-unit ceiling: the [official OpenRouter schema](https://openrouter.ai/openapi.json) declares no additional prompt maxLength. This is an explicitly recorded transport inference, not a universal OpenRouter maximum; live benchmark acceptance validates only the lengths actually submitted. The selected model ID is resolved before budgeting. The schema evidence is saved in `openrouter-video-schema.json`.

Priority order: provider requirements, identity, continuity, shot intent, cinematography, environment, enrichment, optional detail. The first four are required. Deduplication keeps the strongest priority; stable fact IDs make optional admission deterministic. Facts are never cut midway. Unstructured creator prose is conservatively required rather than guessed to be disposable. Short prompts retain their original order when no degradation is necessary. Overflow preserves the unabridged text and records why generation cannot proceed.

`prompt_budget` metadata preserves source facts, limits and their provenance, included/omitted IDs, policy version, and required overflow. `negative_prompt_budget` records required exclusions, defaults omitted, support, and final text. Adapters record the final transformed provider prompt.

### Measured preservation

`prompt-preservation.json` contains reproducible before/after text and source fields. The legacy fixture was 480 characters after clipping and lost its lighting sentinel. The new provider-aware result is 568 characters, below HappyHorse's verified ceiling, with all five checked anchors intact: wardrobe, prop, location, lens, and lighting. This is five preserved anchors versus four before, on this fixture only.

All 25 tested filmmaking fields survive oversized optional decoration, including identity, appearance, wardrobe, injuries, props, location, weather, time, lighting, blocking, screen direction, camera/lens/composition/movement, emotion, continuity, story facts, negative constraints, and provider instructions. Permutations produce the same admission result; oversized mandatory content blocks instead of silently losing facts. These tests establish software preservation, not model compliance or artistic quality.

Standalone legacy previs/storyboard display builders and adherence preview helpers still have their original compact layouts. The video create_job boundary collects the participating helpers losslessly. Source selection (which scene, shot beat, memory atoms, or cast members are retrieved) remains distinct from budget allocation; this phase does not assert that every unselected source fact is discovered. Still-image prompt paths are not covered by the video-provider payload guarantees.

## Changed areas and tests

Backend: auth and auth routes; config/main; SQLite migration and access queries; request access context/middleware/service; project creation ownership; prompt assembly context and models; whole-fact budgeting; render, slot, department and enrichment helpers; adapter payload validation; conftest local test mode. Frontend: session hook/gate/App wrapper, Vite proxy and host, backend supervisor. Launcher: loopback/local settings. Benchmark: fixture, runner, immutable run manifest and expectations.

New tests: `test_project_access_boundary.py`, `test_prompt_budget_adversarial.py`, `test_film_coherence_harness.py`. Original tests were not weakened. Regression-discovered retry delimiter and camera default differences were fixed in implementation. An intermediate test-only APP_ENV override accidentally enabled mock vision; it was removed, preserving real-provider failure behavior.

Verification logs and benchmark results follow.


## Real benchmark execution

The Returned Key uses two fictional characters, a fixed master reference, six four-second shot requests, fixed seeds, one workshop, a brass-key handoff, and a dusk-to-night transition. OpenRouter model discovery and credentials were checked live. All jobs were preflighted before the first paid POST. The real provider is OpenRouter, model alibaba/happyhorse-1.1, 720p, 16:9, requested audio disabled.

Retained attempts 01–04 are setup/preflight evidence, not generated takes. Attempt 01 found absent cast records prevented reference attachment. Attempt 02 exposed required prompt overflow and the old SQLite status constraint. Attempt 03 records all six durable blocked jobs under the inherited 512-character policy. Attempt 04 reached reference serialization and exposed a harness-only Pydantic-to-JSON issue before any submission. Those issues were corrected before the first paid request. Attempt 05 is the first actual video generation run; no generated shot has been retried or selected from alternatives.

The model-specific policy change is based on the official schema and upstream documentation, not on aesthetic results. The reference and requested shot directions did not change. Initial assembled prompts contain 744–832 characters. Exact provider prompts and bodies (reference bytes represented by a hash), source context, seeds, registered reference, task IDs, costs, output hashes, and expectations are retained in `real-run-05/manifest.json`.

The reference still's camera-near bandage appears to be on Nina's right wrist despite the requested left wrist. That is a fixture limitation. Anatomical laterality should be reviewed by a person; do not assign a reference-inherited error only to the video model.

Source-content findings are retained rather than optimized: injected identity prose includes internal phrases such as “not yet verified” and “human review needed”; shot 2 also receives “Environment identity: Jules (jules).” Whole-fact preservation cannot make an incorrectly selected source fact correct. This is a baseline context-quality issue, distinct from truncation.


## Final software verification

- Backend: **3,428 passed, 10 skipped, zero failures**, 269.50 seconds (`backend-final.log`). This is 55 additional passing tests over the preserved 3,373 baseline. The verified copy's application Python files match the working tree byte for byte.
- Frontend: **680 passed**, 76 files (`frontend-final.log`).
- Production build: passed; existing large Three.js bundle warning remains (`production-build.log`).
- Browser: real registration/sign-in, owned-project creation/read, logout, rejected post-logout read, and return to sign-in; zero page errors (`browser-final.log`). API traffic was routed to the isolated real backend, not mocked.
- Runtime: oversized render creation returned HTTP 200 with needs_review and budget evidence; owned retrieval returned 200, anonymous retrieval 401 (`runtime-budget.log`).
- Restart: the session, blocked job, and prompt-budget metadata survived a real isolated backend restart (`restart-check.log`).
- Targeted access/prompt/harness suite: 55 passed. SQLite/prompt/harness follow-up: 45 passed. Migration preservation and the original custom-schema foreign-key test pass without weakening their assertions.

The first final browser attempt raced server startup and received connection refused; it was rerun after readiness and passed. An intermediate full run caught the custom-schema metadata-column issue; the write path was corrected and the entire suite rerun green.


## Initial film-coherence baseline

**Real video generation executed: six completed clips, one paid submission each, no retries, no selected alternate takes.** Provider-reported video cost totals **$2.964**, compared with the preflight estimate of $2.3712. The generated master still is separate from that video cost. All original outputs remain intact. `real-run-05/baseline-cut.mp4` is a 24.736-second stream-copy concatenation in fixture order, with no editorial optimization. `review-observations.json` and the manifest contain all nine film-level answers and per-expectation evidence.

| Shot | Observed baseline |
|---|---|
| 1: establish | Faces, clothes, workshop, key/mug, and dusk/amber light match the reference in sampled frames. Wrist laterality remains a reference ambiguity. |
| 2: Nina close-up | Nina and the room remain recognizable; hesitation is visible. Starts wide and moves toward a medium view rather than delivering the requested medium close-up. |
| 3: Jules reverse | Identity and geography persist. Again starts wide, then moves toward Jules, weakening the intended close-up/reverse cut. Hope is uncertain from sampled performance. |
| 4: key insert | Nina moves the key left-to-right toward Jules, with the mug stationary. Stays a wide two-shot instead of the requested table insert; precise key shape is difficult to inspect. |
| 5: aftermath | Nina releases her posture, but the key resets to the table beside her. Jules does not hold it as requested. This breaks the handoff's story state. |
| 6: later night | Faces and workshop persist. Window remains blue like dusk, so the requested time progression is absent. The key remains near Nina; a small object in Jules's hand may duplicate rather than cleanly transfer the prop. Trust is not clearly established. |

The clips share a recognizable visual world. They do **not** yet demonstrate dependable sequential storytelling: coverage repeatedly falls back to the reference composition, and changes in prop ownership and time are not carried forward reliably. This is the unoptimized baseline, not a claim that the pipeline is incapable of improvement. No changes were made to improve generated outcomes during this run.

Review method: extracted frames at 2 fps for most clips, 4 fps for the handoff, plus a full-resolution first frame for the final prop/window check. Full originals and the straight cut are retained for human playback. This does not replace exhaustive temporal/artifact, audio, or audience evaluation. Reference-image conformity and visual sameness do not establish correct screenplay execution.

## Remaining limits

- Changes are verified in isolated runtimes. The original backend was not restarted and the real project database was not migrated; deployment requires a controlled restart applying migrations 60–61.
- Existing project ownership must be assigned deliberately for authenticated deployment. Explicit loopback local mode preserves the current developer workflow.
- Authenticated global endpoints and unscoped WebSockets remain closed until they receive project-scoped contracts.
- Standalone still-image/previs compact builders and source-retrieval/identity/environment mistakes remain outside the video-budget guarantee. Budget preservation now exposes some incorrect upstream context instead of hiding it.
- The OpenRouter HappyHorse policy uses the upstream model ceiling; live success verifies 744–832-character prompts in this benchmark, not every possible model/length/language combination.
- Visual weaknesses are recorded, not optimized: coverage, prop state, time progression, and reference laterality need subsequent focused work.

The assembled cut loaded at 1280×720 in a real browser, played, and sought near the end without media/page errors (`cut-playback.log`). All six original file hashes, final prompts against preserved requests, model IDs, reference injection, and observation records were checked (`artifact-verification.json`). The final harness also pins the priced model against unrelated shell overrides; its prepare/block regression tests pass (`harness-final.log`).
