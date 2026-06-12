import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.models.production_scan import ProductionScanReport, ProductionScanFlag, Severity, ReadinessLevel
from app.services.memory import memory_service
from app.services.universe_graph_service import universe_graph_service
from app.services.script_intelligence_service import script_intelligence_service
from app.services.director_memory_service import director_memory_service
from app.data.storage import get_storage

logger = logging.getLogger("studio-production-scan")

class ProductionScanService:
    def __init__(self):
        self.storage = get_storage("sqlite")

    async def run_scan(self, project_id: str) -> ProductionScanReport:
        logger.info(f"Running production readiness scan for project {project_id}")
        
        # 1. Fetch data
        memory_data = memory_service.read_memory(project_id)
        scenes_mem = memory_data.get("scenes", {})
        characters_mem = memory_data.get("characters", {})
        
        graph = await universe_graph_service.get_graph(project_id)
        dm_bundle = director_memory_service.get_memory(project_id)
        
        flags = []
        
        # 2. Location Conflicts
        self._scan_location_conflicts(scenes_mem, flags)
        
        # 3. Prop Inconsistencies
        self._scan_prop_inconsistencies(scenes_mem, flags)
        
        # 4. Character Continuity
        await self._scan_character_continuity(project_id, scenes_mem, characters_mem, flags)
        
        # 5. Schedule Complexity
        self._scan_schedule_complexity(scenes_mem, flags)
        
        # 6. Script Gaps
        self._scan_script_gaps(scenes_mem, flags)
        
        # 7. Unresolved Story Threads
        self._scan_unresolved_threads(dm_bundle, flags)
        
        # 8. Determine readiness level and clear_to_shoot
        readiness_level: ReadinessLevel = "ready"
        clear_to_shoot = True
        
        if any(f.severity == "blocker" for f in flags):
            readiness_level = "major_issues"
            clear_to_shoot = False
        elif any(f.severity == "warning" for f in flags):
            readiness_level = "minor_issues"
            
        # 9. Generate Summary
        summary = self._generate_summary(readiness_level, flags)
        
        report = ProductionScanReport(
            scan_id=f"scan-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            readiness_level=readiness_level,
            flags=flags,
            clear_to_shoot=clear_to_shoot,
            summary=summary
        )
        
        return report

    def _scan_location_conflicts(self, scenes_mem: Dict[str, Any], flags: List[ProductionScanFlag]):
        locations: Dict[str, List[Dict]] = {}
        for scene_id, scene in scenes_mem.items():
            loc = scene.get("location_name")
            if not loc: continue
            if loc not in locations:
                locations[loc] = []
            locations[loc].append({"id": scene_id, "time": scene.get("time_of_day"), "weather": scene.get("weather")})
            
        for loc, scene_list in locations.items():
            times = set(s["time"] for s in scene_list if s["time"])
            weathers = set(s["weather"] for s in scene_list if s["weather"])
            
            if len(times) > 1 or len(weathers) > 1:
                affected = [s["id"] for s in scene_list]
                flags.append(ProductionScanFlag(
                    flag_type="Location conflict",
                    severity="warning",
                    description=f"The {loc} location is used under different conditions ({', '.join(filter(None, times))}/{', '.join(filter(None, weathers))}) across multiple scenes.",
                    affected_scenes=affected,
                    co_director_note="Same-location variance without production notes increases setup time and continuity risk."
                ))

    def _scan_prop_inconsistencies(self, scenes_mem: Dict[str, Any], flags: List[ProductionScanFlag]):
        # Check for props mentioned in one scene but missing in adjacent scenes if they seem significant
        # For now, we'll flag any prop that only appears in one scene as a "note"
        prop_usage: Dict[str, List[str]] = {}
        for scene_id, scene in scenes_mem.items():
            for prop in scene.get("props_in_scene", []):
                if prop not in prop_usage:
                    prop_usage[prop] = []
                prop_usage[prop].append(scene_id)
        
        for prop, scenes in prop_usage.items():
            if len(scenes) == 1:
                flags.append(ProductionScanFlag(
                    flag_type="Prop inconsistency",
                    severity="note",
                    description=f"The prop '{prop}' appears in scene {scenes[0]} but is never seen again.",
                    affected_scenes=scenes,
                    co_director_note="One-off props can feel unmotivated unless they are consumed or lost within the scene."
                ))

    async def _scan_character_continuity(self, project_id: str, scenes_mem: Dict[str, Any], characters_mem: Dict[str, Any], flags: List[ProductionScanFlag]):
        try:
            arc_analysis = await script_intelligence_service.analyze_character_arcs(project_id)
            for gap in arc_analysis.arc_gaps:
                flags.append(ProductionScanFlag(
                    flag_type="Character continuity",
                    severity="warning",
                    description=f"{gap.character_name} disappears between scene {gap.gap_start_scene} and {gap.gap_end_scene} with no costume or state change transition.",
                    affected_scenes=[gap.gap_start_scene, gap.gap_end_scene],
                    co_director_note=gap.advisory or "Character continuity gaps risk breaking audience immersion."
                ))
        except Exception as e:
            logger.debug(f"Character arc scan skipped: {e}")

    def _scan_schedule_complexity(self, scenes_mem: Dict[str, Any], flags: List[ProductionScanFlag]):
        for scene_id, scene in scenes_mem.items():
            chars = scene.get("character_positions", {})
            if len(chars) >= 5:
                flags.append(ProductionScanFlag(
                    flag_type="Schedule complexity",
                    severity="warning",
                    description=f"Scene {scene_id} requires a large cast ensemble ({len(chars)} characters).",
                    affected_scenes=[scene_id],
                    co_director_note="Ensemble scenes significantly increase shoot duration and blocking complexity."
                ))

    def _scan_script_gaps(self, scenes_mem: Dict[str, Any], flags: List[ProductionScanFlag]):
        for scene_id, scene in scenes_mem.items():
            # Check for placeholder text or missing content
            notes = scene.get("director_notes", "").lower()
            if not notes or "placeholder" in notes or "todo" in notes or "tbd" in notes:
                flags.append(ProductionScanFlag(
                    flag_type="Script gap",
                    severity="blocker",
                    description=f"Scene {scene_id} has incomplete production notes or placeholder dialogue.",
                    affected_scenes=[scene_id],
                    co_director_note="We can't shoot a placeholder. Resolve the scene beats before moving to set."
                ))

    def _scan_unresolved_threads(self, dm_bundle: Dict[str, Any], flags: List[ProductionScanFlag]):
        # Unresolved story threads can be inferred from notes or debates that haven't reached a conclusion
        # or themes that were introduced but haven't 'surfaced' recently.
        notes = dm_bundle.get("notes", [])
        for note in notes:
            if "unresolved" in note.get("note", "").lower() or "question" in note.get("note", "").lower():
                flags.append(ProductionScanFlag(
                    flag_type="Unresolved story thread",
                    severity="warning",
                    description=f"Subplot/Note '{note.get('headline') or 'Untitled'}' remains unresolved in the current draft.",
                    affected_scenes=[],
                    co_director_note="Open story threads without a payoff lead to a weak climax. Either resolve it or cut it."
                ))

    def _generate_summary(self, level: ReadinessLevel, flags: List[ProductionScanFlag]) -> str:
        if level == "ready" and not flags:
            return "The project is fully prepared for production. Continuity is tight, locations are consistent, and all story threads have been accounted for. Clear to shoot."
        
        if level == "ready":
            return "The project is in good shape with only minor logistical notes. We are clear to move to production once the team reviews the advisory flags."
        
        if level == "minor_issues":
            return f"The scan identified {len(flags)} minor issues, primarily around continuity and location variance. These should be addressed during pre-production to avoid delays on set."
        
        blockers = [f for f in flags if f.severity == "blocker"]
        return f"Production is currently blocked by {len(blockers)} critical issues. Script gaps and incomplete scene data must be resolved before we can clear this project to shoot."

production_scan_service = ProductionScanService()
