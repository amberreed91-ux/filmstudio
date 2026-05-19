from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List

from app.models.symbolism_node import SymbolismNode


class SymbolismGraphService:
    COLORS = {"red", "blue", "green", "black", "white", "gold", "silver", "violet", "amber", "neon"}
    OBJECTS = {"mirror", "door", "window", "clock", "watch", "key", "water", "rain", "phone", "train", "shadow", "light"}
    EMOTION_MARKERS = {
        "grief": {"grief", "loss", "mourning"},
        "fear": {"fear", "dread", "panic", "threat"},
        "hope": {"hope", "resolve", "dawn", "rise"},
        "guilt": {"guilt", "shame", "regret"},
        "love": {"love", "tender", "embrace"},
    }

    def _scene_text(self, scene: Dict[str, Any]) -> str:
        parts = [scene.get("heading"), scene.get("text"), scene.get("description"), scene.get("emotional_target")]
        return " ".join(str(p).strip() for p in parts if isinstance(p, str) and p.strip())

    def _tokens(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-Z']+", text.lower())

    def _detect_meaning(self, text: str) -> str:
        lowered = text.lower()
        scores = []
        for meaning, markers in self.EMOTION_MARKERS.items():
            hits = sum(1 for marker in markers if marker in lowered)
            if hits > 0:
                scores.append((hits, meaning))
        scores.sort(reverse=True)
        return scores[0][1] if scores else "ambiguity"

    def build_symbolism_graph(
        self,
        scenes: Any,
        emotional_arc_profiles: Any = None,
        motif_state: Any = None,
    ) -> Dict[str, Any]:
        scene_list = scenes if isinstance(scenes, list) else []
        motif_counter: Dict[str, int] = defaultdict(int)
        phrase_counter: Dict[str, int] = defaultdict(int)
        env_counter: Dict[str, int] = defaultdict(int)
        style_boost = str(motif_state.get("current_form", "")) if isinstance(motif_state, dict) else ""

        for scene in scene_list:
            if not isinstance(scene, dict):
                continue
            text = self._scene_text(scene)
            tokens = self._tokens(text)
            for token in tokens:
                if token in self.COLORS or token in self.OBJECTS:
                    motif_counter[token] += 1
            for idx in range(max(0, len(tokens) - 1)):
                phrase = f"{tokens[idx]} {tokens[idx + 1]}"
                if len(phrase) > 6:
                    phrase_counter[phrase] += 1
            heading = str(scene.get("heading", "")).lower()
            if "rain" in heading or "storm" in heading or "night" in heading:
                env_counter["weather_dread"] += 1
            if "dawn" in heading or "sunrise" in heading:
                env_counter["hope_light"] += 1

        recurring_imagery = sorted(
            [{"motif": motif, "frequency": freq} for motif, freq in motif_counter.items() if freq >= 2],
            key=lambda row: (-row["frequency"], row["motif"]),
        )
        recurring_phrases = sorted(
            [{"phrase": phrase, "frequency": freq} for phrase, freq in phrase_counter.items() if freq >= 2],
            key=lambda row: (-row["frequency"], row["phrase"]),
        )[:8]
        emotional_callbacks = self._build_emotional_callbacks(emotional_arc_profiles)
        environmental_symbolism = sorted(
            [{"symbol": symbol, "frequency": freq} for symbol, freq in env_counter.items() if freq >= 1],
            key=lambda row: (-row["frequency"], row["symbol"]),
        )

        nodes: List[SymbolismNode] = []
        for row in recurring_imagery:
            motif = row["motif"]
            nodes.append(
                SymbolismNode(
                    motif=motif,
                    object=motif if motif in self.OBJECTS else "",
                    color=motif if motif in self.COLORS else "",
                    emotional_meaning=self._detect_meaning(f"{motif} {style_boost}".strip()),
                    recurrence_frequency=row["frequency"],
                )
            )

        node_dicts = [node.model_dump() for node in nodes]
        edges = self._build_edges(node_dicts)
        visualization = {
            "nodes": node_dicts,
            "edges": edges,
            "layout": "force",
            "legend": "line weight reflects symbolic co-recurrence",
        }
        return {
            "symbolism_nodes": node_dicts,
            "recurring_imagery": recurring_imagery,
            "recurring_phrases": recurring_phrases,
            "emotional_callbacks": emotional_callbacks,
            "environmental_symbolism": environmental_symbolism,
            "symbolism_connections": edges,
            "symbolism_graph_visualization": visualization,
        }

    def _build_emotional_callbacks(self, emotional_arc_profiles: Any) -> List[Dict[str, Any]]:
        rows = emotional_arc_profiles if isinstance(emotional_arc_profiles, list) else []
        callbacks: List[Dict[str, Any]] = []
        previous_scene = ""
        previous_tension = 0.0
        for row in rows:
            if not isinstance(row, dict):
                row = row.model_dump() if hasattr(row, "model_dump") else {}
            scene_id = str(row.get("scene_id", "")).strip()
            tension = float(row.get("tension", 0.0))
            if previous_scene and abs(tension - previous_tension) >= 0.2:
                callbacks.append(
                    {
                        "from_scene": previous_scene,
                        "to_scene": scene_id,
                        "callback_type": "emotional_shift",
                        "delta": round(tension - previous_tension, 3),
                    }
                )
            previous_scene = scene_id
            previous_tension = tension
        return callbacks

    def _build_edges(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        for idx in range(len(nodes)):
            for jdx in range(idx + 1, len(nodes)):
                first = nodes[idx]
                second = nodes[jdx]
                shared_domain = (
                    (first.get("color") and second.get("color"))
                    or (first.get("object") and second.get("object"))
                    or (first.get("emotional_meaning") == second.get("emotional_meaning"))
                )
                if not shared_domain:
                    continue
                weight = min(
                    int(first.get("recurrence_frequency", 0)),
                    int(second.get("recurrence_frequency", 0)),
                )
                edges.append(
                    {
                        "source": first.get("motif", ""),
                        "target": second.get("motif", ""),
                        "weight": max(1, weight),
                    }
                )
        return edges


symbolism_graph_service = SymbolismGraphService()

