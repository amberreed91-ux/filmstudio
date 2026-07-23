from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import RenderJobModel
from app.models.consistency import CharacterReferenceLock, ConsistencyPayload, ReferenceAsset
from app.services.project_store import project_store
from app.utils.helpers import derive_scene_id_from_shot_id

logger = logging.getLogger("studio-character-visual-reference")


class CharacterVisualReferenceService:
    """Owns character-scoped visual reference locking for render workflows."""

    def resolve_shot_characters(
        self,
        *,
        project_id: str,
        shot_id: str,
        storage: Any,
        prompt: str = "",
    ) -> list[dict[str, Any]]:
        scene_id = derive_scene_id_from_shot_id(shot_id)
        names: list[str] = []

        try:
            project = project_store.get_project(project_id)
            if isinstance(project, dict):
                summary = project.get("execution_summary") or {}
                scenes = summary.get("scenes") or []
                scene = next(
                    (
                        item
                        for item in scenes
                        if isinstance(item, dict) and item.get("scene_id") == scene_id
                    ),
                    None,
                )
                if isinstance(scene, dict):
                    raw_names = scene.get("character_appearances") or scene.get("characters") or []
                    if isinstance(raw_names, list):
                        names = [str(name).strip() for name in raw_names if str(name).strip()]
        except Exception as exc:
            logger.debug("Character scene lookup skipped for %s/%s: %s", project_id, shot_id, exc)

        characters: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for name in names:
            try:
                character = storage.get_character_by_name(project_id, name)
            except Exception:
                character = None
            if character and str(character.get("id") or "").strip() not in seen_ids:
                seen_ids.add(str(character.get("id") or "").strip())
                characters.append(character)

        if characters:
            return characters

        try:
            all_characters = storage.get_characters(project_id)
        except Exception:
            all_characters = []
        prompt_lower = prompt.lower()
        for character in all_characters:
            name = str(character.get("name") or "").strip()
            character_id = str(character.get("id") or "").strip()
            if name and character_id and name.lower() in prompt_lower and character_id not in seen_ids:
                seen_ids.add(character_id)
                characters.append(character)

        return characters

    def build_consistency_payload_for_shot(
        self,
        *,
        project_id: str,
        shot_id: str,
        storage: Any,
        prompt: str = "",
    ) -> ConsistencyPayload | None:
        characters = self.resolve_shot_characters(
            project_id=project_id,
            shot_id=shot_id,
            storage=storage,
            prompt=prompt,
        )
        if not characters:
            return None

        self.ensure_provisional_locks_for_shot(
            project_id=project_id,
            shot_id=shot_id,
            characters=characters,
            storage=storage,
        )

        refs: list[ReferenceAsset] = []
        weights: dict[str, float] = {}
        fallback_text: dict[str, str] = {}

        for character in characters[:9]:
            character_id = str(character.get("id") or "").strip()
            character_name = str(character.get("name") or "").strip()
            if not character_id:
                continue
            lock = self.get_best_reference_lock(storage, project_id, character_id)
            if not lock:
                continue
            lock_status = str(lock.get("lock_status") or "locked").strip()
            ref_id = f"charlock:{character_id}"
            refs.append(
                ReferenceAsset(
                    ref_id=ref_id,
                    kind="character_full",
                    image_url=str(lock.get("image_url") or "").strip(),
                    source_shot_id=lock.get("source_shot_id"),
                    project_id=project_id,
                )
            )
            weights[ref_id] = 1.0
            status_label = (
                "provisional storyboard reference"
                if lock_status == "provisional"
                else "locked reference"
            )
            fallback_text[ref_id] = (
                f"Use {status_label} for {character_name or 'this character'}; "
                "preserve face, silhouette, wardrobe, and visual identity."
            )

        if not refs:
            return None
        return ConsistencyPayload(
            project_id=project_id,
            refs=refs,
            weights=weights,
            mode="identity_lock",
            fallback_text=fallback_text,
        )

    def get_best_reference_lock(
        self,
        storage: Any,
        project_id: str,
        character_id: str,
    ) -> dict[str, Any] | None:
        locked = storage.get_character_reference_lock(project_id, character_id, "locked")
        if locked:
            return locked
        return storage.get_character_reference_lock(project_id, character_id, "provisional")

    def ensure_provisional_locks_for_shot(
        self,
        *,
        project_id: str,
        shot_id: str,
        characters: list[dict[str, Any]],
        storage: Any,
    ) -> list[CharacterReferenceLock]:
        storyboard = self.find_storyboard_reference_for_shot(
            project_id=project_id,
            shot_id=shot_id,
            storage=storage,
        )
        if not storyboard:
            return []

        created: list[CharacterReferenceLock] = []
        now = datetime.now().isoformat()
        for character in characters:
            character_id = str(character.get("id") or "").strip()
            if not character_id:
                continue
            if self.get_best_reference_lock(storage, project_id, character_id):
                continue
            lock = CharacterReferenceLock(
                lock_id=f"charlock_{uuid4().hex[:12]}",
                project_id=project_id,
                character_id=character_id,
                character_name=str(character.get("name") or "").strip(),
                source_shot_id=shot_id,
                image_url=storyboard,
                lock_status="provisional",
                provider="qwen-image-max",
                capture_method="storyboard",
                created_at=now,
                updated_at=now,
            )
            saved = storage.save_character_reference_lock(lock.model_dump(mode="json"))
            if saved:
                created.append(CharacterReferenceLock(**saved))

        if created:
            logger.info(
                "CHARACTER_REFERENCE_PROVISIONAL_LOCKED | project=%s | shot=%s | locks=%d",
                project_id,
                shot_id,
                len(created),
            )
        return created

    def find_storyboard_reference_for_shot(
        self,
        *,
        project_id: str,
        shot_id: str,
        storage: Any,
    ) -> str | None:
        scene_id = derive_scene_id_from_shot_id(shot_id)
        try:
            rows = storage.load_previs_images(project_id, scene_id)
        except Exception as exc:
            logger.debug("Storyboard reference lookup skipped for %s/%s: %s", project_id, shot_id, exc)
            return None

        for row in rows:
            if str(row.get("shot_id") or "").strip() != shot_id:
                continue
            if str(row.get("status") or "").strip() != "complete":
                continue
            if bool(row.get("fallback")):
                continue
            image_path = str(row.get("image_path") or "").strip()
            if image_path:
                return image_path
        return None

    def capture_reference_image(self, job: RenderJobModel) -> tuple[str, str] | None:
        if not job.output_payload:
            return None

        thumbnail_url = str(job.output_payload.thumbnail_url or "").strip()
        if thumbnail_url:
            return thumbnail_url, "thumbnail"

        asset_url = str(job.output_payload.asset_url or "").strip()
        if not asset_url:
            return None
        if asset_url.lower().split("?", 1)[0].endswith((".png", ".jpg", ".jpeg", ".webp")):
            return asset_url, "output_image"

        local_path = self._local_output_path(asset_url)
        if local_path and local_path.exists() and local_path.suffix.lower() in {".mp4", ".mov", ".webm"}:
            frame_url = self._extract_frame(job, local_path)
            if frame_url:
                return frame_url, "representative_frame"

        return asset_url, "output_url_fallback"

    def lock_first_references_for_completed_job(
        self,
        *,
        job: RenderJobModel,
        storage: Any,
    ) -> list[CharacterReferenceLock]:
        if job.status != "complete":
            return []
        captured = self.capture_reference_image(job)
        if not captured:
            return []
        image_url, capture_method = captured
        characters = self.resolve_shot_characters(
            project_id=job.project_id,
            shot_id=job.shot_id,
            storage=storage,
            prompt=(job.input_payload.prompt if job.input_payload else "") or "",
        )

        locked: list[CharacterReferenceLock] = []
        now = datetime.now().isoformat()
        for character in characters:
            character_id = str(character.get("id") or "").strip()
            if not character_id:
                continue
            existing_locked = storage.get_character_reference_lock(job.project_id, character_id, "locked")
            if existing_locked:
                continue
            existing_provisional = storage.get_character_reference_lock(
                job.project_id,
                character_id,
                "provisional",
            )
            if not self.should_promote_completed_job(job):
                if existing_provisional:
                    logger.info(
                        "CHARACTER_REFERENCE_PROVISIONAL_RETAINED | project=%s | shot=%s | character=%s",
                        job.project_id,
                        job.shot_id,
                        character_id,
                    )
                continue
            if existing_provisional:
                superseded = dict(existing_provisional)
                superseded["lock_status"] = "superseded"
                superseded["updated_at"] = now
                storage.save_character_reference_lock(superseded)
            lock = CharacterReferenceLock(
                lock_id=f"charlock_{uuid4().hex[:12]}",
                project_id=job.project_id,
                character_id=character_id,
                character_name=str(character.get("name") or "").strip(),
                source_shot_id=job.shot_id,
                image_url=image_url,
                lock_status="locked",
                provider=job.provider,
                capture_method=capture_method,
                created_at=now,
                updated_at=now,
            )
            saved = storage.save_character_reference_lock(lock.model_dump(mode="json"))
            if saved:
                locked.append(CharacterReferenceLock(**saved))

        if locked:
            logger.info(
                "CHARACTER_REFERENCE_LOCKED | project=%s | shot=%s | locks=%d",
                job.project_id,
                job.shot_id,
                len(locked),
            )
        return locked

    @staticmethod
    def should_promote_completed_job(job: RenderJobModel) -> bool:
        metadata = job.metadata if isinstance(job.metadata, dict) else {}
        review = metadata.get("adherence_review")
        if not isinstance(review, dict):
            return True

        verdict = str(review.get("verdict") or "").strip().lower()
        outcome = str(review.get("outcome") or "").strip().lower()
        failed_slots = review.get("failed_slots")
        if isinstance(failed_slots, list) and failed_slots:
            return False
        if verdict and verdict not in {"pass", "passed", "ok"}:
            return False
        if outcome and outcome not in {"pass", "passed", "accepted", "ok"}:
            return False
        return True

    @staticmethod
    def _local_output_path(asset_url: str) -> Path | None:
        if not asset_url.startswith("/outputs/"):
            return None
        backend_root = Path(__file__).resolve().parents[2]
        return backend_root / asset_url.lstrip("/")

    @staticmethod
    def _extract_frame(job: RenderJobModel, video_path: Path) -> str | None:
        output_dir = Path(__file__).resolve().parents[2] / "outputs" / "references" / job.project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_job_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in job.id)
        frame_path = output_dir / f"{safe_job_id}_{job.shot_id}_reference.jpg"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if result.returncode != 0:
                logger.debug("Reference frame extraction failed: %s", result.stderr[-500:])
                return None
        except Exception as exc:
            logger.debug("Reference frame extraction skipped: %s", exc)
            return None
        return f"/outputs/references/{job.project_id}/{frame_path.name}"


character_visual_reference_service = CharacterVisualReferenceService()
