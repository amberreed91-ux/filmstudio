# Phase 3.4: Memory Archivist Architecture Plan

## 1. Executive Summary

The Memory Archivist is a new agent role responsible for **long-form continuity protection** - tracking narrative threads across the entire film lifecycle and ensuring proper payoff. It differs from existing services by providing **proactive continuity auditing** rather than reactive validation.

**Key Distinction**: The Memory Archivist doesn't store memory (that's FilmLevelMemory), doesn't govern creative decisions (that's SpineService), and doesn't evaluate scene quality (that's DirectorEvaluator). Instead, it **monitors continuity health** and **alerts when narrative threads are at risk**.

---

## 2. Responsibility Boundary

### What Memory Archivist DOES

| Responsibility | Description | Output |
|---------------|-------------|--------|
| **Tension Tracking** | Monitor unresolved tensions, predict resolution windows, alert when overdue | Tension health report |
| **Motif Callback Detection** | Track when motifs should recur/transform, verify callbacks happen | Motif continuity map |
| **Character State Consistency** | Track character emotional/physical state across scenes | State consistency alerts |
| **Payoff Prediction** | Identify setups without payoffs, flag narrative debt | Payoff tracker |
| **Visual Callback Verification** | Ensure visual motifs are referenced appropriately | Visual continuity report |
| **Act/Sequence Boundary Health** | Verify act transitions maintain continuity | Boundary health score |

### What Memory Archivist DOES NOT Do

| Excluded Responsibility | Handled By |
|------------------------|------------|
| Memory storage | FilmLevelMemory, MemoryService |
| Creative governance | SpineService, DirectorEvaluator |
| Scene quality evaluation | DirectorEvaluator |
| Pattern adaptation | AdaptationEngine |
| Conflict resolution | ConflictService, AuthorityHierarchy |
| Cross-scene pattern boost | AdaptationEngine (read-only consumer) |

---

## 3. Gap Analysis

### Current Continuity Coverage

| Component | What It Tracks | Gap |
|-----------|---------------|-----|
| **FilmLevelMemory** | Motifs, unresolved tensions, emotional trajectory (static storage) | No active monitoring |
| **DirectorEvaluator._score_continuity()** | Basic character continuity (0.7 base score) | Shallow - only checks if characters appear |
| **AdaptationEngine** | Cross-scene pattern boost (15% influence) | Pattern reuse, not continuity |
| **SpineService** | Creative constraints | Not continuity-specific |
| **_continuity_supervisor_logic()** | Basic continuity check (stub) | Returns hardcoded 0.9 |

### Identified Gaps

1. **No tension resolution tracking**: UnresolvedTension exists but no service actively monitors if tensions are resolved on time
2. **No motif callback scheduling**: MotifRecord exists but no one tracks when a motif should recur
3. **No character state history**: No service tracks "Alice was angry in scene 5, is she still angry in scene 12?"
4. **No payoff prediction**: No service identifies "this was introduced in act 1, it should pay off in act 3"
5. **No visual callback verification**: No service ensures "the red dress motif should appear in scene 20 as callback"

---

## 4. Target Role Design

### Memory Archivist Agent Role

```python
class AgentRole(str, Enum):
    # ... existing roles ...
    MEMORY_ARCHIVIST = "memory_archivist"  # NEW
```

### Memory Archivist Constraints (from Spine)

```python
DIRECTOR_CONSTRAINTS = {
    # ... existing ...
    "track_tension_resolution": True,      # NEW
    "enforce_motif_callbacks": True,        # NEW
    "monitor_character_consistency": True,  # NEW
    "require_act_transition_continuity": True,  # NEW
}
```

### Key Methods

