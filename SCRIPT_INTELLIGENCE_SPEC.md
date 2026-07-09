# Batch H: Script Intelligence — Requirements Specification

**Date**: June 7, 2026  
**Status**: 📋 REQUIREMENTS PHASE  
**Priority**: Medium (After emotional intelligence proof points)

---

## Executive Summary

Script Intelligence adds four strategic analysis features to the Writer's Room that help filmmakers understand their screenplay's structure, character dynamics, and tonal consistency **before** moving to Previs. These features align with the A24-sensibility creative workflow by providing emotionally perceptive, cinematically literate guidance on narrative fundamentals.

### The Four Features

1. **Scene Breakdown** — Structural analysis of pacing, act structure, and scene transitions
2. **Character Arc Analysis** — Character journey mapping and relationship dynamics
3. **Tone Consistency Check** — Emotional coherence and mood tracking across scenes
4. **Script-to-Prompt Pipeline** — Automated scene description enhancement for render quality

---

## Project Context (From AGENTS.md)

### Current Phase Priority
From AGENTS.md:
> **Emotional Intelligence + Cinematic Identity** — in this order:
> 1. Emotional intelligence in scene-level guidance ✅ **DONE**
> 2. Cinematic identity persistence across revisions
> 3. Memory quality and callback reliability
> 4. Creative collaboration quality (co-director voice)

**Script Intelligence Positioning**: This batch supports priorities #2-4 by establishing narrative foundations early in the workflow, improving memory coherence and co-director guidance quality.

### Explicitly Deprioritized (From AGENTS.md)
- ❌ Infrastructure rewrites
- ❌ Speculative scaling
- ❌ Unnecessary multi-agent expansion
- ❌ Integrations that don't improve cinematic outcomes

**Compliance**: Script Intelligence uses **existing ScriptParser** and **existing services** (emotional_arc_service, character_consistency_service, continuity_intelligence_service). No new infrastructure.

---

## Magic Moments Target

From AGENTS.md:
> These are the emotional moments users remember. Prioritize them.

### New Magic Moments from Script Intelligence

1. **"The Studio caught a character arc inconsistency before I rendered anything"**
   - Character Arc Analysis warns about unresolved character journeys
   - Saves render time and creative frustration

2. **"The tone map showed exactly where my script shifted mood unexpectedly"**
   - Tone Consistency Check visualizes emotional flow across all scenes
   - Helps filmmakers make intentional tonal choices

3. **"The script-to-prompt pipeline made my renders match the screenplay without manual tweaking"**
   - Automated prompt enhancement preserves screenplay intent
   - Reduces prompt engineering overhead

4. **"The scene breakdown revealed my second act was too short"**
   - Structural analysis guides pacing decisions early
   - Supports narrative rhythm and audience engagement

---

## Requirements: Feature 1 — Scene Breakdown

### User Story

**As a filmmaker**, I want to see a structural analysis of my screenplay **so that** I can understand pacing, act structure, and scene transitions before moving to Previs.

### Acceptance Criteria

#### AC1: Scene Count & Duration Estimates
- [ ] Display total scene count (e.g., "12 scenes")
- [ ] Estimate total runtime based on scene count (e.g., "~8-12 minutes estimated")
- [ ] Show average scene duration estimate (e.g., "~45 seconds per scene")
- [ ] All calculations use existing scene data — no new inputs required

#### AC2: Act Structure Detection
- [ ] Automatically detect 3-act structure from scene transitions
- [ ] Label scenes as Act 1 (Setup), Act 2 (Confrontation), Act 3 (Resolution)
- [ ] Show act boundaries in scene list UI (visual dividers or badges)
- [ ] Handle edge cases: <3 scenes = "Not enough scenes for act structure"

#### AC3: Pacing Analysis
- [ ] Identify fast-paced scenes (short description, high action)
- [ ] Identify slow-paced scenes (long description, introspective)
- [ ] Visualize pacing rhythm across scenes (e.g., bar chart or timeline)
- [ ] Use co-director voice for pacing notes: "Act 2 feels rushed — consider adding a breathing scene"

#### AC4: Scene Transition Quality
- [ ] Analyze emotional continuity between adjacent scenes
- [ ] Flag jarring transitions (e.g., "Joyful → Tense without setup")
- [ ] Recommend transition improvements using co-director voice
- [ ] No scores or percentages — plain language only

#### AC5: Co-Director Voice Compliance
- [ ] ✅ NO scores, ratings, or percentages
- [ ] ✅ Emotionally perceptive language (e.g., "tension builds naturally")
- [ ] ✅ Cinematically literate references (e.g., "second act plateau")
- [ ] ✅ Respectfully bold when identifying risks
- [ ] ✅ Uncertain where evidence is thin (e.g., "Not enough scenes to confirm pacing pattern")

### Signal Sources (Existing Data Only)

**From ScriptParser**:
- Scene count
- Scene descriptions (length = pacing proxy)
- Scene order

**From emotional_arc_service**:
- Emotional target per scene (for transition analysis)
- Emotional state per scene

**From continuity_intelligence_service**:
- Scene continuity warnings (affects transition quality)

### Integration Points

