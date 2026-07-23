from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from app.services.short_film_stitching_service import (
    EndCardConfig,
    ShortFilmStitchingService,
    SoundtrackConfig,
    TitleCardConfig,
)


def _run_media_cmd(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "media command failed").strip()[:1000])


def _generate_tone_video(path: Path, *, video_duration: float, frequency: int) -> None:
    _run_media_cmd(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x202838:s=320x180:d={video_duration}:r=24",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=8000:duration={video_duration}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )


def _generate_tone_wav(path: Path, *, duration: float, frequency: int) -> None:
    _run_media_cmd(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=8000:duration={duration}",
            "-ac",
            "1",
            str(path),
        ]
    )


def _extract_wav(media_path: Path, wav_path: Path) -> None:
    _run_media_cmd(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "wav",
            str(wav_path),
        ]
    )


def _goertzel_magnitude(samples: list[float], sample_rate: int, target_frequency: float) -> float:
    normalized_frequency = target_frequency / sample_rate
    coeff = 2.0 * math.cos(2.0 * math.pi * normalized_frequency)
    prev = 0.0
    prev2 = 0.0
    for sample in samples:
        current = sample + (coeff * prev) - prev2
        prev2 = prev
        prev = current
    power = (prev2 * prev2) + (prev * prev) - (coeff * prev * prev2)
    return math.sqrt(max(power, 0.0)) / max(len(samples), 1)


def _frequency_magnitude(media_path: Path, frequency: float) -> float:
    wav_path = media_path.with_suffix(".analysis.wav")
    _extract_wav(media_path, wav_path)
    with wave.open(str(wav_path), "rb") as wav:
        sample_rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    samples = [
        int.from_bytes(raw[index:index + 2], byteorder="little", signed=True) / 32768.0
        for index in range(0, len(raw), 2)
    ]
    return _goertzel_magnitude(samples, sample_rate, frequency)


def _project_with_outputs() -> dict:
    return {
        "project_id": "project_test",
        "execution_summary": {
            "scenes": [{"scene_id": "scene_001"}, {"scene_id": "scene_002"}],
            "one_button_render_jobs": [
                {
                    "scene_id": "scene_002",
                    "shot_id": "scene_002_shot_001",
                    "status": "complete",
                    "output_url": "https://example.com/two.mp4",
                    "job_id": "job-2",
                },
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_001",
                    "status": "complete",
                    "output_url": "https://example.com/one.mp4",
                    "job_id": "job-1",
                },
            ],
        },
    }


def test_collects_completed_outputs_in_scene_order():
    service = ShortFilmStitchingService()
    clips = service.collect_completed_project_outputs(_project_with_outputs())
    assert len(clips) == 2
    assert clips[0]["scene_id"] == "scene_001"
    assert clips[1]["scene_id"] == "scene_002"


def test_collects_completed_scene_outputs_in_shot_order():
    service = ShortFilmStitchingService()
    project = {
        "execution_summary": {
            "scenes": [{"scene_id": "scene_001"}, {"scene_id": "scene_002"}],
            "one_button_render_jobs": [
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_002",
                    "status": "complete",
                    "output_url": "https://example.com/one-b.mp4",
                    "job_id": "job-1b",
                },
                {
                    "scene_id": "scene_002",
                    "shot_id": "scene_002_shot_001",
                    "status": "complete",
                    "output_url": "https://example.com/two.mp4",
                    "job_id": "job-2",
                },
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_001",
                    "status": "complete",
                    "output_url": "https://example.com/one-a.mp4",
                    "job_id": "job-1a",
                },
            ],
        }
    }

    clips = service.collect_completed_scene_outputs(project, "scene_001")

    assert [clip["shot_id"] for clip in clips] == ["scene_001_shot_001", "scene_001_shot_002"]
    assert [clip["output_url"] for clip in clips] == [
        "https://example.com/one-a.mp4",
        "https://example.com/one-b.mp4",
    ]


