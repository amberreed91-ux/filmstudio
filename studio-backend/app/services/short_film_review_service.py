from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models import ShortFilmReview


class ShortFilmReviewService:
    """Service for managing short film reviews with persistent storage"""

    def __init__(self, storage=None):
        self._storage = storage

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_review_id(self) -> str:
        return f"review-{uuid.uuid4().hex[:12]}"

    def create_review(
        self,
        project_id: str,
        output_url: str,
        reviewer: str = "",
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ShortFilmReview:
        """Create a new review for a short film"""
        review = ShortFilmReview(
            review_id=self._generate_review_id(),
            project_id=project_id,
            output_url=output_url,
            decision="pending",
            reviewer=reviewer,
            notes=notes,
            created_at=self._now_iso(),
            updated_at=self._now_iso(),
            metadata=metadata or {},
        )
        
        if self._storage:
            self._storage.save_review(review)
            self._sync_matching_packages(review)
        
        return review

    def _sync_matching_packages(self, review: ShortFilmReview) -> None:
        """Bind a creator decision to persisted packages for this exact output."""
        if not self._storage:
            return
        for package in self._storage.list_final_short_film_packages_for_project(review.project_id):
            if package.project_id != review.project_id or package.final_output_url != review.output_url:
                continue
            package.review_id = review.review_id
            package.review_decision = review.decision
            package.updated_at = self._now_iso()
            self._storage.update_final_short_film_package(package)

    def get_review(self, review_id: str) -> Optional[ShortFilmReview]:
        """Get a review by ID"""
        if self._storage:
            return self._storage.get_review(review_id)
        return None

    def list_reviews_for_project(self, project_id: str) -> List[ShortFilmReview]:
        """List all reviews for a project"""
        if self._storage:
            return self._storage.list_reviews_for_project(project_id)
        return []

    def update_review_decision(
        self,
        review_id: str,
        decision: str,
        reviewer: str = "",
        notes: str = "",
    ) -> Optional[ShortFilmReview]:
        """Update the decision of an existing review"""
        valid_decisions = {"pending", "approved", "needs_revision", "rejected"}
        if decision not in valid_decisions:
            raise ValueError(f"Invalid decision: {decision}. Must be one of: {valid_decisions}")

        review = self.get_review(review_id)
        if not review:
            return None

        review.decision = decision
        review.updated_at = self._now_iso()
        if reviewer:
            review.reviewer = reviewer
        if notes:
            review.notes = notes

        if self._storage:
            self._storage.update_review(review)
            self._sync_matching_packages(review)

        return review

    def get_latest_review_for_project(self, project_id: str) -> Optional[ShortFilmReview]:
        """Get the most recent review for a project"""
        reviews = self.list_reviews_for_project(project_id)
        if not reviews:
            return None
        
        return max(reviews, key=lambda r: r.created_at)


# Global service instance
short_film_review_service = ShortFilmReviewService()
