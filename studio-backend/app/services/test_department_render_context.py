from __future__ import annotations

from app.data.storage import DatabaseStorage
from app.services import department_render_context_service as dept_module
from app.services import render as render_module
from app.services.render import RenderService


class _FakeProjectStore:
    def get_project(self, project_id: str):
        return {
            "project_id": project_id,
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "heading": "INT. KITCHEN - NIGHT",
                        "location": "old kitchen",
                        "time_of_day": "night",
                        "emotional_tone": "contained dread",
                        "text": "Maya pauses at the sink and listens to the room.",
                        "characters": ["Maya"],
                    }
                ]
            },
        }


class _FakeDepartmentContext:
    def build_slot_guidance(self, **_kwargs):
        return {
            "slot_guidance": {
                "character_state": "Casting: Maya requires stillness under pressure.",
                "environment_persistence": "Designer: cracked tile and blue enamel mug stay visible.",
                "camera": "Cinematographer: low patient push-in.",
                "lighting": "Colorist: cool shadows with warm practical edge.",
            },
            "metadata": {
                "sources": ["casting", "cinematographer", "colorist", "production_designer"],
                "plan_ids": {"cinematographer": "cam-plan-1"},
                "warnings": [],
            },
        }


def test_structured_previs_render_merges_department_guidance_into_prompt(tmp_path, monkeypatch):
    storage = DatabaseStorage(str(tmp_path))
    render_module.set_storage(storage)
    monkeypatch.setattr(render_module, "project_store", _FakeProjectStore())
    monkeypatch.setattr(dept_module, "department_render_context_service", _FakeDepartmentContext())

    service = RenderService()
    job = service.create_job(
        project_id="project_dept",
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="Maya pauses in the old kitchen, trying not to reveal what she heard.",
        reference_assets=[],
        parameters={
            "structured_prompt": True,
            "skip_character_injection": True,
            "shot_planning": {
                "blocking": "Maya pauses at the sink.",
                "production": "old kitchen",
                "camera": "static wide frame",
            },
        },
    )

    prompt = job.input_payload.prompt
    slots = job.input_payload.parameters["prompt_slots"]

    assert "Maya requires stillness" in prompt
    assert "blue enamel mug" in prompt
    assert "low patient push-in" in prompt
    assert "cool shadows" in prompt
    assert "department_render_context" in job.input_payload.parameters
    assert "cinematographer" in job.input_payload.parameters["department_render_context"]["sources"]
    assert "low patient push-in" in slots["camera"]
