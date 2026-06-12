import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import asyncio

from app.models.universe_graph import UniverseNode, UniverseRelationship, UniverseGraph, AbsenceReport
from app.services.director_memory_service import director_memory_service
from app.services.scene_intelligence_store import SceneIntelligenceStore
from app.services.script_intelligence_service import script_intelligence_service
from app.data.storage import get_storage

logger = logging.getLogger("studio-universe-graph")

class UniverseGraphService:
    def __init__(self):
        self.storage = get_storage("sqlite")
        self.scene_store = SceneIntelligenceStore()

    async def get_graph(self, project_id: str) -> UniverseGraph:
        nodes_raw = self.storage.get_universe_nodes(project_id)
        rels_raw = self.storage.get_universe_relationships(project_id)

        if not nodes_raw and not rels_raw:
            # Auto-populate on first load
            return await self.auto_populate(project_id)

        nodes = []
        for n in nodes_raw:
            n_copy = dict(n)
            n_copy["universe_tags"] = json.loads(n["universe_tags"]) if isinstance(n["universe_tags"], str) else n["universe_tags"]
            nodes.append(UniverseNode(**n_copy))

        relationships = [UniverseRelationship(**r) for r in rels_raw]
        
        # Populate connected_nodes
        for node in nodes:
            connected = []
            for rel in relationships:
                if rel.from_node == node.node_id:
                    connected.append(rel.to_node)
                elif rel.to_node == node.node_id:
                    connected.append(rel.from_node)
            node.connected_nodes = list(set(connected))

        return UniverseGraph(project_id=project_id, nodes=nodes, relationships=relationships)

    async def auto_populate(self, project_id: str) -> UniverseGraph:
        logger.info(f"Auto-populating universe graph for project {project_id}")
        
        nodes = []
        rels = []
        created_nodes = {} # name -> node_id

        # 1. Characters from Script Intelligence and Director Memory
        try:
            arc_analysis = await script_intelligence_service.analyze_character_arcs(project_id)
            memory_data = director_memory_service.get_memory(project_id)
            char_memory_entries = memory_data.get("characters", [])

            for char_prof in arc_analysis.characters:
                node_id = f"char-{uuid.uuid4().hex[:8]}"
                
                # Find matching memory entry
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

            # Add relationships from co-occurrence
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
            logger.warning(f"Character auto-population limited: {e}")

        # 2. Locations from Scene Intelligence
        try:
            scene_data = self.scene_store._load()
            records = scene_data.get("records", {})
            
            locations = {} # name -> {description, scenes}
            for scene_id, scene in records.items():
                # Filter by project (assuming project_id matches film_title or we can't filter easily)
                # In this project, scene_intelligence is often shared but we can try to find relevant scenes
                loc_name = scene.get("scene_name", "").split("-")[0].strip()
                if not loc_name: continue
                
                if loc_name not in locations:
                    locations[loc_name] = {"description": scene.get("director_notes", ""), "scenes": [scene_id]}
                else:
                    if scene_id not in locations[loc_name]["scenes"]:
                        locations[loc_name]["scenes"].append(scene_id)
            
            for loc_name, data in locations.items():
                if loc_name.lower() in created_nodes: continue # Avoid naming collisions
                
                node_id = f"loc-{uuid.uuid4().hex[:8]}"
                node = UniverseNode(
                    node_id=node_id,
                    project_id=project_id,
                    node_type="location",
                    name=loc_name,
                    description=data["description"] or f"A key location where {len(data['scenes'])} scenes take place.",
                    first_scene=data["scenes"][0],
                    last_scene=data["scenes"][-1]
                )
                nodes.append(node)
                created_nodes[loc_name.lower()] = node_id
                self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))
        except Exception as e:
            logger.warning(f"Location auto-population limited: {e}")

        # 3. Objects from Symbols in Director Memory
        try:
            memory_data = director_memory_service.get_memory(project_id)
            symbols = memory_data.get("symbols", [])
            for sym in symbols:
                name = sym.get("symbol")
                if not name or name.lower() in created_nodes: continue
                
                node_id = f"obj-{uuid.uuid4().hex[:8]}"
                node = UniverseNode(
                    node_id=node_id,
                    project_id=project_id,
                    node_type="object",
                    name=name,
                    description=sym.get("meaning", "") or "Significant prop or symbol."
                )
                nodes.append(node)
                created_nodes[name.lower()] = node_id
                self.storage.save_universe_node(node.model_dump(exclude={"connected_nodes"}))
        except Exception as e:
            logger.warning(f"Object auto-population limited: {e}")

        return UniverseGraph(project_id=project_id, nodes=nodes, relationships=rels)

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
                # Find node_id for this character
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
                
                # Connections
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
