from __future__ import annotations

from app.services.continuity_intelligence_service import ContinuityIntelligenceService
from app.services.render import RenderService


class _EnvironmentStorage:
    def __init__(self):
        self.graphs: dict[str, dict] = {}
        self.versions: list[tuple[str, str, dict]] = []

    def load_continuity_graph(self, film_id: str):
        return self.graphs.get(film_id)

    def save_continuity_graph(self, film_id: str, graph: dict) -> bool:
        self.graphs[film_id] = graph
        return True

    def save_continuity_graph_version(self, film_id: str, version_id: str, graph: dict) -> bool:
        self.versions.append((film_id, version_id, graph))
        return True

    def list_reference_assets(self, project_id: str, kind: str | None = None, limit: int = 50):
        return []


def _env(**overrides):
    base = {
        "location": "Harbor House Kitchen",
        "time_of_day": "morning",
        "weather": "rain",
        "season": "winter",
    }
    base.update(overrides)
    return {"environment": base}


def test_sprint4_required_environment_sequence_persists_location_state_and_warnings():
    storage = _EnvironmentStorage()
    svc = ContinuityIntelligenceService(storage=storage)
    film_id = "film-env"

    establishing = svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_001",
        prompt="Establishing shot inside Harbor House Kitchen.",
        scene_data=_env(
            shot_type="establishing",
            room_layout="long galley kitchen with sink under the east window",
            entrances_exits=["front door left", "rear hall right"],
            furniture_placement={"farm table": "center", "stove": "back wall"},
            persistent_objects=["blue enamel mug", "red kettle"],
            lighting_sources=["east window", "stove practical"],
            cleanliness_disorder="tidy but lived-in",
            environmental_storytelling_details=["old flood mark on pantry wall"],
        ),
    )
    assert establishing["location_id"] == "harbor-house-kitchen"

    review = svc.evaluate_environment_render(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_001",
        render_job_id="job-establishing",
        render_output_url="/outputs/kitchen-establishing.mp4",
        prompt="\n".join(establishing["prompt_lines"]),
        scene_data=_env(shot_type="establishing"),
    )
    assert review["passed"] is True

    wide = svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_002",
        prompt="Wide interior in the same kitchen.",
        scene_data=_env(shot_type="wide"),
    )
    assert any("long galley kitchen" in line for line in wide["prompt_lines"])
    assert wide["selected_references"][0]["role"] == "establishing"
    assert "preferred as environment anchors" in wide["reference_explanations"][0]["reason"]

    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_003",
        prompt="Reverse angle across the kitchen.",
        scene_data=_env(
            shot_type="reverse_angle",
            spatial_relationships=["farm table remains between camera and sink"],
        ),
    )
    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_004",
        prompt="Close up near the blue enamel mug.",
        scene_data=_env(shot_type="close_up", recognizable_object="blue enamel mug"),
    )
    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_005",
        prompt="Mara enters through the front door.",
        scene_data=_env(character_entering="Mara through front door left"),
    )
    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_006",
        prompt="Mara exits toward the rear hall.",
        scene_data=_env(character_exiting="Mara through rear hall right"),
    )
    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_007",
        prompt="The mug has been moved.",
        scene_data=_env(object_movements=["blue enamel mug moved from farm table to sink"]),
    )
    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_008",
        prompt="The east window breaks.",
        scene_data=_env(window_broken=True),
    )
    later_broken = svc.resolve_environment_context(
        scene_id="scene_002",
        film_id=film_id,
        shot_id="scene_002_shot_001",
        prompt="Later scene in the same kitchen.",
        scene_data=_env(),
    )
    assert any("window broken" in line for line in later_broken["prompt_lines"])

    contradiction = svc.resolve_environment_context(
        scene_id="scene_002",
        film_id=film_id,
        shot_id="scene_002_shot_002",
        prompt="The window is intact again.",
        scene_data=_env(window_broken=False, prompt_notes="intact window"),
    )
    assert any("window was previously broken" in warning for warning in contradiction["warnings"])

    intentional_time_change = svc.resolve_environment_context(
        scene_id="scene_003",
        film_id=film_id,
        shot_id="scene_003_shot_001",
        prompt="Night in the same kitchen.",
        scene_data=_env(time_of_day="night", intentional_time_of_day_change=True),
    )
    assert not any("time_of_day" in warning for warning in intentional_time_change["warnings"])

    record = storage.graphs[film_id]["environment_continuity"]["locations"]["harbor-house-kitchen"]
    assert record["permanent_location_identity"]["name"] == "Harbor House Kitchen"
    assert record["default_layout"]["furniture_placement"]["farm table"] == "center"
    assert "blue enamel mug" in record["default_layout"]["persistent_objects"]
    assert "window broken" in record["destructive_changes"]
    assert "blue enamel mug moved from farm table to sink" in record["temporary_changes"]
    assert "Harbor House Kitchen" in record["visual_signature"]
    assert "blue enamel mug" in record["visual_signature"]
    assert later_broken["recognizability"]["recognizable"] is True
    assert "blue enamel mug" in later_broken["recognizability"]["preserved_anchors"]
    assert record["scene_state"]["time_of_day"] == "night"
    assert record["shot_state"]["scene_001_shot_005"]["entrance"] == "Mara through front door left"
    assert record["shot_state"]["scene_001_shot_006"]["exit"] == "Mara through rear hall right"