def test_download_or_stream_clips_accepts_local_outputs_url(tmp_path: Path):
    outputs_root = tmp_path / "outputs"
    source = outputs_root / "renders" / "shot_001.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"local-video")
    service = ShortFilmStitchingService(outputs_root=outputs_root)

    files = service.download_or_stream_clips_safely(
        [{"output_url": "/outputs/renders/shot_001.mp4"}],
        tmp_path / "work",
    )

    assert len(files) == 1
    assert files[0].read_bytes() == b"local-video"


def test_download_or_stream_clips_accepts_file_url(tmp_path: Path):
    source = tmp_path / "shot_001.mp4"
    source.write_bytes(b"file-url-video")
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")

    files = service.download_or_stream_clips_safely(
        [{"output_url": source.as_uri()}],
        tmp_path / "work",
    )

    assert len(files) == 1
    assert files[0].read_bytes() == b"file-url-video"


def test_rejects_project_with_no_completed_outputs(tmp_path: Path):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    project = {"project_id": "project_test", "execution_summary": {"one_button_render_jobs": []}}
    result = service.stitch_project("project_test", project, overwrite=False)
    assert result["status"] == "failed"
    assert result["blocker"] == "no_completed_outputs"


def test_ffmpeg_missing_returns_blocker(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    monkeypatch.setattr("app.services.short_film_stitching_service.shutil_which", lambda _name: None)

    def _fake_download(_clips, work_dir):
        first = work_dir / "clip_001.mp4"
        first.write_bytes(b"fake")
        return [first]

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    result = service.stitch_project("project_test", _project_with_outputs(), overwrite=True)
    assert result["status"] == "failed"
    assert result["blocker"] == "ffmpeg_missing"


def test_existing_stitched_output_returns_existing_url(tmp_path: Path):
    outputs_root = tmp_path / "outputs"
    target = outputs_root / "final_films" / "project_test_sandbox_short.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"existing-data")
    service = ShortFilmStitchingService(outputs_root=outputs_root)
    result = service.stitch_project("project_test", _project_with_outputs(), overwrite=False)
    assert result["status"] == "existing"
    assert result["output_url"] == "/outputs/final_films/project_test_sandbox_short.mp4"


def test_simulated_asset_urls_create_local_clip_without_network(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")

    def _no_network(*_args, **_kwargs):
        raise AssertionError("simulated assets should not be downloaded")

    def _fake_simulated_clip(target: Path, _index: int):
        target.write_bytes(b"mock-video")
        return target

    monkeypatch.setattr("app.services.short_film_stitching_service.urllib.request.urlopen", _no_network)
    monkeypatch.setattr(service, "generate_simulated_video_clip", _fake_simulated_clip)

    files = service.download_or_stream_clips_safely(
        [{"output_url": "https://storage.example.com/assets/job-123.mp4"}],
        tmp_path,
    )

    assert len(files) == 1
    assert files[0].read_bytes() == b"mock-video"


def test_title_card_enabled(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    captured = {"concat": ""}

    def _fake_download(_clips, work_dir):
        a = work_dir / "clip_001.mp4"
        b = work_dir / "clip_002.mp4"
        a.write_bytes(b"a")
        b.write_bytes(b"b")
        return [a, b]

    def _fake_title(work_dir, _config):
        title = work_dir / "title_card.mp4"
        title.write_bytes(b"title")
        return title

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        captured["concat"] = concat_list_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"ok")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "generate_title_card_frame", _fake_title)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    result = service.stitch_project_with_cards(
        "project_test",
        _project_with_outputs(),
        overwrite=True,
        title_card_config=TitleCardConfig(enabled=True, title_text="Neon Rain"),
        end_card_config=EndCardConfig(enabled=False),
    )
    assert result["status"] == "completed"
    first_line = captured["concat"].splitlines()[0]
    assert "title_card.mp4" in first_line


def test_end_card_enabled(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    captured = {"concat": ""}

    def _fake_download(_clips, work_dir):
        clip = work_dir / "clip_001.mp4"
        clip.write_bytes(b"clip")
        return [clip]

    def _fake_end(work_dir, _config):
        end = work_dir / "end_card.mp4"
        end.write_bytes(b"end")
        return end

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        captured["concat"] = concat_list_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"ok")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "generate_end_card_frame", _fake_end)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    result = service.stitch_project_with_cards(
        "project_test",
        _project_with_outputs(),
        overwrite=True,
        title_card_config=TitleCardConfig(enabled=False),
        end_card_config=EndCardConfig(enabled=True, text="END"),
    )
    assert result["status"] == "completed"
    assert "end_card.mp4" in captured["concat"].splitlines()[-1]


