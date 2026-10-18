"""Scene 002 creator decision capture — focused worksheet validation.

This module proves the existing version-scoped Scene Direction write surface
(`GET/PUT /projects/{project}/scenes/{scene}/direction`) can record every
creator decision required by the Scene 002 creator-decision worksheet, and
nothing else:

1. No decision exists before explicit creator input.
2. Prompt evidence (or any legacy shot evidence) cannot satisfy coverage.
3. Content assignment requires an explicit shot.
4. Content omission requires an explicit reason.
5. Dialogue assignment requires an explicit shot.
6. Dialogue omission requires an explicit reason.
7. Silence requires the documented line omission plus owning shot dialogue
   disposition of intentional silence with an explicit reason.
8. Unassigned remains unresolved.
9. Decisions are version scoped to the explicit approved version (resolved
   dynamically from the live copy's own blueprint pointer).
10. Existing approved prompts remain byte identical.
11. Existing screenplay bytes remain byte identical.
12. Existing approved camera plans remain unchanged.
13. Existing approved character references remain unchanged.
14. Existing setting reference remains unchanged.
15. Shot 005 DRE visibility cannot be inferred from the existing prompt.
16. No provider is contacted.
17. No render occurs.
18. No generation contract is created.
19. No readiness state is promoted merely because decisions were captured.
20. A partial decision set continues to fail closed.

Part A uses a synthetic Scene 002-shaped fixture (five approved shots with
empty ``shot_kind`` — mirroring the live board's empty-shot_kind condition,
and a Shot 005 prompt that names DRE staging language).

Part B runs against a byte copy of the live Scene 002 database — never the
live file — and is skipped when that file is absent. The only write performed
by Part B happens on the throwaway copy, so the live Scene 002 creative state
is hash-verified untouched.

Nothing in this module generates, runs preflight against a provider, renders,
or contacts any provider.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.scene_direction import CoverageDecision, SaveSceneDirection
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.project_store import ProjectStore
from app.services.scene_coverage_contract import build_scene_coverage_contract
from app.services.scene_direction_service import SceneDirectionService
from app.services.stability import ValidationError as ServiceValidationError
from app.services.stability import StateError

HEADING = "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE"
BODY = (
    "The same city. Different world. The L train is frozen.\n"
    "MAYA\n"
    "That's funny.\n"
    "DRE\n"
    "What?\n"
    "She looks out at Chicago while it is still alive.\n"
)
SHOT_005_PROMPT = (
    "Close-up detail shot. Eyes, hands, specific objects. DRE remains visible at "
    "the edge of frame while Maya wakes up. Intimate beat."
)
PROJECT_ID = "scene002-capture"
LIVE_PROJECT = "project_5907c60cddbc"
LIVE_SCENE = "scene_002"
LIVE_APPROVED_VERSION = "sbv_a6096cb1fea5"
LIVE_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "studio.db")


def _sha(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, str):
        value = value.encode("utf-8")
    if value is None:
        value = b""
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def capture(tmp_path):
    """Five approved Scene 002-shaped shots on an approved version.

    ``shot_kind`` is deliberately left empty on every shot: that mirrors the
    live board's empty-shot_kind condition and pins the model's semantics
    instead of papering over them.
    """
    project = StudioProject(
        project_id=PROJECT_ID,
        title="I was reborn",
        script_text=HEADING + "\n" + BODY,
        execution_summary={
            "scenes": [{
                "scene_id": "scene_002",
                "heading": HEADING,
                "text": BODY,
                "description": "Downtown Chicago after the apocalypse.",
                "characters": ["DRE", "MAYA"],
            }],
            "dialogue_lines": [
                {"line_id": "line_maya_1", "scene_id": "scene_002",
                 "character_name": "MAYA", "text": "That's funny."},
                {"line_id": "line_dre_1", "scene_id": "scene_002",
                 "character_name": "DRE", "text": "What?"},
            ],
        },
    )
    storage = DatabaseStorage(str(tmp_path / "db"))
    storage.save_project(project)
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path / "state.json"))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(
        project_id=PROJECT_ID, scene_id="scene_002", shot_count=5,
    )
    for shot in detail["shots"]:
        prompt = SHOT_005_PROMPT if shot.shot_number == 5 else (
            f"Shot {shot.shot_number} approved prompt. Canonical bytes must not change."
        )
        shot.render_contract.provider_neutral_prompt = prompt
        shot.render_contract.structured_parameters.update({
            "prompt": prompt,
            "camera_plan": {"camera": "fixed", "framing": "medium"},
            "approved_references": ["ref-unchanged"],
        })
        shot.render_contract.reference_assets = ["ref-unchanged"]
        storage.save_storyboard_shot(shot)
    detail["shots"] = storage.list_storyboard_shots(
        detail["blueprint"].blueprint_id, detail["version"].version_id,
    )
    detail["version"] = storage.get_storyboard_blueprint_version(detail["version"].version_id)
    detail["version"].status = StoryboardBlueprintStatus.APPROVED
    detail["version"].approved_at = "2026-09-30T00:00:00+00:00"
    detail["version"].approved_by = "creator"
    detail["blueprint"].status = StoryboardBlueprintStatus.APPROVED
    detail["blueprint"].approved_version_id = detail["version"].version_id
    storage.save_storyboard_blueprint_version(detail["version"])
    storage.save_storyboard_blueprint(detail["blueprint"])
    detail["version"] = storage.get_storyboard_blueprint_version(detail["version"].version_id)
    detail["blueprint"] = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    return service, storage, detail


def payload_for(data) -> SaveSceneDirection:
    return SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[
            shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
            for shot in data.shots
        ],
    )


def _shot_id(data, number: int) -> str:
    return next(shot.shot_id for shot in data.shots if shot.shot_number == number)


def _version_digest(storage, version_id) -> str:
    return _sha(storage.get_storyboard_blueprint_version(version_id).model_dump(mode="json"))


def _shot_digests(storage, blueprint_id, version_id) -> dict:
    return {
        shot.shot_id: _sha(shot.model_dump(mode="json"))
        for shot in storage.list_storyboard_shots(blueprint_id, version_id)
    }


def _build_contract(service, storage, project_id, scene_id, creator_decisions):
    """Run the production coverage contract with supplied creator decisions."""
    detail = service.blueprints.get_blueprint_detail(project_id=project_id, scene_id=scene_id)
    shots = detail["shots"]
    project_model = storage.get_project(project_id)
    project = project_model.model_dump(mode="json") if hasattr(project_model, "model_dump") else dict(project_model or {})
    summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
    scene = next(
        (row for row in summary.get("scenes") or [] if isinstance(row, dict) and row.get("scene_id") == scene_id),
        None,
    )
    shot_rows = []
    for shot in shots:
        row = shot.model_dump(mode="json")
        parameters = dict(row.get("render_contract", {}).get("structured_parameters", {}))
        for key in ("dialogue_lines", "covered_content_ids", "creator_coverage_decisions",
                    "dialogue_disposition", "content_coverage_disposition", "content_coverage_reason"):
            parameters.pop(key, None)
        row["parameters"] = parameters
        row["covered_content_ids"] = []
        row["shot_id"] = shot.shot_id
        row["shot_number"] = shot.shot_number
        row["shot_kind"] = parameters.get("shot_kind") or shot.metadata.get("shot_kind", "")
        shot_rows.append(row)
    canonical_scene = dict(scene)
    for key in ("coverage_decisions", "content_dispositions", "dialogue_dispositions",
                "dialogue_disposition", "speech_disposition", "dialogue_lines"):
        canonical_scene.pop(key, None)
    return build_scene_coverage_contract(
        project_id=project_id, project=project, scene=canonical_scene,
        shots=shot_rows, creator_decisions=creator_decisions,
    )


def _no_provider_contact():
    """Fail loudly if the image submission seam were ever reached."""
    try:
        import app.services.providers.image_provider as image_provider
    except Exception:  # pragma: no cover - seam absent in some builds
        from contextlib import nullcontext
        return nullcontext()
    original = image_provider.submit_image_render
    image_provider.submit_image_render = MagicMock(
        side_effect=AssertionError("provider must never be contacted by decision capture"),
    )
    from contextlib import contextmanager

    @contextmanager
    def _restore():
        try:
            yield image_provider.submit_image_render
        finally:
            image_provider.submit_image_render = original

    return _restore()


# ── Part A: synthetic Scene 002-shaped fixture ──────────────────────────────


def test_capture_surface_begins_unresolved_with_no_creator_input(capture):
    """(1, 8) No decision exists until Amb supplies one; unassigned stays unresolved."""
    service, storage, detail = capture
    data = service.get(PROJECT_ID, "scene_002")
    assert data.version_id == detail["version"].version_id
    assert data.version_status == "approved"
    assert data.saved is False
    assert data.coverage_decisions
    assert all(row.status == "UNASSIGNED" for row in data.coverage_decisions)
    assert all(row.status == "UNASSIGNED" for row in data.coverage_obligations)
    assert all(line.shot_id is None for line in data.dialogue)
    assert set(data.unassigned_line_ids) == {line.line_id for line in data.dialogue}
    assert data.coverage_blocked
    assert data.coverage_blockers
    for row in data.coverage_decisions:
        if row.obligation_type in {"shot_dialogue", "shot_content"}:
            assert row.obligation_id in {shot.shot_id for shot in data.shots}
    # The capture surface offers exactly the worksheet decision kinds.
    kinds = {row.obligation_type for row in data.coverage_decisions}
    assert kinds == {"content", "dialogue", "shot_dialogue", "shot_content"}


def test_prompt_and_legacy_evidence_cannot_satisfy_coverage(capture):
    """(2) Prompt wording and legacy shot evidence never establish a decision."""
    service, storage, detail = capture
    for shot in detail["shots"]:
        shot.render_contract.structured_parameters.update({
            "dialogue_lines": [{"line_id": "line_maya_1", "character": "MAYA", "text": "That's funny."}],
            "covered_content_ids": ["content_forged"],
            "creator_coverage_decisions": [
                {"obligation_type": "dialogue", "obligation_id": "line_maya_1",
                 "status": "ASSIGNED", "shot_id": shot.shot_id, "reason": ""},
            ],
            "dialogue_disposition": "INTENTIONAL_SILENCE",
            "content_coverage_disposition": "INTENTIONAL_SILENCE",
        })
        shot.intent.narrative_function = "DRE and MAYA argue over the gun."
        storage.save_storyboard_shot(shot)

    data = service.get(PROJECT_ID, "scene_002")
    assert all(row.status == "UNASSIGNED" for row in data.coverage_decisions)
    assert all(line.shot_id is None for line in data.dialogue)
    assert data.coverage_blocked

    saved = service.save(PROJECT_ID, "scene_002", payload_for(data))
    assert all(row.status == "UNASSIGNED" for row in saved.coverage_decisions)
    assert all(line.shot_id is None for line in saved.dialogue)
    assert saved.coverage_blocked
    _, blockers, _ = _build_contract(service, storage, PROJECT_ID, "scene_002", creator_decisions=[])
    assert any("creator coverage decisions are missing for content" in item for item in blockers)
    assert any("creator coverage decisions are missing for dialogue" in item for item in blockers)


def test_content_assignment_requires_an_explicit_shot(capture):
    """(3) ASSIGNED content without a specific shot is impossible."""
    with pytest.raises(PydanticValidationError):
        CoverageDecision(obligation_type="content", obligation_id="content-x", status="ASSIGNED")
    with pytest.raises(PydanticValidationError):
        CoverageDecision(obligation_type="content", obligation_id="content-x", status="ASSIGNED", shot_id=None)


def test_content_omission_requires_an_explicit_reason(capture):
    """(4) EXPLICITLY_OMITTED content without a creator reason is impossible."""
    with pytest.raises(PydanticValidationError):
        CoverageDecision(obligation_type="content", obligation_id="content-x", status="EXPLICITLY_OMITTED")
    service, storage, detail = capture
    data = service.get(PROJECT_ID, "scene_002")
    payload = payload_for(data)
    payload.coverage_decisions = [
        row.model_copy(update={"status": "EXPLICITLY_OMITTED", "reason": ""})
        if row.obligation_type == "content" else row
        for row in payload.coverage_decisions
    ]
    with pytest.raises(ServiceValidationError):
        service.save(PROJECT_ID, "scene_002", payload)


def test_dialogue_assignment_requires_an_explicit_shot(capture):
    """(5) ASSIGNED dialogue without a specific shot is impossible."""
    with pytest.raises(PydanticValidationError):
        CoverageDecision(obligation_type="dialogue", obligation_id="line_x", status="ASSIGNED")


def test_dialogue_omission_requires_an_explicit_reason(capture):
    """(6) EXPLICITLY_OMITTED dialogue without a creator reason is impossible."""
    with pytest.raises(PydanticValidationError):
        CoverageDecision(obligation_type="dialogue", obligation_id="line_x", status="EXPLICITLY_OMITTED")


def test_silence_requires_omitted_line_plus_shot_intentional_silence_and_reason(capture):
    """(7) Silence = omitted canonical line + owning shot intentional silence + reasons."""
    service, storage, detail = capture
    data = service.get(PROJECT_ID, "scene_002")
    shot1, shot2, shot3 = _shot_id(data, 1), _shot_id(data, 2), _shot_id(data, 3)

    # Silence disposition itself demands a creator reason.
    with pytest.raises(PydanticValidationError):
        CoverageDecision(
            obligation_type="shot_dialogue", obligation_id=shot2,
            status="INTENTIONAL_SILENCE",
        )

    payload = payload_for(data)
    payload.coverage_decisions = [
        row.model_copy(update={"status": "EXPLICITLY_OMITTED", "reason": "Creator cut this line from the scene."})
        if row.obligation_type == "dialogue" else row
        for row in payload.coverage_decisions
    ]

    # Omitted lines alone do not establish shot-level silence: with every shot
    # disposition unresolved, the coverage gate keeps blocking.
    saved = service.save(PROJECT_ID, "scene_002", payload)
    assert saved.coverage_blocked
    assert any("dialogue disposition unresolved" in item for item in saved.coverage_blockers)
    omitted = {
        row.obligation_id: row for row in saved.coverage_decisions if row.obligation_type == "dialogue"
    }
    assert all(row.status == "EXPLICITLY_OMITTED" and row.reason for row in omitted.values())

    # Owning shot silence requires its own explicit reasoned disposition.
    payload = payload_for(saved)
    payload.expected_version_id = saved.version_id
    payload.coverage_decisions = [
        row.model_copy(update={"status": "INTENTIONAL_SILENCE", "reason": "Reaction beat plays silent."})
        if row.obligation_type == "shot_dialogue" and row.obligation_id == shot2 else row
        for row in payload.coverage_decisions
    ]
    saved_two = service.save(PROJECT_ID, "scene_002", payload)
    assert saved_two.coverage_blocked  # other shots and obligations remain unresolved
    assert not any(
        item.startswith(f"shot {shot2} dialogue disposition unresolved")
        for item in saved_two.coverage_blockers
    )
    assert any(
        item.startswith(f"shot {shot3} dialogue disposition unresolved")
        for item in saved_two.coverage_blockers
    )
    shot_decisions = {
        row.obligation_id: row for row in saved_two.coverage_decisions
        if row.obligation_type == "shot_dialogue"
    }
    assert shot_decisions[shot2].status == "INTENTIONAL_SILENCE"
    assert shot_decisions[shot2].reason

    # A shot that owns assigned dialogue can never be omitted or silenced.
    payload = payload_for(saved_two)
    payload.expected_version_id = saved_two.version_id
    payload.coverage_decisions = [
        row.model_copy(update={"status": "ASSIGNED", "shot_id": shot1})
        if row.obligation_type == "dialogue" else row
        for row in payload.coverage_decisions
    ]
    payload.dialogue = [
        line.model_copy(update={"shot_id": shot1}) for line in payload.dialogue
    ]
    payload.coverage_decisions = [
        row.model_copy(update={"status": "INTENTIONAL_SILENCE", "reason": "Contradiction."})
        if row.obligation_type == "shot_dialogue" and row.obligation_id == shot1 else row
        for row in payload.coverage_decisions
    ]
    with pytest.raises(ServiceValidationError):
        service.save(PROJECT_ID, "scene_002", payload)


def test_unassigned_decisions_remain_unresolved_after_capture(capture):
    """(8, 19) Capturing a complete all-UNASSIGNED set resolves nothing."""
    service, storage, detail = capture
    before_version = _version_digest(storage, detail["version"].version_id)
    data = service.get(PROJECT_ID, "scene_002")
    saved = service.save(PROJECT_ID, "scene_002", payload_for(data))
    assert saved.saved is True
    assert saved.version_id != data.version_id
    assert all(row.status == "UNASSIGNED" for row in saved.coverage_decisions)
    assert all(row.status == "UNASSIGNED" for row in saved.coverage_obligations)
    assert saved.coverage_blocked
    assert any("canonical scene content unresolved" in item for item in saved.coverage_blockers)
    assert any("canonical dialogue unresolved" in item for item in saved.coverage_blockers)
    # The approved source version keeps exactly its pre-capture bytes.
    assert _version_digest(storage, detail["version"].version_id) == before_version
    assert storage.get_storyboard_blueprint_version(detail["version"].version_id).status == StoryboardBlueprintStatus.APPROVED
    # Readiness cannot be promoted by capture: the board must not return to an
    # approved-current chain, and coverage stays blocked.
    blueprint = storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id)
    assert blueprint.status == StoryboardBlueprintStatus.DRAFT
    assert blueprint.current_version_id == saved.version_id
    assert blueprint.approved_version_id == detail["version"].version_id


def test_decisions_are_scoped_to_the_explicit_approved_version(capture):
    """(9) Capture binds to an explicit expected version — never 'latest', never global."""
    service, storage, detail = capture
    approved_id = detail["version"].version_id

    stale = payload_for(service.get(PROJECT_ID, "scene_002"))
    stale.expected_version_id = "sbv_000000000000"
    with pytest.raises(StateError):
        service.save(PROJECT_ID, "scene_002", stale)

    data = service.get(PROJECT_ID, "scene_002")
    assert data.version_id == approved_id
    saved = service.save(PROJECT_ID, "scene_002", payload_for(data))
    successor = storage.get_storyboard_blueprint_version(saved.version_id)
    assert successor.source_version_id == approved_id
    assert storage.get_storyboard_blueprint_version(approved_id).status == StoryboardBlueprintStatus.APPROVED

    # The successor is the new explicit target; replaying the old version id
    # must fail rather than attach decisions to an arbitrary version.
    replay = payload_for(saved)
    replay.expected_version_id = approved_id
    with pytest.raises(StateError):
        service.save(PROJECT_ID, "scene_002", replay)


def test_capture_keeps_creative_records_byte_identical(capture):
    """(10, 11, 12, 13) Prompts, screenplay, camera plans, references unchanged."""
    service, storage, detail = capture
    blueprint_id = detail["blueprint"].blueprint_id
    approved_id = detail["version"].version_id
    source_version = _version_digest(storage, approved_id)
    source_shots = _shot_digests(storage, blueprint_id, approved_id)
    source_project = storage.get_project(PROJECT_ID).model_dump(mode="json")
    source_prompts = {
        shot.shot_id: shot.render_contract.provider_neutral_prompt
        for shot in storage.list_storyboard_shots(blueprint_id, approved_id)
    }
    source_camera = {
        shot.shot_id: shot.render_contract.structured_parameters.get("camera_plan")
        for shot in storage.list_storyboard_shots(blueprint_id, approved_id)
    }
    source_refs = {
        shot.shot_id: (shot.render_contract.reference_assets,
                       shot.render_contract.structured_parameters.get("approved_references"))
        for shot in storage.list_storyboard_shots(blueprint_id, approved_id)
    }

    data = service.get(PROJECT_ID, "scene_002")
    saved = service.save(PROJECT_ID, "scene_002", payload_for(data))

    assert _version_digest(storage, approved_id) == source_version
    assert _shot_digests(storage, blueprint_id, approved_id) == source_shots
    assert storage.get_project(PROJECT_ID).model_dump(mode="json") == source_project
    for shot in storage.list_storyboard_shots(blueprint_id, approved_id):
        assert shot.render_contract.provider_neutral_prompt == source_prompts[shot.shot_id]
        assert shot.render_contract.structured_parameters.get("camera_plan") == source_camera[shot.shot_id]
        assert shot.render_contract.reference_assets == source_refs[shot.shot_id][0]
        assert shot.render_contract.structured_parameters.get("approved_references") == source_refs[shot.shot_id][1]

    # The captured successor preserves every prompt and camera plan byte too —
    # only the documented decision fields are added.
    decision_keys = {"creator_coverage_decisions", "covered_content_ids", "dialogue_disposition",
                     "dialogue_disposition_reason", "content_coverage_disposition", "content_coverage_reason"}
    successor_shots = storage.list_storyboard_shots(blueprint_id, saved.version_id)
    assert len(successor_shots) == len(source_shots)
    for original, clone in zip(
        storage.list_storyboard_shots(blueprint_id, approved_id), successor_shots,
    ):
        assert clone.render_contract.provider_neutral_prompt == source_prompts[original.shot_id]
        assert clone.render_contract.structured_parameters.get("camera_plan") == source_camera[original.shot_id]
        assert clone.render_contract.reference_assets == source_refs[original.shot_id][0]
        original_params = dict(original.render_contract.structured_parameters)
        clone_params = dict(clone.render_contract.structured_parameters)
        for key in decision_keys:
            original_params.pop(key, None)
            clone_params.pop(key, None)
        assert clone_params == original_params


def test_shot_005_dre_staging_is_never_inferred_from_the_prompt(capture):
    """(15) Shot 005 DRE visibility stays an unanswered creator question."""
    service, storage, detail = capture
    shot_five = next(shot for shot in detail["shots"] if shot.shot_number == 5)
    prompt_before = shot_five.render_contract.provider_neutral_prompt
    assert "DRE" in prompt_before  # prompt evidence exists...

    data = service.get(PROJECT_ID, "scene_002")
    shot_five_id = _shot_id(data, 5)
    # ...but no decision and no obligation is ever derived from it.
    content_texts = {
        row.source_text for row in data.coverage_obligations if row.obligation_type == "content"
    }
    assert content_texts == {line for line in BODY.splitlines() if line.strip()}
    assert all("DRE" not in row.source_text or row.source_text == "DRE" for row in data.coverage_obligations)
    for row in data.coverage_decisions:
        if row.obligation_id == shot_five_id:
            assert row.obligation_type in {"shot_dialogue", "shot_content"}
            assert row.status == "UNASSIGNED"
            assert row.shot_id is None
            assert row.reason == ""
    assert all(row.status == "UNASSIGNED" for row in data.coverage_decisions)

    saved = service.save(PROJECT_ID, "scene_002", payload_for(data))
    shot_five_clone = next(
        shot for shot in storage.list_storyboard_shots(
            detail["blueprint"].blueprint_id, saved.version_id,
        ) if shot.shot_number == 5
    )
    assert shot_five_clone.render_contract.provider_neutral_prompt == prompt_before
    assert all(
        row.status == "UNASSIGNED"
        for row in saved.coverage_decisions if row.obligation_id == shot_five_id
    )
    # No staging/visibility decision slot exists to be silently filled either.
    assert not any(
        row.obligation_type not in {"content", "dialogue", "shot_dialogue", "shot_content"}
        for row in saved.coverage_decisions
    )


def test_capture_contacts_no_provider_renders_nothing_builds_no_contract(capture):
    """(16, 17, 18) Decision capture never reaches a provider, a render, or a contract."""
    service, storage, detail = capture
    jobs_before = storage.list_jobs(project_id=PROJECT_ID)
    data = service.get(PROJECT_ID, "scene_002")
    with _no_provider_contact() as seam:
        service.save(PROJECT_ID, "scene_002", payload_for(data))
    assert seam.call_count == 0 if isinstance(seam, MagicMock) else True
    assert storage.list_jobs(project_id=PROJECT_ID) == jobs_before
    # Generation contracts only ever persist inside render jobs; with no new
    # job rows, no generation contract was created.
    assert jobs_before == []


def test_partial_decision_set_is_rejected_and_fails_closed(capture):
    """(20) A partial submission is rejected outright and coverage stays blocked."""
    service, storage, detail = capture
    data = service.get(PROJECT_ID, "scene_002")
    approved_id = detail["version"].version_id
    version_before = _version_digest(storage, approved_id)

    # Drop a single decision.
    payload = payload_for(data)
    removed = payload.coverage_decisions.pop()
    with pytest.raises(ServiceValidationError):
        service.save(PROJECT_ID, "scene_002", payload)
    # Drop an entire obligation kind.
    payload = payload_for(data)
    payload.coverage_decisions = [
        row for row in payload.coverage_decisions if row.obligation_type != "content"
    ]
    with pytest.raises(ServiceValidationError):
        service.save(PROJECT_ID, "scene_002", payload)
    # Duplicate a decision instead of submitting exactly one per obligation.
    payload = payload_for(data)
    payload.coverage_decisions.append(removed)
    with pytest.raises(ServiceValidationError):
        service.save(PROJECT_ID, "scene_002", payload)

    assert _version_digest(storage, approved_id) == version_before
    assert storage.get_storyboard_blueprint_by_id(detail["blueprint"].blueprint_id).current_version_id == approved_id
    assert storage.list_jobs(project_id=PROJECT_ID) == []

    # Even if a partial packet somehow reached storage, the contract itself
    # fails closed with explicit missing/incomplete blockers.
    full = [row.model_dump() for row in data.coverage_decisions]
    _, blockers_empty, _ = _build_contract(service, storage, PROJECT_ID, "scene_002", creator_decisions=[])
    assert any("missing for content obligations" in item for item in blockers_empty)
    assert any("missing for dialogue obligations" in item for item in blockers_empty)
    _, blockers_partial, _ = _build_contract(
        service, storage, PROJECT_ID, "scene_002", creator_decisions=full[:-1],
    )
    assert any("incomplete" in item or "missing" in item for item in blockers_partial)
    _, blockers_full, _ = _build_contract(
        service, storage, PROJECT_ID, "scene_002", creator_decisions=full,
    )
    assert any("canonical scene content unresolved" in item for item in blockers_full)
    assert any("canonical dialogue unresolved" in item for item in blockers_full)


# ── Part B: live Scene 002 write surface, exercised on a byte copy ───────────


def _live_copy(tmp_path):
    """Byte-copy the live DB (+wal/+shm) so the live file is never opened."""
    copy_dir = tmp_path / "live_copy"
    copy_dir.mkdir()
    shutil.copy2(LIVE_DB, copy_dir / "studio.db")
    for suffix in ("-wal", "-shm"):
        if os.path.exists(LIVE_DB + suffix):
            shutil.copy2(LIVE_DB + suffix, copy_dir / ("studio.db" + suffix))
    return copy_dir


def _live_approved_version_id(db_path) -> str:
    """Resolve the copy's approved Scene 002 version dynamically (R4.5-Phase2 #23).

    The live board evolves, so a pinned version hash rots; the copy's own
    blueprint pointer is the valid fixture datum. Read-only."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT approved_version_id FROM storyboard_blueprints WHERE project_id=? AND scene_id=?",
            (LIVE_PROJECT, LIVE_SCENE),
        ).fetchone()
    finally:
        con.close()
    approved_id = str((row or [""])[0] or "")
    assert approved_id, "live copy has no approved Scene 002 version"
    return approved_id