def test_environment_render_review_flags_underrepresented_visual_signature():
    storage = _EnvironmentStorage()
    svc = ContinuityIntelligenceService(storage=storage)
    film_id = "film-env-review"
    svc.resolve_environment_context(
        scene_id="scene_001",
        film_id=film_id,
        shot_id="scene_001_shot_001",
        prompt="Establishing shot inside Harbor House Kitchen.",
        scene_data=_env(
            room_layout="long galley kitchen with sink under the east window",
            furniture_placement={"farm table": "center"},
            persistent_objects=["blue enamel mug"],
            lighting_sources=["east window"],
        ),
    )

    review = svc.evaluate_environment_render(
        scene_id="scene_002",
        film_id=film_id,
        shot_id="scene_002_shot_001",
        render_job_id="job-unrecognizable",
        prompt="A blank white room.",
        scene_data={"environment": {"location": "Harbor House Kitchen"}},
    )

    assert review["passed"] is False
    assert review["environment_drift_detected"] is True
    assert "visual_recognizability: canonical environment anchors are underrepresented" in review["environment_flags"]
    assert review["recognizability"]["status"] == "needs_review"


def test_render_job_injects_environment_context_and_warning_metadata(monkeypatch):
    import app.services.continuity_intelligence_service as cont_module

    class _ContSvcStub:
        def resolve_environment_context(self, **kwargs):
            return {
                "location_id": "harbor-house-kitchen",
                "canonical_environment": {},
                "prompt_lines": [
                    "Environment identity: Harbor House Kitchen",
                    "Persisting damage: window broken",
                ],
                "warnings": ["destruction_damage: window was previously broken"],
                "selected_references": [{"source_shot_id": "scene_001_shot_001", "role": "establishing"}],
                "reference_explanations": [
                    {
                        "source_shot_id": "scene_001_shot_001",
                        "role": "establishing",
                        "reason": "selected because approved establishing shots are preferred as environment anchors",
                    }
                ],
                "state_change_summary": [],
            }

        def build_prompt_context(self, scene_id: str, film_id: str):
            return {
                "emotional_register": "",
                "active_motifs": [],
                "character_states": {},
                "tonal_direction": "",
                "continuity_anchors": [],
            }

    original = cont_module.continuity_intelligence_service
    cont_module.continuity_intelligence_service = _ContSvcStub()  # type: ignore[assignment]
    try:
        svc = RenderService()
        job = svc.create_job(
            project_id="proj-env-render",
            shot_id="scene_001_shot_002",
            provider="simulated",
            prompt="Wide shot inside Harbor House Kitchen with the broken window still visible.",
            parameters={"environment_continuity": {"location": "Harbor House Kitchen"}},
        )
    finally:
        cont_module.continuity_intelligence_service = original  # type: ignore[assignment]

    assert "[ENVIRONMENT CONTINUITY]" in job.input_payload.prompt
    assert "Persisting damage: window broken" in job.input_payload.prompt
    assert job.metadata["environment_continuity_warnings"] == [
        "destruction_damage: window was previously broken"
    ]
    assert job.input_payload.parameters["environment_continuity_context"]["location_id"] == "harbor-house-kitchen"
