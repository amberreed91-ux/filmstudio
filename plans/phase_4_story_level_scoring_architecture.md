# Phase 4: Story-Level Scoring Architecture

## Executive Summary

Story-level scoring evaluates narrative health beyond individual scene quality. Where **DirectorEvaluator** judges "Is this scene good?" and **MemoryArchivistEvaluator** audits "Is this scene consistent?", **StoryLevelScoringService** answers "Does this scene serve the film?"

**Core Principle**: Story-level scoring is **additive and advisory**. It does not block, override, or replace scene-level decisions. It provides film-aware context that helps the Director make better scene-level decisions.

---

## 1. Story-Level Scoring Responsibilities

### 1.1 What Story-Level Scoring Evaluates

| Dimension | Description | Distinguishes From |
|-----------|-------------|-------------------|
| **Thesis Alignment** | Does scene advance or support the film's governing theme? | DirectorEvaluator checks "good scene", Story checks "right scene for this film" |
| **Tone Coherence** | Is tone consistent with film-wide tone? With act/sequence tone? | MemoryArchivist checks scene continuity, Story checks tonal arc |
| **Character Progression** | Are character arcs advancing? Any stagnation or regression? | SceneEvolution tracks iterations, Story tracks arc health |
| **Emotional Trajectory** | Does emotional journey follow intended arc? Any flat spots? | MemoryArchivist tracks tension health, Story tracks emotional arc |
| **Motif Continuity** | Are motifs callback properly? Payoffs earned? | MemoryArchivist tracks motif references, Story tracks payoff timing |
| **Unresolved Tension** | How many tensions unresolved at act/film end? Expected vs actual? | MemoryArchivist flags individual issues, Story aggregates risk |
| **Originality vs Formula** | Does scene rely on clichés? Subverts expectations appropriately? | DirectorEvaluator judges quality, Story judges freshness |
| **Continuity Debt Accumulation** | Is debt increasing faster than payoff? Film health trending down? | FilmContinuityTracker tracks per-scene, Story tracks trajectory |
| **Overall Film Health** | Composite score of all dimensions | Not a scene score - a film score |

### 1.2 What Story-Level Scoring Does NOT Do

- Does NOT evaluate scene technical quality (DirectorEvaluator)
- Does NOT audit continuity consistency (MemoryArchivistEvaluator)
- Does NOT make APPROVE/REVISE/REJECT decisions (Director authority)
- Does NOT resolve conflicts between agents (Conflicts service)
- Does NOT track scene iterations (SceneEvolutionTracker)

---

## 2. Relationship to Existing Evaluators and Services

### 2.1 Input Sources

```
StoryLevelScoringService
├── DirectorEvaluator Output (scene decision, score, revision_notes)
├── MemoryArchivistEvaluator Output (continuity context, alerts)
├── DirectorContinuityDecision (merged output from Phase 3.5)
├── FilmStructure (acts, sequences, scenes hierarchy)
├── FilmLevelMemory / ActMemory / SequenceMemory (film memory hierarchy)
├── CreativeSpine (thesis, motifs, character arcs, restraints)
├── FilmContinuityTracker (accumulated debt per film)
└── SceneEvolutionTracker (iteration history per scene)
```

### 2.2 Relationship to DirectorEvaluator

| Aspect | DirectorEvaluator | StoryLevelScoringService |
|--------|-------------------|--------------------------|
| **Question** | "Is this scene good?" | "Does this scene serve the film?" |
| **Scope** | Single scene | Scene within film context |
| **Authority** | Makes decisions | Provides advisory context |
| **Output** | APPROVE/REVISE/REJECT | Story alignment score, recommendations |
| **Timing** | Per scene iteration | Per scene, per sequence, per act, per film |

**Integration**: StoryLevelScoringService reads DirectorEvaluator output but does not modify it. Director can use story scores as input to their decision.

### 2.3 Relationship to MemoryArchivistEvaluator

