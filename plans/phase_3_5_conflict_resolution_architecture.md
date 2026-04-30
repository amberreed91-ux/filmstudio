# Phase 3.5: Director-Memory Archivist Conflict Resolution Architecture

## Executive Summary

Phase 3.5 designs the conflict resolution system between Director (creative authority) and Memory Archivist (continuity advisor). The core principle: **Director decisions are authoritative, but Memory Archivist alerts must be visible and actionable** before final approval.

---

## 1. Fundamental Design Principles

### 1.1 Authority Hierarchy
```
CREATIVE AUTHORITY (Director)
├── Makes APPROVE/REVISE/REJECT decisions
├── Has final say on creative content
└── Must acknowledge continuity alerts before APPROVE

CONTINUITY ADVISOR (Memory Archivist)
├── Provides continuity health analysis
├── Issues alerts with severity levels
├── Cannot block or override Director
└── Recommendations become revision notes when severity >= WARNING
```

### 1.2 Non-Blocking Design
- Memory Archivist is **advisory only**
- Director never waits for Memory Archivist
- Continuity reports are **attached to** Director decisions, not **merged into** them
- Critical alerts require acknowledgment, not resolution

---

## 2. Conflict Types

### 2.1 Director Approves + Memory Archivist Has CRITICAL Alert
**Scenario**: Director approves scene, Memory Archivist finds a broken tension payoff
```
Resolution: APPROVE with CRITICAL alert attached
Director must acknowledge before scene proceeds to next agent
Alert appears in revision_notes as "Continuity Advisory: [description]"
```

### 2.2 Director Approves + Memory Archivist Has WARNING Alert
**Scenario**: Director approves scene, Memory Archivist notes a motif callback is overdue
```
Resolution: APPROVE with WARNING logged
No blocking - scene proceeds
Alert recorded for film-level health tracking
```

### 2.3 Director REVISE/REJECT + Memory Archivist Has No Issues
**Scenario**: Director rejects for creative reasons, continuity is fine
```
Resolution: Director decision stands
Memory Archivist report attached for reference
No conflict - different evaluation criteria
```

### 2.4 Director Approves + Memory Archivist Has Multiple CRITICAL Alerts
**Scenario**: Scene breaks 2+ tensions, misses motif callbacks, has character inconsistency
```
Resolution: APPROVE with CRITICAL alert bundle
Escalation flag set for film-level review
Scene can proceed but counted in "debt" for film health
```

---

## 3. Severity Model

### 3.1 Alert Severity Levels (from Memory Archivist)

| Severity | Definition | Director Action Required | Blocking |
|----------|------------|-------------------------|----------|
| `CRITICAL` | Breaks narrative contract (unresolved tension, missed payoff) | Must acknowledge in decision | No, but tracked |
| `WARNING` | Continuity debt (overdue motif, character drift) | Informational | No |
| `INFO` | Contextual notes (tension introduced, motif callback) | None | No |

### 3.2 Conflict Severity (for escalation)

| Severity | Trigger | Escalation Path |
|----------|---------|-----------------|
| `LOW` | 1-2 WARNINGs | Log only, no action |
| `MEDIUM` | 3+ WARNINGs or 1 CRITICAL | Log + scene flag |
| `HIGH` | 2+ CRITICALs | Flag for film-level review |
| `BLOCKING` | Reserved for future: user override | Escalate to user |

---

## 4. Output Model

### 4.1 Merged Decision Report

```python
@dataclass
class DirectorContinuityDecision:
    """Combined output from Director + Memory Archivist evaluation"""
    
    # Director's decision
    decision: Decision  # APPROVE/REVISE/REJECT
    score: float
    revision_notes: List[str]
    
    # Memory Archivist's analysis (attached, not merged)
    continuity_report: ContinuityHealthReport
    alerts: List[ContinuityAlert]
    
    # Conflict metadata
    has_conflicts: bool
    conflict_severity: Optional[ConflictSeverity]
    critical_alert_count: int
    warning_alert_count: int
    
    # Resolution status
    alerts_acknowledged: bool
    escalation_flag: bool
```

### 4.2 Decision Output Structure

