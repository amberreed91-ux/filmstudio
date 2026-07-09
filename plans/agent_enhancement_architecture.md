# Phase 3: Agent Enhancement Architecture Plan

## 1. Executive Summary

Phase 3 transforms the generic multi-agent execution system into a film co-direction system with distinct creative roles, productive disagreement, and spine-aware decision making. The system currently has 10 agent roles but lacks a proper DIRECTOR role in the enum (despite having `_director_logic` implementation), has no spine consumption, and uses a flat hierarchy without role-based authority differentiation.

**Key Changes:**
- Add DIRECTOR to AgentRole enum (currently referenced but missing)
- Implement spine consumption for each role
- Create role-based authority hierarchy for creative decisions
- Enable productive disagreement between roles
- Add Memory Archivist role for cross-scene continuity

**Risk Level:** Medium - Requires enum modification and new service integration

---

## 2. Existing Agent Audit

### Current AgentRole Enum ([`models/crew.py:20-39`](studio-backend/app/models/crew.py:20))

| Role | Exists in Enum | Has Logic | Current Function |
|------|----------------|-----------|------------------|
| PRODUCER | ✓ | ✓ | Task coordination, scheduling |
| RENDER_COORDINATOR | ✓ | ✓ | Job management |
| SCRIPT_ANALYST | ✓ | ✓ | Parse and structure (technical) |
| STORYBOARD_ARTIST | ✓ | ✓ | Visual layout (execution) |
| CINEMATOGRAPHER | ✓ | ✓ | Camera specs (technical) |
| PROMPT_ENGINEER | ✓ | ✓ | Prompt optimization (technical) |
| EDITOR | ✓ | ✓ | Sequence assembly (execution) |
| CONTINUITY_SUPERVISOR | ✓ | ✓ | Validation (technical) |
| QUALITY_REVIEWER | ✓ | ✓ | Automated checks |
| SYSTEM_ORCHESTRATOR | ✓ | ✓ | Workflow management |
| **DIRECTOR** | **✗ MISSING** | **✓** | **Referenced in dispatch but not in enum** |

### Agent Logic Methods in [`agent_executor.py`](studio-backend/app/services/agent_executor.py)

| Method | Line | Current Behavior |
|--------|------|------------------|
| `_script_analyst_logic` | 311 | Parses script, extracts scenes, characters |
| `_storyboard_artist_logic` | 371 | Creates visual layouts |
| `_cinematographer_logic` | 566 | Camera/lighting specs |
| `_prompt_engineer_logic` | 611 | Prompt optimization |
| `_render_coordinator_logic` | 740 | Render job management |
| `_quality_reviewer_logic` | 789 | Quality evaluation |
| `_director_logic` | 965 | **Stub - minimal implementation** |
| `_editor_logic` | 995 | Sequence assembly |
| `_continuity_supervisor_logic` | 1017 | Continuity validation |
| `_producer_logic` | 1037 | Production coordination |

### Dispatch Logic Bug ([`agent_executor.py:281`](studio-backend/app/services/agent_executor.py:281))

```python
elif role == AgentRole.DIRECTOR:  # ← This will raise AttributeError!
    output.update(await self._director_logic(task))
```

The dispatch references `AgentRole.DIRECTOR` but it's not in the enum. This is a latent bug.

---

## 3. Gap Analysis

### Missing Roles (Not in Enum, No Logic)

| Role | Priority | Notes |
|------|----------|-------|
| **DIRECTOR** | Critical | Logic exists, just missing from enum |
| **CRITIC/ARTISTIC_ADVISOR** | High | Creative feedback, spine guardian |
| **MEMORY_ARCHIVIST** | Medium | Cross-scene continuity tracking |

### Missing Capabilities

| Capability | Current State | Needed For |
|------------|---------------|------------|
| Spine consumption | Not implemented | All roles |
| Role-based authority | Flat hierarchy | Conflict resolution |
| Creative disagreement | No mechanism | Productive friction |
| Cross-scene memory | Scene-level only | Continuity |

### Role Overlaps

| Roles | Overlap | Resolution |
|-------|---------|------------|
| CONTINUITY_SUPERVISOR + EDITOR | Both check consistency | Differentiate: CS=visual continuity, EDITOR=narrative flow |
| CINEMATOGRAPHER + STORYBOARD_ARTIST | Both handle visuals | CS=camera/lighting specs, SA=composition/layout |
| PRODUCER + DIRECTOR | Both coordinate | PRODUCER=logistics, DIRECTOR=creative authority |