| Aspect | MemoryArchivistEvaluator | StoryLevelScoringService |
|--------|--------------------------|--------------------------|
| **Question** | "Is this scene consistent?" | "Is the film structurally sound?" |
| **Scope** | Scene continuity | Film-level patterns |
| **Authority** | Advisory alerts | Advisory scores |
| **Output** | Alerts with severity | Health scores with trajectory |
| **Timing** | Per scene | Per scene + periodic aggregation |

**Integration**: StoryLevelScoringService consumes MemoryArchivistEvaluator alerts and aggregates them into film-level continuity debt trajectory.

### 2.4 Relationship to Director-Memory Conflict Resolution

**Input**: `DirectorContinuityDecision` from [`director_memory_resolver.py`](studio-backend/app/services/director_memory_resolver.py:40)

The merged output already contains:
- Director decision preserved
- Memory Archivist continuity context attached
- Alert counts and acknowledgment status
- Escalation flags

**Story-Level Use**: StoryLevelScoringService reads DirectorContinuityDecision to understand scene context when computing story-level scores.

### 2.5 Relationship to FilmStructure

**Input**: [`FilmStructure`](studio-backend/app/models/crew.py:737) from `models/crew.py`

Provides:
- Act boundaries for act-level scoring
- Sequence boundaries for sequence-level scoring
- Scene ordering for trajectory calculation
- Beat placement for structural analysis

### 2.6 Relationship to Film Memory Hierarchy

**Input**: 
- [`FilmLevelMemory`](studio-backend/app/models/memory.py:287) - thesis, motifs, tensions
- [`ActMemory`](studio-backend/app/models/memory.py:317) - act-specific thematic focus
- [`SequenceMemory`](studio-backend/app/models/memory.py:380) - sequence-level arc

**Story-Level Use**: Compare current scene against film/act/sequence memory to compute alignment scores.

### 2.7 Relationship to CreativeSpine

**Input**: [`CreativeSpine`](studio-backend/app/models/spine.py:207) from `models/spine.py`

Provides:
- `thesis` - governing question/theme for alignment check
- `motifs` - registered motifs for callback tracking
- `character_arcs` - expected character progression
- `restraints` - what to avoid (originality check)
- `frozen_fields` - immutable elements to preserve

**Story-Level Use**: Validate scene against spine constraints and alignment.

### 2.8 Relationship to FilmContinuityTracker

**Input**: [`FilmContinuityTracker`](studio-backend/app/services/conflicts.py:423) from `services/conflicts.py`

Provides:
- Per-film accumulated alerts
- Critical/warning counts
- Scene-level decision history

**Story-Level Use**: Compute continuity debt trajectory. Is debt increasing? Are critical alerts accumulating faster than resolved?

---

## 3. Scoring Layers and Outputs

### 3.1 Scoring Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    FULL FILM SCORE                          │
│  (Composite of all dimensions across all acts)              │
├─────────────────────────────────────────────────────────────┤
│  ACT 1 SCORE  │  ACT 2 SCORE  │  ACT 3 SCORE               │
│  (Aggregated  │  (Aggregated  │  (Aggregated               │
│   act dims)   │   act dims)   │   act dims)                │
├─────────────────────────────────────────────────────────────┤
│  SEQ 1.1 SCORE │ SEQ 1.2 SCORE │ SEQ 2.1 SCORE │ ...       │
│  (Sequence-   │  (Sequence-   │  (Sequence-                │
│   level)      │   level)      │   level)                   │
├─────────────────────────────────────────────────────────────┤
│  SCENE 1 SCORE │ SCENE 2 SCORE │ SCENE 3 SCORE │ ...       │
│  (Scene with  │  (Scene with  │  (Scene with               │
│   film ctx)   │   film ctx)   │   film ctx)                │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Output Model

