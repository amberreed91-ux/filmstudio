"""
Export Package Service.

Assembles a complete film package: final cut, scene manifest, continuity report,
director notes, and render lineage.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("studio-export-package")


class ExportPackageService:
    """Service for building export packages."""

    def __init__(self, storage=None):
        self._storage = storage

    def _now_iso(self) -> str:
        """Return current time in ISO format."""
        return datetime.now().isoformat()

    async def build_export_package(
        self,
        project_id: str,
        include_continuity_report: bool = True,
        include_render_lineage: bool = True,
        include_director_notes: bool = True,
    ) -> dict:
        """
        Build a complete export package for a project.

        Args:
            project_id: The project identifier.
            include_continuity_report: Include continuity analysis.
            include_render_lineage: Include full render job history.
            include_director_notes: Include director intent and session debriefs.

        Returns:
            Export package dict with manifest, reports, and honest assembly note.
        """
        package_id = f"export_{uuid.uuid4().hex[:12]}"
        export_timestamp = self._now_iso()

        # Load project data
        if not self._storage:
            raise ValueError("Storage not configured")

        project = self._storage.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        project_data = project.model_dump(mode='json')

        # Build manifest
        manifest = await self._build_manifest(project_id, project_data, export_timestamp)

        # Build continuity report
        continuity_report = None
        if include_continuity_report:
            continuity_report = await self._build_continuity_report(project_id)

        # Build render lineage
        render_lineage = None
        if include_render_lineage:
            render_lineage = await self._build_render_lineage(project_id)

        # Build director notes
        director_notes = None
        if include_director_notes:
            director_notes = await self._build_director_notes(project_id)

        # Get Film DNA snapshot
        film_dna_snapshot = None
        try:
            film_dna_snapshot = self._storage.load_film_dna(project_id)
        except Exception as e:
            logger.debug(f"Could not load Film DNA: {e}")

        # Get stitched film URL if available
        stitched_film_url = await self._get_stitched_film_url(project_id)

        # Generate honest assembly note
        honest_assembly_note = self._generate_honest_assembly_note(
            manifest, stitched_film_url
        )

        package = {
            "package_id": package_id,
            "project_id": project_id,
            "status": "complete",
            "manifest": manifest,
            "continuity_report": continuity_report,
            "render_lineage": render_lineage,
            "director_notes": director_notes,
            "film_dna_snapshot": film_dna_snapshot,
            "stitched_film_url": stitched_film_url,
            "honest_assembly_note": honest_assembly_note,
            "created_at": export_timestamp,
        }

        # Store package
        self._storage.save_export_package(project_id, package)

        return package

    async def _build_manifest(
        self, project_id: str, project_data: dict, export_timestamp: str
    ) -> dict:
        """
        Build the scene manifest.

        Args:
            project_id: The project identifier.
            project_data: Full project state.
            export_timestamp: ISO timestamp of export.

        Returns:
            Manifest dict with film metadata and scene/shot structure.
        """
        film_title = project_data.get("title", "Untitled Film")
        render_provider_data = project_data.get("render_provider")
        if render_provider_data and isinstance(render_provider_data, dict):
            render_provider = render_provider_data.get("provider_name", "Unknown")
        else:
            render_provider = "Unknown"

        # Extract scenes from execution_summary
        execution_summary = project_data.get("execution_summary", {})
        scenes_data = execution_summary.get("scenes", [])

        scenes = []
        total_shots = 0

        for idx, scene_data in enumerate(scenes_data):
            if not isinstance(scene_data, dict):
                continue

            scene_id = scene_data.get("scene_id", f"scene_{idx + 1}")
            scene_title = scene_data.get("title", f"Scene {idx + 1}")
            shots_data = scene_data.get("shots", [])

            shots = []
            for shot_data in shots_data:
                if not isinstance(shot_data, dict):
                    continue

                shot_id = shot_data.get("shot_id", "")
                render_job_id = shot_data.get("render_job_id")
                output_url = shot_data.get("output_url")
                status = shot_data.get("status", "pending")
                continuity_review_passed = shot_data.get("continuity_review_passed")

                shots.append({
                    "shot_id": shot_id,
                    "render_job_id": render_job_id,
                    "output_url": output_url,
                    "status": status,
                    "continuity_review_passed": continuity_review_passed,
                })
                total_shots += 1

            scenes.append({
                "scene_id": scene_id,
                "title": scene_title,
                "order_index": idx,
                "shots": shots,
            })

        return {
            "film_title": film_title,
            "scene_count": len(scenes),
            "total_shots": total_shots,
            "render_provider": render_provider,
            "export_timestamp": export_timestamp,
            "scenes": scenes,
        }

    async def _build_continuity_report(self, project_id: str) -> Optional[dict]:
        """
        Build the continuity report.

        Includes:
        - Motif thread analysis
        - Arc completeness
        - Active contradictions

        Args:
            project_id: The project identifier.

        Returns:
            Continuity report dict or None if unavailable.
        """
        report = {}

        # Get motif thread analysis
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service,
            )

            motif_analysis = await continuity_intelligence_service.get_motif_thread_analysis(
                project_id
            )
            report["motif_thread_analysis"] = motif_analysis
        except Exception as e:
            logger.debug(f"Could not get motif thread analysis: {e}")
            report["motif_thread_analysis"] = None

        # Get arc completeness
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service,
            )

            arc_completeness = await continuity_intelligence_service.check_arc_completeness(
                project_id
            )
            report["arc_completeness"] = arc_completeness
        except Exception as e:
            logger.debug(f"Could not get arc completeness: {e}")
            report["arc_completeness"] = None

        # Get active contradictions from continuity graph
        try:
            graph = self._storage.load_continuity_graph(project_id)
            if graph:
                contradictions = []
                for node in graph.get("nodes", []):
                    if isinstance(node, dict) and node.get("contradicted"):
                        contradictions.append({
                            "scene_id": node.get("scene_id"),
                            "element_type": node.get("element_type"),
                            "element_id": node.get("element_id"),
                            "contradiction_notes": node.get("contradiction_notes", ""),
                        })
                report["active_contradictions"] = contradictions
            else:
                report["active_contradictions"] = []
        except Exception as e:
            logger.debug(f"Could not get active contradictions: {e}")
            report["active_contradictions"] = []

        return report if any(report.values()) else None

    async def _build_render_lineage(self, project_id: str) -> Optional[List[dict]]:
        """
        Build render lineage - full render job history per shot.

        Args:
            project_id: The project identifier.

        Returns:
            List of shot lineages with all render jobs.
        """
        try:
            # Get all render jobs for this project from render_jobs table
            with self._storage._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, project_id, shot_id, provider, provider_job_id,
                           status, progress, input_payload, output_payload,
                           error_message, retry_count, created_at, updated_at, completed_at
                    FROM render_jobs
                    WHERE project_id = ?
                    ORDER BY created_at ASC
                    """,
                    (project_id,),
                )
                rows = cursor.fetchall()
                
                if not rows:
                    return None
                
                # Convert rows to dicts
                jobs = []
                for row in rows:
                    job_dict = dict(row)
                    jobs.append(job_dict)
                
                # Group by shot_id
                lineage_by_shot: Dict[str, List[dict]] = {}
                for job in jobs:
                    shot_id = job.get("shot_id", "")
                    if shot_id not in lineage_by_shot:
                        lineage_by_shot[shot_id] = []
                    lineage_by_shot[shot_id].append(job)
                
                # Build lineage list
                lineage = []
                for shot_id, jobs_list in lineage_by_shot.items():
                    lineage.append({
                        "shot_id": shot_id,
                        "jobs": jobs_list,
                    })
                
                return lineage if lineage else None

        except Exception as e:
            logger.debug(f"Could not build render lineage: {e}")
            return None

    async def _build_director_notes(self, project_id: str) -> Optional[dict]:
        """
        Build director notes.

        Includes:
        - Director intent
        - Session debriefs summary (most recent 5)

        Args:
            project_id: The project identifier.

        Returns:
            Director notes dict or None if unavailable.
        """
        notes = {}

        # Get director intent
        try:
            intent = self._storage.load_director_intent(project_id)
            notes["director_intent"] = intent
        except Exception as e:
            logger.debug(f"Could not load director intent: {e}")
            notes["director_intent"] = None

        # Get session debriefs summary
        try:
            debriefs = self._storage.list_session_debriefs(project_id, limit=5)
            notes["recent_session_debriefs"] = debriefs
        except Exception as e:
            logger.debug(f"Could not load session debriefs: {e}")
            notes["recent_session_debriefs"] = []

        return notes if any(notes.values()) else None

    async def _get_stitched_film_url(self, project_id: str) -> Optional[str]:
        """
        Get stitched film URL if available.

        Args:
            project_id: The project identifier.

        Returns:
            Film URL or None if not available.
        """
        try:
            # Check for final short film package
            packages = self._storage.list_final_short_film_packages(project_id)
            if packages:
                # Get most recent package
                latest = packages[0]
                if latest.get("package_status") == "complete":
                    return latest.get("final_output_url")
        except Exception as e:
            logger.debug(f"Could not get stitched film URL: {e}")

        return None

    def _generate_honest_assembly_note(
        self, manifest: dict, stitched_film_url: Optional[str]
    ) -> str:
        """
        Generate honest assembly note that accurately reflects reality.

        Args:
            manifest: The scene manifest.
            stitched_film_url: URL to stitched film if available.

        Returns:
            Honest assembly note string.
        """
        total_shots = manifest.get("total_shots", 0)

        # Count completed renders
        completed_count = 0
        for scene in manifest.get("scenes", []):
            for shot in scene.get("shots", []):
                if shot.get("status") == "complete" and shot.get("output_url"):
                    completed_count += 1

        if stitched_film_url and completed_count == total_shots and total_shots > 0:
            return f"Stitched film assembled from {completed_count} completed render outputs."
        elif completed_count > 0 and completed_count < total_shots:
            missing = total_shots - completed_count
            return f"Package contains {completed_count} of {total_shots} shots with completed renders. {missing} shot(s) have no render output."
        elif completed_count == 0:
            return "No completed render outputs. Package contains scene manifest only."
        elif completed_count == total_shots and total_shots > 0:
            return f"All {completed_count} shots have completed renders. Stitched film may be available separately."
        else:
            return "Package contains scene manifest. Render status varies."

    def get_festival_presets(self) -> dict:
        """
        Get available festival presets.

        Returns:
            Dict of preset_id -> festival_specs.
        """
        return FESTIVAL_PRESETS.copy()

    async def validate_for_festival(
        self,
        package_id: str,
        festival_specs: dict,
    ) -> dict:
        """
        Validate an export package against festival specifications.

        Args:
            package_id: The package identifier.
            festival_specs: Festival requirements dict.

        Returns:
            Validation result with flags and honest note.
        """
        # Load package
        if not self._storage:
            raise ValueError("Storage not configured")

        package = self._storage.load_export_package(package_id)
        if not package:
            raise ValueError(f"Package {package_id} not found")

        festival_name = festival_specs.get("festival_name", "Unknown Festival")
        flags = []
        unknown_count = 0

        # Validate runtime
        runtime_flag = await self._validate_runtime(package, festival_specs)
        flags.append(runtime_flag)
        if runtime_flag["status"] == "unknown":
            unknown_count += 1

        # Validate format
        format_flag = await self._validate_format(package, festival_specs)
        flags.append(format_flag)
        if format_flag["status"] == "unknown":
            unknown_count += 1

        # Validate resolution
        resolution_flag = await self._validate_resolution(package, festival_specs)
        flags.append(resolution_flag)
        if resolution_flag["status"] == "unknown":
            unknown_count += 1

        # Validate aspect ratio
        aspect_flag = await self._validate_aspect_ratio(package, festival_specs)
        flags.append(aspect_flag)
        if aspect_flag["status"] == "unknown":
            unknown_count += 1

        # Validate file size
        file_size_flag = await self._validate_file_size(package, festival_specs)
        flags.append(file_size_flag)
        if file_size_flag["status"] == "unknown":
            unknown_count += 1

        # Validate subtitles
        subtitles_flag = await self._validate_subtitles(package, festival_specs)
        flags.append(subtitles_flag)
        if subtitles_flag["status"] == "unknown":
            unknown_count += 1

        # Validate color grading note
        color_flag = await self._validate_color_grading(package, festival_specs)
        flags.append(color_flag)
        if color_flag["status"] == "unknown":
            unknown_count += 1

        # Validate custom requirements
        custom_flags = await self._validate_custom_requirements(package, festival_specs)
        for flag in custom_flags:
            flags.append(flag)
            if flag["status"] == "unknown":
                unknown_count += 1

        # Remove flags with None requirement (skipped checks)
        flags = [f for f in flags if f["requirement"] is not None]

        # Determine overall validity
        blocking_unmet = any(f["blocking"] and f["status"] == "unmet" for f in flags)
        valid = not blocking_unmet

        # Generate advisory
        advisory = self._generate_festival_advisory(flags, festival_name)

        # Generate honest note
        total_requirements = len(flags)
        honest_note = f"{unknown_count} of {total_requirements} requirements could not be verified from available package data."

        return {
            "festival_name": festival_name,
            "package_id": package_id,
            "valid": valid,
            "flags": flags,
            "advisory": advisory,
            "unknown_count": unknown_count,
            "honest_note": honest_note,
        }

    async def _validate_runtime(self, package: dict, specs: dict) -> dict:
        """Validate runtime requirements."""
        max_runtime = specs.get("max_runtime_minutes")
        min_runtime = specs.get("min_runtime_minutes")

        if max_runtime is None and min_runtime is None:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        if max_runtime:
            return {
                "requirement": f"Maximum runtime: {max_runtime} minutes",
                "status": "unknown",
                "note": "Runtime cannot be verified without scene duration data. Please verify manually.",
                "blocking": False,
            }
        elif min_runtime:
            return {
                "requirement": f"Minimum runtime: {min_runtime} minutes",
                "status": "unknown",
                "note": "Runtime cannot be verified without scene duration data. Please verify manually.",
                "blocking": False,
            }

        return {"requirement": None, "status": "met", "note": "", "blocking": False}

    async def _validate_format(self, package: dict, specs: dict) -> dict:
        """Validate format requirements."""
        required_format = specs.get("required_format")

        if not required_format:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        # Check if we have render outputs
        manifest = package.get("manifest", {})
        has_renders = False
        for scene in manifest.get("scenes", []):
            for shot in scene.get("shots", []):
                if shot.get("output_url"):
                    has_renders = True
                    break

        if not has_renders:
            return {
                "requirement": f"Required format: {required_format}",
                "status": "unknown",
                "note": "No completed renders available to verify format. Please verify manually after rendering.",
                "blocking": False,
            }

        return {
            "requirement": f"Required format: {required_format}",
            "status": "unknown",
            "note": "Format cannot be automatically verified. Please check render output format manually.",
            "blocking": False,
        }

    async def _validate_resolution(self, package: dict, specs: dict) -> dict:
        """Validate resolution requirements."""
        required_resolution = specs.get("required_resolution")

        if not required_resolution:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        # Check if we have render outputs
        manifest = package.get("manifest", {})
        has_renders = False
        for scene in manifest.get("scenes", []):
            for shot in scene.get("shots", []):
                if shot.get("output_url"):
                    has_renders = True
                    break

        if not has_renders:
            return {
                "requirement": f"Required resolution: {required_resolution}",
                "status": "unknown",
                "note": "No completed renders available to verify resolution. Please verify manually after rendering.",
                "blocking": False,
            }

        return {
            "requirement": f"Required resolution: {required_resolution}",
            "status": "unknown",
            "note": "Resolution cannot be automatically verified. Please check render output resolution manually.",
            "blocking": False,
        }

    async def _validate_aspect_ratio(self, package: dict, specs: dict) -> dict:
        """Validate aspect ratio requirements."""
        required_aspect = specs.get("required_aspect_ratio")

        if not required_aspect:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        return {
            "requirement": f"Required aspect ratio: {required_aspect}",
            "status": "unknown",
            "note": "Aspect ratio cannot be automatically verified. Please check render output manually.",
            "blocking": False,
        }

    async def _validate_file_size(self, package: dict, specs: dict) -> dict:
        """Validate file size requirements."""
        max_file_size = specs.get("max_file_size_mb")

        if not max_file_size:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        return {
            "requirement": f"Maximum file size: {max_file_size} MB",
            "status": "unknown",
            "note": "File size cannot be verified without downloading the file. Please check manually.",
            "blocking": False,
        }

    async def _validate_subtitles(self, package: dict, specs: dict) -> dict:
        """Validate subtitle requirements."""
        requires_subtitles = specs.get("requires_subtitles", False)

        if not requires_subtitles:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        return {
            "requirement": "Subtitles required",
            "status": "unknown",
            "note": "Subtitle presence cannot be automatically verified. Please ensure subtitles are included.",
            "blocking": False,
        }

    async def _validate_color_grading(self, package: dict, specs: dict) -> dict:
        """Validate color grading note requirements."""
        requires_color_grading = specs.get("requires_color_grading_note", False)

        if not requires_color_grading:
            return {"requirement": None, "status": "met", "note": "", "blocking": False}

        return {
            "requirement": "Color grading note required",
            "status": "unknown",
            "note": "Color grading documentation cannot be automatically verified. Please include color grading notes.",
            "blocking": False,
        }

    async def _validate_custom_requirements(
        self, package: dict, specs: dict
    ) -> List[dict]:
        """Validate custom requirements."""
        custom_requirements = specs.get("custom_requirements", [])

        flags = []
        for requirement in custom_requirements:
            flags.append({
                "requirement": requirement,
                "status": "unknown",
                "note": "This requirement cannot be automatically verified. Please check manually.",
                "blocking": False,
            })

        return flags

    def _generate_festival_advisory(self, flags: List[dict], festival_name: str) -> str:
        """Generate advisory message for festival validation."""
        unmet_count = sum(1 for f in flags if f["status"] == "unmet")
        unknown_count = sum(1 for f in flags if f["status"] == "unknown")

        if unmet_count > 0:
            return f"Package has {unmet_count} requirement(s) that need attention for {festival_name}. Review flagged items before submission."
        elif unknown_count > 0:
            return f"Package has {unknown_count} requirement(s) that could not be automatically verified. Manual review recommended before submitting to {festival_name}."
        else:
            return f"All verifiable requirements met for {festival_name}. Manual review still recommended."


