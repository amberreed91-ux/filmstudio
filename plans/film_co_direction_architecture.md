# Film Co-Direction System Architecture Plan

## Executive Summary

The existing AI Film Studio codebase is a scene-based generation system with solid foundations for adaptation, memory, conflict resolution, and multi-agent execution. It lacks **film-level consciousness**—the ability to understand and govern a complete narrative arc across scenes, acts, and sequences.

**Target State**: Extend from scene-based to film-aware co-direction with:
- Full screenplay ingestion (film → act → sequence → scene → beat)
- Layered film memory hierarchy
- Creative spine governing tone, motifs, character arcs
- Distinct agent roles with productive disagreement
- Story-level scoring beyond scene-level evaluation

**This is an extension, not a rebuild.** All existing systems remain intact.

---

## 1. Existing Architecture Audit

### 1.1 Core Services (What Exists)

| Service | File | Purpose | Film-Level Awareness |
|---------|------|---------|---------------------|
| **ScriptParser** | `services/script_parser.py` | Parses screenplay text into scenes, characters, locations | Scene-level only |
| **SceneEvolution** | `services/scene_evolution.py` | Tracks scene iterations, quality, alignment | Scene-level only |
| **Adaptation** | `services/adaptation.py` | Weighted pattern memory, context relevance | Scene-level only |
| **Memory** | `services/memory.py` | Project/scene/character/style memory with versioning | Partial (no act/sequence) |
| **AuthorityHierarchy** | `services/authority_hierarchy.py` | Decision priority system | Generic |
| **Conflicts** | `services/conflicts.py` | Agent disagreement resolution | Generic creative |
| **AgentExecutor** | `services/agent_executor.py` | Autonomous agent loop execution | Task-based |
| **CrewService** | `services/crew.py` | Task management, agent coordination | Task-based |

### 1.2 Data Models (What Exists)

| Model | File | Coverage |
|-------|------|----------|
| `Scene` | `script_parser.py` | scene_id, heading, int_ext, location, time_of_day, description, characters, dialogue |
| `Character` | `script_parser.py` | character_id, name, normalized_name, first_appearance, dialogue_count |
| `Location` | `script_parser.py` | location_id, name, int_ext, scenes |
| `SceneContext` | `scene_evolution.py` | scene_type, emotion, visual_goal, genre, emotional_goal, time_of_day, location_type, pacing, lighting_quality, color_palette |
| `SceneIteration` | `scene_evolution.py` | iteration data with quality_score, intent_alignment_score, patterns_used, scene_intent |
| `SceneEvolution` | `scene_evolution.py` | Full evolution history per scene |
| `ProjectEvolution` | `scene_evolution.py` | Project-level summary |
| `ProjectMemory` | `models/memory.py` | tone, genre, visual_style, color_grade, characters, scenes |
| `CharacterMemory` | `models/memory.py` | appearance, personality, speech, mannerisms, relationships |
| `SceneMemory` | `models/memory.py` | location, time, weather, camera, lighting, props |
| `StyleMemory` | `models/memory.py` | camera_language, lighting_approach, pacing_notes |
| `SceneIntent` | `authority_hierarchy.py` | scene_type, emotion, genre, visual_goal, emotional_goal, pacing, intensity, is_turning_point, narrative_beat |

### 1.3 Agent Roles (What Exists)

Current roles in `models/crew.py`:
- `PRODUCER` - Task coordination
- `RENDER_COORDINATOR` - Job management
- `SCRIPT_ANALYST` - Parse and structure
- `STORYBOARD_ARTIST` - Visual layout
- `CINEMATOGRAPHER` - Camera specs
- `PROMPT_ENGINEER` - Prompt optimization
- `EDITOR` - Sequence assembly
- `CONTINUITY_SUPERVISOR` - Validation
- `QUALITY_REVIEWER` - Automated checks
- `SYSTEM_ORCHESTRATOR` - Workflow management

**Gap**: No distinct creative roles (Director, Writer/Dramaturg, Critic) with authority to make or contest creative decisions.

---

## 2. Gap Analysis

### 2.1 Screenplay Ingestion

