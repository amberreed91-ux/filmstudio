# Phase 10: True Co-Director Mode - Architecture Plan

## Executive Summary

Phase 10 transforms the system from a set of independent evaluators into an **active creative collaborator** that challenges weak decisions, proposes stronger alternatives, and maintains session-level awareness. This is NOT autonomous creativity—it is an orchestration layer that leverages existing services with disciplined intervention rules.

**Core Principle**: The Co-Director is a **bounded, advisory orchestration layer**. It reads from canonical sources, invokes existing services, and produces structured creative responses. It does NOT introduce new truth, does NOT mutate FilmLevelMemory or FilmStructure, and does NOT bypass existing evaluators.

---

## 1. What "True Co-Director Mode" Means

### 1.1 Definition

A **Co-Director** is a session-aware orchestration service that:
1. Receives scene/film inputs and existing evaluator outputs
2. Applies disciplined intervention logic to decide: approve, critique, propose, or compare
3. Maintains session context across multiple interactions
4. Produces structured creative responses with clear provenance

### 1.2 Behavioral Contract

| Behavior | Description |
|----------|-------------|
| **Silent on approval** | When DirectorEvaluator approves and no continuity issues exist, the Co-Director stays silent unless explicitly queried |
| **Critiques on revision** | When DirectorEvaluator returns REVISE, the Co-Director provides specific critique grounded in evaluator output |
| **Proposes on rejection** | When DirectorEvaluator returns REJECT, the Co-Director proposes concrete alternatives |
| **Compares on request** | When user requests comparison, the Co-Director evaluates multiple options using existing services |
| **Never contradicts canonical** | All Co-Director outputs reference existing canonical sources (spine, memory, structure) |

### 1.3 Intervention Decision Matrix

| Director Decision | Continuity Report | Co-Director Action |
|-------------------|-------------------|-------------------|
| APPROVE | Clean | Silent (no intervention) |
| APPROVE | Warnings | Note but do not intervene |
| REVISE | Any | Provide critique + specific revision guidance |
| REJECT | Any | Provide critique + alternative proposals |
| Any | Critical alerts | Flag critical issues regardless of approval |

### 1.4 Silence vs. Intervention Rules

**Stay Silent When:**
- Scene is approved and continuity is clean
- User has not requested feedback
- Co-Director confidence is below intervention threshold (0.4)
- Issue is already flagged by existing evaluators

**Intervene When:**
- DirectorEvaluator returns REVISE or REJECT
- Continuity report shows critical alerts
- Scene score is within 0.05 of rejection threshold (marginal cases)
- TasteLearningService indicates a pattern violation
- CinematicLanguageAnalyzer detects restraint violations

---

## 2. Required Additions

### 2.1 New Models

**File**: `studio-backend/app/models/co_director.py`

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class CoDirectorAction(str, Enum):
    """Actions the Co-Director can take"""
    SILENT = "silent"                    # No intervention
    APPROVE = "approve"                  # Affirm the decision
    CRITIQUE = "critique"                # Provide critical feedback
    PROPOSE_ALTERNATIVES = "propose"     # Suggest alternatives
    COMPARE_OPTIONS = "compare"          # Compare multiple directions

class InterventionLevel(str, Enum):
    """How strongly the Co-Director intervenes"""
    NONE = "none"        # Silent
    MINIMAL = "minimal"  # Note only
    MODERATE = "moderate" # Critique with guidance
    STRONG = "strong"    # Propose alternatives

@dataclass
class CoDirectorCritique:
    """A specific critique of a creative decision"""
    dimension: str  # e.g., "visual_coherence", "emotional_consistency"
    finding: str    # What was observed
    concern: str    # Why it matters
    grounded_in: str  # Source: "DirectorEvaluator", "MemoryArchivist", etc.
    confidence: float  # 0.0-1.0

@dataclass
class CoDirectorProposal:
    """A proposed alternative direction"""
    proposal_id: str
    description: str
    rationale: str
    grounded_in: str  # What existing data this builds on
    confidence: float  # 0.0-1.0
    tradeoffs: List[str] = field(default_factory=list)
    alternative_to: Optional[str] = None  # Which rejected element this replaces

@dataclass
class CoDirectorComparison:
    """A comparison of multiple creative options"""
    comparison_id: str
    options: List[Dict[str, Any]]  # Each option with evaluation data
    criteria: List[str]  # What dimensions are being compared
    recommendation: str
    confidence: float

