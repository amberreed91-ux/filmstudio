from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models import ClipRevision

logger = logging.getLogger("clip-revision-service")


class ClipRevisionService:
    """Service for managing clip revisions from reviewed short films"""

    def __init__(self, storage=None, render_service=None):
        self._storage = storage
        self._render_service = render_service

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_revision_id(self) -> str:
        return f"revision-{uuid.uuid4().hex[:12]}"

    def create_revision(
        self,
        project_id: str,
        review_id: str,
        original_job_id: str,
        provider: str,
        revision_prompt: str,
        revision_reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ClipRevision:
        """Create a new clip revision"""
        _metadata = dict(metadata or {})
        try:
            from app.services.identity_snapshot_service import identity_snapshot_service

            _metadata = identity_snapshot_service.attach_to_metadata(_metadata, project_id)
        except Exception as exc:  # noqa: BLE001 — identity snapshot is advisory only
            logger.warning("identity snapshot attach failed for %s: %s", project_id, exc)

        revision = ClipRevision(
            revision_id=self._generate_revision_id(),
            project_id=project_id,
            review_id=review_id,
            original_job_id=original_job_id,
            new_job_id=None,
            provider=provider,
            revision_prompt=revision_prompt,
            revision_reason=revision_reason,
            status="pending",
            output_url=None,
            created_at=self._now_iso(),
            updated_at=self._now_iso(),
            metadata=_metadata,
        )
        
        if self._storage:
            self._storage.save_clip_revision(revision)
        if self._render_service:
            try:
                original_job = self._render_service.get_job(original_job_id)
                if original_job:
                    from app.services.storyboard_blueprint_service import storyboard_blueprint_service

                    storyboard_blueprint_service.storage = self._storage or storyboard_blueprint_service.storage
                    link = storyboard_blueprint_service.link_revision_from_job(
                        project_id=project_id,
                        revision_id=revision.revision_id,
                        original_job=original_job,
                        change_scope={
                            "revision_reason": revision_reason,
                            "revision_prompt": revision_prompt,
                        },
                    )
                    if link:
                        revision.metadata = {
                            **(revision.metadata or {}),
                            "storyboard_revision_link_id": link.link_id,
                            "storyboard_original_version_id": link.original_version_id,
                        }
                        if self._storage:
                            self._storage.update_clip_revision(revision)
            except Exception:
                pass
        
        return revision

    def submit_revision_render(
        self,
        revision_id: str,
        provider_override: Optional[str] = None,
    ) -> Optional[ClipRevision]:
        """Submit a revision render job"""
        revision = self.get_revision(revision_id)
        if not revision:
            return None
        
        if not revision.can_submit():
            raise ValueError(f"Revision {revision_id} cannot be submitted in status: {revision.status}")
        
        # Get original job to copy parameters
        original_job = None
        if self._render_service:
            original_job = self._render_service.get_job(revision.original_job_id)
        
        if not original_job:
            raise ValueError(f"Original job {revision.original_job_id} not found")
        
        # Create new render job with revision prompt
        provider_to_use = provider_override or revision.provider
        
        # Extract original job parameters
        original_prompt = ""
        reference_assets = []
        parameters = {}
        
        if hasattr(original_job, 'input_payload'):
            if hasattr(original_job.input_payload, 'prompt'):
                original_prompt = original_job.input_payload.prompt
            if hasattr(original_job.input_payload, 'referenceAssets'):
                reference_assets = original_job.input_payload.referenceAssets or []
            if hasattr(original_job.input_payload, 'parameters'):
                parameters = original_job.input_payload.parameters or {}
        if isinstance(parameters, dict) and isinstance(parameters.get("storyboard"), dict):
            parameters = dict(parameters)
            parameters["storyboard"] = {
                **parameters["storyboard"],
                "link_type": "revision_render",
                "revision_id": revision.revision_id,
            }
        
        # Create new render job with revised prompt
        new_job = self._render_service.create_job(
            project_id=revision.project_id,
            shot_id=original_job.shot_id,
            provider=provider_to_use,
            prompt=revision.revision_prompt,
            reference_assets=reference_assets,
            parameters=parameters,
        )
        
        # Submit the job
        if self._render_service:
            self._render_service.submit_job(new_job.id)
        
        # Update revision with new job ID
        revision.new_job_id = new_job.id
        revision.status = "submitted"
        revision.updated_at = self._now_iso()
        
        if self._storage:
            self._storage.update_clip_revision(revision)
        try:
            from app.services.storyboard_blueprint_service import storyboard_blueprint_service

            storyboard_blueprint_service.storage = self._storage or storyboard_blueprint_service.storage
            link = storyboard_blueprint_service.link_revision_from_job(
                project_id=revision.project_id,
                revision_id=revision.revision_id,
                original_job=original_job,
                change_scope={
                    "revision_reason": revision.revision_reason,
                    "revision_prompt": revision.revision_prompt,
                    "new_job_id": new_job.id,
                },
            )
            if link:
                revision.metadata = {
                    **(revision.metadata or {}),
                    "storyboard_revision_link_id": link.link_id,
                    "storyboard_original_version_id": link.original_version_id,
                }
                if self._storage:
                    self._storage.update_clip_revision(revision)
        except Exception:
            pass
        
        return revision

    def get_revision(self, revision_id: str) -> Optional[ClipRevision]:
        """Get a revision by ID"""
        if self._storage:
            return self._storage.get_clip_revision(revision_id)
        return None

    def list_revisions_for_project(self, project_id: str) -> List[ClipRevision]:
        """List all revisions for a project"""
        if self._storage:
            return self._storage.list_clip_revisions_for_project(project_id)
        return []

    def list_revisions_for_review(self, review_id: str) -> List[ClipRevision]:
        """List all revisions for a review"""
        if self._storage:
            return self._storage.list_clip_revisions_for_review(review_id)
        return []

    def complete_revision_from_render_job(self, revision_id: str) -> Optional[ClipRevision]:
        """Complete a revision when its render job is finished"""
        revision = self.get_revision(revision_id)
        if not revision:
            return None
        
        if not revision.can_complete():
            raise ValueError(f"Revision {revision_id} cannot be completed in status: {revision.status}")
        
        if not revision.new_job_id:
            raise ValueError(f"Revision {revision_id} has no new_job_id")
        
        # Get the render job status
        render_job = None
        if self._render_service:
            render_job = self._render_service.get_job(revision.new_job_id)
        
        if not render_job:
            raise ValueError(f"Render job {revision.new_job_id} not found")
        
        # Check if job is complete
        if render_job.status != "complete":
            raise ValueError(f"Render job {revision.new_job_id} is not complete: {render_job.status}")
        
        # Get output URL from render job
        output_url = None
        if render_job.output_payload and render_job.output_payload.asset_url:
            output_url = render_job.output_payload.asset_url
        
        # Update revision
        revision.status = "complete"
        revision.output_url = output_url
        revision.updated_at = self._now_iso()
        
        if self._storage:
            self._storage.update_clip_revision(revision)
        
        return revision

    def cancel_revision(self, revision_id: str) -> Optional[ClipRevision]:
        """Cancel a revision"""
        revision = self.get_revision(revision_id)
        if not revision:
            return None
        
        # Cancel the render job if it exists
        if revision.new_job_id and self._render_service:
            try:
                self._render_service.cancel_job(revision.new_job_id)
            except Exception:
                # Best effort - don't fail if cancellation fails
                pass
        
        # Update revision status
        revision.status = "cancelled"
        revision.updated_at = self._now_iso()
        
        if self._storage:
            self._storage.update_clip_revision(revision)
        
        return revision


# Global service instance
clip_revision_service = ClipRevisionService()
