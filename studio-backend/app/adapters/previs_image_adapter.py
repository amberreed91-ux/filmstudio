"""Prompt-to-still generation for Reference Space visual development.

Reuses the casting adapter's provider contract (bounded request, single attempt,
guarded download) and only changes the requested framing. No new provider, key,
or retry policy is introduced here.
"""
from __future__ import annotations

from app.adapters.casting_image_adapter import CastingImageAdapter

# Runway gen4_image aspect ratios. The Reference Space exposes the three
# ratios that matter for stills and shot boards (canonical engine: runway).
ASPECT_RATIO_SIZES: dict[str, str] = {
    "16:9": "1280*720",
    "1:1": "1024*1024",
    "9:16": "720*1280",
}


class PrevisImageAdapter(CastingImageAdapter):
    """Generate one still at a creator-selected aspect ratio."""

    # Reference stills must never carry typography or a collage grid: those are
    # the two artifacts that make a generated reference unusable downstream.
    NEGATIVE_PROMPT = (
        "collage, multiple frames, split screen, text, captions, subtitles, watermarks, "
        "logo, blurry, plastic skin, distorted anatomy, extra limbs"
    )

    def generate_still(self, prompt: str, seed: int, aspect_ratio: str) -> bytes:
        size = ASPECT_RATIO_SIZES.get(aspect_ratio)
        if not size:
            raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")
        return self.generate_at_size(prompt, seed, size)
