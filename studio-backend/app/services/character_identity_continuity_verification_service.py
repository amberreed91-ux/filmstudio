from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import RenderJobModel
from app.models.character_profile import CanonicalCharacterIdentityRecord
from app.services.character_identity_memory_service import character_identity_memory_service
from app.services.visual_embedding_adapter import VisualEmbeddingAdapter, build_visual_embedding_adapter


class CharacterIdentityContinuityVerificationService:
    """Evaluates rendered outputs against approved character identity references."""

    def __init__(self, embedding_adapter: VisualEmbeddingAdapter | None = None):
        self._embedding_adapter = embedding_adapter or build_visual_embedding_adapter()
        self._backend_root = Path(__file__).resolve().parents[2]

    def _local_image_path(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw.startswith(("http://", "https://")):
            return ""
        if raw.startswith("/outputs/"):
            candidate = self._backend_root / raw.lstrip("/")
            return str(candidate) if candidate.exists() else ""
        candidate = Path(raw).expanduser()
        return str(candidate) if candidate.exists() and candidate.is_file() else ""

    def _job_output_image(self, job: RenderJobModel) -> str:
        output = job.output_payload
        if output is None:
            return ""
        metadata = output.metadata if isinstance(output.metadata, dict) else {}
        for key in ("identity_frame", "representative_frame", "reference_frame", "thumbnail_path"):
            resolved = self._local_image_path(metadata.get(key))
            if resolved:
                return resolved
        for value in (output.thumbnail_url, output.asset_url):
            resolved = self._local_image_path(value)
            if resolved:
                return resolved
        return ""

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        return sum(left * right for left, right in zip(a, b))

    @staticmethod
    def _match_label(similarity: float) -> str:
        if similarity >= 0.97:
            return "consistent"
        if similarity >= 0.82:
            return "plausibly_consistent"
        return "identity_drift"

    def _embed(self, image_path: str, context: dict[str, Any]) -> list[float]:
        result = self._embedding_adapter.embed_image(image_path, context)
        if result.status != "complete":
            return []
        return result.vector

    @staticmethod
    def _scene_names(scene_data: dict[str, Any]) -> set[str]:
        raw = scene_data.get("character_appearances") or scene_data.get("characters") or []
        if not isinstance(raw, list):
            return set()
        return {str(name).strip().lower() for name in raw if str(name).strip()}

    def verify_rendered_sequence(
        self,
        *,
        project_id: str,
        character_records: list[CanonicalCharacterIdentityRecord | dict[str, Any]],
        render_jobs: list[RenderJobModel],
        scenes_by_shot_id: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        records = [
            record
            for raw in character_records
            if (record := character_identity_memory_service.build_canonical_record(raw)) is not None
        ]
        scenes = scenes_by_shot_id or {}
        shot_reports: list[dict[str, Any]] = []
        warnings: list[str] = []

        for job in render_jobs:
            scene = scenes.get(job.shot_id, {})
            scene_names = self._scene_names(scene)
            output_image = self._job_output_image(job)
            if job.status != "complete":
                warnings.append(f"{job.shot_id}: render is not complete; identity continuity cannot be verified.")
                shot_reports.append(
                    {
                        "shot_id": job.shot_id,
                        "job_id": job.id,
                        "status": "manual_review",
                        "reason": "render_not_complete",
                        "characters": [],
                    }
                )
                continue
            if not output_image:
                warnings.append(f"{job.shot_id}: no local frame or thumbnail available for identity verification.")
                shot_reports.append(
                    {
                        "shot_id": job.shot_id,
                        "job_id": job.id,
                        "status": "manual_review",
                        "reason": "missing_local_output_frame",
                        "characters": [],
                    }
                )
                continue

            output_vector = self._embed(
                output_image,
                {"project_id": project_id, "shot_id": job.shot_id, "job_id": job.id, "role": "rendered_output"},
            )
            character_reports: list[dict[str, Any]] = []
            for record in records:
                if scene_names and record.name.lower() not in scene_names and record.character_id.lower() not in scene_names:
                    continue
                approved_refs = [
                    ref for ref in record.approved_visual_references
                    if ref.source_status in {"approved", "provisional"} and ref.image_url
                ]
                if not approved_refs:
                    character_reports.append(
                        {
                            "character_id": record.character_id,
                            "character_name": record.name,
                            "status": "manual_review",
                            "reason": "no_approved_reference",
                            "reference_trace": [],
                        }
                    )
                    continue

                best: dict[str, Any] | None = None
                for ref in approved_refs:
                    ref_path = self._local_image_path(ref.image_url)
                    if not ref_path:
                        continue
                    ref_vector = self._embed(
                        ref_path,
                        {
                            "project_id": project_id,
                            "shot_id": job.shot_id,
                            "job_id": job.id,
                            "character_id": record.character_id,
                            "reference_id": ref.ref_id,
                            "role": "approved_identity_reference",
                        },
                    )
                    similarity = self._cosine(output_vector, ref_vector)
                    label = self._match_label(similarity)
                    candidate = {
                        "character_id": record.character_id,
                        "character_name": record.name,
                        "status": label,
                        "viewer_belief": (
                            "same_character"
                            if label in {"consistent", "plausibly_consistent"}
                            else "identity_may_not_read_as_same_character"
                        ),
                        "reference_trace": [
                            {
                                "ref_id": ref.ref_id,
                                "image_url": ref.image_url,
                                "source_shot_id": ref.source_shot_id,
                                "source_job_id": ref.source_job_id,
                                "source_status": ref.source_status,
                                "reliability": ref.reliability,
                                "role": ref.role,
                            }
                        ],
                        "output_trace": {
                            "job_id": job.id,
                            "shot_id": job.shot_id,
                            "image_path": output_image,
                        },
                    }
                    if best is None or label == "consistent":
                        best = candidate
                    if label == "consistent":
                        break

                if best is None:
                    best = {
                        "character_id": record.character_id,
                        "character_name": record.name,
                        "status": "manual_review",
                        "reason": "approved_reference_not_locally_accessible",
                        "reference_trace": [
                            {
                                "ref_id": ref.ref_id,
                                "image_url": ref.image_url,
                                "source_shot_id": ref.source_shot_id,
                                "source_job_id": ref.source_job_id,
                                "source_status": ref.source_status,
                                "reliability": ref.reliability,
                                "role": ref.role,
                            }
                            for ref in approved_refs
                        ],
                    }
                if best["status"] in {"identity_drift", "manual_review"}:
                    warnings.append(f"{job.shot_id}: {record.name or record.character_id} needs identity review.")
                character_reports.append(best)

            shot_statuses = {row["status"] for row in character_reports}
            if "identity_drift" in shot_statuses:
                shot_status = "identity_drift"
            elif "manual_review" in shot_statuses:
                shot_status = "manual_review"
            else:
                shot_status = "consistent"
            shot_reports.append(
                {
                    "shot_id": job.shot_id,
                    "job_id": job.id,
                    "status": shot_status,
                    "characters": character_reports,
                }
            )

        statuses = {row["status"] for row in shot_reports}
        if "identity_drift" in statuses:
            sequence_status = "identity_drift"
        elif "manual_review" in statuses:
            sequence_status = "manual_review"
        else:
            sequence_status = "consistent"

        return {
            "project_id": project_id,
            "sequence_status": sequence_status,
            "viewer_belief_standard": "viewer reasonably believes the shots depict the same actor and character",
            "shot_reports": shot_reports,
            "warnings": warnings,
            "reference_trace_complete": all(
                character.get("reference_trace")
                for shot in shot_reports
                for character in shot.get("characters", [])
                if character.get("status") != "manual_review"
            ),
        }


character_identity_continuity_verification_service = CharacterIdentityContinuityVerificationService()