**Where It Lives**: Writer's Room  
**When It Appears**: After script import or manual scene creation (minimum 2 scenes)  
**UI Placement**: New "Script Analysis" panel below scene list  
**User Action**: Automatic analysis on scene changes OR explicit "Analyze Script" button

### Edge Cases & Constraints

1. **Minimum Scenes**: Require 2+ scenes for analysis; show "Add more scenes" message otherwise
2. **Missing Emotional Data**: If emotional_target not set, use neutral default or skip transition analysis
3. **Very Long Scripts**: Analyze first 50 scenes only; show "Analyzing first 50 scenes..." message
4. **No Act Structure**: Scripts with <3 scenes cannot be divided into acts — graceful fallback message

### Non-Requirements (Out of Scope)

- ❌ Manual act boundary adjustment (v1 is auto-detection only)
- ❌ Scene reordering via drag-and-drop (separate feature)
- ❌ Comparative analysis across multiple scripts
- ❌ External script comparison or benchmarking
- ❌ AI-generated scene suggestions (too speculative)

---

## Requirements: Feature 2 — Character Arc Analysis

### User Story

**As a filmmaker**, I want to see which characters appear in which scenes and how their journeys evolve **so that** I can ensure character arcs are complete and relationships are coherent.

### Acceptance Criteria

#### AC1: Character Inventory
- [ ] List all unique characters detected from scenes
- [ ] Show first appearance scene for each character
- [ ] Display scene count per character (e.g., "Appears in 5 scenes")
- [ ] Sort characters by appearance frequency (most frequent first)

#### AC2: Character Arc Mapping
- [ ] Visualize character presence across scenes (e.g., timeline or grid)
- [ ] Identify character arc gaps (e.g., "Sarah disappears for 4 consecutive scenes")
- [ ] Flag unresolved character journeys (character appears once, never returns)
- [ ] Use co-director voice: "Sarah's arc feels incomplete — she disappears after Scene 3 without resolution"

#### AC3: Character Relationships
- [ ] Detect which characters share scenes
- [ ] Show relationship co-occurrence matrix (e.g., "Sarah & Jake: 3 scenes together")
- [ ] Identify isolated characters (never share scenes with others)
- [ ] Warn about missing relationships: "Jake never interacts with the protagonist"

#### AC4: Character Consistency Warnings
- [ ] Integrate with **existing character_consistency_service**
- [ ] Flag visual inconsistencies (e.g., "Sarah's appearance description changes in Scene 5")
- [ ] Flag behavioral inconsistencies (out of scope for v1 — requires deeper NLP)
- [ ] No scores or percentages — use co-director voice warnings only

#### AC5: Co-Director Voice Compliance
- [ ] ✅ NO scores, ratings, or percentages
- [ ] ✅ Character-centered language (e.g., "Sarah's arc," "Jake's journey")
- [ ] ✅ Emotionally perceptive (e.g., "Sarah's disappearance risks emotional payoff")
- [ ] ✅ Actionable guidance (e.g., "Consider adding a resolution scene for Sarah")

### Signal Sources (Existing Data Only)

**From ScriptParser**:
- Character names per scene
- Character first appearance
- Character descriptions (if available)

**From character_consistency_service**:
- Character visual consistency checks
- Character identity tracking

**From character_identity_memory_service**:
- Character memory records (if scenes have been rendered)

### Integration Points

**Where It Lives**: Writer's Room  
**When It Appears**: After script import (requires characters in scene data)  
**UI Placement**: New "Character Analysis" panel or tab in Writer's Room  
**User Action**: Automatic analysis OR explicit "Analyze Characters" button

### Edge Cases & Constraints

1. **No Characters Detected**: Show "No characters detected in scenes" message
2. **Single Character**: Skip relationship analysis; show "Only one character detected"
3. **Character Name Variations**: Normalize names (e.g., "SARAH" = "Sarah" = "sarah")
4. **Very Large Cast**: Analyze up to 20 characters; truncate with "Showing top 20 characters"
5. **Character-less Scenes**: Handle scenes with no character tags gracefully

### Non-Requirements (Out of Scope)

- ❌ Dialogue analysis (requires deeper parsing — future feature)
- ❌ Character motivation analysis (requires NLP — too complex for v1)
- ❌ Protagonist/antagonist detection (requires narrative understanding)
- ❌ Character backstory generation (AI-generated content — out of scope)

---

## Requirements: Feature 3 — Tone Consistency Check

### User Story

**As a filmmaker**, I want to see how emotional tone shifts across my screenplay **so that** I can ensure tonal consistency or make intentional tonal breaks.

### Acceptance Criteria

#### AC1: Tone Map Visualization
- [ ] Display emotional tone per scene (e.g., Tense, Joyful, Melancholic)
- [ ] Visualize tone flow as a timeline or bar chart
- [ ] Use color coding for tone categories (warm = positive, cool = negative, neutral = gray)
- [ ] Show tone labels clearly alongside scene titles

#### AC2: Tone Shift Detection
- [ ] Identify abrupt tone shifts between adjacent scenes
- [ ] Flag jarring shifts: "Scene 3 (Joyful) → Scene 4 (Dread) without transition"
- [ ] Identify sustained tone streaks: "Scenes 5-8 maintain melancholic tone"
- [ ] Use co-director voice for tone notes: "The shift from joy to dread risks whiplash unless you plant tension earlier"