@dataclass
class CoDirectorResponse:
    """Structured response from Co-Director"""
    session_id: str
    scene_id: str
    film_id: str
    
    action: CoDirectorAction
    intervention_level: InterventionLevel
    
    # Grounded outputs (from existing services)
    director_evaluation_summary: Optional[Dict[str, Any]] = None
    continuity_summary: Optional[Dict[str, Any]] = None
    film_intelligence_summary: Optional[Dict[str, Any]] = None
    
    # Co-Director creative outputs
    critiques: List[CoDirectorCritique] = field(default_factory=list)
    proposals: List[CoDirectorProposal] = field(default_factory=list)
    comparisons: Optional[CoDirectorComparison] = None
    
    # Metadata
    confidence: float = 0.0
    grounded_sources: List[str] = field(default_factory=list)
    heuristic_notes: List[str] = field(default_factory=list)
    timestamp: str = ""
    
    # Debug
    intervention_reason: str = ""
    suppressed_reasons: List[str] = field(default_factory=list)  # Why we stayed silent on certain issues

@dataclass
class CoDirectorSession:
    """Session-level context for multi-step collaboration"""
    session_id: str
    film_id: str
    created_at: str
    last_updated: str
    
    # Interaction history
    interaction_count: int = 0
    critiques_offered: int = 0
    proposals_made: int = 0
    
    # Session state
    active_concerns: List[str] = field(default_factory=list)  # Ongoing issues being tracked
    resolved_concerns: List[str] = field(default_factory=list)  # Issues user addressed
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # Learned preferences
    
    # Film state at session start (for comparison)
    initial_scene_states: Dict[str, str] = field(default_factory=dict)
```

### 2.2 New Services

**File**: `studio-backend/app/services/co_director_service.py`

```python
class CoDirectorService:
    """
    Orchestration layer that transforms evaluators into a collaborative co-director.
    
    This service:
    - Reads from canonical sources (FilmLevelMemory, FilmStructure, CreativeSpine)
    - Invokes existing services (DirectorEvaluator, MemoryArchivist, etc.)
    - Applies intervention logic to decide when/how to respond
    - Maintains session context across interactions
    - Produces structured CoDirectorResponse objects
    
    This service does NOT:
    - Introduce new canonical truth
    - Modify FilmLevelMemory or FilmStructure
    - Bypass or override existing evaluators
    - Make autonomous creative decisions
    """
    
    def __init__(
        self,
        director_evaluator: DirectorEvaluator,
        memory_archivist: MemoryArchivistEvaluator,
        film_intelligence: FilmIntelligenceService,
        cinematic_language: CinematicLanguageAnalyzer,
        taste_learning: TasteLearningService,
        storage: Optional[Any] = None
    ):
        pass
    
    def evaluate_scene(
        self,
        scene_data: Dict[str, Any],
        session_id: str,
        film_id: str,
        user_query: Optional[str] = None  # "critique this", "suggest alternatives", etc.
    ) -> CoDirectorResponse:
        """Main entry point for scene evaluation with co-director awareness."""
        pass
    
    def compare_options(
        self,
        options: List[Dict[str, Any]],
        session_id: str,
        criteria: Optional[List[str]] = None
    ) -> CoDirectorComparison:
        """Compare multiple creative options using existing services."""
        pass
    
    def get_session_context(self, session_id: str) -> Optional[CoDirectorSession]:
        """Retrieve session context for multi-step collaboration."""
        pass
    
    def update_session(self, session_id: str, response: CoDirectorResponse) -> None:
        """Update session with new interaction data."""
        pass
```

**File**: `studio-backend/app/services/proposal_engine.py`

```python
class ProposalEngine:
    """
    Generates creative alternatives grounded in existing film data.
    
    This engine:
    - Receives rejected or marginal scene data
    - Analyzes what specifically failed (via DirectorEvaluator pillars)
    - Proposes concrete alternatives based on:
        * FilmIntelligenceService (what similar scenes in the film do)
        * CinematicLanguageAnalyzer (visual alternatives)
        * MemoryArchivist (character/motif continuity)
        * TasteLearningService (user preference patterns)
    - Does NOT generate free-form creative ideas—only grounded alternatives
    
    All proposals are:
    - Labeled with confidence (grounded vs. heuristic)
    - Traced to source data
    - Reversible (user can reject without consequence)
    """
    
    def generate_alternatives(
        self,
        rejected_scene: Dict[str, Any],
        rejection_reasons: List[str],
        film_context: Dict[str, Any]
    ) -> List[CoDirectorProposal]:
        """Generate grounded alternative proposals."""
        pass
