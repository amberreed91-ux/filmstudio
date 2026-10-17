"""Centralized generation-model registry (provider-agnostic).

Single source of truth for which generation models Studio knows about, what
each can actually do, and what each costs. Nothing else in Studio may hardcode
a model id: adapters, render validation, routing, and the UI all read from
here, so a model can be added, disabled, or retired without touching the
generation architecture.

Evidence discipline (mirrors provider_capability_contract.py):
- Every capability recorded here is VERIFIED against the provider's published
  API documentation (https://docs.dev.runwayml.com — models, API input
  parameters, and pricing pages, verified 2026-09-25) or against the installed
  adapter's code. Unknowns are recorded as such and fail closed; nothing is
  invented to fill a gap.
- ``relative_cost`` is a simple tier (1=cheapest … 5=most expensive) used only
  for human-readable recommendation sentences — never surfaced as a score.

The Runway entries below replace the previous hardcoded
``ALLOWED_RUNWAY_MODELS`` frozenset, which contained two model ids that do not
exist on the current Runway Dev API (``gen6``, ``gen3`` — the changelog
confirms Gen-3 Alpha Turbo and Gen-4 Aleph are retired and requests using
those identifiers fail).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

# ── Capability vocabulary ────────────────────────────────────────────────────

GENERATION_MODES = ("text_to_video", "image_to_video", "video_to_video")

# Modalities: video models render shots; image models render stills; chat
# models are advisory intelligence only and can never render anything.
MODALITY_VIDEO = "video"
MODALITY_IMAGE = "image"
MODALITY_CHAT = "chat"

# Roles distinguish what a model may be used FOR. ``advisory_intelligence``
# models (Co-Director chat) are never render-executable and never mutate
# canonical truth; ``generation`` models are render-executable through the
# video/image adapter layer.
ROLE_GENERATION = "generation"
ROLE_ADVISORY_INTELLIGENCE = "advisory_intelligence"
ROLE_IMAGE_GENERATION = "image_generation"

REFERENCE_TYPES = (
    "character_image",      # identity / locked character references
    "setting_image",        # environment / setting references
    "style_image",          # style boards
    "first_frame",          # first-frame conditioning (I2V init)
    "last_frame",           # last-frame keyframe conditioning
    "reference_video",      # video references
    "reference_audio",      # audio references
)

AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_DISABLED = "disabled"       # operator-disabled inside Studio
AVAILABILITY_RETIRED = "retired"         # provider no longer accepts it


@dataclass(frozen=True)
class ModelDefinition:
    """One generation model with verified, structured metadata."""

    model_id: str
    provider: str
    label: str
    generation_modes: tuple[str, ...]
    reference_types: tuple[str, ...]
    maximum_reference_count: int
    supported_durations: tuple[int, ...]
    supported_resolutions: tuple[str, ...]
    supported_ratios: tuple[str, ...]
    audio_support: bool
    first_frame_support: bool
    last_frame_support: bool
    image_to_video_support: bool
    video_to_video_support: bool
    relative_cost: int                      # 1 (cheapest) … 5 (most expensive)
    credits_per_second: int                 # verified published rate
    availability_status: str = AVAILABILITY_AVAILABLE
    notes: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    evidence: str = "verified_docs"
    # ── Cross-modality extension (additive; defaults preserve every existing
    #    entry's serialized shape for keys above) ──
    modality: str = MODALITY_VIDEO
    modality_detail: str = ""               # e.g. text_to_video | text_to_image | chat_completion
    # Endpoint/auth are recorded as ENV VAR NAMES, never values or keys.
    endpoint_config: str = ""               # env var holding the base URL (+ its default)
    auth_env_var: str = ""                  # env var holding the credential (name only)
    roles: tuple[str, ...] = (ROLE_GENERATION,)

    def supports_mode(self, mode: str) -> bool:
        return mode in self.generation_modes

    def supports_reference_type(self, reference_type: str) -> bool:
        return reference_type in self.reference_types

    def supports_duration(self, duration: int) -> bool:
        return duration in self.supported_durations

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "label": self.label,
            "generation_modes": list(self.generation_modes),
            "reference_types": list(self.reference_types),
            "maximum_reference_count": self.maximum_reference_count,
            "supported_durations": list(self.supported_durations),
            "supported_resolutions": list(self.supported_resolutions),
            "supported_ratios": list(self.supported_ratios),
            "audio_support": self.audio_support,
            "first_frame_support": self.first_frame_support,
            "last_frame_support": self.last_frame_support,
            "image_to_video_support": self.image_to_video_support,
            "video_to_video_support": self.video_to_video_support,
            "relative_cost": self.relative_cost,
            "credits_per_second": self.credits_per_second,
            "availability_status": self.availability_status,
            "notes": self.notes,
            "capabilities": list(self.capabilities),
            "evidence": self.evidence,
            # Additive cross-modality fields (chat/image models carry these;
            # legacy video entries keep their existing defaults).
            "modality": self.modality,
            "modality_detail": self.modality_detail,
            "endpoint_config": self.endpoint_config,
            "auth_env_var": self.auth_env_var,
            "roles": list(self.roles),
        }


# ── Runway video models (verified 2026-09-25 against docs.dev.runwayml.com:
#    /guides/models, /assets/inputs, /guides/pricing, /api-details/api_changelog).
#
#    Duration tuples list the *bounded* set Studio offers filmmakers; models
#    whose docs allow a continuous range list the practical subset Studio
#    exposes so the picker and the router stay deterministic.
#
#    Reference-model notes:
#    - gen4.5: image-to-video takes a single promptImage (first frame or
#      identity reference); no native audio; 12 credits/second.
#    - gen4_turbo: image input only, single promptImage; 5 credits/second.
#    - veo3.1 / veo3.1_fast: first/last keyframes + native audio.
#    - wan3: up to 10 image + 5 video + 5 audio references, first/last
#      keyframes (not mixable), native audio, 2–30 s.
#    - seedance2_5: up to 30 image + 10 video + 10 audio references, 4–30 s.
#    - h3_max: first/last keyframes (single image), 5–15 s, 480p/768p.
#    - hailuo3: reference images/videos/audio, 5–15 s, 768P/2K.
#    - grok_imagine_1_5: up to 7 image + 3 audio references (T2V), single
#      first frame (I2V), native audio, 1–15 s.

_RUNWAY_MODELS: tuple[ModelDefinition, ...] = (
    ModelDefinition(
        model_id="gen4.5",
        provider="runway",
        label="Runway Gen-4.5",
        generation_modes=("text_to_video", "image_to_video"),
        reference_types=("character_image", "setting_image", "first_frame"),
        maximum_reference_count=1,
        supported_durations=tuple(range(2, 11)),
        supported_resolutions=("720p",),
        supported_ratios=("1280:720", "720:1280", "960:960", "1104:832", "832:1104", "1584:672", "672:1584"),
        audio_support=False,
        first_frame_support=True,
        last_frame_support=False,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=3,
        credits_per_second=12,
        notes="Flagship Runway model; single promptImage conditioning (identity reference or first frame).",
    ),
    ModelDefinition(
        model_id="gen4_turbo",
        provider="runway",
        label="Runway Gen-4 Turbo",
        generation_modes=("image_to_video",),
        reference_types=("character_image", "setting_image", "first_frame"),
        maximum_reference_count=1,
        supported_durations=tuple(range(2, 11)),
        supported_resolutions=("720p",),
        supported_ratios=("1280:720", "720:1280", "960:960", "1104:832", "832:1104", "1584:672", "672:1584"),
        audio_support=False,
        first_frame_support=True,
        last_frame_support=False,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=2,
        credits_per_second=5,
        notes="Image input only — cannot run text-to-video. Lower-cost Gen-4 image conditioning.",
    ),
    ModelDefinition(
        model_id="veo3.1",
        provider="runway",
        label="Google Veo 3.1",
        generation_modes=("text_to_video", "image_to_video"),
        reference_types=("first_frame", "last_frame"),
        maximum_reference_count=2,
        supported_durations=(4, 6, 8),
        supported_resolutions=("720p", "1080p"),
        supported_ratios=("16:9", "9:16"),
        audio_support=True,
        first_frame_support=True,
        last_frame_support=True,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=5,
        credits_per_second=40,
        notes="Native audio generation (40 credits/s with audio, 20 without). First/last keyframe conditioning.",
    ),
    ModelDefinition(
        model_id="veo3.1_fast",
        provider="runway",
        label="Google Veo 3.1 Fast",
        generation_modes=("text_to_video", "image_to_video"),
        reference_types=("first_frame", "last_frame"),
        maximum_reference_count=2,
        supported_durations=(4, 6, 8),
        supported_resolutions=("720p", "1080p"),
        supported_ratios=("16:9", "9:16"),
        audio_support=True,
        first_frame_support=True,
        last_frame_support=True,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=4,
        credits_per_second=15,
        notes="Faster, cheaper Veo 3.1 tier with native audio.",
    ),
    ModelDefinition(
        model_id="wan3",
        provider="runway",
        label="WAN 3.0",
        generation_modes=("text_to_video", "image_to_video"),
        reference_types=("character_image", "setting_image", "first_frame", "last_frame", "reference_video", "reference_audio"),
        maximum_reference_count=10,
        supported_durations=(5, 10, 15, 20, 30),
        supported_resolutions=("480p", "720p", "1080p"),
        supported_ratios=("auto_1080p",),
        audio_support=True,
        first_frame_support=True,
        last_frame_support=True,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=3,
        credits_per_second=10,
        notes="Reference-driven shots: up to 10 image / 5 video / 5 audio references. Keyframes cannot be mixed with references. Native audio.",
    ),
    ModelDefinition(
        model_id="seedance2_5",
        provider="runway",
        label="Seedance 2.5",
        generation_modes=("text_to_video", "image_to_video", "video_to_video"),
        reference_types=("character_image", "setting_image", "style_image", "first_frame", "last_frame", "reference_video", "reference_audio"),
        maximum_reference_count=30,
        supported_durations=(5, 10, 15, 20, 30),
        supported_resolutions=("480p", "720p", "1080p"),
        supported_ratios=("1280:720", "1920:1080", "720:1280", "1080:1920"),
        audio_support=True,
        first_frame_support=True,
        last_frame_support=True,
        image_to_video_support=True,
        video_to_video_support=True,
        relative_cost=5,
        credits_per_second=30,
        notes="Largest reference budget (30 images / 10 videos / 10 audio). 80-credit minimum per generation.",
    ),
    ModelDefinition(
        model_id="h3_max",
        provider="runway",
        label="MiniMax H3 Max",
        generation_modes=("text_to_video", "image_to_video"),
        reference_types=("first_frame", "last_frame"),
        maximum_reference_count=2,
        supported_durations=(5, 10, 15),
        supported_resolutions=("480p", "768p"),
        supported_ratios=("adaptive",),
        audio_support=False,
        first_frame_support=True,
        last_frame_support=True,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=1,
        credits_per_second=5,
        notes="Keyframe-only conditioning (first/last), no multi-reference. Lowest published cost tier.",
    ),
    ModelDefinition(
        model_id="hailuo3",
        provider="runway",
        label="Hailuo 3.0",
        generation_modes=("text_to_video", "image_to_video", "video_to_video"),
        reference_types=("character_image", "setting_image", "first_frame", "last_frame", "reference_video", "reference_audio"),
        maximum_reference_count=10,
        supported_durations=(5, 10, 15),
        supported_resolutions=("768P", "2K"),
        supported_ratios=("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"),
        audio_support=False,
        first_frame_support=True,
        last_frame_support=True,
        image_to_video_support=True,
        video_to_video_support=True,
        relative_cost=2,
        credits_per_second=10,
        notes="Reference images/videos/audio with keyframe control (2 credits per reference image).",
    ),
    ModelDefinition(
        model_id="grok_imagine_1_5",
        provider="runway",
        label="Grok Imagine Video 1.5",
        generation_modes=("text_to_video", "image_to_video"),
        reference_types=("character_image", "setting_image", "first_frame", "reference_audio"),
        maximum_reference_count=7,
        supported_durations=(5, 10, 15),
        supported_resolutions=("480p", "720p", "1080p"),
        supported_ratios=("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"),
        audio_support=True,
        first_frame_support=True,
        last_frame_support=False,
        image_to_video_support=True,
        video_to_video_support=False,
        relative_cost=2,
        credits_per_second=10,
        notes="Prompt-addressable image references ([Image 1] …); I2V uses a single first frame. Native audio.",
    ),
    ModelDefinition(
        model_id="gemini_omni_flash",
        provider="runway",
        label="Gemini Omni Flash",
        generation_modes=("text_to_video", "image_to_video", "video_to_video"),
        reference_types=("first_frame",),
        maximum_reference_count=1,
        supported_durations=(5, 10),
        supported_resolutions=("720p",),
        supported_ratios=("1280:720", "720:1280"),
        audio_support=False,
        first_frame_support=True,
        last_frame_support=False,
        image_to_video_support=True,
        video_to_video_support=True,
        relative_cost=2,
        credits_per_second=10,
        notes="720p only; I2V takes a single first frame (+1 credit for the image).",
    ),
)

# ── Muse Glimmer 30B — advisory chat/intelligence model ───────────────────
#
# Advisory only, by contract: this model answers Co-Director chat/intelligence
# calls through the existing chat provider abstraction. It is registered as a
# chat-modality model with NO generation role, so render routing, adapters,
# cost gates, and the readiness gate can never select or execute it. It never
# mutates canonical screenplay, FilmStructure, CreativeSpine, storyboard
# approval state, references, camera approval, dialogue assignments, locks,
# or generation manifests — its output is an advisory reply string only.
#
# Endpoint/auth: OpenAI-compatible chat completions served by the Muse
# endpoint; credential comes from the MUSE_API_KEY environment variable.

_MUSE_MODEL = ModelDefinition(
    # Namespaced served-model id, verified against NVIDIA's published NIM
    # reference for this model (docs.api.nvidia.com / build.nvidia.com,
    # 2026-09-27); the un-namespaced form returned HTTP 404 on
    # integrate.api.nvidia.com/v1/chat/completions.
    model_id="meta/muse-glimmer-30b",
    provider="muse",
    label="Muse Glimmer 30B",
    generation_modes=(),                    # not a generation model — never renders
    reference_types=(),
    maximum_reference_count=0,
    supported_durations=(),
    supported_resolutions=(),
    supported_ratios=(),
    audio_support=False,
    first_frame_support=False,
    last_frame_support=False,
    image_to_video_support=False,
    video_to_video_support=False,
    relative_cost=1,
    credits_per_second=0,                   # not credit-priced (not a render model)
    notes=(
        "Advisory intelligence model for Co-Director chat. Never renders; "
        "never mutates canonical truth; output is advisory text only."
    ),
    modality=MODALITY_CHAT,
    modality_detail="chat_completion",
    endpoint_config="MUSE_API_BASE_URL (default https://api.muse.example.com/v1)",
    auth_env_var="MUSE_API_KEY",
    roles=(ROLE_ADVISORY_INTELLIGENCE,),
)

# ── FLUX.2 Klein 4B — hosted image generation via NVIDIA's API ───────────
#
# Verified against NVIDIA's published NIM visual-genai documentation (the
# OpenAI-compatible image generation endpoint lists ``flux.2-klein-4b`` as a
# supported model name; black-forest-labs/flux_2-klein-4b on build.nvidia.com,
# verified 2026-09-26). Text-to-image only on this integration; the image
# generation itself is submitted through the existing image-provider seam.

_FLUX2_KLEIN_MODEL = ModelDefinition(
    model_id="flux.2-klein-4b",
    provider="nvidia",
    label="FLUX.2 Klein 4B (NVIDIA)",
    generation_modes=("text_to_image",),
    reference_types=(),                     # text-to-image integration; no reference conditioning
    maximum_reference_count=0,
    supported_durations=(),
    supported_resolutions=("1024x1024", "1536x1024", "1024x1536"),
    supported_ratios=("1:1", "3:2", "2:3"),
    audio_support=False,
    first_frame_support=False,
    last_frame_support=False,
    image_to_video_support=False,
    video_to_video_support=False,
    relative_cost=1,
    credits_per_second=0,                   # priced by NVIDIA's image pricing, not Studio credits
    notes=(
        "Hosted text-to-image via NVIDIA's OpenAI-compatible image generation "
        "API. Studio routes it through the image provider seam; no storyboard, "
        "reference, or scene service is coupled to NVIDIA request handling."
    ),
    modality=MODALITY_IMAGE,
    modality_detail="text_to_image",
    endpoint_config="NVIDIA_IMAGE_API_BASE_URL (default https://ai.api.nvidia.com, hosted path /v1/genai/black-forest-labs/flux.2-klein-4b)",
    auth_env_var="NVIDIA_API_KEY",
    roles=(ROLE_IMAGE_GENERATION,),
)

_GEN4_IMAGE_MODEL = ModelDefinition(
    model_id="gen4_image",
    provider="runway",
    label="Runway Gen-4 Image",
    generation_modes=("text_to_image",),
    reference_types=(),                     # image-seam integration; reference support is
    maximum_reference_count=3,              # reported via the provider, not routed here
    supported_durations=(),
    supported_resolutions=("1280:720",),
    supported_ratios=(
        "1024:1024", "1080:1080", "1168:880", "1360:768", "1440:1080",
        "1080:1440", "1808:768", "1920:1080", "1080:1920", "2112:912",
        "1280:720", "720:1280", "720:720", "960:720", "720:960", "1680:720",
    ),
    audio_support=False,
    first_frame_support=False,
    last_frame_support=False,
    image_to_video_support=False,
    video_to_video_support=False,
    relative_cost=1,
    credits_per_second=0,                   # priced per image by Runway, not per second
    notes=(
        "Hosted text-to-image via Runway Dev API POST /v1/text_to_image. Studio "
        "routes it through the image provider seam; no storyboard, reference, "
        "or scene service is coupled to Runway request handling. Not a video "
        "model: video routing never selects it."
    ),
    modality=MODALITY_IMAGE,
    modality_detail="text_to_image",
    endpoint_config="RUNWAY_IMAGE_API_BASE_URL (default https://api.dev.runwayml.com, path /v1/text_to_image)",
    auth_env_var="RUNWAY_API_KEY",
    roles=(ROLE_IMAGE_GENERATION,),
)

_MODELS_BY_PROVIDER: tuple[ModelDefinition, ...] = (
    _MUSE_MODEL,
    _FLUX2_KLEIN_MODEL,
    _GEN4_IMAGE_MODEL,
)


class ModelRegistry:
    """Deterministic lookup over verified model definitions.

    The registry never mutates and never executes anything. Operators extend it
    by adding a ``ModelDefinition``; disabling a model changes
    ``availability_status`` without touching any generation code path.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelDefinition] = {
            definition.model_id: definition for definition in _RUNWAY_MODELS
        }
        # Cross-modality entries (chat intelligence + hosted image generation).
        # Additive: legacy Runway registry behavior is unchanged.
        for definition in _MODELS_BY_PROVIDER:
            self._models[definition.model_id] = definition

    # ── Lookup ────────────────────────────────────────────────────────────

    def get_model(self, model_id: str) -> ModelDefinition | None:
        return self._models.get(str(model_id or "").strip())

    def require_model(self, model_id: str) -> ModelDefinition:
        model = self.get_model(model_id)
        if model is None:
            raise ValueError(
                f"Unknown generation model '{model_id}'. "
                f"Known models: {sorted(self._models)}"
            )
        return model

    def models_for_provider(self, provider: str) -> list[ModelDefinition]:
        normalized = str(provider or "").strip().lower()
        return [
            model
            for model in self._models.values()
            if model.provider == normalized
            and model.availability_status == AVAILABILITY_AVAILABLE
        ]

    def models_for_modality(self, modality: str) -> list[ModelDefinition]:
        """Available models for one modality (video | image | chat)."""
        normalized = str(modality or "").strip().lower()
        return [
            model
            for model in self._models.values()
            if model.modality == normalized
            and model.availability_status == AVAILABILITY_AVAILABLE
        ]

    def advisory_intelligence_model_ids(self) -> frozenset[str]:
        """Model ids carrying the advisory_intelligence role (never render-executable)."""
        return frozenset(
            model.model_id
            for model in self._models.values()
            if ROLE_ADVISORY_INTELLIGENCE in model.roles
        )

    def image_generation_model_ids(self) -> frozenset[str]:
        """Model ids carrying the image_generation role (render via the image seam)."""
        return frozenset(
            model.model_id
            for model in self._models.values()
            if ROLE_IMAGE_GENERATION in model.roles
        )

    def list_models(self, *, include_unavailable: bool = False) -> list[ModelDefinition]:
        models = list(self._models.values())
        if include_unavailable:
            return models
        return [m for m in models if m.availability_status == AVAILABILITY_AVAILABLE]

    def allowed_model_ids(self, provider: str) -> frozenset[str]:
        """Verifiable allowlist for per-request model overrides.

        Scoped to VIDEO-modality models: this allowlist gates per-request model
        overrides on video renders (render validation + the video adapter).
        Image-modality models of the same provider (e.g. runway ``gen4_image``)
        are render-executable through the image provider seam and must never be
        acceptable video-model overrides. Chat/advisory models were already
        excluded by their empty generation surface.
        """
        return frozenset(
            model.model_id
            for model in self.models_for_provider(provider)
            if model.modality == MODALITY_VIDEO
        )

    # ── Mutation points for operators (registry data only) ────────────────

    def register_model(self, definition: ModelDefinition) -> None:
        """Add or replace a model definition (operator action, not runtime)."""
        self._models[definition.model_id] = definition

    def set_availability(self, model_id: str, status: str) -> None:
        model = self.require_model(model_id)
        if status not in {AVAILABILITY_AVAILABLE, AVAILABILITY_DISABLED, AVAILABILITY_RETIRED}:
            raise ValueError(f"Invalid availability status: {status}")
        self._models[model_id] = ModelDefinition(**{
            **{k: v for k, v in model.to_dict().items() if k != "notes"},
            "notes": model.notes,
            "availability_status": status,
        })

    # ── Capability matching ───────────────────────────────────────────────

    def check_requirements(
        self,
        model: ModelDefinition,
        requirements: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        """Check one model against a validated requirements dict.

        Returns (blockers, warnings). Blockers are capability violations that
        must stop the render; warnings are advisory mismatches. Requirement
        keys (all optional):
          generation_mode, reference_types (list[str]), reference_count (int),
          duration_seconds (int), resolution (str), audio (bool),
          first_frame (bool), last_frame (bool)
        """
        blockers: list[str] = []
        warnings: list[str] = []

        mode = str(requirements.get("generation_mode") or "").strip()
        if mode and not model.supports_mode(mode):
            blockers.append(
                f"{model.model_id} does not support {mode}; modes: {', '.join(model.generation_modes)}"
            )

        required_refs = requirements.get("reference_types") or []
        if isinstance(required_refs, list):
            for ref_type in required_refs:
                ref_type = str(ref_type).strip()
                if ref_type and not model.supports_reference_type(ref_type):
                    blockers.append(
                        f"{model.model_id} does not support {ref_type} conditioning"
                    )

        reference_count = requirements.get("reference_count")
        if isinstance(reference_count, int) and reference_count > model.maximum_reference_count:
            blockers.append(
                f"{model.model_id} accepts at most {model.maximum_reference_count} "
                f"reference image(s); the shot requires {reference_count}"
            )

        duration = requirements.get("duration_seconds")
        if isinstance(duration, int) and duration > 0 and not model.supports_duration(duration):
            blockers.append(
                f"{model.model_id} cannot render {duration}s; supported durations: "
                + ", ".join(str(d) for d in model.supported_durations)
            )

        resolution = str(requirements.get("resolution") or "").strip()
        if resolution and resolution not in model.supported_resolutions:
            blockers.append(
                f"{model.model_id} does not support {resolution} output; "
                f"supported: {', '.join(model.supported_resolutions)}"
            )

        if requirements.get("audio") and not model.audio_support:
            warnings.append(
                f"{model.model_id} does not generate native audio; dialogue/audio "
                "must be produced by Studio's audio pipeline"
            )
        if requirements.get("last_frame") and not model.last_frame_support:
            blockers.append(f"{model.model_id} does not support last-frame keyframe conditioning")

        return blockers, warnings

    def estimate_cost_credits(self, model: ModelDefinition, duration_seconds: int) -> int:
        """Deterministic credit estimate from the model's published rate."""
        duration = max(int(duration_seconds or 0), 1)
        return model.credits_per_second * duration


# Single shared instance (read-only after startup; thread-safe by construction).
model_registry = ModelRegistry()


def allowed_runway_model_ids() -> frozenset[str]:
    """Compatibility bridge for the adapter's override validation."""
    return model_registry.allowed_model_ids("runway")


def describe_model(model_id: str) -> dict[str, Any] | None:
    model = model_registry.get_model(model_id)
    return copy.deepcopy(model.to_dict()) if model else None