---

## 4. Target Role Architecture

### Role Categories

```
CREATIVE AUTHORITY (Make Final Decisions)
├── DIRECTOR - Creative vision, spine guardian, final approvals
└── (User) - Ultimate override authority

CREATIVE EXECUTION (Execute Within Constraints)
├── CINEMATOGRAPHER - Visual language, camera, lighting
├── STORYBOARD_ARTIST - Composition, layout, visual storytelling
├── EDITOR - Narrative flow, pacing, sequence assembly
└── SCRIPT_ANALYST - Structure, dialogue, story mechanics

TECHNICAL SUPPORT (Enable and Validate)
├── QUALITY_REVIEWER - Standards compliance, metrics
├── CONTINUITY_SUPERVISOR - Visual continuity, consistency
├── MEMORY_ARCHIVIST - Cross-scene tracking, pattern recognition (NEW)
└── PROMPT_ENGINEER - Technical output quality

PRODUCTION MANAGEMENT (Logistics)
├── PRODUCER - Scheduling, resources, coordination
└── RENDER_COORDINATOR - Technical execution
```

### Proposed Enum Changes

```python
class AgentRole(str, Enum):
    # Production Management
    PRODUCER = "producer"
    RENDER_COORDINATOR = "render_coordinator"
    
    # Creative Authority (NEW - has creative decision power)
    DIRECTOR = "director"  # ADD THIS
    
    # Creative Execution
    SCRIPT_ANALYST = "script_analyst"
    STORYBOARD_ARTIST = "storyboard_artist"
    CINEMATOGRAPHER = "cinematographer"
    EDITOR = "editor"
    
    # Technical Support
    PROMPT_ENGINEER = "prompt_engineer"
    CONTINUITY_SUPERVISOR = "continuity_supervisor"
    QUALITY_REVIEWER = "quality_reviewer"
    MEMORY_ARCHIVIST = "memory_archivist"  # ADD THIS
    
    # System
    SYSTEM_ORCHESTRATOR = "system_orchestrator"
```

### New Roles to Add

| Role | File | Purpose |
|------|------|---------|
| DIRECTOR | Add to enum | Creative authority, spine guardian |
| MEMORY_ARCHIVIST | New logic method | Cross-scene pattern tracking, continuity |

---

## 5. Spine Consumption by Role

### Spine Access Matrix

| Role | Story Thesis | Emotional Contract | Genre Lane | Visual Phil. | Pacing Phil. | Restraint Rules |
|------|--------------|-------------------|------------|--------------|--------------|-----------------|
| **DIRECTOR** | READ | READ | READ | READ/WRITE | READ/WRITE | READ |
| CINEMATOGRAPHER | - | - | READ | READ | - | READ |
| STORYBOARD_ARTIST | - | READ | READ | READ | - | READ |
| EDITOR | - | READ | READ | - | READ | READ |
| SCRIPT_ANALYST | READ | READ | READ | - | - | - |
| QUALITY_REVIEWER | - | - | READ | READ | READ | READ |
| CONTINUITY_SUPERVISOR | - | - | READ | READ | - | READ |
| MEMORY_ARCHIVIST | READ | READ | READ | READ | READ | READ |
| PRODUCER | - | - | - | - | - | - |
| PROMPT_ENGINEER | - | - | - | - | - | READ |

### Memory Consumption by Role

| Role | FilmLevelMemory | ActMemory | SequenceMemory | SceneMemory |
|------|-----------------|-----------|----------------|-------------|
| **DIRECTOR** | ✓ Full | ✓ Full | ✓ Full | ✓ Full |
| CINEMATOGRAPHER | ✓ Motifs, Tensions | ✓ Current act | ✓ Current seq | ✓ Current |
| STORYBOARD_ARTIST | ✓ Motifs | ✓ Current act | ✓ Current seq | ✓ Current |
| EDITOR | ✓ Emotional trajectory | ✓ All acts | ✓ All sequences | ✓ All |
| SCRIPT_ANALYST | ✓ All | ✓ All | ✓ All | ✓ All |
| QUALITY_REVIEWER | ✓ All | ✓ All | ✓ All | ✓ All |
| CONTINUITY_SUPERVISOR | ✓ Motifs | ✓ All | ✓ All | ✓ All |
| MEMORY_ARCHIVIST | ✓ Full + Cross-scene patterns | ✓ Full | ✓ Full | ✓ Full |
| PRODUCER | ✓ Overview only | - | - | - |
| PROMPT_ENGINEER | ✓ Style only | - | - | ✓ Current |

