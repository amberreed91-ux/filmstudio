# Phase 5: Integration and Coherence - Architecture Plan

## 1. Executive Summary

Phase 5 completes the film co-direction system by unifying all components into a coherent runtime. The system currently has all pieces in place but they operate somewhat independently. Phase 5 ensures proper data flow, unified output, clear service boundaries, and production-readiness labeling.

**Current State:**
- Phases 1-4 complete: film structure, memory, spine, director/memory archivist conflict resolution, story-level scoring
- 85 tests passing
- All components integrated into `agent_executor.py` but output is not unified

**Phase 5 Goal:**
- Unified output model that packages director decision, continuity report, conflict resolution, and story score
- Clear service ownership boundaries
- Runtime coherence with proper data flow
- Production-readiness classification for UI/logs

---

## 2. End-to-End Runtime Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FILM CO-DIRECTION RUNTIME                            │
└─────────────────────────────────────────────────────────────────────────────┘

  [1. SCREENPLAY INPUT]
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  ScriptParser / FilmStructureService                            │
  │  - Extracts scenes, characters, beats, acts, sequences          │
  │  - Builds FilmStructure and FilmLevelMemory                     │
  └─────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  SpineConsumptionService (Phase 2)                              │
  │  - Provides role-filtered context to agents                     │
  │  - film_id → structure_context, memory_context, spine_context   │
  └─────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  AgentExecutor._director_logic (Phase 3)                        │
  │  - DirectorEvaluator scores scene against spine                 │
  │  - Returns: creative_decision {approved, notes, requires_revision}│
  │  - Also returns: quality_metrics {vision_consistency, ...}      │
  └─────────────────────────────────────────────────────────────────┘
           │
           ├──────────────────┐──────────────────┐
           ▼                  ▼                  ▼
  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
  │   (async)     │  │   (async)     │  │   (async)     │
  │ MemoryArchivist│  │ StoryScoring │  │   Conflict    │
  │  Evaluator    │  │   Service     │  │   Resolver    │
  └───────────────┘  └───────────────┘  └───────────────┘
           │                  │                  │
           ▼                  ▼                  ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  _merge_with_memory_archivist (Phase 3.5)                       │
  │  - Combines director + memory archivist outputs                 │
  │  - Creates DirectorContinuityDecision                           │
  │  - Records to FilmContinuityTracker                             │
  └─────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Story Scoring (Phase 4.4 - non-blocking)                       │
  │  - Runs after director + memory archivist merge                 │
  │  - Attaches story_score to result                               │
  └─────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  UNIFIED OUTPUT                                                 │
  │  {                                                              │
  │    "scene_id": "...",                                           │
  │    "film_id": "...",                                            │
  │    "creative_decision": {approved, notes, requires_revision},   │
  │    "continuity_report": {...},                                  │
  │    "story_score": {overall_health, dimension_scores, ...},      │
  │    "conflict_resolution": {...},                                │
  │    "quality_metrics": {...},                                    │
  │    "timestamp": "..."                                           │
  │  }                                                              │
  └─────────────────────────────────────────────────────────────────┘
```

### Current Issues in Flow

1. **Story scoring runs AFTER merge** but receives `creative_decision` not `DirectorContinuityDecision` - type mismatch handled gracefully but not ideal
2. **No unified output model** - fields are ad-hoc dicts
3. **Memory archivist runs async** but its output is passed via `input_data` - awkward coupling

---

## 3. Unified Output Model

### Current Output Structure (ad-hoc)

```python
result = {
    "task_type": "creative_review",
    "creative_decision": {
        "approved": bool,
        "notes": str,
        "requires_revision": bool
    },
    "quality_metrics": {...},           # From DirectorEvaluator
    "continuity_report": {...},         # From MemoryArchivist (via merge)
    "alerts": [...],                    # From MemoryArchivist
    "story_score": {...},               # From StoryLevelScoringService
    "conflict_resolution": {...}        # From DirectorMemoryResolver
}
```

### Proposed Unified Output Model

```python
@dataclass
class SceneOutput:
    """Unified output for a scene evaluation."""
    
    # Identity
    scene_id: str
    film_id: str
    timestamp: str
    
    # Core decision (canonical - always present)
    director_decision: DirectorDecision
    
    # Continuity assessment (canonical - always present after Phase 3.5)
    continuity_report: ContinuityReport
    
    # Story-level health (canonical - always present after Phase 4)
    story_health: StoryHealth
    
    # Conflict resolution (if conflicts detected)
    conflicts_resolved: Optional[List[Conflict]] = None
    
    # Metadata (internal/debugging)
    quality_metrics: Dict[str, Any] = None
    processing_time_ms: float = 0.0
    
    def to_app_response(self) -> Dict:
        """Convert to format for app/frontend."""
        return {
            "scene_id": self.scene_id,
            "film_id": self.film_id,
            "decision": {
                "approved": self.director_decision.approved,
                "notes": self.director_decision.notes,
                "requires_revision": self.director_decision.requires_revision
            },
            "continuity": self.continuity_report.to_summary(),
            "story_health": self.story_health.to_summary(),
            "has_warnings": len(self.continuity_report.alerts) > 0,
            "story_score": self.story_health.overall_health
        }
    
    def to_debug_response(self) -> Dict:
        """Full output including internal data."""
        return self.to_dict()
