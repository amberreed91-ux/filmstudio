from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import StyleSignature
from app.services.semantic_memory_service import SemanticMemoryService
from app.services.style_learning_service import StyleLearningService
from app.services.video_asset_service import VideoAssetService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def test_build_project_signature_and_retrieve_patterns(tmp_path: Path):
    storage = _make_storage(tmp_path)
    v1 = tmp_path / "style_a.mp4"
    v2 = tmp_path / "style_b.mp4"
    v1.write_text("a")
    v2.write_text("b")

    assets = VideoAssetService(storage)
    a1 = assets.register_local_file(project_id="project-style", local_path=str(v1), title="A")
    a2 = assets.register_local_file(project_id="project-style", local_path=str(v2), title="B")

    memory = SemanticMemoryService(storage, assets, None)
    memory.ingest_asset_analysis(
        asset_id=a1.asset_id,
        visual_style="warm noir",
        lighting_style="low-key",
        pacing_profile="slow-burn",
        composition_patterns=["rule-of-thirds", "static"],
        cinematic_notes="warm saturated static dolly-in composition",
    )
    memory.ingest_asset_analysis(
        asset_id=a2.asset_id,
        visual_style="cool neon",
        lighting_style="mixed",
        pacing_profile="slow-burn",
        composition_patterns=["rule-of-thirds", "symmetry"],
        cinematic_notes="cool neon handheld pan sequence",
    )

    service = StyleLearningService(storage=storage, semantic_memory=memory, video_assets=assets)
    signature = service.build_project_signature("project-style")
    assert signature.signature_id.startswith("style-")
    assert signature.project_id == "project-style"
    assert signature.advisory_only is True
    assert isinstance(signature.framing_tendencies, list)
    assert isinstance(signature.pacing_patterns, list)
    assert isinstance(signature.color_motifs, list)
    assert isinstance(signature.camera_movement_patterns, list)

    patterns = service.retrieve_style_patterns("project-style")
    assert patterns["signature_count"] >= 1
    assert patterns["latest_signature"] is not None
    assert patterns["advisory_only"] is True


def test_compare_signatures(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = StyleLearningService(storage=storage)

    left = storage.save_style_signature(
        signature=StyleSignature(
            signature_id="style-left",
            project_id="proj-x",
            framing_tendencies=["symmetry", "wide"],
            pacing_patterns=["slow"],
            color_motifs=["warm", "neon"],
            camera_movement_patterns=["static"],
            confidence=0.7,
            advisory_only=True,
            metadata={},
            created_at="2026-01-01T00:00:00Z",
        )
    )
    right = storage.save_style_signature(
        signature=StyleSignature(
            signature_id="style-right",
            project_id="proj-x",
            framing_tendencies=["symmetry", "closeup"],
            pacing_patterns=["slow", "fast-cut"],
            color_motifs=["warm"],
            camera_movement_patterns=["handheld"],
            confidence=0.7,
            advisory_only=True,
            metadata={},
            created_at="2026-01-01T00:00:01Z",
        )
    )

    comparison = service.compare_signatures(left, right)
    assert comparison["advisory_only"] is True
    assert comparison["auto_regeneration_triggered"] is False
    assert 0.0 <= comparison["overall_similarity"] <= 1.0
