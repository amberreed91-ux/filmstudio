from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import ShortFilmReview
from app.services.short_film_review_service import ShortFilmReviewService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_service(storage: DatabaseStorage) -> ShortFilmReviewService:
    return ShortFilmReviewService(storage)


def test_create_review(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    review = service.create_review(
        project_id="project-1",
        output_url="/outputs/final_films/project-1_sandbox_short_with_audio.mp4",
        reviewer="Test Reviewer",
        notes="Initial review notes",
        metadata={"test": True}
    )
    
    assert review.project_id == "project-1"
    assert review.output_url.endswith(".mp4")
    assert review.decision == "pending"
    assert review.reviewer == "Test Reviewer"
    assert review.notes == "Initial review notes"
    assert review.metadata["test"] is True
    assert review.review_id.startswith("review-")
    assert review.created_at != ""
    assert review.updated_at != ""


def test_get_review(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    created = service.create_review(
        project_id="project-1",
        output_url="/outputs/test.mp4",
        reviewer="Test Reviewer"
    )
    
    retrieved = service.get_review(created.review_id)
    assert retrieved is not None
    assert retrieved.review_id == created.review_id
    assert retrieved.project_id == "project-1"
    assert retrieved.decision == "pending"


def test_list_reviews_by_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create reviews for two different projects
    review1 = service.create_review("project-1", "/outputs/test1.mp4", "Reviewer 1")
    review2 = service.create_review("project-1", "/outputs/test2.mp4", "Reviewer 2")
    review3 = service.create_review("project-2", "/outputs/test3.mp4", "Reviewer 3")
    
    # List reviews for project-1
    reviews = service.list_reviews_for_project("project-1")
    assert len(reviews) == 2
    assert all(r.project_id == "project-1" for r in reviews)
    
    # List reviews for project-2
    reviews = service.list_reviews_for_project("project-2")
    assert len(reviews) == 1
    assert reviews[0].project_id == "project-2"


def test_get_latest_review_for_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create multiple reviews with different timestamps
    review1 = service.create_review("project-1", "/outputs/test1.mp4", "Reviewer 1")
    # Small delay to ensure different timestamps
    import time
    time.sleep(0.01)
    review2 = service.create_review("project-1", "/outputs/test2.mp4", "Reviewer 2")
    
    latest = service.get_latest_review_for_project("project-1")
    assert latest is not None
    assert latest.review_id == review2.review_id
    assert latest.reviewer == "Reviewer 2"
    
    # Test with no reviews
    none_latest = service.get_latest_review_for_project("nonexistent")
    assert none_latest is None


def test_update_decision(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    review = service.create_review("project-1", "/outputs/test.mp4", "Original Reviewer")
    
    # Update to approved
    updated = service.update_review_decision(
        review.review_id,
        decision="approved",
        reviewer="New Reviewer",
        notes="Looks good!"
    )
    
    assert updated is not None
    assert updated.review_id == review.review_id
    assert updated.decision == "approved"
    assert updated.reviewer == "New Reviewer"
    assert updated.notes == "Looks good!"
    assert updated.updated_at != review.updated_at
    
    # Verify the update persisted
    retrieved = service.get_review(review.review_id)
    assert retrieved.decision == "approved"
    assert retrieved.notes == "Looks good!"


def test_reject_invalid_decision(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    review = service.create_review("project-1", "/outputs/test.mp4")
    
    # Try to update with invalid decision
    try:
        service.update_review_decision(review.review_id, "invalid_decision")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid decision" in str(e)
        assert "invalid_decision" in str(e)


def test_review_persists_across_service_reload(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Create review with first service instance
    service1 = _make_service(storage)
    review = service1.create_review("project-1", "/outputs/test.mp4", "Original Reviewer", "Original notes")
    
    # Create second service instance with same storage
    service2 = _make_service(storage)
    retrieved = service2.get_review(review.review_id)
    
    assert retrieved is not None
    assert retrieved.review_id == review.review_id
    assert retrieved.project_id == "project-1"
    assert retrieved.reviewer == "Original Reviewer"
    assert retrieved.notes == "Original notes"
    assert retrieved.decision == "pending"


def test_review_helper_methods(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Test pending review
    pending = service.create_review("project-1", "/outputs/test.mp4")
    assert pending.is_pending()
    assert not pending.is_approved()
    assert not pending.needs_revision()
    assert not pending.is_rejected()
    
    # Update to approved
    approved = service.update_review_decision(pending.review_id, "approved")
    assert not approved.is_pending()
    assert approved.is_approved()
    assert not approved.needs_revision()
    assert not approved.is_rejected()
    
    # Update to needs_revision
    needs_rev = service.update_review_decision(approved.review_id, "needs_revision")
    assert not needs_rev.is_pending()
    assert not needs_rev.is_approved()
    assert needs_rev.needs_revision()
    assert not needs_rev.is_rejected()
    
    # Update to rejected
    rejected = service.update_review_decision(needs_rev.review_id, "rejected")
    assert not rejected.is_pending()
    assert not rejected.is_approved()
    assert not rejected.needs_revision()
    assert rejected.is_rejected()