```

### Field Classification

| Field | Canonical | Surfaced to App | Internal/Debug |
|-------|-----------|-----------------|----------------|
| `scene_id` | ✅ | ✅ | - |
| `film_id` | ✅ | ✅ | - |
| `director_decision.approved` | ✅ | ✅ | - |
| `director_decision.notes` | ✅ | ✅ | - |
| `director_decision.requires_revision` | ✅ | ✅ | - |
| `continuity_report.alerts` | ✅ | ✅ (summary) | - |
| `continuity_report.tension_health` | ✅ | ✅ | - |
| `continuity_report.motif_health` | ✅ | ✅ | - |
| `story_health.overall_health` | ✅ | ✅ | - |
| `story_health.dimension_scores` | ✅ | - | ✅ (detailed) |
| `story_health.warnings` | ✅ | ✅ (summary) | - |
| `story_health.recommendations` | ✅ | ✅ (category only) | - |
| `quality_metrics` | - | - | ✅ |
| `processing_time_ms` | - | - | ✅ |
| `conflicts_resolved` | ✅ | ✅ (summary) | - |

---

## 4. Service Boundary Review

### Current Ownership

| Service | Owns | Responsibilities |
|---------|------|------------------|
| `ScriptParser` | Screenplay parsing | Text → scenes, characters, beats |
| `FilmStructureService` | Film structure | Acts, sequences, beats, structure building |
| `SpineConsumptionService` | Context delivery | Role-filtered context for agents |
| `SpineService` | Creative spine | Constraints, frozen fields, deviations |
| `DirectorEvaluator` | Scene evaluation | Vision consistency scoring |
| `MemoryArchivistEvaluator` | Continuity analysis | Tensions, motifs, character states |
| `DirectorMemoryResolver` | Conflict resolution | Merge director + memory archivist |
| `FilmContinuityTracker` | Continuity debt | Scene decisions, debt tracking |
| `StoryLevelScoringService` | Story health | 8-dimension scoring |
| `AgentExecutor` | Agent orchestration | Task routing, result aggregation |

### Overlapping Responsibilities (to clarify)

1. **SpineConsumptionService vs SpineService**
   - `SpineService`: Creates/updates spine, validates decisions
   - `SpineConsumptionService`: Consumes spine for agents
   - **Current**: Both exist, consumption doesn't modify spine
   - **Clarification**: SpineService is authoritative for spine mutations; SpineConsumptionService is read-only

2. **FilmStructureService vs FilmLevelMemory**
   - `FilmStructureService`: Builds structure from text
   - `FilmLevelMemory`: Stores memory data
   - **Current**: Both have themes, acts, emotional_trajectory
   - **Clarification**: Structure is canonical for structural elements; Memory is canonical for learned elements

3. **DirectorEvaluator vs StoryLevelScoringService**
   - `DirectorEvaluator`: Scene-level approval decision
   - `StoryLevelScoringService`: Story-level health metrics
   - **Current**: Both score but at different granularities
   - **Clarification**: DirectorEvaluator makes GO/NO-GO decisions; StoryLevelScoringService provides health metrics

4. **MemoryArchivistEvaluator vs FilmContinuityTracker**
   - `MemoryArchivistEvaluator`: Analyzes continuity health
   - `FilmContinuityTracker`: Records scene decisions, tracks debt
   - **Current**: Both track continuity but different aspects
   - **Clarification**: Evaluator is analytical; Tracker is transactional

### Least-Destructive Cleanup

**Do NOT change:**
- Service interfaces (would break tests)
- Model structures (would break serialization)
- Agent dispatch logic (would break orchestration)

**Can clarify with documentation:**
- Add ownership comments to service classes
- Document data flow in docstrings
- Add type hints where missing

**Can add (additive only):**
- Unified output model as new class
- Conversion methods on existing models
- Factory methods to build unified output

---

## 5. Runtime and Deployment Guidance

### Current Runtime Model

```
AgentExecutor (async loop)
    │
    ├── _script_analyst_logic (sync)
    ├── _storyboard_artist_logic (sync)
    ├── _cinematographer_logic (sync)
    ├── _prompt_engineer_logic (sync)
    ├── _render_coordinator_logic (sync)
    ├── _quality_reviewer_logic (sync)
    ├── _director_logic (sync) ◄── Story scoring runs here
    ├── _memory_archivist_logic (sync)
    ├── _editor_logic (sync)
    ├── _continuity_supervisor_logic (sync)
    └── _producer_logic (sync)
