from __future__ import annotations

import hashlib
import logging
import random
import urllib.parse
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from app.data.storage import get_storage
from app.prompt_assembly_context import preserve_generation_facts
from app.models.storyboard_blueprint import (
    StoryboardBlueprint,
    StoryboardBlueprintInspection,
    StoryboardBlueprintProvenance,
    StoryboardBlueprintStatus,
    StoryboardRenderLink,
    StoryboardRevisionLink,
    StoryboardShot,
    StoryboardShotContinuityPlan,
    StoryboardShotIntent,
    StoryboardShotRenderContract,
    StoryboardShotStatus,
    StoryboardShotVisualPlan,
    StoryboardBlueprintVersion,
    utc_now_iso,
)
from app.services.project_store import project_store
from app.services.shot_rationale_service import shot_rationale_service
from app.services.shot_sequence_service import shot_sequence_service
from app.services.stability import PersistenceError, StateError, ValidationError
from app.utils.helpers import derive_scene_id_from_shot_id

logger = logging.getLogger("storyboard-blueprint-service")


def _prompt_sha256(text: str) -> str:
    """Content hash proving a canonical prompt is machine builder output."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


class StoryboardBlueprintService:
    """Canonical storyboard blueprint lifecycle and production handoff service."""

    def __init__(self, storage: Any | None = None) -> None:
        self.storage = storage or get_storage("sqlite")
        self.project_store = project_store
        self.shot_sequence_service = shot_sequence_service
        self.shot_rationale_service = shot_rationale_service

    def set_storage(self, storage: Any) -> None:
        self.storage = storage

    def get_or_create_blueprint(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_count: int | None = None,
        change_reason: str = "create_or_update_draft",
        preserve_locked_shots: bool = True,
        create_new_version: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        self._validate_ids(project_id, scene_id)
        existing = self.storage.get_storyboard_blueprint(project_id, scene_id)
        if existing and existing.current_version_id:
            if create_new_version:
                return self.create_version(
                    blueprint_id=existing.blueprint_id,
                    shot_count=shot_count,
                    change_reason=change_reason,
                    preserve_locked_shots=preserve_locked_shots,
                )
            return self.get_blueprint_detail(project_id=project_id, scene_id=scene_id)

        scene = self._get_scene(project_id, scene_id)
        if scene is None:
            raise StateError("Scene not found", stage="storyboard_blueprint_create")

        blueprint_id = f"sbp_{project_id}_{scene_id}_{uuid4().hex[:8]}"
        version_id = f"sbv_{uuid4().hex[:12]}"
        provenance = self._build_provenance(project_id, scene_id, scene)
        inspection = StoryboardBlueprintInspection(
            blueprint_id=blueprint_id,
            version_id=version_id,
            render_readiness="ready",
            provenance=provenance,
        )
        blueprint = StoryboardBlueprint(
            blueprint_id=blueprint_id,
            project_id=project_id,
            scene_id=scene_id,
            current_version_id=version_id,
            status=StoryboardBlueprintStatus.DRAFT,
            metadata={"preserve_locked_shots": preserve_locked_shots},
        )
        version = StoryboardBlueprintVersion(
            version_id=version_id,
            blueprint_id=blueprint_id,
            project_id=project_id,
            scene_id=scene_id,
            version_number=1,
            status=StoryboardBlueprintStatus.DRAFT,
            change_reason=change_reason,
            provenance=provenance,
            inspection=inspection,
        )
        shots = self._build_initial_shots(
            project_id=project_id,
            scene_id=scene_id,
            scene=scene,
            blueprint_id=blueprint_id,
            version_id=version_id,
            requested_shot_count=shot_count,
        )
        self._persist_version_bundle(blueprint=blueprint, version=version, shots=shots)
        self._derive_image_prompt_proposals(shots)
        self._sync_scene_memory(project_id, scene_id, shots, approved=False)

        logger.info(
            "project_id=%s job_id=storyboard_%s provider=internal stage=storyboard_blueprint_create duration_ms=%d",
            project_id,
            scene_id,
            int((perf_counter() - started) * 1000),
        )
        return {"blueprint": blueprint, "version": version, "shots": shots, "inspection": inspection}

    # Version selection rule: creator and editing surfaces resolve the working
    # draft (current); frozen and consumption surfaces (inspection, previs,
    # render authorization) opt into the approved version explicitly. Calls
    # that omit the selector keep working-draft behavior.
    def get_blueprint_detail(
        self,
        *,
        project_id: str,
        scene_id: str,
        version_selection: Literal["current", "approved"] = "current",
    ) -> dict[str, Any]:
        self._validate_ids(project_id, scene_id)
        blueprint = self.storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None:
            raise StateError("Storyboard blueprint not found", stage="storyboard_blueprint_get")
        if version_selection == "approved":
            version_id = blueprint.approved_version_id
            if not version_id:
                raise StateError("No approved storyboard version", stage="storyboard_blueprint_get")
        elif version_selection == "current":
            version_id = blueprint.current_version_id
        else:
            raise StateError(f"Unknown version selection: {version_selection}", stage="storyboard_blueprint_get")
        version = (
            self.storage.get_storyboard_blueprint_version(version_id)
            if version_id
            else None
        )
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            if version_selection == "approved":
                raise StateError("Approved storyboard version not found", stage="storyboard_blueprint_get")
            raise StateError("Current storyboard version not found", stage="storyboard_blueprint_get")
        shots = self.storage.list_storyboard_shots(
            blueprint.blueprint_id,
            version_id,
        )
        inspection = self._inspect(blueprint, version, shots)
        # D4: non-blocking length advisory + per-shot render-readiness for the
        # UI and generation-preflight. Never blocks retrieval.
        image_gate: dict[str, Any] = {"approved": True, "not_ready": [], "message": ""}
        image_records: dict[str, Any] = {}
        try:
            prompt_service = self._image_prompt_service()
            image_gate = prompt_service.gate_for_version(shots)
            for shot in shots:
                record = self.storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
                status = prompt_service.status_for_shot(shot, record)
                entry = dict(record) if record else {}
                entry["render_ready"] = status.get("render_ready", False)
                entry["state"] = status.get("state")
                entry["gate_message"] = status.get("message", "")
                entry["canonical_utf16"] = status.get("canonical_utf16")
                image_records[shot.storyboard_shot_id] = entry
            for item in image_gate.get("not_ready", []):
                warning = str(item.get("message") or "").strip()
                if warning and warning not in inspection.warnings:
                    inspection.warnings.append(warning)
        except Exception:
            pass
        return {
            "blueprint": blueprint,
            "version": version,
            "shots": shots,
            "inspection": inspection,
            "image_prompt_gate": image_gate,
            "image_prompts": image_records,
        }

    def list_versions(self, blueprint_id: str) -> list[StoryboardBlueprintVersion]:
        self._require_blueprint(blueprint_id)
        return self.storage.list_storyboard_blueprint_versions(blueprint_id)

    def create_version(
        self,
        *,
        blueprint_id: str,
        shot_count: int | None = None,
        change_reason: str = "storyboard_regeneration",
        preserve_locked_shots: bool = True,
    ) -> dict[str, Any]:
        blueprint = self._require_blueprint(blueprint_id)
        if blueprint.locked:
            raise StateError("Storyboard blueprint is locked", stage="storyboard_version_create")
        source_version = (
            self.storage.get_storyboard_blueprint_version(blueprint.current_version_id)
            if blueprint.current_version_id
            else None
        )
        if source_version is None or source_version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Current storyboard version not found", stage="storyboard_version_create")
        source_shots = self.storage.list_storyboard_shots(blueprint.blueprint_id, source_version.version_id)
        scene = self._get_scene(blueprint.project_id, blueprint.scene_id)
        if scene is None:
            raise StateError("Scene not found", stage="storyboard_version_create")

        versions = self.storage.list_storyboard_blueprint_versions(blueprint.blueprint_id)
        version_number = max((item.version_number for item in versions), default=0) + 1
        version_id = f"sbv_{uuid4().hex[:12]}"
        provenance = self._build_provenance(blueprint.project_id, blueprint.scene_id, scene)
        inspection = StoryboardBlueprintInspection(
            blueprint_id=blueprint.blueprint_id,
            version_id=version_id,
            render_readiness="ready",
            provenance=provenance,
        )
        version = StoryboardBlueprintVersion(
            version_id=version_id,
            blueprint_id=blueprint.blueprint_id,
            project_id=blueprint.project_id,
            scene_id=blueprint.scene_id,
            version_number=version_number,
            status=StoryboardBlueprintStatus.DRAFT,
            change_reason=change_reason,
            source_version_id=source_version.version_id,
            provenance=provenance,
            inspection=inspection,
        )

        if shot_count is None and source_shots:
            shots = [
                self._clone_shot_for_version(
                    shot,
                    version_id=version_id,
                    preserve_lock=preserve_locked_shots,
                )
                for shot in source_shots
            ]
        else:
            shots = self._build_initial_shots(
                project_id=blueprint.project_id,
                scene_id=blueprint.scene_id,
                scene=scene,
                blueprint_id=blueprint.blueprint_id,
                version_id=version_id,
                requested_shot_count=shot_count,
            )
            if preserve_locked_shots:
                generated_by_id = {shot.shot_id: shot for shot in shots}
                for source_shot in source_shots:
                    if not source_shot.locked:
                        continue
                    generated_by_id[source_shot.shot_id] = self._clone_shot_for_version(
                        source_shot,
                        version_id=version_id,
                        preserve_lock=True,
                    )
                shots = sorted(generated_by_id.values(), key=lambda item: (item.shot_number, item.shot_id))
                for position, shot in enumerate(shots, start=1):
                    shot.shot_number = position

        # Carry explicit dialogue choices into revisions; removed shot IDs remain
        # visible as unassigned in scene direction rather than losing the lines.
        if "scene_direction" in source_version.metadata:
            from copy import deepcopy
            version.metadata["scene_direction"] = deepcopy(source_version.metadata["scene_direction"])
            for shot in shots:
                if shot.locked:
                    continue
                shot.render_contract.structured_parameters["dialogue_lines"] = [
                    line for line in version.metadata["scene_direction"]["dialogue"] if line.get("shot_id") == shot.shot_id
                ]

        superseded_version = None
        if source_version.status in {
            StoryboardBlueprintStatus.DRAFT,
            StoryboardBlueprintStatus.NEEDS_REVIEW,
        }:
            superseded_version = source_version.model_copy(deep=True)
            superseded_version.status = StoryboardBlueprintStatus.SUPERSEDED

        blueprint.current_version_id = version.version_id
        blueprint.status = StoryboardBlueprintStatus.DRAFT
        blueprint.updated_at = utc_now_iso()
        blueprint.metadata = {
            key: value
            for key, value in (blueprint.metadata or {}).items()
            if key != "continuity_review"
        }
        blueprint.metadata["preserve_locked_shots"] = preserve_locked_shots
        self._persist_version_bundle(
            blueprint=blueprint,
            version=version,
            shots=shots,
            superseded_version=superseded_version,
        )
        self._carry_forward_and_derive(shots)
        self._sync_scene_memory(blueprint.project_id, blueprint.scene_id, shots, approved=False)
        return self.get_blueprint_detail(project_id=blueprint.project_id, scene_id=blueprint.scene_id)

    def list_project_blueprints(self, project_id: str) -> list[dict[str, Any]]:
        if not project_id.strip():
            raise ValidationError("project_id is required", stage="storyboard_blueprint_list")
        rows = []
        for blueprint in self.storage.list_storyboard_blueprints(project_id):
            shots = self.storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id)
            rows.append(
                {
                    "blueprint_id": blueprint.blueprint_id,
                    "project_id": blueprint.project_id,
                    "scene_id": blueprint.scene_id,
                    "current_version_id": blueprint.current_version_id,
                    "approved_version_id": blueprint.approved_version_id,
                    "status": blueprint.status.value if hasattr(blueprint.status, "value") else blueprint.status,
                    "locked": blueprint.locked,
                    "shot_count": len(shots),
                    "ready_shot_count": sum(
                        1
                        for shot in shots
                        if str(shot.render_contract.render_readiness) == "ready"
                    ),
                    "storyboard_image": next(
                        (shot.storyboard_image_url for shot in shots if shot.storyboard_image_url),
                        None,
                    ),
                    "updated_at": blueprint.updated_at,
                }
            )
        return rows

    def project_wall_projection(self, project_id: str) -> list[dict[str, Any]]:
        """Return the legacy wall shape derived from canonical current versions."""
        if not project_id.strip():
            raise ValidationError("project_id is required", stage="storyboard_wall")
        projection: list[dict[str, Any]] = []
        for blueprint in self.storage.list_storyboard_blueprints(project_id):
            if not blueprint.current_version_id:
                continue
            for shot in self.storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id):
                projection.append(
                    {
                        "shot_id": shot.shot_id,
                        "scene_id": shot.scene_id,
                        "description": shot.intent.narrative_function or shot.intent.purpose,
                        "camera_angle": shot.visual_plan.camera_angle or shot.visual_plan.framing,
                        "status": shot.status.value if hasattr(shot.status, "value") else shot.status,
                        "storyboard_image": shot.storyboard_image_url,
                        "storyboard_shot_id": shot.storyboard_shot_id,
                        "blueprint_id": shot.blueprint_id,
                        "version_id": shot.version_id,
                        "shot_number": shot.shot_number,
                        "canonical": True,
                    }
                )
        projection.sort(key=lambda row: (str(row["scene_id"]), int(row["shot_number"]), str(row["shot_id"])))
        return projection

    def backfill_project_blueprints(
        self,
        *,
        project_id: str,
        shot_count: int | None = None,
        preserve_locked_shots: bool = True,
    ) -> dict[str, Any]:
        if not project_id.strip():
            raise ValidationError("project_id is required", stage="storyboard_blueprint_backfill")
        scene_ids = self._list_project_scene_ids(project_id)
        created: list[dict[str, Any]] = []
        existing: list[dict[str, Any]] = []
        for scene_id in scene_ids:
            current = self.storage.get_storyboard_blueprint(project_id, scene_id)
            detail = self.get_or_create_blueprint(
                project_id=project_id,
                scene_id=scene_id,
                shot_count=shot_count,
                change_reason="project_storyboard_backfill",
                preserve_locked_shots=preserve_locked_shots,
            )
            summary = {
                "scene_id": scene_id,
                "blueprint_id": detail["blueprint"].blueprint_id,
                "version_id": detail["version"].version_id if detail.get("version") else None,
                "shot_count": len(detail.get("shots") or []),
                "status": detail["blueprint"].status.value
                if hasattr(detail["blueprint"].status, "value")
                else detail["blueprint"].status,
            }
            if current:
                existing.append(summary)
            else:
                created.append(summary)
        return {
            "project_id": project_id,
            "scene_count": len(scene_ids),
            "created": created,
            "existing": existing,
        }

    def approve_version(
        self,
        *,
        blueprint_id: str,
        version_id: str,
        approved_by: str = "creator",
        approval_actor_authenticated: bool = False,
    ) -> dict[str, Any]:
        blueprint = self.storage.get_storyboard_blueprint_by_id(blueprint_id)
        if blueprint is None:
            raise StateError("Storyboard blueprint not found", stage="storyboard_blueprint_approve")
        version = self.storage.get_storyboard_blueprint_version(version_id)
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Storyboard version not found", stage="storyboard_blueprint_approve")
        shots = self.storage.list_storyboard_shots(blueprint.blueprint_id, version_id)
        if not shots:
            raise ValidationError("Storyboard version has no shots", stage="storyboard_blueprint_approve")
        blockers = [
            blocker
            for shot in shots
            for blocker in shot.render_contract.render_blockers
        ]
        if blockers:
            raise ValidationError(
                "Storyboard version has render blockers",
                stage="storyboard_blueprint_approve",
                metadata={"blockers": blockers},
            )
        review = self._continuity_review_from_metadata(blueprint.metadata, version_id)
        if not review or review.get("status") != "completed":
            raise ValidationError(
                "Run Continuity Review before approving storyboard blueprint",
                stage="storyboard_blueprint_approve",
                metadata={"blueprint_id": blueprint_id, "version_id": version_id},
            )
        # D4 length gate: BLOCK board approval while any shot's image prompt
        # is missing, stale, unapproved, or over the Runway limit. The
        # canonical prompt's length never blocks approval.
        image_gate = self._image_prompt_service().gate_for_version(shots)
        if not image_gate["approved"]:
            raise ValidationError(
                image_gate["message"],
                stage="storyboard_blueprint_approve",
                metadata={"not_ready": image_gate["not_ready"]},
            )

        now = utc_now_iso()
        version.status = StoryboardBlueprintStatus.APPROVED
        version.approved_at = now
        version.approved_by = approved_by
        version.metadata = dict(version.metadata or {})
        version.metadata["production_approval"] = {
            "actor_id": approved_by,
            "actor_authenticated": bool(approval_actor_authenticated),
        }
        blueprint.status = StoryboardBlueprintStatus.APPROVED
        blueprint.approved_version_id = version.version_id
        blueprint.current_version_id = version.version_id
        blueprint.updated_at = now
        self.storage.save_storyboard_blueprint_version(version)
        self.storage.save_storyboard_blueprint(blueprint)
        for shot in shots:
            shot.status = StoryboardShotStatus.APPROVED
            shot.updated_at = now
            self.storage.save_storyboard_shot(shot)
        self._sync_scene_memory(blueprint.project_id, blueprint.scene_id, shots, approved=True)
        return self.get_blueprint_detail(project_id=blueprint.project_id, scene_id=blueprint.scene_id)

    def run_continuity_review(
        self,
        *,
        blueprint_id: str,
        version_id: str | None = None,
        reviewer: str = "continuity_intelligence",
    ) -> dict[str, Any]:
        started = perf_counter()
        blueprint = self.storage.get_storyboard_blueprint_by_id(blueprint_id)
        if blueprint is None:
            raise StateError("Storyboard blueprint not found", stage="storyboard_continuity_review")
        active_version_id = version_id or blueprint.current_version_id
        if not active_version_id:
            raise StateError("Storyboard version not found", stage="storyboard_continuity_review")
        version = self.storage.get_storyboard_blueprint_version(active_version_id)
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Storyboard version not found", stage="storyboard_continuity_review")
        shots = self.storage.list_storyboard_shots(blueprint.blueprint_id, active_version_id)
        if not shots:
            raise ValidationError("Storyboard version has no shots", stage="storyboard_continuity_review")

        continuity_graph = self._load_continuity_graph(blueprint.project_id)
        issues = self._build_storyboard_continuity_issues(shots, continuity_graph)
        issue_counts = {
            "high": sum(1 for issue in issues if issue["severity"] == "high"),
            "medium": sum(1 for issue in issues if issue["severity"] == "medium"),
            "low": sum(1 for issue in issues if issue["severity"] == "low"),
        }
        reviewed_at = utc_now_iso()
        report = {
            "review_id": f"scr_{uuid4().hex[:12]}",
            "blueprint_id": blueprint.blueprint_id,
            "version_id": active_version_id,
            "project_id": blueprint.project_id,
            "scene_id": blueprint.scene_id,
            "status": "completed",
            "reviewed_at": reviewed_at,
            "reviewer": reviewer,
            "summary": {
                "shot_count": len(shots),
                "issue_count": len(issues),
                "high_count": issue_counts["high"],
                "medium_count": issue_counts["medium"],
                "low_count": issue_counts["low"],
                "readiness": "needs_creator_attention" if issue_counts["high"] else "ready_for_creator_approval",
                "advisory": self._continuity_review_advisory(issue_counts),
            },
            "issues": issues,
            "comparison_modes": ["side_by_side", "overlay", "before_after"],
            "generated_from": {
                "continuity_intelligence": bool(continuity_graph),
                "storyboard_blueprint": True,
                "semantic_memory": True,
                "director_memory": True,
                "character_memory": True,
                "project_memory": True,
            },
        }
        blueprint.metadata = {
            **(blueprint.metadata or {}),
            "continuity_review": report,
        }
        blueprint.status = StoryboardBlueprintStatus.NEEDS_REVIEW if issue_counts["high"] else StoryboardBlueprintStatus.DRAFT
        blueprint.updated_at = reviewed_at
        version.metadata = {
            **(version.metadata or {}),
            "continuity_review": report,
        }
        self.storage.save_storyboard_blueprint_version(version)
        self.storage.save_storyboard_blueprint(blueprint)
        logger.info(
            "project_id=%s job_id=storyboard_%s provider=internal stage=storyboard_continuity_review duration_ms=%d",
            blueprint.project_id,
            blueprint.scene_id,
            int((perf_counter() - started) * 1000),
        )
        return report

    def lock_shot(self, *, blueprint_id: str, storyboard_shot_id: str, locked: bool) -> StoryboardShot:
        _, _, shot = self._require_current_editable_shot(
            blueprint_id,
            storyboard_shot_id,
            stage="storyboard_shot_lock",
            allow_locked=True,
        )
        shot.locked = bool(locked)
        shot.status = StoryboardShotStatus.LOCKED if locked else StoryboardShotStatus.READY
        shot.updated_at = utc_now_iso()
        self.storage.save_storyboard_shot(shot)
        return shot

    def create_shot(
        self,
        *,
        blueprint_id: str,
        shot_id: str | None = None,
        intent: dict[str, Any] | None = None,
        visual_plan: dict[str, Any] | None = None,
        continuity_plan: dict[str, Any] | None = None,
        render_contract: dict[str, Any] | None = None,
        change_reason: str = "creator_shot_create",
    ) -> StoryboardShot:
        blueprint, version = self._require_current_editable_blueprint(
            blueprint_id,
            stage="storyboard_shot_create",
        )
        current = self.storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)
        stable_shot_id = str(shot_id or f"{blueprint.scene_id}_shot_{uuid4().hex[:8]}").strip()
        if not stable_shot_id:
            raise ValidationError("shot_id is required", stage="storyboard_shot_create")
        if any(shot.shot_id == stable_shot_id for shot in current):
            raise StateError("Storyboard shot_id already exists in this version", stage="storyboard_shot_create")

        contract = StoryboardShotRenderContract(**(render_contract or {}))
        if not contract.provider_neutral_prompt.strip():
            contract.render_readiness = "not_ready"
            contract.render_blockers = list(dict.fromkeys([
                *contract.render_blockers,
                "Provider-neutral prompt is required",
            ]))
        contract.provenance = {
            **contract.provenance,
            "blueprint_id": blueprint.blueprint_id,
            "version_id": version.version_id,
            "shot_id": stable_shot_id,
        }
        now = utc_now_iso()
        shot = StoryboardShot(
            storyboard_shot_id=f"sbs_{uuid4().hex[:12]}",
            blueprint_id=blueprint.blueprint_id,
            version_id=version.version_id,
            project_id=blueprint.project_id,
            scene_id=blueprint.scene_id,
            shot_id=stable_shot_id,
            shot_number=len(current) + 1,
            status=StoryboardShotStatus.READY,
            intent=StoryboardShotIntent(**(intent or {})),
            visual_plan=StoryboardShotVisualPlan(**(visual_plan or {})),
            continuity_plan=StoryboardShotContinuityPlan(**(continuity_plan or {})),
            render_contract=contract,
            rationale=str((intent or {}).get("rationale") or ""),
            created_at=now,
            updated_at=now,
            metadata={"last_change_reason": change_reason},
        )
        self.storage.save_storyboard_shot(shot)
        self._sync_scene_memory(shot.project_id, shot.scene_id, [shot], approved=False)
        return shot

    def delete_shot(self, *, blueprint_id: str, storyboard_shot_id: str) -> list[StoryboardShot]:
        blueprint, version, shot = self._require_current_editable_shot(
            blueprint_id,
            storyboard_shot_id,
            stage="storyboard_shot_delete",
        )
        current = self.storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)
        if len(current) <= 1:
            raise ValidationError("Storyboard version must keep at least one shot", stage="storyboard_shot_delete")
        delete = getattr(self.storage, "delete_storyboard_shot", None)
        if not callable(delete) or not delete(shot.storyboard_shot_id, version.version_id):
            raise PersistenceError("Storyboard shot deletion failed", stage="storyboard_shot_delete")
        remaining = [item for item in current if item.storyboard_shot_id != shot.storyboard_shot_id]
        return self.reorder_shots(
            blueprint_id=blueprint.blueprint_id,
            ordered_storyboard_shot_ids=[item.storyboard_shot_id for item in remaining],
        )

    def reorder_shots(
        self,
        *,
        blueprint_id: str,
        ordered_storyboard_shot_ids: list[str],
    ) -> list[StoryboardShot]:
        blueprint, version = self._require_current_editable_blueprint(
            blueprint_id,
            stage="storyboard_shot_reorder",
        )
        current = self.storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)
        ordered = [str(value).strip() for value in ordered_storyboard_shot_ids]
        if any(not value for value in ordered) or len(ordered) != len(set(ordered)):
            raise ValidationError("Storyboard reorder contains invalid or duplicate shot IDs", stage="storyboard_shot_reorder")
        current_ids = [shot.storyboard_shot_id for shot in current]
        if set(ordered) != set(current_ids) or len(ordered) != len(current_ids):
            raise ValidationError(
                "Storyboard reorder must contain every current shot exactly once",
                stage="storyboard_shot_reorder",
            )
        old_positions = {storyboard_shot_id: index for index, storyboard_shot_id in enumerate(current_ids)}
        new_positions = {storyboard_shot_id: index for index, storyboard_shot_id in enumerate(ordered)}
        moved_locked = [
            shot.storyboard_shot_id
            for shot in current
            if shot.locked and old_positions[shot.storyboard_shot_id] != new_positions[shot.storyboard_shot_id]
        ]
        if moved_locked:
            raise StateError(
                "Locked storyboard shots cannot be reordered",
                stage="storyboard_shot_reorder",
                metadata={"storyboard_shot_ids": moved_locked},
            )
        reorder = getattr(self.storage, "reorder_storyboard_shots", None)
        if not callable(reorder):
            raise PersistenceError("Storyboard shot reorder is unavailable", stage="storyboard_shot_reorder")
        try:
            reorder(version.version_id, ordered)
        except ValueError as exc:
            raise ValidationError(str(exc), stage="storyboard_shot_reorder") from exc
        return self.storage.list_storyboard_shots(blueprint.blueprint_id, version.version_id)

    def update_shot(
        self,
        *,
        blueprint_id: str,
        storyboard_shot_id: str,
        intent: dict[str, Any] | None = None,
        visual_plan: dict[str, Any] | None = None,
        continuity_plan: dict[str, Any] | None = None,
        render_contract: dict[str, Any] | None = None,
        change_reason: str = "shot_update",
    ) -> StoryboardShot:
        _, _, shot = self._require_current_editable_shot(
            blueprint_id,
            storyboard_shot_id,
            stage="storyboard_shot_update",
        )
        if intent:
            shot.intent = shot.intent.model_copy(update=intent)
        if visual_plan:
            shot.visual_plan = shot.visual_plan.model_copy(update=visual_plan)
        if continuity_plan:
            shot.continuity_plan = shot.continuity_plan.model_copy(update=continuity_plan)
        if render_contract:
            shot.render_contract = shot.render_contract.model_copy(update=render_contract)
            if "provider_neutral_prompt" in render_contract:
                shot.metadata = {
                    **(shot.metadata or {}),
                    "canonical_hand_edited_at": utc_now_iso(),
                }
        shot.metadata = {**(shot.metadata or {}), "last_change_reason": change_reason}
        shot.status = StoryboardShotStatus.READY
        shot.updated_at = utc_now_iso()
        self.storage.save_storyboard_shot(shot)
        self._sync_scene_memory(shot.project_id, shot.scene_id, [shot], approved=False)
        return shot

    def rebuild_shot_prompts(
        self,
        *,
        blueprint_id: str,
        version_id: str,
        confirmed_shot_ids: list[str] | None = None,
        rebuilt_by: str = "creator",
    ) -> dict[str, Any]:
        """Rebuild canonical prompts with the current prompt builder (explicit only).

        - Approved version: clones to exactly ONE new draft; the approved
          version is never touched.
        - Current draft version: updates shots in place (no new version).
        - Non-current versions are refused.
        - Hand-edited shots (``canonical_hand_edited_at`` marker) are skipped.
        - Shots whose stored text cannot be proven machine-built
          (``builder_output_sha256`` missing or mismatched) require an
          explicit per-shot confirm (``confirmed_shot_ids``, by ``shot_id``).
        - Shots whose scoped locked block resolves empty are refused loudly
          and never written.
        Only ``provider_neutral_prompt`` (plus rebuild bookkeeping in
        ``metadata``) changes; cameras, coverage, and structured parameters
        are preserved by construction.
        """
        from app.services.shot_prompt_builder import locked_appearance_characters

        blueprint = self._require_blueprint(blueprint_id)
        if blueprint.locked:
            raise StateError("Storyboard blueprint is locked", stage="storyboard_prompt_rebuild")
        version = self.storage.get_storyboard_blueprint_version(version_id)
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Storyboard version not found", stage="storyboard_prompt_rebuild")
        if blueprint.current_version_id != version.version_id:
            raise StateError(
                "Prompt rebuild runs only on the current version", stage="storyboard_prompt_rebuild"
            )
        confirmed = {str(item or "").strip() for item in (confirmed_shot_ids or []) if str(item or "").strip()}
        target_version_id = version.version_id
        cloned_from_version_id: str | None = None
        if version.status == StoryboardBlueprintStatus.APPROVED:
            created = self.create_version(blueprint_id=blueprint.blueprint_id, change_reason="prompt_rebuild")
            target_version_id = str(created["version"].version_id)
            cloned_from_version_id = version.version_id
            version = self.storage.get_storyboard_blueprint_version(target_version_id)
        scene = self._get_scene(blueprint.project_id, blueprint.scene_id)
        if scene is None:
            raise StateError("Scene not found", stage="storyboard_prompt_rebuild")
        shots = sorted(
            self.storage.list_storyboard_shots(blueprint.blueprint_id, target_version_id),
            key=lambda item: (item.shot_number, item.shot_id),
        )
        characters = self._project_characters_for_prompt(blueprint.project_id)
        locked = locked_appearance_characters(characters)
        try:
            reference_locks = self.storage.list_character_reference_locks(
                blueprint.project_id, lock_status=None, limit=200
            )
        except Exception:
            reference_locks = []
        reference_lock_info = [
            {
                "character_name": str(row.get("character_name") or ""),
                "lock_status": str(row.get("lock_status") or ""),
                "review_status": str(row.get("review_status") or ""),
                "reference_role": str(row.get("reference_role") or ""),
                "source_shot_id": str(row.get("source_shot_id") or ""),
            }
            for row in reference_locks
            if isinstance(row, dict)
        ]
        rebuilt: list[dict[str, Any]] = []
        skipped_hand_edited: list[str] = []
        refused_empty_block: list[str] = []
        confirm_required: list[dict[str, Any]] = []
        for shot in shots:
            current_prompt = str(shot.render_contract.provider_neutral_prompt or "")
            current_sha = _prompt_sha256(current_prompt)
            if (shot.metadata or {}).get("canonical_hand_edited_at"):
                logger.info(
                    "PROMPT_REBUILD_SKIPPED | reason=hand_edited | shot=%s",
                    shot.shot_id,
                )
                skipped_hand_edited.append(shot.shot_id)
                continue
            stored_hash = str((shot.metadata or {}).get("builder_output_sha256") or "")
            machine_built = bool(stored_hash) and stored_hash == current_sha
            new_text = self._build_provider_neutral_prompt(
                blueprint.project_id,
                scene,
                shot.shot_id,
                shot.shot_number,
                len(shots),
                shot.visual_plan,
                shot.rationale,
            )
            if locked and "Locked appearance" not in new_text:
                logger.warning(
                    "PROMPT_REBUILD_REFUSED | reason=empty_locked_block | shot=%s",
                    shot.shot_id,
                )
                refused_empty_block.append(shot.shot_id)
                continue
            if not machine_built and shot.shot_id not in confirmed:
                confirm_required.append(
                    {
                        "shot_id": shot.shot_id,
                        "storyboard_shot_id": shot.storyboard_shot_id,
                        "before_sha256": current_sha,
                        "after_sha256": _prompt_sha256(new_text),
                        "before": current_prompt,
                        "after": new_text,
                    }
                )
                continue
            tail = new_text.split("Locked appearance", 1)[1] if "Locked appearance" in new_text else ""
            tail_lower = tail.lower()
            block_characters = sorted(
                {
                    str(char.get("name") or "").strip()
                    for char in locked
                    if str(char.get("name") or "").strip()
                    and str(char.get("name") or "").strip().lower() in tail_lower
                }
            )
            shot.render_contract.provider_neutral_prompt = new_text
            shot.metadata = {
                **(shot.metadata or {}),
                "builder_output_sha256": _prompt_sha256(new_text),
                "prompt_rebuild": {
                    "rebuilt_at": utc_now_iso(),
                    "rebuilt_by": rebuilt_by,
                    "prior_sha256": current_sha,
                    "machine_built_prior": machine_built,
                    "confirmed": (not machine_built),
                    # The re-approve action must show the canonical diff, so
                    # both sides are kept on the shot (hashes alone cannot
                    # render a diff).
                    "before_prompt": current_prompt,
                    "after_prompt": new_text,
                },
            }
            shot.status = StoryboardShotStatus.READY
            shot.updated_at = utc_now_iso()
            self.storage.save_storyboard_shot(shot)
            logger.info(
                "PROMPT_REBUILT | shot=%s | block_characters=%s",
                shot.shot_id,
                block_characters,
            )
            rebuilt.append(
                {
                    "shot_id": shot.shot_id,
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "before_sha256": current_sha,
                    "after_sha256": _prompt_sha256(new_text),
                    "block_characters": block_characters,
                }
            )
        summary = {
            "blueprint_id": blueprint.blueprint_id,
            "version_id": target_version_id,
            "cloned_from_version_id": cloned_from_version_id,
            "rebuilt": rebuilt,
            "skipped_hand_edited": skipped_hand_edited,
            "refused_empty_block": refused_empty_block,
            "confirm_required": confirm_required,
            "reference_lock_info": reference_lock_info,
            "rebuilt_by": rebuilt_by,
        }
        version.metadata = {**(version.metadata or {}), "prompt_rebuild": summary}
        self.storage.save_storyboard_blueprint_version(version)
        return summary

    def generate_storyboard_image_for_scene_shot(
        self,
        *,
        project_id: str,
        scene_id: str,
        provider: str = "runway",
        shot_number: int = 1,
        storyboard_shot_id: str | None = None,
        create_revision: bool = False,
        camera_plan: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        normalized_provider = (provider or "runway").strip().lower()
        # Legacy DashScope/Qwen values route to the canonical Runway engine.
        if normalized_provider in {"qwen", "qwen-image-max", "dashscope", "wanx"}:
            normalized_provider = "runway"
        if normalized_provider not in {"runway", "gen4_image", "runway_router", "pollinations", "pollinations.ai", "legacy"}:
            raise ValidationError("provider must be one of: runway, pollinations", stage="storyboard_image_generation")
        edits = {}
        if camera_plan is not None:
            from app.models.camera_presets import StoryboardCameraPlan
            from pydantic import ValidationError as ModelValidationError
            try:
                edits = StoryboardCameraPlan.model_validate(camera_plan).model_dump(exclude_none=True)
            except ModelValidationError as exc:
                raise ValidationError("Invalid storyboard camera plan", stage="storyboard_image_generation") from exc
        detail = self.get_or_create_blueprint(project_id=project_id, scene_id=scene_id)
        shots = detail["shots"]
        safe_shot_number = max(1, int(shot_number or 1))
        shot = (
            next((item for item in shots if item.storyboard_shot_id == storyboard_shot_id), None)
            if storyboard_shot_id
            else next((item for item in shots if item.shot_number == safe_shot_number), None)
        )
        if shot is None:
            raise StateError("Storyboard shot not found", stage="storyboard_image_generation")
        if create_revision and detail["version"].status == StoryboardBlueprintStatus.APPROVED:
            if shot.locked:
                raise StateError("Storyboard shot is locked", stage="storyboard_image_generation")
            source_shot_id = shot.shot_id
            detail = self.create_version(
                blueprint_id=shot.blueprint_id,
                change_reason="storyboard_frame_revision",
                preserve_locked_shots=True,
            )
            shot = next(item for item in detail["shots"] if item.shot_id == source_shot_id)
        _, _, shot = self._require_current_editable_shot(
            shot.blueprint_id,
            shot.storyboard_shot_id,
            stage="storyboard_image_generation",
        )

        # Work on a copy so a provider failure cannot persist a half-applied plan.
        shot = shot.model_copy(deep=True)
        try:
            _gen_scene = self._get_scene(project_id, scene_id)
        except Exception:
            _gen_scene = None
        _locked_block = self._locked_block_for_scene(project_id, _gen_scene)
        if edits:
            base_prompt = shot.metadata.get("camera_plan_base_prompt")
            if base_prompt is None:
                base_prompt = shot.render_contract.provider_neutral_prompt or self._prompt_from_shot(shot, _locked_block)
            base_prompt = self._refresh_prompt_with_locked_characters(base_prompt, project_id, _gen_scene)
            if "camera" in edits:
                shot.visual_plan.camera_movement = edits["camera"].strip()
            if "framing" in edits:
                shot.visual_plan.framing = edits["framing"].strip()
            if "lens" in edits:
                shot.visual_plan.lens_language = edits["lens"].strip()
            if "focal_length" in edits:
                raw = str(edits["focal_length"]).strip()
                if raw.endswith("mm"):
                    raw = raw[:-2].strip()
                shot.visual_plan.focal_length_mm = int(raw)
            if "aperture" in edits:
                shot.visual_plan.aperture = edits["aperture"].strip()
            saved_plan = {
                "camera": shot.visual_plan.camera_movement,
                "framing": shot.visual_plan.framing,
                "lens": shot.visual_plan.lens_language,
                "focal_length": f"{shot.visual_plan.focal_length_mm}mm" if shot.visual_plan.focal_length_mm else "",
                "aperture": shot.visual_plan.aperture,
            }
            saved_plan = {key: value for key, value in saved_plan.items() if value}
            notes = "\n".join(f"{key}: {value}" for key, value in saved_plan.items())
            shot.render_contract.provider_neutral_prompt = base_prompt + ("\n\n[CREATOR CAMERA PLAN — use for this shot]\n" + notes if notes else "")
            shot.render_contract.structured_parameters["camera_plan"] = saved_plan
            shot.render_contract.structured_parameters["shot_planning"] = {
                **(shot.render_contract.structured_parameters.get("shot_planning") or {}),
                **saved_plan,
            }
            shot.metadata["camera_plan_base_prompt"] = base_prompt

        existing_seed = self.storage.get_scene_previs_seed(project_id, scene_id)
        seed = existing_seed if existing_seed is not None else random.randint(1, 999999)
        # Refresh with current locked looks: a lock approved after blueprint
        # creation must still reach the image prompt. Persist back so the
        # contract stays consistent for future renders.
        prompt = self._refresh_prompt_with_locked_characters(
            shot.render_contract.provider_neutral_prompt
            or self._prompt_from_shot(shot, _locked_block),
            project_id,
            _gen_scene,
        )
        shot.render_contract.provider_neutral_prompt = prompt
        # Persist lock anchors so the approved-board → final-render handoff
        # carries face/body refs even for text-only storyboard providers.
        try:
            _lock_refs = self._locked_reference_images_for_scene(project_id, _gen_scene)
        except Exception:
            _lock_refs = []
        if _lock_refs:
            existing_refs = list(shot.render_contract.reference_assets or [])
            for _ref in _lock_refs:
                if _ref not in existing_refs:
                    existing_refs.append(_ref)
            shot.render_contract.reference_assets = existing_refs[:9]
        normalized_provider = (provider or "runway").strip().lower()
        if normalized_provider in {"qwen", "qwen-image-max", "dashscope", "wanx"}:
            normalized_provider = "runway"
        provider_used = "runway"
        model_used = "gen4_image"

        # D4: the Runway promptText is ALWAYS the approved image prompt, never
        # the canonical text. Fail closed BEFORE any provider call. Legacy
        # Pollinations path keeps its previous behavior.
        render_prompt = prompt
        if normalized_provider in {"runway", "gen4_image", "runway_router"}:
            try:
                render_prompt = self._image_prompt_service().approved_prompt_for_shot(shot)
            except (StateError, ValidationError) as exc:
                logger.info(
                    "project_id=%s job_id=%s provider=runway stage=storyboard_image_generation duration_ms=%d",
                    project_id,
                    f"storyboard_{shot.shot_id}_runway",
                    int((perf_counter() - started) * 1000),
                )
                raise StateError(
                    str(getattr(exc, "message", str(exc))),
                    stage="storyboard_image_generation",
                ) from exc
        if normalized_provider in {"pollinations", "pollinations.ai", "legacy"}:
            encoded = urllib.parse.quote(prompt)
            image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=432&nologo=true&seed={seed}"
            provider_used = "pollinations"
            model_used = "pollinations.ai"
            fallback = True
            reference_images_attached = False
        elif normalized_provider in {"runway", "gen4_image", "runway_router"}:
            from app.services.storyboard_image_service import storyboard_image_service

            output_root = Path(__file__).resolve().parents[2] / "outputs" / "previs"
            result = storyboard_image_service.generate_runway_image(
                project_id=project_id,
                scene_id=shot.shot_id,
                prompt=render_prompt,
                output_root=output_root,
                reference_image_urls=_lock_refs,
                aspect_ratio="16:9",
                seed=seed,
            )
            image_url = result.image_url
            provider_used = result.provider
            model_used = result.model
            fallback = False
            reference_images_attached = bool(_lock_refs)
        else:
            raise ValidationError(
                "provider must be one of: runway, pollinations",
                stage="storyboard_image_generation",
            )

        job_id = f"storyboard_{shot.shot_id}_{provider_used}"
        self.storage.save_previs_image(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot.shot_id,
            image_path=image_url,
            job_id=job_id,
            status="complete",
            prompt_used=prompt,
            fallback=fallback,
            previs_seed=seed,
            seed_locked=existing_seed is not None,
        )
        shot.storyboard_image_url = image_url
        shot.render_contract.seed = seed
        shot.render_contract.seed_locked = existing_seed is not None
        shot.status = StoryboardShotStatus.READY
        shot.updated_at = utc_now_iso()
        self.storage.save_storyboard_shot(shot)
        self._sync_legacy_storyboard_projection(project_id, scene_id, shot, image_url, seed)

        from app.services.storyboard_image_service import storyboard_image_service

        image_state = storyboard_image_service.classify_image_url(image_url)
        logger.info(
            "project_id=%s job_id=%s provider=%s stage=storyboard_image_generation duration_ms=%d",
            project_id, job_id, provider_used, int((perf_counter() - started) * 1000),
        )
        try:
            readiness = self.get_consistency_readiness(project_id, scene_id)
        except Exception:
            readiness = {"locked": [], "unlocked": [], "missing_face_reference": [], "scene_cast": [], "warnings": []}
        return {
            "image_url": image_url,
            "status": "complete",
            "seed": seed,
            "provider": provider_used,
            "model": model_used,
            "image_state": image_state.state,
            "retryable": image_state.retryable,
            "message": image_state.message,
            "scene_id": scene_id,
            "shot_id": shot.shot_id,
            "shot_number": safe_shot_number,
            "job_id": job_id,
            "blueprint_id": shot.blueprint_id,
            "storyboard_shot_id": shot.storyboard_shot_id,
            "version_id": shot.version_id,
            "reference_images_used": _lock_refs,
            "reference_images_attached": reference_images_attached if "reference_images_attached" in locals() else False,
            "locked_characters_used": readiness.get("locked", []),
            "consistency_warnings": readiness.get("warnings", []),
        }

    def build_render_contract(self, *, blueprint_id: str, storyboard_shot_id: str) -> StoryboardShotRenderContract:
        shot = self.storage.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.blueprint_id != blueprint_id:
            raise StateError("Storyboard shot not found", stage="storyboard_render_contract_build")
        return shot.render_contract

    def render_storyboard_shot(
        self,
        *,
        blueprint_id: str,
        storyboard_shot_id: str,
        provider: str | None = None,
        render_service: Any | None = None,
        link_type: str = "initial_render",
    ) -> Any:
        from app.services.render import render_service as default_render_service

        shot = self.storage.get_storyboard_shot(storyboard_shot_id)
        self._validate_shot_renderable(
            shot=shot,
            blueprint_id=blueprint_id,
            stage="storyboard_shot_render",
        )
        svc = render_service or default_render_service
        from app.services.storyboard_render_inputs import storyboard_render_inputs
        inputs = storyboard_render_inputs(shot)
        parameters = inputs["parameters"]
        parameters["storyboard"] = self._storyboard_metadata_for_shot(shot)
        if shot.render_contract.seed is not None:
            parameters.setdefault("seed", shot.render_contract.seed)
        send_prompt = shot.render_contract.provider_neutral_prompt
        if str(provider or "").strip().lower() in {"runway", "gen4_image", "runway_router"}:
            # Runway-family renders send ONLY the approved, hash-linked image
            # prompt — never the board's provider_neutral_prompt. Missing,
            # stale, unapproved, or over-limit prompts fail closed here via
            # StateError before any job exists.
            send_prompt = self._image_prompt_service().approved_prompt_for_shot(shot)
        job = svc.create_job(
            project_id=shot.project_id,
            shot_id=shot.shot_id,
            provider=provider,
            prompt=send_prompt,
            reference_assets=inputs["reference_assets"],
            parameters=parameters,
        )
        self.link_render_job(shot=shot, render_job_id=job.id, link_type=link_type)
        return job

    def scene_render_inputs(self, project_id: str, scene_id: str) -> list[dict] | None:
        """Use the current approved version, or signal that no blueprint exists."""
        from app.services.storyboard_render_inputs import storyboard_render_inputs

        blueprint = self.storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None:
            return None
        if not blueprint.approved_version_id or blueprint.current_version_id != blueprint.approved_version_id:
            raise StateError("Approve the current storyboard version before rendering this scene", stage="scene_pipeline_storyboard")
        shots = self.storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.approved_version_id)
        if not shots:
            raise StateError("Approved storyboard has no shots", stage="scene_pipeline_storyboard")
        result = []
        for shot in sorted(shots, key=lambda item: item.shot_number):
            self._validate_shot_renderable(shot=shot, blueprint_id=blueprint.blueprint_id, stage="scene_pipeline_storyboard")
            inputs = storyboard_render_inputs(shot)
            inputs["parameters"]["storyboard"] = {**self._storyboard_metadata_for_shot(shot), "link_type": "scene_pipeline_render"}
            result.append({**inputs, "scene_id": shot.scene_id, "shot_id": shot.shot_id,
                           "character_focus": list(shot.intent.character_focus or []),
                           "duration_seconds": shot.render_contract.duration_seconds,
                           "shot_number": shot.shot_number, "storyboard_shot_id": shot.storyboard_shot_id})
        return result

    def _validate_shot_renderable(
        self,
        *,
        shot: StoryboardShot | None,
        blueprint_id: str,
        stage: str,
    ) -> None:
        if shot is None or shot.blueprint_id != blueprint_id:
            raise StateError("Storyboard shot not found", stage=stage)
        blueprint = self.storage.get_storyboard_blueprint_by_id(blueprint_id)
        if blueprint is None or blueprint.blueprint_id != shot.blueprint_id:
            raise StateError("Storyboard blueprint not found", stage=stage)
        version = self.storage.get_storyboard_blueprint_version(shot.version_id)
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Storyboard version not found", stage=stage)

        approved_version_id = str(blueprint.approved_version_id or "").strip()
        current_version_id = str(blueprint.current_version_id or "").strip()
        if not approved_version_id:
            raise ValidationError(
                "Approve storyboard version before rendering storyboard shot",
                stage=stage,
                metadata={
                    "blueprint_id": blueprint.blueprint_id,
                    "version_id": shot.version_id,
                    "storyboard_shot_id": shot.storyboard_shot_id,
                },
            )
        if shot.version_id != approved_version_id or shot.version_id != current_version_id:
            raise StateError(
                "Storyboard shot belongs to a stale storyboard version",
                stage=stage,
                metadata={
                    "blueprint_id": blueprint.blueprint_id,
                    "current_version_id": current_version_id,
                    "approved_version_id": approved_version_id,
                    "shot_version_id": shot.version_id,
                    "storyboard_shot_id": shot.storyboard_shot_id,
                },
            )
        if version.status != StoryboardBlueprintStatus.APPROVED:
            raise ValidationError(
                "Approve storyboard version before rendering storyboard shot",
                stage=stage,
                metadata={
                    "blueprint_id": blueprint.blueprint_id,
                    "version_id": version.version_id,
                    "status": version.status.value if hasattr(version.status, "value") else version.status,
                },
            )
        if shot.status not in {
            StoryboardShotStatus.APPROVED,
            StoryboardShotStatus.LOCKED,
            StoryboardShotStatus.RENDERED,
        }:
            raise ValidationError(
                "Approve storyboard shot before rendering",
                stage=stage,
                metadata={
                    "blueprint_id": blueprint.blueprint_id,
                    "version_id": version.version_id,
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "status": shot.status.value if hasattr(shot.status, "value") else shot.status,
                },
            )
        blockers = list(shot.render_contract.render_blockers or [])
        if blockers:
            raise ValidationError(
                "Storyboard shot has render blockers",
                stage=stage,
                metadata={
                    "blueprint_id": blueprint.blueprint_id,
                    "version_id": version.version_id,
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "blockers": blockers,
                },
            )

    def link_render_job(self, *, shot: StoryboardShot, render_job_id: str, link_type: str = "initial_render") -> StoryboardRenderLink:
        link = StoryboardRenderLink(
            link_id=f"sbrl_{uuid4().hex[:12]}",
            project_id=shot.project_id,
            scene_id=shot.scene_id,
            shot_id=shot.shot_id,
            storyboard_shot_id=shot.storyboard_shot_id,
            blueprint_id=shot.blueprint_id,
            version_id=shot.version_id,
            render_job_id=render_job_id,
            link_type=link_type,
        )
        self.storage.save_storyboard_render_link(link)
        return link

    def link_revision_from_job(
        self,
        *,
        project_id: str,
        revision_id: str,
        original_job: Any,
        change_scope: dict[str, Any] | None = None,
    ) -> StoryboardRevisionLink | None:
        parameters = getattr(getattr(original_job, "input_payload", None), "parameters", {}) or {}
        storyboard_meta = parameters.get("storyboard") if isinstance(parameters, dict) else None
        if not isinstance(storyboard_meta, dict):
            links = self.storage.list_storyboard_render_links(
                project_id=project_id,
                render_job_id=getattr(original_job, "id", ""),
            )
            storyboard_meta = links[0] if links else None
        if not isinstance(storyboard_meta, dict):
            return None
        version_id = str(storyboard_meta.get("version_id") or "").strip()
        if not version_id:
            return None
        shot_id = str(getattr(original_job, "shot_id", "") or storyboard_meta.get("shot_id") or "").strip()
        scene_id = derive_scene_id_from_shot_id(shot_id)
        link = StoryboardRevisionLink(
            link_id=f"sbrv_{uuid4().hex[:12]}",
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            revision_id=revision_id,
            original_version_id=version_id,
            change_scope=change_scope or {},
            metadata={"original_job_id": getattr(original_job, "id", "")},
        )
        self.storage.save_storyboard_revision_link(link)
        return link

    def _build_initial_shots(
        self,
        *,
        project_id: str,
        scene_id: str,
        scene: dict[str, Any],
        blueprint_id: str,
        version_id: str,
        requested_shot_count: int | None,
    ) -> list[StoryboardShot]:
        plan = self.shot_sequence_service.build_shot_sequence_plan(scene_id, scene)
        candidates = self.shot_sequence_service.build_shot_candidates_from_plan(scene_id, [], plan)
        if requested_shot_count and requested_shot_count > 0:
            candidates = candidates[:requested_shot_count]
        if not candidates:
            candidates = [{"shot_id": f"{scene_id}_shot_001", "order": 1, "shot_type": "establishing_shot"}]

        previs_by_shot = {
            str(row.get("shot_id") or ""): row
            for row in self.storage.load_previs_images(project_id, scene_id)
            if isinstance(row, dict)
        }
        shots: list[StoryboardShot] = []
        for index, candidate in enumerate(candidates, start=1):
            shot_id = str(candidate.get("shot_id") or f"{scene_id}_shot_{index:03d}").strip()
            if shot_id.startswith(f"shot_{scene_id}_"):
                shot_id = f"{scene_id}_shot_{index:03d}"
            rationale_payload = self.shot_rationale_service.get_rationale(project_id, scene_id, scene)
            rationale = str(rationale_payload.get("rationale") or "")
            # Candidate ids are edit grammar ("match_cut", "bridge_action"),
            # not camera moves and not provider-readable framing. Map to
            # human-readable plan language so the image prompt carries the
            # actual shot recommendation instead of raw ids the model ignores.
            _framing_map = {
                "establishing_shot": "Wide establishing shot. Camera far back. Full environment visible.",
                "medium_shot": "Medium shot. Characters from waist up. Action and dialogue beginning.",
                "close_up": "Medium close-up. Character faces and upper body. Emotional beats.",
                "transition_shot": "Dynamic medium shot showing the story transition in motion.",
                "emotional_detail_shot": "Close-up detail shot. Eyes, hands, specific objects. Intimate beat.",
            }
            _raw_framing = str(candidate.get("shot_type") or "").strip()
            _raw_camera = str(candidate.get("transition_hint") or "").strip()
            # transition_hint describes edit continuity, never a camera move —
            # sending "match_cut" as camera actively misdirects the provider.
            _camera_move = _raw_camera if " " in _raw_camera and len(_raw_camera) > 12 else ""
            visual_plan = StoryboardShotVisualPlan(
                framing=_framing_map.get(_raw_framing, _raw_framing),
                camera_movement=_camera_move,
                environment=str(scene.get("location") or scene.get("heading") or ""),
                lighting=" ".join(
                    part
                    for part in [
                        str(scene.get("time_of_day") or ""),
                        str(scene.get("emotional_tone") or ""),
                    ]
                    if part
                ),
            )
            prompt = self._build_provider_neutral_prompt(
                project_id,
                scene,
                shot_id,
                index,
                len(candidates),
                visual_plan,
                rationale,
            )
            previs = previs_by_shot.get(shot_id) or {}
            shots.append(
                StoryboardShot(
                    storyboard_shot_id=f"sbs_{uuid4().hex[:12]}",
                    blueprint_id=blueprint_id,
                    version_id=version_id,
                    project_id=project_id,
                    scene_id=scene_id,
                    shot_id=shot_id,
                    shot_number=index,
                    status=StoryboardShotStatus.READY,
                    intent=StoryboardShotIntent(
                        purpose=str(candidate.get("shot_type") or ""),
                        emotional_target=str(scene.get("emotional_tone") or ""),
                        narrative_function=str(scene.get("description") or scene.get("heading") or ""),
                        character_focus=self._scene_characters(scene),
                        rationale=rationale,
                        source_scene_text_excerpt=self._scene_text(scene)[:500],
                    ),
                    visual_plan=visual_plan,
                    continuity_plan=StoryboardShotContinuityPlan(
                        location_continuity=str(scene.get("location") or ""),
                        emotional_continuity=str(scene.get("emotional_tone") or ""),
                    ),
                    render_contract=StoryboardShotRenderContract(
                        provider_neutral_prompt=prompt,
                        prompt_components=[visual_plan.framing, visual_plan.environment, rationale],
                        structured_parameters={
                            "duration": 5,
                            "ratio": "1280:720",
                            "shot_planning": {
                                "purpose": str(candidate.get("shot_type") or ""),
                                "framing": visual_plan.framing,
                                "camera": visual_plan.camera_movement,
                                "continuity": visual_plan.environment,
                                "rationale": rationale,
                            },
                        },
                        reference_assets=[],
                        duration_seconds=5,
                        aspect_ratio="16:9",
                        render_readiness="ready",
                        provenance={
                            "blueprint_id": blueprint_id,
                            "version_id": version_id,
                            "shot_id": shot_id,
                        },
                    ),
                    storyboard_image_url=previs.get("image_path") or None,
                    previs_image_id=previs.get("id") or None,
                    rationale=rationale,
                    metadata={"builder_output_sha256": _prompt_sha256(prompt)},
                )
            )
        return shots

    @preserve_generation_facts
    def _build_provider_neutral_prompt(
        self,
        project_id: str,
        scene: dict[str, Any],
        shot_id: str,
        shot_number: int,
        shot_count: int,
        visual_plan: StoryboardShotVisualPlan,
        rationale: str,
    ) -> str:
        try:
            from app.services.shot_prompt_builder import build_shot_aware_prompt

            prompt = build_shot_aware_prompt(
                scene_data=scene,
                shot_number=shot_number,
                take_number=1,
                all_characters=self._project_characters_for_prompt(project_id),
                max_length=512,
                # This service already knows the real breakdown; passing it keeps
                # scene-text segmentation aligned with the actual shot list.
                total_shots=shot_count,
            )
        except Exception:
            prompt = ""
        # Plan grammar leads: providers weight early tokens, so framing /
        # camera / shot position come before action and character detail.
        # The locked-appearance tail is re-ensured after the join.
        plan_head = ". ".join(
            part.strip().strip(".")
            for part in [
                visual_plan.framing,
                visual_plan.camera_movement,
                visual_plan.environment,
                visual_plan.lighting,
                f"Shot {shot_number} of {shot_count}.",
            ]
            if str(part or "").strip()
        )
        parts = [plan_head, prompt, rationale]
        text = ". ".join(part.strip().strip(".") for part in parts if str(part or "").strip())
        # build_shot_aware_prompt already appends the locked block, but the join
        # above can bury it mid-prompt; ensure the enforcement tail is present
        # exactly once so it is never truncated away.
        try:
            from app.services.shot_prompt_builder import ensure_locked_appearance_in_prompt

            text = ensure_locked_appearance_in_prompt(
                text, self._project_characters_for_prompt(project_id), scene
            )
        except Exception:
            pass
        try:
            from app.services.shot_prompt_builder import clean_prompt_punctuation

            text = clean_prompt_punctuation(text)
        except Exception:
            pass
        return text

    def _build_provenance(self, project_id: str, scene_id: str, scene: dict[str, Any]) -> StoryboardBlueprintProvenance:
        provenance = StoryboardBlueprintProvenance()
        provenance.canonical_sources["scene_input"] = True
        provenance.derived_sources["shot_sequence_service"] = True
        provenance.derived_sources["shot_rationale_service"] = True
        try:
            if self.storage.load_previs_images(project_id, scene_id):
                provenance.canonical_sources["previs_images"] = True
        except Exception as exc:
            raise PersistenceError(
                "Storyboard previs provenance lookup failed",
                stage="storyboard_provenance",
                metadata={"cause": type(exc).__name__},
            ) from exc
        project = self.project_store.get_project(project_id) or {}
        if isinstance(project.get("storyboard_wall"), list):
            provenance.canonical_sources["storyboard_wall"] = True
        try:
            from app.models.crew import AgentRole
            from app.services.spine_consumption_service import spine_consumption_service

            constraints = spine_consumption_service.get_constraints_for_role(
                film_id=project_id,
                role=AgentRole.STORYBOARD_ARTIST,
            )
            if isinstance(constraints, dict) and "error" not in constraints:
                provenance.canonical_sources["creative_spine"] = True
                provenance.notes.append("Creative Spine constraints were available for storyboard planning.")
        except Exception:
            provenance.notes.append("Creative Spine context unavailable; storyboard remains editable and inspectable.")
        if scene.get("scene_id"):
            provenance.source_ids.append(str(scene["scene_id"]))
        if isinstance(scene.get("metadata"), dict) and scene["metadata"].get("fallback_scene"):
            provenance.canonical_sources["scene_input"] = False
            provenance.notes.append("Scene record was unavailable; used a minimal legacy fallback scene.")
        return provenance

    def _inspect(
        self,
        blueprint: StoryboardBlueprint,
        version: StoryboardBlueprintVersion | None,
        shots: list[StoryboardShot],
    ) -> StoryboardBlueprintInspection:
        blockers = [
            blocker
            for shot in shots
            for blocker in (shot.render_contract.render_blockers or [])
        ]
        readiness = "blocked" if blockers else "ready" if shots else "not_ready"
        provenance = version.provenance if version else StoryboardBlueprintProvenance()
        return StoryboardBlueprintInspection(
            blueprint_id=blueprint.blueprint_id,
            version_id=version.version_id if version else "",
            render_readiness=readiness,
            blockers=blockers,
            provenance=provenance,
        )

    def _continuity_review_from_metadata(self, metadata: dict[str, Any] | None, version_id: str) -> dict[str, Any] | None:
        review = (metadata or {}).get("continuity_review")
        if not isinstance(review, dict):
            return None
        if str(review.get("version_id") or "") != version_id:
            return None
        return review

    def _load_continuity_graph(self, project_id: str) -> dict[str, Any]:
        try:
            from app.services.continuity_intelligence_service import continuity_intelligence_service

            graph = continuity_intelligence_service.get_graph(project_id)
            return graph if isinstance(graph, dict) else {}
        except Exception as exc:
            logger.debug("Continuity graph unavailable for storyboard review %s: %s", project_id, exc)
            return {}

    def _build_storyboard_continuity_issues(
        self,
        shots: list[StoryboardShot],
        continuity_graph: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        ordered = sorted(shots, key=lambda shot: shot.shot_number)
        issues.extend(self._issues_from_continuity_graph(ordered, continuity_graph or {}))
        for index, shot in enumerate(ordered):
            previous = ordered[index - 1] if index > 0 else None
            continuity = shot.continuity_plan
            visual = shot.visual_plan
            intent = shot.intent
            shot_label = f"{shot.shot_number:03d}"
            previous_label = f"{previous.shot_number:03d}" if previous else None

            if not intent.emotional_target.strip():
                issues.append(
                    self._continuity_issue(
                        severity="medium",
                        category="Story Continuity",
                        shot=shot_label,
                        previous_shot=previous_label,
                        expected="An emotional goal for the shot.",
                        detected="No emotional goal is recorded.",
                        explanation="The shot can be rendered, but its emotional handoff is thin without a stated target.",
                        confidence="consistent",
                        recommendation="Add the intended emotional beat before final approval.",
                    )
                )
            if not visual.environment.strip() and not continuity.location_continuity.strip():
                issues.append(
                    self._continuity_issue(
                        severity="high",
                        category="Environment Continuity",
                        shot=shot_label,
                        previous_shot=previous_label,
                        expected="A canonical location or environment constraint.",
                        detected="No environment continuity field is available.",
                        explanation="The visual world has too little anchoring for a professional script-supervisor pass.",
                        confidence="consistent",
                        recommendation="Restore a location or production-design constraint on this shot.",
                    )
                )
            if not visual.framing.strip():
                issues.append(
                    self._continuity_issue(
                        severity="medium",
                        category="Camera Continuity",
                        shot=shot_label,
                        previous_shot=previous_label,
                        expected="A framing or shot grammar choice.",
                        detected="No framing plan is recorded.",
                        explanation="Camera progression cannot be inspected when the shot grammar is blank.",
                        confidence="consistent",
                        recommendation="Set framing before approving the canonical blueprint.",
                    )
                )
            if not shot.render_contract.provider_neutral_prompt.strip():
                issues.append(
                    self._continuity_issue(
                        severity="high",
                        category="Blueprint Consistency",
                        shot=shot_label,
                        previous_shot=previous_label,
                        expected="A provider-neutral render prompt aligned to the blueprint.",
                        detected="The render prompt is empty.",
                        explanation="Previs would receive an under-specified handoff from the storyboard stage.",
                        confidence="consistent",
                        recommendation="Rebuild the render contract from the storyboard blueprint.",
                    )
                )
            for warning in continuity.continuity_warnings:
                if str(warning).strip():
                    issues.append(
                        self._continuity_issue(
                            severity="medium",
                            category="Blueprint Consistency",
                            shot=shot_label,
                            previous_shot=previous_label,
                            expected="Continuity constraints without unresolved warnings.",
                            detected=str(warning).strip(),
                            explanation="The blueprint is already carrying a continuity warning that should be reviewed before approval.",
                            confidence="emerging",
                            recommendation="Fix the affected continuity field or mark it as an intentional creative choice.",
                        )
                    )
            if previous:
                previous_characters = set(previous.intent.character_focus)
                current_characters = set(intent.character_focus)
                if previous_characters and current_characters and previous_characters.isdisjoint(current_characters):
                    issues.append(
                        self._continuity_issue(
                            severity="low",
                            category="Blocking Continuity",
                            shot=shot_label,
                            previous_shot=previous_label,
                            expected=", ".join(sorted(previous_characters)),
                            detected=", ".join(sorted(current_characters)),
                            explanation="The character focus changes sharply between adjacent shots; this may be intentional, but it deserves a quick check.",
                            confidence="emerging",
                            recommendation="Confirm the handoff or add an entrance, exit, or reaction beat.",
                        )
                    )
                previous_location = previous.continuity_plan.location_continuity or previous.visual_plan.environment
                current_location = continuity.location_continuity or visual.environment
                if previous_location and current_location and previous_location.strip().lower() != current_location.strip().lower():
                    issues.append(
                        self._continuity_issue(
                            severity="medium",
                            category="Environment Continuity",
                            shot=shot_label,
                            previous_shot=previous_label,
                            expected=previous_location,
                            detected=current_location,
                            explanation="Adjacent shots point at different location anchors inside the same storyboard scene.",
                            confidence="consistent",
                            recommendation="Align the location field or mark the change as an intentional spatial transition.",
                        )
                    )
        return issues

    def _issues_from_continuity_graph(
        self,
        shots: list[StoryboardShot],
        continuity_graph: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_issues = continuity_graph.get("issues") or continuity_graph.get("alerts") or []
        if not isinstance(raw_issues, list):
            return []
        shot_by_id = {shot.shot_id: shot for shot in shots}
        scene_ids = {shot.scene_id for shot in shots}
        issues: list[dict[str, Any]] = []
        for raw in raw_issues:
            if not isinstance(raw, dict):
                continue
            raw_shot_id = str(raw.get("shot_id") or raw.get("source_shot_id") or raw.get("asset_id") or "").strip()
            raw_scene_id = str(raw.get("scene_id") or "").strip()
            shot = shot_by_id.get(raw_shot_id)
            if shot is None and raw_scene_id and raw_scene_id not in scene_ids:
                continue
            if shot is None and raw_shot_id and raw_shot_id not in shot_by_id:
                continue
            affected = shot or shots[0] if shots else None
            if affected is None:
                continue
            severity = str(raw.get("severity") or "medium").lower()
            if severity not in {"high", "medium", "low"}:
                severity = "medium"
            description = str(raw.get("description") or raw.get("message") or raw.get("evidence") or "Continuity Intelligence flagged this beat.").strip()
            recommendation = str(raw.get("recommendation") or raw.get("recommended_fix") or "Review this continuity signal against the canonical storyboard fields.").strip()
            issues.append(
                self._continuity_issue(
                    severity=severity,
                    category=str(raw.get("category") or raw.get("issue_type") or "Continuity Intelligence"),
                    shot=f"{affected.shot_number:03d}",
                    previous_shot=None,
                    expected=str(raw.get("expected_state") or "The project continuity graph and storyboard blueprint should agree."),
                    detected=str(raw.get("detected_state") or description),
                    explanation=description,
                    confidence=str(raw.get("confidence") or "emerging"),
                    recommendation=recommendation,
                )
            )
        return issues

    def _continuity_issue(
        self,
        *,
        severity: str,
        category: str,
        shot: str,
        previous_shot: str | None,
        expected: str,
        detected: str,
        explanation: str,
        confidence: str,
        recommendation: str,
    ) -> dict[str, Any]:
        return {
            "issue_id": f"sci_{uuid4().hex[:10]}",
            "severity": severity,
            "category": category,
            "affected_shot": shot,
            "previous_shot": previous_shot,
            "current_shot": shot,
            "expected_state": expected,
            "detected_state": detected,
            "ai_explanation": explanation,
            "confidence": confidence,
            "recommended_fix": recommendation,
            "actions": ["fix_automatically", "show_differences", "ignore", "regenerate_selected_shot"],
        }

    def _continuity_review_advisory(self, issue_counts: dict[str, int]) -> str:
        if issue_counts.get("high", 0):
            return "The storyboard is close, but one continuity risk could weaken the handoff into Previs."
        if issue_counts.get("medium", 0):
            return "Continuity mostly holds; review the flagged shot details before calling this blueprint canonical."
        if issue_counts.get("low", 0):
            return "Only soft continuity questions surfaced. The blueprint is ready for creator approval."
        return "Continuity is clean enough for the storyboard to become the canonical blueprint."

    def _sync_scene_memory(self, project_id: str, scene_id: str, shots: list[StoryboardShot], *, approved: bool) -> None:
        try:
            existing = self.storage.get_scene_memory(project_id, scene_id) or {
                "project_id": project_id,
                "scene_id": scene_id,
            }
            field = "approved_shots" if approved else "generated_shots"
            existing[field] = [
                {
                    "shot_id": shot.shot_id,
                    "storyboard_shot_id": shot.storyboard_shot_id,
                    "blueprint_id": shot.blueprint_id,
                    "version_id": shot.version_id,
                    "rationale": shot.rationale,
                }
                for shot in shots
            ]
            self.storage.save_scene_memory(existing)
        except Exception as exc:
            logger.debug("Storyboard scene memory sync skipped for %s/%s: %s", project_id, scene_id, exc)

    def _sync_legacy_storyboard_projection(
        self,
        project_id: str,
        scene_id: str,
        shot: StoryboardShot,
        image_url: str,
        seed: int,
    ) -> None:
        current = self.project_store.get_project(project_id)
        if not isinstance(current, dict):
            return
        summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        for scene in scenes:
            if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                scene["storyboard_image"] = image_url
                images = scene.get("storyboard_images") if isinstance(scene.get("storyboard_images"), dict) else {}
                images[str(shot.shot_number)] = image_url
                images[shot.shot_id] = image_url
                scene["storyboard_images"] = images
                scene["previs_seed"] = seed
                scene["updated_at"] = utc_now_iso()
        summary["scenes"] = scenes
        self.project_store.update_project(project_id, {"execution_summary": summary})

    def _storyboard_metadata_for_shot(self, shot: StoryboardShot) -> dict[str, Any]:
        metadata = {
            "blueprint_id": shot.blueprint_id,
            "version_id": shot.version_id,
            "storyboard_shot_id": shot.storyboard_shot_id,
            "project_id": shot.project_id,
            "scene_id": shot.scene_id,
            "shot_id": shot.shot_id,
            "shot_number": shot.shot_number,
        }
        # D4: pin the approved image prompt digest alongside the canonical
        # prompt metadata (same chain, existing pattern). Absent when no
        # approved image prompt exists, so existing digests are unchanged.
        try:
            from app.services.storyboard_image_prompt_service import (
                storyboard_image_prompt_service,
            )

            digest = storyboard_image_prompt_service.approved_digest_for_shot(shot)
            if digest:
                metadata["image_prompt_sha256"] = digest
        except Exception:
            pass
        return metadata

    def _prompt_from_shot(self, shot: StoryboardShot, locked_block: str = "") -> str:
        base = ". ".join(
            part
            for part in [
                shot.visual_plan.framing,
                shot.visual_plan.environment,
                shot.intent.emotional_target,
                shot.rationale,
            ]
            if part
        )
        block = str(locked_block or "").strip()
        if block and "Locked appearance" not in base:
            base = f"{base.rstrip('. ')}. {block}." if base else f"{block}."
        # Character focus is the last structured signal before free text; keep
        # it in the fallback so a blank contract never goes out character-blind.
        focus = [name for name in (shot.intent.character_focus or []) if str(name).strip()]
        if focus and not any(str(name).lower() in base.lower() for name in focus):
            cast = ", ".join(focus[:3])
            base = f"{base.rstrip('. ')}. Characters: {cast}." if base else f"Characters: {cast}."
        return base

    def _list_project_scene_ids(self, project_id: str) -> list[str]:
        seen: set[str] = set()
        scene_ids: list[str] = []

        def add_from_project(project: dict[str, Any] | None) -> None:
            if not isinstance(project, dict):
                return
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            containers = [summary.get("scenes"), project.get("scenes")]
            for container in containers:
                if not isinstance(container, list):
                    continue
                for scene in container:
                    if not isinstance(scene, dict):
                        continue
                    scene_id = str(scene.get("scene_id") or "").strip()
                    if scene_id and scene_id not in seen:
                        seen.add(scene_id)
                        scene_ids.append(scene_id)

        add_from_project(self.project_store.get_project(project_id))
        try:
            project = self.storage.get_project(project_id)
            project_data = project.model_dump(mode="json") if hasattr(project, "model_dump") else project
            add_from_project(project_data if isinstance(project_data, dict) else None)
        except Exception as exc:
            raise PersistenceError(
                "Storyboard scene ownership lookup failed",
                stage="storyboard_blueprint",
                metadata={"cause": type(exc).__name__},
            ) from exc
        if not scene_ids:
            raise StateError("Project has no scenes to backfill", stage="storyboard_blueprint_backfill")
        return scene_ids

    def _get_scene(self, project_id: str, scene_id: str) -> dict[str, Any] | None:
        current = self.project_store.get_project(project_id)
        if isinstance(current, dict):
            summary = current.get("execution_summary") if isinstance(current.get("execution_summary"), dict) else {}
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
            for scene in scenes:
                if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                    return scene
            for scene in current.get("scenes") or []:
                if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                    return scene
        try:
            project = self.storage.get_project(project_id)
            project_data = project.model_dump(mode="json") if hasattr(project, "model_dump") else project
            if isinstance(project_data, dict):
                summary = project_data.get("execution_summary") if isinstance(project_data.get("execution_summary"), dict) else {}
                scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
                for scene in scenes:
                    if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                        return scene
                for scene in project_data.get("scenes") or []:
                    if isinstance(scene, dict) and scene.get("scene_id") == scene_id:
                        return scene
        except Exception as exc:
            raise PersistenceError(
                "Storyboard scene ownership lookup failed",
                stage="storyboard_blueprint",
                metadata={"cause": type(exc).__name__},
            ) from exc
        return None

    def _scene_text(self, scene: dict[str, Any]) -> str:
        return str(
            scene.get("text")
            or scene.get("content")
            or scene.get("scene_text")
            or scene.get("description")
            or ""
        )

    def _scene_characters(self, scene: dict[str, Any]) -> list[str]:
        raw = scene.get("characters") or scene.get("character_appearances") or []
        if isinstance(raw, str):
            return [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(raw, list):
            return [str(part).strip() for part in raw if str(part).strip()]
        return []

    def _project_characters_for_prompt(self, project_id: str) -> list[dict[str, Any]]:
        try:
            characters = self.storage.get_characters(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Storyboard character reference lookup failed",
                stage="storyboard_prompt_context",
                metadata={"cause": type(exc).__name__},
            ) from exc
        return [character for character in characters if isinstance(character, dict)]

    def _locked_characters_for_prompt(self, project_id: str, characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Intersect appearance-locked characters with the reference-lock table.

        The prompt block's `appearance_approval.status == 'locked'` is a
        project-wide flag (all six scene_001 characters), while
        `character_reference_locks` (`lock_status='locked'`) is the visual
        identity actually bound to references (MAYA/MOM only; DRE is
        provisional). When the lock table has locked rows, characters without
        a locked row are dropped so other scenes' faces never leak in.
        Missing table / lookup failure fails open to the appearance-locked
        list so boards still build."""
        try:
            from app.services.shot_prompt_builder import locked_appearance_characters

            locked = locked_appearance_characters(characters)
            if not locked:
                return locked
            try:
                rows = self.storage.list_character_reference_locks(project_id, lock_status="locked", limit=200)
            except Exception:
                return locked
            if not rows:
                return locked
            allowed_ids: set[str] = set()
            allowed_names: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("character_id") or "").strip()
                if cid:
                    allowed_ids.add(cid)
                cname = str(row.get("character_name") or "").strip().lower()
                if cname:
                    allowed_names.add(cname)
            if not allowed_ids and not allowed_names:
                return locked
            narrowed = []
            for char in locked:
                if not isinstance(char, dict):
                    continue
                cid = str(char.get("id") or char.get("character_id") or "").strip()
                cname = str(char.get("name") or "").strip().lower()
                if (cid and cid in allowed_ids) or (cname and cname in allowed_names):
                    narrowed.append(char)
            # If nothing intersects (e.g. name drift), fail open rather than
            # minting an empty block that the rebuild gate would refuse.
            return narrowed or locked
        except Exception:
            try:
                from app.services.shot_prompt_builder import locked_appearance_characters

                return locked_appearance_characters(characters)
            except Exception:
                return [c for c in characters if isinstance(c, dict)]

    def _locked_block_for_scene(
        self,
        project_id: str,
        scene: dict[str, Any] | None,
        *,
        shot_characters: list[str] | None = None,
        shot_text: str | None = None,
        scene_shot_texts: list[str] | None = None,
    ) -> str:
        """Fresh locked-appearance block so post-lock approvals still apply.

        Shot context (focus names, shot text, scene-wide shot texts for the
        union fallback) scopes the block to this shot; without it an empty
        scene cast resolves empty instead of leaking other scenes' faces."""
        try:
            from app.services.shot_prompt_builder import build_locked_appearance_block

            characters = self._project_characters_for_prompt(project_id)
            characters = self._locked_characters_for_prompt(project_id, characters)
            return build_locked_appearance_block(
                characters,
                scene,
                shot_characters=shot_characters,
                shot_text=shot_text,
                scene_shot_texts=scene_shot_texts,
            ) or ""
        except Exception:
            return ""

    def _locked_reference_images_for_scene(
        self, project_id: str, scene: dict[str, Any] | None
    ) -> list[str]:
        """Face-first lock anchors for this scene, fresh from storage."""
        try:
            from app.utils.character_appearance import appearance_approval

            characters = self._project_characters_for_prompt(project_id)
            locked = self._locked_characters_for_prompt(project_id, characters)
            if isinstance(scene, dict):
                try:
                    from app.services.shot_prompt_builder import _scene_character_names

                    names = _scene_character_names(scene)
                except Exception:
                    names = set()
                if names:
                    scoped = [
                        c for c in locked
                        if str(c.get("name") or "").strip().lower() in names
                    ]
                    if scoped:
                        locked = scoped
            refs: list[str] = []
            # Face first: strongest identity signal, then full-body. No
            # alphabetical truncation: every in-scope locked character keeps
            # its anchors (face pass, then body pass).
            for field in ("face_image_url", "body_image_url"):
                for char in locked:
                    try:
                        url = str(appearance_approval(char).get(field) or "").strip()
                    except Exception:
                        url = ""
                    if url and url not in refs:
                        refs.append(url)
            return refs
        except Exception:
            return []

    def get_consistency_readiness(self, project_id: str, scene_id: str) -> dict[str, Any]:
        """Advisory workflow check: lock + face-ref + cast coverage.

        Never blocks generation (creator authority owns the call); surfaces
        what will be text-only vs image-anchored so the fix is obvious.
        """
        try:
            characters = self._project_characters_for_prompt(project_id)
        except Exception:
            characters = []
        scene: dict[str, Any] | None = None
        try:
            scene = self._get_scene(project_id, scene_id)
        except Exception:
            scene = None
        try:
            from app.services.shot_prompt_builder import (
                _scene_character_names,
                locked_appearance_characters,
            )
            from app.utils.character_appearance import appearance_approval

            locked = locked_appearance_characters(characters)
            locked_names = {str(c.get("name") or "").strip() for c in locked if str(c.get("name") or "").strip()}
            unlocked = [
                str(c.get("name") or "").strip() or "unnamed"
                for c in characters
                if isinstance(c, dict) and c not in locked
            ]
            missing_face = []
            for char in locked:
                try:
                    has_face = bool(str(appearance_approval(char).get("face_image_url") or "").strip())
                except Exception:
                    has_face = False
                if not has_face:
                    missing_face.append(str(char.get("name") or "").strip() or "unnamed")
            scene_names = set()
            if isinstance(scene, dict):
                try:
                    scene_names = set(_scene_character_names(scene) or set())
                except Exception:
                    scene_names = set()
            warnings: list[str] = []
            if unlocked:
                warnings.append(
                    "Unlocked characters render text-only: "
                    + ", ".join(unlocked[:4])
                    + ". Approve their look to lock race/face."
                )
            if missing_face:
                warnings.append(
                    "Locked but no face reference (image-anchor missing): "
                    + ", ".join(missing_face[:4])
                    + ". Upload a portrait on the look screen, then re-Generate."
                )
            if isinstance(scene, dict) and not scene_names and locked_names:
                warnings.append(
                    "Scene cast list is empty, so final video resolves cast by name "
                    "match only. Add characters to the scene to guarantee face refs attach."
                )
            return {
                "locked": sorted(locked_names),
                "unlocked": unlocked[:8],
                "missing_face_reference": missing_face,
                "scene_cast": sorted(scene_names),
                "warnings": warnings,
            }
        except Exception:
            return {"locked": [], "unlocked": [], "missing_face_reference": [], "scene_cast": [], "warnings": []}

    def _refresh_prompt_with_locked_characters(
        self, base_prompt: str | None, project_id: str, scene: dict[str, Any] | None
    ) -> str:
        """Re-attach current locked looks to a possibly stale stored prompt."""
        base = str(base_prompt or "").strip()
        block = self._locked_block_for_scene(project_id, scene)
        if not block or "Locked appearance" in base:
            return base
        if not base:
            return f"{block}."
        return f"{base.rstrip('. ')}. {block}."

    def _require_blueprint(self, blueprint_id: str) -> StoryboardBlueprint:
        blueprint = self.storage.get_storyboard_blueprint_by_id(blueprint_id)
        if blueprint is None:
            raise StateError("Storyboard blueprint not found", stage="storyboard_blueprint")
        return blueprint

    def _require_current_editable_blueprint(
        self,
        blueprint_id: str,
        *,
        stage: str,
    ) -> tuple[StoryboardBlueprint, StoryboardBlueprintVersion]:
        blueprint = self._require_blueprint(blueprint_id)
        if blueprint.locked:
            raise StateError("Storyboard blueprint is locked", stage=stage)
        version = (
            self.storage.get_storyboard_blueprint_version(blueprint.current_version_id)
            if blueprint.current_version_id
            else None
        )
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Current storyboard version not found", stage=stage)
        if version.status in {
            StoryboardBlueprintStatus.APPROVED,
            StoryboardBlueprintStatus.LOCKED,
            StoryboardBlueprintStatus.SUPERSEDED,
            StoryboardBlueprintStatus.ARCHIVED,
        }:
            raise StateError("Approved or historical storyboard versions cannot be edited", stage=stage)
        return blueprint, version

    def _require_current_editable_shot(
        self,
        blueprint_id: str,
        storyboard_shot_id: str,
        *,
        stage: str,
        allow_locked: bool = False,
    ) -> tuple[StoryboardBlueprint, StoryboardBlueprintVersion, StoryboardShot]:
        blueprint, version = self._require_current_editable_blueprint(blueprint_id, stage=stage)
        shot = self.storage.get_storyboard_shot(storyboard_shot_id)
        if (
            shot is None
            or shot.blueprint_id != blueprint.blueprint_id
            or shot.version_id != version.version_id
            or shot.project_id != blueprint.project_id
            or shot.scene_id != blueprint.scene_id
        ):
            raise StateError("Storyboard shot not found in the current version", stage=stage)
        if shot.locked and not allow_locked:
            raise StateError("Storyboard shot is locked", stage=stage)
        return blueprint, version, shot

    def _clone_shot_for_version(
        self,
        source: StoryboardShot,
        *,
        version_id: str,
        preserve_lock: bool,
    ) -> StoryboardShot:
        now = utc_now_iso()
        clone = source.model_copy(deep=True)
        clone.storyboard_shot_id = f"sbs_{uuid4().hex[:12]}"
        clone.version_id = version_id
        clone.status = StoryboardShotStatus.LOCKED if preserve_lock and source.locked else StoryboardShotStatus.READY
        clone.locked = bool(preserve_lock and source.locked)
        clone.created_at = now
        clone.updated_at = now
        clone.render_contract.provenance = {
            **clone.render_contract.provenance,
            "blueprint_id": clone.blueprint_id,
            "version_id": version_id,
            "shot_id": clone.shot_id,
        }
        carried = dict(clone.metadata or {})
        # Provenance from a prior version's rebuild belongs to that version.
        carried.pop("prompt_rebuild", None)
        # Re-stamp the builder hash at clone time only when the text is still
        # provably machine-built. Hand-edited text stays marked hand-edited
        # (Rebuild keeps skipping it) and must not gain a fresh hash that
        # would falsely certify it as builder output.
        if carried.get("canonical_hand_edited_at"):
            carried.pop("builder_output_sha256", None)
        else:
            carried["builder_output_sha256"] = _prompt_sha256(
                str(clone.render_contract.provider_neutral_prompt or "")
            )
        clone.metadata = {
            **carried,
            "source_storyboard_shot_id": source.storyboard_shot_id,
            "source_version_id": source.version_id,
        }
        return clone

    def _persist_version_bundle(
        self,
        *,
        blueprint: StoryboardBlueprint,
        version: StoryboardBlueprintVersion,
        shots: list[StoryboardShot],
        superseded_version: StoryboardBlueprintVersion | None = None,
    ) -> None:
        commit = getattr(self.storage, "commit_storyboard_blueprint_version", None)
        if callable(commit):
            try:
                commit(
                    blueprint=blueprint,
                    version=version,
                    shots=shots,
                    superseded_version=superseded_version,
                )
            except Exception as exc:
                raise PersistenceError(
                    "Storyboard version persistence failed",
                    stage="storyboard_version_persistence",
                    metadata={"cause": type(exc).__name__},
                ) from exc
            return
        try:
            if superseded_version is not None:
                self.storage.save_storyboard_blueprint_version(superseded_version)
            self.storage.save_storyboard_blueprint(blueprint)
            self.storage.save_storyboard_blueprint_version(version)
            for shot in shots:
                self.storage.save_storyboard_shot(shot)
        except Exception as exc:
            raise PersistenceError(
                "Storyboard version persistence failed",
                stage="storyboard_version_persistence",
                metadata={"cause": type(exc).__name__},
            ) from exc

    def _validate_ids(self, project_id: str, scene_id: str) -> None:
        if not project_id.strip() or not scene_id.strip():
            raise ValidationError("project_id and scene_id are required", stage="storyboard_blueprint")

    def get_storyboard_shot(self, storyboard_shot_id: str):
        return self.storage.get_storyboard_shot(storyboard_shot_id)

    def _image_prompt_service(self):
        from app.services.storyboard_image_prompt_service import (
            storyboard_image_prompt_service,
        )

        storyboard_image_prompt_service.set_storage(self.storage)
        return storyboard_image_prompt_service

    def derive_and_approve_image_prompts_for_version(
        self,
        *,
        version_id: str,
        approved_by: str = "creator",
    ) -> list[dict]:
        """D4 convenience: derive (if missing/stale) and human-approve every shot's
        image prompt for a version. A bulk human gesture — never automatic."""
        service = self._image_prompt_service()
        version = self.storage.get_storyboard_blueprint_version(version_id)
        shots = self.storage.list_storyboard_shots(version.blueprint_id, version_id)
        results = []
        for shot in shots:
            record = service.derive_for_shot(shot)
            if record["status"] != "approved":
                record = service.approve_for_shot(
                    shot, approved_by=approved_by
                )
            results.append(record)
        return results

    def _carry_forward_and_derive(self, shots) -> dict[str, Any]:
        """Hash-gated carry-forward (design item C) then derive missing proposals.

        Runs on every ``create_version`` path — explicit regenerate and the
        camera-approval mint (``previs_service.approve_ai_camera`` calls
        ``create_version``). Scene Direction / coverage saves call the same
        helper via ``SceneDirectionService.save``. Carried approved rows keep
        their text/approval; derive only proposes for shots without a fresh
        approved row, so it can never downgrade a carried approval."""
        service = self._image_prompt_service()
        summary: dict[str, Any] = {"carried": [], "skipped_changed": [], "skipped_unapproved": []}
        try:
            summary = service.carry_forward_for_clones(shots)
        except Exception:
            logger.warning(
                "project_id=%s job_id=%s provider=runway stage=image_prompt_carry_failed duration_ms=%d",
                getattr(shots[0], "project_id", "") if shots else "",
                "create_version",
                0,
            )
        self._derive_image_prompt_proposals(shots)
        return summary

    def _derive_image_prompt_proposals(self, shots):
        proposals = []
        service = self._image_prompt_service()
        for shot in shots:
            try:
                existing = self.storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
                if existing and str(existing.get("status") or "") == "approved":
                    from app.services.runway_image_prompt_compactor import canonical_sha256 as _canonical_sha256

                    if str(existing.get("source_prompt_sha256") or "") == _canonical_sha256(
                        str(shot.render_contract.provider_neutral_prompt or "")
                    ):
                        continue  # carried approval stands; never derive over it
                proposals.append(service.derive_for_shot(shot))
            except Exception as exc:
                logger.warning(
                    "project_id=%s job_id=%s provider=runway stage=image_prompt_derive_failed duration_ms=%d",
                    shot.project_id,
                    shot.storyboard_shot_id,
                    0,
                )
        return proposals


storyboard_blueprint_service = StoryboardBlueprintService()
