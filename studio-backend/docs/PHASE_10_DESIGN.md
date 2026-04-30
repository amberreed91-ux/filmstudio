# Phase 10 Design: True Co-Director Mode

## 1. Executive Summary

**What It Is:**
A collaborative orchestration layer that actively challenges weak creative decisions, proposes stronger alternatives, compares options, and guides the creative process—while preserving the existing bounded architecture.

**What It Is NOT:**
- A replacement for existing evaluators
- A new source of canonical truth
- An autonomous decision-maker
- A noisy assistant that speaks on every input

**Core Design Principle:**
The Co-Director is a **collaborative intelligence**—it works *with* the DirectorEvaluator, MemoryArchivistEvaluator, and all existing services, synthesizing their insights into actionable creative guidance. It amplifies human judgment, never replaces it.

---

## 2. Co-Director Responsibilities

### 2.1 What "True Co-Director Mode" Means

| Capability | Definition |
|------------|------------|
| **Active Pushback** | The system challenges weak decisions directly when evidence is grounded—not vague disagreement, but specific critique tied to scoring pillars, rejection rules, or continuity alerts. |
| **Alternative Proposal** | When a decision fails evaluation, the system suggests stronger alternatives grounded in film intelligence patterns, taste calibration, and cinematic language analysis. |
| **Comparative Judgment** | The system ranks creative options (render choices, revision approaches) using existing validation and comparison services, surfacing tradeoffs rather than declaring winners. |
| **Session-Level Collaboration** | The system tracks creative health across a film session, adapting its intervention intensity based on cumulative feedback and acceptance patterns. |
| **Unified Orchestration** | The Co-Director synthesizes insights from all existing services into coherent, actionable guidance without creating parallel evaluation paths. |

### 2.2 Co-Director Modes

```
┌─────────────────────────────────────────────────────────────┐
│                    CO-DIRECTOR MODE                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PASSIVE MODE (default)                                     │
│  ├── Monitors evaluation outputs silently                    │
│  ├── Logs insights for session awareness                    │
│  └── Only speaks when explicitly triggered                  │
│                                                             │
│  ADVISORY MODE                                              │
│  ├── Surfaces critiques after failed evaluations           │
│  ├── Proposes alternatives with confidence thresholds      │
│  ├── Compares options when multiple exist                   │
│  └── User retains full decision authority                   │
│                                                             │
│  COLLABORATIVE MODE (opt-in)                                │
│  ├── Actively monitors continuity health                    │
│  ├── Proposes proactive improvements (sparingly)           │
│  ├── Tracks acceptance/rejection patterns                   │
│  └── Adapts intervention intensity based on feedback        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. What to Add and What Not to Add

### 3.1 NEW Components

#### Models (app/models/)

| Model | Purpose | Canonical? |
|-------|---------|------------|
| `CoDirectorSession` | Tracks session-level context, intervention history, and acceptance patterns | No (session-scoped, transient) |
| `CreativeCritique` | Structured critique with grounded evidence, confidence, and provenance | No (derived, advisory) |
| `CreativeProposal` | Alternative proposal with original decision, suggested alternatives, ranking rationale | No (derived, advisory) |
| `CoDirectorContext` | Session context passed to Co-Director operations | No (derived) |
| `InterventionPolicy` | Configures when/how the Co-Director intervenes | No (configuration) |

#### Services (app/services/)

| Service | Responsibility |
|---------|----------------|
| `CoDirectorOrchestrator` | Central service that synthesizes existing service outputs into Co-Director actions |
| `CritiqueGenerationService` | Generates grounded critiques from DirectorEvaluator and MemoryArchivistEvaluator outputs |
| `ProposalGenerationService` | Generates alternative proposals from film intelligence and cinematic language patterns |
| `CoDirectorSessionManager` | Manages session state, tracks intervention history, calculates intervention intensity |
| `CreativeComparisonService` | Orchestrates option comparison using RenderComparisonService |

### 3.2 What NOT to Add

| Forbidden Addition | Reason |
|-------------------|--------|
| Duplicate evaluation logic | Reuse DirectorEvaluator/MemoryArchivistEvaluator directly |
| New canonical truth sources | FilmLevelMemory, FilmStructure, CreativeSpine remain the only sources of truth |
| Hidden threshold modifications | No changes to APPROVE_THRESHOLD, REVISE_THRESHOLD, or any scoring thresholds |
| Autonomous looping | Single-pass critique cycles; no self-triggering chains |
| Silent mutations | All influence must be explicit and overridable |

### 3.3 Additive Architecture Map

```
┌────────────────────────────────────────────────────────────────────┐
│                    PHASE 10: CO-DIRECTOR                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   ┌─────────────┐     ┌──────────────────┐     ┌───────────────┐   │
│   │ Canonical   │     │  Derived Layers  │     │ Co-Director  │   │
│   │ Sources     │────▶│ (Existing Phases │────▶│ New Layer    │   │
│   └─────────────┘     │  1-9)            │     └───────────────┘   │
│                       └──────────────────┘              │          │
│                              │                          │          │
│                              ▼                          ▼          │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │               EXISTING SERVICES (READ-ONLY)                 │  │
│   │  DirectorEvaluator │ MemoryArchivist │ StoryScoring       │  │
│   │  FilmIntelligence   │ TasteLearning   │ CinematicLanguage  │  │
│   │  ScenePackage       │ RenderValidation│ RenderComparison    │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                              │                                     │
│                              ▼                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │          CO-DIRECTOR SERVICES (NEW - ADVISORY ONLY)          │  │
│   │  CoDirectorOrchestrator │ CritiqueGen │ ProposalGen        │  │
│   │  SessionManager          │ Comparison                        │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                              │                                     │
│                              ▼                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │              USER INTERFACE (DECISION RETAINS AUTHORITY)     │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Relationship to Existing Systems

