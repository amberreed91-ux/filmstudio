# Emotional Intelligence Roadmap

This roadmap intentionally extends the current green demo state without backend architecture rewrites.

## 1. Emotional Pacing Engine
- Problem: Scenes can be visually coherent but emotionally flat across sequence progression.
- Why users care: Filmmakers need rhythm and emotional escalation, not just shot generation.
- Existing data: `dread_curve`, `ending_impact`, `scene_emotional_flow`, scene durations, review outcomes.
- Smallest implementation: Add an advisory pacing summary per scene transition (`rising`, `flat`, `overloaded`).
- Do not overengineer: No autonomous pacing rewrites, no hidden auto-edits.

## 2. Scene Tension Tracking
- Problem: Tension changes are hard to see while iterating quickly.
- Why users care: They need confidence that suspense or release is intentional.
- Existing data: `audio_tension`, `dread_score`, continuity warnings, scene health.
- Smallest implementation: Add a simple tension trend indicator to Previs + Screening notes.
- Do not overengineer: Avoid fake precision scores beyond available evidence.

## 3. Character Emotional Memory
- Problem: Character tone can drift between scenes without obvious alerts.
- Why users care: Emotional continuity drives audience trust.
- Existing data: character consistency services, memory records, dialogue/voice hints.
- Smallest implementation: Surface "character emotional continuity" advisory flags per scene.
- Do not overengineer: No full personality simulation layer.

## 4. Cinematic Motif Persistence
- Problem: Recurring motifs appear once and disappear without accountability.
- Why users care: Motifs make films feel authored and memorable.
- Existing data: motif/state fields, style signatures, memory references.
- Smallest implementation: Track top motif callbacks and missing expected callbacks.
- Do not overengineer: No symbolic graph expansion until callback utility is proven.

## 5. Co-Director Personality/Taste Evolution
- Problem: Feedback can feel generic even with strong technical analysis.
- Why users care: Distinct voice creates creative trust.
- Existing data: director signature, taste profile support, co-director services.
- Smallest implementation: Add style-aware tone templates for critique/approval/disagreement.
- Do not overengineer: No hidden behavior drift without explicit user setting.

## 6. Viewer Emotional Prediction
- Problem: Teams do not know expected audience feeling per beat.
- Why users care: Story impact is the product, not only render fidelity.
- Existing data: emotional arc, ending impact, review notes.
- Smallest implementation: Add "expected audience feeling" line per key scene.
- Do not overengineer: Avoid black-box pseudo-psychology claims.

## 7. Narrative Rhythm Analysis
- Problem: Timing and cadence can break even when visuals are strong.
- Why users care: Rhythm determines watchability.
- Existing data: scene order, duration estimates, flow score, weak/strong moments.
- Smallest implementation: Highlight abrupt cadence jumps with plain-language guidance.
- Do not overengineer: No automatic reorder of timeline.

## 8. "Why This Shot Matters" Intelligence
- Problem: Shot cards explain what exists, not why it matters.
- Why users care: Directors need intent clarity for decision speed.
- Existing data: prompt packs, narrative progression, co-director notes.
- Smallest implementation: Add one-sentence intent rationale per selected hero shot.
- Do not overengineer: Avoid long essay generation.

## 9. Creative Disagreement System
- Problem: Disagreements are technical; they need creative stakes.
- Why users care: Good films come from tension between options.
- Existing data: agent disagreements, critique/proposal/comparison services.
- Smallest implementation: Reframe disagreement into "Option A vs B" with tradeoff language.
- Do not overengineer: No autonomous arbitration loop.

## 10. Film Identity Drift Detection
- Problem: Film identity can erode across revisions without obvious warning.
- Why users care: Brand/tone coherence is core to final quality.
- Existing data: director signature confidence, style drift issues, memory consistency.
- Smallest implementation: Add drift watch summary at Production + Screening checkpoints.
- Do not overengineer: No hard blocking gates unless user opts in.
