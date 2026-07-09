# AGENTS.md — AI Film Studio

This file defines conventions, boundaries, and creative principles for all AI agents working in this codebase.

---

## Project Overview

AI Film Studio is a spec-driven, A24-sensibility film production tool.
- **Backend**: Python 3.11 / FastAPI / SQLite / Runway ML
- **Frontend**: React / TypeScript / Vite / Tailwind
- **Tests**: ~1,700 Pytest (backend) / ~230 Vitest (frontend)
- **Architecture**: Thin routes → Services → Storage. No business logic in routes or UI components.

---

## Architecture Rules (NEVER violate these)

### Service Boundaries
- Routes MUST NOT call provider adapters directly — always go through services
- Routes MUST NOT access storage directly — always service-mediated
- No business logic in frontend components — backend owns logic, frontend owns UI state
- No circular service dependencies

### Correct Pattern
```python
# ✅ Routes call services
result = await render_service.submit_job(job.id)

# ❌ Routes never call providers directly
result = runway_adapter.submit_job(job)
```

### Data Flow
Request → Route (parse/validate) → Service (business logic) → Storage → Route (format response)

### Error Handling
- Services own domain errors (ValidationError, etc.)
- Routes own HTTP formatting (HTTPException)
- Use structured stability error classes: `validation_error`, `provider_error`, `state_error`, `persistence_error`, `playback_error`
- Never swallow errors silently
- Always include stage logging with: `project_id`, `job_id`, `provider`, `stage`, `duration_ms`

---

## Co-Director / Studio Brain Rules

The AI co-director is **advisory only**. It never overrides creator authority.

### Voice
- Emotionally perceptive, respectfully bold, cinematically literate
- Speaks like a collaborator in a real edit bay
- Prioritizes feeling, rhythm, and motif coherence over generic quality adjectives
- Explains *why* a note matters to story impact
- Uncertain where evidence is thin — silence is often stronger than commentary

### Hard Rules
- **NO scores, ratings, or percentages** — ever
- **NO empty praise** — every note must be specific and actionable
- **NO deterministic certainty** from sparse signals
- **NO humiliation** — honest but always supportive of momentum
- **NO commentary on every refresh or poll** — disagreement must feel rare and meaningful
- **NO more than one disagreement note per surface at a time**
- Selectively poetic — only when clarifying tone and feeling

### Good Co-Director Output
- "The visual language is strong, but this beat releases tension too early."
- "This cut earns its stillness. The payoff lands without overstatement."
- "Push this scene one degree darker in emotional implication, not in color grade."
- "This revision is visually sharper, but it softens the tension carried from the prior cut."

### Bad Co-Director Output (never generate this)
- "Great job! Score: 8.5/10"
- "This looks good overall."
- "ERROR: emotional continuity score dropped 18%"
- "I disagree with your creative choice."
- "This is objectively worse."

### When Disagreement Triggers
Only when a meaningful creative risk is visible:
- emotional tension weakens
- continuity meaning breaks
- thematic identity drifts
- pacing undermines payoff
- visual language contradicts prior emotional signals

### Disagreement must NEVER
- block action buttons or workflow progression
- use absolute language ("always", "objectively")
- appear without at least one concrete risk signal

---

## Creative Memory Rules

### Taste Memory (v1 — frontend session only, not yet persistent)
- Infer filmmaker preferences from repeated choices — slowly, softly, reversibly
- Track axes: `emotional_residue_vs_structural_clarity`, `intimacy_vs_scope`, `ambiguity_vs_exposition`, `visual_consistency_vs_experimentation`, `pacing_patience`
- Use tendency language only: "you tend to..." never "you always..."
- Confidence labels: `emerging`, `consistent`, `strong` — no percentages
- One event never defines taste — patterns over time define advisory tendencies
- Never use taste memory to block workflow actions

### Creative Decision Memory (v1 — explicit save only)
- Only save when user explicitly triggers "Save this decision to project memory"
- Never auto-save from toggles, prompts, or passive observation
- Every saved memory must be editable and forgettable
- Scope: project-level only (not user/global profile)
- `inferred_tradeoff` stays language-level — no numeric scoring

