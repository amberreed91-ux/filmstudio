# Director Taste Profile v1 Plan

## Purpose
Define a safe evolution path from session-scoped Taste Memory into an explicit Director Taste Profile without changing runtime behavior, storage, or APIs in v1 planning.

## 1) What The Profile Remembers
The profile should capture bounded creative preference signals from observed choices, not inferred personality traits.

- Revision emphasis choices over time (`emotional_residue` vs `structural_clarity`)
- Accepted vs rejected creative disagreement moments
- Preferred pacing posture (linger vs tighten)
- Emotional residue vs structural clarity tendency
- Tolerance for ambiguity vs explicitness
- Style drift tolerance (strict consistency vs selective experimentation)
- Recurring motif preferences (what the creator repeatedly preserves)

### Signal Strength Model (language-only)
- Weak: one-off click or single revision decision
- Medium: repeated behavior across one session
- Strong: repeated behavior across multiple projects/sessions (future only)

## 2) What It Must Not Do
The profile is advisory and collaborative. It must not become authoritative or intrusive.

- Must not override creator decisions
- Must not pretend certainty from sparse evidence
- Must not produce permanent personality claims
- Must not score taste numerically
- Must not become creepy or over-personalized
- Must not trigger autonomous edits or recuts

## 3) Explicit User Controls
Director Taste must be user-governed and reversible from day one.

- View profile summary (what signals were observed)
- Reset profile
- Forget profile (full wipe)
- Disable taste learning entirely
- Force session-only mode

### Control Requirements
- Controls are always visible where taste is shown
- Any persistent mode requires explicit opt-in
- Reset/forget actions must be immediate and confirmed in plain language

## 4) First Safe Implementation Comparison

### A. Session-only profile
Pros:
- Safest privacy posture
- No persistence risk
- Easy to reason about and test
Cons:
- No longitudinal learning
- Resets on refresh/session end

### B. Local browser profile
Pros:
- Lightweight continuity across sessions on one machine
- No backend changes
Cons:
- Fragile across devices
- Harder trust story unless reset/forget is prominent

### C. Backend project-level profile
Pros:
- Shared across collaborators in project context
- Better continuity per film
Cons:
- Requires storage/API contract work
- Higher consent and governance burden

### D. User-level persistent profile
Pros:
- Strongest personalization potential
Cons:
- Highest privacy and safety risk
- Requires full consent, controls, auditability, and retention policy

### Recommended Safest v1
**Session-only profile** (no persistence) remains the safest v1.

## 5) UI Surfaces
Where taste should appear (advisory context only):
- Screening (revision comparison + co-director notes)
- Previs (shot intent guidance)
- Future dedicated Director Profile room (optional later)

Where taste should not appear:
- Provider router
- Decision gate as a blocking factor
- Hard execution controls

## 6) Language Rules
Tone must remain cautious, collaborative, and non-authoritative.

### Use
- "You seem to be leaning toward..."
- "Across this session, the Studio noticed..."
- "This may reflect your current creative preference..."

### Avoid
- "You always..."
- "Your style is..."
- "The correct choice is..."
- Any deterministic identity claims

## 7) First Magic Moment
"The Studio remembers that you keep choosing emotional residue over structural clarity and adjusts its revision notes accordingly."

Why it works:
- Feels personally relevant
- Demonstrates memory without overreach
- Stays advisory and reversible

## Guardrails Before Any Persistence Phase
Do not move beyond session-only unless all are true:
- Explicit opt-in exists
- Reset + forget are one-click and immediate
- Learning can be disabled globally
- Explanations show *why* the system inferred a tendency
- No numeric taste scoring appears anywhere

## Final Report

### Recommended v1 storage scope
Session-only (in-memory UI state), non-persistent.

### First profile axis
Emotional residue vs structural clarity.

### Biggest safety risk
Overstating weak signals as stable identity (creepy/deterministic personalization).

### Smallest shippable feature
Session-scoped "Emerging Director Taste" read that adjusts wording in Screening revision notes based on repeated emphasis selections.

### What must remain user-controlled
- Whether taste learning is active
- Whether profile memory is retained at all
- Ability to reset/forget instantly
- Visibility into what signals were used
