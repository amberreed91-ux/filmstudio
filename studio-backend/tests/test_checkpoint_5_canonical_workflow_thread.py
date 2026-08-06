from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, StudioProject
from app.services.canonical_production_workflow_service import CanonicalProductionWorkflowService
from app.services.project_store import ProjectStore
from app.services.stability import ProviderError, StateError, ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService


class DeterministicRenderer:
    def __init__(self, storage: DatabaseStorage) -> None:
        self.storage = storage
        self.jobs: dict[str, RenderJobModel] = {}
        self.by_idempotency: dict[str, str] = {}
        self.create_count = 0
        self.fail_next_submission = False
        self.delay_next_submission = False
        self.complete_on_next_status = False

    def create_job(
        self,
        project_id: str,
        shot_id: str,
        provider: str | None = None,
        prompt: str = "",
        reference_assets: list[str] | None = None,
        parameters: dict | None = None,
    ) -> RenderJobModel:
        params = dict(parameters or {})
        idempotency_key = str(params.get("idempotency_key") or "")
        if idempotency_key and idempotency_key in self.by_idempotency:
            return self.jobs[self.by_idempotency[idempotency_key]]
        self.create_count += 1
        job_id = f"job-{self.create_count:03d}-{shot_id}"
        job = RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider=provider or "simulated",
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=prompt,
                referenceAssets=list(reference_assets or []),
                parameters=params,
            ),
            created_at="2026-08-06T12:00:00+00:00",
            updated_at="2026-08-06T12:00:00+00:00",
        )
        self.jobs[job_id] = job
        if idempotency_key:
            self.by_idempotency[idempotency_key] = job_id
        self.storage.save_job(job)
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        job = self.jobs[job_id]
        if self.fail_next_submission:
            self.fail_next_submission = False
            job.status = "failed"
            job.error_message = "deterministic provider failure"
            job.updated_at = "2026-08-06T12:01:00+00:00"
            self.storage.save_job(job)
            return job
        if self.delay_next_submission:
            self.delay_next_submission = False
            self.complete_on_next_status = True
            job.status = "pending"
            self.storage.save_job(job)
            return job
        job.status = "complete"
        job.provider_job_id = f"provider-{job.id}"
        job.output_payload = RenderJobOutput(
            asset_url=f"https://media.example.test/{job.id}.mp4",
            metadata={"deterministic": True},
        )
        job.completed_at = "2026-08-06T12:01:00+00:00"
        job.updated_at = job.completed_at
        self.storage.save_job(job)
        return job

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        job = self.jobs[job_id]
        if self.complete_on_next_status and job.status == "pending":
            self.complete_on_next_status = False
            job.status = "complete"
            job.provider_job_id = f"provider-{job.id}"
            job.output_payload = RenderJobOutput(
                asset_url=f"https://media.example.test/{job.id}.mp4",
                metadata={"deterministic": True},
            )
            job.completed_at = "2026-08-06T12:02:00+00:00"
            job.updated_at = job.completed_at
            self.storage.save_job(job)
        return job

    def get_job(self, job_id: str) -> RenderJobModel | None:
        return self.jobs.get(job_id)

    def list_jobs(self, project_id: str | None = None) -> list[RenderJobModel]:
        rows = list(self.jobs.values())
        return [row for row in rows if project_id is None or row.project_id == project_id]

    async def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None:
            return False
        job.status = "cancelled"
        self.storage.save_job(job)
        return True


def _seed_project(storage: DatabaseStorage, state: ProjectStore, project_id: str = "project-thread") -> None:
    project = {
        "project_id": project_id,
        "title": "Checkpoint 5 Thread",
        "script_text": "INT. EDIT BAY - NIGHT. Maya holds the silence.",
        "production_bible": {
            "creative_intent": "A contained drama about the cost of choosing clarity over comfort."
        },
        "director_intent": {
            "cinematic_language": "Patient frames with one deliberate push inward.",
            "color": "Cool monitor light against a nearly black room.",
        },
        "execution_summary": {
            "script_id": "script-thread-001",
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "script_id": "script-thread-001",
                    "sequence_id": "sequence_001",
                    "beats": [
                        {"beat_id": "beat_001", "objective": "Maya delays the answer."},
                        {"beat_id": "beat_002", "objective": "She finally commits."},
                    ],
                    "heading": "INT. EDIT BAY - NIGHT",
                    "description": "Maya watches the same silent reaction twice, then commits to the harder cut.",
                    "objective": "Make the irreversible choice.",
                    "emotional_objective": "Let dread settle before resolve arrives.",
                    "emotional_tone": "contained dread",
                    "character_intention": {"MAYA": "Protect the truth without surrendering tenderness."},
                    "character_emotional_state": {"MAYA": "Afraid, precise, newly resolved."},
                    "theme": "Clarity has an emotional cost.",
                    "creative_spine": {"central_question": "Can honesty remain humane?"},
                    "director_guidance": {"performance": "Underplay the decision; let the hand reveal it."},
                    "sound_intent": {"room_tone": "Low computer fan, no score."},
                    "editorial_intent": {"rhythm": "Hold, decide, cut."},
                    "characters": ["MAYA"],
                    "character_references": ["character-ref-maya"],
                    "location_references": ["location-ref-edit-bay"],
                    "wardrobe_references": ["wardrobe-ref-maya-night"],
                    "prop_references": ["prop-ref-control-surface"],
                }
            ],
        },
        "film_cut": {
            "cut_id": "default",
            "scene_order": ["scene_001"],
            "included_scenes": ["scene_001"],
            "excluded_scenes": [],
        },
    }
    state.save_project(project)
    storage.save_project(StudioProject(**project))


