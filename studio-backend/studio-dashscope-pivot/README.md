# DashScope pivot — Groq/Runway/Gemini/Chatterbox → Qwen/happyhorse/CosyVoice

One API key (`DASHSCOPE_API_KEY`) now covers LLM, vision scoring, video
render, and dialogue TTS. ACE Step stays as-is for score/ambient/SFX — no
DashScope equivalent for that piece.

## Files

| File | Replaces | Wire into |
|---|---|---|
| `services/shared/dashscope_client.py` | — (shared config) | imported by all four |
| `services/llm/qwen_llm_service.py` | Groq Llama 3.3 70B | Co-Director's five specialist agents, Director's Memory Engine, standing corrections parsing |
| `services/vision/qwen_vision_service.py` | Gemini 2.5 Flash | Loop 1 vision-based adherence scoring |
| `services/render/happyhorse_video_provider.py` | Runway Gen-4.5 | `main.py` render pipeline, behind `ProviderPicker` |
| `services/audio/cosyvoice_tts_service.py` | Chatterbox/Kokoro | per-shot audio orchestrator, dialogue path only |

## Setup

```bash
pip install openai httpx dashscope
```

```bash
# .env
DASHSCOPE_API_KEY=sk-xxx
DASHSCOPE_REGION=intl          # or "beijing" — key is region-locked, pick one
DASHSCOPE_WORKSPACE_ID=        # only needed if a specific endpoint requires it
```

## Suggested rollout order (lowest to highest risk)

1. **LLM (Qwen Plus 3.7)** — near drop-in via the OpenAI-compatible endpoint.
   Re-validate Co-Director's multi-constraint prompts (Taste Memory,
   standing corrections) since instruction-following differs from Llama
   3.3 70B on edge cases.
2. **Vision (Qwen-VL)** — swap Loop 1's scoring call, then run it against a
   batch of frames you already have Gemini scores for, to sanity-check the
   two models agree often enough that Loop 3's retry trigger threshold
   doesn't need retuning.
3. **Dialogue TTS (CosyVoice/Qwen-TTS)** — test voice cloning against your
   two active projects' cast before touching the pipeline; this is also
   where you decide whether it replaces the planned Fish Audio S2 Pro
   integration or runs alongside it.
4. **Video (happyhorse-1.1-t2v)** — highest risk, most value. Before
   wiring into `main.py`:
   - Confirm the exact model string is enabled on your account (Model
     Gallery access may be gated, same pattern as Fun-Music's preview).
   - Confirm `-t2v` returns video only, not joint audio — if you need
     audio-synced HappyHorse, that's likely a different model string.
   - Re-run a subset of Loop 3's validation suite (slot-reordering +
     fresh-seed retry) against real happyhorse renders. Your two existing
     findings docs were derived from Runway-specific behavior:
     - `SEED_NON_DETERMINISM_FINDING.md`
     - `POSITIONAL_WEIGHTING_FINDING.md`
     Both need re-validation, not an assumption of transfer.

## Known gaps

- **Score/ambient/SFX**: no swap. Fun-Music exists but is limited-preview,
  Beijing-only, and vocal-song-focused — not a score/ambient substitute.
  ACE Step stays wired in.
- **Rate limits**: happyhorse-1.1-t2v is 300 RPM; most DashScope
  chat/vision models are 600 RPM / 1M TPM. If you parallelize a full
  scene's shots at once, throttle submission rather than firing all shots
  concurrently.
- **Regions**: API keys are region-locked (`intl` vs `beijing`). Some
  newer endpoints (certain TTS voice-clone paths) are workspace-scoped
  domains rather than the shared host — `dashscope_client.py` handles
  both, but double-check which each model needs in the current docs before
  assuming the shared host works for everything.
