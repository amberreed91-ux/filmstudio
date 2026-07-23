# Enhance Prompt and Co-Director Writer Context Validation

Date: 2026-07-23

## Scope

This note records the local validation for the shared context bug where Enhance
Prompt and Co-Director Writer could claim memory/context usage while producing
generic or near-no-op output.

Live Qwen/DashScope validation was attempted after explicit user approval, but
the managed execution reviewer denied the external call because it would transmit
private screenplay excerpts and Director Memory content to an external provider.
This report therefore documents the strongest allowed evidence: exact local LLM
payload construction, mocked-provider response gates, and targeted tests.

## Root Cause

Two related problems were found:

- Enhance Prompt built provider prompts directly in the route with weak
  instructions and a fallback path that could return the original prompt as a
  successful enhancement.
- Co-Director Writer used bespoke memory serialization that did not read the
  Director Memory `note` field. The UI could show memory was available while the
  Writer prompt missed the useful saved prose.

No response cache was found in these paths.

## Fix Summary

- Shared memory/scene assembly now flows through
  `app.services.study_context.build_study_context()` and
  `select_relevant_memory_entries()`.
- Enhance Prompt now uses `PrevisPromptEnhancementService`, which:
  - injects selected Director Memory, character profiles, and scene text;
  - requires composition/blocking, lighting, lens/depth, camera behavior, and
    tactile production detail;
  - rejects punctuation-only or near-verbatim outputs;
  - retries once and fails closed instead of returning the original prompt.
- Co-Director Writer now uses `CoDirectorChatService`, which:
  - injects selected Director Memory using the same schema-aware selection;
  - includes canonical scene `text` in current-scene/full-script/project-overview
    contexts;
  - classifies clear questions and rejects generic, numeric, or ungrounded
    responses for Writer/Director/Memory Archivist;
  - retries once and fails closed if the response remains noncompliant.
- UI provenance now distinguishes available memory from supplied memory.

## Local Trace Evidence

Safe local trace, with mocked provider text passing through the real services:

- Raw visible Director Memory bundle in the drawer: 15 records.
- Prompt-eligible deduped memory texts: 14.
- Enhance Prompt supplies 8 selected memory entries, scene text, and 6 character
  profiles for the tested project.
- Writer supplies 8 selected memory entries and real screenplay excerpts.
- The actual Enhance Prompt system prompt contains `SCENE TEXT:`,
  `DIRECTOR'S ACTIVE MEMORY`, and the anti-no-op contract including
  `punctuation pass`.
- The actual Writer system prompt contains Director saved rules and screenplay
  details such as the opening line about fire and later rooftop imagery.

## Enhance Prompt Before/After Examples

### Scene 001

Original:

> Over-the-shoulder or two-shot framing for conversation. DOWNTOWN CHICAGO —
> GOLDEN HOUR. MAYA (V.O.) People think the end of the world is fire.
> Buildings. Cinematic, film quality, single continuous shot.

Enhanced:

> A restrained 40mm shoulder-height track holds Maya in the right third as she
> moves through the living Chicago crowd, families crossing the near foreground
> while the L train cuts the skyline behind her. Low golden-hour backlight rims
> her worn locs; warm storefront practicals fall into cooler concrete shadow.
> Keep shallow focus breathing between Maya and the ordinary life she watches as
> her voice-over remembers the fire, one continuous observant move with no
> editorial flourish.

### Scene 002

Original:

> Wide establishing shot. Downtown Chicago after the apocalypse. Maya walks
> through the ruins toward the Chicago River. Cinematic, film quality, single
> continuous shot.

Enhanced:

> A low 28mm wide track follows Maya along the right edge of the reclaimed
> avenue, the frozen L train and cracked towers stacking behind her as she
> approaches the Chicago River. Flat winter daylight catches wet concrete and
> vine-choked steel; her lean figure passes from open gray light into bridge
> shadow. Let the camera lag half a step, observing rather than chasing, with
> deep focus holding the graveyard city and the place where she died in one
> continuous move.

