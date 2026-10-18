# Phase 2 Design Note — single-shot render filter + cost display (DESIGN ONLY)

Date: 2026-10-18. Mission gate item 6. Nothing below is implemented; this note
answers the three report questions and sketches the test plan for owner
approval. Phase 1 (prompt Rebuild + re-approve) is implemented separately.

## 1. Does the dry-run routing call contact Runway, and is it billed?

**It contacts Runway and it is not billed** — with one caveat about reference
bytes below. Verified read-only against current code (no live calls made):

- `submit_runway_router_video_render(..., dry_run=True)` sets
  `body["dryRun"] = True` (`studio-backend/app/services/providers/runway_router_provider.py:619,805`)
  and POSTs to the provider. The dry-run branch returns before polling:
  "Dry run: routing decision only. No task, no output, no billing." (`:1398`).
  `parse_runway_router_response` requires `dryRun is True` **and no task id**
  on a dry run — an id raises (`:999`).
- In-repo evidence agrees: `docs/runway_model_router/FINAL_REPORT_20260928.md`
  ("dry-run 404s create no task; account creditBalance unchanged") and
  `reports/studio-readiness-audit-2026-10-14/R4.3B-live-provider-acceptance-safety-decision.md`
  §5–6 ("runs the full routing pipeline and returns the decision and an
  ESTIMATED cost without creating a task, generating, or billing").
- Local estimate path is consistent: `generation_cost_gate.estimate_shot`
  returns `estimated: False` for `runway_router` — "only estimable from the
  Router's non-billable advisory dry-run response; it is not an authorization
  for the live call" (`generation_cost_gate.py`). The UI must never invent
  Router pricing; cost display for Router shots may only show the advisory
  `estimatedCost.credits` from a real dry-run response (or "estimate
  unavailable").
- **Caveat (Depth-2 adapter path):** `adapters/__init__.py:1806` runs
  ephemeral reference materialization (`POST /v1/uploads` + multipart) *before*
  the dry-run flag takes effect, and the non-protected adapter path proceeds
  to a **live** `_run_sync()` after the dry-run preflight — "there is no
  adapter mode that performs only the dry run and stops"
  (R4.3B §6–7). So: a bare Depth-1 `dry_run=True` provider call is
  contact-without-billing; invoking the full adapter to "probe" is a live
  submission path and must never be used for estimates. Phase 2 cost display
  must call the Depth-1 dry-run function only, never the adapter submit.

## 2. How a filtered render inherits the package's frozen contract

The "frozen contract" is per-shot, not a package blob, so filtering is safe by
construction **if the filter applies after the approved-version pin**:

- `scene_render_inputs` (`storyboard_blueprint_service.py:1167`) pins
  `blueprint.approved_version_id`, refuses unless current == approved, validates
  every shot (`_validate_shot_renderable`), and builds each shot's inputs with
  `storyboard_render_inputs(shot)` (frozen `render_contract` snapshot) plus the
  D4 rule that Runway `promptText` is *always* `approved_prompt_for_shot(shot)`
  (fails closed, `:1029`).
- Proposed filter design: `scene_render_inputs(project_id, scene_id,
  only_shot_ids=[...])` — same pin, same per-shot validation, same builder,
  then keep only the requested `shot_id`s (unknown ids raise, empty selection
  raises). The single shot's payload is then byte-identical to that shot's
  payload in the whole-package build: same approved version, same frozen
  `render_contract`, same approved image prompt, same seed/model. No new
  contract type, no re-derivation, no draft-version involvement (drafts still
  refuse, unchanged).
- Cost display for the filtered request runs `estimate_batch` over the
  filtered subset only, so the total drops to the selected shots; Router rows
  stay `estimated: False` until a Depth-1 dry-run advisory arrives.

## 3. Test plan (fake provider adapter; no live calls)

Location: new `studio-backend/tests/test_single_shot_render_filter.py`.
Patterns to reuse: recording transport doubles from
`test_generation_contract_remediation.py:1213` (`calls[0][1]["dryRun"] is True`)
and `test_runway_router_projection_integration.py:1014`, plus the
`monkeypatch.setattr("app.services.render.get_adapter", ...)` fake-adapter
style in `test_render_pipeline_hardening.py`. Socket-block (`R43K_SOCKET_ONLY`)
stays on; all provider HTTP is a recording fake.

1. **One-shot filter submits exactly one POST.** Approved 5-shot board;
   `scene_render_inputs(..., only_shot_ids=[shot_3])` → submit through the
   fake adapter → assert the transport saw exactly 1 submit POST and its
   `promptText` equals `approved_prompt_for_shot` for shot 3.
2. **Whole package submits five.** Same board, no filter → exactly 5 submit
   POSTs, one per `shot_id`, in shot-number order.
3. **Filter inherits the frozen contract byte-identically.** Filtered shot-3
   payload == shot-3 payload extracted from the full-package build
   (promptText, references, seed, model, duration). Unknown `shot_id` raises;
   empty selection raises; draft (current != approved) still refuses.
4. **Dry-run billing parity.** Fake transport returns `{"dryRun": True, ...,
   "estimatedCost": {"credits": N}}` with no `id` → assert estimate surfaces
   N credits, no task created, no poll calls, no job row billed. A dry-run
   response carrying an `id` raises (parser rule, `:999`).
5. **No invented pricing.** `estimate_batch` over a Router subset without a
   dry-run advisory returns `estimated: False` and the UI total shows
   "estimate unavailable", never a number.

## Open approval questions for the owner

- Is per-shot filtering allowed on the approved version only (yes, per §2), or
  should drafts also render single shots (not recommended — drafts refuse today)?
- Should the filtered render reuse the package's render-job group for history,
  or mint standalone jobs (recommend standalone with a `filtered_from` link)?
