from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.routes import previs_image as route_module
from app.services.previs_image_generation_service import PrevisImageGenerationService
from app.services.stability import ProviderError, ValidationError


def _png_bytes(width: int = 32, height: int = 32) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (20, 20, 24)).save(buffer, format="PNG")
    return buffer.getvalue()


class _Adapter:
    provider = "dashscope"
    model = "qwen-image-max"

    def __init__(self, payload: bytes | None = None, error: Exception | None = None):
        self.payload = payload if payload is not None else _png_bytes()
        self.error = error
        self.calls: list[tuple[str, int, str]] = []

    def generate_still(self, prompt: str, seed: int, aspect_ratio: str) -> bytes:
        self.calls.append((prompt, seed, aspect_ratio))
        if self.error:
            raise self.error
        return self.payload


class _Projects:
    def __init__(self, exists: bool = True):
        self.exists = exists

    def get_project(self, project_id: str):
        return {"project_id": project_id} if self.exists else None


def _service(tmp_path: Path, adapter=None, exists: bool = True) -> PrevisImageGenerationService:
    return PrevisImageGenerationService(adapter=adapter or _Adapter(), outputs_dir=tmp_path, projects=_Projects(exists))


# ── Service ─────────────────────────────────────────────────────────────────


def test_generate_writes_project_scoped_still_and_returns_output_url(tmp_path):
    adapter = _Adapter()
    result = _service(tmp_path, adapter).generate(
        project_id="film-a",
        mode="character",
        prompt="Maya at the loft window before dawn",
        aspect_ratio="9:16",
        style_preset="cinematic_35mm",
        lighting_preset="soft_window",
        seed=42,
    )

    assert result.image_url.startswith("/outputs/reference_generation/film-a/")
    assert (tmp_path / result.image_url.removeprefix("/outputs/")).is_file()
    assert result.seed == 42
    assert result.aspect_ratio == "9:16"
    assert result.model == "qwen-image-max"
    prompt, seed, ratio = adapter.calls[0]
    assert seed == 42 and ratio == "9:16"
    # Creator words come first and unaltered; presets only narrow treatment after.
    assert prompt.splitlines()[0] == "Maya at the loft window before dawn"
    assert "fine grain" in prompt


def test_generate_composes_mode_guard_and_preset_fragments(tmp_path):
    adapter = _Adapter()
    result = _service(tmp_path, adapter).generate(
        project_id="film-a",
        mode="setting",
        prompt="A rain-slick loading dock",
        style_preset="production_plate",
        lighting_preset="practical_night",
        seed=7,
    )
    prompt = result.prompt
    assert "A rain-slick loading dock" in prompt
    assert "no people" in prompt
    assert "production design plate" in prompt
    assert "practicals" in prompt


def test_generate_assigns_a_seed_when_none_is_supplied(tmp_path):
    result = _service(tmp_path).generate(project_id="film-a", mode="character", prompt="A weathered dockworker")
    assert 0 <= result.seed <= 2_147_483_647


def test_generate_rejects_blank_prompt_without_calling_provider(tmp_path):
    adapter = _Adapter()
    with pytest.raises(ValidationError):
        _service(tmp_path, adapter).generate(project_id="film-a", mode="character", prompt="   ")
    assert adapter.calls == []


def test_generate_rejects_unknown_preset_without_calling_provider(tmp_path):
    adapter = _Adapter()
    with pytest.raises(ValidationError):
        _service(tmp_path, adapter).generate(
            project_id="film-a", mode="character", prompt="Maya", style_preset="not-a-preset",
        )
    assert adapter.calls == []


def test_generate_refuses_unknown_project_before_provider_call(tmp_path):
    adapter = _Adapter()
    with pytest.raises(ValidationError) as excinfo:
        _service(tmp_path, adapter, exists=False).generate(project_id="film-a", mode="setting", prompt="A motel room")
    assert excinfo.value.metadata.get("missing_project") is True
    assert adapter.calls == []


