from __future__ import annotations

from pathlib import Path
from typing import Any
import copy

import pytest

from app.models import RenderJobInput, RenderJobModel, RenderJobOutput, SoundtrackConfig
from app.models.consistency import ConsistencyPayload, ReferenceAsset
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.generation_contract import freeze_dialogue_handoff, freeze_generation_contract
from app.services.stability import ValidationError
from conftest import run_async


class FakeRenderService:
    def __init__(self, outputs_dir: Path):
        self.outputs_dir = outputs_dir
        self.created: list[dict[str, Any]] = []
        self.jobs: dict[str, RenderJobModel] = {}
        self.consistency_payload: ConsistencyPayload | None = None

    def create_job(self, **kwargs):
        index = len(self.created) + 1
        job_id = f"job-{index}"
        shot_id = kwargs["shot_id"]
        video = self.outputs_dir / f"{shot_id}.mp4"
        video.write_bytes(b"fake-video")
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
        )
        self.created.append(kwargs)
        self.jobs[job_id] = job
        return job

    async def submit_job(self, job_id: str):
        self.jobs[job_id].status = "complete"
        return self.jobs[job_id]

    async def get_job_status(self, job_id: str):
        return self.jobs[job_id]


class FakeAudioService:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def generate_full_pipeline(self, **kwargs):
        self.calls.append(kwargs)
        video_path = Path(kwargs["video_path"])
        final = video_path.with_name(f"{video_path.stem}_audio.mp4")
        final.write_bytes(b"fake-video-with-audio")
        return {
            "job_id": f"audio-{kwargs['scene_id']}",
            "dialogue_provider": "cosyvoice",
            "score_ambient_provider": kwargs.get("score_ambient_provider") or "none",
            "final_video_path": str(final),
            "final_video_url": f"/outputs/renders/{final.name}",
        }


class FakeStitchingService:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.status = "complete"

    def stitch_scene(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": self.status,
            "clip_count": 2,
            "duration_seconds": 5.5,
            "shot_ids": ["scene_001_shot_001", "scene_001_shot_002"],
            "output_url": f"/outputs/scene_assemblies/{kwargs['project_id']}_{kwargs['scene_id']}.mp4",
            "output_path": f"/tmp/{kwargs['project_id']}_{kwargs['scene_id']}.mp4",
        }


