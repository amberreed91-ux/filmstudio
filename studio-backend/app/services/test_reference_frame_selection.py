"""Tests for candidate-frame scoring when locking a character reference.

The lock is durable — it conditions every later shot for that character — so the
frame chosen matters more than almost anything else in the consistency path. The
previous implementation preferred the provider thumbnail (usually frame 0) and
otherwise grabbed a hardcoded 00:00:01.
"""

from pathlib import Path

import pytest

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.character_visual_reference_service import CharacterVisualReferenceService


def _job(*, asset_url: str = "", thumbnail_url: str = "") -> RenderJobModel:
    return RenderJobModel(
        id="job-frame-test",
        project_id="proj-frame",
        shot_id="scene_001_shot_001",
        provider="happyhorse",
        status="complete",
        input_payload=RenderJobInput(shot_id="scene_001_shot_001", prompt="Maya turns."),
        output_payload=RenderJobOutput(
            asset_url=asset_url,
            thumbnail_url=thumbnail_url,
            metadata={},
        ),
        created_at="2026-08-15T00:00:00",
        updated_at="2026-08-15T00:00:00",
        completed_at="2026-08-15T00:00:00",
    )


# ── candidate timestamp selection ────────────────────────────────────────────


def test_candidates_avoid_the_head_and_tail_of_the_clip():
    stamps = CharacterVisualReferenceService._candidate_timestamps(10.0)

    assert stamps
    # Fade-ups live at the head, provider tail artifacts at the end.
    assert min(stamps) >= 10.0 * CharacterVisualReferenceService.REFERENCE_SAMPLE_START_RATIO - 1e-9
    assert max(stamps) <= 10.0 * CharacterVisualReferenceService.REFERENCE_SAMPLE_END_RATIO + 1e-9


def test_candidate_count_matches_configuration():
    stamps = CharacterVisualReferenceService._candidate_timestamps(10.0)
    assert len(stamps) == CharacterVisualReferenceService.REFERENCE_CANDIDATE_COUNT


def test_candidates_are_distinct_and_ordered():
    stamps = CharacterVisualReferenceService._candidate_timestamps(10.0)
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_unknown_duration_falls_back_to_a_safe_spread():
    assert CharacterVisualReferenceService._candidate_timestamps(None) == [1.0, 0.5, 1.5]
    assert CharacterVisualReferenceService._candidate_timestamps(0) == [1.0, 0.5, 1.5]


def test_short_clip_still_yields_in_range_candidates():
    stamps = CharacterVisualReferenceService._candidate_timestamps(1.5)
    assert stamps
    assert all(0.0 <= stamp <= 1.5 for stamp in stamps)


# ── frame scoring ────────────────────────────────────────────────────────────


def _write_image(path: Path, builder) -> Path:
    Image = pytest.importorskip("PIL.Image")
    image = builder(Image)
    image.save(path)
    return path


def test_black_frame_is_rejected(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    path = tmp_path / "black.jpg"
    Image.new("RGB", (64, 64), (0, 0, 0)).save(path)

    assert CharacterVisualReferenceService._score_candidate_frame(path) == 0.0


def test_blown_out_frame_is_rejected(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    path = tmp_path / "white.jpg"
    Image.new("RGB", (64, 64), (255, 255, 255)).save(path)

    assert CharacterVisualReferenceService._score_candidate_frame(path) == 0.0


def test_sharp_frame_outscores_flat_frame(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")

    flat_path = tmp_path / "flat.jpg"
    Image.new("RGB", (64, 64), (128, 128, 128)).save(flat_path)

    sharp_path = tmp_path / "sharp.jpg"
    sharp = Image.new("RGB", (64, 64), (128, 128, 128))
    draw = ImageDraw.Draw(sharp)
    for offset in range(0, 64, 6):
        draw.line([(offset, 0), (offset, 64)], fill=(20, 20, 20), width=2)
    sharp.save(sharp_path)

    flat_score = CharacterVisualReferenceService._score_candidate_frame(flat_path)
    sharp_score = CharacterVisualReferenceService._score_candidate_frame(sharp_path)

    assert sharp_score > flat_score


def test_sharp_frame_outscores_blurred_copy_of_itself(tmp_path):
    """The real-world case: a motion-blurred frame must lose to a clean one."""
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFilter = pytest.importorskip("PIL.ImageFilter")

    sharp = Image.new("RGB", (64, 64), (128, 128, 128))
    draw = ImageDraw.Draw(sharp)
    for offset in range(0, 64, 6):
        draw.line([(offset, 0), (offset, 64)], fill=(20, 20, 20), width=2)

    sharp_path = tmp_path / "clean.jpg"
    sharp.save(sharp_path)

    blurred_path = tmp_path / "blurred.jpg"
    sharp.filter(ImageFilter.GaussianBlur(radius=3)).save(blurred_path)

    assert CharacterVisualReferenceService._score_candidate_frame(
        sharp_path
    ) > CharacterVisualReferenceService._score_candidate_frame(blurred_path)


def test_missing_file_scores_zero(tmp_path):
    assert CharacterVisualReferenceService._score_candidate_frame(tmp_path / "nope.jpg") == 0.0


# ── capture ordering ─────────────────────────────────────────────────────────


def test_still_image_output_is_used_directly():
    job = _job(asset_url="https://cdn.example.test/frame.png")
    assert CharacterVisualReferenceService().capture_reference_image(job) == (
        "https://cdn.example.test/frame.png",
        "output_image",
    )


def test_thumbnail_is_used_when_no_local_video_exists():
    # The video path is local-shaped but absent on disk, so scoring cannot run.
    job = _job(
        asset_url="/outputs/renders/proj-frame/job.mp4",
        thumbnail_url="https://cdn.example.test/thumb.jpg",
    )
    assert CharacterVisualReferenceService().capture_reference_image(job) == (
        "https://cdn.example.test/thumb.jpg",
        "thumbnail",
    )


def test_scored_frame_is_preferred_over_the_thumbnail(monkeypatch, tmp_path):
    """Frame 0 is usually the worst frame in the clip, so it must not win by default."""
    video = tmp_path / "job.mp4"
    video.write_bytes(b"not-a-real-video")

    monkeypatch.setattr(
        CharacterVisualReferenceService,
        "_local_output_path",
        staticmethod(lambda asset_url: video),
    )
    monkeypatch.setattr(
        CharacterVisualReferenceService,
        "_extract_frame",
        classmethod(lambda cls, job, path: "/outputs/references/proj-frame/best.jpg"),
    )

    job = _job(
        asset_url="/outputs/renders/proj-frame/job.mp4",
        thumbnail_url="https://cdn.example.test/thumb.jpg",
    )
    assert CharacterVisualReferenceService().capture_reference_image(job) == (
        "/outputs/references/proj-frame/best.jpg",
        "representative_frame",
    )


def test_no_output_payload_returns_none():
    job = _job()
    job.output_payload = None
    assert CharacterVisualReferenceService().capture_reference_image(job) is None


def test_no_asset_and_no_thumbnail_returns_none():
    assert CharacterVisualReferenceService().capture_reference_image(_job()) is None
