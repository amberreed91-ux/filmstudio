from __future__ import annotations

import json

import pytest

from app.data.storage import DatabaseStorage
from app.services.character_identity_memory_service import character_identity_memory_service
from app.services.script_parser import ScriptParser


def _storage(tmp_path):
    return DatabaseStorage(str(tmp_path / "db"))


def test_character_identity_memory_service_builds_provider_context_and_drift_warnings():
    profiles = [
        {
            "character_id": "elena",
            "name": "Elena",
            "visual_references": ["ref/elena-face-01.png"],
            "facial_identity": "oval face, scar left brow",
            "silhouette": "narrow shoulders, long coat",
            "movement_style": "measured stillness",
            "emotional_baseline": "guarded",
            "emotional_behavior": "suppresses panic",
            "speech_rhythm": "measured",
        }
    ]
    scene = {"scene_id": "scene_001", "character_appearances": ["Elena"], "emotional_target": "angry"}
    provider_context = character_identity_memory_service.build_provider_identity_context(profiles, scene)
    memory_notes = character_identity_memory_service.build_emotional_memory_continuity(profiles, scene)
    drift = character_identity_memory_service.detect_identity_drift_warnings(profiles, scene)

    assert provider_context["advisory_only"] is True
    assert provider_context["identity_lines"]
    assert provider_context["reference_images"]["elena"] == ["ref/elena-face-01.png"]
    assert any("carry continuity" in note.lower() for note in memory_notes)
    assert any("emotional drift warning" in row.lower() for row in drift)


def test_canonical_character_identity_separates_fixed_and_changeable_traits(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-sprint3",
        "Maya",
        {
            "identity_core_json": """
            {
              "facial_identity": "heart-shaped face, deep-set eyes",
              "body_and_silhouette": "compact frame, squared shoulders",
              "skin_tone": "warm brown",
              "hair_style": "tight coils",
              "hair_length": "chin length",
              "hair_color": "black",
              "age_presentation": "late thirties"
            }
            """,
            "default_appearance_json": """
            {
              "wardrobe": ["charcoal work jacket", "plain white tee"],
              "accessories": ["thin silver chain"],
              "persistent_props": ["brass lighter"],
              "emotional_state": "contained grief"
            }
            """,
        },
    )

    record = character_identity_memory_service.build_canonical_record(character)

    assert record is not None
    assert record.identity_core.skin_tone == "warm brown"
    assert record.identity_core.hair_color == "black"
    assert record.default_appearance.wardrobe == ["charcoal work jacket", "plain white tee"]
    assert record.default_appearance.persistent_props == ["brass lighter"]
    assert record.needs_human_review is True


def test_approved_references_are_reused_and_rejected_references_are_quarantined(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-sprint3",
        "Maya",
        {
            "identity_core_json": """
            {
              "facial_identity": "heart-shaped face",
              "body_and_silhouette": "compact frame",
              "face_reference": "approved-face"
            }
            """,
        },
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-sprint3",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "source_job_id": "job-approved",
            "image_url": "https://cdn.example.test/maya-approved.jpg",
            "lock_status": "locked",
            "source_status": "approved",
            "review_status": "approved",
            "reliability": "high",
        }
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-sprint3",
            "character_id": character["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_002",
            "source_job_id": "job-rejected",
            "image_url": "https://cdn.example.test/maya-rejected.jpg",
            "lock_status": "disabled",
            "source_status": "rejected",
            "review_status": "rejected",
            "reliability": "low",
        }
    )

    records = character_identity_memory_service.build_records_from_storage(
        project_id="proj-sprint3",
        storage=storage,
    )
    context = character_identity_memory_service.build_provider_context_from_records(
        records,
        {"scene_id": "scene_002", "characters": ["Maya"]},
        shot_id="scene_002_shot_001",
    )

    assert len(records) == 1
    assert records[0].approved_visual_references[0].source_job_id == "job-approved"
    assert records[0].rejected_visual_references[0].source_job_id == "job-rejected"
    assert "maya-approved.jpg" in context["reference_images"][character["id"]][0]["image_url"]
    assert "maya-rejected.jpg" not in str(context["reference_images"])