### FilmStructure Consumption by Role

| Role | Acts | Sequences | Beats | Scene Hierarchy |
|------|------|-----------|-------|-----------------|
| **DIRECTOR** | ✓ All | ✓ All | ✓ All | ✓ Full |
| CINEMATOGRAPHER | ✓ Current | ✓ Current | ✓ Current | ✓ Current |
| STORYBOARD_ARTIST | ✓ Current | ✓ Current | ✓ Current | ✓ Current |
| EDITOR | ✓ All | ✓ All | ✓ All | ✓ All |
| SCRIPT_ANALYST | ✓ All | ✓ All | ✓ All | ✓ Full |
| QUALITY_REVIEWER | ✓ All | ✓ All | ✓ All | ✓ All |
| CONTINUITY_SUPERVISOR | ✓ All | ✓ All | ✓ All | ✓ All |
| MEMORY_ARCHIVIST | ✓ All | ✓ All | ✓ All | ✓ Full + Cross-scene |

---

## 6. Conflict Resolution Design

### Authority Hierarchy for Creative Decisions

```
1. USER OVERRIDE (highest)
   └─ Direct user intervention

2. DIRECTOR DECISION
   └─ Creative authority, spine guardian
   └─ Can override any execution role

3. SPINE CONSTRAINTS
   └─ Immutable fields cannot be violated
   └─ Revisable fields require justification

4. ROLE EXPERTISE
   └─ Cinematographer → visual decisions
   └─ Editor → pacing decisions
   └─ etc.

5. ADAPTIVE PATTERNS (lowest)
   └─ Learned preferences from history
```

### Productive Disagreement Protocol

When roles disagree:

1. **Identify the conflict** - Which spine field is affected?
2. **Check if field is frozen** - If immutable, Director wins
3. **If revisable** - Allow debate, log disagreement
4. **Escalate to Director** - If no resolution after N iterations
5. **Director decides** - Decision logged with rationale
6. **Option to override** - User can reverse Director decision

### Conflict Types

| Conflict | Resolution Path |
|----------|-----------------|
| Visual philosophy | Cinematographer vs Director → Director wins |
| Pacing | Editor vs Director → Director wins |
| Creative direction | Any role vs Director → Director wins |
| Technical approach | Peer roles → Expertise-based |
| Resource/scheduling | Producer has final say |

### Disagreement Logging

```python
@dataclass
class RoleDisagreement:
    id: str
    scene_id: str
    conflicting_roles: List[AgentRole]
    spine_field: str  # Which spine field is contested
    positions: Dict[AgentRole, str]  # Each role's position
    resolution: str  # How it was resolved
    resolved_by: AgentRole  # Who decided
    timestamp: datetime
```

---

## 7. File by File Implementation Recommendation

### Phase 3.1: Fix Missing DIRECTOR Role (Low Risk)

**Files:**
- [`models/crew.py`](studio-backend/app/models/crew.py) - Add DIRECTOR to enum

**Change:**
```python
class AgentRole(str, Enum):
    # ... existing roles ...
    
    # Creative Authority (ADD)
    DIRECTOR = "director"
```

**Risk:** Low - Fixes latent bug, no behavioral change yet

---

### Phase 3.2: Create Spine Consumption Service (Medium Risk)

**New File:** `services/spine_consumption_service.py`

**Purpose:** Role-based spine and memory access

**Key Methods:**
```python
class SpineConsumptionService:
    def get_constraints_for_role(film_id, role) -> Dict
    def get_memory_for_role(film_id, role, scene_id) -> Dict
    def get_structure_for_role(film_id, role, scene_id) -> Dict
    def check_authority(role, decision_type) -> bool
```

**Integration Points:**
- `agent_executor.py` - Call consumption service before each task
- `spine_service.py` - Already exists, extend for role-based access

**Risk:** Medium - New service, no existing behavior change

---

### Phase 3.3: Enhance Director Logic (Medium Risk)

**File:** [`agent_executor.py`](studio-backend/app/services/agent_executor.py)

**Changes to `_director_logic`:**
1. Load spine constraints via SpineConsumptionService
2. Review agent outputs against spine
3. Make creative decisions with spine awareness
4. Log decisions for drift detection

**Risk:** Medium - Changes Director behavior, requires Phase 3.2

---

### Phase 3.4: Add Memory Archivist Role (Higher Risk)