def test_title_and_end_ordering(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    captured = {"concat": ""}

    def _fake_download(_clips, work_dir):
        c1 = work_dir / "clip_001.mp4"
        c2 = work_dir / "clip_002.mp4"
        c1.write_bytes(b"1")
        c2.write_bytes(b"2")
        return [c1, c2]

    def _fake_title(work_dir, _config):
        p = work_dir / "title_card.mp4"
        p.write_bytes(b"t")
        return p

    def _fake_end(work_dir, _config):
        p = work_dir / "end_card.mp4"
        p.write_bytes(b"e")
        return p

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        captured["concat"] = concat_list_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"ok")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "generate_title_card_frame", _fake_title)
    monkeypatch.setattr(service, "generate_end_card_frame", _fake_end)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    result = service.stitch_project_with_cards(
        "project_test",
        _project_with_outputs(),
        overwrite=True,
        title_card_config=TitleCardConfig(enabled=True, title_text="N"),
        end_card_config=EndCardConfig(enabled=True, text="E"),
    )
    assert result["status"] == "completed"
    lines = captured["concat"].splitlines()
    assert "title_card.mp4" in lines[0]
    assert "clip_001.mp4" in lines[1]
    assert "clip_002.mp4" in lines[2]
    assert "end_card.mp4" in lines[3]


def test_stitch_without_cards_unchanged(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    captured = {"concat": ""}

    def _fake_download(_clips, work_dir):
        c1 = work_dir / "clip_001.mp4"
        c2 = work_dir / "clip_002.mp4"
        c1.write_bytes(b"1")
        c2.write_bytes(b"2")
        return [c1, c2]

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        captured["concat"] = concat_list_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"ok")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    result = service.stitch_project("project_test", _project_with_outputs(), overwrite=True)
    assert result["status"] == "completed"
    lines = captured["concat"].splitlines()
    assert len(lines) == 2
    assert "clip_001.mp4" in lines[0]
    assert "clip_002.mp4" in lines[1]


def test_stitch_scene_uses_only_requested_scene_clips(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    captured = {"clips": [], "concat": ""}
    project = {
        "execution_summary": {
            "scenes": [{"scene_id": "scene_001"}, {"scene_id": "scene_002"}],
            "one_button_render_jobs": [
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_001",
                    "status": "complete",
                    "output_url": "https://example.com/one-a.mp4",
                    "job_id": "job-1a",
                },
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_002",
                    "status": "complete",
                    "output_url": "https://example.com/one-b.mp4",
                    "job_id": "job-1b",
                },
                {
                    "scene_id": "scene_002",
                    "shot_id": "scene_002_shot_001",
                    "status": "complete",
                    "output_url": "https://example.com/two.mp4",
                    "job_id": "job-2",
                },
            ],
        }
    }

    def _fake_download(clips, work_dir):
        captured["clips"] = clips
        paths = []
        for index, _clip in enumerate(clips, start=1):
            path = work_dir / f"clip_{index:03d}.mp4"
            path.write_bytes(f"clip-{index}".encode("utf-8"))
            paths.append(path)
        return paths

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        captured["concat"] = concat_list_path.read_text(encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"scene")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)

    result = service.stitch_scene("project_test", "scene_001", project, overwrite=True)

    assert result["status"] == "completed"
    assert result["scene_id"] == "scene_001"
    assert result["shot_ids"] == ["scene_001_shot_001", "scene_001_shot_002"]
    assert [clip["scene_id"] for clip in captured["clips"]] == ["scene_001", "scene_001"]
    assert len(captured["concat"].splitlines()) == 2
    assert result["output_url"].endswith("/project_test_scene_001.mp4")