def test_conflicting_identity_references_raise_visible_review_warning(tmp_path):
    storage = _storage(tmp_path)
    character = storage.save_character(
        "proj-sprint3",
        "Maya",
        {
            "identity_core_json": """
            {
              "facial_identity": "round face vs narrow angular face",
              "body_and_silhouette": "compact frame",
              "face_reference": "approved-face"
            }
            """
        },
    )

    record = character_identity_memory_service.build_canonical_record(character)

    assert record is not None
    assert record.needs_human_review is True
    assert any("conflicting facial identity" in warning for warning in record.conflict_warnings)


def test_required_recurring_character_sequence_preserves_identity_and_instructed_changes(tmp_path):
    storage = _storage(tmp_path)
    maya = storage.save_character(
        "proj-sprint3-sequence",
        "Maya",
        {
            "identity_core_json": json.dumps(
                {
                    "face_reference": "approved-face",
                    "facial_identity": "heart-shaped face, deep-set eyes",
                    "body_and_silhouette": "compact frame, squared shoulders",
                    "skin_tone": "warm brown",
                    "hair_style": "tight coils",
                    "hair_length": "chin length",
                    "hair_color": "black",
                    "age_presentation": "late thirties",
                }
            ),
            "default_appearance_json": json.dumps(
                {
                    "wardrobe": ["charcoal work jacket", "plain white tee"],
                    "accessories": ["thin silver chain"],
                    "persistent_props": ["brass lighter"],
                    "emotional_state": "contained grief",
                }
            ),
            "continuity_state_json": json.dumps(
                {
                    "scene_specific_appearance": {
                        "scene_003": {
                            "wardrobe": ["red raincoat", "plain white tee"],
                            "emotional_state": "guarded resolve",
                        }
                    },
                    "shot_specific_state": {
                        "scene_004_shot_001": {
                            "emotional_state": "open anger",
                        }
                    },
                    "temporary_continuity_changes": [
                        {
                            "version_id": "tmp_maya_cheek_cut",
                            "source": "continuity_note",
                            "source_shot_id": "scene_002_shot_002",
                            "applies_from_scene_id": "scene_002",
                            "applies_from_shot_id": "scene_002_shot_002",
                            "clears_at_scene_id": "scene_005",
                            "clears_at_shot_id": "scene_005_shot_002",
                            "change_summary": "small cheek cut and rain dirt persist until cleaned",
                            "appearance": {
                                "injuries": ["small cut on left cheek"],
                                "dirt_blood_or_wear": ["rain dirt on jacket cuff"],
                            },
                            "reliability": "high",
                        }
                    ],
                    "appearance_version_history": [
                        {
                            "version_id": "default_maya_wardrobe",
                            "source": "manual",
                            "change_summary": "canonical default look",
                            "appearance": {
                                "wardrobe": ["charcoal work jacket", "plain white tee"],
                            },
                            "reliability": "high",
                        },
                        {
                            "version_id": "scene003_raincoat",
                            "source": "script",
                            "source_shot_id": "scene_003_shot_001",
                            "change_summary": "scripted exterior wardrobe change",
                            "appearance": {
                                "wardrobe": ["red raincoat", "plain white tee"],
                            },
                            "reliability": "high",
                        },
                    ],
                    "reliability": "high",
                    "trace_sources": [
                        {"kind": "script", "source_id": "uploaded_script"},
                        {"kind": "approved_render", "source_job_id": "job-approved-closeup"},
                    ],
                }
            ),
            "appearance_version_history_json": json.dumps(
                [
                    {
                        "version_id": "default_maya_wardrobe",
                        "source": "manual",
                        "change_summary": "canonical default look",
                        "appearance": {
                            "wardrobe": ["charcoal work jacket", "plain white tee"],
                        },
                        "reliability": "high",
                    },
                    {
                        "version_id": "scene003_raincoat",
                        "source": "script",
                        "source_shot_id": "scene_003_shot_001",
                        "change_summary": "scripted exterior wardrobe change",
                        "appearance": {
                            "wardrobe": ["red raincoat", "plain white tee"],
                        },
                        "reliability": "high",
                    },
                ]
            ),
        },
    )
    storage.save_character(
        "proj-sprint3-sequence",
        "Jonah",
        {
            "identity_core_json": json.dumps(
                {
                    "face_reference": "approved-jonah-face",
                    "facial_identity": "long face, close-cropped beard",
                    "body_and_silhouette": "tall, narrow frame",
                }
            ),
        },
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-sprint3-sequence",
            "character_id": maya["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_001_shot_001",
            "source_job_id": "job-approved-closeup",
            "image_url": "https://cdn.example.test/maya-approved-closeup.jpg",
            "lock_status": "locked",
            "source_status": "approved",
            "review_status": "approved",
            "reference_role": "face",
            "reliability": "high",
        }
    )
    storage.save_character_reference_lock(
        {
            "project_id": "proj-sprint3-sequence",
            "character_id": maya["id"],
            "character_name": "Maya",
            "source_shot_id": "scene_002_shot_001",
            "source_job_id": "job-rejected-medium",
            "image_url": "https://cdn.example.test/maya-rejected-medium.jpg",
            "lock_status": "disabled",
            "source_status": "rejected",
            "review_status": "rejected",
            "reliability": "low",
        }
    )

    record = character_identity_memory_service.build_records_from_storage(
        project_id="proj-sprint3-sequence",
        storage=storage,
        character_ids=[maya["id"]],
    )[0]

    sequence = [
        ("close up", "scene_001", "scene_001_shot_001", ["Maya"], "charcoal work jacket", "contained grief", False),
        ("medium shot", "scene_001", "scene_001_shot_002", ["Maya"], "charcoal work jacket", "contained grief", False),
        ("full body shot", "scene_002", "scene_002_shot_001", ["Maya"], "charcoal work jacket", "contained grief", False),
        ("interior scene", "scene_002", "scene_002_shot_002", ["Maya"], "charcoal work jacket", "contained grief", True),
        ("exterior scene", "scene_003", "scene_003_shot_001", ["Maya"], "red raincoat", "guarded resolve", True),
        ("different lighting", "scene_003", "scene_003_shot_002", ["Maya"], "red raincoat", "guarded resolve", True),
        ("wardrobe change", "scene_003", "scene_003_shot_003", ["Maya"], "red raincoat", "guarded resolve", True),
        ("emotional change", "scene_004", "scene_004_shot_001", ["Maya"], "charcoal work jacket", "open anger", True),
        ("multi character shot", "scene_004", "scene_004_shot_002", ["Maya", "Jonah"], "charcoal work jacket", "contained grief", True),
        ("later scene returning to earlier wardrobe", "scene_005", "scene_005_shot_001", ["Maya"], "charcoal work jacket", "contained grief", True),
    ]

    for label, scene_id, shot_id, characters, wardrobe, emotion, has_cut in sequence:
        context = character_identity_memory_service.build_provider_context_from_records(
            [record],
            {"scene_id": scene_id, "characters": characters, "coverage": label},
            shot_id=shot_id,
            provider_capability={
                "provider": "happyhorse-r2v",
                "supports_render": True,
                "supports_reference_images": True,
            },
        )
        line = context["identity_lines"][0]
        assert "heart-shaped face" in line
        assert "compact frame" in line
        assert "warm brown" in line
        assert "tight coils chin length black" in line
        assert wardrobe in line
        assert emotion in line
        assert ("small cut on left cheek" in line) is has_cut
        assert context["constraint_injection"]["strategy"] == "reference_images_and_text"
        assert context["reference_images"][maya["id"]][0]["source_job_id"] == "job-approved-closeup"
        assert "maya-rejected-medium.jpg" not in str(context["reference_images"])

    text_only_context = character_identity_memory_service.build_provider_context_from_records(
        [record],
        {"scene_id": "scene_001", "characters": ["Maya"]},
        shot_id="scene_001_shot_001",
        provider_capability={"provider": "mock", "supports_render": True},
    )
    assert text_only_context["constraint_injection"]["strategy"] == "text_only"
    assert text_only_context["reference_images"] == {}
    assert text_only_context["constraint_injection"]["text_constraints"]
    assert record.appearance_version_history[1].source_shot_id == "scene_003_shot_001"
    assert record.trace_sources[1]["source_job_id"] == "job-approved-closeup"
    assert record.needs_human_review is False