def _live_digests(db_path, approved_version_id):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    def one(sql, args=()):
        row = con.execute(sql, args).fetchone()
        return dict(row) if row else None

    def many(sql, args=()):
        return [dict(r) for r in con.execute(sql, args).fetchall()]

    project = one("SELECT data FROM projects WHERE project_id=?", (LIVE_PROJECT,))
    pdata = json.loads(project["data"]) if project and project.get("data") else {}
    scenes = (pdata.get("execution_summary") or {}).get("scenes") or []
    scene_row = next((row for row in scenes if isinstance(row, dict) and row.get("scene_id") == LIVE_SCENE), None)
    bp = one("SELECT * FROM storyboard_blueprints WHERE project_id=? AND scene_id=?",
             (LIVE_PROJECT, LIVE_SCENE))
    version = one("SELECT * FROM storyboard_blueprint_versions WHERE version_id=?", (approved_version_id,))
    shots = many("SELECT * FROM storyboard_shots WHERE version_id=? ORDER BY shot_number",
                 (approved_version_id,))
    prompts, camera_plans, shot_rows = {}, {}, {}
    for shot in shots:
        contract = json.loads(shot.get("render_contract_json") or "{}")
        params = contract.get("structured_parameters") or {}
        key = shot.get("shot_id")
        shot_rows[key] = _sha(json.dumps(shot, sort_keys=True, default=str))
        prompts[key] = _sha(params.get("provider_neutral_prompt") or contract.get("provider_neutral_prompt"))
        camera_plans[key] = _sha(params.get("camera_plan"))
    refs = many("SELECT * FROM reference_assets WHERE project_id=? ORDER BY ref_id", (LIVE_PROJECT,))

    def ref_digest(match):
        rows = [row for row in refs if all(row.get(k) == v for k, v in match.items())]
        return _sha(json.dumps(rows, sort_keys=True, default=str)) + f"|count={len(rows)}"

    out = {
        "screenplay": _sha(pdata.get("script_text")),
        "scene_projection": _sha(scene_row.get("text") if scene_row else None),
        "blueprint_approved_version": (bp or {}).get("approved_version_id"),
        "blueprint_locked": (bp or {}).get("locked"),
        "approved_version": _sha(json.dumps(version, sort_keys=True, default=str) if version else None),
        "approved_version_status": (version or {}).get("status"),
        "shot_rows": shot_rows,
        "prompts": prompts,
        "camera_plans": camera_plans,
        "dre_reference": ref_digest({"target_type": "character", "target_id": "chr_f1425498cb68"}),
        "maya_reference": ref_digest({"target_type": "character", "target_id": "chr_3c9e91741ef3"}),
        "environment_reference": ref_digest({"target_type": "setting", "target_id": LIVE_SCENE}),
        "reference_row_count": len(refs),
        "version_count": len(many(
            "SELECT version_id FROM storyboard_blueprint_versions WHERE blueprint_id=?",
            ((bp or {}).get("blueprint_id"),),
        )),
        "jobs": len(many("SELECT 1 FROM render_jobs WHERE project_id=?", (LIVE_PROJECT,))),
        "blueprint_current": (bp or {}).get("current_version_id"),
    }
    con.close()
    return out


