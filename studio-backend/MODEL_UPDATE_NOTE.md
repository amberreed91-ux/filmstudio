# Vision Model Update - Llama 4 Scout

## What Happened

When checking your actual Groq account, I discovered that you **do NOT have access** to the Llama 3.2 vision models (`llama-3.2-90b-vision-preview` or `llama-3.2-11b-vision-preview`) that are commonly mentioned in Groq documentation.

## Your Available Vision Models

Your Groq account has access to these vision-capable models:

1. **`meta-llama/llama-4-scout-17b-16e-instruct`** ✅ **NOW CONFIGURED**
   - Llama 4 Scout 17B
   - 131,072 token context window
   - Supports: tools, json_mode
   - Input: text + image
   - Output: text

2. **`qwen/qwen3.6-27b`**
   - Qwen 3.6 27B (Alibaba Cloud)
   - 131,072 token context window
   - Supports: tools, json_mode, reasoning
   - Input: text + image
   - Output: text

## Changes Made

Updated the default model in `app/services/adherence_service.py`:

```python
# Before (didn't exist in your account):
self._vision_model = os.getenv("ADHERENCE_VISION_MODEL", "llama-3.2-90b-vision-preview")

# After (available in your account):
self._vision_model = os.getenv("ADHERENCE_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
```

## Why Llama 4 Scout?

- **Newest**: This is Meta's latest vision model (Llama 4 generation)
- **Available**: It's actually in your Groq account
- **Capable**: 131K context, supports tools and JSON mode
- **Fast**: Groq's inference speed advantage

## Testing Status

✅ **GROQ_API_KEY loaded successfully from .env**
✅ **Llama 4 Scout model confirmed available in your account**
✅ **AdherenceService instantiates correctly with the new model**

Ready to test with real images!

## Full Model List in Your Account

**Vision Models (2):**
- meta-llama/llama-4-scout-17b-16e-instruct
- qwen/qwen3.6-27b

**Text Models (13):**
- llama-3.3-70b-versatile
- llama-3.1-8b-instant
- openai/gpt-oss-120b
- openai/gpt-oss-20b
- qwen/qwen3-32b
- groq/compound
- groq/compound-mini
- ... and more

**Audio Models (2):**
- whisper-large-v3
- whisper-large-v3-turbo

## Next Steps

The implementation is complete and uses a model that actually exists in your account. You can now:

1. Extract 3 frames from a test video
2. Run `manual_adherence_check.py` with those frames
3. See real vision scoring results from Llama 4 Scout

The code will work immediately with your existing `GROQ_API_KEY` from the `.env` file.