```python
class MemoryArchivistEvaluator:
    """Evaluates continuity health for a scene or film."""

    def evaluate_film_continuity(
        self,
        film_id: str,
        spine: Dict,
        structure: Dict,
        memory: FilmLevelMemory
    ) -> ContinuityHealthReport:
        """
        Returns comprehensive continuity health report for entire film.
        """

    def evaluate_scene_continuity(
        self,
        scene_id: str,
        scene_data: Dict,
        spine: Dict,
        structure: Dict,
        memory: FilmLevelMemory
    ) -> SceneContinuityReport:
        """
        Returns continuity evaluation for a specific scene.
        """

    def get_tension_status(
        self,
        film_id: str
    ) -> List[TensionStatus]:
        """
        Returns status of all unresolved tensions.
        """

    def get_motif_callback_schedule(
        self,
        film_id: str
    ) -> List[MotifCallback]:
        """
        Returns when each motif should callback.
        """
```

### Output Structures

```python
@dataclass
class ContinuityHealthReport:
    film_id: str
    overall_health: float  # 0.0 - 1.0
    tension_health: float
    motif_health: float
    character_health: float
    act_transition_health: float
    alerts: List[ContinuityAlert]
    recommendations: List[str]

@dataclass
class SceneContinuityReport:
    scene_id: str
    passed: bool
    issues: List[str]
    warnings: List[str]
    character_states: Dict[str, str]  # character_id -> state
    motif_references: List[str]  # motifs referenced in scene
    tension_updates: List[str]  # tensions introduced/resolved

@dataclass
class TensionStatus:
    tension_id: str
    description: str
    introduced_scene: str
    expected_resolution_act: int
    actual_resolution_scene: Optional[str]
    is_overdue: bool
    health_score: float

@dataclass
class MotifCallback:
    motif_id: str
    motif_name: str
    last_seen_scene: str
    expected_callback_scene: Optional[str]
    actual_callback_scene: Optional[str]
    is_fulfilled: bool
    is_overdue: bool
```

---

## 5. Workflow Placement

### When Memory Archivist Runs

```
Agent Workflow:
1. Script Analyst → creates initial FilmLevelMemory
2. Director → evaluates scene (uses SpineConsumptionService)
3. Memory Archivist → [AFTER Director, BEFORE Cinematographer] ← NEW
4. Cinematographer → visual design
5. Quality Reviewer → final QC
```

### Memory Archivist Trigger Points

1. **Post-Director Evaluation**: After DirectorEvaluator approves/requests revision, Memory Archivist checks if the scene introduces new tensions or motif references
2. **Pre-Cinematographer**: Before cinematography begins, Memory Archivist provides continuity context
3. **Act Transitions**: When moving between acts, verify continuity health
4. **On-Demand**: When any agent requests continuity context via SpineConsumptionService

### Integration with SpineConsumptionService

```python
# In SpineConsumptionService.add()
def get_memory_archivist_context(
    self,
    film_id: str,
    scene_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get continuity context for Memory Archivist."""
    # Returns:
    # - tension_status: List[TensionStatus]
    # - motif_callback_schedule: List[MotifCallback]
    # - character_state_history: Dict[str, List[str]]
    # - pending_payoffs: List[str]
```

---

## 6. File by File Implementation Recommendation

### Phase 3.4.1: Core Models (NEW)

**File**: `app/models/continuity.py` (NEW)

```python
# Continuity health models
@dataclass
class ContinuityAlert:
    alert_type: str  # tension_overdue, motif_missed, character_inconsistent
    severity: str  # critical, warning, info
    description: str
    affected_elements: List[str]
    recommended_action: str

@dataclass
class TensionStatus:
    # From existing UnresolvedTension + new fields
    tension_id: str
    is_overdue: bool
    health_score: float
    resolution_scene: Optional[str]

@dataclass
class MotifCallback:
    motif_id: str
    motif_name: str
    is_fulfilled: bool
    is_overdue: bool
    callback_scene: Optional[str]

@dataclass
class CharacterStateRecord:
    character_id: str
    scene_id: str
    emotional_state: str
    physical_state: str
    key_actions: List[str]
```

### Phase 3.4.2: Memory Archivist Evaluator (NEW)

**File**: `app/services/memory_archivis.py` (NEW)