```python
# In agent_executor.py _director_logic output:
{
    "decision": "APPROVE",  # or REVISE/REJECT
    "score": 0.85,
    "revision_notes": [
        "Consider adding visual transition between scenes",
        "Continuity Advisory: Tension 'betrayal_setup' is overdue for resolution"
    ],
    "continuity_context": {
        "health_scores": {
            "overall": 0.72,
            "tension": 0.65,
            "motif": 0.80,
            "character": 0.90
        },
        "alerts": [
            {
                "type": "TENSION_OVERDUE",
                "severity": "WARNING",
                "description": "Tension 'betrayal_setup' expected resolution in Act 2",
                "affected_elements": ["tension_betrayal_setup"],
                "recommended_action": "Resolve tension or explicitly defer"
            }
        ],
        "critical_count": 0,
        "warning_count": 1
    },
    "has_continuity_debt": True,
    "requires_acknowledgment": False  # True only if CRITICAL alerts
}
```

---

## 5. Workflow Placement

### 5.1 Execution Order

```
┌─────────────────────────────────────────────────────────────┐
│                    SCENE GENERATION LOOP                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Script Analyst → Scene Data                             │
│           ↓                                                  │
│  2. Storyboard Artist → Visual Layout                       │
│           ↓                                                  │
│  3. Cinematographer → Camera Specs                          │
│           ↓                                                  │
│  4. Prompt Engineer → Optimized Prompt                      │
│           ↓                                                  │
│  5. Render Coordinator → Generated Output                   │
│           ↓                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              PARALLEL EVALUATION                     │   │
│  │  ┌──────────────┐    ┌──────────────────────────┐   │   │
│  │  │   DIRECTOR   │    │    MEMORY ARCHIVIST      │   │   │
│  │  │  (primary)   │    │    (parallel, async)     │   │   │
│  │  │              │    │                          │   │   │
│  │  │ Decision:    │    │ ContinuityReport:        │   │   │
│  │  │ APPROVE/     │    │ - health_scores          │   │   │
│  │  │ REVISE/      │    │ - alerts                 │   │   │
│  │  │ REJECT       │    │ - tension_statuses       │   │   │
│  │  └──────┬───────┘    └──────────┬───────────────┘   │   │
│  │         │                       │                    │   │
│  │         └───────────┬───────────┘                    │   │
│  │                     ↓                                │   │
│  │         ┌───────────────────────┐                   │   │
│  │         │  CONFLICT RESOLVER    │                   │   │
│  │         │                       │                   │   │
│  │         │ - Merge outputs       │                   │   │
│  │         │ - Attach alerts       │                   │   │
│  │         │ - Set flags           │                   │   │
│  │         └───────────┬───────────┘                   │   │
│  └─────────────────────┼───────────────────────────────┘   │
│                        ↓                                    │
│              6. Quality Reviewer                            │
│                        ↓                                    │
│              7. Editor → Assembly                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Conflict Resolution Point

The conflict resolver runs **after** both Director and Memory Archivist complete, **before** the output is returned to the agent executor loop.

```python
# In agent_executor.py
async def _resolve_director_memory_archivist_conflict(
    director_output: Dict,
    memory_archivist_output: Dict,
    task: CrewTask
) -> Dict:
    """
    Merge Director decision with Memory Archivist continuity report.
    This is NOT a conflict in the traditional sense - it's an attachment
    of advisory continuity data to the authoritative creative decision.
    """
    merged = director_output.copy()
    
    # Attach continuity context
    merged["continuity_context"] = {
        "health_scores": memory_archivist_output.get("health_scores", {}),
        "alerts": memory_archivist_output.get("alerts", []),
        "critical_count": len([a for a in memory_archivist_output.get("alerts", []) 
                               if a.get("severity") == "CRITICAL"]),
        "warning_count": len([a for a in memory_archivist_output.get("alerts", []) 
                              if a.get("severity") == "WARNING"])
    }
    
    # Set conflict flags
    merged["has_continuity_debt"] = merged["continuity_context"]["warning_count"] > 0
    merged["has_critical_alerts"] = merged["continuity_context"]["critical_count"] > 0
    
    # Add revision notes for CRITICAL alerts
    if merged["continuity_context"]["critical_count"] > 0:
        for alert in memory_archivist_output.get("alerts", []):
            if alert.get("severity") == "CRITICAL":
                merged["revision_notes"].append(
                    f"Continuity Critical: {alert.get('description', 'See alert')}"
                )
    
    # Set escalation flag for film-level review
    merged["escalation_flag"] = merged["continuity_context"]["critical_count"] >= 2
    
    return merged