#### AC3: Tone Consistency Score (Language Only — NO Percentages)
- [ ] Provide qualitative assessment: "Tone feels consistent across Act 1"
- [ ] Warn about inconsistency: "Act 2 oscillates between tones — consider anchoring around one emotional throughline"
- [ ] NO numeric scores, percentages, or ratings
- [ ] Use labels: "Consistent", "Mostly Consistent", "Inconsistent", "Too Early to Tell"

#### AC4: Emotional Arc Integration
- [ ] Use **existing emotional_arc_service** data for tone analysis
- [ ] Cross-reference emotional_target and emotional_state from scene data
- [ ] Show emotional arc trajectory alongside tone map
- [ ] Identify mismatches: "Scene tone (Joyful) conflicts with emotional target (Guarded)"

#### AC5: Co-Director Voice Compliance
- [ ] ✅ NO scores, ratings, or percentages
- [ ] ✅ Emotionally perceptive tone language
- [ ] ✅ Respectfully bold when identifying risks
- [ ] ✅ Explains why tone matters to story impact

### Signal Sources (Existing Data Only)

**From ScriptParser / Scene Data**:
- emotional_target (from scene metadata)
- emotional_state (from scene metadata)

**From emotional_arc_service**:
- Emotional arc trajectory
- Emotional flow analysis

**From continuity_intelligence_service**:
- Continuity warnings that affect tone perception

### Integration Points

**Where It Lives**: Writer's Room  
**When It Appears**: After scenes have emotional tone set (manual or inferred)  
**UI Placement**: New "Tone Analysis" panel or visual timeline in Writer's Room  
**User Action**: Automatic analysis when tone data available OR explicit "Analyze Tone" button

### Edge Cases & Constraints

1. **Missing Tone Data**: If emotional_target not set, infer from scene description keywords (fallback NLP)
2. **Neutral Tone**: Handle scenes with no clear emotional tone (label as "Neutral")
3. **Very Short Scripts**: Require 3+ scenes for tone flow analysis; otherwise show "Not enough scenes"
4. **All Same Tone**: If all scenes have same tone, show "Tone is consistent but may lack dynamic range"

### Non-Requirements (Out of Scope)

- ❌ Automated tone suggestions (AI-generated — out of scope)
- ❌ Genre-based tone benchmarking (requires external data)
- ❌ Audience mood prediction (speculative)
- ❌ Music/soundtrack tone matching (separate audio feature)

---

## Requirements: Feature 4 — Script-to-Prompt Pipeline

### User Story

**As a filmmaker**, I want my scene descriptions to automatically generate high-quality render prompts **so that** I can reduce manual prompt engineering and maintain screenplay intent in renders.

### Acceptance Criteria

#### AC1: Automatic Prompt Enhancement
- [ ] Parse scene description text into render-ready prompts
- [ ] Extract visual keywords: location, time of day, lighting, mood
- [ ] Preserve screenplay intent in prompt (e.g., "rain-soaked" becomes "wet surfaces, rain visible")
- [ ] Add cinematic language: "tense scene" becomes "dramatic lighting, tight framing"