### 4.1 Read-Only Integration Pattern

| Existing Service | Co-Director Usage | Integration Type |
|------------------|-------------------|------------------|
| **DirectorEvaluator** | Source for rejection reasons, scoring pillar weaknesses, revision notes | Direct call |
| **MemoryArchivistEvaluator** | Source for continuity alerts (CRITICAL/WARNING), character inconsistencies | Direct call |
| **StoryLevelScoringService** | Source for story dimension scores, revision priorities | Direct call |
| **FilmIntelligenceService** | Source for film-scale insights, tension/motif status, arc progression | Direct call |
| **TasteLearningService** | Source for proposal style calibration (subtext preference, visual restraint) | Direct call |
| **CinematicLanguageAnalyzer** | Source for visual opportunities (substitution potential, restraint moments) | Direct call |
| **ScenePackageService** | Source for package context when evaluating renders | Direct call |
| **RenderValidationService** | Input for comparison service | Direct call |
| **RenderComparisonService** | Source for option ranking when comparing renders | Direct call |

### 4.2 Data Flow: Critique Generation

```
Scene Input
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  CoDirectorOrchestrator.evaluate(scene_data)                │
└─────────────────────────────────────────────────────────────┘
    │
    ├──────────────────────────────────────┐
    ▼                                      ▼
┌─────────────────┐              ┌─────────────────────────┐
│DirectorEvaluator│              │MemoryArchivistEvaluator │
│  .evaluate()    │              │  .evaluate_scene()      │
└─────────────────┘              └─────────────────────────┘
    │                                      │
    │ rejection_reasons                   │ alerts (CRITICAL/WARNING)
    │ pillar scores                        │
    │ revision_notes                       │
    ▼                                      ▼
┌─────────────────────────────────────────────────────────────┐
│  CritiqueGenerationService.synthesize()                    │
│  - Grounds critique in: rejection_reasons, pillar scores    │
│  - Flags urgency based on: alert severity, score thresholds │
│  - Labels confidence: GROUNDED (instant rules) vs HEURISTIC │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  CreativeCritique (output)                                   │
│  - critique_type: rejection | weakness | continuity         │
│  - evidence: [{source, field, value}]                      │
│  - confidence: grounded | high | medium | low               │
│  - provenance: [evaluator, dimension, rule]                 │
│  - overridable: true (always)                                │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Data Flow: Proposal Generation

```
Scene Input + Failed Evaluation + Film Context
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  ProposalGenerationService.generate()                        │
└─────────────────────────────────────────────────────────────┘
    │
    ├──────────────────────────────────────────────────────┐
    ▼                                                      ▼
┌─────────────────────────────┐        ┌─────────────────────────────┐
│ FilmIntelligenceService    │        │ CinematicLanguageAnalyzer  │
│  .analyze_sequence()        │        │  .analyze_scene()         │
│  .analyze_act()             │        │                            │
└─────────────────────────────┘        └─────────────────────────────┘
    │                                                      │
    │ tension_summary: overdue?                    │ visual_intent
    │ motif_summary: callback needed?               │ restraint_score
    │ arc_progression: stalled?                     │ substitution_opportunity
    ▼                                                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Synthesis Logic (HEURISTIC - labeled as such)               │
│  - Pattern: "tension_overdue + low_restraint"              │
│    → Proposal: strengthen tension payoff before visual       │
│  - Pattern: "substitution_opportunity > 0.7 + subtext_bias"  │
│    → Proposal: let visuals carry meaning                    │
│  - Pattern: "arc_stalled + motif_callback_due"             │
│    → Proposal: complicate character through motif            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  CreativeProposal (output)                                   │
│  - original_decision: {scene_id, evaluation_summary}       │
│  - alternatives: [{description, rationale, grounded_in}]    │
│  - confidence: medium (heuristic)                           │
│  - provenance: [film_intelligence, cinematic_language]       │
│  - overridable: true (always)                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Collaboration Flow Design

### 5.1 When to Critique vs. Stay Silent

| Condition | Co-Director Behavior |
|-----------|---------------------|
| DirectorEvaluator returns REJECT | **Critique** - surface rejection reasons with urgency |
| DirectorEvaluator returns REVISE with score < 0.7 | **Critique** - highlight weakest pillar |
| MemoryArchivistEvaluator returns CRITICAL alert | **Critique** - emphasize urgency |
| MemoryArchivistEvaluator returns WARNING alert | **Log only** (unless ADVISORY mode enabled) |
| DirectorEvaluator returns APPROVE | **Silent** (unless ADVISORY mode with explicit request) |
| No evaluation triggered | **Silent** |
| User explicitly requests critique | **Critique** (respects mode settings) |

### 5.2 When to Propose Alternatives

| Trigger | Proposal Behavior |
|---------|------------------|
| DirectorEvaluator returns revision notes | **Propose** alternatives matching the notes |
| Multiple render options available | **Propose** comparison with rationale |
| Continuity health declining | **Propose** specific fix tied to alert |
| User requests options | **Propose** (any mode) |
| Taste calibration suggests preference | **Propose** with advisory label |
| Film intelligence shows pattern | **Propose** sparingly (max 1 per scene evaluation in ADVISORY mode) |

