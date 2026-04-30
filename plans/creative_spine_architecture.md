# Phase 2: Creative Spine Architecture Plan

## 1. Executive Summary

The **Creative Spine** is the **governing creative constitution** for a film. It defines and protects the film's identity across structure, memory, agent collaboration, and scoring.

**Key Insight:** FilmLevelMemory already contains most "what" fields (story_thesis, emotional_contract, etc.). The Creative Spine adds the "how" and "why" - the **governance layer** that FilmLevelMemory doesn't need to own.

**Three-Layer Distinction:**
- **FilmStructure** = organizational hierarchy (acts, sequences, scenes, beats)
- **FilmLevelMemory** = parsed/observed content (themes, motifs, tensions, trajectory)
- **CreativeSpine** = governing constraints and rules (what must NOT be violated)

---

## 2. Creative Spine Responsibilities

The Creative Spine has 5 core responsibilities:

| Responsibility | Description |
|----------------|-------------|
| **Immutable Core** | Protect story thesis, emotional contract, genre lane - these cannot be contradicted |
| **Revisable Guardrails** | Visual philosophy, pacing philosophy, restraint rules - can evolve with justification |
| **Drift Detection** | Monitor agent outputs against spine constraints |
| **Consumption API** | Provide agents a clear, read-only view of governing constraints |
| **Override Protocol** | Define how human overrides interact with spine rules |

---

## 3. Canonical vs Derived Fields

### Canonical Fields (Immutable - Cannot Be Violated)
These live in FilmLevelMemory but are **governed** by the Spine:

| Field | Location | Governance |
|-------|----------|------------|
| `story_thesis` | FilmLevelMemory.story_thesis | Agents cannot contradict; scoring penalizes contradiction |
| `emotional_contract` | FilmLevelMemory.emotional_contract | Agents cannot violate emotional promise; scoring validates |
| `genre_lane` | FilmLevelMemory.genre_lane | Agents cannot break genre conventions without flagging |

### Derived/Revisable Fields (Can Evolve With Process)
These also live in FilmLevelMemory but have **looser governance**:

| Field | Location | Governance |
|-------|----------|------------|
| `visual_philosophy` | FilmLevelMemory.visual_philosophy | Can update with director input; agents should reference but not hard-follow |
| `pacing_philosophy` | FilmLevelMemory.pacing_philosophy | Can adjust based on act needs; guidance, not law |
| `restraint_rules` | FilmLevelMemory.restraint_rules | Explicit "do not do" list; agents must avoid |

### New Spine-Only Fields (Not in FilmLevelMemory)

| Field | Type | Purpose |
|-------|------|---------|
| `spine_version` | str | Version for tracking changes |
| `frozen_fields` | List[str] | Canonical fields that are locked |
| `drift_threshold` | float | Acceptable deviation before flagging (0.0-1.0) |
| `override_history` | List[Dict] | Audit trail of human overrides |
| `constraint_weights` | Dict[str, float] | How much each constraint matters for scoring |

---

## 4. Relationship to Existing Models and Services

```
┌─────────────────────────────────────────────────────────────────┐
│                        CreativeSpine                             │
│  (NEW - governance layer, not data layer)                       │
│                                                                 │
│  - Protects: story_thesis, emotional_contract, genre_lane       │
│  - Guards: visual_philosophy, pacing_philosophy, restraint_rules│
│  - Monitors: all agent outputs                                  │
│  - Validates: story-level scoring                               │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ references         │ references         │ validates
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│ FilmLevelMemory │  │  FilmStructure  │  │  StoryLevelScoring  │
│                 │  │                 │  │  (Phase 4 - future) │
│ - story_thesis  │  │ - acts          │  │                     │
│ - emotional_    │  │ - sequences     │  │  Validates agent    │
│   contract      │  │ - scenes        │  │  outputs against    │
│ - genre_lane    │  │ - beats         │  │  spine constraints  │
│ - visual_       │  │                 │  │                     │
│   philosophy    │  └─────────────────┘  └─────────────────────┘
│ - pacing_       │
│   philosophy    │
│ - restraint_    │
│   rules         │
└─────────────────┘
         ▲
         │ populates
┌─────────────────┐
│FilmStructure    │
│Service          │
│                 │
│ - build_film_   │
│   structure     │
│ - build_film_   │
│   memory        │
└─────────────────┘
```

### File Mapping

| File | Role | Phase 2 Changes |
|------|------|-----------------|
| `models/memory.py` | FilmLevelMemory lives here | **NO CHANGES** - spine references it |
| `models/crew.py` | FilmStructure lives here | **NO CHANGES** |
| `services/film_structure_service.py` | Builds structure/memory | **NO CHANGES** - spine is additive |
| `services/adaptation.py` | Pattern learning | **NO CHANGES** - spine validates its outputs |
| `models/spine.py` (NEW) | CreativeSpine model | **NEW FILE** |
| `services/spine_service.py` (NEW) | Spine governance logic | **NEW FILE** |