```

### Synchronous for Now

All agent logic is **synchronous** within the async loop. This is acceptable because:
- Python GIL limits true parallelism anyway
- No external I/O (all data in-memory)
- Simpler debugging and testing

### Could Later Become Async/Worker-Based

| Component | Current | Future Option |
|-----------|---------|---------------|
| Script parsing | Sync | Could be worker queue |
| Film structure building | Sync | Could be worker queue |
| Director evaluation | Sync | Could be parallel with memory archivist |
| Memory archivist | Sync | Could be parallel with director |
| Story scoring | Sync (non-blocking wrapper) | Could be background task |
| Render jobs | Already async | Already worker-based |

### What Should NOT Be Split Yet

1. **AgentExecutor orchestration** - Keep as single async loop
2. **Director + Memory Archivist merge** - Too tightly coupled
3. **Story scoring** - Already non-blocking, fine as sync call

---

## 6. Production-Readiness Classification

### Strongly Grounded (Production Ready)

| Component | Evidence |
|-----------|----------|
| FilmStructureService | Based on explicit screenplay parsing |
| FilmLevelMemory | Based on explicit scene analysis |
| DirectorEvaluator | Rule-based evaluation with clear thresholds |
| FilmContinuityTracker | Transactional record keeping |
| SpineConsumptionService | Direct data access, no computation |

### Heuristic (Use with Caution)

| Component | Heuristic Nature | Risk |
|-----------|------------------|------|
| StoryLevelScoringService | Simple keyword matching for themes/motifs | Medium - may miss nuance |
| OriginalityAnalyzer | Cliché pattern detection | Medium - false positives |
| TensionResolutionAnalyzer | Urgency weighting is arbitrary | Low - clear formula |
| MotifContinuityAnalyzer | Keyword matching | Medium - may miss variations |

### Tunable (Needs Configuration)

| Component | Tunable Parameters |
|-----------|-------------------|
| DirectorEvaluator | `revise_threshold`, `approval_threshold` |
| StoryLevelScoringService | Dimension weights (currently equal) |
| All analyzers | Fallback value (0.5) |

### UI/Log Labeling Recommendations

```python
# In UI, show:
"Story Health: 0.72"  # Overall, not dimensions

# In logs/debug, show:
"Story health: 0.72 (dims: thesis=0.8, tone=0.7, char=0.65, ...)"

# Warnings should be human-readable:
"Low motif continuity - scene doesn't reference established motifs"

# Recommendations should be actionable:
"Consider adding a visual callback to the 'red door' motif in this scene"
```

---

## 7. File-by-File Implementation Recommendation

### Phase 5.1: Unified Output Model (New File)

**File:** `studio-backend/app/models/output.py` (new)

```python
@dataclass
class SceneOutput:
    """Unified output for scene evaluation."""
    scene_id: str
    film_id: str
    timestamp: str
    director_decision: DirectorDecision
    continuity_report: ContinuityReport  
    story_health: StoryHealth
    conflicts_resolved: Optional[List[Conflict]] = None
    quality_metrics: Optional[Dict[str, Any]] = None
    processing_time_ms: float = 0.0
    
    def to_app_response(self) -> Dict: ...
    def to_debug_response(self) -> Dict: ...
