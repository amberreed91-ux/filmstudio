# Slot Budget Reference

## Fixed Slot Character Budgets

Total prompt must **never exceed 512 chars** (Runway's hard limit).

### Slot Assembly Order

Slots are assembled in priority order (most-emphasized first, as Runway weights early tokens more heavily):

| Priority | Slot Name | Budget (chars) | Purpose |
|----------|-----------|----------------|---------|
| 1 | `character_state` | 140 | Visual canon only — hands, face, build, clothing — **never character names** |
| 2 | `action` | 110 | **One action per shot**, not multiple. What the character is doing. |
| 3 | `environment_persistence` | 100 | Recurring motifs/settings that must not drop out (e.g., "ocean" in *The Last Tide*) |
| 4 | `camera` | 70 | Controlled vocabulary: wide/medium/close, static/dolly/pan |
| 5 | `lighting` | 60 | Controlled vocabulary where possible: natural/dramatic, high-contrast/soft |
| 6 | `reserve` | 32 | **Unallocated at first render** — leave empty, this is headroom for corrections later |

**Total Budget**: 512 chars max (sum of all slots + separators)

---

## Budget Enforcement Rules

1. **Each slot** is truncated to its budget if input exceeds limit
2. **Total prompt** is guaranteed to never exceed 512 chars
3. **Reserve slot** is always empty on first render (correction headroom)
4. **Sanitization** happens before budget enforcement (strips scene headings)
5. **Assembly** joins non-empty slots with ". " and adds "Cinematic, film quality." suffix

---

## Example: Budget Usage

```python
result = build_slotted_prompt(
    scene_data={},
    shot_number=1,
    character_visual_canon="Young woman, short dark hair, blue jacket, weathered hands",
    action_text="Walking through crowded market, examining vendors",
    environment_motifs="Urban market with neon signs, ocean visible in background",
    camera_direction="Wide establishing shot, static camera",
    lighting_direction="Natural daylight, high contrast shadows",
)

# result["slots"] = {
#     "character_state": "Young woman, short dark hair, blue jacket, weathered hands",  # 68 chars
#     "action": "Walking through crowded market, examining vendors",  # 55 chars
#     "environment_persistence": "Urban market with neon signs, ocean visible in background",  # 63 chars
#     "camera": "Wide establishing shot, static camera",  # 42 chars
#     "lighting": "Natural daylight, high contrast shadows",  # 43 chars
#     "reserve": ""  # 0 chars (empty on first render)
# }

# result["prompt"] = 
#   "Young woman, short dark hair, blue jacket, weathered hands. 
#    Walking through crowded market, examining vendors. 
#    Urban market with neon signs, ocean visible in background. 
#    Wide establishing shot, static camera. 
#    Natural daylight, high contrast shadows. 
#    Cinematic, film quality."
#
# Length: ~295 chars (well under 512 limit)
# Budget remaining: 217 chars
```

---

## Character State Slot: Visual Canon Only

**DO include**:
- Physical appearance: age, build, hair, facial features
- Clothing: colors, style, condition (weathered, pristine, etc.)
- Distinctive features: scars, tattoos, hands, posture
- Visual character arc signals: disheveled → polished

**DO NOT include**:
- Character names (Maya, John, etc.)
- Personality traits (unless visually observable)
- Backstory (unless visually present)
- Relationships (unless visually staged)

**Why**: Character names don't help image generation. Visual descriptions do. This slot is about **what the camera sees**, not who the character is narratively.

---

## Action Slot: One Action Per Shot

**DO include**:
- Primary action for this shot (walking, examining, reaching, etc.)
- Context for the action (through market, toward door, etc.)
- Verb + object structure (examining vendors, reaching for key)

**DO NOT include**:
- Multiple unrelated actions (walking AND examining AND reaching)
- Dialogue (that's for audio, not visual render)
- Internal thoughts or emotions (unless visually expressed)

**Why**: Image generation models work best with a single clear action. Multiple actions create confusion and reduce adherence.

---

## Environment Persistence Slot: Recurring Motifs

**DO include**:
- Locations that appear across multiple scenes (ocean, lighthouse, harbor)
- Visual motifs that define the film's identity (neon signs, rain, fog)
- Environmental elements that must not drop out (urban setting, coastal setting)

**DO NOT include**:
- One-off props (unless they're recurring motifs)
- Transient weather (unless it's a persistent motif)
- Generic descriptions ("outdoor scene", "indoor setting")

**Why**: This slot enforces visual continuity across shots. In *The Last Tide*, "ocean" appears here so it doesn't disappear mid-film.

---

## Camera Slot: Controlled Vocabulary

**Prefer controlled terms**:
- **Framing**: wide / medium / close / extreme close-up
- **Angle**: eye-level / high angle / low angle / dutch angle
- **Movement**: static / dolly in / dolly out / pan left / pan right / tracking

**Avoid freeform descriptions**: "Camera moves around the character slowly while tilting slightly upward"

**Why**: Controlled vocabulary improves adherence. Runway understands "dolly in" better than verbose descriptions.

---

## Lighting Slot: Controlled Vocabulary

**Prefer controlled terms**:
- **Quality**: natural / dramatic / soft / harsh / high-contrast
- **Direction**: front-lit / backlit / side-lit
- **Time-of-day signal**: daylight / golden hour / dusk / night
- **Style**: naturalistic / expressionist / noir

**Avoid scene-heading tokens**: "DAY", "NIGHT" (those get stripped by sanitization)

**Why**: Lighting is often constrained by provider capabilities. Controlled vocabulary increases adherence.

---

## Reserve Slot: Correction Headroom

**Always empty on first render**.

On subsequent attempts, the correction engine can use these 32 chars to add:
- Corrective tokens ("more shadow on face", "brighter")
- Slot-specific adjustments ("warmer lighting", "closer framing")
- Adherence hints ("match previous shot")

**Why**: Leaving headroom allows iterative corrections without violating the 512-char limit.

---

## Sanitization: What Gets Stripped

Before budget enforcement, each slot is sanitized to remove:

| Token Type | Examples | Pattern |
|------------|----------|---------|
| Scene headings | `INT.`, `EXT.`, `INT./EXT.`, `I/E.` | Start-of-text prefix |
| Time-of-day | `DAY`, `NIGHT`, `MORNING`, `DUSK`, `DAWN`, `EVENING` | Suffix with dash or "at TIME" |
| Transitions | `CUT TO`, `FADE IN`, `DISSOLVE TO`, `SMASH CUT` | Whole-word match |
| Leading articles | `THE`, `A`, `AN` (before location) | Start-of-text prefix |

**Example**:
- Input: `"INT. THE OCEAN - DAY"`
- After sanitization: `"OCEAN"`

**Why**: ScriptParser output can leak structural tokens. Sanitization ensures prompts contain only visual descriptions.

---

## Budget Violation Handling

If assembled prompt exceeds 512 chars (rare with proper slot budgets):

1. Each slot is already truncated to its budget
2. Final prompt is truncated at `512 - reserve` chars
3. "..." suffix added to indicate truncation
4. Log warning with `budget_used` and `budget_remaining`

**In practice**: With proper slot budgets, this should never happen. The slot budgets sum to less than 512 to leave room for separators and suffix.

---

## Monitoring

Every call to `build_slotted_prompt()` logs:

```python
logger.info(
    "SLOTTED_PROMPT_BUILT | shot=%d | budget_used=%d | budget_remaining=%d",
    shot_number,
    budget_used,
    budget_remaining,
)
```

Use these logs to:
- Verify prompts stay under limit
- Identify shots with tight budgets (budget_remaining < 50)
- Optimize slot allocation over time

---

## Quick Reference Card

```
SLOT BUDGETS (chars)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
character_state         140
action                  110
environment_persistence 100
camera                   70
lighting                 60
reserve                  32 (empty initially)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOTAL LIMIT             512

ASSEMBLY ORDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. character_state (visual canon)
2. action (one action per shot)
3. environment_persistence (motifs)
4. camera (controlled vocab)
5. lighting (controlled vocab)
6. reserve (correction headroom)

SANITIZATION STRIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- INT./EXT. prefixes
- Time-of-day markers (DAY, NIGHT, etc.)
- Transition tokens (CUT TO, FADE IN, etc.)
- Leading articles (THE, A, AN)
```