```

---

## 6. Resolution Rules

### 6.1 Rule Matrix

| Director Decision | Alert Severity | Resolution |
|-------------------|----------------|------------|
| APPROVE | No alerts | Standard APPROVE |
| APPROVE | INFO only | APPROVE with info logged |
| APPROVE | WARNING(s) | APPROVE, debt tracked |
| APPROVE | 1+ CRITICAL | APPROVE with acknowledgment required |
| REVISE | Any | REVISE (creative takes precedence) |
| REJECT | Any | REJECT (creative takes precedence) |

### 6.2 Acknowledgment Flow

When CRITICAL alerts exist on an APPROVE:

```
1. Director outputs APPROVE with CRITICAL alert attached
2. Output marked: requires_acknowledgment = True
3. Next agent (Quality Reviewer) sees the flag
4. Quality Reviewer can:
   a. Proceed if acknowledgment is acceptable
   b. Flag for human review if not
5. Scene proceeds unless explicitly blocked by human
```

---

## 7. Data Flow

### 7.1 Scene-Level Flow

```
Task Input
    ↓
┌────────────────────────────────────────────────────────────┐
│ PARALLEL: Director + Memory Archivist                      │
│                                                            │
│ DirectorEvaluator.evaluate(scene_data, spine, context)     │
│   → Decision(APPROVE/REVISE/REJECT)                        │
│   → score, revision_notes                                  │
│                                                            │
│ MemoryArchivistEvaluator.evaluate_scene_continuity(...)    │
│   → ContinuityHealthReport                                 │
│   → alerts, health_scores                                  │
└────────────────────────────────────────────────────────────┘
    ↓
ConflictResolver.merge_director_memory_archivist(director_out, archivist_out)
    ↓
MergedOutput {
    decision, score, revision_notes,
    continuity_context: {
        health_scores, alerts,
        critical_count, warning_count
    },
    has_continuity_debt, escalation_flag
}
    ↓
Agent Executor Loop continues
```

### 7.2 Film-Level Aggregation

```python
class FilmContinuityTracker:
    """
    Tracks film-level continuity debt across all scenes.
    Used for film health scoring beyond per-scene evaluation.
    """
    
    def __init__(self):
        self.film_debt: Dict[str, List[ContinuityAlert]] = {}  # film_id -> alerts
    
    def record_scene_decision(self, film_id: str, scene_id: str, merged_output: Dict):
        """Record a scene's continuity status for film-level tracking."""
        alerts = merged_output.get("continuity_context", {}).get("alerts", [])
        if alerts:
            if film_id not in self.film_debt:
                self.film_debt[film_id] = []
            self.film_debt[film_id].extend(alerts)
    
    def get_film_continuity_debt(self, film_id: str) -> Dict:
        """Get film-level continuity debt summary."""
        alerts = self.film_debt.get(film_id, [])
        return {
            "total_alerts": len(alerts),
            "critical_count": len([a for a in alerts if a.severity == AlertSeverity.CRITICAL]),
            "warning_count": len([a for a in alerts if a.severity == AlertSeverity.WARNING]),
            "by_type": self._group_by_type(alerts)
        }
```

---

## 8. Backward Compatibility

### 8.1 Preserved Behaviors

| Component | Preservation Strategy |
|-----------|----------------------|
| DirectorEvaluator | Returns same Decision + score + notes structure |
| MemoryArchivistEvaluator | Returns same ContinuityHealthReport |
| AgentExecutor._director_logic | Output format unchanged, new fields added |
| AgentExecutor._memory_archivist_logic | Output format unchanged |

### 8.2 New Fields (Optional/Additive)

All new fields are added with defaults to ensure existing code works:

```python
# New fields in director output (all have defaults)
{
    "continuity_context": None,  # Added by conflict resolver
    "has_continuity_debt": False,
    "has_critical_alerts": False,
    "escalation_flag": False
}
```

### 8.3 Test Compatibility

Existing tests continue to pass because:
- New fields have default values
- Conflict resolver only adds data, never removes
- Director and Memory Archivist logic unchanged

---

## 9. Future Compatibility

### 9.1 Story-Level Scoring

The film_continuity_debt tracker enables future story-level scoring:

```python
# Future: Film health affects Director thresholds
FILM_HEALTH_THRESHOLDS = {
    "healthy": 0.80,      # Normal approval threshold
    "degraded": 0.85,     # Higher standards when debt exists
    "critical": 0.90      # Strict approval when film health poor
}

