# Batch H: Script Intelligence — Design Specification

**Date**: June 7, 2026  
**Status**: 🎨 DESIGN PHASE  
**Based On**: SCRIPT_INTELLIGENCE_SPEC.md (Requirements v1.0)

---

## Executive Summary

This design specification defines the technical architecture, API contracts, data models, and implementation details for the four Script Intelligence features. All designs follow AGENTS.md architecture rules: **thin routes → services → storage**.

### Design Principles

1. **Service-First Architecture** — All business logic in ScriptIntelligenceService
2. **Existing Service Integration** — Leverage emotional_arc, character_consistency, continuity_intelligence, style_consistency services
3. **No New Infrastructure** — Use existing SQLite storage, project_store patterns
4. **Co-Director Voice Compliance** — NO scores/percentages in outputs
5. **Performance Budget** — All analysis operations complete in <5 seconds (95th percentile)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Writer's Room (React)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Scene        │  │ Character    │  │ Tone         │          │
│  │ Breakdown    │  │ Arc Timeline │  │ Map          │          │
│  │ Panel        │  │ Component    │  │ Component    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │                   
          │                 │                 │                   
          ▼                 ▼                 ▼                   
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Routes Layer                          │
│  /api/projects/{id}/script-analysis/breakdown                   │
│  /api/projects/{id}/script-analysis/characters                  │
│  /api/projects/{id}/script-analysis/tone                        │
│  /api/projects/{id}/script-analysis/prompts                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              ScriptIntelligenceService (NEW)                     │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ analyze_scene_breakdown()                              │    │
│  │ analyze_character_arcs()                               │    │
│  │ analyze_tone_consistency()                             │    │
│  │ generate_prompts()                                     │    │
│  └────────────────────────────────────────────────────────┘    │
└───────┬─────────────────────────┬─────────────────┬─────────────┘
        │                         │                 │
        ▼                         ▼                 ▼
┌───────────────┐   ┌─────────────────────┐   ┌─────────────────┐
│ emotional_arc │   │ character_          │   │ continuity_     │
│ _service      │   │ consistency_service │   │ intelligence_   │
│ (EXISTING)    │   │ (EXISTING)          │   │ service         │
│               │   │                     │   │ (EXISTING)      │
└───────────────┘   └─────────────────────┘   └─────────────────┘
        │                         │                 │
        └─────────────────────────┴─────────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │  project_store  │
                 │   (EXISTING)    │
                 └─────────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ SQLite Database │
                 └─────────────────┘
```

### Data Flow Example: Scene Breakdown Analysis

1. **User Action**: User clicks "Analyze Script" in Writer's Room
2. **Frontend**: Calls `GET /api/projects/{id}/script-analysis/breakdown`
3. **Route**: Validates project_id, calls `script_intelligence_service.analyze_scene_breakdown(project_id)`
4. **Service**: 
   - Loads project from project_store
   - Extracts scenes data
   - Calls emotional_arc_service for emotional signals
   - Calls continuity_intelligence_service for transition warnings
   - Computes act structure, pacing analysis, transition quality
   - Returns structured analysis with co-director voice notes
5. **Route**: Formats response as Pydantic DTO, returns JSON
6. **Frontend**: Displays analysis in SceneBreakdownPanel component

---

## Service Layer Design

### ScriptIntelligenceService Class

**File**: `app/services/script_intelligence_service.py`

```python
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from collections import defaultdict

from app.services.project_store import project_store
from app.services.emotional_arc_service import emotional_arc_service
from app.services.character_consistency_service import character_consistency_service
from app.services.continuity_intelligence_service import continuity_intelligence_service
from app.services.style_consistency_service import style_consistency_service
from app.services.stability import ValidationError, StateError, log_stage_event, start_timer, elapsed_ms
from app.models.script_intelligence import (
    SceneBreakdownAnalysis,
    ActStructure,
    PacingInsight,
    TransitionWarning,
    CharacterArcAnalysis,
    CharacterProfile,
    CharacterArcGap,
    CharacterRelationship,
    ToneConsistencyAnalysis,
    ToneMapEntry,
    ToneShiftWarning,
    PromptGenerationResult,
    EnhancedPrompt,
)


