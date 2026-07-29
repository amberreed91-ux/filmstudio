from __future__ import annotations

from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models.studio_knowledge import (
    KnowledgeBibleCreateRequest,
    KnowledgeContextRequest,
    KnowledgeRebuildRequest,
    KnowledgeSourceType,
)
from app.models.memory import FilmLevelMemory
from app.models import StyleSignature
from app.services.spine_service import SpineService
from app.services.studio_knowledge_service import StudioKnowledgeService


class FakeProjectStore:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def get_director_memory(self, project_id: str):  # noqa: ARG002
        return {
            "motifs": [
                {
                    "entry_id": "dm_motif_1",
                    "motif": "mirror",
                    "keyword": "reflection",
                }
            ],
            "symbols": [],
            "characters": [],
            "themes": [],
            "notes": [],
            "debates": [],
        }

    def list_creative_memories(self, project_id: str):  # noqa: ARG002
        return [
            {
                "memory_id": "memory_1",
                "decision_type": "revision_emphasis",
                "user_note": "Preserve emotional residue over structural clarity.",
                "inferred_tradeoff": "emotional_residue",
                "source_context": {"gate_id": "gate_1"},
            }
        ]

    def save_creative_memory(self, project_id: str, memory_data: dict):  # pragma: no cover - should not be called
        self.saved.append({"project_id": project_id, "memory_data": memory_data})
        return {"memory_id": "unexpected"}


def _service(tmp_path: Path) -> StudioKnowledgeService:
    storage = DatabaseStorage(str(tmp_path))
    return StudioKnowledgeService(storage=storage, project_store=FakeProjectStore())


def test_register_bible_atomizes_without_saving_creative_memory(tmp_path: Path):
    service = _service(tmp_path)

    response = service.register_bible(
        "project-knowledge",
        KnowledgeBibleCreateRequest(
            title="Visual Bible",
            bible_type="visual",
            content="""
# Tone Rules
- The film must stay patient with tension.
- Never explain the mirror motif too early.

# Visual Style
- Use soft practical light when intimacy is fragile.
""",
        ),
    )

    assert response.bible.status == "atomized"
    assert response.sections
    assert len(response.atoms) == 3
    assert {atom.source_ref.source_type for atom in response.atoms} == {KnowledgeSourceType.BIBLE}
    assert service.project_store.saved == []


def test_rebuild_projects_existing_sources_and_context_records_trace(tmp_path: Path):
    service = _service(tmp_path)
    service.register_bible(
        "project-knowledge",
        KnowledgeBibleCreateRequest(
            title="Story Bible",
            bible_type="story",
            content="- The story should keep the mother unseen until the final act.",
        ),
    )

    run = service.build_index("project-knowledge", KnowledgeRebuildRequest(force=False))
    assert run.status == "complete"
    assert "creative_memory" in {source.value for source in run.source_types}
    assert "director_memory" in {source.value for source in run.source_types}

    pack = service.get_context_pack(
        "project-knowledge",
        KnowledgeContextRequest(
            department="co_director",
            purpose="scene_guidance",
            max_atoms=8,
            consumer_id="test",
        ),
    )

    assert pack.trace_id
    assert pack.atoms
    assert pack.metadata["canonical_state_mutated"] is False
    trace = service.get_trace("project-knowledge", pack.trace_id)
    assert trace.selected_atom_ids == [atom.atom_id for atom in pack.atoms]
    assert trace.source_counts


def test_rebuild_projects_continuity_graph_atoms(tmp_path: Path):
    service = _service(tmp_path)
    service.storage.save_continuity_graph(
        "project-knowledge",
        {
            "character_knowledge_nodes": [
                {
                    "scene_id": "scene_02",
                    "value": {
                        "character": "Mara",
                        "knowledge_events": ["letter_hidden"],
                    },
                }
            ]
        },
    )

    run = service.build_index("project-knowledge", KnowledgeRebuildRequest(force=False))
    assert "continuity_graph" in {source.value for source in run.source_types}

    atoms = service.list_atoms(
        "project-knowledge",
        filters={"source_type": "continuity_graph"},
    )
    assert atoms
    assert atoms[0].scope_id == "scene_02"
    assert "Mara" in atoms[0].canonical_text


def test_rebuild_projects_creative_spine_constraints(tmp_path: Path):
    storage = DatabaseStorage(str(tmp_path))
    spine = SpineService()
    spine.create_spine_from_memory(
        "project-knowledge",
        FilmLevelMemory(
            film_id="project-knowledge",
            project_id="project-knowledge",
            story_thesis="Grief becomes legible only through what remains unsaid.",
            emotional_contract="The audience should feel quiet recognition, not victory.",
            genre_lane="intimate mystery",
        ),
    )
    service = StudioKnowledgeService(storage=storage, project_store=FakeProjectStore(), spine_service=spine)

    run = service.build_index("project-knowledge", KnowledgeRebuildRequest(force=False))
    assert "creative_spine" in {source.value for source in run.source_types}

    atoms = service.list_atoms(
        "project-knowledge",
        filters={"source_type": "creative_spine"},
    )
    assert atoms
    assert any(atom.authority_level == "spine_frozen" for atom in atoms)


def test_rebuild_projects_style_signature_atoms(tmp_path: Path):
    service = _service(tmp_path)
    service.storage.save_style_signature(
        StyleSignature(
            signature_id="style-1",
            project_id="project-knowledge",
            framing_tendencies=["close frames under pressure"],
            pacing_patterns=["patient holds"],
            color_motifs=["muted amber"],
            camera_movement_patterns=["slow push"],
            confidence=0.5,
            advisory_only=True,
            created_at="2026-01-01T00:00:00Z",
        )
    )

    run = service.build_index("project-knowledge", KnowledgeRebuildRequest(force=False))
    assert "style_signature" in {source.value for source in run.source_types}

    atoms = service.list_atoms(
        "project-knowledge",
        filters={"source_type": "style_signature"},
    )
    assert atoms
    assert atoms[0].atom_type == "style_rule"