# Festival presets
FESTIVAL_PRESETS = {
    "sundance": {
        "festival_name": "Sundance Film Festival",
        "max_runtime_minutes": 120.0,
        "min_runtime_minutes": None,
        "required_format": "DCP or ProRes",
        "required_resolution": "1920x1080 or higher",
        "required_aspect_ratio": None,
        "max_file_size_mb": None,
        "requires_subtitles": False,
        "requires_color_grading_note": True,
        "custom_requirements": [
            "Closed captions for dialogue",
            "Stereo or 5.1 audio mix",
        ],
    },
    "tribeca": {
        "festival_name": "Tribeca Film Festival",
        "max_runtime_minutes": 40.0,
        "min_runtime_minutes": None,
        "required_format": "DCP, ProRes, or H.264",
        "required_resolution": "1920x1080",
        "required_aspect_ratio": "16:9",
        "max_file_size_mb": 5000.0,
        "requires_subtitles": False,
        "requires_color_grading_note": False,
        "custom_requirements": [
            "Stereo audio minimum",
        ],
    },
    "sxsw": {
        "festival_name": "SXSW Film Festival",
        "max_runtime_minutes": 30.0,
        "min_runtime_minutes": None,
        "required_format": "DCP or ProRes",
        "required_resolution": "1920x1080 or 3840x2160",
        "required_aspect_ratio": None,
        "max_file_size_mb": None,
        "requires_subtitles": False,
        "requires_color_grading_note": False,
        "custom_requirements": [
            "Stereo or 5.1 audio",
            "Color corrected and graded",
        ],
    },
    "generic_short": {
        "festival_name": "Generic Short Film Festival",
        "max_runtime_minutes": 40.0,
        "min_runtime_minutes": None,
        "required_format": "mp4",
        "required_resolution": "1920x1080",
        "required_aspect_ratio": "16:9",
        "max_file_size_mb": 2000.0,
        "requires_subtitles": False,
        "requires_color_grading_note": False,
        "custom_requirements": [],
    },
}


# Singleton instance
export_package_service = ExportPackageService()