class ScriptIntelligenceService:
    """
    Service for analyzing screenplay structure, character arcs,
    tone consistency, and generating render prompts.
    
    All outputs use co-director voice (no scores/percentages).
    """
    
    def __init__(self):
        self.emotional_arc = emotional_arc_service
        self.character_consistency = character_consistency_service
        self.continuity_intelligence = continuity_intelligence_service
        self.style_consistency = style_consistency_service
    
    # ── Feature 1: Scene Breakdown ──────────────────────────────────
    
    async def analyze_scene_breakdown(self, project_id: str) -> SceneBreakdownAnalysis:
        """
        Analyze screenplay structure: act structure, pacing, transitions.
        
        Returns:
            SceneBreakdownAnalysis with act structure, pacing insights,
            and transition warnings (all using co-director voice).
        """
        timer = start_timer()
        
        # Load project
        project = project_store.get_project(project_id)
        if not project:
            raise ValidationError(f"Project {project_id} not found")
        
        scenes = project.get("scenes", [])
        if len(scenes) < 2:
            raise ValidationError("At least 2 scenes required for breakdown analysis")
        
        # Detect act structure
        act_structure = self._detect_act_structure(scenes)
        
        # Analyze pacing
        pacing_insights = await self._analyze_pacing(scenes, project_id)
        
        # Analyze transitions
        transition_warnings = await self._analyze_transitions(scenes, project_id)
        
        duration = elapsed_ms(timer)
        log_stage_event(
            project_id=project_id,
            stage="script_intelligence_breakdown",
            duration_ms=duration,
            metadata={"scene_count": len(scenes)}
        )
        
        return SceneBreakdownAnalysis(
            total_scenes=len(scenes),
            estimated_runtime_minutes=self._estimate_runtime(scenes),
            act_structure=act_structure,
            pacing_insights=pacing_insights,
            transition_warnings=transition_warnings,
        )
    
    def _detect_act_structure(self, scenes: List[Dict]) -> ActStructure:
        """Detect 3-act structure from scene positions."""
        total = len(scenes)
        
        if total < 3:
            return ActStructure(
                act1_scenes=[],
                act2_scenes=[],
                act3_scenes=[],
                advisory="Not enough scenes for act structure detection. Add at least 3 scenes."
            )
        
        # Traditional 1/4, 1/2, 1/4 split
        act1_end = max(1, total // 4)
        act2_end = total - max(1, total // 4)
        
        act1_ids = [s.get("scene_id") for s in scenes[:act1_end]]
        act2_ids = [s.get("scene_id") for s in scenes[act1_end:act2_end]]
        act3_ids = [s.get("scene_id") for s in scenes[act2_end:]]
        
        # Co-director voice advisory
        advisory = self._generate_act_structure_advisory(len(act1_ids), len(act2_ids), len(act3_ids))
        
        return ActStructure(
            act1_scenes=act1_ids,
            act2_scenes=act2_ids,
            act3_scenes=act3_ids,
            advisory=advisory
        )
    
    # ... additional methods for pacing, transitions, etc.
    
    # ── Feature 2: Character Arc Analysis ──────────────────────────
    
    async def analyze_character_arcs(self, project_id: str) -> CharacterArcAnalysis:
        """Analyze character presence, arcs, and relationships."""
        # Implementation details...
        pass
    
    # ── Feature 3: Tone Consistency ────────────────────────────────
    
    async def analyze_tone_consistency(self, project_id: str) -> ToneConsistencyAnalysis:
        """Analyze emotional tone flow and consistency."""
        # Implementation details...
        pass
    
    # ── Feature 4: Prompt Generation ────────────────────────────────
    
    async def generate_prompts(self, project_id: str, scene_ids: Optional[List[str]] = None) -> PromptGenerationResult:
        """Generate enhanced render prompts from scene descriptions."""
        # Implementation details...
        pass


# Singleton instance
script_intelligence_service = ScriptIntelligenceService()
```

### Service Method Signatures


#### Public Methods (API-facing)

| Method | Returns | Description |
|--------|---------|-------------|
| `analyze_scene_breakdown(project_id)` | `SceneBreakdownAnalysis` | Act structure, pacing, transitions |
| `analyze_character_arcs(project_id)` | `CharacterArcAnalysis` | Character inventory, arcs, relationships |
| `analyze_tone_consistency(project_id)` | `ToneConsistencyAnalysis` | Tone map, shift warnings, consistency assessment |
| `generate_prompts(project_id, scene_ids?)` | `PromptGenerationResult` | Enhanced prompts for scenes |

#### Private Helper Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `_detect_act_structure(scenes)` | `ActStructure` | 3-act structure detection |
| `_estimate_runtime(scenes)` | `float` | Estimated total runtime in minutes |
| `_analyze_pacing(scenes, project_id)` | `List[PacingInsight]` | Pacing analysis per act |
| `_analyze_transitions(scenes, project_id)` | `List[TransitionWarning]` | Scene transition warnings |
| `_generate_act_structure_advisory(a1, a2, a3)` | `str` | Co-director voice act advisory |
| `_extract_characters(scenes)` | `Dict[str, CharacterProfile]` | Character extraction from scenes |
| `_detect_arc_gaps(character_scenes)` | `List[CharacterArcGap]` | Character disappearance detection |
| `_build_relationship_matrix(scenes)` | `List[CharacterRelationship]` | Co-occurrence analysis |
| `_build_tone_map(scenes, project_id)` | `List[ToneMapEntry]` | Tone per scene |
| `_detect_tone_shifts(tone_map)` | `List[ToneShiftWarning]` | Jarring tone transitions |
| `_enhance_scene_prompt(scene, style_guide)` | `EnhancedPrompt` | Prompt enhancement logic |
| `_normalize_character_name(name)` | `str` | Character name normalization |

---

## Data Models (Pydantic)

### File: `app/models/script_intelligence.py`

```python
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Feature 1: Scene Breakdown Models ──────────────────────────────

class ActStructure(BaseModel):
    """3-act structure detection result."""
    act1_scenes: List[str] = Field(default_factory=list, description="Scene IDs in Act 1 (Setup)")
    act2_scenes: List[str] = Field(default_factory=list, description="Scene IDs in Act 2 (Confrontation)")
    act3_scenes: List[str] = Field(default_factory=list, description="Scene IDs in Act 3 (Resolution)")
    advisory: str = Field(default="", description="Co-director voice act structure guidance")


class PacingInsight(BaseModel):
    """Pacing analysis for act or scene range."""
    act_number: int = Field(..., description="Act number (1, 2, or 3)")
    pacing_label: str = Field(..., description="fast | moderate | slow")
    advisory: str = Field(default="", description="Co-director voice pacing note")


class TransitionWarning(BaseModel):
    """Warning about scene transition quality."""
    from_scene_id: str
    to_scene_id: str
    issue_type: str = Field(..., description="jarring | unmotivated | continuity_break")
    advisory: str = Field(default="", description="Co-director voice transition note")


class SceneBreakdownAnalysis(BaseModel):
    """Complete scene breakdown analysis result."""
    total_scenes: int
    estimated_runtime_minutes: float = Field(..., description="Estimated total runtime")
    act_structure: ActStructure
    pacing_insights: List[PacingInsight] = Field(default_factory=list)
    transition_warnings: List[TransitionWarning] = Field(default_factory=list)


# ── Feature 2: Character Arc Models ────────────────────────────────

class CharacterProfile(BaseModel):
    """Character inventory entry."""
    character_id: str = Field(..., description="Normalized character identifier")
    name: str = Field(..., description="Character display name")
    first_appearance_scene: str = Field(..., description="Scene ID of first appearance")
    scene_count: int = Field(..., description="Number of scenes character appears in")
    scene_ids: List[str] = Field(default_factory=list, description="All scene IDs with character")


class CharacterArcGap(BaseModel):
    """Detected gap in character arc."""
    character_id: str
    character_name: str
    gap_start_scene: str = Field(..., description="Scene before disappearance")
    gap_end_scene: str = Field(..., description="Scene after reappearance")
    gap_scene_count: int = Field(..., description="Number of scenes absent")
    advisory: str = Field(default="", description="Co-director voice arc gap note")


class CharacterRelationship(BaseModel):
    """Character co-occurrence relationship."""
    character_a: str
    character_b: str
    shared_scene_count: int = Field(..., description="Number of scenes together")
    shared_scene_ids: List[str] = Field(default_factory=list)


class CharacterArcAnalysis(BaseModel):
    """Complete character arc analysis result."""
    character_count: int
    characters: List[CharacterProfile] = Field(default_factory=list)
    arc_gaps: List[CharacterArcGap] = Field(default_factory=list)
    relationships: List[CharacterRelationship] = Field(default_factory=list)
    overall_advisory: str = Field(default="", description="High-level character arc guidance")


# ── Feature 3: Tone Consistency Models ──────────────────────────────

class ToneMapEntry(BaseModel):
    """Tone for a single scene."""
    scene_id: str
    scene_title: str = Field(default="")
    emotional_tone: str = Field(..., description="joyful | tense | melancholic | hopeful | dread | neutral | etc.")
    tone_source: str = Field(..., description="manual | inferred | emotional_target")


class ToneShiftWarning(BaseModel):
    """Warning about jarring tone shift."""
    from_scene_id: str
    to_scene_id: str
    from_tone: str
    to_tone: str
    severity: str = Field(..., description="jarring | noticeable | subtle")
    advisory: str = Field(default="", description="Co-director voice tone shift note")


class ToneConsistencyAnalysis(BaseModel):
    """Complete tone consistency analysis result."""
    tone_map: List[ToneMapEntry] = Field(default_factory=list)
    tone_shifts: List[ToneShiftWarning] = Field(default_factory=list)
    consistency_label: str = Field(..., description="consistent | mostly_consistent | inconsistent | too_early")
    overall_advisory: str = Field(default="", description="High-level tone consistency guidance")


# ── Feature 4: Prompt Generation Models ─────────────────────────────

class EnhancedPrompt(BaseModel):
    """Enhanced render prompt for a scene."""
    scene_id: str
    original_description: str = Field(..., description="Original scene description text")
    enhanced_prompt: str = Field(..., description="Render-ready enhanced prompt")
    style_tags: List[str] = Field(default_factory=list, description="Applied style elements")
    character_references: List[str] = Field(default_factory=list, description="Character names in prompt")
    is_user_edited: bool = Field(default=False, description="True if user manually edited prompt")


class PromptGenerationResult(BaseModel):
    """Result of prompt generation for multiple scenes."""
    prompts: List[EnhancedPrompt] = Field(default_factory=list)
    style_consistency_note: str = Field(default="", description="Co-director voice style note")
```

---

## API Routes Design

### File: `app/routes/script_intelligence.py` (NEW)


```python
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.script_intelligence_service import script_intelligence_service
from app.services.stability import ValidationError, StateError
from app.models.script_intelligence import (
    SceneBreakdownAnalysis,
    CharacterArcAnalysis,
    ToneConsistencyAnalysis,
    PromptGenerationResult,
)

router = APIRouter(prefix="/api/projects", tags=["script-intelligence"])


# ── Feature 1: Scene Breakdown Endpoint ────────────────────────────

@router.get("/{project_id}/script-analysis/breakdown", response_model=SceneBreakdownAnalysis)
async def get_scene_breakdown(project_id: str):
    """
    Analyze screenplay structure: act structure, pacing, transitions.
    
    Returns:
        SceneBreakdownAnalysis with act structure, pacing insights,
        and transition warnings (all using co-director voice).
    """
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        analysis = await script_intelligence_service.analyze_scene_breakdown(project_id)
        return analysis
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StateError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Feature 2: Character Arc Endpoint ───────────────────────────────

@router.get("/{project_id}/script-analysis/characters", response_model=CharacterArcAnalysis)
async def get_character_arcs(project_id: str):
    """
    Analyze character presence, arcs, and relationships.
    
    Returns:
        CharacterArcAnalysis with character inventory, arc gaps,
        and relationship matrix (all using co-director voice).
    """
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        analysis = await script_intelligence_service.analyze_character_arcs(project_id)
        return analysis
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StateError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Feature 3: Tone Consistency Endpoint ────────────────────────────

@router.get("/{project_id}/script-analysis/tone", response_model=ToneConsistencyAnalysis)
async def get_tone_consistency(project_id: str):
    """
    Analyze emotional tone flow and consistency.
    
    Returns:
        ToneConsistencyAnalysis with tone map, shift warnings,
        and consistency assessment (all using co-director voice).
    """
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        analysis = await script_intelligence_service.analyze_tone_consistency(project_id)
        return analysis
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StateError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Feature 4: Prompt Generation Endpoint ───────────────────────────

class PromptGenerationRequest(BaseModel):
    """Request body for prompt generation."""
    scene_ids: Optional[List[str]] = None  # If None, generate for all scenes


@router.post("/{project_id}/script-analysis/prompts", response_model=PromptGenerationResult)
async def generate_scene_prompts(project_id: str, request: PromptGenerationRequest):
    """
    Generate enhanced render prompts from scene descriptions.
    
    Returns:
        PromptGenerationResult with enhanced prompts for requested scenes.
    """
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        result = await script_intelligence_service.generate_prompts(
            project_id=project_id,
            scene_ids=request.scene_ids
        )
        return result
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StateError as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Route Registration

Add to `app/routes/__init__.py`:

```python
from app.routes import script_intelligence

# In the FastAPI app setup:
app.include_router(script_intelligence.router)
```

### API Endpoint Summary

| Endpoint | Method | Description | Response Model |
|----------|--------|-------------|----------------|
| `/api/projects/{id}/script-analysis/breakdown` | GET | Scene breakdown analysis | `SceneBreakdownAnalysis` |
| `/api/projects/{id}/script-analysis/characters` | GET | Character arc analysis | `CharacterArcAnalysis` |
| `/api/projects/{id}/script-analysis/tone` | GET | Tone consistency analysis | `ToneConsistencyAnalysis` |
| `/api/projects/{id}/script-analysis/prompts` | POST | Generate enhanced prompts | `PromptGenerationResult` |

---

## Algorithm Specifications

### Algorithm 1: Act Structure Detection

**Function**: `_detect_act_structure(scenes: List[Dict]) -> ActStructure`

**Pseudocode**:
```
INPUT: scenes (list of scene dictionaries)
OUTPUT: ActStructure with act1_scenes, act2_scenes, act3_scenes, advisory

1. IF len(scenes) < 3:
     RETURN ActStructure with empty lists and advisory "Not enough scenes"

2. total_scenes = len(scenes)

3. Calculate act boundaries (traditional 1/4, 1/2, 1/4 split):
   act1_end = max(1, total_scenes // 4)
   act2_end = total_scenes - max(1, total_scenes // 4)

4. Partition scenes:
   act1_scenes = scenes[0:act1_end] scene IDs
   act2_scenes = scenes[act1_end:act2_end] scene IDs
   act3_scenes = scenes[act2_end:] scene IDs

5. Generate co-director voice advisory:
   IF len(act2_scenes) < len(act1_scenes) + len(act3_scenes):
     advisory = "Act 2 feels compressed—consider expanding the confrontation"
   ELIF len(act2_scenes) > 2 * (len(act1_scenes) + len(act3_scenes)):
     advisory = "Act 2 dominates the structure—the setup and resolution risk feeling rushed"
   ELSE:
     advisory = "Act structure follows traditional rhythm—setup, confrontation, resolution"

6. RETURN ActStructure(act1_scenes, act2_scenes, act3_scenes, advisory)
```

**Key Design Decisions**:
- **Choice**: Traditional 1/4, 1/2, 1/4 split (not content-aware)
- **Rationale**: Simple, predictable, works for v1; content-aware can be v2
- **Edge Case**: Minimum 3 scenes required for meaningful act division

---

### Algorithm 2: Pacing Analysis

**Function**: `_analyze_pacing(scenes: List[Dict], project_id: str) -> List[PacingInsight]`

**Pseudocode**:
```
INPUT: scenes, project_id
OUTPUT: List[PacingInsight] (one per act)

1. Detect act structure
2. FOR each act (1, 2, 3):
     a. Get scenes in act
     b. Calculate avg_description_length = mean(len(scene["text"]) for scene in act_scenes)
     c. Determine pacing_label:
        IF avg_description_length < 100: pacing_label = "fast"
        ELIF avg_description_length < 250: pacing_label = "moderate"
        ELSE: pacing_label = "slow"
     d. Generate co-director advisory based on act number and pacing:
        - Act 1 fast: "Setup moves quickly—ensure emotional grounding doesn't get lost"
        - Act 2 slow: "Confrontation lingers—risk of losing momentum"
        - Act 3 fast: "Resolution feels rushed—emotional payoff may need more space"
        - etc.
     e. Append PacingInsight(act_number, pacing_label, advisory)

3. RETURN pacing_insights
```

**Key Design Decisions**:
- **Proxy for pacing**: Scene description length (longer = slower)
- **Thresholds**: <100 chars = fast, <250 = moderate, ≥250 = slow
- **Rationale**: Simple heuristic for v1; can add dialogue/action detection in v2

---

### Algorithm 3: Character Arc Gap Detection

**Function**: `_detect_arc_gaps(character_scenes: Dict[str, List[str]]) -> List[CharacterArcGap]`

**Pseudocode**:
```
INPUT: character_scenes = {character_id: [scene_ids in order]}
OUTPUT: List[CharacterArcGap]

1. gaps = []
2. FOR each character_id, scene_ids in character_scenes:
     a. IF len(scene_ids) == 1:
          # Single appearance = unresolved arc
          advisory = f"{character_name}'s arc feels unresolved—they appear once without follow-through"
          gaps.append(CharacterArcGap(..., advisory))
     
     b. FOR each consecutive pair (scene_i, scene_i+1) in scene_ids:
          scene_index_i = global_scene_index(scene_i)
          scene_index_i+1 = global_scene_index(scene_i+1)
          gap_size = scene_index_i+1 - scene_index_i - 1
          
          IF gap_size >= 3:
            # Character disappears for 3+ scenes
            advisory = f"{character_name} disappears for {gap_size} scenes between {scene_i} and {scene_i+1}—arc continuity risks weakening"
            gaps.append(CharacterArcGap(
              character_id,
              character_name,
              gap_start_scene=scene_i,
              gap_end_scene=scene_i+1,
              gap_scene_count=gap_size,
              advisory=advisory
            ))

3. RETURN gaps
```

**Key Design Decisions**:
- **Gap threshold**: 3+ consecutive scenes without character = significant gap
- **Single appearance**: Flagged as unresolved arc
- **Rationale**: Helps filmmakers catch dropped character threads

---

### Algorithm 4: Tone Shift Detection

**Function**: `_detect_tone_shifts(tone_map: List[ToneMapEntry]) -> List[ToneShiftWarning]`

**Pseudocode**:
```
INPUT: tone_map (list of ToneMapEntry with scene_id, emotional_tone)
OUTPUT: List[ToneShiftWarning]

1. Define tone compatibility matrix:
   COMPATIBLE_PAIRS = {
     ("joyful", "hopeful"), ("tense", "dread"), ("melancholic", "somber"),
     # ... more compatible pairs
   }
   
   JARRING_PAIRS = {
     ("joyful", "dread"), ("hopeful", "despair"), ("calm", "panic"),
     # ... more jarring pairs
   }

2. warnings = []
3. FOR each consecutive pair (tone_i, tone_i+1) in tone_map:
     from_tone = tone_i.emotional_tone
     to_tone = tone_i+1.emotional_tone
     
     IF (from_tone, to_tone) in JARRING_PAIRS:
       severity = "jarring"
       advisory = f"The shift from {from_tone} to {to_tone} risks whiplash—consider planting tension earlier"
     
     ELIF from_tone != to_tone AND (from_tone, to_tone) NOT in COMPATIBLE_PAIRS:
       severity = "noticeable"
       advisory = f"The transition from {from_tone} to {to_tone} could use a bridging beat"
     
     ELSE:
       CONTINUE  # No warning needed
     
     warnings.append(ToneShiftWarning(
       from_scene_id=tone_i.scene_id,
       to_scene_id=tone_i+1.scene_id,
       from_tone=from_tone,
       to_tone=to_tone,
       severity=severity,
       advisory=advisory
     ))

4. RETURN warnings
```

**Key Design Decisions**:
- **Tone compatibility**: Predefined matrix of compatible/jarring pairs
- **Severity levels**: jarring (incompatible), noticeable (needs bridge), subtle (ignore)
- **Rationale**: Helps filmmakers identify unintentional tonal breaks

---

### Algorithm 5: Prompt Enhancement

**Function**: `_enhance_scene_prompt(scene: Dict, style_guide: Dict) -> EnhancedPrompt`

**Pseudocode**:
```
INPUT: scene (with text, location, time_of_day, characters)
       style_guide (from style_consistency_service)
OUTPUT: EnhancedPrompt

1. Extract visual keywords from scene description:
   description = scene["text"]
   keywords = extract_keywords(description)  # "rain", "dark", "isolated", etc.

2. Build base prompt from scene structure:
   location = scene.get("location", "")
   time_of_day = scene.get("time_of_day", "")
   base = f"{location} - {time_of_day.upper()}. {description[:200]}"

3. Add cinematic language:
   IF "tension" in keywords: base += ", dramatic lighting, tight framing"
   IF "rain" in keywords: base += ", wet surfaces, rain visible"
   IF "isolated" in keywords: base += ", wide shot, environmental storytelling"
   # ... more keyword mappings

4. Apply style consistency:
   IF style_guide has director_signature:
     base += f", {style_guide['director_signature']}"
   IF style_guide has color_palette:
     base += f", {style_guide['color_palette']}"

5. Add character references (for consistency):
   FOR each character in scene:
     char_desc = get_character_description(character)  # from character_consistency_service
     base += f", featuring {character} ({char_desc})"

6. Truncate to provider limit (512 characters for Runway):
   enhanced_prompt = base[:512]

7. RETURN EnhancedPrompt(
     scene_id=scene["scene_id"],
     original_description=description,
     enhanced_prompt=enhanced_prompt,
     style_tags=["dramatic_lighting", "rain", etc.],
     character_references=[character names],
     is_user_edited=False
   )
```

**Key Design Decisions**:
- **Keyword extraction**: Simple text matching (can upgrade to NLP in v2)
- **Cinematic language mapping**: Predefined keyword → prompt fragment dictionary
- **Style consistency**: Integrate director signature from style_consistency_service
- **Character consistency**: Reference character descriptions from character_consistency_service
- **Truncation**: Respect provider limits (512 chars for Runway)

---

## Frontend Component Architecture

### Component Hierarchy

```
WritersRoom (EXISTING)
  └─ ScriptIntelligencePanel (NEW)
       ├─ SceneBreakdownPanel (NEW)
       │    ├─ ActStructureVisualization
       │    ├─ PacingTimeline
       │    └─ TransitionWarningsList
       │
       ├─ CharacterArcPanel (NEW)
       │    ├─ CharacterInventoryList
       │    ├─ CharacterArcTimeline
       │    ├─ ArcGapWarnings
       │    └─ RelationshipMatrix
       │
       ├─ ToneConsistencyPanel (NEW)
       │    ├─ ToneMapVisualization
       │    ├─ ToneShiftWarnings
       │    └─ ToneConsistencyBadge
       │
       └─ PromptGenerationPanel (NEW)
            ├─ PromptPreviewList
            ├─ PromptEditor
            └─ StyleConsistencyNote

PrevisRoom (EXISTING)
  └─ PromptField (MODIFIED)
       └─ Uses auto-generated prompts from script intelligence
```

### Component Specifications

#### ScriptIntelligencePanel

**File**: `studio-app/src/components/ScriptIntelligencePanel.tsx`

**Purpose**: Container for all 4 analysis features in Writer's Room

**Props**:
```typescript
interface ScriptIntelligencePanelProps {
  projectId: string;
  sceneCount: number;
  onAnalysisComplete?: (analysisType: string) => void;
}
```

**State Management**:
```typescript
const [activeTab, setActiveTab] = useState<'breakdown' | 'characters' | 'tone' | 'prompts'>('breakdown');
const [isAnalyzing, setIsAnalyzing] = useState(false);
const [error, setError] = useState<string | null>(null);
```

**Layout**:
- Tabbed interface (4 tabs for 4 features)
- Collapsible panel (starts collapsed to avoid overwhelm)
- "Analyze Script" button triggers all analyses
- Loading state with spinner + "Analyzing..." message
- Error boundary for graceful failure handling


---

#### SceneBreakdownPanel

**File**: `studio-app/src/components/SceneBreakdownPanel.tsx`

**Purpose**: Display scene breakdown analysis

**Props**:
```typescript
interface SceneBreakdownPanelProps {
  projectId: string;
}
```

**Data Fetching**:
```typescript
const { data: breakdown, isLoading, error } = useQuery(
  ['scene-breakdown', projectId],
  () => fetch(`/api/projects/${projectId}/script-analysis/breakdown`).then(r => r.json())
);
```

**Visual Layout**:
1. **Summary Stats** (top):
   - Total scenes: 12
   - Estimated runtime: ~8-10 minutes
   - Average scene duration: ~45 seconds

2. **Act Structure** (middle):
   - Visual dividers showing Act 1 / Act 2 / Act 3
   - Scene count per act
   - Co-director advisory in amber badge

3. **Pacing Timeline** (middle):
   - Horizontal bar chart showing pacing per act
   - Color coded: fast (red), moderate (yellow), slow (blue)
   - Co-director notes below each act

4. **Transition Warnings** (bottom):
   - List of scene transitions with issues
   - Format: "Scene 3 → Scene 4: jarring emotional shift"
   - Co-director advisory per warning

**Styling**:
- Match PrevisCinematicShowcase style (zinc palette, 11-12px text)
- Amber badges for warnings
- Rose badges for critical issues
- Responsive grid for mobile

---

#### CharacterArcPanel

**File**: `studio-app/src/components/CharacterArcPanel.tsx`

**Purpose**: Display character arc analysis

**Props**:
```typescript
interface CharacterArcPanelProps {
  projectId: string;
}
```

**Visual Layout**:
1. **Character Inventory** (top):
   - List of all characters with appearance counts
   - Sorted by frequency (most frequent first)
   - Format: "SARAH (8 scenes) • First: Scene 1"

2. **Character Arc Timeline** (middle):
   - Grid visualization showing character presence per scene
   - X-axis: Scenes, Y-axis: Characters
   - Cell color: present (zinc-400), absent (zinc-800)
   - Hover shows scene title

3. **Arc Gap Warnings** (middle):
   - List of detected gaps
   - Format: "SARAH disappears for 4 scenes (Scene 3 → Scene 8)"
   - Co-director advisory in rose badge

4. **Relationship Matrix** (bottom):
   - Table showing character co-occurrences
   - Format: "SARAH & JAKE: 3 scenes together"
   - Highlight isolated characters (never share scenes)

**Styling**:
- Grid layout for timeline (CSS Grid)
- Zinc color palette for presence/absence
- Rose badges for arc gaps
- Amber badges for relationship warnings

---

#### ToneConsistencyPanel

**File**: `studio-app/src/components/ToneConsistencyPanel.tsx`

**Purpose**: Display tone consistency analysis


**Props**:
```typescript
interface ToneConsistencyPanelProps {
  projectId: string;
}
```

**Visual Layout**:
1. **Tone Map Visualization** (top):
   - Horizontal timeline showing tone per scene
   - Color-coded blocks: joyful (amber), tense (rose), melancholic (blue), etc.
   - Scene titles on hover
   - Legend showing tone → color mapping

2. **Consistency Badge** (top-right):
   - Label: "Consistent" | "Mostly Consistent" | "Inconsistent"
   - Color: green | amber | rose
   - Co-director overall advisory below

3. **Tone Shift Warnings** (bottom):
   - List of jarring transitions
   - Format: "Scene 2 (Joyful) → Scene 3 (Dread): Jarring shift"
   - Co-director advisory per shift
   - Severity indicator: 🔴 Jarring, 🟡 Noticeable, 🟢 Subtle

**Color Palette** (tone → color):
```typescript
const TONE_COLORS = {
  joyful: 'bg-amber-400',
  hopeful: 'bg-yellow-300',
  tense: 'bg-rose-400',
  dread: 'bg-red-600',
  melancholic: 'bg-blue-400',
  somber: 'bg-slate-500',
  calm: 'bg-green-300',
  neutral: 'bg-zinc-400',
};
```

**Accessibility**:
- Don't rely on color alone (add text labels)
- ARIA labels for timeline blocks
- Keyboard navigation through tone entries

---

#### PromptGenerationPanel

**File**: `studio-app/src/components/PromptGenerationPanel.tsx`


**Purpose**: Generate and edit enhanced prompts

**Props**:
```typescript
interface PromptGenerationPanelProps {
  projectId: string;
  sceneIds?: string[];
}
```

**Visual Layout**:
1. **Generate Button** (top):
   - "Generate Prompts for All Scenes" button
   - Or "Generate for Selected Scenes" if scenes selected
   - Loading state during generation

2. **Prompt Preview List** (middle):
   - Card per scene showing:
     - Scene title
     - Original description (collapsed by default)
     - Enhanced prompt (editable textarea)
     - Style tags (badges): "dramatic_lighting", "rain", etc.
     - Character references
     - "Edit Prompt" / "Save Edit" / "Revert" buttons

3. **Style Consistency Note** (bottom):
   - Co-director voice note about style consistency
   - Example: "Prompts maintain visual consistency with your established signature"

**State Management**:
```typescript
const [prompts, setPrompts] = useState<EnhancedPrompt[]>([]);
const [editingPromptId, setEditingPromptId] = useState<string | null>(null);
const [editedText, setEditedText] = useState<string>('');

const handleSaveEdit = async (sceneId: string) => {
  // Save edited prompt to backend
  // Mark as user-edited to prevent re-generation
};
```

**Integration with Previs**:
- When user clicks "Next: Go to Storyboard", prompts auto-populate
- Previs prompt field shows: "Auto-generated from script" badge
- User can still edit in Previs

---

## State Management Strategy

### Data Fetching Pattern

Use **React Query** for all API calls (consistent with existing codebase):


```typescript
// Example: Scene Breakdown Query
const useSceneBreakdown = (projectId: string) => {
  return useQuery(
    ['scene-breakdown', projectId],
    async () => {
      const response = await fetch(`/api/projects/${projectId}/script-analysis/breakdown`);
      if (!response.ok) throw new Error('Failed to fetch scene breakdown');
      return response.json() as Promise<SceneBreakdownAnalysis>;
    },
    {
      enabled: !!projectId,
      staleTime: 5 * 60 * 1000, // Cache for 5 minutes
      retry: 2,
    }
  );
};
```

### Cache Invalidation Strategy

Invalidate analysis cache when scenes change:

```typescript
// In WritersRoom component
const queryClient = useQueryClient();

const handleSceneUpdate = () => {
  // Invalidate all script intelligence queries
  queryClient.invalidateQueries(['scene-breakdown', projectId]);
  queryClient.invalidateQueries(['character-arcs', projectId]);
  queryClient.invalidateQueries(['tone-consistency', projectId]);
  queryClient.invalidateQueries(['prompts', projectId]);
};
```

### Local State (UI Only)

Use `useState` for UI-only state:
- Tab selection: `activeTab`
- Panel collapse state: `isPanelCollapsed`
- Editing state: `editingPromptId`
- Loading spinners: `isAnalyzing`

### No localStorage for Critical State

Per AGENTS.md: "No localStorage for critical state — backend is source of truth"

- ❌ Don't cache analysis results in localStorage
- ✅ Use React Query cache (memory only)
- ✅ Re-fetch from backend on page reload

---

## Database Schema (Optional Persistence)


### Decision: Compute On-Demand (No Persistence for v1)

**Rationale**:
- All analyses are fast (<5 seconds)
- Scene data changes frequently during writing phase
- Caching adds complexity without significant benefit
- React Query provides sufficient in-memory caching

**Alternative for v2** (if analysis becomes expensive):

```sql
-- Optional table for caching analysis results
CREATE TABLE script_intelligence_cache (
    cache_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    analysis_type TEXT NOT NULL, -- 'breakdown', 'characters', 'tone', 'prompts'
    result_json TEXT NOT NULL,    -- JSON blob of analysis result
    scene_fingerprint TEXT NOT NULL, -- Hash of scene data for invalidation
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_script_intelligence_project ON script_intelligence_cache(project_id, analysis_type);
```

**Fingerprint Calculation** (for cache invalidation):
```python
def calculate_scene_fingerprint(scenes: List[Dict]) -> str:
    """Generate hash of scene data for cache invalidation."""
    scene_ids = [s.get("scene_id") for s in scenes]
    scene_texts = [s.get("text", "") for s in scenes]
    combined = "|".join(scene_ids + scene_texts)
    return hashlib.sha256(combined.encode()).hexdigest()
```

---

## Error Handling Patterns

### Service Layer Errors

```python
# In ScriptIntelligenceService
async def analyze_scene_breakdown(self, project_id: str) -> SceneBreakdownAnalysis:
    timer = start_timer()
    
    try:
        # Validation
        project = project_store.get_project(project_id)
        if not project:
            raise ValidationError(f"Project {project_id} not found")
        
        scenes = project.get("scenes", [])
        if len(scenes) < 2:
            raise ValidationError("At least 2 scenes required for breakdown analysis")
        
        # Business logic
        result = self._perform_analysis(scenes, project_id)
        
        # Success logging
        log_stage_event(
            project_id=project_id,
            stage="script_intelligence_breakdown",
            duration_ms=elapsed_ms(timer),
            metadata={"scene_count": len(scenes)}
        )
        
        return result
    
    except ValidationError:
        # Re-raise validation errors (route will convert to 400)
        raise
    
    except Exception as e:
        # Log unexpected errors
        log_stage_event(
            project_id=project_id,
            stage="script_intelligence_breakdown",
            duration_ms=elapsed_ms(timer),
            metadata={"error": str(e)}
        )
        raise StateError(f"Analysis failed: {str(e)}")
```

### Route Layer Errors

```python
# In script_intelligence.py routes
@router.get("/{project_id}/script-analysis/breakdown")
async def get_scene_breakdown(project_id: str):
    if not project_id.strip():
        raise HTTPException(status_code=400, detail="project_id required")
    
    try:
        analysis = await script_intelligence_service.analyze_scene_breakdown(project_id)
        return analysis
    
    except ValidationError as e:
        # User error (bad input)
        raise HTTPException(status_code=400, detail=str(e))
    
    except StateError as e:
        # Server error (analysis failed)
        raise HTTPException(status_code=500, detail=str(e))
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Frontend Error Handling

```typescript
// In SceneBreakdownPanel component
const { data, isLoading, error } = useSceneBreakdown(projectId);

if (isLoading) {
  return <LoadingSpinner message="Analyzing screenplay structure..." />;
}

if (error) {
  return (
    <ErrorPanel
      message="Failed to analyze scene breakdown"
      details={error.message}
      onRetry={() => queryClient.invalidateQueries(['scene-breakdown', projectId])}
    />
  );
}

if (!data || data.total_scenes === 0) {
  return (
    <EmptyState
      icon={DocumentIcon}
      title="No scenes to analyze"
      message="Add at least 2 scenes to see breakdown analysis"
    />
  );
}

return <SceneBreakdownDisplay data={data} />;
```

### User-Facing Error Messages

**Validation Errors** (400):
- "Project not found"
- "At least 2 scenes required for breakdown analysis"
- "No characters detected in scenes"
- "Scene descriptions too short for tone inference"

**State Errors** (500):
- "Analysis failed. Please try again."
- "Unable to load project data"
- "Service temporarily unavailable"

**Timeout Errors**:
- "Analysis is taking longer than expected. Check back shortly."

---

## Performance Optimization Strategy


### Backend Optimization

#### 1. Lazy Analysis Execution
```python
# Only compute what's requested
# Don't run all 4 analyses on every endpoint call

# ✅ Good: Each endpoint analyzes independently
@router.get("/{project_id}/script-analysis/breakdown")
async def get_scene_breakdown(project_id: str):
    return await script_intelligence_service.analyze_scene_breakdown(project_id)

# ❌ Bad: Single endpoint that runs all analyses
@router.get("/{project_id}/script-analysis")
async def get_all_analyses(project_id: str):
    # Don't do this - too slow
    breakdown = await script_intelligence_service.analyze_scene_breakdown(project_id)
    characters = await script_intelligence_service.analyze_character_arcs(project_id)
    tone = await script_intelligence_service.analyze_tone_consistency(project_id)
    prompts = await script_intelligence_service.generate_prompts(project_id)
    return {breakdown, characters, tone, prompts}
```

#### 2. Scene Limit Enforcement
```python
# Cap analysis at 50 scenes to prevent performance degradation
MAX_SCENES_FOR_ANALYSIS = 50

def _validate_scene_count(scenes: List[Dict]) -> None:
    if len(scenes) > MAX_SCENES_FOR_ANALYSIS:
        raise ValidationError(
            f"Analysis limited to first {MAX_SCENES_FOR_ANALYSIS} scenes. "
            f"Your script has {len(scenes)} scenes."
        )
```

#### 3. Timeout Guards
```python
import asyncio

async def analyze_scene_breakdown(self, project_id: str) -> SceneBreakdownAnalysis:
    try:
        # 5-second timeout per analysis
        return await asyncio.wait_for(
            self._perform_breakdown_analysis(project_id),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        raise StateError("Analysis timeout - script may be too complex")
```


### Frontend Optimization

#### 1. Lazy Loading Panels
```typescript
// Only load analysis when tab is active
const ScriptIntelligencePanel = ({ projectId }) => {
  const [activeTab, setActiveTab] = useState<'breakdown' | 'characters' | 'tone' | 'prompts'>('breakdown');
  
  return (
    <div>
      <TabNav activeTab={activeTab} onChange={setActiveTab} />
      
      {/* Only render active tab */}
      {activeTab === 'breakdown' && <SceneBreakdownPanel projectId={projectId} />}
      {activeTab === 'characters' && <CharacterArcPanel projectId={projectId} />}
      {activeTab === 'tone' && <ToneConsistencyPanel projectId={projectId} />}
      {activeTab === 'prompts' && <PromptGenerationPanel projectId={projectId} />}
    </div>
  );
};
```

#### 2. Query Stale Time Optimization
```typescript
// Cache analysis results for 5 minutes
const useSceneBreakdown = (projectId: string) => {
  return useQuery(
    ['scene-breakdown', projectId],
    () => fetchSceneBreakdown(projectId),
    {
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
    }
  );
};
```

#### 3. Virtualized Lists (for large scripts)
```typescript
// Use react-window for 50+ scenes
import { FixedSizeList } from 'react-window';

const CharacterArcTimeline = ({ scenes, characters }) => {
  if (scenes.length > 20) {
    // Virtualize for performance
    return (
      <FixedSizeList
        height={400}
        itemCount={characters.length}
        itemSize={40}
        width="100%"
      >
        {({ index, style }) => (
          <CharacterRow
            character={characters[index]}
            scenes={scenes}
            style={style}
          />
        )}
      </FixedSizeList>
    );
  }
  
  // Regular rendering for small scripts
  return characters.map(char => <CharacterRow character={char} scenes={scenes} />);
};
```

---

## UI/UX Wireframes (Text Descriptions)

### Scene Breakdown Panel

```
┌─────────────────────────────────────────────────────────────┐
│ Scene Breakdown Analysis                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ 📊 Script Summary                                            │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Total Scenes: 12          Estimated Runtime: ~8-10 min │   │
│ │ Avg Scene Duration: ~45 seconds                        │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ 🎬 Act Structure                                             │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ ACT 1: SETUP              │ ACT 2: CONFRONTATION      │   │
│ │ Scenes 1-3 (3 scenes)     │ Scenes 4-9 (6 scenes)     │   │
│ │                            │                            │   │
│ │ ACT 3: RESOLUTION                                       │   │
│ │ Scenes 10-12 (3 scenes)                                 │   │
│ │                                                          │   │
│ │ [Amber Badge] Act structure follows traditional rhythm  │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ ⚡ Pacing Analysis                                            │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Act 1: ████████░░ Moderate                             │   │
│ │ "Setup moves at a steady pace"                         │   │
│ │                                                          │   │
│ │ Act 2: ██████████ Fast                                  │   │
│ │ "Confrontation feels rushed—consider adding breathing" │   │
│ │                                                          │   │
│ │ Act 3: ██████░░░░ Moderate                             │   │
│ │ "Resolution allows emotional payoff to settle"         │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ ⚠️ Transition Warnings                                       │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Scene 3 → Scene 4                                       │   │
│ │ [Rose Badge] Jarring emotional shift                   │   │
│ │ "The transition from joyful to dread risks whiplash"   │   │
│ │                                                          │   │
│ │ Scene 7 → Scene 8                                       │   │
│ │ [Amber Badge] Continuity break detected                │   │
│ │ "Emotional carryover feels disconnected"               │   │
│ └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Character Arc Panel

```
┌─────────────────────────────────────────────────────────────┐
│ Character Arc Analysis                                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ 👥 Character Inventory (3 characters)                       │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ 1. SARAH       8 scenes  │ First: Scene 1              │   │
│ │ 2. JAKE        6 scenes  │ First: Scene 2              │   │
│ │ 3. EMMA        4 scenes  │ First: Scene 2              │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ 📅 Character Presence Timeline                              │
│ ┌───────────────────────────────────────────────────────┐   │
│ │        S1  S2  S3  S4  S5  S6  S7  S8  S9  S10 S11 S12│   │
│ │ SARAH  ██  ██  ██  ░░  ░░  ░░  ░░  ██  ██  ██  ██  ██│   │
│ │ JAKE   ░░  ██  ██  ██  ██  ██  ██  ░░  ██  ░░  ░░  ░░│   │
│ │ EMMA   ░░  ██  ░░  ██  ░░  ░░  ██  ░░  ░░  ░░  ░░  ██│   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ ⚠️ Arc Gap Warnings                                          │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ [Rose Badge] SARAH's arc gap                           │   │
│ │ "Sarah disappears for 4 scenes (Scene 3 → Scene 8)"   │   │
│ │ "Arc continuity risks weakening without resolution"    │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ 🔗 Character Relationships                                   │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ SARAH & JAKE:  3 scenes together (Scenes 2, 3, 9)     │   │
│ │ SARAH & EMMA:  2 scenes together (Scenes 2, 4)        │   │
│ │ JAKE & EMMA:   3 scenes together (Scenes 2, 4, 7)     │   │
│ └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Tone Consistency Panel

```
┌─────────────────────────────────────────────────────────────┐
│ Tone Consistency Analysis                                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ 🎨 Tone Map               [Badge: Mostly Consistent]        │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Scene 1  │ Scene 2  │ Scene 3  │ Scene 4  │ Scene 5   │   │
│ │ [Calm]   │ [Joyful] │ [Tense]  │ [Dread]  │ [Somber]  │   │
│ │ 🟢       │ 🟡       │ 🔴       │ 🔴       │ 🔵        │   │
│ │                                                          │   │
│ │ Scene 6  │ Scene 7  │ Scene 8  │ Scene 9  │ Scene 10  │   │
│ │ [Somber] │ [Tense]  │ [Hopeful]│ [Calm]   │ [Calm]    │   │
│ │ 🔵       │ 🔴       │ 🟡       │ 🟢       │ 🟢        │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ Legend: 🟢 Calm  🟡 Positive  🔴 Tense  🔵 Melancholic      │
│                                                               │
│ 📊 Consistency Assessment                                    │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ [Amber Badge] Mostly Consistent                        │   │
│ │ "Tone oscillates in Act 2—consider anchoring around    │   │
│ │  one emotional throughline"                             │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                               │
│ ⚠️ Tone Shift Warnings                                       │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ 🔴 Scene 2 (Joyful) → Scene 3 (Tense)                 │   │
│ │    "The shift risks whiplash—plant tension earlier"    │   │
│ │                                                          │   │
│ │ 🟡 Scene 7 (Tense) → Scene 8 (Hopeful)                │   │
│ │    "Consider a bridging beat for smoother transition"  │   │
│ └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration Testing Scenarios

### Test Scenario 1: Complete Workflow

**Steps**:
1. User imports 10-scene script in Writer's Room
2. User clicks "Analyze Script" button
3. System displays Scene Breakdown in first tab
4. User switches to Character Arc tab → sees 3 characters with timeline
5. User switches to Tone tab → sees tone map with 2 warnings
6. User switches to Prompts tab → clicks "Generate Prompts"
7. System generates 10 prompts with style consistency
8. User edits prompt for Scene 3 → saves edit
9. User clicks "Next: Go to Storyboard"
10. Previs loads with auto-populated prompts
11. Scene 3 shows user-edited prompt (not auto-generated)

**Expected Results**:
- All 4 analyses complete without errors
- Co-director voice outputs contain NO scores/percentages
- Edited prompt persists across navigation
- Performance <5 seconds per analysis

---

### Test Scenario 2: Edge Case - Minimal Script

**Steps**:
1. User creates project with 2 scenes only
2. User clicks "Analyze Script"
3. Scene Breakdown shows: "Not enough scenes for act structure"
4. Character Arc shows: 1 character, no relationships
5. Tone Consistency shows: "Too early to assess consistency"
6. Prompt Generation: generates 2 prompts successfully

**Expected Results**:
- Graceful handling of minimal data
- No crashes or 500 errors
- Helpful guidance messages
- Prompts still generate successfully

---

### Test Scenario 3: Performance - Large Script

**Steps**:
1. User imports 50-scene script
2. User clicks "Analyze Script"
3. System displays analysis within 5 seconds
4. Character Arc timeline uses virtualization
5. Tone map scrolls smoothly
6. Prompt generation completes for all 50 scenes

**Expected Results**:
- Performance remains under 5-second budget
- UI remains responsive (no lag)
- Virtualization kicks in for large data sets
- No memory leaks or browser slowdown

---

## Deployment Considerations

### Backend Deployment

**No Infrastructure Changes Required** ✅

- New service: `script_intelligence_service.py`
- New models: `script_intelligence.py`
- New routes: `script_intelligence.py`
- All use existing dependencies (no new packages)

**Deployment Steps**:
1. Add new service file to `app/services/`
2. Add new models file to `app/models/`
3. Add new routes file to `app/routes/`
4. Register routes in `app/routes/__init__.py`
5. Restart backend: `./start_backend.sh`
6. No database migrations needed (no new tables)

---

### Frontend Deployment

**New Components**:
- `ScriptIntelligencePanel.tsx`
- `SceneBreakdownPanel.tsx`
- `CharacterArcPanel.tsx`
- `ToneConsistencyPanel.tsx`
- `PromptGenerationPanel.tsx`

**Integration Point**:
- Modify `WritersRoom.tsx` to include `<ScriptIntelligencePanel />`

**No New Dependencies** ✅
- Uses existing React Query, Tailwind, React hooks

**Deployment Steps**:
1. Add new components to `studio-app/src/components/`
2. Update `WritersRoom.tsx` to import and render panel
3. Build frontend: `npm run build`
4. Deploy static assets

---

## Co-Director Voice Validation Checklist

Before merging any code, validate ALL outputs:

### ❌ Prohibited Patterns (MUST NOT appear anywhere)

```typescript
// Run this regex check on all co-director outputs
const PROHIBITED_PATTERNS = [
  /\d+%/,                    // "45%", "Score: 73%"
  /\d+\/\d+/,                // "5/10", "8/10"
  /score[:\s]+\d+/i,         // "Score: 5", "score 8"
  /rating[:\s]+\d+/i,        // "Rating: 7"
  /\d+\.\d+\/\d+/,           // "7.5/10"
  /great job!?/i,            // "Great job!"
  /well done!?/i,            // "Well done!"
  /excellent!?/i,            // "Excellent!"
  /this is good/i,           // "This is good"
  /objectively/i,            // "objectively better"
  /always/i,                 // "always" (too deterministic)
];

function validateCoDirectorVoice(output: string): boolean {
  for (const pattern of PROHIBITED_PATTERNS) {
    if (pattern.test(output)) {
      console.error(`❌ Co-director voice violation: ${output}`);
      return false;
    }
  }
  return true;
}
```

### ✅ Required Patterns (SHOULD appear)

```typescript
const REQUIRED_CHARACTERISTICS = {
  emotionallyPerceptive: /carries weight|tension|emotional|payoff|momentum/i,
  cinematicallyLiterate: /arc|throughline|beat|structure|visual language/i,
  respectfullyBold: /consider|risks|could|feels/i,
  explainsWhy: /because|so that|which|this/i,
  uncertainWhenThin: /not enough|gathering|uncertain|may/i,
};

function hasCoDirectorCharacteristics(output: string): boolean {
  let matchCount = 0;
  for (const [char, pattern] of Object.entries(REQUIRED_CHARACTERISTICS)) {
    if (pattern.test(output)) {
      matchCount++;
    }
  }
  // At least 2 characteristics should be present
  return matchCount >= 2;
}
```

---

## Testing Checklist Summary

### Unit Tests (Backend)

- [ ] `test_detect_act_structure()` - 3-act detection logic
- [ ] `test_analyze_pacing()` - pacing classification
- [ ] `test_detect_arc_gaps()` - character gap detection
- [ ] `test_detect_tone_shifts()` - tone compatibility matrix
- [ ] `test_enhance_scene_prompt()` - prompt enhancement
- [ ] `test_character_name_normalization()` - "SARAH" = "Sarah"
- [ ] `test_scene_fingerprint()` - cache invalidation
- [ ] `test_co_director_voice_validation()` - NO scores/percentages

### Integration Tests (Backend)

- [ ] `test_breakdown_with_emotional_arc_service()` - service integration
- [ ] `test_character_arc_with_character_consistency()` - service integration
- [ ] `test_tone_with_continuity_intelligence()` - service integration
- [ ] `test_prompts_with_style_consistency()` - service integration
- [ ] `test_analysis_with_2_scenes()` - minimal data
- [ ] `test_analysis_with_50_scenes()` - large data
- [ ] `test_analysis_with_no_characters()` - edge case

### API Tests (Backend)

- [ ] `test_breakdown_endpoint_200()` - success response
- [ ] `test_breakdown_endpoint_400()` - validation error
- [ ] `test_breakdown_endpoint_404()` - project not found
- [ ] `test_characters_endpoint_response_schema()` - DTO validation
- [ ] `test_tone_endpoint_response_schema()` - DTO validation
- [ ] `test_prompts_endpoint_post_body()` - request body validation

### Component Tests (Frontend)

- [ ] `ScriptIntelligencePanel.test.tsx` - tab switching
- [ ] `SceneBreakdownPanel.test.tsx` - data display
- [ ] `CharacterArcPanel.test.tsx` - timeline rendering
- [ ] `ToneConsistencyPanel.test.tsx` - tone map colors
- [ ] `PromptGenerationPanel.test.tsx` - prompt editing
- [ ] Test loading states for all panels
- [ ] Test error states for all panels
- [ ] Test empty states (no data)

### E2E Tests (Manual)

- [ ] Complete workflow (import → analyze → edit → navigate)
- [ ] Edge case: 2-scene script
- [ ] Edge case: 50-scene script
- [ ] Performance: all analyses <5 seconds
- [ ] Co-director voice: NO scores in any output
- [ ] Accessibility: keyboard navigation
- [ ] Accessibility: screen reader compatibility
- [ ] Mobile responsiveness

---

## Implementation Roadmap (Refined)


### Phase 1: Scene Breakdown (Weeks 1-2)

**Backend Tasks**:
- [ ] Create `script_intelligence_service.py` with `analyze_scene_breakdown()`
- [ ] Implement `_detect_act_structure()` algorithm
- [ ] Implement `_analyze_pacing()` algorithm
- [ ] Implement `_analyze_transitions()` algorithm
- [ ] Create `script_intelligence.py` models (ActStructure, PacingInsight, etc.)
- [ ] Create `script_intelligence.py` routes (breakdown endpoint)
- [ ] Write unit tests (10+ tests)
- [ ] Write integration tests (3+ tests)
- [ ] Write API tests (5+ tests)

**Frontend Tasks**:
- [ ] Create `ScriptIntelligencePanel.tsx` (container)
- [ ] Create `SceneBreakdownPanel.tsx` (display component)
- [ ] Add data fetching hook: `useSceneBreakdown()`
- [ ] Integrate into `WritersRoom.tsx`
- [ ] Write component tests (5+ tests)
- [ ] Manual testing with 3 sample scripts

**Acceptance**:
- [ ] Health check passes (40/40)
- [ ] All tests pass (>95%)
- [ ] Co-director voice validated (NO scores)
- [ ] Performance <5 seconds

---

### Phase 2: Character Arc Analysis (Weeks 3-4)

**Backend Tasks**:
- [ ] Add `analyze_character_arcs()` to service
- [ ] Implement `_extract_characters()` algorithm
- [ ] Implement `_detect_arc_gaps()` algorithm
- [ ] Implement `_build_relationship_matrix()` algorithm
- [ ] Add character arc models to `script_intelligence.py`
- [ ] Create character arc endpoint
- [ ] Write unit tests (8+ tests)
- [ ] Write integration tests (2+ tests)
- [ ] Write API tests (4+ tests)

**Frontend Tasks**:
- [ ] Create `CharacterArcPanel.tsx`
- [ ] Create `CharacterArcTimeline.tsx` visualization
- [ ] Add data fetching hook: `useCharacterArcs()`
- [ ] Add to tab navigation in `ScriptIntelligencePanel`
- [ ] Write component tests (6+ tests)
- [ ] Manual testing with character-heavy scripts

**Acceptance**:
- [ ] Character detection works for all name formats
- [ ] Timeline visualization performs well (50+ scenes)
- [ ] Arc gap warnings use co-director voice
- [ ] Health check passes (40/40)

---

### Phase 3: Tone Consistency Check (Weeks 5-6)

**Backend Tasks**:
- [ ] Add `analyze_tone_consistency()` to service
- [ ] Implement `_build_tone_map()` algorithm
- [ ] Implement `_detect_tone_shifts()` algorithm
- [ ] Create tone compatibility matrix
- [ ] Add tone models to `script_intelligence.py`
- [ ] Create tone consistency endpoint
- [ ] Write unit tests (7+ tests)
- [ ] Write integration tests (2+ tests)
- [ ] Write API tests (4+ tests)

**Frontend Tasks**:
- [ ] Create `ToneConsistencyPanel.tsx`
- [ ] Create `ToneMapVisualization.tsx` with color coding
- [ ] Add data fetching hook: `useToneConsistency()`
- [ ] Add to tab navigation
- [ ] Ensure color-blind accessibility
- [ ] Write component tests (5+ tests)
- [ ] Manual testing with varied tone scripts

**Acceptance**:
- [ ] Tone map displays all emotional tones
- [ ] Color coding is accessible (not color-only)
- [ ] Shift warnings use co-director voice
- [ ] Health check passes (40/40)

---

### Phase 4: Script-to-Prompt Pipeline (Weeks 7-8)

**Backend Tasks**:
- [ ] Add `generate_prompts()` to service
- [ ] Implement `_enhance_scene_prompt()` algorithm
- [ ] Create keyword → cinematic language mapping
- [ ] Integrate with style_consistency_service
- [ ] Integrate with character_consistency_service
- [ ] Add prompt models to `script_intelligence.py`
- [ ] Create prompt generation endpoint (POST)
- [ ] Write unit tests (8+ tests)
- [ ] Write integration tests (3+ tests)
- [ ] Write API tests (5+ tests)

**Frontend Tasks**:
- [ ] Create `PromptGenerationPanel.tsx`
- [ ] Create `PromptEditor.tsx` for inline editing
- [ ] Add data mutation hook: `useGeneratePrompts()`
- [ ] Add prompt edit persistence
- [ ] Integrate with Previs (auto-populate prompts)
- [ ] Write component tests (7+ tests)
- [ ] Manual testing with 10+ scene scripts


**Acceptance**:
- [ ] Prompts generate within 5 seconds for 50 scenes
- [ ] Enhanced prompts maintain style consistency
- [ ] User edits persist across navigation
- [ ] Prompts auto-populate in Previs
- [ ] Health check passes (40/40)

---

### Phase 5: Integration & Polish (Week 9)

**Tasks**:
- [ ] Cross-feature testing (all 4 features together)
- [ ] Performance profiling and optimization
- [ ] Accessibility audit (ARIA, keyboard, color-blind)
- [ ] Co-director voice final review (regex validation)
- [ ] Error handling edge case testing
- [ ] Cache invalidation testing
- [ ] Mobile responsiveness testing
- [ ] Browser compatibility testing (Chrome, Firefox, Safari)
- [ ] Fix any bugs discovered in integration
- [ ] Code review and refactoring

**Acceptance**:
- [ ] All 4 features work together without conflicts
- [ ] Performance budget met (<5s per analysis)
- [ ] Accessibility score >90%
- [ ] Zero co-director voice violations
- [ ] Health check passes (40/40)

---

### Phase 6: Documentation & Handoff (Week 10)

**Tasks**:
- [ ] Update `WRITER_ROOM_QUICK_START.md` with script intelligence guide
- [ ] Create `SCRIPT_INTELLIGENCE_USER_GUIDE.md`
- [ ] Add inline help tooltips in Writer's Room UI
- [ ] Record demo video (3-5 minutes) showing all 4 features
- [ ] Update API documentation (Swagger/OpenAPI)
- [ ] Create architecture diagram (service interactions)
- [ ] Write developer onboarding guide
- [ ] Run final health check (40/40 target)
- [ ] Create release notes
- [ ] Deploy to staging for QA

**Deliverables**:
- [ ] User guide (markdown)
- [ ] Developer guide (markdown)
- [ ] Demo video (MP4)
- [ ] API documentation (JSON/YAML)
- [ ] Architecture diagram (PNG/SVG)
- [ ] Release notes (markdown)

---

## Open Questions Resolution

### Question 1: Act Structure Algorithm ✅ RESOLVED

**Decision**: Strict mathematical split (1/4, 1/2, 1/4)

**Rationale**: 
- Simple, predictable, works for v1
- Content-aware detection requires more complex NLP
- Can be enhanced in v2 based on user feedback

---

### Question 2: Tone Inference from Scene Descriptions ✅ RESOLVED

**Decision**: Use keyword matching (Option B)

**Rationale**:
- Keyword matching is fast and deterministic
- No external API costs
- Works well for common emotional keywords
- Graceful degradation: if no match, label as "neutral"
- NLP API (Option C) adds cost and latency

**Keyword Dictionary** (example):
```python
TONE_KEYWORDS = {
    "joyful": ["laugh", "smile", "happy", "celebration", "joy"],
    "tense": ["tension", "tight", "conflict", "pressure", "strain"],
    "melancholic": ["sad", "rain", "alone", "loss", "empty"],
    "dread": ["fear", "dark", "threat", "danger", "horror"],
    "hopeful": ["hope", "light", "future", "dream", "possibility"],
    "calm": ["quiet", "peace", "still", "gentle", "serene"],
}
```

---

### Question 3: Prompt Length for Different Providers ✅ RESOLVED

**Decision**: Provider-specific prompts (Option B)

**Rationale**:
- Different providers have different limits (Runway: 512, ComfyUI: 1024)
- Better quality per provider
- Implementation: Add `max_prompt_length` to provider config

**Implementation**:
```python
def _enhance_scene_prompt(self, scene: Dict, provider: str = "runway") -> EnhancedPrompt:
    # Get provider-specific limit
    max_length = {
        "runway": 512,
        "comfyui": 1024,
        "default": 512,
    }.get(provider, 512)
    
    # Build prompt...
    enhanced_prompt = base_prompt[:max_length]
    
    return EnhancedPrompt(...)
```

---

### Question 4: Character Name Normalization ✅ RESOLVED

**Decision**: Case-insensitive match (Option B)

**Rationale**:
- Catches 95% of duplicates ("SARAH" = "Sarah")
- Simple to implement (`.lower()`)
- Fuzzy matching (Option C) is overkill for v1
- Edge cases ("Sara" vs "Sarah") can be handled manually by user

**Implementation**:
```python
def _normalize_character_name(self, name: str) -> str:
    """Normalize character name for deduplication."""
    return name.strip().lower()
```

---

### Question 5: Analysis Caching Strategy ✅ RESOLVED

**Decision**: No persistent caching (Option A)

**Rationale**:
- All analyses are fast (<5 seconds)
- Scene data changes frequently in Writer's Room
- React Query provides sufficient in-memory caching (5 min stale time)
- Persistent cache adds complexity without significant benefit

**For v2** (if analysis becomes expensive):
- Add SQLite cache table with scene fingerprint
- Invalidate cache when fingerprint changes
- Use cache as fallback if real-time analysis times out

---

## Design Approval Checklist

Before moving to implementation:

- [x] **Service architecture defined** - ScriptIntelligenceService class with 4 public methods
- [x] **Data models complete** - All Pydantic DTOs defined for 4 features
- [x] **API contracts finalized** - 4 endpoints with request/response schemas
- [x] **Algorithms specified** - Pseudocode for 5 core algorithms
- [x] **Frontend components designed** - Component hierarchy and props defined
- [x] **State management strategy** - React Query for data, useState for UI
- [x] **Error handling patterns** - Service/route/frontend error handling defined
- [x] **Performance optimization** - Lazy loading, timeout guards, virtualization
- [x] **Co-director voice validation** - Regex checks and validation functions
- [x] **Testing strategy** - Unit, integration, API, component, E2E tests
- [x] **Deployment plan** - No infrastructure changes, clear deployment steps
- [x] **Open questions resolved** - All 5 design decisions made
- [x] **Integration points mapped** - Existing service dependencies identified
- [x] **UI/UX wireframes** - Text-based wireframes for all 4 panels
- [x] **Implementation roadmap** - 10-week phased approach

---

## Next Steps: Implementation Phase

With the design complete, the team can now proceed to implementation:

### Immediate Actions

1. **Create Feature Branch**:
   ```bash
   git checkout -b feature/script-intelligence-batch-h
   ```

2. **Backend Setup**:
   - Create `app/services/script_intelligence_service.py`
   - Create `app/models/script_intelligence.py`
   - Create `app/routes/script_intelligence.py`

3. **Frontend Setup**:
   - Create `studio-app/src/components/ScriptIntelligencePanel.tsx`
   - Create component subdirectories for each feature

4. **Start with Phase 1**: Scene Breakdown (2 weeks)

---

## Document History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-06-07 | 1.0 | Complete design specification | Kiro AI |

---

## Conclusion

This design specification provides a complete technical blueprint for implementing Batch H: Script Intelligence. All four features are fully designed with:

✅ **Service architecture** - Thin routes → services → storage pattern  
✅ **Data models** - 13 Pydantic models for all features  
✅ **API contracts** - 4 RESTful endpoints  
✅ **Algorithms** - 5 core algorithms with pseudocode  
✅ **Frontend components** - 5 React components with props and state  
✅ **Performance strategy** - <5 second budget, lazy loading, virtualization  
✅ **Co-director voice compliance** - Regex validation, no scores/percentages  
✅ **Testing strategy** - 100+ tests across all layers  
✅ **Deployment plan** - No infrastructure changes required  

**Design Principles Followed**:
- ✅ AGENTS.md architecture rules (thin routes → services → storage)
- ✅ No scores or percentages (co-director voice compliance)
- ✅ Uses existing services only (no new infrastructure)
- ✅ Performance budget (<5 seconds per analysis)
- ✅ Accessibility compliant (ARIA, keyboard, color-blind safe)

**Ready for Implementation**: All design decisions made, open questions resolved, roadmap defined.

**Estimated Timeline**: 10 weeks (4 phases × 2 weeks + 1 week integration + 1 week docs)

**Risk Level**: Low — Uses proven patterns, existing services, no new dependencies

---

## Appendix A: File Structure

```
studio-backend/
  app/
    models/
      script_intelligence.py (NEW - 13 models)
    services/
      script_intelligence_service.py (NEW - main service)
    routes/
      script_intelligence.py (NEW - 4 endpoints)

studio-app/
  src/
    components/
      ScriptIntelligencePanel.tsx (NEW - container)
      SceneBreakdownPanel.tsx (NEW)
      CharacterArcPanel.tsx (NEW)
      ToneConsistencyPanel.tsx (NEW)
      PromptGenerationPanel.tsx (NEW)
    hooks/
      useSceneBreakdown.ts (NEW)
      useCharacterArcs.ts (NEW)
      useToneConsistency.ts (NEW)
      useGeneratePrompts.ts (NEW)
```

---

## Appendix B: Key Constants

```python
# In script_intelligence_service.py

MAX_SCENES_FOR_ANALYSIS = 50
ANALYSIS_TIMEOUT_SECONDS = 5.0
ACT1_RATIO = 0.25  # 1/4 of scenes
ACT3_RATIO = 0.25  # 1/4 of scenes
# ACT2 = remainder

PACING_THRESHOLDS = {
    "fast": 100,      # <100 chars = fast
    "moderate": 250,  # <250 chars = moderate
    "slow": 250,      # ≥250 chars = slow
}

CHARACTER_ARC_GAP_THRESHOLD = 3  # 3+ consecutive absent scenes = gap

TONE_COMPATIBILITY_MATRIX = {
    ("joyful", "hopeful"): "compatible",
    ("joyful", "dread"): "jarring",
    ("tense", "dread"): "compatible",
    # ... more pairs
}

PROMPT_MAX_LENGTH = {
    "runway": 512,
    "comfyui": 1024,
    "default": 512,
}
```

---

**END OF DESIGN SPECIFICATION**