def _project() -> dict[str, Any]:
    return {
        "project_id": "project_test",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "description": "Dre listens before answering.",
                    "text": "INT. OFFICE - DAY\nDRE\nYou heard that too, right?\nDre listens before answering.",
                    "emotional_tone": "restrained concern",
                    "characters": ["Dre"],
                    "setting_id": "set-office",
                    "shots": [
                        {"shot_id": "scene_001_shot_002", "description": "Reverse on Dre."},
                        {"shot_id": "scene_001_shot_001", "description": "Wide two-shot."},
                    ],
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


def _gated_pipeline(tmp_path: Path, *, prepared_mutator=None, **kwargs):
    """Pipeline with readiness checks bypassed but real dialogue proofs intact."""
    from app.services.generation_contract import FrozenGenerationContract, freeze_dialogue_handoff
    from app.services.shot_manifest import build_shot_manifest

    pipeline = SceneProductionPipelineService(backend_root=tmp_path, **kwargs)

    def _noop_prepare(*, project_id, scene_id, project, provider=None, mint_generic_authorization=False):
        scene = pipeline._find_scene(project, scene_id)
        scene["dialogue_disposition"] = "INTENTIONAL_SILENCE"
        scene["dialogue_disposition_reason"] = "The synthetic fixture explicitly holds remaining shots in silence."
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
            from app.services.camera_provenance import (
                CAMERA_PROVENANCE_CREATOR,
                CAMERA_PROVENANCE_UNSPECIFIED,
                camera_plan_digest,
            )
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
                camera_plan,
                camera_provenance,
                source_project_id=project_id,
                source_scene_id=scene_id,
                source_shot_id=shot_id,
            )
            from app.services.camera_provenance import canonical_camera_instructions
            settings["camera_instructions"] = canonical_camera_instructions(camera_plan, camera_provenance)
            frozen = freeze_generation_contract(
                shot_id=shot_id,
                prompt=prompt,
                parameters=settings,
                dialogue_handoff=handoff,
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
            project_id=project_id,
            scene_id=scene_id,
            scene=scene,
            scene_version="test-scene-v1",
            storyboard_version="",
            entries=entries,
        )
        from dataclasses import replace
        for entry in entries:
            entry["manifest_fingerprint"] = manifest["manifest_fingerprint"]
            contract = FrozenGenerationContract.from_record(entry["generation_contract"])
            contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
            entry["generation_contract"] = contract.to_record()
            entry["generation_contract_digest"] = contract.creative_digest()
        from app.services.scene_coverage_contract import build_scene_coverage_contract
        from app.services.camera_provenance import camera_plan_digest

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
        midpoint = max(1, (len(content_units) + 1) // 2)
        shots[0]["covered_content_ids"] = [row["content_id"] for row in content_units[:midpoint]]
        for shot in shots[1:]:
            shot["covered_content_ids"] = [row["content_id"] for row in content_units[midpoint:]]
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
            row["dialogue_id"]: {
                "line_id": row["dialogue_id"],
                "character": row["speaker"],
                "text": row["text"],
                **({"emotional_subtext": next(
                    (
                        line.get("emotional_subtext")
                        for entry in entries
                        for line in entry["dialogue_lines"]
                        if line.get("text") == row["text"]
                    ),
                    "",
                )} if any(line.get("emotional_subtext") for entry in entries for line in entry["dialogue_lines"] if line.get("text") == row["text"]) else {}),
            }
            for row in coverage_probe["dialogue"]
        }
        creator_decisions.extend(
            [
                {
                    "obligation_type": "shot_content",
                    "obligation_id": shot["shot_id"],
                    "status": "UNRESOLVED" if any(row["content_id"] in shot["covered_content_ids"] for row in content_units) else "INTENTIONAL_SILENCE",
                    "shot_id": None,
                    "reason": "" if any(row["content_id"] in shot["covered_content_ids"] for row in content_units) else "Synthetic test fixture leaves this reverse shot without canonical content coverage.",
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
            shot_id = str(shot["shot_id"])
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
        from dataclasses import replace
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
            "canonical_script_sha256": __import__("hashlib").sha256(str(project.get("script_text") or "").encode()).hexdigest(),
            "generation_context_ids": [],
            "cost_estimate": None,
        }
        if prepared_mutator:
            prepared_mutator(batch)
        return batch

    pipeline.prepare_scene_batch = _noop_prepare
    return pipeline


def test_generation_consumes_the_prepared_camera_snapshot_without_rederiving_it(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    render = FakeRenderService(outputs_dir)
    project = _project()
    project["execution_summary"]["scenes"][0]["shots"][1]["parameters"] = {
        "creator_shot_planning": {"camera": "Locked-off", "framing": "Wide"}
    }
    service = _gated_pipeline(
        tmp_path,
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
    )

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=project,
    ))

    created = next(row for row in render.created if row["shot_id"] == "scene_001_shot_001")
    manifest_entry = next(
        row for row in result["shot_manifest"]["shots"] if row["shot_id"] == "scene_001_shot_001"
    )
    contract = created["prepared_generation_contract"]["payload"]
    parameters = created["parameters"]
    assert manifest_entry["camera_plan"] == parameters["camera_plan"] == contract["camera_plan"] == {
        "camera": "Locked-off", "framing": "Wide"
    }
    assert manifest_entry["camera_provenance"] == parameters["camera_provenance"] == contract["camera_provenance"] == "USER_SPECIFIED"
    assert manifest_entry["camera_instructions"] == parameters["camera_instructions"] == contract["camera_instructions"]
    assert {row["dimension"]: row["value"] for row in contract["camera_instructions"] if row["value"]} == contract["camera_plan"]


def test_scene_pipeline_renders_shots_in_order_adds_audio_and_stitches(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    render = FakeRenderService(outputs_dir)
    audio = FakeAudioService()
    stitch = FakeStitchingService()
    service = _gated_pipeline(tmp_path, render_svc=render, audio_svc=audio, stitching_svc=stitch)
    saved_projects: list[dict[str, Any]] = []

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        save_project=lambda updated: saved_projects.append(updated) or updated,
    ))

    assert result["status"] == "complete"
    assert [call["shot_id"] for call in render.created] == ["scene_001_shot_001", "scene_001_shot_002"]
    assert [call["scene_id"] for call in audio.calls] == ["scene_001_shot_001", "scene_001_shot_002"]
    assert audio.calls[0]["dialogue_lines"][0]["emotional_subtext"] == "casual concern"
    assert audio.calls[1]["dialogue_lines"] == []
    assert audio.calls[0]["dialogue_handoff"]["payload"]["shot_id"] == "scene_001_shot_001"
    assert audio.calls[1]["dialogue_handoff"]["payload"]["silence"] is True
    assert render.created[0]["dialogue_handoff"] == audio.calls[0]["dialogue_handoff"]
    manifest_shot = next(row for row in result["shot_manifest"]["shots"] if row["shot_id"] == "scene_001_shot_001")
    assert manifest_shot["dialogue_handoff"] == render.created[0]["dialogue_handoff"]
    assert audio.calls[0]["score_ambient_provider"] == "none"
    render_rows = saved_projects[0]["execution_summary"]["one_button_render_jobs"]
    assert [row["output_url"] for row in render_rows] == [
        "/outputs/renders/scene_001_shot_001_audio.mp4",
        "/outputs/renders/scene_001_shot_002_audio.mp4",
    ]
    assert stitch.calls[0]["project"]["execution_summary"]["one_button_render_jobs"] == render_rows
    assemblies = saved_projects[0]["execution_summary"]["scene_pipeline_assemblies"]
    assert len(assemblies) == 1
    assert assemblies[0]["scene_id"] == "scene_001"
    assert assemblies[0]["status"] == "complete"
    assert assemblies[0]["output_url"] == "/outputs/scene_assemblies/project_test_scene_001.mp4"
    assert assemblies[0]["duration_seconds"] == 5.5
    assert assemblies[0]["score_ambient_provider"] == "none"
    assert result["assembly"] == assemblies[0]


