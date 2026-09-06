from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models.studio_knowledge import (
    KnowledgeAtom,
    KnowledgeAtomType,
    KnowledgeAuthorityLevel,
    KnowledgeBible,
    KnowledgeBibleStatus,
    KnowledgeConfidenceLabel,
    KnowledgeScopeType,
    KnowledgeSourceRef,
    KnowledgeSourceType,
)
from app.services import render as render_module
from app.services.character_name_matching import text_mentions_character
from app.services.render import RenderService, _infer_scene_characters_from_text
from app.services.render_context_enrichment_service import (
    render_context_enrichment_service,
)


def _storage(tmp_path: Path) -> DatabaseStorage:
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return DatabaseStorage(str(db_dir))


def _now() -> str:
    return datetime.now().isoformat()


def _save_bible(
    storage: DatabaseStorage,
    *,
    project_id: str,
    bible_id: str,
    title: str,
    bible_type: str,
) -> None:
    now = _now()
    storage.save_knowledge_bible(
        KnowledgeBible(
            bible_id=bible_id,
            project_id=project_id,
            title=title,
            bible_type=bible_type,
            status=KnowledgeBibleStatus.ATOMIZED,
            atom_count=1,
            created_at=now,
            updated_at=now,
        ),
        "",
    )


def _save_atom(
    storage: DatabaseStorage,
    *,
    project_id: str,
    atom_id: str,
    source_id: str,
    atom_type: KnowledgeAtomType,
    text: str,
    scope_type: KnowledgeScopeType = KnowledgeScopeType.PROJECT,
    scope_id: str = "",
) -> None:
    now = _now()
    storage.save_knowledge_atom(
        KnowledgeAtom(
            atom_id=atom_id,
            project_id=project_id,
            source_ref=KnowledgeSourceRef(
                source_type=KnowledgeSourceType.BIBLE,
                source_id=source_id,
                source_label=source_id,
            ),
            atom_type=atom_type,
            authority_level=KnowledgeAuthorityLevel.BIBLE_COMMITTED,
            scope_type=scope_type,
            scope_id=scope_id,
            canonical_text=text,
            confidence_label=KnowledgeConfidenceLabel.DIRECT,
            source_fingerprint=atom_id,
            created_at=now,
            updated_at=now,
        )
    )


def test_character_name_matching_never_treats_moments_as_mom():
    assert text_mentions_character("MOM crosses the street.", "MOM")
    assert not text_mentions_character("Maya watches small moments pass.", "MOM")

    inferred = _infer_scene_characters_from_text(
        [{"name": "MAYA"}, {"name": "MOM"}],
        primary_text="Maya watches small moments people take for granted.",
        fallback_text="",
    )

    assert inferred == ["MAYA"]


def test_render_context_selects_project_bible_and_creative_spine(tmp_path):
    storage = _storage(tmp_path)
    project_id = "proj-render-canon-selection"
    _save_bible(
        storage,
        project_id=project_id,
        bible_id="bible-project",
        title="Project Bible",
        bible_type="project_bible",
    )
    _save_bible(
        storage,
        project_id=project_id,
        bible_id="bible-spine",
        title="Creative Spine",
        bible_type="creative_spine",
    )
    _save_atom(
        storage,
        project_id=project_id,
        atom_id="atom-project-story",
        source_id="bible-project",
        atom_type=KnowledgeAtomType.STORY_RULE,
        text="Keep patient tension in every emotional handoff.",
    )
    _save_atom(
        storage,
        project_id=project_id,
        atom_id="atom-spine-light",
        source_id="bible-spine",
        atom_type=KnowledgeAtomType.TONE_RULE,
        text="Use practical light as emotional evidence.",
    )
    _save_atom(
        storage,
        project_id=project_id,
        atom_id="atom-other-scene",
        source_id="bible-project",
        atom_type=KnowledgeAtomType.MOTIF,
        text="A red kite belongs only in scene nine.",
        scope_type=KnowledgeScopeType.SCENE,
        scope_id="scene_009",
    )
    _save_atom(
        storage,
        project_id=project_id,
        atom_id="atom-offscreen-character",
        source_id="bible-project",
        atom_type=KnowledgeAtomType.CHARACTER_FACT,
        text="MOM: Maya remembers her silver bob and blue cardigan.",
    )

    context = render_context_enrichment_service.build_context(
        project_id=project_id,
        scene_id="scene_001",
        shot_id="scene_001_shot_001",
        scene_data={"location": "Downtown Chicago", "characters": ["Maya"]},
        character_names=["Maya"],
        storage=storage,
    )

    assert set(context.selected_sources) == {"bible", "creative_spine"}
    assert set(context.selected_atom_ids) == {
        "atom-project-story",
        "atom-spine-light",
    }
    assert "patient tension" in context.slot_guidance["action"]
    assert "practical light" in context.slot_guidance["lighting"]