#### AC2: Prompt Preview & Editing
- [ ] Show enhanced prompt for each scene before rendering
- [ ] Allow filmmaker to edit auto-generated prompts
- [ ] Save edited prompts as overrides (don't re-generate on future updates)
- [ ] Show original scene description alongside prompt for reference

#### AC3: Style Consistency in Prompts
- [ ] Use **existing style_consistency_service** to maintain visual consistency across prompts
- [ ] Apply director signature to prompts (if available from style_learning_service)
- [ ] Ensure character descriptions remain consistent across scenes
- [ ] Warn if prompt deviates from established visual style

#### AC4: Integration with Render Pipeline
- [ ] Auto-populate render prompt field in Previs/Production Board
- [ ] No manual copy-paste required — prompts flow automatically
- [ ] Update prompts when scene descriptions change (with user confirmation)
- [ ] Track prompt version history (original vs. enhanced vs. edited)

#### AC5: Prompt Quality Guidelines
- [ ] Keep prompts concise (<512 characters for provider compatibility)
- [ ] Use provider-friendly language (avoid screenplay-specific jargon)
- [ ] Include essential visual elements: subject, setting, lighting, mood
- [ ] Avoid vague descriptors: "interesting" → "visually striking, high contrast"

### Signal Sources (Existing Data Only)

**From ScriptParser / Scene Data**:
- Scene description text
- Scene location (INT/EXT)
- Time of day
- Character names/descriptions

**From style_consistency_service**:
- Visual style guidelines
- Director signature elements

**From character_consistency_service**:
- Character visual descriptions for prompt consistency

**From existing prompt builder utilities**:
- Cinematic language templates
- Provider-specific prompt formatting

### Integration Points

**Where It Lives**: Writer's Room → Previs → Production Board  
**When It Runs**: After scene creation OR on explicit "Generate Prompts" action  
**UI Placement**:
- Writer's Room: "Generate Render Prompts" button per scene
- Previs: Auto-populated prompt field with "Edit Prompt" option
- Production Board: Prompt shown in render job setup

**User Action**: 
- Automatic: Prompts auto-generate when scene moves to Previs
- Manual: "Generate Prompt" button in Writer's Room for preview

### Edge Cases & Constraints

1. **Empty Scene Description**: Require minimum description length (e.g., 10 characters); warn "Add more detail for better prompts"
2. **Very Long Descriptions**: Summarize to <512 characters; show "Prompt condensed for provider compatibility"
3. **Provider-Specific Limits**: Runway ML has different prompt limits than other providers — adapt per provider
4. **Character Name Privacy**: If character names are real people, use generic descriptions in prompts
5. **Profanity/Unsafe Content**: Filter scene descriptions through guardrails before prompt generation

### Non-Requirements (Out of Scope)

- ❌ AI-generated scene descriptions (content generation out of scope)
- ❌ Image-to-prompt (requires vision model — separate feature)
- ❌ Prompt templates library (user-created templates — future feature)
- ❌ Multi-language prompt translation (English only for v1)

---

## Cross-Feature Requirements

### Shared Co-Director Voice Rules

All four features MUST follow AGENTS.md co-director voice guidelines:

#### ✅ Required Voice Characteristics
- **Emotionally perceptive**: Language like "carries weight," "risks losing momentum"
- **Cinematically literate**: References to "throughline," "arc," "motif," "visual language"
- **Respectfully bold**: Direct about risks without humiliation
- **Explains why**: Every note connects to story impact
- **Uncertain where evidence is thin**: Conditional language when signals are sparse

#### ❌ Prohibited Voice Patterns
- ❌ NO scores, ratings, or percentages (e.g., "Arc completion: 73%")
- ❌ NO empty praise (e.g., "Great job!")
- ❌ NO deterministic certainty from sparse signals
- ❌ NO humiliation (e.g., "This is objectively worse")
- ❌ NO generic quality adjectives without specificity

### Shared UI/UX Principles

#### Layout Consistency
- **Panel-based design**: Match existing Previs/Screening showcase style
- **Badge system**: Use color-coded badges for status (amber = warning, rose = attention, zinc = neutral)
- **Typography**: 10-12px for labels, 11-12px for body text, zinc color palette
- **Responsive**: All analysis panels must work on mobile viewport

#### Performance Requirements
- **No new API calls**: Use existing loaded data from project state
- **Lazy loading**: Analysis runs only when panel is visible or button clicked
- **Timeout guards**: Analysis functions must complete within 5 seconds or show "Analysis in progress..."
- **Error boundaries**: Graceful fallback if analysis fails (don't crash the room)

#### Accessibility
- **ARIA labels**: All interactive elements need aria-label
- **Keyboard navigation**: Tab through analysis panels and buttons
- **Color-blind safe**: Don't rely on color alone for critical information
- **Focus indicators**: Visible focus outlines on all interactive elements

### Shared Error Handling

#### Validation Errors
- **Domain errors in services**: Use structured error classes (ValidationError, StateError)
- **HTTP errors in routes**: Transform to HTTPException with clear messages
- **User-facing errors**: Plain language, actionable guidance (e.g., "Add at least 2 scenes to see analysis")

#### Logging Requirements
- **Stage logging**: Log analysis start/completion with duration_ms
- **Error context**: Include project_id, scene_count, feature_name in error logs
- **No PII in logs**: Never log user-generated content (scene descriptions, character names)

---

## Architecture Compliance (AGENTS.md Rules)

### Service Boundaries ✅

**Correct Pattern**:
```python
# ✅ Routes call services
analysis = await script_intelligence_service.analyze_scene_breakdown(project_id)

# ❌ Routes never call adapters or storage directly
analysis = script_parser.extract_structured_scenes(script_text)  # WRONG
```

### Data Flow ✅

Request → Route (parse/validate) → Service (business logic) → Storage → Route (format response)

**Example**:
```python
# Route: app/routes/script_intelligence.py
@router.get("/projects/{project_id}/script-analysis/breakdown")
async def get_scene_breakdown(project_id: str):
    # ✅ Thin route: validate, call service, format response
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    breakdown = await script_intelligence_service.analyze_scene_breakdown(project_id)
    return breakdown

# Service: app/services/script_intelligence_service.py
class ScriptIntelligenceService:
    async def analyze_scene_breakdown(self, project_id: str) -> dict:
        # ✅ Business logic in service
        project = await project_store.get_project(project_id)
        scenes = project.get("scenes", [])
        
        # Analyze scenes
        act_structure = self._detect_act_structure(scenes)
        pacing_analysis = self._analyze_pacing(scenes)
        
        return {
            "act_structure": act_structure,
            "pacing_analysis": pacing_analysis,
            # ... more fields
        }
```

### No Business Logic in Components ✅

**Frontend components MUST NOT**:
- ❌ Perform analysis logic (character arc calculations, tone detection)
- ❌ Access localStorage for critical state
- ❌ Call backend routes directly (use hooks for data fetching)

**Frontend components SHOULD**:
- ✅ Display analysis data from props
- ✅ Handle UI state (expand/collapse panels, button clicks)
- ✅ Format data for presentation (no calculations)

---

## Testing Strategy

### Backend Tests (Pytest)

#### Unit Tests (Services Layer)
- [ ] `test_script_intelligence_service.py`: Test each analysis function in isolation
- [ ] `test_scene_breakdown_analysis()`: Verify act structure detection logic
- [ ] `test_character_arc_analysis()`: Verify character tracking and gap detection
- [ ] `test_tone_consistency_check()`: Verify tone shift detection
- [ ] `test_script_to_prompt_pipeline()`: Verify prompt enhancement logic

#### Integration Tests (Service Interactions)
- [ ] `test_scene_breakdown_with_emotional_arc_service()`: Verify integration with emotional_arc_service
- [ ] `test_character_arc_with_character_consistency_service()`: Verify integration with character_consistency_service
- [ ] `test_tone_check_with_continuity_intelligence()`: Verify integration with continuity_intelligence_service
- [ ] `test_prompt_pipeline_with_style_consistency()`: Verify integration with style_consistency_service

#### API Tests (Route Contracts)
- [ ] `test_script_intelligence_routes.py`: Test all 4 analysis endpoints
- [ ] `test_scene_breakdown_endpoint()`: Verify response shape and status codes
- [ ] `test_character_arc_endpoint()`: Verify character data structure
- [ ] `test_tone_consistency_endpoint()`: Verify tone analysis response
- [ ] `test_prompt_pipeline_endpoint()`: Verify prompt generation response

#### Edge Case Tests
- [ ] Test with 0 scenes (empty project)
- [ ] Test with 1 scene (insufficient for analysis)
- [ ] Test with 50+ scenes (performance boundary)
- [ ] Test with missing emotional data (graceful fallback)
- [ ] Test with no characters (character-less script)

### Frontend Tests (Vitest)

#### Component Tests
- [ ] `ScriptAnalysisPanel.test.tsx`: Test analysis panel rendering
- [ ] `CharacterArcTimeline.test.tsx`: Test character visualization component
- [ ] `ToneMap.test.tsx`: Test tone visualization component
- [ ] `PromptPreview.test.tsx`: Test prompt editing interface

#### Integration Tests
- [ ] `WritersRoom.test.tsx`: Test Writer's Room with script intelligence features
- [ ] Test analysis panel visibility after scene import
- [ ] Test "Analyze Script" button triggers correct API call
- [ ] Test prompt auto-population in Previs

### Manual Testing Checklist

#### Scene Breakdown
- [ ] Import 10-scene script → Verify act structure detected
- [ ] Import 2-scene script → Verify "Not enough scenes" message
- [ ] Check pacing visualization displays correctly
- [ ] Verify transition warnings use co-director voice (no scores)

#### Character Arc Analysis
- [ ] Import script with 5 characters → Verify all characters listed
- [ ] Check character timeline shows scene appearances
- [ ] Verify arc gap warnings display correctly
- [ ] Check relationship matrix shows co-occurrences

#### Tone Consistency Check
- [ ] Import script with varied tones → Verify tone map displays
- [ ] Check tone shift warnings appear
- [ ] Verify color coding is accessible (color-blind safe)
- [ ] Confirm no percentages or scores in output

#### Script-to-Prompt Pipeline
- [ ] Generate prompts for 5 scenes → Verify prompts are concise
- [ ] Edit a prompt → Verify edit persists (not overwritten)
- [ ] Check prompt auto-populates in Previs
- [ ] Verify style consistency across prompts

---

## Success Metrics

### Quantitative Metrics
1. **Adoption Rate**: % of projects that run script analysis after import (target: >60%)
2. **Prompt Usage**: % of scenes using auto-generated prompts vs. manual (target: >50%)
3. **Analysis Errors**: <5% error rate on analysis endpoint calls
4. **Performance**: All analysis functions complete in <5 seconds (95th percentile)

### Qualitative Metrics (User Feedback)

1. **Magic Moment Confirmation**: Users report "the Studio caught [issue] before rendering"
2. **Co-Director Voice Quality**: Feedback confirms voice is emotionally perceptive, not robotic
3. **Workflow Integration**: Users report script intelligence fits naturally into Writer's Room workflow
4. **Actionability**: Users can act on analysis insights without confusion

---

## Risks & Mitigations

### Risk 1: Analysis Quality Depends on Scene Description Quality

**Risk**: If filmmakers write vague scene descriptions, analysis will be poor.

**Mitigation**:
- Provide guidance in Writer's Room: "Add detail for better analysis"
- Show example scene descriptions in onboarding
- Gracefully degrade: Show "Not enough detail for analysis" instead of bad analysis

### Risk 2: Co-Director Voice Violation (Scores/Percentages Creep)

**Risk**: Developers might accidentally add numeric scores during implementation.

**Mitigation**:
- Code review checklist: "Does output contain ANY numeric scores?"
- Test assertions: Assert NO regex match for `\d+%` or `score: \d+` in output
- AGENTS.md reminder at top of all script intelligence files

### Risk 3: Performance Degradation on Large Scripts

**Risk**: Analyzing 50+ scenes could slow down Writer's Room.

**Mitigation**:
- Lazy loading: Run analysis only when panel is opened
- Timeout guards: Show "Analysis in progress..." after 5 seconds
- Scene limit: Cap analysis at 50 scenes, show warning for larger scripts

### Risk 4: Integration Complexity with Existing Services

**Risk**: Tight coupling with 4+ existing services (emotional_arc, character_consistency, continuity_intelligence, style_consistency) increases brittleness.

**Mitigation**:
- Defensive coding: Check if service data exists before using
- Graceful degradation: If service data missing, show "Analysis limited — run [X] first"
- Unit test mocks: Mock service dependencies in unit tests
- Integration tests: Validate actual service interactions

### Risk 5: User Overwhelm (Too Much Analysis)

**Risk**: Showing all 4 analyses at once might overwhelm filmmakers.

**Mitigation**:
- Progressive disclosure: Use tabs or collapsible panels
- Default to collapsed state: Only "Scene Breakdown" expanded by default
- Allow dismissal: "Hide Analysis" button to collapse all panels
- Onboarding tooltip: "Review script analysis before moving to Previs"

---

## Implementation Phases (High-Level)

### Phase 1: Scene Breakdown (Weeks 1-2)
- Implement ScriptIntelligenceService with scene breakdown logic
- Create /script-analysis/breakdown endpoint
- Build ScriptAnalysisPanel component for Writer's Room
- Write unit + integration + API tests
- Manual testing with 5 sample scripts

### Phase 2: Character Arc Analysis (Weeks 3-4)
- Add character arc analysis to ScriptIntelligenceService
- Create /script-analysis/characters endpoint
- Build CharacterArcTimeline component
- Integrate with character_consistency_service
- Write tests and manual validation

### Phase 3: Tone Consistency Check (Weeks 5-6)
- Add tone analysis to ScriptIntelligenceService
- Create /script-analysis/tone endpoint
- Build ToneMap visualization component
- Integrate with emotional_arc_service
- Write tests and validate tone shift detection

### Phase 4: Script-to-Prompt Pipeline (Weeks 7-8)
- Implement prompt enhancement logic in ScriptIntelligenceService
- Create /script-analysis/generate-prompts endpoint
- Build PromptPreview component with editing interface
- Integrate with style_consistency_service
- Connect to Previs/Production Board for auto-population
- Write tests and validate prompt quality

### Phase 5: Integration & Polish (Week 9)
- Cross-feature testing (all 4 features together)
- Performance optimization (caching, lazy loading)
- Accessibility audit (ARIA, keyboard nav, color-blind)
- Co-director voice review (no scores/percentages)
- Final manual testing with 10+ sample scripts

### Phase 6: Documentation & Handoff (Week 10)
- Update WRITER_ROOM_QUICK_START.md with script intelligence features
- Create SCRIPT_INTELLIGENCE_USER_GUIDE.md
- Add inline help tooltips in Writer's Room UI
- Record demo video showing all 4 features
- Health check validation (40/40 pass target)

---

## Open Questions (To Resolve Before Design Phase)

### Question 1: Act Structure Algorithm
**Question**: Should act structure be strictly 1/4, 1/2, 1/4 split OR dynamic based on scene content?

**Options**:
- A) Strict mathematical split (simple, predictable)
- B) Content-aware split using emotional arc peaks (complex, more accurate)