### 5.3 Intervention Intensity Adaptation

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INTERVENTION INTENSITY                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  LOW (after 3+ consecutive acceptances)                           │
│  ├── Only surface critiques on REJECT decisions                    │
│  ├── Max 1 proposal per scene                                      │
│  └── Wait for explicit user request for comparison                  │
│                                                                     │
│  MEDIUM (after rejection or user engagement)                       │
│  ├── Surface critiques on REVISE decisions                         │
│  ├── Propose alternatives matching revision notes                   │
│  └── Offer comparison when multiple renders available               │
│                                                                     │
│  HIGH (after 3+ consecutive rejections without acceptance)         │
│  ├── Surface critiques on any non-APPROVE decision                 │
│  ├── Proactively suggest based on film intelligence patterns       │
│  └── Recommend specific revision approaches                        │
│                                                                     │
│  CALIBRATION: User can always override intensity via policy        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.4 Avoiding Noise and Overbearing Behavior

| Anti-Pattern | Mitigation |
|--------------|------------|
| Repeating the same critique | Track `critiques_given` per scene; don't repeat unless new evidence |
| Proposing on every revision | Cap proposals per session; require minimum confidence threshold |
| Surprising the user | Co-Director interventions are opt-in per mode (PASSIVE default) |
| Acting without evidence | All critiques require grounded source from existing evaluators |
| Proposing without context | Proposals always include provenance showing source services |

---

## 6. Grounded vs. Heuristic Breakdown

### 6.1 Grounded Elements (Evidence from Canonical/Existing Services)

| Grounded Element | Source | Confidence |
|-----------------|--------|------------|
| Instant rejection reasons | DirectorEvaluator rejection rules | HIGH |
| Pillar score values | DirectorEvaluator._calculate_scores() | HIGH |
| Continuity alert severity | MemoryArchivistEvaluator.alert.severity | HIGH |
| Tension/motif status | FilmIntelligenceService summaries | HIGH |
| Taste calibration deltas | TasteLearningService adjustments | MEDIUM-HIGH |

**Grounded Definition:** The Co-Director cites the exact source—evaluator name, rule/trap/pillar, score value—making every claim traceable.

### 6.2 Heuristic Elements (Necessarily Interpretive)

| Heuristic Element | Basis | Confidence | Labeling |
|------------------|-------|------------|----------|
| Alternative descriptions | Film intelligence patterns + taste calibration | MEDIUM | Explicitly labeled as "proposed alternative" |
| Visual opportunity suggestions | CinematicLanguageAnalyzer signals | MEDIUM | Explicitly labeled with confidence |
| Revision approach recommendations | DirectorEvaluator revision notes + story scores | MEDIUM | Explicitly labeled as "suggestion" |
| Intervention intensity adaptation | Acceptance/rejection patterns | LOW | Explicitly labeled; user-overridable |

**Heuristic Definition:** The Co-Director makes educated suggestions where multiple valid approaches exist. These are always labeled and overridable.

### 6.3 Confidence and Provenance Exposure

```python
@dataclass
class CoDirectorOutputProvenance:
    """Every piece of Co-Director output includes this provenance."""

    # Sources consulted (which existing services were called)
    sources_used: List[str]  # e.g., ["DirectorEvaluator", "MemoryArchivist"]

    # Grounded evidence (direct citations from source services)
    grounded_evidence: List[GroundedEvidenceItem]  # {source, field, value}

    # Heuristic synthesis (interpretive reasoning)
    heuristic_reasoning: Optional[str]  # Free-text explanation

    # Confidence level
    confidence: str  # "grounded" | "high" | "medium" | "low"

    # Whether this can be overridden
    overridable: bool = True  # Always True; no autonomous decisions

    # User-requested vs. proactive
    trigger: str  # "user_requested" | "evaluation_failed" | "film_intelligence_pattern"
```

---

## 7. Safety Constraints

### 7.1 Constraint Matrix

| Constraint | Implementation |
|------------|---------------|
| **No duplicate truth layers** | FilmLevelMemory, FilmStructure, CreativeSpine, explicit scene input remain sole sources of canonical truth. Co-Director outputs are derived, not canonical. |
| **No hidden threshold rewrites** | APPROVE_THRESHOLD (0.80), REVISE_THRESHOLD (0.60), and all scoring weights are read-only. Co-Director never modifies them. |
| **No autonomous looping** | Single-pass critique cycles. If user doesn't act, Co-Director waits for next trigger. No self-triggering chains. |
| **Additive only** | Co-Director adds advisory layer; does not modify existing services, models, or thresholds. |
| **All output overridable** | `overridable: True` on every CreativeCritique and CreativeProposal. User decisions are final. |
| **All influence inspectable** | Full provenance on every output: sources consulted, evidence cited, confidence level, trigger reason. |

### 7.2 Safety Enforcement Points

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SAFETY ENFORCEMENT                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. INPUT VALIDATION                                               │
│     ├── Co-Director never creates canonical data                   │
│     ├── All inputs read from existing service outputs              │
│     └── No direct mutation of FilmLevelMemory/FilmStructure        │
│                                                                     │
│  2. OUTPUT SANDBOXING                                              │
│     ├── CreativeCritique/Proposal: overridable=True always         │
│     ├── No "approve" or "reject" decisions from Co-Director       │
│     └── Only "advise" and "suggest" outputs                        │
│                                                                     │
│  3. THRESHOLD PROTECTION                                           │
│     ├── DirectorEvaluator thresholds read-only                      │
│     ├── Co-Director cannot bypass evaluation decisions             │
│     └── All scoring influence goes through TasteLearning bounds    │
│                                                                     │
│  4. LOOP PREVENTION                                                 │
│     ├── Co-Director output does not trigger re-evaluation          │
│     ├── Intervention intensity capped per session                   │
│     └── Critique repetition tracking per scene                      │
│                                                                     │
│  5. USER OVERRIDE CHANNELS                                         │
│     ├── Mode selection (PASSIVE/ADVISORY/COLLABORATIVE)             │
│     ├── Explicit accept/reject on every proposal                   │
│     └── Intensity policy override                                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.3 Audit Log Requirements

