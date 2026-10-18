"""Phase 5/6 — advisory department guidance and canonical dialogue boundaries.

Camera:
- CameraGrammar/department slot guidance enters the provider prompt only as
  ADDED slot text (``merge_knowledge_guidance_into_slots``). It never writes
  the generation-context camera instructions, so it can never carry
  USER_SPECIFIED/APPROVED provenance or mutate canonical camera intent.
- Explicit creator camera plans may carry only real camera movements: an
  editorial cut token in an APPROVED plan raises instead of laundering.
- The Scene Direction dialogue projection is built only from canonical
  screenplay text / creator-curated rows — fabricated placeholder lines can
  never appear as assignable dialogue.
"""
from __future__ import annotations

import pytest

from app.models.storyboard_blueprint import StoryboardShotRenderContract
from app.services.generation_context_service import (
    CAMERA_SOURCE_APPROVED,
    CAMERA_SOURCE_AI_SUGGESTED,
    CAMERA_SOURCE_USER_SPECIFIED,
    generation_context_service,
)
from app.services.shot_prompt_builder import (
    SLOT_BUDGETS,
    merge_identity_guidance_into_slots,
    merge_knowledge_guidance_into_slots,
)


def test_department_camera_guidance_never_becomes_renderable_camera_data():
    """Department guidance flows into prompt slots only. The generation-context
    camera list built by derive_camera_instructions is untouched by it, so an
    advisory suggestion cannot masquerade as approved camera intent."""
    # Merge guidance into slots (the department path).
    slots = {
        "camera": "Medium shot.",
        "lighting": "",
        "character_state": "",
        "action": "",
        "environment_persistence": "",
        "reserve": "",
    }
    merge_knowledge_guidance_into_slots(
        slots,
        {
            "camera": "favor low-angle hero framing with slow push-in",
            "lighting": "practical neon spill, hard falloff",
        },
    )
    assert "slow push-in" in slots["camera"]
    assert "neon spill" in slots["lighting"]

    # The camera-instruction pipeline (which carries provenance) is derived
    # from creator plan / approved plan / storyboard shot only. No department
    # input is passed, so nothing APPROVED or USER_SPECIFIED can appear.
    instructions = generation_context_service.derive_camera_instructions()
    sources = {instruction.instruction_source for instruction in instructions}
    assert sources <= {"UNSPECIFIED"}


def test_advisory_guidance_cannot_overwrite_existing_slot_intent():
    slots = {"camera": "Static wide."}
    merge_knowledge_guidance_into_slots(slots, {"camera": "handheld chaos"})
    # Guidance is additive and idempotent, never destructive.
    assert slots["camera"].startswith("Static wide.")
    assert "handheld chaos" in slots["camera"]
    before = dict(slots)
    merge_knowledge_guidance_into_slots(slots, {"camera": "handheld chaos"})
    assert slots == before


def test_creator_camera_plan_with_edit_grammar_token_fails_loud():
    """An 'approved' plan carrying a CUT instruction is an authoring bug — it
    must raise, never be laundered into APPROVED camera provenance."""
    from app.services.generation_context_service import is_edit_grammar_movement

    assert is_edit_grammar_movement("match_cut")
    with pytest.raises(ValueError):
        generation_context_service.derive_camera_instructions(
            approved_camera_plan={"camera": "match_cut", "framing": "Medium"},
        )


def test_approved_plan_only_from_explicit_camera_plan_payload():
    """Only the explicit creator camera plan earns APPROVED; a bare visual plan
    on a board shot stays AI_SUGGESTED (pending, unapproved)."""
    class _Shot:
        version_id = "sbv_test"
        visual_plan = None
        render_contract = StoryboardShotRenderContract()
        metadata = {}

    approved = generation_context_service.derive_camera_instructions(
        approved_camera_plan={"camera": "slow dolly in", "framing": "Close-up"},
    )
    assert {i.instruction_source for i in approved} <= {CAMERA_SOURCE_APPROVED, "UNSPECIFIED"}
    assert {i.instruction_source for i in approved if i.value} == {CAMERA_SOURCE_APPROVED}

    from app.services.generation_context_service import pending_ai_camera_suggestions

    pending = pending_ai_camera_suggestions(_Shot())
    # No approval state was created for the unapproved shot.
    instructions = generation_context_service.derive_camera_instructions(storyboard_shot=_Shot())
    assert all(i.instruction_source != CAMERA_SOURCE_APPROVED for i in instructions)
    assert all(i.instruction_source != CAMERA_SOURCE_USER_SPECIFIED for i in instructions)
    assert isinstance(pending, dict)


def test_identity_guidance_is_additive_and_bounded():
    slots = {"character_state": "Only DRE visible. No extras."}
    merge_identity_guidance_into_slots(slots, "faded denim jacket")
    assert slots["character_state"].startswith("Only DRE visible. No extras.; faded denim jacket")
    assert len(slots["character_state"]) <= SLOT_BUDGETS["character_state"]


# ── Scene Direction dialogue authority (Phase 3B) ────────────────────────────


SCENE_TEXT = (
    "DRE\nI need you to understand something.\n"
    "MAYA\nThat's funny.\n"
    "DRE\nSomeone had to.\n"
)


def _project(scene_text: str = SCENE_TEXT) -> dict:
    return {
        "project_id": "project_dialogue",
        "title": "Dialogue Authority",
        "execution_summary": {
            "scenes": [
                {
                    "scene_id": "scene_002",
                    "heading": "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE",
                    "text": scene_text,
                    "characters": ["DRE", "MAYA"],
                }
            ],
            # The historical fabricated projection.
            "dialogue_lines": [
                {"scene_id": "scene_002", "character_id": "dre", "text": "DRE carries the beat with restrained subtext."},
                {"scene_id": "scene_002", "character_id": "maya", "text": "MAYA carries the beat with restrained subtext."},
            ],
        },
    }


def test_scene_direction_dialogue_comes_from_screenplay_not_placeholders(tmp_path):
    from app.data.storage import DatabaseStorage
    from app.services.project_store import ProjectStore
    from app.services.scene_direction_service import SceneDirectionService
    from app.services.storyboard_blueprint_service import StoryboardBlueprintService

    storage = DatabaseStorage(f"sqlite:///{tmp_path}/dialogue-authority.db")
    state = ProjectStore(str(tmp_path / "state.json"))
    project = _project_dict()
    state.save_project(project)
    # Scene Direction reads the project through the blueprint service's
    # storage; point it at the same canonical project dict.
    storage.get_project = lambda pid, *args, **kwargs: project if pid == "project_dialogue" else None
    service = StoryboardBlueprintService(storage)
    service.project_store = state
    direction = SceneDirectionService(storage)
    direction.blueprints.project_store = state
    detail = direction.blueprints.get_or_create_blueprint(
        project_id="project_dialogue", scene_id="scene_002", shot_count=2
    )
    direction.blueprints.project_store = state
    result = direction.get("project_dialogue", "scene_002")
    texts = [line.text for line in result.dialogue]
    assert texts, "canonical dialogue lines must be offered for assignment"
    for text in texts:
        assert "carries the beat" not in text
    assert "I need you to understand something." in texts
    assert "Someone had to." in texts


def _project_dict() -> dict:
    return _project()
