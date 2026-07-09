"""Production Board Recovery Service for ensuring data consistency after restarts."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from app.models import (
    RenderJobModel, 
    ShortFilmReview, 
    ClipRevision, 
    FinalShortFilmPackage,
    StudioProject
)
from app.data.storage import get_storage
from app.services import render_service, short_film_review_service, clip_revision_service, final_short_film_package_service

logger = logging.getLogger("production-recovery")
_storage = get_storage("sqlite")


class ProductionRecoveryService:
    """Service for recovering and maintaining Production Board data consistency."""
    
    def __init__(self):
        self._is_recovering = False
        self._recovery_start_time: Optional[datetime] = None
        self._recovered_jobs: Set[str] = set()
        self._recovered_reviews: Set[str] = set()
        self._recovered_revisions: Set[str] = set()
        self._recovered_packages: Set[str] = set()
        
    async def perform_full_recovery(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Perform comprehensive recovery of all production data."""
        if self._is_recovering:
            logger.warning("Recovery already in progress, skipping")
            return {"status": "already_running"}
            
        self._is_recovering = True
        self._recovery_start_time = datetime.now()
        
        try:
            logger.info(f"Starting production recovery for project: {project_id or 'all'}")
            
            recovery_results = {
                "status": "started",
                "start_time": self._recovery_start_time.isoformat(),
                "project_id": project_id,
                "jobs": {"recovered": 0, "failed": 0, "stale": 0},
                "reviews": {"recovered": 0, "failed": 0},
                "revisions": {"recovered": 0, "failed": 0},
                "packages": {"recovered": 0, "failed": 0},
                "projects": {"recovered": 0, "failed": 0}
            }
            
            # Step 1: Recover render jobs
            await self._recover_render_jobs(project_id, recovery_results["jobs"])
            
            # Step 2: Recover reviews
            await self._recover_reviews(project_id, recovery_results["reviews"])
            
            # Step 3: Recover revisions
            await self._recover_revisions(project_id, recovery_results["revisions"])
            
            # Step 4: Recover packages
            await self._recover_packages(project_id, recovery_results["packages"])
            
            # Step 5: Recover project execution summaries
            await self._recover_project_summaries(project_id, recovery_results["projects"])
            
            # Step 6: Clean up stale data
            await self._cleanup_stale_data(project_id, recovery_results)
            
            recovery_results["status"] = "completed"
            recovery_results["end_time"] = datetime.now().isoformat()
            recovery_results["duration_seconds"] = (
                datetime.now() - self._recovery_start_time
            ).total_seconds()
            
            logger.info(f"Production recovery completed: {recovery_results}")
            return recovery_results
            
        except Exception as e:
            logger.error(f"Production recovery failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "start_time": self._recovery_start_time.isoformat() if self._recovery_start_time else None
            }
        finally:
            self._is_recovering = False
            self._recovery_start_time = None
            
    async def _recover_render_jobs(self, project_id: Optional[str], results: Dict[str, int]):
        """Recover render jobs from storage and update their status."""
        if not _storage:
            logger.warning("No storage available for job recovery")
            return
            
        try:
            # Get all jobs from storage
            if project_id:
                jobs = _storage.list_render_jobs(project_id)
            else:
                jobs = _storage.list_render_jobs()
                
            for job in jobs:
                try:
                    # Check if job is stale (older than 24 hours and not terminal)
                    job_created = datetime.fromisoformat(job.created_at.replace('Z', '+00:00'))
                    is_stale = (
                        not job.is_terminal() and 
                        (datetime.now(job_created.tzinfo) - job_created) > timedelta(hours=24)
                    )
                    
                    if is_stale:
                        # Mark stale jobs as failed
                        job.status = "failed"
                        job.error_message = "Job marked as stale during recovery"
                        job.updated_at = datetime.now().isoformat()
                        _storage.save_job(job)
                        results["stale"] += 1
                        logger.info(f"Marked stale job {job.id} as failed")
                    else:
                        # Refresh job status from provider if not terminal
                        if not job.is_terminal():
                            try:
                                refreshed_job = await render_service.get_job_status(job.id)
                                results["recovered"] += 1
                                self._recovered_jobs.add(job.id)
                                logger.debug(f"Refreshed job {job.id} status to {refreshed_job.status}")
                            except Exception as e:
                                logger.warning(f"Failed to refresh job {job.id}: {e}")
                                results["failed"] += 1
                        else:
                            # Terminal jobs are already recovered
                            results["recovered"] += 1
                            self._recovered_jobs.add(job.id)
                            
                except Exception as e:
                    logger.error(f"Failed to recover job {job.id}: {e}")
                    results["failed"] += 1
                    
        except Exception as e:
            logger.error(f"Job recovery failed: {e}")
            results["failed"] += len(results)
            
    async def _recover_reviews(self, project_id: Optional[str], results: Dict[str, int]):
        """Recover short film reviews."""
        if not _storage:
            return
            
        try:
            # Get reviews from storage
            if project_id:
                reviews = _storage.list_reviews(project_id)
            else:
                reviews = _storage.list_reviews()
                
            for review in reviews:
                try:
                    # Validate review data
                    if not review.review_id or not review.project_id:
                        results["failed"] += 1
                        continue
                        
                    # Ensure review is properly indexed
                    self._recovered_reviews.add(review.review_id)
                    results["recovered"] += 1
                    logger.debug(f"Recovered review {review.review_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to recover review {review.review_id}: {e}")
                    results["failed"] += 1
                    
        except Exception as e:
            logger.error(f"Review recovery failed: {e}")
            results["failed"] += len(results)
            
    async def _recover_revisions(self, project_id: Optional[str], results: Dict[str, int]):
        """Recover clip revisions."""
        if not _storage:
            return
            
        try:
            # Get revisions from storage
            if project_id:
                revisions = _storage.list_revisions(project_id)
            else:
                revisions = _storage.list_revisions()
                
            for revision in revisions:
                try:
                    # Validate revision data
                    if not revision.revision_id or not revision.project_id:
                        results["failed"] += 1
                        continue
                        
                    # Ensure revision is properly indexed
                    self._recovered_revisions.add(revision.revision_id)
                    results["recovered"] += 1
                    logger.debug(f"Recovered revision {revision.revision_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to recover revision {revision.revision_id}: {e}")
                    results["failed"] += 1
                    
        except Exception as e:
            logger.error(f"Revision recovery failed: {e}")
            results["failed"] += len(results)
            
    async def _recover_packages(self, project_id: Optional[str], results: Dict[str, int]):
        """Recover final short film packages."""
        if not _storage:
            return
            
        try:
            # Get packages from storage
            if project_id:
                packages = _storage.list_packages(project_id)
            else:
                packages = _storage.list_packages()
                
            for package in packages:
                try:
                    # Validate package data
                    if not package.package_id or not package.project_id:
                        results["failed"] += 1
                        continue
                        
                    # Ensure package is properly indexed
                    self._recovered_packages.add(package.package_id)
                    results["recovered"] += 1
                    logger.debug(f"Recovered package {package.package_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to recover package {package.package_id}: {e}")
                    results["failed"] += 1
                    
        except Exception as e:
            logger.error(f"Package recovery failed: {e}")
            results["failed"] += len(results)
            
    async def _recover_project_summaries(self, project_id: Optional[str], results: Dict[str, int]):
        """Recover project execution summaries."""
        if not _storage:
            return
            
        try:
            # Get projects from storage
            if project_id:
                projects = [_storage.get_project(project_id)]
            else:
                projects = _storage.list_all_projects().values()
                
            for project in projects:
                try:
                    if not project:
                        continue
                        
                    # Validate project data and execution summary
                    if hasattr(project, 'execution_summary') and project.execution_summary:
                        # Ensure execution summary is properly structured
                        summary = project.execution_summary
                        if isinstance(summary, dict):
                            # Validate required fields
                            if 'scenes' in summary or 'one_button_render_jobs' in summary:
                                results["recovered"] += 1
                                logger.debug(f"Recovered project summary for {project.project_id}")
                            else:
                                logger.warning(f"Project {project.project_id} has incomplete execution summary")
                                results["failed"] += 1
                        else:
                            logger.warning(f"Project {project.project_id} has invalid execution summary type")
                            results["failed"] += 1
                    else:
                        logger.debug(f"Project {project.project_id} has no execution summary")
                        
                except Exception as e:
                    logger.error(f"Failed to recover project summary for {project.project_id if project else 'unknown'}: {e}")
                    results["failed"] += 1
                    
        except Exception as e:
            logger.error(f"Project summary recovery failed: {e}")
            results["failed"] += len(results)
            
    async def _cleanup_stale_data(self, project_id: Optional[str], results: Dict[str, int]):
        """Clean up stale and orphaned data."""
        if not _storage:
            return
            
        try:
            # Clean up orphaned render jobs (jobs without valid projects)
            all_jobs = _storage.list_render_jobs()
            all_projects = set(_storage.list_project_ids())
            
            orphaned_count = 0
            for job in all_jobs:
                if project_id and job.project_id != project_id:
                    continue
                    
                if job.project_id not in all_projects:
                    # Mark orphaned jobs as failed
                    job.status = "failed"
                    job.error_message = "Orphaned job - project not found"
                    job.updated_at = datetime.now().isoformat()
                    _storage.save_job(job)
                    orphaned_count += 1
                    
            logger.info(f"Cleaned up {orphaned_count} orphaned jobs")
            
        except Exception as e:
            logger.error(f"Stale data cleanup failed: {e}")
            
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get current recovery status."""
        return {
            "is_recovering": self._is_recovering,
            "recovery_start_time": self._recovery_start_time.isoformat() if self._recovery_start_time else None,
            "recovered_jobs": list(self._recovered_jobs),
            "recovered_reviews": list(self._recovered_reviews),
            "recovered_revisions": list(self._recovered_revisions),
            "recovered_packages": list(self._recovered_packages),
            "total_recovered": len(self._recovered_jobs) + len(self._recovered_reviews) + len(self._recovered_revisions) + len(self._recovered_packages)
        }
        
    def reset_recovery_state(self):
        """Reset recovery state for testing."""
        self._recovered_jobs.clear()
        self._recovered_reviews.clear()
        self._recovered_revisions.clear()
        self._recovered_packages.clear()


# Global service instance
production_recovery_service = ProductionRecoveryService()