**Decision Required By**: Design Phase kickoff

### Question 2: Tone Inference from Scene Descriptions
**Question**: If emotional_target is missing, should we use NLP to infer tone from scene description?

**Options**:
- A) Require manual tone setting (simpler, more accurate)
- B) Use keyword matching (e.g., "rain" → melancholic)
- C) Use external NLP API (complex, costly)

**Decision Required By**: Phase 3 kickoff

### Question 3: Prompt Length for Different Providers
**Question**: Should prompts vary by provider (Runway vs. ComfyUI vs. future providers)?

**Options**:
- A) Single prompt format (simple, may not optimize for each provider)
- B) Provider-specific prompts (complex, better quality)

**Decision Required By**: Phase 4 kickoff

### Question 4: Character Name Normalization
**Question**: How aggressively should we normalize character names (e.g., "SARAH" vs. "Sarah" vs. "sarah")?

**Options**:
- A) Exact match only (simple, may miss duplicates)
- B) Case-insensitive match (moderate, catches most duplicates)
- C) Fuzzy match with edit distance (complex, catches all variations)

**Decision Required By**: Phase 2 kickoff

### Question 5: Analysis Caching Strategy
**Question**: Should analysis results be cached, and if so, for how long?

**Options**:
- A) No caching (simple, always fresh, slower)
- B) Cache per project with TTL (moderate, faster, may be stale)
- C) Invalidate cache on scene edits (complex, optimal)