def get_approval_threshold(film_id: str) -> float:
    """Dynamic threshold based on film continuity health."""
    debt = film_tracker.get_film_continuity_debt(film_id)
    if debt["critical_count"] >= 3:
        return FILM_HEALTH_THRESHOLDS["critical"]
    elif debt["warning_count"] >= 5:
        return FILM_HEALTH_THRESHOLDS["degraded"]
    return FILM_HEALTH_THRESHOLDS["healthy"]
```

### 9.2 Additional Creative Roles

The conflict resolution architecture supports future roles:

```
┌─────────────────────────────────────────────────────────────┐
│              EXPANDED CREATIVE AUTHORITY                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DIRECTOR (primary)                                          │
│  ├── Final creative decisions                                │
│  ├── APPROVE/REVISE/REJECT                                   │
│  └── Must acknowledge CRITICAL continuity alerts             │
│                                                              │
│  DRAMATURG (future)                                          │
│  ├── Story structure authority                               │
│  ├── Can flag structural issues                              │
│  └── Conflicts with Director → escalation                    │
│                                                              │
│  VISUAL DIRECTOR (future)                                    │
│  ├── Aesthetic authority                                     │
│  ├── Can flag style violations                               │
│  └── Conflicts with Director → negotiation                   │
│                                                              │
│  MEMORY ARCHIVIST (current)                                  │
│  ├── Continuity advisor                                      │
│  ├── Cannot override Director                                │
│  └── CRITICAL alerts require acknowledgment                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 9.3 Escalation Paths

```python
class EscalationPath:
    """Future escalation paths for multi-role conflicts."""
    
    DIRECTOR_VS_ARCHIVIST = "director_acknowledge"
    DIRECTOR_VS_DRAMATURG = "orchestrator_review"
    DRAMATURG_VS_VISUAL = "negotiation_loop"
    ANY_BLOCKING = "human_escalation"
```

---

## 10. Implementation Tasks

### 10.1 Phase 3.5.1: Conflict Resolution Models

- [ ] Add `DirectorContinuityDecision` dataclass to `models/crew.py`
- [ ] Add `FilmContinuityTracker` class to `services/conflicts.py`
- [ ] Add `AlertSeverity` mapping to `ConflictSeverity` in `models/crew.py`

### 10.2 Phase 3.5.2: Conflict Resolver Service

- [ ] Create `services/director_memory_resolver.py`
- [ ] Implement `merge_director_memory_archivist()` function
- [ ] Implement `FilmContinuityTracker` class
- [ ] Add film-level debt tracking

### 10.3 Phase 3.5.3: Agent Executor Integration

- [ ] Update `_director_logic()` to call conflict resolver
- [ ] Update `_memory_archivist_logic()` to call conflict resolver
- [ ] Add `requires_acknowledgment` flag handling
- [ ] Add `escalation_flag` to output

### 10.4 Phase 3.5.4: Tests

- [ ] Test: Director APPROVE + no alerts → standard output
- [ ] Test: Director APPROVE + WARNING → debt tracked
- [ ] Test: Director APPROVE + CRITICAL → acknowledgment required
- [ ] Test: Director REVISE + any alerts → creative takes precedence
- [ ] Test: Film continuity debt aggregation
- [ ] Test: Backward compatibility with existing tests

---

## 11. File Structure

```
studio-backend/app/
├── models/
│   └── crew.py                    # Add DirectorContinuityDecision
├── services/
│   ├── conflicts.py               # Add FilmContinuityTracker
│   ├── director_memory_resolver.py # NEW: Conflict resolution logic
│   ├── director_evaluator.py      # Unchanged
│   ├── memory_archivist.py        # Unchanged
│   └── agent_executor.py          # Integrate conflict resolver
└── services/test_director_memory_resolver.py  # NEW: Tests
```

---

## 12. Summary

Phase 3.5 establishes a **non-blocking, advisory-only** conflict resolution system between Director and Memory Archivist:

1. **Director remains authoritative** - creative decisions are final
2. **Memory Archivist is advisory** - continuity reports attach to decisions
3. **CRITICAL alerts require acknowledgment** - but don't block
4. **Film-level tracking** - continuity debt accumulates across scenes
5. **Backward compatible** - all changes additive, existing tests pass
6. **Future extensible** - architecture supports additional creative roles

The key insight: this is not "conflict resolution" in the traditional sense (two agents disagreeing), but rather "output attachment" (adding continuity context to creative decisions without modifying them).