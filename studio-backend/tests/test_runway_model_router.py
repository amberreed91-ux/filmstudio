from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from app.adapters import RunwayRouterAdapter
from app.models import ProviderConfig, RenderJobInput, RenderJobModel
from app.services.providers.runway_router_provider import (
    DEFAULT_ROUTER_CONFIG_ID,
    build_runway_router_image_request,
    build_runway_router_video_request,
    get_router_config_id,
    submit_runway_router_video_render,
)

ROUTER_DRY_RUN_BODY = {
    "dryRun": True,
    "routing": {
        "model": "gen4.5",
        "provider": "runway",
        "configId": "studio-production-router",
        "estimatedCost": {"credits": 20},
    },
}


def _cfg() -> ProviderConfig:
    return ProviderConfig(
        provider_id="runway_router",
        name="Runway Router",
        enabled=True,
        is_simulated=False,
        api_key="rk_live",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["model_routing", "video_generation", "image_generation"],
    )


def _fake_http(submission=None):
    class Fake:
        def __init__(self):
            self.calls = []

        def __call__(self, url, *, method="GET", payload=None, api_key=None):
            self.calls.append({"url": url, "method": method, "payload": payload, "api_key": api_key})
            if method == "POST":
                return submission or ROUTER_DRY_RUN_BODY
            return {"id": "task-1", "status": "SUCCEEDED", "output": ["https://cdn.test/output.mp4"]}

    return Fake()


def _job(provider: str = "runway_router", **params) -> RenderJobModel:
    from dataclasses import replace

    from app.services.camera_provenance import camera_plan_digest
    from app.services.generation_contract import freeze_generation_contract
    from app.services.scene_coverage_contract import build_scene_coverage_contract
    from app.services.shot_manifest import build_shot_manifest

    project_id = "proj-router-1"
    scene_id = "scene_002"
    shot_id = "scene_002_shot_001"
    prompt = "A slow push-in on Maya at the workshop bench, dawn light, 35mm"
    scene_text = "INT. ROUTER TEST - DAY\nA test subject waits beside a window."
    scene = {"scene_id": scene_id, "heading": "INT. ROUTER TEST - DAY", "text": scene_text, "setting_id": "setting-router-test"}
    project = {"project_id": project_id, "script_text": scene_text, "execution_summary": {"scenes": [], "dialogue_lines": []}}
    references = ["https://cdn.example.com/refs/setting_workshop.png"]
    camera_plan = {"camera": "A slow push-in", "framing": "Medium"}
    camera_params = {
        "camera_plan": camera_plan,
        "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": project_id,
        "camera_source_scene_id": scene_id,
        "camera_source_shot_id": shot_id,
        "camera_target_project_id": project_id,
        "camera_target_scene_id": scene_id,
        "camera_target_shot_id": shot_id,
        **params,
    }
    camera_params["camera_source_digest"] = camera_plan_digest(
        camera_params["camera_plan"], "USER_SPECIFIED", source_project_id=project_id,
        source_scene_id=scene_id, source_shot_id=shot_id,
    )
    from app.services.camera_provenance import canonical_camera_instructions
    camera_params["camera_instructions"] = canonical_camera_instructions(camera_params["camera_plan"], "USER_SPECIFIED")
    reference_binding = [{
        "ref_id": "router-setting", "uri": references[0], "target_type": "setting", "target_id": "setting-router-test",
        "role": "reference", "category": "environment", "canonical": True, "approval_state": "approved",
        "source_kind": "confirmed", "kind": "environment",
    }]
    shot = {
        "shot_id": shot_id, "scene_id": scene_id, "shot_number": 1,
        "covered_content_ids": [], "parameters": camera_params,
        "dialogue_disposition": "INTENTIONAL_SILENCE",
        "dialogue_disposition_reason": "No dialogue in this synthetic router case.",
    }
    requirements = {"setting_id": "setting-router-test", "characters": {}, "reference_binding": reference_binding}
    coverage_probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=[shot], reference_requirements=requirements
    )
    shot["covered_content_ids"] = [row["content_id"] for row in coverage_probe["content_units"]]
    coverage, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=[shot], reference_requirements=requirements
    )
    assert not blockers, blockers
    shot_coverage = coverage["shots"][0]
    contract = freeze_generation_contract(
        shot_id=shot_id, prompt=prompt,
        reference_assets=[{**reference_binding[0], "studio_role": "reference", "source": "canonical_reference_binding"}],
        parameters={"duration": 5, "resolution": "720p", "aspect_ratio": "16:9", **camera_params},
        scene_coverage=coverage, scene_coverage_shot=shot_coverage,
    )
    manifest = build_shot_manifest(
        project_id=project_id, scene_id=scene_id, scene=None, scene_version="test-version",
        storyboard_version="test-version", scene_lineage=coverage,
        entries=[{
            "shot_id": shot_id, "shot_order": 1, "duration_seconds": contract.duration or 0,
            "prompt": contract.prompt, "negative_prompt": contract.negative_prompt, "audio_intent": contract.audio,
            "reference_roles": [ref.studio_role for ref in contract.references],
            "reference_binding": reference_binding, "generation_contract_digest": contract.creative_digest(),
            "aspect_ratio": contract.aspect_ratio, "resolution": contract.resolution, "seed": contract.seed,
            "references": [ref.uri for ref in contract.references], "camera_plan": contract.payload()["camera_plan"],
            "camera_provenance": contract.camera_provenance, "camera_instructions": contract.payload()["camera_instructions"],
            "camera_source_digest": contract.camera_source_digest,
            "camera_source_project_id": contract.camera_source_project_id,
            "camera_source_scene_id": contract.camera_source_scene_id,
            "camera_source_shot_id": contract.camera_source_shot_id,
            "camera_source_storyboard_shot_id": contract.camera_source_storyboard_shot_id,
            "camera_target_project_id": contract.camera_target_project_id,
            "camera_target_scene_id": contract.camera_target_scene_id,
            "camera_target_shot_id": contract.camera_target_shot_id,
            "parameters": {}, "scene_coverage": coverage, "shot_coverage": shot_coverage,
        }],
    )
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest["shots"][0]["generation_contract_digest"] = contract.creative_digest()
    manifest["shots"][0]["scene_coverage"] = coverage
    manifest["shots"][0]["scene_coverage_shot"] = shot_coverage
    contract_record = contract.to_record()
    return RenderJobModel(
        id="job-router-1", project_id=project_id, shot_id=shot_id, provider=provider, status="pending",
        input_payload=RenderJobInput(
            shot_id=shot_id, prompt=prompt, referenceAssets=references,
            parameters={**params, "scene_coverage": coverage, "scene_coverage_shot": shot_coverage, "dialogue_handoff": {}},
        ),
        metadata={
            "creative_generation_contract": contract_record,
            "creative_generation_manifest": manifest,
            "creative_manifest_fingerprint": manifest["manifest_fingerprint"],
            "creative_contract_digest": contract.creative_digest(),
            "creative_generation_identity": {"job_id": "job-router-1", "project_id": project_id, "shot_id": shot_id, "provider": provider},
        },
        created_at="2026-09-28T00:00:00Z", updated_at="2026-09-28T00:00:00Z",
    )