| Requirement | Status | Gap |
|-------------|--------|-----|
| Film-level structure | ❌ None | No Film/Act/Sequence container |
| Scene parsing | ✅ Exists | `ScriptParser` works at scene level |
| Beat detection | ❌ None | No beat/beat sheet extraction |
| Character arc extraction | ⚠️ Partial | `CharacterMemory` exists but no arc tracking |
| Relationship arc tracking | ⚠️ Partial | `relationships: Dict[str, str]` exists but no arc evolution |
| Motif registry | ❌ None | No recurring object/symbol tracking |
| Thematic signal extraction | ❌ None | No theme analysis |
| Tone shift detection | ⚠️ Partial | `SceneContext.emotion` exists but no film-level trend |
| Pacing analysis | ⚠️ Partial | `SceneContext.pacing` exists but no sequence-level pacing |
| Emotional escalation tracking | ❌ None | No arc-level emotional trajectory |

### 2.2 Film Memory Hierarchy

| Level | Status | Gap |
|-------|--------|-----|
| Film memory | ⚠️ Partial | `ProjectMemory` exists but no act/sequence containers |
| Act memory | ❌ None | No act-level memory structure |
| Sequence memory | ❌ None | No sequence-level memory structure |
| Scene memory | ✅ Exists | `SceneMemory` |
| Iteration memory | ✅ Exists | `SceneIteration` |
| Inheritance | ❌ None | No propagation of film/act/sequence context to scenes |

### 2.3 Creative Spine

| Component | Status | Gap |
|-----------|--------|-----|
| Story thesis | ❌ None | No thesis/governing question storage |
| Emotional contract | ❌ None | No audience emotional journey tracking |
| Genre lane | ⚠️ Partial | `genre` field exists but no genre rules/constraints |
| Visual philosophy | ⚠️ Partial | `visual_goal` exists but no film-wide visual thesis |
| Pacing philosophy | ❌ None | No governing pacing principles |
| Motif registry | ❌ None | No tracked motifs/symbols |
| Character maps | ⚠️ Partial | `CharacterMemory` exists but no wound/desire/fear/contradiction |
| Restraint rules | ❌ None | No "what not to do" governing constraints |

### 2.4 Agent Role Separation

| Requirement | Status | Gap |
|-------------|--------|-----|
| Director role | ❌ None | No creative authority role |
| Writer/Dramaturg role | ❌ None | No story structure authority |
| Critic role | ⚠️ Partial | `QualityReviewer` exists but no creative criticism |
| Memory archivist | ⚠️ Partial | `MemoryService` exists but no film-level consciousness |
| Productive disagreement | ⚠️ Partial | `Conflicts` service exists but no creative conflict types |
| Conflict resolution | ⚠️ Partial | Authority-based but not creative-principle-based |

### 2.5 Story-Level Scoring

| Criterion | Status | Gap |
|-----------|--------|-----|
| Scene quality | ✅ Exists | `quality_score`, `intent_alignment_score` |
| Thesis alignment | ❌ None | No story-level evaluation |
| Tone coherence | ⚠️ Partial | Per-scene emotion tracking, no film-level coherence |
| Character progression | ❌ None | No arc integrity scoring |
| Emotional authenticity | ❌ None | No authenticity evaluation |
| Thematic reinforcement | ❌ None | No theme tracking |
| Motif continuity | ❌ None | No motif tracking |
| Originality vs formula | ❌ None | No formula detection |
| Restraint/ambiguity | ❌ None | No restraint evaluation |
| Scene belonging | ❌ None | No "does this scene belong to this film" evaluation |

---

## 3. Target Architecture

### 3.1 Film Structure Hierarchy

```
Film
├── Acts[]
│   ├── Act 1 (Setup)
│   ├── Act 2 (Confrontation)  
│   └── Act 3 (Resolution)
├── Sequences[]
│   └── Sequence (3-5 scenes, mini-arc)
└── Scenes[]
    └── Scene (with Beats[])
```

**New Classes**:
- `FilmStructure` - Top-level container with acts, sequences
- `Act` - act_number, act_type, start_scene, end_scene, thematic_focus
- `Sequence` - sequence_id, act_number, start_scene, end_scene, sequence_goal
- `Beat` - beat_type, scene_position, emotional_shift, purpose

### 3.2 Film Memory Hierarchy