def _approve_storyboard(storage: DatabaseStorage, state: ProjectStore) -> dict:
    service = StoryboardBlueprintService(storage)
    service.project_store = state
    detail = service.get_or_create_blueprint(
        project_id="project-thread",
        scene_id="scene_001",
        shot_count=1,
    )
    try:
        return service.approve_version(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=detail["version"].version_id,
            approved_by="creator",
        )
    except ValidationError as exc:
        # Compatibility with the separate, pre-existing continuity-review worktree.
        review = getattr(service, "run_continuity_review", None)
        if "Continuity Review" not in exc.message or not callable(review):
            raise
        review(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=detail["version"].version_id,
        )
        return service.approve_version(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=detail["version"].version_id,
            approved_by="creator",
        )


def _environment(tmp_path: Path) -> tuple[CanonicalProductionWorkflowService, DatabaseStorage, ProjectStore, DeterministicRenderer]:
    storage = DatabaseStorage(str(tmp_path / "workflow-db"))
    state = ProjectStore(str(tmp_path / "workflow-projects.json"))
    _seed_project(storage, state)
    _approve_storyboard(storage, state)
    renderer = DeterministicRenderer(storage)
    service = CanonicalProductionWorkflowService(
        storage=storage,
        project_store=state,
        renderer=renderer,
    )
    return service, storage, state, renderer


def _begin(service: CanonicalProductionWorkflowService) -> dict:
    return service.begin(
        project_id="project-thread",
        scene_id="scene_001",
        script_id="script-thread-001",
        sequence_id="sequence_001",
        beat_ids=["beat_001", "beat_002"],
    )


def _through_package(service: CanonicalProductionWorkflowService) -> dict:
    run = _begin(service)
    run = asyncio.run(service.generate_previs(run["run_id"]))
    image_ids = [row["previs_image_id"] for row in run["data"]["artifacts"]["previs"]]
    run = service.approve_previs(
        run["run_id"],
        previs_image_ids=image_ids,
        confirmed=True,
    )
    return service.create_production_package(run["run_id"])