@pytest.mark.asyncio
async def test_adherence_score_includes_identity_continuity_dimension_from_legacy_evaluator(monkeypatch):
    from app.services.adherence_service import AdherenceService

    async def fake_vision(*args, **kwargs):
        return {
            "dimensions": {
                "character_state": {"score": 92, "evidence": "same wardrobe and face", "observed": "Maya matches"},
                "action": {"score": 90, "evidence": "", "observed": ""},
                "camera": {"score": 90, "evidence": "", "observed": ""},
                "lighting": {"score": 90, "evidence": "", "observed": ""},
                "environment_persistence": {"score": 90, "evidence": "", "observed": ""},
            },
            "temporal_drift": {"start_score": 90, "end_score": 90},
        }

    service = AdherenceService()
    monkeypatch.setattr(service, "_call_vision_model", fake_vision)

    score = await service.score_render_attempt(
        shot_id="scene_001_shot_001",
        attempt_n=1,
        video_url="/outputs/test.mp4",
        expected_slots={
            "character_state": "Maya enters.",
            "identity_continuity": "Use locked reference for Maya from scene_001_shot_000.",
            "action": "Maya enters.",
            "camera": "medium shot",
            "lighting": "soft interior",
            "environment_persistence": "apartment",
        },
        extracted_frames=["a.jpg", "b.jpg", "c.jpg"],
    )

    assert "identity_continuity" in score.dimensions
    assert score.dimensions["identity_continuity"].expected.startswith("Use locked reference")
    assert "identity_continuity" not in score.failed_slots


