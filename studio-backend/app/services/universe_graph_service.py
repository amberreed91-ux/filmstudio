import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import re

from app.models.universe_graph import UniverseNode, UniverseRelationship, UniverseGraph, AbsenceReport
from app.services import universe_id_resolution as id_resolution
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

    def _derive_scene_specs(
        self, project_id: str, scenes: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Derive node/relationship specs from scenes WITHOUT writing anything.

        Node specs carry a stable ``key`` of ``(project_id, node_type,
        normalized name[, first scene for locations])``. Relationship specs
        reference endpoint keys, resolved to node IDs during upsert. The
        extraction mirrors the legacy derivation exactly; only ID assignment
        moved to :meth:`rebuild_universe_graph_from_scenes` so rebuilds are stable.
        """
        node_specs: list[dict] = []
        rel_specs: list[dict] = []
        created_keys: dict[str, tuple] = {}

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
            name = char_key.title()
            key = id_resolution.stable_universe_key(project_id, "character", name)
            node_specs.append(
                {
                    "key": key,
                    "node_type": "character",
                    "name": name,
                    "description": f"{name} appears in {len(scene_ids)} scene(s).",
                    "first_scene": scene_ids[0],
                    "last_scene": scene_ids[-1],
                    "universe_tags": [],
                }
            )
            created_keys[char_key] = key

        for loc_key, scene_ids in location_scenes.items():
            if loc_key in created_keys:
                continue
            name = loc_key.title()
            key = (
                *id_resolution.stable_universe_key(project_id, "location", name),
                scene_ids[0],
            )
            node_specs.append(
                {
                    "key": key,
                    "node_type": "location",
                    "name": name,
                    "description": f"A key location where {len(scene_ids)} scene(s) take place.",
                    "first_scene": scene_ids[0],
                    "last_scene": scene_ids[-1],
                    "universe_tags": [],
                }
            )
            created_keys[loc_key] = key

        themes = self._detect_themes(full_text)
        for theme in themes:
            if theme.upper() in created_keys:
                continue
            name = theme.title()
            key = id_resolution.stable_universe_key(project_id, "lore", name)
            node_specs.append(
                {
                    "key": key,
                    "node_type": "lore",
                    "name": name,
                    "description": f"Thematic element: {theme}",
                    "first_scene": None,
                    "last_scene": None,
                    "universe_tags": [],
                }
            )
            created_keys[theme.upper()] = key

        for scene in scenes:
            sid = scene.get("scene_id", "")
            chars = scene.get("characters") if isinstance(scene.get("characters"), list) else []
            heading = scene.get("heading") or scene.get("location") or ""
            loc_name = self._extract_location_name(heading)

            loc_key = created_keys.get(loc_name)
            for char_key in [c.strip().upper() for c in chars if c.strip()]:
                char_key_resolved = created_keys.get(char_key)
                if char_key_resolved and loc_key:
                    rel_key = (char_key_resolved, loc_key, "appears_at")
                    if not any(
                        (r["from_key"], r["to_key"], r["relationship_type"]) == rel_key
                        for r in rel_specs
                    ):
                        rel_specs.append(
                            {
                                "from_key": char_key_resolved,
                                "to_key": loc_key,
                                "relationship_type": "appears_at",
                                "description": f"{char_key.title()} appears at {loc_name.title()} in {sid}.",
                            }
                        )

            char_keys_in_scene = [c.strip().upper() for c in chars if c.strip()]
            for i, c1 in enumerate(char_keys_in_scene):
                for c2 in char_keys_in_scene[i + 1:]:
                    key1 = created_keys.get(c1)
                    key2 = created_keys.get(c2)
                    if key1 and key2:
                        if not any(
                            {r["from_key"], r["to_key"]} == {key1, key2}
                            and r["relationship_type"] == "co-occurrence"
                            for r in rel_specs
                        ):
                            rel_specs.append(
                                {
                                    "from_key": key1,
                                    "to_key": key2,
                                    "relationship_type": "co-occurrence",
                                    "description": f"{c1.title()} and {c2.title()} appear together in {sid}.",
                                }
                            )

        return node_specs, rel_specs

    def rebuild_universe_graph_from_scenes(
        self, project_id: str, scenes: list[dict] | None = None
    ) -> dict:
        """Rebuild a project's universe graph WITHOUT wiping anything.

        Upserts every derived node/relationship by stable key: an existing
        node (or relationship) matching the derived stable key keeps its
        current ID; only genuinely new entries mint deterministic hash IDs.
        Existing nodes absent from the new source are never deleted — a
        referenced one is preserved and reported, an unreferenced one is
        kept and listed. Returns an owner-visible report dict; never raises
        for preserved nodes so scene actions are never blocked.
        """
        if scenes is None:
            scenes = self._get_project_scenes(project_id)
        node_specs, rel_specs = self._derive_scene_specs(project_id, scenes or [])

        existing_nodes = {
            str(row.get("node_id")): row
            for row in (self.storage.get_universe_nodes(project_id) or [])
            if isinstance(row, dict) and str(row.get("node_id") or "")
        }
        by_key: dict[tuple, list[dict]] = {}
        for row in existing_nodes.values():
            key = self._existing_node_key(project_id, row)
            by_key.setdefault(key, []).append(row)

        key_to_id: dict[tuple, str] = {}
        adopted: list[str] = []
        created: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []
        ambiguous: list[dict] = []
        for spec in node_specs:
            key = spec["key"]
            matches = by_key.get(key, [])
            needs_save = False
            if len(matches) == 1:
                node_id = str(matches[0].get("node_id"))
                adopted.append(node_id)
                if self._node_content_differs(matches[0], spec):
                    updated.append(node_id)
                    needs_save = True
                else:
                    unchanged.append(node_id)
            elif not matches:
                node_id = self._mint_stable_node_id(
                    project_id, spec["node_type"], spec["name"], set(existing_nodes) | set(created)
                )
                created.append(node_id)
                needs_save = True
            else:
                node_id = str(sorted(str(r.get("node_id")) for r in matches)[0])
                adopted.append(node_id)
                matched = next(
                    r for r in matches if str(r.get("node_id")) == node_id
                )
                if self._node_content_differs(matched, spec):
                    updated.append(node_id)
                    needs_save = True
                else:
                    unchanged.append(node_id)
                ambiguous.append(
                    {
                        "key": [str(part) for part in key],
                        "node_ids": sorted(str(r.get("node_id")) for r in matches),
                        "adopted": node_id,
                    }
                )
            key_to_id[key] = node_id
            if needs_save:
                self.storage.save_universe_node(
                    {
                        "node_id": node_id,
                        "project_id": project_id,
                        "node_type": spec["node_type"],
                        "name": spec["name"],
                        "description": spec.get("description", ""),
                        "first_scene": spec.get("first_scene"),
                        "last_scene": spec.get("last_scene"),
                        "universe_tags": spec.get("universe_tags", []),
                    }
                )

        existing_rels = {
            str(row.get("relationship_id")): row
            for row in (self.storage.get_universe_relationships(project_id) or [])
            if isinstance(row, dict) and str(row.get("relationship_id") or "")
        }
        rel_by_key: dict[tuple, str] = {}
        for rel_id, row in existing_rels.items():
            rel_by_key[
                (
                    str(row.get("from_node") or ""),
                    str(row.get("to_node") or ""),
                    str(row.get("relationship_type") or ""),
                )
            ] = rel_id
        rel_adopted: list[str] = []
        rel_created: list[str] = []
        for spec in rel_specs:
            from_id = key_to_id.get(spec["from_key"])
            to_id = key_to_id.get(spec["to_key"])
            if not from_id or not to_id:
                continue
            rel_type = spec["relationship_type"]
            rel_id = rel_by_key.get((from_id, to_id, rel_type))
            rel_needs_save = False
            if rel_id is None:
                rel_id = id_resolution.stable_relationship_id(project_id, from_id, to_id, rel_type)
                suffix = 0
                while rel_id in existing_rels or rel_id in rel_created:
                    suffix += 1
                    rel_id = f"{rel_id}-{suffix}"
                rel_created.append(rel_id)
                rel_needs_save = True
            else:
                rel_adopted.append(rel_id)
                stored_rel = existing_rels[rel_id]
                if (
                    str(stored_rel.get("from_node") or "") != from_id
                    or str(stored_rel.get("to_node") or "") != to_id
                    or str(stored_rel.get("relationship_type") or "") != rel_type
                    or str(stored_rel.get("description") or "")
                    != str(spec.get("description", ""))
                ):
                    updated.append(rel_id)
                    rel_needs_save = True
                else:
                    unchanged.append(rel_id)
            if rel_needs_save:
                self.storage.save_universe_relationship(
                    {
                        "relationship_id": rel_id,
                        "project_id": project_id,
                        "from_node": from_id,
                        "to_node": to_id,
                        "relationship_type": rel_type,
                        "description": spec.get("description", ""),
                    }
                )

        live_ids = set(adopted) | set(created)
        preserved_referenced: list[dict] = []
        preserved_unreferenced: list[str] = []
        finder = getattr(self.storage, "find_universe_node_references", None)
        for node_id in sorted(set(existing_nodes) - live_ids):
            refs: list[dict] = []
            if callable(finder):
                try:
                    refs = finder(project_id, node_id) or []
                except Exception:  # noqa: BLE001 — reference scan never blocks rebuild
                    refs = []
            if refs:
                tables = sorted({str(r.get("table") or "") for r in refs if isinstance(r, dict)})
                preserved_referenced.append({"node_id": node_id, "referencing": tables})
                logger.warning(
                    "UNIVERSE_NODE_PRESERVED | project_id=%s node_id=%s referencing=%s",
                    project_id,
                    node_id,
                    ",".join(tables),
                )
            else:
                preserved_unreferenced.append(node_id)

        nodes = [
            UniverseNode(
                **{
                    **row,
                    "universe_tags": (
                        json.loads(row["universe_tags"])
                        if isinstance(row.get("universe_tags"), str)
                        else row.get("universe_tags", [])
                    ),
                }
            )
            for row in (self.storage.get_universe_nodes(project_id) or [])
        ]
        relationships = [
            UniverseRelationship(**row)
            for row in (self.storage.get_universe_relationships(project_id) or [])
        ]
        return {
            "project_id": project_id,
            "nodes": nodes,
            "relationships": relationships,
            "adopted": adopted,
            "created": created,
            "reused_ids": len(adopted),
            "created_ids": len(
                [i for i in created if i not in existing_nodes]
                + [i for i in rel_created if i not in existing_rels]
            ),
            "updated_ids": sorted(set(updated)),
            "unchanged_ids": sorted(set(unchanged)),
            "deleted_nodes": [],
            "ambiguous_keys": ambiguous,
            "preserved_referenced": preserved_referenced,
            "preserved_unreferenced": preserved_unreferenced,
            "rel_adopted": rel_adopted,
            "rel_created": rel_created,
        }

    @staticmethod
    def _node_content_differs(stored: dict, spec: dict) -> bool:
        """True when the stored row's derived fields differ from the spec.

        Compares only rebuild-derived content (never created_at); tags are
        normalized because storage may hold them as a JSON string.
        """
        stored_tags = stored.get("universe_tags", [])
        if isinstance(stored_tags, str):
            try:
                stored_tags = json.loads(stored_tags)
            except (json.JSONDecodeError, TypeError):
                stored_tags = []
        return (
            str(stored.get("node_type") or "") != str(spec.get("node_type") or "")
            or str(stored.get("name") or "") != str(spec.get("name") or "")
            or str(stored.get("description") or "") != str(spec.get("description", ""))
            or (stored.get("first_scene") or "") != (spec.get("first_scene") or "")
            or (stored.get("last_scene") or "") != (spec.get("last_scene") or "")
            or list(stored_tags or []) != list(spec.get("universe_tags", []) or [])
        )

    def _existing_node_key(self, project_id: str, row: dict) -> tuple:
        node_type = str(row.get("node_type") or "")
        name = str(row.get("name") or "")
        base = id_resolution.stable_universe_key(project_id, node_type, name)
        if node_type.lower() == "location":
            return (*base, str(row.get("first_scene") or ""))
        return base

    def _mint_stable_node_id(
        self, project_id: str, node_type: str, name: str, taken: set[str]
    ) -> str:
        candidate = id_resolution.stable_node_id(project_id, node_type, name)
        suffix = 0
        while candidate in taken:
            suffix += 1
            candidate = f"{id_resolution.stable_node_id(project_id, node_type, name)}-{suffix}"
        return candidate

    def repair_universe_aliases(self, project_id: str, old_nodes: list[dict]) -> dict:
        """Seed ``universe_id_aliases`` from pre-wipe node rows (explicit repair).

        Each old row maps to the current node sharing its exact
        ``(project_id, node_type, normalized name)`` only when exactly one
        candidate exists — zero or multiple candidates produce a report entry
        and no alias. Never modifies reference rows.
        """
        current = [
            row
            for row in (self.storage.get_universe_nodes(project_id) or [])
            if isinstance(row, dict)
        ]
        live_ids = {str(row.get("node_id") or "") for row in current}
        aliased: list[dict] = []
        ambiguous: list[dict] = []
        unresolvable: list[str] = []
        for old in old_nodes or []:
            if not isinstance(old, dict):
                continue
            old_id = str(old.get("node_id") or "").strip()
            if not old_id or old_id in live_ids:
                continue
            target, reason = id_resolution.match_alias_candidate(current, old)
            if target:
                self.storage.save_universe_id_alias(
                    project_id, old_id, target, "explicit repair: pre-wipe ID retained as alias"
                )
                aliased.append({"old_node_id": old_id, "current_node_id": target})
            elif reason == "ambiguous":
                ambiguous.append({"old_node_id": old_id})
            else:
                unresolvable.append(old_id)
        return {
            "project_id": project_id,
            "aliased": aliased,
            "ambiguous": ambiguous,
            "unresolvable": unresolvable,
        }

    async def auto_populate(self, project_id: str) -> UniverseGraph:
        logger.info(f"Auto-populating universe graph for project {project_id}")

        report = self.rebuild_universe_graph_from_scenes(project_id)
        nodes: list[UniverseNode] = list(report["nodes"])
        rels: list[UniverseRelationship] = list(report["relationships"])

        if not nodes:
            try:
                arc_analysis = await script_intelligence_service.analyze_character_arcs(project_id)
                memory_data = director_memory_service.get_memory(project_id)
                char_memory_entries = memory_data.get("characters", [])
                stored = {
                    str(row.get("node_id")): row
                    for row in (self.storage.get_universe_nodes(project_id) or [])
                    if isinstance(row, dict) and str(row.get("node_id") or "")
                }
                by_key: dict[tuple, list[str]] = {}
                for node_id, row in stored.items():
                    by_key.setdefault(self._existing_node_key(project_id, row), []).append(node_id)
                taken = set(stored)
                created_nodes = {}

                for char_prof in arc_analysis.characters:
                    key = id_resolution.stable_universe_key(project_id, "character", char_prof.name)
                    matches = by_key.get(key, [])
                    if len(matches) == 1:
                        node_id = matches[0]
                    elif not matches:
                        node_id = self._mint_stable_node_id(project_id, "character", char_prof.name, taken)
                        taken.add(node_id)
                    else:
                        node_id = sorted(matches)[0]
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

                stored_rels = {
                    (
                        str(row.get("from_node") or ""),
                        str(row.get("to_node") or ""),
                        str(row.get("relationship_type") or ""),
                    ): str(row.get("relationship_id"))
                    for row in (self.storage.get_universe_relationships(project_id) or [])
                    if isinstance(row, dict) and str(row.get("relationship_id") or "")
                }
                for rel in arc_analysis.relationships:
                    from_id = created_nodes.get(rel.character_a.lower())
                    to_id = created_nodes.get(rel.character_b.lower())
                    if from_id and to_id:
                        relationship_id = stored_rels.get((from_id, to_id, "co-occurrence"))
                        if relationship_id is None:
                            relationship_id = id_resolution.stable_relationship_id(
                                project_id, from_id, to_id, "co-occurrence"
                            )
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
        try:
            report = self.rebuild_universe_graph_from_scenes(project_id, scenes=scenes)
            logger.info(
                f"Auto-populated {len(report['nodes'])} nodes and "
                f"{len(report['relationships'])} relationships for {project_id} "
                f"(adopted={len(report['adopted'])} created={len(report['created'])} "
                f"preserved_referenced={len(report['preserved_referenced'])})"
            )
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
        except Exception:
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
