from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.models import SoundtrackConfig
from app.services.audio_pipeline_service import audio_pipeline_service
from app.services.render import render_service
from app.services.short_film_stitching_service import short_film_stitching_service
from app.services.stability import ProviderError, StateError, ValidationError
from app.utils.helpers import (
    derive_scene_id_from_shot_id,
    derive_shot_number_from_shot_id,
)

logger = logging.getLogger(__name__)

SCENE_SCORE_AMBIENT_PROVIDERS = {"none", "manual_post_render", "ace_step", "musicgen"}


class SceneProductionPipelineService:
    """Coordinate ordered shot rendering, per-shot dialogue, and scene stitching."""

    def __init__(
        self,
        *,
        render_svc: Any = None,
        audio_svc: Any = None,
        stitching_svc: Any = None,
        backend_root: Path | None = None,
    ) -> None:
        self.render_service = render_svc or render_service
        self.audio_service = audio_svc or audio_pipeline_service
        self.stitching_service = stitching_svc or short_film_stitching_service
        self.backend_root = backend_root or Path(__file__).resolve().parents[2]

    async def generate_scene(
        self,
        *,
        project_id: str,
        scene_id: str,
        project: dict[str, Any],
        provider: str | None = None,
        overwrite: bool = False,
        on_audio_overrun: str = "freeze_last_frame",
        score_ambient_provider: str | None = None,
        soundtrack_config: SoundtrackConfig | None = None,
        save_project: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        if not project_id.strip() or not scene_id.strip():
            raise ValidationError("project_id and scene_id are required", stage="scene_pipeline")
        if not isinstance(project, dict):
            raise ValidationError("Project payload is required", stage="scene_pipeline")

        scene = self._find_scene(project, scene_id)
        if scene is None:
            raise StateError(f"Scene {scene_id} not found", stage="scene_pipeline")

        resolved_score_provider = self._normalize_scene_score_provider(score_ambient_provider)
        soundtrack_config = self._resolve_soundtrack_config(
            provider=resolved_score_provider,
            config=soundtrack_config,
        )
        per_shot_score_provider = "none" if resolved_score_provider == "manual_post_render" else resolved_score_provider

        shots = self._resolve_ordered_shots(project, scene)
        if not shots:
            raise StateError(f"Scene {scene_id} has no renderable shots", stage="scene_pipeline")

        working_project = deepcopy(project)
        summary = self._ensure_execution_summary(working_project)
        render_rows = summary.setdefault("one_button_render_jobs", [])
        if not isinstance(render_rows, list):
            render_rows = []
            summary["one_button_render_jobs"] = render_rows

        rendered_shots: list[dict[str, Any]] = []
        for index, shot in enumerate(shots, start=1):
            shot_id = str(shot.get("shot_id") or f"{scene_id}_shot_{index:03d}").strip()
            prompt = self._shot_prompt(scene, shot, index, len(shots))
            job = self.render_service.create_job(
                project_id=project_id,
                shot_id=shot_id,
                provider=provider,
                prompt=prompt,
                reference_assets=shot.get("reference_assets") or shot.get("source_refs") or [],
                parameters=shot.get("parameters") or {},
            )
            self._link_storyboard_render_if_present(shot, getattr(job, "id", ""))
            completed_job = await self._submit_and_wait(job.id)
            source_url = self._job_output_url(completed_job)
            source_path = self._local_output_path(source_url)
            if source_path is None:
                raise ProviderError(
                    f"Rendered shot {shot_id} does not have a local video path for audio merge",
                    stage="scene_pipeline_audio_merge",
                    metadata={"provider": getattr(completed_job, "provider", None), "shot_id": shot_id},
                )

            parameters = shot.get("parameters") or {}
            dialogue_lines = parameters["dialogue_lines"] if "dialogue_lines" in parameters else self._dialogue_lines_for_shot(working_project, scene_id, shot_id, allow_scene_fallback=len(shots) == 1)
            audio_result = await self.audio_service.generate_full_pipeline(
                scene_id=shot_id,
                project_id=project_id,
                scene_text=self._scene_text(scene),
                mood=str(scene.get("emotional_tone") or scene.get("tone") or ""),
                score_notes="",
                ambient_notes="",
                silence_flag=False,
                video_path=source_path,
                estimated_duration_seconds=float(shot.get("duration_seconds") or scene.get("duration_seconds") or 5.0),
                on_audio_overrun=on_audio_overrun,
                score_ambient_provider=per_shot_score_provider,
                characters=self._scene_characters(scene),
                dialogue_lines=dialogue_lines,
                scene_context={"scene": scene, "shot": shot, "shot_index": index, "shot_count": len(shots)},
            )
            final_url = audio_result.get("final_video_url") or source_url
            consistency = self._consistency_summary(completed_job)
            render_row = {
                "scene_id": scene_id,
                "shot_id": shot_id,
                "job_id": getattr(completed_job, "id", ""),
                "status": "complete",
                "provider": getattr(completed_job, "provider", provider or ""),
                "output_url": final_url,
                "source_output_url": source_url,
                "audio_pipeline_job_id": audio_result.get("job_id"),
                "dialogue_provider": audio_result.get("dialogue_provider"),
                "score_ambient_provider": resolved_score_provider,
                "per_shot_score_ambient_provider": audio_result.get("score_ambient_provider"),
                "consistency": consistency,
            }
            self._upsert_render_row(render_rows, render_row)
            rendered_shots.append(
                {
                    "shot_id": shot_id,
                    "render_job_id": getattr(completed_job, "id", ""),
                    "audio": audio_result,
                    "consistency": consistency,
                }
            )

        stitch_result = self.stitching_service.stitch_scene(
            project_id=project_id,
            scene_id=scene_id,
            project=working_project,
            overwrite=overwrite,
            soundtrack_config=soundtrack_config,
        )
        status = self._scene_status_from_stitch(stitch_result)
        assembly = self._scene_assembly_row(
            project_id=project_id,
            scene_id=scene_id,
            status=status,
            stitch_result=stitch_result,
            rendered_shots=rendered_shots,
            score_ambient_provider=resolved_score_provider,
            soundtrack_status=self._soundtrack_status(soundtrack_config),
        )
        self._upsert_scene_assembly(summary, assembly)

        if save_project is not None:
            saved = save_project(working_project)
            if isinstance(saved, dict):
                working_project = saved

        return {
            "status": status,
            "project_id": project_id,
            "scene_id": scene_id,
            "shots": rendered_shots,
            "stitch": stitch_result,
            "assembly": assembly,
            "output_url": stitch_result.get("output_url"),
            "score_ambient_provider": resolved_score_provider,
            "soundtrack_status": self._soundtrack_status(soundtrack_config),
        }

    def _link_storyboard_render_if_present(self, shot: dict[str, Any], render_job_id: str) -> None:
        parameters = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
        storyboard_meta = parameters.get("storyboard") if isinstance(parameters, dict) else None
        if not isinstance(storyboard_meta, dict) or not render_job_id:
            return
        try:
            from app.services.storyboard_blueprint_service import storyboard_blueprint_service

            storyboard_shot_id = str(storyboard_meta.get("storyboard_shot_id") or "").strip()
            storyboard_shot = storyboard_blueprint_service.storage.get_storyboard_shot(storyboard_shot_id)
            if storyboard_shot is not None:
                storyboard_blueprint_service.link_render_job(
                    shot=storyboard_shot,
                    render_job_id=render_job_id,
                    link_type=str(storyboard_meta.get("link_type") or "scene_pipeline_render"),
                )
        except Exception as exc:
            logger.debug("Storyboard scene-pipeline render link skipped for %s: %s", render_job_id, exc)

    def _find_scene(self, project: dict[str, Any], scene_id: str) -> dict[str, Any] | None:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        for container in (summary.get("scenes"), project.get("scenes")):
            if not isinstance(container, list):
                continue
            for scene in container:
                if isinstance(scene, dict) and str(scene.get("scene_id") or "") == scene_id:
                    return scene
        return None

    def _resolve_ordered_shots(self, project: dict[str, Any], scene: dict[str, Any]) -> list[dict[str, Any]]:
        scene_id = str(scene.get("scene_id") or "").strip()
        project_id = str(project.get("project_id") or "").strip()
        if project_id and scene_id:
            from app.services.storyboard_blueprint_service import storyboard_blueprint_service
            blueprint_shots = storyboard_blueprint_service.scene_render_inputs(project_id, scene_id)
            if blueprint_shots is not None:
                return blueprint_shots
        scene_shots = scene.get("shots")
        shots = [shot for shot in scene_shots if isinstance(shot, dict)] if isinstance(scene_shots, list) else []
        if not shots:
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            for candidate_key in ("shot_candidates", "scene_render_jobs", "video_render_assets"):
                candidates = summary.get(candidate_key) or []
                shots = [
                    item
                    for item in candidates
                    if isinstance(item, dict)
                    and (
                        str(item.get("scene_id") or "").strip() == scene_id
                        or derive_scene_id_from_shot_id(
                            str(item.get("shot_id") or "").strip()
                        ) == scene_id
                    )
                ]
                if shots:
                    break
        if not shots:
            ledger = scene.get("multi_shot_execution_ledger")
            if isinstance(ledger, list):
                shots = []
                for index, entry in enumerate(ledger, start=1):
                    if not isinstance(entry, dict):
                        continue
                    raw_id = str(entry.get("shot_id") or "").strip()
                    shot_id = (
                        raw_id
                        if derive_scene_id_from_shot_id(raw_id) == scene_id
                        else f"shot_{scene_id}_{derive_shot_number_from_shot_id(raw_id) or index:03d}"
                    )
                    prompt_pack = entry.get("prompt_pack") if isinstance(entry.get("prompt_pack"), dict) else {}
                    shots.append(
                        {
                            **entry,
                            "scene_id": scene_id,
                            "shot_id": shot_id,
                            "description": (
                                entry.get("description")
                                or prompt_pack.get("base_prompt")
                                or self._scene_text(scene)
                            ),
                        }
                    )
        if not shots:
            shots = [{"shot_id": f"{scene_id}_shot_001", "description": self._scene_text(scene)}]
        return sorted(
            shots,
            key=lambda item: (
                derive_shot_number_from_shot_id(str(item.get("shot_id") or ""))
                or 999999,
                str(item.get("shot_id") or ""),
            ),
        )

    def _shot_prompt(self, scene: dict[str, Any], shot: dict[str, Any], index: int, total: int) -> str:
        base = str(
            shot.get("prompt")
            or shot.get("description")
            or shot.get("visual_description")
            or self._scene_text(scene)
        ).strip()
        position = f"Shot {index} of {total} in scene. Maintain character identity and visual continuity."
        return f"{base}\n\n[SHOT POSITION]\n{position}".strip()

    def _scene_text(self, scene: dict[str, Any]) -> str:
        return str(
            scene.get("scene_text")
            or scene.get("script_text")
            or scene.get("text")
            or scene.get("description")
            or scene.get("summary")
            or ""
        ).strip()

    def _scene_characters(self, scene: dict[str, Any]) -> list[str]:
        raw = scene.get("characters") or []
        if not isinstance(raw, list):
            return []
        names: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict) and str(item.get("name") or "").strip():
                names.append(str(item["name"]).strip())
        return names

    def _dialogue_lines_for_shot(
        self,
        project: dict[str, Any],
        scene_id: str,
        shot_id: str,
        *,
        allow_scene_fallback: bool = False,
    ) -> list[dict[str, str]] | None:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        raw_lines = summary.get("dialogue_lines")
        if not isinstance(raw_lines, list):
            return None if allow_scene_fallback else []
        lines: list[dict[str, str]] = []
        for line in raw_lines:
            if not isinstance(line, dict) or str(line.get("scene_id") or "") != scene_id:
                continue
            line_shot_id = str(line.get("shot_id") or "").strip()
            if line_shot_id != shot_id and not (allow_scene_fallback and not line_shot_id):
                continue
            lines.append({str(key): str(value) for key, value in line.items() if value is not None})
        return lines if lines or not allow_scene_fallback else None

    async def _submit_and_wait(self, job_id: str, max_attempts: int = 90) -> Any:
        job = await self.render_service.submit_job(job_id)
        attempts = 0
        while getattr(job, "status", "") != "needs_review" and not getattr(job, "is_terminal", lambda: True)() and attempts < max_attempts:
            await asyncio.sleep(1)
            job = await self.render_service.get_job_status(job_id)
            attempts += 1
        if getattr(job, "status", "") == "needs_review":
            raise StateError(getattr(job, "error_message", None) or "Review required shot facts before rendering", stage="scene_pipeline_render")
        if getattr(job, "status", "") != "complete":
            raise ProviderError(
                f"Render job {job_id} did not complete",
                stage="scene_pipeline_render",
                metadata={"provider": getattr(job, "provider", None), "job_id": job_id},
            )
        return job

    def _job_output_url(self, job: Any) -> str:
        output = getattr(job, "output_payload", None)
        url = getattr(output, "asset_url", None) if output is not None else None
        if not isinstance(url, str) or not url.strip():
            raise ProviderError(
                f"Render job {getattr(job, 'id', '')} completed without output_url",
                stage="scene_pipeline_render",
                metadata={"provider": getattr(job, "provider", None), "job_id": getattr(job, "id", "")},
            )
        return url.strip()

    def _local_output_path(self, url_or_path: str) -> Path | None:
        value = str(url_or_path or "").strip()
        if not value:
            return None
        path = Path(value)
        if path.is_absolute() and path.exists():
            return path
        if value.startswith("/outputs/"):
            candidate = self.backend_root / value.lstrip("/")
            return candidate if candidate.exists() else None
        if value.startswith("outputs/"):
            candidate = self.backend_root / value
            return candidate if candidate.exists() else None
        return None

    def _ensure_execution_summary(self, project: dict[str, Any]) -> dict[str, Any]:
        summary = project.get("execution_summary")
        if not isinstance(summary, dict):
            summary = {}
            project["execution_summary"] = summary
        scenes = summary.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            project_scenes = project.get("scenes")
            if isinstance(project_scenes, list):
                summary["scenes"] = project_scenes
        return summary

    def _upsert_render_row(self, rows: list[Any], row: dict[str, Any]) -> None:
        for index, existing in enumerate(rows):
            if (
                isinstance(existing, dict)
                and str(existing.get("scene_id") or "") == row["scene_id"]
                and str(existing.get("shot_id") or "") == row["shot_id"]
            ):
                rows[index] = row
                return
        rows.append(row)

    def _scene_status_from_stitch(self, stitch_result: dict[str, Any]) -> str:
        return "complete" if stitch_result.get("status") in {"complete", "completed", "existing"} else "failed"

    def _scene_assembly_row(
        self,
        *,
        project_id: str,
        scene_id: str,
        status: str,
        stitch_result: dict[str, Any],
        rendered_shots: list[dict[str, Any]],
        score_ambient_provider: str,
        soundtrack_status: str,
    ) -> dict[str, Any]:
        return {
            "assembly_id": f"{project_id}_{scene_id}",
            "project_id": project_id,
            "scene_id": scene_id,
            "status": status,
            "output_url": stitch_result.get("output_url"),
            "output_path": stitch_result.get("output_path"),
            "duration_seconds": stitch_result.get("duration_seconds"),
            "clip_count": stitch_result.get("clip_count", len(rendered_shots)),
            "shot_ids": stitch_result.get("shot_ids") or [str(row.get("shot_id") or "") for row in rendered_shots],
            "score_ambient_provider": score_ambient_provider,
            "soundtrack_status": soundtrack_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _upsert_scene_assembly(self, summary: dict[str, Any], row: dict[str, Any]) -> None:
        assemblies = summary.setdefault("scene_pipeline_assemblies", [])
        if not isinstance(assemblies, list):
            assemblies = []
            summary["scene_pipeline_assemblies"] = assemblies
        for index, existing in enumerate(assemblies):
            if isinstance(existing, dict) and str(existing.get("scene_id") or "") == row["scene_id"]:
                assemblies[index] = row
                return
        assemblies.append(row)

    def _soundtrack_status(self, config: SoundtrackConfig | None) -> str:
        if not config or not config.enabled:
            return "deferred"
        if config.audio_url or config.local_audio_path:
            return "manual_post_render"
        return str(config.audio_source_type or "configured")

    def _consistency_summary(self, job: Any) -> dict[str, Any]:
        input_payload = getattr(job, "input_payload", None)
        payload = getattr(input_payload, "consistency_payload", None)
        explicit_refs = getattr(input_payload, "referenceAssets", None)
        if payload is None:
            return {
                "mode": "none",
                "attached": False,
                "reference_count": len(explicit_refs) if isinstance(explicit_refs, list) else 0,
                "reference_kinds": [],
                "primary_reference_url": None,
            }
        refs = getattr(payload, "refs", None)
        ref_items = refs if isinstance(refs, list) else []
        weights = getattr(payload, "weights", {}) if isinstance(getattr(payload, "weights", {}), dict) else {}
        primary = None
        char_full = [ref for ref in ref_items if getattr(ref, "kind", "") == "character_full"]
        if char_full:
            primary = max(char_full, key=lambda ref: weights.get(getattr(ref, "ref_id", ""), 0.0))
        return {
            "mode": getattr(payload, "mode", "identity_lock"),
            "attached": True,
            "reference_count": len(ref_items),
            "reference_kinds": [getattr(ref, "kind", "") for ref in ref_items],
            "primary_reference_url": getattr(primary, "image_url", None) if primary is not None else None,
        }

    def _normalize_scene_score_provider(self, provider: str | None) -> str:
        normalized = (provider or "none").strip().lower()
        aliases = {
            "": "none",
            "off": "none",
            "skip": "none",
            "disabled": "none",
            "no_provider": "none",
            "no-provider": "none",
            "manual": "manual_post_render",
            "manual-post-render": "manual_post_render",
            "manual_post": "manual_post_render",
            "post_render": "manual_post_render",
            "post-render": "manual_post_render",
            "ace": "ace_step",
            "ace-step": "ace_step",
            "acestep": "ace_step",
            "music_gen": "musicgen",
            "music-gen": "musicgen",
            "musicgen-small": "musicgen",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in SCENE_SCORE_AMBIENT_PROVIDERS:
            raise ValidationError(
                "Scene score/ambient provider must be one of "
                f"{sorted(SCENE_SCORE_AMBIENT_PROVIDERS)}",
                stage="scene_soundtrack",
                metadata={"provider": provider},
            )
        return normalized

    def _resolve_soundtrack_config(
        self,
        *,
        provider: str,
        config: SoundtrackConfig | None,
    ) -> SoundtrackConfig | None:
        if provider != "manual_post_render":
            return config
        if not config or not config.enabled or not (config.audio_url or config.local_audio_path):
            raise ValidationError(
                "manual_post_render score/ambient requires a scene-level soundtrack source",
                stage="scene_soundtrack",
                metadata={"provider": provider},
            )
        config.audio_source_type = config.audio_source_type or "local_file"
        return config


scene_production_pipeline_service = SceneProductionPipelineService()