CANONICAL_KEYS = (
    "screenplay", "scene_projection", "blueprint_approved_version", "blueprint_locked",
    "approved_version", "approved_version_status", "shot_rows", "prompts", "camera_plans",
    "dre_reference", "maya_reference", "environment_reference", "reference_row_count",
)


@pytest.mark.skipif(not os.path.exists(LIVE_DB), reason="live studio.db byte copy source is absent")
def test_scene002_write_surface_is_version_scoped_and_hash_safe(tmp_path):
    """(9–15, 19, 20 + database safety) against a byte copy of live Scene 002.

    The only write in this test happens on the throwaway copy. Afterwards only
    the Scene Direction decision surface may differ: the approved version, its
    five shot rows, all five prompts and camera plans, the screenplay, the
    scene projection, and the DRE/MAYA/environment references must hash
    identically, and coverage must still fail closed.
    """
    copy_dir = _live_copy(tmp_path)
    db_path = copy_dir / "studio.db"

    # Dynamic fixture datum (R4.5-Phase2 #23): the copy's own approved pointer,
    # not a pinned hash. Re-point the copy's working draft at it so the test
    # exercises the approved board exactly as the worksheet requires. The live
    # file is never opened; every write below lands on the throwaway copy.
    approved_id = _live_approved_version_id(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "UPDATE storyboard_blueprints SET current_version_id=? WHERE project_id=? AND scene_id=?",
        (approved_id, LIVE_PROJECT, LIVE_SCENE),
    )
    # Restore the pre-input capture state the worksheet requires: the live
    # board has since recorded decisions on its approved version, so strip
    # them on the copy (copy-only) for a deterministic fixture. Baseline
    # digests below are taken after this prep, keeping every comparison
    # self-consistent without touching the live file or production logic.
    row = con.execute(
        "SELECT metadata FROM storyboard_blueprint_versions WHERE version_id=?",
        (approved_id,),
    ).fetchone()
    try:
        meta = json.loads(row[0]) if row and row[0] else {}
    except (json.JSONDecodeError, TypeError):
        meta = {}
    if isinstance(meta, dict) and "scene_direction" in meta:
        del meta["scene_direction"]
        con.execute(
            "UPDATE storyboard_blueprint_versions SET metadata=? WHERE version_id=?",
            (json.dumps(meta), approved_id),
        )
    con.commit()
    con.close()

    # Worksheet scope, read-only, before any write.
    storage = DatabaseStorage(str(copy_dir))
    service = SceneDirectionService(storage)
    data = service.get(LIVE_PROJECT, LIVE_SCENE)
    # Baseline is taken after the storage layer finished opening/migrating the
    # copy, so every later diff can only come from the decision write itself.
    baseline = _live_digests(db_path, approved_id)
    assert data.version_id == approved_id
    assert data.version_status == "approved"
    counts = {
        "content": sum(1 for row in data.coverage_obligations if row.obligation_type == "content"),
        "dialogue": sum(1 for row in data.coverage_obligations if row.obligation_type == "dialogue"),
        "shot_dialogue": sum(1 for row in data.coverage_decisions if row.obligation_type == "shot_dialogue"),
        "shot_content": sum(1 for row in data.coverage_decisions if row.obligation_type == "shot_content"),
    }
    assert counts == {"content": 40, "dialogue": 10, "shot_dialogue": 5, "shot_content": 5}
    assert len(data.coverage_decisions) == 60
    if data.saved:
        pytest.skip("Scene 002 already carries explicit creator decisions; "
                    "pre-input capture state no longer applies")
    assert all(row.status == "UNASSIGNED" for row in data.coverage_decisions)
    assert data.coverage_blocked
    shot_five = next(shot for shot in data.shots if shot.shot_number == 5)
    assert shot_five.shot_kind == ""  # the documented empty shot_kind condition
    assert shot_five.dialogue_disposition == "UNASSIGNED"
    assert shot_five.dialogue_disposition_reason == ""

    # Shot 005 prompt evidence exists in the stored contract but produced no
    # staging decision and no obligation of any kind.
    blueprint_id = storage.get_storyboard_blueprint(LIVE_PROJECT, LIVE_SCENE).blueprint_id
    stored_five = next(
        shot for shot in storage.list_storyboard_shots(blueprint_id, approved_id)
        if shot.shot_number == 5
    )
    prompt_five = stored_five.render_contract.provider_neutral_prompt
    assert isinstance(prompt_five, str) and prompt_five
    assert not any(
        row.obligation_type not in {"content", "dialogue", "shot_dialogue", "shot_content"}
        for row in data.coverage_decisions
    )

    jobs_before = storage.list_jobs(project_id=LIVE_PROJECT)

    # (20) Partial submission rejected with zero writes.
    payload = payload_for(data)
    payload.coverage_decisions.pop()
    with pytest.raises(ServiceValidationError):
        service.save(LIVE_PROJECT, LIVE_SCENE, payload)
    after_partial = _live_digests(db_path, approved_id)
    assert {key: after_partial[key] for key in CANONICAL_KEYS} == {
        key: baseline[key] for key in CANONICAL_KEYS
    }
    assert after_partial["blueprint_current"] == baseline["blueprint_current"]
    assert after_partial["version_count"] == baseline["version_count"]

    # (9) Wrong expected version rejected with zero writes.
    payload = payload_for(data)
    payload.expected_version_id = "sbv_000000000000"
    with pytest.raises(StateError):
        service.save(LIVE_PROJECT, LIVE_SCENE, payload)
    after_stale = _live_digests(db_path, approved_id)
    assert {key: after_stale[key] for key in CANONICAL_KEYS} == {
        key: baseline[key] for key in CANONICAL_KEYS
    }

    # The explicit, complete-but-unresolved capture — the only write.
    payload = payload_for(data)
    with _no_provider_contact():
        saved = service.save(LIVE_PROJECT, LIVE_SCENE, payload)

    after = _live_digests(db_path, approved_id)
    # Canonical creative records: byte identical.
    assert {key: after[key] for key in CANONICAL_KEYS} == {
        key: baseline[key] for key in CANONICAL_KEYS
    }
    # The approved version stays approved and untouched...
    assert after["approved_version"] == baseline["approved_version"]
    assert after["approved_version_status"] == "approved"
    # ...while the blueprint pointer moves to the capture draft, never changing
    # which version is approved.
    assert after["blueprint_approved_version"] == approved_id
    assert after["blueprint_current"] == saved.version_id
    assert after["blueprint_current"] != approved_id
    assert after["version_count"] == baseline["version_count"] + 1
    # No provider, no render, no generation contract.
    assert after["jobs"] == baseline["jobs"]
    assert storage.list_jobs(project_id=LIVE_PROJECT) == jobs_before

    # Decisions are recorded on the successor scoped from the approved version.
    successor = storage.get_storyboard_blueprint_version(saved.version_id)
    assert successor.source_version_id == approved_id
    scene_direction = successor.metadata.get("scene_direction") or {}
    decisions = scene_direction.get("coverage_decisions") or []
    assert len(decisions) == 60
    assert {row.get("status") for row in decisions} == {"UNASSIGNED"}
    assert len(scene_direction.get("dialogue") or []) == 10
    approved_row = storage.get_storyboard_blueprint_version(approved_id)
    assert "scene_direction" not in (approved_row.metadata or {})
    assert approved_row.status == StoryboardBlueprintStatus.APPROVED

    # (19, 20) Capture promoted nothing: still blocked, still unresolved.
    assert saved.coverage_blocked
    assert all(row.status == "UNASSIGNED" for row in saved.coverage_decisions)
    assert saved.coverage_blockers
    assert any("canonical scene content unresolved" in item for item in saved.coverage_blockers)
    assert any("canonical dialogue unresolved" in item for item in saved.coverage_blockers)