def _approved_contract_record(job: RenderJobModel, *, parameters: dict | None = None) -> None:
    from dataclasses import replace
    from app.services.camera_provenance import camera_plan_digest, canonical_camera_instructions
    from app.services.generation_contract import freeze_generation_contract
    from app.services.shot_manifest import build_shot_manifest

    approved_parameters = dict(parameters if parameters is not None else job.input_payload.parameters)
    plan = {"camera": "A slow push-in", "framing": "Medium"}
    camera = {
        "camera_plan": plan, "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": job.project_id, "camera_source_scene_id": "scene_002",
        "camera_source_shot_id": job.shot_id, "camera_target_project_id": job.project_id,
        "camera_target_scene_id": "scene_002", "camera_target_shot_id": job.shot_id,
    }
    camera["camera_source_digest"] = camera_plan_digest(plan, "USER_SPECIFIED", source_project_id=job.project_id, source_scene_id="scene_002", source_shot_id=job.shot_id)
    camera["camera_instructions"] = canonical_camera_instructions(plan, "USER_SPECIFIED")
    contract = freeze_generation_contract(
        shot_id=job.shot_id, prompt=job.input_payload.prompt, reference_assets=list(job.input_payload.referenceAssets or []),
        parameters={**camera, **approved_parameters}, consistency_payload=job.input_payload.consistency_payload,
    )
    # Existing tests use this helper for corrupt-contract rejections. The
    # original canonical synthetic manifest is retained unless callers opt in.
    manifest = job.metadata.get("creative_generation_manifest")
    if not isinstance(manifest, dict):
        manifest = build_shot_manifest(
            project_id=job.project_id, scene_id="scene_002", scene=None, scene_version="approved-test-version",
            storyboard_version="approved-test-version", entries=[{"shot_id": job.shot_id, "prompt": contract.prompt}],
        )
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    manifest = json.loads(json.dumps(manifest))
    manifest_entry = next(row for row in manifest["shots"] if row.get("shot_id") == job.shot_id)
    manifest_entry.update(camera_plan=contract.payload()["camera_plan"], camera_provenance=contract.camera_provenance,
                          camera_instructions=contract.payload()["camera_instructions"], camera_source_digest=contract.camera_source_digest,
                          camera_source_project_id=contract.camera_source_project_id, camera_source_scene_id=contract.camera_source_scene_id,
                          camera_source_shot_id=contract.camera_source_shot_id, camera_source_storyboard_shot_id=contract.camera_source_storyboard_shot_id,
                          camera_target_project_id=contract.camera_target_project_id, camera_target_scene_id=contract.camera_target_scene_id,
                          camera_target_shot_id=contract.camera_target_shot_id, generation_contract_digest=contract.creative_digest())
    manifest["manifest_fingerprint"] = __import__("app.services.shot_manifest", fromlist=["recompute_manifest_fingerprint"]).recompute_manifest_fingerprint(manifest)
    contract = replace(contract, manifest_fingerprint=manifest["manifest_fingerprint"])
    job.metadata.update({
        "creative_generation_contract": contract.to_record(), "creative_generation_manifest": manifest,
        "creative_manifest_fingerprint": manifest["manifest_fingerprint"], "creative_contract_digest": contract.creative_digest(),
        "creative_generation_identity": {"job_id": job.id, "project_id": job.project_id, "shot_id": job.shot_id, "provider": job.provider},
    })