def test_generate_rejects_path_traversal_project_id(tmp_path):
    with pytest.raises(ValidationError):
        _service(tmp_path).generate(project_id="../etc", mode="setting", prompt="A motel room")


def test_provider_failure_saves_nothing(tmp_path):
    service = _service(tmp_path, _Adapter(error=ProviderError("provider down", stage="reference_generation_provider")))
    with pytest.raises(ProviderError):
        service.generate(project_id="film-a", mode="character", prompt="Maya")
    assert not (tmp_path / "reference_generation").exists()


def test_unreadable_provider_payload_is_a_provider_error(tmp_path):
    service = _service(tmp_path, _Adapter(payload=b"not an image"))
    with pytest.raises(ProviderError):
        service.generate(project_id="film-a", mode="character", prompt="Maya")
    assert not (tmp_path / "reference_generation").exists()


def test_presets_catalog_matches_validation_vocabulary():
    catalogue = PrevisImageGenerationService.presets()
    style_ids = {preset["id"] for preset in catalogue["style_presets"]}
    lighting_ids = {preset["id"] for preset in catalogue["lighting_presets"]}
    assert {"none", "cinematic_35mm"} <= style_ids
    assert {"none", "soft_window"} <= lighting_ids
    assert catalogue["aspect_ratios"] == ["16:9", "1:1", "9:16"]


# ── Route ───────────────────────────────────────────────────────────────────


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(route_module.router)
    return app


def _override(api, service) -> None:
    api.dependency_overrides[route_module.get_previs_image_generation_service] = lambda: service


def test_generate_route_returns_still_contract(api, tmp_path):
    _override(api, _service(tmp_path))
    response = TestClient(api).post(
        "/api/f51/studio/generate-previs-image",
        json={
            "project_id": "film-a",
            "mode": "character",
            "prompt": "Maya at the loft window",
            "aspect_ratio": "1:1",
            "style_preset": "docu_realism",
            "lighting_preset": "golden_hour",
            "seed": 11,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "character"
    assert body["aspect_ratio"] == "1:1"
    assert body["seed"] == 11
    assert body["image_url"].startswith("/outputs/reference_generation/film-a/")
    assert body["provider"] == "dashscope"


def test_generate_route_rejects_provider_overrides(api):
    response = TestClient(api).post(
        "/api/f51/studio/generate-previs-image",
        json={"project_id": "film-a", "mode": "character", "prompt": "Maya", "provider": "runway"},
    )
    assert response.status_code == 422


def test_generate_route_rejects_unsupported_aspect_ratio(api):
    response = TestClient(api).post(
        "/api/f51/studio/generate-previs-image",
        json={"project_id": "film-a", "mode": "setting", "prompt": "A motel room", "aspect_ratio": "4:3"},
    )
    assert response.status_code == 422


def test_generate_route_maps_missing_project_to_404(api, tmp_path):
    _override(api, _service(tmp_path, exists=False))
    response = TestClient(api).post(
        "/api/f51/studio/generate-previs-image",
        json={"project_id": "film-a", "mode": "setting", "prompt": "A motel room"},
    )
    assert response.status_code == 404


def test_generate_route_maps_provider_error_to_502(api, tmp_path):
    _override(api, _service(tmp_path, _Adapter(error=ProviderError("provider down", stage="reference_generation_provider"))))
    response = TestClient(api).post(
        "/api/f51/studio/generate-previs-image",
        json={"project_id": "film-a", "mode": "character", "prompt": "Maya"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["error_type"] == "provider_error"


def test_presets_route_returns_catalogue(api):
    response = TestClient(api).get("/api/f51/studio/previs-image-presets")
    assert response.status_code == 200
    body = response.json()
    assert body["aspect_ratios"] == ["16:9", "1:1", "9:16"]
    assert any(preset["id"] == "soft_window" for preset in body["lighting_presets"])
