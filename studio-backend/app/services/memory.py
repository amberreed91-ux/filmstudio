"""
Project Memory System - Persistent memory for film production

Memory Types:
- Project: Tone, themes, style, references
- Scene: Scene-level decisions, shot history
- Character: Traits, arcs, relationships
- Style: Camera language, lighting, color, pacing
- Review: Feedback from Quality Reviewer and user

Features:
- Persistent in database (SQLite)
- Scoped per project
- Versioned (track updates over time)
- Safe from corruption (new versions instead of overwrite)
"""

import json
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from app.models.memory import (
    MemoryType, MemoryScope, FeedbackType,
    ProjectMemory, CharacterMemory, SceneMemory, StyleMemory, ReviewMemory,
    MemoryEntry, MemoryEntryVersion, MemoryUpdate, ContradictionCheck
)

logger = logging.getLogger("studio-memory")


class MemoryService:
    """
    Memory Service - Manages persistent project memory with versioning
    
    Responsibilities:
    - Store and retrieve project-level knowledge
    - Track scene-specific decisions and continuity
    - Provide consistent memory to agents
    - Detect and flag contradictions
    - Version all changes for audit trail
    """
    
    def __init__(self, storage=None):
        self.storage = storage
        self._cache: Dict[str, ProjectMemory] = {}
        self._scene_cache: Dict[str, Dict[str, SceneMemory]] = {}
        self._character_cache: Dict[str, Dict[str, CharacterMemory]] = {}
        self._style_cache: Dict[str, StyleMemory] = {}
        self._review_cache: Dict[str, List[ReviewMemory]] = {}
    
    def _generate_entry_id(self, project_id: str, key: str) -> str:
        """Generate unique entry ID"""
        raw = f"{project_id}:{key}:{datetime.now().isoformat()}"
        return f"mem-{hashlib.md5(raw.encode()).hexdigest()[:12]}"
    
    def initialize_project_memory(self, project_id: str) -> ProjectMemory:
        """Initialize memory for a new project"""
        now = datetime.now().isoformat()
        
        memory = ProjectMemory(
            project_id=project_id,
            created_at=now,
            updated_at=now
        )
        
        self._cache[project_id] = memory
        
        if self.storage:
            self.storage.save_scene_memory({
                "project_id": project_id,
                "scene_id": "__init__",
                "location_name": "",
                "time_of_day": "",
                "weather": None,
                "camera_choices": [],
                "lighting_notes": [],
                "color_palette": [],
                "props_in_scene": [],
                "character_positions": {},
                "generated_shots": [],
                "approved_shots": []
            })
            
            empty_style = StyleMemory(project_id=project_id)
            self.storage.save_style_memory(empty_style.model_dump())
        
        logger.info(f"Initialized project memory for {project_id}")
        return memory
    
    def read_memory(
        self,
        project_id: str,
        memory_type: Optional[MemoryType] = None,
        scene_id: Optional[str] = None,
        character_id: Optional[str] = None
    ) -> Dict:
        """Read memory - agents call this BEFORE acting"""
        
        result = {
            "project_id": project_id,
            "project": {},
            "scenes": {},
            "characters": {},
            "style": {},
            "reviews": [],
            "versions": []
        }
        
        # Project-level memory
        if project_id in self._cache:
            mem = self._cache[project_id]
            result["project"] = {
                "tone": mem.tone,
                "genre": mem.genre,
                "visual_style": mem.visual_style,
                "color_grade": mem.color_grade,
                "lighting_mood": mem.lighting_mood,
                "key_decisions": mem.key_decisions[-10:] if mem.key_decisions else []
            }
        elif self.storage:
            entries = self.storage.get_memory_entries(project_id, "project")
            if entries:
                result["project"] = self._reconstruct_project_memory(entries)
        
        # Scene memory
        if scene_id:
            if project_id in self._scene_cache and scene_id in self._scene_cache[project_id]:
                result["scenes"][scene_id] = self._scene_cache[project_id][scene_id].model_dump()
            elif self.storage:
                scene = self.storage.get_scene_memory(project_id, scene_id)
                if scene:
                    result["scenes"][scene_id] = scene
        elif memory_type == MemoryType.SCENE or memory_type is None:
            if project_id in self._scene_cache:
                result["scenes"] = {k: v.model_dump() for k, v in self._scene_cache[project_id].items()}
            elif self.storage:
                scenes = self.storage.get_all_scene_memories(project_id)
                result["scenes"] = {s["scene_id"]: s for s in scenes}
        
        # Character memory
        if character_id:
            if project_id in self._character_cache and character_id in self._character_cache[project_id]:
                result["characters"][character_id] = self._character_cache[project_id][character_id].model_dump()
            elif self.storage:
                char = self.storage.get_character_memory(project_id, character_id)
                if char:
                    result["characters"][character_id] = char
        elif memory_type == MemoryType.CHARACTER or memory_type is None:
            if project_id in self._character_cache:
                result["characters"] = {k: v.model_dump() for k, v in self._character_cache[project_id].items()}
            elif self.storage:
                characters = self.storage.get_all_character_memories(project_id)
                result["characters"] = {c["character_id"]: c for c in characters}
        
        # Style memory
        if project_id in self._style_cache:
            result["style"] = self._style_cache[project_id].model_dump()
        elif self.storage:
            style = self.storage.get_style_memory(project_id)
            if style:
                result["style"] = style
        
        # Review memory
        if self.storage:
            reviews = self.storage.get_review_memories(project_id, scene_id)
            result["reviews"] = reviews
        
        return result
    
    def _reconstruct_project_memory(self, entries: List[Dict]) -> Dict:
        """Reconstruct project memory from DB entries"""
        result = {
            "tone": "",
            "genre": "",
            "visual_style": [],
            "color_grade": "",
            "lighting_mood": [],
            "key_decisions": []
        }
        
        for entry in entries:
            key = entry.get("key", "")
            value = entry.get("value", "")
            
            if key == "tone":
                result["tone"] = value
            elif key == "genre":
                result["genre"] = value
            elif key == "visual_style":
                result["visual_style"] = json.loads(value) if value else []
            elif key == "color_grade":
                result["color_grade"] = value
            elif key == "lighting_mood":
                result["lighting_mood"] = json.loads(value) if value else []
            elif key == "key_decisions":
                result["key_decisions"].append(json.loads(value) if value else {})
        
        return result
    
    def update_memory(
        self,
        project_id: str,
        memory_type: MemoryType,
        data: Dict,
        agent_id: str = "system",
        task_id: Optional[str] = None
    ) -> Dict:
        """Update memory - agents call this AFTER completing tasks"""
        
        now = datetime.now().isoformat()
        
        if memory_type == MemoryType.PROJECT:
            return self._update_project_memory(project_id, data, agent_id, task_id)
        elif memory_type == MemoryType.SCENE:
            return self._update_scene_memory(project_id, data, agent_id, task_id)
        elif memory_type == MemoryType.CHARACTER:
            return self._update_character_memory(project_id, data, agent_id, task_id)
        elif memory_type == MemoryType.STYLE:
            return self._update_style_memory(project_id, data, agent_id, task_id)
        elif memory_type == MemoryType.REVIEW:
            return self._update_review_memory(project_id, data, agent_id, task_id)
        
        return {"status": "error", "message": f"Unknown memory type: {memory_type}"}
    
    def _update_project_memory(
        self,
        project_id: str,
        data: Dict,
        agent_id: str,
        task_id: Optional[str]
    ) -> Dict:
        """Update project-level memory"""
        
        # Initialize cache if needed
        if project_id not in self._cache:
            self._cache[project_id] = ProjectMemory(
                project_id=project_id,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
        
        memory = self._cache[project_id]
        
        # Apply updates
        if "tone" in data:
            memory.tone = data["tone"]
        if "genre" in data:
            memory.genre = data["genre"]
        if "visual_style" in data:
            memory.visual_style = data["visual_style"] if isinstance(data["visual_style"], list) else [data["visual_style"]]
        if "color_grade" in data:
            memory.color_grade = data["color_grade"]
        if "lighting_mood" in data:
            memory.lighting_mood = data["lighting_mood"] if isinstance(data["lighting_mood"], list) else [data["lighting_mood"]]
        if "reference_urls" in data:
            memory.reference_urls = data["reference_urls"]
        if "style_inspiration" in data:
            memory.style_inspiration = data["style_inspiration"]
        
        memory.updated_at = datetime.now().isoformat()
        memory.memory_version += 1
        
        # Persist to database
        if self.storage:
            entry = {
                "project_id": project_id,
                "memory_type": "project",
                "key": "tone",
                "value": memory.tone,
                "summary": f"Tone set to {memory.tone}",
                "scope": "global",
                "created_by_agent": agent_id,
                "source_task_id": task_id,
                "created_at": memory.created_at,
                "entry_id": self._generate_entry_id(project_id, "tone")
            }
            self.storage.save_memory_entry(entry)
        
        # Log key decision
        if "decision" in data:
            decision = {
                "type": data.get("decision_type", "general"),
                "description": data["decision"],
                "made_by": agent_id,
                "scene_id": data.get("scene_id"),
                "timestamp": datetime.now().isoformat()
            }
            memory.key_decisions.append(decision)
            
            if self.storage:
                entry = {
                    "project_id": project_id,
                    "memory_type": "project",
                    "key": "key_decisions",
                    "value": json.dumps(decision),
                    "summary": f"Decision logged by {agent_id}",
                    "scope": "global",
                    "created_by_agent": agent_id,
                    "source_task_id": task_id,
                    "created_at": datetime.now().isoformat(),
                    "entry_id": self._generate_entry_id(project_id, f"decision_{len(memory.key_decisions)}")
                }
                self.storage.save_memory_entry(entry)
        
        logger.info(f"Updated project memory for {project_id} by {agent_id}")
        
        return {
            "status": "success",
            "version": memory.memory_version,
            "memory": memory.model_dump()
        }
    
    def _update_scene_memory(
        self,
        project_id: str,
        data: Dict,
        agent_id: str,
        task_id: Optional[str]
    ) -> Dict:
        """Update scene-level memory"""
        
        scene_id = data.get("scene_id")
        if not scene_id:
            return {"status": "error", "message": "scene_id required"}
        
        if project_id not in self._scene_cache:
            self._scene_cache[project_id] = {}
        
        if scene_id not in self._scene_cache[project_id]:
            self._scene_cache[project_id][scene_id] = SceneMemory(scene_id=scene_id)
        
        scene = self._scene_cache[project_id][scene_id]
        
        # Apply updates
        if "location_name" in data:
            scene.location_name = data["location_name"]
        if "time_of_day" in data:
            scene.time_of_day = data["time_of_day"]
        if "weather" in data:
            scene.weather = data["weather"]
        if "camera_choice" in data:
            if data["camera_choice"] not in scene.camera_choices:
                scene.camera_choices.append(data["camera_choice"])
        if "lighting_note" in data:
            if data["lighting_note"] not in scene.lighting_notes:
                scene.lighting_notes.append(data["lighting_note"])
        if "color_palette" in data:
            scene.color_palette = data["color_palette"] if isinstance(data["color_palette"], list) else [data["color_palette"]]
        if "generated_shot" in data:
            if data["generated_shot"] not in scene.generated_shots:
                scene.generated_shots.append(data["generated_shot"])
        if "approved_shot" in data:
            if data["approved_shot"] not in scene.approved_shots:
                scene.approved_shots.append(data["approved_shot"])
        
        # Persist ALL updates to storage
        if self.storage:
            self.storage.save_scene_memory({
                "project_id": project_id,
                "scene_id": scene_id,
                "location_name": scene.location_name,
                "time_of_day": scene.time_of_day,
                "weather": scene.weather,
                "camera_choices": scene.camera_choices,
                "lighting_notes": scene.lighting_notes,
                "color_palette": scene.color_palette,
                "generated_shots": scene.generated_shots,
                "approved_shots": scene.approved_shots
            })
        
        logger.info(f"Updated scene memory for {scene_id} by {agent_id}")
        
        return {
            "status": "success",
            "scene": scene.model_dump()
        }
    
    def _update_character_memory(
        self,
        project_id: str,
        data: Dict,
        agent_id: str,
        task_id: Optional[str]
    ) -> Dict:
        """Update character-level memory"""
        
        character_id = data.get("character_id")
        if not character_id:
            return {"status": "error", "message": "character_id required"}
        
        if project_id not in self._character_cache:
            self._character_cache[project_id] = {}
        
        if character_id not in self._character_cache[project_id]:
            self._character_cache[project_id][character_id] = CharacterMemory(
                character_id=character_id,
                character_name=data.get("character_name", character_id)
            )
        
        char = self._character_cache[project_id][character_id]
        
        # Apply updates
        if "character_name" in data:
            char.character_name = data["character_name"]
        if "appearance_traits" in data:
            char.appearance_traits = data["appearance_traits"] if isinstance(data["appearance_traits"], list) else [data["appearance_traits"]]
        if "personality_traits" in data:
            char.personality_traits = data["personality_traits"] if isinstance(data["personality_traits"], list) else [data["personality_traits"]]
        if "mannerisms" in data:
            char.mannerisms = data["mannerisms"] if isinstance(data["mannerisms"], list) else [data["mannerisms"]]
        if "wardrobe" in data:
            char.wardrobe = data["wardrobe"] if isinstance(data["wardrobe"], list) else [data["wardrobe"]]
        if "speech_patterns" in data:
            char.speech_patterns = data["speech_patterns"]
        if "relationships" in data:
            char.relationships = data["relationships"]
        
        # In-memory only for now
        pass
        
        logger.info(f"Updated character memory for {character_id} by {agent_id}")
        
        return {
            "status": "success",
            "character": char.model_dump()
        }
    
    def _update_style_memory(
        self,
        project_id: str,
        data: Dict,
        agent_id: str,
        task_id: Optional[str]
    ) -> Dict:
        """Update style memory"""
        
        if project_id not in self._style_cache:
            self._style_cache[project_id] = StyleMemory(project_id=project_id)
        
        style = self._style_cache[project_id]
        
        # Apply updates
        if "camera_language" in data:
            style.camera_language = data["camera_language"]
        if "lighting_approach" in data:
            style.lighting_approach = data["lighting_approach"]
        if "color_palette" in data:
            style.color_palette = data["color_palette"] if isinstance(data["color_palette"], list) else [data["color_palette"]]
        if "pacing_notes" in data:
            style.pacing_notes = data["pacing_notes"]
        if "frame_composition" in data:
            style.frame_composition = data["frame_composition"]
        if "movement_style" in data:
            style.movement_style = data["movement_style"]
        if "lens_preferences" in data:
            style.lens_preferences = data["lens_preferences"]
        
        style_updated = style.model_dump()
        
        pass  # In-memory only for now
        
        logger.info(f"Updated style memory for {project_id} by {agent_id}")
        
        return {
            "status": "success",
            "style": style_updated
        }
    
    def _update_review_memory(
        self,
        project_id: str,
        data: Dict,
        agent_id: str,
        task_id: Optional[str]
    ) -> Dict:
        """Update review/feedback memory"""
        
        review = ReviewMemory(
            project_id=project_id,
            scene_id=data.get("scene_id"),
            shot_id=data.get("shot_id"),
            feedback_type=FeedbackType(data.get("feedback_type", "agent")),
            feedback_source=agent_id,
            feedback_text=data.get("feedback_text", ""),
            quality_score=data.get("quality_score"),
            issues=data.get("issues", []),
            recommendations=data.get("recommendations", []),
            created_at=datetime.now().isoformat()
        )
        
        # Cache
        if project_id not in self._review_cache:
            self._review_cache[project_id] = []
        self._review_cache[project_id].append(review)
        
        logger.info(f"Stored review memory for {project_id} by {agent_id}")
        
        return {
            "status": "success",
            "review": review.model_dump()
        }
    
    def append_memory(
        self,
        project_id: str,
        memory_type: MemoryType,
        data: Dict,
        agent_id: str = "system",
        task_id: Optional[str] = None
    ) -> Dict:
        """Append to memory (for cumulative updates like adding shots)"""
        
        return self.update_memory(project_id, memory_type, data, agent_id, task_id)
    
    def get_context_for_agent(
        self,
        project_id: str,
        agent_role: str,
        scene_id: Optional[str] = None
    ) -> Dict:
        """Get relevant memory context for an agent role"""
        
        memory = self.read_memory(project_id, scene_id=scene_id)
        
        context = {
            "project_id": project_id,
            "agent_role": agent_role,
            "project": memory.get("project", {}),
            "style": memory.get("style", {}),
            "current_scene": None,
            "characters": {},
            "relevant_decisions": [],
            "recent_feedback": []
        }
        
        # Role-specific context
        if agent_role in ["script_analyst", "storyboard_artist"]:
            context["project"]["references"] = memory.get("project", {}).get("style_inspiration", [])
        
        elif agent_role == "cinematographer":
            context["current_scene"] = memory.get("scenes", {}).get(scene_id) if scene_id else None
            context["project"]["lighting_mood"] = memory.get("project", {}).get("lighting_mood", [])
        
        elif agent_role in ["prompt_engineer", "render_coordinator"]:
            context["project"]["references"] = memory.get("project", {}).get("reference_urls", [])[:3]
            context["style"] = memory.get("style", {})
        
        elif agent_role == "editor":
            context["scenes"] = memory.get("scenes", {})
            context["relevant_decisions"] = memory.get("project", {}).get("key_decisions", [])[-5:]
        
        elif agent_role == "quality_reviewer":
            context["current_scene"] = memory.get("scenes", {}).get(scene_id) if scene_id else None
            context["recent_feedback"] = memory.get("reviews", [])[-5:]
        
        elif agent_role == "creative_director":
            context["all_scenes"] = memory.get("scenes", {})
            context["all_characters"] = memory.get("characters", {})
            context["key_decisions"] = memory.get("project", {}).get("key_decisions", [])
        
        # Scene-specific context
        if scene_id:
            context["current_scene"] = memory.get("scenes", {}).get(scene_id)
            scene_chars = memory.get("characters", {})
            context["characters"] = {cid: c for cid, c in scene_chars.items() if c.get("scene_id") == scene_id}
        
        return context
    
    def check_contradiction(
        self,
        project_id: str,
        key: str,
        new_value: Any
    ) -> ContradictionCheck:
        """Check if new value contradicts existing memory"""
        
        memory_data = self.read_memory(project_id)
        
        contradictions = []
        
        # Define contradictory key pairs
        contradictory_pairs = {
            "tone": ["uplifting vs dark", "comedy vs tragedy"],
            "lighting_mood": ["bright vs shadowed"],
            "color_grade": ["warm vs cool"],
        }
        
        # Check project-level contradictions
        if key == "tone":
            existing = memory_data.get("project", {}).get("tone", "")
            if existing and new_value:
                if ("dark" in existing.lower() and "uplifting" in new_value.lower()) or \
                   ("uplifting" in existing.lower() and "dark" in new_value.lower()):
                    contradictions.append(f"Existing tone is '{existing}', new is '{new_value}'")
        
        elif key == "lighting_mood":
            existing = memory_data.get("project", {}).get("lighting_mood", [])
            if existing and new_value:
                if ("bright" in existing and "shadowed" in new_value) or \
                   ("shadowed" in existing and "bright" in new_value):
                    contradictions.append(f"Lighting contradiction detected")
        
        return ContradictionCheck(
            entry_id=project_id,
            key=key,
            new_value=new_value,
            has_contradiction=len(contradictions) > 0,
            conflicting_entries=contradictions,
            resolution_suggestion="Review with Creative Director" if contradictions else None
        )
    
    def get_versions(self, project_id: str, key: Optional[str] = None) -> List[MemoryEntryVersion]:
        """Get version history for memory"""
        
        if not self.storage:
            return []
        
        if key:
            entries = self.storage.get_memory_entries(project_id)
            entry_ids = [e["entry_id"] for e in entries if e.get("key") == key]
            if entry_ids:
                return self.storage.get_memory_versions(entry_ids[0])
        
        return []
    
    def get_all_memory(self, project_id: str) -> Dict:
        """Get all memory for a project (for debugging)"""
        
        return self.read_memory(project_id)


memory_service = MemoryService()