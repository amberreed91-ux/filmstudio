# DIAGNOSTIC REPORT: Script Parsing Issue

## Executive Summary

**CRITICAL ISSUE IDENTIFIED**: The script parser is **NOT creating multiple scenes** from the provided script because the script format does not match the expected screenplay format.

**Root Cause**: The parser expects scene headings to start with `INT.` or `EXT.`, but the test script uses `SCENE 1: INT.` format, which the regex patterns do not recognize.

---

## Test Results

### Test Script Provided
```
SCENE 1: INT. COFFEE SHOP - DAY
A woman sits alone at a corner table, reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.

Emotional tone: quiet, isolated, contemplative.

SCENE 2: EXT. STREET - NIGHT
She steps outside into heavy rain, pulling her coat tight.
The street is deserted except for distant headlights.

Emotional tone: uneasy, exposed, transitional.

SCENE 3: INT. APARTMENT - NIGHT
She pushes open the door to a dark apartment.
A single envelope sits on the floor beneath the mail slot.
She stares at it without picking it up.

Emotional tone: dread, stillness, arriving at something.
```

### Parsing Results

**Number of scenes created**: **0 scenes** (both methods)

❌ **CRITICAL FAILURE**: No scenes were created at all.

---

## Technical Analysis

### 1. Script Parsing Logic Location

**Primary Parser**: `studio-backend/app/services/script_parser.py`

**Two parsing methods exist**:

1. **`extract_structured_scenes(script_text)`** - Used by `generate-scenes` endpoint in `projects.py`
   - Line 145-245 in script_parser.py
   - Returns: `{"scenes": [...]}`
   - Uses `_simple_heading_pattern` regex

2. **`parse(script_text)`** - Used by `ingest-script` endpoint
   - Line 13399-13416 in script_parser.py
   - Calls `_extract_scenes(lines)` method
   - Uses `SCENE_HEADING_PATTERN` regex
   - Returns: `{"scenes": [...], "characters": {...}, "locations": {...}, "source_stats": {...}}`

### 2. Regex Patterns Used

**Pattern 1: SCENE_HEADING_PATTERN** (used by `parse()` method)
```python
SCENE_HEADING_PATTERN = re.compile(
    r'^(INT\.?|EXT\.?|INT\./EXT\.?|I/E\.?)\s+(.+?)\s*-\s*(.+?)$',
    re.MULTILINE | re.IGNORECASE
)
```

**Pattern 2: _simple_heading_pattern** (used by `extract_structured_scenes()`)
```python
_simple_heading_pattern = re.compile(r'^\s*(INT\.|EXT\.)\s+.+$', re.IGNORECASE)
```

**What these patterns expect**:
- Line must START with `INT.` or `EXT.`
- Format: `INT. LOCATION - TIME`
- Example: `INT. COFFEE SHOP - DAY`

**What the test script provides**:
- Line starts with `SCENE 1:` then `INT.`
- Format: `SCENE 1: INT. LOCATION - TIME`
- Example: `SCENE 1: INT. COFFEE SHOP - DAY`

### 3. Pattern Matching Test Results

Testing each line from the script:

```
Line: "SCENE 1: INT. COFFEE SHOP - DAY"
  SCENE_HEADING_PATTERN match: FALSE ❌
  _simple_heading_pattern match: FALSE ❌

Line: "SCENE 2: EXT. STREET - NIGHT"
  SCENE_HEADING_PATTERN match: FALSE ❌
  _simple_heading_pattern match: FALSE ❌

Line: "SCENE 3: INT. APARTMENT - NIGHT"
  SCENE_HEADING_PATTERN match: FALSE ❌
  _simple_heading_pattern match: FALSE ❌
```

**Conclusion**: The `SCENE X:` prefix prevents the regex from matching.

---

## 4. Scene Description Flow

### When scenes ARE created (with correct format):

1. **Script ingestion** → `parse()` method
2. **Scene extraction** → `_extract_scenes()` method (line 13470)
3. **Scene object creation**:
   ```python
   current_scene = Scene(
       scene_id=f"scene-{scene_number:03d}",
       scene_number=scene_number,
       heading=line,
       int_ext=int_ext,
       location=location,
       time_of_day=time_of_day,
       description=""  # ← Initially empty
   )
   ```
4. **Description accumulation**: All lines after heading are added to `scene_text[]`
5. **Description assignment**: When next scene starts or script ends:
   ```python
   current_scene.description = '\n'.join(scene_text).strip()
   ```

### Current behavior with incorrect format:

1. No scene headings are recognized
2. No scenes are created
3. All script text is ignored
4. Result: Empty scenes array

---

## 5. Render Prompt Builder Analysis

**Location**: `studio-backend/app/services/render.py` - `create_job()` method (line 354)

**How prompts are constructed**:

1. **User-provided prompt** is passed to `create_job()`:
   ```python
   def create_job(
       self,
       project_id: str,
       shot_id: str,
       provider: Optional[str] = None,
       prompt: str = "",  # ← This is what gets sent to Runway
       ...
   )
   ```

2. **Prompt is stored in job**:
   ```python
   job = RenderJobModel(
       ...
       input_payload=RenderJobInput(
           shot_id=shot_id,
           prompt=prompt,  # ← Stored as-is
           ...
       )
   )
   ```

3. **Director intent is prepended** (if exists):
   ```python
   _intent_prefix = build_director_intent_prefix(_intent)
   if _intent_prefix:
       job.input_payload.prompt = _intent_prefix + job.input_payload.prompt
   ```