**Files:**
- [`models/crew.py`](studio-backend/app/models/crew.py) - Add MEMORY_ARCHIVIST to enum
- [`agent_executor.py`](studio-backend/app/services/agent_executor.py) - Add `_memory_archivist_logic`
- [`services/memory_archivist_service.py`](studio-backend/app/services/memory_archivist_service.py) - New service

**Purpose:**
- Track cross-scene patterns
- Maintain continuity database
- Alert on potential inconsistencies
- Support spine drift detection

**Risk:** Higher - New role with new service

---

### Phase 3.5: Implement Conflict Resolution (Higher Risk)

**Files:**
- [`services/conflict_resolution_service.py`](studio-backend/app/services/conflict_resolution_service.py) - New
- [`models/crew.py`](studio-backend/app/models/crew.py) - Add RoleDisagreement model
- [`agent_executor.py`](studio-backend/app/services/agent_executor.py) - Integrate conflict detection

**Risk:** Higher - New workflow, requires careful testing

---

### Implementation Order

```
Phase 3.1 (Low Risk)
└─ Fix DIRECTOR enum bug
   └─ 30 minutes, minimal testing

Phase 3.2 (Medium Risk)  
└─ Create SpineConsumptionService
   └─ 2-3 hours, moderate testing

Phase 3.3 (Medium Risk)
└─ Enhance Director logic with spine awareness
   └─ 2-3 hours, integration testing

Phase 3.4 (Higher Risk)
└─ Add Memory Archivist role
   └─ 3-4 hours, comprehensive testing

Phase 3.5 (Higher Risk)
└─ Implement conflict resolution
   └─ 4-5 hours, extensive testing
```

---

## 8. Backward Compatibility Analysis

### Breaking Changes

| Change | Impact | Mitigation |
|--------|--------|------------|
| Add DIRECTOR to enum | None | Additive only |
| Add MEMORY_ARCHIVIST to enum | None | Additive only |
| Modify `_director_logic` | Low | Existing logic is stub |
| New SpineConsumptionService | None | New service, opt-in |

### Preserved Behaviors

- All existing agent logic methods unchanged until enhanced
- Task dispatch unchanged
- Memory service unchanged
- API routes unchanged

### Migration Path

1. Phase 3.1: Add DIRECTOR to enum (no behavior change)
2. Phase 3.2: SpineConsumptionService available but not called
3. Phase 3.3: Director uses new service (behind feature flag)
4. Phase 3.4: Memory Archivist available (behind feature flag)
5. Phase 3.5: Conflict resolution available (behind feature flag)

---

## 9. First Coding Task for Phase 3

### Task: Add DIRECTOR to AgentRole Enum

**File:** [`studio-backend/app/models/crew.py`](studio-backend/app/models/crew.py)

**Change:**
```python
class AgentRole(str, Enum):
    """Agent roles - each specializes in execution, not creative decisions"""

    # Production Management
    PRODUCER = "producer"
    RENDER_COORDINATOR = "render_coordinator"

    # Creative Authority (ADD THIS SECTION)
    DIRECTOR = "director"  # Creative vision, spine guardian, final approvals

    # Creative Execution (not decision-making)
    SCRIPT_ANALYST = "script_analyst"
    STORYBOARD_ARTIST = "storyboard_artist"
    CINEMATOGRAPHER = "cinematographer"
    PROMPT_ENGINEER = "prompt_engineer"
    EDITOR = "editor"
    CONTINUITY_SUPERVISOR = "continuity_supervisor"

    # Quality & Review (not creative decisions)
    QUALITY_REVIEWER = "quality_reviewer"

    # System (no creative authority)
    SYSTEM_ORCHESTRATOR = "system_orchestrator"
```

**Verification:**
```bash
cd studio-backend && python -c "from app.models.crew import AgentRole; print(AgentRole.DIRECTOR)"
```

**Expected Output:** `AgentRole.DIRECTOR`

**Risk:** None - Fixes latent bug, purely additive

---

## 10. Summary

Phase 3 transforms the agent system into a proper film co-direction system:

1. **Fix the bug** - Add missing DIRECTOR to enum
2. **Build spine awareness** - SpineConsumptionService for role-based access
3. **Enhance Director** - Make Director the spine guardian
4. **Add Memory Archivist** - Cross-scene continuity tracking
5. **Enable disagreement** - Conflict resolution with authority hierarchy

The implementation is designed to be incremental with feature flags, preserving backward compatibility while enabling the film crew metaphor to emerge naturally from the existing generic multi-agent system.