```python
@dataclass
class StoryScore:
    """Story-level scoring output."""
    
    # Identity
    film_id: str
    scope: str  # "scene", "sequence", "act", "film"
    scope_id: Optional[str]  # scene_1, seq_1_2, act_1, None for film
    
    # Dimension Scores (0.0 to 1.0)
    thesis_alignment: float
    tone_coherence: float
    character_progression: float
    emotional_trajectory: float
    motif_continuity: float
    tension_resolution_rate: float  # resolved vs introduced
    originality_score: float  # vs formula risk
    continuity_debt_trajectory: float  # trending up/down
    
    # Aggregates
    overall_health: float  # Weighted composite
    dimension_weights: Dict[str, float]  # Configurable weights
    
    # Context
    scene_count: int
    act_count: int
    sequence_count: int
    
    # Alerts and Recommendations
    warnings: List[str]  # Specific concerns
    recommendations: List[StoryRecommendation]
    
    # Revision Priority
    revision_priority: RevisionPriority  # LOW, MEDIUM, HIGH, CRITICAL
    
    # Metadata
    timestamp: str
    based_on_scenes: List[str]  # Which scenes were evaluated


@dataclass
class StoryRecommendation:
    """Recommendation generated by story-level scoring."""
    
    category: RecommendationCategory
    priority: RevisionPriority
    description: str
    target_scope: str  # Which scope this applies to
    specific_scenes: List[str]  # Which scenes need attention
    rationale: str
    suggested_fix: Optional[str] = None


class RecommendationCategory(Enum):
    THESIS_DRIFT = "thesis_drift"  # Scene doesn't support theme
    TONE_SHIFT = "tone_shift"  # Inconsistent with film tone
    CHARACTER_STAGNATION = "character_stagnation"  # Arc not advancing
    EMOTIONAL_FLAT_SPOT = "emotional_flat_spot"  # No emotional progress
    MOTIF_MISSING_CALLBACK = "motif_missing_callback"  # Overdue callback
    TENSION_UNDERPAY = "tension_underpay"  # Too many unresolved
    FORMULA_RISK = "formula_risk"  # Too predictable
    DEBT_ACCUMULATION = "debt_accumulation"  # Continuity debt increasing


class RevisionPriority(Enum):
    LOW = "low"      # Consider on next pass
    MEDIUM = "medium"  # Address before next act
    HIGH = "high"    # Address before proceeding
    CRITICAL = "critical"  # Stop and fix now
```

### 3.3 Score Calculation by Layer

#### Scene-Level Story Score
- Evaluates single scene in film context
- Inputs: Scene content, DirectorContinuityDecision, CreativeSpine, FilmLevelMemory
- Outputs: Per-dimension 0-1 score, warnings, recommendations
- **Does not block scene** - advisory only

#### Sequence-Level Story Score
- Aggregates scene scores within sequence
- Adds sequence-specific analysis:
  - Sequence goal achievement
  - Sequence-level arc progression
  - Internal pacing
- Outputs: Aggregated scores, sequence-specific warnings

#### Act-Level Story Score
- Aggregates sequence scores within act
- Adds act-specific analysis:
  - Act climax effectiveness
  - Act-level thematic focus
  - Act transition coherence
- Outputs: Act health, act-specific warnings, act recommendations

#### Film-Level Story Score
- Aggregates all act scores
- Adds film-wide analysis:
  - Overall thesis expression
  - Film-wide character arc completion
  - Emotional journey shape
  - Final act resolution quality
- Outputs: Complete film health, film recommendations, revision priorities

---

## 4. Workflow Placement

### 4.1 When Story-Level Scoring Runs

| Trigger | Scope | Rationale |
|---------|-------|-----------|
| **After each scene decision** | Scene | Keep story context current for next scene |
| **After sequence completes** | Sequence | Validate sequence arc before next |
| **After act completes** | Act | Validate act before next |
| **On-demand** | Any | User/Director requests |
| **Periodic** | Film | Background health check |

### 4.2 Hybrid Workflow

