"""Durable casting candidates, explicit creator selection, and idempotent submission."""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.adapters.casting_image_adapter import CastingImageAdapter
from app.models.character_look import CharacterCastingRequest, CharacterLook
from app.services.character_look_service import CharacterLookService, validate_reference_image
from app.services.stability import PersistenceError, ProviderError, StabilityError, StateError, ValidationError, elapsed_ms, log_stage_event, start_timer
from app.utils.character_appearance import appearance_approval, appearance_description, continuity_document
from app.utils.character_casting import ACTIVE_CASTING, CASTING_KEY, CASTING_TIMEOUT_SECONDS, appearance_fingerprint, casting_jobs


class CharacterCastingService:
    def __init__(self, looks: CharacterLookService | None = None, adapter=None):
        self.looks = looks or CharacterLookService()
        self.adapter = adapter or CastingImageAdapter()

    def _update(self, project_id: str, character_id: str, change) -> dict:
        """Merge only our metadata with the latest row; never replay provider I/O."""
        for _ in range(8):
            character = self.looks._character(project_id, character_id)
            document = continuity_document(character)
            if not change(character, document):
                return character
            try:
                saved = self.looks.storage.patch_character_revision(project_id, character_id, {"continuity_state_json": json.dumps(document)}, character["updated_at"])
            except Exception as exc:
                raise PersistenceError("Casting progress could not be saved. Refresh before starting another set.", stage="casting_persistence") from exc
            if saved:
                return saved
        raise StateError("This character is being updated elsewhere. Refresh before continuing.", stage="casting_persistence")

    @staticmethod
    def _prompt(character: dict, direction: str) -> str:
        prompt = (
            "Create one realistic casting photograph of one fictional character. Head and shoulders, face clearly visible, "
            "eyes toward camera, neutral expression, soft even daylight, plain neutral background, natural skin texture. "
            "Follow every saved physical trait below. Plain wardrobe unless the description specifies clothing. "
            "Explore a possible face only in details the profile leaves unspecified. No text, montage, dramatic scene or other people.\n"
            f"Character: {character['name']}\nSaved appearance: {appearance_description(character)}\n"
        )
        if direction:
            prompt += f"Casting direction (subordinate to saved physical traits): {direction}\n"
        # Refuse overlong input, rather than knowingly letting the provider silently
        # truncate the tail of an authoritative description. This byte-size guard
        # keeps ordinary casting prose comfortably inside the model prompt budget.
        if len(prompt.encode("utf-8")) > 2400:
            raise ValidationError("This casting description is too long. Shorten the saved physical description or casting direction so all details fit in the portrait request.", stage="casting_prompt")
        return prompt

    def start(self, project_id: str, character_id: str, request: CharacterCastingRequest) -> CharacterLook:
        timer = start_timer()
        job_id = str(request.request_id)
        direction = request.direction.strip()
        character = self.looks._character(project_id, character_id)
        existing = next((job for job in casting_jobs(character) if job["id"] == job_id), None)
        if existing:
            if existing["direction"] != direction:
                raise StateError("This casting request was already used with different direction.", stage="casting_submit")
            return self.looks._view(character)
        self.looks._expect_revision(character, request.expected_profile_revision)
        if appearance_approval(character).get("status") == "locked":
            raise StateError("Choose Revise look before generating another appearance.", stage="casting_submit")
        if not any(str(character.get(field) or "").strip() for field in ("look", "appearance_core", "visual_prompt_summary")):
            raise ValidationError("Save this character’s physical description before generating casting options.", stage="casting_submit")
        prompt = self._prompt(character, direction)
        self.adapter.check_configured()
        job = {"id": job_id, "status": "queued", "requested_count": 3, "images": [], "direction": direction,
               "prompt": prompt, "profile_fingerprint": appearance_fingerprint(character), "profile_revision": character["updated_at"],
               "created_at": datetime.now(timezone.utc).isoformat(), "deadline": time.time() + CASTING_TIMEOUT_SECONDS,
               "seeds": [secrets.randbelow(2147483648) for _ in range(3)], "provider": self.adapter.provider, "model": self.adapter.model, "error": None}

        def create(current, document):
            jobs = document.setdefault(CASTING_KEY, [])
            duplicate = next((row for row in jobs if row["id"] == job_id), None)
            if duplicate:
                if duplicate["direction"] != direction:
                    raise StateError("This casting request was already used with different direction.", stage="casting_submit")
                return False
            self.looks._expect_revision(current, request.expected_profile_revision)
            if any(row["status"] in ACTIVE_CASTING and row["deadline"] > time.time() for row in jobs):
                raise StateError("A casting set is already being generated for this character. Its progress is saved here.", stage="casting_submit")
            jobs.append(job)
            return True

        saved = self._update(project_id, character_id, create)
        log_stage_event(project_id=project_id, job_id=job_id, provider=self.adapter.provider, stage="casting_submit", duration_ms=elapsed_ms(timer))
        return self.looks._view(saved)

    def run(self, project_id: str, character_id: str, job_id: str) -> None:
        """Claim once, then save each result. An interrupted job is never replayed."""
        timer = start_timer()
        worker_id = uuid4().hex
        target = None
        try:
            def claim(_character, document):
                job = next((row for row in document.get(CASTING_KEY, []) if row["id"] == job_id), None)
                if not job or job["status"] != "queued" or job["deadline"] <= time.time():
                    return False
                job.update(status="running", worker_id=worker_id)
                return True

            saved = self._update(project_id, character_id, claim)
            job = next((row for row in casting_jobs(saved) if row["id"] == job_id), None)
            if not job or job.get("worker_id") != worker_id:
                return
            for seed in job["seeds"]:
                if time.time() >= job["deadline"]:
                    raise StateError("Casting reached its time limit. Finished portraits are saved.", stage="casting_timeout")
                data = self.adapter.generate(job["prompt"], seed)
                try:
                    extension = validate_reference_image(data)
                except ValidationError as exc:
                    raise ProviderError("The image provider returned an unreadable portrait. Finished portraits are saved.", stage="casting_download") from exc
                relative = self.looks._folder(project_id, character_id) / f"{uuid4().hex}.{extension}"
                target = self.looks.outputs_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                url = f"/outputs/{relative.as_posix()}"

                def append(_character, document):
                    current = next(row for row in document[CASTING_KEY] if row["id"] == job_id)
                    if current.get("worker_id") != worker_id or current["status"] != "running" or current["deadline"] <= time.time():
                        raise StateError("This casting set is no longer running. Finished portraits are saved.", stage="casting_timeout")
                    current["images"].append(url)
                    if len(current["images"]) == current["requested_count"]:
                        current["status"] = "complete"
                    return True

                self._update(project_id, character_id, append)
                target = None  # Registered files now belong to the character.
        except Exception as exc:
            if target is not None:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    log_stage_event(project_id=project_id, job_id=job_id, provider=self.adapter.provider, stage="casting_cleanup_failed", duration_ms=elapsed_ms(timer), extra={"error_type": "persistence_error"})
            error = exc.message if isinstance(exc, StabilityError) else "Casting could not finish this set. Finished portraits are saved."
            log_stage_event(project_id=project_id, job_id=job_id, provider=self.adapter.provider, stage="casting_failed", duration_ms=elapsed_ms(timer), extra={"error_type": exc.error_type if isinstance(exc, StabilityError) else "persistence_error"})
            try:
                def fail(_character, document):
                    current = next((row for row in document.get(CASTING_KEY, []) if row["id"] == job_id), None)
                    if not current or current.get("worker_id") != worker_id or current["status"] not in ACTIVE_CASTING:
                        return False
                    current.update(status="partial" if current["images"] else "failed", error=error)
                    return True
                self._update(project_id, character_id, fail)
            except Exception:
                # A storage outage leaves a durable deadline. Read projections turn
                # it terminal without resubmission when that deadline expires.
                log_stage_event(project_id=project_id, job_id=job_id, provider=self.adapter.provider, stage="casting_failure_persistence", duration_ms=elapsed_ms(timer), extra={"error_type": "persistence_error"})
        else:
            log_stage_event(project_id=project_id, job_id=job_id, provider=self.adapter.provider, stage="casting_complete", duration_ms=elapsed_ms(timer))


def get_character_casting_service() -> CharacterCastingService:
    return CharacterCastingService()
