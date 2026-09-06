# The Returned Key: controlled continuity benchmark

Six four-second shots, two fictional characters, one workshop, one prop handoff, and a dusk-to-night transition. Each shot has concrete expectations and review labels. There are no aesthetic scores and no automatic retries, selection, or prompt optimization.

Use a disposable backend checkout, with the existing virtualenv interpreter. Do not run from the production backend directory: some application services still use source-relative stores. Set `OPENROUTER_API_KEY` in the environment without printing it. The runner redirects the principal stores into the run output directory and uses the real RenderService and adapter. It never selects a simulated provider.

Prepare only:

```sh
python benchmarks/film_coherence/run.py --reference /absolute/master.png --output /absolute/new-run
```

Real submission (new output directory required):

```sh
python benchmarks/film_coherence/run.py --reference /absolute/master.png --output /absolute/new-real-run --execute --max-cost-usd 3
```

Model availability and current pricing are checked before submission. The cost ceiling gates the estimate for the requested six clips; it is not an account spending limit or a guarantee of final vendor billing. Every shot is preflighted before any paid POST. Existing run directories cannot be overwritten. After a provider timeout/interruption, reconcile its task ID before considering any further run.

The manifest preserves fixture/source context, requested and assembled prompts, prompt-budget evidence, provider/model, parameters/seeds, reference path and SHA-256, provider request information, task IDs, accessible downloaded outputs and their SHA-256, and shot expectations. A prepared or blocked manifest never describes nonexistent outputs as generated.

Review each entire clip, then adjacent cuts. Record `preserved`, `violated`, `unclear`, or `not_visible` with a timestamp/frame and concrete observation. Keep `not_generated` for unavailable clips. Answer all nine film-level questions only where visible evidence supports an answer. Contact sheets are useful evidence but cannot establish motion, a prop transfer, or emotional progression alone.

## Initial run: 2026-09-05

The first paid run is `reports/phase-two-2026-09-05/real-run-05/manifest.json`: six real OpenRouter HappyHorse clips completed, one submission per shot, total provider-reported video cost $2.964. The 24.736-second `baseline-cut.mp4` concatenates all outputs in fixture order without editorial optimization. See the report and per-shot observations for the sampled visual review.

Preflight attempts 01–04 are retained: missing cast/reference attachment, required-context overflow under the inherited budget, SQLite needs_review persistence, and harness serialization. None submitted a paid video. Official OpenRouter schema evidence supported an explicit HappyHorse model budget using the upstream limit; actual 744–832-character submissions then succeeded. No generated take was retried or selected.

Initial findings: faces, wardrobe and room persist; requested close-ups/insert tend to restart wide; the key resets after its handoff; the final window does not progress to night. The master still also has ambiguous wrist laterality. These are preserved baseline findings, not optimized outcomes.
