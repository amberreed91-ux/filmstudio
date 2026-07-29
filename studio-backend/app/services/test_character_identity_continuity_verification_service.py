from __future__ import annotations

from pathlib import Path

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.models.character_profile import (
    CanonicalCharacterIdentityRecord,
    CharacterAppearanceTraits,
    CharacterIdentityCore,
    CharacterVisualReference,
)
from app.services.character_identity_continuity_verification_service import (
    CharacterIdentityContinuityVerificationService,
)
from app.services.visual_embedding_adapter import MockLocalVisualEmbeddingAdapter


def _write_frame(path: Path, marker: bytes) -> str:
    path.write_bytes(marker)
    return str(path)


def _job(project_id: str, shot_id: str, frame_path: str) -> RenderJobModel:
    return RenderJobModel(
        id=f"job-{shot_id}",
        project_id=project_id,
        shot_id=shot_id,
        provider="local",
        status="complete",
        input_payload=RenderJobInput(shot_id=shot_id, prompt=f"Render {shot_id}"),
        output_payload=RenderJobOutput(
            asset_url=frame_path,
            thumbnail_url=frame_path,
            metadata={"representative_frame": frame_path},
        ),
        created_at="2026-07-24T00:00:00",
        updated_at="2026-07-24T00:00:00",
        completed_at="2026-07-24T00:00:01",
    )


def _maya_record(reference_path: str) -> CanonicalCharacterIdentityRecord:
    return CanonicalCharacterIdentityRecord(
        character_id="maya",
        name="Maya",
        identity_core=CharacterIdentityCore(
            face_reference=reference_path,
            facial_identity="heart-shaped face, deep-set eyes",
            body_and_silhouette="compact frame, squared shoulders",
            skin_tone="warm brown",
            hair_style="tight coils",
            hair_length="chin length",
            hair_color="black",
            age_presentation="late thirties",
        ),
        default_appearance=CharacterAppearanceTraits(
            wardrobe=["charcoal work jacket", "plain white tee"],
            accessories=["thin silver chain"],
            persistent_props=["brass lighter"],
            emotional_state="contained grief",
        ),
        approved_visual_references=[
            CharacterVisualReference(
                ref_id="charlock:maya",
                image_url=reference_path,
                source_shot_id="scene_001_shot_001",
                source_job_id="job-scene_001_shot_001",
                source_status="approved",
                reliability="high",
                role="face",
            )
        ],
        rejected_visual_references=[
            CharacterVisualReference(
                ref_id="charlock:maya-rejected",
                image_url="https://cdn.example.test/rejected-maya.jpg",
                source_shot_id="scene_002_shot_001",
                source_job_id="job-rejected",
                source_status="rejected",
                reliability="low",
            )
        ],
        reliability="high",
        trace_sources=[
            {"kind": "approved_render", "source_job_id": "job-scene_001_shot_001"},
        ],
    )


