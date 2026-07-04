# Adherence Vision Model Implementation - Groq Switch

## Summary

Switched the vision provider default from OpenAI/GPT-4o to Groq's `llama-3.2-90b-vision-preview` model and implemented the real vision API call in `AdherenceService._call_vision_model()`. Also created a standalone manual testing script.

## Changes Made

### 1. Updated `app/services/adherence_service.py`

#### Added Imports
- `asyncio` - for running sync Groq client in thread pool
- `base64` - for encoding frame images
- `from groq import Groq` - Groq SDK client

#### Updated Provider Configuration
Changed default vision provider from OpenAI to Groq:

```python
# Before:
self._vision_provider = os.getenv("ADHERENCE_VISION_PROVIDER", "openai")
self._vision_model = os.getenv("ADHERENCE_VISION_MODEL", "gpt-4o")

# After:
# NOTE: Using Groq's llama-3.2-90b-vision-preview as placeholder.
# For production fine-grained consistency judgments (e.g., "is this the same
# weathered hand as attempt 1"), swap in a stronger vision model like GPT-4o
# or Claude via ADHERENCE_VISION_PROVIDER once available.
self._vision_provider = os.getenv("ADHERENCE_VISION_PROVIDER", "groq")
self._vision_model = os.getenv("ADHERENCE_VISION_MODEL", "llama-3.2-90b-vision-preview")
```

**Important Note**: The code includes a comment explicitly noting that Groq is a placeholder and stronger models (GPT-4o, Claude) should be swapped in for production via environment variables.

#### Implemented Real Vision API Call

Replaced the mock implementation in `_call_vision_model()` with a real Groq API call:

**Key Implementation Details:**

1. **Frame Encoding**: Reads frame files and encodes as base64
   ```python
   with open(frame_path, "rb") as f:
       frame_bytes = f.read()
       b64_frame = base64.b64encode(frame_bytes).decode("utf-8")
   ```

2. **Message Construction**: Uses OpenAI-compatible format with image_url content type
   ```python
   content_parts.append({
       "type": "image_url",
       "image_url": {
           "url": f"data:image/jpeg;base64,{b64_frame}"
       }
   })
   ```

3. **API Call**: Uses Groq SDK in thread pool (since SDK is sync)
   ```python
   def _sync_vision_call():
       client = Groq(api_key=os.getenv("GROQ_API_KEY"))
       response = client.chat.completions.create(
           model=self._vision_model,
           messages=messages,
           max_tokens=2048,
           temperature=0.3,
       )
       return response.choices[0].message.content
   
   response_text = await asyncio.to_thread(_sync_vision_call)
   ```

4. **JSON Parsing**: Extracts JSON from response (handles markdown code blocks)
   ```python
   if "```json" in response_text:
       json_start = response_text.find("```json") + 7
       json_end = response_text.find("```", json_start)
       response_text = response_text[json_start:json_end].strip()
   
   result = json.loads(response_text)
   ```

5. **Schema Validation**: Validates required keys and dimensions
   ```python
   required_keys = ["dimensions", "temporal_drift"]
   required_dimensions = ["character_state", "action", "camera", 
                          "lighting", "environment_persistence"]
   ```

6. **Error Handling**: Catches JSON parse errors and API failures with detailed logging

### 2. Created `manual_adherence_check.py`

A standalone script for manual testing of the adherence scoring system.

**Features:**

- **CLI Interface**: Takes frame paths and expected slot text as arguments
- **Real API Calls**: Directly invokes `AdherenceService.score_render_attempt()`
- **Human-Readable Output**: Formats `AdherenceScore` as a detailed report
- **JSON Mode**: Optional `--json` flag for machine-readable output
- **Exit Codes**: Different codes for pass/correctable/manual_review/error
- **Validation**: Checks that frames exist, are readable, and GROQ_API_KEY is set

**Usage Example:**

```bash
python manual_adherence_check.py \
    --frames frame_10pct.jpg frame_50pct.jpg frame_90pct.jpg \
    --character "weathered hand, pale skin" \
    --action "reaching toward artifact" \
    --camera "extreme closeup" \
    --lighting "dim candlelight" \
    --environment "stone pedestal"
```

**Output Example:**

```
================================================================================
ADHERENCE SCORE REPORT
================================================================================
Shot ID: manual_test
Attempt: 1
Overall Adherence Score: 82.5/100
Verdict: PASS

DIMENSION SCORES:
--------------------------------------------------------------------------------
CHARACTER STATE: 85.0/100
  Expected:  weathered hand, pale skin
  Observed:  Pale hand with visible veining
  Evidence:  Hand matches description with clear vein visibility
