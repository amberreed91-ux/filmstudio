from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class VisionAnalysisResult:
    caption: str
    visual_summary: str
    mood_tags: List[str]
    lighting_tags: List[str]
    composition_tags: List[str]
    color_palette: List[str]
    detected_subjects: List[str]
    camera_notes: str
    confidence: float
    provider: str
    model: str
    status: str
    metadata: Dict[str, object]


class VisionModelAdapter:
    """Provider-agnostic adapter for keyframe still-image analysis."""

    def analyze_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisionAnalysisResult:
        raise NotImplementedError


class UnavailableVisionModelAdapter(VisionModelAdapter):
    def analyze_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisionAnalysisResult:
        return VisionAnalysisResult(
            caption="",
            visual_summary="",
            mood_tags=[],
            lighting_tags=[],
            composition_tags=[],
            color_palette=[],
            detected_subjects=[],
            camera_notes="",
            confidence=0.0,
            provider="unavailable",
            model="unconfigured",
            status="unavailable",
            metadata={"message": "vision analysis not configured"},
        )


class MockLocalVisionModelAdapter(VisionModelAdapter):
    """Deterministic local test adapter for non-credit QA runs."""

    def analyze_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisionAnalysisResult:
        frame_name = Path(image_path).name.lower()
        if "0000" in frame_name:
            mood = ["calm", "anticipatory"]
            lighting = ["soft", "natural"]
            composition = ["wide", "establishing"]
        elif "0001" in frame_name:
            mood = ["tense", "focused"]
            lighting = ["contrasty", "directional"]
            composition = ["medium", "center-weighted"]
        else:
            mood = ["reflective"]
            lighting = ["low-key"]
            composition = ["close-up"]
        return VisionAnalysisResult(
            caption="Mock local frame analysis (still-image mode).",
            visual_summary="Deterministic local analysis for keyframe QA without external vision calls.",
            mood_tags=mood,
            lighting_tags=lighting,
            composition_tags=composition,
            color_palette=["#1f2937", "#6b7280", "#f59e0b"],
            detected_subjects=["subject_unspecified"],
            camera_notes="Still-frame approximation only; motion analysis disabled in this phase.",
            confidence=0.62,
            provider="mock_local",
            model="mock-vision-v1",
            status="complete",
            metadata={
                "mode": "still_image_only",
                "advisory_only": True,
                "external_call": False,
                "context_project_id": (context or {}).get("project_id"),
            },
        )


def build_vision_model_adapter() -> VisionModelAdapter:
    provider = (os.getenv("VISION_ANALYSIS_PROVIDER") or "").strip().lower()
    if provider in {"mock", "mock_local", "local"}:
        return MockLocalVisionModelAdapter()
    # Local/test runtime fallback for QA: keep analysis deterministic without external calls.
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    render_test_mode = (os.getenv("RENDER_PROVIDER_TEST_MODE") or "").strip().lower()
    if not provider and (app_env in {"local", "test", "dev", "development"} or render_test_mode == "mock_success"):
        return MockLocalVisionModelAdapter()
    return UnavailableVisionModelAdapter()