**Decision Required By**: Phase 5 (optimization phase)

---

## Dependencies on Existing Services

### Required Services (Must Integrate)

1. **ScriptParser** (`app/services/script_parser.py`)
   - Used by: All 4 features
   - Provides: Scene data, character extraction, location parsing
   - Risk: None (already stable and tested)

2. **emotional_arc_service** (`app/services/emotional_arc_service.py`)
   - Used by: Scene Breakdown, Tone Consistency Check
   - Provides: emotional_target, emotional_state per scene
   - Risk: Low (service exists, may need minor enhancements)

3. **character_consistency_service** (`app/services/character_consistency_service.py`)
   - Used by: Character Arc Analysis, Script-to-Prompt Pipeline
   - Provides: Character visual consistency checks
   - Risk: Low (service exists and stable)

4. **continuity_intelligence_service** (`app/services/continuity_intelligence_service.py`)
   - Used by: Scene Breakdown, Tone Consistency Check
   - Provides: Continuity warnings, scene transition analysis
   - Risk: Low (service exists and well-tested)

5. **style_consistency_service** (`app/services/style_consistency_service.py`)
   - Used by: Script-to-Prompt Pipeline
   - Provides: Visual style guidelines, director signature
   - Risk: Low (service exists and stable)

6. **project_store** (`app/services/project_store.py`)
   - Used by: All 4 features (for loading project/scene data)
   - Provides: Project persistence, scene storage
   - Risk: None (core service, extremely stable)

