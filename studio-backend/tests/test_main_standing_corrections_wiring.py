from __future__ import annotations

from pathlib import Path


def test_main_wires_standing_corrections_into_render_runtime():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert "from app.routes.standing_corrections import router as standing_corrections_router" in source
    assert "app.include_router(standing_corrections_router)" in source
    assert "set_storage(storage)" in source
    assert "set_job_update_callback(notify_job_update)" in source
    assert "from app.services.standing_corrections_service import standing_corrections_service" in source
    assert "standing_corrections_service._storage = storage" in source
    assert "from app.services.render_retry_service import render_retry_service" in source
    assert "render_retry_service.set_storage(storage)" in source
    assert "render_retry_service._keyframe_service = keyframe_extraction_service" in source
    assert "render_retry_service._video_asset_service = video_asset_service" in source
    assert "adherence_service._storage = storage" in source


def test_render_path_injects_and_records_standing_corrections():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "render.py"
    ).read_text(encoding="utf-8")

    assert "build_slotted_prompt" in source
    assert "_sc_svc.inject_into_slots" in source
    assert "reassemble_prompt_from_slots" in source
    assert "job_id=job_id" in source
    assert '"prompt_slots"' in source
    assert '"structured_prompt"' in source
    assert "STRUCTURED_PREVIS_PROMPT_APPLIED" in source
    assert "expected_slots=_expected_slots" in source
    assert "_run_render_quality_check" in source
    assert "render_retry_service.record_render_attempt" in source
    assert "_sc_svc.record_render_outcome" in source
    assert "previous_status = job.status" in source
    assert "submitted_job.status == \"complete\" and previous_status != \"complete\"" in source


def test_render_routes_expose_explicit_adherence_retry_loop():
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "render.py"
    ).read_text(encoding="utf-8")

    assert "@router.post(\"/jobs/{job_id}/adherence-retry\")" in source
    assert "AdherenceRetryRequest" in source
    assert "evaluate_and_select_best" in source
    assert "prompt_slots" in source
