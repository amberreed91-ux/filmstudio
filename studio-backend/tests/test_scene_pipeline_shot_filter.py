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

import copy
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.services.generation_contract import (
    FrozenGenerationContract,
    freeze_dialogue_handoff,
    freeze_generation_contract,
)
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.shot_manifest import build_shot_manifest
from app.services.stability import ValidationError
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
    """FakeRenderService that also counts submit_job calls (submit POSTs)."""

    def __init__(self, outputs_dir: Path):
        super().__init__(outputs_dir)
        self.submits: list[str] = []

    async def submit_job(self, job_id: str):
        self.submits.append(job_id)
        return await super().submit_job(job_id)


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
