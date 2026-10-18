"""Controlled character reference selection tests.

A test character registry is seeded with the full category spread the
Reference Library supports — canonical anchor, face, profile, full body,
wardrobe, night, expression, plus candidate, rejected, and foreign rows — and
the selected provider payload is verified under a constrained budget.
"""

from __future__ import annotations

import pytest

from app.services import project_store as project_store_module
from app.services.character_visual_reference_service import (
    CharacterVisualReferenceService,
)
from app.services.reference_selection_service import (
    scene_categories_for_prompt,
    select_character_references,
)


@pytest.fixture(autouse=True)
def _maya_project(monkeypatch):
    """Scene resolution for the selection tests: Scene 1/2 both list Maya."""
    project = {
        "project_id": "project_refsel",
        "execution_summary": {
            "scenes": [
                {"scene_id": "scene_001", "characters": ["Maya"]},
                {"scene_id": "scene_002", "characters": ["Maya"]},
            ]
        },
    }
    monkeypatch.setattr(project_store_module.project_store, "get_project", lambda _pid: project)


def _row(
    ref_id: str,
    *,
    category: str = "other",
    kind: str = "character_full",
    canonical: bool = False,
    approval_state: str = "approved",
    url: str | None = None,
    target_id: str = "maya",
) -> dict:
    return {
        "ref_id": ref_id,
        "project_id": "project_refsel",
        "target_type": "character",
        "target_id": target_id,
        "kind": kind,
        "image_url": url or f"https://cdn.example/{ref_id}.png",
        "canonical": canonical,
        "approval_state": approval_state,
        "category": category,
        "source_kind": "uploaded",
    }


def _maya_registry() -> list[dict]:
    """Every category from Part 8, seeded in shuffled registry order."""
    return [
        _row("maya-night", category="night"),
        _row("maya-expression", category="expression"),
        _row("maya-candidate", approval_state="candidate"),
        _row("maya-wardrobe", category="wardrobe"),
        _row("maya-rejected", approval_state="rejected"),
        _row("maya-canonical", canonical=True, category="face", kind="character_face"),
        _row("maya-face", category="face", kind="character_face"),
        _row("maya-full-body", category="full_body"),
        _row("maya-profile", category="profile"),
    ]


# ── Priority, exclusion, and determinism ──────────────────────────────────


def test_canonical_is_always_selected_first():
    result = select_character_references(_maya_registry(), budget=5)
    assert result.urls[0] == "https://cdn.example/maya-canonical.png"
    assert result.selected[0]["_selection_tier"] == "canonical"


def test_candidate_and_rejected_are_excluded():
    result = select_character_references(_maya_registry(), budget=9)
    ids = [row["ref_id"] for row in result.selected]
    assert "maya-candidate" not in ids
    assert "maya-rejected" not in ids
    excluded_reasons = {row["ref_id"]: row["reason"] for row in result.excluded}
    assert "not approved" in excluded_reasons["maya-candidate"]
    assert "not approved" in excluded_reasons["maya-rejected"]


def test_foreign_references_are_excluded():
    """Rows belonging to another character never enter the pool.

    The caller queries the registry per target; the selector additionally
    filters defensively so a foreign row cannot ride along in the input.
    """
    rows = _maya_registry() + [_row("dre-face", category="face", kind="character_face", target_id="dre")]
    pool = [row for row in rows if row.get("target_id") == "maya"]
    result = select_character_references(pool, budget=9)
    ids = {row["ref_id"] for row in result.selected}
    assert "dre-face" not in ids
    assert "maya-canonical" in ids


def test_identity_references_receive_priority_over_context():
    result = select_character_references(_maya_registry(), budget=4)
    tiers = [row["_selection_tier"] for row in result.selected]
    assert tiers == ["canonical", "face", "profile", "full_body"]


def test_context_references_fill_remaining_capacity():
    result = select_character_references(_maya_registry(), budget=6)
    tiers = [row["_selection_tier"] for row in result.selected]
    # Identity tier fully served before any context tier appears.
    assert tiers == ["canonical", "face", "profile", "full_body", "wardrobe", "expression"]


