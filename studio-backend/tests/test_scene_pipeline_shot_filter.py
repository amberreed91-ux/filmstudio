"""Phase 2B item 4: D5 shot-filter tests for the scene-pipeline submit path.

Contract under test (all through SceneProductionPipelineService.generate_scene
with hermetic fakes + temp dirs — no provider contact, no live DB):

- one storyboard_shot_id -> exactly one create + one submit, carrying the
  frozen contract/prompt, with scene assembly skipped (subset safety);
- five shots -> refused without allow_full_package, five creates + submits
  with it (full selection keeps the normal assembly path);
- every gate failure (unknown/duplicate/multi/empty filter, over-ceiling
  SUM, unknown cost without ack, duplicate submit) -> zero creates AND zero
  submits (fail closed before any provider contact).
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput
from app.services.generation_contract import (
    FrozenGenerationContract,
    freeze_dialogue_handoff,
    freeze_generation_contract,
)
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.shot_manifest import build_shot_manifest
from app.services.stability import ProviderError, ValidationError
from app.services.test_scene_production_pipeline_service import (
    FakeAudioService,
    FakeRenderService,
    FakeStitchingService,
)
from conftest import run_async


def _project5() -> dict[str, Any]:
    shots = [
        {"shot_id": f"scene_001_shot_00{index}", "description": f"Beat {index}."}
        for index in range(1, 6)
    ]
    return {
        "project_id": "project_filter_test",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "description": "Dre listens before answering.",
                    "text": "INT. OFFICE - DAY\nDRE\nYou heard that too, right?\nDre listens before answering.\nMaya holds the look.",
                    "emotional_tone": "restrained concern",
                    "characters": ["Dre"],
                    "setting_id": "set-office",
                    "shots": shots,
                }
            ],
            "dialogue_lines": [
                {
                    "scene_id": "scene_001",
                    "shot_id": "scene_001_shot_001",
                    "character": "Dre",
                    "text": "You heard that too, right?",
                    "emotional_subtext": "casual concern",
                }
            ],
        },
    }


class CountingRenderService(FakeRenderService):
    """Hermetic submit path with mirrors of the production guarantees.

    Mirrors of RenderService (cited so drift is reviewable): explicit
    idempotency-key reuse on create returns the existing row with no new
    row (cf. create_job / _find_idempotent_job); submit skips live and
    finished jobs and serializes concurrent submits per job id (cf.
    submit_job's _submit_locks + status skip), so each counted submit is
    one provider POST. Anything these mirrors get wrong is a test-only
    gap, never production behavior.
    """

    def __init__(self, outputs_dir: Path):
        super().__init__(outputs_dir)
        self.submits: list[str] = []
        self._submit_locks: set[str] = set()
        self.fail_next_submit: Exception | None = None

    @staticmethod
    def _explicit_key(kwargs: dict[str, Any]) -> str:
        params = kwargs.get("parameters") or {}
        return str(params.get("idempotency_key") or "").strip()

    def create_job(self, **kwargs):
        key = self._explicit_key(kwargs)
        if key:
            for existing in self.jobs.values():
                reliability = ((existing.metadata or {}).get("pipeline_reliability") or {})
                if (
                    existing.project_id == kwargs["project_id"]
                    and existing.shot_id == kwargs["shot_id"]
                    and existing.provider == (kwargs.get("provider") or "happyhorse")
                    and reliability.get("idempotency_key") == key
                ):
                    return existing
        index = len(self.created) + 1
        job_id = f"job-{index}"
        shot_id = kwargs["shot_id"]
        video = self.outputs_dir / f"{shot_id}.mp4"
        video.write_bytes(b"fake-video")
        metadata: dict[str, Any] = dict(kwargs.get("metadata") or {})
        reliability = dict(metadata.get("pipeline_reliability") or {})
        if key:
            reliability["idempotency_key"] = key
            reliability["idempotency_key_source"] = "caller"
            metadata["pipeline_reliability"] = reliability
        job = RenderJobModel(
            id=job_id,
            project_id=kwargs["project_id"],
            shot_id=shot_id,
            provider=kwargs.get("provider") or "happyhorse",
            status="pending",
            input_payload=RenderJobInput(
                shot_id=shot_id,
                prompt=kwargs["prompt"],
                referenceAssets=kwargs.get("reference_assets") or [],
                parameters=kwargs.get("parameters") or {},
                consistency_payload=self.consistency_payload,
            ),
            output_payload=RenderJobOutput(asset_url=f"/outputs/renders/{video.name}"),
            metadata=metadata,
        )
        self.created.append(kwargs)
        self.jobs[job_id] = job
        return job

    async def submit_job(self, job_id: str):
        import asyncio

        if job_id in self._submit_locks:
            return self.jobs[job_id]
        job = self.jobs[job_id]
        if job.status in {"rendering", "complete", "needs_review"}:
            return job
        self._submit_locks.add(job_id)
        try:
            self.submits.append(job_id)
            if self.fail_next_submit is not None:
                exc = self.fail_next_submit
                self.fail_next_submit = None
                job.status = "failed"
                job.error_message = str(exc)
                raise exc
            await asyncio.sleep(0)  # let a concurrent duplicate arrive mid-POST
            job.status = "complete"
            return job
        finally:
            self._submit_locks.discard(job_id)

    async def get_job_status(self, job_id: str):
        return self.jobs[job_id]

    def list_persisted_jobs(self, project_id: str | None = None):
        return [
            job for job in self.jobs.values()
            if project_id is None or job.project_id == project_id
        ]

    def seed_job(self, shot_id: str, status: str, provider: str = "runway_router") -> RenderJobModel:
        """Plant a leftover/history job row (e.g. from a crashed request)."""
        job = RenderJobModel(
            id=f"seed-{len(self.jobs)}-{shot_id}-{status}",
            project_id="project_filter_test",
            shot_id=shot_id,
            provider=provider,
            status=status,
            input_payload=RenderJobInput(shot_id=shot_id, prompt="seed"),
        )
        self.jobs[job.id] = job
        return job


def _tag_shots(costs: list[float | None]):
    """prepared_mutator: board ids + per-shot cost pictures onto the batch."""

    def _mutate(batch: dict[str, Any]) -> None:
        for position, entry in enumerate(batch["entries"]):
            entry["storyboard_shot_id"] = f"sbs-00{position + 1}"
            credit = costs[position]
            if credit is None:
                entry["cost_estimate"] = {
                    "model": None,
                    "duration_seconds": 5,
                    "estimated_credits": None,
                    "estimated": False,
                }
            else:
                entry["cost_estimate"] = {
                    "model": "test-model",
                    "duration_seconds": 5,
                    "estimated_credits": credit,
                    "estimated": True,
                }

    return _mutate


def _noop_prepare5(pipeline: SceneProductionPipelineService, tag: Any):
    """Ready-batch builder mirroring the shared 2-shot fixture, but dealing
    canonical content units round-robin so all five shots hold unique
    coverage (shared claims are duplicate-coverage blockers)."""

    def _prepare(*, project_id, scene_id, project, provider=None, mint_generic_authorization=False):
        from app.services.camera_provenance import (
            CAMERA_PROVENANCE_CREATOR,
            CAMERA_PROVENANCE_UNSPECIFIED,
            camera_plan_digest,
            canonical_camera_instructions,
        )
        from app.services.scene_coverage_contract import build_scene_coverage_contract

        scene = pipeline._find_scene(project, scene_id)
        scene["dialogue_disposition"] = "INTENTIONAL_SILENCE"
        scene["dialogue_disposition_reason"] = "The synthetic fixture holds non-dialogue shots in silence."
        shots = pipeline._resolve_ordered_shots(project, scene)
        entries = []
        for index, shot in enumerate(shots, start=1):
            shot_id = str(shot.get("shot_id"))
            prompt = pipeline._shot_prompt(scene, shot, index, len(shots))
            dialogue = pipeline._dialogue_lines_for_shot(project, scene_id, shot_id) or []
            handoff = freeze_dialogue_handoff(scene_id=scene_id, shot_id=shot_id, lines=dialogue)
            settings = dict(shot.get("parameters") or {})
            creator_plan = settings.get("creator_shot_planning")
            creator_plan = creator_plan if isinstance(creator_plan, dict) else {
                "camera": "Locked-off", "framing": "Medium"
            }
            settings["creator_shot_planning"] = creator_plan
            settings["character_focus"] = ["Dre"]
            camera_plan = {key: value for key, value in creator_plan.items() if value}
            if camera_plan:
                camera_plan.setdefault("camera", "Locked-off")
            camera_provenance = CAMERA_PROVENANCE_CREATOR if camera_plan else CAMERA_PROVENANCE_UNSPECIFIED
            settings.update(
                camera_plan=camera_plan,
                camera_provenance=camera_provenance,
                camera_instructions=[],
                camera_source_project_id=project_id,
                camera_source_scene_id=scene_id,
                camera_source_shot_id=shot_id,
                camera_source_storyboard_shot_id="",
                camera_target_project_id=project_id,
                camera_target_scene_id=scene_id,
                camera_target_shot_id=shot_id,
                dialogue_lines=handoff["payload"]["lines"],
                dialogue_handoff=handoff,
            )
            settings["camera_source_digest"] = camera_plan_digest(
                camera_plan, camera_provenance,
                source_project_id=project_id, source_scene_id=scene_id, source_shot_id=shot_id,
            )
            settings["camera_instructions"] = canonical_camera_instructions(camera_plan, camera_provenance)
            frozen = freeze_generation_contract(
                shot_id=shot_id, prompt=prompt, parameters=settings, dialogue_handoff=handoff,
            )
            entries.append({
                "shot_id": shot_id,
                "prompt": prompt,
                "references": list(shot.get("reference_assets") or shot.get("source_refs") or []),
                "generation_settings": settings,
                "duration_seconds": shot.get("duration_seconds", 5),
                "dialogue_lines": handoff["payload"]["lines"],
                "dialogue_handoff": handoff,
                "camera_plan": camera_plan,
                "camera_provenance": frozen.camera_provenance,
                "camera_source_digest": frozen.camera_source_digest,
                "camera_source_project_id": frozen.camera_source_project_id,
                "camera_source_scene_id": frozen.camera_source_scene_id,
                "camera_source_shot_id": frozen.camera_source_shot_id,
                "camera_source_storyboard_shot_id": frozen.camera_source_storyboard_shot_id,
                "camera_target_project_id": frozen.camera_target_project_id,
                "camera_target_scene_id": frozen.camera_target_scene_id,
                "camera_target_shot_id": frozen.camera_target_shot_id,
                "camera_instructions": frozen.payload()["camera_instructions"],
                "generation_contract": frozen.to_record(),
                "generation_contract_digest": frozen.creative_digest(),
                "parameters": settings,
            })
        manifest = build_shot_manifest(
            project_id=project_id, scene_id=scene_id, scene=scene,
            scene_version="test-scene-v1", storyboard_version="", entries=entries,
        )
        for entry in entries:
            entry["manifest_fingerprint"] = manifest["manifest_fingerprint"]
            contract = FrozenGenerationContract.from_record(entry["generation_contract"])
            contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
            entry["generation_contract"] = contract.to_record()
            entry["generation_contract_digest"] = contract.creative_digest()
        references = [
            {"ref_id": "ref-dre-face", "uri": "https://assets.example.test/dre.png", "target_type": "character", "target_id": "char-dre", "role": "face", "category": "face", "canonical": True, "approval_state": "approved", "source_kind": "confirmed", "kind": "character_face"},
            {"ref_id": "ref-office", "uri": "https://assets.example.test/office.png", "target_type": "setting", "target_id": "set-office", "role": "environment", "category": "environment", "canonical": True, "approval_state": "approved", "source_kind": "confirmed", "kind": "setting"},
        ]
        requirements = {
            "setting_id": "set-office",
            "characters": {"char-dre": {"name": "Dre"}},
            "reference_binding": references,
        }
        project["script_text"] = pipeline._scene_text(scene)
        for shot, entry in zip(shots, entries):
            shot_id = str(shot.get("shot_id"))
            shot["scene_id"] = scene_id
            shot["parameters"] = dict(entry["generation_settings"])
            shot["parameters"]["character_focus"] = ["Dre"]
            shot["parameters"]["dialogue_disposition"] = "ASSIGNED" if entry["dialogue_lines"] else "INTENTIONAL_SILENCE"
            shot["parameters"]["dialogue_disposition_reason"] = "Dre's silent reaction shot." if not entry["dialogue_lines"] else ""
            shot["parameters"]["dialogue_lines"] = entry["dialogue_lines"]
            shot["parameters"]["camera_source_digest"] = camera_plan_digest(
                entry["camera_plan"], entry["camera_provenance"],
                source_project_id=project_id, source_scene_id=scene_id, source_shot_id=shot_id,
            )
            shot["parameters"]["creator_shot_planning"] = entry["camera_plan"]
            entry["camera_source_digest"] = shot["parameters"]["camera_source_digest"]
            entry["generation_settings"].update(shot["parameters"])
        coverage_probe, _, _ = build_scene_coverage_contract(
            project_id=project_id, project=project, scene=scene, shots=shots,
            reference_requirements=requirements,
        )
        content_units = coverage_probe["content_units"]
        # Round-robin deal: every unit claimed exactly once, every shot holds
        # at least one unit (duplicate claims are coverage blockers).
        for position, shot in enumerate(shots):
            shot["covered_content_ids"] = [
                row["content_id"] for order, row in enumerate(content_units)
                if order % len(shots) == position
            ]
        creator_decisions = [
            {
                "obligation_type": "content",
                "obligation_id": row["content_id"],
                "status": "ASSIGNED",
                "shot_id": next(
                    shot["shot_id"] for shot in shots
                    if row["content_id"] in shot.get("covered_content_ids", [])
                ),
                "reason": "Synthetic test fixture assigns canonical scene action to its covering shot.",
            }
            for row in content_units
        ]
        dialogue_shot_by_text = {
            line.get("text"): row["shot_id"]
            for row in entries
            for line in row["dialogue_lines"]
            if line.get("text")
        }
        creator_decisions.extend(
            {
                "obligation_type": "dialogue",
                "obligation_id": row["dialogue_id"],
                "status": "ASSIGNED",
                "shot_id": dialogue_shot_by_text.get(row["text"], shots[0]["shot_id"]),
                "reason": "",
            }
            for row in coverage_probe["dialogue"]
        )
        canonical_dialogue_line_by_id = {
            row["dialogue_id"]: {"line_id": row["dialogue_id"], "character": row["speaker"], "text": row["text"]}
            for row in coverage_probe["dialogue"]
        }
        creator_decisions.extend(
            [
                {
                    "obligation_type": "shot_content",
                    "obligation_id": shot["shot_id"],
                    "status": "UNRESOLVED" if any(row["content_id"] in shot["covered_content_ids"] for row in content_units) else "INTENTIONAL_SILENCE",
                    "shot_id": None,
                    "reason": "" if any(row["content_id"] in shot["covered_content_ids"] for row in content_units) else "Synthetic test fixture leaves this take without canonical content coverage.",
                }
                for shot in shots
            ]
        )
        creator_decisions.extend(
            [
                {
                    "obligation_type": "shot_dialogue",
                    "obligation_id": shot["shot_id"],
                    "status": "UNRESOLVED" if shot["shot_id"] in dialogue_shot_by_text.values() else "INTENTIONAL_SILENCE",
                    "shot_id": None,
                    "reason": "Synthetic test fixture holds this shot in silence." if shot["shot_id"] not in dialogue_shot_by_text.values() else "",
                }
                for shot in shots
            ]
        )
        coverage, coverage_blockers, dialogue_by_shot = build_scene_coverage_contract(
            project_id=project_id, project=project, scene=scene, shots=shots,
            reference_requirements=requirements,
            creator_decisions=creator_decisions,
            legacy_sources_blocked=False,
        )
        assert not coverage_blockers, coverage_blockers
        coverage_shots = {row["shot_id"]: row for row in coverage["shots"]}
        for shot, entry in zip(shots, entries):
            shot_id = str(shot.get("shot_id"))
            shot_coverage = coverage_shots[shot_id]
            entry["scene_coverage"] = coverage
            entry["shot_coverage"] = shot_coverage
            entry["dialogue_lines"] = [
                {
                    **canonical_dialogue_line_by_id.get(str(row.get("line_id") or ""), row),
                    **row,
                    "scene_id": scene_id,
                    "shot_id": shot_id,
                }
                for row in dialogue_by_shot[shot_id]
            ]
            entry["dialogue_handoff"] = freeze_dialogue_handoff(
                scene_id=scene_id, shot_id=shot_id, lines=entry["dialogue_lines"]
            )
            entry["references"] = [row["uri"] for row in references]
            entry["reference_roles"] = [row["role"] for row in references]
            entry["reference_binding"] = references
            entry["generation_settings"].update(
                dialogue_lines=entry["dialogue_lines"], dialogue_handoff=entry["dialogue_handoff"],
                scene_coverage=coverage, scene_coverage_shot=shot_coverage,
                reference_roles=entry["reference_roles"], frozen_reference_binding=references,
            )
            contract_references = [
                {"uri": row["uri"], "studio_role": row["role"], "source": "canonical_reference_binding",
                 "ref_id": row["ref_id"], "target_type": row["target_type"], "target_id": row["target_id"],
                 "category": row["category"], "canonical": row["canonical"],
                 "approval_state": row["approval_state"], "source_kind": row["source_kind"], "kind": row["kind"]}
                for row in references
            ]
            frozen = freeze_generation_contract(
                shot_id=shot_id, prompt=entry["prompt"], reference_assets=contract_references,
                parameters=entry["generation_settings"], dialogue_handoff=entry["dialogue_handoff"],
                scene_coverage=coverage, scene_coverage_shot=shot_coverage,
            )
            entry["generation_contract"] = frozen.to_record()
            entry["generation_contract_digest"] = frozen.creative_digest()
            entry["camera_plan"] = frozen.payload()["camera_plan"]
            entry["camera_provenance"] = frozen.camera_provenance
            entry["camera_instructions"] = frozen.payload()["camera_instructions"]
            entry["parameters"] = entry["generation_settings"]
        manifest = build_shot_manifest(
            project_id=project_id, scene_id=scene_id, scene=scene,
            scene_version="test-scene-v1", storyboard_version="", entries=entries,
            scene_lineage=coverage,
        )
        for entry in entries:
            entry["manifest_fingerprint"] = manifest["manifest_fingerprint"]
            frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
            frozen = replace(frozen, manifest_fingerprint=manifest["manifest_fingerprint"])
            entry["generation_contract"] = frozen.to_record()
            entry["generation_contract_digest"] = frozen.creative_digest()
        scene["shots"] = copy.deepcopy(shots)
        batch = {
            "project_id": project_id,
            "scene_id": scene_id,
            "ready": True,
            "blockers": [],
            "shots": shots,
            "entries": entries,
            "scene_coverage": coverage,
            "manifest": manifest,
            "scene_snapshot": scene,
            "scene_snapshot_fingerprint": pipeline._snapshot_fingerprint(scene),
            "source_kind": "scene_shots",
            "shot_source_fingerprint": pipeline._snapshot_fingerprint(pipeline._sort_shots(scene.get("shots") or [])),
            "canonical_script_sha256": hashlib.sha256(str(project.get("script_text") or "").encode()).hexdigest(),
            "generation_context_ids": [],
            "cost_estimate": None,
        }
        if tag:
            tag(batch)
        return batch

    return _prepare


def _harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, costs: list[float | None]):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    monkeypatch.setenv("RUNWAY_RENDER_MAX_CREDITS", "300")
    render = CountingRenderService(outputs_dir)
    stitching = FakeStitchingService()
    pipeline = SceneProductionPipelineService(
        backend_root=tmp_path,
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=stitching,
    )
    pipeline.prepare_scene_batch = _noop_prepare5(pipeline, _tag_shots(costs))  # type: ignore[method-assign]
    return pipeline, render, stitching


def _generate(service: Any, project: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return run_async(service.generate_scene(
        project_id="project_filter_test",
        scene_id="scene_001",
        project=project,
        provider="runway_router",
        **kwargs,
    ))


def test_single_shot_filter_creates_and_submits_exactly_one_post_with_frozen_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    service, render, stitching = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    project = _project5()

    result = _generate(service, project, storyboard_shot_ids=["sbs-002"])

    assert len(render.created) == 1
    assert len(render.submits) == 1
    created = render.created[0]
    assert created["shot_id"] == "scene_001_shot_002"
    assert created["provider"] == "runway_router"
    # The frozen contract + verbatim prompt ride on the single create.
    assert isinstance(created["generation_contract"], dict)
    assert created["generation_contract"]["payload"]["shot_id"] == "scene_001_shot_002"
    assert created["prompt"] == created["generation_contract"]["payload"]["prompt"]
    assert created["creative_manifest_fingerprint"]
    assert created["metadata"]["batch_authorization"]["shot_verdict"] == "authorized"
    # Subset safety: no stitch, no assembly, filter echoed.
    assert stitching.calls == []
    assert result["status"] == "complete"
    assert result["stitch"] is None
    assert result["assembly"] is None
    assert result["assembly_skipped"] == "subset_selection_has_no_scene_assembly"
    assert result["shot_filter"]["selected_shot_ids"] == ["scene_001_shot_002"]
    assert result["shot_filter"]["omitted_shot_ids"] == [
        "scene_001_shot_001", "scene_001_shot_003", "scene_001_shot_004", "scene_001_shot_005",
    ]
    assert result["output_url"] == result["shots"][0]["audio"]["final_video_url"]


def test_five_shots_only_with_allow_full_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, stitching = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    project = _project5()
    all_ids = [f"sbs-00{index}" for index in range(1, 6)]

    with pytest.raises(ValidationError):
        _generate(service, project, storyboard_shot_ids=all_ids)
    assert render.created == []
    assert render.submits == []

    result = _generate(service, project, storyboard_shot_ids=all_ids, allow_full_package=True)
    assert len(render.created) == 5
    assert len(render.submits) == 5
    # A full selection keeps the normal assembly path.
    assert len(stitching.calls) == 1
    assert result["assembly"] is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"storyboard_shot_ids": ["nope-sbs-1"]},
        {"storyboard_shot_ids": ["sbs-002", "sbs-002"]},
        {"storyboard_shot_ids": ["sbs-001", "sbs-002"]},
        {"storyboard_shot_ids": []},
        {"storyboard_shot_ids": [""]},
    ],
    ids=["unknown-id", "duplicate-id", "multi-without-flag", "empty-filter", "blank-id"],
)
def test_filter_shape_failures_create_zero_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    with pytest.raises(ValidationError):
        _generate(service, _project5(), **kwargs)
    assert render.created == []
    assert render.submits == []


def test_over_ceiling_sum_refused_with_zero_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[100.0] * 5)
    with pytest.raises(ValidationError) as excinfo:
        _generate(
            service, _project5(),
            storyboard_shot_ids=[f"sbs-00{index}" for index in range(1, 6)],
            allow_full_package=True,
        )
    assert "ceiling" in str(excinfo.value.message)
    assert render.created == []
    assert render.submits == []


def test_single_over_ceiling_shot_refused_with_zero_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0, 500.0, 10.0, 10.0, 10.0])
    with pytest.raises(ValidationError):
        _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    assert render.created == []
    assert render.submits == []


def test_unknown_cost_needs_acknowledgement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[None] * 5)
    with pytest.raises(ValidationError) as excinfo:
        _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    assert "acknowledge_unknown_cost" in str(excinfo.value.message)
    assert render.created == []
    assert render.submits == []

    result = _generate(
        service, _project5(), storyboard_shot_ids=["sbs-002"], acknowledge_unknown_cost=True,
    )
    assert len(render.created) == 1
    assert len(render.submits) == 1
    assert result["shot_filter"]["selected_shot_ids"] == ["scene_001_shot_002"]


def test_duplicate_submit_refused_with_zero_new_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, stitching = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    project = _project5()

    def _persist(updated: dict[str, Any]) -> dict[str, Any]:
        project["execution_summary"] = updated.get("execution_summary", {})
        return updated

    first = run_async(service.generate_scene(
        project_id="project_filter_test",
        scene_id="scene_001",
        project=project,
        provider="runway_router",
        storyboard_shot_ids=["sbs-002"],
        save_project=_persist,
    ))
    assert first["status"] == "complete"
    assert len(render.created) == 1

    with pytest.raises(ValidationError) as excinfo:
        _generate(service, project, storyboard_shot_ids=["sbs-002"])
    assert "duplicate" in str(excinfo.value.message).lower()
    assert len(render.created) == 1
    assert len(render.submits) == 1


def test_legacy_whole_scene_path_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, stitching = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    result = _generate(service, _project5())
    assert len(render.created) == 5
    assert len(render.submits) == 5
    assert len(stitching.calls) == 1
    assert result["assembly"] is not None
    assert "shot_filter" not in result


def test_filtered_create_carries_deterministic_idempotency_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    result = _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    key = render.created[0]["parameters"]["idempotency_key"]
    assert key.endswith(":scene_001_shot_002")
    assert result["shot_manifest"]["manifest_fingerprint"] in key
    job = render.jobs[render.submits[0]]
    assert job.metadata["pipeline_reliability"]["idempotency_key"] == key
    assert job.metadata["pipeline_reliability"]["idempotency_key_source"] == "caller"


@pytest.mark.parametrize("status", ["queued", "submitted", "rendering", "complete", "cancelled"])
def test_leftover_non_failed_job_blocks_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    render.seed_job("scene_001_shot_002", status)
    with pytest.raises(ValidationError) as excinfo:
        _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    assert "has not failed" in str(excinfo.value.message)
    assert render.created == []
    assert render.submits == []


def test_failed_prior_attempt_allows_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    render.seed_job("scene_001_shot_002", "failed")
    result = _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    assert result["status"] == "complete"
    assert len(render.created) == 1
    assert len(render.submits) == 1


def test_concurrent_duplicate_requests_produce_one_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    project = _project5()

    async def _both():
        first = service.generate_scene(
            project_id="project_filter_test", scene_id="scene_001", project=project,
            provider="runway_router", storyboard_shot_ids=["sbs-002"],
        )
        second = service.generate_scene(
            project_id="project_filter_test", scene_id="scene_001", project=project,
            provider="runway_router", storyboard_shot_ids=["sbs-002"],
        )
        return await asyncio.gather(first, second, return_exceptions=True)

    outcomes = run_async(_both())
    assert render.submits == [render.submits[0]] and len(render.submits) == 1
    assert len(render.created) == 1
    successes = [row for row in outcomes if isinstance(row, dict)]
    refusals = [row for row in outcomes if isinstance(row, ValidationError)]
    assert len(successes) == 1 and len(refusals) == 1
    assert "has not failed" in str(refusals[0].message)


def test_provider_error_after_post_does_not_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, stitching = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    render.fail_next_submit = ProviderError("router exploded", stage="provider_submission")
    with pytest.raises(ProviderError):
        _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    # Exactly one POST: the failure propagates with no automatic retry,
    # no assembly, no persisted take.
    assert len(render.submits) == 1
    assert stitching.calls == []
    # The failed take does not block an explicit retry, which reuses the
    # same idempotent job row and POSTs once more.
    retry = _generate(service, _project5(), storyboard_shot_ids=["sbs-002"])
    assert retry["status"] == "complete"
    assert len(render.created) == 1
    assert len(render.submits) == 2


def test_prior_counts_split_total_and_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, render, _ = _harness(tmp_path, monkeypatch, costs=[10.0] * 5)
    render.seed_job("scene_001_shot_001", "complete")
    render.seed_job("scene_001_shot_001", "complete")
    render.seed_job("scene_001_shot_001", "failed")
    render.seed_job("scene_001_shot_002", "queued")
    counts = service.count_prior_router_submissions(
        project_id="project_filter_test",
        shot_ids=["scene_001_shot_001", "scene_001_shot_002"],
    )
    assert counts == {
        "scene_001_shot_001": {"total": 3, "failed": 1},
        "scene_001_shot_002": {"total": 1, "failed": 0},
    }
