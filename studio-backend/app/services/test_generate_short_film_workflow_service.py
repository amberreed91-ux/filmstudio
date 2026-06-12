from __future__ import annotations

from app.services.generate_short_film_workflow_service import generate_short_film_workflow_service


def test_generate_short_film_workflow_contains_required_stages_and_agents():
    result = generate_short_film_workflow_service.build_workflow(
        project_id="project_test",
        concept="A lonely pianist finds a signal in deep fog.",
        execution_summary={"scenes": [{"scene_id": "scene_001"}], "shot_candidates": [{"shot_id": "shot_001"}]},
        manual_overrides={"tone": "dreamlike"},
    )["short_film_workflow"]

    stage_names = [row["stage"] for row in result["stages"]]
    assert stage_names == [
        "concept",
        "screenplay_outline",
        "scene_generation",
        "shot_sequencing",
        "render_orchestration",
        "audio_generation",
        "film_assembly",
        "final_export",
    ]
    assert result["manual_override"] is True
    assert isinstance(result["crew_updates"], list)
    assert any(row.get("agent") == "Director" for row in result["crew_updates"])
    assert any(row.get("agent") == "Writer" for row in result["crew_updates"])
    assert any(row.get("agent") == "Memory Archivist" for row in result["crew_updates"])
    assert any(row.get("agent") == "Provider Router" for row in result["crew_updates"])
    assert result["runtime_metadata"]["final_status"] == "completed"