@pytest.mark.parametrize(
    ("polled_task", "expected_reason"),
    [
        (
            {
                "id": "different-task-2",
                "status": "SUCCEEDED",
                "output": ["https://cdn.test/unrelated.mp4"],
            },
            "runway_task_output_identity_mismatch",
        ),
        (
            {
                "id": "submitted-task-1",
                "status": "SUCCEEDED",
                "output": ["https://cdn.test/task-one.mp4"],
            },
            None,
        ),
    ],
)
def test_router_poll_binds_output_to_submitted_task_id(monkeypatch, polled_task, expected_reason):
    calls = []

    def capture(url, *, method="GET", payload=None, api_key=None):
        calls.append((method, url))
        if method == "POST":
            return {
                "dryRun": False,
                "id": "submitted-task-1",
                "routing": {"model": "gen4.5", "provider": "runway", "configId": get_router_config_id()},
            }
        return polled_task

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("RUNWAY_ROUTER_MAX_POLL_ATTEMPTS", "1")
    monkeypatch.setattr("app.services.providers.runway_router_provider._runway_router_request", capture)

    result = submit_runway_router_video_render(
        "Approved prompt", config_id=get_router_config_id(), _sleep=lambda _: None,
    )

    if expected_reason:
        assert result["status"] == "failed"
        assert result["url"] is None
        assert "does not match the submitted task" in result["error"]
        assert result["meta"]["runway_task_id"] == "submitted-task-1"
    else:
        assert result["status"] == "success"
        assert result["url"] == polled_task["output"][0]
        assert result["meta"]["output_identity"] == {
            "provider_task_id": "submitted-task-1",
            "output_url": "https://cdn.test/task-one.mp4",
            "association_source": "runway_router_polled_task",
        }
    assert calls == [
        ("POST", "https://api.dev.runwayml.com/v1/generate/video"),
        ("GET", "https://api.dev.runwayml.com/v1/tasks/submitted-task-1"),
    ]


def test_video_request_is_model_agnostic_and_schema_shaped():
    body = build_runway_router_video_request("A slow push-in", duration=5, aspect_ratio="16:9")
    assert set(body.keys()) == {"configId", "input"}
    assert "model" not in json.dumps(body)
    assert body["input"]["promptText"] == "A slow push-in"
    assert body["input"]["aspectRatio"] == "16:9"
    assert body["input"]["duration"] == 5
    assert "dryRun" not in body


def test_image_request_is_model_agnostic_and_schema_shaped():
    body = build_runway_router_image_request("A product photo", aspect_ratio="1:1")
    assert set(body.keys()) == {"configId", "input"}
    assert "model" not in json.dumps(body)
    assert body["input"]["aspectRatio"] == "1:1"


def test_dry_run_flag_lands_in_body_for_both_modalities():
    video = build_runway_router_video_request("x", dry_run=True)
    image = build_runway_router_image_request("x", dry_run=True)
    assert video["dryRun"] is True and image["dryRun"] is True


def test_video_request_role_mapping_first_and_reference():
    body = build_runway_router_video_request("x", first_frame_reference="https://cdn.example.com/frame.png", references=["https://cdn.example.com/char.png"])
    refs = body["input"]["referenceImages"]
    assert [ref["role"] for ref in refs] == ["first", "reference"]


def test_config_id_is_studio_production_router(monkeypatch):
    monkeypatch.delenv("RUNWAY_ROUTER_CONFIG_ID", raising=False)
    body = build_runway_router_video_request("x")
    assert body["configId"] == "studio-production-router"
    assert get_router_config_id() == "studio-production-router"
    assert DEFAULT_ROUTER_CONFIG_ID == "studio-production-router"


def test_config_id_is_never_the_router_resource_uuid(monkeypatch):
    monkeypatch.delenv("RUNWAY_ROUTER_CONFIG_ID", raising=False)
    body = build_runway_router_video_request("x")
    assert "138f4c50-3411-4aee-88a9-91dd56b90987" not in json.dumps(body)


def test_config_id_env_override_changes_the_slug(monkeypatch):
    monkeypatch.setenv("RUNWAY_ROUTER_CONFIG_ID", "draft-fast")
    try:
        assert get_router_config_id() == "draft-fast"
        body = build_runway_router_video_request("x")
        assert body["configId"] == "draft-fast"
    finally:
        monkeypatch.delenv("RUNWAY_ROUTER_CONFIG_ID", raising=False)
