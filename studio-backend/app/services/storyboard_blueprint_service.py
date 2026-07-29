from __future__ import annotations

import logging
import random
import urllib.parse
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.data.storage import get_storage
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
from app.services.stability import StateError, ValidationError
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
    ) -> dict[str, Any]:
        started = perf_counter()
        self._validate_ids(project_id, scene_id)
        existing = self.storage.get_storyboard_blueprint(project_id, scene_id)
        if existing and existing.current_version_id:
            return self.get_blueprint_detail(project_id=project_id, scene_id=scene_id)

        scene = self._get_scene(project_id, scene_id)
        if scene is None:
            scene = {
                "scene_id": scene_id,
                "heading": scene_id.replace("_", " ").title(),
                "description": "Storyboard fallback scene generated from the requested scene identifier.",
                "location": "cinematic scene",
                "time_of_day": "day",
                "emotional_tone": "neutral",
                "characters": [],
                "metadata": {"fallback_scene": True},
            }

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
        self.storage.save_storyboard_blueprint(blueprint)
        self.storage.save_storyboard_blueprint_version(version)
        for shot in shots:
            self.storage.save_storyboard_shot(shot)
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
        shots = self.storage.list_storyboard_shots(
            blueprint.blueprint_id,
            blueprint.current_version_id,
        )
        inspection = self._inspect(blueprint, version, shots)
        return {"blueprint": blueprint, "version": version, "shots": shots, "inspection": inspection}

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

    def lock_shot(self, *, blueprint_id: str, storyboard_shot_id: str, locked: bool) -> StoryboardShot:
        shot = self.storage.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.blueprint_id != blueprint_id:
            raise StateError("Storyboard shot not found", stage="storyboard_shot_lock")
        shot.locked = bool(locked)
        shot.status = StoryboardShotStatus.LOCKED if locked else StoryboardShotStatus.READY
        shot.updated_at = utc_now_iso()
        self.storage.save_storyboard_shot(shot)
        return shot

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
        shot = self.storage.get_storyboard_shot(storyboard_shot_id)
        if shot is None or shot.blueprint_id != blueprint_id:
            raise StateError("Storyboard shot not found", stage="storyboard_shot_update")
        blueprint = self.storage.get_storyboard_blueprint_by_id(blueprint_id)
        if blueprint and blueprint.locked:
            raise StateError("Storyboard blueprint is locked", stage="storyboard_shot_update")
        version = self.storage.get_storyboard_blueprint_version(shot.version_id)
        if version and version.status in {StoryboardBlueprintStatus.APPROVED, StoryboardBlueprintStatus.LOCKED}:
            raise StateError("Approved storyboard versions cannot be edited", stage="storyboard_shot_update")
        if shot.locked:
            raise StateError("Storyboard shot is locked", stage="storyboard_shot_update")
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
    ) -> dict[str, Any]:
        detail = self.get_or_create_blueprint(project_id=project_id, scene_id=scene_id)
        shots = detail["shots"]
        safe_shot_number = max(1, int(shot_number or 1))
        shot = next((item for item in shots if item.shot_number == safe_shot_number), None)
        if shot is None:
            raise StateError("Storyboard shot not found", stage="storyboard_image_generation")

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
        if shot is None or shot.blueprint_id != blueprint_id:
            raise StateError("Storyboard shot not found", stage="storyboard_render_contract_build")
        svc = render_service or default_render_service
        parameters = dict(shot.render_contract.structured_parameters or {})
        parameters["storyboard"] = self._storyboard_metadata_for_shot(shot)
        if shot.render_contract.seed is not None:
            parameters.setdefault("seed", shot.render_contract.seed)
        job = svc.create_job(
            project_id=shot.project_id,
            shot_id=shot.shot_id,
            provider=provider,
            prompt=shot.render_contract.provider_neutral_prompt,
            reference_assets=shot.render_contract.reference_assets,
            parameters=parameters,
        )
        self.link_render_job(shot=shot, render_job_id=job.id, link_type=link_type)
        return job

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
        return text[:512] if len(text) > 512 else text

    def _build_provenance(self, project_id: str, scene_id: str, scene: dict[str, Any]) -> StoryboardBlueprintProvenance:
        provenance = StoryboardBlueprintProvenance()
        provenance.canonical_sources["scene_input"] = True
        provenance.derived_sources["shot_sequence_service"] = True
        provenance.derived_sources["shot_rationale_service"] = True
        try:
            if self.storage.load_previs_images(project_id, scene_id):
                provenance.canonical_sources["previs_images"] = True
        except Exception:
            pass
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
        except Exception:
            pass
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
        except Exception:
            pass
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
        except Exception:
            return []
        return [character for character in characters if isinstance(character, dict)]

    def _validate_ids(self, project_id: str, scene_id: str) -> None:
        if not project_id.strip() or not scene_id.strip():
            raise ValidationError("project_id and scene_id are required", stage="storyboard_blueprint")

    def get_storyboard_shot(self, storyboard_shot_id: str):
        return self.storage.get_storyboard_shot(storyboard_shot_id)


storyboard_blueprint_service = StoryboardBlueprintService()
