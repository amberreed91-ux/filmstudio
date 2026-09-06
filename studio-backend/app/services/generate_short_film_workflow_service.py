from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List
from app.services import render as render_module

from app.models.generate_short_film_workflow import (
    GenerateShortFilmWorkflow,
    WORKFLOW_STAGES,
    WorkflowStageState,
)
from app.utils.helpers import as_non_empty_string, ensure_scene_fallback, scene_sequence_from_summary

logger = logging.getLogger(__name__)


class GenerateShortFilmWorkflowService:
    STAGE_AGENT = {
        "concept": "Director",
        "screenplay_outline": "Writer",
        "scene_generation": "Provider Router",
        "shot_sequencing": "Director",
        "render_orchestration": "Provider Router",
        "audio_generation": "Writer",
        "film_assembly": "Memory Archivist",
        "final_export": "Provider Router",
    }

    STAGE_ACTIVITY = {
        "concept": "Director framing cinematic concept...",
        "screenplay_outline": "Writer drafting short film outline...",
        "scene_generation": "Provider Router selecting generation path...",
        "shot_sequencing": "Director sequencing shots for flow...",
        "render_orchestration": "Provider Router orchestrating renders...",
        "audio_generation": "Writer and Memory Archivist aligning voice and ambience...",
        "film_assembly": "Memory Archivist validating continuity across scenes...",
        "final_export": "Provider Router preparing delivery exports...",
    }

    def build_workflow(
        self,
        project_id: str,
        concept: str,
        execution_summary: Dict[str, Any],
        manual_overrides: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        sanitized_concept = concept.strip() if isinstance(concept, str) else ""
        overrides = manual_overrides if isinstance(manual_overrides, dict) else {}
        stages: List[WorkflowStageState] = []
        crew_updates: List[Dict[str, str]] = []
        progress_step = int(100 / max(1, len(WORKFLOW_STAGES)))
        progress = 0
        for stage in WORKFLOW_STAGES:
            progress = min(100, progress + progress_step)
            stages.append(
                WorkflowStageState(
                    stage=stage,
                    status="completed",
                    progress=progress,
                    activity=self.STAGE_ACTIVITY.get(stage, ""),
                    updated_by=self.STAGE_AGENT.get(stage, "Director"),
                )
            )
            crew_updates.append(
                {
                    "agent": self.STAGE_AGENT.get(stage, "Director"),
                    "stage": stage,
                    "activity": self.STAGE_ACTIVITY.get(stage, ""),
                }
            )

        scene_count = len(execution_summary.get("scenes", [])) if isinstance(execution_summary.get("scenes"), list) else 0
        shot_count = len(execution_summary.get("shot_candidates", [])) if isinstance(execution_summary.get("shot_candidates"), list) else 0
        workflow = GenerateShortFilmWorkflow(
            workflow_id=f"short_film_{project_id}",
            concept=sanitized_concept,
            manual_override=bool(overrides),
            manual_overrides=overrides,
            stages=stages,
            crew_updates=crew_updates,
            runtime_metadata={
                "project_id": project_id,
                "scene_count": scene_count,
                "shot_count": shot_count,
                "stages_completed": len(stages),
                "final_status": "completed",
            },
        )
        return {"short_film_workflow": workflow.model_dump()}

    async def handle_generate_short_film_request(
        self,
        project_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle the complete generate_short_film request workflow"""
        from app.services.project_store import project_store
        from app.services.script_parser import ScriptParser
        from app.services.stability import log_stage_event, elapsed_ms, start_timer, StateError
        from fastapi import HTTPException
        
        start_all = start_timer()
        current = project_store.get_project(project_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Project not found")
        
        concept = payload.get("concept", "")
        parser = ScriptParser()
        summary = parser.build_script_breakdown_bundle(concept)
        summary = ensure_scene_fallback(summary, concept)
        scene_ids = [
            str((scene or {}).get("scene_id") or "").strip()
            for scene in (summary.get("scenes") if isinstance(summary.get("scenes"), list) else [])
        ]
        scene_ids = [scene_id for scene_id in scene_ids if scene_id]
        
        workflow = self.build_workflow(
            project_id=project_id,
            concept=concept,
            execution_summary=summary,
            manual_overrides=payload.get("manual_overrides"),
        )
        workflow_payload = workflow.get("short_film_workflow", {}) if isinstance(workflow, dict) else {}
        if isinstance(workflow_payload, dict):
            workflow_payload["render_chaining"] = {
                "submit_renders": bool(payload.get("submit_renders")),
                "assemble_final": bool(payload.get("assemble_final")),
            }
        
        # Handle render job submission
        render_jobs: List[Dict[str, Any]] = []
        assembly_result: Dict[str, Any] = {}
        
        submit_renders = bool(payload.get("submit_renders"))
        assemble_final = bool(payload.get("assemble_final"))
        app_env = os.getenv("APP_ENV", "").lower()
        overrides = payload.get("manual_overrides", {}) if isinstance(payload.get("manual_overrides"), dict) else {}
        use_mock_success = bool(overrides.get("use_mock_success"))
        if use_mock_success and app_env not in {"local", "test", "dev", "development"}:
            raise HTTPException(status_code=400, detail="mock_success_not_allowed")

        if os.getenv("APP_ENV", "").lower() in {"local", "development", "dev", "test"}:
            logger.info(
                "[OneButtonDebug] request project_id=%s provider=%s submit_renders=%s assemble_final=%s use_mock_success=%s app_env=%s render_provider_test_mode=%s manual_overrides=%s scenes=%s shots=%s",
                project_id,
                as_non_empty_string(payload.get("manual_overrides", {}).get("provider")) or "default",
                submit_renders,
                assemble_final,
                use_mock_success,
                app_env or "unset",
                os.getenv("RENDER_PROVIDER_TEST_MODE", ""),
                bool(payload.get("manual_overrides")),
                len(summary.get("scenes", []) if isinstance(summary.get("scenes"), list) else []),
                len(summary.get("shot_candidates", []) if isinstance(summary.get("shot_candidates"), list) else []),
            )

        if submit_renders:
            self._ensure_canonical_project_before_render(project_id, current)
            from app.services import render_service

            selected_provider = (
                as_non_empty_string(payload.get("manual_overrides", {}).get("provider"))
                or render_service.get_default_provider()
            )
            if selected_provider == "mock_success":
                # Mock-success is a backend test mode for runway adapter, not a provider id.
                selected_provider = "runway"
            ratio = as_non_empty_string(payload.get("manual_overrides", {}).get("ratio")) or "1280:720"
            duration_seconds = payload.get("manual_overrides", {}).get("duration_per_shot_seconds")
            try:
                duration = int(duration_seconds) if duration_seconds is not None else 5
            except Exception:
                duration = 5
            
            shots = summary.get("shot_candidates") if isinstance(summary.get("shot_candidates"), list) else []
            if not shots:
                fallback_scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
                for idx, scene in enumerate(fallback_scenes):
                    if not isinstance(scene, dict):
                        continue
                    scene_id = as_non_empty_string(scene.get("scene_id")) or f"scene_{idx + 1:03d}"
                    heading = as_non_empty_string(scene.get("scene_heading"))
                    desc = as_non_empty_string(scene.get("scene_description"))
                    prompt_basis = desc or heading or concept
                    shots.append(
                        {
                            "shot_id": f"{scene_id}_shot_001",
                            "scene_id": scene_id,
                            "prompt": f"Cinematic shot for {scene_id}: {prompt_basis[:220]}",
                        }
                    )
                if len(shots) == 1:
                    first_shot = shots[0]
                    shots.append(
                        {
                            "shot_id": f"{first_shot.get('scene_id', 'scene_001')}_shot_002",
                            "scene_id": first_shot.get("scene_id", "scene_001"),
                            "prompt": f"{as_non_empty_string(first_shot.get('prompt'))} Secondary cinematic angle.",
                        }
                    )
            seen_job_ids: set[str] = set()
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[OneButtonDebug] submit phase",
                    extra={
                        "project_id": project_id,
                        "provider": selected_provider,
                        "submit_renders": submit_renders,
                        "assemble_final": assemble_final,
                        "scene_count": len(summary.get("scenes", []) if isinstance(summary.get("scenes"), list) else []),
                        "shot_count": len(shots),
                    },
                )
            
            for idx, shot in enumerate(shots):
                if not isinstance(shot, dict):
                    continue
                shot_id = as_non_empty_string(shot.get("shot_id")) or f"scene_{idx + 1:03d}_shot_001"
                scene_id = as_non_empty_string(shot.get("scene_id")) or f"scene_{idx + 1:03d}"
                prompt = as_non_empty_string(shot.get("prompt")) or f"Cinematic shot for {scene_id}: {concept[:180]}"
                
                try:
                    shot_timer = start_timer()
                    parameters = {"ratio": ratio, "duration": max(1, min(duration, 20))}
                    if use_mock_success:
                        parameters["use_mock_success"] = True
                    created_job = render_service.create_job(
                        project_id=project_id,
                        shot_id=shot_id,
                        provider=selected_provider,
                        prompt=prompt,
                        parameters=parameters,
                    )
                    if created_job.id in seen_job_ids:
                        raise HTTPException(status_code=409, detail="Duplicate render job submission")
                    seen_job_ids.add(created_job.id)
                    metadata={"job_id": created_job.id, "shot_id": shot_id}
                    
                    render_job = await render_service.submit_job(created_job.id)
                    submitted_job = await render_service.get_job_status(created_job.id)
                    poll_start = start_timer()
                    
                    for _ in range(3):
                        if submitted_job.is_terminal():
                            break
                        await asyncio.sleep(0.25)
                        submitted_job = await render_service.get_job_status(created_job.id)
                        if elapsed_ms(poll_start) > 60000:
                            from app.services.stability import ProviderError
                            raise ProviderError(
                                "Provider timeout during poll",
                                stage="render_polling",
                                metadata={"job_id": created_job.id, "provider": selected_provider},
                            )
                    
                    output_url = (submitted_job.output_payload.asset_url if submitted_job.output_payload else None)
                    render_jobs.append(
                        {
                            "scene_id": scene_id,
                            "shot_id": shot_id,
                            "job_id": submitted_job.id,
                            "provider": submitted_job.provider,
                            "status": submitted_job.status,
                            "task_id": submitted_job.provider_job_id,
                            "output_url": output_url,
                            "preview_url": (submitted_job.output_payload.thumbnail_url if submitted_job.output_payload else None),
                            "error_message": submitted_job.error_message,
                        }
                    )
                    log_stage_event(
                        project_id=project_id,
                        job_id=submitted_job.id,
                        provider=selected_provider,
                        stage="render_submission",
                        duration_ms=elapsed_ms(shot_timer),
                        extra={"status": submitted_job.status, "has_output_url": bool(as_non_empty_string(output_url))},
                    )
                except Exception as exc:
                    render_jobs.append(
                        {
                            "scene_id": scene_id,
                            "shot_id": shot_id,
                            "job_id": None,
                            "provider": selected_provider,
                            "status": "failed",
                            "task_id": None,
                            "output_url": None,
                            "preview_url": None,
                            "error_message": str(exc),
                        }
                    )
                    log_stage_event(
                        project_id=project_id,
                        job_id=None,
                        provider=selected_provider,
                        stage="render_submission_error",
                        duration_ms=0,
                        extra={"error": str(exc), "shot_id": shot_id},
                    )
        
        # Handle assembly logic
        if assemble_final:
            try:
                scene_sequence = scene_sequence_from_summary(summary)
                successful_outputs = [row for row in render_jobs if as_non_empty_string(row.get("output_url"))]
                if not successful_outputs:
                    assembly_result = {
                        "attempted": True,
                        "assembled": False,
                        "blockers": ["Assembly unavailable: no completed render outputs"],
                    }
                    successful_outputs = []
                else:
                    from app.services.cinematic_scene_stitching_service import cinematic_scene_stitching_service
                    from app.services.full_film_assembly_service import full_film_assembly_service
                
                    stitched = cinematic_scene_stitching_service.build_scene_assembly_v2(
                        scene_sequence=scene_sequence,
                        render_output={"outputs": successful_outputs},
                        pacing_profile="balanced",
                    )
                    
                    full_assembly = full_film_assembly_service.build_film_assembly_timeline(
                        scenes=summary.get("scenes", []),
                        scene_transitions=summary.get("scene_transitions", []),
                        ambient_audio_timeline=summary.get("ambient_audio_timeline", {}),
                        audio_dialogue_timeline=summary.get("audio_dialogue_timeline", {}),
                        stitched_export=stitched.get("stitched_export", {}),
                    )
                    
                    assembly_result = {
                        "attempted": True,
                        "assembled": True,
                        "blockers": [],
                        "scene_assembly": stitched,
                        "film_assembly": full_assembly,
                    }
            except Exception as exc:
                assembly_result = {
                    "attempted": True,
                    "assembled": False,
                    "blockers": [f"Assembly unavailable: {str(exc)}"],
                }
        
        # Update project with workflow results
        updated_film_cut = {
            "cut_id": "short_film_v1",
            "scene_order": scene_ids,
            "included_scenes": list(scene_ids),
            "excluded_scenes": [],
            "created_at": str(current.get("updated_at") or ""),
        }
        
        updated = project_store.update_project(
            project_id,
            {
                "script_text": concept,
                "execution_summary": {
                    **summary,
                    "short_film_workflow": workflow_payload,
                    "one_button_render_jobs": render_jobs,
                    "one_button_assembly": assembly_result,
                },
                "one_button_render_jobs": render_jobs,
                "one_button_assembly": assembly_result,
                "reviewed_scenes": [],
                "approved_scenes": [],
                "scene_review_status": {scene_id: "not_reviewed" for scene_id in scene_ids},
                "film_cut": updated_film_cut,
            },
        )
        
        if updated is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if not isinstance(updated.get("execution_summary"), dict):
            raise HTTPException(
                status_code=500,
                detail=StateError("Hydration mismatch: missing execution_summary after update", stage="project_hydration").to_dict(),
            )
        
        response: Dict[str, Any] = {"project": updated, "short_film_workflow": workflow_payload}
        if render_jobs:
            response["render_jobs"] = render_jobs
        if assembly_result:
            response["assembly"] = assembly_result
        if os.getenv("APP_ENV", "").lower() in {"local", "development", "dev", "test"}:
            submitted_count = len([row for row in render_jobs if as_non_empty_string((row or {}).get("job_id"))])
            output_count = len([row for row in render_jobs if as_non_empty_string((row or {}).get("output_url"))])
            logger.info(
                "[OneButtonDebug] response project_id=%s render_jobs=%s submitted_jobs=%s output_urls=%s assembled=%s",
                project_id,
                len(render_jobs),
                submitted_count,
                output_count,
                bool(assembly_result.get("assembled")) if assembly_result else False,
            )
        
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider=None,
            stage="generate_short_film",
            duration_ms=elapsed_ms(start_all),
            extra={"render_job_count": len(render_jobs), "assembled": bool(assembly_result.get("assembled")) if assembly_result else False},
        )
        
        return response

    def _ensure_canonical_project_before_render(self, project_id: str, project: Dict[str, Any]) -> None:
        storage = render_module._storage
        if storage is None:
            return
        try:
            existing = storage.get_project(project_id)
            if existing is not None:
                return
        except Exception:
            pass
        try:
            from app.models import StudioProject

            storage.save_project(
                StudioProject(
                    project_id=project_id,
                    title=str((project or {}).get("title") or project_id),
                    updated_at=str((project or {}).get("updated_at") or ""),
                )
            )
        except Exception as exc:
            logger.warning(
                "[OneButtonDebug] canonical project pre-sync failed project_id=%s error=%s",
                project_id,
                exc,
            )


generate_short_film_workflow_service = GenerateShortFilmWorkflowService()
