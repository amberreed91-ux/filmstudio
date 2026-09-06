"""Read-only casting projections shared by appearance approval and generation."""
from __future__ import annotations

import json
import time
from hashlib import sha256

from app.utils.character_appearance import APPEARANCE_FIELDS, continuity_document

CASTING_KEY = "appearance_casting_jobs"
ACTIVE_CASTING = {"queued", "running"}
CASTING_TIMEOUT_SECONDS = 600


def appearance_fingerprint(character: dict) -> str:
    profile = {field: character.get(field) for field in APPEARANCE_FIELDS}
    return sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def casting_jobs(character: dict) -> list[dict]:
    return continuity_document(character).get(CASTING_KEY, [])


def casting_job_view(job: dict, character: dict) -> dict:
    expired = job["status"] in ACTIVE_CASTING and time.time() >= job["deadline"]
    count = len(job.get("images", []))
    return {
        "id": job["id"],
        "status": ("partial" if count else "failed") if expired else job["status"],
        "requested_count": job["requested_count"], "completed_count": count,
        "direction": job["direction"], "created_at": job["created_at"],
        "error": "Casting stopped before this set finished. Finished portraits are saved; generating a new set is a separate request." if expired else job.get("error"),
        "matches_current_profile": job["profile_fingerprint"] == appearance_fingerprint(character),
    }