@pytest.mark.asyncio
async def test_adherence_flags_direct_identity_continuity_failure(monkeypatch):
    from app.services.adherence_service import AdherenceService

    async def fake_vision(*args, **kwargs):
        return {
            "dimensions": {
                "character_state": {"score": 88, "evidence": "character action is present", "observed": "Maya enters"},
                "identity_continuity": {
                    "score": 38,
                    "evidence": "face shape and hair color no longer match the approved reference",
                    "observed": "different apparent actor",
                },
                "action": {"score": 90, "evidence": "", "observed": ""},
                "camera": {"score": 90, "evidence": "", "observed": ""},
                "lighting": {"score": 90, "evidence": "", "observed": ""},
                "environment_persistence": {"score": 90, "evidence": "", "observed": ""},
            },
            "temporal_drift": {"start_score": 90, "end_score": 90},
        }

    service = AdherenceService()
    monkeypatch.setattr(service, "_call_vision_model", fake_vision)

    score = await service.score_render_attempt(
        shot_id="scene_004_shot_002",
        attempt_n=1,
        video_url="/outputs/test.mp4",
        expected_slots={
            "character_state": "Maya returns in the earlier jacket.",
            "identity_continuity": "Maya must match the approved face and full-body reference.",
            "action": "Maya enters.",
            "camera": "medium shot",
            "lighting": "exterior dusk",
            "environment_persistence": "street",
        },
        extracted_frames=["a.jpg", "b.jpg", "c.jpg"],
    )

    assert score.dimensions["identity_continuity"].observed == "different apparent actor"
    assert "identity_continuity" in score.failed_slots


def test_script_breakdown_bundle_includes_identity_memory_fields_and_warnings():
    bundle = ScriptParser().build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT
ELENA stares into a mirror.
MARCUS
We have to move now.
"""
    )
    assert isinstance(bundle.get("character_identity_memory"), dict)
    assert isinstance(bundle.get("provider_identity_context"), dict)
    assert isinstance(bundle.get("emotional_identity_continuity"), list)
    assert isinstance(bundle.get("identity_drift_warnings"), list)
    assert isinstance(bundle.get("continuity_warnings"), list)


def test_provider_text_omits_internal_review_status_but_keeps_review_metadata():
    record = {'character_id': 'nina', 'name': 'Nina', 'needs_human_review': True, 'default_appearance': {'wardrobe': ['olive jacket']}}
    context = character_identity_memory_service.build_provider_context_from_records([record])
    text = ' '.join(context['identity_lines'])
    assert 'not yet verified' not in text
    assert 'human review needed' not in text
    assert context['human_review_required'] is True