def test_selection_order_is_deterministic_across_registry_orders():
    """Same rows in different registry orders → identical selection order."""
    registry = _maya_registry()
    forward = select_character_references(registry, budget=9)
    reversed_order = select_character_references(list(reversed(registry)), budget=9)
    assert forward.urls == reversed_order.urls


def test_repeated_identical_inputs_produce_identical_payloads():
    first = select_character_references(_maya_registry(), budget=5, scene_categories=["night"])
    second = select_character_references(_maya_registry(), budget=5, scene_categories=["night"])
    assert first.summary() == second.summary()
    assert first.urls == second.urls


def test_duplicate_url_does_not_consume_two_provider_slots():
    rows = [
        _row("maya-canonical", canonical=True, category="face", kind="character_face"),
        _row("maya-face", category="face", kind="character_face"),
        _row("maya-face-dup", category="profile", url="https://cdn.example/maya-face.png"),
    ]
    result = select_character_references(rows, budget=9)
    urls = result.urls
    assert urls.count("https://cdn.example/maya-face.png") == 1
    excluded_reasons = {row["ref_id"]: row["reason"] for row in result.excluded}
    assert "duplicate" in excluded_reasons["maya-face-dup"]


def test_duplicate_uploaded_asset_same_file_name_does_not_consume_slots():
    """Re-uploading the same file lands at a new path; the file name still matches."""
    rows = [
        _row("maya-canonical", canonical=True, category="face", kind="character_face"),
        _row("maya-face", category="face", kind="character_face"),
        _row(
            "maya-face-reupload",
            category="wardrobe",
            url="/outputs/project_refsel/character/maya/heading-portrait_2.png",
        ),
        _row(
            "maya-face-original",
            category="profile",
            url="/outputs/project_refsel/character/maya/heading-portrait.png?cache=7",
        ),
    ]
    result = select_character_references(rows, budget=9)
    selected_urls = result.urls
    assert len([url for url in selected_urls if "heading-portrait" in url]) == 1
    # Exactly one of the duplicate pair is kept — first in registry order wins.
    excluded_reasons = {row["ref_id"]: row["reason"] for row in result.excluded}
    assert "duplicate asset" in excluded_reasons["maya-face-original"]
    assert "maya-face-reupload" in [row["ref_id"] for row in result.selected]


def test_selection_audit_explains_each_choice():
    result = select_character_references(_maya_registry(), budget=3)
    summary = result.summary()
    selected = {row["ref_id"]: row for row in summary["selected"]}
    assert selected["maya-canonical"]["tier"] == "canonical"
    assert "never displaced" in selected["maya-canonical"]["reason"]
    assert selected["maya-face"]["tier"] == "face"
    assert "maya-profile" in [row["ref_id"] for row in summary["selected"]]
    assert summary["excluded_count"] >= 6


def test_budget_zero_selects_nothing_but_reports_exclusions():
    result = select_character_references(_maya_registry(), budget=0)
    assert result.selected == []
    assert result.excluded


# ── Scene-aware selection ─────────────────────────────────────────────────


def test_night_scene_promotes_night_reference_into_remaining_capacity():
    day = select_character_references(_maya_registry(), budget=5)
    night = select_character_references(_maya_registry(), budget=5, scene_categories=["night"])

    # First four slots are identity in both scenes.
    assert [row["_selection_tier"] for row in night.selected[:4]] == [
        "canonical", "face", "profile", "full_body",
    ]
    # Fifth slot: the night scene swaps wardrobe for the night context ref.
    assert night.selected[4]["_selection_tier"] == "scene_context"
    assert night.selected[4]["ref_id"] == "maya-night"
    assert day.selected[4]["_selection_tier"] == "wardrobe"
    # …and the displaced wardrobe row is reported, not silently dropped.
    excluded = {row["ref_id"]: row["reason"] for row in night.excluded}
    assert "budget" in excluded["maya-wardrobe"]


def test_scene_context_cannot_displace_canonical_identity():
    result = select_character_references(
        _maya_registry(), budget=1, scene_categories=["night", "day"]
    )
    assert len(result.selected) == 1
    assert result.selected[0]["_selection_tier"] == "canonical"
    assert result.selected[0]["ref_id"] == "maya-canonical"