### Optional Services (Nice to Have)

1. **character_identity_memory_service** — For character backstory context
2. **semantic_memory_service** — For motif/callback detection in character arcs
3. **studio_brain_service** — For higher-level narrative intelligence

---

## Acceptance Gates (Definition of Done)

A feature is **DONE** when:

### Backend Completion Criteria
- [ ] Service layer implements business logic with proper error handling
- [ ] Service includes stage logging with duration_ms
- [ ] Route layer is thin (validate, call service, format response)
- [ ] Pydantic DTOs define all API contracts
- [ ] No boundary violations (routes never call storage/providers directly)
- [ ] Unit tests written (services layer)
- [ ] Integration tests written (service interactions)
- [ ] API tests written (route contracts)
- [ ] All tests pass (target: >95% pass rate)

### Frontend Completion Criteria
- [ ] Component displays analysis data correctly
- [ ] No business logic in components (display only)
- [ ] API contracts match backend Pydantic DTOs exactly
- [ ] Error boundaries handle failures gracefully
- [ ] Accessibility: ARIA labels, keyboard nav, color-blind safe
- [ ] Component tests written (Vitest)
- [ ] All tests pass (target: >95% pass rate)

### Co-Director Voice Compliance
- [ ] ✅ NO scores, ratings, or percentages in any output
- [ ] ✅ Emotionally perceptive language used throughout
- [ ] ✅ Cinematically literate references where appropriate
- [ ] ✅ Respectfully bold when identifying creative risks
- [ ] ✅ Explains why insights matter to story impact
- [ ] ✅ Uncertain language when evidence is thin

### Integration & Polish
- [ ] Feature works in Writer's Room without breaking existing workflow
- [ ] Analysis runs in <5 seconds (95th percentile)
- [ ] No console errors or warnings in browser
- [ ] Health check passes (40/40 target)
- [ ] Manual testing completed with 10+ sample scripts
- [ ] User documentation updated (WRITER_ROOM_QUICK_START.md)

---

## Next Steps: Design Phase

Once this requirements spec is approved, the next phase is **Design**, which will define:

### Technical Design Documents

1. **Service Architecture**
   - ScriptIntelligenceService class design
   - Method signatures for all 4 analysis functions
   - Error handling strategy
   - Integration patterns with existing services

2. **API Contracts (Pydantic DTOs)**
   - Request/response schemas for all 4 endpoints
   - Data validation rules
   - Enum definitions for act structure, tone labels, etc.

3. **Data Models**
   - Scene analysis result structure
   - Character arc data structure
   - Tone map data structure
   - Prompt metadata structure

4. **Frontend Component Architecture**
   - Component hierarchy for Writer's Room integration
   - State management strategy (hooks, context)
   - UI/UX wireframes for all 4 features
   - Responsive design breakpoints

5. **Database Schema (If Needed)**
   - Decide if analysis results should be persisted
   - Cache table design (if caching strategy chosen)
   - Migration scripts

6. **Algorithm Specifications**
   - Act structure detection algorithm pseudocode
   - Character arc gap detection logic
   - Tone shift detection thresholds
   - Prompt enhancement rules and templates

---

## Approval Checklist

Before moving to Design Phase, confirm:

- [ ] **Requirements are complete**: All 4 features have clear acceptance criteria
- [ ] **Co-director voice rules are clear**: No ambiguity on prohibited patterns
- [ ] **Architecture compliance verified**: Aligns with AGENTS.md rules
- [ ] **Integration points identified**: All service dependencies mapped
- [ ] **Risks documented**: Mitigations defined for top 5 risks
- [ ] **Open questions listed**: Decision points for Design Phase
- [ ] **Success metrics defined**: Both quantitative and qualitative
- [ ] **Testing strategy outlined**: Unit, integration, API, manual tests
- [ ] **Magic moments validated**: Features deliver user-memorable experiences
- [ ] **User stories validated**: Each feature solves a real filmmaker pain point
- [ ] **Edge cases covered**: Graceful handling of degenerate inputs

---

## Appendix A: Example Co-Director Voice Outputs

### Scene Breakdown Examples

**Good Output ✅**:
> "Act 2 feels rushed — the emotional build from Scene 5 to Scene 8 compresses tension too quickly. Consider adding a breathing scene to let the stakes settle before the climax."

