# Creative Decision Memory v1 — Implementation Complete

**Status**: ✅ Complete  
**Date**: Context Transfer Session  
**AGENTS.md Compliance**: Full

---

## Overview

Creative Decision Memory v1 allows filmmakers to explicitly save creative decisions to project memory. Following AGENTS.md rules, this feature:

- **Only saves when explicitly triggered** — never auto-saves from toggles, prompts, or passive observation
- **Shows exactly what will be saved** — before saving, with edit/discard/session-only options
- **Every memory is editable and forgettable** — no permanent creative profiles
- **Project-level scope only** — not user/global
- **Language-only tradeoff inference** — no numeric scoring

---

## Architecture

### Backend (Python/FastAPI)

**Routes Added**: `studio-backend/app/routes/projects.py`

```python
POST   /api/f51/studio/projects/{project_id}/creative-memories
GET    /api/f51/studio/projects/{project_id}/creative-memories
PATCH  /api/f51/studio/projects/{project_id}/creative-memories/{memory_id}
DELETE /api/f51/studio/projects/{project_id}/creative-memories/{memory_id}
```

**Storage Methods Added**: `studio-backend/app/services/project_store.py`

```python
save_creative_memory(project_id, memory_data) -> Dict[str, Any]
list_creative_memories(project_id) -> List[Dict[str, Any]]
update_creative_memory(project_id, memory_id, updates) -> Optional[Dict[str, Any]]
delete_creative_memory(project_id, memory_id) -> bool
```

**Storage Location**: Project JSON file at `memory_context.creative_memories[]`

### Frontend (React/TypeScript)

**Type Definitions**: `studio-app/src/types/creativeMemory.ts`

```typescript
type DecisionType = 
  | 'cut_revision'
  | 'scene_approval'
  | 'pacing_choice'
  | 'tension_adjustment'
  | 'visual_preference'
  | 'creative_note'

type InferredTradeoff = 
  | 'emotional_residue_favored'
  | 'structural_clarity_favored'
  | 'balanced_approach'
  | 'not_inferred'
```

**Modal Component**: `studio-app/src/components/SaveDecisionMemoryModal.tsx`
- Full UI for review-before-save workflow
- Editable note field
- Decision type selector
- Read-only tradeoff inference display
- Session-only / Save / Discard actions

**API Functions**: `studio-app/src/lib/studioApi.ts`

```typescript
saveCreativeDecisionMemory(projectId, memory)
listCreativeDecisionMemories(projectId)
updateCreativeDecisionMemory(projectId, memoryId, updates)
deleteCreativeDecisionMemory(projectId, memoryId)
```

**Integration Point**: `studio-app/src/components/ScreeningCinematicShowcase.tsx`
- "Save this decision to project memory" button in Cut Decision Journal
- Infers tradeoff from current `revisionEmphasis` + `tasteMemory` state
- Modal handlers for save/session-only/discard

---

## User Workflow

### In Screening Room — Cut Decision Journal

1. **Write a note** in the journal textarea (e.g., "This cut preserves the emotional pause before the reveal")
2. **Click "Save this decision to project memory"** button
3. **Review modal appears** showing:
   - Your note (editable)
   - Decision type selector
   - Studio's creative read (language only, no scores)
   - Source context (scene, revision, emphasis)
4. **Choose one**:
   - **"Save to Project Memory"** — saves permanently to project JSON
   - **"Keep Session-Only"** — discards without saving
   - **"Discard"** — closes modal without action

### Tradeoff Inference Logic

The Studio infers creative preference from:
- Current `revisionEmphasis` toggle (`emotional_residue` or `structural_clarity`)
- Taste memory confidence level (`emerging`, `consistent`, `strong`)

**Example Inferred Explanations**:
- "You consistently favor emotional residue and longer emotional carryover across cuts." (strong confidence)
- "You tend to favor structural clarity over emotional residue in your revision choices." (consistent confidence)
- "For this decision, you leaned toward emotional residue over structural clarity." (emerging confidence)

---

## Memory Structure

Each saved memory contains:

```typescript
{
  memory_id: "memory_a1b2c3d4e5f6",
  project_id: "project_xyz",
  decision_type: "cut_revision",
  user_note: "This cut preserves the emotional pause before the reveal",
  inferred_tradeoff: "emotional_residue_favored",
  inferred_tradeoff_explanation: "For this decision, you leaned toward...",
  source_context: {
    scene_id: "scene_003",
    revision_id: "revision_002",
    revision_emphasis: "emotional_residue",
    screen_location: "screening_room_journal"
  },
  saved_at: "2026-06-06T12:34:56.789Z",
  editable: true,
  forgettable: true
}
```

---

## AGENTS.md Compliance

✅ **Only save when explicitly triggered** — Button must be clicked, modal must be confirmed  
✅ **Never auto-save** — No passive observation, no toggle tracking without explicit save  
✅ **Show user exactly what will be saved** — Modal displays all fields before save  
✅ **Allow editing before saving** — User can edit note and decision type in modal  
✅ **Allow discard** — "Discard" button available  
✅ **Allow session-only mode** — "Keep Session-Only" button available  
✅ **Project-level only** — Stored in project JSON, not user profile  
✅ **Language-only tradeoff** — No scores, no percentages, plain English only  
✅ **Editable and forgettable** — `editable: true`, `forgettable: true` always set

---

## Co-Director Voice Examples

**Good (follows AGENTS.md)**:
- "For this session, you leaned toward emotional residue over structural clarity."
- "You tend to favor structural clarity in your revision choices."
- "The Studio noticed a consistent preference for emotional carryover."

**Bad (violates AGENTS.md)**:
- "Emotional residue score: 8.5/10" ❌ (no scores)
- "You always prefer emotional residue" ❌ (no absolute language)
- "This is the correct creative choice" ❌ (no deterministic certainty)

---

## Testing

**Health Check**: 40/40 passed  
**Backend Routes**: All 4 endpoints functional  
**Storage**: JSON persistence working  
**Frontend**: Modal component complete, integration functional  

---

## Future Enhancements (Not in v1)

- **Memory browsing UI** — view/edit/delete saved memories in a dedicated panel
- **Memory search** — filter by decision type, date, scene
- **Memory export** — include in pitch packs or archive snapshots
- **Multi-project taste persistence** — user-level (not project-level) taste profile
- **Memory-driven advisory** — use saved decisions to inform future co-director notes

---

## Files Modified/Created

### Created
- `studio-app/src/types/creativeMemory.ts` (type definitions)
- `studio-app/src/components/SaveDecisionMemoryModal.tsx` (modal UI)
- `CREATIVE_DECISION_MEMORY_V1.md` (this documentation)

### Modified
- `studio-backend/app/routes/projects.py` (4 new routes)
- `studio-backend/app/services/project_store.py` (4 new storage methods)
- `studio-app/src/lib/studioApi.ts` (4 new API functions)
- `studio-app/src/components/ScreeningCinematicShowcase.tsx` (modal integration)

---

**Implementation Complete** ✅
