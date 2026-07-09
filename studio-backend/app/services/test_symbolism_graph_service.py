from __future__ import annotations

from app.services.script_parser import ScriptParser
from app.services.symbolism_graph_service import symbolism_graph_service


def test_symbolism_graph_detects_recurring_imagery_phrases_and_connections():
    scenes = [
        {
            "scene_id": "scene_001",
            "heading": "INT. HALLWAY - NIGHT",
            "text": "A red mirror reflects dread as rain hits the window. red mirror.",
        },
        {
            "scene_id": "scene_002",
            "heading": "EXT. STREET - NIGHT",
            "text": "The red mirror returns beside a black door in storm rain.",
        },
    ]
    result = symbolism_graph_service.build_symbolism_graph(scenes, [], {"current_form": "embedded"})

    assert isinstance(result.get("symbolism_nodes"), list)
    assert any(node.get("motif") == "red" for node in result["symbolism_nodes"])
    assert any(row.get("motif") == "mirror" for row in result.get("recurring_imagery", []))
    assert isinstance(result.get("symbolism_graph_visualization"), dict)
    assert "nodes" in result["symbolism_graph_visualization"]
    assert "edges" in result["symbolism_graph_visualization"]
    assert isinstance(result.get("symbolism_connections"), list)


def test_script_breakdown_bundle_includes_symbolism_graph_contexts():
    bundle = ScriptParser().build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT
A red mirror watches over a black door.

EXT. ROOFTOP - DAWN
The red mirror appears again as hope rises.
"""
    )

    assert isinstance(bundle.get("symbolism_nodes"), list)
    assert isinstance(bundle.get("recurring_imagery"), list)
    assert isinstance(bundle.get("recurring_phrases"), list)
    assert isinstance(bundle.get("emotional_callbacks"), list)
    assert isinstance(bundle.get("environmental_symbolism"), list)
    assert isinstance(bundle.get("symbolism_connections"), list)
    assert isinstance(bundle.get("symbolism_graph_visualization"), dict)
    assert isinstance(bundle.get("memory_archivist_symbolism_context"), dict)
    assert isinstance(bundle.get("emotional_arc_symbolism_context"), dict)
    assert isinstance(bundle.get("director_symbolism_context"), dict)