def test_audio_rejects_lines_that_do_not_match_frozen_dialogue_before_job_creation(tmp_path: Path):
    from app.services.audio_pipeline_service import AudioPipelineService

    handoff = freeze_dialogue_handoff(
        scene_id="scene_001",
        shot_id="scene_001_shot_001",
        lines=[{"character": "Dre", "text": "Approved line."}],
    )
    audio = AudioPipelineService()
    with pytest.raises(ValueError, match="do not match"):
        run_async(audio.generate_full_pipeline(
            scene_id="scene_001_shot_001",
            project_id="project_test",
            dialogue_lines=[],
            dialogue_handoff=handoff,
            dialogue_scene_id="scene_001",
            dialogue_shot_id="scene_001_shot_001",
        ))
    assert audio._jobs == {}


@pytest.mark.parametrize("invalid_case", ["missing", "stale_scene", "malformed", "digest", "shot", "placeholder", "tampered"])
def test_narrative_audio_rejects_invalid_handoffs_before_jobs_or_provider(
    tmp_path: Path,
    monkeypatch,
    invalid_case: str,
):
    import hashlib
    import json

    from app.services import audio_pipeline_service as audio_module
    from app.services.audio_pipeline_service import AudioPipelineService

    service = AudioPipelineService()
    service.output_base = tmp_path / "audio"
    provider_calls: list[str] = []

    async def unexpected_provider(*args, **kwargs):
        provider_calls.append("dialogue")
        raise AssertionError("invalid handoffs must be rejected before provider submission")

    monkeypatch.setattr(service, "generate_dialogue", unexpected_provider)
    monkeypatch.setattr(audio_module, "MOCK_MODE", False)

    handoff = None
    if invalid_case == "stale_scene":
        handoff = freeze_dialogue_handoff(
            scene_id="scene_999", shot_id="scene_001_shot_001", lines=[]
        )
    elif invalid_case == "shot":
        handoff = freeze_dialogue_handoff(
            scene_id="scene_001", shot_id="scene_001_shot_002", lines=[]
        )
    elif invalid_case == "digest":
        handoff = freeze_dialogue_handoff(
            scene_id="scene_001", shot_id="scene_001_shot_001", lines=[]
        )
        handoff["payload"]["silence"] = False
    elif invalid_case == "malformed":
        handoff = {"payload": {}, "sha256": "bad"}
    elif invalid_case == "tampered":
        handoff = freeze_dialogue_handoff(
            scene_id="scene_001", shot_id="scene_001_shot_001", lines=[]
        )
        handoff["sha256"] = "0" * 64
    elif invalid_case == "placeholder":
        handoff = freeze_dialogue_handoff(
            scene_id="scene_001", shot_id="scene_001_shot_001", lines=[]
        )
        handoff["payload"]["lines"] = [
            {"character": "Dre", "text": "DRE carries the beat with restrained subtext."}
        ]
        handoff["payload"]["silence"] = False
        canonical = json.dumps(handoff["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        handoff["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(ValueError):
        run_async(service.generate_full_pipeline(
            scene_id="scene_001_shot_001",
            project_id="project_test",
            scene_text="DRE\\nCanonical words." if invalid_case == "missing" else "",
            dialogue_lines=None if handoff is None else handoff.get("payload", {}).get("lines", []),
            dialogue_handoff=handoff,
            narrative_audio=True,
            dialogue_scene_id="scene_001",
            dialogue_shot_id="scene_001_shot_001",
            score_ambient_provider="none",
        ))

    assert service._jobs == {}
    assert provider_calls == []


def test_explicit_silence_handoff_is_valid_and_skips_dialogue_provider(tmp_path: Path, monkeypatch):
    from app.services import audio_pipeline_service as audio_module
    from app.services.audio_pipeline_service import AudioPipelineService, TrackStatus

    service = AudioPipelineService()
    service.output_base = tmp_path / "audio"
    monkeypatch.setattr(audio_module, "MOCK_MODE", False)
    provider_calls: list[str] = []

    def unexpected_tts(*args, **kwargs):
        provider_calls.append("tts")
        raise AssertionError("explicit silence must not submit dialogue to a provider")

    async def mix(project_id, scene_id, dialogue_path, score_path=None, ambient_path=None):
        assert dialogue_path.exists()
        return {"track": "mixed", "status": TrackStatus.COMPLETE, "file_path": str(dialogue_path)}

    monkeypatch.setattr(service, "_generate_dialogue_tts_sync", unexpected_tts)
    monkeypatch.setattr(service, "mix_audio_tracks", mix)
    handoff = freeze_dialogue_handoff(scene_id="scene_001", shot_id="scene_001_shot_001", lines=[])

    result = run_async(service.generate_full_pipeline(
        scene_id="scene_001_shot_001",
        project_id="project_test",
        scene_text="DRE\\nThis text must not be re-extracted.",
        dialogue_lines=[],
        dialogue_handoff=handoff,
        narrative_audio=True,
        dialogue_scene_id="scene_001",
        dialogue_shot_id="scene_001_shot_001",
        score_ambient_provider="none",
    ))

    assert result["status"] == "complete"
    assert result["steps"]["dialogue"]["status"] == TrackStatus.SKIPPED
    assert provider_calls == []


def test_non_narrative_audio_pipeline_still_accepts_empty_dialogue(tmp_path: Path, monkeypatch):
    from app.services import audio_pipeline_service as audio_module
    from app.services.audio_pipeline_service import AudioPipelineService, TrackStatus

    service = AudioPipelineService()
    service.output_base = tmp_path / "audio"
    monkeypatch.setattr(audio_module, "MOCK_MODE", False)
    provider_calls: list[str] = []

    def unexpected_tts(*args, **kwargs):
        provider_calls.append("tts")
        raise AssertionError("non-narrative audio must not invoke dialogue TTS")

    async def mix(project_id, scene_id, dialogue_path, score_path=None, ambient_path=None):
        return {"track": "mixed", "status": TrackStatus.COMPLETE, "file_path": str(dialogue_path)}

    monkeypatch.setattr(service, "_generate_dialogue_tts_sync", unexpected_tts)
    monkeypatch.setattr(service, "mix_audio_tracks", mix)

    result = run_async(service.generate_full_pipeline(
        scene_id="scene_001",
        project_id="project_test",
        score_ambient_provider="none",
    ))

    assert result["status"] == "complete"
    assert provider_calls == []


def test_dialogue_manifest_and_contract_digest_cover_handoff(tmp_path: Path):
    from app.services.generation_contract import FrozenGenerationContract, freeze_generation_contract
    from app.services.shot_manifest import build_shot_manifest, recompute_manifest_fingerprint

    handoff = freeze_dialogue_handoff(
        scene_id="scene_001",
        shot_id="scene_001_shot_001",
        lines=[{"character": "Dre", "text": "You heard that too, right?"}],
    )
    contract = freeze_generation_contract(
        shot_id="scene_001_shot_001",
        prompt="Approved shot",
        parameters={"dialogue_lines": handoff["payload"]["lines"]},
        dialogue_handoff=handoff,
    )
    manifest = build_shot_manifest(
        project_id="project_test",
        scene_id="scene_001",
        scene=None,
        scene_version="v1",
        storyboard_version="",
        entries=[{
            "shot_id": "scene_001_shot_001",
            "shot_order": 1,
            "prompt": "Approved shot",
            "dialogue_handoff": handoff,
            "generation_contract_digest": contract.creative_digest(),
        }],
    )

    assert FrozenGenerationContract.from_record(contract.to_record()).payload()["dialogue_handoff"] == handoff
    assert manifest["shots"][0]["dialogue_handoff"] == handoff
    assert recompute_manifest_fingerprint(manifest) == manifest["manifest_fingerprint"]
    manifest["shots"][0]["dialogue_handoff"]["payload"]["lines"][0]["text"] = "mutated"
    assert recompute_manifest_fingerprint(manifest) != manifest["manifest_fingerprint"]


def test_invalid_prepared_dialogue_blocks_render_and_audio(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    render = FakeRenderService(outputs_dir)
    audio = FakeAudioService()

    def mutate(batch):
        batch["entries"][0]["dialogue_handoff"]["payload"]["lines"][0]["text"] = "tampered"

    service = _gated_pipeline(
        tmp_path,
        render_svc=render,
        audio_svc=audio,
        stitching_svc=FakeStitchingService(),
        prepared_mutator=mutate,
    )
    try:
        run_async(service.generate_scene(project_id="project_test", scene_id="scene_001", project=_project()))
    except ValidationError as exc:
        assert exc.stage == "generation_dialogue_integrity"
    else:
        raise AssertionError("tampered dialogue should fail before render submission")
    assert render.created == []
    assert audio.calls == []


def test_preflight_emits_one_isolated_entry_per_approved_storyboard_shot(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    project_id = "project_scene002_multishot"
    scene_id = "scene_002"
    shot_ids = [f"{scene_id}_shot_{index:03d}" for index in range(1, 6)]
    scene = {
        "scene_id": scene_id,
        "heading": "INT. TEST LOCATION - NIGHT",
        "text": "Canonical test scene body.",
        "characters": [],
        "setting_id": "",
    }
    project = {
        "project_id": project_id,
        "script_text": "INT. TEST LOCATION - NIGHT\nCanonical test scene body.",
        "execution_summary": {"scenes": [scene]},
    }
    board_shots = []
    for index, shot_id in enumerate(shot_ids, start=1):
        camera_plan = {"framing": f"framing-{index}", "camera": f"move-{index}"}
        parameters = {
            "duration": 5,
            "ratio": "16:9",
            "negative_prompt": f"negative-{index}",
            "storyboard": {
                "version_id": "approved-test-version",
                "storyboard_shot_id": f"board-shot-{index}",
            },
        }
        shot = SimpleNamespace(
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            shot_number=index,
            storyboard_shot_id=f"board-shot-{index}",
            version_id="approved-test-version",
            status="approved",
            updated_at=f"2026-10-01T00:00:0{index}+00:00",
            prompt=f"originating-prompt-{index}",
            duration_seconds=5,
            parameters=parameters,
            camera_plan=camera_plan,
            render_contract=SimpleNamespace(
                provider_neutral_prompt=f"originating-prompt-{index}",
                structured_parameters={"camera_plan": camera_plan},
                duration_seconds=5,
                aspect_ratio="16:9",
            ),
            metadata={},
        )
        board_shots.append(shot)

    monkeypatch.setattr(
        "app.services.storyboard_blueprint_service.storyboard_blueprint_service.scene_render_inputs",
        lambda _project_id, _scene_id: board_shots,
    )

    service = SceneProductionPipelineService(backend_root=tmp_path)
    processed_shots = []

    def _resolve_requirements(**kwargs):
        # This isolated fixture deliberately has no canonical cast or setting;
        # the test concerns entry fan-out, not reference selection.
        return {"scene_id": scene_id, "character_ids": [], "characters": {}, "setting_id": "", "setting_urls": [], "setting_references": [], "allowed_urls": []}

    from app.services.scene_coverage_contract import build_scene_coverage_contract

    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id,
        project=project,
        scene=scene,
        shots=[{"shot_id": shot_id, "scene_id": scene_id, "parameters": {}} for shot_id in shot_ids],
        reference_requirements={"setting_id": "", "characters": {}, "reference_binding": []},
    )
    creator_decisions = [
        {
            "obligation_type": "content",
            "obligation_id": row["content_id"],
            "status": "ASSIGNED",
            "shot_id": shot_ids[0],
            "reason": "Synthetic test fixture assigns its canonical scene action.",
        }
        for row in probe["content_units"]
    ]
    creator_decisions.extend(
        {
            "obligation_type": "shot_content",
            "obligation_id": shot_id,
            "status": "UNRESOLVED",
            "shot_id": None,
            "reason": "",
        }
        for shot_id in shot_ids
    )
    creator_decisions.extend(
        {
            "obligation_type": "shot_dialogue",
            "obligation_id": shot_id,
            "status": "INTENTIONAL_SILENCE",
            "shot_id": None,
            "reason": "This synthetic shot contains no spoken dialogue.",
        }
        for shot_id in shot_ids
    )
    board_shots[0].parameters["creator_coverage_decisions"] = creator_decisions

    monkeypatch.setattr(
        "app.services.reference_validation.resolve_scene_reference_requirements",
        _resolve_requirements,
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.validate_generation_context",
        lambda **kwargs: SimpleNamespace(blockers=[]),
    )
    def _create_context(**kwargs):
        processed_shots.append(kwargs["shot_id"])
        return SimpleNamespace(
            generation_context_id=f"ctx-{kwargs['shot_id']}",
            scene_version="scene-version",
            shot_version=f"version-{kwargs['shot_id']}",
            reference_version="none",
            to_dict=lambda: {"shot_id": kwargs["shot_id"]},
        )

    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.create_generation_context",
        _create_context,
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.reference_version",
        lambda **kwargs: "none",
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.enforce_shot_limit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.estimate_batch",
        lambda *, provider, shots: {"provider": provider, "per_shot": [], "estimated": False},
    )
    from app.services.storyboard_blueprint_service import storyboard_blueprint_service
    from app.services.storyboard_image_prompt_service import storyboard_image_prompt_service

    board_shots_by_id = {shot.storyboard_shot_id: shot for shot in board_shots}
    monkeypatch.setattr(
        storyboard_blueprint_service.storage,
        "get_storyboard_shot",
        lambda storyboard_shot_id: board_shots_by_id.get(storyboard_shot_id),
    )
    # Prompt authority: provider-bound text is the approved image prompt.
    # These synthetic board shots carry approved prompts without image rows.
    # D6: the send-time authority is the central gate; stub it here.
    approved_texts = {
        f"board-shot-{index}": f"approved-image-prompt-{index}" for index in range(1, 6)
    }
    monkeypatch.setattr(
        storyboard_image_prompt_service,
        "resolve_provider_send_text",
        lambda shot: approved_texts[shot.storyboard_shot_id],
    )
    batch = service.prepare_scene_batch(
        project_id=project_id,
        scene_id=scene_id,
        project=project,
        provider="simulated",
    )

    entries = batch["entries"]
    assert len(processed_shots) == 5
    assert len(entries) == len(processed_shots)
    assert [entry["shot_id"] for entry in entries] == shot_ids
    assert len({entry["shot_id"] for entry in entries}) == len(shot_ids)
    assert [entry["prompt"] for entry in entries] == [
        f"approved-image-prompt-{index}" for index in range(1, 6)
    ]
    assert [entry["image_prompt_ready"] for entry in entries] == [True] * 5
    # The board text never reaches provider-bound fields, and the shot
    # version binds the sendable image prompt (not the board version alone).
    assert [entry["shot_version"] for entry in entries] != [
        f"version-{shot_id}" for shot_id in shot_ids
    ]
    assert [entry["camera_plan"] for entry in entries] == [
        {"framing": f"framing-{index}", "camera": f"move-{index}"}
        for index in range(1, 6)
    ]
    assert [entry["camera_provenance"] for entry in entries] == ["APPROVED"] * 5
    assert [entry["camera_source_shot_id"] for entry in entries] == shot_ids
    assert [entry["parameters"]["negative_prompt"] for entry in entries] == [
        f"negative-{index}" for index in range(1, 6)
    ]
    assert [entry["generation_context"]["shot_id"] for entry in entries] == shot_ids
    assert [entry["duration_seconds"] for entry in entries] == [5.0] * 5
    assert [entry["aspect_ratio"] for entry in entries] == ["16:9"] * 5
    assert all(
        not any("canonical scene content unresolved" in blocker for blocker in entry["blockers"])
        for entry in entries
    )
    assert batch["manifest"]["batch"]["shot_count"] == 5
    assert [shot["shot_id"] for shot in batch["manifest"]["shots"]] == shot_ids
    assert [shot["shot_prompt"] for shot in batch["manifest"]["shots"]] == [
        f"approved-image-prompt-{index}" for index in range(1, 6)
    ]
    assert [shot["camera_plan"] for shot in batch["manifest"]["shots"]] == [
        entry["camera_plan"] for entry in entries
    ]


def test_reference_resolution_failure_blocks_preflight_without_authorization_or_submission(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    project = _project()
    project["script_text"] = project["execution_summary"]["scenes"][0]["text"]
    scene = project["execution_summary"]["scenes"][0]
    render = FakeRenderService(tmp_path / "outputs" / "renders")
    service = SceneProductionPipelineService(render_svc=render, backend_root=tmp_path)
    service._resolve_shot_source = lambda _project, _scene, **_kwargs: (copy.deepcopy(scene["shots"]), "scene_shots", "shots")

    class NoLiveStorage:
        pass

    monkeypatch.setattr("app.data.storage.get_storage", lambda _kind: NoLiveStorage())

    def fail_reference_resolution(**_kwargs):
        raise RuntimeError("isolated reference resolution failure")

    monkeypatch.setattr(
        "app.services.reference_validation.resolve_scene_reference_requirements",
        fail_reference_resolution,
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.create_generation_context",
        lambda *, shot_id, **_kwargs: SimpleNamespace(
            generation_context_id=f"ctx-{shot_id}", scene_version="scene-v1",
            shot_version=f"shot-v1-{shot_id}", reference_version="none",
            to_dict=lambda: {"shot_id": shot_id},
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.validate_generation_context",
        lambda **_kwargs: SimpleNamespace(blockers=[]),
    )
    monkeypatch.setattr(
        "app.services.generation_context_service.generation_context_service.reference_version",
        lambda **_kwargs: "none",
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.enforce_shot_limit",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.generation_cost_gate.generation_cost_gate.estimate_batch",
        lambda *, provider, shots: {"provider": provider, "per_shot": [], "estimated": False},
    )

    batch = service.prepare_scene_batch(
        project_id="project_test", scene_id="scene_001", project=project, provider="simulated",
    )

    assert batch["ready"] is False
    assert any("reference gate: isolated reference resolution failure" in blocker for blocker in batch["blockers"])
    assert batch["entries"]
    assert all(entry["reference_projection_authorization"] is None for entry in batch["entries"])
    assert render.created == []
    assert service._prepared_scene_batches == {}


def test_fabricated_dialogue_is_filtered_before_prepared_handoff(tmp_path: Path):
    project = _project()
    project["execution_summary"]["dialogue_lines"].append({
        "scene_id": "scene_001",
        "shot_id": "scene_001_shot_001",
        "character": "Dre",
        "text": "DRE carries the beat with restrained subtext.",
    })
    service = SceneProductionPipelineService(backend_root=tmp_path)
    lines = service._dialogue_lines_for_shot(
        project, "scene_001", "scene_001_shot_001"
    )
    handoff = freeze_dialogue_handoff(
        scene_id="scene_001", shot_id="scene_001_shot_001", lines=lines or []
    )

    assert [row["text"] for row in lines or []] == ["You heard that too, right?"]
    assert handoff["payload"]["lines"] == lines


def test_stale_structured_dialogue_blocks_preflight(tmp_path: Path):
    project = _project()
    project["execution_summary"]["scenes"][0]["shots"][0]["parameters"] = {
        "dialogue_lines": [{
            "scene_id": "scene_001",
            "shot_id": "scene_999_shot_001",
            "character": "Dre",
            "text": "Stale dialogue.",
        }]
    }
    service = SceneProductionPipelineService(backend_root=tmp_path)

    batch = service.prepare_scene_batch(project_id="project_test", scene_id="scene_001", project=project)

    assert batch["ready"] is False
    assert any("dialogue handoff" in blocker for blocker in batch["blockers"])
    assert service._prepared_scene_batches == {}


def test_scene_pipeline_accepts_stitcher_completed_status(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    stitch = FakeStitchingService()
    stitch.status = "completed"
    service = _gated_pipeline(tmp_path, render_svc=FakeRenderService(outputs_dir), audio_svc=FakeAudioService(), stitching_svc=stitch)

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
    ))

    assert result["status"] == "complete"


def test_scene_pipeline_resolves_all_auto_split_candidates_in_numeric_order(tmp_path: Path):
    service = SceneProductionPipelineService(backend_root=tmp_path)
    scene = {"scene_id": "scene_002", "description": "Maya faces Dre."}
    project = {
        "execution_summary": {
            "shot_candidates": [
                {"shot_id": "shot_scene_002_003", "scene_id": "scene_002"},
                {"shot_id": "shot_scene_003_001", "scene_id": "scene_003"},
                {"shot_id": "shot_scene_002_001", "scene_id": "scene_002"},
                {"shot_id": "shot_scene_002_002", "scene_id": "scene_002"},
            ]
        }
    }

    shots = service._resolve_ordered_shots(project, scene)

    assert [shot["shot_id"] for shot in shots] == [
        "shot_scene_002_001",
        "shot_scene_002_002",
        "shot_scene_002_003",
    ]


def test_scene_pipeline_excludes_legacy_multi_shot_ledger(tmp_path: Path):
    """P0 (H-5): the mock-era multi_shot_execution_ledger is NOT a generation
    fallback. It holds placeholder renders and synthetic shot intents; ordering
    it into a render would resurrect hallucinated shots. Without storyboard or
    scene shots, the pipeline falls through to the explicit single-shot
    fallback instead of the ledger."""
    service = SceneProductionPipelineService(backend_root=tmp_path)
    scene = {
        "scene_id": "scene_002",
        "description": "Maya faces Dre.",
        "multi_shot_execution_ledger": [
            {"shot_id": "shot_002", "prompt_pack": {"base_prompt": "Reverse on Maya."}},
            {"shot_id": "shot_001", "prompt_pack": {"base_prompt": "Wide on both."}},
        ],
    }

    shots = service._resolve_ordered_shots({"execution_summary": {}}, scene)

    assert [shot["shot_id"] for shot in shots] == ["scene_002_shot_001"]
    assert not any("prompt_pack" in shot for shot in shots)


def test_scene_pipeline_persists_reference_lock_evidence(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    render = FakeRenderService(outputs_dir)
    render.consistency_payload = ConsistencyPayload(
        project_id="project_test",
        mode="identity_lock",
        refs=[
            ReferenceAsset(
                ref_id="dre-full",
                kind="character_full",
                image_url="/outputs/refs/dre-full.png",
                project_id="project_test",
            ),
            ReferenceAsset(
                ref_id="dre-face",
                kind="character_face",
                image_url="/outputs/refs/dre-face.png",
                project_id="project_test",
            ),
        ],
        weights={"dre-full": 1.0, "dre-face": 0.55},
    )
    service = _gated_pipeline(tmp_path, render_svc=render, audio_svc=FakeAudioService(), stitching_svc=FakeStitchingService())
    saved_projects: list[dict[str, Any]] = []

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        save_project=lambda updated: saved_projects.append(updated) or updated,
    ))

    first_consistency = result["shots"][0]["consistency"]
    assert first_consistency == {
        "mode": "identity_lock",
        "attached": True,
        "reference_count": 2,
        "reference_kinds": ["character_full", "character_face"],
        "primary_reference_url": "/outputs/refs/dre-full.png",
    }
    render_rows = saved_projects[0]["execution_summary"]["one_button_render_jobs"]
    assert render_rows[0]["consistency"] == first_consistency


def test_scene_pipeline_reports_manual_post_render_soundtrack(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    service = _gated_pipeline(tmp_path, render_svc=FakeRenderService(outputs_dir), audio_svc=FakeAudioService(), stitching_svc=FakeStitchingService())

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        score_ambient_provider="manual_post_render",
        soundtrack_config=SoundtrackConfig(
            enabled=True,
            audio_source_type="local_file",
            local_audio_path=str(tmp_path / "score.wav"),
        ),
    ))

    assert result["score_ambient_provider"] == "manual_post_render"
    assert result["soundtrack_status"] == "manual_post_render"


def test_scene_pipeline_manual_post_render_skips_per_shot_score_generation(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    audio = FakeAudioService()
    service = _gated_pipeline(tmp_path, render_svc=FakeRenderService(outputs_dir), audio_svc=audio, stitching_svc=FakeStitchingService())

    run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
        score_ambient_provider="manual",
        soundtrack_config=SoundtrackConfig(
            enabled=True,
            audio_source_type="local_file",
            local_audio_path=str(tmp_path / "score.wav"),
        ),
    ))

    assert {call["score_ambient_provider"] for call in audio.calls} == {"none"}


def test_scene_pipeline_manual_post_render_requires_soundtrack_source(tmp_path: Path):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True)
    service = _gated_pipeline(tmp_path, render_svc=FakeRenderService(outputs_dir), audio_svc=FakeAudioService(), stitching_svc=FakeStitchingService())

    try:
        run_async(service.generate_scene(
            project_id="project_test",
            scene_id="scene_001",
            project=_project(),
            score_ambient_provider="manual_post_render",
            soundtrack_config=SoundtrackConfig(enabled=True, audio_source_type="local_file"),
        ))
    except ValidationError as exc:
        assert exc.error_type == "validation_error"
        assert exc.stage == "scene_soundtrack"
    else:
        raise AssertionError("manual_post_render without source should fail")
