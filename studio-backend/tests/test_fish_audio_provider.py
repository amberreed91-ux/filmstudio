from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_provider_module():
    path = _BACKEND_ROOT / "fish_audio_provider.py"
    spec = importlib.util.spec_from_file_location("fish_audio_provider", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.content = b"audio"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs
        self.calls = []

    async def post(self, path: str, **kwargs):
        self.calls.append((path, kwargs))
        if path == "/model":
            return FakeResponse({"_id": "fish-model-123"})
        return FakeResponse({})

    async def aclose(self):
        return None


async def test_fish_audio_clone_voice_uses_current_model_endpoint(tmp_path, monkeypatch):
    module = _load_provider_module()
    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"RIFFfake")

    provider = module.FishAudioProvider(api_key="fish-key")
    voice_id = await provider.clone_voice(str(reference), "Dre comparison")

    assert voice_id == "fish-model-123"
    assert provider._client.init_kwargs["base_url"] == "https://api.fish.audio"
    path, kwargs = provider._client.calls[0]
    assert path == "/model"
    assert kwargs["data"]["type"] == "tts"
    assert kwargs["data"]["title"] == "Dre comparison"
    assert kwargs["data"]["train_mode"] == "fast"
    assert kwargs["data"]["visibility"] == "private"
    assert "voices" in kwargs["files"]


async def test_fish_audio_synthesize_uses_v1_tts_endpoint(monkeypatch):
    module = _load_provider_module()
    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)

    provider = module.FishAudioProvider(api_key="fish-key")
    result = await provider.synthesize("Keep your voice down.", "fish-model-123", emotion_tag="whispering")

    assert result.audio_bytes == b"audio"
    path, kwargs = provider._client.calls[0]
    assert path == "/v1/tts"
    assert kwargs["json"]["reference_id"] == "fish-model-123"
    assert kwargs["json"]["text"] == "[whispering] Keep your voice down."