```
Scene Loop:
    for each scene:
        1. Director evaluates scene → DirectorContinuityDecision
        2. Story scoring (scene-level) → StoryScore attached to decision
        3. If CRITICAL story warning → pause, alert Director
        4. Continue to next agent
        
After Sequence N completes:
    1. Story scoring (sequence-level) → Sequence StoryScore
    2. If HIGH+ warning → pause, alert Director
    3. Continue to next sequence
    
After Act N completes:
    1. Story scoring (act-level) → Act StoryScore
    2. If HIGH+ warning → pause, alert Director
    3. Continue to next act
    
After Film completes:
    1. Story scoring (film-level) → Final Film StoryScore
    2. Generate film health report
    3. Flag any unresolved issues
```

### 4.3 Non-Blocking Design

- Story-level scores are **attached** to decisions, not merged
- CRITICAL warnings **pause** but don't block (Director can override)
- Story scoring runs in parallel with scene processing when possible
- On-demand scoring available for Director review

---

## 5. File-by-File Implementation Plan

### Phase 4.1: Core Models (Low Risk - Additive)

| Step | File | Action |
|------|------|--------|
| 4.1.1 | `models/crew.py` | Add `StoryScore`, `StoryRecommendation`, `RecommendationCategory`, `RevisionPriority` |
| 4.1.2 | `models/crew.py` | Add `StoryScoringContext` dataclass for passing context |

### Phase 4.2: Story Scoring Service (Medium Risk - New Service)

| Step | File | Action |
|------|------|--------|
| 4.2.1 | `services/story_scoring.py` | Create `StoryLevelScoringService` class |
| 4.2.2 | `services/story_scoring.py` | Implement `score_scene()` method |
| 4.2.3 | `services/story_scoring.py` | Implement `score_sequence()` method |
| 4.2.4 | `services/story_scoring.py` | Implement `score_act()` method |
| 4.2.5 | `services/story_scoring.py` | Implement `score_film()` method |

### Phase 4.3: Dimension Analyzers (Medium Risk - New Logic)

| Step | File | Action |
|------|------|--------|
| 4.3.1 | `services/story_scoring.py` | Add `ThesisAlignmentAnalyzer` |
| 4.3.2 | `services/story_scoring.py` | Add `ToneCoherenceAnalyzer` |
| 4.3.3 | `services/story_scoring.py` | Add `CharacterProgressionAnalyzer` |
| 4.3.4 | `services/story_scoring.py` | Add `EmotionalTrajectoryAnalyzer` |
| 4.3.5 | `services/story_scoring.py` | Add `MotifContinuityAnalyzer` |
| 4.3.6 | `services/story_scoring.py` | Add `TensionResolutionAnalyzer` |
| 4.3.7 | `services/story_scoring.py` | Add `OriginalityAnalyzer` |
| 4.3.8 | `services/story_scoring.py` | Add `ContinuityDebtTrajectoryAnalyzer` |

### Phase 4.4: Integration (Medium Risk - Modify Existing)

| Step | File | Action |
|------|------|--------|
| 4.4.1 | `services/agent_executor.py` | Wire story scoring into Director logic (optional input) |
| 4.4.2 | `services/agent_executor.py` | Add story scoring to post-sequence/post-act hooks |
| 4.4.3 | `services/spine_consumption_service.py` | Add `get_story_scoring_context()` method |

### Phase 4.5: Testing (Low Risk - Additive)

| Step | File | Action |
|------|------|--------|
| 4.5.1 | `services/test_story_scoring.py` | Create tests for all analyzers |
| 4.5.2 | `services/test_story_scoring.py` | Create integration tests |

---

## 6. Risks and Mitigation

### High Risk Changes

1. **Performance Impact**: Story scoring on every scene could slow processing
   - **Mitigation**: Make story scoring async/background when possible, cache results

2. **Circular Dependencies**: Story scoring needs outputs from services that depend on scene processing
   - **Mitigation**: Story scoring reads outputs only, doesn't modify them; use cached data