```

**Rationale:** Additive only, no existing code modified.

### Phase 5.2: Factory Method for Unified Output (Modify AgentExecutor)

**File:** `studio-backend/app/services/agent_executor.py`

Add method:
```python
def build_scene_output(
    self,
    scene_id: str,
    film_id: str,
    director_decision: Dict,
    continuity_report: Dict,
    story_score: Optional[Dict],
    quality_metrics: Dict
) -> SceneOutput:
    """Build unified SceneOutput from current flow data."""
```

**Rationale:** Centralizes output construction, doesn't change existing flow.

### Phase 5.3: Documentation Updates (No Code Changes)

**Files:** Add docstrings to existing services

- `SpineService`: Document as authoritative for spine mutations
- `SpineConsumptionService`: Document as read-only consumer
- `FilmStructureService`: Document canonical ownership
- `FilmLevelMemory`: Document learned content ownership

### Phase 5.4: Add Conversion Methods to Existing Models (Additive)

**Files:** `crew.py`, `memory.py`

```python
# In DirectorContinuityDecision
def to_summary(self) -> Dict:
    """Return app-surfaced summary."""
    return {
        "decision": self.decision,
        "score": self.score,
        "has_alerts": self.critical_alert_count > 0 or self.warning_alert_count > 0
    }

# In StoryScore  
def to_summary(self) -> Dict:
    """Return app-surfaced summary."""
    return {
        "overall_health": self.overall_health,
        "priority": self.priority.value,
        "has_warnings": len(self.warnings) > 0
    }
```

---

## 8. Risks

### Low Risk

1. **Adding new output model** - Pure additive, no existing code touched
2. **Adding factory method** - Uses existing data, just reorganizes
3. **Adding conversion methods** - Returns new dict, doesn't modify model

### Medium Risk

1. **Changing StoryScoringContext to accept dict instead of DirectorContinuityDecision**
   - Would fix type mismatch but changes interface
   - **Recommendation:** Keep as-is, handle gracefully (already done)

2. **Modifying dimension weights**
   - Could change scoring behavior
   - **Recommendation:** Make weights configurable but keep defaults

### High Risk (Avoid)

1. **Refactoring service boundaries** - Would break many tests
2. **Changing model structures** - Would break serialization
3. **Making agents truly async** - Would require significant testing

---

## 9. First Coding Task for Phase 5 (Do Not Execute Yet)

### Task: Create Unified Output Model

**File to create:** `studio-backend/app/models/scene_output.py`

**Steps:**
1. Create `SceneOutput` dataclass with fields defined in Section 3
2. Add `to_app_response()` method for frontend consumption
3. Add `to_debug_response()` method for internal debugging
4. Add tests in `test_scene_output.py`

**Validation:**
- Run: `python3 -m pytest test_scene_output.py -v`
- All 5 tests should pass
- No existing tests should break

**Time estimate:** ~2 hours for model + tests

---

## 10. Summary Status Table

| Component | Phase | Status | Notes |
|-----------|-------|--------|-------|
| Film Structure Models | 1.1-1.4 | ✅ Complete | |
| Film Memory Models | 1.1-1.4 | ✅ Complete | |
| CreativeSpine | 2.1-2.4 | ✅ Complete | |
| DirectorEvaluator | 3.1-3.4 | ✅ Complete | |
| MemoryArchivistEvaluator | 3.1-3.4 | ✅ Complete | |
| Conflict Resolution | 3.5 | ✅ Complete | |
| Story Scoring Models | 4.1 | ✅ Complete | |
| StoryLevelScoringService | 4.2-4.3 | ✅ Complete | |
| agent_executor Integration | 4.4 | ✅ Complete | |
| Validation | 4.5 | ✅ Complete | 85 tests passing |
| **Unified Output Model** | **5.1** | **Pending** | New file only |
| **Factory Method** | **5.2** | **Pending** | Additive |
| **Documentation** | **5.3** | **Pending** | Docstrings |
| **Conversion Methods** | **5.4** | **Pending** | Additive |

---

## 11. Recommended Implementation Order

1. **Phase 5.1**: Create `SceneOutput` model (new file, no risk)
2. **Phase 5.2**: Add factory method to AgentExecutor (uses existing data)
3. **Phase 5.3**: Update docstrings (documentation only)
4. **Phase 5.4**: Add `to_summary()` methods (additive conversions)

**Total estimated changes:** 3 new methods, 1 new file, documentation updates
**Risk level:** Low (all additive)
**Test impact:** Should add 5-10 new tests, no existing tests broken