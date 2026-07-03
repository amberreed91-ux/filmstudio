# Piper TTS Voice Models

This directory contains Piper TTS voice model files used by the audio pipeline for dialogue generation.

## Required Model

The project uses the `en_US-lessac-medium` voice model. You need two files:

- `en_US-lessac-medium.onnx` — the voice model
- `en_US-lessac-medium.onnx.json` — the model config

## Download

Download from the Piper voices repository on HuggingFace:

```bash
# From this directory (studio-backend/models/piper/):
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

## Why Not Committed

These model files are ~63MB binary files excluded from version control via `.gitignore`. Download them separately after cloning the repository.

## Source

- Project: https://github.com/rhasspy/piper
- Voices: https://huggingface.co/rhasspy/piper-voices