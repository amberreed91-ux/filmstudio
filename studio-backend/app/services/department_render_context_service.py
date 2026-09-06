from __future__ import annotations

import logging
from typing import Any

from app.models.casting_intelligence import RoleBreakdownBuildRequest
from app.models.cinematography import CameraGrammarPlanRequest, CameraGrammarRenderContextRequest
from app.models.colorist import ColorLookBibleRequest, ColoristLookPlanRequest, ColorRenderContextRequest
from app.models.production_design import ProductionDesignPlanRequest, ProductionDesignRenderContextRequest
from app.services.stability import elapsed_ms, log_stage_event, start_timer

logger = logging.getLogger("studio-department-render-context")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _compact(parts: list[str], max_chars: int) -> str:
    text = "; ".join(part for part in (_clean(part) for part in parts) if part)
    from app.prompt_assembly_context import collecting_generation_prompt
    if collecting_generation_prompt.get() or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip(" ;,.") + "..."


def _slot_suggestion(suggestions: list[Any], slot_name: str) -> str:
    for suggestion in suggestions or []:
        if _clean(getattr(suggestion, "slot", "")) == slot_name:
            return _clean(getattr(suggestion, "suggestion", ""))
    return ""


class DepartmentRenderContextService:
    """Translate crew intelligence records into provider-facing render slots."""

    def build_slot_guidance(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_id: str,
        render_job_id: str | None = None,
        scene_context: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = start_timer()
        parameters = parameters if isinstance(parameters, dict) else {}
        scene_context = dict(scene_context or {})
        metadata: dict[str, Any] = {
            "enabled": parameters.get("department_context_enabled", True) is not False,
            "sources": [],
            "plan_ids": {},
            "warnings": [],
        }
        guidance = {
            "character_state": "",
            "environment_persistence": "",
            "camera": "",
            "lighting": "",
        }
        if not metadata["enabled"]:
            return {"slot_guidance": guidance, "metadata": metadata}

        try:
            camera_guidance = self._camera_guidance(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=shot_id,
                render_job_id=render_job_id,
                scene_context=scene_context,
            )
            self._merge_guidance(guidance, camera_guidance["slot_guidance"])
            metadata["sources"].append("cinematographer")
            metadata["plan_ids"]["cinematographer"] = camera_guidance["plan_id"]
        except Exception as exc:
            metadata["warnings"].append(f"cinematographer unavailable: {type(exc).__name__}")
            logger.debug("Cinematographer render guidance skipped for %s/%s: %s", project_id, shot_id, exc)

        try:
            design_guidance = self._production_design_guidance(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=shot_id,
                render_job_id=render_job_id,
                scene_context=scene_context,
            )
            self._merge_guidance(guidance, design_guidance["slot_guidance"])
            metadata["sources"].append("production_designer")
            metadata["plan_ids"]["production_designer"] = design_guidance["plan_id"]
        except Exception as exc:
            metadata["warnings"].append(f"production designer unavailable: {type(exc).__name__}")
            logger.debug("Production design render guidance skipped for %s/%s: %s", project_id, shot_id, exc)

        try:
            color_guidance = self._colorist_guidance(
                project_id=project_id,
                scene_id=scene_id,
                shot_id=shot_id,
                render_job_id=render_job_id,
                scene_context=scene_context,
            )
            self._merge_guidance(guidance, color_guidance["slot_guidance"])
            metadata["sources"].append("colorist")
            metadata["plan_ids"]["colorist"] = color_guidance["plan_id"]
            if color_guidance.get("look_bible_id"):
                metadata["plan_ids"]["color_look_bible"] = color_guidance["look_bible_id"]
        except Exception as exc:
            metadata["warnings"].append(f"colorist unavailable: {type(exc).__name__}")
            logger.debug("Colorist render guidance skipped for %s/%s: %s", project_id, shot_id, exc)

        try:
            casting_guidance = self._casting_guidance(
                project_id=project_id,
                scene_id=scene_id,
            )
            self._merge_guidance(guidance, casting_guidance["slot_guidance"])
            metadata["sources"].append("casting")
            metadata["plan_ids"]["casting_roles"] = casting_guidance["role_ids"]
            if casting_guidance["decision_ids"]:
                metadata["plan_ids"]["casting_decisions"] = casting_guidance["decision_ids"]
        except Exception as exc:
            metadata["warnings"].append(f"casting unavailable: {type(exc).__name__}")
            logger.debug("Casting render guidance skipped for %s/%s: %s", project_id, shot_id, exc)

        metadata["sources"] = sorted(set(metadata["sources"]))
        log_stage_event(
            project_id=project_id,
            job_id=render_job_id,
            provider="internal",
            stage="department_render_context",
            duration_ms=elapsed_ms(started),
            extra={"source_count": len(metadata["sources"]), "warnings": len(metadata["warnings"])},
        )
        return {"slot_guidance": guidance, "metadata": metadata}

    def _merge_guidance(self, base: dict[str, str], incoming: dict[str, str]) -> None:
        for slot, text in incoming.items():
            text = _clean(text)
            if not text:
                continue
            base[slot] = _compact([base.get(slot, ""), text], 220)

    def _camera_guidance(self, *, project_id: str, scene_id: str, shot_id: str, render_job_id: str | None, scene_context: dict[str, Any]) -> dict[str, Any]:
        from app.services.cinematographer_intelligence_service import cinematographer_intelligence_service

        plans = cinematographer_intelligence_service.list_plans(
            project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            status="active",
            limit=1,
        )
        plan = plans[0] if plans else cinematographer_intelligence_service.create_plan(
            project_id,
            CameraGrammarPlanRequest(
                scene_id=scene_id,
                shot_id=shot_id,
                render_job_id=render_job_id,
                plan_scope="shot",
                scene_context=scene_context,
            ),
        ).plan
        context = cinematographer_intelligence_service.build_render_context(
            project_id,
            CameraGrammarRenderContextRequest(
                plan_id=plan.plan_id,
                scene_id=scene_id,
                shot_id=shot_id,
                provider="render",
            ),
        )
        return {
            "plan_id": plan.plan_id,
            "slot_guidance": {
                "camera": context.camera_direction,
                "lighting": context.lighting_direction,
            },
        }

    def _production_design_guidance(self, *, project_id: str, scene_id: str, shot_id: str, render_job_id: str | None, scene_context: dict[str, Any]) -> dict[str, Any]:
        from app.services.production_design_intelligence_service import production_design_intelligence_service

        plans = production_design_intelligence_service.list_plans(
            project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            limit=1,
        )
        plan = plans[0] if plans else production_design_intelligence_service.create_plan(
            project_id,
            ProductionDesignPlanRequest(
                scene_id=scene_id,
                shot_id=shot_id,
                render_job_id=render_job_id,
                scope="shot",
                scene_context=scene_context,
            ),
        ).plan
        context = production_design_intelligence_service.build_render_context(
            project_id,
            ProductionDesignRenderContextRequest(
                plan_id=plan.plan_id,
                scene_id=scene_id,
                shot_id=shot_id,
                provider="render",
            ),
        )
        return {
            "plan_id": plan.plan_id,
            "slot_guidance": {
                "character_state": context.character_direction,
                "environment_persistence": _compact(
                    [context.environment_direction, context.style_direction, context.negative_design_direction],
                    180,
                ),
            },
        }

    def _colorist_guidance(self, *, project_id: str, scene_id: str, shot_id: str, render_job_id: str | None, scene_context: dict[str, Any]) -> dict[str, Any]:
        from app.services.colorist_intelligence_service import colorist_intelligence_service

        look_bibles = colorist_intelligence_service.list_look_bibles(project_id, scope="project", status="active", limit=1)
        look_bible = look_bibles[0] if look_bibles else colorist_intelligence_service.create_or_update_look_bible(
            project_id,
            ColorLookBibleRequest(scope="project", project_context=scene_context),
        ).look_bible
        plans = colorist_intelligence_service.list_look_plans(
            project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            status="active",
            limit=1,
        )
        plan = plans[0] if plans else colorist_intelligence_service.create_look_plan(
            project_id,
            ColoristLookPlanRequest(
                look_bible_id=look_bible.look_bible_id,
                scene_id=scene_id,
                shot_id=shot_id,
                render_job_id=render_job_id,
                scope="shot",
                scene_context=scene_context,
            ),
        ).plan
        context = colorist_intelligence_service.build_render_context(
            project_id,
            ColorRenderContextRequest(
                plan_id=plan.plan_id,
                scene_id=scene_id,
                shot_id=shot_id,
                provider="render",
            ),
        )
        return {
            "plan_id": plan.plan_id,
            "look_bible_id": look_bible.look_bible_id,
            "slot_guidance": {
                "lighting": context.color_direction,
            },
        }

    def _casting_guidance(self, *, project_id: str, scene_id: str) -> dict[str, Any]:
        from app.services.casting_intelligence_service import casting_intelligence_service

        roles = casting_intelligence_service.list_role_breakdowns(project_id, limit=500)
        if not roles:
            roles = casting_intelligence_service.build_role_breakdowns(
                project_id,
                RoleBreakdownBuildRequest(),
            ).roles
        scene_roles = [
            role for role in roles
            if not role.scene_ids or scene_id in role.scene_ids
        ]
        decisions = casting_intelligence_service.list_casting_decisions(project_id, active=True, limit=500)
        talent_by_id = {
            talent.talent_id: talent
            for talent in casting_intelligence_service.list_talent_profiles(project_id, limit=500)
        }
        lines: list[str] = []
        decision_ids: list[str] = []
        for role in scene_roles[:3]:
            decision = next((item for item in decisions if item.role_id == role.role_id), None)
            if decision:
                decision_ids.append(decision.decision_id)
                talent = talent_by_id.get(decision.talent_id)
                lines.append(_compact([
                    f"{role.character_name} cast as {talent.display_name if talent else decision.talent_id}",
                    ", ".join((talent.visual_characteristics if talent else [])[:2]),
                    ", ".join((talent.performance_strengths if talent else [])[:2]),
                ], 110))
            else:
                lines.append(_compact([
                    f"{role.character_name} casting demands",
                    ", ".join(role.visual_requirements[:2]),
                    ", ".join(role.performance_demands[:2]),
                ], 110))
        return {
            "role_ids": [role.role_id for role in scene_roles[:5]],
            "decision_ids": decision_ids,
            "slot_guidance": {
                "character_state": _compact(lines, 180),
            },
        }


department_render_context_service = DepartmentRenderContextService()