def test_stitch_scene_can_mix_scene_level_soundtrack(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")

    def _fake_download(_clips, work_dir):
        clip = work_dir / "clip_001.mp4"
        clip.write_bytes(b"clip")
        return [clip]

    def _fake_stitch(_concat_list_path, output_path, transcode=False):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        return {"status": "completed"}

    def _fake_placeholder(work_dir, _duration):
        audio = work_dir / "score.wav"
        audio.write_bytes(b"score")
        return audio

    def _fake_mix(video_path, audio_path, output_path, soundtrack_config, video_duration_seconds):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video+score")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    monkeypatch.setattr(service, "create_placeholder_audio", _fake_placeholder)
    monkeypatch.setattr(service, "mix_audio_into_video", _fake_mix)
    monkeypatch.setattr(service, "_probe_has_audio_stream", lambda _p: True)

    result = service.stitch_scene(
        "project_test",
        "scene_001",
        _project_with_outputs(),
        overwrite=True,
        soundtrack_config=SoundtrackConfig(enabled=True, audio_source_type="generated_placeholder"),
    )

    assert result["status"] == "completed"
    assert result["output_url"].endswith("/project_test_scene_001_with_audio.mp4")


def test_soundtrack_disabled_leaves_behavior_unchanged(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")

    def _fake_download(_clips, work_dir):
        c1 = work_dir / "clip_001.mp4"
        c1.write_bytes(b"1")
        return [c1]

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        return {"status": "completed"}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    result = service.stitch_project_with_cards(
        "project_test",
        _project_with_outputs(),
        overwrite=True,
        title_card_config=TitleCardConfig(enabled=False),
        end_card_config=EndCardConfig(enabled=False),
        soundtrack_config=SoundtrackConfig(enabled=False),
    )
    assert result["status"] == "completed"
    assert result["output_url"].endswith("/project_test_sandbox_short.mp4")


def test_placeholder_soundtrack_creates_output(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")

    def _fake_download(_clips, work_dir):
        c1 = work_dir / "clip_001.mp4"
        c1.write_bytes(b"1")
        return [c1]

    def _fake_stitch(concat_list_path, output_path, transcode=False):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        return {"status": "completed"}

    def _fake_placeholder(work_dir, _duration):
        p = work_dir / "placeholder.wav"
        p.write_bytes(b"audio")
        return p

    def _fake_mix(video_path, audio_path, output_path, soundtrack_config, video_duration_seconds):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video+audio")
        return {"status": "completed", "command": ["ffmpeg"]}

    monkeypatch.setattr(service, "download_or_stream_clips_safely", _fake_download)
    monkeypatch.setattr(service, "stitch_clips", _fake_stitch)
    monkeypatch.setattr(service, "create_placeholder_audio", _fake_placeholder)
    monkeypatch.setattr(service, "mix_audio_into_video", _fake_mix)
    monkeypatch.setattr(service, "_probe_has_audio_stream", lambda _p: True)

    result = service.stitch_project_with_cards(
        "project_test",
        _project_with_outputs(),
        overwrite=True,
        soundtrack_config=SoundtrackConfig(enabled=True, audio_source_type="generated_placeholder"),
    )
    assert result["status"] == "completed"
    assert result["output_url"].endswith("/project_test_sandbox_short_with_audio.mp4")


def test_volume_fade_settings_included_in_ffmpeg_command(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    out = tmp_path / "out.mp4"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    captured = {"cmd": []}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, capture_output=True, text=True):
        captured["cmd"] = cmd
        out.write_bytes(b"va")
        return _Proc()

    monkeypatch.setattr("app.services.short_film_stitching_service.subprocess.run", _fake_run)
    monkeypatch.setattr("app.services.short_film_stitching_service.shutil_which", lambda _name: "ffmpeg")
    monkeypatch.setattr(service, "_probe_has_audio_stream", lambda _path: True)

    cfg = SoundtrackConfig(
        enabled=True,
        audio_source_type="generated_placeholder",
        volume=0.4,
        fade_in_seconds=2.0,
        fade_out_seconds=3.0,
        loop_to_duration=True,
    )
    result = service.mix_audio_into_video(video, audio, out, cfg, video_duration_seconds=10.0)
    assert result["status"] == "completed"
    cmd_text = " ".join(captured["cmd"])
    assert "volume=0.4" in cmd_text
    assert "afade=t=in:st=0:d=2.0" in cmd_text
    assert "afade=t=out:st=7.0:d=3.0" in cmd_text
    assert "amix=inputs=2:duration=first:dropout_transition=0" in cmd_text
    assert "[0:a:0][bgm]" in cmd_text
    assert "[aout]" in captured["cmd"]


def test_soundtrack_mix_uses_bgm_only_when_video_has_no_audio(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    out = tmp_path / "out.mp4"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    captured = {"cmd": []}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, capture_output=True, text=True):
        captured["cmd"] = cmd
        out.write_bytes(b"va")
        return _Proc()

    monkeypatch.setattr("app.services.short_film_stitching_service.subprocess.run", _fake_run)
    monkeypatch.setattr("app.services.short_film_stitching_service.shutil_which", lambda _name: "ffmpeg")
    monkeypatch.setattr(service, "_probe_has_audio_stream", lambda _path: False)

    result = service.mix_audio_into_video(
        video,
        audio,
        out,
        SoundtrackConfig(enabled=True, audio_source_type="local_file", volume=0.2),
        video_duration_seconds=4.0,
    )

    assert result["status"] == "completed"
    cmd_text = " ".join(captured["cmd"])
    assert "amix=inputs=2" not in cmd_text
    assert "[bgm]" in captured["cmd"]


def test_soundtrack_mix_preserves_existing_dialogue_audio_with_real_media(tmp_path: Path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe required for media-level mix regression")

    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    video = tmp_path / "dialogue_video.mp4"
    soundtrack = tmp_path / "manual_score.wav"
    output = tmp_path / "mixed.mp4"
    _generate_tone_video(video, video_duration=2.0, frequency=440)
    _generate_tone_wav(soundtrack, duration=2.0, frequency=196)

    result = service.mix_audio_into_video(
        video,
        soundtrack,
        output,
        SoundtrackConfig(
            enabled=True,
            audio_source_type="local_file",
            volume=0.8,
            fade_in_seconds=0.0,
            fade_out_seconds=0.0,
            loop_to_duration=False,
        ),
        video_duration_seconds=2.0,
    )

    assert result["status"] == "completed"
    assert _frequency_magnitude(output, 440.0) > 0.005
    assert _frequency_magnitude(output, 196.0) > 0.003


def test_missing_audio_source_returns_blocker(tmp_path: Path):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    _, blocker = service.validate_audio_source(
        work_dir=tmp_path,
        soundtrack_config=SoundtrackConfig(enabled=True, audio_source_type="local_file", local_audio_path="", audio_url=""),
        video_duration_seconds=10.0,
    )
    assert blocker == "missing_audio_source"


def test_final_output_validates_audio_stream(tmp_path: Path, monkeypatch):
    service = ShortFilmStitchingService(outputs_root=tmp_path / "outputs")
    out = tmp_path / "mix.mp4"
    out.write_bytes(b"fake")
    monkeypatch.setattr(service, "_probe_has_audio_stream", lambda _p: True)
    result = service.validate_final_audio_video_output(out)
    assert result["valid"] is True