```
FilmMemory (extends existing ProjectMemory)
├── film_level: FilmLevelMemory
│   ├── thesis
│   ├── emotional_contract
│   ├── genre_lane
│   ├── visual_philosophy
│   ├── pacing_philosophy
│   ├── motif_registry[]
│   ├── symbol_registry[]
│   └── restraint_rules[]
├── acts: Dict[int, ActMemory]
├── sequences: Dict[str, SequenceMemory]
└── scenes: Dict[str, SceneMemory] (existing)

CharacterMemory (extends existing)
├── wound
├── desire
├── fear
├── contradiction
└── arc_history: List[ArcPoint]
```

### 3.3 Creative Spine Components

```python
class CreativeSpine:
    """Governing creative layer for the entire film"""
    
    # Core thesis
    story_thesis: str  # One-sentence governing question
    thematic_statements: List[str]  # 3-5 key themes
    
    # Emotional contract
    emotional_contract: EmotionalContract
    #   - opening_state: emotional baseline
    #   - journey_through: list of emotional beats
    #   - closing_state: emotional destination
    
    # Style guardrails
    genre_lane: GenreLane
    #   - genre_tags
    #   - conventions_to_honor
    #   - conventions_to_subvert
    
    visual_philosophy: VisualPhilosophy
    #   - visual_thesis
    #   - camera_principles
    #   - color_approach
    #   - lighting_philosophy
    
    pacing_philosophy: PacingPhilosophy
    #   - rhythm_statement
    #   - tempo_curve  # Scene-by-scene pacing target
    #   - restraint_principles
    
    # Tracking
    motif_registry: List[Motif]
    #   - name, first_appearance, recurrences[], visual_description
    
    symbol_registry: List[Symbol]
    #   - name, associated_theme, visual_form, occurrences[]
    
    # Character psychology
    character_maps: Dict[str, CharacterMap]
    #   - wound, desire, fear, contradiction per character
    
    # Restraint rules
    restraint_rules: List[RestraintRule]
    #   - rule: what not to do
    #   - reason: why it's wrong for THIS film
    #   - alternatives: what to do instead
```

### 3.4 Agent Role Mapping

| Current Role | New Creative Role | Authority |
|--------------|-------------------|-----------|
| SYSTEM_ORCHESTRATOR | System Orchestrator | Workflow only |
| (new) | **Creative Director** | Final creative authority, can override all |
| (new) | **Dramaturg** | Story structure, arc integrity, thematic coherence |
| SCRIPT_ANALYST | Script Analyst (enhanced) | Technical parsing, beat detection |
| CINEMATOGRAPHER | Cinematographer | Visual philosophy adherence |
| EDITOR | Editor | Pacing, rhythm, sequence construction |
| (new) | **Critic** | Quality review + creative critique + formula detection |
| QUALITY_REVIEWER | Quality Reviewer | Technical quality only |
| CONTINUITY_SUPERVISOR | Continuity Supervisor | Factual consistency |
| STORYBOARD_ARTIST | Storyboard Artist | Visual layout |
| PROMPT_ENGINEER | Prompt Engineer | Technical prompt execution |
| PRODUCER | Producer | Resource/logistics |
| RENDER_COORDINATOR | Render Coordinator | Technical |
| (new) | **Memory Archivist** | Film-level memory coherence |

### 3.5 Conflict Resolution Enhancement

```python
class CreativeConflict(BaseModel):
    """Conflict driven by creative principles, not just authority"""
    conflict_type: CreativeConflictType
    # CREATIVE_VISION, TONE_BREAK, PACING_VIOLATION, 
    # CHARACTER_INTEGRITY, THEME_MISALIGNMENT, RESTRAINT_BREAK
    
    severity: CreativeSeverity  # MINOR, MODERATE, MAJOR, DEALBREAKER
    
    conflicting_agents: List[AgentRole]
    
    principle_in_dispute: str  # Which creative principle
    
    # Resolution options
    resolution_paths: List[ResolutionPath]
    #   - path: description
    #   - wins: which side
    #   -代价: what is lost
    
    escalated_to: Optional[CreativeRole]  # Dramaturg, Director
```

### 3.6 Story-Level Scoring

```python
class StoryScore:
    """Film-aware evaluation beyond scene level"""
    
    # Alignment scores (0.0 - 1.0)
    thesis_alignment: float
    tone_coherence: float
    character_progression_integrity: float
    emotional_authenticity: float
    thematic_reinforcement: float
    motif_continuity: float
    
    # Risk scores
    originality_vs_formula_risk: float  # High formula = bad
    restraint_preservation: float  # Ambiguity preserved = good
    belonging_score: float  # Does scene belong to THIS film
    
    # Component scores
    pacing_score: float
    visual_consistency: float
    dialogue_authenticity: float
    
    # Aggregates
    overall_health: float  # Weighted composite
    warnings: List[str]  # Specific concerns
```