def test_complete_canonical_workflow_trace_survives_reload(tmp_path: Path) -> None:
    service, storage, state, renderer = _environment(tmp_path)
    run = _begin(service)
    run_id = run["run_id"]
    identifiers = run["data"]["identifiers"]
    assert identifiers["project_id"] == "project-thread"
    assert identifiers["script_id"] == "script-thread-001"
    assert identifiers["scene_id"] == "scene_001"
    assert identifiers["sequence_id"] == "sequence_001"
    assert identifiers["beat_ids"] == ["beat_001", "beat_002"]
    assert identifiers["storyboard_id"] == run["blueprint_id"]
    assert identifiers["blueprint_id"] == run["blueprint_id"]
    assert identifiers["blueprint_version_id"] == run["blueprint_version_id"]
    assert run["data"]["creative_context"]["emotional_objective"] == "Let dread settle before resolve arrives."
    assert run["data"]["continuity_context"]["shot_plans"]

    with pytest.raises(StateError):
        service.create_production_package(run_id)

    run = asyncio.run(service.generate_previs(run_id))
    previs_create_count = renderer.create_count
    assert asyncio.run(service.generate_previs(run_id))["run_id"] == run_id
    assert renderer.create_count == previs_create_count
    previs_ids = [row["previs_image_id"] for row in run["data"]["artifacts"]["previs"]]
    with pytest.raises(ValidationError):
        service.approve_previs(run_id, previs_image_ids=previs_ids, confirmed=False)
    run = service.approve_previs(run_id, previs_image_ids=previs_ids, confirmed=True)
    assert all(row["approved"] for row in run["data"]["artifacts"]["previs"])

    run = service.create_production_package(run_id)
    package_id = run["data"]["identifiers"]["production_package_id"]
    package = storage.get_previs_production_package(package_id)
    assert package["blueprint_version_id"] == run["blueprint_version_id"]
    assert package["payload"]["shots"][0]["continuity"]

    run = asyncio.run(service.render_production_package(run_id, provider="simulated"))
    assert run["status"] == "render_completed"
    production_create_count = renderer.create_count
    assert asyncio.run(service.render_production_package(run_id, provider="simulated"))["status"] == "render_completed"
    assert renderer.create_count == production_create_count
    render_row = run["data"]["artifacts"]["render_jobs"][0]
    render_job = renderer.get_job(render_row["render_job_id"])
    parameters = render_job.input_payload.parameters
    assert parameters["canonical_workflow"]["run_id"] == run_id
    assert parameters["canonical_workflow"]["production_package_id"] == package_id
    assert parameters["canonical_workflow"]["storyboard_id"] == run["blueprint_id"]
    assert parameters["canonical_workflow"]["blueprint_version_id"] == run["blueprint_version_id"]
    assert parameters["creative_intent"]["emotional_target"]
    assert parameters["continuity"]
    assert render_row["asset_id"] in run["data"]["identifiers"]["asset_ids"]
    assert render_row["clip_id"] in run["data"]["identifiers"]["clip_ids"]
    assert render_row["render_request_id"] in run["data"]["identifiers"]["render_request_ids"]
    assert render_job.provider_job_id in run["data"]["identifiers"]["provider_job_ids"]

    run = asyncio.run(service.sync_screening(run_id))
    screening_ids = run["data"]["identifiers"]["screening_output_ids"]
    assert screening_ids
    with pytest.raises(ValidationError):
        service.approve_screening(run_id, screening_output_ids=screening_ids, confirmed=False)
    run = service.approve_screening(run_id, screening_output_ids=screening_ids, confirmed=True)
    approval_id = run["data"]["identifiers"]["approval_id"]
    assert storage.get_review(approval_id).decision == "approved"

    assert storage.list_cinematic_memory_for_project("project-thread") == []
    with pytest.raises(ValidationError):
        service.save_approved_memory(run_id, confirmed=False)

    run = service.analyze_editorial(run_id, revision_emphasis="emotional_residue")
    analysis_id = run["data"]["identifiers"]["editorial_analysis_id"]
    analysis = storage.get_editorial_analysis_record(analysis_id)
    assert analysis.source_package_id == package_id
    assert analysis.source_cut_id == run["data"]["identifiers"]["film_cut_id"]
    assert analysis.metadata["blueprint_version_id"] == run["blueprint_version_id"]
    decision_id = analysis.edit_decisions[0].decision_id

    with pytest.raises(ValidationError):
        service.apply_editorial_decision(
            run_id,
            analysis_id=analysis_id,
            decision_id=decision_id,
            confirmed=False,
        )
    run = service.apply_editorial_decision(
        run_id,
        analysis_id=analysis_id,
        decision_id=decision_id,
        confirmed=True,
    )
    application_id = run["data"]["identifiers"]["editorial_application_id"]
    application = storage.get_editorial_decision_application(application_id)
    assert application.analysis_id == analysis_id
    assert application.source_cut_id == analysis.source_cut_id

    run = service.update_film_cut(run_id, confirmed=True)
    cut_id = run["data"]["identifiers"]["film_cut_id"]
    cut = storage.get_film_cut_version(cut_id)
    assert run["data"]["identifiers"]["timeline_revision_id"] == cut_id
    assert cut["source_cut_id"] == analysis.source_cut_id
    assert cut["source_analysis_id"] == analysis_id
    assert cut["source_application_id"] == application_id
    assert cut["metadata"]["production_package_id"] == package_id
    with pytest.raises(ValidationError):
        service.approve_film_cut(run_id, confirmed=False)
    run = service.approve_film_cut(run_id, confirmed=True)
    assert storage.get_film_cut_version(cut_id)["status"] == "approved"

    original_job_id = run["data"]["identifiers"]["render_job_ids"][0]
    run = service.create_revision(
        run_id,
        original_job_id=original_job_id,
        revision_prompt="Hold Maya's hand on the controls for one additional breath before the cut.",
        revision_reason="Protect the emotional residue selected in Editorial.",
        changed_fields=["timing", "performance_guidance"],
        confirmed=True,
    )
    revision_id = run["data"]["identifiers"]["clip_revision_id"]
    revision = storage.get_clip_revision(revision_id)
    assert revision.original_job_id == original_job_id
    assert revision.metadata["film_cut_id"] == cut_id
    assert revision.metadata["preserved_continuity"] is True

    renderer.delay_next_submission = True
    revision_create_count = renderer.create_count
    submitted_run = asyncio.run(service.render_revision(run_id, provider="simulated"))
    assert submitted_run["status"] == "revision_pending"
    assert submitted_run["data"]["artifacts"]["revision"]["status"] == "submitted"
    assert submitted_run["data"]["identifiers"]["revision_render_job_id"]
    assert renderer.create_count == revision_create_count + 1

    run = asyncio.run(service.render_revision(run_id, provider="simulated"))
    assert run["status"] == "revision_completed"
    assert renderer.create_count == revision_create_count + 1
    revision = storage.get_clip_revision(revision_id)
    assert revision.status == "complete"
    assert revision.new_job_id == run["data"]["identifiers"]["revision_render_job_id"]
    revision_job = renderer.get_job(revision.new_job_id)
    assert revision_job.input_payload.parameters["canonical_workflow"]["revision_id"] == revision_id
    assert revision_job.input_payload.parameters["continuity"] == render_job.input_payload.parameters["continuity"]

    run = service.save_approved_memory(
        run_id,
        confirmed=True,
        summary="The held hand movement carries dread into resolve without explaining it.",
    )
    memory_id = run["data"]["identifiers"]["memory_record_id"]
    memory = storage.get_cinematic_memory_record(memory_id)
    assert memory.metadata["explicit_creator_save"] is True
    assert memory.metadata["approval_id"] == approval_id
    assert memory.metadata["blueprint_version_id"] == run["blueprint_version_id"]
    assert run["data"]["identifiers"]["continuity_record_id"] == f"continuity-snapshot-{run_id}"

    reloaded_storage = DatabaseStorage(str(tmp_path / "workflow-db"))
    reloaded_state = ProjectStore(str(tmp_path / "workflow-projects.json"))
    reloaded = CanonicalProductionWorkflowService(
        storage=reloaded_storage,
        project_store=reloaded_state,
        renderer=renderer,
    ).get(run_id)
    assert reloaded["status"] == "revision_completed"
    assert reloaded["data"]["identifiers"]["memory_record_id"] == memory_id
    assert reloaded["data"]["identifiers"]["clip_revision_id"] == revision_id
    transitions = reloaded_storage.list_canonical_workflow_transitions(run_id)
    assert transitions[0]["from_status"] == "blueprint_approved"
    assert transitions[-1]["event_type"] == "approved_memory_explicitly_saved"
    assert len({row["idempotency_key"] for row in transitions}) == len(transitions)


