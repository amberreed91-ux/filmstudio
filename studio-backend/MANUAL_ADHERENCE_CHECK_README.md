# Manual Adherence Check Script

This script allows you to test the adherence scoring system with real images and expected slot text, using Groq's vision model.

## Purpose

The `manual_adherence_check.py` script calls the `AdherenceService.score_render_attempt()` function directly with real image files and expected prompt text. It's designed for manual testing and debugging of the adherence scoring system before full integration with the render pipeline.

## Prerequisites

1. **GROQ_API_KEY environment variable** must be set:
   ```bash
   export GROQ_API_KEY="your_api_key_here"
   ```

2. **Three frame images** extracted from a rendered video at 10%, 50%, and 90% positions

3. **Expected slot text** from the original prompt that generated the video

## Usage

### Basic Example

```bash
python manual_adherence_check.py \
    --frames frame_10pct.jpg frame_50pct.jpg frame_90pct.jpg \
    --character "weathered hand, pale skin, visible veins" \
    --action "reaching slowly toward ancient artifact" \
    --camera "extreme closeup, shallow focus" \
    --lighting "dim candlelight, warm amber glow" \
    --environment "dusty stone pedestal, gothic chamber"
```

### Arguments

**Required:**
- `--frames FRAME1 FRAME2 FRAME3`: Paths to 3 frame images (10%, 50%, 90% positions)
- `--character TEXT`: Expected character state text
- `--action TEXT`: Expected action text
- `--camera TEXT`: Expected camera direction text
- `--lighting TEXT`: Expected lighting text
- `--environment TEXT`: Expected environment persistence text

**Optional:**
- `--shot-id ID`: Shot identifier (default: "manual_test")
- `--attempt N`: Attempt number (default: 1)
- `--json`: Output raw JSON instead of human-readable report

### Output

The script prints a detailed adherence score report including:

- Overall adherence score (0-100)
- Verdict: `pass`, `correctable`, or `manual_review`
- Per-dimension scores with evidence
- Temporal drift analysis across the 3 frames
- List of failed dimensions (score < 50)

#### Example Output

```
================================================================================
ADHERENCE SCORE REPORT
================================================================================
Shot ID: manual_test
Attempt: 1
Frames Scored: [0.1, 0.5, 0.9]
Overall Adherence Score: 82.5/100
Verdict: PASS

DIMENSION SCORES:
--------------------------------------------------------------------------------

CHARACTER STATE: 85.0/100
  Expected:  weathered hand, pale skin, visible veins
  Observed:  Pale hand with visible veining, weathered texture
  Evidence:  Hand matches description with clear vein visibility

ACTION: 90.0/100
  Expected:  reaching slowly toward ancient artifact
  Observed:  Smooth reaching motion toward central object
  Evidence:  Action clearly shows deliberate reaching movement

CAMERA: 75.0/100
  Expected:  extreme closeup, shallow focus
  Observed:  Close framing with moderate depth of field
  Evidence:  Closeup achieved but focus could be shallower

LIGHTING: 88.0/100
  Expected:  dim candlelight, warm amber glow
  Observed:  Warm amber illumination with soft shadows
  Evidence:  Lighting mood matches candlelight aesthetic

ENVIRONMENT PERSISTENCE: 80.0/100
  Expected:  dusty stone pedestal, gothic chamber
  Observed:  Stone surface visible, atmospheric consistency
  Evidence:  Environment elements persist across frames

TEMPORAL DRIFT:
--------------------------------------------------------------------------------
  Start (10%): 85.0/100
  End (90%):   78.0/100
  Delta:       -7.0
================================================================================
```

### Exit Codes

- `0`: Pass verdict (score ≥ 80)
- `1`: Correctable verdict (50 ≤ score < 80)
- `2`: Manual review verdict (score < 50 or attempts exhausted)
- `3`: Error occurred

### JSON Output Mode

Use `--json` flag for machine-readable output:

```bash
python manual_adherence_check.py \
    --frames frame1.jpg frame2.jpg frame3.jpg \
    --character "text" --action "text" --camera "text" \
    --lighting "text" --environment "text" \
    --json
```

This outputs a structured JSON object with all scoring details.

## Vision Model Notes

### Current Provider: Groq

The script currently uses **Groq's `meta-llama/llama-4-scout-17b-16e-instruct`** model (Llama 4 Scout 17B). This is configurable via environment variables:

```bash
export ADHERENCE_VISION_PROVIDER="groq"
export ADHERENCE_VISION_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
```

**Alternative Groq vision models available:**
- `meta-llama/llama-4-scout-17b-16e-instruct` - Llama 4 Scout (recommended, newest)
- `qwen/qwen3.6-27b` - Qwen 3.6 27B (alternative option)

### Production Considerations

**⚠️ IMPORTANT**: Groq's vision model is a placeholder for testing. For production fine-grained consistency judgments (e.g., "is this the same weathered hand as attempt 1"), you should swap in a stronger vision model:

- **GPT-4o** (OpenAI): Superior visual detail recognition
- **Claude 3 Opus** (Anthropic): Strong multimodal reasoning

To switch providers, set:
```bash
export ADHERENCE_VISION_PROVIDER="openai"
export ADHERENCE_VISION_MODEL="gpt-4o"
```

The code contains a comment noting this limitation near the provider configuration.

## How It Works

1. **Frame Loading**: Reads the 3 provided frame images and encodes them as base64
2. **Vision API Call**: Sends frames + expected slot text to Groq's vision model via OpenAI-compatible API
3. **Structured Parsing**: Extracts JSON response with dimension scores and temporal drift
4. **Score Calculation**: Computes weighted adherence score across 5 dimensions
5. **Verdict Assignment**: 
   - `pass` if score ≥ 80
   - `correctable` if 50 ≤ score < 80 and attempts remain
   - `manual_review` otherwise

## Troubleshooting

### "GROQ_API_KEY not found"
Set the environment variable:
```bash
export GROQ_API_KEY="your_key_here"
```

### "Frame file not found"
Ensure all 3 frame paths exist and are readable image files.

### "Vision model returned invalid JSON"
The vision model may have returned malformed output. Check logs for the raw response. This can happen if:
- The prompt is unclear
- The images are corrupted or unreadable
- The model is rate-limited

### Vision model doesn't see details I expect
Consider switching to a stronger vision model like GPT-4o via the environment variable configuration.

## Example Workflow

```bash
# 1. Extract frames from a rendered video (using ffmpeg or similar)
ffmpeg -i render_output.mp4 -vf "select='eq(n\,floor(0.1*N))+eq(n\,floor(0.5*N))+eq(n\,floor(0.9*N))'" \
       -vsync 0 frame_%d.jpg

# 2. Run adherence check with the frames and original prompt slots
python manual_adherence_check.py \
    --frames frame_1.jpg frame_2.jpg frame_3.jpg \
    --character "weathered hand" \
    --action "reaching" \
    --camera "closeup" \
    --lighting "dim" \
    --environment "stone"

# 3. Review the output and iterate on prompt if needed
```

## Integration Path

This standalone script is the foundation for:
1. **Automated retry loop**: If verdict is "correctable", generate diff and retry
2. **Corrective diff generation**: Use failed dimensions to create prompt corrections
3. **Full render pipeline integration**: Automatically score every render attempt

None of these are implemented yet - this script focuses purely on making the vision scoring call real.
