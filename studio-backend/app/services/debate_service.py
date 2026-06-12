import random
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.models.debate import CoDirectorDebate, DebateRoundRequest, AgentResponse
from app.services.director_memory_service import director_memory_service
from app.services.project_store import project_store

class DebateService:
    def __init__(self):
        self.agent_metadata = {
            "Writer": {"perspective": "Narrative structure, character voice, and dialogue integrity.", "icon": "typewriter"},
            "Director": {"perspective": "Overall tone, emotional arc, and pacing.", "icon": "clapperboard"},
            "Cinematographer": {"perspective": "Visual language, lighting motifs, and composition logic.", "icon": "camera"},
            "Editor": {"perspective": "Rhythmic flow, information sequencing, and scene necessity.", "icon": "film_reel"},
            "Producer": {"perspective": "Resource implications, schedule complexity, and logistics.", "icon": "slate"},
        }

    def generate_debate(self, request: DebateRoundRequest) -> CoDirectorDebate:
        project_id = request.project_id
        query = request.query
        
        memory = director_memory_service.get_memory(project_id)
        
        # Get context
        themes = memory.get("themes", [])
        symbols = memory.get("symbols", [])
        characters = memory.get("characters", [])
        
        relevant_theme = self._find_relevant_entry(query, themes) or "thematic resonance"
        relevant_symbol = self._find_relevant_entry(query, symbols) or "visual motif"
        relevant_character = self._find_relevant_entry(query, characters) or "the protagonist"

        # Generate agent responses
        agent_responses = []
        
        # 1. Writer Agent
        agent_responses.append(self._analyze_writer(query, relevant_theme, relevant_character))
        
        # 2. Director Agent
        agent_responses.append(self._analyze_director(query, relevant_theme))
        
        # 3. Cinematographer Agent
        agent_responses.append(self._analyze_cinematographer(query, relevant_symbol))
        
        # 4. Editor Agent
        agent_responses.append(self._analyze_editor(query))
        
        # 5. Producer Agent
        agent_responses.append(self._analyze_producer(query))

        # Find agreement and conflict
        points_of_agreement, points_of_conflict = self._identify_consensus_and_friction(agent_responses)

        # Generate Synthesis (A24 Voice)
        synthesis = self._generate_a24_synthesis(query, agent_responses, points_of_agreement, points_of_conflict, relevant_theme)

        debate_id = f"debate_{uuid.uuid4().hex[:8]}"
        
        debate = CoDirectorDebate(
            debate_id=debate_id,
            project_id=project_id,
            scene_id=request.scene_id,
            act_number=request.act_number,
            is_full_project=request.is_full_project,
            query=query,
            agent_responses=agent_responses,
            points_of_agreement=points_of_agreement,
            points_of_conflict=points_of_conflict,
            synthesis=synthesis,
            filmmaker_prerogative="The decision, as always, is the filmmaker's."
        )
        
        # Save to project memory
        director_memory_service.save_entry(project_id, "debates", debate.model_dump())
        
        return debate

    def _analyze_writer(self, query: str, theme: str, character: str) -> AgentResponse:
        positions = ["Pro-dialogue reduction", "Character-driven resistance", "Structural pivot recommended"]
        pos = random.choice(positions)
        return AgentResponse(
            agent_name="Writer Agent",
            perspective=self.agent_metadata["Writer"]["perspective"],
            position=pos,
            reasoning=f"The dialogue in this beat feels slightly too explanatory. If we lean into {character}'s silence, we honor the {theme} more effectively. The subtext is already doing the heavy lifting.",
            recommendation="Trim the last three lines of dialogue. Let the reaction sell the turn."
        )

    def _analyze_director(self, query: str, theme: str) -> AgentResponse:
        return AgentResponse(
            agent_name="Director Agent",
            perspective=self.agent_metadata["Director"]["perspective"],
            position="Protecting emotional dread",
            reasoning=f"We're risking a premature release of tension. The {theme} needs a moment of absolute stasis before the break. If we move too fast, the audience won't feel the weight of the consequence.",
            recommendation="Lengthen the transition beat. Hold on the empty frame for two seconds longer than planned."
        )

    def _analyze_cinematographer(self, query: str, symbol: str) -> AgentResponse:
        return AgentResponse(
            agent_name="Cinematographer Agent",
            perspective=self.agent_metadata["Cinematographer"]["perspective"],
            position="Visual motif reinforcement",
            reasoning=f"The lighting should mirror the character's internal fractured state. By using the {symbol} in the background, we create a visual anchor for the psychological dread.",
            recommendation="Shift the key light to a 45-degree rim to emphasize the silhouette. Keep the foreground in deep shadow."
        )

    def _analyze_editor(self, query: str) -> AgentResponse:
        return AgentResponse(
            agent_name="Editor Agent",
            perspective=self.agent_metadata["Editor"]["perspective"],
            position="Rhythmic tightening",
            reasoning="The scene handoff is lagging. We're lingering on the exit when the emotional data is already transmitted. We need to cut on the look, not the movement.",
            recommendation="Hard cut to the next scene exactly 12 frames earlier. Kill the trailing ambient sound."
        )

    def _analyze_producer(self, query: str) -> AgentResponse:
        return AgentResponse(
            agent_name="Producer Agent",
            perspective=self.agent_metadata["Producer"]["perspective"],
            position="Logistical pragmatism",
            reasoning="The proposed visual complexity for this scene adds four hours to the setup. Given our current overage on Act 2, this setup puts the night exterior at risk.",
            recommendation="Simplify the camera move. Use a fixed tripod setup with a slow zoom instead of the dolly track."
        )

    def _identify_consensus_and_friction(self, responses: List[AgentResponse]) -> tuple[List[str], List[str]]:
        agreements = [
            "Consensus on the need for increased emotional stakes in this transition.",
            "Alignment between Writing and Direction on character-driven silence."
        ]
        conflicts = [
            "Direct conflict between Cinematographer's visual complexity and Producer's schedule constraints.",
            "Divergence between Director's desire for stasis and Editor's push for rhythmic speed."
        ]
        return random.sample(agreements, 1), random.sample(conflicts, 1)

    def _generate_a24_synthesis(self, query: str, responses: List[AgentResponse], agreements: List[str], conflicts: List[str], theme: str) -> str:
        synthesis_templates = [
            "The room is divided by the pull between structural purity and logistical gravity. While we agree the {theme} is served by silence, the clock remains our most honest antagonist. We're chasing a haunting stasis, yet the rhythm demands we move. Choose the silence that costs the least, but earns the most.",
            "There is a beautiful friction here between the visual fractured state we're painting and the cold reality of the production clock. We alignment on the subtext, but our methods diverge on the speed of the cut. The {theme} lives in the gaps we're afraid to leave. Trust the dread, but respect the timeline.",
        ]
        return random.choice(synthesis_templates).format(theme=theme)

    def _find_relevant_entry(self, query: str, entries: List[Dict[str, Any]]) -> Optional[str]:
        query_lower = query.lower()
        for entry in entries:
            name = (entry.get("theme") or entry.get("symbol") or entry.get("character") or entry.get("name") or "").lower()
            if name and name in query_lower:
                return name
        return None

debate_service = DebateService()