def test_render_failure_is_recoverable_without_erasing_upstream_or_creating_memory(tmp_path: Path) -> None:
    service, storage, _, renderer = _environment(tmp_path)
    run = _through_package(service)
    run_id = run["run_id"]
    package_id = run["data"]["identifiers"]["production_package_id"]
    renderer.fail_next_submission = True

    with pytest.raises(ProviderError):
        asyncio.run(service.render_production_package(run_id, provider="simulated"))

    failed = service.get(run_id)
    assert failed["status"] == "render_failed"
    assert storage.get_previs_production_package(package_id)["status"] == "ready"
    assert storage.list_screening_outputs("project-thread") == []
    assert storage.list_cinematic_memory_for_project("project-thread") == []
    render_job_ids = failed["data"]["identifiers"]["render_job_ids"]
    create_count = renderer.create_count

    with pytest.raises(ValidationError):
        asyncio.run(service.render_production_package(run_id, provider="simulated"))

    recovered = asyncio.run(
        service.render_production_package(
            run_id,
            provider="simulated",
            retry_confirmed=True,
        )
    )
    assert recovered["status"] == "render_completed"
    assert recovered["data"]["identifiers"]["render_job_ids"] == render_job_ids
    assert renderer.create_count == create_count


def test_workflow_rejects_cross_script_and_invalid_state_transitions(tmp_path: Path) -> None:
    service, _, _, _ = _environment(tmp_path)
    with pytest.raises(StateError):
        service.begin(
            project_id="project-thread",
            scene_id="scene_001",
            script_id="script-other",
        )
    run = _begin(service)
    with pytest.raises(StateError):
        service.approve_screening(
            run["run_id"],
            screening_output_ids=["screening-unowned"],
            confirmed=True,
        )
    with pytest.raises(StateError):
        service.create_revision(
            run["run_id"],
            original_job_id="job-unowned",
            revision_prompt="Change it.",
            revision_reason="No reason.",
            changed_fields=["timing"],
            confirmed=True,
        )
