# Creative Decision Memory v1 Plan

## 1. Purpose
Creative Decision Memory should preserve creative reasoning in a transparent, consent-driven way. The goal is to remember meaningful editorial intent (why a choice was made), not to silently profile the filmmaker.

Guiding principle: memory must support creative collaboration and recall, never covert judgment.

## 2. Candidate Memories
Potential memory candidates (only when explicitly saved):
- Chosen revision emphasis (`emotional_residue` vs `structural_clarity`)
- Cut decision notes from the session journal
- Accepted disagreement moments
- Rejected disagreement moments
- Final package decision rationale
- Pacing preference (when explicitly stated)
- Emotional residue preference (when explicitly stated)
- Structural clarity preference (when explicitly stated)

## 3. What Should NOT Be Remembered
The system should not persist:
- Every click or transient UI interaction
- Every temporary mood swing or one-off toggle
- Private/raw notes without explicit save consent
- Permanent personality claims
- Weak one-off signals without decision context

## 4. Consent Model
Before anything becomes persistent:
- Show exactly what will be saved
- Allow user edit before save
- Allow discard
- Allow session-only mode
- Allow reset/forget after save

Consent must be specific, reversible, and visible at the moment of save.

## 5. Memory Shape
Draft project-level JSON shape:

```json
{
  "project_id": "demo_studio_cinematic_001",
  "decision_id": "dec_2026_05_23_001",
  "decision_type": "revision_emphasis",
  "user_note": "I chose emotional residue because the pause feels more honest.",
  "inferred_tradeoff": "emotion_over_clarity",
  "source_context": {
    "room": "screening",
    "revision_emphasis": "emotional_residue",
    "comparison_context": "revision_a_vs_revision_b",
    "decision_gate_state": "ready"
  },
  "saved_at": "2026-05-23T00:00:00Z",
  "editable": true,
  "forgettable": true
}
```

Notes:
- `inferred_tradeoff` should remain language-level and bounded (no numeric scoring).
- `source_context` should include only creative-decision context, not broad behavioral telemetry.

## 6. First Safe Implementation
Recommended v1 behavior:
- Add explicit action: `Save this decision to project memory`
- Never auto-save from toggles, prompts, or passive observation
- Keep scope project-level first (not user/global profile)

Why this is safest:
- Constrains blast radius
- Keeps memory contextual to a specific film
- Avoids cross-project identity claims too early

## 7. UI Surfaces
Initial and future surfaces for explicit save/use:
- Screening journal (save a note as decision memory)
- Revision comparison (save accepted tradeoff reasoning)
- Final package summary (save final editorial rationale)
- Future Director Profile room (view/edit/forget saved decisions)

## 8. Anti-Patterns
Avoid:
- Creepy surveillance framing
- Taste scoring or percentile ranking
- Automatic profiling from passive behavior
- Irreversible memory records
- Overconfident identity claims (e.g., "you are this kind of director")

## Final Report

### 1. Recommended v1 persistence scope
Project-level creative decision memory only, explicitly saved by the user.

### 2. First memory type to save
Cut decision note with selected revision emphasis and explicit tradeoff rationale.

### 3. Biggest safety risk
Silent drift from explicit creative memory into implicit behavioral profiling.

### 4. Smallest shippable version
Single explicit save action in Screening journal that writes one editable/forgettable project decision record.

### 5. What must require explicit user action
Any persistent save of notes, tradeoffs, or inferred preferences; any non-session retention; any profile-level aggregation.
