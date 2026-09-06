from __future__ import annotations

import logging
import random
import urllib.parse
from pathlib import Path
from time import perf_counter
from typing import Any
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
        self._sync_scene_memory(project_id, scene_id, shots, approved=False)

        logger.info(
            "project_id=%s job_id=storyboard_%s provider=internal stage=storyboard_blueprint_create duration_ms=%d",
            project_id,
            scene_id,
            int((perf_counter() - started) * 1000),
        )
        return {"blueprint": blueprint, "version": version, "shots": shots, "inspection": inspection}

    def get_blueprint_detail(self, *, project_id: str, scene_id: str) -> dict[str, Any]:
        self._validate_ids(project_id, scene_id)
        blueprint = self.storage.get_storyboard_blueprint(project_id, scene_id)
        if blueprint is None:
            raise StateError("Storyboard blueprint not found", stage="storyboard_blueprint_get")
        version = (
            self.storage.get_storyboard_blueprint_version(blueprint.current_version_id)
            if blueprint.current_version_id
            else None
        )
        if version is None or version.blueprint_id != blueprint.blueprint_id:
            raise StateError("Current storyboard version not found", stage="storyboard_blueprint_get")
        shots = self.storage.list_storyboard_shots(
            blueprint.blueprint_id,
            blueprint.current_version_id,
        )
        inspection = self._inspect(blueprint, version, shots)
        return {"blueprint": blueprint, "version": version, "shots": shots, "inspection": inspection}

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

    def approve_version(self, *, blueprint_id: str, version_id: str, approved_by: str = "creator") -> dict[str, Any]:
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

        now = utc_now_iso()
        version.status = StoryboardBlueprintStatus.APPROVED
        version.approved_at = now
        version.approved_by = approved_by
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
        shot.metadata = {**(shot.metadata or {}), "last_change_reason": change_reason}
        shot.status = StoryboardShotStatus.READY
        shot.updated_at = utc_now_iso()
        self.storage.save_storyboard_shot(shot)
        self._sync_scene_memory(shot.project_id, shot.scene_id, [shot], approved=False)
        return shot

    def generate_storyboard_image_for_scene_shot(
        self,
        *,
        project_id: str,
        scene_id: str,
        provider: str = "qwen-image-max",
        shot_number: int = 1,
        storyboard_shot_id: str | None = None,
    ) -> dict[str, Any]:
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
        _, _, shot = self._require_current_editable_shot(
            shot.blueprint_id,
            shot.storyboard_shot_id,
            stage="storyboard_image_generation",
        )

        existing_seed = self.storage.get_scene_previs_seed(project_id, scene_id)
        seed = existing_seed if existing_seed is not None else random.randint(1, 999999)
        prompt = shot.render_contract.provider_neutral_prompt or self._prompt_from_shot(shot)
        normalized_provider = (provider or "qwen-image-max").strip().lower()
        provider_used = "pollinations"
        model_used = "pollinations.ai"

        if normalized_provider in {"pollinations", "pollinations.ai", "legacy"}:
            encoded = urllib.parse.quote(prompt)
            image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=432&nologo=true&seed={seed}"
            fallback = True
        elif normalized_provider in {"qwen", "qwen-image-max", "dashscope"}:
            from app.services.storyboard_image_service import storyboard_image_service

            output_root = Path(__file__).resolve().parents[2] / "outputs" / "previs"
            result = storyboard_image_service.generate_qwen_image(
                project_id=project_id,
                scene_id=shot.shot_id,
                prompt=prompt,
                output_root=output_root,
            )
            image_url = result.image_url
            provider_used = result.provider
            model_used = result.model
            fallback = False
        else:
            raise ValidationError(
                "provider must be one of: qwen-image-max, pollinations",
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
        job = svc.create_job(
            project_id=shot.project_id,
            shot_id=shot.shot_id,
            provider=provider,
            prompt=shot.render_contract.provider_neutral_prompt,
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
            visual_plan = StoryboardShotVisualPlan(
                framing=str(candidate.get("shot_type") or ""),
                camera_movement=str(candidate.get("transition_hint") or ""),
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
        parts = [
            prompt,
            visual_plan.framing,
            visual_plan.environment,
            visual_plan.lighting,
            f"Shot {shot_number} of {shot_count}.",
            rationale,
        ]
        text = ". ".join(part.strip().strip(".") for part in parts if str(part or "").strip())
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
        return {
            "blueprint_id": shot.blueprint_id,
            "version_id": shot.version_id,
            "storyboard_shot_id": shot.storyboard_shot_id,
            "project_id": shot.project_id,
            "scene_id": shot.scene_id,
            "shot_id": shot.shot_id,
            "shot_number": shot.shot_number,
        }

    def _prompt_from_shot(self, shot: StoryboardShot) -> str:
        return ". ".join(
            part
            for part in [
                shot.visual_plan.framing,
                shot.visual_plan.environment,
                shot.intent.emotional_target,
                shot.rationale,
            ]
            if part
        )

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
        clone.metadata = {
            **(clone.metadata or {}),
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


storyboard_blueprint_service = StoryboardBlueprintService()
