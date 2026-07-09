# Taste Memory v1 Plan

## 1. Purpose

Taste Memory v1 is a bounded advisory memory of filmmaker preferences inferred from repeated choices, not a personality simulator.

It should remember:
- accepted tradeoffs
- ignored disagreements
- repeated revision emphasis choices
- preferred emotional pacing
- preferred clarity vs ambiguity
- visual motif tolerance
- style drift tolerance
- whether the creator tends to favor emotional residue or structural clarity

It should not:
- override the user
- make autonomous decisions
- score taste
- become a personality clone
- overfit from one choice
- pretend certainty

Working principle:
- infer tendencies slowly
- present them softly
- keep them reversible

## 2. Signals

Use only explicit or strongly implied signals.

Candidate signals:
- Revision Emphasis selection
- `Approve Cut`
- `Request Revision`
- `Compare Revision`
- whether disagreement appears and the user proceeds with or against it
- repeated room navigation patterns
- manual edit notes (future, if available)

### Signal strength model

Weak:
- single emphasis toggle click
- one-off room navigation
- single compare action without outcome

Medium:
- repeated emphasis choice across multiple revision comparisons
- repeated `Request Revision` after same disagreement pattern
- repeated “compare then choose same direction” behavior

Strong:
- recurring emphasis + matching action outcome (`Approve Cut` or `Request Revision`) across several sessions/revisions
- sustained pattern where disagreement appears and user consistently chooses one tradeoff direction

Interpretation rule:
- one event never defines taste
- patterns over time define advisory tendencies

## 3. Memory Shape (Draft)

```json
{
  "profile_id": "local_creator_profile",
  "preference_axes": {
    "emotional_residue_vs_structural_clarity": {
      "current_tendency": "emotional_residue",
      "confidence_label": "emerging",
      "last_observed": "2026-05-22T00:00:00Z"
    },
    "intimacy_vs_scope": {
      "current_tendency": "undetermined",
      "confidence_label": "emerging"
    },
    "ambiguity_vs_exposition": {
      "current_tendency": "undetermined",
      "confidence_label": "emerging"
    },
    "visual_consistency_vs_experimentation": {
      "current_tendency": "undetermined",
      "confidence_label": "emerging"
    },
    "pacing_patience": {
      "current_tendency": "undetermined",
      "confidence_label": "emerging"
    }
  },
  "evidence_log": [
    {
      "timestamp": "2026-05-22T00:00:00Z",
      "signal": "revision_emphasis_selected",
      "value": "emotional_residue",
      "strength": "weak",
      "context": {
        "project_id": "demo_studio_cinematic_001",
        "surface": "screening_comparison"
      }
    }
  ],
  "confidence_level": "emerging",
  "last_updated": "2026-05-22T00:00:00Z",
  "advisory_notes": [
    "You tend to preserve emotional carryover when choosing between revisions."
  ]
}
```

Confidence labels are language-only:
- `emerging`
- `consistent`
- `strong`

No percentages in v1.

## 4. Guardrails

Hard rules:
- never use taste memory to block workflow actions
- never present preferences as permanent
- always phrase as tendency language (`you tend to...`)
- avoid certainty language (`you always...`, `this is your style`)
- allow reset/forget in later versions
- keep visibility quiet but legible

Behavior rules:
- disagreement remains optional advisory, never enforcement
- taste memory modifies wording, not system authority
- uncertain states should default to neutral copy

## 5. First Implementation Candidate

Question:
- frontend-only session memory
- local profile service (persistent backend profile)

### Option A: Frontend-only session memory
Pros:
- lowest risk
- no storage/schema/API changes
- easy rollback
- ideal for validating UX language

Cons:
- no cross-session continuity
- limited long-term trend fidelity

### Option B: Local profile service
Pros:
- persistent behavior memory
- stronger trend detection over time

Cons:
- introduces storage/API contracts early
- higher risk of overreach before UX is proven

### Recommendation for v1
Use **frontend-only session memory** first.

Reason:
- validates advisory behavior safely
- proves user value before persistence complexity
- maintains current architecture stability

## 6. UI Surfaces

Good initial surfaces:
- Screening revision comparison
- Co-Director notes (short tendency-aware phrasing)
- Previs guidance (light wording shifts)
- future profile page (explicit, optional visibility)

Surfaces to avoid:
- every card
- every room header
- blocking decision gate
- provider router or execution systems

## 7. First Magic Moment

"The Studio notices you keep choosing emotional residue over structural clarity and adjusts its wording accordingly."

Why it matters:
- user feels seen
- guidance feels collaborative
- no claim of automation or hidden scoring

## 8. Final Recommendation Summary

1. Recommended v1 approach:
- frontend-only session memory with advisory wording shifts only

2. First preference axis to track:
- emotional residue vs structural clarity

3. Strongest signal:
- repeated emphasis selection paired with downstream action (`Approve Cut` or `Request Revision`)

4. Biggest risk:
- premature certainty from sparse signals (overfitting from one or two actions)

5. Smallest shippable feature:
- session-scoped tendency note in Screening that adapts co-director phrasing after repeated emphasis selections

6. Must remain advisory-only:
- disagreement logic
- decision gate behavior
- route selection
- render/provider behavior
- workflow execution authority
