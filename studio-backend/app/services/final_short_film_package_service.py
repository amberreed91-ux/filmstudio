from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path
from urllib.parse import urlparse

from app.models import FinalShortFilmPackage
from app.services.short_film_stitching_service import short_film_stitching_service


class FinalShortFilmPackageService:
    """Service for managing final short film packages"""

    def __init__(self, storage=None, render_service=None, review_service=None, revision_service=None, video_asset_service=None):
        self._storage = storage
        self._render_service = render_service
        self._review_service = review_service
        self._revision_service = revision_service
        self._video_asset_service = video_asset_service
        self._outputs_root = Path(__file__).resolve().parents[2] / "outputs"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_package_id(self) -> str:
        return f"package-{uuid.uuid4().hex[:12]}"

    def validate_final_output_exists(self, final_output_url: str) -> bool:
        """Validate that the final output URL exists and is reachable"""
        if not final_output_url:
            return False
        
        # For local files, check if file exists
        if final_output_url.startswith('/outputs/'):
            file_path = self._outputs_root / final_output_url.removeprefix('/outputs/')
            return file_path.exists() and file_path.is_file()

        if final_output_url.startswith('/') or final_output_url.startswith('./'):
            file_path = Path(final_output_url)
            return file_path.exists() and file_path.is_file()
        
        # For remote URLs, we could do a HEAD request, but for now assume it's valid
        # In production, you might want to validate remote URLs
        return True

    def collect_project_render_metadata(self, project_id: str) -> Dict[str, Any]:
        """Collect render job metadata from the project"""
        metadata = {
            'render_job_ids': [],
            'scene_count': 0,
            'shot_count': 0,
        }
        
        if self._render_service:
            # Get all render jobs for the project
            jobs = self._render_service.list_jobs(project_id) if hasattr(self._render_service, 'list_jobs') else []
            
            for job in jobs:
                metadata['render_job_ids'].append(job.id)
                
                # Count unique scenes and shots
                if hasattr(job, 'shot_id'):
                    shot_id = job.shot_id
                    if '_' in shot_id:
                        scene_id = shot_id.split('_')[0] + '_' + shot_id.split('_')[1]
                        if scene_id not in metadata.get('scenes', set()):
                            metadata.setdefault('scenes', set()).add(scene_id)
                            metadata['scene_count'] = len(metadata['scenes'])
                    metadata['shot_count'] = len(set(job.id for job in jobs))
        
        return metadata

    def attach_latest_review(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Attach the latest review information"""
        if not self._review_service:
            return None
        
        latest_review = self._review_service.get_latest_review_for_project(project_id)
        if not latest_review:
            return None
        
        return {
            'review_id': latest_review.review_id,
            'review_decision': latest_review.decision,
        }

    def attach_completed_revisions(self, project_id: str) -> List[str]:
        """Attach completed revision IDs"""
        if not self._revision_service:
            return []
        
        revisions = self._revision_service.list_revisions_for_project(project_id)
        completed_revisions = [r.revision_id for r in revisions if r.status == 'complete']
        return completed_revisions

    def create_package_from_project(
        self,
        project_id: str,
        film_title: str,
        final_output_url: str,
        final_output_path: Optional[str] = None,
        has_title_card: bool = False,
        has_end_card: bool = False,
        has_soundtrack: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FinalShortFilmPackage:
        """Create a final package from a project"""
        
        # Validate final output exists
        if not self.validate_final_output_exists(final_output_url):
            raise ValueError(f"Final output URL does not exist or is not reachable: {final_output_url}")
        
        # Collect project metadata
        render_metadata = self.collect_project_render_metadata(project_id)
        review_info = self.attach_latest_review(project_id)
        completed_revisions = self.attach_completed_revisions(project_id)
        
        # Determine package status based on review
        package_status = "draft"
        if review_info:
            if review_info['review_decision'] == "approved":
                package_status = "approved"
            elif review_info['review_decision'] in ["pending", "needs_revision", "rejected"]:
                package_status = "ready_for_review"
        
        # Create package
        package = FinalShortFilmPackage(
            package_id=self._generate_package_id(),
            project_id=project_id,
            film_title=film_title,
            final_output_url=final_output_url,
            final_output_path=final_output_path,
            review_id=review_info['review_id'] if review_info else None,
            review_decision=review_info['review_decision'] if review_info else "pending",
            runtime_seconds=None,  # Could be calculated from video file if needed
            scene_count=render_metadata['scene_count'],
            shot_count=render_metadata['shot_count'],
            render_job_ids=render_metadata['render_job_ids'],
            revision_ids=completed_revisions,
            has_title_card=has_title_card,
            has_end_card=has_end_card,
            has_soundtrack=has_soundtrack,
            package_status=package_status,
            created_at=self._now_iso(),
            updated_at=self._now_iso(),
            metadata=metadata or {},
        )
        
        if self._storage:
            self._storage.save_final_short_film_package(package)

        if self._video_asset_service and final_output_url:
            try:
                self._video_asset_service.register_generated_output(
                    project_id=project_id,
                    source_url=final_output_url,
                    title=f"{film_title} (Final Package)",
                    description="Auto-registered from final short film package output",
                    metadata={
                        "package_id": package.package_id,
                        "origin": "final_short_film_package",
                    },
                )
            except Exception:
                # Keep package creation resilient even if asset registration fails.
                pass
        
        return package

    def _collect_completed_render_clips(self, project_id: str) -> List[Dict[str, Any]]:
        clips: List[Dict[str, Any]] = []
        if self._render_service and hasattr(self._render_service, "list_jobs"):
            jobs = self._render_service.list_jobs(project_id)
            for job in jobs:
                status = str(getattr(job, "status", "")).strip().lower()
                if status != "complete":
                    continue
                output_payload = getattr(job, "output_payload", None)
                raw_job = job.model_dump() if hasattr(job, "model_dump") else {}
                top_level_output_url = str(raw_job.get("output_url") or "") if isinstance(raw_job, dict) else ""
                output_url = str(
                    top_level_output_url
                    or getattr(output_payload, "asset_url", "")
                    or ""
                ).strip()
                if not output_url:
                    continue
                metadata = getattr(output_payload, "metadata", {}) or {}
                provider_mode = ""
                if isinstance(metadata, dict):
                    provider_mode = str(metadata.get("provider_mode") or "").strip().lower()
                clips.append(
                    {
                        "job_id": str(getattr(job, "id", "") or "").strip(),
                        "shot_id": str(getattr(job, "shot_id", "") or "").strip(),
                        "provider": str(getattr(job, "provider", "") or "").strip(),
                        "provider_mode": provider_mode,
                        "output_url": output_url,
                        "created_at": str(getattr(job, "created_at", "") or "").strip(),
                        "updated_at": str(getattr(job, "updated_at", "") or "").strip(),
                        "completed_at": str(getattr(job, "completed_at", "") or "").strip(),
                    }
                )

        try:
            from app.services.project_store import project_store

            project = project_store.get_project(project_id) or {}
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            summary_jobs = summary.get("one_button_render_jobs") if isinstance(summary.get("one_button_render_jobs"), list) else []
            for row in summary_jobs:
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or "").strip().lower()
                output_url = str(row.get("output_url") or "").strip()
                if status != "complete" or not output_url:
                    continue
                clips.append(
                    {
                        "job_id": str(row.get("job_id") or row.get("id") or "").strip(),
                        "shot_id": str(row.get("shot_id") or "").strip(),
                        "provider": str(row.get("provider") or "").strip(),
                        "provider_mode": str(row.get("provider_mode") or "").strip().lower(),
                        "output_url": output_url,
                        "created_at": str(row.get("created_at") or "").strip(),
                        "updated_at": str(row.get("updated_at") or "").strip(),
                        "completed_at": str(row.get("completed_at") or "").strip(),
                    }
                )
        except Exception:
            pass

        def _sort_key(row: Dict[str, Any]) -> str:
            return str(row.get("completed_at") or row.get("updated_at") or row.get("created_at") or "")

        clips.sort(key=_sort_key, reverse=True)
        return clips

    @staticmethod
    def _clip_sort_key(row: Dict[str, Any]) -> str:
        return str(row.get("completed_at") or row.get("updated_at") or row.get("created_at") or "")

    def _stitch_hosted_clips(self, project_id: str, clips: List[Dict[str, Any]]) -> Dict[str, Any]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        output_path = self._outputs_root / "final_films" / f"{project_id}_{timestamp}.mp4"
        with tempfile.TemporaryDirectory(prefix=f"final_pkg_{project_id}_") as temp_dir:
            work_dir = Path(temp_dir)
            try:
                clip_paths = short_film_stitching_service.download_or_stream_clips_safely(clips, work_dir)
            except Exception as exc:
                return {"status": "failed", "blocker": "clip_download_failed", "error_message": str(exc)}

            if len(clip_paths) < 2:
                return {"status": "failed", "blocker": "insufficient_clip_files", "error_message": "Need at least two clip files to stitch"}

            concat_list = short_film_stitching_service.build_ffmpeg_concat_list(clip_paths, work_dir)
            stitch_result = short_film_stitching_service.stitch_clips(concat_list, output_path, transcode=False)
            if stitch_result.get("status") != "completed":
                return stitch_result

        validation = short_film_stitching_service.validate_output_file(output_path)
        if not validation.get("valid"):
            return {"status": "failed", "blocker": validation.get("blocker") or "output_invalid", "error_message": "Stitched output validation failed"}

        return {
            "status": "completed",
            "output_path": str(output_path),
            "output_url": f"/outputs/final_films/{output_path.name}",
            "size_bytes": validation.get("size_bytes"),
        }

    def create_package_from_completed_renders(
        self,
        project_id: str,
        film_title: str,
        final_output_path: Optional[str] = None,
        has_title_card: bool = False,
        has_end_card: bool = False,
        has_soundtrack: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FinalShortFilmPackage:
        clips = self._collect_completed_render_clips(project_id)
        if not clips:
            raise ValueError("No completed render outputs available for package assembly")

        provided_metadata = dict(metadata or {})
        stitch_warnings: List[str] = []
        def _is_hosted_clip(clip: Dict[str, Any]) -> bool:
            if str(clip.get("provider_mode") or "").strip().lower() == "hosted_api":
                return True
            url = str(clip.get("output_url") or "").strip()
            if not url:
                return False
            parsed = urlparse(url)
            if parsed.scheme in {"http", "https"} and parsed.netloc and "storage.example.com" not in parsed.netloc:
                return True
            return False

        hosted_clips = [clip for clip in clips if _is_hosted_clip(clip)]
        preferred_clips = hosted_clips or clips
        ordered_preferred = sorted(preferred_clips, key=self._clip_sort_key)
        latest_clip = ordered_preferred[-1]

        if len(ordered_preferred) == 1:
            assembly_kind = "single_scene_preview"
            final_output_url = str(latest_clip.get("output_url") or "").strip()
            assembly_metadata = {
                "assembly_kind": assembly_kind,
                "stitched_video_available": True,
                "clip_count": 1,
                "source_render_job_ids": [latest_clip.get("job_id", "")],
                "clip_urls": [final_output_url],
                "stitch_status": "not_required",
            }
        elif len(hosted_clips) >= 2:
            ordered_hosted = sorted(hosted_clips, key=self._clip_sort_key)
            stitch_result = self._stitch_hosted_clips(project_id=project_id, clips=ordered_hosted)
            if stitch_result.get("status") == "completed":
                assembly_kind = "stitched_film"
                final_output_url = str(stitch_result.get("output_url") or "").strip()
                assembly_metadata = {
                    "assembly_kind": assembly_kind,
                    "stitched_video_available": True,
                    "clip_count": len(ordered_hosted),
                    "source_render_job_ids": [str(row.get("job_id") or "") for row in ordered_hosted],
                    "clip_urls": [str(row.get("output_url") or "") for row in ordered_hosted],
                    "stitch_status": "completed",
                    "stitched_output_path": str(stitch_result.get("output_path") or ""),
                }
            else:
                stitch_warnings.append(str(stitch_result.get("error_message") or stitch_result.get("blocker") or "stitch_failed"))
                assembly_kind = "assembled_manifest"
                final_output_url = f"manifest://{project_id}/latest"
                assembly_metadata = {
                    "assembly_kind": assembly_kind,
                    "stitched_video_available": False,
                    "clip_count": len(ordered_hosted),
                    "source_render_job_ids": [str(row.get("job_id") or "") for row in ordered_hosted],
                    "clip_urls": [str(row.get("output_url") or "") for row in ordered_hosted],
                    "stitch_status": "failed",
                    "stitch_error": str(stitch_result.get("error_message") or stitch_result.get("blocker") or "stitch_failed"),
                }
        else:
            assembly_kind = "assembled_manifest"
            final_output_url = f"manifest://{project_id}/latest"
            assembly_metadata = {
                "assembly_kind": assembly_kind,
                "stitched_video_available": False,
                "clip_count": len(ordered_preferred),
                "source_render_job_ids": [str(row.get("job_id") or "") for row in ordered_preferred],
                "clip_urls": [str(row.get("output_url") or "") for row in ordered_preferred],
                "stitch_status": "skipped_not_hosted",
            }

        merged_metadata = {**provided_metadata, **assembly_metadata}
        if stitch_warnings:
            merged_metadata["warnings"] = stitch_warnings
        package = self.create_package_from_project(
            project_id=project_id,
            film_title=film_title,
            final_output_url=final_output_url,
            final_output_path=final_output_path,
            has_title_card=has_title_card,
            has_end_card=has_end_card,
            has_soundtrack=has_soundtrack,
            metadata=merged_metadata,
        )
        if assembly_kind == "assembled_manifest":
            package.package_status = "ready_for_review"
            package.updated_at = self._now_iso()
            if self._storage:
                self._storage.update_final_short_film_package(package)
        return package

    def update_package_status(self, package_id: str, new_status: str) -> Optional[FinalShortFilmPackage]:
        """Update the status of a package"""
        package = self.get_package(package_id)
        if not package:
            return None
        
        # Validate status transition
        valid_statuses = ["draft", "ready_for_review", "approved", "packaged", "archived"]
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid package status: {new_status}. Must be one of: {valid_statuses}")
        
        package.package_status = new_status
        package.updated_at = self._now_iso()
        
        if self._storage:
            self._storage.update_final_short_film_package(package)
        
        return package

    def get_package(self, package_id: str) -> Optional[FinalShortFilmPackage]:
        """Get a package by ID"""
        if self._storage:
            return self._storage.get_final_short_film_package(package_id)
        return None

    def list_packages_for_project(self, project_id: str) -> List[FinalShortFilmPackage]:
        """List all packages for a project"""
        if self._storage:
            return self._storage.list_final_short_film_packages_for_project(project_id)
        return []

    def get_latest_package_for_project(self, project_id: str) -> Optional[FinalShortFilmPackage]:
        """Get the latest package for a project"""
        packages = self.list_packages_for_project(project_id)
        if not packages:
            return None
        
        # Return the most recently created package
        latest_package = max(packages, key=lambda p: p.created_at)
        return latest_package


# Global service instance
final_short_film_package_service = FinalShortFilmPackageService()