4. **Continuity context is injected** (if available):
   ```python
   _ctx = _cont_svc.build_prompt_context(scene_id=_scene_id, film_id=project_id)
   # Context includes: emotional_register, active_motifs, tonal_direction, continuity_anchors
   ```

**Key Finding**: The prompt sent to Runway is **exactly what the frontend passes** to `create_job()`, plus any director intent prefix.

**If the same scene keeps rendering**, it means:
- The frontend is passing the same prompt for all scenes
- OR the scene descriptions in the database are all the same
- OR the scene descriptions were never created because parsing failed

---

## 6. Frontend Render Flow

**Location**: `studio-app/src/pages/ProductionBoard.tsx` - `handleGenerateScene()` (line ~700)

```typescript
async function handleGenerateScene(sceneId: string) {
  const duration = sceneDurations[sceneId] || 10
  const shotId = `${sceneId}_shot_001`
  
  // Create render job with explicit provider
  const job = await createJob(
    shotId,
    'runway',
    `Generate scene ${sceneId} with cinematic quality. Duration: ${duration}s`,  // ← HARDCODED PROMPT
    [],
  )
  
  await submitJob(job.id)
}
```

**ISSUE IDENTIFIED**: The frontend is using a **hardcoded generic prompt** instead of using the scene's actual description!

The prompt is: `"Generate scene ${sceneId} with cinematic quality. Duration: ${duration}s"`

This explains why the same generic scene keeps rendering - the prompt doesn't include the scene's actual description.

---

## 7. What Should Happen vs. What Is Happening

### Expected Flow:

1. User pastes script with format: `INT. COFFEE SHOP - DAY`
2. Parser recognizes scene heading
3. Parser creates scene object with unique description
4. Scene stored in database with description
5. Frontend retrieves scene description
6. Frontend passes scene description as prompt to render job
7. Runway generates video based on scene description

### Actual Flow (Current):

1. User pastes script with format: `SCENE 1: INT. COFFEE SHOP - DAY`
2. Parser **does not recognize** scene heading ❌
3. Parser creates **zero scenes** ❌
4. No scenes stored in database ❌
5. Frontend has no scene descriptions ❌
6. Frontend passes **generic hardcoded prompt** ❌
7. Runway generates same generic video every time ❌

---

## 8. Root Causes Summary

### Primary Issue: Script Format Mismatch
- **Expected**: `INT. COFFEE SHOP - DAY`
- **Provided**: `SCENE 1: INT. COFFEE SHOP - DAY`
- **Impact**: Parser creates 0 scenes

### Secondary Issue: Hardcoded Prompts
- **Location**: `ProductionBoard.tsx` line ~700
- **Current**: `"Generate scene ${sceneId} with cinematic quality. Duration: ${duration}s"`
- **Should be**: Scene's actual description from database
- **Impact**: Even if scenes were parsed correctly, the same generic prompt would be used

### Tertiary Issue: No Scene Description Retrieval
- Frontend doesn't fetch scene descriptions from backend
- Frontend doesn't pass scene descriptions to render jobs
- Render jobs use generic prompts instead of scene-specific descriptions

---

## 9. Why The Same Scene Keeps Rendering

**Three compounding issues**:

1. **No scenes are created** because script format doesn't match parser expectations
2. **Frontend uses hardcoded prompt** instead of scene description
3. **No mechanism exists** to pass scene description from database to render job

Even if the parser worked correctly, the frontend would still send the same generic prompt for every scene.

---

## 10. Verification Steps Performed

✅ Tested `extract_structured_scenes()` with provided script → 0 scenes created
✅ Tested `parse()` with provided script → 0 scenes created  
✅ Verified regex patterns don't match `SCENE X:` prefix
✅ Traced render job creation flow
✅ Identified hardcoded prompt in frontend
✅ Confirmed no scene description retrieval in frontend

---

## 11. Files Involved

### Backend:
- `studio-backend/app/services/script_parser.py` - Scene parsing logic
- `studio-backend/app/services/projects.py` - Script ingestion
- `studio-backend/app/routes/__init__.py` - `/ingest-script` endpoint
- `studio-backend/app/routes/projects.py` - `/generate-scenes` endpoint
- `studio-backend/app/services/render.py` - Render job creation

### Frontend:
- `studio-app/src/pages/ProductionBoard.tsx` - Scene generation UI
- `studio-app/src/pages/WritersRoom.tsx` - Script input
- `studio-app/src/lib/studioApi.ts` - API calls

---

## 12. Recommended Fixes (Not Implemented)

### Fix 1: Update Parser to Handle "SCENE X:" Prefix
Add alternative regex pattern or strip prefix before matching.

### Fix 2: Use Scene Descriptions in Render Prompts
Modify `handleGenerateScene()` to:
1. Fetch scene description from backend
2. Pass scene description as prompt instead of hardcoded text

### Fix 3: Add Scene Description Field to Scene CRUD
Ensure scene descriptions are stored and retrievable via API.

### Fix 4: Update Frontend to Display Scene Descriptions
Show scene descriptions in ProductionBoard so users can verify correct content.

---

## Conclusion

The script parser is **fundamentally incompatible** with the provided script format. The parser expects standard screenplay format (`INT. LOCATION - TIME`) but the test script uses a numbered format (`SCENE 1: INT. LOCATION - TIME`).

Additionally, even if parsing worked, the frontend uses hardcoded generic prompts instead of scene-specific descriptions, which would cause all scenes to render identically.

**Both issues must be fixed** to enable multi-scene rendering with unique content per scene.
