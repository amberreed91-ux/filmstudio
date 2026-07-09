# Adaptive Behavior System - Technical Documentation

## Overview

The adaptive behavior system enables the autonomous studio to improve output quality over time using stored project memory and prior results. It implements a feedback loop where agents learn from approved and rejected outputs.

## Files Created/Modified

### New Files
- `app/services/adaptation.py` - Core adaptation engine (24KB)
- `ADAPTIVE_BEHAVIOR_SYSTEM.md` - This documentation

### Modified Files
- `app/services/agent_executor.py` - Added adaptive behavior to agents
  - `_storyboard_artist_logic()` - Adapts framing based on prior scenes
  - `_prompt_engineer_logic()` - Improves prompts based on feedback
  - `_quality_reviewer_logic()` - Adjusts evaluation criteria

- `app/routes/crew.py` - Added adaptation API endpoints

## Architecture

### AdaptationEngine

Central coordinator managing:

1. **Pattern Feedback Tracking**
   - Records approved/rejected patterns per project
   - Calculates success rates for each pattern
   - Maintains pattern history

2. **Pattern Learning**
   - Identifies successful patterns from feedback
   - Ranks patterns by confidence score
   - Recommends patterns for new scenes

3. **Consistency Guard**
   - Prevents contradictions across scenes
   - Checks new values against established patterns
   - Flags potential style drift

4. **Control Mechanisms**
   - Style boundaries limit adaptation range
   - User overrides always take priority
   - Logs all adaptive decisions

### Pattern Types

| Pattern Type | Description | Examples |
|--------------|-------------|----------|
| camera_angle | Shot framing | wide, medium, close_up, extreme_close |
| lighting | Lighting setup | low_key, high_key, chiaroscuro |
| prompt_style | AI prompt style | film_noir, bright, dramatic |
| render_settings | Technical settings | steps, guidance_scale |
| framing | Composition style | centered, rule_of_thirds, low_angle |

## Agent Integration

### Shot Planner (`_storyboard_artist_logic`)

**Before**: Generated generic shot plans without context

**After**: 
```
1. Reads established camera angles from feedback
2. Checks consistency with prior scenes
3. Selects shots based on success rates
4. Logs adaptive decisions with reasoning
```

**Adaptive Elements**:
- Suggested camera angles from feedback
- Framing adjustments based on prior success
- Consistency warnings for contradictions

### Prompt Engineer (`_prompt_engineer_logic`)

**Before**: Generated prompts without considering feedback

**After**:
```
1. Gets reinforced elements from successful renders
2. Gets avoid elements from rejected renders
3. Applies settings adjustments based on feedback
4. Logs prompt generation decisions
```

**Adaptive Elements**:
- Reinforced prompt elements (high success rate)
- Avoid elements (rejected patterns)
- Settings adjustments from feedback

### Quality Reviewer (`_quality_reviewer_logic`)

**Before**: Applied fixed evaluation thresholds

**After**:
```
1. Gets project-specific evaluation criteria
2. Adjusts thresholds based on genre/style
3. Applies consistency bonuses/penalties
4. Records feedback for learning
```

**Adaptive Elements**:
- Genre-specific evaluation weights
- Consistency checks with prior scenes
- Adaptive approval thresholds

## API Endpoints

### Feedback Recording

```
POST /crew/projects/{project_id}/adaptation/feedback
{
  "pattern_type": "camera_angle",
  "pattern_value": "wide",
  "approved": true,
  "scene_id": "scene-001",
  "render_job_id": "job-xxx"
}
```

### Pattern Suggestions

```
GET /crew/projects/{project_id}/adaptation/suggestions?pattern_type=camera_angle
{
  "suggestions": [
    {"value": "wide", "confidence": 0.95},
    {"value": "medium", "confidence": 0.85}
  ]
}
```

### User Override

```
POST /crew/projects/{project_id}/adaptation/user-override
{
  "key": "camera_angle",
  "value": "drone_shot"
}
```