```python
class MemoryArchivistEvaluator:
    """Main evaluator for continuity health."""

    def evaluate_film_continuity(
        self,
        film_id: str,
        spine: Dict,
        structure: Dict,
        memory: FilmLevelMemory
    ) -> ContinuityHealthReport

    def evaluate_scene_continuity(
        self,
        scene_id: str,
        scene_data: Dict,
        spine: Dict,
        structure: Dict,
        memory: FilmLevelMemory
    ) -> SceneContinuityReport

    def _check_tension_health(
        self,
        memory: FilmLevelMemory,
        current_act: int
    ) -> List[TensionStatus]

    def _check_motif_callbacks(
        self,
        memory: FilmLevelMemory,
        current_scene: int
    ) -> List[MotifCallback]

    def _track_character_state(
        self,
        scene_data: Dict,
        character_id: str,
        state: str
    ) -> None

    def _verify_act_transition(
        self,
        from_act: int,
        to_act: int,
        memory: FilmLevelMemory
    ) -> bool
```

### Phase 3.4.3: Integration with SpineConsumptionService (EXTEND)

**File**: `app/services/spine_consumption_service.py`

```python
# Add to SpineConsumptionService
def get_memory_archivist_context(
    self,
    film_id: str,
    scene_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get continuity context for Memory Archivist."""
    # Returns tension_status, motif_callbacks, character_states
```

### Phase 3.4.4: Agent Executor Hookup (EXTEND)

**File**: `app/services/agent_executor.py`

```python
# Add _memory_archivis_logic() method
async def _memory_archivis_logic(self, task: CrewTask) -> Dict[str, Any]:
    """Memory Archivist: Monitors long-form continuity."""
    # Uses SpineConsumptionService.get_memory_archivist_context()
    # Uses MemoryArchivistEvaluator
    # Returns continuity health report

# Add to dispatch in _run_agent_logic()
elif role == AgentRole.MEMORY_ARCHIVIST:
    output.update(await self._memory_archivis_logic(task))
```

### Phase 3.4.5: Tests (NEW)

**File**: `app/services/test_memory_archivis.py` (NEW)

```python
# Tests for Memory Archivist
def test_tension_tracking_overdue():
def test_motif_callback_detection():
def test_character_state_consistency():
def test_act_transition_continuity():
def test_continuity_health_report():
def test_scene_continuity_report():
```

---

## 7. First Coding Task for Phase 3.4

**Task**: Create `app/services/memory_archivis.py` with `MemoryArchivistEvaluator` class

**File**: `app/services/memory_archivis.py`

**Core Methods**:
1. `evaluate_film_continuity()` - returns ContinuityHealthReport
2. `evaluate_scene_continuity()` - returns SceneContinuityReport
3. `_check_tension_health()` - identifies overdue tensions
4. `_check_motif_callbacks()` - identifies missed motif callbacks
5. `_track_character_state()` - maintains character state history

**Dependencies**:
- `app.models.memory.FilmLevelMemory`
- `app.models.continuity.*` (new models)
- `app.services.spine_consumption_service` (for context)

**Constraints**:
- All changes additive (no breaking changes)
- No randomness (deterministic evaluation)
- No silent failures (always return structured report)
- Backward compatible with existing services

**Do NOT implement yet**:
- AgentExecutor hookup (wait for evaluator to be stable)
- SpineConsumptionService extension (wait for evaluator)
- Tests (wait for evaluator)

---

## 8. Backward Compatibility

| Existing Component | Impact | Mitigation |
|-------------------|--------|------------|
| FilmLevelMemory | No change | Memory Archivist reads only |
| SpineService | No change | Uses SpineConsumptionService |
| DirectorEvaluator | No change | Memory Archivist runs after |
| AdaptationEngine | No change | Memory Archivist read-only consumer |
| MemoryService | No change | Different responsibility |

## 9. Summary

The Memory Archivist fills a critical gap: **proactive continuity monitoring** across the film's narrative lifecycle. It:

1. Tracks tension resolution health
2. Monitors motif callback schedules
3. Maintains character state history
4. Verifies act transition continuity
5. Provides structured continuity reports

It does NOT replace any existing service but complements them by providing the continuity-specific oversight that currently doesn't exist.