def test_generic_render_uses_visible_character_and_saved_canon(
    tmp_path,
    monkeypatch,
):
    storage = _storage(tmp_path)
    project_id = "proj-shared-render-fix"
    storage.save_character(
        project_id,
        "MAYA",
        {
            "visual_prompt_summary": (
                "A lean Black woman in her late 20s with deep brown skin and "
                "natural locs, wearing layered earth-toned practical clothing."
            )
        },
    )
    storage.save_character(
        project_id,
        "MOM",
        {
            "visual_prompt_summary": (
                "A white woman in her sixties with a silver bob and a blue cardigan."
            )
        },
    )
    _save_bible(
        storage,
        project_id=project_id,
        bible_id="project-bible",
        title="Project Bible",
        bible_type="project_bible",
    )
    _save_bible(
        storage,
        project_id=project_id,
        bible_id="creative-spine",
        title="Creative Spine",
        bible_type="creative_spine",
    )
    _save_atom(
        storage,
        project_id=project_id,
        atom_id="canon-story",
        source_id="project-bible",
        atom_type=KnowledgeAtomType.STORY_RULE,
        text="Keep patient tension through the handoff.",
    )
    _save_atom(
        storage,
        project_id=project_id,
        atom_id="canon-light",
        source_id="creative-spine",
        atom_type=KnowledgeAtomType.TONE_RULE,
        text="Use practical light as emotional evidence.",
    )

    def fake_project(requested_project_id: str):
        return {
            "project_id": requested_project_id,
            "execution_summary": {
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "heading": "EXT. DOWNTOWN CHICAGO - GOLDEN HOUR",
                        "location": "Downtown Chicago",
                        "time_of_day": "golden hour",
                        "text": (
                            "Maya walks through the city watching small moments "
                            "people take for granted."
                        ),
                        "characters": [],
                    }
                ]
            },
        }

    monkeypatch.setattr(render_module, "_storage", storage)
    monkeypatch.setattr(render_module.project_store, "get_project", fake_project)
    monkeypatch.setattr(
        "app.services.character_visual_reference_service.project_store.get_project",
        fake_project,
    )
    monkeypatch.setattr(
        "app.data.storage.get_storage",
        lambda *_args, **_kwargs: storage,
    )

    job = RenderService().create_job(
        project_id=project_id,
        shot_id="scene_001_shot_001",
        provider="simulated",
        prompt="",
    )

    prompt = job.input_payload.prompt
    character_slot = job.input_payload.parameters["prompt_slots"]["character_state"]
    knowledge = job.input_payload.parameters["render_knowledge_context"]
    identity = job.input_payload.parameters["character_identity_context"]

    assert "Only MAYA visible; no extras" in character_slot
    assert "Black woman" in character_slot
    assert "late 20s" in character_slot
    assert "deep brown skin" in character_slot
    assert "natural locs" in character_slot
    assert "MOM" not in character_slot
    assert "patient tension" in prompt
    assert "practical light" in prompt
    assert set(knowledge["selected_sources"]) == {"bible", "creative_spine"}
    assert set(knowledge["selected_atom_ids"]) == {"canon-story", "canon-light"}
    assert len(identity["identity_lines"]) == 1
    assert identity["identity_lines"][0].startswith("MAYA ")