Every Co-Director intervention must log:
- Timestamp
- Session ID
- Mode at time of intervention
- Scene/Film context
- Sources consulted
- Output type (critique/proposal/comparison)
- Grounded evidence citations
- Heuristic reasoning (if applicable)
- Confidence level
- `overridable: True`
- User response (accept/reject/ignore)

---

## 8. Implementation Plan

### Phase 10.1: Foundation
**Goal:** Establish minimal Co-Director infrastructure without changing behavior.

| Step | Component | Description |
|------|-----------|-------------|
| 10.1.1 | CoDirectorSession model | Session tracking with intervention history, acceptance patterns |
| 10.1.2 | CoDirectorMode enum | PASSIVE/ADVISORY/COLLABORATIVE modes |
| 10.1.3 | InterventionPolicy model | Configuration for when/how to intervene |
| 10.1.4 | CoDirectorSessionManager service | Basic session CRUD, no active intervention |
| 10.1.5 | Unit tests for session management | Verify mode switching, policy loading |

### Phase 10.2: Read-Only Exposure
**Goal:** Verify Co-Director can read existing services without side effects.

| Step | Component | Description |
|------|-----------|-------------|
| 10.2.1 | CoDirectorContext model | Typed context for passing to Co-Director operations |
| 10.2.2 | CoDirectorOrchestrator skeleton | Service that calls existing evaluators, logs outputs |
| 10.2.3 | Integration with DirectorEvaluator | Call evaluate(), capture outputs, log summary |
| 10.2.4 | Integration with MemoryArchivistEvaluator | Call evaluate_scene(), capture alerts, log summary |
| 10.2.5 | Read-only verification tests | Confirm no mutations to existing services |

### Phase 10.3: Debug Visibility
**Goal:** Expose Co-Director reasoning for inspection before activation.

| Step | Component | Description |
|------|-----------|-------------|
| 10.3.1 | CoDirectorDebugView model | Read-only view of what Co-Director would say |
| 10.3.2 | Orchestrator.debug_preview() | Return DebugView without side effects |
| 10.3.3 | Session history logging | Record all evaluations with Co-Director insights |
| 10.3.4 | Debug endpoint | GET /co-director/preview/{scene_id} |
| 10.3.5 | Tests for debug output | Verify provenance, confidence, labeling |

### Phase 10.4: Bounded Critique (ADVISORY mode)
**Goal:** Surface critiques with grounded evidence when evaluations fail.

| Step | Component | Description |
|------|-----------|-------------|
| 10.4.1 | CreativeCritique model | Structured critique with evidence, provenance |
| 10.4.2 | CritiqueGenerationService | Synthesize critique from DirectorEvaluator + MemoryArchivistEvaluator |
| 10.4.3 | Confidence labeling | Ground rejection reasons = HIGH, scoring dimensions = MEDIUM |
| 10.4.4 | Orchestrator.critique() | Generate critique (ADVISORY mode only) |
| 10.4.5 | Critique endpoint | POST /co-director/critique/{scene_id} |
| 10.4.6 | User override tracking | Record accept/reject on critiques |
| 10.4.7 | Tests for critique generation | Verify grounded evidence, provenance, labeling |

### Phase 10.5: Bounded Proposals (ADVISORY mode)
**Goal:** Suggest alternatives with heuristic reasoning and provenance.

| Step | Component | Description |
|------|-----------|-------------|
| 10.5.1 | CreativeProposal model | Original decision + alternatives + rationale |
| 10.5.2 | ProposalGenerationService | Generate proposals from FilmIntelligenceService + CinematicLanguageAnalyzer |
| 10.5.3 | Heuristic labeling | Explicitly label proposals as "heuristic" with confidence |
| 10.5.4 | Orchestrator.propose() | Generate proposals (ADVISORY mode only) |
| 10.5.5 | Proposal endpoint | POST /co-director/propose/{scene_id} |
| 10.5.6 | Acceptance tracking | Update intervention intensity based on acceptance |
| 10.5.7 | Tests for proposal generation | Verify alternatives, provenance, heuristic labeling |

### Phase 10.6: Creative Comparison
**Goal:** Orchestrate render comparison with Co-Director context.

| Step | Component | Description |
|------|-----------|-------------|
| 10.6.1 | CreativeComparisonReport model | RenderComparisonService output + Co-Director annotations |
| 10.6.2 | CreativeComparisonService | Orchestrate RenderComparisonService + add Co-Director insights |
| 10.6.3 | Orchestrator.compare() | Generate comparison with annotations |
| 10.6.4 | Comparison endpoint | POST /co-director/compare |
| 10.6.5 | Tests for comparison | Verify annotations, provenance, no winner declaration |

### Phase 10.7: Session Awareness & Intensity Adaptation
**Goal:** Track collaboration history and adapt intervention intensity.

| Step | Component | Description |
|------|-----------|-------------|
| 10.7.1 | Session analytics | Track critique acceptance rate, proposal acceptance rate |
| 10.7.2 | Intervention intensity calculator | Adjust based on acceptance patterns |
| 10.7.3 | Intensity override endpoint | Allow user to set intensity level |
| 10.7.4 | Session summary endpoint | GET /co-director/session/{session_id}/summary |
| 10.7.5 | Tests for intensity adaptation | Verify correct intensity based on patterns |

### Phase 10.8: COLLABORATIVE Mode
**Goal:** Enable proactive Co-Director behavior with safeguards.

