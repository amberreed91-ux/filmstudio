"""D5 guarded single-shot render (Phase A6; fake adapter, temp DBs only).

Covers: one-shot filter submits exactly one POST; whole package submits five
only with allow_full_package; empty/unknown/duplicate/multi filters refused;
already-submitted shots skipped without a second POST; credit ceiling refuses
over-limit estimates; unknown cost needs acknowledgement; the filtered path
inherits the frozen package payload byte-identically; duration validation.
No live DB, no restart, no provider contact (the estimator seam is sealed).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, StudioProject
from app.services.canonical_production_workflow_service import CanonicalProductionWorkflowService
from app.services.project_store import ProjectStore
from app.services.stability import ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService


class RecordingRenderer:
    """Fake adapter: counts create/submit POSTs, completes instantly."""

    def __init__(self, storage: DatabaseStorage) -> None:
        self.storage = storage
        self.jobs: dict[str, RenderJobModel] = {}
        self.by_idempotency: dict[str, str] = {}
        self.create_count = 0
        self.submit_posts: list[str] = []

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
        metadata: dict | None = None
        if (provider or "") == "runway_router":
            # Synthetic router-contract metadata. The real storage choke point
            # (DatabaseStorage.save_job) requires these five keys for
            # runway_router rows, so the fake attaches type-correct synthetic
            # values. This proves the service-layer submit count on the router
            # path — NOT real Router authority (the real renderer fails closed
            # earlier, at RenderService.create_job, without a generation
            # contract, and real frozen metadata is never synthetic).
            metadata = {
                "creative_generation_contract": {"synthetic": True},
                "creative_generation_manifest": {"synthetic": True},
                "creative_manifest_fingerprint": "synthetic-fingerprint",
                "creative_contract_digest": "synthetic-digest",
                "creative_generation_identity": {"synthetic": True},
            }
        job = RenderJobModel(
            id=job_id,
            project_id=project_id,
            shot_id=shot_id,
            provider=provider or "simulated",
            status="pending",
            metadata=metadata,
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=prompt,
                referenceAssets=list(reference_assets or []),
                parameters=params,
            ),
            created_at="2026-10-18T12:00:00+00:00",
            updated_at="2026-10-18T12:00:00+00:00",
        )
        self.jobs[job_id] = job
        if idempotency_key:
            self.by_idempotency[idempotency_key] = job_id
        self.storage.save_job(job)
        return job

    async def submit_job(self, job_id: str) -> RenderJobModel:
        job = self.jobs[job_id]
        self.submit_posts.append(job_id)
        job.status = "complete"
        job.provider_job_id = f"provider-{job.id}"
        job.output_payload = RenderJobOutput(
            asset_url=f"https://media.example.test/{job.id}.mp4",
            metadata={"deterministic": True},
        )
        job.completed_at = "2026-10-18T12:01:00+00:00"
        job.updated_at = job.completed_at
        self.storage.save_job(job)
        return job

    async def get_job_status(self, job_id: str) -> RenderJobModel:
        return self.jobs[job_id]

    def get_job(self, job_id: str) -> RenderJobModel | None:
        return self.jobs.get(job_id)

    def list_jobs(self, project_id: str | None = None) -> list[RenderJobModel]:
        rows = list(self.jobs.values())
        return [row for row in rows if project_id is None or row.project_id == project_id]


def _seed_project(storage: DatabaseStorage, state: ProjectStore) -> None:
    project = {
        "project_id": "project-singleshot",
        "title": "Single Shot Filter",
        "script_text": "INT. EDIT BAY - NIGHT. Maya holds the silence.",
        "production_bible": {"creative_intent": "Clarity has an emotional cost."},
        "director_intent": {"cinematic_language": "Patient frames."},
        "execution_summary": {
            "script_id": "script-single-001",
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "script_id": "script-single-001",
                    "sequence_id": "sequence_001",
                    "beats": [{"beat_id": "beat_001", "objective": "Maya commits."}],
                    "heading": "INT. EDIT BAY - NIGHT",
                    "description": "Maya watches, then commits.",
                    "objective": "Make the choice.",
                    "emotional_objective": "Dread before resolve.",
                    "emotional_tone": "contained dread",
                    "character_intention": {"MAYA": "Protect the truth."},
                    "character_emotional_state": {"MAYA": "Resolved."},
                    "theme": "Clarity costs.",
                    "creative_spine": {"central_question": "Can honesty remain humane?"},
                    "director_guidance": {"performance": "Underplay it."},
                    "sound_intent": {"room_tone": "Fan hum."},
                    "editorial_intent": {"rhythm": "Hold, decide, cut."},
                    "characters": ["MAYA"],
                    "character_references": ["character-ref-maya"],
                    "location_references": ["location-ref-edit-bay"],
                    "wardrobe_references": [],
                    "prop_references": [],
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


def _environment(tmp_path: Path, shot_count: int = 5):
    storage = DatabaseStorage(str(tmp_path / "singleshot-db"))
    state = ProjectStore(str(tmp_path / "singleshot-projects.json"))
    _seed_project(storage, state)
    service = StoryboardBlueprintService(storage)
    service.project_store = state
    detail = service.get_or_create_blueprint(
        project_id="project-singleshot",
        scene_id="scene_001",
        shot_count=shot_count,
    )
    try:
        service.derive_and_approve_image_prompts_for_version(version_id=detail["version"].version_id)
        service.approve_version(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=detail["version"].version_id,
            approved_by="creator",
        )
    except ValidationError as exc:
        review = getattr(service, "run_continuity_review", None)
        if "Continuity Review" not in exc.message or not callable(review):
            raise
        review(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=detail["version"].version_id,
        )
        service.derive_and_approve_image_prompts_for_version(version_id=detail["version"].version_id)
        service.approve_version(
            blueprint_id=detail["blueprint"].blueprint_id,
            version_id=detail["version"].version_id,
            approved_by="creator",
        )
    renderer = RecordingRenderer(storage)
    workflow = CanonicalProductionWorkflowService(
        storage=storage,
        project_store=state,
        renderer=renderer,
    )
    # Seal the spend-estimate seam: no provider contact in any test.
    workflow._estimate_shot_credits = lambda *args, **kwargs: None  # type: ignore[method-assign]
    return workflow, storage, renderer


def _through_package(workflow: CanonicalProductionWorkflowService) -> dict:
    run = workflow.begin(
        project_id="project-singleshot",
        scene_id="scene_001",
        script_id="script-single-001",
        sequence_id="sequence_001",
        beat_ids=["beat_001"],
    )
    run = asyncio.run(workflow.generate_previs(run["run_id"]))
    assert run["status"] == "previs_generated"
    image_ids = [row["previs_image_id"] for row in run["data"]["artifacts"]["previs"]]
    run = workflow.approve_previs(run["run_id"], previs_image_ids=image_ids, confirmed=True)
    packaged = workflow.create_production_package(run["run_id"])
    # Baselines for the render-phase assertions below: previs jobs are not
    # render POSTs, so reset the fake transport counters here.
    workflow.renderer.create_count = 0
    workflow.renderer.submit_posts = []
    return packaged


def _package_ids(run: dict) -> list[str]:
    package = run["data"]["artifacts"]["production_package"]
    return [row["storyboard_shot_id"] for row in package["payload"]["shots"]]


def test_one_shot_filter_submits_exactly_one_post(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)
    assert len(ids) == 5

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[1]],
            acknowledge_unknown_cost=True,
        )
    )
    assert result["status"] == "render_completed"
    assert renderer.create_count == 1
    assert len(renderer.submit_posts) == 1
    row = result["data"]["artifacts"]["render_jobs"][0]
    assert row["storyboard_shot_id"] == ids[1]
    # The exact frozen package prompt is what the job carries.
    package = run["data"]["artifacts"]["production_package"]
    frozen = next(r for r in package["payload"]["shots"] if r["storyboard_shot_id"] == ids[1])
    job = renderer.get_job(row["render_job_id"])
    assert job is not None and job.input_payload.prompt == frozen["prompt"]
    assert job.input_payload.prompt
    assert len(job.input_payload.prompt) <= 20000


def test_whole_package_refused_without_flag_and_submits_five_with_flag(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)

    with pytest.raises(ValidationError, match="allow_full_package"):
        asyncio.run(
            workflow.render_production_package(run["run_id"], provider="runway")
        )
    with pytest.raises(ValidationError, match="allow_full_package"):
        asyncio.run(
            workflow.render_production_package(
                run["run_id"], provider="runway", storyboard_shot_ids=[]
            )
        )
    assert renderer.create_count == 0
    assert renderer.submit_posts == []

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            allow_full_package=True,
            acknowledge_unknown_cost=True,
        )
    )
    assert result["status"] == "render_completed"
    assert renderer.create_count == 5
    assert len(renderer.submit_posts) == 5


def test_filter_refusals_name_each_id(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    with pytest.raises(ValidationError, match="nope-not-a-shot"):
        asyncio.run(
            workflow.render_production_package(
                run["run_id"],
                provider="runway",
                storyboard_shot_ids=["nope-not-a-shot"],
                acknowledge_unknown_cost=True,
            )
        )
    with pytest.raises(ValidationError) as dup:
        asyncio.run(
            workflow.render_production_package(
                run["run_id"],
                provider="runway",
                storyboard_shot_ids=[ids[0], ids[0]],
                acknowledge_unknown_cost=True,
            )
        )
    assert ids[0] in str(dup.value.message)
    with pytest.raises(ValidationError, match="allow_full_package"):
        asyncio.run(
            workflow.render_production_package(
                run["run_id"],
                provider="runway",
                storyboard_shot_ids=[ids[0], ids[1]],
                acknowledge_unknown_cost=True,
            )
        )
    assert renderer.create_count == 0
    assert renderer.submit_posts == []


def test_multi_shot_with_flag_submits_each_once(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[0], ids[2]],
            allow_full_package=True,
            acknowledge_unknown_cost=True,
        )
    )
    assert result["status"] == "render_completed"
    assert renderer.create_count == 2
    assert len(renderer.submit_posts) == 2


def test_already_submitted_shot_skipped_without_second_post(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    first = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[3]],
            acknowledge_unknown_cost=True,
        )
    )
    assert first["status"] == "render_completed"
    assert len(renderer.submit_posts) == 1

    # A repeat call for the same shot never submits twice.
    second = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[3]],
            acknowledge_unknown_cost=True,
        )
    )
    assert second["status"] == "render_completed"
    assert len(renderer.submit_posts) == 1
    assert renderer.create_count == 1


def test_ceiling_refuses_over_limit_estimate(tmp_path: Path, monkeypatch) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    monkeypatch.setattr(workflow, "_estimate_shot_credits", lambda *a, **k: 9999.0)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "300")
    with pytest.raises(ValidationError, match="exceeds"):
        asyncio.run(
            workflow.render_production_package(
                run["run_id"],
                provider="runway",
                storyboard_shot_ids=[ids[0]],
                acknowledge_unknown_cost=True,
            )
        )
    assert renderer.create_count == 0
    assert renderer.submit_posts == []


def test_unknown_cost_needs_acknowledgement(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    with pytest.raises(ValidationError, match="acknowledge_unknown_cost"):
        asyncio.run(
            workflow.render_production_package(
                run["run_id"],
                provider="runway",
                storyboard_shot_ids=[ids[0]],
            )
        )
    assert renderer.create_count == 0

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[0]],
            acknowledge_unknown_cost=True,
        )
    )
    assert result["status"] == "render_completed"
    assert len(renderer.submit_posts) == 1


def test_under_ceiling_estimate_passes_without_ack(tmp_path: Path, monkeypatch) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    monkeypatch.setattr(workflow, "_estimate_shot_credits", lambda *a, **k: 12.0)
    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[0]],
        )
    )
    assert result["status"] == "render_completed"
    assert len(renderer.submit_posts) == 1


def test_filtered_path_inherits_frozen_package_payload(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)
    package = run["data"]["artifacts"]["production_package"]
    frozen = next(r for r in package["payload"]["shots"] if r["storyboard_shot_id"] == ids[2])

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[2]],
            acknowledge_unknown_cost=True,
        )
    )
    job = renderer.get_job(result["data"]["artifacts"]["render_jobs"][0]["render_job_id"])
    assert job is not None
    # Byte-identical to the whole-package build: same frozen prompt, same
    # references, same planned duration — the filter only narrows the loop.
    assert job.input_payload.prompt == frozen["prompt"]
    assert job.input_payload.referenceAssets == list(frozen["reference_assets"])
    params = job.input_payload.parameters
    assert params["duration"] == (frozen["parameters"] or {}).get("duration")
    selection = params["canonical_workflow"]["selection"]
    assert selection["storyboard_shot_ids"] == [ids[2]]
    assert selection["filtered_from"] == "full_package"


def test_duration_validation(tmp_path: Path) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    for bad in (1, 31, 0, -5):
        with pytest.raises(ValidationError, match="between 2"):
            asyncio.run(
                workflow.render_production_package(
                    run["run_id"],
                    provider="runway",
                    storyboard_shot_ids=[ids[0]],
                    duration_seconds=bad,
                    acknowledge_unknown_cost=True,
                )
            )
    assert renderer.create_count == 0

    planned = workflow._planned_shot_duration(
        next(r for r in run["data"]["artifacts"]["production_package"]["payload"]["shots"] if r["storyboard_shot_id"] == ids[0])
    )
    assert planned is not None
    override = 8 if planned != 8 else 5
    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[0]],
            duration_seconds=override,
            acknowledge_unknown_cost=True,
        )
    )
    job = renderer.get_job(result["data"]["artifacts"]["render_jobs"][0]["render_job_id"])
    assert job is not None
    assert job.input_payload.parameters["duration"] == override
    assert job.input_payload.parameters["duration_seconds"] == override
    assert job.input_payload.parameters["planned_duration_seconds"] == planned


def test_estimate_probe_returns_advisory_without_jobs(tmp_path: Path, monkeypatch) -> None:
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    monkeypatch.setattr(
        CanonicalProductionWorkflowService,
        "dry_run_estimate_for_shot",
        lambda self, shot, **kwargs: (20.0, "gen4.5"),
    )
    probe = workflow.estimate_render_cost(
        run["run_id"], storyboard_shot_ids=[ids[1]], provider="runway"
    )
    assert probe["ceiling_credits"] == 300
    assert probe["ceiling_env_var"] == "RUNWAY_RENDER_MAX_CREDITS"
    assert len(probe["estimates"]) == 1
    row = probe["estimates"][0]
    assert row["storyboard_shot_id"] == ids[1]
    assert row["estimated_credits"] == 20.0
    assert row["resolved_model"] == "gen4.5"
    assert row["estimate_available"] is True
    # The probe creates nothing.
    assert renderer.create_count == 0
    assert renderer.submit_posts == []

    with pytest.raises(ValidationError, match="Unknown"):
        workflow.estimate_render_cost(
            run["run_id"], storyboard_shot_ids=["missing-id"], provider="runway"
        )


def test_one_shot_router_path_submits_exactly_one_post(tmp_path: Path) -> None:
    """Gate 1 Q1: the one-shot filter is provider-agnostic at the service layer.

    Provider `runway_router` through the same fake adapter submits exactly ONE
    create and ONE submit POST for a one-shot request. No live DB, no restart,
    no provider contact (the estimator seam is sealed; the router-contract
    metadata on the fake row is synthetic — see RecordingRenderer.create_job).
    """
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)
    assert len(ids) == 5

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway_router",
            storyboard_shot_ids=[ids[1]],
            acknowledge_unknown_cost=True,
        )
    )
    assert result["status"] == "render_completed"
    assert renderer.create_count == 1
    assert len(renderer.submit_posts) == 1
    row = result["data"]["artifacts"]["render_jobs"][0]
    assert row["storyboard_shot_id"] == ids[1]
    job = renderer.get_job(row["render_job_id"])
    assert job is not None
    assert job.provider == "runway_router"
    # The exact frozen package prompt is what the job carries.
    package = run["data"]["artifacts"]["production_package"]
    frozen = next(r for r in package["payload"]["shots"] if r["storyboard_shot_id"] == ids[1])
    assert job.input_payload.prompt == frozen["prompt"]
    assert job.input_payload.prompt


def test_created_job_record_stores_estimate_ack_and_prompt(tmp_path: Path, monkeypatch) -> None:
    """Gate 1 Q5: the created job record stores the estimate, the
    acknowledgement flag, and the exact promptText sent, so the Phase C
    audit can read them off the run artifact.
    """
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)
    package = run["data"]["artifacts"]["production_package"]
    frozen = next(r for r in package["payload"]["shots"] if r["storyboard_shot_id"] == ids[0])
    planned = workflow._planned_shot_duration(frozen)
    assert planned is not None

    monkeypatch.setattr(workflow, "_estimate_shot_credits", lambda *a, **k: 20.0)
    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[0]],
            acknowledge_unknown_cost=True,
        )
    )
    row = result["data"]["artifacts"]["render_jobs"][0]
    assert row["estimated_credits"] == 20.0
    assert row["acknowledge_unknown_cost"] is True
    assert row["effective_duration_seconds"] == planned
    job = renderer.get_job(row["render_job_id"])
    assert job is not None
    assert row["prompt_text"] == job.input_payload.prompt == frozen["prompt"]
    assert row["prompt_text"]


def test_created_job_record_marks_unknown_cost(tmp_path: Path) -> None:
    """Gate 1 Q5 (unknown-cost leg): no estimate available, acknowledged —
    the record stores estimated_credits=None alongside ack=True.
    """
    workflow, _, renderer = _environment(tmp_path)
    run = _through_package(workflow)
    ids = _package_ids(run)

    result = asyncio.run(
        workflow.render_production_package(
            run["run_id"],
            provider="runway",
            storyboard_shot_ids=[ids[0]],
            acknowledge_unknown_cost=True,
        )
    )
    row = result["data"]["artifacts"]["render_jobs"][0]
    assert row["estimated_credits"] is None
    assert row["acknowledge_unknown_cost"] is True
    job = renderer.get_job(row["render_job_id"])
    assert job is not None
    assert row["prompt_text"] == job.input_payload.prompt
    assert row["prompt_text"]