```

**File**: `studio-backend/app/services/comparison_engine.py`

```python
class ComparisonEngine:
    """
    Compares multiple creative options using existing evaluation services.
    
    This engine:
    - Takes multiple scene/option candidates
    - Runs each through DirectorEvaluator, MemoryArchivist, etc.
    - Produces structured comparison with recommendation
    
    Does NOT make the final decision—presents comparison for user choice.
    """
    
    def compare(
        self,
        options: List[Dict[str, Any]],
        criteria: List[str],
        film_context: Dict[str, Any]
    ) -> CoDirectorComparison:
        """Compare options and return structured comparison."""
        pass
```

### 2.3 Session Storage

**New Memory Type**: `co_director_session`

```python
# Stored in existing storage infrastructure
CoDirectorSession = {
    "type": "co_director_session",
    "session_id": str,
    "film_id": str,
    "created_at": str,
    "interactions": [...],  # List of CoDirectorResponse summaries
    "active_concerns": [...],
    "user_preferences": {...}
}
```

---

## 3. Collaboration Flow

### 3.1 Standard Scene Evaluation Flow

```
[User Submit Scene/Change]
         │
         ▼
┌─────────────────────────────────────────┐
│     CoDirectorService.evaluate_scene()  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. Load Session Context (if session_id) │
│ 2. Load Film Context (structure, memory,│
│    spine) from canonical sources        │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 2. Invoke Existing Services (parallel): │
│    - DirectorEvaluator.evaluate()       │
│    - MemoryArchivist.analyze()          │
│    - CinematicLanguageAnalyzer.analyze()│
│    - FilmIntelligenceService.analyze()  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 3. Apply Intervention Decision Matrix   │
│    Determine: SILENT / CRITIQUE /       │
│    PROPOSE / COMPARE                    │
└─────────────────────────────────────────┘
         │
         ▼
    ┌────┴────┐
    │         │
[APPROVE]  [REVISE/REJECT]
    │         │
    ▼         ▼
[Check     ┌─────────────────────────────────┐
 user      │ If REVISE:                      │
 query]    │ - Generate critiques            │
    │      │ - Provide revision guidance     │
    ▼      └─────────────────────────────────┘
[If query] │         │
    │      ▼         │
    │  [If REJECT]   │
    │      │         │
    │      ▼         │
    │  ┌─────────────────────────────────┐  │
    │  │ ProposalEngine.generate()       │  │
    │  │ - Grounded alternatives         │  │
    │  │ - Tradeoff analysis             │  │
    │  └─────────────────────────────────┘  │
    │         │                              │
    └─────────┼──────────────────────────────┘
              ▼
┌─────────────────────────────────────────┐
│ 4. Package CoDirectorResponse           │
│    - All grounded outputs               │
│    - All heuristic outputs (labeled)    │
│    - Provenance for every claim         │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│ 5. Update Session Context               │
│    - Record interaction                 │
│    - Update active_concerns             │
│    - Learn from user response           │
└─────────────────────────────────────────┘
              │
              ▼
       [Return to User]
```

### 3.2 Comparison Flow

```
[User Request Comparison]
         │
         ▼