| Step | Component | Description |
|------|-----------|-------------|
| 10.8.1 | Proactive trigger logic | Surface insights when film health declines |
| 10.8.2 | Film health monitoring | Track continuity health, tension status across scenes |
| 10.8.3 | Proactive proposal cap | Max 1 proactive proposal per scene evaluation |
| 10.8.4 | Mode-specific behavior matrix | Document behavior differences per mode |
| 10.8.5 | Enhanced tests | Verify safeguards, caps, mode isolation |

### Phase 10.9: Integration & Polish
**Goal:** Ensure seamless integration with existing workflows.

| Step | Component | Description |
|------|-----------|-------------|
| 10.9.1 | Integration with existing routes | Ensure Co-Director doesn't break existing flows |
| 10.9.2 | Error handling | Graceful degradation if services unavailable |
| 10.9.3 | Performance verification | Co-Director overhead < 10% on evaluation latency |
| 10.9.4 | Documentation | API docs, integration guide, safety documentation |
| 10.9.5 | Final integration tests | End-to-end workflow tests |

---

## 9. First Coding Task (Do Not Execute)

### Task: Implement Phase 10.1 - Co-Director Session Foundation

**Objective:** Create minimal Co-Director infrastructure without changing system behavior.

**Files to Create:**

1. `app/models/co_directorship.py` - Core Co-Director models

```python
"""
Co-Director Models - Phase 10.1

Minimal session and configuration models for Co-Director mode.
This phase establishes infrastructure only—no active intervention behavior.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class CoDirectorMode(str, Enum):
    """Co-Director operational modes."""
    
    # Silent monitoring—only logs insights, never surfaces
    PASSIVE = "passive"
    
    # Surfaces critiques/proposals after evaluation failures
    ADVISORY = "advisory"
    
    # Proactively monitors film health, suggests improvements
    COLLABORATIVE = "collaborative"


class InterventionIntensity(str, Enum):
    """How actively the Co-Director intervenes."""
    
    LOW = "low"      # After 3+ consecutive acceptances
    MEDIUM = "medium" # Default after engagement
    HIGH = "high"     # After 3+ consecutive rejections


@dataclass
class SessionIntervention:
    """A single Co-Director intervention in a session."""
    
    intervention_id: str
    scene_id: str
    film_id: str
    intervention_type: str  # "critique" | "proposal" | "comparison"
    triggered_by: str  # "evaluation_failed" | "user_requested" | "film_intelligence_pattern"
    mode: CoDirectorMode
    confidence: str  # "grounded" | "high" | "medium" | "low"
    overridable: bool = True  # Always True
    user_response: Optional[str] = None  # "accepted" | "rejected" | "ignored"
    created_at: str = field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMetrics:
    """Aggregated metrics for a Co-Director session."""
    
    total_interventions: int = 0
    critiques_given: int = 0
    proposals_given: int = 0
    comparisons_provided: int = 0
    acceptances: int = 0
    rejections: int = 0
    current_streak_type: str = "none"  # "acceptance" | "rejection" | "none"
    current_streak_count: int = 0
    consecutive_acceptances: int = 0
    consecutive_rejections: int = 0
    current_intensity: InterventionIntensity = InterventionIntensity.MEDIUM


@dataclass
class CoDirectorSession:
    """
    Session-level context for Co-Director collaboration.
    
    This is transient session state—no canonical film truth lives here.
    """
    
    session_id: str
    project_id: str
    film_id: str
    mode: CoDirectorMode = CoDirectorMode.PASSIVE
    created_at: str = field(default_factory=utc_now_iso)
    last_activity_at: str = field(default_factory=utc_now_iso)
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    interventions: List[SessionIntervention] = field(default_factory=list)
    scene_intervention_counts: Dict[str, int] = field(default_factory=dict)  # scene_id -> count
    intensity_overridden: bool = False  # User explicitly set intensity
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def record_intervention(self, intervention: SessionIntervention) -> None:
        """Record an intervention and update metrics."""
        self.interventions.append(intervention)
        self.last_activity_at = utc_now_iso()
        self.metrics.total_interventions += 1
        
        # Track per-scene counts
        scene_id = intervention.scene_id
        self.scene_intervention_counts[scene_id] = (
            self.scene_intervention_counts.get(scene_id, 0) + 1
        )
        
        # Update type counts
        if intervention.intervention_type == "critique":
            self.metrics.critiques_given += 1
        elif intervention.intervention_type == "proposal":
            self.metrics.proposals_given += 1
        elif intervention.intervention_type == "comparison":
            self.metrics.comparisons_provided += 1
        
        # Update response tracking
        if intervention.user_response:
            self._update_streak(intervention.user_response)
            if intervention.user_response == "accepted":
                self.metrics.acceptances += 1
            elif intervention.user_response == "rejected":
                self.metrics.rejections += 1
        
        # Recalculate intensity
        self._recalculate_intensity()
    
    def _update_streak(self, response: str) -> None:
        """Update acceptance/rejection streak tracking."""
        if response == "accepted":
            if self.metrics.current_streak_type == "acceptance":
                self.metrics.current_streak_count += 1
            else:
                self.metrics.current_streak_type = "acceptance"
                self.metrics.current_streak_count = 1
            self.metrics.consecutive_acceptances += 1
            self.metrics.consecutive_rejections = 0
        elif response == "rejected":
            if self.metrics.current_streak_type == "rejection":
                self.metrics.current_streak_count += 1
            else:
                self.metrics.current_streak_type = "rejection"
                self.metrics.current_streak_count = 1
            self.metrics.consecutive_rejections += 1
            self.metrics.consecutive_acceptances = 0
    
    def _recalculate_intensity(self) -> None:
        """Recalculate intervention intensity based on patterns."""
        if self.intensity_overridden:
            return  # User override takes precedence
        
        if self.metrics.consecutive_acceptances >= 3:
            self.metrics.current_intensity = InterventionIntensity.LOW
        elif self.metrics.consecutive_rejections >= 3:
            self.metrics.current_intensity = InterventionIntensity.HIGH
        else:
            self.metrics.current_intensity = InterventionIntensity.MEDIUM
    
    def get_interventions_for_scene(self, scene_id: str) -> List[SessionIntervention]:
        """Get all interventions for a specific scene."""
        return [i for i in self.interventions if i.scene_id == scene_id]
    
    def get_critique_count_for_scene(self, scene_id: str) -> int:
        """Get critique count for a scene (for repetition prevention)."""
        return self.scene_intervention_counts.get(scene_id, 0)


@dataclass
class InterventionPolicy:
    """
    Configuration for Co-Director intervention behavior.
    
    These are advisory defaults that can be overridden per session.
    """
    
    # When to surface critiques
    critique_on_reject: bool = True
    critique_on_revise_low_score: bool = True  # Score < 0.7
    critique_on_critical_alert: bool = True
    critique_on_warning_alert: bool = False  # Only in ADVISORY/COLLABORATIVE
    
    # When to generate proposals
    propose_on_revision_notes: bool = True
    propose_on_multiple_renders: bool = True
    propose_on_continuity_decline: bool = True
    max_proposals_per_scene: int = 2
    
    # Intensity thresholds
    low_intensity_acceptance_threshold: int = 3  # Consecutive acceptances
    high_intensity_rejection_threshold: int = 3  # Consecutive rejections
    
    # Repetition prevention
    max_critique_repetition_per_scene: int = 2
    
    # Confidence thresholds
    min_proposal_confidence: str = "medium"  # Don't propose with low confidence
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InterventionPolicy:
        """Create policy from dict (for configuration loading)."""
        return cls(**{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__
        })
```

