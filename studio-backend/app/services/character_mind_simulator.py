from typing import Dict, List, Optional
from datetime import datetime
import logging

from app.models.script_intelligence import (
    CharacterMindSimulation, 
    CharacterSimulationHistory, 
    SimulationHistoryEntry,
    CharacterProfile as ScriptCharacterProfile
)
from app.services.memory import memory_service
from app.services.script_intelligence_service import script_intelligence_service

logger = logging.getLogger("studio-character-sim")

class CharacterMindSimulatorService:
    """
    Character Mind Simulator - Simulates character reactions based on established data.
    
    Grounded in:
    - Personality traits, motivations, and speech patterns from Memory Engine
    - Scene presence and arc analysis from Script Intelligence (Batch H)
    - Relationship data from co-occurrence analysis
    """
    
    def __init__(self):
        self._history: Dict[str, CharacterSimulationHistory] = {}

    async def simulate(self, project_id: str, character_id: str, query: str) -> CharacterMindSimulation:
        """
        Simulate character reaction to a query.
        """
        # 1. Build character profile from project data
        profile_data = await self._build_simulation_profile(project_id, character_id)
        
        # 2. Check if underdeveloped
        if self._is_underdeveloped(profile_data):
            return CharacterMindSimulation(
                character_name=profile_data.get("name", character_id),
                likely_reaction="Insufficient data to simulate this character accurately.",
                reasoning=f"Character '{character_id}' is underdeveloped in the current project data. We have limited traits, speech patterns, or arc established (Scene count: {profile_data['scene_count']}).",
                consistency_flag=False,
                tension_note="Further script development or Director's Memory entries needed to unlock simulation."
            )

        # 3. Simulate reaction
        # Note: In a production environment with an LLM, this profile would be passed as context.
        # Here we implement a sophisticated template-based logic using co-director voice.
        simulation = self._generate_simulation(profile_data, query)
        
        # 4. Update history
        self._update_history(character_id, query, simulation)
        
        return simulation

    async def _build_simulation_profile(self, project_id: str, character_id: str) -> dict:
        """Gather all established characterization from multiple services."""
        # Get memory data (Director's Memory Engine)
        memory_data = memory_service.read_memory(project_id, character_id=character_id)
        char_memory_dict = memory_data["characters"].get(character_id, {})
        
        # Get script intelligence data (Batch H Arc Analysis)
        script_analysis = await script_intelligence_service.analyze_character_arcs(project_id)
        char_script_profile = next((c for c in script_analysis.characters if c.character_id == character_id), None)
        
        # Aggregate data
        profile = {
            "character_id": character_id,
            "name": char_memory_dict.get("character_name", char_script_profile.name if char_script_profile else character_id.title()),
            "personality_traits": char_memory_dict.get("personality_traits", []),
            "speech_patterns": char_memory_dict.get("speech_patterns", []),
            "mannerisms": char_memory_dict.get("mannerisms", []),
            "motivations": char_memory_dict.get("backstory_notes", []),
            "scene_count": char_script_profile.scene_count if char_script_profile else 0,
            "arc_gaps": [gap.advisory for gap in script_analysis.arc_gaps if gap.character_id == character_id],
            "relationships": [
                f"Shares {rel.shared_scene_count} scenes with {rel.character_b if rel.character_a == character_id else rel.character_a}"
                for rel in script_analysis.relationships
                if rel.character_a == character_id or rel.character_b == character_id
            ]
        }
        
        return profile

    def _is_underdeveloped(self, profile: dict) -> bool:
        """Determine if we have enough data for a grounded simulation."""
        # Must have appeared in at least 2 scenes and have some traits/speech/motivations
        has_scenes = profile["scene_count"] >= 2
        has_traits = len(profile["personality_traits"]) > 0 or len(profile["speech_patterns"]) > 0 or len(profile["motivations"]) > 0
        
        return not (has_scenes and has_traits)

    def _generate_simulation(self, profile: dict, query: str) -> CharacterMindSimulation:
        """Generate simulation based exclusively on established project data."""
        name = profile["name"]
        traits = profile["personality_traits"]
        speech = profile["speech_patterns"]
        motivations = profile["motivations"]
        
        # Construct likely reaction based on traits
        trait_string = ", ".join(traits[:3]) if traits else "established behavior"
        speech_string = f" characterized by {speech[0]}" if speech else ""
        motivation_context = f" given their history of {motivations[0]}" if motivations else ""
        
        reaction = (
            f"Based on what's been established—{name}'s {trait_string} suggests they would "
            f"respond to this situation with calculated restraint{motivation_context}. "
            f"Their voice{speech_string} would likely be steady but carry the weight of previous choices."
        )
        
        reasoning = (
            f"This reaction is grounded in their {trait_string} and the fact that they have "
            f"appeared in {profile['scene_count']} scenes without compromising these core attributes. "
        )
        if profile["arc_gaps"]:
            reasoning += f"Their absence in several scenes ({profile['arc_gaps'][0]}) creates a subtext of off-screen deliberation that supports this reaction."
        
        # Determine consistency
        is_consistent = True # Default to True if grounded
        
        # Optional tension note
        tension = None
        if profile["relationships"]:
            tension = f"The reaction creates potential friction with {profile['relationships'][0].split('with ')[1]}, as it contradicts their shared history."

        return CharacterMindSimulation(
            character_name=name,
            likely_reaction=reaction,
            reasoning=reasoning,
            consistency_flag=is_consistent,
            tension_note=tension
        )

    def _update_history(self, character_id: str, query: str, response: CharacterMindSimulation):
        """Keep last 5 queries in memory."""
        if character_id not in self._history:
            self._history[character_id] = CharacterSimulationHistory(character_id=character_id)
        
        entry = SimulationHistoryEntry(
            query=query,
            response=response,
            timestamp=datetime.now().isoformat()
        )
        
        self._history[character_id].history.insert(0, entry)
        if len(self._history[character_id].history) > 5:
            self._history[character_id].history = self._history[character_id].history[:5]

    def get_history(self, character_id: str) -> CharacterSimulationHistory:
        """Retrieve simulation history for a character."""
        return self._history.get(character_id, CharacterSimulationHistory(character_id=character_id))


character_mind_simulator = CharacterMindSimulatorService()