### Medium Risk Changes

1. **Score Subjectivity**: "Originality" and "thesis alignment" are subjective
   - **Mitigation**: Make scoring configurable with weights; Director can adjust

2. **Dimension Overlap**: Scores might overlap with DirectorEvaluator or MemoryArchivistEvaluator
   - **Mitigation**: Clear responsibility boundaries; Story is film-context, others are scene-specific

### Low Risk Changes

1. New models are additive only
2. New service is pure addition
3. Integration points are optional (story scoring doesn't block existing flow)

---

## 7. Backward Compatibility

### Additive Integration Only
- No existing fields modified
- No existing services modified (integration is optional)
- No API changes to existing endpoints
- Story scoring can be disabled via feature flag

### Least Destructive Path
1. Add models without modifying existing
2. Create new service without touching existing
3. Add integration points that don't affect existing flow
4. Make story scoring opt-in per project

---

## 8. Future Compatibility

### Additional Creative Roles
- Story scoring designed to support multiple evaluators
- Can add `StoryScoreFor[Role]` variants if needed
- Framework extensible for new scoring dimensions

### Full Feature Script Ingestion
- Story scoring works with any film structure
- Supports variable act/sequence counts
- No assumptions about traditional 3-act structure

### External Render Validation
- Story scoring outputs are data, not render commands
- Can be extended to validate render output against story scores
- Framework supports future integration points

---

## 9. First Coding Task for Phase 4

**Task**: Create `models/crew.py` additions for StoryScore model

**File**: `studio-backend/app/models/crew.py`

**Action**: Add the following classes at the end of the file (before any final exports):

```python
# Story-Level Scoring Models - Phase 4

class RevisionPriority(str, Enum):
    """Priority level for story-level revision recommendations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationCategory(str, Enum):
    """Categories for story-level recommendations."""
    THESIS_DRIFT = "thesis_drift"
    TONE_SHIFT = "tone_shift"
    CHARACTER_STAGNATION = "character_stagnation"
    EMOTIONAL_FLAT_SPOT = "emotional_flat_spot"
    MOTIF_MISSING_CALLBACK = "motif_missing_callback"
    TENSION_UNDERPAY = "tension_underpay"
    FORMULA_RISK = "formula_risk"
    DEBT_ACCUMULATION = "debt_accumulation"


@dataclass
class StoryRecommendation:
    """A recommendation generated by story-level scoring."""
    category: RecommendationCategory
    priority: RevisionPriority
    description: str
    target_scope: str  # "scene", "sequence", "act", "film"
    specific_scenes: List[str]
    rationale: str
    suggested_fix: Optional[str] = None


@dataclass
class StoryScore:
    """Story-level scoring output for film-aware evaluation."""
    film_id: str
    scope: str  # "scene", "sequence", "act", "film"
    scope_id: Optional[str] = None
    
    # Dimension scores (0.0 to 1.0)
    thesis_alignment: float = 0.0
    tone_coherence: float = 0.0
    character_progression: float = 0.0
    emotional_trajectory: float = 0.0
    motif_continuity: float = 0.0
    tension_resolution_rate: float = 0.0
    originality_score: float = 0.0
    continuity_debt_trajectory: float = 0.0
    
    # Aggregate
    overall_health: float = 0.0
    dimension_weights: Dict[str, float] = field(default_factory=dict)
    
    # Context
    scene_count: int = 0
    act_count: int = 0
    sequence_count: int = 0
    
    # Alerts
    warnings: List[str] = field(default_factory=list)
    recommendations: List[StoryRecommendation] = field(default_factory=list)
    
    # Priority
    revision_priority: RevisionPriority = RevisionPriority.LOW
    
    # Metadata
    timestamp: str = ""
    based_on_scenes: List[str] = field(default_factory=list)
```

**Risk**: Low - purely additive, no existing code modified

**Verification**: Run existing tests to ensure no regressions