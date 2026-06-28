import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import re

from app.models.universe_graph import UniverseNode, UniverseRelationship, UniverseGraph, AbsenceReport
from app.services.director_memory_service import director_memory_service
from app.services.scene_intelligence_store import SceneIntelligenceStore
from app.services.script_intelligence_service import script_intelligence_service
from app.data.storage import get_storage

logger = logging.getLogger("studio-universe-graph")

THEME_KEYWORDS = {
    "memory and loss": ["memory", "remember", "forget", "lost", "loss", "past", "father", "notebook"],
    "community displacement": ["community", "neighbor", "family", "together", "home", "displace", "evacuate", "resident", "future"],
    "environmental change": ["flood", "storm", "wave", "ocean", "sea", "water", "rise", "climate", "coastal", "shore", "tide", "wall"],
    "the tide / ocean / water": ["tide", "wave", "ocean", "water", "sea", "shore", "beach", "fishing", "boat", "coastal"],
}

class UniverseGraphService:
    def __init__(self):
        self.storage = get_storage("sqlite")
        self.scene_store = SceneIntelligenceStore()

    async def get_graph(self, project_id: str) -> UniverseGraph:
        nodes_raw = self.storage.get_universe_nodes(project_id)
        rels_raw = self.storage.get_universe_relationships(project_id)

        if not nodes_raw and not rels_raw:
            return await self.auto_populate(project_id)

        nodes = []
        for n in nodes_raw:
            n_copy = dict(n)
            n_copy["universe_tags"] = json.loads(n["universe_tags"]) if isinstance(n["universe_tags"], str) else n["universe_tags"]
            nodes.append(UniverseNode(**n_copy))

        relationships = [UniverseRelationship(**r) for r in rels_raw]

        for node in nodes:
            connected = []
            for rel in relationships:
                if rel.from_node == node.node_id:
                    connected.append(rel.to_node)
                elif rel.to_node == node.node_id:
                    connected.append(rel.from_node)
            node.connected_nodes = list(set(connected))

        return UniverseGraph(project_id=project_id, nodes=nodes, relationships=relationships)

    def _get_project_scenes(self, project_id: str) -> list[dict]:
        project = self.storage.get_project(project_id)
        if not project:
            return []
        if hasattr(project, "model_dump"):
            data = project.model_dump(mode="json")
        elif isinstance(project, dict):
            data = project
        else:
            return []
        summary = data.get("execution_summary") if isinstance(data.get("execution_summary"), dict) else {}
        return summary.get("scenes") if isinstance(summary.get("scenes"), list) else []

    def _extract_location_name(self, heading: str) -> str:
        heading = heading.strip()
        heading = re.sub(r"^(INT\.|EXT\.|INT/EXT\.)\s*", "", heading, flags=re.IGNORECASE).strip()
        parts = heading.split(",")
        return parts[0].strip().upper()

    def _detect_themes(self, text: str) -> list[str]:
        text_lower = text.lower()
        found = []
        for theme, keywords in THEME_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                found.append(theme)
        return found

    async def _populate_from_scenes(self, project_id: str, scenes: list[dict]) -> tuple[list[UniverseNode], list[UniverseRelationship]]:
        nodes = []
        rels = []
        created_nodes: dict[str, str] = {}

        character_scenes: dict[str, list[str]] = {}
        location_scenes: dict[str, list[str]] = {}
        all_text_parts: list[str] = []

        for scene in scenes:
            sid = scene.get("scene_id", "")
            chars = scene.get("characters") if isinstance(scene.get("characters"), list) else []
            heading = scene.get("heading") or scene.get("location") or ""
            text = scene.get("text") or scene.get("description") or ""
            all_text_parts.append(text)

            for char_name in chars:
                char_key = char_name.strip().upper()
                if not char_key:
                    continue
                if char_key not in character_scenes:
                    character_scenes[char_key] = []
                if sid not in character_scenes[char_key]:
                    character_scenes[char_key].append(sid)

            loc_name = self._extract_location_name(heading)
            if loc_name:
                if loc_name not in location_scenes:
                    location_scenes[loc_name] = []
                if sid not in location_scenes[loc_name]:
                    location_scenes[loc_name].append(sid)

        full_text = " ".join(all_text_parts)

        for char_key, scene_ids in character_scenes.items():
            node_id = f"char-{uuid.uuid4().hex[:8]}"
            name = char_key.title()
            node = UniverseNode(
                node_id=node_id,
                project_id=project_id,
                node_type="character",
                name=name,
                description=f"{name} appears in {len(scene_ids)} scene(s).",
                first_scene=scene_ids[0],
                last_scene=scene_ids[-1],
            )
            nodes.append(node)
            created_nodes[char_key] = node_id
            self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))

        for loc_key, scene_ids in location_scenes.items():
            if loc_key in created_nodes:
                continue
            node_id = f"loc-{uuid.uuid4().hex[:8]}"
            name = loc_key.title()
            node = UniverseNode(
                node_id=node_id,
                project_id=project_id,
                node_type="location",
                name=name,
                description=f"A key location where {len(scene_ids)} scene(s) take place.",
                first_scene=scene_ids[0],
                last_scene=scene_ids[-1],
            )
            nodes.append(node)
            created_nodes[loc_key] = node_id
            self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))

        themes = self._detect_themes(full_text)
        for theme in themes:
            if theme.upper() in created_nodes:
                continue
            node_id = f"lore-{uuid.uuid4().hex[:8]}"
            node = UniverseNode(
                node_id=node_id,
                project_id=project_id,
                node_type="lore",
                name=theme.title(),
                description=f"Thematic element: {theme}",
            )
            nodes.append(node)
            created_nodes[theme.upper()] = node_id
            self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))

        for scene in scenes:
            sid = scene.get("scene_id", "")
            chars = scene.get("characters") if isinstance(scene.get("characters"), list) else []
            heading = scene.get("heading") or scene.get("location") or ""
            loc_name = self._extract_location_name(heading)

            loc_id = created_nodes.get(loc_name)
            for char_key in [c.strip().upper() for c in chars if c.strip()]:
                char_id = created_nodes.get(char_key)
                if char_id and loc_id:
                    rel_exists = any(
                        r.from_node == char_id and r.to_node == loc_id
                        for r in rels
                    )
                    if not rel_exists:
                        rel_id = f"rel-{uuid.uuid4().hex[:8]}"
                        rels.append(UniverseRelationship(
                            relationship_id=rel_id,
                            project_id=project_id,
                            from_node=char_id,
                            to_node=loc_id,
                            relationship_type="appears_at",
                            description=f"{char_key.title()} appears at {loc_name.title()} in {sid}.",
                        ))
                        self.storage.save_universe_relationship(rels[-1].model_dump())

            char_keys_in_scene = [c.strip().upper() for c in chars if c.strip()]
            for i, c1 in enumerate(char_keys_in_scene):
                for c2 in char_keys_in_scene[i + 1:]:
                    id1 = created_nodes.get(c1)
                    id2 = created_nodes.get(c2)
                    if id1 and id2:
                        rel_exists = any(
                            (r.from_node == id1 and r.to_node == id2) or
                            (r.from_node == id2 and r.to_node == id1)
                            for r in rels
                        )
                        if not rel_exists:
                            rel_id = f"rel-{uuid.uuid4().hex[:8]}"
                            rels.append(UniverseRelationship(
                                relationship_id=rel_id,
                                project_id=project_id,
                                from_node=id1,
                                to_node=id2,
                                relationship_type="co-occurrence",
                                description=f"{c1.title()} and {c2.title()} appear together in {sid}.",
                            ))
                            self.storage.save_universe_relationship(rels[-1].model_dump())

        return nodes, rels

    async def auto_populate(self, project_id: str) -> UniverseGraph:
        logger.info(f"Auto-populating universe graph for project {project_id}")

        self.storage.delete_universe_project_data(project_id)

        nodes = []
        rels = []

        scenes = self._get_project_scenes(project_id)
        if scenes:
            scene_nodes, scene_rels = await self._populate_from_scenes(project_id, scenes)
            nodes.extend(scene_nodes)
            rels.extend(scene_rels)

        if not nodes:
            try:
                arc_analysis = await script_intelligence_service.analyze_character_arcs(project_id)
                memory_data = director_memory_service.get_memory(project_id)
                char_memory_entries = memory_data.get("characters", [])
                created_nodes = {}

                for char_prof in arc_analysis.characters:
                    node_id = f"char-{uuid.uuid4().hex[:8]}"
                    char_mem = next((c for c in char_memory_entries
                                    if (c.get("character") or c.get("name") or "").lower() == char_prof.name.lower()), {})
                    description = char_mem.get("backstory_notes") or ""
                    if not description and char_mem.get("personality_traits"):
                        description = f"Character known for being {', '.join(char_mem['personality_traits'])}."
                    node = UniverseNode(
                        node_id=node_id,
                        project_id=project_id,
                        node_type="character",
                        name=char_prof.name,
                        description=description or "Established character in the story.",
                        first_scene=char_prof.first_appearance_scene,
                        last_scene=char_prof.scene_ids[-1] if char_prof.scene_ids else None,
                        universe_tags=char_mem.get("tags", [])
                    )
                    nodes.append(node)
                    created_nodes[char_prof.name.lower()] = node_id
                    self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))

                for rel in arc_analysis.relationships:
                    from_id = created_nodes.get(rel.character_a.lower())
                    to_id = created_nodes.get(rel.character_b.lower())
                    if from_id and to_id:
                        relationship_id = f"rel-{uuid.uuid4().hex[:8]}"
                        universe_rel = UniverseRelationship(
                            relationship_id=relationship_id,
                            project_id=project_id,
                            from_node=from_id,
                            to_node=to_id,
                            relationship_type="co-occurrence",
                            description=f"Appeared in {rel.shared_scene_count} scenes together."
                        )
                        rels.append(universe_rel)
                        self.storage.save_universe_relationship(universe_rel.model_dump())
            except Exception as e:
                logger.warning(f"Character arc auto-population limited: {e}")

        return UniverseGraph(project_id=project_id, nodes=nodes, relationships=rels)

    def auto_populate_from_scenes(self, project_id: str) -> None:
        scenes = self._get_project_scenes(project_id)
        if not scenes:
            logger.info(f"No scenes found for {project_id}, skipping sync auto-populate")
            return
        self.storage.delete_universe_project_data(project_id)
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            nodes, rels = loop.run_until_complete(self._populate_from_scenes(project_id, scenes))
            loop.close()
            logger.info(f"Auto-populated {len(nodes)} nodes and {len(rels)} relationships for {project_id}")
        except Exception as e:
            logger.warning(f"Sync auto-populate failed for {project_id}: {e}")

    def save_node(self, project_id: str, node: UniverseNode) -> bool:
        node.project_id = project_id
        node.updated_at = datetime.now().isoformat()
        return self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))

    def delete_node(self, node_id: str) -> bool:
        return self.storage.delete_universe_node(node_id)

    def save_relationship(self, project_id: str, rel: UniverseRelationship) -> bool:
        rel.project_id = project_id
        return self.storage.save_universe_relationship(rel.model_dump())

    def delete_relationship(self, relationship_id: str) -> bool:
        return self.storage.delete_universe_relationship(relationship_id)

    async def detect_absences(self, project_id: str) -> AbsenceReport:
        graph = await self.get_graph(project_id)
        try:
            arc_analysis = await script_intelligence_service.analyze_character_arcs(project_id)
            absences = []
            for gap in arc_analysis.arc_gaps:
                node = next((n for n in graph.nodes if n.name.lower() == gap.character_name.lower()), None)
                if node:
                    absences.append({
                        "node_id": node.node_id,
                        "name": node.name,
                        "type": "character",
                        "last_seen_scene": gap.gap_start_scene,
                        "advisory": gap.advisory
                    })
            return AbsenceReport(project_id=project_id, absences=absences)
        except:
            return AbsenceReport(project_id=project_id, absences=[])

    async def export_bible(self, project_id: str) -> str:
        graph = await self.get_graph(project_id)
        bible = f"# Universe Bible: {project_id}\n\n"
        bible += f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n"

        for ntype in ['character', 'location', 'object', 'lore']:
            type_nodes = [n for n in graph.nodes if n.node_type == ntype]
            if not type_nodes: continue
            bible += f"## {ntype.title()}s\n\n"
            for node in type_nodes:
                bible += f"### {node.name}\n"
                if node.description:
                    bible += f"{node.description}\n\n"
                if node.first_scene:
                    bible += f"- **First Appearance:** {node.first_scene}\n"
                if node.last_scene:
                    bible += f"- **Last Appearance:** {node.last_scene}\n"
                connected = [n.name for n in graph.nodes if n.node_id in node.connected_nodes]
                if connected:
                    bible += f"- **Connections:** {', '.join(connected)}\n"
                bible += "\n"

        bible += "## Relationships\n\n"
        for rel in graph.relationships:
            from_node = next((n.name for n in graph.nodes if n.node_id == rel.from_node), rel.from_node)
            to_node = next((n.name for n in graph.nodes if n.node_id == rel.to_node), rel.to_node)
            bible += f"- **{from_node}** ↔ **{to_node}**: {rel.relationship_type}"
            if rel.description:
                bible += f" ({rel.description})"
            bible += "\n"

        return bible

universe_graph_service = UniverseGraphService()