### Scene 003

Original:

> Medium two-shot in Dre's warm apartment at night. Maya watches Dre cooking
> before he notices her. Cinematic, film quality, single continuous shot.

Enhanced:

> From the dark doorway, a patient 50mm frame keeps Maya soft in the near-left
> foreground while Dre cooks in warm kitchen practicals beyond her. Drift focus
> from his hands splitting the meal to her held expression; amber light reaches
> him but falls off before touching her face. He crosses toward the stove as she
> stays rooted, then the camera makes one restrained push when he finally
> notices her, preserving the apartment's lived-in warmth in a continuous shot.

## Writer Response Examples

The Writer trace was run through `CoDirectorChatService.chat()` with a mocked
LLM callable that captures the exact `system_prompt` and `user_message` passed
to the provider boundary before returning a controlled response. This verifies
the full service path without transmitting project text externally.

### Writer Trace 1

Question:

> How can I make the scenes more emotionally triggering?

Trace:

- `context_type`: `full_script`
- `memory_entries_used`: 8
- `references_used`: 5
- `scene_excerpts_used`: 14
- `request_classification`: `CLEAR`
- `system_prompt_chars`: 16387
- Prompt markers present:
  - Writer persona
  - direct-answer response policy
  - `Director's explicitly saved rules`
  - `Studio pattern:` memory text
  - opening line: `People think the end of the world is fire`
  - ending/rooftop imagery

Question:

> How can I make the scenes more emotionally triggering?

Grounded response:

> Make Maya's Chicago walk cost her a present-tense choice: let one ordinary
> family image collide with what she knows the city becomes.

### Writer Trace 2

Question:

> How should Maya's opening carry the film's exhausted grief?

Trace:

- `context_type`: `current_scene`
- `scene_id`: `scene_001`
- `memory_entries_used`: 8
- `references_used`: 5
- `scene_excerpts_used`: 1
- `request_classification`: `CLEAR`
- `system_prompt_chars`: 5168
- Prompt markers present:
  - Writer persona
  - direct-answer response policy
  - `Director's explicitly saved rules`
  - `Studio pattern:` memory text
  - opening line: `People think the end of the world is fire`
  - scene anchors including Maya, Chicago, Lake Michigan, golden hour

Question:

> How should Maya's opening carry the film's exhausted grief?

Grounded response:

> In Maya's downtown Chicago walk, hold on the families and Lake Michigan before
> the voice-over names fire; that delay lets ordinary beauty become the
> emotional cost rather than decoration.

### Writer Trace 3

Question:

> Which images or lines echo from the opening into the ending?

Trace:

- `context_type`: `full_script`
- `memory_entries_used`: 8
- `references_used`: 5
- `scene_excerpts_used`: 14
- `request_classification`: `CLEAR`
- `system_prompt_chars`: 16447
- Prompt markers present:
  - Writer persona
  - direct-answer response policy
  - `Director's explicitly saved rules`
  - `Studio pattern:` memory text
  - opening line: `People think the end of the world is fire`
  - ending/rooftop imagery

Question:

> Which images or lines echo from the opening into the ending?

Grounded response:

> The opening's beautiful Chicago returns as the dark city beneath Maya on the
> rooftop, turning remembered beauty into chosen survival.

## Verification Commands

Backend:

```bash
.venv/bin/python -m pytest -q \
  tests/test_previs_prompt_enhancement.py \
  tests/test_co_director_grounding.py \
  tests/test_co_director_chat.py
```

Frontend:

```bash
npx vitest run \
  src/components/CoDirectorDrawer.test.ts \
  src/lib/studioApi.test.ts \
  -t "CoDirectorDrawer context wiring|preserves exact context-supplied provenance"
```

Build:

```bash
npx vite build
```

## Remaining Limitation

The only unverified item is live external-provider behavior. The local code now
constructs and gates the correct payloads, but this environment is not allowed
to send the private screenplay and memory context to Qwen/DashScope for the
final live round trip.
