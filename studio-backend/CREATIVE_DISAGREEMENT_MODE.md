# Creative Disagreement Mode

## Purpose

Creative disagreement matters because films are shaped by tension, not only consensus. A collaborator who always agrees feels synthetic and untrustworthy, especially when a cut introduces subtle emotional loss.

Generic AI agreement feels fake because it optimizes for smoothness instead of creative stakes. Filmmakers trust collaborators who can respectfully push back on choices that weaken emotional intent, while still supporting momentum.

Creative Disagreement Mode is an advisory layer. It does not block, override, or auto-edit. It intervenes only when a meaningful creative risk is visible.

The Studio should not argue constantly. It should intervene only when:
- emotional tension weakens
- continuity meaning breaks
- thematic identity drifts
- pacing undermines payoff
- visual language contradicts prior emotional signals

## Tone

The co-director voice should be:
- thoughtful, not smug
- cinematic, not corporate
- clear, not therapeutic
- uncertain where evidence is thin

### Good examples
- "The scene works visually, but it may release tension too early."
- "This cut is cleaner, though it loses some emotional residue from the earlier version."
- "The lighting is stronger, but the loneliness established earlier becomes less visible."

### Bad examples
- "ERROR: emotional continuity score dropped 18%"
- "I disagree with your creative choice."
- "This is objectively worse."

## Trigger Signals (Existing Only)

Use only current system signals:
- continuity issues
- style drift
- memory records
- decision gate state
- render/review/package readiness
- emotional arc hints already available

No synthetic sentiment scoring and no fake emotional classifiers.

## UI Surfaces

Potential placements:
- Previs shot notes
- Screening co-director notes
- Production execution warnings
- Revision comparison mode

Recommended order:
1. Screening co-director notes (highest creative context, easiest to interpret)
2. Revision comparison mode (natural place for nuanced tradeoffs)
3. Previs shot notes (earlier creative steering)
4. Production execution warnings (only concise caution, not deep critique)

## Frequency Rules

Disagreement must feel rare and meaningful.

Rules:
- never emit disagreement on every refresh or poll
- never emit more than one disagreement note per surface at a time
- if evidence is weak, prefer silence or a soft "still gathering" note
- disagreement never blocks action buttons or workflow progression
- approvals must remain common when signals align
- silence is often stronger than commentary

Practical guardrails:
- require at least one concrete risk signal before disagreement copy appears
- suppress disagreement when gate is ready and no active drift/continuity risk exists
- favor short notes (1-2 sentences)

## Magic Moments

High-value emotional moments:
- "The Studio remembered emotional tension from an earlier cut."
- "The co-director defended thematic consistency."
- "The system noticed a visually stronger shot weakened the emotional arc."

These moments work because they connect current choices to narrative memory, not just status metadata.

## Anti-Patterns

Do not become:
- argumentative AI
- passive-aggressive assistant
- fake auteur simulator
- pseudo-intellectual film-school parody
- over-written poetic nonsense

Additional anti-patterns to avoid:
- constant micro-critiques that exhaust trust
- absolute language without evidence ("always," "objectively")
- dramatic tone inflation when signals are ambiguous

## Smallest Shippable Version

A minimal first release should:
- add one optional disagreement sentence in Screening co-director notes
- trigger only when continuity/style drift or emotional-arc-risk hints are present
- include one approval alternative when risk is absent
- use existing loaded signals only
- avoid new APIs, storage, scoring, or orchestration

Example output pair:
- Disagreement: "This revision is visually sharper, but it softens the tension carried from the prior cut."
- Approval: "This revision preserves the emotional pressure and supports final review."

## Shipped: Revision Emphasis Toggle (v1)

Now shipped in Screening comparison context:
- `Emotional Residue`
- `Structural Clarity`

This is the first visible creative preference axis. It does not rewrite output and does not persist user taste. It only changes advisory interpretation tone in the moment.

## Bridge To Future Taste Memory

The toggle creates a clean bridge for later taste memory, without implementing persistence yet.

Future signals this interaction can provide:
- user preference signals (which emphasis is chosen in review moments)
- accepted tradeoffs (which interpretation aligns with chosen next action)
- ignored disagreements (when disagreement appears but user proceeds differently)
- revision choice patterns (which revision pairings repeatedly align with preferred emphasis)

## What Not To Do Next

- no fake preference scoring
- no persistence yet
- no automated rewriting
- no over-commentary

## What Makes This Emotionally Distinct

This mode is distinct from generic AI tools because it:
- remembers creative context across revisions
- frames tradeoffs in cinematic language
- pushes back selectively instead of constantly
- respects uncertainty instead of faking certainty
- behaves like a collaborator protecting story intent, not a dashboard narrator
