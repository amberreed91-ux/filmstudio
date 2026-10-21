"""Option B draft-carry tests for Scene Direction setting_reference_decision.

Disposable data only: project_5907c60cddbc / scene_002. Never scene_001.
Real service + synthetic fixture must agree:
- unchanged decision on current draft carries (no 409), live check still runs
- changed/new decision on draft still 409
- deauthorized row on next draft save still 422
- omitted field inherits and carries on draft
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.scene_direction import SaveSceneDirection, SettingReferenceDecision
from app.models.storyboard_blueprint import StoryboardBlueprintStatus
from app.services.project_store import ProjectStore
from app.services.reference_asset_service import (
    SCENE002_PROJECT_ID,
    SCENE002_SETTING_ID,
    ReferenceAssetService,
)
from app.services.scene_direction_service import SceneDirectionService
from app.services.stability import StateError, ValidationError
from creator_workspace_fixture import (
    PROJECT_ID as FIX_PROJECT,
    SCENE_ID as FIX_SCENE,
    SETTING_ID as FIX_SETTING,
    SOURCE_VERSION_ID as FIX_SOURCE,
    FixtureStore,
    create_app,
)

PROJECT_ID = "project_5907c60cddbc"
SCENE_ID = "scene_002"
SHARED_URI = "https://assets.example.test/scene002-draft-carry.png"
SHARED_URI_2 = "https://assets.example.test/scene002-draft-carry-2.png"


def _setup(tmp_path, dirname: str = "draft-carry"):
    text = "EXT. CHICAGO RIVER - DAY\nMaya studies the water.\nMAYA\nKeep it."
    project = StudioProject(
        project_id=PROJECT_ID,
        title="Draft carry fixture",
        script_text=text,
        execution_summary={
            "scenes": [{
                "scene_id": SCENE_ID,
                "setting_id": SCENE002_SETTING_ID,
                "description": "Fixture scene.",
                "text": text,
                "characters": [],
            }],
            "dialogue_lines": [{
                "line_id": "scene002-line-1", "scene_id": SCENE_ID,
                "character_name": "MAYA", "text": "Keep it.",
            }],
        },
    )
    storage = DatabaseStorage(str(tmp_path / dirname))
    storage.save_project(project)
    storage.save_universe_node({
        "node_id": SCENE002_SETTING_ID, "project_id": PROJECT_ID,
        "node_type": "location", "name": "Exact setting entity",
        "first_scene": SCENE_ID, "last_scene": SCENE_ID,
    })
    service = SceneDirectionService(storage)
    service.blueprints.project_store = ProjectStore(str(tmp_path / f"{dirname}-state.json"))
    service.blueprints.project_store.save_project(project.model_dump())
    detail = service.blueprints.get_or_create_blueprint(
        project_id=PROJECT_ID, scene_id=SCENE_ID, shot_count=1,
    )
    source = detail["version"]
    source.status = StoryboardBlueprintStatus.APPROVED
    source.approved_at = "2026-10-01T00:00:00+00:00"
    source.approved_by = "synthetic creator"
    detail["blueprint"].status = StoryboardBlueprintStatus.APPROVED
    detail["blueprint"].approved_version_id = source.version_id
    storage.save_storyboard_blueprint_version(source)
    storage.save_storyboard_blueprint(detail["blueprint"])
    refs = ReferenceAssetService(storage)
    candidate = refs.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI)
    refs.approve_scene002_setting_reference(PROJECT_ID, candidate["ref_id"])
    refs.designate_scene002_setting_reference_canonical(PROJECT_ID, candidate["ref_id"])
    return service, storage, detail, candidate["ref_id"]


def _payload(data, decision):
    return SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
                  for shot in data.shots],
        setting_reference_decision=decision,
    )


def _payload_omitted(data):
    # Omit setting_reference_decision entirely so model_fields_set lacks it.
    return SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in data.dialogue],
        coverage_decisions=[row.model_dump() for row in data.coverage_decisions],
        handoffs=[shot.model_dump(include={"shot_id", "opening_state", "action_change", "ending_state"})
                  for shot in data.shots],
    )


def test_lifecycle_approved_then_two_draft_resaves_succeed(tmp_path):
    service, storage, _, ref_id = _setup(tmp_path, "lifecycle")
    data = service.get(PROJECT_ID, SCENE_ID)
    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=ref_id,
    )
    saved1 = service.save(PROJECT_ID, SCENE_ID, _payload(data, decision))
    assert saved1.version_status == "draft"
    assert saved1.setting_reference_decision is not None
    assert saved1.setting_reference_decision.reference_id == ref_id

    draft1 = service.get(PROJECT_ID, SCENE_ID)
    assert draft1.version_id == saved1.version_id
    saved2 = service.save(PROJECT_ID, SCENE_ID, _payload(draft1, decision))
    assert saved2.version_status == "draft"
    assert saved2.setting_reference_decision is not None
    assert saved2.setting_reference_decision.reference_id == ref_id

    draft2 = service.get(PROJECT_ID, SCENE_ID)
    saved3 = service.save(PROJECT_ID, SCENE_ID, _payload(draft2, decision))
    assert saved3.version_status == "draft"
    assert saved3.setting_reference_decision is not None
    assert saved3.setting_reference_decision.reference_id == ref_id


def test_changed_reference_on_draft_still_409(tmp_path):
    service, storage, _, ref_id = _setup(tmp_path, "changed-409")
    data = service.get(PROJECT_ID, SCENE_ID)
    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=ref_id,
    )
    saved1 = service.save(PROJECT_ID, SCENE_ID, _payload(data, decision))

    refs = ReferenceAssetService(storage)
    other = refs.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI_2)
    refs.approve_scene002_setting_reference(PROJECT_ID, other["ref_id"])
    refs.designate_scene002_setting_reference_canonical(PROJECT_ID, other["ref_id"])

    draft1 = service.get(PROJECT_ID, SCENE_ID)
    changed = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=other["ref_id"],
    )
    with pytest.raises(StateError):
        service.save(PROJECT_ID, SCENE_ID, _payload(draft1, changed))


def test_deauthorized_row_next_draft_save_returns_422(tmp_path):
    service, storage, _, ref_id = _setup(tmp_path, "stale-422")
    data = service.get(PROJECT_ID, SCENE_ID)
    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=ref_id,
    )
    saved1 = service.save(PROJECT_ID, SCENE_ID, _payload(data, decision))
    assert saved1.setting_reference_decision is not None

    storage.update_reference_asset_state(ref_id, PROJECT_ID, "rejected")
    draft1 = service.get(PROJECT_ID, SCENE_ID)
    with pytest.raises(ValidationError):
        service.save(PROJECT_ID, SCENE_ID, _payload(draft1, decision))


def test_omitted_field_inherits_and_carries_on_draft(tmp_path):
    service, _, _, ref_id = _setup(tmp_path, "omitted-carry")
    data = service.get(PROJECT_ID, SCENE_ID)
    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=ref_id,
    )
    saved1 = service.save(PROJECT_ID, SCENE_ID, _payload(data, decision))
    draft1 = service.get(PROJECT_ID, SCENE_ID)
    assert draft1.setting_reference_decision is not None
    assert draft1.setting_reference_decision.reference_id == ref_id

    carried = service.save(PROJECT_ID, SCENE_ID, _payload_omitted(draft1))
    assert carried.setting_reference_decision is not None
    assert carried.setting_reference_decision.reference_id == ref_id
    assert carried.version_status == "draft"


def test_guard_distinguishes_carry_from_authorize(tmp_path):
    """Unchanged draft carry succeeds; changed draft is StateError (409);
    stale live row is ValidationError (422)."""
    from app.routes.scene_direction import http_error

    service, storage, _, ref_id = _setup(tmp_path, "guard")
    data = service.get(PROJECT_ID, SCENE_ID)
    decision = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=ref_id,
    )
    service.save(PROJECT_ID, SCENE_ID, _payload(data, decision))
    draft = service.get(PROJECT_ID, SCENE_ID)

    # Carry: same decision on current draft must NOT raise.
    carried = service.save(PROJECT_ID, SCENE_ID, _payload(draft, decision))
    assert carried.setting_reference_decision is not None

    # Authorize: different reference_id on draft must be StateError -> HTTP 409.
    refs = ReferenceAssetService(storage)
    other = refs.create_scene002_setting_candidate(PROJECT_ID, SHARED_URI_2)
    refs.approve_scene002_setting_reference(PROJECT_ID, other["ref_id"])
    refs.designate_scene002_setting_reference_canonical(PROJECT_ID, other["ref_id"])
    draft2 = service.get(PROJECT_ID, SCENE_ID)
    changed = SettingReferenceDecision(
        canonical_setting_id=SCENE002_SETTING_ID, reference_id=other["ref_id"],
    )
    try:
        service.save(PROJECT_ID, SCENE_ID, _payload(draft2, changed))
        raise AssertionError("changed draft decision should have raised StateError")
    except StateError as exc:
        assert http_error(exc).status_code == 409

    # Live check: same decision after deauthorization must be ValidationError -> 422.
    storage.update_reference_asset_state(ref_id, PROJECT_ID, "rejected")
    draft3 = service.get(PROJECT_ID, SCENE_ID)
    try:
        service.save(PROJECT_ID, SCENE_ID, _payload(draft3, decision))
        raise AssertionError("stale draft decision should have raised ValidationError")
    except ValidationError as exc:
        assert http_error(exc).status_code == 422


def test_fixture_parity_carry_409_422_and_omitted_inheritance():
    """Synthetic fixture enforces the same Option B rule as the real service."""
    store = FixtureStore()
    app = create_app(store)
    url = f"/api/f51/studio/projects/{FIX_PROJECT}/scenes/{FIX_SCENE}/direction"
    ref_url = f"/api/f51/studio/projects/{FIX_PROJECT}/setting-references/{FIX_SETTING}"
    with TestClient(app) as client:
        opened = client.get(url).json()
        reg = client.post(ref_url, json={"image_url": "fixture://carry-a", "category": "environment"}).json()["reference_asset"]
        reg2 = client.post(ref_url, json={"image_url": "fixture://carry-b", "category": "environment"}).json()["reference_asset"]
        for ref in (reg, reg2):
            assert client.post(f"{ref_url}/{ref['ref_id']}/approve").status_code == 200
        assert client.post(f"{ref_url}/{reg['ref_id']}/canonical", json={"canonical": True}).status_code == 200

        def payload_for(direction, decision_set=True, decision=None):
            body = {
                "expected_version_id": direction["version_id"],
                "dialogue": direction["dialogue"],
                "coverage_decisions": direction["coverage_decisions"],
                "handoffs": [
                    {"shot_id": s["shot_id"], "opening_state": "", "action_change": "", "ending_state": ""}
                    for s in direction["shots"]
                ],
            }
            if decision_set:
                body["setting_reference_decision"] = decision
            return body

        ready = client.get(url).json()
        first = client.put(url, json=payload_for(
            ready, True,
            {"canonical_setting_id": FIX_SETTING, "reference_id": reg["ref_id"]},
        ))
        assert first.status_code == 200, first.text
        assert first.json()["setting_reference_decision"]["reference_id"] == reg["ref_id"]

        # Second + third saves with unchanged decision succeed (explicit).
        draft1 = client.get(url).json()
        second = client.put(url, json=payload_for(
            draft1, True,
            {"canonical_setting_id": FIX_SETTING, "reference_id": reg["ref_id"]},
        ))
        assert second.status_code == 200, second.text
        draft2 = client.get(url).json()
        third = client.put(url, json=payload_for(draft2, True,
            {"canonical_setting_id": FIX_SETTING, "reference_id": reg["ref_id"]}))
        assert third.status_code == 200, third.text

        # Omitted field inherits and carries.
        draft3 = client.get(url).json()
        omitted = client.put(url, json=payload_for(draft3, False))
        assert omitted.status_code == 200, omitted.text
        assert omitted.json()["setting_reference_decision"]["reference_id"] == reg["ref_id"]

        # Changed decision on draft is 409.
        draft4 = client.get(url).json()
        assert client.post(f"{ref_url}/{reg2['ref_id']}/canonical", json={"canonical": True}).status_code == 200
        # Re-approve reg (canonical flag moved); reg stays approved but non-canonical
        # so using reg2 as the changed decision is the new-reference path.
        changed = client.put(url, json=payload_for(
            draft4, True,
            {"canonical_setting_id": FIX_SETTING, "reference_id": reg2["ref_id"]},
        ))
        # reg2 is approved+canonical, but the decision itself is new/changed on a
        # draft, so the approved-version gate must reject it.
        assert changed.status_code == 409, changed.text

        # Deauthorized row: same carried decision is 422 on next draft save.
        for row in store.references:
            if row["ref_id"] == reg["ref_id"]:
                row["approval_state"] = "rejected"
                row["canonical"] = True
        # Point the draft back at the deauthorized ref to exercise the live check.
        store.direction["setting_reference_decision"] = {
            "canonical_setting_id": FIX_SETTING, "reference_id": reg["ref_id"],
        }
        draft5 = client.get(url).json()
        stale = client.put(url, json=payload_for(
            draft5, True,
            {"canonical_setting_id": FIX_SETTING, "reference_id": reg["ref_id"]},
        ))
        assert stale.status_code == 422, stale.text
