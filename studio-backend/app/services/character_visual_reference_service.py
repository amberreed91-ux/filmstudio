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

    # happyhorse-1.1-r2v accepts up to 9 reference images per request.
    MAX_PROVIDER_REFERENCES = 9
    # Per character, so one character in a crowded shot cannot consume the whole
    # budget and leave the others unreferenced.
    MAX_REFERENCES_PER_CHARACTER = 3

    # Prominence weighting. Previously every reference carried 1.0, so a
    # character standing out of focus in the background pulled exactly as hard
    # as the subject of a close-up.
    SUBJECT_PROMINENCE = 1.0
    SECONDARY_PROMINENCE = 0.75
    BACKGROUND_PROMINENCE = 0.45

    # Role weighting: a face crop is stronger identity evidence than a wide
    # full-body frame, and an alternate angle is supporting rather than primary.
    ROLE_WEIGHTS = {
        "face": 1.0,
        "general": 0.9,
        "wardrobe": 0.8,
        "alternate_angle": 0.7,
        "full_body": 0.65,
        "temporary_state": 0.6,
    }

    @classmethod
    def prominence_by_character(
        cls,
        characters: list[dict[str, Any]],
        prompt: str = "",
    ) -> dict[str, float]:
        """Rank characters by how central they are to this shot.

        The render prompt is assembled subject-first (character_state leads, and
        within it the shot's subject is named first), so position of a character's
        name in the prompt is a usable prominence signal. Characters not named in
        the prompt at all fall back to the resolved order, then to background.
        """
        ranked: list[tuple[int, str]] = []
        haystack = str(prompt or "")
        for index, character in enumerate(characters):
            character_id = str(character.get("id") or "").strip()
            name = str(character.get("name") or "").strip()
            if not character_id:
                continue
            position = haystack.find(name) if name and haystack else -1
            # Unnamed characters sort after every named one, preserving resolved
            # order among themselves.
            sort_key = position if position >= 0 else len(haystack) + index
            ranked.append((sort_key, character_id))

        ranked.sort(key=lambda item: item[0])
        weights: dict[str, float] = {}
        for rank, (_, character_id) in enumerate(ranked):
            if rank == 0:
                weights[character_id] = cls.SUBJECT_PROMINENCE
            elif rank == 1:
                weights[character_id] = cls.SECONDARY_PROMINENCE
            else:
                weights[character_id] = cls.BACKGROUND_PROMINENCE
        return weights

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

        prominence = self.prominence_by_character(characters, prompt)

        for character in characters:
            if len(refs) >= self.MAX_PROVIDER_REFERENCES:
                break
            character_id = str(character.get("id") or "").strip()
            character_name = str(character.get("name") or "").strip()
            if not character_id:
                continue
            locks = self.get_reference_locks_for_character(storage, project_id, character_id)
            if not locks:
                continue

            character_weight = prominence.get(character_id, self.BACKGROUND_PROMINENCE)
            for lock in locks[: self.MAX_REFERENCES_PER_CHARACTER]:
                if len(refs) >= self.MAX_PROVIDER_REFERENCES:
                    break
                image_url = str(lock.get("image_url") or "").strip()
                if not image_url:
                    continue
                lock_status = str(lock.get("lock_status") or "locked").strip()
                role = str(lock.get("reference_role") or "general").strip()
                ref_id = f"charlock:{character_id}:{role}"
                refs.append(
                    ReferenceAsset(
                        ref_id=ref_id,
                        kind="character_face" if role == "face" else "character_full",
                        image_url=image_url,
                        source_shot_id=lock.get("source_shot_id"),
                        project_id=project_id,
                    )
                )
                # Prominence × role: the shot's subject should pull harder than a
                # character standing out of focus behind them, and a face crop is
                # stronger identity evidence than a wide full-body frame.
                weights[ref_id] = round(
                    character_weight * self.ROLE_WEIGHTS.get(role, self.ROLE_WEIGHTS["general"]),
                    4,
                )
                status_label = (
                    "provisional storyboard reference"
                    if lock_status == "provisional"
                    else "locked reference"
                )
                reliability = str(
                    lock.get("reliability") or ("medium" if lock_status == "provisional" else "high")
                )
                source_shot = str(lock.get("source_shot_id") or "").strip()
                role_label = "" if role == "general" else f" ({role.replace('_', ' ')} view)"
                fallback_text[ref_id] = (
                    f"Use {status_label}{role_label} for {character_name or 'this character'}; "
                    "preserve fixed identity (face, body, silhouette, skin tone, age presentation) "
                    "and preserve changeable appearance (hair, wardrobe, accessories, temporary marks) unless this shot explicitly changes them. "
                    f"Reference reliability: {reliability}; source shot: {source_shot or 'unknown'}."
                )

        if not refs:
            return self._build_confirmed_reference_asset_payload(
                project_id=project_id,
                storage=storage,
                characters=characters,
            )
        return ConsistencyPayload(
            project_id=project_id,
            refs=refs,
            weights=weights,
            mode="identity_lock",
            fallback_text=fallback_text,
        )

    def _build_confirmed_reference_asset_payload(
        self,
        *,
        project_id: str,
        storage: Any,
        characters: list[dict[str, Any]],
    ) -> ConsistencyPayload | None:
        """Fallback to confirmed project references for shots with resolved cast.

        Character reference locks are the strongest source, but some projects
        already have confirmed reference_assets rows before the first completed
        render is approved. Use those only when the shot has resolved characters;
        otherwise broad project references would leak into unrelated shots.
        """
        if not characters or not hasattr(storage, "list_reference_assets"):
            return None
        try:
            raw_refs = storage.list_reference_assets(project_id=project_id, limit=12)
        except Exception as exc:
            logger.debug("Confirmed reference asset lookup skipped for %s: %s", project_id, exc)
            return None

        refs: list[ReferenceAsset] = []
        weights: dict[str, float] = {}
        fallback_text: dict[str, str] = {}
        kind_weights = {
            "character_full": 0.9,
            "character_face": 0.7,
            "environment": 0.35,
            "style": 0.2,
        }
        character_names = [
            str(character.get("name") or "").strip()
            for character in characters
            if str(character.get("name") or "").strip()
        ]
        character_label = ", ".join(character_names) if character_names else "the resolved cast"

        for raw in raw_refs:
            if not isinstance(raw, dict):
                continue
            ref_id = str(raw.get("ref_id") or "").strip()
            kind = str(raw.get("kind") or "").strip()
            image_url = str(raw.get("image_url") or "").strip()
            if not ref_id or kind not in kind_weights or not image_url:
                continue
            try:
                ref = ReferenceAsset(
                    ref_id=ref_id,
                    kind=kind,  # type: ignore[arg-type]
                    image_url=image_url,
                    embedding=raw.get("embedding") if isinstance(raw.get("embedding"), list) else None,
                    source_shot_id=raw.get("source_shot_id"),
                    project_id=project_id,
                )
            except Exception:
                continue
            refs.append(ref)
            weights[ref.ref_id] = kind_weights[kind]
            if kind in {"character_full", "character_face"}:
                fallback_text[ref.ref_id] = (
                    f"Use confirmed {kind.replace('_', ' ')} reference for {character_label}; "
                    "preserve identity, silhouette, face, and wardrobe continuity."
                )
            elif kind == "environment":
                fallback_text[ref.ref_id] = "Use confirmed environment reference for spatial and lighting continuity."
            elif kind == "style":
                fallback_text[ref.ref_id] = "Use confirmed style reference for project visual language."

        if not refs:
            return None
        logger.info(
            "CONFIRMED_REFERENCE_ASSETS_ATTACHED | project=%s | refs=%d | characters=%d",
            project_id,
            len(refs),
            len(characters),
        )
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

    def get_reference_locks_for_character(
        self,
        storage: Any,
        project_id: str,
        character_id: str,
    ) -> list[dict[str, Any]]:
        """Every usable reference for one character, best first.

        Canonical locks win over provisional ones, and within each group the
        stronger role sorts first so a truncated set keeps the best evidence.
        Falls back to the single-lock read on storages that predate the
        multi-reference API.
        """
        rows: list[dict[str, Any]] = []
        reader = getattr(storage, "list_character_reference_locks_for_character", None)
        if callable(reader):
            try:
                rows = list(reader(project_id, character_id, "locked") or [])
            except Exception as exc:
                logger.debug("Multi-reference lookup failed for %s/%s: %s", project_id, character_id, exc)
                rows = []
        if not rows:
            single = storage.get_character_reference_lock(project_id, character_id, "locked")
            rows = [single] if single else []
        if not rows:
            provisional = storage.get_character_reference_lock(project_id, character_id, "provisional")
            rows = [provisional] if provisional else []

        def _rank(row: dict[str, Any]) -> tuple[int, float]:
            status = str(row.get("lock_status") or "").strip()
            role = str(row.get("reference_role") or "general").strip()
            return (
                0 if status == "locked" else 1,
                -self.ROLE_WEIGHTS.get(role, self.ROLE_WEIGHTS["general"]),
            )

        return sorted([row for row in rows if row], key=_rank)

    def relock_character_reference(
        self,
        *,
        project_id: str,
        character_id: str,
        image_url: str,
        storage: Any,
        reference_role: str = "general",
        character_name: str = "",
        source_shot_id: str = "",
        source_job_id: str = "",
        capture_method: str = "director_override",
        reason: str = "",
    ) -> CharacterReferenceLock | None:
        """Replace a character's locked reference for one role.

        The first passing render used to define a character permanently: the
        lock was written once and `lock_first_references_for_completed_job`
        skipped any character that already had one. A reference captured from a
        bad frame therefore degraded every later shot with no way to correct it.
        This is the correction path — for a director picking a better frame, and
        for automatic upgrades.
        """
        clean_image = str(image_url or "").strip()
        if not clean_image or not str(character_id or "").strip():
            return None

        now = datetime.now().isoformat()
        existing = storage.get_character_reference_lock(
            project_id, character_id, "locked", reference_role
        )
        if existing:
            if str(existing.get("image_url") or "").strip() == clean_image:
                return CharacterReferenceLock(**existing)
            superseded = dict(existing)
            superseded["lock_status"] = "superseded"
            superseded["updated_at"] = now
            superseded["trace_notes"] = (
                f"Superseded by re-lock ({capture_method})"
                + (f": {reason}" if reason else "")
            )
            storage.save_character_reference_lock(superseded)

        lock = CharacterReferenceLock(
            lock_id=f"charlock_{uuid4().hex[:12]}",
            project_id=project_id,
            character_id=character_id,
            character_name=character_name or str((existing or {}).get("character_name") or ""),
            source_shot_id=source_shot_id or str((existing or {}).get("source_shot_id") or "relock"),
            image_url=clean_image,
            lock_status="locked",
            provider=str((existing or {}).get("provider") or ""),
            capture_method=capture_method,
            reference_role=reference_role,  # type: ignore[arg-type]
            reliability="high",
            source_job_id=source_job_id,
            source_status="approved",
            review_status="approved" if capture_method == "director_override" else "unreviewed",
            trace_notes=reason or f"Re-locked via {capture_method}",
            created_at=now,
            updated_at=now,
        )
        saved = storage.save_character_reference_lock(lock.model_dump(mode="json"))
        if not saved:
            return None
        logger.info(
            "CHARACTER_REFERENCE_RELOCKED | project=%s | character=%s | role=%s | method=%s",
            project_id,
            character_id,
            reference_role,
            capture_method,
        )
        return CharacterReferenceLock(**saved)

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
                reference_role="general",
                reliability="medium",
                source_job_id=f"storyboard_{shot_id}",
                source_status="provisional",
                review_status="unreviewed",
                trace_notes="Created from completed storyboard image before approved render exists.",
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
        """Choose the image that will define this character for the rest of the film.

        Order matters here. The provider thumbnail used to win unconditionally,
        but on most clips it is frame 0 — which on a fade-up or a moving shot is
        the single worst frame available. Because a lock is durable and
        conditions every later shot, it is worth spending a few ffmpeg calls to
        pick a good frame from the actual video when one is on disk, and to fall
        back to the thumbnail only when it is not.
        """
        if not job.output_payload:
            return None

        asset_url = str(job.output_payload.asset_url or "").strip()
        thumbnail_url = str(job.output_payload.thumbnail_url or "").strip()

        if asset_url and asset_url.lower().split("?", 1)[0].endswith((".png", ".jpg", ".jpeg", ".webp")):
            return asset_url, "output_image"

        local_path = self._local_output_path(asset_url) if asset_url else None
        if local_path and local_path.exists() and local_path.suffix.lower() in {".mp4", ".mov", ".webm"}:
            frame_url = self._extract_frame(job, local_path)
            if frame_url:
                return frame_url, "representative_frame"

        if thumbnail_url:
            return thumbnail_url, "thumbnail"

        if not asset_url:
            return None

        return asset_url, "output_url_fallback"

    def capture_reference_images(
        self,
        job: RenderJobModel,
        count: int | None = None,
    ) -> list[tuple[str, str, str]]:
        """Capture up to `count` reference views from a completed job.

        Returns [(image_url, capture_method, reference_role), ...] best first.
        Only the local-video path can yield more than one view; still images,
        thumbnails, and remote URLs collapse to the single primary reference.
        """
        limit = max(1, count or self.MAX_REFERENCES_PER_CHARACTER)
        if not job.output_payload:
            return []

        asset_url = str(job.output_payload.asset_url or "").strip()
        local_path = self._local_output_path(asset_url) if asset_url else None
        is_video = (
            local_path is not None
            and local_path.exists()
            and local_path.suffix.lower() in {".mp4", ".mov", ".webm"}
        )

        if is_video and limit > 1:
            frames = self._extract_reference_frames(job, local_path, count=limit)
            if frames:
                return [
                    (image_url, "representative_frame", self._role_for_rank(index))
                    for index, (image_url, _score) in enumerate(frames)
                ]

        primary = self.capture_reference_image(job)
        if not primary:
            return []
        image_url, capture_method = primary
        return [(image_url, capture_method, "general")]

    @staticmethod
    def _role_for_rank(index: int) -> str:
        """Role for the Nth-best frame captured from one clip.

        Without a face detector these frames cannot be honestly labelled `face`
        or `full_body` — that classification needs to know how much of the frame
        the subject occupies. They are labelled for what they actually are:
        the primary reference, and additional angles of the same character.
        """
        return "general" if index == 0 else "alternate_angle"

    def lock_first_references_for_completed_job(
        self,
        *,
        job: RenderJobModel,
        storage: Any,
    ) -> list[CharacterReferenceLock]:
        if job.status != "complete":
            return []
        captures = self.capture_reference_images(job)
        if not captures:
            return []
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

            # Lock every captured view, not just one. Uniqueness is per
            # (project, character, role), so the primary frame and any
            # additional angles coexist and are all sent to r2v.
            for image_url, capture_method, reference_role in captures:
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
                    reference_role=reference_role,  # type: ignore[arg-type]
                    reliability="high" if reference_role == "general" else "medium",
                    source_job_id=job.id,
                    source_status="approved",
                    review_status="approved",
                    trace_notes="Promoted only after completed render passed adherence review.",
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

    def verify_shot_identity(
        self,
        *,
        job: RenderJobModel,
        storage: Any,
        embedding_adapter: Any = None,
    ) -> dict[str, Any]:
        """Measure whether this render's characters still look like their locks.

        This is the render-time identity check. It compares a frame from the
        completed job against each appearing character's locked reference using
        the visual embedding adapter, with thresholds chosen for that adapter's
        embedding kind.

        Returns a report; never raises. A shot with no locks yet (every
        character's first appearance) is `not_applicable`, not a failure.
        """
        from app.services.visual_embedding_adapter import (
            EMBEDDING_KIND_OPAQUE,
            build_visual_embedding_adapter,
            match_label,
        )

        report: dict[str, Any] = {
            "status": "not_applicable",
            "shot_id": job.shot_id,
            "job_id": job.id,
            "characters": [],
            "embedding_kind": EMBEDDING_KIND_OPAQUE,
            "measures_identity": False,
        }
        if job.status != "complete":
            report["reason"] = "render_not_complete"
            return report

        adapter = embedding_adapter or build_visual_embedding_adapter()
        kind = getattr(adapter, "kind", EMBEDDING_KIND_OPAQUE)
        report["embedding_kind"] = kind
        # Only a face-identity embedding answers "is this the same person". A
        # general-visual embedding answers "does this look like the same
        # picture", which is continuity evidence, not a likeness verdict — and
        # this flag is what stops callers from treating them as equivalent.
        report["measures_identity"] = kind == "face_identity"

        captured = self.capture_reference_image(job)
        if not captured:
            report["status"] = "unavailable"
            report["reason"] = "no_output_frame"
            return report

        output_local = self._resolve_local_image(captured[0])
        if not output_local:
            report["status"] = "unavailable"
            report["reason"] = "output_frame_not_local"
            return report

        output_result = adapter.embed_image(
            output_local,
            {"project_id": job.project_id, "shot_id": job.shot_id, "job_id": job.id, "role": "rendered_output"},
        )
        if output_result.status != "complete" or not output_result.vector:
            # No vector means no evidence. Reporting drift here would turn an
            # unconfigured embedder into a permanent false alarm.
            report["status"] = "unavailable"
            report["reason"] = str(output_result.metadata.get("message") or "embedding_unavailable")
            return report

        characters = self.resolve_shot_characters(
            project_id=job.project_id,
            shot_id=job.shot_id,
            storage=storage,
            prompt=(job.input_payload.prompt if job.input_payload else "") or "",
        )

        rows: list[dict[str, Any]] = []
        for character in characters:
            character_id = str(character.get("id") or "").strip()
            if not character_id:
                continue
            locks = self.get_reference_locks_for_character(storage, job.project_id, character_id)
            # Skip locks sourced from this very job — comparing a frame to itself
            # proves nothing.
            locks = [
                lock for lock in locks
                if str(lock.get("source_job_id") or "") != job.id
            ]
            if not locks:
                continue

            best: dict[str, Any] | None = None
            for lock in locks:
                reference_local = self._resolve_local_image(str(lock.get("image_url") or ""))
                if not reference_local:
                    continue
                reference_result = adapter.embed_image(
                    reference_local,
                    {
                        "project_id": job.project_id,
                        "character_id": character_id,
                        "role": "locked_reference",
                    },
                )
                if reference_result.status != "complete" or not reference_result.vector:
                    continue
                similarity = self._cosine_similarity(output_result.vector, reference_result.vector)
                candidate = {
                    "character_id": character_id,
                    "character_name": str(character.get("name") or "").strip(),
                    "reference_role": str(lock.get("reference_role") or "general"),
                    "reference_image_url": str(lock.get("image_url") or ""),
                    "similarity": round(similarity, 4),
                    "status": match_label(similarity, kind),
                }
                if best is None or similarity > best["similarity"]:
                    best = candidate
            if best is not None:
                rows.append(best)

        if not rows:
            report["reason"] = "no_comparable_locked_reference"
            return report

        report["characters"] = rows
        statuses = {row["status"] for row in rows}
        if "identity_drift" in statuses:
            report["status"] = "identity_drift"
        elif "plausibly_consistent" in statuses:
            report["status"] = "plausibly_consistent"
        else:
            report["status"] = "consistent"

        logger.info(
            "SHOT_IDENTITY_VERIFIED | job=%s | shot=%s | status=%s | kind=%s | characters=%d",
            job.id,
            job.shot_id,
            report["status"],
            kind,
            len(rows),
        )
        return report

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        return sum(a * b for a, b in zip(left, right))

    @classmethod
    def _resolve_local_image(cls, image_url: str) -> str:
        """Map a stored asset URL to a readable local file, or "" if remote."""
        raw = str(image_url or "").strip()
        if not raw or raw.startswith(("http://", "https://", "data:")):
            return ""
        backend_root = Path(__file__).resolve().parents[2]
        if raw.startswith("/previs-assets/"):
            candidate = backend_root / "outputs" / "previs" / raw.removeprefix("/previs-assets/")
        elif raw.startswith("/outputs/"):
            candidate = backend_root / raw.lstrip("/")
        else:
            candidate = Path(raw).expanduser()
        try:
            return str(candidate) if candidate.is_file() else ""
        except OSError:
            return ""

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

    # How many candidate frames to sample before choosing a reference.
    REFERENCE_CANDIDATE_COUNT = 6
    # Ignore the head and tail of the clip: fade-ups, provider slates, and
    # end-of-clip artifacts cluster there.
    REFERENCE_SAMPLE_START_RATIO = 0.15
    REFERENCE_SAMPLE_END_RATIO = 0.85
    # Mean luma band (0-255) a usable reference frame must fall inside. Outside
    # this, the frame is crushed black or blown out and carries no likeness.
    REFERENCE_MIN_MEAN_LUMA = 25.0
    REFERENCE_MAX_MEAN_LUMA = 235.0

    @staticmethod
    def _probe_duration_seconds(video_path: Path) -> float | None:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode != 0:
                return None
            duration = float((result.stdout or "").strip())
            return duration if duration > 0 else None
        except Exception:
            return None

    @classmethod
    def _score_candidate_frame(cls, frame_path: Path) -> float:
        """Score a candidate reference frame. Higher is better; 0.0 rejects it.

        Sharpness is measured as the standard deviation of an edge-detected copy
        — the Pillow equivalent of variance-of-Laplacian, the standard blur
        metric. A motion-blurred or defocused frame has far less edge energy than
        a clean one, which is exactly the difference between a reference that
        holds a likeness and one that poisons every shot that follows.

        Exposure is a gate rather than a score: a crushed or blown frame is
        rejected outright no matter how much edge energy it has.
        """
        try:
            from PIL import Image, ImageFilter, ImageStat
        except Exception:
            # Pillow missing — treat all candidates as equal so selection falls
            # back to the first usable frame rather than failing the capture.
            return 1.0

        try:
            with Image.open(frame_path) as image:
                grayscale = image.convert("L")
                mean_luma = ImageStat.Stat(grayscale).mean[0]
                if not (cls.REFERENCE_MIN_MEAN_LUMA <= mean_luma <= cls.REFERENCE_MAX_MEAN_LUMA):
                    return 0.0
                edges = grayscale.filter(ImageFilter.FIND_EDGES)
                return float(ImageStat.Stat(edges).stddev[0])
        except Exception as exc:
            logger.debug("Reference frame scoring failed for %s: %s", frame_path, exc)
            return 0.0

    @staticmethod
    def _grab_frame_at(video_path: Path, timestamp: float, destination: Path) -> bool:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(destination),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if result.returncode != 0:
                logger.debug("Reference frame extraction failed: %s", result.stderr[-500:])
                return False
        except Exception as exc:
            logger.debug("Reference frame extraction skipped: %s", exc)
            return False
        return destination.exists() and destination.stat().st_size > 0

    @classmethod
    def _candidate_timestamps(cls, duration: float | None) -> list[float]:
        if not duration or duration <= 0:
            # Unknown duration — probe a short spread that is safe on any clip
            # long enough to be worth locking from.
            return [1.0, 0.5, 1.5]
        start = duration * cls.REFERENCE_SAMPLE_START_RATIO
        end = duration * cls.REFERENCE_SAMPLE_END_RATIO
        count = max(1, cls.REFERENCE_CANDIDATE_COUNT)
        if count == 1 or end <= start:
            return [start]
        step = (end - start) / (count - 1)
        return [start + step * index for index in range(count)]

    # Minimum spacing between two frames locked from the same clip, as a
    # fraction of clip duration. Two frames 40ms apart are the same picture and
    # add nothing as a second reference view.
    REFERENCE_MIN_SEPARATION_RATIO = 0.2

    @classmethod
    def _rank_candidate_frames(
        cls,
        job: RenderJobModel,
        video_path: Path,
        output_dir: Path,
    ) -> tuple[list[tuple[float, float]], float | None, int]:
        """Score every candidate timestamp. Returns (ranked, duration, scored_count).

        `ranked` is [(score, timestamp), ...] best first, rejects excluded.
        """
        duration = cls._probe_duration_seconds(video_path)
        timestamps = cls._candidate_timestamps(duration)
        safe_job_id = cls._safe_job_id(job)
        candidate_path = output_dir / f"{safe_job_id}_{job.shot_id}_candidate.jpg"

        ranked: list[tuple[float, float]] = []
        scored = 0
        for timestamp in timestamps:
            if not cls._grab_frame_at(video_path, timestamp, candidate_path):
                continue
            scored += 1
            score = cls._score_candidate_frame(candidate_path)
            if score > 0.0:
                ranked.append((score, timestamp))

        try:
            if candidate_path.exists():
                candidate_path.unlink()
        except Exception:
            pass

        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked, duration, scored

    @staticmethod
    def _safe_job_id(job: RenderJobModel) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in job.id)

    @classmethod
    def _extract_frame(cls, job: RenderJobModel, video_path: Path) -> str | None:
        """Pick the best available frame from the clip as the character reference.

        Replaces a hardcoded grab at 00:00:01, which selected whatever happened to
        be one second in — frequently a blurred or transitional frame.
        """
        frames = cls._extract_reference_frames(job, video_path, count=1)
        return frames[0][0] if frames else None

    @classmethod
    def _extract_reference_frames(
        cls,
        job: RenderJobModel,
        video_path: Path,
        count: int = 1,
    ) -> list[tuple[str, float]]:
        """Extract up to `count` well-separated, high-scoring frames.

        Returns [(asset_url, score), ...] best first. More than one view of a
        character materially improves identity hold on happyhorse-1.1-r2v, which
        accepts up to 9 reference images.
        """
        output_dir = Path(__file__).resolve().parents[2] / "outputs" / "references" / job.project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_job_id = cls._safe_job_id(job)

        ranked, duration, scored = cls._rank_candidate_frames(job, video_path, output_dir)

        if not ranked:
            # Every candidate was rejected on exposure, or nothing scored. Fall
            # back to the original fixed grab so capture still succeeds.
            fallback_path = output_dir / f"{safe_job_id}_{job.shot_id}_reference.jpg"
            if not cls._grab_frame_at(video_path, 1.0, fallback_path):
                return []
            logger.info(
                "REFERENCE_FRAME_FALLBACK | job=%s | shot=%s | candidates_scored=%d",
                job.id,
                job.shot_id,
                scored,
            )
            return [(f"/outputs/references/{job.project_id}/{fallback_path.name}", 0.0)]

        min_separation = (duration or 0.0) * cls.REFERENCE_MIN_SEPARATION_RATIO
        chosen: list[tuple[float, float]] = []
        for score, timestamp in ranked:
            if len(chosen) >= max(1, count):
                break
            if any(abs(timestamp - taken) < min_separation for _, taken in chosen):
                continue
            chosen.append((score, timestamp))

        results: list[tuple[str, float]] = []
        for index, (score, timestamp) in enumerate(chosen):
            suffix = "reference" if index == 0 else f"reference_{index + 1}"
            frame_path = output_dir / f"{safe_job_id}_{job.shot_id}_{suffix}.jpg"
            if not cls._grab_frame_at(video_path, timestamp, frame_path):
                continue
            results.append((f"/outputs/references/{job.project_id}/{frame_path.name}", score))
            logger.info(
                "REFERENCE_FRAME_SELECTED | job=%s | shot=%s | rank=%d | timestamp=%.3f | "
                "sharpness=%.2f | candidates=%d | duration=%s",
                job.id,
                job.shot_id,
                index + 1,
                timestamp,
                score,
                scored,
                f"{duration:.2f}" if duration else "unknown",
            )
        return results


character_visual_reference_service = CharacterVisualReferenceService()