---

## 4. File-by-File Implementation Plan

### Phase 1: Foundation (Film Structure + Ingestion)

| Step | File | Action | Risk |
|------|------|--------|------|
| 1.1 | `models/crew.py` | Add `FilmStructure`, `Act`, `Sequence`, `Beat` classes | Low - additive only |
| 1.2 | `models/memory.py` | Add `FilmLevelMemory`, `ActMemory`, `SequenceMemory` | Low - additive only |
| 1.3 | `services/script_parser.py` | Extend to detect acts (INT./EXT. acts), sequences, beats | Medium - modify existing parsing |
| 1.4 | `services/crew.py` | Add `FilmStructureService` to manage structure | Low - new service |

### Phase 2: Creative Spine

| Step | File | Action | Risk |
|------|------|--------|------|
| 2.1 | `models/memory.py` | Add `CreativeSpine`, `Motif`, `Symbol`, `CharacterMap`, `RestraintRule` | Low - additive only |
| 2.2 | `services/memory.py` | Add `CreativeSpineService` to manage spine | Low - new service |
| 2.3 | `services/memory.py` | Extend `CharacterMemory` with arc tracking | Low - extend existing |
| 2.4 | `services/crew.py` | Add `ToneBibleGenerator` to extract tone from script | Medium - new logic |

### Phase 3: Agent Enhancement

| Step | File | Action | Risk |
|------|------|--------|------|
| 3.1 | `models/crew.py` | Add `CreativeDirector`, `Dramaturg`, `Critic`, `MemoryArchivist` roles | Low - additive only |
| 3.2 | `services/conflicts.py` | Add `CreativeConflict` types and resolution | Medium - extend existing |
| 3.3 | `services/authority_hierarchy.py` | Add creative authority levels | Medium - modify existing |
| 3.4 | `services/crew.py` | Add role-specific handlers for new roles | Low - additive only |

### Phase 4: Story-Level Scoring

| Step | File | Action | Risk |
|------|------|--------|------|
| 4.1 | `models/crew.py` | Add `StoryScore` class | Low - additive only |
| 4.2 | `services/scene_evolution.py` | Add `StoryScoringService` for film-aware evaluation | Medium - new service |
| 4.3 | `services/scene_evolution.py` | Extend `SceneEvolutionTracker` with story-level metrics | Medium - extend existing |
| 4.4 | `services/adaptation.py` | Integrate story scoring into pattern boost | Low - additive parameter |

### Phase 5: Integration

| Step | File | Action | Risk |
|------|------|--------|------|
| 5.1 | `services/agent_executor.py` | Wire new services into agent loop | Medium - modify existing |
| 5.2 | `services/memory.py` | Ensure memory propagation film→act→sequence→scene | Medium - modify existing |
| 5.3 | `services/crew.py` | Add film-level tasks to task types | Low - additive only |
| 5.4 | `routes/crew.py` | Add film-level API endpoints | Low - additive only |

---

## 5. Risks and Regression Concerns

### High Risk Changes
1. **`script_parser.py` modifications** - Could break existing scene parsing. Mitigation: Keep backward compatibility, add new methods alongside existing.

2. **`scene_evolution.py` extensions** - Existing scene iteration tracking must remain functional. Mitigation: Additive changes only, no modification of existing `SceneIteration` structure.

3. **`memory.py` model changes** - Existing memory structures are persisted. Mitigation: Add new optional fields with defaults, never remove existing fields.

### Medium Risk Changes
1. **Agent role additions** - New roles must not conflict with existing task assignment. Mitigation: New roles handle new task types only.

2. **Conflict resolution extensions** - Existing conflict handling must remain. Mitigation: New `CreativeConflict` types handled by new resolver, existing paths unchanged.

3. **Authority hierarchy modifications** - Existing priority order must hold. Mitigation: Add new authority levels above/below existing, don't reorder.

### Low Risk Changes
1. New services (`FilmStructureService`, `CreativeSpineService`, `StoryScoringService`) - Pure additions.

2. New API endpoints - Additive only.

3. New data models - Additive only.

---

## 6. Recommended Implementation Order