---

## 5. Risks of Duplication or Drift

### Risk 1: Duplicating FilmLevelMemory Fields
**Problem:** If CreativeSpine copies story_thesis, emotional_contract, etc., they can diverge.

**Mitigation:** CreativeSpine **references** FilmLevelMemory fields, doesn't copy them. The spine is a governance wrapper, not a data store.

### Risk 2: Spine Becomes "Another Memory"
**Problem:** If spine accumulates parsed data, it becomes redundant with FilmLevelMemory.

**Mitigation:** Spine only holds governance data (versions, thresholds, override history). Parsed content stays in FilmLevelMemory.

### Risk 3: Agents Bypass Spine
**Problem:** Agents might ignore spine constraints if not enforced.

**Mitigation:** 
- Story-level scoring (Phase 4) validates against spine
- Adaptation engine checks spine before recommending patterns
- Clear consumption API makes spine easy to use

### Risk 4: Over-Constraining Creative Output
**Problem:** Too many restraint rules stifles creativity.

**Mitigation:** 
- Restraint rules are guidance, not hard blocks
- `drift_threshold` allows minor deviations
- Human overrides can relax constraints

---

## 6. File-by-File Implementation Recommendation

### Step 1: Create `models/spine.py`
```python
class CreativeSpine(BaseModel):
    """Governing creative constitution for a film."""
    film_id: str
    
    # Version tracking
    spine_version: str = "1.0"
    created_at: datetime
    updated_at: datetime
    
    # Frozen canonical fields (references to FilmLevelMemory)
    # These are the field NAMES that are immutable
    frozen_fields: List[str] = ["story_thesis", "emotional_contract", "genre_lane"]
    
    # Drift detection
    drift_threshold: float = 0.2  # 20% deviation allowed before flagging
    
    # Constraint weights for scoring (field -> weight)
    constraint_weights: Dict[str, float] = {}
    
    # Override audit trail
    override_history: List[Dict] = []
    
    # Human-approved deviations
    approved_deviations: List[Dict] = []
```

### Step 2: Create `services/spine_service.py`
```python
class SpineService:
    """Service for managing CreativeSpine governance."""
    
    def get_spike_for_film(self, film_id: str) -> CreativeSpine
    def create_spine(self, film_id: str, memory: FilmLevelMemory) -> CreativeSpine
    def validate_against_spine(self, agent_output: Dict, spine: CreativeSpine) -> ValidationResult
    def record_override(self, film_id: str, field: str, old_value: Any, new_value: Any, reason: str)
    def check_drift(self, memory: FilmLevelMemory, spine: CreativeSpine) -> List[DriftReport]
```

### Step 3: Extend FilmStructureService
Add spine integration helpers:
```python
def build_spine_from_memory(self, film_id: str, memory: FilmLevelMemory) -> CreativeSpine
def get_spince_constraints(self, spine: CreativeSpine) -> Dict[str, Any]
```

### Step 4: Add Tests
- Test spine creation from FilmLevelMemory
- Test validation catches violations
- Test override audit trail
- Test drift detection

---

## 7. First Coding Task for Phase 2

**Do not execute yet - this is the recommended first step:**

### Task: Create `models/spine.py` with CreativeSpine model

**Rationale:** Starting with the model keeps changes surgical and establishes the core data structure before adding service logic.

**Implementation:**
1. Create `studio-backend/app/models/spine.py`
2. Define `CreativeSpine` class with fields described in Section 6
3. Include `SpineConstraint` and `DriftReport` supporting classes
4. Add basic validation methods

**Verification:**
```bash
cd studio-backend && PYTHONPATH=. python -c "from app.models.spine import CreativeSpine; print('OK')"
```

---

## 8. Backward Compatibility

The Creative Spine is **additive only**:
- No existing models are modified
- No existing services are modified
- FilmLevelMemory and FilmStructure remain unchanged
- Agents can ignore spine until Phase 4 (Story-Level Scoring) enforces it
- Existing tests continue to pass

---

## 9. Summary

| Aspect | Decision |
|--------|----------|
| **Model Location** | New file `models/spine.py` |
| **Service Location** | New file `services/spine_service.py` |
| **Data Source** | References FilmLevelMemory, doesn't copy |
| **Immutable Fields** | story_thesis, emotional_contract, genre_lane |
| **Revisable Fields** | visual_philosophy, pacing_philosophy, restraint_rules |
| **First Task** | Create CreativeSpine model in `models/spine.py` |
| **Backward Compatible** | Yes - additive only |