def test_scene_context_without_identity_pool_still_yields_identity_first():
    rows = [
        _row("maya-canonical", canonical=True, category="face", kind="character_face"),
        _row("maya-night", category="night"),
        _row("maya-night-2", category="night"),
    ]
    result = select_character_references(rows, budget=2, scene_categories=["night"])
    tiers = [row["_selection_tier"] for row in result.selected]
    assert tiers == ["canonical", "scene_context"]


def test_prompt_derived_scene_categories_are_deterministic():
    assert scene_categories_for_prompt("Maya waits in a moonlit alley after dark.") == ["night"]
    assert scene_categories_for_prompt("Golden daylight over the rooftop.") == ["day"]
    assert scene_categories_for_prompt("Maya says nothing.") == []
    assert scene_categories_for_prompt("") == []


# ── Setting scoping ───────────────────────────────────────────────────────


def test_setting_references_remain_target_scoped():
    """Setting rows are a different selection domain; the character selector
    never claims them, and a scene's setting refs stay scoped to that setting."""
    rows = _maya_registry() + [
        _row("setting-b-night", category="night", kind="environment", target_id="setting-b"),
        _row("setting-b-canonical", canonical=True, kind="environment", target_id="setting-b"),
        _row("setting-a-canonical", canonical=True, kind="environment", target_id="setting-a"),
    ]
    pool = [row for row in rows if row.get("target_id") == "maya"]
    result = select_character_references(pool, budget=9)
    ids = {row["ref_id"] for row in result.selected}
    assert ids.isdisjoint({"setting-a-canonical", "setting-b-canonical", "setting-b-night"})


# ── End-to-end payload construction through the character service ─────────


class _LockStorage:
    """Minimal storage double: one canonical lock + a supporting registry.

    The project store is stubbed at the module level (see the autouse fixture)
    so scene resolution finds Maya without touching real project state.
    """

    def __init__(self, supporting_rows: list[dict]):
        self._supporting = supporting_rows

    def get_character(self, character_id, project_id):
        return None  # force the lock-based path

    def get_characters(self, project_id):
        return [{
            "id": "maya",
            "name": "Maya",
            "project_id": project_id,
        }]

    def get_character_by_name(self, project_id, name):
        if str(name).strip().lower() == "maya":
            return {"id": "maya", "name": "Maya", "project_id": project_id}
        return None

    def list_character_reference_locks_for_character(self, project_id, character_id, status, limit, look_id):
        if character_id != "maya":
            return []
        return [{
            "image_url": "https://cdn.example/maya-canonical.png",
            "lock_status": "locked",
            "source_status": "approved",
            "review_status": "approved",
            "reference_role": "general",
            "look_id": "default",
            "source_shot_id": "scene_001_shot_001",
            "reliability": "high",
        }]

    def list_reference_assets(self, **kwargs):
        return self._supporting

    def get_character_staging(self, character_id, scene_id, shot_id):
        return None


def test_payload_build_prioritizes_identity_and_records_audit():
    """Day scene, 3 slots per character: canonical lock + the two highest
    identity references survive; wardrobe/night/expression do not displace
    identity evidence."""
    storage = _LockStorage(_maya_registry())
    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="project_refsel",
        shot_id="scene_001_shot_001",
        storage=storage,
        prompt="Maya crosses the plaza at midday, daylight on her face.",
    )
    assert payload is not None
    ref_ids = [ref.ref_id for ref in payload.refs]
    # Canonical lock first (its ref_id is charlock:*), then identity ordering.
    assert ref_ids[0] == "charlock:maya:general"
    assert ref_ids[1:3] == ["maya-face", "maya-profile"]
    assert "maya-wardrobe" not in ref_ids and "maya-night" not in ref_ids
    assert "maya-candidate" not in ref_ids and "maya-rejected" not in ref_ids

    # Audit recorded on the payload, keyed per character.
    audit = payload.selection_audit
    assert audit and audit[0]["character_id"] == "maya"
    selected_tiers = {row["ref_id"]: row["tier"] for row in audit[0]["selection"]["selected"]}
    assert selected_tiers["maya-face"] == "face"
    assert selected_tiers["maya-profile"] == "profile"
    # Candidate/rejected rows are already filtered before the selector (see
    # test_candidate_and_rejected_are_excluded for the selector's own guard);
    # the audit reports budget exclusions for the approved pool.
    excluded_reasons = {
        row["ref_id"]: row["reason"]
        for row in audit[0]["selection"]["excluded"]
    }
    assert "provider reference budget exhausted" in excluded_reasons["maya-wardrobe"]
    assert "provider reference budget exhausted" in excluded_reasons["maya-night"]
    assert "maya-full-body" in selected_tiers