def test_rendered_sequence_identity_continuity_uses_approved_reference_trace(tmp_path):
    project_id = "proj-sprint3-visual-sequence"
    reference = _write_frame(tmp_path / "maya_approved_reference.jpg", b"maya-consistent-visual-identity")
    record = _maya_record(reference)
    service = CharacterIdentityContinuityVerificationService(
        embedding_adapter=MockLocalVisualEmbeddingAdapter()
    )

    shots = [
        ("close up", "scene_001", "scene_001_shot_001"),
        ("medium shot", "scene_001", "scene_001_shot_002"),
        ("full body shot", "scene_002", "scene_002_shot_001"),
        ("interior scene", "scene_002", "scene_002_shot_002"),
        ("exterior scene", "scene_003", "scene_003_shot_001"),
        ("different lighting", "scene_003", "scene_003_shot_002"),
        ("wardrobe change", "scene_003", "scene_003_shot_003"),
        ("emotional change", "scene_004", "scene_004_shot_001"),
        ("multi character shot", "scene_004", "scene_004_shot_002"),
        ("later scene returning to earlier wardrobe", "scene_005", "scene_005_shot_001"),
    ]
    jobs = [
        _job(
            project_id,
            shot_id,
            _write_frame(tmp_path / f"{shot_id}.jpg", b"maya-consistent-visual-identity"),
        )
        for _, _, shot_id in shots
    ]
    scenes_by_shot_id = {
        shot_id: {"scene_id": scene_id, "characters": ["Maya"], "coverage": label}
        for label, scene_id, shot_id in shots
    }
    scenes_by_shot_id["scene_004_shot_002"]["characters"] = ["Maya", "Jonah"]

    report = service.verify_rendered_sequence(
        project_id=project_id,
        character_records=[record],
        render_jobs=jobs,
        scenes_by_shot_id=scenes_by_shot_id,
    )

    assert report["sequence_status"] == "consistent"
    assert report["reference_trace_complete"] is True
    assert report["viewer_belief_standard"].startswith("viewer reasonably believes")
    assert len(report["shot_reports"]) == 10
    assert report["warnings"] == []
    for shot in report["shot_reports"]:
        maya = shot["characters"][0]
        assert maya["status"] == "consistent"
        assert maya["viewer_belief"] == "same_character"
        assert maya["reference_trace"][0]["source_job_id"] == "job-scene_001_shot_001"
        assert maya["reference_trace"][0]["source_status"] == "approved"
        assert "rejected" not in str(maya["reference_trace"]).lower()


def test_rendered_sequence_identity_continuity_flags_drift_for_visual_mismatch(tmp_path):
    project_id = "proj-sprint3-visual-sequence"
    reference = _write_frame(tmp_path / "maya_approved_reference.jpg", b"maya-consistent-visual-identity")
    drift_frame = _write_frame(tmp_path / "scene_004_shot_002.jpg", b"different-casting-decision")
    record = _maya_record(reference)
    service = CharacterIdentityContinuityVerificationService(
        embedding_adapter=MockLocalVisualEmbeddingAdapter()
    )

    report = service.verify_rendered_sequence(
        project_id=project_id,
        character_records=[record],
        render_jobs=[_job(project_id, "scene_004_shot_002", drift_frame)],
        scenes_by_shot_id={
            "scene_004_shot_002": {
                "scene_id": "scene_004",
                "characters": ["Maya"],
                "coverage": "multi character shot",
            }
        },
    )

    assert report["sequence_status"] == "identity_drift"
    assert report["shot_reports"][0]["characters"][0]["viewer_belief"] == "identity_may_not_read_as_same_character"
    assert report["warnings"] == ["scene_004_shot_002: Maya needs identity review."]


def test_rendered_sequence_identity_continuity_requires_local_visual_evidence(tmp_path):
    project_id = "proj-sprint3-visual-sequence"
    reference = _write_frame(tmp_path / "maya_approved_reference.jpg", b"maya-consistent-visual-identity")
    record = _maya_record(reference)
    job = RenderJobModel(
        id="job-scene_001_shot_001",
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="remote",
        status="complete",
        input_payload=RenderJobInput(shot_id="scene_001_shot_001"),
        output_payload=RenderJobOutput(asset_url="https://cdn.example.test/shot.mp4", thumbnail_url=""),
    )
    service = CharacterIdentityContinuityVerificationService(
        embedding_adapter=MockLocalVisualEmbeddingAdapter()
    )

    report = service.verify_rendered_sequence(
        project_id=project_id,
        character_records=[record],
        render_jobs=[job],
        scenes_by_shot_id={"scene_001_shot_001": {"scene_id": "scene_001", "characters": ["Maya"]}},
    )

    assert report["sequence_status"] == "manual_review"
    assert report["shot_reports"][0]["reason"] == "missing_local_output_frame"
    assert report["reference_trace_complete"] is True