┌─────────────────────────────────────────┐
│  CoDirectorService.compare_options()    │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  ComparisonEngine.compare()             │
│  - Run each option through evaluators   │
│  - Score on common criteria             │
│  - Generate comparison matrix           │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Package CoDirectorComparison           │
│  - Options with scores                  │
│  - Criteria breakdown                   │
│  - Recommendation (with confidence)     │
└─────────────────────────────────────────┘
```

### 3.3 Output Structure

```python
# Standard CoDirectorResponse
{
    "session_id": "sess-123",
    "scene_id": "scene-45",
    "film_id": "film-7",
    
    "action": "critique",  # or "silent", "propose", "compare"
    "intervention_level": "moderate",
    
    # Grounded outputs from existing services
    "director_evaluation": {
        "decision": "REVISE",
        "score": 0.65,
        "pillars": {...},
        "rejection_reasons": [...]
    },
    "continuity_report": {
        "passed": True,
        "alerts": [...]
    },
    "film_intelligence": {
        "sequence_summary": {...},
        "act_summary": {...}
    },
    
    # Co-Director creative outputs
    "critiques": [
        {
            "dimension": "visual_coherence",
            "finding": "Scene uses generic establishing shot",
            "concern": "Doesn't serve narrative or emotional purpose",
            "grounded_in": "CinematicLanguageAnalyzer",
            "confidence": 0.78
        }
    ],
    "proposals": [
        {
            "proposal_id": "prop-1",
            "description": "Replace establishing shot with character-focused insert",
            "rationale": "Tighter visual storytelling; mirrors Act 1 opening",
            "grounded_in": "FilmIntelligenceService (scene-12 pattern)",
            "confidence": 0.72,
            "tradeoffs": ["May require additional coverage"]
        }
    ],
    
    # Metadata
    "confidence": 0.72,
    "grounded_sources": [
        "DirectorEvaluator",
        "CinematicLanguageAnalyzer", 
        "FilmIntelligenceService"
    ],
    "heuristic_notes": [
        "Proposal confidence reduced due to limited similar scenes in film"
    ],
    "timestamp": "2026-04-21T07:00:00Z",
    
    # Debug
    "intervention_reason": "DirectorEvaluator returned REVISE",
    "suppressed_reasons": [
        "Continuity warnings below intervention threshold"
    ]
}
```

---

## 4. How It Uses Existing Systems

### 4.1 DirectorEvaluator (Baseline Judgment)

**Role**: Primary scoring engine for scene quality

**Co-Director Usage**:
- Read `decision`, `score`, `pillars`, `rejection_reasons` from evaluation
- Use decision to drive intervention logic (APPROVE → silent, REVISE/REJECT → intervene)
- Use pillar scores to focus critiques on weakest dimensions
- Use rejection reasons as grounded critique content

**Boundaries**:
- Co-Director does NOT re-score or override DirectorEvaluator scores
- Co-Director does NOT change DirectorEvaluator thresholds
- Co-Director critique is ADDITIVE to DirectorEvaluator output

### 4.2 FilmIntelligenceService (Long-Range Context)

**Role**: Film-scale rollups (sequences, acts, themes, motifs)

**Co-Director Usage**:
- Query `analyze_sequence()` to understand scene's narrative context
- Query `analyze_act()` to understand act-level progression
- Use `setup_payoff_summaries` to identify setup/payoff opportunities
- Use `tension_summaries` to track unresolved threads
- Use `motif_summaries` to inform visual motif proposals

**Boundaries**:
- Co-Director reads only—does NOT modify FilmIntelligenceService outputs
- Proposals referencing film intelligence must cite specific scene/element

### 4.3 MemoryArchivistEvaluator (Continuity Constraints)

**Role**: Long-form continuity protection (tensions, motifs, character states)

**Co-Director Usage**:
- Read `continuity_report.alerts` for critical/warning issues
- Use `tension_updates` to understand what's been introduced/resolved
- Use `motif_references` to inform visual motif proposals
- Use `character_states` to ensure proposals maintain consistency

**Boundaries**:
- Co-Director does NOT modify continuity state
- Co-Director does NOT resolve tensions—only flags them
- Critical alerts trigger Co-Director intervention regardless of approval

### 4.4 CinematicLanguageAnalyzer (Visual Storytelling Critique)

**Role**: Interpretive analysis of visual choices as meaning

**Co-Director Usage**:
- Read `visual_intent_category` to understand if visuals are motivated
- Read `framing_meaning` to critique power/relationship dynamics
- Read `restraint_score` to identify over-direction
- Read `dialogue_substitution_opportunity` to suggest visual storytelling
- Use `motif_evolution_stage` to propose visual callbacks

**Boundaries**:
- Co-Director does NOT re-analyze—uses CinematicLanguageAnalyzer output
- Proposals must be grounded in specific analyzer signals

### 4.5 TasteLearningService (Preference Shaping - Bounded)

**Role**: Record and derive user preference patterns

**Co-Director Usage**:
- Query `derive_project_preference_profile()` to understand user taste
- Use preference profile to:
    - Weight critique dimensions (if user values visual restraint, emphasize that)
    - Generate proposals aligned with known preferences
    - Suppress suggestions that contradict learned preferences
- Record user responses to Co-Director outputs as feedback traces

**Boundaries**:
- TasteLearningService influence is CAPPED (max 0.05 score adjustment)
- Co-Director does NOT let taste learning override grounded evaluator signals
- All taste influence is labeled and auditable

### 4.6 StoryLevelScoringService (Story Health)

**Role**: Story-level scoring beyond scene evaluation

**Co-Director Usage**:
- Read `story_health` for film-level health signals
- Use dimension scores to inform critique focus
- Use `recommendations` as input to proposal generation

**Boundaries**:
- Co-Director does NOT re-score story health
- Co-Director does NOT override story-level recommendations

---

## 5. Grounded vs. Heuristic

### 5.1 Strictly Grounded Elements

These elements come directly from existing services and carry high confidence:

| Element | Source | Confidence |
|---------|--------|------------|
| DirectorEvaluator decision | Direct output | 0.9+ |
| DirectorEvaluator pillar scores | Direct output | 0.85+ |
| MemoryArchivist alerts | Direct output | 0.9+ |
| FilmIntelligence summaries | Derived from canonical | 0.85+ |
| CinematicLanguage signals | Derived from scene data | 0.75-0.85 |
| Continuity state | FilmLevelMemory | 0.95+ |

### 5.2 Heuristic Elements

These elements involve interpretation or generation and must be labeled:

| Element | Type | Confidence | Notes |
|---------|------|------------|-------|
| Critique concerns | Inferred from grounded data | 0.6-0.8 | Labeled with reasoning |
| Alternative proposals | Generated from patterns | 0.5-0.75 | Labeled with source pattern |
| Comparison recommendations | Aggregated scores | 0.6-0.8 | Labeled with criteria |
| Session-level concerns | Inferred from history | 0.4-0.7 | Labeled with evidence |

### 5.3 Confidence and Provenance Exposure

Every Co-Director output includes:

```python
{
    "confidence": 0.72,  # Overall confidence
    
    # Per-element provenance
    "grounded_sources": [
        "DirectorEvaluator",
        "MemoryArchivistEvaluator", 
        "CinematicLanguageAnalyzer"
    ],
    
    # Heuristic labeling
    "heuristic_notes": [
        "Proposal confidence reduced due to limited similar scenes",
        "Critique concern is inferred, not directly stated by evaluator"
    ],
    
    # Per-critique provenance
    "critiques": [{
        "dimension": "visual_coherence",
        "grounded_in": "CinematicLanguageAnalyzer.restraint_score",
        "confidence": 0.78
    }]
}
```

---

## 6. Safety Constraints

### 6.1 Prevent Over-Intervention

| Constraint | Mechanism |
|------------|-----------|
| Maximum interventions per session | 10 per scene per session |
| Minimum score delta for critique | 0.1 below threshold |
| Silent on approval unless queried | Action matrix enforces this |
| Suppressed reasons logged | `suppressed_reasons` field |

### 6.2 Prevent Noisy Suggestions

| Constraint | Mechanism |
|------------|-----------|
| Confidence threshold for proposals | Only propose if confidence >= 0.5 |
| Maximum proposals per response | 3 alternatives max |
| Proposals must cite source | `grounded_in` field required |
| Tradeoffs must be listed | `tradeoffs` field required |

### 6.3 Prevent Contradiction with Canonical Film Memory

| Constraint | Mechanism |
|------------|-----------|
| All proposals checked against FilmLevelMemory | Validation step before returning |
| Character state consistency enforced | MemoryArchivist state used as constraint |
| Motif proposals verified | MotifRegistry consulted |
| Taste learning cannot override canonical | Capped influence, labeled |

### 6.4 Auditable and Reversible

| Requirement | Implementation |
|-------------|----------------|
| All decisions logged | Session stores every CoDirectorResponse |
| User can reject proposals | No canonical mutation on proposal |
| Proposal history tracked | `proposals_made` counter in session |
| Intervention history tracked | `critiques_offered` counter in session |
| User can undo feedback | TasteLearningService supports trace deletion |

---

## 7. Implementation Roadmap

### Phase 10.1: Foundation (Models + Services Only)

**Goal**: Create core infrastructure without integration

**Tasks**:
- [ ] Create `models/co_director.py` with all dataclasses
- [ ] Create `services/proposal_engine.py` (stub implementation)
- [ ] Create `services/comparison_engine.py` (stub implementation)
- [ ] Create `services/co_director_service.py` (minimal: session storage only)
- [ ] Write unit tests for models

**Deliverable**: Core types exist, no integration yet

### Phase 10.2: Read-Only Exposure

**Goal**: Co-Director reads existing services but produces no creative output

**Tasks**:
- [ ] Integrate DirectorEvaluator into CoDirectorService
- [ ] Integrate MemoryArchivistEvaluator into CoDirectorService
- [ ] Integrate FilmIntelligenceService into CoDirectorService
- [ ] Implement `evaluate_scene()` that packages existing outputs
- [ ] Add session context loading/saving
- [ ] Write integration tests

**Deliverable**: Co-Director packages existing evaluator outputs in CoDirectorResponse format

### Phase 10.3: Debug Visibility

**Goal**: Make Co-Director decision process transparent

**Tasks**:
- [ ] Add `intervention_reason` to all responses
- [ ] Add `suppressed_reasons` for silent decisions
- [ ] Add per-element provenance tracking
- [ ] Create debug endpoint: `GET /co-director/debug/{session_id}`
- [ ] Log all intervention decisions
- [ ] Write debug visibility tests

**Deliverable**: Full audit trail of Co-Director decisions

### Phase 10.4: Bounded Intervention

**Goal**: Co-Director can critique and propose, within safety constraints

**Tasks**:
- [ ] Implement intervention decision matrix
- [ ] Implement critique generation from evaluator outputs
- [ ] Implement ProposalEngine.generate_alternatives()
- [ ] Add confidence thresholds for proposals
- [ ] Add maximum intervention limits
- [ ] Implement ComparisonEngine.compare()
- [ ] Write intervention tests

**Deliverable**: Co-Director can critique and propose with safety constraints

### Phase 10.5: Taste Learning Integration

**Goal**: Co-Director learns from user feedback within bounds

**Tasks**:
- [ ] Integrate TasteLearningService for preference shaping
- [ ] Record user responses to Co-Director outputs
- [ ] Apply taste influence to proposal ranking
- [ ] Add taste influence to response metadata
- [ ] Write taste integration tests

**Deliverable**: Co-Director adapts to user preferences within bounds

---

## 8. First Coding Task (Do Not Implement)

### Smallest Safe Starting Point for Phase 10

**Task**: Create Phase 10.1 Foundation - Models Only

**Rationale**: Starting with models is safe because:
1. No integration risk—models don't affect runtime
2. Establishes types before services depend on them
3. Can be tested in isolation
4. No risk of mutating canonical state

**Specific Deliverables**:

1. **File**: `studio-backend/app/models/co_director.py`
   - `CoDirectorAction` enum
   - `InterventionLevel` enum
   - `CoDirectorCritique` dataclass
   - `CoDirectorProposal` dataclass
   - `CoDirectorComparison` dataclass
   - `CoDirectorResponse` dataclass
   - `CoDirectorSession` dataclass

2. **File**: `studio-backend/app/services/test_co_director_models.py`
   - Test all dataclass serialization
   - Test enum values
   - Test default values
   - Test field constraints

**Why This Is Safe**:
- No existing code depends on these models yet
- No integration with existing services
- No mutation of canonical state
- Pure type definition with basic serialization tests

**Next Steps After Models**:
- Phase 10.2 would add CoDirectorService stub that reads existing services
- Phase 10.3 would add debug visibility
- Phase 10.4 would add intervention logic
- Phase 10.5 would add taste learning

---

## 9. Summary

Phase 10 transforms the system into a true co-director by:

1. **Orchestrating existing services** rather than replacing them
2. **Applying disciplined intervention rules** rather than unbounded creativity
3. **Maintaining session awareness** for multi-step collaboration
4. **Labeling all outputs** as grounded or heuristic with provenance
5. **Enforcing safety constraints** to prevent over-intervention and noise
6. **Keeping all behavior auditable and reversible**

The Co-Director is NOT:
- An autonomous creative agent
- A replacement for DirectorEvaluator or other services
- A source of new canonical truth
- A free-form idea generator

The Co-Director IS:
- A bounded, advisory orchestration layer
- A disciplined collaborator that knows when to speak and when to stay silent
- A package of existing evaluator insights with creative additions
- A session-aware service that learns from interaction history