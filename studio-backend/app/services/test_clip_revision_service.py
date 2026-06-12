from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models import ClipRevision
from app.services.clip_revision_service import ClipRevisionService


def _make_storage(tmp_path: Path) -> DatabaseStorage:
    return DatabaseStorage(str(tmp_path / "storage"))


def _make_service(storage: DatabaseStorage) -> ClipRevisionService:
    return ClipRevisionService(storage)


def test_create_revision(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    revision = service.create_revision(
        project_id="project-1",
        review_id="review-1",
        original_job_id="job-1",
        provider="runway",
        revision_prompt="Make the character smile more",
        revision_reason="Character looks too serious",
        metadata={"test": True}
    )
    
    assert revision.project_id == "project-1"
    assert revision.review_id == "review-1"
    assert revision.original_job_id == "job-1"
    assert revision.provider == "runway"
    assert revision.revision_prompt == "Make the character smile more"
    assert revision.revision_reason == "Character looks too serious"
    assert revision.status == "pending"
    assert revision.metadata["test"] is True
    assert revision.revision_id.startswith("revision-")
    assert revision.created_at != ""
    assert revision.updated_at != ""


def test_get_revision(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    created = service.create_revision(
        project_id="project-1",
        review_id="review-1",
        original_job_id="job-1",
        provider="runway",
        revision_prompt="Test revision",
        revision_reason="Test reason"
    )
    
    retrieved = service.get_revision(created.revision_id)
    assert retrieved is not None
    assert retrieved.revision_id == created.revision_id
    assert retrieved.project_id == "project-1"
    assert retrieved.status == "pending"


def test_list_revisions_by_project(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create revisions for two different projects
    revision1 = service.create_revision("project-1", "review-1", "job-1", "runway", "prompt1", "reason1")
    revision2 = service.create_revision("project-1", "review-1", "job-2", "runway", "prompt2", "reason2")
    revision3 = service.create_revision("project-2", "review-2", "job-3", "runway", "prompt3", "reason3")
    
    # List revisions for project-1
    revisions = service.list_revisions_for_project("project-1")
    assert len(revisions) == 2
    assert all(r.project_id == "project-1" for r in revisions)
    
    # List revisions for project-2
    revisions = service.list_revisions_for_project("project-2")
    assert len(revisions) == 1
    assert revisions[0].project_id == "project-2"


def test_list_revisions_by_review(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create revisions for two different reviews
    revision1 = service.create_revision("project-1", "review-1", "job-1", "runway", "prompt1", "reason1")
    revision2 = service.create_revision("project-1", "review-1", "job-2", "runway", "prompt2", "reason2")
    revision3 = service.create_revision("project-1", "review-2", "job-3", "runway", "prompt3", "reason3")
    
    # List revisions for review-1
    revisions = service.list_revisions_for_review("review-1")
    assert len(revisions) == 2
    assert all(r.review_id == "review-1" for r in revisions)
    
    # List revisions for review-2
    revisions = service.list_revisions_for_review("review-2")
    assert len(revisions) == 1
    assert revisions[0].review_id == "review-2"


def test_submit_revision_render(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock render service
    class MockRenderService:
        def __init__(self):
            self.jobs = {}
            self.submitted_jobs = []
        
        def get_job(self, job_id):
            return self.jobs.get(job_id)
        
        def create_job(self, project_id, shot_id, provider, prompt="", reference_assets=None, parameters=None):
            job = type('MockJob', (), {
                'id': f'new-job-{len(self.jobs)}',
                'project_id': project_id,
                'shot_id': shot_id,
                'provider': provider,
                'input_payload': type('MockInput', (), {
                    'prompt': prompt,
                    'referenceAssets': reference_assets or [],
                    'parameters': parameters or {},
                    'model_copy': lambda self: type('MockInput', (), {
                        'prompt': prompt,
                        'referenceAssets': reference_assets or [],
                        'parameters': parameters or {}
                    })()
                })()
            })()
            self.jobs[job.id] = job
            return job
        
        def submit_job(self, job_id):
            self.submitted_jobs.append(job_id)
    
    mock_render_service = MockRenderService()
    service = _make_service(storage)
    service._render_service = mock_render_service
    
    # Create original job
    original_job = type('MockJob', (), {
        'id': 'original-job-1',
        'project_id': 'project-1',
        'shot_id': 'shot-1',
        'provider': 'runway',
        'input_payload': type('MockInput', (), {
            'prompt': 'Original prompt',
            'model_copy': lambda self: type('MockInput', (), {'prompt': 'Original prompt'})()
        })()
    })()
    mock_render_service.jobs['original-job-1'] = original_job
    
    # Create revision
    revision = service.create_revision(
        project_id="project-1",
        review_id="review-1",
        original_job_id="original-job-1",
        provider="runway",
        revision_prompt="Make the character smile more",
        revision_reason="Character looks too serious"
    )
    
    # Submit revision for rendering
    submitted = service.submit_revision_render(revision.revision_id)
    
    assert submitted is not None
    assert submitted.status == "submitted"
    assert submitted.new_job_id is not None
    assert submitted.new_job_id.startswith("new-job-")
    
    # Verify new job was created and submitted
    assert submitted.new_job_id in mock_render_service.jobs
    assert submitted.new_job_id in mock_render_service.submitted_jobs
    
    # Verify new job has revised prompt
    new_job = mock_render_service.get_job(submitted.new_job_id)
    assert new_job.input_payload.prompt == "Make the character smile more"


def test_submit_revision_with_provider_override(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock render service
    class MockRenderService:
        def __init__(self):
            self.jobs = {}
        
        def get_job(self, job_id):
            return self.jobs.get(job_id)
        
        def create_job(self, project_id, shot_id, provider, prompt="", reference_assets=None, parameters=None):
            job = type('MockJob', (), {
                'id': f'new-job-{len(self.jobs)}',
                'project_id': project_id,
                'shot_id': shot_id,
                'provider': provider,
                'input_payload': type('MockInput', (), {
                    'prompt': prompt,
                    'referenceAssets': reference_assets or [],
                    'parameters': parameters or {},
                    'model_copy': lambda self: type('MockInput', (), {
                        'prompt': prompt,
                        'referenceAssets': reference_assets or [],
                        'parameters': parameters or {}
                    })()
                })()
            })()
            self.jobs[job.id] = job
            return job
        
        def submit_job(self, job_id):
            pass
    
    mock_render_service = MockRenderService()
    service = _make_service(storage)
    service._render_service = mock_render_service
    
    # Create original job
    original_job = type('MockJob', (), {
        'id': 'original-job-1',
        'project_id': 'project-1',
        'shot_id': 'shot-1',
        'provider': 'runway',
        'input_payload': type('MockInput', (), {
            'prompt': 'Original prompt',
            'model_copy': lambda self: type('MockInput', (), {'prompt': 'Original prompt'})()
        })()
    })()
    mock_render_service.jobs['original-job-1'] = original_job
    
    # Create revision
    revision = service.create_revision(
        project_id="project-1",
        review_id="review-1",
        original_job_id="original-job-1",
        provider="runway",
        revision_prompt="Make the character smile more",
        revision_reason="Character looks too serious"
    )
    
    # Submit with provider override
    submitted = service.submit_revision_render(revision.revision_id, provider_override="simulated")
    
    assert submitted is not None
    assert submitted.status == "submitted"
    
    # Verify new job uses override provider
    new_job = mock_render_service.get_job(submitted.new_job_id)
    assert new_job.provider == "simulated"


def test_complete_revision_from_render_job(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock render service
    class MockRenderService:
        def get_job(self, job_id):
            if job_id == "completed-job":
                return type('MockJob', (), {
                    'id': 'completed-job',
                    'status': 'complete',
                    'output_payload': type('MockOutput', (), {'asset_url': 'https://example.com/output.mp4'})()
                })()
            return None
    
    mock_render_service = MockRenderService()
    service = _make_service(storage)
    service._render_service = mock_render_service
    
    # Create revision with submitted job
    revision = service.create_revision(
        project_id="project-1",
        review_id="review-1",
        original_job_id="original-job-1",
        provider="runway",
        revision_prompt="Make the character smile more",
        revision_reason="Character looks too serious"
    )
    revision.new_job_id = "completed-job"
    revision.status = "submitted"
    storage.update_clip_revision(revision)
    
    # Complete revision from render job
    completed = service.complete_revision_from_render_job(revision.revision_id)
    
    assert completed is not None
    assert completed.status == "complete"
    assert completed.output_url == "https://example.com/output.mp4"


def test_cancel_revision(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Mock render service
    class MockRenderService:
        def __init__(self):
            self.cancelled_jobs = []
        
        def cancel_job(self, job_id):
            self.cancelled_jobs.append(job_id)
    
    mock_render_service = MockRenderService()
    service = _make_service(storage)
    service._render_service = mock_render_service
    
    # Create revision with submitted job
    revision = service.create_revision(
        project_id="project-1",
        review_id="review-1",
        original_job_id="original-job-1",
        provider="runway",
        revision_prompt="Make the character smile more",
        revision_reason="Character looks too serious"
    )
    revision.new_job_id = "new-job-1"
    revision.status = "submitted"
    storage.update_clip_revision(revision)
    
    # Cancel revision
    cancelled = service.cancel_revision(revision.revision_id)
    
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert "new-job-1" in mock_render_service.cancelled_jobs


def test_revision_helper_methods(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Test pending revision
    pending = service.create_revision("project-1", "review-1", "job-1", "runway", "prompt", "reason")
    assert pending.is_pending()
    assert not pending.is_submitted()
    assert not pending.is_complete()
    assert not pending.is_failed()
    assert not pending.is_cancelled()
    assert pending.can_submit()
    assert not pending.can_complete()
    
    # Update to submitted
    pending.new_job_id = "new-job-1"
    pending.status = "submitted"
    storage.update_clip_revision(pending)
    
    submitted = service.get_revision(pending.revision_id)
    assert submitted is not None
    assert not submitted.is_pending()
    assert submitted.is_submitted()
    assert not submitted.is_complete()
    assert not submitted.is_failed()
    assert not submitted.is_cancelled()
    assert not submitted.can_submit()
    assert submitted.can_complete()


def test_revision_persists_across_service_reload(tmp_path: Path):
    storage = _make_storage(tmp_path)
    
    # Create revision with first service instance
    service1 = _make_service(storage)
    revision = service1.create_revision("project-1", "review-1", "job-1", "runway", "prompt", "reason")
    
    # Create second service instance with same storage
    service2 = _make_service(storage)
    retrieved = service2.get_revision(revision.revision_id)
    
    assert retrieved is not None
    assert retrieved.revision_id == revision.revision_id
    assert retrieved.project_id == "project-1"
    assert retrieved.revision_prompt == "prompt"
    assert retrieved.status == "pending"


def test_submit_revision_invalid_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create revision
    revision = service.create_revision("project-1", "review-1", "job-1", "runway", "prompt", "reason")
    
    # Try to submit revision in invalid status (already submitted)
    revision.status = "submitted"
    storage.update_clip_revision(revision)
    
    try:
        service.submit_revision_render(revision.revision_id)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be submitted" in str(e)


def test_complete_revision_invalid_status(tmp_path: Path):
    storage = _make_storage(tmp_path)
    service = _make_service(storage)
    
    # Create revision
    revision = service.create_revision("project-1", "review-1", "job-1", "runway", "prompt", "reason")
    
    # Try to complete revision in invalid status (not submitted)
    try:
        service.complete_revision_from_render_job(revision.revision_id)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be completed" in str(e)