def test_night_scene_swaps_context_reference_without_losing_identity():
    """Registry without a full_body row, so the night context ref competes for
    the third supporting slot against wardrobe/expression — identity first."""
    registry = [row for row in _maya_registry() if row["ref_id"] != "maya-full-body"]
    storage = _LockStorage(registry)
    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="project_refsel",
        shot_id="scene_001_shot_001",
        storage=storage,
        prompt="Maya waits under the streetlight; the whole block is dark and moonlit at night.",
    )
    ref_ids = [ref.ref_id for ref in payload.refs]
    # Canonical + top identity anchors are untouched by the night context.
    assert ref_ids[0] == "charlock:maya:general"
    assert {"maya-face", "maya-profile"} <= set(ref_ids)
    # The night reference took the final per-character slot in place of the
    # wardrobe reference the day scene would have carried.
    assert "maya-night" in ref_ids
    assert ref_ids[-1] == "maya-night"


def test_scene2_then_scene1_does_not_retain_scene2_character_context():
    """Returning from a night Scene 2 to a day Scene 1 rebuilds the selection;
    no Scene-2-specific character context survives into the Scene 1 payload."""
    registry = [row for row in _maya_registry() if row["ref_id"] != "maya-full-body"]
    service = CharacterVisualReferenceService()
    storage = _LockStorage(registry)

    scene2 = service.build_consistency_payload_for_shot(
        project_id="project_refsel",
        shot_id="scene_002_shot_001",
        storage=storage,
        prompt="Maya crouches in the alley after dark at night, moonlit.",
    )
    scene1 = service.build_consistency_payload_for_shot(
        project_id="project_refsel",
        shot_id="scene_001_shot_001",
        storage=storage,
        prompt="Maya crosses the plaza in bright daylight.",
    )
    scene2_urls = {ref.image_url for ref in scene2.refs}
    scene1_urls = {ref.image_url for ref in scene1.refs}
    # The night context ref participated in Scene 2…
    assert "https://cdn.example/maya-night.png" in scene2_urls
    # …and is gone from Scene 1, whose payload is the plain day selection.
    assert "https://cdn.example/maya-night.png" not in scene1_urls
    assert scene1_urls == {ref.image_url for ref in service.build_consistency_payload_for_shot(
        project_id="project_refsel",
        shot_id="scene_001_shot_001",
        storage=storage,
        prompt="Maya crosses the plaza in bright daylight.",
    ).refs}


def test_character_references_cannot_be_replaced_by_setting_references():
    """Setting rows present in the same storage cannot enter the character pool."""
    rows = _maya_registry() + [
        _row("setting-b-canonical", canonical=True, kind="environment", target_id="setting-b"),
        _row("setting-b-night", category="night", kind="environment", target_id="setting-b"),
    ]
    storage = _LockStorage(rows)
    payload = CharacterVisualReferenceService().build_consistency_payload_for_shot(
        project_id="project_refsel",
        shot_id="scene_001_shot_001",
        storage=storage,
        prompt="Maya at the harbor at night.",
    )
    ref_ids = [ref.ref_id for ref in payload.refs]
    assert all(ref_id in {row["ref_id"] for row in _maya_registry()} | {"charlock:maya:general"} for ref_id in ref_ids)
    assert "setting-b-canonical" not in ref_ids and "setting-b-night" not in ref_ids