### What Must NEVER Be Remembered Automatically
- Every click or transient UI interaction
- Temporary one-off toggles
- Private/raw notes without explicit consent
- Permanent personality claims

---

## Magic Moments (High-Value Features)

These are the emotional moments users remember. Prioritize them:

1. **"The co-director noticed the emotional callback"** — motif in later scene matches earlier emotional context
2. **"Why this shot matters"** — one-sentence intent rationale in Previs + Screening using existing signals
3. **"Screening explained why the cut worked"** — coherent advisory rationale at approved gate
4. **"The studio remembered a visual motif from Act 1"** — motif persistence + memory records
5. **"Production felt like a real film pipeline"** — queue + provider status + ready-to-screen in one view
6. **"I can steer the interpretation without changing the cut"** — Revision Emphasis toggle (`Emotional Residue` / `Structural Clarity`)

The "Why this shot matters" feature is the **smallest highest-impact next feature** — uses existing loaded signals, no new APIs needed.

---

## Current Phase Priority

**Emotional Intelligence + Cinematic Identity** — in this order:
1. Emotional intelligence in scene-level guidance
2. Cinematic identity persistence across revisions
3. Memory quality and callback reliability
4. Creative collaboration quality (co-director voice)
5. Presentation quality in room-to-room handoff
6. Onboarding/demo magic moments
7. Storytelling polish in final review context

### Explicitly Deprioritized (do not suggest or implement)
- Infrastructure rewrites
- Speculative scaling
- Unnecessary multi-agent expansion
- Integrations that don't improve cinematic outcomes
- No major backend/system rewrites until emotional intelligence proof points are visible in live demo

---

## Python Conventions

- Python 3.11+ — use `str | None` union syntax, not `Optional[str]`
- All async endpoints use `async def`
- Pydantic DTOs define all API contracts
- Services injected via dependency injection, not imported directly in routes
- Use `app.utils.helpers` for shared utilities (`as_non_empty_string`, `ensure_scene_fallback`)
- SQLite via service layer — never raw SQL in routes
- Run with venv Python: `.venv/bin/python -m pytest`

### Stability Patterns (always follow)
- Validate required fields early: `title`, `output_url`, `final_output_url` must be non-empty before entering workflow
- Render polling must have explicit timeout guards
- Guard against duplicate/stale job IDs in polling loops
- Stitch soundtrack requires `audio_url` or `local_audio_path` — never enable without concrete source
- Review decisions must validate transition: only `approve`, `revise`, `reject` accepted
- Revisions require `review_id` and `original_job_id`
- Packaging requires `final_output_url`

### Test Conventions
- Pytest for all backend tests
- Tests organized by layer: unit (services), integration (service interactions), API (route contracts)
- Never test across architectural boundaries

---

## TypeScript/React Conventions

- Functional components only — no class components
- Tailwind for all styling
- No business logic in components — use hooks for data fetching
- API contracts match backend Pydantic DTOs exactly
- No `localStorage` for critical state — backend is source of truth
- Error boundaries required on major component trees
- Shared status normalization in `jobStatus.ts` — never duplicate status logic across components

---

## Key Services Reference

| Service | Owns |
|---|---|
| RenderService | Render job lifecycle, provider abstraction, polling |
| ProjectStoreService | Project persistence and state |
| SemanticMemoryService | Scene memory ingestion and retrieval |
| ContinuityIntelligenceService | Continuity analysis |
| StyleLearningService | Style signature analysis |
| DirectorCommentaryService | AI commentary workflow |
| SemanticSearchService | `list_analyses_for_asset()` for status workflows |

---

## What "Done" Means

A feature is done when:
1. Service layer implements business logic with proper error handling + stage logging
2. Route layer is thin — validates input, calls service, formats response
3. Pydantic DTOs define the API contract
4. Tests written for each layer (unit + integration + API)
5. No boundary violations (no direct storage/provider access in routes)
6. Co-director outputs contain zero scores, ratings, or generic praise
7. Any creative memory is explicit-save only, editable, and forgettable