...
```

### 3. Updated `requirements.txt`

Added Groq SDK dependency:
```
groq>=0.4.0
```

### 4. Created Documentation

- `MANUAL_ADHERENCE_CHECK_README.md`: Comprehensive guide for using the manual test script
- `ADHERENCE_GROQ_IMPLEMENTATION.md`: This file - implementation summary

## What Was NOT Implemented

Per the requirements, the following were explicitly NOT built:

1. **Retry Loop**: No automatic retry with corrected prompts on "correctable" verdict
2. **Database Persistence**: No storage of adherence scores
3. **Render Pipeline Integration**: No automatic scoring after render completion
4. **Corrective Diff Integration**: `_call_groq_corrector()` still uses mock implementation
5. **Keyframe Extraction**: No integration with `KeyframeExtractionService`

These are intentionally deferred - this implementation focuses solely on making the vision scoring call real.

## Testing the Implementation

### Prerequisites

1. Set Groq API key:
   ```bash
   export GROQ_API_KEY="your_groq_api_key"
   ```

2. Extract 3 frames from a test video at 10%, 50%, 90% positions

### Run Manual Test

```bash
cd studio-backend
python manual_adherence_check.py \
    --frames /path/to/frame1.jpg /path/to/frame2.jpg /path/to/frame3.jpg \
    --character "your expected character text" \
    --action "your expected action text" \
    --camera "your expected camera text" \
    --lighting "your expected lighting text" \
    --environment "your expected environment text"
```

The script will:
1. Load and encode the 3 frames
2. Call Groq's vision API with the frames and expected text
3. Parse the JSON response
4. Calculate dimension scores and overall adherence
5. Print a detailed report

### Expected Behavior

- **Success**: Prints adherence report with scores, evidence, and verdict
- **Failure**: Logs detailed error with exception info

### Troubleshooting

**"GROQ_API_KEY not found"**
- Set the environment variable before running

**"Frame file not found"**
- Verify all 3 frame paths are correct and files exist

**"Vision model returned invalid JSON"**
- Check logs for raw response
- Model may need clearer prompt or better-quality images
- Consider switching to a stronger model via environment variables

## Configuration

The vision model can be configured via environment variables:

```bash
# Use Groq with Llama 4 Scout (current default - available in your account)
export ADHERENCE_VISION_PROVIDER="groq"
export ADHERENCE_VISION_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"

# Or use Qwen vision model (alternative Groq option)
export ADHERENCE_VISION_MODEL="qwen/qwen3.6-27b"

# Or switch to OpenAI (when API key available)
export ADHERENCE_VISION_PROVIDER="openai"
export ADHERENCE_VISION_MODEL="gpt-4o"
export OPENAI_API_KEY="your_openai_key"
```

Note: Switching to OpenAI would require implementing OpenAI client code in `_call_vision_model()`, which is not done yet. The current implementation only supports Groq.

## Vision Model Comparison

| Model | Provider | Strengths | Weaknesses |
|-------|----------|-----------|------------|
| meta-llama/llama-4-scout-17b-16e-instruct | Groq | Fast inference, Available now, Newest Meta vision model | Less detailed than GPT-4o |
| qwen/qwen3.6-27b | Groq | Fast, supports reasoning | Alternative option |
| gpt-4o | OpenAI | Superior detail recognition | Requires separate API key |
| Claude 3 Opus | Anthropic | Strong multimodal reasoning | Requires separate API key |

**Recommendation**: Use Llama 4 Scout for initial testing (it's available now), then evaluate GPT-4o or Claude for production once API keys are available and quality requirements are clearer.

## Code Quality Notes

- **No mock data**: The vision API call is completely real
- **Error handling**: Proper exception handling with detailed logging
- **Schema validation**: Validates response structure before using
- **Async-compatible**: Uses `asyncio.to_thread()` for sync Groq client
- **Follows project conventions**: Matches existing `llm_client.py` pattern
- **Architecture compliance**: Service layer only, no route/storage logic
- **Documentation**: Inline comments explain placeholders and trade-offs

## Next Steps (NOT Implemented Yet)

When ready to build the full adherence scoring pipeline:

1. **Integrate KeyframeExtractionService**: Extract frames automatically after render
2. **Implement Groq Corrector**: Replace mock in `_call_groq_corrector()`
3. **Build Retry Loop**: Automatically retry with corrected prompts on "correctable"
4. **Persist Scores**: Store `AdherenceScore` in database
5. **Wire to Render Pipeline**: Call `score_render_attempt()` after each render completes
6. **Evaluate Model Quality**: Compare Groq vs GPT-4o on real renders
7. **Tune Thresholds**: Adjust VERDICT_PASS_THRESHOLD based on model performance

The foundation is now in place for all of these.
