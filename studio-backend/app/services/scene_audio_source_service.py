"""Read-only fingerprints for the local recordings consumed by scene assembly."""
from hashlib import sha256
from pathlib import Path

from app.services.stability import PersistenceError, StateError


class SceneAudioSourceService:
    def __init__(self, audio_root: Path):
        self.audio_root = Path(audio_root)

    def supplied_path(self, project_id: str, scene_id: str, shot_id: str) -> Path | None:
        directory = self.audio_root / project_id / scene_id / "pre_supplied"
        for extension in (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"):
            candidate = directory / f"{shot_id}{extension}"
            if not candidate.resolve().is_relative_to(self.audio_root.resolve()):
                raise StateError("Recording is outside the project audio store", stage="scene_audio_inputs")
            if candidate.is_file():
                return candidate
        return None

    def snapshot(self, project_id: str, scene_id: str, shot_ids: list[str]) -> dict:
        result = {}
        for shot_id in shot_ids:
            try:
                source = self.supplied_path(project_id, scene_id, shot_id)
                if source is None:
                    result[shot_id] = None
                    continue
                digest = sha256()
                with source.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
                result[shot_id] = {"filename": source.name, "sha256": digest.hexdigest()}
            except FileNotFoundError as exc:
                raise StateError("Recording changed while checking the cut. Refresh and try again.", stage="scene_audio_inputs", metadata={"shot_id": shot_id}) from exc
            except OSError as exc:
                raise PersistenceError("Could not read the recording for this shot", stage="scene_audio_inputs", metadata={"shot_id": shot_id}) from exc
        return result
