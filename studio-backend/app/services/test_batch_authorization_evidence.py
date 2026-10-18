"""Durable batch-authorization evidence on created jobs (R4.3).

Proves the authorization-decision -> job link is durable per job: every job
created by the canonical batch path carries a compact ``batch_authorization``
stamp (preflight verdict, policy version, digest status, batch position,
shared manifest fingerprint + snapshot id, confirmation-enforcement flag)
alongside any existing reference-projection authorization. Uses the shared
gated-pipeline fakes; no providers, no renders.
"""

from __future__ import annotations

from pathlib import Path

from app.services.scene_production_pipeline_service import (
    SceneProductionPipelineService,
)
from app.services.test_scene_production_pipeline_service import (
    FakeAudioService,
    FakeRenderService,
    FakeStitchingService,
    _gated_pipeline,
    _project,
)
from conftest import run_async


def _pipeline(tmp_path: Path, **kwargs):
    outputs_dir = tmp_path / "outputs" / "renders"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    render = FakeRenderService(outputs_dir)
    service = _gated_pipeline(
        tmp_path,
        render_svc=render,
        audio_svc=FakeAudioService(),
        stitching_svc=FakeStitchingService(),
        **kwargs,
    )
    return service, render


def _stamps(render: FakeRenderService) -> list[dict]:
    assert render.created, "expected the batch to create jobs"
    return [kwargs["metadata"]["batch_authorization"] for kwargs in render.created]


# ── Stamp presence, correctness, and batch enumerability ────────────────────

def test_created_jobs_carry_batch_authorization_stamp(tmp_path):
    service, render = _pipeline(tmp_path)

    result = run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
    ))

    assert result["status"] == "complete"
    stamps = _stamps(render)
    assert len(stamps) == len(result["shots"]) == 2
    for stamp in stamps:
        assert stamp["preflight"] == "batch_authorization_preflight"
        assert stamp["project_id"] == "project_test"
        assert stamp["scene_id"] == "scene_001"
        assert stamp["shot_verdict"] == "authorized"
        assert stamp["confirmation_enforced"] is False
        assert stamp["manifest_fingerprint"] == result["shot_manifest"]["manifest_fingerprint"]
        assert stamp["digest"] == "skipped_no_expectations"


def test_stamp_batch_positions_enumerate_the_batch(tmp_path):
    service, render = _pipeline(tmp_path)

    run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
    ))

    stamps = _stamps(render)
    assert sorted(stamp["batch_shot_index"] for stamp in stamps) == [1, 2]
    assert {stamp["batch_shot_count"] for stamp in stamps} == {2}
    # One shared fingerprint + snapshot id across every job: the batch is
    # enumerable from any single job's stamp, including after a partial
    # execution failure drops the in-memory batch record.
    assert len({stamp["manifest_fingerprint"] for stamp in stamps}) == 1
    assert len({stamp["prepared_snapshot_id"] for stamp in stamps}) == 1
    created_shots = [kwargs["shot_id"] for kwargs in render.created]
    by_index = sorted(zip([s["batch_shot_index"] for s in stamps], created_shots))
    assert [shot for _, shot in by_index] == sorted(created_shots)


def test_stamp_preserves_reference_projection_authorization(tmp_path):
    proof = {"frozen_reference_binding_sha256": "sha-test-proof"}

    def _mutator(batch):
        for entry in batch["entries"]:
            entry["reference_projection_authorization"] = dict(proof)

    service, render = _pipeline(tmp_path, prepared_mutator=_mutator)

    run_async(service.generate_scene(
        project_id="project_test",
        scene_id="scene_001",
        project=_project(),
    ))

    for kwargs in render.created:
        assert kwargs["metadata"]["reference_projection_authorization"] == proof
        assert kwargs["metadata"]["batch_authorization"]["shot_verdict"] == "authorized"


# ── Helper-level: enforcement flag and fail-honest verdicts ────────────────

def test_helper_records_confirmation_enforcement_and_unmapped_verdict():
    stamped = SceneProductionPipelineService._batch_authorized_job_metadata(
        prepared_entry={},
        shot_verdict={"ok": True, "policy_version": "v2", "digest": "verified"},
        project_id="project_test",
        scene_id="scene_001",
        manifest_fingerprint="fp-test",
        prepared_snapshot_id="snap-test",
        batch_shot_index=1,
        batch_shot_count=1,
        confirmation_enforced=True,
    )
    assert stamped["batch_authorization"]["confirmation_enforced"] is True
    assert stamped["batch_authorization"]["policy_version"] == "v2"
    assert stamped["batch_authorization"]["digest"] == "verified"

    unmapped = SceneProductionPipelineService._batch_authorized_job_metadata(
        prepared_entry={},
        shot_verdict={},
        project_id="project_test",
        scene_id="scene_001",
        manifest_fingerprint="fp-test",
        prepared_snapshot_id="",
        batch_shot_index=1,
        batch_shot_count=1,
        confirmation_enforced=False,
    )
    # A job whose shot has no preflight row must never claim authorization.
    assert unmapped["batch_authorization"]["shot_verdict"] == "unmapped"


def test_helper_does_not_mutate_inputs():
    entry = {"reference_projection_authorization": {"proof": "keep"}}
    verdict = {"ok": True, "policy_version": None, "digest": "not_required"}
    SceneProductionPipelineService._batch_authorized_job_metadata(
        prepared_entry=entry,
        shot_verdict=verdict,
        project_id="project_test",
        scene_id="scene_001",
        manifest_fingerprint="fp-test",
        prepared_snapshot_id="",
        batch_shot_index=2,
        batch_shot_count=2,
        confirmation_enforced=False,
    )
    assert entry == {"reference_projection_authorization": {"proof": "keep"}}
    assert verdict == {"ok": True, "policy_version": None, "digest": "not_required"}
