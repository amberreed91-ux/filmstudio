"""Reference Space still generation: creator prompt -> provider -> project file.

Explicit creator action only. This service generates and stores one still; it
never approves, canonicalizes, trains, or binds anything. Turning a generated
still into a reference stays with the reference-library approval workflow, and
attaching one to a shot stays with the shot-binding path.

Provider contract: one bounded request per creator action, no implicit retries.
A failed generation registers nothing, so the creator can retry deliberately.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.adapters.previs_image_adapter import ASPECT_RATIO_SIZES, PrevisImageAdapter
from app.services.character_look_service import validate_reference_image
from app.services.stability import (
    PersistenceError,
    ProviderError,
    ValidationError,
    elapsed_ms,
    log_stage_event,
    start_timer,
)

MAX_PROMPT_CHARS = 1200
MIN_PROMPT_CHARS = 3
MAX_SEED = 2_147_483_647
MAX_PROJECT_ID_CHARS = 128
_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]+$")

#: Style vocabulary shared by Character and Setting generation. ``prompt_fragment``
#: is subordinate to the creator's own words — it narrows rendering treatment,
#: never subject matter.
STYLE_PRESETS: tuple[dict[str, str], ...] = (
    {"id": "none", "label": "No style preset", "prompt_fragment": ""},
    {"id": "cinematic_35mm", "label": "Cinematic 35mm", "prompt_fragment": "shot on 35mm film, fine grain, natural halation, restrained contrast"},
    {"id": "docu_realism", "label": "Documentary realism", "prompt_fragment": "documentary still, available light, unposed, honest skin texture"},
    {"id": "painterly", "label": "Painterly", "prompt_fragment": "painterly rendering, visible brushwork, softened edges, muted palette"},
    {"id": "production_plate", "label": "Production plate", "prompt_fragment": "production design plate, architectural clarity, readable materials, no stylisation"},
    {"id": "grain_mono", "label": "Monochrome grain", "prompt_fragment": "black and white, deep grain, silver halide tonality"},
)

#: Lighting vocabulary applied after style so exposure intent reads last.
LIGHTING_PRESETS: tuple[dict[str, str], ...] = (
    {"id": "none", "label": "No lighting preset", "prompt_fragment": ""},
    {"id": "soft_window", "label": "Soft window", "prompt_fragment": "soft directional window light, gentle falloff, low contrast shadows"},
    {"id": "golden_hour", "label": "Golden hour", "prompt_fragment": "low golden hour sun, long warm shadows, atmospheric haze"},
    {"id": "practical_night", "label": "Practical night", "prompt_fragment": "night interior lit by practicals, warm pools of light, deep unlit background"},
    {"id": "high_key", "label": "High key", "prompt_fragment": "high key lighting, bright even exposure, minimal shadow"},
    {"id": "single_source", "label": "Single source", "prompt_fragment": "single hard key light, strong directional shadow, chiaroscuro"},
)

_STYLE_BY_ID = {preset["id"]: preset for preset in STYLE_PRESETS}
_LIGHTING_BY_ID = {preset["id"]: preset for preset in LIGHTING_PRESETS}

#: Composition guards keep a generated still usable as a reference. They state
#: framing, never content — the creator's prompt still decides what is depicted.
_MODE_GUARDS: dict[str, str] = {
    "character": (
        "One fictional character only, alone in frame, head and shoulders through full body readable, "
        "face clearly visible, plain neutral background, no text, no other people."
    ),
    "setting": (
        "Environment only, no people, no text. Wide establishing frame with readable spatial layout, "
        "materials, and set dressing a production designer could build from."
    ),
}


@dataclass(frozen=True)
class GeneratedStill:
    project_id: str
    mode: str
    image_url: str
    seed: int
    aspect_ratio: str
    style_preset: str
    lighting_preset: str
    provider: str
    model: str
    prompt: str
    created_at: str


class PrevisImageGenerationService:
    def __init__(self, adapter=None, outputs_dir: Path | None = None, projects=None):
        self.adapter = adapter or PrevisImageAdapter()
        self.outputs_dir = outputs_dir or Path(__file__).resolve().parents[2] / "outputs"
        self._projects = projects

    # ── Presentation -------------------------------------------------------
    @staticmethod
    def presets() -> dict:
        """The creator-facing preset catalogue, in display order."""
        return {
            "style_presets": [dict(preset) for preset in STYLE_PRESETS],
            "lighting_presets": [dict(preset) for preset in LIGHTING_PRESETS],
            "aspect_ratios": list(ASPECT_RATIO_SIZES.keys()),
            "max_prompt_chars": MAX_PROMPT_CHARS,
        }

    # ── Generation ---------------------------------------------------------
    def generate(
        self,
        *,
        project_id: str,
        mode: str,
        prompt: str,
        aspect_ratio: str = "16:9",
        style_preset: str = "none",
        lighting_preset: str = "none",
        seed: int | None = None,
    ) -> GeneratedStill:
        timer = start_timer()
        job_id = f"refgen-{uuid4().hex[:12]}"
        project = self._validate_project_id(project_id)
        composed = self._compose_prompt(mode=mode, prompt=prompt, style_preset=style_preset, lighting_preset=lighting_preset)
        resolved_seed = self._resolve_seed(seed)
        self._ensure_project(project)

        try:
            data = self.adapter.generate_still(composed, resolved_seed, aspect_ratio)
        except ProviderError as exc:
            log_stage_event(
                project_id=project, job_id=job_id, provider=self.adapter.provider,
                stage="reference_generation_provider", duration_ms=elapsed_ms(timer),
                extra={"error_type": exc.error_type, "mode": mode, "aspect_ratio": aspect_ratio},
            )
            raise
        except Exception as exc:  # provider adapters raise typed errors; this is a safety net
            log_stage_event(
                project_id=project, job_id=job_id, provider=self.adapter.provider,
                stage="reference_generation_provider", duration_ms=elapsed_ms(timer),
                extra={"error_type": "provider_error", "mode": mode},
            )
            raise ProviderError(
                "The image provider did not return a usable still. Nothing was saved; try again when you are ready.",
                stage="reference_generation_provider",
            ) from exc

        try:
            extension = validate_reference_image(data)
        except ValidationError as exc:
            raise ProviderError(
                "The image provider returned an unreadable still. Nothing was saved.",
                stage="reference_generation_download",
            ) from exc

        relative = Path("reference_generation") / project / f"{uuid4().hex}.{extension}"
        target = self.outputs_dir / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as exc:
            raise PersistenceError(
                "The generated still could not be saved to this project. Nothing was registered.",
                stage="reference_generation_persist",
            ) from exc

        log_stage_event(
            project_id=project, job_id=job_id, provider=self.adapter.provider,
            stage="reference_generation_complete", duration_ms=elapsed_ms(timer),
            extra={"mode": mode, "aspect_ratio": aspect_ratio, "style_preset": style_preset, "lighting_preset": lighting_preset},
        )
        return GeneratedStill(
            project_id=project,
            mode=mode,
            image_url=f"/outputs/{relative.as_posix()}",
            seed=resolved_seed,
            aspect_ratio=aspect_ratio,
            style_preset=style_preset,
            lighting_preset=lighting_preset,
            provider=self.adapter.provider,
            model=self.adapter.model,
            prompt=composed,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Validation ---------------------------------------------------------
    @staticmethod
    def _validate_project_id(project_id: str) -> str:
        candidate = (project_id or "").strip()
        if not candidate or len(candidate) > MAX_PROJECT_ID_CHARS or not _PROJECT_ID.match(candidate):
            raise ValidationError(
                "Choose a project before generating a reference still.",
                stage="reference_generation_validation",
            )
        return candidate

    @staticmethod
    def _compose_prompt(*, mode: str, prompt: str, style_preset: str, lighting_preset: str) -> str:
        if mode not in _MODE_GUARDS:
            raise ValidationError("Generation mode must be character or setting.", stage="reference_generation_validation")
        text = (prompt or "").strip()
        if len(text) < MIN_PROMPT_CHARS:
            raise ValidationError(
                "Describe what this reference should show before generating.",
                stage="reference_generation_validation",
            )
        if len(text) > MAX_PROMPT_CHARS:
            raise ValidationError(
                f"Keep the reference description under {MAX_PROMPT_CHARS} characters so the whole idea reaches the provider.",
                stage="reference_generation_validation",
            )
        style = _STYLE_BY_ID.get(style_preset or "none")
        lighting = _LIGHTING_BY_ID.get(lighting_preset or "none")
        if style is None:
            raise ValidationError("That style preset is not recognised. Pick one from the list.", stage="reference_generation_validation")
        if lighting is None:
            raise ValidationError("That lighting preset is not recognised. Pick one from the list.", stage="reference_generation_validation")
        # Creator words first and unaltered; presets only narrow treatment after.
        parts = [text, _MODE_GUARDS[mode]]
        if style["prompt_fragment"]:
            parts.append(style["prompt_fragment"])
        if lighting["prompt_fragment"]:
            parts.append(lighting["prompt_fragment"])
        return "\n".join(parts)

    @staticmethod
    def _resolve_seed(seed: int | None) -> int:
        if seed is None:
            return secrets.randbelow(MAX_SEED)
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 or seed > MAX_SEED:
            raise ValidationError(
                f"Seed must be a whole number between 0 and {MAX_SEED}.",
                stage="reference_generation_validation",
            )
        return seed

    def _ensure_project(self, project_id: str) -> None:
        if self._projects is None:
            from app.services.service_registry import project_service

            self._projects = project_service
        try:
            found = self._projects.get_project(project_id)
        except Exception as exc:  # storage outage is not a missing project
            raise PersistenceError(
                "The project could not be read right now. Nothing was generated.",
                stage="reference_generation_project",
            ) from exc
        if not found:
            raise ValidationError(
                "This project could not be found, so no reference was generated.",
                stage="reference_generation_project",
                metadata={"missing_project": True},
            )


def get_previs_image_generation_service() -> PrevisImageGenerationService:
    return PrevisImageGenerationService()