```
Phase 1: Film Structure Foundation
├── 1.1 Add film structure models
├── 1.2 Add film memory models  
├── 1.3 Extend script parser for act/sequence/beat
└── 1.4 Create FilmStructureService

Phase 2: Creative Spine
├── 2.1 Add creative spine models
├── 2.2 Create CreativeSpineService
├── 2.3 Extend character memory with arcs
└── 2.4 Build ToneBibleGenerator

Phase 3: Agent Enhancement
├── 3.1 Add new creative roles
├── 3.2 Extend conflict types
├── 3.3 Add creative authority levels
└── 3.4 Add role handlers

Phase 4: Story Scoring
├── 4.1 Add StoryScore model
├── 4.2 Create StoryScoringService
├── 4.3 Extend SceneEvolutionTracker
└── 4.4 Integrate with adaptation

Phase 5: Integration
├── 5.1 Wire into agent executor
├── 5.2 Memory propagation
├── 5.3 Film-level tasks
└── 5.4 API endpoints
```

---

## 7. First Coding Task (Do Not Execute Yet)

**Task**: Implement Phase 1.1 - Add film structure models

**Files to modify**:
- `studio-backend/app/models/crew.py`

**New classes to add**:
```python
class BeatType(str, Enum):
    """Types of dramatic beats"""
    OPENING = "opening"
    INCITING = "inciting"
    RISING = "rising"
    CLIMAX = "climax"
    FALLING = "falling"
    RESOLUTION = "resolution"
    THEME_STATEMENT = "theme_statement"
    CHARACTER = "character"
    PLOT = "plot"
    EMOTIONAL = "emotional"

class Beat(BaseModel):
    """A single dramatic beat within a scene"""
    beat_id: str
    beat_type: BeatType
    scene_id: str
    position_in_scene: float  # 0.0 - 1.0
    description: str
    emotional_shift: str
    purpose: str  # setup, complication, revelation, etc.

class Sequence(BaseModel):
    """A sequence of scenes with a mini-arc (3-5 scenes)"""
    sequence_id: str
    act_number: int
    sequence_number: int
    start_scene_index: int
    end_scene_index: int
    sequence_goal: str
    mini_thesis: str
    scenes: List[str] = []  # scene_ids
    beats: List[Beat] = []
    emotional_trajectory: List[str] = []  # emotional states through sequence

class ActType(str, Enum):
    SETUP = "setup"  # Act 1
    CONFRONTATION = "confrontation"  # Act 2
    RESOLUTION = "resolution"  # Act 3

class Act(BaseModel):
    """An act containing multiple sequences"""
    act_number: int
    act_type: ActType
    start_scene_index: int
    end_scene_index: int
    thematic_focus: str
    sequences: List[Sequence] = []
    emotional_contract: str  # What emotional state should audience feel

class FilmStructure(BaseModel):
    """Complete film structure hierarchy"""
    film_id: str
    title: str = ""
    total_scenes: int = 0
    
    # Hierarchy
    acts: List[Act] = []
    all_sequences: List[Sequence] = []  # Flattened for easy access
    all_beats: List[Beat] = []
    
    # Metadata
    estimated_runtime_minutes: int = 0
    pacing_profile: str = ""  # slow_burn, balanced, accelerated, etc.
    
    # Character presence tracking
    character_scenes: Dict[str, List[str]] = {}  # character_id -> scene_ids
    
    # Tone tracking
    tone_shifts: List[Dict] = []  # {scene_index, from_tone, to_tone, trigger}
```

**Backward compatibility**: All existing code in `crew.py` remains unchanged. New classes are purely additive.

**Test approach**: Add unit tests for `FilmStructure` parsing and hierarchy validation.

---

## 8. Summary Status Table

| Component | Already Exists | Partially Exists | Must Be Built |
|-----------|---------------|------------------|---------------|
| Screenplay ingestion | Scene parsing | Beat detection, motif tracking | Act/sequence structure, thematic extraction |
| Film memory hierarchy | Scene memory | Project memory | Act/sequence memory, inheritance |
| Creative spine | Scene intent | Visual goals | Thesis, motifs, symbols, restraints |
| Agent roles | Task agents | Quality reviewer | Director, dramaturg, critic, archivist |
| Story scoring | Scene quality | Tone tracking | Thesis alignment, character arcs, formula detection |
| Conflict resolution | Authority-based | Creative fields | Creative principle-based |