2. `app/services/co_director_session_manager.py` - Session management service

```python
"""
Co-Director Session Manager - Phase 10.1

Manages Co-Director session lifecycle.
This phase provides basic session CRUD—no active intervention behavior.
"""

from __future__ import annotations

from typing import Dict, Optional
import logging

from app.models.co_directorship import (
    CoDirectorSession,
    CoDirectorMode,
    InterventionIntensity,
    InterventionPolicy,
    SessionIntervention,
)

logger = logging.getLogger("studio-co-director")


class CoDirectorSessionManager:
    """
    Manages Co-Director session state.
    
    Responsibilities:
    - Create/retrieve/update sessions
    - Track interventions and metrics
    - Apply intervention policies
    - Calculate intervention intensity
    
    This phase establishes the session infrastructure.
    Active critique/proposal generation comes in later phases.
    """
    
    # In-memory session storage (would be replaced with persistent storage in production)
    _sessions: Dict[str, CoDirectorSession] = {}
    
    # Default policy (can be overridden per session)
    DEFAULT_POLICY = InterventionPolicy()
    
    def __init__(self):
        """Initialize the session manager."""
        pass
    
    def create_session(
        self,
        session_id: str,
        project_id: str,
        film_id: str,
        mode: CoDirectorMode = CoDirectorMode.PASSIVE,
        policy: Optional[InterventionPolicy] = None,
    ) -> CoDirectorSession:
        """
        Create a new Co-Director session.
        
        Args:
            session_id: Unique session identifier
            project_id: Project context
            film_id: Film context
            mode: Initial Co-Director mode (default: PASSIVE)
            policy: Intervention policy (default: use DEFAULT_POLICY)
        
        Returns:
            New CoDirectorSession
        """
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists; returning existing")
            return self._sessions[session_id]
        
        session = CoDirectorSession(
            session_id=session_id,
            project_id=project_id,
            film_id=film_id,
            mode=mode,
            metadata={"policy_type": "default" if policy is None else "custom"},
        )
        
        self._sessions[session_id] = session
        logger.info(f"Created Co-Director session: {session_id}")
        
        return session
    
    def get_session(self, session_id: str) -> Optional[CoDirectorSession]:
        """
        Retrieve an existing session.
        
        Args:
            session_id: Session to retrieve
        
        Returns:
            CoDirectorSession if found, None otherwise
        """
        return self._sessions.get(session_id)
    
    def update_session_mode(
        self,
        session_id: str,
        mode: CoDirectorMode,
    ) -> Optional[CoDirectorSession]:
        """
        Update a session's Co-Director mode.
        
        Args:
            session_id: Session to update
            mode: New mode
        
        Returns:
            Updated session or None if not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        
        old_mode = session.mode
        session.mode = mode
        logger.info(f"Session {session_id} mode: {old_mode} -> {mode}")
        
        return session
    
    def record_intervention(
        self,
        session_id: str,
        intervention: SessionIntervention,
    ) -> bool:
        """
        Record an intervention in a session.
        
        Args:
            session_id: Session to update
            intervention: Intervention to record
        
        Returns:
            True if recorded, False if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            logger.warning(f"Cannot record intervention: session {session_id} not found")
            return False
        
        session.record_intervention(intervention)
        logger.debug(
            f"Recorded {intervention.intervention_type} intervention "
            f"for scene {intervention.scene_id} in session {session_id}"
        )
        
        return True
    
    def set_intervention_intensity(
        self,
        session_id: str,
        intensity: InterventionIntensity,
        override: bool = True,
    ) -> Optional[CoDirectorSession]:
        """
        Explicitly set intervention intensity (user override).
        
        Args:
            session_id: Session to update
            intensity: New intensity level
            override: Mark as user override (prevents automatic recalculation)
        
        Returns:
            Updated session or None if not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        
        session.metrics.current_intensity = intensity
        session.intensity_overridden = override
        
        logger.info(
            f"Session {session_id} intensity set to {intensity} "
            f"(override={override})"
        )
        
        return session
    
    def get_session_summary(
        self,
        session_id: str,
    ) -> Optional[Dict]:
        """
        Get a read-only summary of session state.
        
        Args:
            session_id: Session to summarize
        
        Returns:
            Summary dict or None if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None
        
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "film_id": session.film_id,
            "mode": session.mode.value,
            "current_intensity": session.metrics.current_intensity.value,
            "intensity_overridden": session.intensity_overridden,
            "metrics": {
                "total_interventions": session.metrics.total_interventions,
                "critiques_given": session.metrics.critiques_given,
                "proposals_given": session.metrics.proposals_given,
                "acceptances": session.metrics.acceptances,
                "rejections": session.metrics.rejections,
                "consecutive_acceptances": session.metrics.consecutive_acceptances,
                "consecutive_rejections": session.metrics.consecutive_rejections,
            },
            "created_at": session.created_at,
            "last_activity_at": session.last_activity_at,
        }
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session (cleanup).
        
        Args:
            session_id: Session to delete
        
        Returns:
            True if deleted, False if not found
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted Co-Director session: {session_id}")
            return True
        return False


# Global singleton
co_director_session_manager = CoDirectorSessionManager()
```

