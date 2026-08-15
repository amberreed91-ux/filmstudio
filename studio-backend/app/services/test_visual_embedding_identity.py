"""Tests for real visual embeddings and render-time identity verification.

The embedding layer previously defaulted to an adapter that returned empty
vectors, and the only alternative hashed the file's bytes. Cosine similarity
over either measures nothing about whether two frames show the same person, and
because empty vectors produce a 0.0 cosine, every comparison silently read as
identity drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.character_visual_reference_service import CharacterVisualReferenceService
from app.services.visual_embedding_adapter import (
    EMBEDDING_KIND_FACE,
    EMBEDDING_KIND_OPAQUE,
    EMBEDDING_KIND_VISUAL,
    DashScopeMultimodalEmbeddingAdapter,
    LocalFaceEmbeddingAdapter,
    MockLocalVisualEmbeddingAdapter,
    UnavailableVisualEmbeddingAdapter,
    VisualEmbeddingResult,
    build_visual_embedding_adapter,
    match_label,
    similarity_thresholds,
)


# ── thresholds are per embedding kind ────────────────────────────────────────


def test_face_and_visual_thresholds_are_different():
    # A single hardcoded threshold pair cannot be right for both: ArcFace and
    # CLIP cosines live on completely different scales.
    assert similarity_thresholds(EMBEDDING_KIND_FACE) != similarity_thresholds(EMBEDDING_KIND_VISUAL)


def test_same_similarity_reads_differently_per_kind():
    # 0.60 is a confident face match and a weak general-visual match.
    assert match_label(0.60, EMBEDDING_KIND_FACE) == "consistent"
    assert match_label(0.60, EMBEDDING_KIND_VISUAL) == "identity_drift"


def test_unknown_kind_falls_back_to_conservative_thresholds():
    assert similarity_thresholds("nonsense") == similarity_thresholds(EMBEDDING_KIND_OPAQUE)


@pytest.mark.parametrize(
    "similarity,expected",
    [(0.99, "consistent"), (0.90, "plausibly_consistent"), (0.10, "identity_drift")],
)
def test_match_label_bands(similarity, expected):
    assert match_label(similarity, EMBEDDING_KIND_OPAQUE) == expected


# ── adapter selection ────────────────────────────────────────────────────────


def test_explicit_mock_selection(monkeypatch):
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "mock")
    assert isinstance(build_visual_embedding_adapter(), MockLocalVisualEmbeddingAdapter)


def test_explicit_face_selection(monkeypatch):
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "face")
    assert isinstance(build_visual_embedding_adapter(), LocalFaceEmbeddingAdapter)


def test_explicit_dashscope_selection(monkeypatch):
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "dashscope")
    assert isinstance(build_visual_embedding_adapter(), DashScopeMultimodalEmbeddingAdapter)


def test_explicit_off_selection(monkeypatch):
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "none")
    assert isinstance(build_visual_embedding_adapter(), UnavailableVisualEmbeddingAdapter)


def test_auto_detect_prefers_local_face_over_hosted(monkeypatch):
    monkeypatch.delenv("VISUAL_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(LocalFaceEmbeddingAdapter, "is_available", staticmethod(lambda: True))
    assert isinstance(build_visual_embedding_adapter(), LocalFaceEmbeddingAdapter)


def test_auto_detect_falls_back_to_dashscope_when_configured(monkeypatch):
    monkeypatch.delenv("VISUAL_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(LocalFaceEmbeddingAdapter, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(
        "app.services.visual_embedding_adapter._dashscope_is_configured", lambda: True
    )
    assert isinstance(build_visual_embedding_adapter(), DashScopeMultimodalEmbeddingAdapter)


def test_auto_detect_ends_at_unavailable_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("VISUAL_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(LocalFaceEmbeddingAdapter, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(
        "app.services.visual_embedding_adapter._dashscope_is_configured", lambda: False
    )
    assert isinstance(build_visual_embedding_adapter(), UnavailableVisualEmbeddingAdapter)


def test_unrecognised_provider_name_does_not_crash(monkeypatch):
    monkeypatch.setenv("VISUAL_EMBEDDING_PROVIDER", "wat")
    monkeypatch.setattr(LocalFaceEmbeddingAdapter, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(
        "app.services.visual_embedding_adapter._dashscope_is_configured", lambda: False
    )
    assert isinstance(build_visual_embedding_adapter(), UnavailableVisualEmbeddingAdapter)


# ── adapters declare what they measure ───────────────────────────────────────


def test_mock_adapter_declares_it_does_not_measure_identity(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    path = tmp_path / "f.jpg"
    Image.new("RGB", (32, 32), (120, 120, 120)).save(path)

    result = MockLocalVisualEmbeddingAdapter().embed_image(str(path))
    assert result.status == "complete"
    assert result.metadata["measures_identity"] is False
    assert result.kind == EMBEDDING_KIND_OPAQUE


def test_face_adapter_is_the_only_kind_that_claims_identity():
    assert LocalFaceEmbeddingAdapter.kind == EMBEDDING_KIND_FACE
    assert DashScopeMultimodalEmbeddingAdapter.kind == EMBEDDING_KIND_VISUAL


def test_missing_file_is_unavailable_not_a_zero_vector():
    result = LocalFaceEmbeddingAdapter().embed_image("/nope/missing.jpg")
    assert result.status == "unavailable"
    assert result.vector == []


def test_dashscope_response_parsing():
    body = {"output": {"embeddings": [{"embedding": [3.0, 4.0]}]}}
    assert DashScopeMultimodalEmbeddingAdapter._extract_vector(body) == [3.0, 4.0]


@pytest.mark.parametrize(
    "body",
    [{}, {"output": {}}, {"output": {"embeddings": []}}, {"output": {"embeddings": [{"embedding": "x"}]}}],
)
def test_dashscope_malformed_responses_yield_no_vector(body):
    assert DashScopeMultimodalEmbeddingAdapter._extract_vector(body) == []


# ── render-time identity verification ────────────────────────────────────────


class _StubAdapter:
    """Returns a fixed vector per image path, so similarity is controllable."""

    kind = EMBEDDING_KIND_FACE

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = vectors

    def embed_image(self, image_path, context=None):
        for fragment, vector in self._vectors.items():
            if fragment in str(image_path):
                return VisualEmbeddingResult(
                    vector=vector,
                    dimension=len(vector),
                    provider="stub",
                    model="stub",
                    status="complete",
                    kind=self.kind,
                )
        return VisualEmbeddingResult(
            vector=[], dimension=0, provider="stub", model="stub", status="unavailable", kind=self.kind
        )


def _job_with_frame(frame_path: Path, project_id="proj-verify") -> RenderJobModel:
    return RenderJobModel(
        id="job-verify-1",
        project_id=project_id,
        shot_id="scene_001_shot_002",
        provider="happyhorse",
        status="complete",
        input_payload=RenderJobInput(shot_id="scene_001_shot_002", prompt="Maya turns."),
        output_payload=RenderJobOutput(asset_url=str(frame_path), thumbnail_url="", metadata={}),
        created_at="2026-08-15T00:00:00",
        updated_at="2026-08-15T00:00:00",
        completed_at="2026-08-15T00:00:00",
    )


def _setup(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path / "db"))
    character = storage.save_character("proj-verify", "Maya", {})
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_001", "characters": ["Maya"]}]},
        },
    )
    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"ref")
    output = tmp_path / "output.jpg"
    output.write_bytes(b"out")
    storage.save_character_reference_lock(
        {
            "project_id": "proj-verify",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "source_job_id": "job-earlier",
            "image_url": str(reference),
            "lock_status": "locked",
            "reference_role": "general",
        }
    )
    return storage, character, reference, output


def test_matching_face_reads_as_consistent(tmp_path, monkeypatch):
    storage, _character, reference, output = _setup(tmp_path, monkeypatch)
    adapter = _StubAdapter({"reference": [1.0, 0.0], "output": [1.0, 0.0]})

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output), storage=storage, embedding_adapter=adapter
    )

    assert report["status"] == "consistent"
    assert report["measures_identity"] is True


def test_different_face_reads_as_drift(tmp_path, monkeypatch):
    storage, _character, reference, output = _setup(tmp_path, monkeypatch)
    adapter = _StubAdapter({"reference": [1.0, 0.0], "output": [0.0, 1.0]})

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output), storage=storage, embedding_adapter=adapter
    )

    assert report["status"] == "identity_drift"
    assert report["characters"][0]["similarity"] == pytest.approx(0.0)


def test_unavailable_embedder_reports_unavailable_not_drift(tmp_path, monkeypatch):
    """The bug this replaces: an unconfigured embedder used to look like drift."""
    storage, _character, _reference, output = _setup(tmp_path, monkeypatch)

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output),
        storage=storage,
        embedding_adapter=UnavailableVisualEmbeddingAdapter(),
    )

    assert report["status"] == "unavailable"
    assert report["status"] != "identity_drift"


def test_general_visual_embedding_does_not_claim_to_measure_identity(tmp_path, monkeypatch):
    storage, _character, _reference, output = _setup(tmp_path, monkeypatch)
    adapter = _StubAdapter({"reference": [1.0, 0.0], "output": [1.0, 0.0]})
    adapter.kind = EMBEDDING_KIND_VISUAL

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output), storage=storage, embedding_adapter=adapter
    )

    assert report["embedding_kind"] == EMBEDDING_KIND_VISUAL
    assert report["measures_identity"] is False


def test_first_appearance_is_not_applicable_rather_than_a_failure(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path / "db"))
    storage.save_character("proj-verify", "Maya", {})
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        lambda project_id: {
            "project_id": project_id,
            "execution_summary": {"scenes": [{"scene_id": "scene_001", "characters": ["Maya"]}]},
        },
    )
    output = tmp_path / "output.jpg"
    output.write_bytes(b"out")
    adapter = _StubAdapter({"output": [1.0, 0.0]})

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output), storage=storage, embedding_adapter=adapter
    )

    assert report["status"] == "not_applicable"
    assert report["reason"] == "no_comparable_locked_reference"


def test_reference_from_the_same_job_is_not_compared_against_itself(tmp_path, monkeypatch):
    storage, character, _reference, output = _setup(tmp_path, monkeypatch)
    # Re-point the existing lock at this very job.
    row = storage.get_character_reference_lock("proj-verify", character["id"], "locked", "general")
    row["source_job_id"] = "job-verify-1"
    storage.save_character_reference_lock(row)

    adapter = _StubAdapter({"reference": [1.0, 0.0], "output": [1.0, 0.0]})
    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output), storage=storage, embedding_adapter=adapter
    )

    assert report["status"] == "not_applicable"


def test_incomplete_render_is_not_verified(tmp_path, monkeypatch):
    storage, _character, _reference, output = _setup(tmp_path, monkeypatch)
    job = _job_with_frame(output)
    job.status = "running"

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=job, storage=storage, embedding_adapter=_StubAdapter({})
    )

    assert report["status"] == "not_applicable"
    assert report["reason"] == "render_not_complete"


def test_remote_only_reference_is_skipped_without_crashing(tmp_path, monkeypatch):
    storage, character, _reference, output = _setup(tmp_path, monkeypatch)
    row = storage.get_character_reference_lock("proj-verify", character["id"], "locked", "general")
    row["image_url"] = "https://cdn.example.test/remote.jpg"
    storage.save_character_reference_lock(row)

    report = CharacterVisualReferenceService().verify_shot_identity(
        job=_job_with_frame(output),
        storage=storage,
        embedding_adapter=_StubAdapter({"output": [1.0, 0.0]}),
    )

    assert report["status"] == "not_applicable"