**Bad Output ❌**:
> "Act 2 pacing score: 62/100. Add 1.5 scenes to improve balance."

---

### Character Arc Examples

**Good Output ✅**:
> "Sarah's arc feels incomplete — she carries weight in Scene 3 but disappears for the next 4 scenes without resolution. Consider adding a final beat to close her journey."

**Bad Output ❌**:
> "Sarah's character completion: 45%. Gap detected: Scenes 4-7."

---

### Tone Consistency Examples

**Good Output ✅**:
> "The shift from joyful (Scene 2) to dread (Scene 3) risks whiplash unless you plant tension earlier. The tonal break feels unearned."

**Bad Output ❌**:
> "Tone inconsistency detected. Emotional variance: 78%. Warning: high volatility."

---

### Script-to-Prompt Examples

**Good Enhancement ✅**:
- **Original Scene Description**: "A woman sits in a coffee shop, reading."
- **Enhanced Prompt**: "INT. COFFEE SHOP - DAY. A woman sits alone at a corner table, reading a worn paperback. Warm ambient lighting, soft focus background, intimate framing. Cinematic, A24 aesthetic."

**Bad Enhancement ❌**:
- **Original Scene Description**: "A woman sits in a coffee shop, reading."
- **Enhanced Prompt**: "woman, coffee shop, reading, photorealistic, 4k, trending on artstation"

---

## Appendix B: Sample Test Scripts

### Test Script 1: Minimal (2 Scenes)
```
SCENE 1: INT. APARTMENT - NIGHT
She enters, dripping wet from the rain.

SCENE 2: INT. APARTMENT - NIGHT
She stands in the dark, phone ringing.
```

**Expected Analysis**:
- Scene breakdown: "Not enough scenes for act structure"
- Character arc: 1 character (unnamed protagonist)
- Tone: Consistent (melancholic)
- Prompts: 2 prompts generated

---

### Test Script 2: Balanced (10 Scenes, 3 Characters)
```
SCENE 1: INT. COFFEE SHOP - DAY
SARAH sits alone, reading. JAKE enters, notices her.

SCENE 2: INT. COFFEE SHOP - DAY
JAKE approaches SARAH. They talk. EMMA watches from the counter.

SCENE 3: EXT. STREET - NIGHT
SARAH walks alone, phone buzzing.

SCENE 4: INT. APARTMENT - NIGHT
SARAH and EMMA argue about JAKE.

SCENE 5: INT. BAR - NIGHT
JAKE drinks alone, regretful.

SCENE 6: EXT. PARK - DAY
SARAH and JAKE meet. Tension.

SCENE 7: INT. COFFEE SHOP - DAY
EMMA confronts JAKE.

SCENE 8: INT. APARTMENT - NIGHT
SARAH deletes JAKE's number.

SCENE 9: INT. BAR - NIGHT
JAKE sees EMMA. They talk.

SCENE 10: EXT. STREET - DAY
SARAH walks, umbrella forgotten. Rain.
```

**Expected Analysis**:
- Scene breakdown: Act 1 (Scenes 1-3), Act 2 (Scenes 4-7), Act 3 (Scenes 8-10)
- Character arc: SARAH (10 scenes), JAKE (6 scenes), EMMA (4 scenes)
- Tone: Mixed (hopeful → tense → melancholic)
- Prompts: 10 prompts with character consistency

---

### Test Script 3: Edge Case (50 Scenes, Many Characters)

**Expected Analysis**:
- Scene breakdown: Full act structure, pacing warnings
- Character arc: Top 20 characters only
- Tone: Long timeline, potential consistency issues
- Prompts: 50 prompts generated, performance within 5 seconds

---

## Appendix C: Glossary

### Terms Used in This Spec

- **Act Structure**: Traditional 3-act narrative division (Setup, Confrontation, Resolution)
- **Co-Director Voice**: Emotionally perceptive, cinematically literate advisory tone (per AGENTS.md)
- **Dread Curve**: Emotional tension trajectory across scenes
- **Emotional Target**: Intended emotional state for a scene
- **Magic Moment**: User-memorable feature experience that creates emotional impact
- **Pacing**: Rhythm and speed of scene transitions
- **Scene Breakdown**: Structural analysis of screenplay composition
- **Script-to-Prompt**: Automated conversion of scene descriptions to render prompts
- **Tone Consistency**: Coherence of emotional mood across screenplay
- **Tone Shift**: Change in emotional tone between adjacent scenes

---

## Document History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-06-07 | 1.0 | Initial requirements specification | Kiro AI |

---

## Conclusion

This requirements specification defines **Batch H: Script Intelligence** with four distinct features that enhance the Writer's Room workflow. All features align with AGENTS.md principles:

- ✅ **No scores or percentages** — Co-director voice only
- ✅ **Uses existing services** — No unnecessary complexity
- ✅ **Delivers magic moments** — Users remember when features catch issues early
- ✅ **Architecture compliant** — Thin routes → Services → Storage pattern

**Next Phase**: Design Phase — Define technical architecture, API contracts, data models, and UI/UX wireframes.

**Approval Required**: Review this requirements spec and confirm readiness for Design Phase.
