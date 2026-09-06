from __future__ import annotations

import json
import re
import warnings
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.data.storage import get_storage
from app.models.character_look import CharacterLook, CharacterLookApprovalRequest
from app.services.stability import PersistenceError, StateError, ValidationError, elapsed_ms, log_stage_event, start_timer
from app.utils.character_casting import casting_jobs, casting_job_view
from app.utils.character_appearance import APPEARANCE_FIELDS, appearance_approval, appearance_description, continuity_document


MAX_REFERENCE_BYTES = 10 * 1024 * 1024


def validate_reference_image(data: bytes) -> str:
    if not data or len(data) > MAX_REFERENCE_BYTES:
        raise ValidationError("Choose a JPEG, PNG, or WebP image up to 10 MB.", stage="character_look_upload")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(image.format)
                if not extension or image.width * image.height > 24_000_000 or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unsupported image dimensions, animation, or format")
                image.verify()
            # verify() is metadata-only for some formats; decode once to reject truncated images.
            with Image.open(BytesIO(data)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError("Choose a valid, still JPEG, PNG, or WebP image under 24 megapixels.", stage="character_look_upload") from exc
    return extension


class CharacterLookService:
    """Explicit creator approval; its single saved snapshot is authoritative for renders."""

    def __init__(self, storage=None, outputs_dir: Path | None = None):
        self._storage = storage
        self.outputs_dir = outputs_dir or Path(__file__).resolve().parents[2] / "outputs"

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    def _character(self, project_id: str, character_id: str) -> dict:
        character = self.storage.get_character(character_id, project_id)
        if not character:
            raise LookupError("Character not found in this project")
        return character

    def _folder(self, project_id: str, character_id: str) -> Path:
        # Hash both scopes; no caller-controlled path segments or filenames.
        return Path("references/character-looks") / sha256(project_id.encode()).hexdigest()[:24] / sha256(character_id.encode()).hexdigest()[:24]

    def _candidates(self, character: dict) -> list[dict]:
        project_id, character_id = character["project_id"], character["id"]
        candidates: dict[str, dict] = {}
        for status in ("locked", "provisional", "superseded"):
            for row in self.storage.list_character_reference_locks_for_character(project_id, character_id, status, 50):
                url = str(row.get("image_url") or "").strip()
                if url:
                    candidates[url] = {"image_url": url, "role": row.get("reference_role") or "general", "source": "Existing reference — review before approving"}
        approval = appearance_approval(character)
        for field, role in (("face_image_url", "face"), ("body_image_url", "full_body")):
            if approval.get(field):
                url = approval[field]
                candidates[url] = {"image_url": url, "role": role, "source": "Previously selected reference"}
        folder = self._folder(project_id, character_id)
        prefix = f"/outputs/{folder.as_posix()}/"
        for url in continuity_document(character).get("appearance_reference_uploads", []):
            if isinstance(url, str) and url.startswith(prefix):
                filename = url.removeprefix(prefix)
                if re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", filename) and (self.outputs_dir / folder / filename).is_file():
                    candidates[url] = {"image_url": url, "role": "general", "source": "Uploaded reference — awaiting selection"}
        for job in casting_jobs(character):
            matches = casting_job_view(job, character)["matches_current_profile"]
            for url in job.get("images", []):
                if isinstance(url, str) and url.startswith(prefix):
                    filename = url.removeprefix(prefix)
                    if re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", filename) and (self.outputs_dir / folder / filename).is_file():
                        candidates[url] = {"image_url": url, "role": "face", "source": "Generated casting option — awaiting selection", "generation_id": job["id"], "matches_current_profile": matches}
        return list(candidates.values())

    def _view(self, character: dict) -> CharacterLook:
        approval = appearance_approval(character)
        return CharacterLook(
            character_id=character["id"], project_id=character["project_id"], name=character["name"],
            age=character.get("age"), description=appearance_description(character),
            physical_description=str(character.get("look") or character.get("appearance_core") or ""),
            visual_prompt_summary=str(character.get("visual_prompt_summary") or ""),
            status="locked" if approval.get("status") == "locked" else "draft",
            version=int(approval.get("version") or 0), profile_revision=character["updated_at"],
            face_image_url=approval.get("face_image_url"), body_image_url=approval.get("body_image_url"),
            approved_at=approval.get("approved_at") if approval.get("status") == "locked" else None,
            candidates=self._candidates(character),
            casting_generations=[casting_job_view(job, character) for job in reversed(casting_jobs(character))],
        )

    def get(self, project_id: str, character_id: str) -> CharacterLook:
        return self._view(self._character(project_id, character_id))

    def list(self, project_id: str) -> list[CharacterLook]:
        return [self._view(row) for row in self.storage.get_characters(project_id)]

    @staticmethod
    def _expect_revision(character: dict, expected: str) -> None:
        if character["updated_at"] != expected:
            raise StateError("This profile changed. Refresh the saved look before continuing.", stage="character_look_revision")

    def _save(self, character: dict, approval: dict, stage: str) -> CharacterLook:
        timer = start_timer()
        document = continuity_document(character)
        document["appearance_approval"] = approval
        try:
            saved = self.storage.patch_character_revision(
                character["project_id"], character["id"],
                {"continuity_state_json": json.dumps(document)}, character["updated_at"],
            )
        except Exception as exc:
            raise PersistenceError("The character look could not be saved.", stage=stage) from exc
        if not saved:
            raise StateError("This profile changed. Refresh the saved look before continuing.", stage=stage)
        log_stage_event(project_id=character["project_id"], job_id=None, provider=None, stage=stage,
                        duration_ms=elapsed_ms(timer), extra={"character_id": character["id"], "version": approval["version"]})
        return self._view(saved)

    def approve(self, project_id: str, character_id: str, request: CharacterLookApprovalRequest) -> CharacterLook:
        character = self._character(project_id, character_id)
        self._expect_revision(character, request.expected_profile_revision)
        current = appearance_approval(character)
        if current.get("status") == "locked":
            raise StateError("Choose Revise look before changing this approved appearance.", stage="character_look_approve")
        if not any(str(character.get(field) or "").strip() for field in ("look", "appearance_core", "visual_prompt_summary")):
            raise ValidationError("Save this character’s physical description before approving the look.", stage="character_look_approve")
        known = {row["image_url"] for row in self._candidates(character)}
        for url in (request.face_image_url, request.body_image_url):
            if url is not None and url not in known:
                raise ValidationError("Choose or upload a reference belonging to this character.", stage="character_look_approve")
        approval = {
            "status": "locked", "version": int(current.get("version") or 0) + 1,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "face_image_url": request.face_image_url, "body_image_url": request.body_image_url,
            "description": appearance_description(character),
            "profile": {field: character.get(field) for field in APPEARANCE_FIELDS},
            "history": current.get("history", []),
        }
        return self._save(character, approval, "character_look_approve")

    def revise(self, project_id: str, character_id: str, expected_revision: str) -> CharacterLook:
        character = self._character(project_id, character_id)
        self._expect_revision(character, expected_revision)
        current = appearance_approval(character)
        if current.get("status") != "locked":
            raise StateError("This look is already open for editing.", stage="character_look_revise")
        history = list(current.get("history", []))
        history.append({key: value for key, value in current.items() if key != "history"})
        return self._save(character, {**current, "status": "draft", "history": history}, "character_look_revise")

    def upload(self, project_id: str, character_id: str, data: bytes) -> str:
        timer = start_timer()
        character = self._character(project_id, character_id)
        if appearance_approval(character).get("status") == "locked":
            raise StateError("Choose Revise look before uploading a new appearance reference.", stage="character_look_upload")
        extension = validate_reference_image(data)
        relative = self._folder(project_id, character_id) / f"{uuid4().hex}.{extension}"
        target = self.outputs_dir / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as exc:
            raise PersistenceError("The reference image could not be saved.", stage="character_look_upload") from exc
        url = f"/outputs/{relative.as_posix()}"
        document = continuity_document(character)
        document["appearance_reference_uploads"] = [*document.get("appearance_reference_uploads", []), url]
        try:
            saved = self.storage.patch_character_revision(project_id, character_id, {"continuity_state_json": json.dumps(document)}, character["updated_at"])
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise PersistenceError("The reference image could not be registered.", stage="character_look_upload") from exc
        if not saved:
            target.unlink(missing_ok=True)
            raise StateError("This profile changed. Refresh before uploading again.", stage="character_look_upload")
        log_stage_event(project_id=project_id, job_id=None, provider=None, stage="character_look_upload",
                        duration_ms=elapsed_ms(timer), extra={"character_id": character_id})
        return url


def get_character_look_service() -> CharacterLookService:
    return CharacterLookService()