### Style Boundaries

```
POST /crew/projects/{project_id}/adaptation/style-boundaries
{
  "boundaries": {
    "camera_angle": ["wide", "medium", "close"],
    "lighting": ["low_key", "chiaroscuro"]
  }
}
```

### Consistency Check

```
POST /crew/projects/{project_id}/adaptation/consistency-check
{
  "pattern_type": "camera_angle",
  "proposed_value": "extreme_wide"
}
```

### Evolution Metrics

```
GET /crew/projects/{project_id}/adaptation/evolution
{
  "metrics": {
    "total_feedback_records": 45,
    "approved_patterns": 38,
    "rejected_patterns": 7,
    "success_rate": 0.84,
    "established_patterns": 8,
    "evolution_phase": "refining"
  }
}
```

## Feedback Loop

```
Scene N Render Complete
        │
        ▼
Quality Reviewer Evaluates
        │
        ▼
Feedback Recorded (approved/rejected)
        │
        ▼
Pattern Success Rate Updated
        │
        ▼
Established Patterns Updated
        │
        ▼
Scene N+1 Gets Adaptive Suggestions
        │
        ▼
Improved Output
```

## Evolution Phases

| Phase | Feedback Count | Description |
|-------|---------------|-------------|
| learning | < 5 | Initial patterns forming |
| adapting | 5-20 | Patterns being validated |
| refining | 20-50 | Fine-tuning based on feedback |
| optimized | > 50 | Stable, high-confidence patterns |

## Example: Output Improvement

### Scene 1 (Before Feedback)
```
Shot Plan: Generic wide-medium-close
Prompt: "Scene description, cinematic"
Result: Rejected - "Too generic, lacks noir feel"
```

### Scene 2 (After Feedback)
```
Feedback: low_key approved, close_up approved
Shot Plan: Wide (established) + Medium with shadows
Prompt: "cinematic, film_noir, low_key lighting"
Result: Approved - "Good noir atmosphere"
```

### Scene 3 (Patterns Reinforced)
```
Feedback: film_noir style approved
Shot Plan: Adapted to noir aesthetic
Prompt: "film_grain, noir_lighting, high_contrast"
Result: Approved - "Perfect noir style"
```

### Scene 4+ (Optimized)
```
Shot Plan: Fully optimized for genre
Prompt: Refined based on accumulated feedback
Result: Consistent high-quality outputs
```

## Logging Format

Every adaptive decision is logged with:

```
ADAPTIVE_DECISION | 
  project=xxx | 
  agent=shot_planner | 
  type=camera_angle | 
  decision=wide | 
  reason=Based on 3 successful uses | 
  feedback_based=True | 
  override=False | 
  contradicted=False
```

## Control Guarantees

1. **User Override Priority**: User commands always take precedence over adaptive suggestions

2. **Style Boundaries**: When set, adaptation stays within defined limits

3. **Consistency Warnings**: Potential contradictions are flagged, not automatically blocked

4. **Logging**: All decisions are traceable for audit

## Testing

Run the adaptive behavior test:
```bash
cd studio-backend
python3 -m uvicorn main:app --port 8010
```

Then execute the test:
```bash
python3 -c "
import requests
BASE = 'http://localhost:8010/api/f51/studio'

# Create project
resp = requests.post(f'{BASE}/ingest-script', data={
    'title': 'Test',
    'creative_intent': 'Neo-noir thriller',
    'render_provider': 'simulated',
    'script_text': 'INT. ROOM - DAY\nTest scene.'
})
project_id = resp.json().get('project_id')

# Record feedback
requests.post(f'{BASE}/crew/projects/{project_id}/adaptation/feedback', json={
    'pattern_type': 'camera_angle',
    'pattern_value': 'wide',
    'approved': True
})

# Get suggestions
suggestions = requests.get(f'{BASE}/crew/projects/{project_id}/adaptation/suggestions',
    params={'pattern_type': 'camera_angle'})
print(suggestions.json())
"
```