3. `app/services/test_co_director_session_manager.py` - Unit tests

```python
"""
Tests for Co-Director Session Manager - Phase 10.1

Verifies basic session lifecycle and intervention tracking.
"""

import pytest
from app.models.co_directorship import (
    CoDirectorMode,
    CoDirectorSession,
    InterventionIntensity,
    InterventionPolicy,
    SessionIntervention,
    SessionMetrics,
)
from app.services.co_director_session_manager import CoDirectorSessionManager


class TestCoDirectorSessionManager:
    """Tests for Co-DirectorSessionManager."""
    
    def setup_method(self):
        """Create fresh manager for each test."""
        self.manager = CoDirectorSessionManager()
        # Clear any existing sessions
        self.manager._sessions.clear()
    
    def test_create_session(self):
        """Test session creation with defaults."""
        session = self.manager.create_session(
            session_id="test-session-1",
            project_id="project-1",
            film_id="film-1",
        )
        
        assert session is not None
        assert session.session_id == "test-session-1"
        assert session.project_id == "project-1"
        assert session.film_id == "film-1"
        assert session.mode == CoDirectorMode.PASSIVE
        assert session.metrics.total_interventions == 0
    
    def test_create_session_with_mode(self):
        """Test session creation with specific mode."""
        session = self.manager.create_session(
            session_id="test-session-2",
            project_id="project-1",
            film_id="film-1",
            mode=CoDirectorMode.ADVISORY,
        )
        
        assert session.mode == CoDirectorMode.ADVISORY
    
    def test_get_session(self):
        """Test session retrieval."""
        created = self.manager.create_session(
            session_id="test-session-3",
            project_id="project-1",
            film_id="film-1",
        )
        
        retrieved = self.manager.get_session("test-session-3")
        
        assert retrieved is not None
        assert retrieved.session_id == created.session_id
    
    def test_get_nonexistent_session(self):
        """Test retrieval of non-existent session returns None."""
        result = self.manager.get_session("nonexistent")
        assert result is None
    
    def test_update_session_mode(self):
        """Test mode switching."""
        self.manager.create_session(
            session_id="test-session-4",
            project_id="project-1",
            film_id="film-1",
        )
        
        updated = self.manager.update_session_mode(
            "test-session-4",
            CoDirectorMode.COLLABORATIVE,
        )
        
        assert updated is not None
        assert updated.mode == CoDirectorMode.COLLABORATIVE
    
    def test_record_intervention(self):
        """Test intervention recording."""
        self.manager.create_session(
            session_id="test-session-5",
            project_id="project-1",
            film_id="film-1",
        )
        
        intervention = SessionIntervention(
            intervention_id="int-1",
            scene_id="scene-1",
            film_id="film-1",
            intervention_type="critique",
            triggered_by="evaluation_failed",
            mode=CoDirectorMode.ADVISORY,
            confidence="high",
        )
        
        result = self.manager.record_intervention("test-session-5", intervention)
        
        assert result is True
        session = self.manager.get_session("test-session-5")
        assert session.metrics.total_interventions == 1
        assert session.metrics.critiques_given == 1
    
    def test_record_intervention_updates_streak(self):
        """Test that accepting/rejecting updates streaks."""
        self.manager.create_session(
            session_id="test-session-6",
            project_id="project-1",
            film_id="film-1",
        )
        
        # Record two acceptances
        for i in range(2):
            intervention = SessionIntervention(
                intervention_id=f"int-{i}",
                scene_id="scene-1",
                film_id="film-1",
                intervention_type="proposal",
                triggered_by="user_requested",
                mode=CoDirectorMode.ADVISORY,
                confidence="medium",
                user_response="accepted",
            )
            self.manager.record_intervention("test-session-6", intervention)
        
        session = self.manager.get_session("test-session-6")
        assert session.metrics.consecutive_acceptances == 2
        assert session.metrics.current_streak_type == "acceptance"
    
    def test_intensity_recalculates_on_acceptances(self):
        """Test that intensity drops after consecutive acceptances."""
        self.manager.create_session(
            session_id="test-session-7",
            project_id="project-1",
            film_id="film-1",
        )
        
        # Record three acceptances
        for i in range(3):
            intervention = SessionIntervention(
                intervention_id=f"int-{i}",
                scene_id="scene-1",
                film_id="film-1",
                intervention_type="proposal",
                triggered_by="user_requested",
                mode=CoDirectorMode.ADVISORY,
                confidence="medium",
                user_response="accepted",
            )
            self.manager.record_intervention("test-session-7", intervention)
        
        session = self.manager.get_session("test-session-7")
        assert session.metrics.current_intensity == InterventionIntensity.LOW
    
    def test_intensity_recalculates_on_rejections(self):
        """Test that intensity rises after consecutive rejections."""
        self.manager.create_session(
            session_id="test-session-8",
            project_id="project-1",
            film_id="film-1",
        )
        
        # Record three rejections
        for i in range(3):
            intervention = SessionIntervention(
                intervention_id=f"int-{i}",
                scene_id="scene-1",
                film_id="film-1",
                intervention_type="proposal",
                triggered_by="user_requested",
                mode=CoDirectorMode.ADVISORY,
                confidence="medium",
                user_response="rejected",
            )
            self.manager.record_intervention("test-session-8", intervention)
        
        session = self.manager.get_session("test-session-8")
        assert session.metrics.current_intensity == InterventionIntensity.HIGH
    
    def test_user_override_prevents_recalculation(self):
        """Test that user override prevents automatic intensity changes."""
        self.manager.create_session(
            session_id="test-session-9",
            project_id="project-1",
            film_id="film-1",
        )
        
        # Set low intensity manually
        self.manager.set_intervention_intensity(
            "test-session-9",
            InterventionIntensity.LOW,
            override=True,
        )
        
        # Record rejections (shouldn't change intensity)
        for i in range(3):
            intervention = SessionIntervention(
                intervention_id=f"int-{i}",
                scene_id="scene-1",
                film_id="film-1",
                intervention_type="proposal",
                triggered_by="user_requested",
                mode=CoDirectorMode.ADVISORY,
                confidence="medium",
                user_response="rejected",
            )
            self.manager.record_intervention("test-session-9", intervention)
        
        session = self.manager.get_session("test-session-9")
        assert session.metrics.current_intensity == InterventionIntensity.LOW
        assert session.intensity_overridden is True
    
    def test_get_session_summary(self):
        """Test session summary generation."""
        self.manager.create_session(
            session_id="test-session-10",
            project_id="project-1",
            film_id="film-1",
            mode=CoDirectorMode.ADVISORY,
        )
        
        summary = self.manager.get_session_summary("test-session-10")
        
        assert summary is not None
        assert summary["session_id"] == "test-session-10"
        assert summary["mode"] == "advisory"
        assert summary["metrics"]["total_interventions"] == 0
    
    def test_delete_session(self):
        """Test session deletion."""
        self.manager.create_session(
            session_id="test-session-11",
            project_id="project-1",
            film_id="film-1",
        )
        
        result = self.manager.delete_session("test-session-11")
        
        assert result is True
        assert self.manager.get_session("test-session-11") is None
    
    def test_intervention_per_scene_tracking(self):
        """Test that per-scene intervention counts are tracked."""
        self.manager.create_session(
            session_id="test-session-12",
            project_id="project-1",
            film_id="film-1",
        )
        
        # Record interventions for same scene
        for i in range(3):
            intervention = SessionIntervention(
                intervention_id=f"int-{i}",
                scene_id="scene-a",
                film_id="film-1",
                intervention_type="critique",
                triggered_by="evaluation_failed",
                mode=CoDirectorMode.ADVISORY,
                confidence="high",
            )
            self.manager.record_intervention("test-session-12", intervention)
        
        session = self.manager.get_session("test-session-12")
        assert session.get_critique_count_for_scene("scene-a") == 3
        assert session.get_critique_count_for_scene("scene-b") == 0


class TestInterventionPolicy:
    """Tests for InterventionPolicy."""
    
    def test_default_policy_values(self):
        """Test default policy has expected values."""
        policy = InterventionPolicy()
        
        assert policy.critique_on_reject is True
        assert policy.critique_on_critical_alert is True
        assert policy.critique_on_warning_alert is False
        assert policy.max_proposals_per_scene == 2
        assert policy.max_critique_repetition_per_scene == 2
    
    def test_policy_from_dict(self):
        """Test policy creation from dict."""
        data = {
            "critique_on_reject": False,
            "max_proposals_per_scene": 5,
        }
        
        policy = InterventionPolicy.from_dict(data)
        
        assert policy.critique_on_reject is False
        assert policy.max_proposals_per_scene == 5
        # Unspecified fields should use defaults
        assert policy.critique_on_critical_alert is True
```

---

**Next Steps After Phase 10.1:**
- Phase 10.2: Read-Only Exposure (verify Co-Director can call existing services)
- Phase 10.3: Debug Visibility (expose what Co-Director would say)
- Phase 10.4: Bounded Critique (ADVISORY mode critique generation)
- Phase 10.5: Bounded Proposals (ADVISORY mode proposal generation)
- Phase 10.6: Creative Comparison (render comparison orchestration)
- Phase 10.7: Session Awareness (intensity adaptation)
- Phase 10.8: COLLABORATIVE Mode (proactive behavior with safeguards)
- Phase 10.9: Integration & Polish

---

## Summary

This design establishes the Co-Director as a **collaborative orchestration layer** that:

1. **Leverages existing systems** without modifying them
2. **Maintains canonical truth** as the sole source of film reality
3. **Operates in bounded modes** (PASSIVE → ADVISORY → COLLABORATIVE)
4. **Labels all outputs** as grounded vs. heuristic
5. **Preserves user authority** through `overridable: True` and explicit modes
6. **Tracks collaboration history** to adapt intervention intensity
7. **Provides full provenance** for every critique and proposal

The implementation follows the same discipline as earlier phases: **foundation → read-only exposure → debug visibility → bounded integration**.
